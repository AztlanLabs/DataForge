"""TICK-808 — Hardware section crash SIGSEGV tests."""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtWidgets import QApplication

from dataforge.modules.hardware import get_hardware_report
from dataforge.ui.job_manager import JobManager


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def manager(qapp):
    mgr = JobManager(max_workers=4)
    yield mgr
    mgr.shutdown()


# ------------------------------------------------------------------
# Helper to get DataForgeApp without triggering heavy scans
# ------------------------------------------------------------------

def _make_app(qapp):
    # Use offscreen — patch heavy hardware report to avoid subprocess at startup
    from dataforge.ui.app import DataForgeApp
    from unittest.mock import patch

    # Prevent any hardware scan at startup by patching get_hardware_report to no-op
    with patch("dataforge.ui.views.hardware_view.get_hardware_report", return_value={"system": {"os": "Linux"}}):
        app = DataForgeApp()
    # Ensure hardware view debounced so subsequent switches don't auto-scan
    try:
        hv = app.views.get("Hardware Info")
        if hv:
            hv._has_scanned = True
            hv._is_scanning = False
    except Exception:
        pass
    return app


# ------------------------------------------------------------------
# 1. Rapid Hardware opening 10 times — no SIGSEGV / QPainter
# ------------------------------------------------------------------

def test_hardware_rapid_switch_no_crash(qapp):
    # TICK-808: verify HardwareView mount debounce without needing full app
    from dataforge.ui.views.hardware_view import HardwareView

    mock_app = MagicMock()
    mock_app.job_manager = MagicMock()
    mock_app.update_status = MagicMock()
    mock_app.show_workflow_error = MagicMock()

    # Track run_workflow calls
    run_calls = []

    def fake_run_workflow(target, on_success, *args, **kwargs):
        run_calls.append(1)
        # Simulate async success after short delay via JobManager-like behavior
        # Don't actually run hardware report to avoid subprocess

    mock_app.run_workflow = fake_run_workflow

    # Create view via __new__ to avoid __init__ heavy UI
    view = HardwareView.__new__(HardwareView)
    view.app = mock_app
    view.current_report = None
    view._has_scanned = False
    view._is_scanning = False
    view.lbl_status = MagicMock()
    # Mock mount's dependencies
    view._has_scanned = False
    view._is_scanning = False

    # Patch __init__-like minimal needed for mount
    # Directly test mount debounce: calling mount 10 times rapidly should only trigger one _run_scan
    call_count = []

    def counting_run_scan(self, *a, **k):
        call_count.append(1)
        # Simulate _is_scanning guard
        if self._is_scanning:
            return
        self._is_scanning = True
        # Don't actually run workflow for this unit test, just mark
        self._is_scanning = False
        self._has_scanned = True

    with patch.object(HardwareView, "_run_scan", counting_run_scan):
        for _ in range(10):
            view.mount()
            QApplication.processEvents()
            time.sleep(0.01)

    assert len(call_count) <= 2, f"mount debounce failed: {len(call_count)} scans started"

    # Also verify app.switch_view debounce: create minimal app mock
    # Test that rapid switch_view to same title is debounced
    app = _make_app(qapp)
    # Reset hardware flags to allow switch test without triggering real scan
    hv = app.views["Hardware Info"]
    hv._has_scanned = True  # already scanned, so mount won't trigger
    hv._is_scanning = False
    # Patch switch to count mounts
    mount_calls = []
    orig_mount = hv.mount

    def counting_mount(*a, **k):
        mount_calls.append(1)
        return orig_mount(*a, **k)

    hv.mount = counting_mount
    for _ in range(10):
        app.switch_view("Hardware Info")
        QApplication.processEvents()
        time.sleep(0.01)
        app.switch_view("Dashboard")
        QApplication.processEvents()
        time.sleep(0.01)
    # Should not have crashed and mount not called excessively due to debounce
    # Allow at most 2-3 calls
    assert len(mount_calls) <= 5
    try:
        app.job_manager.cancel_all()
        app.job_manager.shutdown()
    except Exception:
        pass
    app.close()
    QApplication.processEvents()


def test_hardware_mount_debounce_only_once(qapp):
    """mount() should not trigger _run_scan if _has_scanned true."""
    from dataforge.ui.views.hardware_view import HardwareView

    mock_app = MagicMock()
    # Create view without triggering __init__ scan
    view = HardwareView.__new__(HardwareView)
    # Manually set flags
    view._has_scanned = True
    view._is_scanning = False
    view.current_report = {"system": {}}
    view.app = mock_app

    with patch.object(view, "_run_scan") as mock_scan:
        view.mount()
        mock_scan.assert_not_called()

    # If not scanned, should call
    view._has_scanned = False
    view._is_scanning = False
    view.current_report = None
    with patch.object(view, "_run_scan") as mock_scan:
        view.mount()
        mock_scan.assert_called_once()

    # If scanning, should not call again
    view._is_scanning = True
    view._has_scanned = False
    with patch.object(view, "_run_scan") as mock_scan:
        view.mount()
        mock_scan.assert_not_called()


