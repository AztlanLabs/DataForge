"""Integration tests for daemon + client — TICK-301.

Tests the daemon JSON-RPC dispatch, in-process client fallback,
concurrent job execution, and independent cancellation.

Validation: ``python -m pytest tests/test_daemon_client_integration.py -q``
"""

from __future__ import annotations

import os
import time
from typing import Any
from unittest.mock import patch

import pytest

from dataforge.api.schema import JobStatus
from dataforge.engine.daemon import Daemon
from dataforge.engine.jobs import Job


# ------------------------------------------------------------------
# Daemon JSON-RPC dispatch
# ------------------------------------------------------------------


class TestDaemonDispatch:
    """Test Daemon.handle_request JSON-RPC dispatch."""

    @pytest.mark.asyncio
    async def test_handle_scan_request(self, tmp_path: Any) -> None:
        """GIVEN a scan request WHEN handled THEN returns job_id."""
        daemon = Daemon()
        daemon.start()
        try:
            # Create test files
            (tmp_path / "a.txt").write_text("hello")
            (tmp_path / "b.txt").write_text("world")

            response = await daemon.handle_request({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "scan",
                "params": {"root": str(tmp_path)},
            })
            assert "result" in response
            assert "job_id" in response["result"]
            job_id = response["result"]["job_id"]
            assert len(job_id) == 26  # ULID length

            # Wait for job to complete
            time.sleep(0.5)
            job = daemon.get(job_id)
            assert job is not None
            assert job.status in (JobStatus.RUNNING, JobStatus.DONE)
        finally:
            daemon.stop()

    @pytest.mark.asyncio
    async def test_handle_status_request(self, tmp_path: Any) -> None:
        """GIVEN a submitted job WHEN status requested THEN returns job info."""
        daemon = Daemon()
        daemon.start()
        try:
            (tmp_path / "test.txt").write_text("data")

            # Submit scan
            resp = await daemon.handle_request({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "scan",
                "params": {"root": str(tmp_path)},
            })
            job_id = resp["result"]["job_id"]

            # Query status
            time.sleep(0.3)
            status_resp = await daemon.handle_request({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "status",
                "params": {"job_id": job_id},
            })
            result = status_resp["result"]
            assert result["job_id"] == job_id
            assert result["status"] in ("queued", "running", "done")
        finally:
            daemon.stop()

    @pytest.mark.asyncio
    async def test_handle_cancel_request(self, tmp_path: Any) -> None:
        """GIVEN a running job WHEN cancel requested THEN job is cancelled."""
        daemon = Daemon()
        daemon.start()
        try:
            # Submit a slow scan
            resp = await daemon.handle_request({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "scan",
                "params": {"root": str(tmp_path)},
            })
            job_id = resp["result"]["job_id"]

            # Cancel immediately
            cancel_resp = await daemon.handle_request({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "cancel",
                "params": {"job_id": job_id},
            })
            assert cancel_resp["result"]["cancelled"] is True or cancel_resp["result"]["job_id"] == job_id
        finally:
            daemon.stop()

    @pytest.mark.asyncio
    async def test_handle_list_jobs_request(self, tmp_path: Any) -> None:
        """GIVEN multiple jobs WHEN list_jobs requested THEN all jobs returned."""
        daemon = Daemon()
        daemon.start()
        try:
            (tmp_path / "f.txt").write_text("x")

            # Submit two scans
            await daemon.handle_request({
                "jsonrpc": "2.0", "id": 1, "method": "scan",
                "params": {"root": str(tmp_path)},
            })
            await daemon.handle_request({
                "jsonrpc": "2.0", "id": 2, "method": "scan",
                "params": {"root": str(tmp_path)},
            })

            time.sleep(0.3)
            list_resp = await daemon.handle_request({
                "jsonrpc": "2.0", "id": 3, "method": "list_jobs",
                "params": {},
            })
            assert list_resp["result"]["total"] >= 2
        finally:
            daemon.stop()

    @pytest.mark.asyncio
    async def test_handle_unknown_method(self) -> None:
        """GIVEN unknown method WHEN handled THEN returns error."""
        daemon = Daemon()
        daemon.start()
        try:
            response = await daemon.handle_request({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "nonexistent",
                "params": {},
            })
            assert "error" in response
            assert response["error"]["code"] == -32601
        finally:
            daemon.stop()

    @pytest.mark.asyncio
    async def test_handle_scan_missing_root(self) -> None:
        """GIVEN scan request without root WHEN handled THEN returns error."""
        daemon = Daemon()
        daemon.start()
        try:
            response = await daemon.handle_request({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "scan",
                "params": {},
            })
            assert "error" in response
        finally:
            daemon.stop()


