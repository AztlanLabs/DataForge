"""Contract tests for TICK-915 — job engine stability.

Covers:
- max_workers enforcement (P0.4)
- cancelled queued jobs never invoke their target (P0.5)
- cancelled running jobs stop gracefully
- exactly one terminal status event per job (P0.10)
- TypeError targets run exactly once (no retry loop) (P1.20)
- shutdown terminalizes pending jobs and clears futures (P1.20)
- progress sentinel: negative total becomes None (P0.9)
- deterministic status transitions (P0.10)
"""

from __future__ import annotations

import threading
import time

from dataforge.api.schema import JobStatus
from dataforge.engine.jobs import JobQueue


def _poll_status(job, *terminal, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline and job.status not in terminal:
        time.sleep(0.01)


def _status_sequence(job):
    return [e.status for e in job.events if e.type == "status"]


# ------------------------------------------------------------------
# max_workers enforcement (P0.4)
# ------------------------------------------------------------------

def test_max_workers_limits_concurrency():
    q = JobQueue(max_workers=1)
    try:
        lock = threading.Lock()
        active = 0
        peak = 0

        def worker(cancel_token=None, progress_callback=None):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.1)
            with lock:
                active -= 1
            return {"ok": True}

        jobs = [q.submit(worker) for _ in range(5)]
        for job in jobs:
            _poll_status(job, JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)
        assert peak <= 1, f"max_workers=1 violated: peak concurrency {peak}"
        assert all(j.status == JobStatus.DONE for j in jobs)
    finally:
        q.shutdown(wait=True, cancel_futures=True)


def test_max_workers_zero_clamped_to_one():
    q = JobQueue(max_workers=0)
    try:
        assert q.max_workers == 1
        assert q._executor._max_workers == 1  # type: ignore[attr-defined]
    finally:
        q.shutdown(wait=True)


# ------------------------------------------------------------------
# cancellation guard (P0.5)
# ------------------------------------------------------------------

def test_cancelled_queued_job_never_invokes_target():
    q = JobQueue(max_workers=1)
    try:
        started = threading.Event()
        release = threading.Event()
        calls = []

        def blocker(cancel_token=None, progress_callback=None):
            started.set()
            release.wait(timeout=5)
            return {"blocked": True}

        def target(cancel_token=None, progress_callback=None):
            calls.append(1)
            return {"ran": True}

        q.submit(blocker)
        assert started.wait(timeout=2)
        job = q.submit(target)
        # Still queued (blocker holds the only worker)
        time.sleep(0.1)
        assert job.status == JobStatus.QUEUED
        assert q.cancel(job.job_id) is True
        release.set()
        _poll_status(job, JobStatus.CANCELLED, JobStatus.DONE, JobStatus.FAILED)
        assert job.status == JobStatus.CANCELLED
        assert calls == [], "cancelled queued job must never invoke its target"
    finally:
        q.shutdown(wait=True, cancel_futures=True)


def test_cancelled_running_job_stops_gracefully():
    q = JobQueue(max_workers=2)
    try:
        started = threading.Event()

        def slow(cancel_token=None, progress_callback=None):
            started.set()
            for _ in range(1000):
                if cancel_token and cancel_token.is_set():
                    return {"cancelled": True}
                time.sleep(0.01)
            return {"done": True}

        job = q.submit(slow)
        assert started.wait(timeout=2)
        assert q.cancel(job.job_id) is True
        _poll_status(job, JobStatus.CANCELLED)
        assert job.status == JobStatus.CANCELLED
        deadline = time.time() + 5
        while time.time() < deadline and job.results is None:
            time.sleep(0.01)
        assert job.results is not None and job.results.get("cancelled") is True
    finally:
        q.shutdown(wait=True, cancel_futures=True)


# ------------------------------------------------------------------
# single terminal event (P0.10)
# ------------------------------------------------------------------

