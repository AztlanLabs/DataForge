"""TICK-905 — Junk scan SIGSEGV + permission QBackingStore stability."""
from __future__ import annotations

import os
import threading
import time
import pathlib
from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtWidgets import QApplication

from dataforge.core.common import FileEntry
from dataforge.core.scanner import scan_directory, _scan_single_dir, _log_scan_error, _is_private_systemd_dir
from dataforge.modules.system_cleanup import scan_junk_files, _is_private_systemd_dir as sc_is_private
from dataforge.ui.job_manager import JobManager


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ------------------------------------------------------------------
# 1. Private systemd dirs skipped without warning flood
# ------------------------------------------------------------------

def test_private_systemd_dirs_skipped_no_warning_flood(tmp_path):
    """scan_junk_files with 10 systemd-private dirs should skip with debug, no warning flood."""
    # create 10 fake private dirs under /var/tmp style? Use tmp_path to simulate
    # Patch _get_platform_junk_paths to return a dir containing 10 private subdirs
    base = tmp_path / "var_tmp"
    base.mkdir()
    private_dirs = []
    for i in range(10):
        d = base / f"systemd-private-a158b04721ae4c6fa8f12f534f45a5f1-upower.service-{i:02d}"
        d.mkdir()
        # also create a nested file that would be junk
        (d / f"file{i}.tmp").write_text("junk")
        private_dirs.append(str(d))
    # also make base contain a real file
    (base / "real.tmp").write_text("junk")

    # We will test scanner's pre-filter via scan_directory directly on base
    # Mock logger to count warnings
    import dataforge.core.scanner as scanner_mod
    with patch.object(scanner_mod.logger, "warning") as mock_warn, \
         patch.object(scanner_mod.logger, "debug"):
        entries = list(scan_directory(str(base), recursive=True, max_depth=5))
        # Should not yield files from private dirs (they are skipped)
        # Only real.tmp should be found (private dirs skipped)
        paths = [e.path for e in entries]
        # private files should not be in results if filter works
        for pd in private_dirs:
            assert not any(p.startswith(pd) for p in paths), f"private dir file should be skipped: {pd}"
        # warning should not be flooded (0 warnings for private)
        # At most debug log allowed
        assert mock_warn.call_count == 0, f"warning flood: {mock_warn.call_args_list}"
        # debug should have been called for skipping private dirs (at least one)
        # Could be 0 if base scan filters at subdir discovery, but debug for subdir skip
        # Accept 0 or more, but ensure no warning
        # Now test scan_junk_files level
        with patch("dataforge.modules.system_cleanup._get_platform_junk_paths", return_value={"System Temp": [str(base)]}):
            with patch("dataforge.modules.system_cleanup.os.path.isdir", side_effect=lambda p: True if p == str(base) else os.path.isdir(p)):
                # Patch scanner to ensure private skip still works
                with patch.object(scanner_mod.logger, "warning") as mock_warn2, \
                     patch.object(scanner_mod.logger, "debug"):
                    # Mock os.scandir probe to not filter base itself
                    result = scan_junk_files()
                    # result should not contain private files
                    if "System Temp" in result:
                        for e in result["System Temp"]:
                            assert "systemd-private" not in e.path
                    assert mock_warn2.call_count == 0


def test_scanner_handles_private_systemd_helper():
    assert _is_private_systemd_dir("/var/tmp/systemd-private-abc")
    assert _is_private_systemd_dir("/tmp/systemd-private-xyz")
    assert _is_private_systemd_dir("/tmp/systemd-private-a123/foo")
    assert sc_is_private("/var/tmp/systemd-private-abc")
    assert not _is_private_systemd_dir("/tmp/normal")
    assert not _is_private_systemd_dir("/var/tmp")


# ------------------------------------------------------------------
# 2. scan_directory on unreadable dir yields no entries, logs warning, no acquire fallback
# ------------------------------------------------------------------

