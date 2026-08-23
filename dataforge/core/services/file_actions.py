from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait
from dataclasses import dataclass
from datetime import datetime, timezone
import functools
import os
import re
import threading
import zipfile
from typing import Any, Callable, Iterable, Optional

from ..config import config
from ..logger import logger
from ..operations import apply_result_to_entry, delete_path, rename_path, render_template_name, transfer_path
from ..operations.files import OperationResult, normalize_path
from ..utils import normalize_filename, safe_zip_write
from ..case import is_evidence_mode


def _get_batch_workers() -> int:
    try:
        return min(16, (os.cpu_count() or 4) * 2)
    except Exception:
        return 4


def _normalize_path_value(path: Any) -> str:
    if path is None:
        return ""
    return normalize_path(path)


def _default_path_getter(item: Any) -> str:
    if isinstance(item, str):
        return _normalize_path_value(item)
    if isinstance(item, dict):
        return _normalize_path_value(item.get("path") or item.get("source_path") or "")
    return _normalize_path_value(getattr(item, "path", ""))


def _default_destination_getter(_item: Any) -> Optional[str]:
    return None


class AuditIntegrityError(RuntimeError):
    """Raised when audit log hash chain is broken while in Evidence Mode."""

# Alias for test compatibility — tests may expect IntegrityError
IntegrityError = AuditIntegrityError


class _HybridMethod:
    """Descriptor that allows a method to be called both as instance and class method.

    - Via instance: svc.transfer_items(...) -> func(svc, ...)
    - Via class: FileActionService.transfer_items(...) -> func(default_instance, ...)
    """

    def __init__(self, func):
        self.func = func
        functools.update_wrapper(self, func)

    def __get__(self, instance, owner):
        if instance is None:
            @functools.wraps(self.func)
            def class_wrapper(*args, **kwargs):
                default = owner()
                return self.func(default, *args, **kwargs)

            return class_wrapper
        else:
            @functools.wraps(self.func)
            def instance_wrapper(*args, **kwargs):
                return self.func(instance, *args, **kwargs)

            return instance_wrapper


@dataclass
class BatchActionRecord:
    item: Any
    source_path: str
    message: str
    result: Optional[OperationResult] = None
    success: bool = False
    skipped: bool = False


@dataclass
class BatchActionOutcome:
    action: str
    records: list[BatchActionRecord]
    cancelled: bool = False

    @property
    def successes(self) -> list[BatchActionRecord]:
        return [record for record in self.records if record.success]

    @property
    def failures(self) -> list[BatchActionRecord]:
        return [record for record in self.records if not record.success and not record.skipped]

    @property
    def skipped_records(self) -> list[BatchActionRecord]:
        return [record for record in self.records if record.skipped]

    @property
    def requested(self) -> int:
        return len(self.records)


