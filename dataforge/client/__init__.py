"""DataForge client — auto-discovering transport wrapper.

Provides :class:`DataForge`, the primary client entry point for
interacting with the DataForge engine.  ``DataForge.connect()``
auto-discovers the best available transport (UDS, Named Pipe, or
HTTP fallback) and returns a connected client.

Usage::

    from dataforge.client import DataForge

    # Async usage
    engine = await DataForge.connect()
    job = await engine.scan("/home/me", recursive=True)
    async for event in job.events():
        print(event)

    # In-process fallback (no daemon needed)
    engine = await DataForge.connect(in_process=True)

Spec: ``docs/proposals/NATIVE_OS_API_REVIEW.md §3.1``
Depends: TICK-205 (UDS/Named Pipe transports)
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, AsyncIterator, Dict, Optional

from dataforge.api.schema import JobEvent, JobStatus  # noqa: F401

logger = logging.getLogger(__name__)

__all__ = ["DataForge", "DataForgeJob", "DataForgeClient"]


class DataForgeJob:
    """Handle to a submitted engine job.

    Wraps the job ID and transport to provide status queries and
    event streaming.
    """

    def __init__(
        self,
        job_id: str,
        client: "DataForgeClient",
    ) -> None:
        self.job_id = job_id
        self._client = client

    async def status(self) -> Dict[str, Any]:
        """Query the current job status."""
        return await self._client._send_request("status", {"job_id": self.job_id})

    async def cancel(self) -> bool:
        """Cancel this job."""
        result = await self._client._send_request("cancel", {"job_id": self.job_id})
        return result.get("cancelled", False)

    def events(self) -> AsyncIterator[Dict[str, Any]]:
        """Return an async iterator over job events.

        Each yielded item is a ``JobEvent`` dict.  The iterator ends
        when a ``result`` or ``error`` event is received.
        """
        return _JobEventIterator(self._client, self.job_id)


class _JobEventIterator:
    """Async iterator that yields events for a specific job."""

    def __init__(self, client: "DataForgeClient", job_id: str) -> None:
        self._client = client
        self._job_id = job_id
        self._done = False

    def __aiter__(self) -> "_JobEventIterator":
        return self

    async def __anext__(self) -> Dict[str, Any]:
        if self._done:
            raise StopAsyncIteration
        # Poll for events via status request
        while True:
            result = await self._client._send_request("status", {"job_id": self._job_id})
            status = result.get("status", "")
            if status in ("done", "cancelled", "failed"):
                self._done = True
                # Return the final event
                return {
                    "job_id": self._job_id,
                    "type": "result" if status == "done" else "error",
                    "status": status,
                    "payload": result.get("results"),
                    "message": result.get("error", "done"),
                }
            await asyncio.sleep(0.1)


class DataForgeClient:
    """Low-level client that wraps a transport.

    Handles JSON-RPC 2.0 request/response over the connected transport.
    """

    def __init__(self, transport: Any) -> None:
        self._transport = transport
        self._request_id = 0

    async def _send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a JSON-RPC 2.0 request and return the result."""
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }
        response = await self._transport.send(payload)
        if "error" in response:
            error = response["error"]
            raise RuntimeError(f"Engine error: {error.get('message', error)}")
        return response.get("result", {})

    async def close(self) -> None:
        """Close the transport connection."""
        if hasattr(self._transport, "close"):
            await self._transport.close()


