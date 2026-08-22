"""Unix Domain Socket transport — Linux / macOS primary local IPC.

Implements :class:`dataforge.api.transport.base.Transport` over
``asyncio.start_unix_server`` / ``asyncio.open_unix_connection`` with
length-prefixed MessagePack framing and JSON-RPC 2.0 payloads.

Security:
* Socket created with ``0o700`` (owner-only).
* Server checks ``SO_PEERCRED`` (Linux) or ``LOCAL_PEERCRED`` (macOS) to
  verify the connecting UID matches the process UID.

Spec: ``docs/proposals/NATIVE_OS_API_REVIEW.md §2–3``
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import struct
import sys
from typing import Any, AsyncIterator, Dict, Optional

import msgpack

from dataforge.api.transport.base import Transport

logger = logging.getLogger(__name__)

_FRAME_HEADER = struct.Struct(">I")  # 4-byte big-endian length prefix
_MAX_FRAME = 16 * 1024 * 1024  # 16 MiB safety cap


# ------------------------------------------------------------------
# Framing helpers
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
# Peer credential check (Linux SO_PEERCRED / macOS LOCAL_PEERCRED)
# ------------------------------------------------------------------

def _check_peer_credentials(sock: socket.socket) -> bool:
    """Return True if the peer UID matches the process UID.

    On Linux uses ``SO_PEERCRED`` (``struct ucred``).
    On macOS uses ``LOCAL_PEERCRED`` (``struct xucred``).
    On other platforms returns True (no check).
    """
    if sys.platform == "linux":
        try:
            import struct as _struct
            ucred = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _struct.calcsize("iii"))
            peer_pid, peer_uid, _peer_gid = _struct.unpack("iii", ucred)
            return peer_uid == os.getuid()
        except (OSError, AttributeError):
            return False
    elif sys.platform == "darwin":
        try:
            import struct as _struct
            LOCAL_PEERCRED = 0x001
            xucred = sock.getsockopt(socket.SOL_LOCAL, LOCAL_PEERCRED, 12)
            # xucred: uint32 version, uid_t uid, short ngids, gid_t gid[1]
            _version, peer_uid = _struct.unpack_from("Ii", xucred, 0)
            return peer_uid == os.getuid()
        except (OSError, AttributeError):
            return False
    return True  # no check on other platforms


# ------------------------------------------------------------------
# UDS Client
# ------------------------------------------------------------------

class UdsTransport(Transport):
    """Unix Domain Socket client transport.

    Connects to a UDS endpoint and exchanges length-prefixed MessagePack
    JSON-RPC 2.0 frames.
    """

    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False

    async def connect(self) -> None:
        """Open the connection to the UDS endpoint."""
        if self._connected:
            return
        self._reader, self._writer = await asyncio.open_unix_connection(self._socket_path)
        self._connected = True

    async def close(self) -> None:
        """Close the connection."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
        self._reader = None
        self._writer = None
        self._connected = False

    async def send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC request and return the response."""
        if not self._connected:
            await self.connect()
        assert self._writer is not None and self._reader is not None
        await _send_frame(self._writer, _pack(payload))
        data = await _recv_frame(self._reader)
        if data is None:
            raise ConnectionError("Server closed connection")
        return _unpack(data)

    async def recv(self) -> Dict[str, Any]:
        """Receive the next frame from the server."""
        if not self._connected:
            await self.connect()
        assert self._reader is not None
        data = await _recv_frame(self._reader)
        if data is None:
            raise ConnectionError("Server closed connection")
        return _unpack(data)

    def subscribe(self, job_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Return an async iterator over event frames for *job_id*."""
        return _UdsEventIterator(self, job_id)

    @classmethod
    def auto_discover(cls) -> Optional[str]:
        """Probe well-known UDS endpoints in discovery order.

        Returns the first reachable socket path, or ``None``.
        """
        for ep in cls._discover_endpoints():
            if ep.startswith("http") or ep.startswith("\\\\"):
                break  # UDS candidates come before HTTP/pipe
            if os.path.exists(ep):
                return ep
        return None

    @classmethod
    def create_server(
        cls,
        socket_path: str,
        handler: Any,
    ) -> "UdsServer":
        """Create a UDS server bound to *socket_path*.

        *handler* is an async callable ``(payload: dict) -> dict`` that
        processes each incoming JSON-RPC request.
        """
        return UdsServer(socket_path, handler)


# ------------------------------------------------------------------
# Async iterator for subscribe()
# ------------------------------------------------------------------

class _UdsEventIterator:
    """Async iterator that yields event frames for a specific job."""

    def __init__(self, transport: UdsTransport, job_id: str) -> None:
        self._transport = transport
        self._job_id = job_id

    def __aiter__(self) -> "_UdsEventIterator":
        return self

    async def __anext__(self) -> Dict[str, Any]:
        while True:
            frame = await self._transport.recv()
            if frame.get("job_id") == self._job_id:
                return frame
            # If the frame signals end-of-stream for this job, stop
            if frame.get("type") in ("result", "error") and frame.get("job_id") == self._job_id:
                raise StopAsyncIteration


# ------------------------------------------------------------------
# UDS Server
# ------------------------------------------------------------------

class UdsServer:
    """Async UDS server that listens on a Unix domain socket.

    Usage::

        async def handler(payload):
            return {"jsonrpc": "2.0", "id": payload.get("id"), "result": "ok"}

        server = UdsServer("/tmp/engine.sock", handler)
        await server.start()
        # ... server runs until stopped ...
        await server.stop()
    """

    def __init__(
        self,
        socket_path: str,
        handler: Any,
    ) -> None:
        self._socket_path = socket_path
        self._handler = handler
        self._server: Optional[asyncio.AbstractServer] = None

    async def start(self) -> None:
        """Start listening on the UDS socket with 0700 permissions."""
        # Remove stale socket file
        try:
            os.unlink(self._socket_path)
        except FileNotFoundError:
            pass

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=self._socket_path,
        )
        # Set 0700 permissions (owner-only)
        os.chmod(self._socket_path, 0o700)
        logger.info("UDS server listening on %s (0700)", self._socket_path)

    async def stop(self) -> None:
        """Stop the server and clean up the socket."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        try:
            os.unlink(self._socket_path)
        except FileNotFoundError:
            pass
        logger.info("UDS server stopped")

    async def _handle_client(
        self,
        reader: asyncio.StreamWriter,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single client connection."""
        # Peer credential check
        transport_obj = writer.transport
        sock = transport_obj.get_extra_info("socket")
        if sock is not None and not _check_peer_credentials(sock):
            logger.warning("Rejected connection: peer credential mismatch")
            writer.close()
            return

        try:
            while True:
                data = await _recv_frame(reader)
                if data is None:
                    break
                payload = _unpack(data)
                try:
                    response = await self._handler(payload)
                except Exception as exc:
                    response = {
                        "jsonrpc": "2.0",
                        "id": payload.get("id"),
                        "error": {"code": -32603, "message": str(exc)},
                    }
                await _send_frame(writer, _pack(response))
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except OSError:
                pass


__all__ = ["UdsTransport", "UdsServer"]
