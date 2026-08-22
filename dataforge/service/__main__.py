"""DataForge engine entrypoint — ``python -m dataforge.service``.

This is the Wave-0 stub for the ``dataforge-engine`` console script.
The full daemon loop (``asyncio`` + transports) is TICK-301 and will
overwrite this file in Wave 3 (sequential re-entry per
``docs/PARALLEL_BACKLOG.md``).

The stub exists so ``python -m dataforge.service --help`` succeeds in
Wave 0 and service lifecycle files (systemd, launchd, Windows Service)
can reference ``dataforge-engine`` as the ``ExecStart`` target.

See ``docs/proposals/NATIVE_OS_API_REVIEW.md §3.2`` and
``dataforge/engine/daemon.py``.
"""

from __future__ import annotations

import argparse
import sys

from dataforge.engine.daemon import Daemon

__all__ = ["main"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dataforge-engine",
        description="DataForge engine daemon — listens on UDS/Named Pipe for JSON-RPC requests.",
    )
    parser.add_argument(
        "--socket",
        type=str,
        default=None,
        help="Path to Unix Domain Socket (default: $XDG_RUNTIME_DIR/dataforge/engine.sock).",
    )
    parser.add_argument(
        "--pipe",
        type=str,
        default=None,
        help="Named Pipe name on Windows (default: \\\\.\\pipe\\dataforge-engine).",
    )
    parser.add_argument(
        "--dbus",
        action="store_true",
        default=False,
        help="Register on D-Bus session bus (Linux only).",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        default=False,
        help="Probe the running daemon and exit 0 if healthy, 1 otherwise.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``dataforge-engine`` console script."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.health:
        # Health check: try connecting to the running daemon.
        # In stub mode there is no real daemon, so always exit 1.
        print("dataforge-engine: daemon not running (stub mode)", file=sys.stderr)
        raise SystemExit(1)

    daemon = Daemon()
    daemon.start()
    print(
        f"dataforge-engine: daemon started (stub mode, socket={args.socket}, pipe={args.pipe}, dbus={args.dbus})",
        file=sys.stderr,
    )
    try:
        # In stub mode, block until interrupted.
        import time

        while daemon.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        daemon.stop()
        print("dataforge-engine: daemon stopped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
