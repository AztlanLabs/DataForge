"""TICK-917 — Evidence mode at mutation boundary + app shutdown + callback contract.

Covers the STABILITY_AUDIT_2026-08-23 findings P0.7 (bypassable evidence
mode), P1.1 (swallowed exceptions) and P1.2 (callback contract), plus the
missing ``DataForgeApp.closeEvent``.
"""
from __future__ import annotations

import logging
import time

import pytest
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import QApplication

from dataforge.core import case
from dataforge.core.actions.base import ActionContext
from dataforge.core.actions.io import DeleteStep
from dataforge.core.services import FileActionService
from dataforge.modules.metadata import MetadataEngine

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _reset_evidence():
    case.set_evidence_mode(False)
    case.clear_context()


@pytest.fixture(autouse=True)
def _clean_evidence():
    yield
    _reset_evidence()


@pytest.fixture
def app(qapp):
    """DataForgeApp with auto-scans debounced so jobs only run on demand."""
    from unittest.mock import patch

    from dataforge.ui.app import DataForgeApp

    with patch("dataforge.ui.views.dashboard.DashboardView.refresh_stats", lambda self: None), patch(
        "dataforge.ui.views.hardware_view.get_hardware_report",
        return_value={"system": {"os": "Linux"}},
    ):
        instance = DataForgeApp()
    yield instance
    try:
        instance.job_manager.shutdown()
    except Exception:
        pass
    instance.close()
    instance.deleteLater()


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    from PyQt5.QtWidgets import QApplication

    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
        QApplication.processEvents()
    return predicate()


# ---------------------------------------------------------------------------
# P0.7 — evidence mode enforced at the mutation boundary
# ---------------------------------------------------------------------------


def test_evidence_mode_blocks_metadata_write():
    """GIVEN evidence mode WHEN write_metadata (real write) THEN blocked dict returned."""
    case.set_evidence_mode(True)
    result = MetadataEngine.write_metadata("/nonexistent/evidence.jpg", {"comment": "x"}, dry_run=False)
    assert result == {"success": False, "message": "Blocked by Evidence Mode", "blocked": True}


def test_evidence_mode_blocks_metadata_strip():
    """GIVEN evidence mode WHEN remove_metadata (real write) THEN blocked dict returned."""
    case.set_evidence_mode(True)
    result = MetadataEngine.remove_metadata("/nonexistent/evidence.jpg", fields=None, dry_run=False)
    assert result == {"success": False, "message": "Blocked by Evidence Mode", "blocked": True}


def test_evidence_mode_allows_dry_run_preview():
    """GIVEN evidence mode WHEN dry_run preview THEN proceeds (F3 contract)."""
    case.set_evidence_mode(True)
    result = MetadataEngine.write_metadata("/nonexistent/evidence.jpg", {"comment": "x"}, dry_run=True)
    assert result["dry_run"] is True
    assert "blocked" not in result


def test_evidence_mode_blocks_file_delete():
    """GIVEN evidence mode WHEN delete_items THEN all records failed."""
    case.set_evidence_mode(True)
    outcome = FileActionService.delete_items(["dummy"], dry_run=False)
    assert len(outcome.records) == 1
    assert not outcome.records[0].success
    assert "Evidence Mode" in outcome.records[0].message


def test_evidence_mode_blocks_file_move():
    """GIVEN evidence mode WHEN transfer_items(move) THEN all records failed."""
    case.set_evidence_mode(True)
    outcome = FileActionService.transfer_items(["dummy"], "/tmp/df-evidence", "move", dry_run=False)
    assert len(outcome.records) == 1
    assert not outcome.records[0].success
    assert "Evidence Mode" in outcome.records[0].message


def test_evidence_mode_blocks_rename():
    """GIVEN evidence mode WHEN rename_items THEN all records failed."""
    case.set_evidence_mode(True)
    outcome = FileActionService.rename_items(["dummy"], lambda p, i: "new", dry_run=False)
    assert len(outcome.records) == 1
    assert not outcome.records[0].success
    assert "Evidence Mode" in outcome.records[0].message


def test_evidence_mode_blocks_archive():
    """GIVEN evidence mode WHEN archive_items THEN all records failed."""
    case.set_evidence_mode(True)
    outcome = FileActionService.archive_items(["dummy"], dry_run=False)
    assert len(outcome.records) == 1
    assert not outcome.records[0].success
    assert "Evidence Mode" in outcome.records[0].message


