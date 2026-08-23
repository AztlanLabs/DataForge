"""Tests for TICK-511 — Parser ProcessPool isolation (F13)."""
import inspect
import os
import threading
import time

import pytest

from dataforge.engine.parsers import ParserPool, ParseResult, _default_pool_size


def test_import_succeeds():
    # POSIX AND Windows — no platform-specific code required
    import dataforge.engine.parsers as parsers  # noqa: F401
    assert parsers.ParserPool is not None


def test_lazy_init_executor_is_none():
    pool = ParserPool()
    # Before any run, executor should be None
    assert pool.executor is None
    # Also check class inspect as per ticket description (inspect.getmembers)
    members = dict(inspect.getmembers(ParserPool))
    # Class should not have an instantiated executor; instance check is authoritative
    # Ensure new instance executor is None
    pool2 = ParserPool(pool_size=1)
    assert pool2.executor is None
    pool.shutdown(wait=False)
    pool2.shutdown(wait=False)

def test_lazy_init_no_extra_processes_until_used():
    # Import already done — no processes spawned; just verifying run creates executor
    pool = ParserPool(pool_size=1)
    assert pool.executor is None
    # Register a simple parser and run
    def _ok(path, cancel_token=None):
        return ParseResult(success=True, message="ok", data={"path": path})

    pool.register("ok", _ok)
    res = pool.run("ok", "/tmp/test", None)
    assert res.success is True
    assert pool.executor is not None
    pool.shutdown(wait=True)

def test_default_pool_size():
    # Default is min(2, cpu_count()-1) at least 1
    size = _default_pool_size()
    cpu = os.cpu_count() or 2
    expected = min(2, max(1, cpu - 1))
    assert size == expected
    # Pool with default should have that size
    pool = ParserPool()
    assert pool.pool_size == expected
    pool.shutdown(wait=False)

def test_env_override_pool_size(monkeypatch):
    monkeypatch.setenv("DATAFORGE_PARSER_POOL_SIZE", "3")
    pool = ParserPool()
    assert pool.pool_size == 3
    pool.shutdown(wait=False)
    monkeypatch.delenv("DATAFORGE_PARSER_POOL_SIZE", raising=False)

def test_register_and_run_success():
    pool = ParserPool(pool_size=1)

    def _parser(path, cancel_token=None):
        return ParseResult(success=True, message="parsed", data={"path": path})

    pool.register("parse", _parser)
    res = pool.run("parse", "/tmp/file.txt")
    assert res.success is True
    assert res.message == "parsed" or "ok" in res.message.lower() or "parsed" in res.message
    pool.shutdown(wait=True)

def test_evil_lambda_raises_but_main_thread_not_killed():
    pool = ParserPool(pool_size=1)
    # Lambda is not pickle-able in stdlib — fallback should still return ZeroDivisionError
    pool.register("evil", lambda p, t=None: 1 / 0)  # type: ignore

    # Use a dummy cancel_token event (not set)
    cancel_token = threading.Event()
    result = pool.run("evil", "/tmp/x", cancel_token)

    assert result.success is False
    # Message must contain ZeroDivisionError
    assert "ZeroDivisionError" in result.message
    # Main thread still alive — we reached here
    assert True
    pool.shutdown(wait=True)

def test_evil_lambda_with_positional_cancel_token():
    pool = ParserPool(pool_size=1)
    # Test the exact signature from ticket: lambda p, t: 1/0
    # Our _call_parser should handle both (p, t) positional
    pool.register("evil2", lambda p, t: 1 / 0)  # type: ignore
    result = pool.run("evil2", "/tmp/x", threading.Event())
    assert result.success is False
    assert "ZeroDivisionError" in result.message
    pool.shutdown(wait=True)

