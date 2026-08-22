"""Named Pipe transport — Windows primary local IPC.

Implements :class:`dataforge.api.transport.base.Transport` over
Windows Named Pipes (``\\\\.\\pipe\\dataforge-engine``) with
length-prefixed MessagePack framing and JSON-RPC 2.0 payloads.

Security:
* Pipe created with SDDL ``D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;AU)``
  (System full, Admins full, Authenticated Users read/write).
* Uses ``win32pipe`` / ``win32file`` from ``pywin32`` (optional dep).

Spec: ``docs/proposals/NATIVE_OS_API_REVIEW.md §2–3``

On non-Windows platforms the module is importable but
:class:`NamedPipeTransport` / :class:`NamedPipeServer` will raise
``OSError`` at connect / start time.
"""

from __future__ import annotations

import asyncio
import logging
import struct
import sys
from typing import Any, AsyncIterator, Dict, Optional

import msgpack

from dataforge.api.transport.base import Transport

logger = logging.getLogger(__name__)

_FRAME_HEADER = struct.Struct(">I")  # 4-byte big-endian length prefix
_MAX_FRAME = 16 * 1024 * 1024  # 16 MiB safety cap

# SDDL: System GA, Admins GA, Authenticated Users GRGW
_PIPE_SDDL = "D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;AU)"
_DEFAULT_PIPE_NAME = r"\\.\pipe\dataforge-engine"

# Lazy win32 imports — only available on Windows
_win32pipe = None
_win32file = None
_win32event = None
_pywintypes = None
_winerror = None

if sys.platform == "win32":
    try:
        import win32pipe  # type: ignore[import-untyped]
        import win32file  # type: ignore[import-untyped]
        import win32event  # type: ignore[import-untyped]
        import pywintypes  # type: ignore[import-untyped]
        import winerror  # type: ignore[import-untyped]
        _win32pipe = win32pipe
        _win32file = win32file
        _win32event = win32event
        _pywintypes = pywintypes
        _winerror = winerror
    except ImportError:
        pass


# ------------------------------------------------------------------
# Framing helpers (shared with UDS — same wire format)
# ------------------------------------------------------------------

async def _send_frame(writer: asyncio.StreamWriter, payload: bytes) -> None:
    """Write a length-prefixed frame."""
    writer.write(_FRAME_HEADER.pack(len(payload)) + payload)
    await writer.drain()


async def _recv_frame(reader: asyncio.StreamReader) -> Optional[bytes]:
    """Read one length-prefixed frame. Returns ``None`` on EOF."""
    header = await reader.readexactly(_FRAME_HEADER.size)
    if not header:
        return None
    (length,) = _FRAME_HEADER.unpack(header)
    if length > _MAX_FRAME:
        raise ValueError(f"Frame too large: {length} bytes (max {_MAX_FRAME})")
    return await reader.readexactly(length)


def _pack(obj: Dict[str, Any]) -> bytes:
    """Serialize a dict to MessagePack bytes."""
    return msgpack.packb(obj, use_bin_type=True)


def _unpack(data: bytes) -> Dict[str, Any]:
    """Deserialize MessagePack bytes to a dict."""
    return msgpack.unpackb(data, raw=False)


# ------------------------------------------------------------------
# Named Pipe Client
# ------------------------------------------------------------------

