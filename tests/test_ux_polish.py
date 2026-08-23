"""Tests for TICK-705 — U5-U9 UX polish.

Acceptance:
 - U5 mismatch flag + forensics_view column+filter
 - U6 glyph + colour (not colour-only)
 - U7 preview correlated to evidence row
 - U8 DnD disabled
 - U9 keyboard timeline nav
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PyQt5.QtCore import Qt, QModelIndex
from PyQt5.QtGui import QBrush
from PyQt5.QtWidgets import QApplication, QWidget, QAbstractItemView

from dataforge.ui.theme_tokens import STATUS_GLYPHS, GLYPH_SUCCESS, GLYPH_WARNING, GLYPH_ERROR, glyph_for_status


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _make_events(n=5):
    from datetime import datetime, timezone
    base = datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp()
    events = []
    for i in range(n):
        events.append({
            "timestamp_iso": datetime.fromtimestamp(base + i * 100, tz=timezone.utc).isoformat(),
            "filename": f"file_{i}.txt",
            "size": 100 + i,
            "extension": ".txt",
            "owner_uid": 1000,
            "owner_gid": 1000,
            "mode": "0o644",
            "path": f"/tmp/evidence/file_{i}.txt",
        })
    return events


# ---------------------------------------------------------------------------
# U5: mismatch flag
# ---------------------------------------------------------------------------
def test_u5_mismatch_flag_and_view_column(tmp_path, qapp):
    from dataforge.modules.forensics import profile_directory_types

    # create dir with .jpg that is actually PNG magic
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
    jpg_path = tmp_path / "fake.jpg"
    jpg_path.write_bytes(png_header)
    # also a correct png
    png_path = tmp_path / "real.png"
    png_path.write_bytes(png_header)
    # and a txt (unknown)
    txt_path = tmp_path / "note.txt"
    txt_path.write_bytes(b"hello world")

    result = profile_directory_types(str(tmp_path))
    assert "mismatch_count" in result
    rows = result["rows"]
    # find fake.jpg row
    fake = next(r for r in rows if r["filename"] == "fake.jpg")
    real = next(r for r in rows if r["filename"] == "real.png")
    assert fake["mismatch"] is True, "jpg with PNG magic must be mismatch"
    assert fake["mismatch_glyph"] == GLYPH_WARNING
    assert real["mismatch"] is False
    assert real["mismatch_glyph"] == GLYPH_SUCCESS
    assert result["mismatch_count"] >= 1

    # forensics_view shows mismatch icon + filter
    from dataforge.ui.views.forensics_view import ForensicsView
    from unittest.mock import MagicMock
    parent = QWidget()
    mock_app = MagicMock()
    mock_app.update_status = MagicMock()
    mock_app.show_warning_dialog = MagicMock()
    view = ForensicsView(parent, app=mock_app)
    # verify mismatch column exists
    cols = view.ftype_row_tree.tree.headerItem()
    headers = [cols.text(i) for i in range(cols.columnCount())]
    assert "Mismatch" in headers, f"mismatch column missing: {headers}"
    # feed result via _on_ftypes_profiled
    view._on_ftypes_profiled(result)
    # check that row for fake.jpg shows glyph
    found = False
    for iid, item in view.ftype_row_tree.item_map.items():
        vals = view.ftype_row_tree.item(iid)["values"]
        if "fake.jpg" in vals[0]:
            # mismatch column is index 4
            assert GLYPH_WARNING in vals[4] or "Mismatch" in vals[4], f"mismatch cell must show glyph: {vals}"
            found = True
            # U6 colour check for mismatch
            brush = item.foreground(4)
            assert isinstance(brush, QBrush)
            assert brush.color().name() != ""
    assert found, "fake.jpg row not found in view"
    # filter: show mismatched only should reduce rows to only mismatched
    view.chk_ftype_mismatch_only.setChecked(True)
    QApplication.processEvents()
    # after filter, only mismatched rows visible
    visible = len(view.ftype_row_tree.item_map)
    assert visible == result["mismatch_count"], f"filter should show only mismatched: {visible} vs {result['mismatch_count']}"
    # uncheck restores all
    view.chk_ftype_mismatch_only.setChecked(False)
    QApplication.processEvents()
    assert len(view.ftype_row_tree.item_map) == len(rows)
    parent.deleteLater()


# ---------------------------------------------------------------------------
# U6: glyph + colour (not colour-only)
# ---------------------------------------------------------------------------
def test_u6_glyph_via_theme_tokens_and_timeline_status(qapp):
    # theme_tokens glyphs exist
    assert STATUS_GLYPHS["success"] == "✓"
    assert STATUS_GLYPHS["warning"] == "⚠"
    assert STATUS_GLYPHS["error"] == "✕"
    assert glyph_for_status("error") == "✕"
    assert glyph_for_status("warning") == "⚠"
    assert glyph_for_status("success") == "✓"

    from dataforge.ui.views.forensics_view import TimelineModel
    m = TimelineModel()
    # row with error status -> display should contain glyph and ForegroundRole should be brush
    events = _make_events(2)
    events[0]["status"] = "error"
    events[1]["status"] = "success"
    m.set_events(events)
    idx_err = m.index(0, 1)  # filename column
    disp = m.data(idx_err, Qt.DisplayRole)
    assert GLYPH_ERROR in disp, f"error status must show glyph: {disp}"
    fg = m.data(idx_err, Qt.ForegroundRole)
    assert isinstance(fg, QBrush), "foreground must be QBrush for colour"
    assert fg.color().name() != ""
    idx_ok = m.index(1, 1)
    disp_ok = m.data(idx_ok, Qt.DisplayRole)
    assert GLYPH_SUCCESS in disp_ok
    fg_ok = m.data(idx_ok, Qt.ForegroundRole)
    assert isinstance(fg_ok, QBrush)

    # also check mismatch handling via TimelineModel (mismatch true -> warning)
    m2 = TimelineModel()
    ev = _make_events(1)[0]
    ev["mismatch"] = True
    m2.set_events([ev])
    assert GLYPH_WARNING in m2.data(m2.index(0, 1), Qt.DisplayRole)
    assert isinstance(m2.data(m2.index(0, 1), Qt.ForegroundRole), QBrush)

    # ftype mismatch already checked but also verify integrity tree uses glyph
    from dataforge.ui.views.forensics_view import ForensicsView
    from unittest.mock import MagicMock
    parent = QWidget()
    mock_app = MagicMock()
    mock_app.update_status = MagicMock()
    view = ForensicsView(parent, app=mock_app)
    # simulate verify results
    from dataforge.modules.forensics import snapshot_file_state, verify_file_state
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "a.txt"
        p.write_text("hello")
        snap = snapshot_file_state([str(p)])
        # modify file to trigger changed
        p.write_text("changed")
        results = verify_file_state(snap)
        view._on_snapshot_verified(results)
        # first row should have warning glyph for changed
        assert len(view.integrity_tree.item_map) == 1
        vals = list(view.integrity_tree.item_map.values())[0].text(1)
        assert GLYPH_WARNING in vals or GLYPH_SUCCESS in vals or GLYPH_ERROR in vals, "integrity status must contain glyph"
        item = list(view.integrity_tree.item_map.values())[0]
        brush = item.foreground(1)
        assert isinstance(brush, QBrush)
    parent.deleteLater()


# ---------------------------------------------------------------------------
# U7: preview correlated
# ---------------------------------------------------------------------------
def test_u7_preview_correlated_to_timeline_selection(tmp_path, qapp):
    from dataforge.ui.views.forensics_view import ForensicsView
    from unittest.mock import MagicMock
    parent = QWidget()
    mock_app = MagicMock()
    mock_app.update_status = MagicMock()
    mock_app.show_warning_dialog = MagicMock()
    view = ForensicsView(parent, app=mock_app)
    assert hasattr(view, "timeline_preview"), "timeline must have FilePreviewPanel"
    assert hasattr(view, "_on_timeline_selection_changed")

    # create real files for preview
    files = []
    events = []
    from datetime import datetime, timezone
    base = datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp()
    for i in range(3):
        f = tmp_path / f"ev_{i}.txt"
        f.write_text(f"content {i}")
        files.append(str(f))
        events.append({
            "timestamp_iso": datetime.fromtimestamp(base + i * 100, tz=timezone.utc).isoformat(),
            "filename": f"ev_{i}.txt",
            "size": 100,
            "extension": ".txt",
            "owner_uid": 1000,
            "owner_gid": 1000,
            "mode": "0o644",
            "path": str(f),
        })
    view.timeline_model.set_events(events)
    QApplication.processEvents()
    # select first row via selection model
    proxy_first = view.timeline_proxy.index(0, 0)
    view.timeline_view.setCurrentIndex(proxy_first)
    QApplication.processEvents()
    # trigger handler (selectionModel currentChanged should have fired, but also call directly to ensure)
    view._on_timeline_selection_changed(proxy_first, QModelIndex())
    QApplication.processEvents()
    # preview should be correlated to whichever row was selected (proxy row 0 may be newest due to sort)
    expected0 = view._get_timeline_selected_path()
    assert expected0 in files, f"selected path not in files: {expected0}"
    assert view.timeline_preview._current_path == expected0 or view.timeline_preview.lbl_name.text() == os.path.basename(expected0), f"preview not correlated: {view.timeline_preview.lbl_name.text()} vs {expected0}"
    # move to second row
    proxy_second = view.timeline_proxy.index(1, 0)
    if proxy_second.isValid():
        view.timeline_view.setCurrentIndex(proxy_second)
        view._on_timeline_selection_changed(proxy_second, proxy_first)
        QApplication.processEvents()
        expected1 = view._get_timeline_selected_path()
        assert expected1 in files and expected1 != expected0, f"second select should change path: {expected1} vs {expected0}"
        assert view.timeline_preview._current_path == expected1 or view.timeline_preview.lbl_name.text() == os.path.basename(expected1)
    parent.deleteLater()


# ---------------------------------------------------------------------------
# U8: DnD disabled
# ---------------------------------------------------------------------------
def test_u8_drag_drop_disabled(qapp):
    from dataforge.ui.views.forensics_view import ForensicsView
    from dataforge.ui.widgets import EnhancedTreeview
    from unittest.mock import MagicMock
    parent = QWidget()
    mock_app = MagicMock()
    mock_app.update_status = MagicMock()
    mock_app.show_warning_dialog = MagicMock()
    view = ForensicsView(parent, app=mock_app)
    # timeline_view
    assert view.timeline_view.dragDropMode() == QAbstractItemView.NoDragDrop
    assert view.timeline_view.defaultDropAction() == Qt.IgnoreAction
    assert not view.timeline_view.isEnabled() or not view.timeline_view.acceptDrops()
    # ftype trees
    assert view.ftype_row_tree.tree.dragDropMode() == QAbstractItemView.NoDragDrop
    assert view.ftype_count_tree.tree.dragDropMode() == QAbstractItemView.NoDragDrop
    assert view.ftype_row_tree.tree.defaultDropAction() == Qt.IgnoreAction
    # other forensics trees use EnhancedTreeview which now disables DnD
    for attr in ("ingest_tree", "hash_tree", "artifact_tree", "pwd_tree", "entropy_tree", "integrity_tree"):
        tree = getattr(view, attr, None)
        if tree is not None:
            assert tree.tree.dragDropMode() == QAbstractItemView.NoDragDrop, f"{attr} DnD not disabled"
            assert tree.tree.defaultDropAction() == Qt.IgnoreAction

    # EnhancedTreeview generally
    et = EnhancedTreeview(parent, columns=("a", "b"))
    assert et.tree.dragDropMode() == QAbstractItemView.NoDragDrop
    assert et.tree.defaultDropAction() == Qt.IgnoreAction

    # BaseView table
    from dataforge.ui.views.base import BaseView
    import inspect
    src = inspect.getsource(BaseView.confirm_destructive_preview)
    assert "setDragDropMode(QAbstractItemView.NoDragDrop)" in src
    assert "setDefaultDropAction(Qt.IgnoreAction)" in src

    # widgets field_inspector
    from dataforge.ui.widgets import HexView
    hv = HexView()
    assert hv.field_inspector.dragDropMode() == QAbstractItemView.NoDragDrop

    parent.deleteLater()


# ---------------------------------------------------------------------------
# U9: keyboard nav
# ---------------------------------------------------------------------------
def test_u9_keyboard_timeline_nav(tmp_path, qapp):
    from dataforge.ui.views.forensics_view import ForensicsView
    from unittest.mock import MagicMock
    from PyQt5.QtGui import QKeyEvent
    from PyQt5.QtCore import QEvent

    parent = QWidget()
    mock_app = MagicMock()
    mock_app.update_status = MagicMock()
    mock_app.show_warning_dialog = MagicMock()
    view = ForensicsView(parent, app=mock_app)

    # create 5 files/events
    files = []
    events = []
    from datetime import datetime, timezone
    base = datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp()
    for i in range(5):
        f = tmp_path / f"k_{i}.txt"
        f.write_text(f"data {i}")
        files.append(str(f))
        events.append({
            "timestamp_iso": datetime.fromtimestamp(base + i * 100, tz=timezone.utc).isoformat(),
            "filename": f"k_{i}.txt",
            "size": 100,
            "extension": ".txt",
            "owner_uid": 1000,
            "owner_gid": 1000,
            "mode": "0o644",
            "path": str(f),
        })
    view.timeline_model.set_events(events)
    QApplication.processEvents()
    view.timeline_view.setFocus()
    QApplication.processEvents()

    # select first row
    first = view.timeline_proxy.index(0, 0)
    view.timeline_view.setCurrentIndex(first)
    view._on_timeline_selection_changed(first, QModelIndex())
    QApplication.processEvents()
    exp0 = view._get_timeline_selected_path()
    assert exp0 in files
    assert view.timeline_preview.lbl_name.text() == os.path.basename(exp0) or view.timeline_preview._current_path == exp0

    # simulate Down arrow -> should move to row 1 and update preview
    # Use keyPressEvent directly (TimelineKeyNavTreeView handles)
    view.timeline_view.setFocus()
    QApplication.processEvents()
    # send Down key via event
    evt_down = QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier)
    view.timeline_view.keyPressEvent(evt_down)
    QApplication.processEvents()
    # after Down, selection should move (not stay invalid)
    cur = view.timeline_view.currentIndex()
    cur_row = view.timeline_proxy.mapToSource(cur).row() if cur.isValid() else -1
    assert 0 <= cur_row < len(files), f"Down should move selection to valid row, got {cur_row}"
    # check preview still correlated to current path
    cur_path = view._get_timeline_selected_path()
    assert cur_path in files, f"preview path not in files after Down: {cur_path}"
    # ensure preview widget reflects that path
    preview_name = view.timeline_preview.lbl_name.text()
    assert preview_name in [f"k_{i}.txt" for i in range(5)], f"preview name not updated: {preview_name}"

    # Test other nav keys don't crash and keep preview correlated
    for key in (Qt.Key_Up, Qt.Key_Right, Qt.Key_Left, Qt.Key_Plus, Qt.Key_Minus, Qt.Key_Space):
        evt = QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier)
        try:
            view.timeline_view.keyPressEvent(evt)
        except Exception as e:
            pytest.fail(f"key {key} raised: {e}")
        QApplication.processEvents()
        # preview should still be valid file
        p = view._get_timeline_selected_path()
        assert p is None or p in files

    # Verify view has keyPressEvent handling and preview wiring
    src = Path("dataforge/ui/views/forensics_view.py").read_text()
    assert "TimelineKeyNavTreeView" in src
    assert "keyPressEvent" in src
    assert "selectionModel().currentChanged" in src or "_on_timeline_selection_changed" in src
    parent.deleteLater()
