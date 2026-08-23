"""Tests for TICK-702 — R-CORE-7 logger makedirs bare filename guard.

Acceptance:
 - bare filename "app.log" -> no crash, file in cwd, makedirs not called with ''
 - empty string "" -> fallback to default log_file, no crash
 - deep path /tmp/a/b/c/app.log -> makedirs succeeds
 - existing logger tests still pass (covered in full suite)
"""

import logging
import os
import stat

from dataforge.core.logger import setup_logger


def _clean_logger(name):
    lg = logging.getLogger(name)
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    for f in list(lg.filters):
        try:
            lg.removeFilter(f)
        except Exception:
            pass
    lg.propagate = False
    return lg


def test_bare_filename_no_makedirs_crash(tmp_path, monkeypatch):
    """GIVEN bare filename WHEN called THEN no crash, file in cwd, makedirs not called with ''."""
    monkeypatch.chdir(tmp_path)
    calls = []
    orig_makedirs = os.makedirs

    def fake_makedirs(path, exist_ok=False):
        calls.append(path)
        return orig_makedirs(path, exist_ok=exist_ok)

    monkeypatch.setattr(os, "makedirs", fake_makedirs)

    name = "dataforge.test702.bare"
    _clean_logger(name)
    lg = setup_logger(name, "bare.log", level=logging.INFO)
    assert any(isinstance(h, logging.FileHandler) for h in lg.handlers), "bare filename should add FileHandler"
    # makedirs must not have been called with '' (empty)
    assert "" not in calls, f"makedirs should not be called with '' but got {calls!r}"
    lg.info("bare test 702")
    for h in lg.handlers:
        try:
            h.flush()
        except Exception:
            pass
    assert (tmp_path / "bare.log").exists(), "file should be created in cwd"
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    lg.filters.clear()


def test_bare_filename_with_dot_slash(tmp_path, monkeypatch):
    """Variant: ./app.log has dirname '.' -> makedirs('.') is ok or skipped."""
    monkeypatch.chdir(tmp_path)
    name = "dataforge.test702.dotbare"
    _clean_logger(name)
    lg = setup_logger(name, "./dot.log", level=logging.INFO)
    assert any(isinstance(h, logging.FileHandler) for h in lg.handlers)
    lg.info("dot test")
    for h in lg.handlers:
        try:
            h.flush()
        except Exception:
            pass
    assert (tmp_path / "dot.log").exists()
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    lg.filters.clear()


def test_empty_string_fallback(tmp_path, monkeypatch):
    """GIVEN log_file='' WHEN called THEN fallback to default log_file, no crash, makedirs not called with ''."""
    # Redirect fallback to tmp_path to avoid writing to real home
    import importlib
    import sys

    logger_module = sys.modules.get("dataforge.core.logger") or importlib.import_module("dataforge.core.logger")

    fallback = str(tmp_path / "fallback" / "app.log")
    monkeypatch.setattr(logger_module, "default_log_path", fallback)

    calls = []
    orig_makedirs = os.makedirs

    def fake_makedirs(path, exist_ok=False):
        calls.append(path)
        return orig_makedirs(path, exist_ok=exist_ok)

    monkeypatch.setattr(os, "makedirs", fake_makedirs)

    name = "dataforge.test702.empty"
    _clean_logger(name)
    lg = setup_logger(name, "", level=logging.INFO)
    assert "" not in calls, f"makedirs should not be called with '' got {calls}"
    # Should have file handler at fallback
    assert any(isinstance(h, logging.FileHandler) for h in lg.handlers), "empty string should fallback to default and add FileHandler"
    lg.info("empty fallback test")
    for h in lg.handlers:
        try:
            h.flush()
        except Exception:
            pass
    assert os.path.exists(fallback), f"fallback file should exist at {fallback}"
    # dirname fallback should have been makedirs
    assert str(tmp_path / "fallback") in calls or os.path.dirname(fallback) in calls
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    lg.filters.clear()


def test_whitespace_string_fallback(tmp_path, monkeypatch):
    """Whitespace-only log_file should also fallback."""
    import importlib
    import sys

    logger_module = sys.modules.get("dataforge.core.logger") or importlib.import_module("dataforge.core.logger")

    fallback = str(tmp_path / "fallback_ws" / "app.log")
    monkeypatch.setattr(logger_module, "default_log_path", fallback)

    name = "dataforge.test702.ws"
    _clean_logger(name)
    lg = setup_logger(name, "   ", level=logging.INFO)
    assert any(isinstance(h, logging.FileHandler) for h in lg.handlers)
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    lg.filters.clear()
    assert os.path.exists(fallback)


def test_deep_path_makedirs(tmp_path):
    """GIVEN deep path /tmp/a/b/c/app.log WHEN called THEN makedirs succeeds."""
    deep = tmp_path / "a" / "b" / "c" / "app.log"
    name = "dataforge.test702.deep"
    _clean_logger(name)
    lg = setup_logger(name, str(deep), level=logging.INFO)
    assert any(isinstance(h, logging.FileHandler) for h in lg.handlers)
    lg.info("deep path test")
    for h in lg.handlers:
        try:
            h.flush()
        except Exception:
            pass
    assert deep.exists()
    assert deep.parent.exists()
    mode = stat.S_IMODE(os.stat(deep).st_mode)
    assert mode == 0o600
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    lg.filters.clear()


def test_makedirs_oserror_fallback_to_stream_only(tmp_path, monkeypatch):
    """GIVEN makedirs raises OSError WHEN setup_logger THEN no crash, fallback to StreamHandler only."""
    monkeypatch.setattr(os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(OSError("perm denied")))

    name = "dataforge.test702.makedirs_err"
    _clean_logger(name)
    deep = str(tmp_path / "nope" / "app.log")
    lg = setup_logger(name, deep, level=logging.INFO)
    # Should still have console handler but no file handler
    assert any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in lg.handlers)
    assert not any(isinstance(h, logging.FileHandler) for h in lg.handlers), "file handler should be skipped on makedirs OSError"
    # Should not crash on emit
    lg.info("test after makedirs error")
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    lg.filters.clear()


def test_file_handler_oserror_fallback(tmp_path, monkeypatch):
    """GIVEN RotatingFileHandler raises OSError WHEN called THEN fallback to StreamHandler only."""
    import importlib
    import sys

    logger_module = sys.modules.get("dataforge.core.logger") or importlib.import_module("dataforge.core.logger")

    def failing_rfh(*a, **k):
        raise OSError("handler fail")

    monkeypatch.setattr(logger_module, "RotatingFileHandler", failing_rfh)

    name = "dataforge.test702.handler_err"
    _clean_logger(name)
    lg = setup_logger(name, str(tmp_path / "app.log"), level=logging.INFO)
    assert any(isinstance(h, logging.StreamHandler) for h in lg.handlers)
    # No file handler because it failed
    assert not any(isinstance(h, logging.FileHandler) for h in lg.handlers)
    lg.info("handler error test")
    lg.handlers.clear()
    lg.filters.clear()
    # restore not needed due to monkeypatch


def test_none_log_file_only_stream(tmp_path):
    """GIVEN log_file=None WHEN called THEN only StreamHandler, no crash."""
    name = "dataforge.test702.none"
    _clean_logger(name)
    lg = setup_logger(name, None, level=logging.INFO)
    assert len([h for h in lg.handlers if isinstance(h, logging.FileHandler)]) == 0
    assert any(isinstance(h, logging.StreamHandler) for h in lg.handlers)
    lg.info("none test")
    lg.handlers.clear()
    lg.filters.clear()