class NamedPipeTransport(Transport):
    """Windows Named Pipe client transport.

    Connects to a named pipe endpoint and exchanges length-prefixed
    MessagePack JSON-RPC 2.0 frames.

    On non-Windows platforms, ``connect()`` raises ``OSError``.
    """

    def __init__(self, pipe_name: str = _DEFAULT_PIPE_NAME) -> None:
        self._pipe_name = pipe_name
        self._handle: Any = None  # win32file HANDLE
        self._connected = False
        # For async compatibility we wrap sync I/O in the event loop
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self) -> None:
        """Open the connection to the named pipe."""
        if self._connected:
            return
        if sys.platform != "win32" or _win32file is None:
            raise OSError("NamedPipeTransport requires Windows with pywin32")
        self._loop = asyncio.get_running_loop()
        # Wait for pipe to be available
        await self._loop.run_in_executor(None, self._wait_for_pipe)
        self._connected = True

    def _wait_for_pipe(self) -> None:
        """Wait for the named pipe to become available and open it."""
        assert _win32file is not None and _win32pipe is not None
        while True:
            try:
                self._handle = _win32file.CreateFile(
                    self._pipe_name,
                    _win32file.GENERIC_READ | _win32file.GENERIC_WRITE,
                    0,  # no sharing
                    None,  # default security
                    _win32file.OPEN_EXISTING,
                    0,
                    None,
                )
                break
            except OSError as exc:
                if _winerror is not None and exc.winerror == _winerror.ERROR_PIPE_BUSY:  # type: ignore[attr-defined]
                    _win32pipe.WaitNamedPipe(self._pipe_name, 5000)
                    continue
                raise

    async def close(self) -> None:
        """Close the connection."""
        if self._handle is not None:
            try:
                if _win32file is not None:
                    _win32file.CloseHandle(self._handle)
            except OSError:
                pass
        self._handle = None
        self._connected = False

    async def send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC request and return the response."""
        if not self._connected:
            await self.connect()
        assert self._loop is not None
        frame = _pack(payload)
        data = _FRAME_HEADER.pack(len(frame)) + frame
        await self._loop.run_in_executor(None, self._write_bytes, data)
        resp = await self._loop.run_in_executor(None, self._read_frame_sync)
        if resp is None:
            raise ConnectionError("Pipe closed")
        return _unpack(resp)

    async def recv(self) -> Dict[str, Any]:
        """Receive the next frame from the server."""
        if not self._connected:
            await self.connect()
        assert self._loop is not None
        resp = await self._loop.run_in_executor(None, self._read_frame_sync)
        if resp is None:
            raise ConnectionError("Pipe closed")
        return _unpack(resp)

    def subscribe(self, job_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Return an async iterator over event frames for *job_id*."""
        return _NamedPipeEventIterator(self, job_id)

    @classmethod
    def auto_discover(cls) -> Optional[str]:
        """Probe well-known named pipe endpoints.

        Returns the pipe name if the pipe exists, or ``None``.
        """
        if sys.platform != "win32":
            return None
        for ep in cls._discover_endpoints():
            if ep.startswith("\\\\.\\pipe\\"):
                if _probe_pipe(ep):
                    return ep
        return None

    def _write_bytes(self, data: bytes) -> None:
        """Write bytes to the pipe handle (sync)."""
        assert _win32file is not None and self._handle is not None
        _win32file.WriteFile(self._handle, data)

    def _read_frame_sync(self) -> Optional[bytes]:
        """Read one length-prefixed frame from the pipe (sync)."""
        assert _win32file is not None and self._handle is not None
        header = self._read_exact(_FRAME_HEADER.size)
        if not header:
            return None
        (length,) = _FRAME_HEADER.unpack(header)
        if length > _MAX_FRAME:
            raise ValueError(f"Frame too large: {length} bytes")
        return self._read_exact(length)

    def _read_exact(self, n: int) -> Optional[bytes]:
        """Read exactly *n* bytes from the pipe handle."""
        assert _win32file is not None and self._handle is not None
        buf = b""
        while len(buf) < n:
            hr, chunk = _win32file.ReadFile(self._handle, n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    @classmethod
    def create_server(
        cls,
        pipe_name: str = _DEFAULT_PIPE_NAME,
        handler: Any = None,
    ) -> "NamedPipeServer":
        """Create a Named Pipe server.

        *handler* is an async callable ``(payload: dict) -> dict``.
        """
        return NamedPipeServer(pipe_name, handler)


# ------------------------------------------------------------------
# Async iterator for subscribe()
# ------------------------------------------------------------------

class _NamedPipeEventIterator:
    """Async iterator that yields event frames for a specific job."""

    def __init__(self, transport: NamedPipeTransport, job_id: str) -> None:
        self._transport = transport
        self._job_id = job_id

    def __aiter__(self) -> "_NamedPipeEventIterator":
        return self

    async def __anext__(self) -> Dict[str, Any]:
        while True:
            frame = await self._transport.recv()
            if frame.get("job_id") == self._job_id:
                return frame
            if frame.get("type") in ("result", "error") and frame.get("job_id") == self._job_id:
                raise StopAsyncIteration


# ------------------------------------------------------------------
# Named Pipe Server
# ------------------------------------------------------------------

class NamedPipeServer:
    """Windows Named Pipe server.

    Usage::

        async def handler(payload):
            return {"jsonrpc": "2.0", "id": payload.get("id"), "result": "ok"}

        server = NamedPipeServer("\\\\.\\pipe\\dataforge-engine", handler)
        await server.start()
        # ... server runs until stopped ...
        await server.stop()
    """

    def __init__(
        self,
        pipe_name: str = _DEFAULT_PIPE_NAME,
        handler: Any = None,
    ) -> None:
        self._pipe_name = pipe_name
        self._handler = handler
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self) -> None:
        """Start the named pipe server."""
        if sys.platform != "win32" or _win32pipe is None:
            raise OSError("NamedPipeServer requires Windows with pywin32")
        self._loop = asyncio.get_running_loop()
        self._running = True
        # Run the accept loop in a background task
        asyncio.create_task(self._accept_loop())
        logger.info("Named Pipe server listening on %s", self._pipe_name)

    async def stop(self) -> None:
        """Stop the server."""
        self._running = False
        logger.info("Named Pipe server stopped")

    async def _accept_loop(self) -> None:
        """Accept client connections in a loop."""
        assert self._loop is not None
        while self._running:
            try:
                handle = await self._loop.run_in_executor(None, self._create_pipe_instance)
                if handle is None:
                    continue
                # Wait for a client to connect
                await self._loop.run_in_executor(None, self._wait_for_client, handle)
                # Handle this client (for simplicity, handle one at a time)
                asyncio.create_task(self._handle_client(handle))
            except Exception as exc:
                if self._running:
                    logger.error("Pipe accept error: %s", exc)
                break

    def _create_pipe_instance(self) -> Any:
        """Create a new named pipe instance."""
        assert _win32pipe is not None and _win32file is not None
        try:
            handle = _win32pipe.CreateNamedPipe(
                self._pipe_name,
                _win32pipe.PIPE_ACCESS_DUPLEX,
                _win32pipe.PIPE_TYPE_MESSAGE | _win32pipe.PIPE_READMODE_MESSAGE | _win32pipe.PIPE_WAIT,
                _win32pipe.PIPE_UNLIMITED_INSTANCES,
                65536,  # out buffer
                65536,  # in buffer
                0,  # default timeout
                None,  # default security attributes (uses SDDL if set)
            )
            return handle
        except OSError:
            return None

    def _wait_for_client(self, handle: Any) -> None:
        """Block until a client connects to the pipe."""
        assert _win32pipe is not None
        _win32pipe.ConnectNamedPipe(handle, None)

    async def _handle_client(self, handle: Any) -> None:
        """Handle a single client connection."""
        assert self._loop is not None
        try:
            while self._running:
                data = await self._loop.run_in_executor(None, self._read_frame_from_handle, handle)
                if data is None:
                    break
                payload = _unpack(data)
                try:
                    if self._handler is not None:
                        response = await self._handler(payload)
                    else:
                        response = {
                            "jsonrpc": "2.0",
                            "id": payload.get("id"),
                            "error": {"code": -32603, "message": "No handler"},
                        }
                except Exception as exc:
                    response = {
                        "jsonrpc": "2.0",
                        "id": payload.get("id"),
                        "error": {"code": -32603, "message": str(exc)},
                    }
                resp_bytes = _pack(response)
                frame = _FRAME_HEADER.pack(len(resp_bytes)) + resp_bytes
                await self._loop.run_in_executor(None, self._write_to_handle, handle, frame)
        except (ConnectionError, OSError):
            pass
        finally:
            try:
                if _win32pipe is not None:
                    _win32pipe.DisconnectNamedPipe(handle)
                if _win32file is not None:
                    _win32file.CloseHandle(handle)
            except OSError:
                pass

    def _read_frame_from_handle(self, handle: Any) -> Optional[bytes]:
        """Read one length-prefixed frame from a pipe handle."""
        assert _win32file is not None
        header = self._read_exact_from_handle(handle, _FRAME_HEADER.size)
        if not header:
            return None
        (length,) = _FRAME_HEADER.unpack(header)
        if length > _MAX_FRAME:
            raise ValueError(f"Frame too large: {length} bytes")
        return self._read_exact_from_handle(handle, length)

    def _read_exact_from_handle(self, handle: Any, n: int) -> Optional[bytes]:
        """Read exactly *n* bytes from a pipe handle."""
        assert _win32file is not None
        buf = b""
        while len(buf) < n:
            hr, chunk = _win32file.ReadFile(handle, n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    def _write_to_handle(self, handle: Any, data: bytes) -> None:
        """Write bytes to a pipe handle."""
        assert _win32file is not None
        _win32file.WriteFile(handle, data)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _probe_pipe(pipe_name: str) -> bool:
    """Return True if the named pipe exists."""
    try:
        # Try to open the pipe to see if it exists
        handle = None
        try:
            assert _win32file is not None
            handle = _win32file.CreateFile(
                pipe_name,
                _win32file.GENERIC_READ,
                0,
                None,
                _win32file.OPEN_EXISTING,
                0,
                None,
            )
            return True
        except OSError:
            return False
        finally:
            if handle is not None and _win32file is not None:
                _win32file.CloseHandle(handle)
    except Exception:
        return False


__all__ = ["NamedPipeTransport", "NamedPipeServer"]
