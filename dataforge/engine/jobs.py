"""Job model and JobQueue stub — TICK-005 contract.

Domain: Engine / Jobs
Spec: docs/proposals/NATIVE_OS_API_REVIEW.md#3.3
Depends: dataforge.api.schema.JobStatus / JobEvent (TICK-003)

Design notes
------------
* ``Job`` is the unit of work: ``id`` (ULID-like), ``provider``, ``params``,
  ``cancel_token`` (``threading.Event``), ``progress_callback`` → event stream,
  and ``results``.
* ``JobQueue`` is an in-process stub with queue depth 8.  It uses a
  ``ThreadPoolExecutor`` to mimic the real daemon queue (``asyncio`` +
  ``ThreadPool`` + ``ProcessPool`` in TICK-301).  Status lifecycle::

      queued → running → done | cancelled | failed

* ``cancel_token.set()`` makes ``is_cancelled()`` return ``True`` immediately.
* ``job_id`` is ULID-like (26-char Crockford base32) and JSON-safe.
* Append-only jobs-table hook ``_append_job_record`` is a no-op stub for
  future F1 (hash-chained audit).  No I/O on import.

No side effects on import — real daemon loop is TICK-301.
"""

from __future__ import annotations

import inspect
import json
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from dataforge.api.schema import JobEvent, JobStatus

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_QUEUE_DEPTH: int = 8
QUEUE_DEPTH: int = _QUEUE_DEPTH


class QueueFullError(queue.Full):
    """Raised when ``JobQueue.submit`` exceeds the configured queue depth.

    TICK-911: subclasses ``queue.Full`` (backwards compatible) but carries a
    user-actionable message so UI layers can surface "Too many jobs, try
    again" instead of a silent ``None``.
    """

_last_timestamp_ms: int = 0
_last_random: int = 0
_ulid_lock = threading.Lock()


def _encode_base32(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(out))


def generate_ulid() -> str:
    global _last_timestamp_ms, _last_random
    with _ulid_lock:
        now_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
        if now_ms == _last_timestamp_ms:
            _last_random = (_last_random + 1) & ((1 << 80) - 1)
        else:
            _last_random = int.from_bytes(os.urandom(10), "big")
            _last_timestamp_ms = now_ms
        time_part = _encode_base32(now_ms, 10)
        rand_part = _encode_base32(_last_random, 16)
        return time_part + rand_part


_generate_ulid = generate_ulid


