"""TICK-911 — Global app stability audit + job lifecycle hardening.

Covers the acceptance criteria:

1. GIVEN 20 concurrent jobs (scan + hash + junk + dup) submitted via
   JobManager WHEN running with cancel bursts THEN no double execution
   (each target call count == 1), is_busy eventually False within 3s,
   no dangling QThreads.
2. GIVEN progress_callback called ~1000 times per second via several
   workers WHEN throttled THEN app.update_progress called at most ~10x/sec
   (100ms coalesce) and per-worker signal emission is bounded.
3. GIVEN JobQueue depth 8 WHEN submitting a 9th job while 8 are queued
   THEN it is rejected with a queue-full error and the existing jobs are
   not lost.
4. GIVEN evidence_mode true WHEN EnhancedTreeview-style rename/delete
   closures wrapping FileActionService are submitted THEN blocked with
   PermissionError (no JobManager bypass).
5. GIVEN daemon import WHEN imported THEN no server starts (side-effect
   free) and per-job cancel tokens work.
Plus engine invariants: ULID uniqueness under a 20-burst submit, cancel
while QUEUED -> CANCELLED without RUNNING, synchronous status update on
cancel, and shutdown waits for workers.
"""

from __future__ import annotations

import importlib
import queue
import threading
import time

import pytest

from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication

from dataforge.api.schema import JobStatus
from dataforge.engine import daemon as daemon_module
from dataforge.engine.daemon import Daemon
from dataforge.engine.jobs import QUEUE_DEPTH, Job, JobQueue, QueueFullError, generate_ulid
from dataforge.ui.job_manager import JobManager

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def qapp():
    """Ensure a QApplication exists for Qt signal tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def manager(qapp):
    """Fresh JobManager; teardown must not hang."""
    mgr = JobManager(max_workers=2)
    yield mgr
    mgr.shutdown()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _blocking_task(block: threading.Event, cancel_token=None, progress_callback=None):
    """Run until released or cancelled; never finishes on its own."""
    while not block.wait(0.05):
        if cancel_token is not None and cancel_token.is_set():
            return {"cancelled": True}
    return {"done": True}


def _make_flood_task(n: int = 1000):
    """Return a task that fires *n* progress callbacks as fast as possible."""

    def _flood(cancel_token=None, progress_callback=None):
        for i in range(n):
            if cancel_token is not None and cancel_token.is_set():
                if progress_callback:
                    progress_callback(i, n, "flood")
                return {"cancelled": True}
            if progress_callback:
                progress_callback(i, n, f"flood {i}")
        if progress_callback:
            progress_callback(n, n, "done")  # final callback, mirrors real targets
        return {"done": True}

    return _flood


def _wait_until(predicate, timeout: float = 3.0, interval: float = 0.02) -> bool:
    """Poll *predicate* (processing Qt events) until True or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
        QApplication.processEvents()
    return predicate()


class _FakeApp(QObject):
    """Minimal QObject stand-in for DataForgeApp.update_progress."""

    def __init__(self) -> None:
        super().__init__()
        self.updates = 0
        self.last = None

    def update_progress(self, current: int, total: int, step_name: str = "") -> None:
        self.updates += 1
        self.last = (current, total, step_name)


# ------------------------------------------------------------------
# Engine invariants (jobs.py)
# ------------------------------------------------------------------


def test_ulid_unique_burst_submit_20():
    """GIVEN a 20-job burst WHEN submitted THEN all ULIDs are unique, 26-char."""
    q = JobQueue(max_workers=2, queue_depth=32)
    try:
        ids = set()
        for _ in range(20):
            # registry-only burst (the JobManager path): no depth interference
            job = q.submit(lambda: {"ok": True}, params={}, execute=False)
            assert len(job.job_id) == 26
            ids.add(job.job_id)
        assert len(ids) == 20
        assert len(q) == 20
    finally:
        q.shutdown(wait=True, cancel_futures=True)


def test_queue_depth_9th_rejected_not_lost():
    """GIVEN depth 8 with 8 queued WHEN 9th submitted THEN QueueFullError and no loss."""
    assert QUEUE_DEPTH == 8, "default queue depth invariant"
    q = JobQueue(max_workers=1, queue_depth=8)
    block = threading.Event()
    try:
        first = q.submit(lambda: _blocking_task(block), params={}, execute=True)
        time.sleep(0.1)
        accepted = [first]
        for _ in range(8):
            accepted.append(q.submit(lambda: _blocking_task(block), params={}, execute=True))
        with pytest.raises(queue.Full):
            q.submit(lambda: _blocking_task(block), params={}, execute=True)
        # Existing jobs are not lost
        assert len(q.list_jobs()) == 9
        assert all(q.get(j.job_id) is not None for j in accepted)
    finally:
        block.set()
        q.shutdown(wait=True, cancel_futures=True)


