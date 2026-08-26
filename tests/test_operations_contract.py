"""TICK-919 — Unified result contract, rename confinement, transfer safety.

Covers audit findings P1.1 (mixed result types -> OperationReport) and P1.7
(rename path escape, same-file overwrite) from
docs/reviews/STABILITY_AUDIT_2026-08-23.md.
"""

from __future__ import annotations

import os

import pytest

from dataforge.core.operations import OperationReport, rename_path, transfer_path
from dataforge.core.services import FileActionService


def _make_file(tmp_path, name: str = "orig.txt") -> str:
    f = tmp_path / name
    f.write_text("tick-919 payload")
    return str(f)


def test_rename_rejects_dotdot(tmp_path):
    src = _make_file(tmp_path)
    with pytest.raises(ValueError):
        rename_path(src, "../escape.txt")


def test_rename_rejects_absolute(tmp_path):
    src = _make_file(tmp_path)
    with pytest.raises(ValueError):
        rename_path(src, "/tmp/escape.txt")


def test_rename_rejects_separator(tmp_path):
    src = _make_file(tmp_path)
    with pytest.raises(ValueError):
        rename_path(src, "sub/name.txt")


def test_rename_rejects_empty(tmp_path):
    src = _make_file(tmp_path)
    with pytest.raises(ValueError):
        rename_path(src, "")


def test_rename_accepts_valid_basename(tmp_path):
    src = _make_file(tmp_path)
    result = rename_path(src, "new_name.txt", dry_run=False)
    assert result is not None
    assert result.success
    assert (tmp_path / "new_name.txt").exists()
    assert not (tmp_path / "orig.txt").exists()


def test_rename_preserves_directory(tmp_path):
    sub = tmp_path / "subdir"
    sub.mkdir()
    src = _make_file(sub)
    result = rename_path(src, "renamed.txt", dry_run=False)
    assert result is not None
    assert result.success
    assert os.path.dirname(result.destination_path) == str(sub)
    assert (sub / "renamed.txt").exists()


def test_transfer_same_file_no_overwrite(tmp_path):
    src = _make_file(tmp_path)
    result = transfer_path(src, src, "copy")
    assert result.success is False
    assert "same file" in result.message.lower()


def test_transfer_different_file_succeeds(tmp_path):
    src = _make_file(tmp_path)
    dest_dir = tmp_path / "out"
    result = transfer_path(src, str(dest_dir), "copy", dry_run=False)
    assert result.success
    assert (dest_dir / "orig.txt").exists()
    assert (tmp_path / "orig.txt").read_text() == "tick-919 payload"


def test_operation_report_fields():
    report = OperationReport(
        operation="transfer",
        requested=3,
        completed=2,
        failed=1,
        errors=["boom"],
    )
    assert report.operation == "transfer"
    assert report.requested == 3
    assert report.completed == 2
    assert report.failed == 1
    assert report.skipped == 0
    assert report.cancelled is False
    assert report.success is True
    assert report.errors == ["boom"]
    assert report.outputs == []
    assert report.warnings == []
    assert report.dry_run is False


def test_batch_outcome_requested_equals_records(tmp_path):
    files = [_make_file(tmp_path, f"f{i}.txt") for i in range(5)]
    outcome = FileActionService.transfer_items(
        files,
        str(tmp_path / "dest"),
        "copy",
        dry_run=True,
    )
    assert outcome.requested == 5
    assert len(outcome.records) == 5