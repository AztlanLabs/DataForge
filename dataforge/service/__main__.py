"""DataForge engine service entrypoint.

Usage::

    # Start with UDS (Linux/macOS)
    python -m dataforge.service --socket /run/user/1000/dataforge/engine.sock

    # Start with Named Pipe (Windows)
    python -m dataforge.service --pipe \\\\.\\pipe\\dataforge-engine

    # Auto-discover best transport
    python -m dataforge.service

Spec: ``docs/proposals/NATIVE_OS_API_REVIEW.md §3.2``
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from typing import Any, Optional

logger = logging.getLogger("dataforge.engine")


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging for the engine service."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def _get_default_socket_path() -> str:
    """Get the default UDS socket path based on the platform."""
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        return os.path.join(xdg, "dataforge", "engine.sock")
    if sys.platform == "darwin":
        return os.path.join(
            os.path.expanduser("~"),
            "Library", "Application Support", "DataForge", "engine.sock",
        )
    # Fallback
    return "/tmp/dataforge-engine.sock"


async def _run_uds_server(
    socket_path: str,
    daemon: Any,
) -> None:
    """Run the UDS transport server."""
    from dataforge.api.transport.uds import UdsServer

    server = UdsServer(socket_path, daemon.handle_request)
    await server.start()
    logger.info("Engine listening on UDS: %s", socket_path)

    # Wait for shutdown signal
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows doesn't support add_signal_handler

    await stop_event.wait()
    await server.stop()


async def _run_named_pipe_server(
    pipe_name: str,
    daemon: Any,
) -> None:
    """Run the Named Pipe transport server (Windows only)."""
    from dataforge.api.transport.named_pipe import NamedPipeServer

    server = NamedPipeServer(pipe_name, daemon.handle_request)
    await server.start()
    logger.info("Engine listening on Named Pipe: %s", pipe_name)

    # Wait for shutdown signal
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    await stop_event.wait()
    await server.stop()


def main(argv: Optional[list] = None) -> int:
    """Main entry point for the DataForge engine service."""
    parser = argparse.ArgumentParser(
        prog="dataforge-engine",
        description="DataForge engine daemon",
    )
    parser.add_argument(
        "--socket",
        help="UDS socket path (Linux/macOS)",
        default=None,
    )
    parser.add_argument(
        "--pipe",
        help="Named Pipe path (Windows)",
        default=None,
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Max worker threads (default: 4)",
    )
    parser.add_argument(
        "--queue-depth",
        type=int,
        default=8,
        help="Max queue depth (default: 8)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    from dataforge.engine.daemon import Daemon

    daemon = Daemon(
        max_workers=args.workers,
        queue_depth=args.queue_depth,
    )
    daemon.start()

    # Determine transport
    if args.socket:
        # UDS mode
        logger.info("Starting with UDS transport: %s", args.socket)
        asyncio.run(_run_uds_server(args.socket, daemon))
    elif args.pipe:
        # Named Pipe mode
        logger.info("Starting with Named Pipe transport: %s", args.pipe)
        asyncio.run(_run_named_pipe_server(args.pipe, daemon))
    elif sys.platform == "win32":
        # Default to Named Pipe on Windows
        pipe_name = args.pipe or r"\\.\pipe\dataforge-engine"
        logger.info("Starting with Named Pipe transport: %s", pipe_name)
        asyncio.run(_run_named_pipe_server(pipe_name, daemon))
    else:
        # Default to UDS on Linux/macOS
        socket_path = args.socket or _get_default_socket_path()
        logger.info("Starting with UDS transport: %s", socket_path)
        asyncio.run(_run_uds_server(socket_path, daemon))

    daemon.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
