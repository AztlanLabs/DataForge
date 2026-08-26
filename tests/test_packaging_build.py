"""TICK-930 — Packaging: platform maps, spec files, asset references, build verification.

Acceptance:
- macOS platform maps resolve to the darwin hidden-import/exclude sets
- Release spec contains no hardcoded /mnt/ paths
- Debug spec references PyQt5 (not the retired Tkinter/ttkbootstrap stack)
- WiX executable reference matches build_exe.py output (no dataforge-engine.exe)
- nfpm assets exist on disk
- build_exe.py has a working onedir profile
- Platform excludes reference real module names
"""
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent

BUILD_EXE = PROJECT_ROOT / "build_exe.py"
RELEASE_SPEC = PROJECT_ROOT / "buildspec" / "release" / "DataForge.spec"
DEBUG_SPEC = PROJECT_ROOT / "buildspec" / "debug" / "DataForge-debug.spec"
WXS = PROJECT_ROOT / "packaging" / "wix" / "Product.wxs"
NFPM = PROJECT_ROOT / "packaging" / "nfpm.yaml"


@pytest.fixture(scope="module")
def build_exe():
    spec = importlib.util.spec_from_file_location("build_exe_test", str(BUILD_EXE))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_exe_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestPlatformMapping:
    def test_macos_platform_maps_correctly(self, build_exe, monkeypatch):
        """GIVEN detect_platform() on macOS WHEN platform lookups run THEN
        the darwin hidden-import/exclude sets resolve."""
        monkeypatch.setattr(build_exe.sys, "platform", "darwin")
        assert build_exe.detect_platform() == "macos"
        imports = build_exe.get_platform_hidden_imports("macos")
        excludes = build_exe.get_platform_excludes("macos")
        assert "Foundation" in imports, f"macos hidden imports missing, got {imports}"
        assert "AppKit" in imports
        assert "gtk" in excludes, f"macos excludes missing, got {excludes}"
        assert "win32api" not in excludes

    def test_darwin_alias_still_resolves(self, build_exe):
        """GIVEN a 'darwin' platform string WHEN lookups run THEN the same
        sets resolve (both spellings must work)."""
        assert build_exe.get_platform_hidden_imports("darwin") == build_exe.get_platform_hidden_imports("macos")

    def test_unknown_platform_falls_back_to_defaults(self, build_exe):
        """GIVEN an unknown platform name WHEN lookups run THEN empty tuples
        are returned (no crash)."""
        assert build_exe.get_platform_hidden_imports("amiga") == ()
        assert build_exe.get_platform_excludes("amiga") == ()

    def test_detect_platform_known_values(self, build_exe):
        """GIVEN known sys.platform values WHEN detect_platform runs THEN the
        canonical names are returned."""
        assert build_exe.detect_platform() in ("linux", "windows", "macos")

    def test_platform_excludes_are_valid(self, build_exe):
        """GIVEN every platform's excludes WHEN checked THEN each name is a
        real (importable or known) module name."""
        all_excludes = set()
        for platform_key in ("windows", "darwin", "macos", "linux"):
            all_excludes.update(build_exe.get_platform_excludes(platform_key))
        for name in all_excludes:
            try:
                spec = importlib.util.find_spec(name.split(".")[0])
            except (ImportError, ValueError, ModuleNotFoundError):
                spec = None
            # Excludes may reference modules not installed on this host, so
            # a None spec is acceptable — but the name must at least be a
            # plausible dotted module identifier.
            assert name and all(part.isidentifier() for part in name.split(".")), (
                f"invalid module name in excludes: {name}"
            )
            assert spec is not None or name in (
                "win32api", "win32con", "win32gui", "gtk", "gi", "win32file", "win32pipe", "pywintypes",
            ), f"excluded module '{name}' is not a known module"


class TestSpecFiles:
    def test_release_spec_no_hardcoded_paths(self):
        """GIVEN the release spec WHEN read THEN no /mnt/ or user paths."""
        text = RELEASE_SPEC.read_text()
        assert "/mnt/" not in text, "release spec must not contain hardcoded /mnt/ paths"
        assert "run_ui.py" in text
        assert "SPECPATH" in text

    def test_debug_spec_references_pyqt5(self):
        """GIVEN the debug spec WHEN read THEN it uses PyQt5 imports."""
        text = DEBUG_SPEC.read_text()
        assert "PyQt5" in text, "debug spec must reference PyQt5"
        assert "PyQt5.QtWidgets" in text
        assert "ttkbootstrap" not in text, "debug spec must not reference the retired Tk stack"
        assert "PIL.ImageTk" not in text
        assert "SPECPATH" in text

    def test_debug_spec_no_hardcoded_paths(self):
        """GIVEN the debug spec WHEN read THEN no OneDrive/user paths."""
        text = DEBUG_SPEC.read_text()
        assert "C:\\Users" not in text
        assert "OneDrive" not in text


class TestWix:
    def test_wix_executable_matches_build(self):
        """GIVEN Product.wxs WHEN read THEN it references the executable the
        build script actually creates."""
        text = WXS.read_text()
        assert "DataForge.exe" in text
        assert "dataforge-engine.exe" not in text, (
            "WiX must not reference dataforge-engine.exe (build_exe.py does not build it)"
        )
        assert "StartService" not in text


class TestNfpmAssets:
    def test_nfpm_asset_exists(self):
        """GIVEN nfpm.yaml WHEN parsed THEN every referenced asset exists."""
        cfg = yaml.safe_load(NFPM.read_text())
        missing = []
        for entry in cfg.get("contents", []):
            src = entry.get("src", "")
            if src.startswith("packaging/") or src.startswith("dist/"):
                if not src.startswith("dist/"):
                    if not (PROJECT_ROOT / src).exists():
                        missing.append(src)
        assert not missing, f"nfpm references missing assets: {missing}"

    def test_nfpm_icon_reference_exists(self):
        """GIVEN nfpm.yaml icon entry WHEN checked THEN the SVG asset exists."""
        cfg = yaml.safe_load(NFPM.read_text())
        icon_entries = [c for c in cfg["contents"] if "icons" in c.get("dst", "")]
        assert icon_entries, "nfpm must install an icon"
        for entry in icon_entries:
            assert (PROJECT_ROOT / entry["src"]).exists(), (
                f"icon asset missing: {entry['src']}"
            )


class TestBuildExeProfile:
    def test_build_exe_has_onedir_profile(self, build_exe):
        """GIVEN build_exe.py WHEN onedir_args called THEN valid PyInstaller
        args are returned."""
        args = build_exe.onedir_args("linux")
        assert isinstance(args, list)
        assert "--onedir" in args
        assert "--name=DataForge" in args
        assert any("--distpath=" in a and a.endswith("dist/onedir") for a in args)

    def test_build_exe_common_args_platform_aware(self, build_exe):
        """GIVEN build_common_args WHEN run for macos THEN darwin imports and
        excludes are present in the args."""
        args = build_exe.build_common_args("onedir", "DataForge", "macos")
        joined = " ".join(args)
        assert "--hidden-import=Foundation" in joined
        assert "--hidden-import=AppKit" in joined
        assert "--exclude-module=gtk" in joined
        assert "--exclude-module=win32api" not in joined