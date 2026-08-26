"""TICK-914 — Progress callback safety + QThread lifecycle + affinity contract.

Regression tests for the Wave 11 P0 crash fixes in ``JobManager``:

- P0.1: progress callbacks never mutate Qt widgets from the worker thread.
- P0.2: every callback entry point has an explicit GUI-thread affinity
  contract (``@pyqtSlot`` + ``Qt.QueuedConnection`` on JobManager).
- P0.3: worker cleanup happens on the native ``QThread.finished``, never
  while the thread is still running; ``shutdown()`` waits for workers.
- P0.4: noisy progress updates are coalesced to prevent repaint storms.
- P0.6: events delivered after a job reached a terminal state are discarded.

Validation: ``QT_QPA_PLATFORM=offscreen python -m pytest tests/test_job_lifecycle_safety.py -q``
"""

from __future__ import annotations

import threading
import time

import pytest

from PyQt5.QtCore import QObject, QThread
from PyQt5.QtWidgets import QApplication

from dataforge.ui.job_manager import JobManager


@pytest.fixture
def qapp():
    """Ensure a QApplication exists for Qt signal tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def gui_thread(qapp):
    return QApplication.instance().thread()


class ProgressRecorder(QObject):
    """Stands in for DataForgeApp.update_progress and records call context."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[int, int, str]] = []
        self.threads: list[QThread] = []

    def update_progress(self, current: int, total: int, step_name: str = "") -> None:
        self.calls.append((current, total, step_name))
        self.threads.append(QThread.currentThread())