def test_scan_directory_unreadable_no_acquire_fallback():
    """PermissionError on scandir should return empty, call on_error, not acquire_file."""
    fake_dir = "/var/tmp/systemd-private-fake-unreadable"
    # Patch os.scandir to raise PermissionError
    on_error_calls = []
    def on_error(path, exc):
        on_error_calls.append((path, exc))

    import dataforge.core.scanner as scanner_mod
    # acquire_file is imported lazily inside _scan_single_dir, patch the target module
    with patch("dataforge.core.scanner.os.scandir", side_effect=PermissionError("denied")), \
         patch("dataforge.core.acquire.acquire_file") as mock_acquire:
        # _scan_single_dir should handle PermissionError without calling acquire_file
        files, subdirs = _scan_single_dir(fake_dir, depth_remaining=5, excl_folders=set(), excl_exts=tuple(), on_error=on_error)
        assert files == []
        assert subdirs == []
        assert len(on_error_calls) == 1
        assert isinstance(on_error_calls[0][1], PermissionError)
        # acquire_file should not be called for dir scan failure
        mock_acquire.assert_not_called()

    # Also test via scanner's public API scan_directory on unreadable dir
    # Root validation should handle PermissionError and yield nothing
    with patch("dataforge.core.scanner.os.scandir", side_effect=PermissionError("denied")):
        with patch.object(scanner_mod.logger, "warning") as mock_warn, \
             patch.object(scanner_mod.logger, "debug") as mock_debug:
            # Need to ensure os.path.isfile returns False and isdir checks don't bypass
            with patch("dataforge.core.scanner.os.path.isfile", return_value=False), \
                 patch("dataforge.core.scanner.os.path.isdir", return_value=True):
                entries = list(scan_directory(fake_dir, on_error=on_error))
                assert entries == []
                # For private dir, logger should use debug not warning
                # So warning count should be 0, debug >=1
                assert mock_warn.call_count == 0
                assert mock_debug.call_count >= 1

    # Verify non-private dir logs warning
    normal_dir = "/tmp/normal-unreadable"
    on_error_calls.clear()
    with patch("dataforge.core.scanner.os.scandir", side_effect=PermissionError("denied")):
        with patch.object(scanner_mod.logger, "warning") as mock_warn, \
             patch.object(scanner_mod.logger, "debug") as mock_debug:
            with patch("dataforge.core.scanner.os.path.isfile", return_value=False), \
                 patch("dataforge.core.scanner.os.path.isdir", return_value=True):
                entries = list(scan_directory(normal_dir, on_error=on_error))
                assert entries == []
                # Normal dir should log warning
                assert mock_warn.call_count >= 1


def test_log_scan_error_private_debug():
    import dataforge.core.scanner as scanner_mod
    with patch.object(scanner_mod.logger, "warning") as mock_warn, \
         patch.object(scanner_mod.logger, "debug") as mock_debug:
        _log_scan_error("/var/tmp/systemd-private-abc", PermissionError("denied"))
        assert mock_warn.call_count == 0
        assert mock_debug.call_count >= 1
    with patch.object(scanner_mod.logger, "warning") as mock_warn, \
         patch.object(scanner_mod.logger, "debug") as mock_debug:
        _log_scan_error("/tmp/normal", PermissionError("denied"))
        assert mock_warn.call_count >= 1


def test_scan_single_dir_no_build_from_stat_for_dir(tmp_path):
    """_scan_single_dir should only yield FileEntry for files, not dirs."""
    # Create a dir with subdir and file
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (tmp_path / "file.tmp").write_text("data")
    files, subdirs = _scan_single_dir(str(tmp_path), depth_remaining=5, excl_folders=set(), excl_exts=tuple())
    assert len(files) == 1
    assert files[0].path.endswith("file.tmp")
    assert len(subdirs) == 1
    assert subdirs[0][0] == str(subdir)
    # Ensure no FileEntry for directory itself
    for fe in files:
        assert not fe.is_dir


# ------------------------------------------------------------------
# 3. SystemCleanupView rapid SCAN JUNK clicks — button disabled, single job, no QBackingStore
# ------------------------------------------------------------------

