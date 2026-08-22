"""UI Job Manager — replaces single BackgroundWorker with queued jobs.

Domain: UI / Shell
Spec: docs/proposals/PERFORMANCE_INVESTIGATION.md#1.11
Depends: dataforge.engine.jobs (TICK-005), dataforge.api.schema (TICK-003)

Design notes
------------
* ``JobManager`` wraps ``engine.jobs.JobQueue`` (depth 8, ThreadPoolExecutor)
  and bridges ``Job.events`` → Qt signals so multiple views can run
  concurrently without a global ``is_busy`` guard.
* Each submitted job gets its own ``cancel_token`` (``threading.Event``)
  and progress callback that emits through the manager's Qt signals.
* ``evidence_mode`` flag blocks destructive operations (delete, remove,
  strip, clean, move, rename, archive) when enabled.
* The public API mirrors ``DataForgeApp.run_background`` / ``run_workflow``
  so existing views need minimal changes — they call ``app.run_background``
  which now delegates to ``JobManager.submit``.
"""

from __future__ import annotations

import inspect
import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Protocol

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from dataforge.api.schema import JobStatus
from dataforge.engine.jobs import QUEUE_DEPTH, Job, JobQueue

logger = logging.getLogger(__name__)

__all__ = ["JobManager", "ManagedWorker"]

# Destructive operation keywords — checked against target function name
# when evidence_mode is enabled.
_DESTRUCTIVE_KEYWORDS = frozenset({
    "delete", "remove", "strip", "clean", "move", "rename",
    "archive", "trash", "purge", "wipe", "secure_delete",
})


class ProgressCallback(Protocol):
    def __call__(self, current: int, total: int, step_name: str = "") -> None: ...


class SuccessCallback(Protocol):
    def __call__(self, result: Any) -> None: ...


class ErrorCallback(Protocol):
    def __call__(self, error: Exception) -> None: ...


class ManagedWorker(QThread):
    """QThread that runs a single target function and emits Qt signals.

    Each ``ManagedWorker`` is paired with a ``Job`` from the engine
    ``JobQueue``.  The worker bridges the job's progress callback to
    Qt signals so the UI can update without polling.
    """

    progress_signal = pyqtSignal(int, int, str)
    status_signal = pyqtSignal(str)
    result_signal = pyqtSignal(object)
    error_signal = pyqtSignal(Exception)
    finished_signal = pyqtSignal(str)  # job_id

    def __init__(
        self,
        job_id: str,
        target: Callable[..., Any],
        args: tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        cancel_token: Optional[threading.Event] = None,
    ) -> None:
        super().__init__()
        self._job_id = job_id
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}
        self._cancel_token = cancel_token

    def run(self) -> None:
        try:
            sig = inspect.signature(self._target)
            kwargs_copy = dict(self._kwargs)

            if "cancel_token" in sig.parameters and self._cancel_token:
                kwargs_copy["cancel_token"] = self._cancel_token

            if "progress_callback" in sig.parameters:
                def progress_callback(current: int, total: int, step_name: str = "") -> None:
                    self.progress_signal.emit(current, total, step_name)
                kwargs_copy["progress_callback"] = progress_callback

            result = self._target(*self._args, **kwargs_copy)
            self.result_signal.emit(result)
        except Exception as e:
            self.error_signal.emit(e)
        finally:
            self.finished_signal.emit(self._job_id)


