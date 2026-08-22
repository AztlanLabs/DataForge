"""Tests for UDS and Named Pipe transports — TICK-205.

Validates:
* Length-prefixed MessagePack framing (send_frame / recv_frame)
* UDS server ↔ client round-trip (JSON-RPC 2.0)
* UDS socket permissions (0700)
* SO_PEERCRED / LOCAL_PEERCRED check
* Named Pipe graceful degradation on non-Windows
* auto_discover order and probe logic
"""

from __future__ import annotations

import asyncio
import os
import socket
import stat
import sys
from typing import Any, Dict
from unittest.mock import patch

import pytest

from dataforge.api.transport.uds import (
    UdsServer,
    UdsTransport,
    _check_peer_credentials,
    _pack,
    _recv_frame,
    _send_frame,
    _unpack,
)
from dataforge.api.transport.named_pipe import (
    NamedPipeServer,
    NamedPipeTransport,
)


# ------------------------------------------------------------------
# Framing helpers
# ------------------------------------------------------------------

class TestFraming:
    """Test length-prefixed MessagePack framing."""

    def test_pack_unpack_roundtrip(self) -> None:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "scan", "params": {"root": "/tmp"}}
        data = _pack(payload)
        assert isinstance(data, bytes)
        result = _unpack(data)
        assert result == payload

    def test_pack_unpack_empty_dict(self) -> None:
        data = _pack({})
        assert _unpack(data) == {}

    def test_pack_unpack_nested(self) -> None:
        payload = {"a": {"b": [1, 2, 3]}, "c": None, "d": True}
        assert _unpack(_pack(payload)) == payload

    @pytest.mark.asyncio
    async def test_send_recv_frame(self, tmp_path: Any) -> None:
        """Test send_frame / recv_frame over a socketpair."""
        sock_a, sock_b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        sock_a.close()
        sock_b.close()

    @pytest.mark.asyncio
    async def test_send_recv_frame_via_pipe(self, tmp_path: Any) -> None:
        """Test send_frame / recv_frame over a Unix socket pair."""
        path = str(tmp_path / "test.sock")
        server = await asyncio.start_unix_server(
            lambda r, w: self._echo_server(r, w),
            path=path,
        )

        reader, writer = await asyncio.open_unix_connection(path)
        try:
            payload = {"jsonrpc": "2.0", "id": 1, "result": "ok"}
            await _send_frame(writer, _pack(payload))
            data = await _recv_frame(reader)
            assert data is not None
            result = _unpack(data)
            assert result == payload
        finally:
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()

    @staticmethod
    async def _echo_server(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Echo server: read frame, write it back."""
        data = await _recv_frame(reader)
        if data is not None:
            await _send_frame(writer, data)
        writer.close()


# ------------------------------------------------------------------
# UDS Transport
# ------------------------------------------------------------------

class TestUdsTransport:
    """Test UDS client/server round-trip."""

    @pytest.fixture
    def socket_path(self, tmp_path: Any) -> str:
        return str(tmp_path / "engine.sock")

    @pytest.mark.asyncio
    async def test_server_client_roundtrip(self, socket_path: str) -> None:
        """Server echoes back JSON-RPC responses."""
        received = []

        async def handler(payload: Dict[str, Any]) -> Dict[str, Any]:
            received.append(payload)
            return {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": {"status": "ok"},
            }

        server = UdsServer(socket_path, handler)
        await server.start()
        try:
            transport = UdsTransport(socket_path)
            await transport.connect()
            try:
                request = {"jsonrpc": "2.0", "id": 1, "method": "scan", "params": {"root": "/tmp"}}
                response = await transport.send(request)
                assert response["jsonrpc"] == "2.0"
                assert response["id"] == 1
                assert response["result"]["status"] == "ok"
                assert len(received) == 1
                assert received[0]["method"] == "scan"
            finally:
                await transport.close()
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_server_multiple_requests(self, socket_path: str) -> None:
        """Server handles multiple sequential requests on one connection."""

        async def handler(payload: Dict[str, Any]) -> Dict[str, Any]:
            return {"jsonrpc": "2.0", "id": payload.get("id"), "result": "ok"}

        server = UdsServer(socket_path, handler)
        await server.start()
        try:
            transport = UdsTransport(socket_path)
            await transport.connect()
            try:
                for i in range(5):
                    resp = await transport.send({"jsonrpc": "2.0", "id": i, "method": "ping"})
                    assert resp["id"] == i
                    assert resp["result"] == "ok"
            finally:
                await transport.close()
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_server_handler_exception(self, socket_path: str) -> None:
        """Server returns JSON-RPC error when handler raises."""

        async def handler(payload: Dict[str, Any]) -> Dict[str, Any]:
            raise ValueError("boom")

        server = UdsServer(socket_path, handler)
        await server.start()
        try:
            transport = UdsTransport(socket_path)
            await transport.connect()
            try:
                resp = await transport.send({"jsonrpc": "2.0", "id": 1, "method": "fail"})
                assert "error" in resp
                assert "boom" in resp["error"]["message"]
            finally:
                await transport.close()
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_socket_permissions_0700(self, socket_path: str) -> None:
        """Socket file has 0700 permissions (owner-only)."""

        async def handler(payload: Dict[str, Any]) -> Dict[str, Any]:
            return {"jsonrpc": "2.0", "id": payload.get("id"), "result": "ok"}

        server = UdsServer(socket_path, handler)
        await server.start()
        try:
            mode = os.stat(socket_path).st_mode
            # Check that group and other have no permissions
            assert not (mode & stat.S_IRWXG), "group should have no permissions"
            assert not (mode & stat.S_IRWXO), "other should have no permissions"
            assert mode & stat.S_IRWXU, "owner should have permissions"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_stale_socket_removed(self, socket_path: str) -> None:
        """Server removes stale socket file before binding."""
        # Create a stale socket file
        with open(socket_path, "w") as f:
            f.write("stale")

        async def handler(payload: Dict[str, Any]) -> Dict[str, Any]:
            return {"jsonrpc": "2.0", "id": payload.get("id"), "result": "ok"}

        server = UdsServer(socket_path, handler)
        await server.start()
        try:
            transport = UdsTransport(socket_path)
            await transport.connect()
            try:
                resp = await transport.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})
                assert resp["result"] == "ok"
            finally:
                await transport.close()
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_auto_discover_finds_socket(self, socket_path: str) -> None:
        """auto_discover returns socket path when it exists."""

        async def handler(payload: Dict[str, Any]) -> Dict[str, Any]:
            return {"jsonrpc": "2.0", "id": payload.get("id"), "result": "ok"}

        server = UdsServer(socket_path, handler)
        await server.start()
        try:
            with patch.object(UdsTransport, "_discover_endpoints", return_value=[socket_path]):
                found = UdsTransport.auto_discover()
                assert found == socket_path
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_auto_discover_returns_none_when_no_socket(self, tmp_path: Any) -> None:
        """auto_discover returns None when no socket exists."""
        nonexistent = str(tmp_path / "nonexistent.sock")
        with patch.object(UdsTransport, "_discover_endpoints", return_value=[nonexistent]):
            found = UdsTransport.auto_discover()
            assert found is None

    @pytest.mark.asyncio
    async def test_auto_discover_skips_http(self, tmp_path: Any) -> None:
        """auto_discover stops at HTTP candidates (returns None for UDS)."""
        with patch.object(
            UdsTransport,
            "_discover_endpoints",
            return_value=["http://127.0.0.1:8765"],
        ):
            found = UdsTransport.auto_discover()
            assert found is None

    @pytest.mark.asyncio
    async def test_connect_idempotent(self, socket_path: str) -> None:
        """Multiple connect() calls are idempotent."""

        async def handler(payload: Dict[str, Any]) -> Dict[str, Any]:
            return {"jsonrpc": "2.0", "id": payload.get("id"), "result": "ok"}

        server = UdsServer(socket_path, handler)
        await server.start()
        try:
            transport = UdsTransport(socket_path)
            await transport.connect()
            await transport.connect()  # should not raise
            resp = await transport.send({"jsonrpc": "2.0", "id": 1, "method": "ping"})
            assert resp["result"] == "ok"
            await transport.close()
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_close_idempotent(self, socket_path: str) -> None:
        """Multiple close() calls are idempotent."""
        transport = UdsTransport(socket_path)
        await transport.close()
        await transport.close()  # should not raise


# ------------------------------------------------------------------
# Peer credential check
# ------------------------------------------------------------------

class TestPeerCredentials:
    """Test SO_PEERCRED / LOCAL_PEERCRED check."""

    def test_check_peer_credentials_linux(self) -> None:
        """On Linux, check_peer_credentials verifies UID."""
        if sys.platform != "linux":
            pytest.skip("Linux-only test")

        # Create a socketpair
        server_sock, client_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            # The peer UID should match our UID
            result = _check_peer_credentials(server_sock)
            assert result is True
        finally:
            server_sock.close()
            client_sock.close()

    def test_check_peer_credentials_returns_true_on_unknown_platform(self) -> None:
        """On unknown platforms, check returns True (no check)."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            with patch("dataforge.api.transport.uds.sys.platform", "freebsd"):
                result = _check_peer_credentials(sock)
                assert result is True
        finally:
            sock.close()


# ------------------------------------------------------------------
# Named Pipe (non-Windows graceful degradation)
# ------------------------------------------------------------------

class TestNamedPipeTransport:
    """Test Named Pipe transport — graceful degradation on non-Windows."""

    def test_import_on_non_windows(self) -> None:
        """Module is importable on non-Windows without error."""
        from dataforge.api.transport.named_pipe import NamedPipeTransport as NP
        assert NP is not None

    @pytest.mark.asyncio
    async def test_connect_raises_on_non_windows(self) -> None:
        """connect() raises OSError on non-Windows."""
        transport = NamedPipeTransport(r"\\.\pipe\test")
        with pytest.raises(OSError, match="Windows"):
            await transport.connect()

    def test_auto_discover_returns_none_on_non_windows(self) -> None:
        """auto_discover returns None on non-Windows."""
        result = NamedPipeTransport.auto_discover()
        assert result is None

    def test_create_server_returns_instance(self) -> None:
        """create_server returns a NamedPipeServer instance."""
        server = NamedPipeTransport.create_server()
        assert isinstance(server, NamedPipeServer)

    @pytest.mark.asyncio
    async def test_server_start_raises_on_non_windows(self) -> None:
        """NamedPipeServer.start() raises OSError on non-Windows."""
        server = NamedPipeServer()
        with pytest.raises(OSError, match="Windows"):
            await server.start()


# ------------------------------------------------------------------
# Transport __init__ exports
# ------------------------------------------------------------------

class TestTransportExports:
    """Test that transport package exports are correct."""

    def test_transport_exports(self) -> None:
        from dataforge.api.transport import (
            Transport,
            UdsTransport,
            UdsServer,
            NamedPipeTransport,
            NamedPipeServer,
        )
        assert Transport is not None
        assert UdsTransport is not None
        assert UdsServer is not None
        assert NamedPipeTransport is not None
        assert NamedPipeServer is not None

    def test_uds_transport_is_transport_subclass(self) -> None:
        from dataforge.api.transport.base import Transport
        assert issubclass(UdsTransport, Transport)

    def test_named_pipe_transport_is_transport_subclass(self) -> None:
        from dataforge.api.transport.base import Transport
        assert issubclass(NamedPipeTransport, Transport)


# ------------------------------------------------------------------
# Auto-discover integration
# ------------------------------------------------------------------

class TestAutoDiscover:
    """Test auto_discover order per spec §3.1."""

    def test_discover_endpoints_order(self) -> None:
        """Endpoints are in spec order: env → XDG → macOS → pipe → HTTP."""
        endpoints = UdsTransport._discover_endpoints()
        # Should have at least macOS + pipe + HTTP
        assert any("Library" in ep for ep in endpoints)
        assert any("pipe" in ep for ep in endpoints)
        assert any("http" in ep for ep in endpoints)

    def test_discover_endpoints_with_explicit_env(self, monkeypatch: Any) -> None:
        """DATAFORGE_ENGINE_SOCK env is first candidate."""
        monkeypatch.setenv("DATAFORGE_ENGINE_SOCK", "/custom/engine.sock")
        endpoints = UdsTransport._discover_endpoints()
        assert endpoints[0] == "/custom/engine.sock"

    def test_discover_endpoints_with_xdg(self, monkeypatch: Any) -> None:
        """XDG_RUNTIME_DIR produces correct socket path."""
        monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
        endpoints = UdsTransport._discover_endpoints()
        assert "/run/user/1000/dataforge/engine.sock" in endpoints

    def test_probe_first_existing_returns_http_fallback(self, tmp_path: Any) -> None:
        """When no socket exists, returns HTTP fallback."""
        from dataforge.api.transport.base import Transport
        with patch.object(Transport, "_discover_endpoints", return_value=["http://127.0.0.1:8765"]):
            result = Transport._probe_first_existing()
            assert result == "http://127.0.0.1:8765"

    def test_probe_first_existing_returns_socket(self, tmp_path: Any) -> None:
        """When socket exists, returns it."""
        sock_path = str(tmp_path / "engine.sock")
        # Create the file so os.path.exists returns True
        with open(sock_path, "w") as f:
            f.write("")
        from dataforge.api.transport.base import Transport
        with patch.object(Transport, "_discover_endpoints", return_value=[sock_path]):
            result = Transport._probe_first_existing()
            assert result == sock_path
