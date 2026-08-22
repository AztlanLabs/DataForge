"""Contract tests for TICK-005 — Job model and JobQueue stub."""

from __future__ import annotations

import json
import queue
import re
import threading
import time

import pytest

from dataforge.api.schema import JobStatus
from dataforge.engine.daemon import Daemon
from dataforge.engine.jobs import Job, JobQueue, QUEUE_DEPTH, generate_ulid


def test_job_ulid_and_json_safe():
    job = Job(provider="local", params={"root": "/tmp"})
    # ULID-like: 26 chars, Crockford base32
    assert isinstance(job.job_id, str)
    assert re.match(r"^[0-9A-Z]{26}$", job.job_id), job.job_id
    # JSON-safe
    d = job.to_dict()
    json.dumps(d)
    # second job has different id
    job2 = Job()
    assert job.job_id != job2.job_id
    assert re.match(r"^[0-9A-Z]{26}$", job2.job_id)


def test_generate_ulid_json_safe():
    ulid = generate_ulid()
    assert re.match(r"^[0-9A-Z]{26}$", ulid)
    json.dumps({"job_id": ulid})


def test_job_fields():
    tok = threading.Event()

    def cb(c, t, m):
        return None

    job = Job(provider="local", params={"root": "/tmp"}, cancel_token=tok, progress_callback=cb, results=None)
    assert job.provider == "local"
    assert job.params == {"root": "/tmp"}
    assert job.cancel_token is tok
    assert job.progress_callback is cb
    assert hasattr(job, "results")
    assert hasattr(job, "events")
    assert hasattr(job, "status")


def test_is_cancelled():
    job = Job()
    assert not job.is_cancelled()
    job.cancel_token.set()
    assert job.is_cancelled()
    # via cancel()
    job2 = Job()
    assert not job2.is_cancelled()
    job2.cancel()
    assert job2.is_cancelled()


def test_queue_status_transitions_done():
    q = JobQueue(max_workers=2)

    def fn(cancel_token=None, progress_callback=None):
        time.sleep(0.05)
        return {"done": True}

    job = q.submit(fn, params={"root": "/tmp"})
    # initial is queued or running (race)
    assert job.status in (JobStatus.QUEUED, JobStatus.RUNNING)
    # poll until done
    deadline = time.time() + 2
    while time.time() < deadline and job.status not in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
        time.sleep(0.02)
    assert job.status == JobStatus.DONE
    assert job.results == {"done": True}
    assert job.finished_at is not None
    q.shutdown(wait=True)


def test_queue_status_cancelled():
    q = JobQueue(max_workers=2)

    def slow(cancel_token=None, progress_callback=None):
        # check token
        for _ in range(10):
            if cancel_token and cancel_token.is_set():
                return {"cancelled": True}
            time.sleep(0.05)
        return {"done": True}

    job = q.submit(slow)
    time.sleep(0.05)
    job.cancel_token.set()
    deadline = time.time() + 2
    while time.time() < deadline and job.status not in (JobStatus.CANCELLED, JobStatus.DONE, JobStatus.FAILED):
        time.sleep(0.02)
    assert job.is_cancelled()
    assert job.status in (JobStatus.CANCELLED, JobStatus.DONE, JobStatus.FAILED)
    q.shutdown(wait=True)


def test_queue_status_failed():
    q = JobQueue()

    def bad():
        raise ValueError("boom")

    job = q.submit(bad)
    deadline = time.time() + 2
    while time.time() < deadline and job.status not in (JobStatus.FAILED, JobStatus.DONE):
        time.sleep(0.02)
    assert job.status == JobStatus.FAILED
    assert "boom" in (job.error or "")
    q.shutdown(wait=True)


def test_progress_callback_event_stream():
    q = JobQueue()

    def fn(cancel_token=None, progress_callback=None):
        for i in range(3):
            if progress_callback:
                progress_callback(i, 3, f"step {i}")
            time.sleep(0.02)
        return {"ok": True}

    captured = []

    def my_cb(c, t, m):
        captured.append((c, t, m))

    job = q.submit(fn, progress_callback=my_cb)
    deadline = time.time() + 2
    while time.time() < deadline and job.status != JobStatus.DONE:
        time.sleep(0.02)
    assert job.status == JobStatus.DONE
    # events should contain progress
    progress_events = [e for e in job.events if e.type == "progress"]
    assert len(progress_events) >= 3
    assert len(captured) >= 3
    # also via subscribe
    evts = list(q.subscribe(job.job_id))
    assert len(evts) >= 3
    q.shutdown(wait=True)


def test_queue_depth_enforced():
    q = JobQueue(max_workers=1, queue_depth=2)
    block = threading.Event()

    def blocker(cancel_token=None, progress_callback=None):
        block.wait(timeout=3)
        return {}

    # Fill queue: one running, up to 2 queued = 3 total? But queue_depth is queued count
    # With max_workers=1, first job runs, next 2 are queued, 4th should raise Full
    q.submit(blocker)
    # wait for first to be running
    time.sleep(0.05)
    q.submit(blocker)
    q.submit(blocker)
    # next should be full
    with pytest.raises(queue.Full):
        q.submit(blocker)
    assert q.queue_depth == 2
    assert QUEUE_DEPTH == 8
    # Also check class constants
    assert JobQueue.QUEUE_DEPTH == 8
    block.set()
    time.sleep(0.2)
    q.shutdown(wait=True)


def test_job_serialized_json_safe():
    job = Job(provider="local", params={"root": "/tmp", "recursive": True})
    d = job.to_dict()
    # must be JSON dumpsable
    s = json.dumps(d)
    loaded = json.loads(s)
    assert loaded["job_id"] == job.job_id
    assert re.match(r"^[0-9A-Z]{26}$", loaded["job_id"])
    assert loaded["provider"] == "local"


def test_daemon_import_no_side_effect():
    # Import should not start server
    import dataforge.engine.daemon as daemon_mod

    d = daemon_mod.Daemon()
    assert not d.is_running()
    assert not d.running
    d.start()
    assert d.is_running()
    d.stop()
    assert not d.is_running()
    # get_daemon lazy
    from dataforge.engine.daemon import get_daemon

    g = get_daemon()
    assert isinstance(g, Daemon)


def test_job_queue_get_and_cancel():
    q = JobQueue()

    def fn(cancel_token=None, progress_callback=None):
        time.sleep(0.5)
        return {}

    job = q.submit(fn)
    # get
    fetched = q.get(job.job_id)
    assert fetched is job
    assert q.get_status(job.job_id) in (JobStatus.QUEUED, JobStatus.RUNNING)
    # cancel via queue
    ok = q.cancel(job.job_id)
    assert ok
    assert job.is_cancelled()
    time.sleep(0.2)
    q.shutdown(wait=True)


def test_append_only_hook_exists():
    q = JobQueue()
    assert hasattr(q, "_append_job_record")
    job = Job()
    # should be callable and not raise
    q._append_job_record(job)
