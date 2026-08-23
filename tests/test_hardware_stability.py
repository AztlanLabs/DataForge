"""TICK-901 — Hardware section QPainter/SIGSEGV deep hardening stability."""
from __future__ import annotations

import threading
import time
import pathlib
import io
import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtWidgets import QApplication

from dataforge.modules.hardware import get_hardware_report, _check_cancel, _safe_psutil_call
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
    try:
        mgr.shutdown()
    except Exception:
        pass


def _make_app(qapp, patch_hardware=True):
    from dataforge.ui.app import DataForgeApp

    if patch_hardware:
        with patch("dataforge.ui.views.hardware_view.get_hardware_report", return_value={"system": {"os": "Linux"}}):
            app = DataForgeApp()
    else:
        app = DataForgeApp()
    # debounce already scanned for tests that don't want auto-scan
    try:
        hv = app.views.get("Hardware Info")
        if hv:
            hv._has_scanned = True
            hv._is_scanning = False
            hv.__dict__.pop("_mount_scheduled", None)
    except Exception:
        pass
    return app


# ------------------------------------------------------------------
# 1. Rapid 20x switch — only one hardware job, no SIGSEGV
# ------------------------------------------------------------------

def test_hardware_rapid_20_no_sigsegv(qapp):
    from dataforge.ui.views.hardware_view import HardwareView

    mock_app = MagicMock()
    mock_app.job_manager = MagicMock()
    mock_app.update_status = MagicMock()

    run_calls = []

    def fake_run_workflow(target, on_success, *args, **kwargs):
        run_calls.append(1)

    mock_app.run_workflow = fake_run_workflow

    view = HardwareView.__new__(HardwareView)
    view.app = mock_app
    view.current_report = None
    view._has_scanned = False
    view._is_scanning = False
    view.__dict__.pop("_mount_scheduled", None)
    view.lbl_status = MagicMock()

    call_count = []

    def counting_run_scan(self, *a, **k):
        call_count.append(1)
        if self.__dict__.get("_is_scanning") or self.__dict__.get("_has_scanned"):
            return
        self._is_scanning = True
        self._is_scanning = False
        self._has_scanned = True

    with patch.object(HardwareView, "_run_scan", counting_run_scan):
        for _ in range(20):
            view.mount()
            QApplication.processEvents()
            time.sleep(0.005)

    assert len(call_count) <= 2, f"20x mount should coalesce, got {len(call_count)}"

    # Full app switch_view 20x
    app = _make_app(qapp)
    hv = app.views["Hardware Info"]
    hv._has_scanned = True
    hv._is_scanning = False
    hv.__dict__.pop("_mount_scheduled", None)
    # patch mount to count
    mount_calls = []
    orig_mount = hv.mount

    def counting_mount(*a, **k):
        mount_calls.append(1)
        return orig_mount(*a, **k)

    hv.mount = counting_mount
    for _ in range(20):
        app.switch_view("Hardware Info")
        QApplication.processEvents()
        time.sleep(0.005)
        app.switch_view("Dashboard")
        QApplication.processEvents()
        time.sleep(0.005)

    assert len(mount_calls) <= 5, f"20x switch should be debounced, got {len(mount_calls)}"
    # At least not 20 jobs
    assert len(app.job_manager.list_jobs()) < 10

    try:
        app.job_manager.cancel_all()
        app.job_manager.shutdown()
    except Exception:
        pass
    app.close()
    QApplication.processEvents()


# ------------------------------------------------------------------
# 2. Viewport AttributeError fixed — uses refresh_viewport
# ------------------------------------------------------------------

def test_viewport_no_attribute_error(qapp):
    from dataforge.ui.views.hardware_view import HardwareView

    view = HardwareView.__new__(HardwareView)
    view.overview_layout = MagicMock()
    view.overview_layout.count.return_value = 1
    view.overview_layout.parentWidget.return_value = MagicMock()
    view.overview_placeholder = MagicMock()
    view.detail_tree = MagicMock()
    view.detail_tree.refresh_viewport = MagicMock()
    view.detail_tree.tree = MagicMock()
    view.detail_tree.tree.viewport.return_value = MagicMock()
    view.detail_tree.setUpdatesEnabled = MagicMock()
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
    view.__dict__.pop("_mount_scheduled", None)
    view.setUpdatesEnabled = MagicMock()

    report = {
        "system": {"os": "Linux", "os_release": "x", "distro": "y", "hostname": "h", "machine": "m"},
        "cpu": {"model": "x", "physical_cores": 4, "logical_cores": 8},
        "ram": {"formatted_total": "8G", "percent_used": 10},
        "storage": {"devices": []},
        "gpu": [],
        "motherboard": {},
    }

    # Should not raise AttributeError
    view._build_overview(report)
    assert view.setUpdatesEnabled.call_count >= 2
    assert view.detail_tree.refresh_viewport.called

    # Verify source does not contain buggy patterns
    src = pathlib.Path("dataforge/ui/views/hardware_view.py").read_text()
    assert "self.detail_tree.viewport()" not in src
    assert "overview_layout.parentWidget().update()" not in src

    # Also check detail tree
    view.detail_tree.refresh_viewport.reset_mock()
    view.detail_tree.setUpdatesEnabled.reset_mock()
    view._build_detail_tree(report)
    assert view.detail_tree.setUpdatesEnabled.call_count >= 2
    assert view.detail_tree.refresh_viewport.called

    # EnhancedTreeview wrapper has viewport on tree, not on wrapper
    from dataforge.ui.widgets import EnhancedTreeview
    assert hasattr(EnhancedTreeview, "refresh_viewport")
    # Check source of widgets.py to ensure wrapper uses self.tree.viewport()
    import pathlib as _pl

    w_src = _pl.Path("dataforge/ui/widgets.py").read_text()
    assert "self.tree.viewport().update()" in w_src


