"""TICK-927 — Dependencies: optional imports, acquire cleanup, VSS, package extras.

Covers STABILITY_AUDIT_2026-08-23 P1.13 (CLI/Pillow import coupling, pyproject
deps) and P1.20 (acquire temp leak, VSS returning None without a contract):
the `fm` CLI must import without GUI/media dependencies, pyproject must declare
extras and core deps, sudo-copied temp files must always be cleaned up, and the
Windows VSS provider must fall back honestly (None, never raise).
"""
from __future__ import annotations

import builtins
import importlib
import os
import shutil
import sys
import tempfile
import tomllib
import types
from pathlib import Path

import pytest

import dataforge.core.acquire as acquire

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"


def _block_pillow(monkeypatch):
    for name in ("PIL", "PIL.Image", "PIL.ExifTags", "PIL.PngImagePlugin"):
        monkeypatch.setitem(sys.modules, name, None)


def _import_fresh(monkeypatch, module_name):
    sys.modules.pop(module_name, None)
    _block_pillow(monkeypatch)
    return importlib.import_module(module_name)


# ---------------------------------------------------------------------------
# Lazy imports — CLI and cleaner importable without Pillow (P1.13)
# ---------------------------------------------------------------------------


def test_cli_importable_without_pillow(monkeypatch):
    """GIVEN Pillow unavailable WHEN cli is imported THEN no ImportError and Pillow stays unloaded."""
    mod = _import_fresh(monkeypatch, "dataforge.cli")
    assert mod is not None
    assert sys.modules["PIL"] is None


def test_cleaner_importable_without_pillow(monkeypatch):
    """GIVEN Pillow unavailable WHEN cleaner is imported THEN no ImportError and Pillow stays unloaded."""
    mod = _import_fresh(monkeypatch, "dataforge.modules.cleaner")
    assert mod is not None
    assert mod.remove_empty_folders is not None
    assert sys.modules["PIL"] is None


# ---------------------------------------------------------------------------
# pyproject extras and core deps (P1.13)
# ---------------------------------------------------------------------------


def _load_pyproject():
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def _all_dep_specs(pyproject):
    deps = list(pyproject.get("project", {}).get("dependencies", []))
    extras = pyproject.get("project", {}).get("optional-dependencies", {})
    for group in extras.values():
        deps.extend(group)
    return deps


def test_pyproject_has_extras():
    """GIVEN pyproject.toml WHEN parsed THEN gui/media/forensics/dev extras exist."""
    pyproject = _load_pyproject()
    extras = pyproject["project"]["optional-dependencies"]
    for group in ("gui", "media", "forensics", "dev"):
        assert group in extras, f"missing extras group: {group}"
    assert any(spec.lower().startswith("pyqt5") for spec in extras["gui"])
    assert any(spec.lower().startswith("pillow") for spec in extras["media"])
    assert any(spec.lower().startswith("pymupdf") for spec in extras["media"])


def test_pyproject_has_msgpack():
    """GIVEN pyproject.toml WHEN parsed THEN msgpack is declared in deps or extras."""
    specs = _all_dep_specs(_load_pyproject())
    assert any(spec.lower().startswith("msgpack") for spec in specs)


def test_pyproject_has_platformdirs():
    """GIVEN pyproject.toml WHEN parsed THEN platformdirs is declared in deps or extras."""
    specs = _all_dep_specs(_load_pyproject())
    assert any(spec.lower().startswith("platformdirs") for spec in specs)


# ---------------------------------------------------------------------------
# Acquire temp cleanup (P1.20)
# ---------------------------------------------------------------------------


@pytest.fixture
def _locked_file(tmp_path):
    src = tmp_path / "locked.txt"
    src.write_text("top secret", encoding="utf-8")
    return src


@pytest.fixture
def _deny_sudo(monkeypatch):
    """Never invoke the real sudo binary — tests stub the sudo cp/dd result."""

    def _fake_run(cmd, capture_output=False, text=False, timeout=None):
        raise FileNotFoundError("sudo not available")

    monkeypatch.setattr(acquire.subprocess, "run", _fake_run)
    return monkeypatch


