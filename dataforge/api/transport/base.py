"""Transport ABC — pluggable IPC for the DataForge engine.

Mirrors ``docs/proposals/NATIVE_OS_API_REVIEW.md §3``.

Concrete transports (UDS, Named Pipe, HTTP) live in sibling modules and
must subclass :class:`Transport`.  The ABC enforces the four operations
required by the spec:

* ``send`` — send a JSON-RPC payload, await a reply
* ``recv`` — receive a payload (for server-side)
* ``subscribe`` — async-iter over :class:`dataforge.api.schema.JobEvent` frames
* ``auto_discover`` — classmethod that probes the well-known endpoint order
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, Optional


class Transport(ABC):
    """Abstract transport. Subclasses must implement all four operations."""

    @abstractmethod
    async def send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC 2.0 payload and return the response dict."""
        raise NotImplementedError

    @abstractmethod
    async def recv(self) -> Dict[str, Any]:
        """Receive the next JSON-RPC 2.0 payload (server side)."""
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, job_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Return an async iterator over event frames for *job_id*.

        Each yielded item is a ``JobEvent`` dict (``job_id``, ``type``, ...).
        The method itself is synchronous and returns an async iterator so
        callers may ``async for event in transport.subscribe(job_id)``.
        """
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def auto_discover(cls) -> Optional[str]:
        """Probe well-known endpoints in discovery order.

        Order per ``NATIVE_OS_API_REVIEW.md §3.1``:

        1. ``$DATAFORGE_ENGINE_SOCK`` (explicit)
        2. ``$XDG_RUNTIME_DIR/dataforge/engine.sock``
        3. ``~/Library/Application Support/DataForge/engine.sock`` (macOS)
        4. ``\\\\.\\pipe\\dataforge-engine`` (Windows)
        5. ``http://127.0.0.1:8765`` (HTTP fallback)

        Returns the first endpoint string that appears reachable, or ``None``.
        The base implementation provides the canonical probe order so
        subclasses may call ``super().auto_discover()``.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helper — subclasses may delegate to this.
    # ------------------------------------------------------------------
    @classmethod
    def _discover_endpoints(cls) -> list[str]:
        """Return the ordered list of candidate endpoint strings."""
        candidates: list[str] = []
        # 1. explicit env
        explicit = os.environ.get("DATAFORGE_ENGINE_SOCK")
        if explicit:
            candidates.append(explicit)
        # 2. XDG_RUNTIME_DIR
        xdg = os.environ.get("XDG_RUNTIME_DIR")
        if xdg:
            candidates.append(os.path.join(xdg, "dataforge", "engine.sock"))
        # 3. macOS Application Support
        candidates.append(
            os.path.join(
                os.path.expanduser("~"),
                "Library",
                "Application Support",
                "DataForge",
                "engine.sock",
            )
        )
        # 4. Windows Named Pipe
        candidates.append(r"\\.\pipe\dataforge-engine")
        # 5. HTTP fallback
        candidates.append("http://127.0.0.1:8765")
        return candidates

    @classmethod
    def _probe_first_existing(cls) -> Optional[str]:
        """Return first candidate that exists on the filesystem or is HTTP fallback."""
        for ep in cls._discover_endpoints():
            if ep.startswith("http"):
                return ep
            # For UDS / pipe: check existence; if none exist, still return HTTP
            if os.path.exists(ep):
                return ep
        # Fallback to HTTP if nothing else matched
        return "http://127.0.0.1:8765"


__all__ = ["Transport"]
