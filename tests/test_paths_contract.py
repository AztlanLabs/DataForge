"""Contract tests for ``dataforge/core/paths.py`` and the version source."""

import contextlib
import importlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path

import pytest

import dataforge
from dataforge.core import paths

XDG_VARS = ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR")
WIN_OVERRIDES = ("WIN_PD_OVERRIDE_LOCAL_APPDATA", "WIN_PD_OVERRIDE_APPDATA")
SAVED_VARS = (
    "HOME",
    "LOCALAPPDATA",
    "APPDATA",
    paths.SKIP_MIGRATION_ENV,
    *XDG_VARS,
    *WIN_OVERRIDES,
)

WIN_LOCAL_APPDATA = r"C:\Users\tester\AppData\Local"
WIN_ROAMING_APPDATA = r"C:\Users\tester\AppData\Roaming"


@contextlib.contextmanager
def isolated_paths(
    home: Path,
    platform_name: str | None = None,
    skip_migration: bool = True,
):
    """Reload ``dataforge.core.paths`` against an isolated HOME/XDG sandbox."""
    saved_env = {name: os.environ.get(name) for name in SAVED_VARS}
    saved_platform = sys.platform
    try:
        xdg_root = home / ".xdg"
        os.environ["HOME"] = str(home)
        os.environ["XDG_CONFIG_HOME"] = str(xdg_root / "config")
        os.environ["XDG_CACHE_HOME"] = str(xdg_root / "cache")
        os.environ["XDG_STATE_HOME"] = str(xdg_root / "state")
        os.environ["XDG_RUNTIME_DIR"] = str(xdg_root / "runtime")
        if platform_name == "win32":
            os.environ["WIN_PD_OVERRIDE_LOCAL_APPDATA"] = WIN_LOCAL_APPDATA
            os.environ["WIN_PD_OVERRIDE_APPDATA"] = WIN_ROAMING_APPDATA
        if platform_name == "darwin":
            for name in XDG_VARS:
                os.environ.pop(name, None)
        if skip_migration:
            os.environ[paths.SKIP_MIGRATION_ENV] = "1"
        else:
            os.environ.pop(paths.SKIP_MIGRATION_ENV, None)
        if platform_name is not None:
            sys.platform = platform_name
        import platformdirs

        importlib.reload(platformdirs)
        yield importlib.reload(paths)
    finally:
        sys.platform = saved_platform
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        import platformdirs

        importlib.reload(platformdirs)
        os.environ[paths.SKIP_MIGRATION_ENV] = "1"
        importlib.reload(paths)
        os.environ.pop(paths.SKIP_MIGRATION_ENV, None)


def make_legacy(home: Path, config: dict | None = None) -> Path:
    legacy = home / ".dataforge"
    legacy.mkdir(parents=True, exist_ok=True)
    payload = {"theme": "cosmo"} if config is None else config
    (legacy / "config.json").write_text(json.dumps(payload), encoding="utf-8")
    return legacy


def test_version_is_exposed_and_matches_pyproject():
    pyproject_version = dataforge._version_from_pyproject()
    assert pyproject_version == "0.2.0"
    assert dataforge.__version__ == pyproject_version


def test_version_falls_back_to_pyproject_without_install(monkeypatch):
    from importlib.metadata import PackageNotFoundError

    def missing(name, *args, **kwargs):
        raise PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    assert dataforge._resolve_version() == "0.2.0"


def test_version_pyproject_missing_file_defaults_cleanly(tmp_path):
    assert dataforge._version_from_pyproject(tmp_path / "nope.toml") == "0.1.0"


def test_linux_xdg_contract(tmp_path):
    with isolated_paths(tmp_path) as p:
        xdg_root = tmp_path / ".xdg"
        assert p.config_dir == xdg_root / "config" / "DataForge"
        assert p.config_file == xdg_root / "config" / "DataForge" / "config.json"
        assert p.cache_db == xdg_root / "cache" / "DataForge" / "cache.db"
        assert p.jobs_db == xdg_root / "state" / "DataForge" / "jobs.db"
        assert p.log_file == xdg_root / "state" / "DataForge" / "logs" / "app.log"
        assert p.runtime_dir == xdg_root / "runtime" / "DataForge"
        assert p.exports_dir == tmp_path / "Documents" / "DataForge"


@pytest.mark.skipif(
    importlib.util.find_spec("platformdirs") is None,
    reason="platformdirs not installed (pre-TICK-402)",
)
def test_macos_contract(tmp_path):
    with isolated_paths(tmp_path, platform_name="darwin") as p:
        import platformdirs

        reference = platformdirs.PlatformDirs("DataForge", "DataForge")
        assert type(p.dirs).__name__ == "MacOS"
        assert p.config_file == reference.user_config_path / "config.json"
        assert p.cache_db == reference.user_cache_path / "cache.db"
        assert p.jobs_db == reference.user_state_path / "jobs.db"
        assert p.log_file == reference.user_log_path / "app.log"
        app_support = tmp_path / "Library" / "Application Support" / "DataForge"
        caches = tmp_path / "Library" / "Caches" / "DataForge"
        logs = tmp_path / "Library" / "Logs" / "DataForge"
        assert p.config_dir == app_support
        assert p.cache_dir == caches
        assert p.log_dir == logs