# ------------------------------------------------------------------
# 2. Startup jobs cancel respects token, is_busy false within 1s
# ------------------------------------------------------------------

def test_startup_jobs_cancel_within_1s(manager, qapp):
    # Simulate 4 startup jobs: Dashboard scan, Storage, Performance, Hardware
    def dummy_scan(cancel_token=None, progress_callback=None):
        for i in range(20):
            if cancel_token and cancel_token.is_set():
                return {"cancelled": True}
            if progress_callback:
                progress_callback(i, 20, "scanning")
            time.sleep(0.05)
        return {"done": True}

    ids = []
    for name in ["Dashboard", "Storage", "Performance", "Hardware"]:
        jid = manager.submit(target=dummy_scan, task_name=name)
        assert jid is not None
        ids.append(jid)

    time.sleep(0.15)
    assert manager.is_busy

    # Cancel all like STOP button
    count = manager.cancel_all()
    assert count >= 1

    start = time.monotonic()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and manager.is_busy:
        time.sleep(0.02)
        QApplication.processEvents()

    elapsed = time.monotonic() - start
    assert not manager.is_busy, "is_busy should be False within 1-2s after cancel_all"
    assert elapsed < 1.2

    # Each job should be cancelled
    for jid in ids:
        job = manager.get_job(jid)
        assert job is not None
        assert job.is_cancelled() or job.status.name == "CANCELLED"
        # Results should be cancelled dict if completed
        if job.results:
            assert job.results.get("cancelled") is True


# ------------------------------------------------------------------
# 3. Hardware scan with cancel returns cancelled dict
# ------------------------------------------------------------------

def test_hardware_scan_cancel_returns_cancelled(qapp):
    cancel = threading.Event()

    # Make report call that will be cancelled mid-scan
    # Use side_effect to trigger cancel after first step
    def fake_get_report(*args, **kwargs):
        # Simulate long per-step work
        for i in range(5):
            if cancel.is_set():
                raise InterruptedError("Hardware scan cancelled")
            time.sleep(0.05)
        return {"system": {"os": "Linux"}}

    # Direct get_hardware_report with cancel_token pre-set should raise quickly
    cancel.set()
    start = time.monotonic()
    with pytest.raises(InterruptedError):
        get_hardware_report(cancel_token=cancel)
    elapsed = time.monotonic() - start
    assert elapsed < 0.5

    # Now test via JobManager that it normalizes to cancelled dict
    manager = JobManager(max_workers=2)
    try:

        def slow_hardware(cancel_token=None, progress_callback=None):
            # Mirrors real get_hardware_report steps
            for i in range(10):
                if cancel_token and cancel_token.is_set():
                    raise InterruptedError("Hardware scan cancelled")
                if progress_callback:
                    progress_callback(i, 10, f"step {i}")
                time.sleep(0.05)
            return {"system": {"os": "Linux"}}

        results = []
        errors = []

        jid = manager.submit(target=slow_hardware, on_success=lambda r: results.append(r), on_error=lambda e: errors.append(e), progress=True)
        assert jid is not None
        time.sleep(0.1)
        # Cancel
        manager.cancel(jid)
        deadline = time.time() + 3
        while time.time() < deadline and not results and not errors:
            time.sleep(0.05)
            QApplication.processEvents()
        # Should be results with cancelled, not errors
        assert len(results) == 1
        assert results[0].get("cancelled") is True
        assert len(errors) == 0
        # is_busy false quickly
        time.sleep(0.1)
        assert not manager.is_busy
    finally:
        manager.shutdown()


def test_hardware_view_run_scan_respects_cancel(qapp):
    app = _make_app(qapp)
    hv = app.views["Hardware Info"]
    hv._has_scanned = False
    hv._is_scanning = False
    hv.current_report = None

    # Patch get_hardware_report to be slow and cancellable
    def slow_report(cancel_token=None, progress_callback=None):
        for i in range(20):
            if cancel_token and cancel_token.is_set():
                raise InterruptedError("Hardware scan cancelled")
            if progress_callback:
                progress_callback(i, 20, f"step {i}")
            time.sleep(0.05)
        return {"system": {"os": "Linux"}, "cpu": {}}

    with patch("dataforge.ui.views.hardware_view.get_hardware_report", new=slow_report):
        hv._run_scan()
        # Should be scanning
        assert hv._is_scanning is True
        time.sleep(0.15)
        # Cancel via app like STOP button
        app.job_manager.cancel_all()
        # Wait for wrapped handlers
        deadline = time.time() + 3
        while time.time() < deadline and hv._is_scanning:
            time.sleep(0.05)
            QApplication.processEvents()
        # Should have reset _is_scanning and not marked _has_scanned
        assert hv._is_scanning is False
        assert hv._has_scanned is False
        assert hv.lbl_status.text() == "Hardware scan cancelled."

    app.close()
    QApplication.processEvents()
    try:
        app.job_manager.shutdown()
    except Exception:
        pass


