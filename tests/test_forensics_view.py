"""Tests for TICK-506 — Virtualise timeline for >5k events (U3).

Acceptance:
 - GIVEN 10k events WHEN displayed THEN no hard cap applied
 - GIVEN 100k events WHEN displayed THEN UI remains responsive
 - GIVEN timeline events WHEN sorted THEN sorting works correctly
 - GIVEN timeline events WHEN filtered THEN filtering works correctly
"""
import os
import time

# Offscreen for headless CI
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _make_events(n, base_name="file", mixed=False):
    """Generate n synthetic timeline events mimicking build_timeline output."""
    from datetime import datetime, timezone
    base = datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp()
    events = []
    for i in range(n):
        # vary filename / size / ext for filtering/sorting checks
        ext = ".txt" if i % 3 == 0 else (".log" if i % 3 == 1 else ".bin")
        fname = f"{base_name}_{i:06d}{ext}" if not mixed else (f"alpha_{i}.txt" if i % 2 == 0 else f"zeta_{i}.log")
        events.append({
            "timestamp_iso": datetime.fromtimestamp(base + i * 61, tz=timezone.utc).isoformat(),
            "timestamp": datetime.fromtimestamp(base + i * 61, tz=timezone.utc).isoformat(),
            "filename": fname,
            "size": (i * 137) % 100000 + 100,
            "extension": ext,
            "ext": ext,
            "owner_uid": 1000 + (i % 4),
            "owner_gid": 1000,
            "mode": "0o644" if i % 2 == 0 else "0o755",
            "path": f"/tmp/evidence/{fname}",
        })
    return events


def test_timeline_model_exists_and_columns(qapp):
    from dataforge.ui.views.forensics_view import TimelineModel
    m = TimelineModel()
    assert hasattr(m, "COLUMNS")
    assert len(m.COLUMNS) == 7  # preserve 7-column structure
    assert "Timestamp" in m.COLUMNS[0]
    assert "Filename" in m.COLUMNS[1]
    assert m.columnCount() == 7
    assert m.rowCount() == 0
    # headerData
    assert m.headerData(0, Qt.Horizontal, Qt.DisplayRole) == m.COLUMNS[0]
    assert m.headerData(1, Qt.Horizontal, Qt.DisplayRole) == m.COLUMNS[1]


def test_no_hard_cap_10k(qapp):
    from dataforge.ui.views.forensics_view import TimelineModel
    m = TimelineModel()
    events = _make_events(10_000)
    m.set_events(events)
    assert m.rowCount() == 10_000, "virtualised model must not cap at 5000"
    # Verify data accessible via model (no widget per row created)
    idx = m.index(9999, 1)
    assert m.data(idx, Qt.DisplayRole) is not None
    # source file must not contain hard cap string events[:5000] (excluding comments is ok)
    src = Path("dataforge/ui/views/forensics_view.py").read_text()
    # ensure the actual slicing loop is gone (allow comments mentioning it)
    # count non-comment lines containing events[:5000]
    hit = False
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "events[:5000]" in line and "for ev in" in line:
            hit = True
    assert not hit, "hard cap events[:5000] must be removed from active code"


def test_100k_remains_responsive(qapp):
    from dataforge.ui.views.forensics_view import TimelineModel
    m = TimelineModel()
    events = _make_events(100_000)
    t0 = time.time()
    m.set_events(events)
    elapsed_set = time.time() - t0
    assert m.rowCount() == 100_000
    # Data access for random rows should be fast (<0.5s for 1000 accesses)
    t0 = time.time()
    for r in (0, 50000, 99999, 1234, 87654):
        for c in range(m.columnCount()):
            idx = m.index(r, c)
            _ = m.data(idx, Qt.DisplayRole)
    elapsed_access = time.time() - t0
    assert elapsed_access < 0.5, f"100k data access too slow: {elapsed_access:.3f}s"
    assert elapsed_set < 1.0, f"set_events for 100k too slow: {elapsed_set:.3f}s"


def test_sorting_works(qapp):
    from dataforge.ui.views.forensics_view import TimelineModel, TimelineProxyModel
    m = TimelineModel()
    proxy = TimelineProxyModel()
    proxy.setSourceModel(m)
    # Create unsorted filenames
    events = _make_events(20, mixed=True)  # alpha/zeta mixing
    # Reverse to ensure unsorted vs sorted distinguishable
    events = list(reversed(events))
    m.set_events(events)
    # Direct model sort by filename (col 1) ascending -> alpha first
    m.sort(1, Qt.AscendingOrder)
    first = m.data(m.index(0, 1), Qt.DisplayRole)
    last = m.data(m.index(m.rowCount() - 1, 1), Qt.DisplayRole)
    assert "alpha" in first.lower(), f"ascending sort failed, first={first}"
    assert "zeta" in last.lower(), f"ascending sort failed, last={last}"
    # Descending
    m.sort(1, Qt.DescendingOrder)
    first_d = m.data(m.index(0, 1), Qt.DisplayRole)
    assert "zeta" in first_d.lower()
    # Proxy sorting: size column (2) numeric
    events2 = _make_events(10)
    # shuffle sizes via randomish generation already increases; test proxy lessThan numeric
    m.set_events(events2)
    proxy.sort(2, Qt.AscendingOrder)
    # Collect sizes via proxy order (UserRole numeric)
    sizes = []
    for r in range(proxy.rowCount()):
        src = proxy.mapToSource(proxy.index(r, 2))
        ev = m.get_event(src.row())
        sizes.append(ev["size"])
    # Proxy sorted ascending -> sizes monotonic
    assert sizes == sorted(sizes), f"proxy size sort failed: {sizes}"
    # Test timestamp sort via model
    m.sort(0, Qt.AscendingOrder)
    ts0 = m.data(m.index(0, 0), Qt.DisplayRole)
    ts_last = m.data(m.index(m.rowCount() - 1, 0), Qt.DisplayRole)
    assert ts0 < ts_last


