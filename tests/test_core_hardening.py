"""TICK-501 — R-CORE-3/4/6: config persistence, cache null-guard, scanner error reporting.

Acceptance:
- GIVEN config with custom key WHEN reloaded THEN custom key preserved
- GIVEN cache init fails WHEN get_hash called THEN returns None (no crash)
- GIVEN scanner encounters FileNotFoundError WHEN scanning THEN logs warning and continues
- GIVEN scanner encounters PermissionError WHEN scanning THEN logs warning and continues
"""

import json
import logging
import sqlite3
from unittest.mock import patch



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_config_singleton():
    import importlib

    cfg_mod = importlib.import_module("dataforge.core.config")
    orig = cfg_mod.ConfigManager._instance
    cfg_mod.ConfigManager._instance = None
    # keep reference to original so caller can restore
    return cfg_mod.ConfigManager, orig


def _restore_config_singleton(orig):
    import importlib

    cfg_mod = importlib.import_module("dataforge.core.config")
    cfg_mod.ConfigManager._instance = orig


# ---------------------------------------------------------------------------
# R-CORE-3: config persistence — unknown keys preserved
# ---------------------------------------------------------------------------


class TestConfigPersistence:
    def test_custom_key_preserved_on_reload(self, tmp_path, monkeypatch):
        ConfigManager, orig = _reset_config_singleton()
        try:
            cfg_file = tmp_path / "config.json"
            cfg_dir = str(tmp_path)

            # Isolate from HOME-based paths
            monkeypatch.setenv("DATAFORGE_SKIP_LEGACY_MIGRATION", "1")

            mgr = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            mgr.set("collapsed_groups", {"group_a": True})
            mgr.set("my_custom_key", "hello")
            # Ensure saved
            with open(cfg_file) as f:
                saved = json.load(f)
            assert saved.get("collapsed_groups") == {"group_a": True}
            assert saved.get("my_custom_key") == "hello"

            # Simulate reload: reset singleton and load again
            ConfigManager._instance = None
            mgr2 = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            assert mgr2.get("collapsed_groups") == {"group_a": True}
            assert mgr2.get("my_custom_key") == "hello"
        finally:
            _restore_config_singleton(orig)

    def test_unknown_keys_survive_validation(self, tmp_path, monkeypatch):
        ConfigManager, orig = _reset_config_singleton()
        try:
            cfg_file = tmp_path / "config2.json"
            cfg_dir = str(tmp_path)
            monkeypatch.setenv("DATAFORGE_SKIP_LEGACY_MIGRATION", "1")

            mgr = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            # Inject invalid known key and unknown key directly into file
            raw = dict(mgr.data)
            raw["hash_algorithm"] = "INVALID_ALGO"  # should be rejected on reload
            raw["collapsed_groups"] = {"x": False}
            raw["plugin_foo"] = {"enabled": True}
            raw["_schema_version"] = 2
            with open(cfg_file, "w") as f:
                json.dump(raw, f)

            ConfigManager._instance = None
            mgr2 = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            # Invalid known key should revert to default, unknown keys preserved
            assert mgr2.get("hash_algorithm") == "sha256"  # default, not INVALID
            assert mgr2.get("collapsed_groups") == {"x": False}
            assert mgr2.get("plugin_foo") == {"enabled": True}
        finally:
            _restore_config_singleton(orig)

    def test_merge_preserves_unknown_via_merge_method(self, tmp_path, monkeypatch):
        """Direct _merge_validated preserves unknown keys without needing reload."""
        ConfigManager, orig = _reset_config_singleton()
        try:
            cfg_file = tmp_path / "config3.json"
            monkeypatch.setenv("DATAFORGE_SKIP_LEGACY_MIGRATION", "1")
            mgr = ConfigManager(config_file=str(cfg_file), config_dir=str(tmp_path))
            # Directly test merge
            mgr.data = dict(mgr.DEFAULT_CONFIG)
            loaded = {
                "theme": "darkly",
                "collapsed_groups": {"a": True},
                "custom_extra": 123,
            }
            mgr._merge_validated(loaded)
            assert mgr.data["theme"] == "darkly"
            assert mgr.data["collapsed_groups"] == {"a": True}
            assert mgr.data["custom_extra"] == 123
        finally:
            _restore_config_singleton(orig)


# ---------------------------------------------------------------------------
# R-CORE-4: cache null-guard
# ---------------------------------------------------------------------------


