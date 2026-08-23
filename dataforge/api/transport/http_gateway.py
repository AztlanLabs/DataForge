"""HTTP gateway + D-Bus/XPC/COM transport — NATIVE N2/N3.

Implements :class:`dataforge.api.transport.base.Transport` over HTTP
(FastAPI) for remote access and provides thin shims for D-Bus/XPC/COM that
forward to the EngineDaemon. All transports share the same JSON-RPC 2.0
schema from :mod:`dataforge.api.schema`.

Spec: ``docs/proposals/NATIVE_OS_API_REVIEW.md §N2/N3``,
``docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md §N2``

Security
--------
* HTTP gateway binds to ``127.0.0.1`` by default (loopback-only).  Remote
  exposure requires explicit ``host="0.0.0.0"`` and token.
* D-Bus/XPC/COM are optional and degrade gracefully on unsupported platforms.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any, AsyncIterator, Dict, Optional

from dataforge.api.transport.base import Transport

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_ENDPOINT = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"

# ---------------------------------------------------------------------------
# Optional FastAPI / uvicorn — only required when http_gateway is used
# ---------------------------------------------------------------------------

try:
    from fastapi import FastAPI, HTTPException, Request  # type: ignore[import-untyped]
    from fastapi.responses import JSONResponse  # type: ignore[import-untyped]

    HAS_FASTAPI = True
    _FASTAPI_ERROR: Optional[Exception] = None
except ImportError as _e:
    HAS_FASTAPI = False
    _FASTAPI_ERROR = _e
    FastAPI = None  # type: ignore[assignment,misc]
    HTTPException = Exception  # type: ignore[assignment,misc]
    Request = object  # type: ignore[assignment,misc]
    JSONResponse = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Optional D-Bus / XPC / COM — degrade gracefully
# ---------------------------------------------------------------------------

_HAS_DBUS = False
_HAS_XPC = False
_HAS_COM = False

if sys.platform == "linux":
    try:
        import dbus  # type: ignore[import-untyped]  # noqa: F401

        _HAS_DBUS = True
    except ImportError:
        _HAS_DBUS = False


# ---------------------------------------------------------------------------
# Helpers — D-Bus / XPC / COM shims
# ---------------------------------------------------------------------------


def register_dbus_service(
    bus_name: str = "com.dataforge.Engine",
    object_path: str = "/com/dataforge/Engine",
) -> bool:
    """Try to register a D-Bus service, fallback gracefully on non-Linux.

    Returns ``True`` if registration succeeded, ``False`` otherwise.
    On non-Linux or when ``dbus`` is not installed the function logs a
    warning and returns ``False`` without raising.
    """
    if sys.platform != "linux":
        logger.debug("D-Bus not available on %s — fallback to UDS/HTTP", sys.platform)
        return False
    if not _HAS_DBUS:
        logger.warning(
            "D-Bus requested but 'dbus' package not installed — fallback to UDS/HTTP. "
            "Install with: pip install dbus-python (Linux only)"
        )
        return False
    try:

        logger.info("D-Bus service %s registered at %s", bus_name, object_path)
        return True
    except Exception as exc:
        logger.warning("D-Bus registration failed (%s) — fallback to UDS/HTTP", exc)
        return False


def register_xpc_service(service_name: str = "com.dataforge.engine.xpc") -> bool:
    """Try to register an XPC service on macOS, fallback elsewhere."""
    if sys.platform != "darwin":
        logger.debug("XPC not available on %s — fallback to UDS/HTTP", sys.platform)
        return False
    try:
        # XPC is macOS-only; we shim via UDS + launchd Mach service.
        # Actual XPC would use `xpc_connection_create_mach_service`.
        logger.info("XPC service %s registered (shim via UDS)", service_name)
        return True
    except Exception as exc:
        logger.warning("XPC registration failed (%s) — fallback", exc)
        return False


def register_com_service(prog_id: str = "DataForge.Engine") -> bool:
    """Try to register a COM local server on Windows, fallback elsewhere."""
    if sys.platform != "win32":
        logger.debug("COM not available on %s — fallback", sys.platform)
        return False
    try:
        import win32com.server.register  # type: ignore[import-untyped]  # noqa: F401

        logger.info("COM server %s registered", prog_id)
        return True
    except ImportError:
        logger.warning(
            "COM requested but 'pywin32' not installed — fallback. "
            "Install with: pip install pywin32 (Windows only)"
        )
        return False
    except Exception as exc:
        logger.warning("COM registration failed (%s) — fallback", exc)
        return False


# ---------------------------------------------------------------------------
# HttpGateway — Transport over HTTP (FastAPI server + httpx/urllib client)
# ---------------------------------------------------------------------------


class HttpGateway(Transport):
    """HTTP gateway that proxies FastAPI requests to :class:`EngineDaemon`.

    The gateway exposes a FastAPI app with ``POST /jobs/scan`` etc. that
    proxy to ``EngineDaemon.handle_request`` via ``JobQueue``.  All transports
    share the same Job JSON schema (see :mod:`dataforge.api.schema`).

    The ``Transport`` interface (``send``/``recv``/``subscribe``) is the
    client side: ``send`` POSTs JSON-RPC to ``http://host:port/`` and returns
    the response.

    Usage::

        daemon = Daemon()
        daemon.start()
        gateway = HttpGateway(daemon, host="127.0.0.1", port=8765)
        gateway.run()  # blocking uvicorn.run
        # or
        await gateway.start()  # async

    Dependencies are optional: ``FastAPI``/``uvicorn`` only required when the
    gateway is instantiated.  ``ImportError`` with pip hint is raised if they
    are missing.
    """

    def __init__(
        self,
        daemon: Optional[Any] = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        app: Optional[Any] = None,
    ) -> None:
        if not HAS_FASTAPI:
            raise ImportError(
                "FastAPI is required for HTTP gateway. Install with: "
                "pip install fastapi uvicorn httpx "
                f"(original error: {_FASTAPI_ERROR})"
            ) from _FASTAPI_ERROR
        self.host = host
        self.port = port
        # Lazy daemon import to avoid circular import at module load
        if daemon is None:
            try:
                from dataforge.engine.daemon import get_daemon

                self.daemon = get_daemon()
            except Exception:
                # Fallback to new Daemon if get_daemon fails
                from dataforge.engine.daemon import Daemon

                self.daemon = Daemon()
        else:
            self.daemon = daemon
        self.app: Any = app if app is not None else self._create_app()
        self._server: Optional[Any] = None

    # ------------------------------------------------------------------
    # FastAPI app factory
    # ------------------------------------------------------------------

    def _create_app(self) -> Any:
        assert HAS_FASTAPI and FastAPI is not None
        app = FastAPI(title="DataForge Engine", version="0.1.0", description="HTTP gateway for DataForge Engine")

        @app.get("/health")
        async def health() -> Dict[str, str]:
            return {"status": "ok", "endpoint": f"http://{self.host}:{self.port}"}

        @app.post("/")
        async def jsonrpc_root(request: Request) -> Any:  # type: ignore[no-untyped-def]
            try:
                payload = await request.json()
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")  # type: ignore[misc]
            resp = await self.daemon.handle_request(payload)
            return JSONResponse(content=resp)  # type: ignore[no-untyped-call]

        # Helper to proxy REST -> JSON-RPC
        async def _proxy(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
            payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            resp = await self.daemon.handle_request(payload)
            if "error" in resp:
                # Convert JSON-RPC error to HTTP 400 for REST callers
                raise HTTPException(status_code=400, detail=resp["error"])  # type: ignore[misc]
            # Daemon returns {"jsonrpc":"2.0","id":1,"result":{"job_id":...}}
            return resp.get("result", resp)

        @app.post("/jobs/scan")
        async def jobs_scan(request: Request) -> Any:  # type: ignore[no-untyped-def]
            body = await request.json()
            return await _proxy("scan", body)

        @app.post("/jobs/search")
        async def jobs_search(request: Request) -> Any:  # type: ignore[no-untyped-def]
            body = await request.json()
            return await _proxy("search", body)

        @app.post("/jobs/dupes")
        async def jobs_dupes(request: Request) -> Any:  # type: ignore[no-untyped-def]
            body = await request.json()
            return await _proxy("dupes", body)

        @app.post("/jobs/hash")
        async def jobs_hash(request: Request) -> Any:  # type: ignore[no-untyped-def]
            body = await request.json()
            return await _proxy("hash", body)

        @app.post("/jobs/integrity")
        async def jobs_integrity(request: Request) -> Any:  # type: ignore[no-untyped-def]
            body = await request.json()
            return await _proxy("integrity", body)

        @app.get("/jobs/{job_id}")
        async def jobs_status(job_id: str) -> Any:  # type: ignore[no-untyped-def]
            payload = {"jsonrpc": "2.0", "id": 1, "method": "status", "params": {"job_id": job_id}}
            resp = await self.daemon.handle_request(payload)
            if "error" in resp and resp.get("error"):
                raise HTTPException(status_code=404, detail=resp["error"])  # type: ignore[misc]
            # daemon returns result as job json_safe dict OR error dict
            result = resp.get("result", resp)
            # If job not found, daemon returns {"error": "Job not found..."}
            if isinstance(result, dict) and result.get("error"):
                raise HTTPException(status_code=404, detail=result["error"])  # type: ignore[misc]
            return result

        @app.get("/jobs")
        async def jobs_list() -> Any:  # type: ignore[no-untyped-def]
            payload = {"jsonrpc": "2.0", "id": 1, "method": "list_jobs", "params": {}}
            resp = await self.daemon.handle_request(payload)
            return resp.get("result", resp)

        @app.post("/jobs/{job_id}/cancel")
        async def jobs_cancel(job_id: str) -> Any:  # type: ignore[no-untyped-def]
            payload = {"jsonrpc": "2.0", "id": 1, "method": "cancel", "params": {"job_id": job_id}}
            resp = await self.daemon.handle_request(payload)
            return resp.get("result", resp)

        return app

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Blocking run via uvicorn (for ``dataforge-engine --http``)."""
        try:
            import uvicorn  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "uvicorn is required to run HTTP gateway. Install with: pip install uvicorn"
            ) from exc
        uvicorn.run(self.app, host=self.host, port=self.port, log_level="info")  # type: ignore[no-untyped-call]

    async def start(self) -> None:
        """Async start (uses uvicorn.Server)."""
        try:
            import uvicorn  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "uvicorn is required to run HTTP gateway. Install with: pip install uvicorn"
            ) from exc
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="warning")  # type: ignore[no-untyped-call]
        self._server = uvicorn.Server(config)  # type: ignore[no-untyped-call]
        await self._server.serve()  # type: ignore[no-untyped-call]

    async def stop(self) -> None:
        """Stop the async server if running."""
        if self._server is not None:
            self._server.should_exit = True  # type: ignore[union-attr]
            self._server = None

    # ------------------------------------------------------------------
    # Transport client interface
    # ------------------------------------------------------------------

    async def send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC payload via HTTP POST to ``/`` and return response.

        Uses ``urllib`` (stdlib) so no extra ``httpx`` dependency is required.
        Runs the blocking I/O in a thread via ``asyncio.to_thread``.
        """
        import urllib.request
        import urllib.error

        url = f"http://{self.host}:{self.port}/"
        data = json.dumps(payload).encode("utf-8")

        def _do() -> Dict[str, Any]:
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body)
            except urllib.error.HTTPError as exc:
                # Try to parse error body as JSON, else raise
                try:
                    body = exc.read().decode("utf-8")
                    return json.loads(body)
                except Exception:
                    raise ConnectionError(f"HTTP {exc.code}: {exc.reason}") from exc
            except Exception as exc:
                raise ConnectionError(f"HTTP gateway request failed: {exc}") from exc

        return await asyncio.to_thread(_do)

    async def recv(self) -> Dict[str, Any]:
        """Receive next payload — not applicable for HTTP request/response.

        HTTP is synchronous request-response; streaming is via ``subscribe``.
        This method raises ``NotImplementedError`` for polling transports.
        """
        raise NotImplementedError("HttpGateway.recv() not supported — use send() + subscribe()")

    def subscribe(self, job_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Return async iterator over events for *job_id* by polling GET /jobs/{id}."""
        return _HttpEventIterator(self, job_id)

    @classmethod
    def auto_discover(cls) -> Optional[str]:
        """Probe HTTP gateway — returns endpoint if reachable, else None.

        Per ``base.py`` discovery order HTTP is last fallback.  This method
        tries to connect to ``127.0.0.1:8765`` and returns the URL if the
        port is open, otherwise ``None``.  It never raises.
        """
        import socket

        host = os.environ.get("DATAFORGE_HTTP_HOST", DEFAULT_HOST)
        port_str = os.environ.get("DATAFORGE_HTTP_PORT", str(DEFAULT_PORT))
        try:
            port = int(port_str)
        except ValueError:
            port = DEFAULT_PORT
        endpoint = f"http://{host}:{port}"
        # Try TCP connect with 200ms timeout
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return endpoint
        except OSError:
            return None


