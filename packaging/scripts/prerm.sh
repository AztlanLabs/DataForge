#!/bin/bash
set -e

# DataForge prerm script
# Runs before package removal on deb/rpm systems

echo "Stopping DataForge services..."

# Stop and disable systemd user units
if command -v systemctl >/dev/null 2>&1; then
    systemctl --user stop dataforge.socket 2>/dev/null || true
    systemctl --user stop dataforge.service 2>/dev/null || true
    systemctl --user disable dataforge.socket 2>/dev/null || true
    systemctl --user disable dataforge.service 2>/dev/null || true
    systemctl --user daemon-reload 2>/dev/null || true

    echo "DataForge systemd units stopped and disabled."
fi

echo "DataForge removal complete."