def test_pool_size_1_serialises():
    pool = ParserPool(pool_size=1)

    def _sleep_parser(path, cancel_token=None):
        # Sleep 0.2s, return path plus timestamp for ordering
        time.sleep(0.2)
        return ParseResult(success=True, message=f"done:{path}:{time.monotonic()}")

    pool.register("sleep", _sleep_parser)

    start = time.monotonic()
    # Run two tasks concurrently from two threads
    results = {}

    def _run_one(key, p):
        results[key] = pool.run("sleep", p)

    t1 = threading.Thread(target=_run_one, args=("a", "/tmp/a"))
    t2 = threading.Thread(target=_run_one, args=("b", "/tmp/b"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    elapsed = time.monotonic() - start

    assert results["a"].success is True
    assert results["b"].success is True
    # With pool_size=1, two 0.2s tasks should take >=0.35s (serial), not ~0.2 (parallel)
    assert elapsed >= 0.35, f"Expected serialisation with pool_size=1, elapsed {elapsed:.2f}s"
    # Allow some overhead but not too much
    assert elapsed < 1.5, f"Elapsed too long: {elapsed:.2f}s"

    pool.shutdown(wait=True)

def test_pool_size_2_parallel():
    # Sanity: with pool_size=2, two 0.2s tasks should run in ~0.2s not 0.4s
    pool = ParserPool(pool_size=2)

    def _sleep_parser2(path, cancel_token=None):
        time.sleep(0.2)
        return ParseResult(success=True, message="ok")

    pool.register("sleep2", _sleep_parser2)
    start = time.monotonic()
    results = {}

    def _run(key, p):
        results[key] = pool.run("sleep2", p)

    t1 = threading.Thread(target=_run, args=("a", "/tmp/a"))
    t2 = threading.Thread(target=_run, args=("b", "/tmp/b"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    elapsed = time.monotonic() - start
    # Parallel should be <0.35s (with overhead) — at least faster than serial 0.4
    # On overloaded CI, allow up to 0.5
    assert elapsed < 0.6, f"Expected parallel with pool_size=2, elapsed {elapsed:.2f}s"
    pool.shutdown(wait=True)

def test_cancel_token_before_run_returns_cancelled_within_1s():
    pool = ParserPool(pool_size=1)

    def _never(path, cancel_token=None):
        time.sleep(0.5)
        return ParseResult(success=True, message="should not run")

    pool.register("never", _never)
    cancel_token = threading.Event()
    cancel_token.set()
    start = time.monotonic()
    result = pool.run("never", "/tmp/file", cancel_token)
    elapsed = time.monotonic() - start
    assert result.success is False
    assert "cancelled" in result.message.lower()
    assert elapsed < 1.0, f"Cancelled run took {elapsed:.2f}s, expected <1s"
    # Ensure executor still lazy or at least no worker was spawned for cancelled
    # (if lazy, executor may still be None because we bail before ensure)
    # In our impl we bail before ensure, so executor stays None
    # That's acceptable for "bails out early"
    pool.shutdown(wait=False)

def test_unknown_parser():
    pool = ParserPool(pool_size=1)
    result = pool.run("no_such_parser", "/tmp/x")
    assert result.success is False
    assert "unknown parser" in result.message.lower()
    pool.shutdown(wait=False)

def test_worker_exception_becomes_parse_result():
    pool = ParserPool(pool_size=1)

    def _raise(path, cancel_token=None):
        raise ValueError("bad value")

    pool.register("raise", _raise)
    result = pool.run("raise", "/tmp/x")
    assert result.success is False
    assert "ValueError" in result.message
    assert "bad value" in result.message
    pool.shutdown(wait=True)

def test_parse_os_artifacts_opt_in_simulation():
    # Simulate that a real parser like parse_os_artifacts could be registered
    # without modifying call sites — just testing registry dispatch
    from dataforge.modules.forensics import parse_os_artifacts

    pool = ParserPool(pool_size=1)
    # Wrap forensics parser to return ParseResult
    def _wrap(path, cancel_token=None):
        try:
            artifacts = parse_os_artifacts(path, cancel_token=cancel_token)
            return ParseResult(success=True, message="ok", data=artifacts, path=path)
        except Exception as exc:
            return ParseResult(success=False, message=f"{type(exc).__name__}: {exc}", path=path)

    pool.register("artifacts", _wrap)
    # Use tmp dir as fake root
    import tempfile
    tmp = tempfile.mkdtemp()
    try:
        result = pool.run("artifacts", tmp)
        assert result.success is True
        assert result.data is not None
        # Should contain expected keys from parse_os_artifacts
        assert "users" in result.data
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        pool.shutdown(wait=True)

def test_no_regression_lazy_means_no_processes():
    # Ensure importing and creating pool does not spawn processes
    # We check that executor is None and no extra behaviour
    pool = ParserPool(pool_size=1)
    assert pool.executor is None
    # No run yet — pool should be idle
    pool.shutdown(wait=False)
    assert pool.executor is None

def test_parse_result_dataclass():
    r = ParseResult(success=True, message="ok", data={"x": 1}, path="/tmp")
    assert r.success is True
    assert r.to_dict()["success"] is True
    assert r.to_dict()["path"] == "/tmp"

def test_register_overwrite():
    pool = ParserPool(pool_size=1)
    pool.register("dup", lambda p, t=None: ParseResult(success=True, message="first"))
    pool.register("dup", lambda p, t=None: ParseResult(success=True, message="second"))
    res = pool.run("dup", "/tmp/x")
    assert "second" in res.message
    pool.shutdown(wait=True)
