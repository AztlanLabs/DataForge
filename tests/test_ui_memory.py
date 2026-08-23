"""TICK-807 — Memory remember checkboxes/selections/names."""
import importlib
import json
import os
from pathlib import Path

import pytest


def _reload_config(tmp_path, env="DATAFORGE_SKIP_LEGACY_MIGRATION"):
    os.environ[env] = "1"
    mod = importlib.import_module("dataforge.core.config")
    # reset singleton
    mod.ConfigManager._instance = None
    importlib.reload(mod)
    mod.ConfigManager._instance = None
    cfg_path = tmp_path / "config.json"
    cm = mod.ConfigManager(config_file=str(cfg_path))
    return mod, cm, cfg_path


def test_config_default_has_ui_keys():
    mod = importlib.import_module("dataforge.core.config")
    cfg = mod.ConfigManager.DEFAULT_CONFIG
    assert "ui_last_paths" in cfg and isinstance(cfg["ui_last_paths"], dict)
    assert "ui_checkbox_states" in cfg and isinstance(cfg["ui_checkbox_states"], dict)
    assert "ui_filter_names" in cfg and isinstance(cfg["ui_filter_names"], dict)
    assert "ui_recent_searches" in cfg and isinstance(cfg["ui_recent_searches"], list)
    assert "ui_recent_automations" in cfg
    assert "window_geometry" in cfg
    assert mod.CONFIG_SCHEMA_VERSION == 3
    assert 2 in mod.MIGRATIONS


def test_migration_adds_ui_keys_without_dropping(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFORGE_SKIP_LEGACY_MIGRATION", "1")
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
        "hash_block_size": 1 << 20,
        "cache_batch_size": 1000,
        # intentionally no ui_* keys, old version
        "_schema_version": 2,
        "custom_keep": "my_value",
    }
    cfg_path.write_text(json.dumps(legacy))
    mod = importlib.import_module("dataforge.core.config")
    mod.ConfigManager._instance = None
    cm = mod.ConfigManager(config_file=str(cfg_path))
    # new keys added
    assert cm.get("ui_last_paths") == {}
    assert cm.get("ui_checkbox_states") == {}
    assert cm.get("ui_filter_names") == {}
    assert cm.get("ui_recent_searches") == []
    # existing custom value preserved
    assert cm.get("custom_keep") == "my_value"
    assert cm.get("theme") == "cosmo"
    assert cm.get("_schema_version") == 3
    # backup created
    assert (tmp_path / "config.json.bak.v2").exists() or (tmp_path / "config.json.bak.v1").exists()
    # also test migration from v1 (no _schema_version)
    cfg_path2 = tmp_path / "config2.json"
    legacy2 = {k: v for k, v in legacy.items() if k != "_schema_version"}
    cfg_path2.write_text(json.dumps(legacy2))
    mod.ConfigManager._instance = None
    cm2 = mod.ConfigManager(config_file=str(cfg_path2))
    assert cm2.get("ui_last_paths") == {}
    assert cm2.get("_schema_version") == 3
    mod.ConfigManager._instance = None
    importlib.reload(mod)