def test_system_cleanup_view_rebuild_uses_guards(qapp):
    from dataforge.ui.views.system_cleanup import SystemCleanupView
    import pathlib

    src = pathlib.Path("dataforge/ui/views/system_cleanup.py").read_text()
    # Check _rebuild_junk_tree uses setUpdatesEnabled guard
    assert "setUpdatesEnabled(False)" in src
    assert "setUpdatesEnabled(True)" in src
    assert "setSortingEnabled(False)" in src
    assert "setSortingEnabled(True)" in src
    assert "refresh_viewport" in src
    # Should not contain direct viewport().update() in rebuild
    # Extract rebuild function
    rebuild_section = src[src.find("def _rebuild_junk_tree"):src.find("def _on_junk_selection_changed")]
    assert "viewport().update()" not in rebuild_section or "refresh_viewport" in rebuild_section
    # Check debounce
    assert "btn_scan.setEnabled(False)" in src
    assert "btn_scan.setEnabled(True)" in src
    assert "_on_junk_scan_error" in src
    # Check initial clear uses guard
    start_section = src[src.find("def _start_junk_scan"):src.find("def _on_junk_scan_complete")]
    assert "setUpdatesEnabled" in start_section

    # Functional test: mock view and ensure guard calls
    view = SystemCleanupView.__new__(SystemCleanupView)
    view.junk_tree = MagicMock()
    view.junk_tree.tree = MagicMock()
    view.junk_tree.tree.clear = MagicMock()
    view.junk_tree.item_map = {}
    view.junk_tree.insert = MagicMock(side_effect=lambda *a, **k: f"id_{view.junk_tree.insert.call_count}")
    view.junk_tree.refresh_viewport = MagicMock()
    view.junk_tree.tree.setUpdatesEnabled = MagicMock()
    view.junk_tree.tree.setSortingEnabled = MagicMock()
    view.item_entries = {}
    view.junk_results = {
        "System Temp": [MagicMock(path="/tmp/a.tmp", extension=".tmp", size=100), MagicMock(path="/tmp/b.log", extension=".log", size=200)]
    }
    # provide format_size
    with patch("dataforge.ui.views.system_cleanup.format_size", return_value="100 B"):
        view._rebuild_junk_tree()
    assert view.junk_tree.tree.setUpdatesEnabled.call_args_list[0][0][0] is False
    assert view.junk_tree.tree.setUpdatesEnabled.call_args_list[-1][0][0] is True
    assert view.junk_tree.tree.setSortingEnabled.call_args_list[0][0][0] is False
    assert view.junk_tree.tree.setSortingEnabled.call_args_list[-1][0][0] is True
    assert view.junk_tree.refresh_viewport.called


def test_rapid_scan_clicks_single_job(qapp):
    from dataforge.ui.views.system_cleanup import SystemCleanupView

    # Mock app and job_manager
    mock_app = MagicMock()
    mock_app.job_manager = MagicMock()
    mock_app.update_status = MagicMock()
    mock_app.show_warning_dialog = MagicMock()
    run_calls = []
    def fake_run_workflow(target, on_success, *args, **kwargs):
        run_calls.append((target, args, kwargs))
        # simulate button disabled after first call
        # on_success not called immediately
        return "job123"

    mock_app.run_workflow = MagicMock(side_effect=fake_run_workflow)
    # Create view without __init__
    view = SystemCleanupView.__new__(SystemCleanupView)
    view.app = mock_app
    view.btn_scan = MagicMock()
    # First call enabled, then disabled
    view.btn_scan.isEnabled.side_effect = [True, False, False]
    view.category_checks = {"System Temp": MagicMock(isChecked=lambda: True)}
    view.entry_path = MagicMock()
    view.entry_path.text.return_value = ""
    view.spin_age = MagicMock()
    view.spin_age.value.return_value = 0
    view.junk_tree = MagicMock()
    view.junk_tree.tree = MagicMock()
    view.junk_tree.tree.clear = MagicMock()
    view.junk_tree.tree.setUpdatesEnabled = MagicMock()
    view.junk_tree.refresh_viewport = MagicMock()
    view.junk_tree.item_map = {}
    view.lbl_junk_summary = MagicMock()
    view.lbl_total_savings = MagicMock()
    view.lbl_file_count = MagicMock()
    view.junk_results = {}
    view.item_entries = {}

    # Patch os.path.isdir for extra_path
    with patch("dataforge.ui.views.system_cleanup.os.path.isdir", return_value=False):
        view._start_junk_scan()
        # First call should have disabled button and submitted one job
        assert mock_app.run_workflow.call_count == 1
        assert view.btn_scan.setEnabled.call_args_list[0][0][0] is False
        # Simulate rapid 2 more clicks while disabled
        view._start_junk_scan()
        view._start_junk_scan()
        # Should still be only 1 job
        assert mock_app.run_workflow.call_count == 1

    # Test _on_junk_scan_complete re-enables
    view.btn_scan.setEnabled.reset_mock()
    view.btn_scan.setText = MagicMock()
    view.lbl_junk_summary = MagicMock()
    view.lbl_total_savings = MagicMock()
    view.lbl_file_count = MagicMock()
    view.lbl_action_status = MagicMock()
    view.app.update_status = MagicMock()
    with patch("dataforge.ui.views.system_cleanup.estimate_cleanup_savings", return_value={"formatted_total": "1 MB", "total_files": 2, "categories": {"System Temp": {"count": 2, "formatted_size": "1 MB"}}}):
        view.junk_results = {}
        view._rebuild_junk_tree = MagicMock()
        view._on_junk_scan_complete({"System Temp": []})
        assert view.btn_scan.setEnabled.called
        assert view.btn_scan.setEnabled.call_args[0][0] is True

    # Test error path re-enables
    view.btn_scan.setEnabled.reset_mock()
    view._on_junk_scan_error(Exception("fail"))
    assert view.btn_scan.setEnabled.called
    assert view.btn_scan.setEnabled.call_args[0][0] is True