def test_filtering_works(qapp):
    from dataforge.ui.views.forensics_view import TimelineModel, TimelineProxyModel
    m = TimelineModel()
    proxy = TimelineProxyModel()
    proxy.setSourceModel(m)
    events = []
    # 6 txt, 4 log
    for i in range(10):
        ext = ".txt" if i < 6 else ".log"
        events.append({
            "timestamp_iso": f"2023-01-01T00:00:{i:02d}+00:00",
            "filename": f"file_{i}{ext}",
            "size": 100 + i,
            "extension": ext,
            "owner_uid": 1000,
            "owner_gid": 1000,
            "mode": "0o644",
            "path": f"/tmp/file_{i}{ext}",
        })
    m.set_events(events)
    assert proxy.rowCount() == 10
    # Filter for txt
    proxy.setFilterFixedString(".txt")
    assert proxy.rowCount() == 6, f"filter .txt should yield 6 rows, got {proxy.rowCount()}"
    # Filter case-insensitive: TXT uppercase
    proxy.setFilterFixedString("TXT")
    # proxy is case-insensitive, should still match 6 (DisplayRole contains .txt lower)
    # Our proxy lowercases pattern and data, so should pass
    assert proxy.rowCount() == 6
    # Filter for specific filename substring
    proxy.setFilterFixedString("file_1")
    # matches file_1.txt and maybe file_1? Actually files are file_0..file_9 -> only file_1 matches prefix file_1
    # plus file_?  Should be 1 row (file_1.txt)
    assert proxy.rowCount() == 1
    # Clear filter
    proxy.setFilterFixedString("")
    assert proxy.rowCount() == 10
    # Filter for non-existent should give 0
    proxy.setFilterFixedString("NONEXISTENT123")
    assert proxy.rowCount() == 0


def test_forensics_view_uses_qtableview(qapp):
    src = Path("dataforge/ui/views/forensics_view.py").read_text()
    assert "class TimelineModel(QAbstractTableModel)" in src
    assert "class TimelineProxyModel" in src
    assert "QTreeView" in src
    assert "TimelineModel" in src
    assert "setModel" in src
    assert "QAbstractTableModel" in src
    # EnhancedTreeview should not be used for timeline anymore (still used elsewhere, but not for timeline)
    # Ensure timeline section does not instantiate EnhancedTreeview with timeline columns
    # We check that after the new code, the timeline_tree instantiation no longer exists as active code
    lines = [ln for ln in src.splitlines() if "timeline_tree = EnhancedTreeview" in ln and not ln.strip().startswith("#")]
    assert len(lines) == 0, "timeline must not use EnhancedTreeview anymore"
    # Virtualisation flags
    assert "setUniformRowHeights(True)" in src
    assert "setRootIsDecorated(False)" in src


def test_forensics_view_integration(qapp):
    """Smoke-test that ForensicsView can be instantiated and _on_timeline_built handles large sets."""
    from dataforge.ui.views.forensics_view import ForensicsView
    from unittest.mock import MagicMock

    # Minimal mock app
    # Create a dummy parent widget to host view
    from PyQt5.QtWidgets import QWidget
    parent = QWidget()
    mock_app = MagicMock()
    mock_app.update_status = MagicMock()
    mock_app.show_warning_dialog = MagicMock()
    mock_app.show_error_dialog = MagicMock()
    mock_app.show_info_dialog = MagicMock()

    view = ForensicsView(parent, app=mock_app)
    assert hasattr(view, "timeline_model")
    assert hasattr(view, "timeline_view")
    assert hasattr(view, "timeline_proxy")
    assert hasattr(view, "timeline_filter")
    # Simulate building timeline with 10k events
    events = _make_events(10_000)
    view._on_timeline_built(events)
    assert view.timeline_model.rowCount() == 10_000
    assert view.timeline_proxy.rowCount() == 10_000
    # After filter, proxy count should drop
    view.timeline_filter.setText(".txt")
    # process events to apply filter
    QApplication.processEvents()
    # .txt is 1/3 of events (since ext cycles txt/log/bin) -> ~3334
    assert view.timeline_proxy.rowCount() < 10_000
    assert view.timeline_proxy.rowCount() > 0
    # Clear filter restores
    view.timeline_filter.setText("")
    QApplication.processEvents()
    assert view.timeline_proxy.rowCount() == 10_000
    # Verify no hard cap in status label
    assert "10000" in view.lbl_timeline_status.text()
    assert "5000" not in view.lbl_timeline_status.text() or "10000" in view.lbl_timeline_status.text()
    parent.deleteLater()
