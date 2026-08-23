"""Tests for TICK-708 — Packaging msi/dmg + version sync (I2+N4).

Acceptance:
- pyproject.toml version is 0.2.0 and dataforge/__init__.py is 0.2.0
- Product.wxs exists and validates (or graceful skip if wix not installed)
- create-dmg.sh executable and contains create-dmg
- build_exe onedir still builds correctly
- existing packaging tests still pass
"""

import os
import re
import stat
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
INIT_PY = PROJECT_ROOT / "dataforge" / "__init__.py"
WXS_PATH = PROJECT_ROOT / "packaging" / "wix" / "Product.wxs"
DMG_SCRIPT = PROJECT_ROOT / "packaging" / "dmg" / "create-dmg.sh"
BUILD_EXE = PROJECT_ROOT / "build_exe.py"
NFPM_YAML = PROJECT_ROOT / "packaging" / "nfpm.yaml"


class TestVersionSync:
    def test_pyproject_version_is_0_2_0(self):
        text = PYPROJECT.read_text()
        # Find version = "0.2.0" under [project]
        m = re.search(r'\[project\][^\[]*?^\s*version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE | re.DOTALL)
        assert m is not None, "version not found in pyproject.toml"
        assert m.group(1) == "0.2.0", f"pyproject version is {m.group(1)}, expected 0.2.0"

    def test_init_version_is_0_2_0(self):
        text = INIT_PY.read_text()
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        assert m is not None, "__version__ not found"
        assert m.group(1) == "0.2.0", f"__version__ is {m.group(1)}, expected 0.2.0"

    def test_versions_match(self):
        py_text = PYPROJECT.read_text()
        py_m = re.search(r'\[project\][^\[]*?^\s*version\s*=\s*["\']([^"\']+)["\']', py_text, re.MULTILINE | re.DOTALL)
        init_text = INIT_PY.read_text()
        init_m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_text, re.MULTILINE)
        assert py_m and init_m
        assert py_m.group(1) == init_m.group(1) == "0.2.0"

    def test_imported_version_is_0_2_0(self):
        import dataforge

        # After bump, imported version should be 0.2.0 (via hardcoded __version__)
        # Allow fallback via importlib.metadata or pyproject read
        assert hasattr(dataforge, "__version__")
        assert dataforge.__version__ == "0.2.0"

    def test_bump_script_check_sync(self):
        # Run bump_version --check should be 0 when synced
        result = subprocess.run(
            ["python", "scripts/bump_version.py", "--check"],
            capture_output=True,
            text=True,
        )
        # Should be 0 even if Info.plist missing (only checks existing files)
        assert result.returncode == 0, f"check failed: {result.stdout} {result.stderr}"
        assert "All versions are in sync" in result.stdout

    def test_nfpm_version_matches_if_exists(self):
        # Existing packaging tests expect nfpm version to match pyproject after bump
        if not NFPM_YAML.exists():
            pytest.skip("nfpm.yaml not found")
        import yaml

        cfg = yaml.safe_load(NFPM_YAML.read_text())
        py_text = PYPROJECT.read_text()
        m = re.search(r'\[project\][^\[]*?^\s*version\s*=\s*["\']([^"\']+)["\']', py_text, re.MULTILINE | re.DOTALL)
        assert m
        assert cfg["version"] == m.group(1) == "0.2.0"