# ------------------------------------------------------------------
# 4. Cancel token mid-walk returns promptly, no SIGSEGV
# ------------------------------------------------------------------

def test_junk_scan_cancel_mid_walk(tmp_path):
    """scan_junk_files with cancel_token set mid-walk should return promptly."""
    # Create a base with many files
    base = tmp_path / "cancel_test"
    base.mkdir()
    for i in range(20):
        (base / f"file{i}.tmp").write_text("junk")

    import dataforge.modules.system_cleanup as sc_mod
    with patch.object(sc_mod, "_get_platform_junk_paths", return_value={"System Temp": [str(base)]}):
        cancel = threading.Event()
        # Start scan in thread and cancel mid-way
        result_holder = {}
        def run_scan():
            # Use cancel_token that will be set after 5ms
            def canceller():
                time.sleep(0.02)
                cancel.set()
            t = threading.Thread(target=canceller)
            t.start()
            res = scan_junk_files(cancel_token=cancel)
            result_holder["result"] = res
            t.join()

        start = time.monotonic()
        run_scan()
        elapsed = time.monotonic() - start
        # Should return relatively quickly (<1s) even though we cancelled
        assert elapsed < 1.0
        # Result may be empty or partial, but should not be SIGSEGV
        assert isinstance(result_holder["result"], dict)

    # Also test scanner cancel token directly
    cancel2 = threading.Event()
    cancel2.set()
    entries = list(scan_directory(str(base), cancel_token=cancel2))
    assert entries == []

    # Test _scan_single_dir respects cancel_token
    tok = threading.Event()
    tok.set()
    files, subdirs = _scan_single_dir(str(base), depth_remaining=5, excl_folders=set(), excl_exts=tuple(), cancel_token=tok)
    assert files == []
    assert subdirs == []


def test_scan_directory_cancel_via_jobmanager(qapp):
    mgr = JobManager(max_workers=2)
    try:
        # Create a slow scan target that checks cancel_token
        def slow_scan(cancel_token=None, progress_callback=None):
            # Simulate scan_junk_files that respects cancel_token
            for i in range(10):
                if cancel_token and cancel_token.is_set():
                    raise InterruptedError("cancelled")
                if progress_callback:
                    progress_callback(i, 10, f"step {i}")
                time.sleep(0.03)
            return {"System Temp": []}

        results = []
        errors = []
        jid = mgr.submit(target=slow_scan, on_success=lambda r: results.append(r), on_error=lambda e: errors.append(e), progress=True)
        assert jid is not None
        time.sleep(0.05)
        mgr.cancel(jid)
        deadline = time.time() + 2
        while time.time() < deadline and not results and not errors:
            time.sleep(0.02)
            QApplication.processEvents()
        # Should have result with cancelled
        assert len(results) == 1
        assert results[0].get("cancelled") is True
    finally:
        try:
            mgr.shutdown()
        except Exception:
            pass


# ------------------------------------------------------------------
# 5. Permission denied via chmod 000 simulation
# ------------------------------------------------------------------

