import concurrent.futures
import csv
import json
import mmap
import os
import re
from datetime import datetime, timedelta, timezone
from typing import List

from ..core.common import FileEntry
from ..core.scanner import build_file_entry, scan_directory
from ..core.utils import parse_extensions

try:
    import magic as _magic  # type: ignore

    _HAS_MAGIC = True
except ImportError:  # pragma: no cover - optional dep
    _magic = None  # type: ignore
    _HAS_MAGIC = False

# Engine-shared constants: mmap + bytes regex, 1 MiB window, 10 MB cap
_MAX_CONTENT_BYTES = 10 * 1024 * 1024
_WINDOW_SIZE = 1 << 20
_OVERLAP_SIZE = 8192


def _get_search_workers() -> int:
    try:
        from ..core.config import config as _cfg

        v = _cfg.get("search_thread_workers", None)
        if isinstance(v, int) and 1 <= v <= 256:
            return min(32, v)
    except Exception:
        pass
    try:
        c = os.cpu_count()
        return min(32, (c or 4) * 2)
    except Exception:
        return 8


def _is_text_file(path: str) -> bool:
    if _HAS_MAGIC:
        try:
            mime = _magic.from_file(path, mime=True)  # type: ignore
            if mime:
                if mime == "inode/x-empty":
                    return True
                if mime.startswith("text/"):
                    return True
                text_mimes = {
                    "application/json",
                    "application/xml",
                    "application/javascript",
                    "application/x-sh",
                    "application/x-httpd-php",
                    "application/x-python",
                    "application/x-perl",
                    "application/x-ruby",
                    "application/yaml",
                    "application/csv",
                    "application/x-empty",
                }
                if mime in text_mimes:
                    return True
                return False
        except Exception:
            pass
    try:
        with open(path, "rb") as fh:
            sample = fh.read(8192)
            if not sample:
                return True
            if b"\x00" in sample:
                return False
            return True
    except OSError:
        return False


def _search_bytes_with_mmap(
    path: str,
    pattern_bytes: re.Pattern,
    cap: int = _MAX_CONTENT_BYTES,
    window: int = _WINDOW_SIZE,
    overlap: int = _OVERLAP_SIZE,
    cancel_token=None,
) -> bool:
    try:
        st_size = os.path.getsize(path)
    except OSError:
        return False
    if st_size == 0:
        return False
    effective = st_size if st_size < cap else cap
    if effective == 0:
        return False
    if cancel_token is not None and cancel_token.is_set():
        return False
    try:
        with open(path, "rb") as f:
            if cancel_token is not None and cancel_token.is_set():
                return False
            try:
                with mmap.mmap(f.fileno(), length=effective, access=mmap.ACCESS_READ) as mm:
                    if effective <= window:
                        if cancel_token is not None and cancel_token.is_set():
                            return False
                        return pattern_bytes.search(mm) is not None
                    step = window - overlap if window > overlap else window
                    for offset in range(0, effective, step):
                        if cancel_token is not None and cancel_token.is_set():
                            return False
                        end = offset + window
                        if end < effective:
                            # include overlap to catch patterns spanning boundary
                            end = min(end + overlap, effective)
                        else:
                            end = effective
                        chunk = mm[offset:end]
                        if pattern_bytes.search(chunk):
                            return True
                        if end >= effective:
                            break
                    return False
            except (OSError, ValueError, OverflowError):
                pass
            # Fallback chunked read without mmap (still windowed, no line iteration)
            f.seek(0)
            remaining = effective
            tail = b""
            while remaining > 0:
                if cancel_token is not None and cancel_token.is_set():
                    return False
                read_size = window if remaining > window else remaining
                data = f.read(read_size)
                if not data:
                    break
                chunk = tail + data if tail else data
                if pattern_bytes.search(chunk):
                    return True
                if len(chunk) > overlap:
                    tail = chunk[-overlap:]
                else:
                    tail = chunk
                remaining -= read_size
            return False
    except OSError:
        return False
    except Exception:
        return False


