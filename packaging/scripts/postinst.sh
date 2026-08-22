#!/bin/bash
set -e

# DataForge postinst script
# Runs after package installation on deb/rpm systems

echo "Configuring DataForge..."

# Reload systemd user units
if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload 2>/dev/null || true

    # Enable and start socket (socket activation)
    systemctl --user enable dataforge.socket 2>/dev/null || true
    systemctl --user start dataforge.socket 2>/dev/null || true

    echo "DataForge systemd units installed and enabled."
fi

# Update desktop database
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications 2>/dev/null || true
fi

# Update icon cache
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache /usr/share/icons/hicolor 2>/dev/null || true
fi

echo "DataForge installation complete."
