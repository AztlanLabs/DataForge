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
* TICK-802 fix: Eliminate double execution. Previously JobManager called
  ``JobQueue.submit`` (which runs via ThreadPoolExecutor) *and* started a
  ``ManagedWorker`` QThread for the same target — the job ran twice.
  Now ``JobQueue`` is used as pure registry (``execute=False``) and
  ``ManagedWorker`` is the sole executor. ``JobQueue`` tracks Job metadata
  (status/events/cancel_token) while the QThread does the work. This fixes
  STOP latency, is_busy drift, and progress duplication. Documented as
  Option B (preferred) in TICK-802 prompt.
"""

from __future__ import annotations

import inspect
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Protocol

from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot

from dataforge.api.schema import JobEvent, JobStatus
from dataforge.engine.jobs import QUEUE_DEPTH, Job, JobQueue, QueueFullError

logger = logging.getLogger(__name__)

__all__ = ["JobManager", "ManagedWorker"]

# TICK-914 P0.4: minimum interval between delivered progress updates.
# Updates closer than this are coalesced away (except 0/total and
# total/total boundaries) to prevent QWidget repaint storms.
_PROGRESS_COALESCE_MS = 0.1  # seconds


def _is_app_progress_callback(cb: Any) -> bool:
    """True when *cb* is a UI-affine progress callback (a QObject-bound method).

    TICK-911: the app's ``post_progress`` mutates ``QProgressBar``/``QLabel``
    and must never be invoked inline from the worker thread (P0.1 SIGSEGV:
    ``QWidget::repaint: Recursive repaint detected``). When the worker sees it
    we skip the inline call — the queued ``progress_signal`` delivers the same
    event on the GUI thread via ``JobManager._dispatch_progress`` instead.

    TICK-914 merge: the guard is *any* QObject-bound method. Widgets are
    QObjects, so a bound method may mutate widgets no matter its name; only
    plain closures (no ``__self__``) are provably safe to chain inline from
    the worker thread.
    """
    self_obj = getattr(cb, "__self__", None)
    return self_obj is not None and isinstance(self_obj, QObject)


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
        job: Optional[Job] = None,
    ) -> None:
        super().__init__()
        self._job_id = job_id
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}
        self._cancel_token = cancel_token
        self._job = job

    def run(self) -> None:
        # TICK-802: ensure Job status is updated synchronously in worker thread
        # so is_busy/job.status checks don't require event-loop processing.
        if self._job is not None:
            try:
                if self._job.status == JobStatus.QUEUED and not self._job.is_cancelled():
                    self._job.status = JobStatus.RUNNING
                    self._job.started_at = time.time()
                    self._job.events.append(
                        JobEvent(
                            job_id=self._job.job_id,
                            type="status",
                            status=JobStatus.RUNNING,
                            message="running",
                        )
                    )
                elif self._job.is_cancelled() and self._job.status != JobStatus.CANCELLED:
                    self._job.status = JobStatus.CANCELLED
                    if self._job.finished_at is None:
                        self._job.finished_at = time.time()
            except Exception:
                pass
        try:
            sig = inspect.signature(self._target)
            params = sig.parameters
            has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
            kwargs_copy = dict(self._kwargs)

            if ("cancel_token" in params or has_var_kw) and self._cancel_token is not None:
                kwargs_copy["cancel_token"] = self._cancel_token

            if "progress_callback" in params or has_var_kw:
                # TICK-911 merge: caller-supplied progress callbacks are chained
                # inline UNLESS they are UI-affine (QObject-bound methods such as
                # DataForgeApp.post_progress). UI-affine callbacks must never run
                # inline from this worker thread (TICK-914 P0.1 SIGSEGV —
                # QWidget::repaint recursive repaint); the queued progress_signal
                # delivers them on the GUI thread instead. TICK-911 also coalesces
                # *signal* emission to 100ms so a 32-worker progress flood
                # (1000+ callbacks/sec) cannot emit more than ~10 signals/sec
                # (QBackingStore active painter). The final callback
                # (current == total) always passes the throttle.
                orig_cb = kwargs_copy.get("progress_callback")
                last_emit = [0.0]

                def progress_callback(current: int, total: int, step_name: str = "") -> None:
                    now = time.monotonic()
                    emit_signal = True
                    if total > 0 and current != total and now - last_emit[0] < 0.1:
                        emit_signal = False
                    else:
                        last_emit[0] = now
                    try:
                        if orig_cb is not None and not _is_app_progress_callback(orig_cb):
                            orig_cb(current, total, step_name)
                    except Exception:
                        pass
                    if emit_signal:
                        self.progress_signal.emit(current, total, step_name)

                kwargs_copy["progress_callback"] = progress_callback

            result = self._target(*self._args, **kwargs_copy)
            # TICK-802: normalize token-cancelled to dict so UI hides STOP
            if self._cancel_token is not None and self._cancel_token.is_set():
                if self._job is not None:
                    try:
                        self._job.status = JobStatus.CANCELLED
                        if isinstance(result, dict) and result.get("cancelled"):
                            self._job.results = result
                        elif isinstance(result, dict):
                            out = dict(result)
                            out["cancelled"] = True
                            self._job.results = out
                            result = out
                        else:
                            self._job.results = {"cancelled": True, "result": result}
                            result = self._job.results
                        if self._job.finished_at is None:
                            self._job.finished_at = time.time()
                        if not self._job.events or self._job.events[-1].status != JobStatus.CANCELLED:
                            self._job.events.append(
                                JobEvent(
                                    job_id=self._job.job_id,
                                    type="status",
                                    status=JobStatus.CANCELLED,
                                    message="cancelled",
                                )
                            )
                    except Exception:
                        pass
                if isinstance(result, dict) and result.get("cancelled"):
                    self.result_signal.emit(result)
                elif isinstance(result, dict):
                    out = dict(result)
                    out["cancelled"] = True
                    self.result_signal.emit(out)
                else:
                    self.result_signal.emit({"cancelled": True, "result": result})
                return
            if self._job is not None:
                try:
                    is_cancelled_result = isinstance(result, dict) and result.get("cancelled") is True
                    if is_cancelled_result:
                        self._job.status = JobStatus.CANCELLED
                        self._job.results = result
                        if self._job.finished_at is None:
                            self._job.finished_at = time.time()
                        if not self._job.events or self._job.events[-1].status != JobStatus.CANCELLED:
                            self._job.events.append(
                                JobEvent(
                                    job_id=self._job.job_id,
                                    type="status",
                                    status=JobStatus.CANCELLED,
                                    message="cancelled",
                                )
                            )
                    else:
                        self._job.status = JobStatus.DONE
                        self._job.results = result
                        self._job.finished_at = time.time()
                        self._job.events.append(
                            JobEvent(
                                job_id=self._job.job_id,
                                type="result",
                                status=JobStatus.DONE,
                                payload={"result": result} if isinstance(result, dict) else {"result": result},
                                message="done",
                            )
                        )
                except Exception:
                    pass
            self.result_signal.emit(result)
        except InterruptedError as e:
            if self._job is not None:
                try:
                    self._job.status = JobStatus.CANCELLED
                    self._job.results = {"cancelled": True, "message": str(e)}
                    self._job.error = None
                    if self._job.finished_at is None:
                        self._job.finished_at = time.time()
                    if not self._job.events or self._job.events[-1].status != JobStatus.CANCELLED:
                        self._job.events.append(
                            JobEvent(
                                job_id=self._job.job_id,
                                type="status",
                                status=JobStatus.CANCELLED,
                                message="cancelled",
                            )
                        )
                except Exception:
                    pass
            # Normalize cancellation exception to cancelled result (not error dialog)
            try:
                self.result_signal.emit({"cancelled": True, "message": str(e)})
            except Exception:
                self.error_signal.emit(e)
        except Exception as e:
            # TICK-802: token set or message indicates cancel → normalize to cancelled dict
            is_cancel = False
            if self._cancel_token is not None and self._cancel_token.is_set():
                is_cancel = True
            if "cancelled" in str(e).lower():
                is_cancel = True
            if is_cancel and self._job is not None:
                try:
                    self._job.status = JobStatus.CANCELLED
                    self._job.results = {"cancelled": True, "message": str(e)}
                    self._job.error = None
                    if self._job.finished_at is None:
                        self._job.finished_at = time.time()
                    if not self._job.events or self._job.events[-1].status != JobStatus.CANCELLED:
                        self._job.events.append(
                            JobEvent(
                                job_id=self._job.job_id,
                                type="status",
                                status=JobStatus.CANCELLED,
                                message="cancelled",
                            )
                        )
                except Exception:
                    pass
            if is_cancel:
                try:
                    self.result_signal.emit({"cancelled": True, "message": str(e)})
                    return
                except Exception:
                    pass
            if self._job is not None and not is_cancel:
                try:
                    self._job.status = JobStatus.FAILED
                    self._job.error = str(e)
                    self._job.finished_at = time.time()
                    self._job.events.append(
                        JobEvent(
                            job_id=self._job.job_id,
                            type="error",
                            status=JobStatus.FAILED,
                            message=str(e),
                        )
                    )
                except Exception:
                    pass
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

    def __init__(
        self,
        parent: Optional[QObject] = None,
        max_workers: int = 4,
        queue_depth: int = QUEUE_DEPTH,
    ) -> None:
        super().__init__(parent)
        self._queue = JobQueue(max_workers=max_workers, queue_depth=queue_depth)
        self._workers: Dict[str, ManagedWorker] = {}
        self._callbacks: Dict[str, Dict[str, Any]] = {}
        self._last_progress_at: Dict[str, float] = {}
        self._delivered_terminal: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._evidence_mode: bool = False
        self._shutdown_done: bool = False
        self._last_progress_forward: float = 0.0

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
        """True if any job is currently RUNNING (queue or QThread)."""
        # Check JobQueue status
        for job in self._queue.list_jobs():
            if job.status == JobStatus.RUNNING:
                return True
        # Also check live QThreads (ManagedWorker) — they may still be
        # running after queue marks DONE/CANCELLED, or queue may be
        # RUNNING while worker finished first. Both need checking.
        with self._lock:
            for w in self._workers.values():
                try:
                    if w.isRunning():
                        return True
                except RuntimeError:
                    pass
        return False

    @property
    def active_job_count(self) -> int:
        """Number of jobs currently RUNNING."""
        c = sum(1 for j in self._queue.list_jobs() if j.status == JobStatus.RUNNING)
        with self._lock:
            for w in self._workers.values():
                try:
                    if w.isRunning() and w._job_id not in {j.job_id for j in self._queue.list_jobs() if j.status == JobStatus.RUNNING}:
                        c += 1
                except RuntimeError:
                    pass
        return c

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

        Returns the job_id, or None if rejected (queue full).
        """
        if kwargs is None:
            kwargs = {}

        # TICK-911: reject before the queue fills so the user gets an explicit
        # error callback instead of a silently dropped job. Counts queued jobs
        # (RUNNING workers are still executing and will drain).
        if self.queued_job_count >= self._queue.queue_depth:
            logger.warning(
                "Job queue full (%s queued ≥ depth %s), rejecting %s",
                self.queued_job_count,
                self._queue.queue_depth,
                getattr(target, "__name__", target),
            )
            if on_error:
                on_error(RuntimeError("Too many jobs, try again — queue is full"))
            return None

        # TICK-802: Use JobQueue as pure registry (execute=False) — ManagedWorker is sole executor.
        # Prevents double execution (ThreadPool + QThread both running target).
        try:
            job = self._queue.submit(
                target,
                params=kwargs,
                progress_callback=None,  # we bridge via ManagedWorker
                execute=False,
            )
        except QueueFullError as e:
            logger.error("Job queue full: %s", e)
            if on_error:
                on_error(RuntimeError(str(e)))
            return None
        except Exception as e:
            logger.error("Failed to submit job: %s", e)
            if on_error:
                on_error(e)
            return None

        # TICK-802: Do NOT mark RUNNING here — keep QUEUED so _queued_count
        # accurately reflects depth for burst submits (8 queued + workers). Worker
        # will set RUNNING synchronously at run() start. is_busy remains true
        # via worker.isRunning() even while QUEUED.

        # Create ManagedWorker for Qt signal bridging (sole executor)
        worker = ManagedWorker(
            job_id=job.job_id,
            target=target,
            args=args,
            kwargs=kwargs,
            cancel_token=job.cancel_token,
            job=job,
        )

        # Store per-job callbacks for GUI-thread dispatch (TICK-914 P0.2).
        # Every callback entry point has an explicit affinity contract: the
        # dispatch slots below are pyqtSlot methods on JobManager (a QObject
        # living in the GUI thread), connected with Qt.QueuedConnection.
        with self._lock:
            self._callbacks[job.job_id] = {
                "on_success": on_success,
                "on_error": on_error,
                "progress": progress,
            }

        # Connect signals — explicit queued delivery to the GUI thread.
        # Internal JobQueue metadata sync runs on the GUI thread too, then
        # user callbacks are forwarded from the dispatch slots.
        worker.result_signal.connect(self._dispatch_result, Qt.QueuedConnection)
        worker.error_signal.connect(self._dispatch_error, Qt.QueuedConnection)
        worker.progress_signal.connect(self._dispatch_progress, Qt.QueuedConnection)

        # TICK-914 P0.3: connect cleanup to the NATIVE QThread.finished
        # (fires only after run() returns and the thread has stopped), not
        # to finished_signal which is emitted inside run() while the thread
        # is still running. A direct connect would raise TypeError (native
        # finished has no arguments), so capture the job_id in a lambda.
        worker.finished.connect(lambda jid=job.job_id: self._on_worker_finished(jid))

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
        TICK-802: cancels both JobQueue future and ManagedWorker token; ensures
        status becomes CANCELLED even if RUNNING.
        """
        success = self._queue.cancel(job_id)
        # Also ensure worker token is set even if queue says already cancelled/terminal
        # (e.g., worker still isRunning() but job already marked CANCELLED)
        with self._lock:
            w = self._workers.get(job_id)
            if w is not None:
                try:
                    tok = w._cancel_token  # type: ignore[attr-defined]
                    if tok is not None and not tok.is_set():
                        tok.set()
                        success = True
                except Exception:
                    pass
                # Ensure job object marked cancelled if still RUNNING
                j = self._queue.get(job_id)
                if j is not None and j.status == JobStatus.RUNNING:
                    try:
                        j.cancel()
                        success = True
                    except Exception:
                        pass
        if success:
            try:
                self.jobs_changed.emit()
            except Exception:
                pass
        return success

    def cancel_all(self) -> int:
        """Cancel all running/queued jobs. Returns count cancelled.

        TICK-802: cancels both queue futures and QThreads, ensures is_busy
        becomes False quickly. Iterates snapshot of jobs + live workers.
        """
        count = 0
        # Snapshot to avoid mutation during iteration
        snapshot = list(self._queue.list_jobs())
        for job in snapshot:
            if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                if self.cancel(job.job_id):
                    count += 1
        # Also handle workers that areRunning but job already CANCELLED/DONE (edge)
        with self._lock:
            for wid, w in list(self._workers.items()):
                try:
                    if w.isRunning():
                        j = self._queue.get(wid)
                        # If job not in snapshot or already cancelled but worker still alive, ensure token set
                        if j is None or j.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                            if self.cancel(wid):
                                # avoid double count
                                if j is None or j.status not in (JobStatus.CANCELLED,):
                                    count += 1
                        else:
                            # Job already CANCELLED but worker still running — ensure token
                            tok = w._cancel_token  # type: ignore[attr-defined]
                            if tok is not None and not tok.is_set():
                                tok.set()
                except RuntimeError:
                    pass
                except Exception:
                    pass
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
    # Internal — GUI-thread dispatch slots (explicit affinity contract)
    # ------------------------------------------------------------------
    #
    # These @pyqtSlot methods live on JobManager, a QObject created in the
    # GUI thread. ManagedWorker signals are connected to them with explicit
    # Qt.QueuedConnection, so every callback entry point runs on the GUI
    # thread — never on the worker QThread (TICK-914 P0.1/P0.2).

    def _job_id_for_sender(self) -> Optional[str]:
        sender = self.sender()
        if sender is None:
            return None
        with self._lock:
            for jid, w in self._workers.items():
                if w is sender:
                    return jid
        return None

    @pyqtSlot(int, int, str)
    def _dispatch_progress(self, current: int, total: int, message: str) -> None:
        """Deliver a progress update on the GUI thread.

        The ManagedWorker emits progress_signal on its thread; this slot runs
        on the main thread (Qt queued connection) and forwards to the
        parent app's update_progress so the status bar leaves indeterminate
        mode and shows real 0..total progress (TICK-914 P0.2 affinity).

        Coalesces noisy updates to prevent repaint storms: updates closer
        than 100ms apart are dropped except for the 0/total and total/total
        boundaries (TICK-914 P0.4; TICK-911 throttles signal emission at the
        worker, this slot bounds GUI delivery).
        """
        job_id = self._job_id_for_sender()
        if job_id is None:
            return
        # Post-terminal events are discarded (TICK-914 P0.6).
        if job_id in self._delivered_terminal:
            return
        with self._lock:
            callbacks = self._callbacks.get(job_id)
            progress_enabled = bool(callbacks and callbacks.get("progress"))
        if not progress_enabled:
            return
        # Coalesce: skip if <100ms since last delivered update, except
        # boundaries (0/total and total/total).
        now = time.monotonic()
        last = self._last_progress_at.get(job_id, 0.0)
        if now - last < _PROGRESS_COALESCE_MS and current != 0 and current != total:
            return
        self._last_progress_at[job_id] = now
        try:
            parent = self.parent()
            if parent is not None and hasattr(parent, "update_progress"):
                # monotonic(): an NTP clock step backwards must not zero the
                # coalesce interval and defeat the repaint gate.
                now = time.monotonic()
                if (
                    total > 0
                    and current != total
                    and now - getattr(self, "_last_progress_forward", 0.0) < 0.1
                ):
                    return
                self._last_progress_forward = now
                parent.update_progress(current, total, message)
        except Exception:
            pass
        try:
            self.jobs_changed.emit()
        except Exception:
            pass

    @pyqtSlot(object)
    def _dispatch_result(self, result: Any) -> None:
        """Sync JobQueue metadata and forward success on the GUI thread."""
        job_id = self._job_id_for_sender()
        if job_id is None:
            return
        if job_id in self._delivered_terminal:
            return
        self._delivered_terminal[job_id] = "result"
        self._sync_job_result(job_id, result)
        with self._lock:
            callbacks = self._callbacks.get(job_id)
            on_success = callbacks.get("on_success") if callbacks else None
        if on_success:
            try:
                on_success(result)
            except Exception:
                logger.exception("on_success callback failed for job %s", job_id)

    @pyqtSlot(Exception)
    def _dispatch_error(self, error: Exception) -> None:
        """Sync JobQueue metadata and forward error on the GUI thread."""
        job_id = self._job_id_for_sender()
        if job_id is None:
            return
        if job_id in self._delivered_terminal:
            return
        self._delivered_terminal[job_id] = "error"
        self._sync_job_error(job_id, error)
        with self._lock:
            callbacks = self._callbacks.get(job_id)
            on_error = callbacks.get("on_error") if callbacks else None
        if on_error:
            try:
                on_error(error)
            except Exception:
                logger.exception("on_error callback failed for job %s", job_id)

    def _sync_job_result(self, job_id: str, result: Any) -> None:
        """Keep JobQueue metadata in sync after a job succeeds.

        Runs on the GUI thread (called from _dispatch_result). The queue's
        own lock protects the shared Job object.
        """
        j = self._queue.get(job_id)
        if j is not None:
            with self._queue._lock:
                is_cancelled_result = isinstance(result, dict) and result.get("cancelled") is True
                token_cancelled = j.is_cancelled()
                if is_cancelled_result or token_cancelled:
                    j.status = JobStatus.CANCELLED
                    j.results = result if isinstance(result, dict) else {"cancelled": True, "result": result}
                    if j.finished_at is None:
                        j.finished_at = time.time()
                    if not j.events or j.events[-1].status != JobStatus.CANCELLED:
                        j.events.append(
                            JobEvent(
                                job_id=j.job_id,
                                type="status",
                                status=JobStatus.CANCELLED,
                                message="cancelled",
                            )
                        )
                else:
                    j.status = JobStatus.DONE
                    j.results = result
                    j.finished_at = time.time()
                    j.events.append(
                        JobEvent(
                            job_id=j.job_id,
                            type="result",
                            status=JobStatus.DONE,
                            payload={"result": result} if isinstance(result, dict) else {"result": result},
                            message="done",
                        )
                    )
            try:
                self.jobs_changed.emit()
            except Exception:
                pass

    def _sync_job_error(self, job_id: str, err: Exception) -> None:
        """Keep JobQueue metadata in sync after a job fails.

        Runs on the GUI thread (called from _dispatch_error).
        """
        j = self._queue.get(job_id)
        if j is not None:
            with self._queue._lock:
                is_cancel = j.is_cancelled() or isinstance(err, InterruptedError) or "cancelled" in str(err).lower()
                if is_cancel:
                    j.status = JobStatus.CANCELLED
                    j.results = {"cancelled": True, "message": str(err)}
                    j.error = None
                    if j.finished_at is None:
                        j.finished_at = time.time()
                    if not j.events or j.events[-1].status != JobStatus.CANCELLED:
                        j.events.append(
                            JobEvent(
                                job_id=j.job_id,
                                type="status",
                                status=JobStatus.CANCELLED,
                                message="cancelled",
                            )
                        )
                else:
                    j.status = JobStatus.FAILED
                    j.error = str(err)
                    j.finished_at = time.time()
                    j.events.append(
                        JobEvent(
                            job_id=j.job_id,
                            type="error",
                            status=JobStatus.FAILED,
                            message=str(err),
                        )
                    )
            try:
                self.jobs_changed.emit()
            except Exception:
                pass

    def _on_worker_finished(self, job_id: str) -> None:
        """Clean up when a ManagedWorker's native thread has stopped.

        Connected to the native QThread.finished signal (see submit), which
        fires only after run() returns and the thread has terminated — so
        deleteLater() here never destroys a running QThread (TICK-914 P0.3).
        """
        with self._lock:
            worker = self._workers.pop(job_id, None)
            self._callbacks.pop(job_id, None)
            self._last_progress_at.pop(job_id, None)
            self._delivered_terminal.pop(job_id, None)
        if worker is not None:
            try:
                worker.deleteLater()
            except RuntimeError:
                pass
        try:
            self.jobs_changed.emit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self, timeout: float = 2.0) -> None:
        """Cancel all jobs, wait for workers, and shut down the executor.

        TICK-911: previously the queue executor was shut down but live
        ``ManagedWorker`` QThreads were left dangling on app close — a
        shutdown leak that can crash at exit. This now waits (bounded) for
        workers to observe their cancel tokens, then tears them down.
        Idempotent: calling it twice is safe.

        TICK-914 P0.3: any worker still running after the bounded poll gets
        a hard ``wait(5000)`` so no QThread is destroyed while still
        running (the bounded poll covers the common case; the hard wait is
        the guarantee). Called from DataForgeApp.closeEvent (TICK-917).
        """
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True
        self.cancel_all()
        # Give workers a bounded window to observe the cancel token and exit.
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                running = [w for w in self._workers.values() if w.isRunning()]
            if not running:
                break
            time.sleep(0.02)
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for w in workers:
            try:
                if w.isRunning():
                    w.wait(5000)
                w.deleteLater()
            except Exception:
                pass
        self._queue.shutdown(wait=True, cancel_futures=True)