def build_search_query(
    *,
    name_pattern: str = None,
    use_regex: bool = False,
    extensions: str | list[str] = None,
    content_text: str = None,
    content_is_regex: bool = False,
    case_sensitive: bool = False,
    min_size_bytes: int = None,
    max_size_bytes: int = None,
    newer_than_days: float = None,
    older_than_days: float = None,
    force_binary: bool = False,
) -> "SearchQuery":
    query = SearchQuery()

    if name_pattern:
        pattern = name_pattern if use_regex else _glob_to_regex(name_pattern)
        query.set_name_pattern(pattern)

    if extensions:
        if isinstance(extensions, str):
            query.set_extensions(parse_extensions(extensions))
        else:
            query.set_extensions(extensions)

    if content_text:
        query.set_content(
            content_text,
            is_regex=content_is_regex,
            case_sensitive=case_sensitive,
            force_binary=force_binary,
        )

    query.set_size_range(min_size_bytes, max_size_bytes)

    now = datetime.now(timezone.utc)
    after = now - timedelta(days=float(newer_than_days)) if newer_than_days is not None else None
    before = now - timedelta(days=float(older_than_days)) if older_than_days is not None else None
    query.set_modified_date(after=after, before=before)
    return query


def _glob_to_regex(pattern: str) -> str:
    import fnmatch

    return fnmatch.translate(pattern)


def serialize_file_entry(entry: FileEntry, **extra_fields) -> dict:
    row = {
        "path": entry.path,
        "filename": entry.filename,
        "extension": entry.extension,
        "size": entry.size,
        "created_at": entry.created_at,
        "modified_at": entry.modified_at,
        "is_dir": entry.is_dir,
    }
    row.update(extra_fields)
    return row


