#!/usr/bin/env python3
"""Centralize version bump across pyproject.toml, dataforge/__init__.py, and installer files.

Usage::

    # Bump to a new version
    python scripts/bump_version.py 0.2.0

    # Check that all version sources are in sync
    python scripts/bump_version.py --check

Spec: ``docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md §2``
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
INIT_PATH = PROJECT_ROOT / "dataforge" / "__init__.py"
WIX_PATH = PROJECT_ROOT / "packaging" / "wix" / "Product.wxs"
INFO_PLIST_PATH = PROJECT_ROOT / "packaging" / "macos" / "DataForge.app" / "Contents" / "Info.plist"

# Regex patterns for version extraction/update
PYPROJECT_VERSION_RE = re.compile(
    r'(^version\s*=\s*["\'])([^"\']+)(["\'])',
    re.MULTILINE,
)
INIT_VERSION_RE = re.compile(
    r'(^__version__\s*=\s*["\'])([^"\']+)(["\'])',
    re.MULTILINE,
)
WIX_VERSION_RE = re.compile(
    r'(<Product[^>]*Version=")([^"]+)(")',
    re.DOTALL,
)
PLIST_VERSION_RE = re.compile(
    r"(<key>CFBundleShortVersionString</key>\s*<string>)([^<]+)(</string>)",
    re.DOTALL,
)


def read_pyproject_version() -> str:
    """Read version from pyproject.toml."""
    text = PYPROJECT_PATH.read_text(encoding="utf-8")
    match = PYPROJECT_VERSION_RE.search(text)
    if match is None:
        raise ValueError(f"Could not find version in {PYPROJECT_PATH}")
    return match.group(2)


def read_init_version() -> str | None:
    """Read __version__ from dataforge/__init__.py."""
    if not INIT_PATH.exists():
        return None
    text = INIT_PATH.read_text(encoding="utf-8")
    match = INIT_VERSION_RE.search(text)
    if match is None:
        return None
    return match.group(2)


def read_wix_version() -> str | None:
    """Read ProductVersion from wix/Product.wxs."""
    if not WIX_PATH.exists():
        return None
    text = WIX_PATH.read_text(encoding="utf-8")
    match = WIX_VERSION_RE.search(text)
    if match is None:
        return None
    return match.group(2)


def read_plist_version() -> str | None:
    """Read CFBundleShortVersionString from Info.plist."""
    if not INFO_PLIST_PATH.exists():
        return None
    text = INFO_PLIST_PATH.read_text(encoding="utf-8")
    match = PLIST_VERSION_RE.search(text)
    if match is None:
        return None
    return match.group(2)


def write_pyproject_version(version: str) -> None:
    """Write version to pyproject.toml."""
    text = PYPROJECT_PATH.read_text(encoding="utf-8")
    new_text, count = PYPROJECT_VERSION_RE.subn(rf"\g<1>{version}\3", text, count=1)
    if count == 0:
        raise ValueError(f"Could not find version in {PYPROJECT_PATH}")
    PYPROJECT_PATH.write_text(new_text, encoding="utf-8")


def write_init_version(version: str) -> None:
    """Write __version__ to dataforge/__init__.py."""
    if not INIT_PATH.exists():
        raise FileNotFoundError(f"__init__.py not found at {INIT_PATH}")
    text = INIT_PATH.read_text(encoding="utf-8")
    new_text, count = INIT_VERSION_RE.subn(rf"\g<1>{version}\3", text, count=1)
    if count == 0:
        raise ValueError(f"Could not find __version__ in {INIT_PATH}")
    INIT_PATH.write_text(new_text, encoding="utf-8")


def write_wix_version(version: str) -> None:
    """Write ProductVersion to wix/Product.wxs."""
    if not WIX_PATH.exists():
        return  # WiX file doesn't exist yet, skip
    text = WIX_PATH.read_text(encoding="utf-8")
    new_text, count = WIX_VERSION_RE.subn(rf"\g<1>{version}\3", text, count=1)
    if count == 0:
        raise ValueError(f"Could not find Product Version in {WIX_PATH}")
    WIX_PATH.write_text(new_text, encoding="utf-8")


def write_plist_version(version: str) -> None:
    """Write CFBundleShortVersionString to Info.plist."""
    if not INFO_PLIST_PATH.exists():
        return  # Info.plist doesn't exist yet, skip
    text = INFO_PLIST_PATH.read_text(encoding="utf-8")
    new_text, count = PLIST_VERSION_RE.subn(rf"\g<1>{version}\3", text, count=1)
    if count == 0:
        raise ValueError(f"Could not find CFBundleShortVersionString in {INFO_PLIST_PATH}")
    INFO_PLIST_PATH.write_text(new_text, encoding="utf-8")


def check_versions() -> tuple[bool, dict[str, str | None]]:
    """Check if all version sources are in sync.

    Returns:
        Tuple of (all_sync, versions_dict) where versions_dict maps source name to version.
    """
    versions: dict[str, str | None] = {}
    versions["pyproject.toml"] = read_pyproject_version()
    versions["dataforge/__init__.py"] = read_init_version()
    versions["wix/Product.wxs"] = read_wix_version()
    versions["Info.plist"] = read_plist_version()

    # Filter out None values (files that don't exist)
    existing_versions = {k: v for k, v in versions.items() if v is not None}

    if not existing_versions:
        return False, versions

    # Check if all existing versions are the same
    unique_versions = set(existing_versions.values())
    all_sync = len(unique_versions) == 1

    return all_sync, versions


def bump_version(version: str) -> None:
    """Bump version across all files."""
    # Validate version format (basic semver check)
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        raise ValueError(f"Invalid version format: {version}. Expected X.Y.Z")

    print(f"Bumping version to {version}...")

    write_pyproject_version(version)
    print(f"  Updated {PYPROJECT_PATH}")

    write_init_version(version)
    print(f"  Updated {INIT_PATH}")

    write_wix_version(version)
    if WIX_PATH.exists():
        print(f"  Updated {WIX_PATH}")
    else:
        print(f"  Skipped {WIX_PATH} (not found)")

    write_plist_version(version)
    if INFO_PLIST_PATH.exists():
        print(f"  Updated {INFO_PLIST_PATH}")
    else:
        print(f"  Skipped {INFO_PLIST_PATH} (not found)")

    print(f"Version bumped to {version}")


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Centralize version bump across pyproject.toml, dataforge/__init__.py, and installer files.",
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="New version string (X.Y.Z). If omitted, prints current version.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if all version sources are in sync and exit.",
    )

    args = parser.parse_args(argv)

    if args.check:
        all_sync, versions = check_versions()
        for source, version in versions.items():
            status = version if version else "(not found)"
            print(f"  {source}: {status}")
        if all_sync:
            print("All versions are in sync.")
            return 0
        else:
            print("ERROR: Versions are NOT in sync!")
            return 1

    if args.version:
        bump_version(args.version)
        return 0

    # No version argument and no --check: print current version
    try:
        current = read_pyproject_version()
        print(f"Current version: {current}")
        return 0
    except Exception as e:
        print(f"Error reading version: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
