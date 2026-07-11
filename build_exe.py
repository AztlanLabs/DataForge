import argparse
import os
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


def build_add_data_arg(source: Path, target: str) -> str:
    return f'--add-data={source}{DATA_SEPARATOR}{target}'


def build_common_args(profile_name: str, executable_name: str) -> list[str]:
    profile_root = PROJECT_ROOT / 'buildspec' / profile_name
    profile_root.mkdir(parents=True, exist_ok=True)
    args = [
        str(ENTRY_SCRIPT),
        f'--name={executable_name}',
        '--noconfirm',
        '--clean',
        f'--distpath={PROJECT_ROOT / "dist" / profile_name}',
        f'--workpath={PROJECT_ROOT / "build" / profile_name}',
        f'--specpath={profile_root}',
        build_add_data_arg(PLUGIN_SOURCE, PLUGIN_TARGET),
    ]
    for hidden_import in COMMON_HIDDEN_IMPORTS:
        args.append(f'--hidden-import={hidden_import}')
    return args


def release_args() -> list[str]:
    return build_common_args('release', 'DataForge') + [
        '--windowed',
        '--onefile',
    ]


def debug_args() -> list[str]:
    return build_common_args('debug', 'DataForge-debug') + [
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
        choices=('release', 'debug', 'all'),
        default='release',
        help='Select which build profile to generate.',
    )
    return parser.parse_args()


def run_build(profile: str) -> None:
    if profile == 'release':
        args = release_args()
    elif profile == 'debug':
        args = debug_args()
    else:
        raise ValueError(f'Unsupported profile: {profile}')

    print(f'Building {profile} profile...')
    PyInstaller.__main__.run(args)
    print(f'{profile.capitalize()} build complete.')


def main() -> None:
    args = parse_args()

    if args.profile == 'all':
        run_build('release')
        run_build('debug')
        return

    run_build(args.profile)


if __name__ == '__main__':
    main()
