"""TICK-908 — Global cursor pointers + app QPainter hardening.

Acceptance:
- GIVEN app running WHEN hovering over any QPushButton (primary/warning/success)
  THEN cursor is PointingHandCursor (widget.cursor().shape() == Qt.PointingHandCursor)
- GIVEN tree view row WHEN hovering THEN cursor is PointingHandCursor, not ArrowCursor
- GIVEN JobManager.is_busy true (scan running) WHEN busy THEN app override cursor is
  WaitCursor and cleared on _on_job_completed
- GIVEN CollapsibleCard header toggle WHEN hovered THEN cursor is PointingHandCursor
- GIVEN switch_view rapid 10x WHEN animating THEN no QBackingStore::endPaint active
  painter warning on stderr (capture)
- GIVEN view with evidence_mode enabled WHEN destructive button disabled THEN cursor
  is ForbiddenCursor
"""

from __future__ import annotations

import io
import threading
import time
from contextlib import redirect_stderr
from unittest.mock import patch

import pytest

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QPushButton, QTreeWidget, QSplitter, QLineEdit, QTextEdit, QSpinBox,
)

from dataforge.ui.theme_tokens import CURSORS
from dataforge.ui.views.base import BaseView


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _TestView(BaseView):
    """Minimal BaseView subclass with a couple of interactive children."""

    def get_title(self) -> str:
        return "Cursor Test View"


@pytest.fixture
def view(qapp):
    """A BaseView with one button of every semantic variant."""
    v = _TestView()
    v.buttons = {}
    for variant in ("primary", "warning", "danger", "info"):
        btn = QPushButton(variant, v)
        btn.setProperty("variant", variant)
        v.buttons[variant] = btn
    v.disabled_btn = QPushButton("disabled", v)
    v.disabled_btn.setEnabled(False)
    v.tree = QTreeWidget(v)
    v.splitter_v = QSplitter(Qt.Vertical, v)
    v.splitter_h = QSplitter(Qt.Horizontal, v)
    v.line_edit = QLineEdit(v)
    v.text_edit = QTextEdit(v)
    v.spin = QSpinBox(v)
    QApplication.processEvents()
    return v


@pytest.fixture
def app(qapp):
    """DataForgeApp with auto-scans debounced so jobs only run on demand."""
    from dataforge.ui.app import DataForgeApp

    with patch("dataforge.ui.views.dashboard.DashboardView.refresh_stats", lambda self: None), patch(
        "dataforge.ui.views.hardware_view.get_hardware_report",
        return_value={"system": {"os": "Linux"}},
    ):
        instance = DataForgeApp()
    hv = instance.views.get("Hardware Info")
    if hv is not None:
        hv._has_scanned = True
        hv._is_scanning = False
        hv._mount_scheduled = False
    yield instance
    try:
        instance.job_manager.shutdown()
    except Exception:
        pass
    instance.close()
    instance.deleteLater()


# ------------------------------------------------------------------
# 1. QPushButton variants → PointingHandCursor
# ------------------------------------------------------------------

def test_button_variants_pointing_hand(view):
    """GIVEN primary/warning/danger/info buttons WHEN hovered THEN PointingHandCursor."""
    for variant, btn in view.buttons.items():
        assert btn.cursor().shape() == Qt.PointingHandCursor, variant


def test_disabled_button_forbidden_cursor(view):
    """GIVEN disabled button WHEN hovered THEN ForbiddenCursor."""
    assert view.disabled_btn.cursor().shape() == Qt.ForbiddenCursor


def test_text_inputs_ibeam_cursor(view):
    """GIVEN text-editing widgets THEN IBeamCursor."""
    for w in (view.line_edit, view.text_edit, view.spin):
        assert w.cursor().shape() == Qt.IBeamCursor


def test_tree_viewport_pointing_hand(view):
    """GIVEN tree view rows WHEN hovering THEN PointingHandCursor on viewport."""
    assert view.tree.viewport().cursor().shape() == Qt.PointingHandCursor


def test_splitter_cursors(view):
    """GIVEN splitters THEN SplitVCursor / SplitHCursor by orientation."""
    assert view.splitter_v.cursor().shape() == Qt.SplitVCursor
    assert view.splitter_h.cursor().shape() == Qt.SplitHCursor


def test_collapsible_card_toggle_pointing_hand(qapp):
    """GIVEN CollapsibleCard header toggle WHEN hovered THEN PointingHandCursor."""
    from dataforge.ui.widgets import CollapsibleCard

    v = _TestView()
    card = CollapsibleCard(master=v, title="Card", expanded=True)
    QApplication.processEvents()
    assert card.btn_toggle.cursor().shape() == Qt.PointingHandCursor


