from setuptools import setup

# All package metadata (name, version, dependencies, entry points) now
# lives in pyproject.toml. This shim exists only so that
# `python setup.py --version` / `python setup.py sdist` keep working
# unchanged (see docs/CONTRIBUTING.md's release runbook).
setup()
