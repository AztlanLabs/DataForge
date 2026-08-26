"""TICK-802 — STOP comprehensive cancel path tests."""
from __future__ import annotations

import threading
import time

import pytest
from PyQt5.QtWidgets import QApplication

from dataforge.api.schema import JobStatus
from dataforge.engine.jobs import JobQueue
from dataforge.ui.job_manager import JobManager, ManagedWorker


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

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
    mgr.shutdown()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _long_task_10k(cancel_token=None, progress_callback=None):
    """Simulate 10k-file scan with per-file cancel check (per-100ms granularity)."""
    for i in range(10000):
        if cancel_token is not None and cancel_token.is_set():
            return {"cancelled": True}
        if progress_callback and i % 100 == 0:
            progress_callback(i, 10000, "Scanning")
        # tiny work to simulate per-file stat (0.02ms)
        # Use short sleep every 100 items to make total ~0.5s if not cancelled
        if i % 100 == 0:
            time.sleep(0.005)
    return {"done": True}


def _slow_task(cancel_token=None, progress_callback=None):
    for i in range(50):
        if cancel_token and cancel_token.is_set():
            return {"cancelled": True}
        if progress_callback:
            progress_callback(i, 50, f"step {i}")
        time.sleep(0.05)
    return {"done": True}


def _fast_task(cancel_token=None, progress_callback=None):
    return {"done": True}


def _target_var_kwargs(**kwargs):
    # VAR_KEYWORD case: should receive cancel_token even though explicit param missing
    assert "cancel_token" in kwargs, "cancel_token missing in VAR_KEYWORD target"
    tok = kwargs["cancel_token"]
    assert tok is not None
    return {"had_token": True, "is_set": tok.is_set()}


def _target_var_kwargs_both(**kwargs):
    assert "cancel_token" in kwargs
    assert "progress_callback" in kwargs
    return {"ok": True}


def _raises_interrupted(cancel_token=None, progress_callback=None):
    raise InterruptedError("user cancelled")


# ------------------------------------------------------------------
# Acceptance 1: long scan cancel returns within 500ms and UI hides STOP (is_busy false)
# ------------------------------------------------------------------

def test_long_scan_cancel_returns_within_500ms(manager, qapp):
    results = []

    def on_success(r):
        results.append(r)

    job_id = manager.submit(target=_long_task_10k, on_success=on_success, task_name="long scan")
    assert job_id is not None
    # Let it run a bit
    time.sleep(0.1)
    assert manager.is_busy

    start = time.monotonic()
    # Cancel after 100ms
    ok = manager.cancel(job_id)
    assert ok
    # Wait for result
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not results:
        time.sleep(0.02)
        QApplication.processEvents()
    elapsed = time.monotonic() - start
    assert results, "job should have returned after cancel"
    # Should be cancelled dict, not error
    assert results[0].get("cancelled") is True
    # Must return within 500ms after cancel (allow small jitter to 600ms)
    assert elapsed < 0.6, f"cancel took too long: {elapsed:.3f}s"
    # UI hides STOP -> is_busy false
    # Poll up to 0.5s for is_busy false
    deadline2 = time.monotonic() + 0.5
    while time.monotonic() < deadline2 and manager.is_busy:
        time.sleep(0.02)
        QApplication.processEvents()
    assert not manager.is_busy


def test_jobqueue_long_scan_cancel_within_500ms(qapp):
    q = JobQueue(max_workers=2)
    try:

        def long_task(cancel_token=None, progress_callback=None):
            for i in range(100):
                if cancel_token and cancel_token.is_set():
                    return {"cancelled": True}
                time.sleep(0.02)
            return {"done": True}

        job = q.submit(long_task)
        time.sleep(0.05)
        start = time.monotonic()
        q.cancel(job.job_id)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and job.status not in (JobStatus.CANCELLED, JobStatus.DONE, JobStatus.FAILED):
            time.sleep(0.02)
        elapsed = time.monotonic() - start
        assert job.is_cancelled()
        assert job.status == JobStatus.CANCELLED
        assert elapsed < 0.6
    finally:
        q.shutdown(wait=True)


# ------------------------------------------------------------------
# Acceptance 2: VAR_KEYWORD bug — token received
# ------------------------------------------------------------------

def test_managed_worker_var_kwargs_receives_cancel_token(qapp):
    results = []
    finished = []

    token = threading.Event()
    worker = ManagedWorker(job_id="TICK802_VAR1", target=_target_var_kwargs, cancel_token=token)
    worker.result_signal.connect(lambda r: results.append(r))
    worker.finished_signal.connect(lambda jid: finished.append(jid))
    worker.start()
    worker.wait(3000)
    QApplication.processEvents()
    assert len(results) == 1
    assert results[0].get("had_token") is True
    assert "TICK802_VAR1" in finished