def test_cancel_queued_job_never_running():
    """GIVEN a QUEUED job WHEN cancelled THEN CANCELLED without ever RUNNING."""
    q = JobQueue(max_workers=1, queue_depth=8)
    block = threading.Event()
    try:
        q.submit(lambda: _blocking_task(block), params={}, execute=True)
        time.sleep(0.1)  # first job is RUNNING
        queued = [q.submit(lambda: _blocking_task(block), params={}, execute=True) for _ in range(3)]
        victim = queued[1]
        assert victim.status == JobStatus.QUEUED
        assert q.cancel(victim.job_id) is True
        assert victim.status == JobStatus.CANCELLED
        time.sleep(0.3)
        assert victim.status == JobStatus.CANCELLED
        assert victim.started_at is None
        statuses = [e.status for e in victim.events]
        assert JobStatus.RUNNING not in statuses
        assert statuses[-1] == JobStatus.CANCELLED
    finally:
        block.set()
        q.shutdown(wait=True, cancel_futures=True)


def test_submit_rejects_non_bool_execute():
    """GIVEN execute=None WHEN submitted THEN TypeError (no silent registry mode)."""
    q = JobQueue(max_workers=1)
    try:
        with pytest.raises(TypeError):
            q.submit(lambda: None, params={}, execute=None)  # type: ignore[arg-type]
    finally:
        q.shutdown(wait=True)


def test_submit_accepts_caller_cancel_token():
    """GIVEN a caller-owned cancel_token WHEN submitted THEN the Job uses it."""
    q = JobQueue(max_workers=1)
    token = threading.Event()
    try:
        job = q.submit(lambda: None, params={}, execute=False, cancel_token=token)
        assert job.cancel_token is token
        q.cancel(job.job_id)
        assert token.is_set()
    finally:
        q.shutdown(wait=True)


# ------------------------------------------------------------------
# JobManager stability (job_manager.py)
# ------------------------------------------------------------------


def test_job_manager_burst_20_no_double_execution(qapp):
    """20 mixed jobs + cancel bursts: each target runs exactly once, no QThread leak."""
    counter: dict = {}
    counter_lock = threading.Lock()

    def make_target(name: str):
        def _target(cancel_token=None, progress_callback=None):
            with counter_lock:
                counter[name] = counter.get(name, 0) + 1
            for _ in range(5):
                if cancel_token is not None and cancel_token.is_set():
                    return {"cancelled": True}
                time.sleep(0.01)
            return {"done": name}

        _target.__name__ = f"{name}_worker"
        return _target

    targets = {
        "scan": make_target("scan"),
        "hash": make_target("hash"),
        "junk": make_target("junk"),
        "dup": make_target("dup"),
    }
    names = ["scan", "hash", "junk", "dup"] * 5  # 20 jobs

    mgr = JobManager(max_workers=4, queue_depth=32)
    try:
        ids = []
        for name in names:
            jid = mgr.submit(target=targets[name], task_name=name)
            assert jid is not None, f"job {name} rejected — queue full"
            ids.append(jid)

        # Cancel bursts mid-flight (some may already be terminal — cancel is best-effort)
        for jid in ids[:8]:
            mgr.cancel(jid)

        assert _wait_until(lambda: not mgr.is_busy, timeout=3.0), "is_busy must clear within 3s"

        # No double execution: each target ran exactly once per job
        total_calls = sum(counter.values())
        assert total_calls == 20, f"expected 20 target calls, got {total_calls}"

        # No dangling QThreads after all finished_signal events drain
        assert _wait_until(lambda: len(mgr._workers) == 0, timeout=3.0)
        for job in mgr.list_jobs():
            assert job.status in (JobStatus.DONE, JobStatus.CANCELLED)
    finally:
        mgr.shutdown()


def test_job_manager_cancel_sets_status_synchronously(manager):
    """GIVEN a running job WHEN cancel THEN Job.status is CANCELLED synchronously."""
    started = threading.Event()

    def _slow(cancel_token=None, progress_callback=None):
        started.set()
        while not cancel_token.wait(0.05):
            pass
        return {"cancelled": True}

    job_id = manager.submit(target=_slow, task_name="sync cancel")
    assert started.wait(timeout=3)
    time.sleep(0.05)
    assert manager.cancel(job_id) is True
    # Synchronous: no event-loop processing required for the status flip
    assert manager.get_status(job_id) == JobStatus.CANCELLED
    assert _wait_until(lambda: not manager.is_busy, timeout=3.0)