def _pump_until(cond, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        QApplication.processEvents()
        time.sleep(0.02)
    QApplication.processEvents()
    return cond()


def _fast_job(cancel_token=None, progress_callback=None):
    return {"done": True}


# ------------------------------------------------------------------
# 1-3: callbacks must run on the GUI thread
# ------------------------------------------------------------------

def test_progress_callback_runs_on_gui_thread(qapp, gui_thread):
    """GIVEN a progress=True job THEN delivered progress runs on the GUI thread."""
    recorder = ProgressRecorder()
    mgr = JobManager(parent=recorder, max_workers=1)

    def job(cancel_token=None, progress_callback=None):
        for i in range(3):
            progress_callback(i, 3, f"step {i}")
            time.sleep(0.02)
        return {"done": True}

    try:
        jid = mgr.submit(target=job, progress=True)
        assert jid is not None
        assert _pump_until(lambda: len(recorder.threads) >= 1)
        assert len(recorder.calls) >= 1
        assert all(t is gui_thread for t in recorder.threads)
    finally:
        mgr.shutdown()


def test_result_callback_runs_on_gui_thread(qapp, gui_thread):
    """GIVEN a successful job THEN on_success runs on the GUI thread."""
    mgr = JobManager(max_workers=1)
    got: dict = {}

    def on_success(result):
        got["thread"] = QThread.currentThread()
        got["result"] = result

    try:
        jid = mgr.submit(target=_fast_job, on_success=on_success)
        assert jid is not None
        assert _pump_until(lambda: "thread" in got)
        assert got["thread"] is gui_thread
        assert got["result"] == {"done": True}
    finally:
        mgr.shutdown()


def test_error_callback_runs_on_gui_thread(qapp, gui_thread):
    """GIVEN a failing job THEN on_error runs on the GUI thread."""
    mgr = JobManager(max_workers=1)
    got: dict = {}

    def boom(cancel_token=None):
        raise ValueError("intentional TICK-914 failure")

    def on_error(error):
        got["thread"] = QThread.currentThread()
        got["error"] = error

    try:
        jid = mgr.submit(target=boom, on_error=on_error)
        assert jid is not None
        assert _pump_until(lambda: "thread" in got)
        assert got["thread"] is gui_thread
        assert "TICK-914" in str(got["error"])
    finally:
        mgr.shutdown()


# ------------------------------------------------------------------
# 4-5: exactly-once delivery, no duplicate progress per tick
# ------------------------------------------------------------------

def test_progress_called_exactly_once_per_event(qapp):
    """GIVEN a job emitting 5 progress events THEN update_progress is called 5x.

    Events are spaced >100ms so the coalescer does not drop them — this
    asserts one delivery per emitted event (no double delivery).
    """
    recorder = ProgressRecorder()
    mgr = JobManager(parent=recorder, max_workers=1)

    def job(cancel_token=None, progress_callback=None):
        for i in range(5):
            progress_callback(i, 5, f"step {i}")
            time.sleep(0.12)
        return {"done": True}

    try:
        jid = mgr.submit(target=job, progress=True)
        assert jid is not None
        assert _pump_until(lambda: len(recorder.calls) >= 5)
        time.sleep(0.15)
        QApplication.processEvents()
        assert len(recorder.calls) == 5
        assert recorder.calls[0] == (0, 5, "step 0")
        assert recorder.calls[-1] == (4, 5, "step 4")
    finally:
        mgr.shutdown()


def test_no_duplicate_progress_per_tick(qapp):
    """GIVEN a job with an emitted progress event THEN only one GUI delivery.

    The old code chained the caller's progress_callback AND emitted the
    signal (two deliveries per tick); the signal must now be the sole path.
    Events are spaced >100ms and processed while emitted, so the coalescer
    does not drop them — this asserts 1:1 signal emission → GUI delivery.
    """
    recorder = ProgressRecorder()
    mgr = JobManager(parent=recorder, max_workers=1)
    emitted = {"count": 0}

    def job(cancel_token=None, progress_callback=None):
        for i in range(4):
            emitted["count"] += 1
            progress_callback(i, 4, f"tick {i}")
            time.sleep(0.12)
        return {"done": True}

    try:
        jid = mgr.submit(target=job, progress=True)
        assert jid is not None
        assert _pump_until(lambda: len(recorder.calls) >= 4)
        time.sleep(0.15)
        QApplication.processEvents()
        assert len(recorder.calls) == emitted["count"] == 4
    finally:
        mgr.shutdown()


# ------------------------------------------------------------------
# 6-7: QThread lifecycle safety
# ------------------------------------------------------------------

def test_qthread_cleanup_after_native_finish(qapp, capsys):
    """GIVEN a completed job THEN no 'Destroyed while thread is still running'.

    Cleanup must be tied to the native QThread.finished (fires after run()
    returns), never to a signal emitted inside run().
    """
    mgr = JobManager(max_workers=1)
    try:
        jid = mgr.submit(target=_fast_job)
        assert jid is not None
        assert _pump_until(lambda: mgr.get_status(jid) is not None)
        for _ in range(20):
            QApplication.processEvents()
            time.sleep(0.01)
        assert _pump_until(lambda: mgr.get_status(jid).name != "RUNNING")
    finally:
        mgr.shutdown()
    for _ in range(20):
        QApplication.processEvents()
        time.sleep(0.01)
    err = capsys.readouterr().err
    assert "Destroyed while thread is still running" not in err
    assert "Recursive repaint" not in err


def test_shutdown_waits_for_active_workers(qapp):
    """GIVEN a running job WHEN shutdown() THEN it waits for the worker."""
    mgr = JobManager(max_workers=1)
    finished = threading.Event()

    def slow(cancel_token=None):
        time.sleep(0.4)
        finished.set()
        return {"done": True}

    try:
        jid = mgr.submit(target=slow)
        assert jid is not None
        time.sleep(0.1)
        start = time.monotonic()
        mgr.shutdown()
        elapsed = time.monotonic() - start
        assert finished.is_set(), "shutdown returned before the worker finished"
        assert elapsed >= 0.3
        assert not mgr.is_busy
    finally:
        mgr.shutdown()


# ------------------------------------------------------------------
# 8-9: reentrant submission + worker thread isolation
# ------------------------------------------------------------------

def test_completion_callback_submits_followup_job(qapp, gui_thread):
    """GIVEN on_success submits a second job THEN both complete on GUI thread."""
    mgr = JobManager(max_workers=2)
    threads: list[QThread] = []
    completed: list[dict] = []

    def first(cancel_token=None):
        return {"first": True}

    def second(cancel_token=None):
        return {"second": True}

    def on_success(result):
        threads.append(QThread.currentThread())
        if result.get("first"):
            jid2 = mgr.submit(target=second, on_success=on_success)
            assert jid2 is not None
        else:
            completed.append(result)

    try:
        jid = mgr.submit(target=first, on_success=on_success)
        assert jid is not None
        assert _pump_until(lambda: len(completed) == 1)
        assert len(threads) == 2
        assert all(t is gui_thread for t in threads)
        assert completed == [{"second": True}]
    finally:
        mgr.shutdown()


def test_worker_does_not_touch_widgets(qapp, gui_thread):
    """GIVEN a job target THEN it runs on a worker thread, never the GUI thread."""
    mgr = JobManager(max_workers=1)
    observed: dict = {}
    started = threading.Event()

    def job(cancel_token=None):
        observed["thread"] = QThread.currentThread()
        started.set()
        return {"done": True}

    try:
        jid = mgr.submit(target=job)
        assert jid is not None
        assert started.wait(5)
        assert observed["thread"] is not gui_thread
    finally:
        mgr.shutdown()


# ------------------------------------------------------------------
# 10: post-terminal events are discarded
# ------------------------------------------------------------------

def test_progress_after_terminal_is_discarded(qapp):
    """GIVEN a completed job WHEN _dispatch_progress fires late THEN no crash/delivery."""
    recorder = ProgressRecorder()
    mgr = JobManager(parent=recorder, max_workers=1)
    done = threading.Event()

    def job(cancel_token=None, progress_callback=None):
        progress_callback(1, 5, "first")
        done.set()
        return {"done": True}

    try:
        jid = mgr.submit(target=job, progress=True)
        assert jid is not None
        assert done.wait(5)
        # Wait for the queued progress event to be delivered (it was emitted
        # before the result event, but delivery is async on the GUI thread).
        assert _pump_until(lambda: len(recorder.calls) >= 1)
        assert _pump_until(lambda: mgr.get_status(jid).name in ("DONE", "CANCELLED"))
        before = len(recorder.calls)
        # Late event after terminal state — must be discarded without crashing.
        mgr._dispatch_progress(2, 5, "late")
        QApplication.processEvents()
        assert len(recorder.calls) == before
    finally:
        mgr.shutdown()


# ------------------------------------------------------------------
# Edge cases from the ticket
# ------------------------------------------------------------------

def test_progress_storm_is_coalesced(qapp):
    """GIVEN 1000 rapid progress events THEN deliveries are bounded (<100)."""
    recorder = ProgressRecorder()
    mgr = JobManager(parent=recorder, max_workers=1)

    def job(cancel_token=None, progress_callback=None):
        for i in range(1000):
            progress_callback(i, 1000, "flood")
        return {"done": True}

    try:
        jid = mgr.submit(target=job, progress=True)
        assert jid is not None
        assert _pump_until(lambda: mgr.get_status(jid).name in ("DONE", "CANCELLED"))
        time.sleep(0.2)
        QApplication.processEvents()
        assert len(recorder.calls) < 100
        assert recorder.calls[0] == (0, 1000, "flood")
    finally:
        mgr.shutdown()


def test_interrupted_error_is_cancellation_not_error(qapp):
    """GIVEN a job raising InterruptedError THEN no error callback fires."""
    mgr = JobManager(max_workers=1)
    got: dict = {}

    def job(cancel_token=None):
        raise InterruptedError("cancelled")

    def on_success(result):
        got["success"] = result

    def on_error(error):
        got["error"] = error

    try:
        jid = mgr.submit(target=job, on_success=on_success, on_error=on_error)
        assert jid is not None
        # Pump until the cancellation result is delivered on the GUI thread
        # (status flips to CANCELLED synchronously in the worker first).
        assert _pump_until(lambda: got.get("success") is not None or got.get("error") is not None)
        assert "error" not in got
        assert got.get("success", {}).get("cancelled") is True
    finally:
        mgr.shutdown()


def test_shutdown_with_zero_jobs_returns_immediately(qapp):
    """GIVEN no active jobs WHEN shutdown() THEN it returns immediately."""
    mgr = JobManager(max_workers=1)
    start = time.monotonic()
    mgr.shutdown()
    assert time.monotonic() - start < 1.0