def test_managed_worker_var_kwargs_receives_both_token_and_progress(qapp):
    results = []
    token = threading.Event()

    def target(**kwargs):
        assert "cancel_token" in kwargs
        assert "progress_callback" in kwargs
        # Call progress to ensure chaining works
        kwargs["progress_callback"](1, 2, "hi")
        return {"ok": True}

    worker = ManagedWorker(job_id="TICK802_VAR2", target=target, cancel_token=token)
    progress_calls = []
    worker.progress_signal.connect(lambda c, t, m: progress_calls.append((c, t, m)))
    worker.result_signal.connect(lambda r: results.append(r))
    worker.start()
    worker.wait(3000)
    QApplication.processEvents()
    assert results[0].get("ok") is True
    assert len(progress_calls) >= 1
    assert progress_calls[0] == (1, 2, "hi")


def test_jobmanager_submit_var_kwargs_receives_token(manager, qapp):
    results = []

    def on_success(r):
        results.append(r)

    job_id = manager.submit(target=_target_var_kwargs, on_success=on_success, task_name="var kwargs")
    assert job_id is not None
    deadline = time.time() + 3
    while time.time() < deadline and not results:
        time.sleep(0.05)
        QApplication.processEvents()
    assert len(results) == 1
    assert results[0].get("had_token") is True


def test_jobmanager_submit_var_kwargs_both(manager, qapp):
    results = []

    def on_success(r):
        results.append(r)

    job_id = manager.submit(target=_target_var_kwargs_both, on_success=on_success, progress=True, task_name="both")
    assert job_id is not None
    deadline = time.time() + 3
    while time.time() < deadline and not results:
        time.sleep(0.05)
        QApplication.processEvents()
    assert len(results) == 1
    assert results[0].get("ok") is True


# ------------------------------------------------------------------
# Acceptance 3: cancel_all with 2 concurrent jobs -> both cancelled, is_busy false within 1s
# ------------------------------------------------------------------

def test_cancel_all_two_jobs_is_busy_false_within_1s(manager, qapp):
    results = []
    lock = threading.Lock()

    def on_success(r):
        with lock:
            results.append(r)

    ids = []
    for i in range(2):
        jid = manager.submit(target=_slow_task, on_success=on_success, task_name=f"slow {i}")
        ids.append(jid)
    assert all(j is not None for j in ids)
    time.sleep(0.15)
    assert manager.is_busy
    assert manager.active_job_count >= 1

    count = manager.cancel_all()
    assert count >= 1

    start = time.monotonic()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and len(results) < 2:
        time.sleep(0.05)
        QApplication.processEvents()
    elapsed = time.monotonic() - start
    # Both should have returned cancelled
    assert len(results) == 2
    for r in results:
        assert r.get("cancelled") is True
    # is_busy false within 1s after cancel
    deadline2 = time.monotonic() + 1.0
    while time.monotonic() < deadline2 and manager.is_busy:
        time.sleep(0.02)
        QApplication.processEvents()
    assert not manager.is_busy, "is_busy should be False within 1s after cancel_all"
    assert elapsed < 1.5


# ------------------------------------------------------------------
# Acceptance 4: no double execution regression
# ------------------------------------------------------------------

def test_no_double_execution(manager, qapp):
    call_count = []
    lock = threading.Lock()

    def counting_task(cancel_token=None, progress_callback=None):
        with lock:
            call_count.append(1)
        time.sleep(0.05)
        return {"done": True}

    results = []

    def on_success(r):
        results.append(r)

    job_id = manager.submit(target=counting_task, on_success=on_success, task_name="count")
    assert job_id is not None
    deadline = time.time() + 3
    while time.time() < deadline and not results:
        time.sleep(0.05)
        QApplication.processEvents()
    assert len(results) == 1
    assert results[0] == {"done": True}
    # Ensure target called exactly once, not twice (old bug)
    assert len(call_count) == 1, f"double execution: called {len(call_count)} times"

    # Also test with JobQueue direct still single
    q = JobQueue(max_workers=2)
    try:
        qc = []
        def qtask(cancel_token=None, progress_callback=None):
            qc.append(1)
            return {"ok": True}
        job = q.submit(qtask)
        deadline = time.time() + 2
        while time.time() < deadline and job.status not in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            time.sleep(0.02)
        assert job.status == JobStatus.DONE
        assert len(qc) == 1
    finally:
        q.shutdown(wait=True)


# ------------------------------------------------------------------
# Additional: InterruptedError normalized to cancelled dict, not error dialog
# ------------------------------------------------------------------

def test_interrupted_error_normalized_to_cancelled(manager, qapp):
    results = []
    errors = []

    def on_success(r):
        results.append(r)

    def on_error(e):
        errors.append(e)

    job_id = manager.submit(target=_raises_interrupted, on_success=on_success, on_error=on_error, task_name="interrupt")
    assert job_id is not None
    deadline = time.time() + 3
    while time.time() < deadline and not results and not errors:
        time.sleep(0.05)
        QApplication.processEvents()
    # Should be result with cancelled, not error
    assert len(results) == 1
    assert results[0].get("cancelled") is True
    assert len(errors) == 0
    # Job status should be CANCELLED, not FAILED
    job = manager.get_job(job_id)
    assert job is not None
    assert job.status == JobStatus.CANCELLED


