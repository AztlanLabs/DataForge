"""TICK-929 — Service entrypoint arguments, transport security, pipe SDDL."""
import asyncio
import re
import shlex
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import dataforge.api.transport.named_pipe as named_pipe
import dataforge.api.transport.http_gateway as http_gateway
import dataforge.service.__main__ as service_main
from dataforge.api.transport.named_pipe import NamedPipeServer, _PIPE_SDDL
from dataforge.api.transport.uds import UdsTransport
from dataforge.client import DataForge


def test_service_parser_accepts_dbus():
    parser = service_main.build_parser()
    args = parser.parse_args(["--dbus"])
    assert args.dbus is True


def test_service_parser_accepts_socket():
    parser = service_main.build_parser()
    args = parser.parse_args(["--socket", "/tmp/test.sock"])
    assert args.socket == "/tmp/test.sock"


def test_service_parser_accepts_pipe():
    parser = service_main.build_parser()
    args = parser.parse_args(["--pipe", "test"])
    assert args.pipe == "test"


def test_service_parser_rejects_unknown():
    parser = service_main.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--unknown"])


def test_service_unit_flags_supported():
    unit = Path(__file__).resolve().parent.parent / "dataforge" / "service" / "linux" / "dataforge.service"
    text = unit.read_text()
    match = re.search(r"^\s*ExecStart=\S+(.*)$", text, re.MULTILINE)
    assert match, "ExecStart line missing from source unit"
    flags = shlex.split(match.group(1))
    assert flags, "ExecStart has no flags"
    parser = service_main.build_parser()
    args = parser.parse_args(flags)
    assert args.socket
    assert args.dbus is True


def test_uds_iterator_terminal_check():
    frames = [
        {"job_id": "j1", "type": "progress", "payload": {}},
        {"job_id": "other", "type": "progress", "payload": {}},
        {"job_id": "j1", "type": "result", "payload": {}},
    ]
    transport = UdsTransport("/tmp/nonexistent.sock")

    async def fake_recv():
        return frames.pop(0)

    transport.recv = fake_recv
    iterator = transport.subscribe("j1")

    async def run():
        out = []
        async for ev in iterator:
            out.append(ev)
        return out

    out = asyncio.run(run())
    # Only the j1 progress frame is yielded; the foreign-job frame is skipped
    # and the terminal result frame stops the iterator.
    assert out == [{"job_id": "j1", "type": "progress", "payload": {}}]


def test_pipe_sddl_applied(monkeypatch):
    fake_pipe = MagicMock()
    fake_pipe.CreateNamedPipe.return_value = "handle-1"
    fake_file = MagicMock()

    class FakePywintypes:
        @staticmethod
        def SECURITY_ATTRIBUTES():
            return MagicMock()

    monkeypatch.setattr(named_pipe, "_win32pipe", fake_pipe)
    monkeypatch.setattr(named_pipe, "_win32file", fake_file)
    monkeypatch.setattr(named_pipe, "_pywintypes", FakePywintypes)

    server = NamedPipeServer(r"\\.\pipe\test-sddl")
    server._create_pipe_instance()
    args, _ = fake_pipe.CreateNamedPipe.call_args
    security_attributes = args[-1]
    assert security_attributes is not None
    assert security_attributes.Sddl == _PIPE_SDDL


def test_pipe_stop_cancels_blocked(monkeypatch):
    fake_pipe = MagicMock()
    fake_file = MagicMock()
    fake_file.ReadFile.return_value = (0, b"")
    monkeypatch.setattr(named_pipe.sys, "platform", "win32")
    monkeypatch.setattr(named_pipe, "_win32pipe", fake_pipe)
    monkeypatch.setattr(named_pipe, "_win32file", fake_file)
    monkeypatch.setattr(named_pipe, "_pywintypes", None)

    server = NamedPipeServer(r"\\.\pipe\test-stop")

    async def scenario():
        await server.start()
        await asyncio.sleep(0.05)
        await asyncio.wait_for(server.stop(), timeout=2.0)

    asyncio.run(scenario())
    assert server._running is False
    assert server._accept_task is None


def test_client_discovers_http():
    fake_transport = MagicMock()
    with patch.object(http_gateway, "HttpGateway") as mock_http:
        mock_http.auto_discover.return_value = "http://127.0.0.1:8765"
        mock_http.return_value = fake_transport
        transport = DataForge._auto_discover_transport()
    assert transport is fake_transport
    assert fake_transport.host == "127.0.0.1"
    assert fake_transport.port == 8765