@pytest.mark.skipif(
    importlib.util.find_spec("platformdirs") is None,
    reason="platformdirs not installed (pre-TICK-402)",
)
def test_windows_contract(tmp_path):
    with isolated_paths(tmp_path, platform_name="win32") as p:
        import platformdirs

        reference = platformdirs.PlatformDirs("DataForge", "DataForge")
        assert type(p.dirs).__name__ == "Windows"
        assert p.config_file == reference.user_config_path / "config.json"
        assert p.cache_db == reference.user_cache_path / "cache.db"
        assert p.jobs_db == reference.user_state_path / "jobs.db"
        assert p.log_file == reference.user_log_path / "app.log"
        assert WIN_LOCAL_APPDATA in str(p.config_dir)
        assert WIN_ROAMING_APPDATA not in str(p.config_dir)
        assert p.cache_db.parent.name == "Cache"
        assert p.log_file.parent.name == "Logs"


def test_migration_copies_to_new_location_with_backup(caplog, tmp_path):
    legacy = make_legacy(tmp_path)
    (legacy / "cache.db").write_bytes(b"sqlite")
    with caplog.at_level(logging.INFO, logger="dataforge.paths"):
        with isolated_paths(tmp_path, skip_migration=False) as p:
            migrated = json.loads(p.config_file.read_text(encoding="utf-8"))
            cache_bytes = p.cache_db.read_bytes()
            backups = list(tmp_path.glob(".dataforge.backup.*"))
    assert migrated == {"theme": "cosmo"}
    assert cache_bytes == b"sqlite"
    assert len(backups) == 1
    backup = backups[0]
    assert json.loads((backup / "config.json").read_text(encoding="utf-8")) == {
        "theme": "cosmo"
    }
    assert (backup / "cache.db").read_bytes() == b"sqlite"
    assert legacy.exists(), "legacy directory must be preserved, never deleted"
    assert "migrated_from_legacy" in caplog.text


def test_migration_noop_when_canonical_config_exists(tmp_path):
    make_legacy(tmp_path)
    xdg_config = tmp_path / ".xdg" / "config" / "DataForge"
    xdg_config.mkdir(parents=True)
    sentinel = {"theme": "fresh-install"}
    (xdg_config / "config.json").write_text(json.dumps(sentinel), encoding="utf-8")
    with isolated_paths(tmp_path, skip_migration=False) as p:
        assert json.loads(p.config_file.read_text(encoding="utf-8")) == sentinel
    assert not list(tmp_path.glob(".dataforge.backup.*"))


def test_migration_noop_without_legacy(tmp_path):
    with isolated_paths(tmp_path, skip_migration=False) as p:
        assert not p.migrate_from_legacy()
        assert not p.config_file.exists()
    assert not list(tmp_path.glob(".dataforge.backup.*"))


def test_migrate_from_legacy_is_idempotent(tmp_path, caplog):
    make_legacy(tmp_path)
    with caplog.at_level(logging.INFO, logger="dataforge.paths"):
        with isolated_paths(tmp_path, skip_migration=True) as p:
            first = p.migrate_from_legacy()
            second = p.migrate_from_legacy()
    assert first is True
    assert second is False
    assert caplog.text.count("migrated_from_legacy") == 1


def test_migrate_accepts_explicit_source(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    source = make_legacy(elsewhere)
    (source / "app.log").write_text("old log", encoding="utf-8")
    with isolated_paths(tmp_path, skip_migration=True) as p:
        assert p.migrate_from_legacy(legacy_dir=source) is True
        assert p.log_file.read_text(encoding="utf-8") == "old log"
        backups = list(elsewhere.glob(".dataforge.backup.*"))
    assert len(backups) == 1
    assert not (tmp_path / ".dataforge").exists()


def test_ensure_dirs_creates_layout(tmp_path):
    with isolated_paths(tmp_path) as p:
        assert not p.config_dir.exists()
        p.ensure_dirs()
        assert p.config_dir.is_dir()
        assert p.cache_dir.is_dir()
        assert p.state_dir.is_dir()
        assert p.log_dir.is_dir()


def test_core_package_exports_paths_contract():
    from dataforge.core import cache_db, config_file

    assert config_file == paths.config_file
    assert config_file.name == "config.json"
    assert cache_db == paths.cache_db
    assert cache_db.name == "cache.db"
