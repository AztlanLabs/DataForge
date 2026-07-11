from setuptools import setup, find_packages

setup(
    name="filemanager-utils",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click",
        "rich",
        "tqdm",
        "send2trash",
        "psutil>=5.9.0",
        "python-magic>=0.4.27",
        "PyExifTool>=0.5.0",
        "mutagen>=1.47.0",
        "py-cpuinfo>=9.0.0",
    ],
    entry_points={
        "console_scripts": [
            "fm=filemanager.cli:main",
        ],
    },
    # Note: PyQt5 and Pillow are intentionally excluded here since they only
    # back the desktop GUI (`run_ui.py`), not the `fm` CLI console script.
    # Install from requirements.txt for full GUI/media support.
)