def test_progress_flood_throttled_globally(qapp):
    """1000 cps across 4 workers: app.update_progress coalesced to ~10x/sec."""
    fake = _FakeApp()
    mgr = JobManager(parent=fake, max_workers=4, queue_depth=16)
    try:
        flood = _make_flood_task(1000)
        t0 = time.time()
        for _ in range(4):
            assert mgr.submit(target=flood, progress=True, task_name="flood") is not None

        assert _wait_until(lambda: not mgr.is_busy, timeout=5.0)
        elapsed = time.time() - t0
        # Allow queued signals to drain
        for _ in range(20):
            QApplication.processEvents()

        assert fake.updates >= 1, "at least one progress event must reach the app"
        # 100ms global coalesce: ~10/sec max + per-worker finals + boundary slack
        assert fake.updates <= int(elapsed * 10) + 6, (
            f"update_progress called {fake.updates}x over {elapsed:.2f}s — not throttled"
        )
    finally:
        mgr.shutdown()


def test_progress_signal_throttled_per_worker(qapp):
    """A single worker firing 1000 callbacks emits ~10x/sec Qt signals."""
    mgr = JobManager(max_workers=2, queue_depth=16)
    try:
        flood = _make_flood_task(1000)
        signals = []
        t0 = time.time()
        job_id = mgr.submit(target=flood, progress=True, task_name="flood 1")
        assert job_id is not None
        worker = mgr._workers[job_id]
        worker.progress_signal.connect(lambda c, t, m: signals.append((c, t, m)))

        assert _wait_until(lambda: not mgr.is_busy, timeout=5.0)
        elapsed = time.time() - t0
        for _ in range(20):
            QApplication.processEvents()

        assert len(signals) >= 1
        assert len(signals) <= int(elapsed * 10) + 6, (
            f"progress_signal emitted {len(signals)}x over {elapsed:.2f}s — not throttled"
        )
        assert signals[-1][0] == signals[-1][1], "final progress (c==t) must be delivered"
    finally:
        mgr.shutdown()


def test_progress_callback_chain_preserved(qapp):
    """Caller's own progress_callback still fires for every event (TICK-802 contract)."""
    mgr = JobManager(max_workers=2)
    try:
        seen = []

        def orig_cb(current, total, step_name=""):
            seen.append((current, total, step_name))

        def _reporting(cancel_token=None, progress_callback=None):
            for i in range(3):
                if progress_callback:
                    progress_callback(i, 3, f"step {i}")
                time.sleep(0.05)
            return {"done": True}

        mgr.submit(
            target=_reporting,
            kwargs={"progress_callback": orig_cb},
            task_name="chain",
        )
        assert _wait_until(lambda: len(seen) >= 3, timeout=3.0)
        assert len(seen) == 3
    finally:
        mgr.shutdown()


def test_job_manager_queue_full_error_callback(qapp):
    """GIVEN 8 queued jobs WHEN 9th submitted THEN 'Too many jobs' error, none lost."""
    mgr = JobManager(max_workers=1)
    errors = []
    try:
        # Pre-populate the registry with 8 QUEUED jobs (deterministic: QThreads
        # start too fast to hold a queued state in a live-submit race).
        for _ in range(8):
            mgr._queue.submit(lambda: {"ok": True}, params={}, execute=False)
        assert mgr.queued_job_count == 8

        extra = mgr.submit(
            target=lambda: {"ok": True},
            on_error=lambda e: errors.append(e),
            task_name="overflow",
        )
        assert extra is None
        assert len(errors) == 1
        assert "Too many jobs" in str(errors[0])
        # None of the earlier jobs were lost
        assert len(mgr.list_jobs()) >= 8
    finally:
        mgr.cancel_all()
        mgr.shutdown()


def test_evidence_mode_blocks_treeview_style_closures(manager):
    """GIVEN evidence_mode WHEN EnhancedTreeview-style delete/rename closures THEN PermissionError."""
    from dataforge.core.services import FileActionService  # noqa: F401  (never invoked)

    def make_closure(kind: str):
        if kind == "delete":
            def _do_delete():
                return FileActionService.delete_items(["dummy"], dry_run=False)
            return _do_delete
        if kind == "rename":
            def _do_rename():
                return FileActionService.rename_items(["dummy"], lambda p, i: "new", dry_run=False)
            return _do_rename
        if kind == "copy":
            def _do_copy():
                return FileActionService.transfer_items(["dummy"], "/tmp", "copy", dry_run=False)
            return _do_copy
        raise AssertionError(kind)

    manager.evidence_mode = True
    errors = []
    for kind in ("delete", "rename"):
        errors.clear()
        jid = manager.submit(
            target=make_closure(kind),
            on_error=lambda e: errors.append(e),
            task_name=f"{kind} file",
        )
        assert jid is None, f"{kind} closure must be blocked in evidence mode"
        assert len(errors) == 1
        assert isinstance(errors[0], PermissionError)
        assert "EVIDENCE MODE" in str(errors[0])

    # Non-destructive closure (copy) still allowed
    jid = manager.submit(target=make_closure("copy"), task_name="copy file")
    assert jid is not None
    assert _wait_until(lambda: not manager.is_busy, timeout=3.0)

    # Keyword detection sees through nested qualnames (EnhancedTreeview pattern)
    assert JobManager._is_destructive(make_closure("delete"))
    assert JobManager._is_destructive(make_closure("rename"))
    assert not JobManager._is_destructive(make_closure("copy"))


