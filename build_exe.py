import argparse
import os
import sys
from pathlib import Path

import PyInstaller.__main__


PROJECT_ROOT = Path(__file__).resolve().parent
ENTRY_SCRIPT = PROJECT_ROOT / 'run_ui.py'
PLUGIN_SOURCE = PROJECT_ROOT / 'dataforge' / 'ui' / 'plugins'
PLUGIN_TARGET = 'dataforge/ui/plugins'
DATA_SEPARATOR = os.pathsep

COMMON_HIDDEN_IMPORTS = (
    'PyQt5',
    'PyQt5.QtCore',
    'PyQt5.QtWidgets',
    'PyQt5.QtGui',
    'PIL',
    'send2trash',
    'pypdf',
)

PLATFORM_HIDDEN_IMPORTS = {
    'windows': (
        'ctypes.wintypes',
        'win32api',
        'win32con',
        'win32gui',
        'pywintypes',
        'pythoncom',
    ),
    'darwin': (
        'Foundation',
        'AppKit',
        'objc',
        'pkg_resources',
    ),
    # TICK-930 P1.19: detect_platform() returns 'macos'; keep both spellings
    # so lookups succeed regardless of which name is used.
    'macos': (
        'Foundation',
        'AppKit',
        'objc',
        'pkg_resources',
    ),
    'linux': (
        'gi',
        'gi.repository.Gtk',
        'gi.repository.Gdk',
        'gi.repository.GLib',
    ),
}

PLATFORM_EXCLUDES = {
    'windows': (
        'gtk',
        'gi',
    ),
    'darwin': (
        'gtk',
        'gi',
    ),
    'macos': (
        'gtk',
        'gi',
    ),
    'linux': (
        'win32api',
        'win32con',
        'win32gui',
    ),
}

# TICK-930 P1.19: detect_platform() returns 'macos' but the lookup dicts
# above are keyed by sys.platform values ('darwin'). Map one to the other.
PLATFORM_MAP = {
    'linux': 'linux',
    'darwin': 'macos',
    'win32': 'windows',
}


def normalize_platform(platform_name: str) -> str:
    """Map raw sys.platform values to canonical build platform names."""
    return PLATFORM_MAP.get(platform_name, platform_name)


def get_platform_hidden_imports(platform_name: str) -> tuple:
    """Platform-specific hidden imports, tolerant of macos/darwin naming."""
    key = PLATFORM_MAP.get(platform_name, platform_name)
    return PLATFORM_HIDDEN_IMPORTS.get(key, ())


def get_platform_excludes(platform_name: str) -> tuple:
    """Platform-specific excludes, tolerant of macos/darwin naming."""
    key = PLATFORM_MAP.get(platform_name, platform_name)
    return PLATFORM_EXCLUDES.get(key, ())


def detect_platform() -> str:
    """Detect current platform."""
    if sys.platform == 'win32':
        return 'windows'
    elif sys.platform == 'darwin':
        return 'macos'
    else:
        return 'linux'


def get_platform_icon(platform_name: str) -> Path | None:
    """Get platform-specific icon path if it exists."""
    icons = {
        'windows': PROJECT_ROOT / 'packaging' / 'assets' / 'dataforge.ico',
        'macos': PROJECT_ROOT / 'packaging' / 'assets' / 'dataforge.icns',
        'linux': PROJECT_ROOT / 'packaging' / 'assets' / 'dataforge.png',
    }
    icon_path = icons.get(platform_name)
    if icon_path and icon_path.exists():
        return icon_path
    return None


def build_add_data_arg(source: Path, target: str) -> str:
    return f'--add-data={source}{DATA_SEPARATOR}{target}'


def build_common_args(
    profile_name: str,
    executable_name: str,
    platform_name: str,
) -> list[str]:
    profile_root = PROJECT_ROOT / 'buildspec' / profile_name
    profile_root.mkdir(parents=True, exist_ok=True)

    # Include platform in dist path for multi-platform builds
    dist_name = f'{profile_name}-{platform_name}' if platform_name != detect_platform() else profile_name
    dist_path = PROJECT_ROOT / 'dist' / dist_name

    args = [
        str(ENTRY_SCRIPT),
        f'--name={executable_name}',
        '--noconfirm',
        '--clean',
        f'--distpath={dist_path}',
        f'--workpath={PROJECT_ROOT / "build" / dist_name}',
        f'--specpath={profile_root}',
        build_add_data_arg(PLUGIN_SOURCE, PLUGIN_TARGET),
    ]

    # Add common hidden imports
    for hidden_import in COMMON_HIDDEN_IMPORTS:
        args.append(f'--hidden-import={hidden_import}')

    # Add platform-specific hidden imports
    for hidden_import in get_platform_hidden_imports(platform_name):
        args.append(f'--hidden-import={hidden_import}')

    # Add platform-specific excludes
    for exclude in get_platform_excludes(platform_name):
        args.append(f'--exclude-module={exclude}')

    # Add icon if available
    icon_path = get_platform_icon(platform_name)
    if icon_path:
        args.append(f'--icon={icon_path}')

    return args


def release_args(platform_name: str) -> list[str]:
    args = build_common_args('release', 'DataForge', platform_name)
    args.append('--onefile')

    # --windowed is not supported on Linux (no effect, but doesn't hurt)
    # On Windows/macOS it suppresses the console window
    if platform_name in ('windows', 'macos'):
        args.append('--windowed')

    return args


def onedir_args(platform_name: str) -> list[str]:
    args = build_common_args('onedir', 'DataForge', platform_name)
    args.append('--onedir')

    if platform_name in ('windows', 'macos'):
        args.append('--windowed')

    return args


def debug_args(platform_name: str) -> list[str]:
    return build_common_args('debug', 'DataForge-debug', platform_name) + [
        '--console',
        '--onedir',
        '--debug=all',
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Build DataForge PyInstaller bundles.',
    )
    parser.add_argument(
        'profile',
        nargs='?',
        choices=('release', 'onedir', 'debug', 'all'),
        default='release',
        help='Select which build profile to generate.',
    )
    parser.add_argument(
        '-p', '--platform',
        choices=('auto', 'linux', 'windows', 'macos'),
        default='auto',
        help='Target platform (default: auto-detect current OS).',
    )
    return parser.parse_args()


def run_build(profile: str, platform_name: str) -> None:
    if profile == 'release':
        args = release_args(platform_name)
    elif profile == 'onedir':
        args = onedir_args(platform_name)
    elif profile == 'debug':
        args = debug_args(platform_name)
    else:
        raise ValueError(f'Unsupported profile: {profile}')

    print(f'Building {profile} profile for {platform_name}...')
    PyInstaller.__main__.run(args)
    print(f'{profile.capitalize()} build complete for {platform_name}.')


def main() -> None:
    args = parse_args()

    # Resolve platform
    if args.platform == 'auto':
        platform_name = detect_platform()
    else:
        platform_name = args.platform

    # Warn if building for a different platform
    current_platform = detect_platform()
    if platform_name != current_platform:
        print(
            f'Warning: Building for {platform_name} on {current_platform}. '
            f'PyInstaller cannot cross-compile; the build may fail or produce '
            f'a non-functional binary. Use a {platform_name} machine for reliable builds.',
            file=sys.stderr,
        )

    if args.profile == 'all':
        run_build('release', platform_name)
        run_build('onedir', platform_name)
        run_build('debug', platform_name)
        return

    run_build(args.profile, platform_name)


if __name__ == '__main__':
    main()