def test_nav_buttons_pointing_hand(app):
    """GIVEN sidebar nav buttons and group headers THEN PointingHandCursor."""
    QApplication.processEvents()
    assert app.nav_buttons, "nav_buttons should be built"
    for btn, _title in app.nav_buttons:
        assert btn.cursor().shape() == Qt.PointingHandCursor, btn.text()
    for group_name, header_btn in app.group_headers.items():
        assert header_btn.cursor().shape() == Qt.PointingHandCursor, group_name


def test_evidence_mode_destructive_button_forbidden(app):
    """GIVEN evidence_mode enabled WHEN destructive button disabled THEN ForbiddenCursor.

    The destructive button is disabled while evidence mode blocks writes; the
    disabled state maps to ForbiddenCursor via _apply_cursors. The disabled
    button is a child of the current view, so switch_view's cursor re-scan
    applies it."""
    v = app.views.get("Dashboard")
    btn = QPushButton("Delete", v)
    btn.setProperty("variant", "danger")
    app.evidence_mode = True
    btn.setEnabled(False)
    app.switch_view("Dashboard")  # re-mount -> re-scan cursors
    QApplication.processEvents()
    assert btn.cursor().shape() == Qt.ForbiddenCursor


# ------------------------------------------------------------------
# 2. Busy WaitCursor override
# ------------------------------------------------------------------

def test_busy_wait_cursor_set_and_cleared(app):
    """GIVEN a running job WHEN busy THEN WaitCursor override; cleared on completion."""
    gate = threading.Event()

    def _gated_task(cancel_token=None):
        gate.wait(timeout=10)
        return {"done": True}

    app.run_background(_gated_task, lambda r: None, show_progress=True)
    deadline = time.time() + 10
    while not app.job_manager.is_busy and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.02)
    assert app.job_manager.is_busy
    assert app._busy_cursor_active
    override = QApplication.overrideCursor()
    assert override is not None
    assert override.shape() == Qt.WaitCursor

    gate.set()
    deadline = time.time() + 10
    while app.job_manager.is_busy and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.02)
    QApplication.processEvents()
    assert not app.job_manager.is_busy
    assert not app._busy_cursor_active
    assert QApplication.overrideCursor() is None


# ------------------------------------------------------------------
# 3. switch_view rapid 10x — no QBackingStore::endPaint warning
# ------------------------------------------------------------------

def test_switch_view_rapid_no_paint_warning(app):
    """GIVEN switch_view rapid 10x WHEN animating THEN no endPaint active painter warning."""
    titles = [
        "Dashboard", "Search", "Duplicate Finder", "Automations", "Media Tools",
        "Clean Up Space", "Performance", "File Recovery", "Metadata & EXIF",
        "Hardware Info", "Forensics", "Storage & Devices", "Settings",
    ]
    buffer = io.StringIO()
    with redirect_stderr(buffer):
        for i in range(10):
            title = titles[i % len(titles)]
            app.switch_view(title)
            QApplication.processEvents()
            time.sleep(0.03)
        # Let the last crossfade finish
        deadline = time.time() + 5
        while app._in_switch and time.time() < deadline:
            QApplication.processEvents()
            time.sleep(0.02)
        QApplication.processEvents()
    stderr = buffer.getvalue()
    assert "endPaint" not in stderr, f"QBackingStore::endPaint warning captured:\n{stderr}"


# ------------------------------------------------------------------
# 4. Theme apply does not freeze updates (paint-deadlock guard)
# ------------------------------------------------------------------

def test_apply_theme_does_not_freeze_updates(app):
    """GIVEN apply_theme WHEN run THEN no widget is left with updates frozen
    and the WaitCursor override is restored (TICK-908 paint-hardening)."""
    for w in QApplication.instance().topLevelWidgets():
        w.setUpdatesEnabled(True)
    QApplication.restoreOverrideCursor()
    app.apply_theme(is_dark=True)
    QApplication.processEvents()
    for w in QApplication.instance().topLevelWidgets():
        assert w.updatesEnabled(), f"{w} left with updates frozen"
    assert QApplication.overrideCursor() is None


# ------------------------------------------------------------------
# 5. CURSORS token table sanity
# ------------------------------------------------------------------

def test_cursors_token_table():
    """GIVEN the CURSORS table THEN every semantic key maps to a CursorShape."""
    expected = {
        "button": Qt.PointingHandCursor,
        "tree": Qt.PointingHandCursor,
        "splitter_h": Qt.SplitHCursor,
        "splitter_v": Qt.SplitVCursor,
        "header": Qt.PointingHandCursor,
        "text": Qt.IBeamCursor,
        "wait": Qt.WaitCursor,
        "forbidden": Qt.ForbiddenCursor,
        "grab": Qt.OpenHandCursor,
        "grabbing": Qt.ClosedHandCursor,
    }
    assert CURSORS == expected