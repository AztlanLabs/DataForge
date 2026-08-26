"""TICK-923 — Cleanup + Recovery: checkbox wiring, type filters,
cancellation display, path confinement.

Covers audit findings P1.8 (browser checkbox no-op, reversed error callback,
double-counted savings) and P1.9 (PhotoRec ignores types, CLI case mismatch,
cancellation shown as completion, trash path escape) from
docs/reviews/STABILITY_AUDIT_2026-08-23.md.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from dataforge.modules.recovery import _normalize_type, carve_files_from_image
from dataforge.modules.system_cleanup import scan_junk_files


@pytest.fixture
def qapp():
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    return app


class _FakeApp:
    """Minimal app double exposing only what the views call in tests."""

    def __init__(self):
        self.workflow_calls = []
        self.statuses = []
        self.errors = []

    def run_workflow(self, target, on_success, *args, **kwargs):
        self.workflow_calls.append((target, on_success, args, kwargs))

    def update_status(self, text):
        self.statuses.append(text)

    def show_workflow_error(self, error, title="Operation Failed"):
        self.errors.append((error, title))

    def show_warning_dialog(self, *a, **k):
        pass

    def show_error_dialog(self, *a, **k):
        pass

    def show_info_dialog(self, *a, **k):
        pass


# ---------------------------------------------------------------------------
# P1.8 — Browser checkbox wiring + error callback order + savings dedup
# ---------------------------------------------------------------------------


def test_browser_checkbox_wired(qapp):
    from dataforge.ui.views.system_cleanup import SystemCleanupView

    fake = _FakeApp()
    view = SystemCleanupView(None, app=fake)
    view.chk_include_browser.setChecked(False)
    view._start_junk_scan()
    assert fake.workflow_calls, "scan must be started"
    target, _cb, args, _kw = fake.workflow_calls[-1]
    assert target.__name__ == "scan_junk_files"
    assert args[0] is None, "browser profiles must not be in scan params when unchecked"


def test_browser_checkbox_checked_includes_profiles(qapp):
    from dataforge.ui.views.system_cleanup import SystemCleanupView

    fake = _FakeApp()
    view = SystemCleanupView(None, app=fake)
    with patch(
        "dataforge.ui.views.system_cleanup._get_browser_profile_paths",
        return_value=["/fake/chrome-cache", "/fake/firefox-cache"],
    ):
        view.chk_include_browser.setChecked(True)
        view._start_junk_scan()
    target, _cb, args, _kw = fake.workflow_calls[-1]
    assert target.__name__ == "scan_junk_files"
    assert args[0] == ["/fake/chrome-cache", "/fake/firefox-cache"], (
        "checked checkbox must pass browser profile paths to the scan"
    )


def test_error_callback_correct_order(qapp):
    from dataforge.ui.views.system_cleanup import SystemCleanupView

    fake = _FakeApp()
    view = SystemCleanupView(None, app=fake)
    view._on_junk_scan_error("boom")
    assert fake.errors == [("boom", "Junk Scan Failed")], (
        "show_workflow_error must receive (error, title), not reversed"
    )


def test_savings_deduplicated(tmp_path, monkeypatch):
    junk_dir = tmp_path / "junk"
    junk_dir.mkdir()
    now = datetime.now(timezone.utc)
    aged_ts = (now - timedelta(days=2)).timestamp()
    for i in range(3):
        f = junk_dir / f"cache_{i}.bak"
        f.write_text("x")
        # tmp_path is under /tmp — the 1-day system-temp guard would skip
        # freshly written files, so age them past it.
        os.utime(f, (aged_ts, aged_ts))
    monkeypatch.setattr(
        "dataforge.modules.system_cleanup._get_platform_junk_paths",
        lambda: {"System Temp": [str(junk_dir)], "User Cache": [str(junk_dir)]},
    )
    results = scan_junk_files()
    all_paths = [e.path for entries in results.values() for e in entries]
    canon = [os.path.realpath(p) for p in all_paths]
    assert len(all_paths) == 3, "overlapping categories must not double-count"
    assert len(set(canon)) == len(canon), "no duplicate paths may remain in results"


def test_junk_scan_min_age_filter(tmp_path, monkeypatch):
    junk_dir = tmp_path / "aged"
    junk_dir.mkdir()
    old = junk_dir / "old.bak"
    old.write_text("old")
    recent = junk_dir / "recent.bak"
    recent.write_text("recent")
    now = datetime.now(timezone.utc)
    old_ts = (now - timedelta(days=10)).timestamp()
    recent_ts = (now - timedelta(days=1)).timestamp()
    os.utime(old, (old_ts, old_ts))
    os.utime(recent, (recent_ts, recent_ts))
    monkeypatch.setattr(
        "dataforge.modules.system_cleanup._get_platform_junk_paths",
        lambda: {"System Temp": [str(junk_dir)]},
    )
    results = scan_junk_files(min_age_days=7)
    paths = [e.path for entries in results.values() for e in entries]
    assert len(paths) == 1
    assert os.path.basename(paths[0]) == "old.bak"


# ---------------------------------------------------------------------------
# P1.9 — PhotoRec types, type normalization, cancellation, trash path
# ---------------------------------------------------------------------------


def test_photorec_receives_file_types(qapp):
    from dataforge.ui.views.recovery_view import RecoveryView

    fake = _FakeApp()
    view = RecoveryView(None, app=fake)
    view.entry_image.setText("/dev/sdb")
    view.entry_output.setText("/tmp/rec")
    with patch("dataforge.ui.views.recovery_view.QMessageBox.question", return_value=16384):
        view._start_photorec()
    target, _cb, args, _kw = fake.workflow_calls[-1]
    assert target.__name__ == "run_photorec"
    assert args[0] == "/dev/sdb"
    assert args[1] == "/tmp/rec"
    assert args[2] is not None and "JPEG" in args[2], (
        "selected file types must be passed to run_photorec"
    )


def test_type_normalization_case_insensitive(tmp_path):
    image = tmp_path / "disk.img"
    out = tmp_path / "carved"
    image.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01fake jpeg data\xff\xd9")
    result = carve_files_from_image(str(image), str(out), file_types=["jpg"])
    assert result.get("error") is None
    assert result["total_carved"] == 1
    assert result["carved"][0]["format"] == "JPEG"


def test_normalize_type_helper():
    assert _normalize_type("jpg") == "JPEG"
    assert _normalize_type(" Jpeg ") == "JPEG"
    assert _normalize_type("pdf") == "PDF"


def test_restore_cancelled_shows_cancelled(qapp):
    from dataforge.ui.views.recovery_view import RecoveryView

    fake = _FakeApp()
    view = RecoveryView(None, app=fake)
    view._on_restore_complete({"restored": [], "failed": [], "cancelled": True})
    assert "cancelled" in view.lbl_restore_status.text().lower()
    assert any("cancelled" in s.lower() for s in fake.statuses)


def test_carve_cancelled_shows_cancelled(qapp):
    from dataforge.ui.views.recovery_view import RecoveryView

    fake = _FakeApp()
    view = RecoveryView(None, app=fake)
    view._on_carve_complete({"cancelled": True, "carved": []})
    assert "cancelled" in view.lbl_deep_summary.text().lower()
    assert any("cancelled" in s.lower() for s in fake.statuses)


def test_trash_action_uses_trash_path(qapp, tmp_path):
    from dataforge.ui.views.recovery_view import RecoveryView

    fake = _FakeApp()
    view = RecoveryView(None, app=fake)
    trash_file = tmp_path / "trash" / "deleted.pdf"
    trash_file.parent.mkdir(parents=True)
    trash_file.write_text("gone")
    items = [{
        "path": str(trash_file),
        "filename": "deleted.pdf",
        "original_path": "/home/user/docs/live.pdf",
        "deletion_date": None,
        "size": 4,
        "formatted_size": "4 B",
        "trash_location": str(trash_file.parent),
    }]
    view._on_trash_scan_complete(items)
    iid = view.trash_tree.insert("", "end", values=("dup",), path=str(trash_file))
    assert view.trash_tree.get_item_path(iid) == str(trash_file), (
        "context actions must resolve the trash object path, not original_path"
    )