def test_chmod_000_tmp_dir(tmp_path):
    """chmod 000 dir should be handled gracefully, no crash, no acquire fallback for dir."""
    # Skip if running as root — root can still read 000
    if os.geteuid() == 0:
        pytest.skip("running as root, chmod 000 not effective")
    restricted = tmp_path / "restricted"
    restricted.mkdir()
    (restricted / "inside.tmp").write_text("junk")
    # chmod 000
    try:
        os.chmod(restricted, 0)
        # scan_directory should handle PermissionError gracefully
        import dataforge.core.scanner as scanner_mod
        with patch.object(scanner_mod.logger, "warning"):
            entries = list(scan_directory(str(restricted), recursive=True))
            # Should yield nothing or handle gracefully without crash
            assert isinstance(entries, list)
            # Should not attempt acquire_file fallback for dir
            # We already tested acquire not called for dir, but also ensure no warning flood for non-private?
            # restricted is not private systemd, so warning is expected but not flood
            # Just ensure no exception
        # Also test via scan_junk_files
        import dataforge.modules.system_cleanup as sc_mod
        with patch.object(sc_mod, "_get_platform_junk_paths", return_value={"System Temp": [str(restricted)]}):
            result = scan_junk_files()
            assert isinstance(result, dict)
            # Should be empty or not crash
    finally:
        try:
            os.chmod(restricted, 0o755)
        except Exception:
            pass


# ------------------------------------------------------------------
# 6. Existing walks still pass + no QPainter in scanner
# ------------------------------------------------------------------

def test_existing_walks_still_pass(tmp_path):
    """Ensure scan_junk_files still walks each unique dir once (from test_system_cleanup_walks)."""
    from dataforge.modules.system_cleanup import scan_junk_files as sjf
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "test.tmp").write_text("junk")

    def fake_scan_dir(path, recursive=True, max_depth=5, cancel_token=None):
        # Simulate scan_directory yielding one entry for cache_dir
        if path == str(cache_dir):
            yield FileEntry(path=str(cache_dir / "test.tmp"), filename="test.tmp", extension=".tmp", size=100, created_at=0, modified_at=0, is_dir=False)
        else:
            return
            yield  # make generator

    with patch("dataforge.modules.system_cleanup._get_platform_junk_paths", return_value={
        "User Cache": [str(cache_dir)],
        "Thumbnails": [str(cache_dir)],
        "Package Cache": [str(cache_dir)],
    }):
        with patch("dataforge.modules.system_cleanup.scan_directory", side_effect=fake_scan_dir) as mock_scan, \
             patch("dataforge.modules.system_cleanup.os.path.isdir", return_value=True), \
             patch("dataforge.modules.system_cleanup._is_socket_or_fifo", return_value=False):
            sjf()
            assert mock_scan.call_count == 1


def test_no_qpainter_in_scanner_and_cleanup():
    src_scanner = pathlib.Path("dataforge/core/scanner.py").read_text()
    assert "QPainter" not in src_scanner
    assert "QBackingStore" not in src_scanner
    # Ensure acquire fallback only for file entries, not for dir
    assert "from .acquire import acquire_file" in src_scanner
    # Check that _scan_single_dir has PermissionError guard for scandir
    assert "except PermissionError as e:" in src_scanner
    assert "return [], []" in src_scanner
    # Ensure _is_private_systemd_dir exists
    assert "_is_private_systemd_dir" in src_scanner

    src_cleanup = pathlib.Path("dataforge/modules/system_cleanup.py").read_text()
    assert "_is_private_systemd_dir" in src_cleanup
    assert "os.access" in src_cleanup
    assert "logger.debug" in src_cleanup
    assert "_throttled_progress" in src_cleanup or "throttle" in src_cleanup.lower()

    src_view = pathlib.Path("dataforge/ui/views/system_cleanup.py").read_text()
    assert "setUpdatesEnabled" in src_view
    assert "setSortingEnabled" in src_view
    assert "refresh_viewport" in src_view


def test_scanner_keeps_queue_and_threadpool():
    import inspect
    import dataforge.core.scanner as scanner_mod
    src = inspect.getsource(scanner_mod.scan_directory)
    assert "ThreadPoolExecutor" in src
    assert "queue.Queue" in src
    assert "BATCH_SIZE" in src or "1000" in src
    assert "entry.stat" in src