class JobManager(QObject):
    """Manages multiple concurrent background jobs with Qt signal bridging.

    Replaces the single ``BackgroundWorker`` + ``is_busy`` pattern in
    ``DataForgeApp``.  Jobs are queued (depth 8) and run via
    ``engine.jobs.JobQueue``; each job's progress is bridged to Qt
    signals through a ``ManagedWorker`` QThread.

    Usage::

        manager = JobManager(parent=app)
        job_id = manager.submit(
            target=some_function,
            args=(arg1,),
            kwargs={"key": "value"},
            on_success=handle_result,
            on_error=handle_error,
            progress=True,
            task_name="Scan files",
        )
        # Cancel later
        manager.cancel(job_id)
    """

    # Qt signals for aggregate status
    jobs_changed = pyqtSignal()  # emitted when job list changes

    def __init__(self, parent: Optional[QObject] = None, max_workers: int = 4) -> None:
        super().__init__(parent)
        self._queue = JobQueue(max_workers=max_workers, queue_depth=QUEUE_DEPTH)
        self._workers: Dict[str, ManagedWorker] = {}
        self._lock = threading.Lock()
        self._evidence_mode: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def evidence_mode(self) -> bool:
        """Whether evidence mode is active (blocks destructive ops)."""
        return self._evidence_mode

    @evidence_mode.setter
    def evidence_mode(self, value: bool) -> None:
        self._evidence_mode = bool(value)

    @property
    def is_busy(self) -> bool:
        """True if any job is currently RUNNING."""
        for job in self._queue.list_jobs():
            if job.status == JobStatus.RUNNING:
                return True
        return False

    @property
    def active_job_count(self) -> int:
        """Number of jobs currently RUNNING."""
        return sum(1 for j in self._queue.list_jobs() if j.status == JobStatus.RUNNING)

    @property
    def queued_job_count(self) -> int:
        """Number of jobs waiting to start."""
        return sum(1 for j in self._queue.list_jobs() if j.status == JobStatus.QUEUED)

    # ------------------------------------------------------------------
    # Submit / Cancel
    # ------------------------------------------------------------------

    def submit(
        self,
        target: Callable[..., Any],
        args: tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        on_success: Optional[SuccessCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        progress: bool = False,
        task_name: Optional[str] = None,
    ) -> Optional[str]:
        """Submit a background job.

        Returns the job_id, or None if rejected (evidence mode or queue full).
        """
        if kwargs is None:
            kwargs = {}

        # Evidence mode check
        if self._evidence_mode and self._is_destructive(target):
            logger.warning("Evidence mode: blocked destructive operation %s", target)
            if on_error:
                on_error(PermissionError("EVIDENCE MODE — writes blocked"))
            return None

        # Submit to engine JobQueue
        try:
            job = self._queue.submit(
                target,
                params=kwargs,
                progress_callback=None,  # we bridge via ManagedWorker
            )
        except Exception as e:
            logger.error("Failed to submit job: %s", e)
            if on_error:
                on_error(e)
            return None

        # Create ManagedWorker for Qt signal bridging
        worker = ManagedWorker(
            job_id=job.job_id,
            target=target,
            args=args,
            kwargs=kwargs,
            cancel_token=job.cancel_token,
        )

        # Connect signals
        if progress:
            worker.progress_signal.connect(
                lambda c, t, m: self._on_progress(job.job_id, c, t, m)
            )

        if on_success:
            worker.result_signal.connect(on_success)

        if on_error:
            worker.error_signal.connect(on_error)

        worker.finished_signal.connect(self._on_worker_finished)

        # Store and start
        with self._lock:
            self._workers[job.job_id] = worker

        worker.start()
        self.jobs_changed.emit()

        logger.info("Submitted job %s: %s", job.job_id, task_name or target.__name__)
        return job.job_id

    def cancel(self, job_id: str) -> bool:
        """Cancel a running or queued job.

        Returns True if the job was found and cancellation was requested.
        The job will finish naturally after its cancel token is set.
        """
        success = self._queue.cancel(job_id)
        if success:
            self.jobs_changed.emit()
        return success

    def cancel_all(self) -> int:
        """Cancel all running/queued jobs. Returns count cancelled."""
        count = 0
        for job in self._queue.list_jobs():
            if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                if self.cancel(job.job_id):
                    count += 1
        return count

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a Job by ID."""
        return self._queue.get(job_id)

    def list_jobs(self) -> List[Job]:
        """List all jobs (any status)."""
        return self._queue.list_jobs()

    def list_active_jobs(self) -> List[Job]:
        """List only RUNNING or QUEUED jobs."""
        return [
            j for j in self._queue.list_jobs()
            if j.status in (JobStatus.QUEUED, JobStatus.RUNNING)
        ]

    def get_status(self, job_id: str) -> Optional[JobStatus]:
        """Get the status of a specific job."""
        job = self._queue.get(job_id)
        return job.status if job else None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_progress(self, job_id: str, current: int, total: int, message: str) -> None:
        """Bridge progress from ManagedWorker to JobManager signal."""
        # The individual view connections handle their own progress;
        # this is for aggregate monitoring if needed.
        pass

    def _on_worker_finished(self, job_id: str) -> None:
        """Clean up when a ManagedWorker finishes."""
        with self._lock:
            worker = self._workers.pop(job_id, None)
        if worker:
            worker.deleteLater()
        self.jobs_changed.emit()

    @staticmethod
    def _is_destructive(target: Callable[..., Any]) -> bool:
        """Check if a target function is a destructive operation."""
        name = getattr(target, "__name__", "") or ""
        qualname = getattr(target, "__qualname__", "") or ""
        combined = f"{name} {qualname}".lower()
        return any(kw in combined for kw in _DESTRUCTIVE_KEYWORDS)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Cancel all jobs and shut down the executor."""
        self.cancel_all()
        self._queue.shutdown(wait=True, cancel_futures=True)
