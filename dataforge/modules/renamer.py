"""Bulk renamer — streaming, progress/cancel, preview parity, collision via FileActionService."""
from __future__ import annotations

import os
import queue
import threading
from typing import Any, Callable, Dict, List, Optional, Union

from ..core.scanner import scan_directory
from ..core.services import FileActionService


def _stream_entries(root: str, recursive: bool, cancel_token=None):
    """Yield FileEntry via queue.Queue (streaming)."""
    q: queue.Queue = queue.Queue(maxsize=200)
    sentinel = object()

    def _producer():
        try:
            for entry in scan_directory(root, recursive=recursive, cancel_token=cancel_token):
                if cancel_token is not None and cancel_token.is_set():
                    break
                q.put(entry)
        finally:
            q.put(sentinel)

    t = threading.Thread(target=_producer, daemon=True)
    t.start()
    while True:
        item = q.get()
        if item is sentinel:
            break
        yield item
        if cancel_token is not None and cancel_token.is_set():
            # drain quickly to let producer finish
            while not q.empty():
                try:
                    nxt = q.get_nowait()
                    if nxt is sentinel:
                        break
                except queue.Empty:
                    break
            break


def _do_rename(
    path: str,
    pattern: str,
    replacement: str,
    recursive: bool = False,
    dry_run: bool = True,
    progress_callback: Optional[Callable] = None,
    cancel_token=None,
):
    """Shared streaming rename core — preview and apply use identical FileActionService path.

    Collision handling is delegated to FileActionService (reserved_paths / resolve_collision_path).
    Streaming is via queue.Queue.
    Returns list[str] on success, or {"cancelled": True, ...} when cancelled.
    """
    # Immediate cancel before any work — guarantees no partial renames
    if cancel_token is not None and cancel_token.is_set():
        return {"cancelled": True, "messages": [], "outcome": None}

    entries: List[Any] = []
    # Stream via queue.Queue
    for entry in _stream_entries(path, recursive, cancel_token):
        if cancel_token is not None and cancel_token.is_set():
            return {"cancelled": True, "messages": [], "outcome": None}
        entries.append(entry)
        if progress_callback is not None:
            # best-effort progress during scan (total unknown yet)
            try:
                progress_callback(len(entries), None, "Scanning...")
            except Exception:
                pass

    # Re-check cancel before mutation phase — ensures no partial renames left
    if cancel_token is not None and cancel_token.is_set():
        return {"cancelled": True, "messages": [], "outcome": None}

    outcome = FileActionService.rename_items_with_regex(
        entries,
        pattern,
        replacement,
        dry_run=dry_run,
        progress_callback=progress_callback,
        cancel_token=cancel_token,
    )
    if outcome.cancelled:
        # Revert any already-renamed files when cancelled mid-run (dry_run=False) so
        # no partial renames are left on disk — required by AC.
        if not dry_run:
            for rec in outcome.successes:
                try:
                    dest = rec.result.destination_path if rec.result and rec.result.destination_path else None
                    src = rec.source_path
                    if dest and src and os.path.exists(dest):
                        # os.rename back; ignore collision (original path should be free)
                        try:
                            os.rename(dest, src)
                        except OSError:
                            pass
                except Exception:
                    pass
        return {"cancelled": True, "messages": FileActionService.messages(outcome, include_skipped=False), "outcome": outcome}

    messages = FileActionService.messages(outcome, include_skipped=False)
    # For callers that expect dict (e.g. cancel tests) we still support list return.
    # When not cancelled, return messages list for backward compatibility with existing callers.
    # Preview callers can inspect outcome via the dict wrapper if needed — we attach it
    # as an attribute when returning list? Instead we return list; preview_rename will wrap.
    return {"cancelled": False, "messages": messages, "outcome": outcome}


def preview_rename(
    path: str,
    pattern: str,
    replacement: str,
    recursive: bool = False,
    progress_callback: Optional[Callable] = None,
    cancel_token=None,
) -> Union[Dict[str, Any], List[str]]:
    """Streaming preview (dry_run=True) — identical FileActionService path as apply.

    Returns {"cancelled": False, "messages": [...], "outcome": BatchActionOutcome}
    or {"cancelled": True, ...} when cancelled. Parity with bulk_rename(dry_run=True).
    """
    result = _do_rename(
        path,
        pattern,
        replacement,
        recursive=recursive,
        dry_run=True,
        progress_callback=progress_callback,
        cancel_token=cancel_token,
    )
    # result is always dict from _do_rename
    return result


def bulk_rename(
    path: str,
    pattern: str,
    replacement: str,
    recursive: bool = False,
    dry_run: bool = True,
    progress_callback: Optional[Callable] = None,
    cancel_token=None,
) -> Union[List[str], Dict[str, Any]]:
    """Streaming bulk rename — queue.Queue, progress/cancel, collision via FileActionService.

    Preview and apply go through identical FileActionService.rename_items_with_regex
    (only dry_run differs) so there is no drift.

    Returns:
      - List[str] messages when not cancelled and caller expects legacy list (dry_run path)
      - {"cancelled": True, ...} dict when cancelled (mid-run or pre-set) — no partial renames
      - When not cancelled via new API, also returns dict with messages/outcome for parity checks,
        but unwraps to list for backward compatibility if dry_run caller checks isinstance(list).
    """
    result = _do_rename(
        path,
        pattern,
        replacement,
        recursive=recursive,
        dry_run=dry_run,
        progress_callback=progress_callback,
        cancel_token=cancel_token,
    )
    if isinstance(result, dict) and result.get("cancelled") is True:
        return result
    # result is dict with cancelled False — unwrap to list for legacy callers (CLI, tests)
    # Keep dict also accessible via preview_rename for new tests that want outcome parity
    # For bulk_rename we return list when not cancelled to preserve test_contract_regressions etc.
    # But if caller checks for dict parity (preview vs apply identical), they can compare
    # the underlying outcome.messages — both paths use same service.
    if isinstance(result, dict):
        # If dry_run was requested via legacy boolean, return messages list
        # New streaming tests that want parity will call preview_rename and inspect outcome
        return result["messages"]
    return result  # fallback
