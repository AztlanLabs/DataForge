"""Engine daemon — TICK-301 consolidation.

Main event loop for the DataForge out-of-process engine.  Uses
:class:`dataforge.engine.jobs.JobQueue` for job management and exposes
a JSON-RPC 2.0 handler that processes ``scan``, ``search``, ``dupes``,
``hash``, and ``integrity`` requests.

Transports (UDS, Named Pipe) are started by the service entrypoint
(``dataforge.service.__main__``) and delegate to :meth:`Daemon.handle_request`.

Spec: ``docs/proposals/NATIVE_OS_API_REVIEW.md §3``
Depends: TICK-205 (UDS/Named Pipe), TICK-201 (FileActionService)
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Optional

from dataforge.engine.jobs import Job, JobQueue

logger = logging.getLogger(__name__)

__all__ = ["Daemon", "EngineDaemon", "get_daemon"]


class Daemon:
    """Engine daemon wrapping a :class:`JobQueue` with JSON-RPC dispatch.

    The daemon is the single integration point between transports and
    the module layer.  Each incoming JSON-RPC request is dispatched to
    the appropriate module function via :meth:`handle_request`.

    Usage::

        daemon = Daemon()
        daemon.start()
        # ... daemon handles requests via handle_request() ...
        daemon.stop()
    """

    def __init__(
        self,
        queue_depth: int = 8,
        max_workers: int = 4,
    ) -> None:
        self.queue = JobQueue(max_workers=max_workers, queue_depth=queue_depth)
        self._running: bool = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Mark the daemon as running."""
        with self._lock:
            self._running = True
        logger.info("Engine daemon started")

    def stop(self) -> None:
        """Stop the daemon and shut down the job queue."""
        with self._lock:
            self._running = False
        try:
            self.queue.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        logger.info("Engine daemon stopped")

    def is_running(self) -> bool:
        """Return True if the daemon is running."""
        with self._lock:
            return self._running

    @property
    def running(self) -> bool:
        return self.is_running()

    def submit(self, *args: Any, **kwargs: Any) -> Job:
        """Submit a job to the queue."""
        return self.queue.submit(*args, **kwargs)

    def get(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        return self.queue.get(job_id)

    def cancel(self, job_id: str) -> bool:
        """Cancel a job by ID."""
        return self.queue.cancel(job_id)

    def list_jobs(self) -> List[Job]:
        """List all jobs."""
        return self.queue.list_jobs()

    # ------------------------------------------------------------------
    # JSON-RPC 2.0 dispatch
    # ------------------------------------------------------------------

    async def handle_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a JSON-RPC 2.0 request and return a response.

        Dispatches to the appropriate module function based on the
        ``method`` field.  Returns a JSON-RPC 2.0 response dict.
        """
        method = payload.get("method", "")
        params = payload.get("params", {})
        request_id = payload.get("id", 1)

        try:
            handler = self._get_handler(method)
            if handler is None:
                return self._error_response(
                    request_id,
                    -32601,
                    f"Method not found: {method}",
                )
            result = await handler(params)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
        except Exception as exc:
            logger.exception("Error handling request: %s", method)
            return self._error_response(request_id, -32603, str(exc))

    def _get_handler(self, method: str) -> Optional[Callable[..., Any]]:
        """Return the handler for *method*, or None."""
        handlers = {
            "scan": self._handle_scan,
            "search": self._handle_search,
            "dupes": self._handle_dupes,
            "hash": self._handle_hash,
            "integrity": self._handle_integrity,
            "status": self._handle_status,
            "cancel": self._handle_cancel,
            "list_jobs": self._handle_list_jobs,
        }
        return handlers.get(method)

    @staticmethod
    def _error_response(
        request_id: Any,
        code: int,
        message: str,
    ) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    # ------------------------------------------------------------------
    # Module dispatch handlers
    # ------------------------------------------------------------------

    async def _handle_scan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a ``scan`` request by submitting a job."""
        from dataforge.core.scanner import scan_directory

        root = params.get("root", "")
        recursive = params.get("recursive", True)
        max_depth = params.get("max_depth", -1)

        if not root:
            raise ValueError("root is required")

        def _scan_worker(
            root: str,
            recursive: bool = True,
            max_depth: int = -1,
            progress_callback: Any = None,
            cancel_token: Any = None,
        ) -> Dict[str, Any]:
            entries = []
            for entry in scan_directory(root, recursive=recursive, max_depth=max_depth, cancel_token=cancel_token):
                if cancel_token and cancel_token.is_set():
                    break
                entries.append({
                    "path": entry.path,
                    "filename": entry.filename,
                    "extension": entry.extension,
                    "size": entry.size,
                    "is_dir": entry.is_dir,
                })
                if progress_callback and len(entries) % 100 == 0:
                    progress_callback(len(entries), -1, f"Scanned {len(entries)} files")
            return {"total": len(entries), "files": entries}

        job = self.queue.submit(
            _scan_worker,
            params={"root": root, "recursive": recursive, "max_depth": max_depth},
        )
        return {"job_id": job.job_id}

    async def _handle_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a ``search`` request by submitting a job."""
        from dataforge.modules.search import build_search_query, search_files

        root = params.get("root", "")
        if not root:
            raise ValueError("root is required")

        def _search_worker(
            root: str,
            progress_callback: Any = None,
            cancel_token: Any = None,
            **kwargs: Any,
        ) -> Dict[str, Any]:
            query = build_search_query(
                name_pattern=kwargs.get("name_pattern"),
                use_regex=kwargs.get("use_regex", False),
                extensions=kwargs.get("extensions"),
                content_text=kwargs.get("content_text"),
                content_is_regex=kwargs.get("content_is_regex", False),
                case_sensitive=kwargs.get("case_sensitive", False),
                min_size_bytes=kwargs.get("min_size_bytes"),
                max_size_bytes=kwargs.get("max_size_bytes"),
                newer_than_days=kwargs.get("newer_than_days"),
                older_than_days=kwargs.get("older_than_days"),
            )
            results = search_files(
                root,
                query,
                recursive=kwargs.get("recursive", True),
                max_depth=kwargs.get("max_depth", -1),
                progress_callback=progress_callback,
                cancel_token=cancel_token,
            )
            return {
                "total": len(results),
                "files": [
                    {
                        "path": e.path,
                        "filename": e.filename,
                        "extension": e.extension,
                        "size": e.size,
                    }
                    for e in results
                ],
            }

        job = self.queue.submit(
            _search_worker,
            params={**params, "root": root},
        )
        return {"job_id": job.job_id}

    async def _handle_dupes(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a ``dupes`` request by submitting a job."""
        from dataforge.modules.duplicates import find_duplicates

        root = params.get("root", "")
        if not root:
            raise ValueError("root is required")

        def _dupes_worker(
            root: str,
            progress_callback: Any = None,
            cancel_token: Any = None,
            **kwargs: Any,
        ) -> Dict[str, Any]:
            duplicates = find_duplicates(
                root,
                recursive=kwargs.get("recursive", True),
                max_depth=kwargs.get("max_depth", -1),
                progress_callback=progress_callback,
                cancel_token=cancel_token,
            )
            groups = []
            for hash_val, entries in duplicates.items():
                groups.append({
                    "hash": hash_val,
                    "count": len(entries),
                    "files": [
                        {"path": e.path, "filename": e.filename, "size": e.size}
                        for e in entries
                    ],
                })
            return {"total_groups": len(groups), "groups": groups}

        job = self.queue.submit(
            _dupes_worker,
            params={**params, "root": root},
        )
        return {"job_id": job.job_id}

    async def _handle_hash(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a ``hash`` request by submitting a job."""
        from dataforge.core.hasher import get_file_hash, get_hashes

        path = params.get("path")
        paths = params.get("paths")
        algo = params.get("algo", "sha256")
        algos = params.get("algos")

        if path:
            def _hash_single(
                path: str,
                algo: str = "sha256",
                progress_callback: Any = None,
                cancel_token: Any = None,
            ) -> Dict[str, Any]:
                result = get_file_hash(path, algo=algo, cancel_token=cancel_token)
                return {"path": path, "algo": algo, "hash": result}

            job = self.queue.submit(
                _hash_single,
                params={"path": path, "algo": algo},
            )
        elif paths:
            def _hash_multi(
                paths: list,
                algo: str = "sha256",
                progress_callback: Any = None,
                cancel_token: Any = None,
            ) -> Dict[str, Any]:
                results = {}
                for p in paths:
                    if cancel_token and cancel_token.is_set():
                        break
                    results[p] = get_file_hash(p, algo=algo, cancel_token=cancel_token)
                    if progress_callback:
                        progress_callback(len(results), len(paths), f"Hashed {len(results)}/{len(paths)}")
                return {"algo": algo, "results": results}

            job = self.queue.submit(
                _hash_multi,
                params={"paths": paths, "algo": algo},
            )
        elif algos:
            def _hash_algos(
                path: str,
                algos: list,
                progress_callback: Any = None,
                cancel_token: Any = None,
            ) -> Dict[str, Any]:
                results = get_hashes(path, algos)
                return {"path": path, "results": results}

            job = self.queue.submit(
                _hash_algos,
                params={"path": path or "", "algos": algos},
            )
        else:
            raise ValueError("path or paths required")

        return {"job_id": job.job_id}

    async def _handle_integrity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle an ``integrity`` request by submitting a job."""
        from dataforge.modules.integrity import IntegrityMonitor

        path = params.get("path", "")
        snapshot = params.get("snapshot", "")
        operation = params.get("operation", "create")
        algorithm = params.get("algorithm", "sha256")

        if not path or not snapshot:
            raise ValueError("path and snapshot are required")

        def _integrity_worker(
            path: str,
            snapshot: str,
            operation: str = "create",
            algorithm: str = "sha256",
            progress_callback: Any = None,
            cancel_token: Any = None,
        ) -> Dict[str, Any]:
            if operation == "create":
                return IntegrityMonitor.create_snapshot(
                    path, snapshot,
                    progress_callback=progress_callback,
                    cancel_token=cancel_token,
                )
            elif operation in ("verify", "check"):
                return IntegrityMonitor.verify_snapshot(path, snapshot)
            else:
                raise ValueError(f"Unknown operation: {operation}")

        job = self.queue.submit(
            _integrity_worker,
            params={
                "path": path,
                "snapshot": snapshot,
                "operation": operation,
                "algorithm": algorithm,
            },
        )
        return {"job_id": job.job_id}

    async def _handle_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a ``status`` request — return job status."""
        job_id = params.get("job_id", "")
        if not job_id:
            raise ValueError("job_id is required")

        job = self.queue.get(job_id)
        if job is None:
            return {"error": f"Job not found: {job_id}"}
        return job.json_safe()

    async def _handle_cancel(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a ``cancel`` request — cancel a job."""
        job_id = params.get("job_id", "")
        if not job_id:
            raise ValueError("job_id is required")

        cancelled = self.queue.cancel(job_id)
        return {"job_id": job_id, "cancelled": cancelled}

    async def _handle_list_jobs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a ``list_jobs`` request — list all jobs."""
        jobs = self.queue.list_jobs()
        return {
            "total": len(jobs),
            "jobs": [j.json_safe() for j in jobs],
        }


EngineDaemon = Daemon

_daemon: Optional[Daemon] = None


def get_daemon() -> Daemon:
    """Get or create the global daemon singleton."""
    global _daemon
    if _daemon is None:
        _daemon = Daemon()
    return _daemon