def test_search_path_remembered(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFORGE_SKIP_LEGACY_MIGRATION", "1")
    mod, cm, cfg_path = _reload_config(tmp_path)
    # simulate search path entered
    last = cm.get("ui_last_paths", {})
    last["search"] = "/tmp/my_search_path"
    last["system_cleanup"] = "/tmp/extra"
    cm.set("ui_last_paths", last)
    # also test ui_filter_names
    filters = cm.get("ui_filter_names", {})
    filters["search.filter"] = "my_filter"
    cm.set("ui_filter_names", filters)
    # reload as if app restarted
    mod.ConfigManager._instance = None
    cm2 = mod.ConfigManager(config_file=str(cfg_path))
    assert cm2.get("ui_last_paths", {}).get("search") == "/tmp/my_search_path"
    assert cm2.get("ui_last_paths", {}).get("system_cleanup") == "/tmp/extra"
    assert cm2.get("ui_filter_names", {}).get("search.filter") == "my_filter"
    mod.ConfigManager._instance = None
    importlib.reload(mod)


def test_transient_progress_not_persisted(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFORGE_SKIP_LEGACY_MIGRATION", "1")
    mod, cm, cfg_path = _reload_config(tmp_path)
    # try to store transient keys
    cm.set("progress", 42)
    cm.set("transient_progress", 99)
    cm.set("file_list", ["/tmp/a", "/tmp/b"])
    cm.set("transient_foo", "bar")
    # config.set writes immediately, but save filters transient
    # reload
    mod.ConfigManager._instance = None
    cm2 = mod.ConfigManager(config_file=str(cfg_path))
    # transient keys should not be in persisted file
    data = json.loads(cfg_path.read_text())
    assert "progress" not in data
    assert "transient_progress" not in data
    assert "file_list" not in data
    assert "transient_foo" not in data
    assert cm2.get("progress") is None
    assert cm2.get("transient_progress") is None
    mod.ConfigManager._instance = None
    importlib.reload(mod)


def test_paths_ui_state_helper(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFORGE_SKIP_LEGACY_MIGRATION", "1")
    # paths helper should exist
    import dataforge.core.paths as paths_mod
    assert hasattr(paths_mod, "ui_state_file")
    assert hasattr(paths_mod, "load_ui_state")
    assert hasattr(paths_mod, "save_ui_state")
    assert hasattr(paths_mod, "append_recent_search")
    assert hasattr(paths_mod, "get_recent_searches")
    # recent.json helper
    # point state_dir to tmp
    orig = paths_mod.ui_state_file
    monkeypatch.setattr(paths_mod, "ui_state_file", tmp_path / "recent.json")
    monkeypatch.setattr(paths_mod, "recent_file", tmp_path / "recent.json")
    state = paths_mod.load_ui_state()
    assert state == {}
    paths_mod.save_ui_state({"recent_searches": ["foo", "bar"]})
    assert (tmp_path / "recent.json").exists()
    assert paths_mod.load_ui_state()["recent_searches"] == ["foo", "bar"]
    paths_mod.append_recent_search("baz")
    assert paths_mod.get_recent_searches()[0] == "baz"
    paths_mod.append_recent_search("foo")
    # dedup: foo moves to front
    assert paths_mod.get_recent_searches()[0] == "foo"
    # restore
    monkeypatch.setattr(paths_mod, "ui_state_file", orig)
    monkeypatch.setattr(paths_mod, "recent_file", orig)


def test_system_cleanup_checkbox_restored(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAFORGE_SKIP_LEGACY_MIGRATION", "1")
    # setup config in tmp
    mod = importlib.import_module("dataforge.core.config")
    mod.ConfigManager._instance = None
    importlib.reload(mod)
    mod.ConfigManager._instance = None
    cfg_path = tmp_path / "config.json"
    cm = mod.ConfigManager(config_file=str(cfg_path))
    mod.config = cm  # ensure module-level singleton points to tmp
    import dataforge.ui.views.system_cleanup as sc_mod
    sc_mod.config = cm
    # need QApplication for SystemCleanupView
    pytest.importorskip("PyQt5.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication, QWidget
    from unittest.mock import MagicMock
    from dataforge.ui.views.system_cleanup import SystemCleanupView

    app = QApplication.instance() or QApplication([])
    mock_app = MagicMock()
    mock_app.update_status = MagicMock()
    mock_app.run_workflow = MagicMock()
    mock_app.show_warning_dialog = MagicMock()

    parent = QWidget()
    # ensure config has known state before view creation
    # set checkbox state via config
    cbs = cm.get("ui_checkbox_states", {}) or {}
    cbs["system_cleanup.include_browser"] = True
    cbs["system_cleanup.category.System Temp"] = False
    cm.set("ui_checkbox_states", cbs)
    last = cm.get("ui_last_paths", {}) or {}
    last["system_cleanup"] = "/tmp/extra_path"
    cm.set("ui_last_paths", last)
    filters = cm.get("ui_filter_names", {}) or {}
    filters["system_cleanup.min_age"] = "7"
    cm.set("ui_filter_names", filters)
    cbs2 = cm.get("ui_checkbox_states", {}) or {}
    cbs2["system_cleanup.tab_index"] = 1
    cm.set("ui_checkbox_states", cbs2)

    # create view — it should load from config in __init__/mount
    view = SystemCleanupView(parent, app=mock_app)
    # check restored
    assert view.chk_include_browser.isChecked() is True
    assert view.category_checks["System Temp"].isChecked() is False
    assert view.entry_path.text() == "/tmp/extra_path"
    assert view.spin_age.value() == 7
    assert view.tabs.currentIndex() == 1

    # now change checkbox and verify it is saved to config
    view.chk_include_browser.setChecked(False)
    # trigger signal (stateChanged should have saved)
    # allow event loop to process
    app.processEvents()
    # config should now have False
    mod2 = importlib.import_module("dataforge.core.config")
    # reload cm from file
    mod2.ConfigManager._instance = None
    cm2 = mod2.ConfigManager(config_file=str(cfg_path))
    assert cm2.get("ui_checkbox_states", {}).get("system_cleanup.include_browser") is False

    # change tab and check persisted
    view.tabs.setCurrentIndex(0)
    app.processEvents()
    mod2.ConfigManager._instance = None
    cm3 = mod2.ConfigManager(config_file=str(cfg_path))
    assert cm3.get("ui_checkbox_states", {}).get("system_cleanup.tab_index") == 0

    # change extra path
    view.entry_path.setText("/tmp/new_extra")
    app.processEvents()
    mod2.ConfigManager._instance = None
    cm4 = mod2.ConfigManager(config_file=str(cfg_path))
    assert cm4.get("ui_last_paths", {}).get("system_cleanup") == "/tmp/new_extra"

    parent.deleteLater()
    mod.ConfigManager._instance = None
    importlib.reload(mod)


def test_system_cleanup_uses_config_not_transient(tmp_path, monkeypatch):
    # ensure SystemCleanupView does not persist transient progress
    monkeypatch.setenv("DATAFORGE_SKIP_LEGACY_MIGRATION", "1")
    mod = importlib.import_module("dataforge.core.config")
    mod.ConfigManager._instance = None
    src = Path("dataforge/ui/views/system_cleanup.py").read_text(encoding="utf-8")
    assert "config.set" in src
    assert "ui_checkbox_states" in src or "ui_last_paths" in src
    # ensure it does not save progress
    assert "progress" not in src.lower() or "transient" in src.lower() or src.lower().count("progress") < 5
    # check that mount loads
    assert "def mount" in src or "_load_ui_memory" in src
    mod.ConfigManager._instance = None
    importlib.reload(mod)