class TestCacheNullGuard:
    def _make_manager(self, tmp_path):
        from dataforge.core.cache import CacheManager

        db_path = tmp_path / "cache.db"
        cm = CacheManager(str(db_path))
        return cm

    def test_get_hash_returns_none_when_conn_none(self, tmp_path):
        cm = self._make_manager(tmp_path)
        cm.conn = None
        # Should not raise AttributeError
        assert cm.get_hash("/some/path", 100, 1234.0, "md5") is None
        cm.close()

    def test_set_hash_no_crash_when_conn_none(self, tmp_path):
        cm = self._make_manager(tmp_path)
        cm.conn = None
        # Should not raise
        cm.set_hash("/some/path", 100, 1234.0, "abc", "md5")
        cm.close()

    def test_set_hash_many_no_crash_when_conn_none(self, tmp_path):
        cm = self._make_manager(tmp_path)
        cm.conn = None
        result = cm.set_hash_many([("/a.txt", 10, 1.0, "aaa", "md5")])
        assert result is None
        # empty list also
        assert cm.set_hash_many([]) is None
        cm.close()

    def test_clear_no_crash_when_conn_none(self, tmp_path):
        cm = self._make_manager(tmp_path)
        cm.conn = None
        cm.clear()  # should not raise
        cm.close()

    def test_init_failure_leaves_conn_none_and_methods_safe(self, tmp_path, monkeypatch):
        from dataforge.core import cache as cache_mod

        original_connect = sqlite3.connect

        def failing_connect(*args, **kwargs):
            raise sqlite3.Error("simulated failure")

        monkeypatch.setattr(cache_mod.sqlite3, "connect", failing_connect)

        cm = cache_mod.CacheManager(str(tmp_path / "fail.db"))
        assert cm.conn is None
        # All methods must be safe
        assert cm.get_hash("/x", 1, 1.0) is None
        cm.set_hash("/x", 1, 1.0, "h", "md5")
        cm.set_hash_many([("/x", 1, 1.0, "h", "md5")])
        cm.clear()
        # get_user_version should still work (returns int)
        assert isinstance(cm.get_user_version(), int)
        # restore
        monkeypatch.setattr(cache_mod.sqlite3, "connect", original_connect)
        cm.close()

    def test_close_safe_when_conn_none(self, tmp_path):
        cm = self._make_manager(tmp_path)
        cm.conn = None
        cm.close()  # should not raise


# ---------------------------------------------------------------------------
# R-CORE-6: scanner error reporting
# ---------------------------------------------------------------------------


