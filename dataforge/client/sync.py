"""Synchronous wrapper for the DataForge client.

Provides :class:`DataForgeSync`, a synchronous wrapper around
:class:`dataforge.client.DataForge` for use in CLI and other
synchronous contexts.

Usage::

    from dataforge.client.sync import DataForgeSync

    engine = DataForgeSync.connect()
    job = engine.scan("/home/me", recursive=True)
    print(job.status())
    engine.close()
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from dataforge.client import DataForge, DataForgeJob

__all__ = ["DataForgeSync", "DataForgeJobSync"]


class DataForgeJobSync:
    """Synchronous wrapper for :class:`DataForgeJob`."""

    def __init__(self, job: DataForgeJob, loop: asyncio.AbstractEventLoop) -> None:
        self._job = job
        self._loop = loop

    @property
    def job_id(self) -> str:
        return self._job.job_id

    def status(self) -> Dict[str, Any]:
        """Query the current job status."""
        return self._loop.run_until_complete(self._job.status())

    def cancel(self) -> bool:
        """Cancel this job."""
        return self._loop.run_until_complete(self._job.cancel())

    def wait(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Wait for the job to complete and return the result.

        Args:
            timeout: Maximum time to wait in seconds. None = wait forever.

        Returns:
            The job result dict.

        Raises:
            TimeoutError: If the job does not complete within *timeout*.
            RuntimeError: If the job fails.
        """
        import time

        start = time.monotonic()
        while True:
            result = self.status()
            status = result.get("status", "")
            if status in ("done", "completed"):
                return result
            if status == "failed":
                raise RuntimeError(f"Job failed: {result.get('error', 'unknown')}")
            if status == "cancelled":
                raise RuntimeError("Job was cancelled")
            if timeout is not None and (time.monotonic() - start) >= timeout:
                raise TimeoutError(f"Job did not complete within {timeout}s")
            time.sleep(0.1)


class DataForgeSync:
    """Synchronous wrapper for :class:`DataForge`.

    Usage::

        # Auto-discover daemon
        engine = DataForgeSync.connect()

        # In-process fallback
        engine = DataForgeSync.connect(in_process=True)

        # Use the engine
        job = engine.scan("/home/me")
        result = job.wait(timeout=60)
        engine.close()
    """

    def __init__(self, engine: DataForge, loop: asyncio.AbstractEventLoop) -> None:
        self._engine = engine
        self._loop = loop

    @classmethod
    def connect(
        cls,
        in_process: bool = False,
        transport: Optional[Any] = None,
    ) -> "DataForgeSync":
        """Connect to the DataForge engine synchronously.

        Args:
            in_process: If True, use the in-process engine (no daemon).
            transport: Explicit transport to use (skips auto-discovery).

        Returns:
            A connected synchronous DataForge client.
        """
        loop = asyncio.new_event_loop()
        try:
            engine = loop.run_until_complete(
                DataForge.connect(in_process=in_process, transport=transport)
            )
        except Exception:
            loop.close()
            raise
        return cls(engine, loop)

    def scan(self, root: str, **kwargs: Any) -> DataForgeJobSync:
        """Submit a scan job."""
        job = self._loop.run_until_complete(self._engine.scan(root, **kwargs))
        return DataForgeJobSync(job, self._loop)

    def search(self, root: str, **kwargs: Any) -> DataForgeJobSync:
        """Submit a search job."""
        job = self._loop.run_until_complete(self._engine.search(root, **kwargs))
        return DataForgeJobSync(job, self._loop)

    def dupes(self, root: str, **kwargs: Any) -> DataForgeJobSync:
        """Submit a duplicate detection job."""
        job = self._loop.run_until_complete(self._engine.dupes(root, **kwargs))
        return DataForgeJobSync(job, self._loop)

    def hash(self, path: str, **kwargs: Any) -> DataForgeJobSync:
        """Submit a hash job."""
        job = self._loop.run_until_complete(self._engine.hash(path, **kwargs))
        return DataForgeJobSync(job, self._loop)

    def integrity(self, path: str, snapshot: str, **kwargs: Any) -> DataForgeJobSync:
        """Submit an integrity job."""
        job = self._loop.run_until_complete(
            self._engine.integrity(path, snapshot, **kwargs)
        )
        return DataForgeJobSync(job, self._loop)

    def list_jobs(self) -> Dict[str, Any]:
        """List all jobs."""
        return self._loop.run_until_complete(self._engine.list_jobs())

    def close(self) -> None:
        """Close the client connection and event loop."""
        try:
            self._loop.run_until_complete(self._engine.close())
        finally:
            self._loop.close()
