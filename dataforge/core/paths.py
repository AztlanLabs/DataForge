"""Single source of truth for DataForge filesystem locations.

Canonical layout follows ``docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md`` §1:
XDG directories on Linux, ``~/Library`` on macOS and ``AppData`` on Windows,
via :class:`platformdirs.PlatformDirs`. The legacy ``~/.dataforge`` directory
is kept only as a one-shot migration source; importing this module copies its
artifacts to the canonical locations and leaves a timestamped backup at
``~/.dataforge.backup.<ts>``. Set ``DATAFORGE_SKIP_LEGACY_MIGRATION=1`` (or a
non-empty value) to suppress the import-time migration.
"""

import logging
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

logger = logging.getLogger("dataforge.paths")

APP_NAME = "DataForge"
APP_AUTHOR = "DataForge"

SKIP_MIGRATION_ENV = "DATAFORGE_SKIP_LEGACY_MIGRATION"


class _FallbackDirs:
    """XDG stand-in used until pyproject.toml gains the platformdirs dep."""

    def __init__(self, appname: str, appauthor: str | None) -> None:
        self.appname = appname
        self.appauthor = appauthor

    @staticmethod
    def _xdg(var: str, default: str) -> Path:
        return Path(os.environ.get(var) or Path.home() / default)

    @property
    def user_config_path(self) -> Path:
        return self._xdg("XDG_CONFIG_HOME", ".config") / self.appname

    @property
    def user_cache_path(self) -> Path:
        return self._xdg("XDG_CACHE_HOME", ".cache") / self.appname

    @property
    def user_state_path(self) -> Path:
        return self._xdg("XDG_STATE_HOME", os.path.join(".local", "state")) / self.appname

    @property
    def user_log_path(self) -> Path:
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
            return Path(base) / self.appname / self.appname / "Logs"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Logs" / self.appname
        return self.user_state_path / "logs"

    @property
    def user_runtime_path(self) -> Path:
        base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
        return Path(base) / self.appname


try:
    import platformdirs as _platformdirs

    _DirsImpl = _platformdirs.PlatformDirs
except ImportError:  # pragma: no cover - exercised only without platformdirs
    _DirsImpl = _FallbackDirs

dirs = _DirsImpl(APP_NAME, APP_AUTHOR)

LEGACY_DIR = Path.home() / ".dataforge"

config_dir: Path = dirs.user_config_path
config_file: Path = config_dir / "config.json"
cache_dir: Path = dirs.user_cache_path
cache_db: Path = cache_dir / "cache.db"
state_dir: Path = dirs.user_state_path
jobs_db: Path = state_dir / "jobs.db"
if sys.platform in ("darwin", "win32"):
    log_dir: Path = dirs.user_log_path
else:
    log_dir = state_dir / "logs"
log_file: Path = log_dir / "app.log"
runtime_dir: Path = dirs.user_runtime_path
exports_dir: Path = Path.home() / "Documents" / "DataForge"


def ensure_dirs(*extra: Path) -> None:
    """Create the canonical directory layout (best effort)."""
    targets = (config_dir, cache_dir, state_dir, log_dir, runtime_dir, *extra)
    for directory in targets:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Could not create %s: %s", directory, exc)


def migrate_from_legacy(legacy_dir: Path | None = None) -> bool:
    """Copy legacy ``~/.dataforge`` artifacts into the canonical layout.

    One-shot per install: a no-op when the legacy config is absent or the
    canonical config already exists. The whole legacy tree is preserved at
    ``~/.dataforge.backup.<ts>`` before anything is copied.

    Returns True when a migration was performed.
    """
    legacy = Path(legacy_dir) if legacy_dir else LEGACY_DIR
    src_config = legacy / "config.json"
    if not src_config.is_file() or config_file.exists():
        return False

    backup = _backup_target(legacy)
    shutil.copytree(legacy, backup)

    targets = {"config.json": config_file, "cache.db": cache_db, "app.log": log_file}
    copied: list[str] = []
    for name, dest in targets.items():
        src = legacy / name
        if not src.is_file():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(name)
    logger.info(
        "migrated_from_legacy=true legacy=%s backup=%s copied=%s",
        legacy,
        backup,
        copied,
    )
    return True


def _backup_target(legacy: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = legacy.parent / f"{legacy.name}.backup.{stamp}"
    sequence = 1
    while candidate.exists():
        sequence += 1
        candidate = legacy.parent / f"{legacy.name}.backup.{stamp}.{sequence}"
    return candidate


if not os.environ.get(SKIP_MIGRATION_ENV):
    try:
        migrate_from_legacy()
    except OSError as exc:
        logger.warning("Legacy migration failed: %s", exc)

__all__ = [
    "APP_AUTHOR",
    "APP_NAME",
    "LEGACY_DIR",
    "SKIP_MIGRATION_ENV",
    "cache_db",
    "cache_dir",
    "config_dir",
    "config_file",
    "dirs",
    "ensure_dirs",
    "exports_dir",
    "jobs_db",
    "log_dir",
    "log_file",
    "migrate_from_legacy",
    "runtime_dir",
    "state_dir",
]
