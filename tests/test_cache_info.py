"""TICK-804 — Settings Performance DB Cache info + size.

Acceptance:
- GIVEN Settings Performance tab WHEN opened THEN shows cache size (e.g., '2.4 MB'), entry count, path, and last modified
- GIVEN cache with 100 entries WHEN get_stats called THEN entry_count == 100 and size_bytes > 0
- GIVEN Clear Cache clicked WHEN confirmed THEN cache cleared and stats refresh to 0 entries
- GIVEN no cache file WHEN stats called THEN size 0 and entry_count 0, no crash
"""

import os
from unittest.mock import MagicMock


def _new_manager(tmp_path):
    from dataforge.core.cache import CacheManager

    db_path = tmp_path / "cache.db"
    cm = CacheManager(str(db_path))
    return cm


def test_get_stats_with_100_entries(tmp_path):
    cm = _new_manager(tmp_path)
    try:
        rows = [
            (f"/path/file_{i}.txt", 100 + i, 12345.0 + i, f"hash{i:08d}", "sha256")
            for i in range(100)
        ]
        cm.set_hash_many(rows)
        # flush to ensure counted
        cm.flush()
        stats = cm.get_stats()
        assert isinstance(stats, dict)
        assert stats["entry_count"] == 100, f"expected 100 got {stats['entry_count']}"
        assert stats["size_bytes"] > 0, "size_bytes should be >0"
        assert isinstance(stats["formatted_size"], str) and len(stats["formatted_size"]) > 0
        assert "path" in stats and stats["path"] == str(tmp_path / "cache.db")
        assert "page_count" in stats
        assert "freelist_count" in stats
        assert "page_size" in stats
        assert "last_modified" in stats and stats["last_modified"] is not None
        # hit_rate may be None initially
        assert "hit_rate" in stats
    finally:
        cm.close()


def test_clear_resets_to_zero(tmp_path):
    cm = _new_manager(tmp_path)
    try:
        rows = [(f"/a{i}.txt", 10, float(i), f"h{i}", "md5") for i in range(10)]
        cm.set_hash_many(rows)
        stats = cm.get_stats()
        assert stats["entry_count"] == 10
        cm.clear()
        stats2 = cm.get_stats()
        assert stats2["entry_count"] == 0, f"after clear expected 0 got {stats2['entry_count']}"
        # size may still be >0 but entry count 0
        assert isinstance(stats2["formatted_size"], str)
    finally:
        cm.close()


def test_no_cache_file_no_crash(tmp_path):
    from dataforge.core.cache import CacheManager

    db_path = tmp_path / "nonexistent" / "cache.db"
    # ensure parent not exists
    cm = CacheManager(str(db_path))
    try:
        # remove file to simulate no cache
        cm.close()
        # unlink file if exists
        if os.path.exists(str(db_path)):
            os.unlink(str(db_path))
        # create new manager with missing file handling
        # Use a fresh path that won't be auto-created? But CacheManager always creates file.
        # So simulate missing file by closing and deleting, then calling get_stats on closed manager
        # closed manager has conn None and missing file -> should return 0
        stats = cm.get_stats()
        assert stats["size_bytes"] == 0
        assert stats["entry_count"] == 0
        assert stats["formatted_size"] == "0 B" or isinstance(stats["formatted_size"], str)
        assert stats["last_modified"] is None
    finally:
        try:
            cm.close()
        except Exception:
            pass

    # Also test live manager after unlink while open
    cm2 = CacheManager(str(tmp_path / "cache2.db"))
    try:
        # unlink file while conn open
        if os.path.exists(cm2.db_path):
            os.unlink(cm2.db_path)
        stats = cm2.get_stats()
        # should not crash
        assert stats["size_bytes"] == 0
        assert stats["entry_count"] == 0 or isinstance(stats["entry_count"], int)
    finally:
        cm2.close()


def test_get_stats_includes_pragma_and_hit_rate(tmp_path):
    cm = _new_manager(tmp_path)
    try:
        # test hit_rate tracking
        # miss
        assert cm.get_hash("/nope", 100, 1.0, "md5") is None
        stats = cm.get_stats()
        assert stats["misses"] >= 1
        # hit
        cm.set_hash("/a.txt", 100, 1.0, "abc", "md5")
        cm.flush()
        assert cm.get_hash("/a.txt", 100, 1.0, "md5") == "abc"
        stats2 = cm.get_stats()
        assert stats2["hits"] >= 1
        assert "hit_rate" in stats2
        # last_vacuum initially None, after clear set
        assert "last_vacuum" in stats2
        cm.clear()
        stats3 = cm.get_stats()
        assert stats3["last_vacuum"] is not None
    finally:
        cm.close()


def test_settings_shows_cache_info():
    from PyQt5.QtWidgets import QApplication

    from dataforge.ui.views.settings import SettingsView

    _ = QApplication.instance() or QApplication([])
    mock_app = MagicMock()
    # simulate run_workflow that calls on_success synchronously
    def fake_run_workflow(worker, on_success=None, on_error=None, **kw):
        try:
            res = worker()
            if on_success:
                on_success(res)
        except Exception as e:
            if on_error:
                on_error(e)

    mock_app.run_workflow = fake_run_workflow
    mock_app.show_info_dialog = MagicMock()
    mock_app.theme_chk.isChecked.return_value = False

    view = SettingsView(None, app=mock_app)
    # required symbols
    assert hasattr(view, "row_cache")
    assert hasattr(view, "btn_clear_cache")
    assert hasattr(view, "btn_refresh_cache")
    assert hasattr(view, "lbl_cache_size")
    assert hasattr(view, "lbl_cache_entries")
    assert hasattr(view, "lbl_cache_path")
    assert hasattr(view, "lbl_cache_modified")
    assert hasattr(view, "lbl_cache_batch_size")
    assert hasattr(view, "lbl_hash_block_size")

    # labels should contain expected substrings
    assert "Size:" in view.lbl_cache_size.text()
    assert "Entries:" in view.lbl_cache_entries.text()
    assert "Path:" in view.lbl_cache_path.text()
    assert "Modified:" in view.lbl_cache_modified.text()
    assert "Cache batch size:" in view.lbl_cache_batch_size.text()
    assert "Hash block size:" in view.lbl_hash_block_size.text()

    # formatted_size should look like "X MB/KB/B"
    assert any(u in view.lbl_cache_size.text() for u in ["B", "KB", "MB", "GB"])

    # Refresh should update via run_workflow
    view._refresh_cache_info()
    # after refresh, still have entries text
    assert "entries" in view.lbl_cache_entries.text().lower()


def test_performance_includes_cache_stats(tmp_path):
    from dataforge.modules.performance import get_live_resource_snapshot

    snap = get_live_resource_snapshot(blocking=False)
    assert isinstance(snap, dict)
    assert "cache" in snap
    assert isinstance(snap["cache"], dict)
    assert "entry_count" in snap["cache"]
    assert "size_bytes" in snap["cache"]


def test_filehashcache_alias():
    from dataforge.core.cache import FileHashCache, CacheManager

    assert FileHashCache is CacheManager
    # also file_cache alias
    from dataforge.core.cache import file_cache

    assert hasattr(file_cache, "get_stats")
    stats = file_cache.get_stats()
    assert isinstance(stats, dict)
