"""DataForge — File System Management with Steroids and Superpowers."""

import re
from pathlib import Path

# Version is synced by scripts/bump_version.py — do not edit manually
__version__ = "0.1.0"

_FALLBACK_VERSION = "0.1.0"
_PYPROJECT_PATH = Path(__file__).resolve().parent.parent / "pyproject.toml"
_PROJECT_VERSION_RE = re.compile(
    r"\[project\][^\[]*?^\s*version\s*=\s*[\"']([^\"']+)[\"']",
    re.MULTILINE | re.DOTALL,
)


def _version_from_pyproject(pyproject_path: str | Path | None = None) -> str:
    path = Path(pyproject_path) if pyproject_path else _PYPROJECT_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return _FALLBACK_VERSION
    match = _PROJECT_VERSION_RE.search(text)
    if match is None:
        return _FALLBACK_VERSION
    return match.group(1)


def _resolve_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError
        from importlib.metadata import version as metadata_version

        try:
            return metadata_version("dataforge")
        except PackageNotFoundError:
            pass
    except Exception:
        pass
    return _version_from_pyproject()


# Use hardcoded __version__ as primary, fallback to dynamic resolution
__all__ = ["__version__"]
