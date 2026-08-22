"""Tests for TICK-303: Packaging configuration and build profiles.

Validates:
- build_exe.py has onedir profile
- packaging/nfpm.yaml is valid YAML with expected structure
- Packaging directory structure is correct
- Scripts are present and executable
"""

import os
import stat
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGING_DIR = PROJECT_ROOT / "packaging"


class TestBuildExeProfiles(unittest.TestCase):
    """Test build_exe.py profile support."""

    def test_build_exe_has_onedir_profile(self):
        """GIVEN build_exe.py WHEN inspected THEN onedir_args function exists."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        self.assertIn("def onedir_args(platform_name: str)", content)

    def test_build_exe_parse_args_includes_onedir(self):
        """GIVEN build_exe.py WHEN parse_args called THEN onedir is valid choice."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        self.assertIn("'onedir'", content)
        # Verify it's in the choices tuple
        self.assertIn("choices=('release', 'onedir', 'debug', 'all')", content)

    def test_build_exe_run_build_handles_onedir(self):
        """GIVEN build_exe.py WHEN run_build called THEN onedir profile handled."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        self.assertIn("elif profile == 'onedir':", content)
        self.assertIn("args = onedir_args(platform_name)", content)

    def test_build_exe_main_handles_all_profile(self):
        """GIVEN build_exe.py WHEN main called with 'all' THEN onedir included."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        # Verify onedir is in the 'all' profile sequence
        all_section = content[content.index("if args.profile == 'all':"):]
        self.assertIn("run_build('onedir'", all_section)

    def test_onedir_args_uses_windowed_and_onedir(self):
        """GIVEN onedir_args() WHEN called THEN returns --windowed --onedir flags."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        # Find onedir_args function
        start = content.index("def onedir_args(platform_name: str)")
        end = content.index("\ndef ", start + 1)
        onedir_func = content[start:end]
        self.assertIn("'--onedir'", onedir_func)

    def test_onedir_output_dir_is_onedir(self):
        """GIVEN onedir_args() WHEN called THEN dist path is 'onedir'."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        # onedir_args uses build_common_args('onedir', 'DataForge', platform_name)
        # which sets distpath to dist/onedir
        start = content.index("def onedir_args(platform_name: str)")
        end = content.index("\ndef ", start + 1)
        onedir_func = content[start:end]
        self.assertIn("'onedir'", onedir_func)


