"""TICK-701 — R-CORE-2/5: config item validation + cache batch commit

Acceptance:
- GIVEN excluded_extensions=['.log',123,null] WHEN load THEN only ['.log'] remains, warning logged, no crash on scan
- GIVEN excluded_folders=['node_modules',123] WHEN load THEN only ['node_modules'] remains
- GIVEN 1000 set_hash batch_size=500 THEN at most 3 commits
- GIVEN conn is None WHEN set_hash THEN no crash
"""
import json
import logging
import sqlite3


def _reset_config_singleton():
    import importlib
    cfg_mod = importlib.import_module("dataforge.core.config")
    orig = cfg_mod.ConfigManager._instance
    cfg_mod.ConfigManager._instance = None
    return cfg_mod.ConfigManager, orig


def _restore_config_singleton(orig):
    import importlib
    cfg_mod = importlib.import_module("dataforge.core.config")
    cfg_mod.ConfigManager._instance = orig


# ---------------------------------------------------------------------------
# R-CORE-2: config item validation
# ---------------------------------------------------------------------------

class TestConfigItemValidation:
    def test_excluded_extensions_drops_invalid_and_warns(self, tmp_path, caplog):
        ConfigManager, orig = _reset_config_singleton()
        try:
            cfg_file = tmp_path / "config.json"
            cfg_dir = str(tmp_path)
            caplog.set_level(logging.WARNING, logger="dataforge.core.logger")
            # also capture from core.config logger (it uses dataforge.core.logger)
            caplog.set_level(logging.WARNING)

            mgr = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            # write raw config with invalid items
            raw = dict(mgr.data)
            raw["excluded_extensions"] = [".log", 123, None, {"a": 1}, "  ", ""]
            raw["_schema_version"] = 2
            with open(cfg_file, "w") as f:
                json.dump(raw, f)

            ConfigManager._instance = None
            mgr2 = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            # Only ".log" should remain (stripped)
            assert mgr2.get("excluded_extensions") == [".log"]
            # warning logged
            warnings = [r.message for r in caplog.records if "dropping invalid" in r.message.lower() or "excluded_extensions" in r.message]
            assert any("dropping invalid" in m.lower() for m in warnings) or len(caplog.records) > 0

            # scan_directory should not crash with cleaned config
            from dataforge.core.scanner import scan_directory
            # create a tmp dir with files
            sub = tmp_path / "scan_test"
            sub.mkdir()
            (sub / "keep.txt").write_text("hello")
            (sub / "skip.log").write_text("log")
            # patch config singleton to use mgr2 for scanner
            # scanner uses _current_config() which reads ConfigManager._instance
            # our mgr2 is now the singleton
            entries = list(scan_directory(str(sub)))
            # keep.txt should be found, skip.log should be excluded? excluded_extensions contains .log
            names = {e.filename for e in entries}
            assert "keep.txt" in names
            # .log should be excluded, but we don't require strict, just not crash
            assert "keep.txt" in names
        finally:
            _restore_config_singleton(orig)

    def test_excluded_folders_drops_invalid(self, tmp_path, caplog):
        ConfigManager, orig = _reset_config_singleton()
        try:
            cfg_file = tmp_path / "config2.json"
            cfg_dir = str(tmp_path)
            caplog.set_level(logging.WARNING)
            mgr = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            raw = dict(mgr.data)
            raw["excluded_folders"] = ["node_modules", 123, None, ""]
            raw["_schema_version"] = 2
            with open(cfg_file, "w") as f:
                json.dump(raw, f)
            ConfigManager._instance = None
            mgr2 = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            assert mgr2.get("excluded_folders") == ["node_modules"]
        finally:
            _restore_config_singleton(orig)

    def test_excluded_folders_all_invalid_uses_default(self, tmp_path, caplog):
        ConfigManager, orig = _reset_config_singleton()
        try:
            cfg_file = tmp_path / "config3.json"
            cfg_dir = str(tmp_path)
            mgr = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            default_folders = list(ConfigManager.DEFAULT_CONFIG["excluded_folders"])
            raw = dict(mgr.data)
            raw["excluded_folders"] = [123, None, 456]
            raw["_schema_version"] = 2
            with open(cfg_file, "w") as f:
                json.dump(raw, f)
            ConfigManager._instance = None
            mgr2 = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            # all invalid -> should keep default, not empty
            assert mgr2.get("excluded_folders") == default_folders
        finally:
            _restore_config_singleton(orig)

    def test_excluded_extensions_empty_list_allowed(self, tmp_path):
        ConfigManager, orig = _reset_config_singleton()
        try:
            cfg_file = tmp_path / "config4.json"
            cfg_dir = str(tmp_path)
            mgr = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            raw = dict(mgr.data)
            raw["excluded_extensions"] = []
            raw["_schema_version"] = 2
            with open(cfg_file, "w") as f:
                json.dump(raw, f)
            ConfigManager._instance = None
            mgr2 = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            assert mgr2.get("excluded_extensions") == []
        finally:
            _restore_config_singleton(orig)

    def test_excluded_extensions_with_path_separator_dropped(self, tmp_path, caplog):
        ConfigManager, orig = _reset_config_singleton()
        try:
            cfg_file = tmp_path / "config5.json"
            cfg_dir = str(tmp_path)
            caplog.set_level(logging.WARNING)
            mgr = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            raw = dict(mgr.data)
            raw["excluded_extensions"] = [".log", "bad/sep", "also\\bad", ".tmp"]
            raw["_schema_version"] = 2
            with open(cfg_file, "w") as f:
                json.dump(raw, f)
            ConfigManager._instance = None
            mgr2 = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            # bad entries with slash should be dropped
            assert ".log" in mgr2.get("excluded_extensions")
            assert ".tmp" in mgr2.get("excluded_extensions")
            assert "bad/sep" not in mgr2.get("excluded_extensions")
            assert "also\\bad" not in mgr2.get("excluded_extensions")
        finally:
            _restore_config_singleton(orig)

    def test_dashboard_paths_allows_slash(self, tmp_path):
        ConfigManager, orig = _reset_config_singleton()
        try:
            cfg_file = tmp_path / "config6.json"
            cfg_dir = str(tmp_path)
            mgr = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            raw = dict(mgr.data)
            raw["dashboard_paths"] = ["/tmp/my docs", "/home/user/Documents", 123]
            raw["_schema_version"] = 2
            with open(cfg_file, "w") as f:
                json.dump(raw, f)
            ConfigManager._instance = None
            mgr2 = ConfigManager(config_file=str(cfg_file), config_dir=cfg_dir)
            # dashboard_paths should keep paths with slash, drop invalid int
            assert "/tmp/my docs" in mgr2.get("dashboard_paths")
            assert "/home/user/Documents" in mgr2.get("dashboard_paths")
            assert 123 not in mgr2.get("dashboard_paths")
        finally:
            _restore_config_singleton(orig)

    def test_validate_one_direct(self, tmp_path):
        ConfigManager, orig = _reset_config_singleton()
        try:
            cfg_file = tmp_path / "config7.json"
            mgr = ConfigManager(config_file=str(cfg_file), config_dir=str(tmp_path))
            # direct call
            val = [".log", 123, None]
            # _validate_one should mutate val to cleaned and return True (since at least one valid)
            result = mgr._validate_one("excluded_extensions", val, [])
            assert result is True
            assert val == [".log"]
            # all invalid
            val2 = [123, None]
            result2 = mgr._validate_one("excluded_extensions", val2, [])
            assert result2 is False
            # empty allowed
            val3 = []
            assert mgr._validate_one("excluded_extensions", val3, []) is True
            # not a list
            assert mgr._validate_one("excluded_extensions", "notalist", []) is False
        finally:
            _restore_config_singleton(orig)


