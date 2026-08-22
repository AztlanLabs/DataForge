"""Tests for version synchronization across pyproject.toml, dataforge/__init__.py, and installer files.

Spec: ``docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md §2``
Ticket: TICK-402
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
INIT_PATH = PROJECT_ROOT / "dataforge" / "__init__.py"

# Add scripts to path for import
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from bump_version import (  # noqa: E402
    check_versions,
    main,
    read_init_version,
    read_pyproject_version,
    write_init_version,
    write_pyproject_version,
)


class TestVersionReading:
    """Tests for reading version from files."""

    def test_read_pyproject_version(self):
        """GIVEN pyproject.toml WHEN reading version THEN returns version string."""
        version = read_pyproject_version()
        assert version is not None
        assert re.match(r"^\d+\.\d+\.\d+$", version)

    def test_read_init_version(self):
        """GIVEN dataforge/__init__.py WHEN reading version THEN returns version string."""
        version = read_init_version()
        assert version is not None
        assert re.match(r"^\d+\.\d+\.\d+$", version)

    def test_versions_match(self):
        """GIVEN pyproject.toml and __init__.py WHEN comparing versions THEN they match."""
        pyproject_ver = read_pyproject_version()
        init_ver = read_init_version()
        assert pyproject_ver == init_ver


class TestVersionWriting:
    """Tests for writing version to files."""

    def test_write_pyproject_version(self, tmp_path):
        """GIVEN a pyproject.toml WHEN writing version THEN version is updated."""
        # Create a temporary pyproject.toml
        test_file = tmp_path / "pyproject.toml"
        test_file.write_text('[project]\nname = "test"\nversion = "0.1.0"\n')

        with patch("bump_version.PYPROJECT_PATH", test_file):
            write_pyproject_version("0.2.0")
            content = test_file.read_text()
            assert 'version = "0.2.0"' in content

    def test_write_init_version(self, tmp_path):
        """GIVEN a __init__.py WHEN writing version THEN version is updated."""
        # Create a temporary __init__.py
        test_file = tmp_path / "__init__.py"
        test_file.write_text('__version__ = "0.1.0"\n')

        with patch("bump_version.INIT_PATH", test_file):
            write_init_version("0.2.0")
            content = test_file.read_text()
            assert '__version__ = "0.2.0"' in content

    def test_write_preserves_other_content(self, tmp_path):
        """GIVEN a file with other content WHEN writing version THEN other content is preserved."""
        test_file = tmp_path / "pyproject.toml"
        test_file.write_text('[project]\nname = "test"\nversion = "0.1.0"\ndeps = ["foo"]\n')

        with patch("bump_version.PYPROJECT_PATH", test_file):
            write_pyproject_version("0.2.0")
            content = test_file.read_text()
            assert 'name = "test"' in content
            assert 'deps = ["foo"]' in content
            assert 'version = "0.2.0"' in content


class TestVersionChecking:
    """Tests for checking version synchronization."""

    def test_check_versions_in_sync(self):
        """GIVEN all files with same version WHEN checking THEN returns True."""
        all_sync, versions = check_versions()
        assert all_sync is True
        assert versions["pyproject.toml"] is not None
        assert versions["dataforge/__init__.py"] is not None

    def test_check_versions_out_of_sync(self, tmp_path):
        """GIVEN files with different versions WHEN checking THEN returns False."""
        # Create temporary files with different versions
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\nversion = "0.2.0"\n')

        init = tmp_path / "__init__.py"
        init.write_text('__version__ = "0.1.0"\n')

        with (
            patch("bump_version.PYPROJECT_PATH", pyproject),
            patch("bump_version.INIT_PATH", init),
        ):
            all_sync, versions = check_versions()
            assert all_sync is False
            assert versions["pyproject.toml"] == "0.2.0"
            assert versions["dataforge/__init__.py"] == "0.1.0"


class TestBumpVersion:
    """Tests for bump_version function."""

    def test_bump_version_updates_all_files(self, tmp_path):
        """GIVEN a new version WHEN bumping THEN all files are updated."""
        # Create temporary files
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\nversion = "0.1.0"\n')

        init = tmp_path / "__init__.py"
        init.write_text('__version__ = "0.1.0"\n')

        with (
            patch("bump_version.PYPROJECT_PATH", pyproject),
            patch("bump_version.INIT_PATH", init),
            patch("bump_version.WIX_PATH", tmp_path / "nonexistent.wxs"),
            patch("bump_version.INFO_PLIST_PATH", tmp_path / "nonexistent.plist"),
        ):
            from bump_version import bump_version

            bump_version("0.2.0")

            assert 'version = "0.2.0"' in pyproject.read_text()
            assert '__version__ = "0.2.0"' in init.read_text()

    def test_bump_version_validates_format(self):
        """GIVEN an invalid version format WHEN bumping THEN raises ValueError."""
        from bump_version import bump_version

        with pytest.raises(ValueError, match="Invalid version format"):
            bump_version("invalid")

    def test_bump_version_accepts_semver(self):
        """GIVEN a valid semver version WHEN bumping THEN no error."""
        # This should not raise
        # We're just testing the validation, not the actual write
        with patch("bump_version.write_pyproject_version"):
            with patch("bump_version.write_init_version"):
                with patch("bump_version.write_wix_version"):
                    with patch("bump_version.write_plist_version"):
                        from bump_version import bump_version

                        bump_version("1.2.3")


class TestMainFunction:
    """Tests for main entry point."""

    def test_main_check_mode(self):
        """GIVEN --check flag WHEN running main THEN exits 0 if in sync."""
        result = main(["--check"])
        assert result == 0

    def test_main_print_current_version(self, capsys):
        """GIVEN no arguments WHEN running main THEN prints current version."""
        result = main([])
        assert result == 0
        captured = capsys.readouterr()
        assert "Current version:" in captured.out

    def test_main_bump_version(self, tmp_path):
        """GIVEN a version argument WHEN running main THEN bumps version."""
        # Create temporary files
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\nversion = "0.1.0"\n')

        init = tmp_path / "__init__.py"
        init.write_text('__version__ = "0.1.0"\n')

        with (
            patch("bump_version.PYPROJECT_PATH", pyproject),
            patch("bump_version.INIT_PATH", init),
            patch("bump_version.WIX_PATH", tmp_path / "nonexistent.wxs"),
            patch("bump_version.INFO_PLIST_PATH", tmp_path / "nonexistent.plist"),
        ):
            result = main(["0.2.0"])
            assert result == 0
            assert 'version = "0.2.0"' in pyproject.read_text()
            assert '__version__ = "0.2.0"' in init.read_text()


class TestInitVersionAttribute:
    """Tests for dataforge.__version__ attribute."""

    def test_version_attribute_exists(self):
        """GIVEN dataforge package WHEN importing THEN __version__ exists."""
        import dataforge

        assert hasattr(dataforge, "__version__")

    def test_version_is_string(self):
        """GIVEN dataforge package WHEN accessing __version__ THEN it is a string."""
        import dataforge

        assert isinstance(dataforge.__version__, str)

    def test_version_matches_pyproject(self):
        """GIVEN dataforge.__version__ and pyproject.toml WHEN comparing THEN they match."""
        import dataforge

        pyproject_ver = read_pyproject_version()
        assert dataforge.__version__ == pyproject_ver