class TestScannerErrorReporting:
    def test_scan_single_dir_logs_file_not_found(self, tmp_path, caplog):
        from dataforge.core.scanner import _scan_single_dir

        caplog.set_level(logging.WARNING, logger="dataforge.core.scanner")
        missing = str(tmp_path / "does_not_exist_12345")

        files, subdirs = _scan_single_dir(missing, -1, set(), tuple())
        # Should return empty, not raise
        assert files == []
        assert subdirs == []
        # Should have logged warning containing path or FileNotFound
        warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Path not found" in m or "not found" in m.lower() or missing in m for m in warnings), warnings

    def test_scan_single_dir_logs_permission_error(self, tmp_path, caplog):
        from dataforge.core.scanner import _scan_single_dir

        caplog.set_level(logging.WARNING, logger="dataforge.core.scanner")

        # Mock os.scandir to yield an entry whose is_dir raises PermissionError
        class FakeEntry:
            path = str(tmp_path / "fake")
            name = "fake"

            def is_symlink(self):
                return False

            def is_dir(self, follow_symlinks=False):
                raise PermissionError("permission denied")

            def is_file(self, follow_symlinks=False):
                return False

            def stat(self, follow_symlinks=False):
                raise PermissionError("x")

        class FakeScandir:
            def __enter__(self):
                return [FakeEntry()]

            def __exit__(self, *args):
                return False

        with patch("dataforge.core.scanner.os.scandir", return_value=FakeScandir()):
            files, subdirs = _scan_single_dir(str(tmp_path), -1, set(), tuple())
            assert files == []
            warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
            assert any("Permission denied" in m or "permission" in m.lower() for m in warnings), warnings

    def test_scan_single_dir_generic_os_error(self, tmp_path, caplog):
        from dataforge.core.scanner import _scan_single_dir

        caplog.set_level(logging.WARNING, logger="dataforge.core.scanner")

        class FakeEntry2:
            path = str(tmp_path / "generic")
            name = "generic"

            def is_symlink(self):
                return False

            def is_dir(self, follow_symlinks=False):
                raise OSError("generic oserror")

            def is_file(self, follow_symlinks=False):
                return False

            def stat(self, follow_symlinks=False):
                raise OSError("x")

        class FakeScandir2:
            def __enter__(self):
                return [FakeEntry2()]

            def __exit__(self, *args):
                return False

        with patch("dataforge.core.scanner.os.scandir", return_value=FakeScandir2()):
            files, _ = _scan_single_dir(str(tmp_path), -1, set(), tuple())
            assert files == []
            warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
            assert any("OS error" in m for m in warnings), warnings

    def test_on_error_callback_invoked(self, tmp_path, caplog):
        from dataforge.core.scanner import _scan_single_dir

        caplog.set_level(logging.WARNING, logger="dataforge.core.scanner")
        errors = []

        def on_error(path, exc):
            errors.append((path, exc))

        # Use missing dir path which raises FileNotFoundError on scandir
        missing = str(tmp_path / "missing_callback_test")
        _scan_single_dir(missing, -1, set(), tuple(), on_error=on_error)
        assert len(errors) == 1
        assert errors[0][0] == missing
        assert isinstance(errors[0][1], FileNotFoundError)

    def test_scan_directory_logs_and_continues(self, tmp_path, caplog, monkeypatch):
        import importlib

        cfg = importlib.import_module("dataforge.core.config").config
        from dataforge.core.scanner import scan_directory

        caplog.set_level(logging.WARNING, logger="dataforge.core.scanner")
        # Ensure clean config (isolated via monkeypatch)
        monkeypatch.setattr(cfg, "data", dict(cfg.data))
        cfg.data["excluded_folders"] = []
        cfg.data["excluded_extensions"] = []

        good = tmp_path / "good"
        good.mkdir()
        (good / "keep.txt").write_text("hello")

        bad = str(tmp_path / "nonexistent_root_xyz")
        # Scan bad root — should log and return empty, not crash
        entries = list(scan_directory(bad))
        assert entries == []
        warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Path not found" in m or bad in m or "not found" in m.lower() for m in warnings), warnings
        # Still able to scan good dir after
        caplog.clear()
        entries2 = list(scan_directory(str(good)))
        assert len(entries2) == 1
        assert entries2[0].filename == "keep.txt"

    def test_scan_directory_with_on_error_continues(self, tmp_path, caplog, monkeypatch):
        import importlib

        cfg = importlib.import_module("dataforge.core.config").config
        from dataforge.core.scanner import scan_directory

        caplog.set_level(logging.WARNING, logger="dataforge.core.scanner")
        monkeypatch.setattr(cfg, "data", dict(cfg.data))
        cfg.data["excluded_folders"] = []
        cfg.data["excluded_extensions"] = []

        root = tmp_path / "root"
        root.mkdir()
        sub_good = root / "good"
        sub_good.mkdir()
        (sub_good / "a.txt").write_text("a")
        sub_bad = root / "bad"
        sub_bad.mkdir()
        (sub_bad / "b.txt").write_text("b")

        # Patch _scan_single_dir to raise PermissionError for bad subdir only
        from dataforge.core import scanner as scanner_mod

        original = scanner_mod._scan_single_dir

        def side_effect(dir_path, depth_remaining, excl_folders, excl_exts, cancel_token=None, on_error=None):
            if dir_path == str(sub_bad):
                e = PermissionError("denied")
                scanner_mod._log_scan_error(dir_path, e, on_error)
                return [], []
            return original(dir_path, depth_remaining, excl_folders, excl_exts, cancel_token, on_error)

        errors = []

        def on_error(path, exc):
            errors.append(path)

        with patch("dataforge.core.scanner._scan_single_dir", side_effect=side_effect):
            entries = list(scan_directory(str(root), on_error=on_error))
            # Should still get good file
            names = {e.filename for e in entries}
            assert "a.txt" in names
            # on_error should have been called for bad
            assert any(str(sub_bad) in p for p in errors)

    def test_scanner_handles_mixed_errors_without_crash(self, tmp_path, caplog, monkeypatch):
        """Ensure scanner yields files even when some entries raise OSError inside scan."""
        import importlib

        cfg = importlib.import_module("dataforge.core.config").config
        from dataforge.core.scanner import scan_directory

        caplog.set_level(logging.WARNING, logger="dataforge.core.scanner")
        monkeypatch.setattr(cfg, "data", dict(cfg.data))
        cfg.data["excluded_folders"] = []
        cfg.data["excluded_extensions"] = []

        root = tmp_path / "mix"
        root.mkdir()
        (root / "good1.txt").write_text("x")
        (root / "good2.txt").write_text("y")

        # Patch os.scandir to simulate one entry raising FileNotFoundError during stat
        real_scandir = __import__("os").scandir

        class BadEntry:
            def __init__(self, real_entry):
                self._real = real_entry
                self.path = real_entry.path
                self.name = real_entry.name

            def is_symlink(self):
                return self._real.is_symlink()

            def is_dir(self, follow_symlinks=False):
                return self._real.is_dir(follow_symlinks=False)

            def is_file(self, follow_symlinks=False):
                # For one file, simulate FileNotFoundError on stat only
                if self.name == "good1.txt":
                    return True
                return self._real.is_file(follow_symlinks=False)

            def stat(self, follow_symlinks=False):
                if self.name == "good1.txt":
                    raise FileNotFoundError("simulated missing after scandir")
                return self._real.stat(follow_symlinks=False)

        def fake_scandir(path):
            # Only intercept the root scan
            if path == str(root):
                real_it = real_scandir(path)

                class Wrap:
                    def __enter__(self):
                        entries = list(real_it.__enter__())
                        return [BadEntry(e) for e in entries]

                    def __exit__(self, *a):
                        return real_it.__exit__(*a)

                return Wrap()
            return real_scandir(path)

        with patch("dataforge.core.scanner.os.scandir", side_effect=fake_scandir):
            entries = list(scan_directory(str(root)))
            # good2 should still be found, good1 was skipped due to FileNotFoundError
            names = {e.filename for e in entries}
            assert "good2.txt" in names
            assert "good1.txt" not in names
            # Warning should have been logged
            warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
            assert any("Path not found" in m for m in warnings), warnings