def export_result_rows(rows, destination_path: str, format: str = "csv") -> str:
    serialized_rows = list(rows)
    if not serialized_rows:
        raise ValueError("No results available to export.")

    normalized_format = (format or "csv").lower()
    if normalized_format == "json":
        with open(destination_path, "w", encoding="utf-8") as handle:
            json.dump(serialized_rows, handle, indent=2)
        return destination_path

    if normalized_format != "csv":
        raise ValueError(f"Unsupported export format: {format}")

    fieldnames = []
    for row in serialized_rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    with open(destination_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(serialized_rows)
    return destination_path


def export_search_results(results, destination_path: str, format: str = "csv") -> str:
    return export_result_rows((serialize_file_entry(entry) for entry in results), destination_path, format=format)


def order_search_results(results, sort_key: str = None, reverse: bool = False, limit: int = None) -> list[FileEntry]:
    ordered = list(results)

    if sort_key:
        key_funcs = {
            "ext": lambda entry: (entry.extension.lower(), entry.filename.lower(), entry.path.lower()),
            "path": lambda entry: entry.path.lower(),
            "name": lambda entry: entry.filename.lower(),
            "size": lambda entry: (entry.size, entry.path.lower()),
            "created": lambda entry: (entry.created_at, entry.path.lower()),
            "modified": lambda entry: (entry.modified_at, entry.path.lower()),
        }
        ordered = sorted(ordered, key=key_funcs[sort_key], reverse=reverse)
    elif reverse:
        ordered.reverse()

    if limit is not None:
        ordered = ordered[:limit]

    return ordered


class SearchQuery:
    def __init__(self):
        self.name_pattern = None  # Regex object
        self.extensions = []  # List of lower case extensions WITH dot
        self.min_size = None
        self.max_size = None
        self.modified_after = None
        self.modified_before = None

        # content search
        self.content_pattern = None  # Compiled Regex for str path (backward compat)
        self.content_pattern_bytes: re.Pattern | None = None  # compiled bytes pattern for mmap
        self.content_is_regex = False
        self.force_binary = False
        self._content_text: str | None = None
        self._content_flags: int = 0

    def set_name_pattern(self, pattern_obj):
        self.name_pattern = re.compile(pattern_obj) if isinstance(pattern_obj, str) else pattern_obj
        return self

    def set_extensions(self, exts):
        self.extensions = parse_extensions(",".join(exts) if isinstance(exts, list) else exts)
        return self

    def set_content(self, text, is_regex=False, case_sensitive=False, force_binary=False):
        flags = 0 if case_sensitive else re.IGNORECASE
        self.content_is_regex = is_regex
        self.force_binary = bool(force_binary)
        self._content_text = text
        self._content_flags = flags
        if is_regex:
            self.content_pattern = re.compile(text, flags)
            btext = text.encode("utf-8", "ignore")
            self.content_pattern_bytes = re.compile(btext, flags)
        else:
            esc = re.escape(text)
            self.content_pattern = re.compile(esc, flags)
            self.content_pattern_bytes = re.compile(esc.encode("utf-8"), flags)
        # Adjust overlap for literal patterns longer than default
        return self

    def set_size_range(self, min_bytes: int = None, max_bytes: int = None):
        self.min_size = min_bytes
        self.max_size = max_bytes
        return self

    def set_modified_date(self, after: datetime = None, before: datetime = None):
        if after:
            self.modified_after = after.timestamp()
        if before:
            self.modified_before = before.timestamp()
        return self

    def _matches_without_content(self, entry) -> bool:
        if self.name_pattern:
            if not self.name_pattern.match(entry.filename):
                return False
        if self.extensions:
            found = False
            name_lower = entry.filename.lower()
            for ext in self.extensions:
                if name_lower.endswith(ext.lower()):
                    found = True
                    break
            if not found:
                return False
        if self.min_size is not None or self.max_size is not None or self.modified_after is not None or self.modified_before is not None:
            if self.min_size is not None and entry.size < self.min_size:
                return False
            if self.max_size is not None and entry.size > self.max_size:
                return False
            if self.modified_after is not None and entry.modified_at < self.modified_after:
                return False
            if self.modified_before is not None and entry.modified_at > self.modified_before:
                return False
        return True

    def matches(self, entry):
        if not self._matches_without_content(entry):
            return False
        if self.content_pattern is not None:
            if not self._check_content(entry.path):
                return False
        return True

    def _check_content(self, path, cancel_token=None):
        if self.content_pattern_bytes is None:
            return False
        # binary-aware skip unless force_binary
        if not self.force_binary:
            if not _is_text_file(path):
                return False
        # Determine overlap for literal patterns (ensure spanning window is caught)
        overlap = _OVERLAP_SIZE
        if not self.content_is_regex and self._content_text is not None:
            try:
                tlen = len(self._content_text.encode("utf-8"))
                if tlen > overlap:
                    overlap = min(tlen + 1, _WINDOW_SIZE // 2)
            except Exception:
                pass
        return _search_bytes_with_mmap(path, self.content_pattern_bytes, overlap=overlap, cancel_token=cancel_token)


def iter_search_files(root_path: str, query: SearchQuery, recursive: bool = True, max_depth: int = -1, progress_callback=None, cancel_token=None):
    if cancel_token is not None and cancel_token.is_set():
        return
    has_content = query.content_pattern is not None and query.content_pattern_bytes is not None
    max_workers = _get_search_workers()

    try:
        if root_path and os.path.isfile(root_path):
            if cancel_token and cancel_token.is_set():
                return
            entry = build_file_entry(root_path)
            if entry is None:
                return
            if progress_callback:
                progress_callback(1, 1, "Searching...")
            if query.matches(entry):
                yield entry
            return

        if not has_content:
            count = 0
            for entry in scan_directory(root_path, recursive, max_depth=max_depth, cancel_token=cancel_token):
                if cancel_token and cancel_token.is_set():
                    return
                count += 1
                if progress_callback and count % 50 == 0:
                    progress_callback(count, 0, "Searching...")
                if query.matches(entry):
                    yield entry
            return

        # Content path: parallel ThreadPool with streaming and bounded pending
        count = 0
        pending: dict[concurrent.futures.Future, FileEntry] = {}
        # Keep memory bounded: batches of workers*4
        batch = max(4, max_workers * 4)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for entry in scan_directory(root_path, recursive, max_depth=max_depth, cancel_token=cancel_token):
                if cancel_token and cancel_token.is_set():
                    for f in list(pending.keys()):
                        f.cancel()
                    return
                count += 1
                if progress_callback and count % 50 == 0:
                    progress_callback(count, 0, "Searching...")
                # cheap filter before submitting
                if not query._matches_without_content(entry):
                    continue
                fut = executor.submit(query._check_content, entry.path, cancel_token)
                pending[fut] = entry
                if len(pending) >= batch:
                    done, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
                    for f in list(done):
                        e = pending.pop(f)
                        try:
                            matched = f.result()
                        except Exception:
                            matched = False
                        if matched:
                            yield e
                    # also drain any other already done to keep batch small
                    # peek for additional completeds without blocking
                    extra_done = [f for f in list(pending.keys()) if f.done()]
                    for f in extra_done:
                        e = pending.pop(f)
                        try:
                            matched = f.result()
                        except Exception:
                            matched = False
                        if matched:
                            yield e
            # drain remaining
            if pending:
                for fut in concurrent.futures.as_completed(pending):
                    if cancel_token and cancel_token.is_set():
                        break
                    e = pending[fut]
                    try:
                        matched = fut.result()
                    except Exception:
                        matched = False
                    if matched:
                        yield e
    except InterruptedError:
        return


def search_files(root_path: str, query: SearchQuery, recursive: bool = True, max_depth: int = -1, progress_callback=None, cancel_token=None) -> List[FileEntry]:
    return list(
        iter_search_files(
            root_path,
            query,
            recursive=recursive,
            max_depth=max_depth,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
        )
    )


# Shared engine helper for forensics.keyword_search reuse
def keyword_search_shared(
    paths: list[str],
    keywords: list[str],
    case_sensitive: bool = False,
    force_binary: bool = False,
    cancel_token=None,
) -> list[dict]:
    """Engine-shared content matcher used by forensics.keyword_search.

    Uses the same mmap + bytes regex + ThreadPool path as search_files.
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    patterns: list[tuple[str, re.Pattern]] = []
    for kw in keywords:
        esc = re.escape(kw)
        pat = re.compile(esc.encode("utf-8"), flags)
        patterns.append((kw, pat))

    def _check_path(p: str):
        if not force_binary and not _is_text_file(p):
            return None
        try:
            st = os.path.getsize(p)
            if st == 0 or st > _MAX_CONTENT_BYTES * 2:  # still cap search to _MAX_CONTENT_BYTES via helper
                # we still search up to cap; helper handles cap
                pass
        except OSError:
            return None
        matched_kw = []
        for kw, pat in patterns:
            if _search_bytes_with_mmap(p, pat, cancel_token=cancel_token):
                matched_kw.append(kw)
        if matched_kw:
            try:
                size = os.path.getsize(p)
            except OSError:
                size = 0
            return {"path": p, "filename": os.path.basename(p), "size": size, "matched_keywords": matched_kw, "match_count": len(matched_kw)}
        return None

    max_workers = _get_search_workers()
    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        fut_to_path = {executor.submit(_check_path, p): p for p in paths}
        for fut in concurrent.futures.as_completed(fut_to_path):
            if cancel_token and cancel_token.is_set():
                break
            try:
                res = fut.result()
            except Exception:
                res = None
            if res is not None:
                results.append(res)
    return results
