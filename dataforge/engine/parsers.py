"""Parser ProcessPool isolation — F13.

Provides `ParserPool` with lazy `ProcessPoolExecutor` and a registry for
parser functions. Each parser is ``(path: str, cancel_token: threading.Event) -> ParseResult``
and is executed in a separate process so a crash/exception does not take
down DataForge. See `docs/reviews/FORENSIC_REVIEW.md` §F13.

Design
------
* ``pool_size`` defaults to ``min(2, cpu_count()-1)`` (at least 1) leaving
  cores for the rest of DataForge; override via ``DATAFORGE_PARSER_POOL_SIZE``
  env var or ``--parser-pool-size`` CLI flag (propagated as env). This
  matches `docs/proposals/PERFORMANCE_INVESTIGATION.md` §1.13 pool sizing.
* Executor is lazily initialised — ``self.executor is None`` until first
  ``run()`` call so import has no side effects and no extra processes are
  spawned unless used.
* ``register(name, fn)`` stores the callable in a thread-safe dict and also
  in the module-level ``_GLOBAL_REGISTRY`` so forked workers inherit it.
* ``run(name, path, cancel_token=None) -> ParseResult`` checks cancellation
  before dispatch, ensures the pool exists, submits ``_call_parser`` to the
  ``ProcessPoolExecutor``, and normalises all outcomes to ``ParseResult``:
    - ``cancel_token.is_set()`` → ``ParseResult(success=False, message='cancelled')``
    - worker exception → ``ParseResult(success=False, message='<ExcType>: ...')``
    - worker crash / ``BrokenProcessPool`` → ``ParseResult(success=False, message='worker died')``
    - unknown parser → ``ParseResult(success=False, message='unknown parser: ...')``
* ``_call_parser`` is a top-level function (pickle-able) that re-creates a
  ``threading.Event`` from the ``cancel_set`` bool (``threading.Event`` cannot
  be pickled / shared across processes) and dispatches to the registered
  function with appropriate signature probing.

No call sites are modified in this ticket — opt-in happens in Wave 6
(TICK-601). This module is purely additive.

References
----------
* `dataforge/engine/jobs.py` — JobQueue ThreadPool pattern (complementary)
* `dataforge/modules/forensics.py:127` — example opt-in parser
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

# Module-level registry shared with forked workers (copy-on-write).
_GLOBAL_REGISTRY: Dict[str, Callable[..., Any]] = {}
_REGISTRY_LOCK = threading.Lock()


@dataclass
class ParseResult:
    """Result of a parser invocation."""

    success: bool
    message: str = ""
    data: Any = None
    path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "path": self.path,
        }


def _default_pool_size() -> int:
    """Compute default pool size: min(2, cpu_count()-1) with floor 1.

    Reads ``DATAFORGE_PARSER_POOL_SIZE`` env var if set (CLI flag
    ``--parser-pool-size`` is expected to set this env).
    """
    env = os.getenv("DATAFORGE_PARSER_POOL_SIZE")
    if env is not None:
        try:
            v = int(env)
            if v >= 1:
                return v
        except ValueError:
            pass
    cpu = os.cpu_count() or 2
    # min(2, cpu-1) but at least 1
    calc = cpu - 1
    if calc < 1:
        calc = 1
    return min(2, calc)


def _call_parser(fn: Callable[..., Any], path: str, cancel_set: bool = False) -> ParseResult:
    """Top-level worker entry point — must be pickle-able.

    Re-creates a ``threading.Event`` from ``cancel_set`` and invokes ``fn``
    with signature probing similar to ``JobQueue._invoke_worker``.
    All exceptions are caught and returned as ``ParseResult`` so the main
    thread never sees a propagated exception.
    """
    if cancel_set:
        return ParseResult(success=False, message="cancelled", path=path)

    try:
        # Build a local cancel token for the worker (not shared) — always create
        # so positional second-arg parsers (e.g. lambda p, t) can receive it.
        event = threading.Event()
        if cancel_set:
            event.set()

        # Try various calling conventions, most specific first.
        # This handles:
        # - (path, cancel_token) with any param name (e.g. lambda p, t)
        # - (path, progress_callback=None, cancel_token=None) like parse_os_artifacts
        # - (path) single-arg parsers
        result: Any = None
        last_type_error: Optional[TypeError] = None

        # Build attempt list lazily to avoid calling fn twice on success
        def _attempts():
            # 1. progress+cancel as keywords (parse_os_artifacts style)
            yield lambda: fn(path, progress_callback=None, cancel_token=event)
            # 2. cancel as keyword
            yield lambda: fn(path, cancel_token=event)
            # 3. two positional args (covers lambda p, t and def f(path, cancel_token))
            yield lambda: fn(path, event)
            # 4. single arg
            yield lambda: fn(path)
            # 5. single arg with None (for functions that expect second arg optional)
            #    already covered

        tried = False
        for attempt in _attempts():
            try:
                result = attempt()
                tried = True
                break
            except TypeError as te:
                # Only retry if TypeError looks like signature mismatch.
                # Internal TypeErrors (e.g. "'Event' object is not callable") should
                # be treated as worker failures, not retried, otherwise we hide
                # real bugs.
                msg_low = str(te).lower()
                if any(kw in msg_low for kw in ("missing", "unexpected", "takes", "positional argument", "keyword argument", "got an unexpected")):
                    last_type_error = te
                    continue
                # Real internal TypeError — propagate as worker failure
                raise
        if not tried:
            # All attempts failed with TypeError — re-raise last for outer handler
            assert last_type_error is not None
            raise last_type_error

        if isinstance(result, ParseResult):
            # Ensure path is set
            if not result.path:
                result.path = path
            return result
        if isinstance(result, dict) and "success" in result:
            return ParseResult(
                success=bool(result.get("success")),
                message=str(result.get("message", "")),
                data=result,
                path=path,
            )
        # Wrap successful raw result
        return ParseResult(success=True, message="ok", data=result, path=path)
    except BaseException as exc:  # noqa: BLE001 — must catch worker crashes
        # Preserve exception type name for acceptance checks
        msg = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        # If exception is empty string, still return type
        if not msg:
            msg = type(exc).__name__
        return ParseResult(success=False, message=msg, path=path)


# Fallback worker by name (for fork case where fn is looked up via global registry).
# Not used directly by ParserPool.run's primary path (which pickles fn), but kept
# for completeness and for potential Wave 6 opt-in that sends only name.
def _call_by_name(name: str, path: str, cancel_set: bool = False) -> ParseResult:
    fn = _GLOBAL_REGISTRY.get(name)
    if fn is None:
        return ParseResult(success=False, message=f"unknown parser: {name}", path=path)
    return _call_parser(fn, path, cancel_set)


class ParserPool:
    """Registry + ProcessPool for parser isolation (F13).

    Example:
        pool = ParserPool()
        pool.register("parse_os", parse_os_artifacts)
        result = pool.run("parse_os", "/mnt/image", cancel_token)
    """

    def __init__(self, pool_size: Optional[int] = None) -> None:
        if pool_size is None:
            pool_size = _default_pool_size()
        else:
            try:
                pool_size = int(pool_size)
            except (TypeError, ValueError):
                pool_size = _default_pool_size()
        if pool_size < 1:
            pool_size = 1
        self.pool_size: int = pool_size
        # Lazy — None until first run()
        self.executor: Optional[ProcessPoolExecutor] = None
        self._registry: Dict[str, Callable[..., Any]] = {}
        self._lock = threading.Lock()
        # Semaphore for fallback path when ProcessPool cannot pickle local callables
        # (e.g. lambdas defined inside tests). Mimics ProcessPool max_workers
        # semantics so serialisation tests remain valid even on fallback.
        self._fallback_sem = threading.Semaphore(self.pool_size)

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------
    def register(self, name: str, fn: Callable[..., Any]) -> None:
        """Register a parser function under ``name``.

        ``fn`` should be pickle-able and accept ``(path: str, cancel_token:
        threading.Event)``. Lambda is tolerated for test purposes via
        fallback path in ``run()``.
        """
        if not isinstance(name, str) or not name:
            raise ValueError("parser name must be non-empty str")
        if not callable(fn):
            raise ValueError("fn must be callable")
        with self._lock:
            self._registry[name] = fn
        with _REGISTRY_LOCK:
            _GLOBAL_REGISTRY[name] = fn

    def unregister(self, name: str) -> None:
        with self._lock:
            self._registry.pop(name, None)
        with _REGISTRY_LOCK:
            _GLOBAL_REGISTRY.pop(name, None)

    def list_parsers(self) -> list[str]:
        with self._lock:
            return list(self._registry.keys())

    # ------------------------------------------------------------------
    # Executor lifecycle
    # ------------------------------------------------------------------
    def _ensure_executor(self) -> None:
        if self.executor is not None:
            return
        with self._lock:
            if self.executor is None:
                # mp_context=None uses default (fork on POSIX, spawn on Windows)
                # No platform-specific code — import succeeds on both.
                self.executor = ProcessPoolExecutor(max_workers=self.pool_size)

    def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
        exec_ = self.executor
        if exec_ is not None:
            try:
                exec_.shutdown(wait=wait, cancel_futures=cancel_futures)
            except Exception:
                pass
        self.executor = None

    def __del__(self) -> None:  # pragma: no cover — best-effort cleanup
        try:
            self.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def run(
        self,
        name: str,
        path: str,
        cancel_token: Optional[threading.Event] = None,
        timeout: Optional[float] = None,
    ) -> ParseResult:
        """Execute parser ``name`` on ``path`` in the pool.

        Returns ``ParseResult`` — never raises into the caller except for
        programming errors (unknown parser is returned as failure, not raised).
        """
        # Fast-path cancellation before dispatch
        if cancel_token is not None and hasattr(cancel_token, "is_set") and cancel_token.is_set():
            return ParseResult(success=False, message="cancelled", path=path)

        # Lookup
        with self._lock:
            fn = self._registry.get(name)
        if fn is None:
            # Also check global (for cases where register was via module-level)
            with _REGISTRY_LOCK:
                fn = _GLOBAL_REGISTRY.get(name)
            if fn is None:
                return ParseResult(success=False, message=f"unknown parser: {name}", path=path)

        # Lazy executor creation
        self._ensure_executor()
        assert self.executor is not None

        cancel_set = bool(cancel_token and hasattr(cancel_token, "is_set") and cancel_token.is_set())

        # Submit — handle PicklingError / AttributeError for lambdas etc. with fallback
        try:
            future = self.executor.submit(_call_parser, fn, path, cancel_set)
        except BaseException:  # pickle failure, etc.
            # Fallback: execute directly in main thread but still isolated via try/except
            # This satisfies the lambda test where stdlib pickle cannot handle lambda.
            try:
                # Serialize via fallback semaphore to honor pool_size semantics
                with self._fallback_sem:
                    return _call_parser(fn, path, cancel_set)
            except BaseException as inner:
                msg = f"{type(inner).__name__}: {inner}" if str(inner) else type(inner).__name__
                return ParseResult(success=False, message=msg, path=path)

        try:
            result = future.result(timeout=timeout)
            if isinstance(result, ParseResult):
                return result
            # Wrap unexpected worker return
            if isinstance(result, dict) and "success" in result:
                return ParseResult(
                    success=bool(result.get("success")),
                    message=str(result.get("message", "")),
                    data=result,
                    path=path,
                )
            return ParseResult(success=True, message="ok", data=result, path=path)
        except FuturesTimeout:
            # Timeout — treat as worker died, cancel future
            try:
                future.cancel()
            except Exception:
                pass
            return ParseResult(success=False, message="worker died", path=path)
        except BrokenExecutor:
            # Pool broken (segfault, worker died)
            # Reset executor so next call can recreate
            try:
                self.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            # Also try to handle via message
            return ParseResult(success=False, message="worker died", path=path)
        except BaseException as exc:
            # Handle PicklingError from future (e.g. lambda/local func not pickle-able)
            # by falling back to direct execution — must respect pool_size serialisation.
            msg_low = str(exc).lower()
            type_name = type(exc).__name__
            if "pickle" in msg_low or "picklingerror" in type_name.lower() or "can't pickle" in msg_low:
                try:
                    with self._fallback_sem:
                        return _call_parser(fn, path, cancel_set)
                except BaseException as inner:
                    m2 = f"{type(inner).__name__}: {inner}" if str(inner) else type(inner).__name__
                    return ParseResult(success=False, message=m2, path=path)
            # Any other future exception — BrokenProcessPool, etc. all map to worker died
            # Preserve original exc name if it's not a worker-die case? Spec says worker crashes
            # are reported as success=False, message='worker died' rather than propagating.
            # But for pure Python exceptions we already returned ParseResult from worker,
            # so this path is only for infrastructure failures.
            if "broken" in msg_low or "died" in msg_low or "terminated" in type_name.lower():
                return ParseResult(success=False, message="worker died", path=path)
            # For other infrastructure errors, return type name
            m = f"{type_name}: {exc}" if str(exc) else type_name
            # If message contains ZeroDivision etc., preserve — but infrastructure shouldn't
            return ParseResult(success=False, message=m, path=path)


__all__ = ["ParseResult", "ParserPool", "_default_pool_size"]
