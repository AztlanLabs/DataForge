import csv
import json
import re
import os
from typing import List
from datetime import datetime, timedelta
from ..core.common import FileEntry
from ..core.scanner import build_file_entry, scan_directory

from ..core.utils import parse_extensions


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
        query.set_content(content_text, is_regex=content_is_regex, case_sensitive=case_sensitive)

    query.set_size_range(min_size_bytes, max_size_bytes)

    now = datetime.now()
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
            'ext': lambda entry: (entry.extension.lower(), entry.filename.lower(), entry.path.lower()),
            'path': lambda entry: entry.path.lower(),
            'name': lambda entry: entry.filename.lower(),
            'size': lambda entry: (entry.size, entry.path.lower()),
            'created': lambda entry: (entry.created_at, entry.path.lower()),
            'modified': lambda entry: (entry.modified_at, entry.path.lower()),
        }
        ordered = sorted(ordered, key=key_funcs[sort_key], reverse=reverse)
    elif reverse:
        ordered.reverse()

    if limit is not None:
        ordered = ordered[:limit]

    return ordered


class SearchQuery:
    def __init__(self):
        self.name_pattern = None # Regex object
        self.extensions = [] # List of lower case extensions WITH dot
        self.min_size = None
        self.max_size = None
        self.modified_after = None
        self.modified_before = None
        
        # content search
        self.content_pattern = None # Compiled Regex or string
        self.content_is_regex = False
    
    def set_name_pattern(self, pattern_obj):
        self.name_pattern = re.compile(pattern_obj) if isinstance(pattern_obj, str) else pattern_obj
        return self
        
    def set_extensions(self, exts):
        self.extensions = parse_extensions(",".join(exts) if isinstance(exts, list) else exts)
        return self

    def set_content(self, text, is_regex=False, case_sensitive=False):
        flags = 0 if case_sensitive else re.IGNORECASE
        if is_regex:
            self.content_pattern = re.compile(text, flags)
        else:
            # Escape if literal
            self.content_pattern = re.compile(re.escape(text), flags)
        self.content_is_regex = is_regex
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

    def matches(self, entry):
        # 1. Name
        if self.name_pattern:
            if not self.name_pattern.match(entry.filename):
                return False
                
        # 2. Extension
        if self.extensions:
            # os.path.splitext can be slow, maybe check endswith?
            # entry.filename is available
            found = False
            name_lower = entry.filename.lower()
            for ext in self.extensions:
                if name_lower.endswith(ext.lower()):
                    found = True
                    break
            if not found:
                return False
                
        # 3. Size / Date (use FileEntry fields directly)
        if self.min_size is not None or self.max_size is not None or \
           self.modified_after is not None or self.modified_before is not None:
             if self.min_size is not None and entry.size < self.min_size: return False
             if self.max_size is not None and entry.size > self.max_size: return False
             if self.modified_after is not None and entry.modified_at < self.modified_after: return False
             if self.modified_before is not None and entry.modified_at > self.modified_before: return False

        # 4. Content (Expensive - Do last)
        if self.content_pattern:
            if not self._check_content(entry.path):
                return False
                
        return True

    def _check_content(self, path):
        # Skip binary / large files?
        # Simple heuristic: read first 1MB? Or line by line
        try:
            # Check size first to avoid huge files? config?
            # limit to 10MB for now
            if os.path.getsize(path) > 10 * 1024 * 1024: 
                return False 
                
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if self.content_pattern.search(line):
                        return True
        except Exception:
            return False
        return False

def iter_search_files(root_path: str, query: SearchQuery, recursive: bool = True, max_depth: int = -1, progress_callback=None, cancel_token=None):
    count = 0

    try:
        if root_path and os.path.isfile(root_path):
            if cancel_token and cancel_token.is_set():
                return

            entry = build_file_entry(root_path)
            if entry is None:
                return

            count = 1
            if progress_callback:
                progress_callback(count, count, "Searching...")

            if query.matches(entry):
                yield entry
        else:
            for entry in scan_directory(root_path, recursive, max_depth=max_depth, cancel_token=cancel_token):
                if cancel_token and cancel_token.is_set():
                    raise InterruptedError("Search cancelled")

                count += 1
                if progress_callback and count % 50 == 0:
                    progress_callback(count, 0, "Searching...")

                if query.matches(entry):
                    yield entry
    except InterruptedError:
        # Re-raise to be caught by wrapper
        raise


def search_files(root_path: str, query: SearchQuery, recursive: bool = True, max_depth: int = -1, progress_callback=None, cancel_token=None) -> List[FileEntry]:
    return list(iter_search_files(
        root_path,
        query,
        recursive=recursive,
        max_depth=max_depth,
        progress_callback=progress_callback,
        cancel_token=cancel_token,
    ))