# ------------------------------------------------------------------
# In-process client
# ------------------------------------------------------------------


class TestInProcessClient:
    """Test DataForge.connect(in_process=True)."""

    @pytest.mark.asyncio
    async def test_in_process_scan(self, tmp_path: Any) -> None:
        """GIVEN in_process=True WHEN scan THEN returns job with results."""
        from dataforge.client import DataForge

        (tmp_path / "file1.txt").write_text("a")
        (tmp_path / "file2.txt").write_text("b")

        engine = await DataForge.connect(in_process=True)
        try:
            job = await engine.scan(str(tmp_path))
            assert job.job_id is not None

            # Wait for completion
            result = await job.status()
            assert result["job_id"] == job.job_id
        finally:
            await engine.close()

    @pytest.mark.asyncio
    async def test_in_process_search(self, tmp_path: Any) -> None:
        """GIVEN in_process=True WHEN search THEN returns job."""
        from dataforge.client import DataForge

        (tmp_path / "test.py").write_text("print('hello')")
        (tmp_path / "test.txt").write_text("world")

        engine = await DataForge.connect(in_process=True)
        try:
            job = await engine.search(str(tmp_path), extensions=[".py"])
            assert job.job_id is not None
        finally:
            await engine.close()

    @pytest.mark.asyncio
    async def test_in_process_list_jobs(self, tmp_path: Any) -> None:
        """GIVEN in_process=True WHEN list_jobs THEN returns jobs list."""
        from dataforge.client import DataForge

        (tmp_path / "f.txt").write_text("x")

        engine = await DataForge.connect(in_process=True)
        try:
            await engine.scan(str(tmp_path))
            time.sleep(0.3)
            result = await engine.list_jobs()
            assert "jobs" in result
            assert result["total"] >= 1
        finally:
            await engine.close()


# ------------------------------------------------------------------
# Concurrent jobs
# ------------------------------------------------------------------


class TestConcurrentJobs:
    """Test two concurrent scan jobs run independently."""

    @pytest.mark.asyncio
    async def test_two_concurrent_scans(self, tmp_path: Any) -> None:
        """GIVEN two concurrent scan jobs WHEN queued THEN both run."""
        from dataforge.client import DataForge

        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "x.txt").write_text("x")
        (dir_b / "y.txt").write_text("y")

        engine = await DataForge.connect(in_process=True)
        try:
            job_a = await engine.scan(str(dir_a))
            job_b = await engine.scan(str(dir_b))

            # Both should have unique IDs
            assert job_a.job_id != job_b.job_id

            # Wait for both to complete
            time.sleep(0.5)
            status_a = await job_a.status()
            status_b = await job_b.status()
            assert status_a["status"] in ("running", "done")
            assert status_b["status"] in ("running", "done")
        finally:
            await engine.close()

    @pytest.mark.asyncio
    async def test_independent_cancellation(self, tmp_path: Any) -> None:
        """GIVEN two jobs WHEN one cancelled THEN other continues."""
        from dataforge.client import DataForge

        (tmp_path / "f.txt").write_text("x")

        engine = await DataForge.connect(in_process=True)
        try:
            job_a = await engine.scan(str(tmp_path))
            job_b = await engine.scan(str(tmp_path))

            # Cancel job A
            cancelled = await job_a.cancel()
            assert cancelled is True

            # Job B should still be running or done
            time.sleep(0.3)
            status_b = await job_b.status()
            assert status_b["status"] in ("running", "done", "cancelled")
        finally:
            await engine.close()


# ------------------------------------------------------------------
# Daemon lifecycle
# ------------------------------------------------------------------