class DataForge:
    """Primary client entry point for the DataForge engine.

    ``DataForge.connect()`` auto-discovers the best available transport
    and returns a connected :class:`DataForgeClient`.

    Usage::

        # Auto-discover daemon
        engine = await DataForge.connect()

        # In-process fallback
        engine = await DataForge.connect(in_process=True)

        # Explicit transport
        from dataforge.api.transport.uds import UdsTransport
        transport = UdsTransport("/run/user/1000/dataforge/engine.sock")
        engine = DataForge(transport)
    """

    def __init__(self, transport: Any) -> None:
        self._client = DataForgeClient(transport)

    @classmethod
    async def connect(
        cls,
        in_process: bool = False,
        transport: Optional[Any] = None,
    ) -> "DataForge":
        """Connect to the DataForge engine.

        Args:
            in_process: If True, use the in-process engine (no daemon).
            transport: Explicit transport to use (skips auto-discovery).

        Returns:
            A connected DataForge client.
        """
        if in_process:
            return cls._connect_in_process()

        if transport is not None:
            client = cls(transport)
            if hasattr(transport, "connect"):
                await transport.connect()
            return client

        # Auto-discover
        discovered = cls._auto_discover_transport()
        if discovered is not None:
            transport = discovered
            client = cls(transport)
            if hasattr(transport, "connect"):
                await transport.connect()
            return client

        # Fallback to in-process
        logger.info("No daemon found, falling back to in-process engine")
        return cls._connect_in_process()

    @classmethod
    def _connect_in_process(cls) -> "DataForge":
        """Create an in-process client using the Daemon directly."""
        from dataforge.engine.daemon import Daemon

        daemon = Daemon()
        daemon.start()
        return cls(_InProcessTransport(daemon))

    @classmethod
    def _auto_discover_transport(cls) -> Optional[Any]:
        """Auto-discover the best available transport.

        Order per NATIVE_OS_API_REVIEW.md §3.1:
        1. $DATAFORGE_ENGINE_SOCK (explicit)
        2. $XDG_RUNTIME_DIR/dataforge/engine.sock
        3. ~/Library/Application Support/DataForge/engine.sock
        4. \\\\.\\pipe\\dataforge-engine
        5. http://127.0.0.1:8765 (HTTP fallback)
        """
        import os

        # 1. Explicit env
        explicit = os.environ.get("DATAFORGE_ENGINE_SOCK")
        if explicit and os.path.exists(explicit):
            try:
                from dataforge.api.transport.uds import UdsTransport
                return UdsTransport(explicit)
            except ImportError:
                pass

        # 2. XDG_RUNTIME_DIR
        xdg = os.environ.get("XDG_RUNTIME_DIR")
        if xdg:
            sock_path = os.path.join(xdg, "dataforge", "engine.sock")
            if os.path.exists(sock_path):
                try:
                    from dataforge.api.transport.uds import UdsTransport
                    return UdsTransport(sock_path)
                except ImportError:
                    pass

        # 3. macOS Application Support
        mac_sock = os.path.join(
            os.path.expanduser("~"),
            "Library", "Application Support", "DataForge", "engine.sock",
        )
        if os.path.exists(mac_sock):
            try:
                from dataforge.api.transport.uds import UdsTransport
                return UdsTransport(mac_sock)
            except ImportError:
                pass

        # 4. Windows Named Pipe
        if sys.platform == "win32":
            try:
                from dataforge.api.transport.named_pipe import NamedPipeTransport
                transport = NamedPipeTransport()
                # Try to probe the pipe
                if transport.auto_discover():
                    return transport
            except (ImportError, OSError):
                pass

        # 5. HTTP fallback — not implemented yet (requires HTTP transport)
        return None

    # ------------------------------------------------------------------
    # High-level API
    # ------------------------------------------------------------------

    async def scan(self, root: str, **kwargs: Any) -> DataForgeJob:
        """Submit a scan job."""
        result = await self._client._send_request("scan", {"root": root, **kwargs})
        return DataForgeJob(result["job_id"], self._client)

    async def search(self, root: str, **kwargs: Any) -> DataForgeJob:
        """Submit a search job."""
        result = await self._client._send_request("search", {"root": root, **kwargs})
        return DataForgeJob(result["job_id"], self._client)

    async def dupes(self, root: str, **kwargs: Any) -> DataForgeJob:
        """Submit a duplicate detection job."""
        result = await self._client._send_request("dupes", {"root": root, **kwargs})
        return DataForgeJob(result["job_id"], self._client)

    async def hash(self, path: str, **kwargs: Any) -> DataForgeJob:
        """Submit a hash job."""
        result = await self._client._send_request("hash", {"path": path, **kwargs})
        return DataForgeJob(result["job_id"], self._client)

    async def integrity(self, path: str, snapshot: str, **kwargs: Any) -> DataForgeJob:
        """Submit an integrity job."""
        result = await self._client._send_request(
            "integrity", {"path": path, "snapshot": snapshot, **kwargs}
        )
        return DataForgeJob(result["job_id"], self._client)

    async def list_jobs(self) -> Dict[str, Any]:
        """List all jobs."""
        return await self._client._send_request("list_jobs", {})

    async def close(self) -> None:
        """Close the client connection."""
        await self._client.close()


class _InProcessTransport:
    """Transport that delegates directly to the Daemon (no IPC).

    Used when ``DataForge.connect(in_process=True)`` is called.
    """

    def __init__(self, daemon: Any) -> None:
        self._daemon = daemon

    async def send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle request directly via the daemon."""
        return await self._daemon.handle_request(payload)

    async def recv(self) -> Dict[str, Any]:
        raise NotImplementedError("InProcessTransport does not support recv()")

    def subscribe(self, job_id: str) -> AsyncIterator[Dict[str, Any]]:
        raise NotImplementedError("InProcessTransport does not support subscribe()")

    async def close(self) -> None:
        """Stop the daemon."""
        self._daemon.stop()
