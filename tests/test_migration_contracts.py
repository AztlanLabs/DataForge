"""TICK-004 migration contracts — Wave 0.

Covers:
- config schema migration 1→2 with backup
- adaptive worker defaults
- cache PRAGMA user_version enumeration
- set_hash_many signature validation
"""

import json
import os
import sqlite3
import importlib
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Config: migration 1→2
# ---------------------------------------------------------------------------

def test_config_migration_v1_to_v2(tmp_path, monkeypatch):
    """GIVEN config.json with no _schema_version WHEN loaded THEN migrated."""
    cfg_path = tmp_path / "config.json"
    legacy = {
        "theme": "cosmo",
        "safe_mode": True,
        "excluded_extensions": [".tmp"],
        "excluded_folders": [".git"],
        "max_thread_workers": 4,
        "search_thread_workers": 4,
        "hash_algorithm": "sha256",
        "log_level": "INFO",
        "size_unit": "Auto",
        "path_display_mode": "full",
        "dashboard_paths": [str(tmp_path)],
        "settings_ui_tier": "Simple",
        "duplicate_default_keep_strategy": "first path",
        "plugins_enabled": False,
        "ui_reduce_motion": False,
    }
    cfg_path.write_text(json.dumps(legacy))
    mod = importlib.import_module("dataforge.core.config")
    mod.ConfigManager._instance = None
    cm = mod.ConfigManager(config_file=str(cfg_path))
    assert cm.get("_schema_version") == mod.CONFIG_SCHEMA_VERSION
    # TICK-807 bumps to 3, but migration from v1 should still land on current version
    assert cm.get("_schema_version") in (2, 3)
    backup = Path(str(cfg_path) + ".bak.v1")
    assert backup.exists(), "config.json.bak.v1 should be created"
    assert cm.get("hash_block_size") == 1 << 20
    assert cm.get("cache_batch_size") == 1000
    saved = json.loads(cfg_path.read_text())
    assert saved["_schema_version"] == mod.CONFIG_SCHEMA_VERSION
    assert saved["hash_block_size"] == 1 << 20
    assert saved["cache_batch_size"] == 1000
    # TICK-807 new keys should also be present after migration
    if mod.CONFIG_SCHEMA_VERSION >= 3:
        assert "ui_last_paths" in saved
        assert "ui_checkbox_states" in saved
    mod.ConfigManager._instance = None
    importlib.reload(mod)


def test_config_adaptive_workers_12_core(monkeypatch, tmp_path):
    """GIVEN 12-core host WHEN config.get('max_thread_workers') THEN ==32."""
    mod = importlib.import_module("dataforge.core.config")
    monkeypatch.setattr(os, "cpu_count", lambda: 12)
    importlib.reload(mod)
    cfg_path = tmp_path / "config.json"
    mod.ConfigManager._instance = None
    cm = mod.ConfigManager(config_file=str(cfg_path))
    assert cm.get("max_thread_workers") == 32, "12*4=48 capped to 32"
    assert cm.get("search_thread_workers") == 24
    assert cm.get("hash_block_size") == 1 << 20
    assert cm.get("cache_batch_size") == 1000
    mod.ConfigManager._instance = None
    monkeypatch.undo()
    importlib.reload(mod)


def test_config_default_constants():
    mod = importlib.import_module("dataforge.core.config")
    assert mod.CONFIG_SCHEMA_VERSION in (2, 3)
    assert isinstance(mod.MIGRATIONS, dict)
    assert 1 in mod.MIGRATIONS
    assert mod.ConfigManager.DEFAULT_CONFIG["hash_block_size"] == 1 << 20
    assert mod.ConfigManager.DEFAULT_CONFIG["cache_batch_size"] == 1000
    assert "_schema_version" in mod.ConfigManager.DEFAULT_CONFIG
    if mod.CONFIG_SCHEMA_VERSION >= 3:
        assert "ui_last_paths" in mod.ConfigManager.DEFAULT_CONFIG
        assert "ui_checkbox_states" in mod.ConfigManager.DEFAULT_CONFIG
        assert 2 in mod.MIGRATIONS


def test_cache_user_version_pending_enumerated(tmp_path):
    cache_mod = importlib.import_module("dataforge.core.cache")
    migrations_dir = cache_mod.MIGRATIONS_DIR
    migrations_dir.mkdir(parents=True, exist_ok=True)
    dummy = migrations_dir / "dummy_1_2.sql"
    dummy.write_text("-- dummy migration\nSELECT 1;")
    try:
        db_path = tmp_path / "cache.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE IF NOT EXISTS file_hashes (path TEXT PRIMARY KEY, size INTEGER, mtime REAL, hash TEXT, algo TEXT)")
        conn.execute("PRAGMA user_version=1")
        conn.commit()
        conn.close()
        cm = cache_mod.CacheManager(str(db_path))
        pending = cm.get_pending_migrations()
        assert len(pending) >= 1
        assert any(p.name == "dummy_1_2.sql" for p in pending)
        assert len(cm.pending_migrations) >= 1
        assert cm.get_user_version() == 1
        cm.close()
    finally:
        if dummy.exists():
            dummy.unlink()


def test_cache_pending_empty_when_current(tmp_path):
    cache_mod = importlib.import_module("dataforge.core.cache")
    db_path = tmp_path / "cache.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS file_hashes (path TEXT PRIMARY KEY, size INTEGER, mtime REAL, hash TEXT, algo TEXT)")
    conn.execute(f"PRAGMA user_version={cache_mod.CACHE_SCHEMA_VERSION}")
    conn.commit()
    conn.close()
    cm = cache_mod.CacheManager(str(db_path))
    assert cm.get_pending_migrations() == []
    assert cm.get_user_version() == cache_mod.CACHE_SCHEMA_VERSION
    cm.close()


def test_set_hash_many_validates_shape(tmp_path):
    cache_mod = importlib.import_module("dataforge.core.cache")
    db_path = tmp_path / "cache.db"
    cm = cache_mod.CacheManager(str(db_path))
    valid = [("/path/a.txt", 100, 12345.0, "abc123", "md5")]
    assert cm.set_hash_many(valid) is None
    assert cm.set_hash_many([]) is None
    # Wave 0 stub returned None; Wave 1 (TICK-104) impl persists via executemany
    assert cm.get_hash("/path/a.txt", 100, 12345.0, "md5") == "abc123"
    with pytest.raises(TypeError):
        cm.set_hash_many("not a list")  # type: ignore
    with pytest.raises(ValueError):
        cm.set_hash_many([("/a", 100, 1.0, "hash")])
    with pytest.raises(TypeError):
        cm.set_hash_many([("/a", "100", 1.0, "hash", "md5")])
    with pytest.raises(TypeError):
        cm.set_hash_many([("/a", 100, "1.0", "hash", "md5")])
    with pytest.raises(TypeError):
        cm.set_hash_many([(123, 100, 1.0, "hash", "md5")])
    cm.close()


def test_cache_schema_version_constant():
    mod = importlib.import_module("dataforge.core.cache")
    # v3: inode column added to file_hashes (TICK-922 cache invalidation)
    assert mod.CACHE_SCHEMA_VERSION == 3
    assert mod.MIGRATIONS_DIR.name == "migrations"
    assert mod.MIGRATIONS_DIR.exists()


def test_engine_package_exists():
    mod = importlib.import_module("dataforge.engine")
    assert mod.MIGRATIONS_DIR.exists()
    readme = mod.MIGRATIONS_DIR / "README.md"
    assert readme.exists()