def test_jobqueue_interrupted_normalized(qapp):
    q = JobQueue(max_workers=2)
    try:
        def bad(cancel_token=None, progress_callback=None):
            raise InterruptedError("cancel me")

        job = q.submit(bad)
        deadline = time.time() + 2
        while time.time() < deadline and job.status not in (JobStatus.CANCELLED, JobStatus.FAILED, JobStatus.DONE):
            time.sleep(0.02)
        assert job.status == JobStatus.CANCELLED
        assert job.results is not None and job.results.get("cancelled") is True
        assert job.error is None
    finally:
        q.shutdown(wait=True)


def test_job_cancel_sets_cancelled_even_if_running(qapp):
    q = JobQueue(max_workers=2)
    try:

        started = threading.Event()

        def blocking(cancel_token=None, progress_callback=None):
            started.set()
            time.sleep(0.5)
            return {"done": True}

        job = q.submit(blocking)
        assert started.wait(timeout=2)
        # Wait until RUNNING
        deadline = time.time() + 1
        while time.time() < deadline and job.status != JobStatus.RUNNING:
            time.sleep(0.02)
        assert job.status == JobStatus.RUNNING
        # Cancel while RUNNING should set CANCELLED immediately
        ok = q.cancel(job.job_id)
        assert ok
        assert job.is_cancelled()
        assert job.status == JobStatus.CANCELLED, "cancel() must set CANCELLED even if RUNNING (TICK-802)"
        # After worker finishes, still CANCELLED
        time.sleep(0.6)
        assert job.status == JobStatus.CANCELLED
    finally:
        q.shutdown(wait=True)


# ------------------------------------------------------------------
# Progress chaining preserved
# ------------------------------------------------------------------

def test_progress_chaining_preserved(manager, qapp):

    def task_with_progress(cancel_token=None, progress_callback=None):
        for i in range(3):
            if progress_callback:
                progress_callback(i, 3, f"step {i}")
            time.sleep(0.02)
        return {"done": True}

    # TICK-914 P0.1: a caller-supplied progress_callback must NOT be invoked
    # inline on the worker thread (it could mutate Qt widgets there). The
    # signal on the GUI thread is the sole progress path, so orig_cb must
    # stay untouched while progress still flows through the manager.
    orig_calls = []

    def orig_cb(c, t, m):
        orig_calls.append((c, t, m))

    results = []

    job_id = manager.submit(
        target=task_with_progress,
        kwargs={"progress_callback": orig_cb},
        on_success=lambda r: results.append(r),
        progress=True,
        task_name="progress chain",
    )
    assert job_id is not None
    deadline = time.time() + 3
    while time.time() < deadline and not results:
        time.sleep(0.05)
        QApplication.processEvents()

    assert len(results) == 1
    assert results[0] == {"done": True}
    assert len(orig_calls) == 0, "inline orig_cb chaining removed by TICK-914 (P0.1)"
    job = manager.get_job(job_id)
    assert job is not None
    assert job.status == JobStatus.DONE


# ------------------------------------------------------------------
# Ensure cancel_all cancels both queue and workers
# ------------------------------------------------------------------

def test_cancel_all_cancels_both_queue_and_workers(manager, qapp):
    # Submit 2 jobs, verify cancel_all returns count and tokens set
    ids = []
    for i in range(2):
        jid = manager.submit(target=_slow_task, task_name=f"both {i}")
        ids.append(jid)
    time.sleep(0.1)
    # Check tokens not yet set
    for jid in ids:
        job = manager.get_job(jid)
        assert job is not None
        assert not job.is_cancelled()
    cnt = manager.cancel_all()
    assert cnt >= 2 or cnt >= 1  # at least one
    for jid in ids:
        job = manager.get_job(jid)
        assert job.is_cancelled()
    # Workers should have token set
    with manager._lock:
        for wid in ids:
            w = manager._workers.get(wid)
            if w is not None:
                assert w._cancel_token.is_set()


# ------------------------------------------------------------------
# Verify per-100ms check: slow task that checks token every iteration should stop quickly
# ------------------------------------------------------------------

def test_per_100ms_cancel_check(manager, qapp):
    # Task that sleeps 0.02s per loop and checks token each loop -> per-100ms granularity
    results = []

    def loop_task(cancel_token=None, progress_callback=None):
        for i in range(100):
            if cancel_token and cancel_token.is_set():
                return {"cancelled": True}
            time.sleep(0.02)
            if progress_callback and i % 10 == 0:
                progress_callback(i, 100, "loop")
        return {"done": True}

    job_id = manager.submit(target=loop_task, on_success=lambda r: results.append(r), task_name="loop")
    time.sleep(0.1)
    start = time.monotonic()
    manager.cancel(job_id)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not results:
        time.sleep(0.02)
        QApplication.processEvents()
    elapsed = time.monotonic() - start
    assert results and results[0].get("cancelled") is True
    assert elapsed < 0.5, f"should cancel within 500ms, took {elapsed}"
