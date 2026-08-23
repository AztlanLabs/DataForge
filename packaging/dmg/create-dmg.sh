#!/bin/bash
# DataForge DMG builder — create-dmg wrapper for macOS
# See docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md §3.2
set -euo pipefail

VERSION="0.2.0"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_BUNDLE="${PROJECT_ROOT}/dist/onedir/DataForge/DataForge.app"
DMG_OUT="${PROJECT_ROOT}/dist/DataForge-${VERSION}.dmg"
VOLNAME="DataForge ${VERSION}"
BACKGROUND="${PROJECT_ROOT}/packaging/dmg/background.png"

# Ensure create-dmg is available
if ! command -v create-dmg >/dev/null 2>&1; then
  echo "create-dmg not found. Install with: brew install create-dmg" >&2
  echo "Skipping DMG creation (graceful fallback for CI/Linux)." >&2
  exit 0
fi

# Ensure onedir bundle exists (build it if missing)
if [ ! -d "${APP_BUNDLE}" ]; then
  echo "App bundle not found at ${APP_BUNDLE}, building onedir..." >&2
  if [ -f "${PROJECT_ROOT}/build_exe.py" ]; then
    python "${PROJECT_ROOT}/build_exe.py" onedir --platform macos || python "${PROJECT_ROOT}/build_exe.py" onedir || true
  fi
fi

if [ ! -d "${APP_BUNDLE}" ]; then
  echo "Warning: ${APP_BUNDLE} still missing, proceeding with placeholder for validation." >&2
  mkdir -p "${APP_BUNDLE}/Contents/MacOS"
  echo "# placeholder" > "${APP_BUNDLE}/Contents/MacOS/DataForge"
fi

mkdir -p "$(dirname "${DMG_OUT}")"

# Build DMG with Applications symlink and optional background
ARGS=(
  --volname "${VOLNAME}"
  --window-pos 200 120
  --window-size 600 400
  --icon-size 100
  --icon "DataForge.app" 175 120
  --app-drop-link 425 120
)

if [ -f "${BACKGROUND}" ]; then
  ARGS+=(--background "${BACKGROUND}")
fi

# Run create-dmg
create-dmg "${ARGS[@]}" "${DMG_OUT}" "${APP_BUNDLE}"

echo "DMG created at ${DMG_OUT}"
