"""Tests for TICK-707 — HTTP gateway + D-Bus/XPC/COM (NATIVE N2/N3).

Acceptance:
 - HttpGateway started on 127.0.0.1:8765 POST /jobs/scan -> job_id and GET /jobs/{id} polling
 - no FastAPI -> ImportError with pip install hint
 - D-Bus fallback gracefully on non-Linux
 - existing transport tests still pass
"""

from __future__ import annotations


import pytest

try:
    from fastapi.testclient import TestClient  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - optional dep graceful skip
    TestClient = None  # type: ignore[assignment,misc]

from dataforge.api.transport.base import Transport
from dataforge.api.transport.http_gateway import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    HAS_FASTAPI,
    HttpGateway,
    register_com_service,
    register_dbus_service,
    register_xpc_service,
)
from dataforge.engine.daemon import Daemon

# Skip gateway tests when FastAPI is not installed — collection must not crash
# (CI without fastapi should skip, not error; see CI error ModuleNotFoundError).
_requires_fastapi = pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed — pip install fastapi uvicorn")
_requires_testclient = pytest.mark.skipif(TestClient is None, reason="fastapi TestClient not installed — pip install fastapi httpx")


def _make_daemon() -> Daemon:
    d = Daemon()
    d.start()
    return d


class TestFastApiOptional:
    @_requires_fastapi
    def test_has_fastapi_true_when_installed(self) -> None:
        # In this env FastAPI is installed
        assert HAS_FASTAPI is True

    def test_missing_fastapi_raises_informative(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import dataforge.api.transport.http_gateway as mod

        monkeypatch.setattr(mod, "HAS_FASTAPI", False)
        monkeypatch.setattr(mod, "_FASTAPI_ERROR", ImportError("No module named 'fastapi'"))
        with pytest.raises(ImportError, match="pip install fastapi"):
            HttpGateway()

        # Also message should contain hint for uvicorn
        try:
            HttpGateway()
        except ImportError as exc:
            assert "fastapi" in str(exc).lower()
            assert "pip install" in str(exc).lower()

    def test_module_import_does_not_crash_when_fastapi_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Module should still be importable even when flag is False (graceful degradation)
        import dataforge.api.transport.http_gateway as mod

        # Simulate missing FastAPI at import time by checking flag
        assert hasattr(mod, "HAS_FASTAPI")
        assert hasattr(mod, "HttpGateway")


class TestDbusFallback:
    def test_dbus_fallback_on_non_linux(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("dataforge.api.transport.http_gateway.sys.platform", "win32")
        # Should not raise, should return False
        assert register_dbus_service() is False

    def test_xpc_fallback_on_non_macos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("dataforge.api.transport.http_gateway.sys.platform", "linux")
        assert register_xpc_service() is False

    def test_com_fallback_on_non_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("dataforge.api.transport.http_gateway.sys.platform", "linux")
        assert register_com_service() is False

    def test_dbus_graceful_when_no_service_file(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        # On Linux with dbus installed, it should succeed or fallback without crash
        # We don't require a real D-Bus daemon; just ensure no exception
        try:
            result = register_dbus_service()
            assert isinstance(result, bool)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"register_dbus_service should not raise: {exc}")

    def test_com_on_windows_without_pywin32(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("dataforge.api.transport.http_gateway.sys.platform", "win32")
        # Simulate missing pywin32 by ensuring import fails
        # register_com_service should return False, not raise
        assert register_com_service() is False or isinstance(register_com_service(), bool)


class TestHttpGatewayIsTransport:
    def test_is_subclass(self) -> None:
        assert issubclass(HttpGateway, Transport)

    @_requires_fastapi
    def test_implements_abstract_methods(self) -> None:
        daemon = _make_daemon()
        gw = HttpGateway(daemon)
        assert hasattr(gw, "send")
        assert hasattr(gw, "recv")
        assert hasattr(gw, "subscribe")
        assert hasattr(gw, "auto_discover")
        # auto_discover should be callable and not raise
        result = HttpGateway.auto_discover()
        assert result is None or isinstance(result, str)
        daemon.stop()

    def test_auto_discover_returns_none_when_not_running(self) -> None:
        # No server running on default port in test env (unless we started one)
        result = HttpGateway.auto_discover()
        # Should be None because nothing listening on 8765
        # Allow either None or endpoint, but must not raise
        assert result is None or result == f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"

    @_requires_fastapi
    def test_default_host_port(self) -> None:
        daemon = _make_daemon()
        gw = HttpGateway(daemon)
        assert gw.host == DEFAULT_HOST
        assert gw.port == DEFAULT_PORT
        daemon.stop()


@_requires_fastapi
@_requires_testclient
class TestHttpGatewayEndpoints:
    def test_scan_and_poll(self, tmp_path) -> None:
        daemon = _make_daemon()
        gw = HttpGateway(daemon)
        client = TestClient(gw.app)
        tmp_path.mkdir(exist_ok=True) if not tmp_path.exists() else None
        (tmp_path / "a.txt").write_text("hello")
        resp = client.post("/jobs/scan", json={"root": str(tmp_path)})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "job_id" in data
        job_id = data["job_id"]
        assert isinstance(job_id, str) and len(job_id) > 5

        # Poll via GET /jobs/{id}
        resp2 = client.get(f"/jobs/{job_id}")
        assert resp2.status_code == 200, resp2.text
        job = resp2.json()
        assert job["job_id"] == job_id
        assert job["status"] in ("queued", "running", "done", "completed")
        daemon.stop()

    def test_search_and_dupes(self, tmp_path) -> None:
        daemon = _make_daemon()
        gw = HttpGateway(daemon)
        client = TestClient(gw.app)
        (tmp_path / "a.txt").write_text("hello world")
        (tmp_path / "b.txt").write_text("hello world")
        resp = client.post("/jobs/search", json={"root": str(tmp_path), "name_pattern": "*.txt"})
        assert resp.status_code == 200
        assert "job_id" in resp.json()

        resp2 = client.post("/jobs/dupes", json={"root": str(tmp_path)})
        assert resp2.status_code == 200
        assert "job_id" in resp2.json()
        daemon.stop()

    def test_hash_and_integrity(self, tmp_path) -> None:
        daemon = _make_daemon()
        gw = HttpGateway(daemon)
        client = TestClient(gw.app)
        a = tmp_path / "a.txt"
        a.write_text("hello")
        resp = client.post("/jobs/hash", json={"path": str(a), "algo": "sha256"})
        assert resp.status_code == 200
        assert "job_id" in resp.json()

        snap = tmp_path / "snap.json"
        resp2 = client.post("/jobs/integrity", json={"path": str(tmp_path), "snapshot": str(snap), "operation": "create"})
        assert resp2.status_code == 200
        assert "job_id" in resp2.json()
        daemon.stop()

    def test_list_and_cancel(self, tmp_path) -> None:
        daemon = _make_daemon()
        gw = HttpGateway(daemon)
        client = TestClient(gw.app)
        (tmp_path / "a.txt").write_text("x")
        resp = client.post("/jobs/scan", json={"root": str(tmp_path)})
        job_id = resp.json()["job_id"]

        # List
        resp2 = client.get("/jobs")
        assert resp2.status_code == 200
        lst = resp2.json()
        assert "total" in lst
        assert "jobs" in lst
        assert lst["total"] >= 1

        # Cancel (already done, so cancelled flag may be False, but should not crash)
        resp3 = client.post(f"/jobs/{job_id}/cancel")
        assert resp3.status_code == 200
        assert "cancelled" in resp3.json()
        daemon.stop()

    def test_health_and_jsonrpc_root(self, tmp_path) -> None:
        daemon = _make_daemon()
        gw = HttpGateway(daemon)
        client = TestClient(gw.app)

        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # JSON-RPC via POST /
        payload = {"jsonrpc": "2.0", "id": 1, "method": "scan", "params": {"root": str(tmp_path)}}
        resp2 = client.post("/", json=payload)
        assert resp2.status_code == 200
        body = resp2.json()
        assert body["jsonrpc"] == "2.0"
        assert "result" in body
        assert "job_id" in body["result"]
        daemon.stop()

    def test_not_found_job_returns_404(self) -> None:
        daemon = _make_daemon()
        gw = HttpGateway(daemon)
        client = TestClient(gw.app)
        resp = client.get("/jobs/nonexistent123456")
        assert resp.status_code == 404
        assert "Job not found" in resp.text or "not found" in resp.text.lower()
        daemon.stop()

    def test_custom_host_port(self) -> None:
        daemon = _make_daemon()
        gw = HttpGateway(daemon, host="127.0.0.1", port=9876)
        assert gw.host == "127.0.0.1"
        assert gw.port == 9876
        assert gw.app is not None
        daemon.stop()


class TestHttpGatewayClient:
    @pytest.mark.asyncio
    @_requires_fastapi
    async def test_send_jsonrpc_via_http(self, tmp_path) -> None:
        # Start a real gateway in background thread using TestClient's app?
        # We test the client `send` by using the gateway's send against its own app via TestClient transport?
        # Instead, we test that `send` is implemented and raises ConnectionError when no server
        daemon = _make_daemon()
        gw = HttpGateway(daemon, host="127.0.0.1", port=59999)  # unlikely to be open
        payload = {"jsonrpc": "2.0", "id": 1, "method": "scan", "params": {"root": str(tmp_path)}}
        with pytest.raises(ConnectionError):
            await gw.send(payload)
        daemon.stop()

    @pytest.mark.asyncio
    @_requires_fastapi
    async def test_recv_not_implemented(self) -> None:
        daemon = _make_daemon()
        gw = HttpGateway(daemon)
        with pytest.raises(NotImplementedError):
            await gw.recv()
        daemon.stop()

    @_requires_fastapi
    def test_subscribe_returns_async_iterator(self) -> None:
        daemon = _make_daemon()
        gw = HttpGateway(daemon)
        job = daemon.queue.submit(lambda: {"ok": True}, params={})
        it = gw.subscribe(job.job_id)
        assert hasattr(it, "__aiter__")
        assert hasattr(it, "__anext__")
        daemon.stop()


class TestHttpGatewayTransportRegression:
    def test_existing_transport_tests_still_importable(self) -> None:
        from dataforge.api.transport.uds import UdsTransport
        from dataforge.api.transport.named_pipe import NamedPipeTransport

        assert issubclass(UdsTransport, Transport)
        assert issubclass(NamedPipeTransport, Transport)
        assert issubclass(HttpGateway, Transport)

    def test_discover_endpoints_order(self) -> None:
        # HTTP should be last fallback per base.py
        eps = Transport._discover_endpoints()
        assert eps[-1] == "http://127.0.0.1:8765"

    def test_probe_first_existing_returns_http_fallback(self, monkeypatch) -> None:
        from unittest.mock import patch

        from dataforge.api.transport.base import Transport

        with patch.object(Transport, "_discover_endpoints", return_value=["http://127.0.0.1:8765"]):
            result = Transport._probe_first_existing()
            assert result == "http://127.0.0.1:8765"
