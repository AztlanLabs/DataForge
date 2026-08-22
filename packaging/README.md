# DataForge Packaging

This directory contains packaging configurations for building native Linux packages (deb/rpm) using [nfpm](https://github.com/goreleaser/nfpm).

## Directory Structure

```
packaging/
├── nfpm.yaml                    # nfpm package configuration
├── README.md                    # This file
├── assets/
│   ├── dataforge.desktop        # Freedesktop entry
│   ├── dataforge.svg            # Application icon (SVG source)
│   └── dataforge.png            # Application icon (256x256 PNG)
├── dbus/
│   └── com.dataforge.Engine.service  # D-Bus user service
├── scripts/
│   ├── postinst.sh              # Post-installation script
│   └── prerm.sh                 # Pre-removal script
└── systemd/
    ├── dataforge.service        # systemd --user service unit
    └── dataforge.socket         # systemd --user socket unit
```

## Prerequisites

Install nfpm:

```bash
# macOS
brew install nfpm

# Linux (deb/rpm)
go install github.com/goreleaser/nfpm/v2/cmd/nfpm@latest

# Or download from https://github.com/goreleaser/nfpm/releases
```

## Building Packages

### 1. Build the onedir bundle first

```bash
python build_exe.py onedir
```

This creates `dist/onedir/DataForge/` with the PyInstaller onedir output.

### 2. Generate the package icon (optional)

Convert SVG to PNG if needed:

```bash
# Using ImageMagick
convert -background none -resize 256x256 packaging/assets/dataforge.svg packaging/assets/dataforge.png

# Using rsvg-convert
rsvg-convert -w 256 -h 256 packaging/assets/dataforge.svg > packaging/assets/dataforge.png
```

### 3. Build deb package

```bash
nfpm pkg --packager deb --target dist/packages/
```

Output: `dist/packages/dataforge_0.2.0_amd64.deb`

### 4. Build rpm package

```bash
nfpm pkg --packager rpm --target dist/packages/
```

Output: `dist/packages/dataforge_0.2.0_amd64.rpm`

## Installation

### Debian/Ubuntu

```bash
sudo dpkg -i dist/packages/dataforge_0.2.0_amd64.deb
sudo apt-get install -f  # Fix dependencies if needed
```

### Fedora/RHEL

```bash
sudo rpm -i dist/packages/dataforge_0.2.0_amd64.rpm
```

## Package Contents

The package installs:

| Path | Description |
|------|-------------|
| `/opt/dataforge/` | PyInstaller onedir bundle (main application) |
| `/usr/bin/dataforge` | CLI shim (symlink to `/opt/dataforge/DataForge`) |
| `/usr/share/applications/dataforge.desktop` | Desktop entry |
| `/usr/share/icons/hicolor/256x256/apps/dataforge.png` | Application icon |
| `/usr/lib/systemd/user/dataforge.service` | systemd --user service unit |
| `/usr/lib/systemd/user/dataforge.socket` | systemd --user socket unit |
| `/usr/share/dbus-1/services/com.dataforge.Engine.service` | D-Bus user service |

## Service Management

After installation, the DataForge engine runs as a systemd --user service with socket activation:

```bash
# Check status
systemctl --user status dataforge.service

# View logs
journalctl --user -u dataforge.service

# Stop/start
systemctl --user stop dataforge.service
systemctl --user start dataforge.service

# Disable auto-start
systemctl --user disable dataforge.socket dataforge.service
```

## Uninstallation

### Debian/Ubuntu

```bash
sudo apt remove dataforge
```

### Fedora/RHEL

```bash
sudo rpm -e dataforge
```

The uninstall scripts automatically stop and disable the systemd units.

## Configuration

User configuration and data remain in `~/.dataforge/` (or XDG-compliant locations after TICK-001) and are **not** removed on uninstall. To fully purge:

```bash
rm -rf ~/.dataforge/
rm -rf ~/.config/DataForge/
rm -rf ~/.cache/DataForge/
rm -rf ~/.local/state/DataForge/
```

## CI Integration

In CI, build packages after the onedir bundle:

```yaml
- name: Build onedir bundle
  run: python build_exe.py onedir

- name: Build deb package
  run: nfpm pkg --packager deb --target dist/packages/

- name: Build rpm package
  run: nfpm pkg --packager rpm --target dist/packages/

- name: Upload artifacts
  uses: actions/upload-artifact@v4
  with:
    name: packages
    path: dist/packages/
```

## References

- [INSTALL_UPGRADE_LIFECYCLE.md](../docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md) — Full install/upgrade/remove lifecycle design
- [nfpm documentation](https://nfpm.goreleaser.com/) — Package configuration reference
- [systemd.unit](https://www.freedesktop.org/software/systemd/man/systemd.unit.html) — Unit file syntax
- [D-Bus specification](https://dbus.freedesktop.org/doc/dbus-specification.html) — Service files