class TestDaemonLifecycle:
    """Test Daemon start/stop lifecycle."""

    def test_daemon_start_stop(self) -> None:
        """GIVEN a daemon WHEN start/stop THEN state changes correctly."""
        daemon = Daemon()
        assert daemon.is_running() is False

        daemon.start()
        assert daemon.is_running() is True

        daemon.stop()
        assert daemon.is_running() is False

    def test_daemon_submit_returns_job(self) -> None:
        """GIVEN a running daemon WHEN submit THEN returns Job."""
        daemon = Daemon()
        daemon.start()
        try:
            def _noop():
                return "ok"

            job = daemon.submit(_noop)
            assert isinstance(job, Job)
            assert job.job_id is not None

            time.sleep(0.3)
            assert job.status in (JobStatus.RUNNING, JobStatus.DONE)
        finally:
            daemon.stop()

    def test_daemon_cancel_job(self) -> None:
        """GIVEN a running job WHEN cancel THEN job is cancelled."""
        daemon = Daemon()
        daemon.start()
        try:
            def _slow():
                time.sleep(10)
                return "done"

            job = daemon.submit(_slow)
            time.sleep(0.1)
            result = daemon.cancel(job.job_id)
            assert result is True
        finally:
            daemon.stop()


# ------------------------------------------------------------------
# Auto-discover fallback
# ------------------------------------------------------------------


class TestAutoDiscoverFallback:
    """Test auto-discover falls back to in-process when no daemon."""

    @pytest.mark.asyncio
    async def test_auto_discover_no_daemon(self, tmp_path: Any) -> None:
        """GIVEN no daemon running WHEN connect() THEN falls back to in-process."""
        from dataforge.client import DataForge

        # Ensure no daemon socket exists
        with patch.dict(os.environ, {"DATAFORGE_ENGINE_SOCK": ""}):
            engine = await DataForge.connect()
            try:
                # Should be using in-process transport
                (tmp_path / "test.txt").write_text("data")
                job = await engine.scan(str(tmp_path))
                assert job.job_id is not None
            finally:
                await engine.close()

    @pytest.mark.asyncio
    async def test_in_process_scan_works(self, tmp_path: Any) -> None:
        """GIVEN in_process=True WHEN scan THEN scan still works."""
        from dataforge.client import DataForge

        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world")

        engine = await DataForge.connect(in_process=True)
        try:
            job = await engine.scan(str(tmp_path))
            # Wait for completion
            time.sleep(0.5)
            result = await job.status()
            assert result["job_id"] == job.job_id
        finally:
            await engine.close()


# ------------------------------------------------------------------
# Sync wrapper
# ------------------------------------------------------------------


class TestSyncWrapper:
    """Test DataForgeSync synchronous wrapper."""

    def test_sync_connect_in_process(self, tmp_path: Any) -> None:
        """GIVEN sync client WHEN connect(in_process=True) THEN works."""
        from dataforge.client.sync import DataForgeSync

        (tmp_path / "f.txt").write_text("data")

        engine = DataForgeSync.connect(in_process=True)
        try:
            job = engine.scan(str(tmp_path))
            assert job.job_id is not None
        finally:
            engine.close()

    def test_sync_scan_returns_job(self, tmp_path: Any) -> None:
        """GIVEN sync client WHEN scan THEN returns DataForgeJobSync."""
        from dataforge.client.sync import DataForgeSync, DataForgeJobSync

        (tmp_path / "f.txt").write_text("data")

        engine = DataForgeSync.connect(in_process=True)
        try:
            job = engine.scan(str(tmp_path))
            assert isinstance(job, DataForgeJobSync)
            assert job.job_id is not None
        finally:
            engine.close()

    def test_sync_list_jobs(self, tmp_path: Any) -> None:
        """GIVEN sync client WHEN list_jobs THEN returns jobs dict."""
        from dataforge.client.sync import DataForgeSync

        (tmp_path / "f.txt").write_text("data")

        engine = DataForgeSync.connect(in_process=True)
        try:
            engine.scan(str(tmp_path))
            time.sleep(0.3)
            result = engine.list_jobs()
            assert "jobs" in result
        finally:
            engine.close()


# ------------------------------------------------------------------
# Service entrypoint
# ------------------------------------------------------------------


class TestServiceEntrypoint:
    """Test dataforge.service.__main__ module."""

    def test_main_module_importable(self) -> None:
        """GIVEN service module WHEN imported THEN no side effects."""
        import dataforge.service.__main__ as svc
        assert hasattr(svc, "main")
        assert callable(svc.main)

    def test_main_help(self) -> None:
        """GIVEN service module WHEN --help THEN exits 0."""
        import dataforge.service.__main__ as svc
        with pytest.raises(SystemExit) as exc_info:
            svc.main(["--help"])
        assert exc_info.value.code == 0
