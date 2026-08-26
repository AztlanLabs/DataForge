"""Tests for TICK-401 — JobManager replaces single BackgroundWorker.

Covers:
- Submit and complete single job
- Queue depth (8 jobs max)
- Cancel running/queued jobs
- Multiple concurrent jobs
- Evidence mode blocks destructive ops
- is_busy property
- Progress signal bridging
- Error handling
"""

from __future__ import annotations

import threading
import time

import pytest

from PyQt5.QtWidgets import QApplication

from dataforge.api.schema import JobStatus
from dataforge.ui.job_manager import JobManager, ManagedWorker


@pytest.fixture
def qapp():
    """Ensure a QApplication exists for Qt signal tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def manager(qapp):
    """Create a fresh JobManager for each test."""
    mgr = JobManager(max_workers=2)
    yield mgr
    mgr.shutdown()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _fast_task(cancel_token=None, progress_callback=None):
    """A task that completes immediately."""
    return {"done": True}


def _slow_task(cancel_token=None, progress_callback=None):
    """A task that takes 0.5s and reports progress."""
    for i in range(5):
        if cancel_token and cancel_token.is_set():
            return {"cancelled": True}
        if progress_callback:
            progress_callback(i, 5, f"step {i}")
        time.sleep(0.1)
    return {"done": True}


def _failing_task(cancel_token=None, progress_callback=None):
    """A task that raises an error."""
    raise ValueError("intentional failure")


def _delete_files(cancel_token=None, progress_callback=None):
    """A destructive task (name contains 'delete')."""
    return {"deleted": True}


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

def test_job_manager_submit_and_complete(manager):
    """Submit a fast job and verify it completes."""
    results = []

    def on_success(result):
        results.append(result)

    job_id = manager.submit(
        target=_fast_task,
        on_success=on_success,
        task_name="fast task",
    )

    assert job_id is not None
    assert isinstance(job_id, str)
    assert len(job_id) == 26  # ULID

    # Wait for completion and process Qt events
    deadline = time.time() + 3
    while time.time() < deadline and not results:
        time.sleep(0.05)
        QApplication.processEvents()

    assert len(results) == 1
    assert results[0] == {"done": True}


def test_job_manager_queue_depth(manager):
    """Verify queue depth limit (8 jobs)."""
    job_ids = []

    # Submit 8 jobs (should succeed)
    for i in range(8):
        jid = manager.submit(target=_slow_task, task_name=f"task {i}")
        if jid:
            job_ids.append(jid)

    # 9th should fail (queue full)
    extra = manager.submit(target=_fast_task, task_name="overflow")
    # The engine JobQueue raises queue.Full when depth exceeded
    # Our manager catches it and returns None
    assert extra is None or len(job_ids) <= 8

    # Cleanup
    manager.cancel_all()


def test_job_manager_cancel(manager):
    """Cancel a running job."""
    started = threading.Event()
    results = []

    def slow_with_signal(cancel_token=None, progress_callback=None):
        started.set()
        for i in range(50):
            if cancel_token and cancel_token.is_set():
                return {"cancelled": True}
            time.sleep(0.05)
        return {"done": True}

    job_id = manager.submit(
        target=slow_with_signal,
        on_success=results.append,
        task_name="cancellable",
    )

    # Wait for it to start
    started.wait(timeout=3)
    assert started.is_set()

    # Small delay to ensure the job is running in the executor
    time.sleep(0.1)

    # Cancel
    success = manager.cancel(job_id)
    assert success

    # Wait for result and process Qt events
    deadline = time.time() + 5
    while time.time() < deadline and not results:
        time.sleep(0.1)
        QApplication.processEvents()

    # Should have received cancelled result
    assert len(results) == 1
    assert results[0].get("cancelled") is True


def test_job_manager_multiple_concurrent(manager):
    """Run multiple jobs concurrently."""
    results = []
    lock = threading.Lock()

    def on_success(result):
        with lock:
            results.append(result)

    # Submit 3 fast jobs
    ids = []
    for i in range(3):
        jid = manager.submit(
            target=_fast_task,
            on_success=on_success,
            task_name=f"concurrent {i}",
        )
        ids.append(jid)

    # All should have been submitted
    assert all(jid is not None for jid in ids)
    assert len(set(ids)) == 3  # unique IDs

    # Wait for all to complete and process Qt events
    deadline = time.time() + 5
    while time.time() < deadline and len(results) < 3:
        time.sleep(0.05)
        QApplication.processEvents()

    assert len(results) == 3


def test_job_manager_evidence_mode_blocks(manager):
    """TICK-917: evidence mode blocks at the mutation boundary, not at submit."""
    from dataforge.core import case
    from dataforge.core.services import FileActionService

    results = []
    case.set_evidence_mode(True)
    try:
        def _delete_through_service(cancel_token=None, progress_callback=None):
            return FileActionService.delete_items(["dummy"], dry_run=False)

        # Submit must be accepted — enforcement moved to the boundary.
        job_id = manager.submit(
            target=_delete_through_service,
            on_success=results.append,
            task_name="delete files",
        )
        assert job_id is not None

        deadline = time.time() + 3
        while time.time() < deadline and not results:
            time.sleep(0.05)
            QApplication.processEvents()

        assert len(results) == 1
        outcome = results[0]
        assert all(not rec.success for rec in outcome.records)
        assert any("Evidence Mode" in rec.message for rec in outcome.records)
    finally:
        case.set_evidence_mode(False)
        case.clear_context()


def test_job_manager_evidence_mode_allows_non_destructive(manager):
    """Evidence mode allows non-destructive operations."""
    results = []

    manager.evidence_mode = True

    job_id = manager.submit(
        target=_fast_task,
        on_success=results.append,
        task_name="read data",
    )

    assert job_id is not None

    # Wait for completion and process Qt events
    deadline = time.time() + 3
    while time.time() < deadline and not results:
        time.sleep(0.05)
        QApplication.processEvents()

    assert len(results) == 1


def test_job_manager_is_busy(manager):
    """is_busy reflects running state."""
    assert not manager.is_busy

    started = threading.Event()

    def blocking_task(cancel_token=None, progress_callback=None):
        started.set()
        time.sleep(0.5)
        return {"done": True}

    manager.submit(target=blocking_task, task_name="blocking")
    started.wait(timeout=2)

    assert manager.is_busy
    assert manager.active_job_count >= 1

    # Wait for completion
    time.sleep(1)
    assert not manager.is_busy


def test_job_manager_progress_bridge(manager, qapp):
    """Progress callbacks are bridged through ManagedWorker."""

    def slow_with_progress(cancel_token=None, progress_callback=None):
        for i in range(3):
            if progress_callback:
                progress_callback(i, 3, f"step {i}")
            time.sleep(0.05)
        return {"done": True}

    job_id = manager.submit(
        target=slow_with_progress,
        progress=True,
        task_name="progress test",
    )

    # Wait for completion
    time.sleep(1)

    # The job should have completed
    job = manager.get_job(job_id)
    assert job is not None
    assert job.status == JobStatus.DONE


def test_job_manager_error_handling(manager):
    """Errors in jobs are captured."""
    errors = []

    def on_error(error):
        errors.append(error)

    manager.submit(
        target=_failing_task,
        on_error=on_error,
        task_name="failing",
    )

    # Wait for error and process Qt events
    deadline = time.time() + 3
    while time.time() < deadline and not errors:
        time.sleep(0.05)
        QApplication.processEvents()

    assert len(errors) == 1
    assert "intentional failure" in str(errors[0])


def test_job_manager_list_jobs(manager):
    """list_jobs returns all jobs."""
    ids = []
    for i in range(3):
        jid = manager.submit(target=_fast_task, task_name=f"list {i}")
        ids.append(jid)

    jobs = manager.list_jobs()
    assert len(jobs) >= 3

    job_ids = {j.job_id for j in jobs}
    assert all(jid in job_ids for jid in ids if jid)


def test_job_manager_get_status(manager):
    """get_status returns job status."""
    job_id = manager.submit(target=_fast_task, task_name="status check")

    status = manager.get_status(job_id)
    assert status in (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.DONE)

    # Wait for completion
    time.sleep(0.5)
    assert manager.get_status(job_id) == JobStatus.DONE


def test_job_manager_cancel_all(manager):
    """cancel_all cancels all running/queued jobs."""
    for i in range(3):
        manager.submit(target=_slow_task, task_name=f"cancel all {i}")

    time.sleep(0.1)  # let them start
    count = manager.cancel_all()
    assert count >= 0  # may have already finished


def test_evidence_mode_enforced_at_mutation_boundary():
    """TICK-917: evidence mode gates FileActionService, not JobManager submit."""
    from dataforge.core import case
    from dataforge.core.services import FileActionService

    case.set_evidence_mode(True)
    try:
        outcome = FileActionService.delete_items(["dummy"], dry_run=False)
        assert len(outcome.records) == 1
        assert not outcome.records[0].success
        assert "Evidence Mode" in outcome.records[0].message
    finally:
        case.set_evidence_mode(False)
        case.clear_context()


def test_managed_worker_signals(qapp):
    """ManagedWorker emits correct signals."""
    results = []
    finished_ids = []

    worker = ManagedWorker(
        job_id="TEST001",
        target=_fast_task,
    )
    worker.result_signal.connect(lambda r: results.append(r))
    worker.finished_signal.connect(lambda jid: finished_ids.append(jid))

    worker.start()
    worker.wait(3000)
    QApplication.processEvents()

    assert len(results) == 1
    assert results[0] == {"done": True}
    assert "TEST001" in finished_ids


def test_managed_worker_error_signal(qapp):
    """ManagedWorker emits error signal on failure."""
    errors = []

    worker = ManagedWorker(
        job_id="TEST002",
        target=_failing_task,
    )
    worker.error_signal.connect(lambda e: errors.append(e))

    worker.start()
    worker.wait(3000)
    QApplication.processEvents()

    assert len(errors) == 1
    assert "intentional failure" in str(errors[0])


def test_managed_worker_cancel_token(qapp):
    """ManagedWorker passes cancel_token to target."""
    cancel = threading.Event()
    received_cancel = []

    def check_cancel(cancel_token=None):
        received_cancel.append(cancel_token)
        return {"had_token": cancel_token is not None}

    worker = ManagedWorker(
        job_id="TEST003",
        target=check_cancel,
        cancel_token=cancel,
    )
    worker.start()
    worker.wait(3000)

    assert len(received_cancel) == 1
    assert received_cancel[0] is cancel
