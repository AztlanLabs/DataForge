from __future__ import annotations

import os
import threading

import pytest

from dataforge.core.operations.files import rename_path
from dataforge.core.services.file_actions import FileActionService


def _make_files(tmp_path, count: int, prefix: str = "f"):
    src = tmp_path / prefix
    src.mkdir()
    for i in range(count):
        (src / f"{prefix}{i}.txt").write_text(f"content {i}")
    return [str(src / f"{prefix}{i}.txt") for i in range(count)]


class TestParallelFailureRecords:
    def test_parallel_failure_produces_record(self, tmp_path):
        good1 = tmp_path / "g1.txt"
        good1.write_text("g1")
        good2 = tmp_path / "g2.txt"
        good2.write_text("g2")
        missing = tmp_path / "missing.txt"

        items = [str(good1), str(missing), str(good2)]
        dest = tmp_path / "dest"
        dest.mkdir()

        outcome = FileActionService.transfer_items(items, str(dest), "move", dry_run=False)

        assert len(outcome.records) == 3
        failures = outcome.failures
        assert len(failures) == 1
        assert "ERROR" in failures[0].message

    def test_parallel_exception_indexing(self, tmp_path):
        import dataforge.core.services.file_actions as fa_mod

        items = _make_files(tmp_path, 3)
        dest = tmp_path / "dest"
        dest.mkdir()

        _orig = fa_mod.transfer_path

        def _raise_worker(source_path, destination_dir, action, dry_run=True, reserved_paths=None):
            if source_path == items[1]:
                raise PermissionError("simulated worker crash")
            return _orig(source_path, destination_dir, action, dry_run=dry_run, reserved_paths=reserved_paths)

        fa_mod.transfer_path = _raise_worker
        try:
            outcome = FileActionService.transfer_items(items, str(dest), "move", dry_run=False)
        finally:
            fa_mod.transfer_path = _orig

        assert len(outcome.records) == 3
        failure = outcome.failures[0]
        assert failure.source_path == items[1]
        assert "ERROR" in failure.message


class TestCancellationAccounting:
    def test_cancellation_reports_accurate_counts(self, tmp_path):
        import time
        from unittest.mock import patch

        import dataforge.core.services.file_actions as fa_mod

        items = _make_files(tmp_path, 10)
        dest = tmp_path / "dest"
        dest.mkdir()
        cancel = threading.Event()

        progress_calls = []
        lock = threading.Lock()

        def on_progress(current, total, msg):
            with lock:
                progress_calls.append((current, total, msg))
            if current >= 3:
                cancel.set()

        _orig = fa_mod.transfer_path

        def _slow_transfer(source_path, destination_dir, action, dry_run=True, reserved_paths=None):
            time.sleep(0.02)
            return _orig(source_path, destination_dir, action, dry_run=dry_run, reserved_paths=reserved_paths)

        fa_mod.transfer_path = _slow_transfer
        try:
            with patch.object(fa_mod, "_get_batch_workers", return_value=4):
                outcome = FileActionService.transfer_items(
                    items, str(dest), "move", dry_run=False, cancel_token=cancel, progress_callback=on_progress
                )
        finally:
            fa_mod.transfer_path = _orig

        assert outcome.cancelled
        assert len(outcome.records) == 10
        assert len(outcome.successes) >= 3
        assert len(outcome.skipped_records) >= 1

    def test_requested_equals_input_count(self, tmp_path):
        items = _make_files(tmp_path, 5)
        dest = tmp_path / "dest"
        dest.mkdir()

        outcome = FileActionService.transfer_items(items, str(dest), "move", dry_run=False)

        assert len(outcome.records) == 5
        assert outcome.requested == 5


class TestRenameConfinement:
    def test_rename_rejects_dotdot(self, tmp_path):
        src = tmp_path / "file.txt"
        src.write_text("data")

        with pytest.raises(ValueError):
            rename_path(str(src), "../escape.txt", dry_run=True)

    def test_rename_rejects_separator(self, tmp_path):
        src = tmp_path / "file.txt"
        src.write_text("data")

        with pytest.raises(ValueError):
            rename_path(str(src), "sub/name.txt", dry_run=True)

    def test_rename_accepts_valid_basename(self, tmp_path):
        src = tmp_path / "file.txt"
        src.write_text("data")

        result = rename_path(str(src), "new_name.txt", dry_run=True)

        assert result is not None
        assert result.success


class TestArchiveTempSafety:
    def test_archive_temp_is_unique(self, tmp_path):
        items1 = _make_files(tmp_path, 3, prefix="a")
        items2 = _make_files(tmp_path, 3, prefix="b")
        dest1 = tmp_path / "out1.zip"
        dest2 = tmp_path / "out2.zip"

        outcome1 = FileActionService.archive_items(items1, mode="single", destination=str(dest1), dry_run=False)
        outcome2 = FileActionService.archive_items(items2, mode="single", destination=str(dest2), dry_run=False)

        assert len(outcome1.successes) == 3
        assert len(outcome2.successes) == 3
        assert dest1.exists()
        assert dest2.exists()
        leftovers = [p for p in os.listdir(str(tmp_path)) if p.endswith(".dataforge.tmp")]
        assert leftovers == []

    def test_archive_temp_cleaned_on_failure(self, tmp_path):
        good = tmp_path / "good.txt"
        good.write_text("good")
        dest = tmp_path / "out.zip"

        import dataforge.core.services.file_actions as fa_mod
        _orig = fa_mod.safe_zip_write

        def _mock(zf, source_path, arcname, existing_names):
            raise OSError("simulated mid-write failure")

        fa_mod.safe_zip_write = _mock
        try:
            outcome = FileActionService.archive_items(
                [str(good)], mode="single", destination=str(dest), dry_run=False
            )
        finally:
            fa_mod.safe_zip_write = _orig

        assert len(outcome.failures) == 1
        assert not dest.exists()
        leftovers = [p for p in os.listdir(str(tmp_path)) if p.endswith(".dataforge.tmp")]
        assert leftovers == []


class TestOutcomeCancelled:
    def test_outcome_cancelled_field_matches_token(self, tmp_path):
        items = _make_files(tmp_path, 3)
        dest = tmp_path / "dest"
        dest.mkdir()
        cancel = threading.Event()
        cancel.set()

        outcome = FileActionService.transfer_items(items, str(dest), "move", dry_run=False, cancel_token=cancel)

        assert outcome.cancelled is True