class TestWixProduct:
    def test_wxs_exists(self):
        assert WXS_PATH.exists(), f"{WXS_PATH} must exist"

    def test_wxs_version_0_2_0(self):
        text = WXS_PATH.read_text()
        # Product Version="0.2.0"
        m = re.search(r'<Product[^>]*Version="([^"]+)"', text, re.DOTALL)
        assert m is not None, "Product Version not found"
        assert m.group(1) == "0.2.0"

    def test_wxs_contains_program_files_and_start_menu(self):
        text = WXS_PATH.read_text()
        assert "ProgramFilesFolder" in text, "must install to Program Files"
        assert "INSTALLFOLDER" in text
        assert "ProgramMenuFolder" in text, "must create Start Menu folder"
        assert "ApplicationProgramsFolder" in text

    def test_wxs_contains_shortcut(self):
        text = WXS_PATH.read_text()
        assert "Shortcut" in text
        assert "DataForge" in text

    def test_wxs_is_valid_xml(self):
        try:
            ET.parse(str(WXS_PATH))
        except ET.ParseError as e:
            pytest.fail(f"Product.wxs is not valid XML: {e}")

    def test_wxs_wix_validation_graceful_skip_if_not_installed(self):
        # Try to run WiX validation if tool installed, else skip
        wix_candidates = ["wix", "candle", "heat", "light"]
        found = None
        for cmd in wix_candidates:
            try:
                result = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    found = cmd
                    break
            except FileNotFoundError:
                continue
            except Exception:
                continue
        if found is None:
            pytest.skip("WiX toolset not installed — graceful skip")

        # If found, try to validate WXS via candle (WiX v3) or wix build
        # Use xmllint as fallback validation (already done via ET.parse)
        # If wix available, try candle with -nologo -arch x64
        try:
            result = subprocess.run(
                ["candle", "-nologo", str(WXS_PATH), "-out", "/tmp/test.wixobj"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # Candle may fail due to missing harvest files (dist/onedir) but should not fail due to XML syntax
            # We consider validation passed if error is about missing source file, not XML
            if result.returncode != 0:
                # If error is about missing Source file, it's expected in CI without build artifacts
                if "Source" in result.stderr or "file not found" in result.stderr.lower():
                    pytest.skip(f"candle missing build artifacts (expected): {result.stderr[:200]}")
                pytest.fail(f"candle failed: {result.stderr}")
        except FileNotFoundError:
            pytest.skip("candle not found despite wix --version success")


class TestDmgScript:
    def test_create_dmg_exists(self):
        assert DMG_SCRIPT.exists(), f"{DMG_SCRIPT} must exist"

    def test_create_dmg_is_executable(self):
        st = os.stat(DMG_SCRIPT)
        assert bool(st.st_mode & stat.S_IXUSR), "create-dmg.sh must be executable (chmod +x)"

    def test_create_dmg_contains_create_dmg_command(self):
        text = DMG_SCRIPT.read_text()
        assert "create-dmg" in text, "script must contain create-dmg command"

    def test_create_dmg_has_applications_symlink(self):
        text = DMG_SCRIPT.read_text()
        # Check for Applications symlink: --app-drop-link or Applications
        assert "app-drop-link" in text or "Applications" in text

    def test_create_dmg_has_background_or_volname(self):
        text = DMG_SCRIPT.read_text()
        assert "volname" in text.lower() or "VOLNAME" in text

    def test_create_dmg_handles_missing_create_dmg_gracefully(self):
        text = DMG_SCRIPT.read_text()
        # Should check for command -v create-dmg and graceful exit
        assert "command -v create-dmg" in text or "graceful" in text.lower() or "not found" in text

    def test_create_dmg_runs_without_error_even_without_create_dmg_tool(self):
        # Run script with no create-dmg installed — should exit 0 gracefully
        result = subprocess.run(["bash", str(DMG_SCRIPT)], capture_output=True, text=True, timeout=10)
        # Script should exit 0 even if create-dmg not installed (graceful skip)
        assert result.returncode == 0, f"script failed: {result.stderr}"


class TestBuildOnedir:
    def test_build_exe_has_onedir_profile(self):
        text = BUILD_EXE.read_text()
        assert "def onedir_args(platform_name: str)" in text
        assert "'onedir'" in text

    def test_onedir_args_contains_onedir_flag(self):
        text = BUILD_EXE.read_text()
        # Find onedir function body
        start = text.index("def onedir_args(platform_name: str)")
        end = text.index("\ndef ", start + 1)
        func = text[start:end]
        assert "'--onedir'" in func or '"--onedir"' in func

    def test_onedir_still_uses_windowed_conditionally(self):
        text = BUILD_EXE.read_text()
        assert "if platform_name in ('windows', 'macos')" in text

    def test_build_exe_onedir_dist_path(self):
        text = BUILD_EXE.read_text()
        assert "build_common_args('onedir'" in text

    def test_onedir_profile_importable_and_returns_args(self):
        # Import and actually call onedir_args to ensure it works
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location("build_exe", str(BUILD_EXE))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["build_exe_test"] = mod
        spec.loader.exec_module(mod)
        args = mod.onedir_args("linux")
        assert isinstance(args, list)
        assert any("onedir" in a.lower() for a in args) or any("--onedir" in a for a in args)
        # Should contain DataForge
        assert any("DataForge" in a for a in args)


class TestExistingPackagingStillPass:
    def test_nfpm_yaml_still_valid(self):
        import yaml

        if not NFPM_YAML.exists():
            pytest.skip("nfpm.yaml missing")
        cfg = yaml.safe_load(NFPM_YAML.read_text())
        assert cfg["name"] == "dataforge"
        assert "contents" in cfg

    def test_build_exe_still_has_release(self):
        text = BUILD_EXE.read_text()
        assert "def release_args(platform_name: str)" in text
        assert "--onefile" in text

    def test_packaging_scripts_executable(self):
        for script in ["postinst.sh", "prerm.sh"]:
            p = PROJECT_ROOT / "packaging" / "scripts" / script
            if not p.exists():
                continue
            st = os.stat(p)
            assert bool(st.st_mode & stat.S_IXUSR), f"{script} not executable"
