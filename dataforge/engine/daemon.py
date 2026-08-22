"""Engine daemon stub — TICK-005 contract.

This is the Wave-0 stub.  Importing this module has **no side effects**
(no server start, no thread, no socket).  The real daemon loop
(``asyncio`` + ``ThreadPool``/``ProcessPool`` + transports) is TICK-301
and will overwrite this file in Wave 3 (sequential re-entry per
``docs/PARALLEL_BACKLOG.md``).

The stub exists so ``from dataforge.engine.daemon import Daemon`` and
``import dataforge.engine.daemon`` succeed in Wave 0 and tests can
assert the import is side-effect free.

See ``docs/proposals/NATIVE_OS_API_REVIEW.md §3`` and
``dataforge/engine/jobs.py``.
"""

from __future__ import annotations

from typing import Optional

from .jobs import JobQueue

__all__ = ["Daemon", "EngineDaemon", "get_daemon"]


class Daemon:
    """Minimal daemon stub wrapping a :class:`JobQueue`."""

    def __init__(self, queue_depth: int = 8, max_workers: int = 4) -> None:
        self.queue = JobQueue(max_workers=max_workers, queue_depth=queue_depth)
        self._running: bool = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False
        try:
            self.queue.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    def is_running(self) -> bool:
        return self._running

    @property
    def running(self) -> bool:
        return self._running

    def submit(self, *args, **kwargs):
        return self.queue.submit(*args, **kwargs)

    def get(self, job_id: str):
        return self.queue.get(job_id)

    def cancel(self, job_id: str) -> bool:
        return self.queue.cancel(job_id)


EngineDaemon = Daemon

_daemon: Optional[Daemon] = None


def get_daemon() -> Daemon:
    global _daemon
    if _daemon is None:
        _daemon = Daemon()
    return _daemon