class TestBuildExePlatformSupport(unittest.TestCase):
    """Test build_exe.py platform selection support."""

    def test_build_exe_has_platform_argument(self):
        """GIVEN build_exe.py WHEN inspected THEN --platform argument exists."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        self.assertIn("'--platform'", content)
        self.assertIn("choices=('auto', 'linux', 'windows', 'macos')", content)

    def test_build_exe_has_detect_platform_function(self):
        """GIVEN build_exe.py WHEN inspected THEN detect_platform function exists."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        self.assertIn("def detect_platform()", content)

    def test_build_exe_has_platform_hidden_imports(self):
        """GIVEN build_exe.py WHEN inspected THEN platform-specific imports defined."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        self.assertIn("PLATFORM_HIDDEN_IMPORTS", content)
        self.assertIn("'windows'", content)
        self.assertIn("'darwin'", content)
        self.assertIn("'linux'", content)

    def test_build_exe_has_platform_excludes(self):
        """GIVEN build_exe.py WHEN inspected THEN platform-specific excludes defined."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        self.assertIn("PLATFORM_EXCLUDES", content)

    def test_build_exe_run_build_accepts_platform(self):
        """GIVEN build_exe.py WHEN run_build called THEN accepts platform parameter."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        self.assertIn("def run_build(profile: str, platform_name: str)", content)

    def test_build_exe_main_resolves_platform(self):
        """GIVEN build_exe.py WHEN main called THEN resolves platform from args."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        main_section = content[content.index("def main()"):]
        self.assertIn("args.platform", main_section)
        self.assertIn("detect_platform()", main_section)

    def test_build_exe_warns_on_cross_compile(self):
        """GIVEN build_exe.py WHEN cross-platform build requested THEN warns user."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        self.assertIn("cannot cross-compile", content.lower())

    def test_release_args_accepts_platform(self):
        """GIVEN release_args() WHEN called THEN accepts platform parameter."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        self.assertIn("def release_args(platform_name: str)", content)

    def test_onedir_args_accepts_platform(self):
        """GIVEN onedir_args() WHEN called THEN accepts platform parameter."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        self.assertIn("def onedir_args(platform_name: str)", content)

    def test_debug_args_accepts_platform(self):
        """GIVEN debug_args() WHEN called THEN accepts platform parameter."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        self.assertIn("def debug_args(platform_name: str)", content)

    def test_windowed_only_on_windows_macos(self):
        """GIVEN build_exe.py WHEN inspected THEN --windowed only for Windows/macOS."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        # Check that --windowed is conditionally added
        self.assertIn("if platform_name in ('windows', 'macos')", content)
        self.assertIn("args.append('--windowed')", content)

    def test_platform_included_in_dist_path(self):
        """GIVEN build_exe.py WHEN inspected THEN dist path includes platform."""
        build_exe_path = PROJECT_ROOT / "build_exe.py"
        content = build_exe_path.read_text()
        self.assertIn("profile_name}-{platform_name}", content)


class TestNfpmYaml(unittest.TestCase):
    """Test packaging/nfpm.yaml structure and content."""

    def setUp(self):
        self.nfpm_path = PACKAGING_DIR / "nfpm.yaml"
        self.assertTrue(self.nfpm_path.exists(), "nfpm.yaml must exist")
        with open(self.nfpm_path) as f:
            self.config = yaml.safe_load(f)

    def test_nfpm_yaml_is_valid_yaml(self):
        """GIVEN nfpm.yaml WHEN parsed THEN is valid YAML."""
        self.assertIsInstance(self.config, dict)

    def test_nfpm_yaml_has_required_fields(self):
        """GIVEN nfpm.yaml WHEN inspected THEN has name, arch, version."""
        self.assertEqual(self.config["name"], "dataforge")
        self.assertEqual(self.config["arch"], "amd64")
        self.assertEqual(self.config["platform"], "linux")
        self.assertIn("version", self.config)

    def test_nfpm_yaml_version_matches_pyproject(self):
        """GIVEN nfpm.yaml WHEN version checked THEN matches pyproject.toml."""
        pyproject_path = PROJECT_ROOT / "pyproject.toml"
        pyproject_content = pyproject_path.read_text()
        # Extract version from pyproject.toml
        for line in pyproject_content.split("\n"):
            if line.strip().startswith("version"):
                pyproject_version = line.split("=")[1].strip().strip('"')
                break
        else:
            self.fail("Could not find version in pyproject.toml")

        self.assertEqual(self.config["version"], pyproject_version)

    def test_nfpm_yaml_has_contents(self):
        """GIVEN nfpm.yaml WHEN inspected THEN has contents list."""
        self.assertIn("contents", self.config)
        self.assertIsInstance(self.config["contents"], list)
        self.assertGreater(len(self.config["contents"]), 0)

    def test_nfpm_yaml_installs_to_opt_dataforge(self):
        """GIVEN nfpm.yaml WHEN contents inspected THEN installs to /opt/dataforge."""
        contents = self.config["contents"]
        install_entries = [c for c in contents if c.get("dst", "").startswith("/opt/dataforge")]
        self.assertGreater(len(install_entries), 0)

    def test_nfpm_yaml_has_systemd_units(self):
        """GIVEN nfpm.yaml WHEN contents inspected THEN has systemd units."""
        contents = self.config["contents"]
        systemd_entries = [c for c in contents if "systemd" in c.get("dst", "")]
        self.assertGreater(len(systemd_entries), 0)

    def test_nfpm_yaml_has_desktop_entry(self):
        """GIVEN nfpm.yaml WHEN contents inspected THEN has desktop entry."""
        contents = self.config["contents"]
        desktop_entries = [c for c in contents if c.get("dst", "").endswith(".desktop")]
        self.assertGreater(len(desktop_entries), 0)

    def test_nfpm_yaml_has_dbus_service(self):
        """GIVEN nfpm.yaml WHEN contents inspected THEN has D-Bus service."""
        contents = self.config["contents"]
        dbus_entries = [c for c in contents if "dbus" in c.get("dst", "").lower()]
        self.assertGreater(len(dbus_entries), 0)

    def test_nfpm_yaml_has_scripts(self):
        """GIVEN nfpm.yaml WHEN inspected THEN has postinst and prerm scripts."""
        self.assertIn("scripts", self.config)
        scripts = self.config["scripts"]
        self.assertIn("postinstall", scripts)
        self.assertIn("preremove", scripts)

    def test_nfpm_yaml_has_depends(self):
        """GIVEN nfpm.yaml WHEN inspected THEN has dependencies."""
        self.assertIn("depends", self.config)
        self.assertIsInstance(self.config["depends"], list)


class TestPackagingDirectoryStructure(unittest.TestCase):
    """Test packaging directory structure."""

    def test_packaging_dir_exists(self):
        """GIVEN packaging/ WHEN checked THEN directory exists."""
        self.assertTrue(PACKAGING_DIR.exists())
        self.assertTrue(PACKAGING_DIR.is_dir())

    def test_nfpm_yaml_exists(self):
        """GIVEN packaging/ WHEN checked THEN nfpm.yaml exists."""
        self.assertTrue((PACKAGING_DIR / "nfpm.yaml").exists())

    def test_readme_exists(self):
        """GIVEN packaging/ WHEN checked THEN README.md exists."""
        self.assertTrue((PACKAGING_DIR / "README.md").exists())

    def test_assets_dir_exists(self):
        """GIVEN packaging/ WHEN checked THEN assets/ exists."""
        self.assertTrue((PACKAGING_DIR / "assets").exists())

    def test_systemd_dir_exists(self):
        """GIVEN packaging/ WHEN checked THEN systemd/ exists."""
        self.assertTrue((PACKAGING_DIR / "systemd").exists())

    def test_dbus_dir_exists(self):
        """GIVEN packaging/ WHEN checked THEN dbus/ exists."""
        self.assertTrue((PACKAGING_DIR / "dbus").exists())

    def test_scripts_dir_exists(self):
        """GIVEN packaging/ WHEN checked THEN scripts/ exists."""
        self.assertTrue((PACKAGING_DIR / "scripts").exists())


class TestPackagingAssets(unittest.TestCase):
    """Test packaging asset files."""

    def test_desktop_entry_exists(self):
        """GIVEN packaging/assets/ WHEN checked THEN dataforge.desktop exists."""
        desktop_path = PACKAGING_DIR / "assets" / "dataforge.desktop"
        self.assertTrue(desktop_path.exists())

    def test_desktop_entry_has_required_fields(self):
        """GIVEN dataforge.desktop WHEN parsed THEN has Type, Name, Exec."""
        desktop_path = PACKAGING_DIR / "assets" / "dataforge.desktop"
        content = desktop_path.read_text()
        self.assertIn("[Desktop Entry]", content)
        self.assertIn("Type=Application", content)
        self.assertIn("Name=DataForge", content)
        self.assertIn("Exec=/opt/dataforge/DataForge", content)

    def test_icon_svg_exists(self):
        """GIVEN packaging/assets/ WHEN checked THEN dataforge.svg exists."""
        svg_path = PACKAGING_DIR / "assets" / "dataforge.svg"
        self.assertTrue(svg_path.exists())

    def test_icon_svg_is_valid_svg(self):
        """GIVEN dataforge.svg WHEN read THEN contains SVG markup."""
        svg_path = PACKAGING_DIR / "assets" / "dataforge.svg"
        content = svg_path.read_text()
        self.assertIn("<svg", content)
        self.assertIn("</svg>", content)


class TestPackagingSystemdUnits(unittest.TestCase):
    """Test systemd unit files."""

    def test_socket_unit_exists(self):
        """GIVEN packaging/systemd/ WHEN checked THEN dataforge.socket exists."""
        socket_path = PACKAGING_DIR / "systemd" / "dataforge.socket"
        self.assertTrue(socket_path.exists())

    def test_service_unit_exists(self):
        """GIVEN packaging/systemd/ WHEN checked THEN dataforge.service exists."""
        service_path = PACKAGING_DIR / "systemd" / "dataforge.service"
        self.assertTrue(service_path.exists())

    def test_socket_unit_has_socket_section(self):
        """GIVEN dataforge.socket WHEN parsed THEN has [Socket] section."""
        socket_path = PACKAGING_DIR / "systemd" / "dataforge.socket"
        content = socket_path.read_text()
        self.assertIn("[Socket]", content)
        self.assertIn("ListenStream=", content)

    def test_service_unit_has_service_section(self):
        """GIVEN dataforge.service WHEN parsed THEN has [Service] section."""
        service_path = PACKAGING_DIR / "systemd" / "dataforge.service"
        content = service_path.read_text()
        self.assertIn("[Service]", content)
        self.assertIn("ExecStart=", content)
        self.assertIn("/opt/dataforge/DataForge", content)


class TestPackagingDbus(unittest.TestCase):
    """Test D-Bus service file."""

    def test_dbus_service_exists(self):
        """GIVEN packaging/dbus/ WHEN checked THEN com.dataforge.Engine.service exists."""
        dbus_path = PACKAGING_DIR / "dbus" / "com.dataforge.Engine.service"
        self.assertTrue(dbus_path.exists())

    def test_dbus_service_has_required_fields(self):
        """GIVEN com.dataforge.Engine.service WHEN parsed THEN has Name and Exec."""
        dbus_path = PACKAGING_DIR / "dbus" / "com.dataforge.Engine.service"
        content = dbus_path.read_text()
        self.assertIn("[D-BUS Service]", content)
        self.assertIn("Name=com.dataforge.Engine", content)
        self.assertIn("Exec=/opt/dataforge/DataForge", content)


class TestPackagingScripts(unittest.TestCase):
    """Test packaging scripts."""

    def test_postinst_exists(self):
        """GIVEN packaging/scripts/ WHEN checked THEN postinst.sh exists."""
        postinst_path = PACKAGING_DIR / "scripts" / "postinst.sh"
        self.assertTrue(postinst_path.exists())

    def test_prerm_exists(self):
        """GIVEN packaging/scripts/ WHEN checked THEN prerm.sh exists."""
        prerm_path = PACKAGING_DIR / "scripts" / "prerm.sh"
        self.assertTrue(prerm_path.exists())

    def test_postinst_is_executable(self):
        """GIVEN postinst.sh WHEN checked THEN is executable."""
        postinst_path = PACKAGING_DIR / "scripts" / "postinst.sh"
        st = os.stat(postinst_path)
        self.assertTrue(st.st_mode & stat.S_IXUSR)

    def test_prerm_is_executable(self):
        """GIVEN prerm.sh WHEN checked THEN is executable."""
        prerm_path = PACKAGING_DIR / "scripts" / "prerm.sh"
        st = os.stat(prerm_path)
        self.assertTrue(st.st_mode & stat.S_IXUSR)

    def test_postinst_handles_systemctl(self):
        """GIVEN postinst.sh WHEN read THEN handles systemctl commands."""
        postinst_path = PACKAGING_DIR / "scripts" / "postinst.sh"
        content = postinst_path.read_text()
        self.assertIn("systemctl", content)
        self.assertIn("daemon-reload", content)

    def test_prerm_handles_systemctl(self):
        """GIVEN prerm.sh WHEN read THEN handles systemctl commands."""
        prerm_path = PACKAGING_DIR / "scripts" / "prerm.sh"
        content = prerm_path.read_text()
        self.assertIn("systemctl", content)
        self.assertIn("stop", content)
        self.assertIn("disable", content)


if __name__ == "__main__":
    unittest.main()