class FileActionService:
    """Central batch file-operations service with optional audit logging (TICK-503).

    All public batch methods can be called either as class methods (legacy,
    no audit) or as instance methods with an injected AuditLog/CaseContext.

    Example:
        log = AuditLog(db_path="/tmp/audit.db")
        ctx = CaseContext(case_id="CASE-001", operator="Alice", evidence_mode=False)
        svc = FileActionService(audit_log=log, case_context=ctx)
        svc.transfer_items(files, "/dest", "move", dry_run=False)
    """

    def __init__(
        self,
        provider=None,
        audit_log=None,
        case_context=None,
    ):
        # provider is optional; keep for TICK-503 contract but not yet wired into ops
        if provider is not None:
            self.provider = provider
        else:
            try:
                from ..provider import default_provider

                self.provider = default_provider()
            except Exception:
                self.provider = None
        self.audit_log = audit_log
        self.case_context = case_context

    # -- internal audit helpers ---------------------------------------------

    def _is_evidence_mode(self) -> bool:
        """True if instance case_context or global context is in evidence mode."""
        if self.case_context is not None and getattr(self.case_context, "evidence_mode", False):
            return True
        try:
            return bool(is_evidence_mode())
        except Exception:
            return False

    def _verify_audit(self) -> None:
        """Verify audit log chain; raises AuditIntegrityError if tampered.

        Only called in Evidence Mode when audit_log is present and dry_run is False.
        """
        if self.audit_log is None:
            return
        try:
            result = self.audit_log.verify()
        except AuditIntegrityError:
            raise
        except Exception as exc:
            raise AuditIntegrityError(f"Audit log verification failed: {exc}") from exc

        # verify() returns dict {"valid": bool, ...} in current implementation
        if isinstance(result, dict):
            valid = result.get("valid", False)
        else:
            valid = bool(result)
        if not valid:
            raise AuditIntegrityError(f"Audit log integrity check failed: {result}")

    def _record_audit(
        self,
        operation: str,
        sources: list[str],
        destinations: list[str],
        outcome: BatchActionOutcome,
        dry_run: bool = False,
        error: str | None = None,
    ) -> None:
        """Append a single audit entry for the batch operation if audit_log is set."""
        if self.audit_log is None:
            return
        try:
            # Build payload with required fields per TICK-503
            payload: dict[str, Any] = {
                "operation": operation,
                "sources": list(sources),
                "destinations": list(destinations),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "result": "success" if len(outcome.failures) == 0 and len(outcome.successes) > 0 else "failure" if outcome.failures else "blocked" if any("Evidence Mode" in r.message for r in outcome.records) or any("Audit log integrity" in r.message for r in outcome.records) else "skipped" if outcome.skipped_records else "success",
                "dry_run": dry_run,
                "requested": outcome.requested,
                "success_count": len(outcome.successes),
                "failure_count": len(outcome.failures),
                "cancelled": outcome.cancelled,
            }
            if error:
                payload["error"] = error
            # Include case metadata if available
            if self.case_context is not None:
                try:
                    payload["case_id"] = getattr(self.case_context, "case_id", "")
                    payload["operator"] = getattr(self.case_context, "operator", "")
                    payload["evidence_mode"] = getattr(self.case_context, "evidence_mode", False)
                    # host if available
                    if hasattr(self.case_context, "host"):
                        payload["host"] = self.case_context.host
                except Exception:
                    pass
            # Fallback to global context if instance has no case_id but global does
            if not payload.get("case_id"):
                try:
                    from ..case import get_context

                    gctx = get_context()
                    if gctx is not None:
                        if not payload.get("case_id") and getattr(gctx, "case_id", ""):
                            payload["case_id"] = gctx.case_id
                        if not payload.get("operator") and getattr(gctx, "operator", ""):
                            payload["operator"] = gctx.operator
                except Exception:
                    pass

            # AuditLog.append expects (action, payload) — action is operation
            self.audit_log.append(operation, payload)
        except AuditIntegrityError:
            raise
        except Exception:
            # Audit failures must not break file operations
            try:
                logger.debug("audit log append failed", exc_info=True)
            except Exception:
                pass

    @staticmethod
    def _log_record(record: BatchActionRecord):
        if record.skipped:
            logger.info(record.message)
            return
        if record.success:
            logger.info(record.message)
            return
        logger.error(record.message)

    @classmethod
    def _run_batch_operation(
        cls,
        items: Iterable[Any],
        *,
        action: str,
        progress_message: str,
        operation: Callable[[Any, str, int], BatchActionRecord],
        cancel_token=None,
        progress_callback=None,
        path_getter: Callable[[Any], str] = _default_path_getter,
    ) -> BatchActionOutcome:
        records: list[BatchActionRecord] = []
        items = list(items)
        total = len(items)

        for index, item in enumerate(items, start=1):
            if cancel_token and cancel_token.is_set():
                return BatchActionOutcome(action=action, records=records, cancelled=True)

            source_path = _normalize_path_value(path_getter(item))
            record = operation(item, source_path, index)
            cls._log_record(record)
            records.append(record)

            if progress_callback:
                progress_callback(index, total, progress_message)

        return BatchActionOutcome(action=action, records=records)

    @classmethod
    def _run_batch_parallel(
        cls,
        items: list[Any],
        *,
        action: str,
        progress_message: str,
        operation: Callable[[Any, str, int], BatchActionRecord],
        cancel_token=None,
        progress_callback=None,
        path_getter: Callable[[Any], str] = _default_path_getter,
    ) -> BatchActionOutcome:
        total = len(items)
        if total == 0:
            return BatchActionOutcome(action=action, records=[])

        workers = _get_batch_workers()
        records: list[BatchActionRecord] = [None] * total  # type: ignore[list-item]
        counter_lock = threading.Lock()
        completed_count = 0

        def _do_one(idx: int, item: Any) -> tuple[int, BatchActionRecord]:
            source_path = _normalize_path_value(path_getter(item))
            record = operation(item, source_path, idx + 1)
            return idx, record

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for idx, item in enumerate(items):
                if cancel_token and cancel_token.is_set():
                    break
                futures[pool.submit(_do_one, idx, item)] = idx

            while futures:
                if cancel_token and cancel_token.is_set():
                    for f in futures:
                        f.cancel()
                    break

                done, _ = wait(futures, timeout=0.1, return_when=FIRST_COMPLETED)
                for fut in done:
                    futures.pop(fut, None)
                    if fut.cancelled():
                        continue
                    exc = fut.exception()
                    if exc is not None:
                        idx = futures.get(fut, -1)
                        if idx < 0:
                            for k, v in list(futures.items()):
                                if k is fut:
                                    idx = v
                                    break
                        if idx >= 0:
                            item = items[idx]
                            sp = _normalize_path_value(path_getter(item))
                            msg = f"ERROR: {exc}"
                            result = OperationResult(action, sp, None, False, msg)
                            rec = BatchActionRecord(item=item, source_path=sp, message=msg, result=result, success=False)
                            records[idx] = rec
                            cls._log_record(rec)
                        continue

                    idx, record = fut.result()
                    records[idx] = record
                    cls._log_record(record)

                    with counter_lock:
                        completed_count += 1
                        if progress_callback:
                            progress_callback(completed_count, total, progress_message)

        records = [r for r in records if r is not None]
        cancelled = cancel_token is not None and cancel_token.is_set()
        return BatchActionOutcome(action=action, records=records, cancelled=cancelled)

    @staticmethod
    def records_for_output(outcome: BatchActionOutcome, *, include_skipped: bool = True) -> list[BatchActionRecord]:
        if include_skipped:
            return list(outcome.records)
        return [record for record in outcome.records if not record.skipped]

    @classmethod
    def messages(cls, outcome: BatchActionOutcome, *, include_skipped: bool = True) -> list[str]:
        return [record.message for record in cls.records_for_output(outcome, include_skipped=include_skipped)]

    @classmethod
    def log_outcome(
        cls,
        outcome: BatchActionOutcome,
        action_label: str,
        log_func: Callable[[str, str, str], None],
        *,
        include_skipped: bool = True,
    ):
        for record in cls.records_for_output(outcome, include_skipped=include_skipped):
            log_func(record.source_path, action_label, record.message)

    @_HybridMethod
    def transfer_items(
        self,
        items: Iterable[Any],
        destination_dir: Optional[str],
        action: str,
        *,
        dry_run: bool = True,
        progress_callback=None,
        cancel_token=None,
        path_getter: Callable[[Any], str] = _default_path_getter,
        destination_getter: Callable[[Any], Optional[str]] = _default_destination_getter,
    ) -> BatchActionOutcome:
        # F1/F3: Evidence Mode + audit integrity gate (TICK-503)
        if self._is_evidence_mode() and not dry_run:
            if self.audit_log is not None:
                self._verify_audit()
            items_list_ev = list(items)
            # Preserve original items for audit
            ev_sources = [_normalize_path_value(path_getter(it)) for it in items_list_ev]
            ev_dests = [_normalize_path_value(destination_getter(it) or destination_dir) for it in items_list_ev]
            records = [
                BatchActionRecord(
                    item=item,
                    source_path=_normalize_path_value(path_getter(item)),
                    message="Evidence Mode is active — transfer blocked (ACPO §1)",
                    result=OperationResult(action, _normalize_path_value(path_getter(item)), None, False, "Evidence Mode active"),
                    success=False,
                )
                for item in items_list_ev
            ]
            outcome = BatchActionOutcome(action=action, records=records)
            # Audit the blocked attempt
            self._record_audit("transfer", ev_sources, ev_dests, outcome, dry_run, error="Evidence Mode active")
            return outcome

        reserved_paths = set()

        def _transfer_record(item: Any, source_path: str, _index: int) -> BatchActionRecord:
            target_dir = _normalize_path_value(destination_getter(item) or destination_dir)
            result = transfer_path(source_path, target_dir, action, dry_run=dry_run, reserved_paths=reserved_paths)
            return BatchActionRecord(item=item, source_path=source_path, message=result.message, result=result, success=result.success)

        items_list = list(items)
        # Collect sources/destinations for audit (before operation, as intended destinations)
        audit_sources = [_normalize_path_value(path_getter(it)) for it in items_list]
        audit_dests = [_normalize_path_value(destination_getter(it) or destination_dir) for it in items_list]

        if dry_run or len(items_list) <= 1:
            outcome = self.__class__._run_batch_operation(
                items_list,
                action=action,
                progress_message=f"{action.title()}...",
                operation=_transfer_record,
                cancel_token=cancel_token,
                progress_callback=progress_callback,
                path_getter=path_getter,
            )
        else:
            outcome = self.__class__._run_batch_parallel(
                items_list,
                action=action,
                progress_message=f"{action.title()}...",
                operation=_transfer_record,
                cancel_token=cancel_token,
                progress_callback=progress_callback,
                path_getter=path_getter,
            )

        # TICK-503: record operation in audit log
        # Also handle post-operation audit verification failure recovery? No
        # For failures due to audit tamper, we already verified pre-op.

        # Build more accurate destinations from actual results if available
        result_dests: list[str] = []
        for rec in outcome.records:
            if rec.result and rec.result.destination_path:
                result_dests.append(_normalize_path_value(rec.result.destination_path))
            else:
                # fallback to intended dest
                result_dests.append(audit_dests[len(result_dests)] if len(result_dests) < len(audit_dests) else "")

        # Use result_dests if not empty else audit_dests
        final_dests = result_dests if result_dests else audit_dests
        self._record_audit("transfer", audit_sources, final_dests, outcome, dry_run)
        return outcome

    @_HybridMethod
    def delete_items(
        self,
        items: Iterable[Any],
        *,
        dry_run: bool = True,
        safe_mode: Optional[bool] = None,
        progress_callback=None,
        cancel_token=None,
        path_getter: Callable[[Any], str] = _default_path_getter,
    ) -> BatchActionOutcome:
        if self._is_evidence_mode() and not dry_run:
            if self.audit_log is not None:
                self._verify_audit()
            items_list_ev = list(items)
            ev_sources = [_normalize_path_value(path_getter(it)) for it in items_list_ev]
            records = [
                BatchActionRecord(
                    item=item,
                    source_path=_normalize_path_value(path_getter(item)),
                    message="Evidence Mode is active — delete blocked (ACPO §1)",
                    result=OperationResult("delete", _normalize_path_value(path_getter(item)), None, False, "Evidence Mode active"),
                    success=False,
                )
                for item in items_list_ev
            ]
            outcome = BatchActionOutcome(action="delete", records=records)
            self._record_audit("delete", ev_sources, [], outcome, dry_run, error="Evidence Mode active")
            return outcome

        safe_mode = config.get("safe_mode", True) if safe_mode is None else safe_mode

        def _delete_record(item: Any, source_path: str, _index: int) -> BatchActionRecord:
            result = delete_path(source_path, dry_run=dry_run, safe_mode=safe_mode)
            return BatchActionRecord(item=item, source_path=source_path, message=result.message, result=result, success=result.success)

        items_list = list(items)
        audit_sources = [_normalize_path_value(path_getter(it)) for it in items_list]

        if dry_run or len(items_list) <= 1:
            outcome = self.__class__._run_batch_operation(
                items_list,
                action="delete",
                progress_message="Deleting...",
                operation=_delete_record,
                cancel_token=cancel_token,
                progress_callback=progress_callback,
                path_getter=path_getter,
            )
        else:
            outcome = self.__class__._run_batch_parallel(
                items_list,
                action="delete",
                progress_message="Deleting...",
                operation=_delete_record,
                cancel_token=cancel_token,
                progress_callback=progress_callback,
                path_getter=path_getter,
            )

        self._record_audit("delete", audit_sources, [], outcome, dry_run)
        return outcome

    @_HybridMethod
    def rename_items(
        self,
        items: Iterable[Any],
        name_getter: Callable[[Any, int], str],
        *,
        dry_run: bool = True,
        progress_callback=None,
        cancel_token=None,
        path_getter: Callable[[Any], str] = _default_path_getter,
    ) -> BatchActionOutcome:
        # Evidence Mode gate for rename as well (TICK-503 extends F3 to all mutations)
        if self._is_evidence_mode() and not dry_run:
            if self.audit_log is not None:
                self._verify_audit()
            items_list_ev = list(items)
            ev_sources = [_normalize_path_value(path_getter(it)) for it in items_list_ev]
            # Try to compute intended destinations for audit
            ev_dests: list[str] = []
            for idx, it in enumerate(items_list_ev, start=1):
                try:
                    new_name = name_getter(it, idx)
                    src = ev_sources[idx - 1]
                    ev_dests.append(os.path.join(os.path.dirname(src), new_name) if src else new_name)
                except Exception:
                    ev_dests.append("")
            records = [
                BatchActionRecord(
                    item=item,
                    source_path=_normalize_path_value(path_getter(item)),
                    message="Evidence Mode is active — rename blocked (ACPO §1)",
                    result=OperationResult("rename", _normalize_path_value(path_getter(item)), None, False, "Evidence Mode active"),
                    success=False,
                )
                for item in items_list_ev
            ]
            outcome = BatchActionOutcome(action="rename", records=records)
            self._record_audit("rename", ev_sources, ev_dests, outcome, dry_run, error="Evidence Mode active")
            return outcome

        reserved_paths = set()

        def _rename_record(item: Any, source_path: str, index: int) -> BatchActionRecord:
            try:
                new_name = name_getter(item, index)
                result = rename_path(source_path, new_name, dry_run=dry_run, reserved_paths=reserved_paths)
            except Exception as exc:
                message = f"ERROR: Could not prepare rename for {os.path.basename(source_path)}: {exc}"
                result = OperationResult("rename", source_path, None, False, message)
                return BatchActionRecord(item=item, source_path=source_path, message=message, result=result, success=False)
            if result is None:
                message = f"Skipped rename: {os.path.basename(source_path)} unchanged"
                return BatchActionRecord(item=item, source_path=source_path, message=message, skipped=True)
            return BatchActionRecord(item=item, source_path=source_path, message=result.message, result=result, success=result.success)

        items_list = list(items)
        audit_sources = [_normalize_path_value(path_getter(it)) for it in items_list]
        # Compute intended destinations for audit
        audit_dests: list[str] = []
        for idx, it in enumerate(items_list, start=1):
            try:
                new_name = name_getter(it, idx)
                src = audit_sources[idx - 1]
                audit_dests.append(os.path.join(os.path.dirname(src), new_name) if src else new_name)
            except Exception:
                audit_dests.append("")

        if dry_run or len(items_list) <= 1:
            outcome = self.__class__._run_batch_operation(
                items_list,
                action="rename",
                progress_message="Renaming...",
                operation=_rename_record,
                cancel_token=cancel_token,
                progress_callback=progress_callback,
                path_getter=path_getter,
            )
        else:
            outcome = self.__class__._run_batch_parallel(
                items_list,
                action="rename",
                progress_message="Renaming...",
                operation=_rename_record,
                cancel_token=cancel_token,
                progress_callback=progress_callback,
                path_getter=path_getter,
            )

        # Refine destinations from actual results where available
        result_dests: list[str] = []
        for rec in outcome.records:
            if rec.result and rec.result.destination_path:
                result_dests.append(_normalize_path_value(rec.result.destination_path))
            else:
                # fallback to intended
                idx = len(result_dests)
                result_dests.append(audit_dests[idx] if idx < len(audit_dests) else "")

        final_dests = result_dests if result_dests else audit_dests
        self._record_audit("rename", audit_sources, final_dests, outcome, dry_run)
        return outcome

    @_HybridMethod
    def rename_items_with_regex(
        self,
        items: Iterable[Any],
        pattern: str,
        replacement: str,
        *,
        dry_run: bool = True,
        progress_callback=None,
        cancel_token=None,
        path_getter: Callable[[Any], str] = _default_path_getter,
    ) -> BatchActionOutcome:
        regex = re.compile(pattern)

        def _name_getter(item: Any, _index: int) -> str:
            current_name = os.path.basename(path_getter(item))
            return regex.sub(replacement, current_name)

        return self.rename_items(
            items,
            _name_getter,
            dry_run=dry_run,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=path_getter,
        )

    @_HybridMethod
    def rename_items_with_template(
        self,
        items: Iterable[Any],
        template: str,
        *,
        counter_start: int = 1,
        dry_run: bool = True,
        progress_callback=None,
        cancel_token=None,
        path_getter: Callable[[Any], str] = _default_path_getter,
    ) -> BatchActionOutcome:
        def _name_getter(item: Any, index: int) -> str:
            counter = counter_start + index - 1
            return render_template_name(template, item, counter)

        return self.rename_items(
            items,
            _name_getter,
            dry_run=dry_run,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=path_getter,
        )

    @_HybridMethod
    def rename_items_with_rules(
        self,
        items: Iterable[Any],
        *,
        strip_leading_dot: bool = False,
        find_text: str = "",
        replace_text: str = "",
        use_regex: bool = False,
        numeric_pattern: str = "",
        numeric_replacement: str = "",
        numeric_pad: int = 0,
        case_mode: str = "none",
        collapse_separators: bool = False,
        prefix: str = "",
        suffix: str = "",
        index_start: int = 0,
        dry_run: bool = True,
        progress_callback=None,
        cancel_token=None,
        path_getter: Callable[[Any], str] = _default_path_getter,
    ) -> BatchActionOutcome:
        def _name_getter(item: Any, index: int) -> str:
            current_name = os.path.basename(path_getter(item))
            return normalize_filename(
                current_name,
                index=index_start + index - 1,
                strip_leading_dot=strip_leading_dot,
                find_text=find_text,
                replace_text=replace_text,
                use_regex=use_regex,
                numeric_pattern=numeric_pattern,
                numeric_replacement=numeric_replacement,
                numeric_pad=numeric_pad,
                case_mode=case_mode,
                collapse_separators=collapse_separators,
                prefix=prefix,
                suffix=suffix,
            )

        return self.rename_items(
            items,
            _name_getter,
            dry_run=dry_run,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=path_getter,
        )

    @_HybridMethod
    def archive_items(
        self,
        items: Iterable[Any],
        *,
        mode: str = "single",
        destination: Optional[str] = None,
        compression: int = zipfile.ZIP_DEFLATED,
        dry_run: bool = True,
        progress_callback=None,
        cancel_token=None,
        path_getter: Callable[[Any], str] = _default_path_getter,
    ) -> BatchActionOutcome:
        # Evidence Mode gate for archive
        if self._is_evidence_mode() and not dry_run:
            if self.audit_log is not None:
                self._verify_audit()
            items_list_ev = list(items)
            ev_sources = [_normalize_path_value(path_getter(it)) for it in items_list_ev]
            ev_dests = [_normalize_path_value(destination) if destination else f"{os.path.splitext(s)[0]}.zip" for s in ev_sources]
            records = [
                BatchActionRecord(
                    item=item,
                    source_path=_normalize_path_value(path_getter(item)),
                    message="Evidence Mode is active — archive blocked (ACPO §1)",
                    result=OperationResult("archive", _normalize_path_value(path_getter(item)), None, False, "Evidence Mode active"),
                    success=False,
                )
                for item in items_list_ev
            ]
            outcome = BatchActionOutcome(action="archive", records=records)
            self._record_audit("archive", ev_sources, ev_dests, outcome, dry_run, error="Evidence Mode active")
            return outcome

        items = list(items)
        records: list[BatchActionRecord] = []
        total = len(items)
        normalized_mode = mode.lower()

        if normalized_mode not in {"single", "individual"}:
            raise ValueError(f"Unsupported archive mode: {mode}")

        if normalized_mode == "single" and not destination:
            raise ValueError("destination is required for single archive mode")

        audit_sources = [_normalize_path_value(path_getter(it)) for it in items]
        audit_dests_single = [_normalize_path_value(destination) if destination else ""]

        if normalized_mode == "single":
            if dry_run:
                for index, item in enumerate(items, start=1):
                    source_path = _normalize_path_value(path_getter(item))
                    message = f"Would archive: {source_path} -> {destination}"
                    record = BatchActionRecord(item=item, source_path=source_path, message=message, success=True)
                    self.__class__._log_record(record)
                    records.append(record)
                    if progress_callback:
                        progress_callback(index, total, "Previewing Archive...")
                outcome = BatchActionOutcome(action="archive", records=records)
                self._record_audit("archive", audit_sources, audit_dests_single, outcome, dry_run)
                return outcome

            destination = _normalize_path_value(destination)
            tmp_path = destination + ".tmp"
            output_dir = os.path.dirname(destination)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            existing_names: set[str] = set()
            any_failed = False
            try:
                with zipfile.ZipFile(tmp_path, "w", compression) as archive_handle:
                    for index, item in enumerate(items, start=1):
                        if cancel_token and cancel_token.is_set():
                            try:
                                os.remove(tmp_path)
                            except OSError:
                                pass
                            outcome = BatchActionOutcome(action="archive", records=records, cancelled=True)
                            self._record_audit("archive", audit_sources, audit_dests_single, outcome, dry_run)
                            return outcome

                        source_path = _normalize_path_value(path_getter(item))
                        try:
                            archived_name = safe_zip_write(archive_handle, source_path, os.path.basename(source_path), existing_names)
                            result = OperationResult("archive", source_path, destination, True, f"Archived: {source_path} -> {destination} ({archived_name})")
                            record = BatchActionRecord(item=item, source_path=source_path, message=result.message, result=result, success=True)
                        except Exception as exc:
                            any_failed = True
                            result = OperationResult("archive", source_path, destination, False, f"ERROR: Could not archive {source_path}: {exc}")
                            record = BatchActionRecord(item=item, source_path=source_path, message=result.message, result=result, success=False)
                        self.__class__._log_record(record)
                        records.append(record)

                        if progress_callback:
                            progress_callback(index, total, "Archiving...")

                if any_failed:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                else:
                    os.replace(tmp_path, destination)
            except Exception as exc:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                failed_result = OperationResult("archive", destination, destination, False, f"ERROR: Could not archive to {destination}: {exc}")
                record = BatchActionRecord(item=destination, source_path=destination, message=failed_result.message, result=failed_result, success=False)
                self.__class__._log_record(record)
                records.append(record)
            outcome = BatchActionOutcome(action="archive", records=records)
            self._record_audit("archive", audit_sources, audit_dests_single, outcome, dry_run)
            return outcome

        def _individual_record(item: Any, source_path: str, _index: int) -> BatchActionRecord:
            archive_path = _normalize_path_value(destination) or f"{os.path.splitext(source_path)[0]}.zip"
            output_dir = os.path.dirname(archive_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            tmp_path = archive_path + ".tmp"
            try:
                with zipfile.ZipFile(tmp_path, "w", compression) as archive_handle:
                    safe_zip_write(archive_handle, source_path, os.path.basename(source_path), set())
                os.replace(tmp_path, archive_path)
                result = OperationResult("archive", source_path, archive_path, True, f"Archived: {source_path} -> {archive_path}")
                return BatchActionRecord(item=item, source_path=source_path, message=result.message, result=result, success=True)
            except Exception as exc:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                result = OperationResult("archive", source_path, archive_path, False, f"ERROR: Could not archive {source_path}: {exc}")
                return BatchActionRecord(item=item, source_path=source_path, message=result.message, result=result, success=False)

        if dry_run:
            for index, item in enumerate(items, start=1):
                source_path = _normalize_path_value(path_getter(item))
                archive_path = _normalize_path_value(destination) or f"{os.path.splitext(source_path)[0]}.zip"
                message = f"Would archive: {source_path} -> {archive_path}"
                record = BatchActionRecord(item=item, source_path=source_path, message=message, success=True)
                self.__class__._log_record(record)
                records.append(record)
                if progress_callback:
                    progress_callback(index, total, "Previewing Archive...")
            outcome = BatchActionOutcome(action="archive", records=records)
            # destinations for dry_run individual: per-item zip paths
            audit_dests_indiv = [_normalize_path_value(destination) or f"{os.path.splitext(s)[0]}.zip" for s in audit_sources]
            self._record_audit("archive", audit_sources, audit_dests_indiv, outcome, dry_run)
            return outcome

        outcome = self.__class__._run_batch_parallel(
            items,
            action="archive",
            progress_message="Archiving...",
            operation=_individual_record,
            cancel_token=cancel_token,
            progress_callback=progress_callback,
            path_getter=path_getter,
        )
        audit_dests_indiv = [_normalize_path_value(destination) or f"{os.path.splitext(s)[0]}.zip" for s in audit_sources]
        # Prefer actual destinations from results
        result_dests = [r.result.destination_path if r.result and r.result.destination_path else audit_dests_indiv[i] if i < len(audit_dests_indiv) else "" for i, r in enumerate(outcome.records)]
        self._record_audit("archive", audit_sources, result_dests, outcome, dry_run)
        return outcome

    @staticmethod
    def apply_successes_to_entries(outcome: BatchActionOutcome):
        for record in outcome.successes:
            item = record.item
            if hasattr(item, "path"):
                apply_result_to_entry(item, record.result)
