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

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from dataforge.engine.jobs import Job, JobQueue

logger = logging.getLogger(__name__)

__all__ = ["Daemon", "EngineDaemon", "get_daemon"]


class Daemon:
    """Engine daemon wrapping a :class:`JobQueue` with JSON-RPC dispatch.

    The daemon is the single integration point between transports and
    the module layer.  Each incoming JSON-RPC request is dispatched to
    the appropriate module function via :meth:`handle_request`.

    Importing this module is side-effect-free: no server is started, no
    daemon instance is created and no threads spawn until ``Daemon()`` /
    ``start()`` is explicitly called (TICK-911 invariant).

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
        """Submit a job to the queue.

        TICK-911: passes through to :meth:`JobQueue.submit`; a caller-owned
        ``cancel_token`` may be supplied per job (``execute`` stays explicit).
        """
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
    # Automation store (TICK-806) — JSON at exports_dir/automations
    # ------------------------------------------------------------------
    def _automation_store_dir(self) -> Path:
        try:
            import dataforge.core.paths as _paths
            base = Path(_paths.exports_dir)
        except Exception:
            base = Path.home() / "Documents" / "DataForge"
        return base / "automations"

    def _sanitize_automation_name(self, name: str) -> str:
        s = (name or "").strip() or "automation"
        s = re.sub(r'[^a-zA-Z0-9._-]', '_', s)
        s = re.sub(r'_+', '_', s).strip('._')
        return s[:80] if len(s) > 80 else s or "automation"

    def list_automations(self) -> List[Dict[str, Any]]:
        """List all stored automations (from exports_dir/automations/*.json)."""
        store = self._automation_store_dir()
        try:
            store.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        out: List[Dict[str, Any]] = []
        try:
            for p in sorted(store.glob("*.json")):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        if not data.get("name"):
                            data["name"] = p.stem
                        if "steps" not in data:
                            data["steps"] = []
                        out.append(data)
                except Exception:
                    continue
        except Exception:
            pass
        out.sort(key=lambda d: d.get("name", "").lower())
        return out

    def get_automation(self, name: str) -> Optional[Dict[str, Any]]:
        """Load a single automation by name (sanitized filename)."""
        if not name:
            return None
        store = self._automation_store_dir()
        path = store / f"{self._sanitize_automation_name(name)}.json"
        # Try exact file, then case-insensitive search
        try:
            if path.is_file():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            # Fallback scan for case differences
            for p in store.glob("*.json"):
                if p.stem.lower() == self._sanitize_automation_name(name).lower():
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception:
            pass
        return None

    def schedule_automation(
        self,
        name: str,
        source: str = "",
        dry_run: bool = True,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Schedule a stored automation as a JobQueue job.

        Loads ``name`` from the automation store and submits a worker that
        replays its steps via ``ActionContext``. Returns ``{"job_id": ...}``.

        Args:
            name: automation name (matches file ``<sanitized>.json``)
            source: source path for the pipeline (passed to scanner)
            dry_run: if True, steps run in dry-run mode
            params: optional override params merged into submission
        """
        data = self.get_automation(name)
        if data is None:
            raise ValueError(f"Automation not found: {name}")
        steps_data = data.get("steps", []) or []
        # Build worker that lazily imports step classes to avoid circular deps
        def _automation_worker(
            source: str = source,
            steps_data: List[Dict[str, Any]] = steps_data,
            dry_run: bool = dry_run,
            progress_callback: Any = None,
            cancel_token: Any = None,
            **_: Any,
        ) -> Dict[str, Any]:
            from dataforge.core.scanner import scan_directory
            from dataforge.core.actions.base import ActionContext
            # Local registry (mirrors action_builder)
            try:
                from dataforge.core.actions.filters import (
                    SearchFilter, SizeFilter, DateFilter, ImagePropFilter,
                    ExtensionFilter, DuplicateFilter, SignatureMismatchFilter,
                    EmptyFileFilter, EmptyFolderFilter,
                )
                from dataforge.core.actions.modifications import RenameStep, MetaCleanStep, HashLogStep, NormalizeNameStep
                from dataforge.core.actions.io import MoveStep, CopyStep, DeleteStep, ZipStep
                from dataforge.core.actions.organize import OrganizeStep
                from dataforge.core.actions.media import ConvertImageStep
                _reg = {
                    "SearchFilter": SearchFilter, "SizeFilter": SizeFilter, "DateFilter": DateFilter,
                    "ImagePropFilter": ImagePropFilter, "ExtensionFilter": ExtensionFilter,
                    "DuplicateFilter": DuplicateFilter, "SignatureMismatchFilter": SignatureMismatchFilter,
                    "EmptyFileFilter": EmptyFileFilter, "EmptyFolderFilter": EmptyFolderFilter,
                    "RenameStep": RenameStep, "MetaCleanStep": MetaCleanStep, "HashLogStep": HashLogStep,
                    "NormalizeNameStep": NormalizeNameStep, "MoveStep": MoveStep, "CopyStep": CopyStep,
                    "DeleteStep": DeleteStep, "ZipStep": ZipStep, "OrganizeStep": OrganizeStep,
                    "ConvertImageStep": ConvertImageStep,
                }
            except Exception:
                _reg = {}
            # Rebuild steps
            steps = []
            for entry in steps_data:
                if not isinstance(entry, dict):
                    continue
                t = entry.get("type")
                p = entry.get("params", {}) if isinstance(entry.get("params"), dict) else {}
                cls = _reg.get(t)
                if cls is None:
                    continue
                try:
                    step = cls(p)
                    step.params = dict(p)
                except Exception:
                    try:
                        step = cls()
                        step.params = dict(p)
                    except Exception:
                        continue
                steps.append(step)
            # Scan source if provided
            files = []
            if source and os.path.exists(source):
                try:
                    for entry in scan_directory(source, recursive=True, max_depth=-1, cancel_token=cancel_token):
                        if cancel_token and cancel_token.is_set():
                            break
                        files.append(entry)
                        if progress_callback and len(files) % 50 == 0:
                            progress_callback(len(files), 0, "Scanning...")
                except Exception:
                    pass
            # If no source/files, just log empty run
            ctx = ActionContext(files, update_progress=progress_callback)
            ctx.is_dry_run = bool(dry_run)
            ctx.cancel_token = cancel_token
            ctx.variables["source_path"] = source
            total = len(steps)
            for i, step in enumerate(steps):
                if ctx.should_cancel():
                    break
                if progress_callback:
                    try:
                        progress_callback(i, total, f"Running {getattr(step, 'name', str(step))}")
                    except Exception:
                        pass
                try:
                    step.execute(ctx)
                except Exception as e:
                    try:
                        ctx.log("Pipeline", "Error", f"Step {getattr(step,'name', '')} failed: {e}")
                    except Exception:
                        pass
            return {"automation": name, "dry_run": dry_run, "source": source, "results": getattr(ctx, "results", []), "files": len(files)}

        job = self.queue.submit(
            _automation_worker,
            params={"source": source, "dry_run": dry_run, **(params or {})},
            execute=True,
        )
        return {"job_id": job.job_id, "automation": name}

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
            "list_automations": self._handle_list_automations,
            "get_automation": self._handle_get_automation,
            "schedule_automation": self._handle_schedule_automation,
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
            execute=True,
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
            execute=True,
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
            execute=True,
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
                execute=True,
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
                execute=True,
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
                execute=True,
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
            execute=True,
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

    async def _handle_list_automations(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ``list_automations`` — list stored automations."""
        items = self.list_automations()
        return {"total": len(items), "automations": items}

    async def _handle_get_automation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ``get_automation`` — load one automation."""
        name = params.get("name", "")
        if not name:
            raise ValueError("name is required")
        data = self.get_automation(name)
        if data is None:
            return {"error": f"Automation not found: {name}"}
        return {"automation": data}

    async def _handle_schedule_automation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ``schedule_automation`` — schedule stored automation as job."""
        name = params.get("name", "")
        if not name:
            raise ValueError("name is required")
        source = params.get("source", "") or params.get("root", "")
        dry_run = bool(params.get("dry_run", True))
        result = self.schedule_automation(name, source=source, dry_run=dry_run)
        return result


EngineDaemon = Daemon

_daemon: Optional[Daemon] = None


def get_daemon() -> Daemon:
    """Get or create the global daemon singleton."""
    global _daemon
    if _daemon is None:
        _daemon = Daemon()
    return _daemon
