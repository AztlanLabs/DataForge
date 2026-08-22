from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait
from dataclasses import dataclass
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

    @classmethod
    def transfer_items(
        cls,
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
        # F3/U2: Evidence Mode gate
        if is_evidence_mode() and not dry_run:
            items_list = list(items)
            records = [
                BatchActionRecord(
                    item=item,
                    source_path=_normalize_path_value(path_getter(item)),
                    message="Evidence Mode is active — transfer blocked (ACPO §1)",
                    result=OperationResult(action, _normalize_path_value(path_getter(item)), None, False, "Evidence Mode active"),
                    success=False,
                )
                for item in items_list
            ]
            return BatchActionOutcome(action=action, records=records)

        reserved_paths = set()
        def _transfer_record(item: Any, source_path: str, _index: int) -> BatchActionRecord:
            target_dir = _normalize_path_value(destination_getter(item) or destination_dir)
            result = transfer_path(source_path, target_dir, action, dry_run=dry_run, reserved_paths=reserved_paths)
            return BatchActionRecord(item=item, source_path=source_path, message=result.message, result=result, success=result.success)

        items_list = list(items)
        if dry_run or len(items_list) <= 1:
            return cls._run_batch_operation(
                items_list,
                action=action,
                progress_message=f"{action.title()}...",
                operation=_transfer_record,
                cancel_token=cancel_token,
                progress_callback=progress_callback,
                path_getter=path_getter,
            )

        return cls._run_batch_parallel(
            items_list,
            action=action,
            progress_message=f"{action.title()}...",
            operation=_transfer_record,
            cancel_token=cancel_token,
            progress_callback=progress_callback,
            path_getter=path_getter,
        )

    @classmethod
    def delete_items(
        cls,
        items: Iterable[Any],
        *,
        dry_run: bool = True,
        safe_mode: Optional[bool] = None,
        progress_callback=None,
        cancel_token=None,
        path_getter: Callable[[Any], str] = _default_path_getter,
    ) -> BatchActionOutcome:
        # F3/U2: Evidence Mode gate
        if is_evidence_mode() and not dry_run:
            items_list = list(items)
            records = [
                BatchActionRecord(
                    item=item,
                    source_path=_normalize_path_value(path_getter(item)),
                    message="Evidence Mode is active — delete blocked (ACPO §1)",
                    result=OperationResult("delete", _normalize_path_value(path_getter(item)), None, False, "Evidence Mode active"),
                    success=False,
                )
                for item in items_list
            ]
            return BatchActionOutcome(action="delete", records=records)

        safe_mode = config.get("safe_mode", True) if safe_mode is None else safe_mode
        def _delete_record(item: Any, source_path: str, _index: int) -> BatchActionRecord:
            result = delete_path(source_path, dry_run=dry_run, safe_mode=safe_mode)
            return BatchActionRecord(item=item, source_path=source_path, message=result.message, result=result, success=result.success)

        items_list = list(items)
        if dry_run or len(items_list) <= 1:
            return cls._run_batch_operation(
                items_list,
                action="delete",
                progress_message="Deleting...",
                operation=_delete_record,
                cancel_token=cancel_token,
                progress_callback=progress_callback,
                path_getter=path_getter,
            )

        return cls._run_batch_parallel(
            items_list,
            action="delete",
            progress_message="Deleting...",
            operation=_delete_record,
            cancel_token=cancel_token,
            progress_callback=progress_callback,
            path_getter=path_getter,
        )

    @classmethod
    def rename_items(
        cls,
        items: Iterable[Any],
        name_getter: Callable[[Any, int], str],
        *,
        dry_run: bool = True,
        progress_callback=None,
        cancel_token=None,
        path_getter: Callable[[Any], str] = _default_path_getter,
    ) -> BatchActionOutcome:
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
        if dry_run or len(items_list) <= 1:
            return cls._run_batch_operation(
                items_list,
                action="rename",
                progress_message="Renaming...",
                operation=_rename_record,
                cancel_token=cancel_token,
                progress_callback=progress_callback,
                path_getter=path_getter,
            )

        return cls._run_batch_parallel(
            items_list,
            action="rename",
            progress_message="Renaming...",
            operation=_rename_record,
            cancel_token=cancel_token,
            progress_callback=progress_callback,
            path_getter=path_getter,
        )

    @classmethod
    def rename_items_with_regex(
        cls,
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

        return cls.rename_items(
            items,
            _name_getter,
            dry_run=dry_run,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=path_getter,
        )

    @classmethod
    def rename_items_with_template(
        cls,
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

        return cls.rename_items(
            items,
            _name_getter,
            dry_run=dry_run,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=path_getter,
        )

    @classmethod
    def rename_items_with_rules(
        cls,
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

        return cls.rename_items(
            items,
            _name_getter,
            dry_run=dry_run,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=path_getter,
        )

    @classmethod
    def archive_items(
        cls,
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
        items = list(items)
        records: list[BatchActionRecord] = []
        total = len(items)
        normalized_mode = mode.lower()

        if normalized_mode not in {"single", "individual"}:
            raise ValueError(f"Unsupported archive mode: {mode}")

        if normalized_mode == "single" and not destination:
            raise ValueError("destination is required for single archive mode")

        if normalized_mode == "single":
            if dry_run:
                for index, item in enumerate(items, start=1):
                    source_path = _normalize_path_value(path_getter(item))
                    message = f"Would archive: {source_path} -> {destination}"
                    record = BatchActionRecord(item=item, source_path=source_path, message=message, success=True)
                    cls._log_record(record)
                    records.append(record)
                    if progress_callback:
                        progress_callback(index, total, "Previewing Archive...")
                return BatchActionOutcome(action="archive", records=records)

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
                            return BatchActionOutcome(action="archive", records=records, cancelled=True)

                        source_path = _normalize_path_value(path_getter(item))
                        try:
                            archived_name = safe_zip_write(archive_handle, source_path, os.path.basename(source_path), existing_names)
                            result = OperationResult("archive", source_path, destination, True, f"Archived: {source_path} -> {destination} ({archived_name})")
                            record = BatchActionRecord(item=item, source_path=source_path, message=result.message, result=result, success=True)
                        except Exception as exc:
                            any_failed = True
                            result = OperationResult("archive", source_path, destination, False, f"ERROR: Could not archive {source_path}: {exc}")
                            record = BatchActionRecord(item=item, source_path=source_path, message=result.message, result=result, success=False)
                        cls._log_record(record)
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
                cls._log_record(record)
                records.append(record)
            return BatchActionOutcome(action="archive", records=records)

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
                cls._log_record(record)
                records.append(record)
                if progress_callback:
                    progress_callback(index, total, "Previewing Archive...")
            return BatchActionOutcome(action="archive", records=records)

        return cls._run_batch_parallel(
            items,
            action="archive",
            progress_message="Archiving...",
            operation=_individual_record,
            cancel_token=cancel_token,
            progress_callback=progress_callback,
            path_getter=path_getter,
        )

    @staticmethod
    def apply_successes_to_entries(outcome: BatchActionOutcome):
        for record in outcome.successes:
            item = record.item
            if hasattr(item, "path"):
                apply_result_to_entry(item, record.result)