from __future__ import annotations

import os
import threading
import zipfile

from dataforge.core.services.file_actions import (
    BatchActionOutcome,
    BatchActionRecord,
    FileActionService,
    _get_batch_workers,
)


class TestParallelTransfer:
    def test_move_dry_run_sequential(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        for i in range(5):
            (src / f"f{i}.txt").write_text(f"content {i}")
        dest = tmp_path / "dest"
        dest.mkdir()

        items = [str(src / f"f{i}.txt") for i in range(5)]
        outcome = FileActionService.transfer_items(items, str(dest), "move", dry_run=True)

        assert outcome.requested == 5
        assert len(outcome.successes) == 5
        assert all(r.message.startswith("Would move") for r in outcome.successes)
        for i in range(5):
            assert (src / f"f{i}.txt").exists()

    def test_move_execute_parallel(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        for i in range(20):
            (src / f"f{i}.txt").write_text(f"content {i}")
        dest = tmp_path / "dest"
        dest.mkdir()

        items = [str(src / f"f{i}.txt") for i in range(20)]
        outcome = FileActionService.transfer_items(items, str(dest), "move", dry_run=False)

        assert outcome.requested == 20
        assert len(outcome.successes) == 20
        assert not outcome.cancelled
        for i in range(20):
            assert not (src / f"f{i}.txt").exists()
            assert (dest / f"f{i}.txt").exists()

    def test_copy_execute_parallel(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        for i in range(10):
            (src / f"f{i}.txt").write_text(f"content {i}")
        dest = tmp_path / "dest"
        dest.mkdir()

        items = [str(src / f"f{i}.txt") for i in range(10)]
        outcome = FileActionService.transfer_items(items, str(dest), "copy", dry_run=False)

        assert outcome.requested == 10
        assert len(outcome.successes) == 10
        for i in range(10):
            assert (src / f"f{i}.txt").exists()
            assert (dest / f"f{i}.txt").exists()

    def test_reserved_paths_thread_safe_no_collision(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        for i in range(30):
            (src / f"f{i}.txt").write_text(f"content {i}")
        dest = tmp_path / "dest"
        dest.mkdir()

        items = [str(src / f"f{i}.txt") for i in range(30)]
        outcome = FileActionService.transfer_items(items, str(dest), "move", dry_run=False)

        assert outcome.requested == 30
        assert len(outcome.successes) == 30
        dest_files = sorted(os.listdir(str(dest)))
        assert len(dest_files) == 30
        assert len(set(dest_files)) == 30


class TestParallelDelete:
    def test_delete_dry_run(self, tmp_path):
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text(f"content {i}")

        items = [str(tmp_path / f"f{i}.txt") for i in range(5)]
        outcome = FileActionService.delete_items(items, dry_run=True, safe_mode=False)

        assert outcome.requested == 5
        assert len(outcome.successes) == 5
        for i in range(5):
            assert (tmp_path / f"f{i}.txt").exists()

    def test_delete_execute_parallel(self, tmp_path):
        for i in range(20):
            (tmp_path / f"f{i}.txt").write_text(f"content {i}")

        items = [str(tmp_path / f"f{i}.txt") for i in range(20)]
        outcome = FileActionService.delete_items(items, dry_run=False, safe_mode=False)

        assert outcome.requested == 20
        assert len(outcome.successes) == 20
        for i in range(20):
            assert not (tmp_path / f"f{i}.txt").exists()


class TestParallelRename:
    def test_rename_dry_run(self, tmp_path):
        for i in range(5):
            (tmp_path / f"old{i}.txt").write_text(f"content {i}")

        items = [str(tmp_path / f"old{i}.txt") for i in range(5)]
        outcome = FileActionService.rename_items_with_regex(
            items, r"old", "new", dry_run=True
        )

        assert outcome.requested == 5
        assert len(outcome.successes) == 5
        for i in range(5):
            assert (tmp_path / f"old{i}.txt").exists()

    def test_rename_execute_parallel(self, tmp_path):
        for i in range(20):
            (tmp_path / f"old_{i}.txt").write_text(f"content {i}")

        items = [str(tmp_path / f"old_{i}.txt") for i in range(20)]
        outcome = FileActionService.rename_items_with_regex(
            items, r"old_", "new_", dry_run=False
        )

        assert outcome.requested == 20
        assert len(outcome.successes) == 20
        for i in range(20):
            assert not (tmp_path / f"old_{i}.txt").exists()
            assert (tmp_path / f"new_{i}.txt").exists()


class TestArchiveRops2:
    def test_single_mode_bad_file_others_still_get_records(self, tmp_path):
        good1 = tmp_path / "good1.txt"
        good1.write_text("good1")
        bad = tmp_path / "bad.txt"
        bad.write_bytes(b"\x00" * 10)
        good2 = tmp_path / "good2.txt"
        good2.write_text("good2")
        dest = tmp_path / "out.zip"

        items = [str(good1), str(bad), str(good2)]

        import dataforge.core.services.file_actions as fa_mod
        _orig = fa_mod.safe_zip_write

        def _mock(zf, source_path, arcname, existing_names):
            if os.path.basename(source_path) == "bad.txt":
                raise PermissionError("simulated write failure")
            return _orig(zf, source_path, arcname, existing_names)

        fa_mod.safe_zip_write = _mock
        try:
            outcome = FileActionService.archive_items(
                items, mode="single", destination=str(dest), dry_run=False
            )
        finally:
            fa_mod.safe_zip_write = _orig

        assert outcome.requested == 3
        assert len(outcome.records) == 3
        bad_records = [r for r in outcome.records if not r.success]
        assert len(bad_records) == 1
        assert bad_records[0].source_path == str(bad)
        assert "ERROR" in bad_records[0].message
        good_records = [r for r in outcome.records if r.success]
        assert len(good_records) == 2

    def test_single_mode_bad_file_partial_zip_removed(self, tmp_path):
        good1 = tmp_path / "good1.txt"
        good1.write_text("good1")
        bad = tmp_path / "bad.txt"
        bad.write_bytes(b"\x00" * 10)
        dest = tmp_path / "out.zip"

        items = [str(good1), str(bad)]

        import dataforge.core.services.file_actions as fa_mod
        _orig = fa_mod.safe_zip_write

        def _mock(zf, source_path, arcname, existing_names):
            if os.path.basename(source_path) == "bad.txt":
                raise IOError("simulated")
            return _orig(zf, source_path, arcname, existing_names)

        fa_mod.safe_zip_write = _mock
        try:
            FileActionService.archive_items(
                items, mode="single", destination=str(dest), dry_run=False
            )
        finally:
            fa_mod.safe_zip_write = _orig

        assert not dest.exists()
        assert not (tmp_path / "out.zip.tmp").exists()

    def test_single_mode_cancel_removes_tmp(self, tmp_path):
        for i in range(10):
            (tmp_path / f"f{i}.txt").write_text(f"content {i}")
        dest = tmp_path / "out.zip"
        cancel = threading.Event()

        items = [str(tmp_path / f"f{i}.txt") for i in range(10)]

        import dataforge.core.services.file_actions as fa_mod
        _orig = fa_mod.safe_zip_write
        call_count = 0

        def _mock(zf, source_path, arcname, existing_names):
            nonlocal call_count
            call_count += 1
            if call_count >= 5:
                cancel.set()
            return _orig(zf, source_path, arcname, existing_names)

        fa_mod.safe_zip_write = _mock
        try:
            outcome = FileActionService.archive_items(
                items, mode="single", destination=str(dest),
                dry_run=False, cancel_token=cancel,
            )
        finally:
            fa_mod.safe_zip_write = _orig

        assert outcome.cancelled
        assert not dest.exists()
        assert not (tmp_path / "out.zip.tmp").exists()

    def test_single_mode_atomic_replace(self, tmp_path):
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text(f"content {i}")
        dest = tmp_path / "out.zip"

        items = [str(tmp_path / f"f{i}.txt") for i in range(5)]
        outcome = FileActionService.archive_items(
            items, mode="single", destination=str(dest), dry_run=False
        )

        assert len(outcome.successes) == 5
        assert dest.exists()
        assert not (tmp_path / "out.zip.tmp").exists()
        with zipfile.ZipFile(str(dest), "r") as zf:
            names = zf.namelist()
            assert len(names) == 5


class TestArchiveIndividualParallel:
    def test_individual_parallel(self, tmp_path):
        for i in range(10):
            (tmp_path / f"f{i}.txt").write_text(f"content {i}")

        items = [str(tmp_path / f"f{i}.txt") for i in range(10)]
        outcome = FileActionService.archive_items(
            items, mode="individual", dry_run=False
        )

        assert outcome.requested == 10
        assert len(outcome.successes) == 10
        for i in range(10):
            zip_path = tmp_path / f"f{i}.zip"
            assert zip_path.exists()
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                assert f"f{i}.txt" in zf.namelist()

    def test_individual_bad_file_others_succeed(self, tmp_path):
        good = tmp_path / "good.txt"
        good.write_text("good")
        bad = tmp_path / "bad.txt"
        bad.write_bytes(b"\x00" * 10)

        items = [str(good), str(bad)]

        import dataforge.core.services.file_actions as fa_mod
        _orig = fa_mod.safe_zip_write

        def _mock(zf, source_path, arcname, existing_names):
            if os.path.basename(source_path) == "bad.txt":
                raise OSError("simulated")
            return _orig(zf, source_path, arcname, existing_names)

        fa_mod.safe_zip_write = _mock
        try:
            outcome = FileActionService.archive_items(
                items, mode="individual", dry_run=False
            )
        finally:
            fa_mod.safe_zip_write = _orig

        assert outcome.requested == 2
        assert len(outcome.successes) == 1
        assert len(outcome.failures) == 1
        assert outcome.failures[0].source_path == str(bad)
        assert (tmp_path / "good.zip").exists()
        assert not (tmp_path / "bad.zip").exists()
        assert not (tmp_path / "bad.zip.tmp").exists()


class TestCancelToken:
    def test_cancel_transfer_accounts_all_items(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        for i in range(20):
            (src / f"f{i}.txt").write_text(f"content {i}")
        dest = tmp_path / "dest"
        dest.mkdir()
        cancel = threading.Event()
        cancel.set()

        items = [str(src / f"f{i}.txt") for i in range(20)]
        outcome = FileActionService.transfer_items(
            items, str(dest), "move", dry_run=False, cancel_token=cancel
        )

        assert outcome.cancelled
        assert len(outcome.records) == 20
        assert len(outcome.skipped_records) == 20

    def test_cancel_delete_accounts_all_items(self, tmp_path):
        for i in range(20):
            (tmp_path / f"f{i}.txt").write_text(f"content {i}")
        cancel = threading.Event()
        cancel.set()

        items = [str(tmp_path / f"f{i}.txt") for i in range(20)]
        outcome = FileActionService.delete_items(
            items, dry_run=False, safe_mode=False, cancel_token=cancel
        )

        assert outcome.cancelled
        assert len(outcome.records) == 20
        assert len(outcome.skipped_records) == 20


class TestProgressCallback:
    def test_progress_called_with_atomic_counter(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        for i in range(10):
            (src / f"f{i}.txt").write_text(f"content {i}")
        dest = tmp_path / "dest"
        dest.mkdir()

        progress_calls: list[tuple[int, int, str]] = []
        lock = threading.Lock()

        def on_progress(current, total, msg):
            with lock:
                progress_calls.append((current, total, msg))

        items = [str(src / f"f{i}.txt") for i in range(10)]
        FileActionService.transfer_items(
            items, str(dest), "move", dry_run=False, progress_callback=on_progress
        )

        assert len(progress_calls) == 10
        totals = {t for _, t, _ in progress_calls}
        assert totals == {10}
        currents = sorted(c for c, _, _ in progress_calls)
        assert currents == list(range(1, 11))


class TestBatchWorkers:
    def test_get_batch_workers_returns_positive(self):
        workers = _get_batch_workers()
        assert workers >= 1
        assert workers <= 16

    def test_threadpool_used_for_execute(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        for i in range(10):
            (src / f"f{i}.txt").write_text(f"content {i}")
        dest = tmp_path / "dest"
        dest.mkdir()

        thread_ids: list[int] = []
        lock = threading.Lock()

        import dataforge.core.services.file_actions as fa_mod
        import dataforge.core.operations.files as ops_mod

        _orig_ops = ops_mod.transfer_path
        _orig_fa = fa_mod.transfer_path

        def _tracking(source_path, destination_dir, action, dry_run=True, reserved_paths=None):
            with lock:
                thread_ids.append(threading.get_ident())
            return _orig_ops(source_path, destination_dir, action, dry_run=dry_run, reserved_paths=reserved_paths)

        ops_mod.transfer_path = _tracking
        fa_mod.transfer_path = _tracking
        try:
            items = [str(src / f"f{i}.txt") for i in range(10)]
            FileActionService.transfer_items(items, str(dest), "move", dry_run=False)
        finally:
            ops_mod.transfer_path = _orig_ops
            fa_mod.transfer_path = _orig_fa

        assert len(thread_ids) == 10
        main_id = threading.get_ident()
        worker_ids = [t for t in thread_ids if t != main_id]
        assert len(worker_ids) >= 1


class TestOutcomeShape:
    def test_outcome_has_successes_failures_requested(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        for i in range(5):
            (src / f"f{i}.txt").write_text(f"content {i}")
        dest = tmp_path / "dest"
        dest.mkdir()

        items = [str(src / f"f{i}.txt") for i in range(5)]
        outcome = FileActionService.transfer_items(items, str(dest), "move", dry_run=False)

        assert isinstance(outcome, BatchActionOutcome)
        assert outcome.action == "move"
        assert outcome.requested == 5
        assert len(outcome.successes) == 5
        assert len(outcome.failures) == 0
        assert len(outcome.skipped_records) == 0
        assert not outcome.cancelled
        for record in outcome.records:
            assert isinstance(record, BatchActionRecord)
            assert record.source_path
            assert record.message