def test_shutdown_waits_for_workers_and_is_idempotent(qapp):
    """GIVEN a running job WHEN shutdown THEN workers drain and double-shutdown is safe."""
    mgr = JobManager(max_workers=2)
    started = threading.Event()

    def _slow(cancel_token=None, progress_callback=None):
        started.set()
        while not cancel_token.wait(0.05):
            pass
        return {"cancelled": True}

    job_id = mgr.submit(target=_slow, task_name="drain")
    assert started.wait(timeout=3)
    time.sleep(0.1)

    mgr.shutdown()
    assert not mgr.is_busy
    assert len(mgr._workers) == 0
    assert mgr.get_status(job_id) == JobStatus.CANCELLED
    mgr.shutdown()  # idempotent


# ------------------------------------------------------------------
# Daemon invariants (daemon.py)
# ------------------------------------------------------------------


def test_daemon_import_is_side_effect_free():
    """GIVEN daemon module import WHEN reloaded THEN no threads spawn, no daemon starts.

    Restores the pre-reload bindings afterwards so tests that hold ``from
    dataforge.engine.daemon import Daemon`` references keep working.
    """
    names = ("Daemon", "EngineDaemon", "get_daemon", "_daemon")
    saved = {name: getattr(daemon_module, name) for name in names}
    try:
        before = {t.name for t in threading.enumerate()}
        mod = importlib.reload(daemon_module)
        after = {t.name for t in threading.enumerate()}
        assert before == after, f"import spawned threads: {after - before}"
        assert mod._daemon is None, "import must not create the daemon singleton"
        # reload() rebinds fresh class objects; verify names + engine symbol identity
        assert mod.Daemon.__name__ == "Daemon"
        assert mod.EngineDaemon is mod.Daemon
        assert mod.Job is Job
        assert mod.JobQueue is JobQueue

        d = mod.Daemon()
        assert d.is_running() is False
        d.start()
        assert d.is_running() is True
        d.stop()
        assert d.is_running() is False
    finally:
        for name, value in saved.items():
            setattr(daemon_module, name, value)


def test_daemon_per_job_cancel_token():
    """GIVEN a caller token WHEN daemon.submit THEN the Job cancels through it."""
    daemon = Daemon()
    token = threading.Event()
    try:
        def _slow(cancel_token=None, progress_callback=None):
            while not cancel_token.wait(0.05):
                pass
            return {"cancelled": True}

        job = daemon.submit(_slow, cancel_token=token, execute=True)
        assert job.cancel_token is token
        time.sleep(0.1)
        assert daemon.cancel(job.job_id) is True
        assert token.is_set()
        deadline = time.time() + 3
        while time.time() < deadline and job.status != JobStatus.CANCELLED:
            time.sleep(0.02)
        assert job.status == JobStatus.CANCELLED
    finally:
        daemon.stop()


def test_daemon_queue_depth_uses_same_semantics():
    """GIVEN a daemon JobQueue depth 8 WHEN 9 queued THEN reject with QueueFullError."""
    daemon = Daemon()
    block = threading.Event()
    try:
        def _blocked(cancel_token=None, progress_callback=None):
            return _blocking_task(block, cancel_token, progress_callback)

        daemon.queue = JobQueue(max_workers=1, queue_depth=8)
        daemon.submit(_blocked, params={}, execute=True)
        time.sleep(0.1)
        for _ in range(8):
            daemon.submit(_blocked, params={}, execute=True)
        with pytest.raises(QueueFullError):
            daemon.submit(_blocked, params={}, execute=True)
    finally:
        block.set()
        daemon.stop()


def test_generate_ulid_export():
    """generate_ulid is part of the engine public API."""
    a = generate_ulid()
    b = generate_ulid()
    assert a != b
    assert len(a) == 26
    assert len(b) == 26