def test_evidence_mode_blocks_pipeline_delete_step():
    """GIVEN evidence mode WHEN pipeline runs DeleteStep THEN delete blocked, pipeline reports failure."""
    case.set_evidence_mode(True)
    ctx = ActionContext(files=["dummy"])
    ctx.is_dry_run = False
    DeleteStep().execute(ctx)
    assert ctx.files == []
    assert any("Evidence Mode" in message for (_path, _action, message) in ctx.results)


def test_evidence_mode_allows_read_operations(tmp_path):
    """GIVEN evidence mode WHEN read ops run THEN they succeed."""
    f = tmp_path / "readme.txt"
    f.write_text("evidence-safe read\n")
    case.set_evidence_mode(True)
    meta = MetadataEngine.read_metadata(str(f))
    assert isinstance(meta, dict)
    assert "blocked" not in meta
    assert case.is_evidence_mode()


def test_evidence_mode_initializes_context_gracefully():
    """GIVEN no CaseContext WHEN toggled THEN context is created and usable."""
    case.clear_context()
    case.set_evidence_mode(True)
    assert case.is_evidence_mode()
    result = MetadataEngine.write_metadata("/nonexistent/evidence.jpg", {"comment": "x"}, dry_run=False)
    assert result["blocked"] is True
    case.set_evidence_mode(False)
    assert not case.is_evidence_mode()


# ---------------------------------------------------------------------------
# No closeEvent / worker shutdown
# ---------------------------------------------------------------------------


def test_close_event_waits_for_workers(app):
    """GIVEN a running job WHEN closeEvent THEN workers drain before returning."""
    def _slow(cancel_token=None, progress_callback=None):
        start = time.time()
        while time.time() - start < 30:
            if cancel_token is not None and cancel_token.is_set():
                return {"cancelled": True}
            time.sleep(0.02)
        return {"done": True}

    app.run_background(_slow, None, task_name="close-wait")
    assert _wait_until(lambda: app.job_manager.is_busy, timeout=5.0)
    started = time.time()
    app.closeEvent(QCloseEvent())
    elapsed = time.time() - started
    assert elapsed < 10.0, f"closeEvent took too long: {elapsed:.1f}s"
    assert not app.job_manager.is_busy


def test_close_event_cancels_pending_jobs(app):
    """GIVEN queued jobs WHEN closeEvent THEN all reach terminal state."""
    def _task(n, cancel_token=None, progress_callback=None):
        start = time.time()
        while time.time() - start < 30:
            if cancel_token is not None and cancel_token.is_set():
                return {"cancelled": True, "n": n}
            time.sleep(0.02)
        return {"n": n}

    for i in range(3):
        app.run_background(_task, None, i, task_name=f"close-{i}")
    app.closeEvent(QCloseEvent())
    assert not app.job_manager.is_busy


def test_close_event_is_idempotent(app):
    """GIVEN closeEvent twice THEN second call is a safe no-op."""
    app.closeEvent(QCloseEvent())
    app.closeEvent(QCloseEvent())


# ---------------------------------------------------------------------------
# P1.2 — restore_tree_selection callback contract
# ---------------------------------------------------------------------------


def test_restore_tree_selection_no_arg_callback():
    """GIVEN a no-arg callback WHEN restore_tree_selection THEN no TypeError."""
    from unittest.mock import MagicMock

    from dataforge.ui.views.base import BaseView

    tree = MagicMock()
    tree.restore_selection = MagicMock()
    # Invoke unbound: the method touches only tree/item_ids/on_select.
    BaseView.restore_tree_selection(None, tree, ["id1"], on_select=lambda: None)
    tree.restore_selection.assert_called_once_with(["id1"])


def test_restore_tree_selection_arg_callback_still_gets_none():
    """GIVEN an arg-taking callback WHEN restore_tree_selection THEN on_select(None)."""
    from unittest.mock import MagicMock

    from dataforge.ui.views.base import BaseView

    captured = []
    tree = MagicMock()
    BaseView.restore_tree_selection(None, tree, [], on_select=lambda arg: captured.append(arg))
    assert captured == [None]


# ---------------------------------------------------------------------------
# P1.1 — callback exceptions logged, not swallowed
# ---------------------------------------------------------------------------


def test_callback_exception_logged_not_swallowed(app, caplog):
    """GIVEN a callback that raises WHEN job completes THEN logged and surfaced."""
    def _fast():
        return {"ok": True}

    def _boom(_result):
        raise RuntimeError("callback boom")

    with caplog.at_level(logging.ERROR):
        app.run_background(_fast, _boom, task_name="callback-boom")
        assert _wait_until(
            lambda: app.status_label.text().startswith("Callback error"), timeout=5.0
        )
    assert any("Completion callback failed" in r.message for r in caplog.records)
    assert "callback boom" in app.status_label.text()