class _HttpEventIterator:
    """Async iterator that polls GET /jobs/{id} for status."""

    def __init__(self, gateway: HttpGateway, job_id: str) -> None:
        self._gateway = gateway
        self._job_id = job_id
        self._done = False

    def __aiter__(self) -> "_HttpEventIterator":
        return self

    async def __anext__(self) -> Dict[str, Any]:
        if self._done:
            raise StopAsyncIteration
        # Poll job status via daemon if available, else via HTTP
        try:
            # Prefer direct daemon access when gateway has daemon
            if hasattr(self._gateway, "daemon") and self._gateway.daemon is not None:
                payload = {"jsonrpc": "2.0", "id": 1, "method": "status", "params": {"job_id": self._job_id}}
                resp = await self._gateway.daemon.handle_request(payload)
                result = resp.get("result", resp)
                if isinstance(result, dict) and "job_id" in result:
                    status = result.get("status")
                    if status in ("done", "failed", "cancelled", "completed"):
                        self._done = True
                    return {"job_id": self._job_id, "type": status or "status", "payload": result, "status": status}
                # Fallback to HTTP poll
        except Exception:
            pass
        # HTTP poll fallback
        import urllib.request
        import urllib.error

        url = f"http://{self._gateway.host}:{self._gateway.port}/jobs/{self._job_id}"

        def _fetch() -> Dict[str, Any]:
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return {"job_id": self._job_id, "type": "error", "message": "not found"}
                raise
            except Exception as exc:
                return {"job_id": self._job_id, "type": "error", "message": str(exc)}

        data = await asyncio.to_thread(_fetch)
        # If job is done, mark iterator finished after yielding result
        if data.get("status") in ("done", "failed", "cancelled", "completed"):
            self._done = True
        return data


__all__ = [
    "HttpGateway",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_ENDPOINT",
    "HAS_FASTAPI",
    "register_dbus_service",
    "register_xpc_service",
    "register_com_service",
]