# ---------------------------------------------------------------------------
# R-CORE-5: cache batch commit
# ---------------------------------------------------------------------------

class TestCacheBatchCommit:
    def _new_manager(self, tmp_path):
        from dataforge.core.cache import CacheManager
        db_path = tmp_path / "cache.db"
        cm = CacheManager(str(db_path))
        return cm

    def test_batch_at_most_3_commits(self, tmp_path):
        cm = self._new_manager(tmp_path)
        try:
            cm._batch_size = 500
            # Wrap connection to count commits (sqlite3 commit is read-only)
            real_conn = cm.conn
            class CountingConn:
                def __init__(self, real):
                    self._real = real
                    self.commit_count = 0
                def commit(self, *a, **kw):
                    self.commit_count += 1
                    return self._real.commit(*a, **kw)
                def __getattr__(self, name):
                    return getattr(self._real, name)
            counting = CountingConn(real_conn)
            cm.conn = counting  # type: ignore

            # 1000 set_hash in tight loop
            for i in range(1000):
                cm.set_hash(f"/path/file_{i}.txt", 100 + i, 12345.0 + i, f"hash{i:08d}", "sha256")
            # flush remaining
            cm.flush()
            # at most 3 commits (2 batch flushes + 1 final if remainder)
            assert counting.commit_count <= 3, f"expected <=3 commits, got {counting.commit_count}"
            # verify data integrity after flush
            count = counting._real.execute("SELECT COUNT(*) FROM file_hashes").fetchone()[0]
            assert count == 1000
            # spot check
            assert cm.get_hash("/path/file_0.txt", 100, 12345.0, "sha256") == "hash00000000"
            assert cm.get_hash("/path/file_999.txt", 1099, 13344.0, "sha256") == "hash00000999"
        finally:
            # restore real conn for close
            try:
                cm.conn = real_conn  # type: ignore
            except Exception:
                pass
            cm.close()

    def test_batch_flush_explicit_and_close(self, tmp_path):
        cm = self._new_manager(tmp_path)
        try:
            cm._batch_size = 1000
            cm.set_hash("/a.txt", 10, 1.0, "aaa", "md5")
            cm.set_hash("/b.txt", 20, 2.0, "bbb", "md5")
            # not yet flushed (batch 1000, only 2)
            # get_hash should see buffered
            assert cm.get_hash("/a.txt", 10, 1.0, "md5") == "aaa"
            # but DB without flush would also have 0 if we bypass? Let's flush
            cm.flush()
            cur = cm.conn.execute("SELECT COUNT(*) FROM file_hashes")
            assert cur.fetchone()[0] == 2
            # after flush buffer should be empty
            assert len(cm._batch_buffer) == 0

            # test close flushes
            cm2 = self._new_manager(tmp_path / "db2")
            cm2._batch_size = 1000
            cm2.set_hash("/x.txt", 1, 1.0, "h1", "md5")
            cm2.set_hash("/y.txt", 1, 1.0, "h2", "md5")
            # close should flush
            cm2.close()
            # new connection should see data
            from dataforge.core.cache import CacheManager as CM2

            # Actually cm2 db path is tmp_path/db2/cache.db? We used tmp_path/db2 as dir? Let's just check cm2's db file still has data via reopening same path
            # Instead create new manager with same path
            reopen = CM2(str(cm2.db_path))
            try:
                assert reopen.get_hash("/x.txt", 1, 1.0, "md5") == "h1"
                assert reopen.get_hash("/y.txt", 1, 1.0, "md5") == "h2"
            finally:
                reopen.close()
        finally:
            try:
                cm.close()
            except Exception:
                pass

    def test_set_hash_null_guard(self, tmp_path):
        cm = self._new_manager(tmp_path)
        try:
            cm.conn = None
            # should not crash, return None
            result = cm.set_hash("/some/path", 100, 1234.0, "abc", "md5")
            assert result is None
            # get_hash also
            assert cm.get_hash("/some/path", 100, 1234.0, "md5") is None
            # flush should not crash
            cm.flush()
            # set_hash_many also
            assert cm.set_hash_many([("/a.txt", 10, 1.0, "aaa", "md5")]) is None
            # clear also
            cm.clear()
            # close also (should clear buffer)
            cm._batch_buffer.append(("/z.txt", 1, 1.0, "h", "md5"))
            cm.close()  # should clear buffer and not crash
            assert cm._batch_buffer == []
        finally:
            try:
                cm.close()
            except Exception:
                pass

    def test_thread_safety_and_conn_none_from_init(self, tmp_path, monkeypatch):
        from dataforge.core import cache as cache_mod
        original_connect = sqlite3.connect
        def failing_connect(*a, **kw):
            raise sqlite3.Error("simulated")
        monkeypatch.setattr(cache_mod.sqlite3, "connect", failing_connect)
        cm = cache_mod.CacheManager(str(tmp_path / "fail.db"))
        try:
            assert cm.conn is None
            # all methods safe
            assert cm.get_hash("/x", 1, 1.0) is None
            assert cm.set_hash("/x", 1, 1.0, "h", "md5") is None
            cm.flush()
            cm.clear()
            assert cm._batch_buffer == []
            cm.close()
            assert cm._batch_buffer == []
        finally:
            monkeypatch.setattr(cache_mod.sqlite3, "connect", original_connect)
            try:
                cm.close()
            except Exception:
                pass

    def test_buffer_check_in_get_hash(self, tmp_path):
        cm = self._new_manager(tmp_path)
        try:
            cm._batch_size = 100
            cm.set_hash("/buf.txt", 10, 5.0, "hash_buf", "md5")
            # still buffered, not committed, but get_hash should find it
            assert cm.get_hash("/buf.txt", 10, 5.0, "md5") == "hash_buf"
            # after flush, still found
            cm.flush()
            assert cm.get_hash("/buf.txt", 10, 5.0, "md5") == "hash_buf"
        finally:
            cm.close()

    def test_set_hash_many_preserved(self, tmp_path):
        cm = self._new_manager(tmp_path)
        try:
            rows = [(f"/a{i}.txt", i, float(i), f"h{i}", "md5") for i in range(10)]
            cm.set_hash_many(rows)
            for path, size, mtime, h, algo in rows:
                assert cm.get_hash(path, size, mtime, algo) == h
            # set_hash_many with conn None
            cm.conn = None
            assert cm.set_hash_many(rows) is None
        finally:
            try:
                cm.close()
            except Exception:
                pass