@dataclass
class Job:
    job_id: str = field(default_factory=generate_ulid)
    provider: Any = "local"
    params: Dict[str, Any] = field(default_factory=dict)
    cancel_token: threading.Event = field(default_factory=threading.Event)
    progress_callback: Optional[Callable[..., Any]] = None
    status: JobStatus = JobStatus.QUEUED
    results: Any = None
    error: Optional[str] = None
    events: List[JobEvent] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.job_id:
            self.job_id = generate_ulid()
        if self.params is None:
            self.params = {}
        if isinstance(self.status, str):
            try:
                self.status = JobStatus(self.status)
            except ValueError:
                self.status = JobStatus.QUEUED
        if not self.events:
            self.events.append(
                JobEvent(
                    job_id=self.job_id,
                    type="status",
                    status=JobStatus.QUEUED,
                    message="queued",
                )
            )

    def is_cancelled(self) -> bool:
        return self.cancel_token.is_set()

    def cancel(self) -> None:
        self.cancel_token.set()
        # TICK-802: set CANCELLED even if RUNNING (not only QUEUED). Done/Failed already terminal.
        if self.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.COMPLETED):
            return
        self.status = JobStatus.CANCELLED
        if self.finished_at is None:
            self.finished_at = time.time()
        # Avoid duplicate consecutive CANCELLED events
        if not self.events or self.events[-1].status != JobStatus.CANCELLED:
            self.events.append(
                JobEvent(
                    job_id=self.job_id,
                    type="status",
                    status=JobStatus.CANCELLED,
                    message="cancelled",
                )
            )

    def to_dict(self) -> Dict[str, Any]:
        if isinstance(self.provider, str):
            provider_repr: Any = self.provider
        else:
            try:
                provider_repr = str(self.provider)
            except Exception:
                provider_repr = repr(self.provider)
        return {
            "job_id": self.job_id,
            "provider": provider_repr,
            "params": self.params,
            "status": self.status.value if isinstance(self.status, JobStatus) else str(self.status),
            "results": self.results,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "is_cancelled": self.is_cancelled(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def as_dict(self) -> Dict[str, Any]:
        return self.to_dict()

    def json_safe(self) -> Dict[str, Any]:
        d = self.to_dict()
        json.dumps(d)
        return d


class JobQueue:
    QUEUE_DEPTH: int = _QUEUE_DEPTH
    MAX_QUEUE_DEPTH: int = _QUEUE_DEPTH
    DEFAULT_QUEUE_DEPTH: int = _QUEUE_DEPTH

    def __init__(self, max_workers: int = 4, queue_depth: int = 8) -> None:
        self.max_workers = max_workers
        self.queue_depth = queue_depth
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dataforge-job")
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._futures: Dict[str, Any] = {}

    def _append_job_record(self, job: Job) -> None:
        pass

    def _queued_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status == JobStatus.QUEUED)

    def _invoke_worker(self, job: Job, func: Callable[..., Any]) -> Any:
        def _progress(current: int, total: int, message: str = "") -> None:
            if job.is_cancelled():
                return
            evt = JobEvent(
                job_id=job.job_id,
                type="progress",
                current=current,
                total=total,
                message=message,
            )
            job.events.append(evt)
            if job.progress_callback is not None:
                try:
                    job.progress_callback(current, total, message)
                except Exception:
                    pass

        try:
            sig = inspect.signature(func)
            params_meta = sig.parameters
            has_cancel = "cancel_token" in params_meta
            has_progress = "progress_callback" in params_meta
            has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params_meta.values())
        except (ValueError, TypeError):
            sig = None
            has_cancel = has_progress = has_var_kw = False

        kwargs: Dict[str, Any] = {}
        if has_cancel:
            kwargs["cancel_token"] = job.cancel_token
        if has_progress:
            kwargs["progress_callback"] = _progress

        raw_params: Any = job.params
        if raw_params is None:
            raw_params = {}
        is_dict_params = isinstance(raw_params, dict)

        attempts: list[Callable[[], Any]] = []

        if is_dict_params:
            d: Dict[str, Any] = raw_params
            if sig is not None:
                if has_var_kw or all(k in params_meta or k in kwargs for k in d):
                    merged = {**d, **kwargs}
                    if not has_var_kw:
                        merged = {k: v for k, v in merged.items() if k in params_meta}
                        if has_cancel and "cancel_token" not in merged:
                            merged["cancel_token"] = job.cancel_token
                        if has_progress and "progress_callback" not in merged:
                            merged["progress_callback"] = _progress
                    attempts.append(lambda m=merged: func(**m))  # type: ignore[misc]
            attempts.append(lambda: func(d, **kwargs) if kwargs else func(d))
            if kwargs:
                attempts.append(lambda: func(**kwargs))
            attempts.append(lambda: func())
            if sig is not None and d:
                filtered = {k: v for k, v in d.items() if k in params_meta}
                if filtered and filtered != d:
                    merged2 = {**filtered, **kwargs}
                    attempts.append(lambda m=merged2: func(**m))  # type: ignore[misc]
        else:
            attempts.append(lambda: func(raw_params, **kwargs) if kwargs else func(raw_params))
            if kwargs:
                attempts.append(lambda: func(**kwargs))
            attempts.append(lambda: func())

        last_exc: Optional[Exception] = None
        for attempt in attempts:
            try:
                return attempt()
            except TypeError as exc:
                last_exc = exc
                continue
            except Exception:
                raise
        if last_exc is not None:
            raise last_exc
        return func()

    def _run_job(self, job: Job, func: Callable[..., Any]) -> None:
        with self._lock:
            if job.status == JobStatus.CANCELLED:
                job.finished_at = time.time()
                self._append_job_record(job)
                return
            job.status = JobStatus.RUNNING
            job.started_at = time.time()
            job.events.append(
                JobEvent(
                    job_id=job.job_id,
                    type="status",
                    status=JobStatus.RUNNING,
                    message="running",
                )
            )
        self._append_job_record(job)
        if job.is_cancelled():
            with self._lock:
                job.status = JobStatus.CANCELLED
                job.finished_at = time.time()
                job.events.append(
                    JobEvent(
                        job_id=job.job_id,
                        type="status",
                        status=JobStatus.CANCELLED,
                        message="cancelled",
                    )
                )
            self._append_job_record(job)
            return
        try:
            result = self._invoke_worker(job, func)
            # TICK-802: normalize dict cancelled result even if token not set
            is_result_cancelled = isinstance(result, dict) and result.get("cancelled") is True
            with self._lock:
                if job.is_cancelled() or is_result_cancelled:
                    job.status = JobStatus.CANCELLED
                    if is_result_cancelled:
                        job.results = result
                    elif isinstance(result, dict) and "cancelled" not in result:
                        # Preserve normal result but mark cancelled for UI
                        job.results = {"cancelled": True, "result": result}
                    else:
                        job.results = result
                    job.events.append(
                        JobEvent(
                            job_id=job.job_id,
                            type="status",
                            status=JobStatus.CANCELLED,
                            message="cancelled",
                        )
                    )
                else:
                    job.results = result
                    job.status = JobStatus.DONE
                    job.events.append(
                        JobEvent(
                            job_id=job.job_id,
                            type="result",
                            status=JobStatus.DONE,
                            payload={"result": result} if isinstance(result, dict) else {"result": result},
                            message="done",
                        )
                    )
                job.finished_at = time.time()
            self._append_job_record(job)
        except InterruptedError as exc:  # TICK-802: normalize to cancelled, not FAILED
            with self._lock:
                job.status = JobStatus.CANCELLED
                job.results = {"cancelled": True, "message": str(exc)}
                job.error = None
                job.finished_at = time.time()
                job.events.append(
                    JobEvent(
                        job_id=job.job_id,
                        type="status",
                        status=JobStatus.CANCELLED,
                        message="cancelled",
                    )
                )
            self._append_job_record(job)
        except Exception as exc:  # pylint: disable=broad-except
            with self._lock:
                if job.is_cancelled() or isinstance(exc, InterruptedError):
                    job.status = JobStatus.CANCELLED
                    job.results = {"cancelled": True, "message": str(exc)}
                    job.error = None
                    job.events.append(
                        JobEvent(
                            job_id=job.job_id,
                            type="status",
                            status=JobStatus.CANCELLED,
                            message="cancelled",
                        )
                    )
                else:
                    job.error = str(exc)
                    job.status = JobStatus.FAILED
                    job.events.append(
                        JobEvent(
                            job_id=job.job_id,
                            type="error",
                            status=JobStatus.FAILED,
                            message=str(exc),
                        )
                    )
                job.finished_at = time.time()
            self._append_job_record(job)

    def submit(
        self,
        func: Callable[..., Any],
        params: Optional[Any] = None,
        provider: Any = "local",
        progress_callback: Optional[Callable[..., Any]] = None,
        *,
        execute: bool = True,
        cancel_token: Optional[threading.Event] = None,
        **kwargs: Any,
    ) -> Job:
        """Submit a job.

        ``execute`` is keyword-only and must be an explicit bool — there is no
        positional shorthand:

        * ``execute=False`` — registry only. The Job is tracked (status,
          events, cancel_token) but never runs; a ManagedWorker QThread is the
          sole executor. This is the UI JobManager path (TICK-802/TICK-911).
        * ``execute=True`` — run via the internal ThreadPoolExecutor. Used by
          daemon transports and direct engine callers.

        Passing a non-bool ``execute`` (e.g. ``None``) raises ``TypeError``
        instead of silently falling into registry-only mode.

        ``cancel_token`` optionally supplies a caller-owned ``threading.Event``
        for the Job; when omitted the Job creates its own (``job.cancel()``
        sets it). Per-job tokens let daemon clients cancel from outside.

        Raises ``QueueFullError`` (a ``queue.Full`` subclass) when the number
        of queued jobs already equals ``queue_depth``.
        """
        if not isinstance(execute, bool):
            raise TypeError(
                "execute must be an explicit bool "
                "(True=run via ThreadPool, False=registry-only)"
            )
        if params is None:
            norm_params: Any = {}
        else:
            norm_params = params
        if isinstance(norm_params, dict) and kwargs:
            norm_params = {**norm_params, **kwargs}
        elif kwargs and not isinstance(norm_params, dict):
            norm_params = kwargs
        elif isinstance(norm_params, dict):
            norm_params = dict(norm_params)
        queued = self._queued_count()
        if queued >= self.queue_depth:
            raise QueueFullError(
                f"Too many jobs, try again — JobQueue depth {self.queue_depth} "
                f"exceeded ({queued} queued)"
            )
        job_kwargs: Dict[str, Any] = dict(
            provider=provider,
            params=norm_params if isinstance(norm_params, dict) else {"_value": norm_params},
            progress_callback=progress_callback,
            status=JobStatus.QUEUED,
        )
        if cancel_token is not None:
            job_kwargs["cancel_token"] = cancel_token
        job = Job(**job_kwargs)
        if not isinstance(params, dict) and params is not None and not kwargs:
            job.params = params  # type: ignore[assignment]
        with self._lock:
            self._jobs[job.job_id] = job
        self._append_job_record(job)
        if execute:
            future = self._executor.submit(self._run_job, job, func)
            with self._lock:
                self._futures[job.job_id] = future
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.get(job_id)

    def get_status(self, job_id: str) -> Optional[JobStatus]:
        job = self.get(job_id)
        return job.status if job else None

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None:
            return False
        if job.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.COMPLETED):
            return False
        job.cancel()
        fut = self._futures.get(job_id)
        if fut is not None:
            try:
                fut.cancel()
            except Exception:
                pass
        self._append_job_record(job)
        return True

    def list_jobs(self) -> List[Job]:
        with self._lock:
            return list(self._jobs.values())

    def jobs(self) -> List[Job]:
        return self.list_jobs()

    def subscribe(self, job_id: str):
        job = self.get(job_id)
        if job is None:
            return iter([])
        return iter(list(job.events))

    def events_for(self, job_id: str) -> List[JobEvent]:
        job = self.get(job_id)
        return list(job.events) if job else []

    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)

    def __len__(self) -> int:
        with self._lock:
            return len(self._jobs)

    def __contains__(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._jobs


__all__ = [
    "Job",
    "JobQueue",
    "QueueFullError",
    "QUEUE_DEPTH",
    "generate_ulid",
]