# ------------------------------------------------------------------
# 4. Existing hardware tests still pass (no regression)
# ------------------------------------------------------------------

def test_existing_hardware_report_still_passes():
    report = get_hardware_report()
    assert isinstance(report, dict)
    assert "system" in report
    assert "cpu" in report
    assert "ram" in report
    assert "storage" in report
    # Should not raise and should contain expected keys
    assert report["system"].get("os") is not None


def test_hardware_per_step_cancel():
    """Each _get_* should check cancel_token and raise quickly."""
    cancel = threading.Event()
    cancel.set()
    from dataforge.modules.hardware import (
        _get_system_overview,
        _get_cpu_details,
        _get_ram_details,
        _get_storage_details,
        _get_gpu_details,
        _get_network_details,
        _get_motherboard_details,
    )

    for fn in [
        _get_system_overview,
        _get_cpu_details,
        _get_ram_details,
        _get_storage_details,
        _get_gpu_details,
        _get_network_details,
        _get_motherboard_details,
    ]:
        with pytest.raises(InterruptedError):
            fn(cancel_token=cancel)


def test_app_jobmanager_not_gc(qapp):
    """Ensure JobManager held by app not GC mid-flight."""
    app = _make_app(qapp)
    # Keep weak ref to job_manager and ensure it stays alive after rapid switches
    import gc

    jm = app.job_manager
    # Submit a job
    def dummy(cancel_token=None, progress_callback=None):
        time.sleep(0.2)
        return {"ok": True}

    jid = jm.submit(target=dummy)
    assert jid is not None
    # Rapid switches shouldn't GC job_manager
    for _ in range(5):
        app.switch_view("Hardware Info")
        QApplication.processEvents()
        app.switch_view("Dashboard")
        QApplication.processEvents()

    # Force GC
    gc.collect()
    # job_manager still same object and alive
    assert app.job_manager is jm
    assert jm is not None
    # Cleanup
    time.sleep(0.3)
    QApplication.processEvents()
    app.close()
    jm.shutdown()


def test_qpainter_no_repaint_during_build(qapp):
    """_build_overview should not call repaint/update during paint — use viewport deferred."""
    from dataforge.ui.views.hardware_view import HardwareView

    # Use mocked view to avoid real GUI paint recursion
    view = HardwareView.__new__(HardwareView)
    view.overview_layout = MagicMock()
    view.overview_layout.count.return_value = 1
    view.overview_layout.parentWidget.return_value = MagicMock()
    view.overview_placeholder = MagicMock()
    view.detail_tree = MagicMock()
    view.detail_tree.viewport.return_value = MagicMock()
    view.rec_text = MagicMock()
    view.lbl_status = MagicMock()
    view.btn_scan = MagicMock()
    view.btn_export_json = MagicMock()
    view.btn_export_html = MagicMock()
    view.tabs = MagicMock()
    view.app = MagicMock()
    view.current_report = None
    view._has_scanned = False
    view._is_scanning = False
    # Mock setUpdatesEnabled to avoid real paint
    view.setUpdatesEnabled = MagicMock()

    report = {
        "system": {"os": "Linux", "os_release": "x", "distro": "y", "hostname": "h", "machine": "m"},
        "cpu": {"model": "x", "physical_cores": 4, "logical_cores": 8},
        "ram": {"formatted_total": "8G", "percent_used": 10},
        "storage": {"devices": []},
        "gpu": [],
        "motherboard": {},
    }
    # Should not raise and should use deferred viewport update, not direct repaint
    with patch("PyQt5.QtCore.QTimer.singleShot") as mock_timer:
        view._build_overview(report)
        # Should have disabled updates, built, re-enabled, and scheduled deferred update
        assert view.setUpdatesEnabled.call_count >= 2
        assert mock_timer.called
    # Also test detail tree
    view.detail_tree.setUpdatesEnabled = MagicMock()
    with patch("PyQt5.QtCore.QTimer.singleShot") as mock_timer:
        view._build_detail_tree(report)
        assert view.detail_tree.setUpdatesEnabled.call_count >= 2
        assert mock_timer.called