def test_exactly_one_terminal_event_per_job():
    q = JobQueue(max_workers=2)
    try:
        def fn(cancel_token=None, progress_callback=None):
            return {"ok": True}

        job = q.submit(fn)
        _poll_status(job, JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)
        assert job.status == JobStatus.DONE
        terminal = [
            e for e in job.events
            if e.type == "status"
            and e.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)
        ]
        assert len(terminal) == 1, f"expected exactly 1 terminal event, got {len(terminal)}"
        assert terminal[0].status == JobStatus.DONE
    finally:
        q.shutdown(wait=True, cancel_futures=True)


def test_cancel_with_progress_interleaving_single_terminal_event():
    q = JobQueue(max_workers=2)
    try:
        started = threading.Event()

        def slow(cancel_token=None, progress_callback=None):
            started.set()
            for i in range(1000):
                if cancel_token and cancel_token.is_set():
                    return {"cancelled": True}
                if progress_callback:
                    progress_callback(i, -1, "step")
                time.sleep(0.01)
            return {"done": True}

        job = q.submit(slow)
        assert started.wait(timeout=2)
        time.sleep(0.05)
        assert q.cancel(job.job_id) is True
        _poll_status(job, JobStatus.CANCELLED)
        deadline = time.time() + 5
        while time.time() < deadline and job.results is None:
            time.sleep(0.01)
        cancelled = [
            e for e in job.events
            if e.type == "status" and e.status == JobStatus.CANCELLED
        ]
        assert len(cancelled) == 1, f"expected exactly 1 CANCELLED event, got {len(cancelled)}"
    finally:
        q.shutdown(wait=True, cancel_futures=True)


# ------------------------------------------------------------------
# TypeError retry removed (P1.20)
# ------------------------------------------------------------------

def test_typeerror_retry_does_not_re_execute():
    q = JobQueue(max_workers=2)
    try:
        counter = []

        def target(x):
            counter.append(1)
            raise TypeError("boom")

        job = q.submit(target, params={"x": 1})
        _poll_status(job, JobStatus.FAILED, JobStatus.DONE, JobStatus.CANCELLED)
        assert job.status == JobStatus.FAILED
        assert len(counter) == 1, f"target invoked {len(counter)} times (expected 1)"
    finally:
        q.shutdown(wait=True, cancel_futures=True)


def test_positional_only_params_invoked_once():
    q = JobQueue(max_workers=2)
    try:
        received = []

        def target(x, /):
            received.append(x)
            return {"ok": x}

        job = q.submit(target, params={"x": 42})
        _poll_status(job, JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)
        assert job.status == JobStatus.DONE, f"job failed: {job.error}"
        assert received == [{"x": 42}]
    finally:
        q.shutdown(wait=True, cancel_futures=True)


# ------------------------------------------------------------------
# shutdown (P1.20)
# ------------------------------------------------------------------

def test_shutdown_transitions_pending_to_cancelled():
    q = JobQueue(max_workers=1)
    try:
        def slow(cancel_token=None, progress_callback=None):
            while cancel_token is not None and not cancel_token.is_set():
                time.sleep(0.01)
            return {"cancelled": True}

        jobs = [q.submit(slow) for _ in range(3)]
        time.sleep(0.1)
        q.shutdown(wait=True, cancel_futures=True)
        for j in jobs:
            assert j.status == JobStatus.CANCELLED, f"job {j.job_id} left {j.status}"
    finally:
        q.shutdown(wait=True, cancel_futures=True)


def test_shutdown_clears_futures():
    q = JobQueue(max_workers=2)
    try:
        def fn(cancel_token=None, progress_callback=None):
            return {"ok": True}

        jobs = [q.submit(fn) for _ in range(3)]
        for j in jobs:
            _poll_status(j, JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)
        assert len(q._futures) == 3
        q.shutdown(wait=True, cancel_futures=True)
        assert q._futures == {}, "shutdown must release future references"
    finally:
        q.shutdown(wait=True, cancel_futures=True)


