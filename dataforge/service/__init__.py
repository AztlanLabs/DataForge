"""DataForge service package — engine entrypoint and lifecycle files.

This package contains:
- ``__main__.py`` — ``dataforge-engine`` entrypoint (``python -m dataforge.service``)
- ``linux/`` — systemd user socket + service + D-Bus service file
- ``windows/`` — pywin32 ServiceFramework + SCM installer
- ``macos/`` — launchd LaunchAgent plist

See: docs/proposals/NATIVE_OS_API_REVIEW.md §3.2
See: docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md §3.2
"""

from __future__ import annotations
