"""DataForge Windows Service — pywin32 ServiceFramework.

Registers with Windows SCM (Service Control Manager) as ``DataForgeEngine``.
Exposes a Named Pipe at ``\\\\.\\pipe\\dataforge-engine`` with SDDL:
``D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;AU)`` — System full, Admins full,
Authenticated Users read/write.

Install:  python -m dataforge.service.windows.install install
Start:    sc start DataForgeEngine
Status:   sc query DataForgeEngine
Remove:   python -m dataforge.service.windows.install remove

Requires: pywin32 (``pip install pywin32``).

See: docs/proposals/NATIVE_OS_API_REVIEW.md §3.2
See: docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md §3.2
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("dataforge.service.windows")

# pywin32 is optional — only needed when running as a Windows Service.
# Guard the import so the module can be imported on non-Windows for tests.
try:
    import win32event
    import win32pipe
    import win32security
    import win32service
    import win32serviceutil

    _HAS_PYWIN32 = True
except ImportError:  # pragma: no cover — exercised only on Windows without pywin32
    _HAS_PYWIN32 = False

    # Provide a stub base class so the module can be imported on Linux/macOS.
    class _StubServiceFramework:  # type: ignore[no-redef]
        """Stub for non-Windows platforms."""

        _svc_name_ = "DataForgeEngine"
        _svc_display_name_ = "DataForge Engine"
        _svc_description_ = "DataForge forensic-grade file management engine."

    win32serviceutil = None  # type: ignore[assignment]
    win32serviceutil_ServiceFramework = _StubServiceFramework  # type: ignore[misc]
else:
    win32serviceutil_ServiceFramework = win32serviceutil.ServiceFramework


# SDDL: System (GA), Administrators (GA), Authenticated Users (GRGW)
_PIPE_SDDL = "D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;AU)"
_PIPE_NAME = r"\\.\pipe\dataforge-engine"


class DataForgeService(win32serviceutil_ServiceFramework):  # type: ignore[misc]
    """Windows Service wrapper for the DataForge engine."""

    _svc_name_ = "DataForgeEngine"
    _svc_display_name_ = "DataForge Engine"
    _svc_description_ = (
        "DataForge forensic-grade file management engine. "
        "Listens on Named Pipe \\\\.\\pipe\\dataforge-engine for JSON-RPC requests."
    )

    def __init__(self, args: tuple) -> None:
        if _HAS_PYWIN32:
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self._running = False

    def SvcStop(self) -> None:
        """Called by SCM to stop the service."""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self._running = False
        if hasattr(self, "stop_event"):
            win32event.SetEvent(self.stop_event)

    def SvcDoRun(self) -> None:
        """Called by SCM to start the service."""
        self._running = True
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        logger.info("DataForgeEngine service starting")
        try:
            self._run_engine()
        except Exception:
            logger.exception("DataForgeEngine service crashed")
            self.SvcStop()

    def _run_engine(self) -> None:
        """Main service loop — creates Named Pipe and processes requests."""
        if not _HAS_PYWIN32:
            return

        # Build security descriptor from SDDL
        sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
            _PIPE_SDDL,
            win32security.SDDL_REVISION_1,
        )

        # Create Named Pipe
        pipe_handle = win32pipe.CreateNamedPipe(
            _PIPE_NAME,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
            win32pipe.PIPE_UNLIMITED_INSTANCES,
            65536,
            65536,
            0,
            sd,
        )

        logger.info("DataForgeEngine listening on %s", _PIPE_NAME)

        try:
            while self._running:
                # Wait for a client connection (blocks until connect or stop)
                win32pipe.ConnectNamedPipe(pipe_handle, None)

                if not self._running:
                    break

                # In stub mode, just disconnect and wait for next connection.
                # Full JSON-RPC handling is TICK-301.
                win32pipe.DisconnectNamedPipe(pipe_handle)
                time.sleep(0.1)
        finally:
            win32pipe.CloseHandle(pipe_handle)
            logger.info("DataForgeEngine pipe closed")


# Alias for win32serviceutil registration
if _HAS_PYWIN32:
    # win32serviceutil expects the class to be directly importable.
    # The install.py module handles registration via command-line.
    pass


__all__ = ["DataForgeService", "_PIPE_NAME", "_PIPE_SDDL"]
