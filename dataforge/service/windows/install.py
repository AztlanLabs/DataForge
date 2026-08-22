"""DataForge Windows Service installer — registers/unregisters with SCM.

Usage:
    python -m dataforge.service.windows.install install   # Register service
    python -m dataforge.service.windows.install remove    # Unregister service
    python -m dataforge.service.windows.install start     # Start service
    python -m dataforge.service.windows.install stop      # Stop service
    python -m dataforge.service.windows.install status    # Query service status

Requires: pywin32 (``pip install pywin32``).

The service runs as ``NT SERVICE\\DataForgeEngine`` with Named Pipe SDDL:
``D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;AU)`` — System full, Admins full,
Authenticated Users read/write.

See: docs/proposals/NATIVE_OS_API_REVIEW.md §3.2
See: docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md §3.2
"""

from __future__ import annotations

import argparse
import sys

# pywin32 is optional — only needed on Windows.
try:
    import win32service
    import win32serviceutil

    _HAS_PYWIN32 = True
except ImportError:
    _HAS_PYWIN32 = False

_SDDL = "D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;AU)"


def _check_pywin32() -> None:
    if not _HAS_PYWIN32:
        print(
            "Error: pywin32 is required for Windows Service management.\n"
            "Install it with: pip install pywin32",
            file=sys.stderr,
        )
        raise SystemExit(1)


def install_service() -> None:
    """Register DataForgeEngine with Windows SCM."""
    _check_pywin32()
    # win32serviceutil.InstallService expects the module path and class name.
    # When run as `python -m dataforge.service.windows.install install`,
    # we use the service module path.
    win32serviceutil.InstallService(
        pythonClassString="dataforge.service.windows.service.DataForgeService",
        serviceName="DataForgeEngine",
        displayName="DataForge Engine",
        description=(
            "DataForge forensic-grade file management engine. "
            "Listens on Named Pipe \\\\.\\pipe\\dataforge-engine for JSON-RPC requests."
        ),
        startType=win32service.SERVICE_AUTO_START,
    )
    print("DataForgeEngine service registered successfully.")
    print(f"  SDDL: {_SDDL}")
    print("  Start: sc start DataForgeEngine")
    print("  Status: sc query DataForgeEngine")


def remove_service() -> None:
    """Unregister DataForgeEngine from Windows SCM."""
    _check_pywin32()
    try:
        win32serviceutil.RemoveService("DataForgeEngine")
        print("DataForgeEngine service removed successfully.")
    except Exception as exc:
        print(f"Error removing service: {exc}", file=sys.stderr)
        raise SystemExit(1)


def start_service() -> None:
    """Start the DataForgeEngine service."""
    _check_pywin32()
    try:
        win32serviceutil.StartService("DataForgeEngine")
        print("DataForgeEngine service started.")
    except Exception as exc:
        print(f"Error starting service: {exc}", file=sys.stderr)
        raise SystemExit(1)


def stop_service() -> None:
    """Stop the DataForgeEngine service."""
    _check_pywin32()
    try:
        win32serviceutil.StopService("DataForgeEngine")
        print("DataForgeEngine service stopped.")
    except Exception as exc:
        print(f"Error stopping service: {exc}", file=sys.stderr)
        raise SystemExit(1)


def status_service() -> None:
    """Query DataForgeEngine service status."""
    _check_pywin32()
    try:
        status = win32serviceutil.QueryServiceStatus("DataForgeEngine")
        state = status[1]
        state_names = {
            win32service.SERVICE_STOPPED: "STOPPED",
            win32service.SERVICE_START_PENDING: "START_PENDING",
            win32service.SERVICE_STOP_PENDING: "STOP_PENDING",
            win32service.SERVICE_RUNNING: "RUNNING",
            win32service.SERVICE_CONTINUE_PENDING: "CONTINUE_PENDING",
            win32service.SERVICE_PAUSE_PENDING: "PAUSE_PENDING",
            win32service.SERVICE_PAUSED: "PAUSED",
        }
        state_name = state_names.get(state, f"UNKNOWN({state})")
        print(f"DataForgeEngine: {state_name}")
    except Exception as exc:
        print(f"Error querying service: {exc}", file=sys.stderr)
        raise SystemExit(1)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dataforge-service-install",
        description="DataForge Windows Service installer — manages SCM registration.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install", help="Register DataForgeEngine with Windows SCM.")
    sub.add_parser("remove", help="Unregister DataForgeEngine from Windows SCM.")
    sub.add_parser("start", help="Start the DataForgeEngine service.")
    sub.add_parser("stop", help="Stop the DataForgeEngine service.")
    sub.add_parser("status", help="Query DataForgeEngine service status.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m dataforge.service.windows.install``."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    commands = {
        "install": install_service,
        "remove": remove_service,
        "start": start_service,
        "stop": stop_service,
        "status": status_service,
    }
    commands[args.command]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