@pytest.fixture
def _lock_source(monkeypatch):
    """Make os.open fail only for the locked source path. The os module is
    shared process-wide, so other paths (tempfile.mkstemp staging) must pass."""

    def _deny_open(path, flags, *args, **kwargs):
        if str(path) == str(_lock_source.target):
            raise PermissionError("simulated locked file")
        return _lock_source.real_open(path, flags, *args, **kwargs)

    _lock_source.real_open = os.open
    _lock_source.target = None
    monkeypatch.setattr(os, "open", _deny_open)
    return _lock_source


def test_acquire_temp_cleaned_on_close(tmp_path, monkeypatch, _locked_file, _lock_source, _deny_sudo):
    """GIVEN a sudo-copied file WHEN the acquired handle closes THEN the temp copy is removed."""
    src = _locked_file
    _lock_source.target = str(src)
    captured = {}

    def _fake_run(cmd, capture_output=False, text=False, timeout=None):
        if cmd and len(cmd) >= 3 and cmd[0] == "sudo" and cmd[2] == "cp":
            src_path, dst = cmd[4], cmd[5]
            shutil.copyfile(src_path, dst)
            captured["tmp"] = dst
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        raise FileNotFoundError("sudo not available")

    monkeypatch.setattr(acquire.subprocess, "run", _fake_run)

    with acquire.acquire_file(str(src), "rb") as fh:
        assert fh.read() == b"top secret"
        assert os.path.exists(captured["tmp"])

    assert not os.path.exists(captured["tmp"]), "temp copy leaked after close"


def test_acquire_temp_cleaned_on_exception(tmp_path, monkeypatch, _locked_file, _lock_source, _deny_sudo):
    """GIVEN sudo copy staging fails WHEN acquire falls back and still fails THEN every temp is removed."""
    src = _locked_file
    _lock_source.target = str(src)
    created = []
    real_mkstemp = tempfile.mkstemp

    def _fake_mkstemp():
        fd, p = real_mkstemp()
        created.append(p)
        return fd, p

    real_open = builtins.open

    def _fake_open(path, mode="r", *args, **kwargs):
        if str(path) == str(src) and "r" in mode:
            raise PermissionError("simulated locked file")
        return real_open(path, mode, *args, **kwargs)

    def _fake_run(cmd, capture_output=False, text=False, timeout=None):
        if cmd and len(cmd) >= 3 and cmd[0] == "sudo" and cmd[2] == "cp":
            return types.SimpleNamespace(returncode=1, stdout="", stderr="")
        raise FileNotFoundError("sudo not available")

    monkeypatch.setattr(acquire.tempfile, "mkstemp", _fake_mkstemp)
    monkeypatch.setattr(acquire, "open", _fake_open, raising=False)
    monkeypatch.setattr(acquire.subprocess, "run", _fake_run)

    with pytest.raises(PermissionError):
        with acquire.acquire_file(str(src), "rb"):
            raise AssertionError("acquire should not have yielded")

    assert created, "expected sudo staging to create temp files"
    for p in created:
        assert not os.path.exists(p), f"temp file leaked after failure: {p}"


def test_acquire_missing_file_no_temp_leak(tmp_path, monkeypatch, _deny_sudo):
    """GIVEN a missing path WHEN acquire fails with FileNotFoundError THEN no temp file remains."""
    missing = tmp_path / "does-not-exist.txt"
    with pytest.raises(FileNotFoundError):
        with acquire.acquire_file(str(missing), "rb"):
            raise AssertionError("acquire should not have yielded")


# ---------------------------------------------------------------------------
# VSS honesty (P1.20)
# ---------------------------------------------------------------------------


def test_vss_returns_none(monkeypatch):
    """GIVEN the VSS provider WHEN invoked on non-Windows THEN None (never raises)."""
    assert acquire._try_windows_acquire("C:\\tmp\\file.txt", "rb") is None


def test_vss_windows_path_returns_none(monkeypatch):
    """GIVEN Windows WITH vssadmin missing or shadow copies present WHEN VSS acquire runs THEN None, no raise."""
    monkeypatch.setattr(acquire.sys, "platform", "win32")

    def _vssadmin_available(cmd, capture_output=False, text=False, timeout=None):
        assert cmd[0] == "vssadmin"
        return types.SimpleNamespace(returncode=0, stdout="Shadow Copy available", stderr="")

    monkeypatch.setattr(acquire.subprocess, "run", _vssadmin_available)
    assert acquire._try_windows_acquire("C:\\tmp\\file.txt", "rb") is None