# ------------------------------------------------------------------
# 3. get_hardware_report cancel returns cancelled dict via JobManager
# ------------------------------------------------------------------

def test_get_hardware_report_cancel_via_jobmanager(manager, qapp):
    cancel = threading.Event()
    cancel.set()
    # Direct call should raise InterruptedError quickly
    start = time.monotonic()
    with pytest.raises(InterruptedError):
        get_hardware_report(cancel_token=cancel)
    assert time.monotonic() - start < 0.5

    # Via JobManager should normalize to cancelled dict within 500ms
    def slow_hardware(cancel_token=None, progress_callback=None):
        for i in range(10):
            _check_cancel(cancel_token)
            if progress_callback:
                progress_callback(i, 10, f"step {i}")
            time.sleep(0.05)
        return {"system": {"os": "Linux"}}

    results = []
    errors = []

    jid = manager.submit(target=slow_hardware, on_success=lambda r: results.append(r), on_error=lambda e: errors.append(e), progress=True)
    assert jid is not None
    time.sleep(0.1)
    manager.cancel(jid)
    deadline = time.time() + 3
    while time.time() < deadline and not results and not errors:
        time.sleep(0.05)
        QApplication.processEvents()

    assert len(results) == 1
    assert results[0].get("cancelled") is True
    assert len(errors) == 0
    time.sleep(0.1)
    assert not manager.is_busy
    job = manager.get_job(jid)
    assert job is not None
    assert job.status.name == "CANCELLED"


def test_hardware_per_step_cancel():
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

    # _check_cancel helper
    with pytest.raises(InterruptedError):
        _check_cancel(cancel)

    # _safe_psutil_call timeout fallback
    def slow_fn():
        time.sleep(0.5)
        return 123

    # timeout 0.1 should return default None
    res = _safe_psutil_call(slow_fn, default="fallback", timeout=0.1)
    assert res == "fallback"


# ------------------------------------------------------------------
# 4. Crossfade (ViewAnim 160ms) + 4 concurrent jobs — no QPainter warning
# ------------------------------------------------------------------

def test_crossfade_no_qpainter_warning(qapp):
    app = _make_app(qapp)
    # Capture stderr
    captured = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured
    try:
        hv = app.views["Hardware Info"]
        hv._has_scanned = False
        hv._is_scanning = False
        hv.__dict__.pop("_mount_scheduled", None)
        hv.current_report = None

        report = {
            "system": {"os": "Linux", "os_release": "x", "distro": "y", "hostname": "h", "machine": "m"},
            "cpu": {"model": "x", "physical_cores": 4, "logical_cores": 8},
            "ram": {"formatted_total": "8G", "percent_used": 10},
            "storage": {"devices": []},
            "gpu": [],
            "motherboard": {},
        }

        # Simulate 4 concurrent jobs
        def dummy(cancel_token=None, progress_callback=None):
            for i in range(5):
                if cancel_token and cancel_token.is_set():
                    return {"cancelled": True}
                if progress_callback:
                    progress_callback(i, 5, "dummy")
                time.sleep(0.02)
            return {"ok": True}

        ids = []
        for _ in range(4):
            jid = app.job_manager.submit(target=dummy, task_name="dummy")
            ids.append(jid)

        # Trigger crossfade animation
        app.switch_view("Hardware Info")
        QApplication.processEvents()
        # While animation active (160ms), build overview/detail
        time.sleep(0.02)
        hv._build_overview(report)
        hv._build_detail_tree(report)
        QApplication.processEvents()
        time.sleep(0.05)
        QApplication.processEvents()

        # Check stderr for QPainter warnings
        output = captured.getvalue()
        assert "QPainter::begin" not in output
        assert "QBackingStore::endPaint" not in output
        assert "active painter" not in output.lower()

        app.job_manager.cancel_all()
        time.sleep(0.1)
        QApplication.processEvents()
    finally:
        sys.stderr = old_stderr
        try:
            app.job_manager.shutdown()
        except Exception:
            pass
        app.close()
        QApplication.processEvents()


# ------------------------------------------------------------------
# 5. No QPainter in hardware.py, existing tests still pass
# ------------------------------------------------------------------

def test_no_qpainter_in_hardware_module():
    src = pathlib.Path("dataforge/modules/hardware.py").read_text()
    assert "QPainter" not in src
    assert "QPixmap" not in src
    assert "QImage" not in src
    # Should have _check_cancel and _safe_psutil_call
    assert "_check_cancel" in src
    assert "_safe_psutil_call" in src
    assert "ThreadPoolExecutor" in src
    # _run_cmd timeout should be 5
    assert "def _run_cmd(cmd, timeout=5" in src


def test_existing_hardware_report_still_passes():
    report = get_hardware_report()
    assert isinstance(report, dict)
    assert "system" in report
    assert "cpu" in report
    assert "ram" in report
    assert "storage" in report
    assert report["system"].get("os") is not None