# ------------------------------------------------------------------
# progress sentinel (P0.9)
# ------------------------------------------------------------------

def test_progress_negative_total_becomes_none():
    q = JobQueue(max_workers=2)
    try:
        def fn(cancel_token=None, progress_callback=None):
            if progress_callback:
                progress_callback(5, -1, "scanning")
            return {"ok": True}

        job = q.submit(fn)
        _poll_status(job, JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)
        assert job.status == JobStatus.DONE, f"job failed: {job.error}"
        progress = [e for e in job.events if e.type == "progress"]
        assert progress, "expected at least one progress event"
        assert any(e.total is None for e in progress), "negative total must normalize to None"
        assert all(e.total is None or e.total >= 0 for e in progress)
    finally:
        q.shutdown(wait=True, cancel_futures=True)


def test_progress_zero_total_preserved():
    q = JobQueue(max_workers=2)
    try:
        def fn(cancel_token=None, progress_callback=None):
            if progress_callback:
                progress_callback(0, 0, "start")
            return {"ok": True}

        job = q.submit(fn)
        _poll_status(job, JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)
        assert job.status == JobStatus.DONE, f"job failed: {job.error}"
        progress = [e for e in job.events if e.type == "progress"]
        assert progress and all(e.total == 0 for e in progress)
    finally:
        q.shutdown(wait=True, cancel_futures=True)


# ------------------------------------------------------------------
# deterministic transitions (P0.10)
# ------------------------------------------------------------------

def test_job_status_transitions_are_deterministic():
    q = JobQueue(max_workers=1)
    try:
        def ok(cancel_token=None, progress_callback=None):
            return {"ok": True}

        def boom(cancel_token=None, progress_callback=None):
            raise ValueError("boom")

        def slow(cancel_token=None, progress_callback=None):
            for _ in range(1000):
                if cancel_token and cancel_token.is_set():
                    return {"cancelled": True}
                time.sleep(0.01)
            return {"ok": True}

        # Complete
        done_job = q.submit(ok)
        _poll_status(done_job, JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)
        assert _status_sequence(done_job) == [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.DONE]

        # Fail
        failed_job = q.submit(boom)
        _poll_status(failed_job, JobStatus.FAILED, JobStatus.DONE, JobStatus.CANCELLED)
        assert _status_sequence(failed_job) == [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.FAILED]

        # Cancel before start (blocker holds the only worker)
        started = threading.Event()
        release = threading.Event()

        def blocker(cancel_token=None, progress_callback=None):
            started.set()
            release.wait(timeout=5)
            return {}

        q.submit(blocker)
        assert started.wait(timeout=2)
        pre_cancel = q.submit(slow)
        time.sleep(0.05)
        assert pre_cancel.status == JobStatus.QUEUED
        assert q.cancel(pre_cancel.job_id) is True
        release.set()
        _poll_status(pre_cancel, JobStatus.CANCELLED, JobStatus.DONE, JobStatus.FAILED)
        assert _status_sequence(pre_cancel) == [JobStatus.QUEUED, JobStatus.CANCELLED]

        # Cancel while running
        started2 = threading.Event()
        release2 = threading.Event()

        def blocker2(cancel_token=None, progress_callback=None):
            started2.set()
            release2.wait(timeout=5)
            return {}

        running = q.submit(blocker2)
        assert started2.wait(timeout=2)
        assert running.status == JobStatus.RUNNING
        assert q.cancel(running.job_id) is True
        release2.set()
        _poll_status(running, JobStatus.CANCELLED, JobStatus.DONE, JobStatus.FAILED)
        assert _status_sequence(running) == [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLED]

        # No duplicate consecutive statuses anywhere
        for job in (done_job, failed_job, pre_cancel, running):
            seq = _status_sequence(job)
            assert len(seq) == len(set(seq)), f"duplicate status events in {seq}"
    finally:
        q.shutdown(wait=True, cancel_futures=True)