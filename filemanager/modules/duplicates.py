import filecmp
from collections import defaultdict
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from ..core.scanner import scan_directory
from ..core.hasher import get_file_hash
from ..core.common import FileEntry
from ..core.logger import logger
from ..core.cache import file_cache
from ..core.config import config
from .search import serialize_file_entry


KEEP_STRATEGIES = ("first path", "newest", "oldest", "largest", "smallest")


def build_duplicate_records(duplicates: Dict[str, List[FileEntry]]) -> list[dict]:
    records = []
    for hash_value, entries in duplicates.items():
        group_size = len(entries)
        for entry in entries:
            records.append({
                "hash": hash_value,
                "group_size": group_size,
                "entry": entry,
            })
    return records


def order_duplicate_records(records, sort_key: str = None, reverse: bool = False, limit: int = None) -> list[dict]:
    ordered = list(records)

    if sort_key:
        ordered = sorted(ordered, key=lambda record: record["entry"].path.lower())

        if sort_key == "group":
            ordered = sorted(ordered, key=lambda record: record["group_size"], reverse=reverse)
        elif sort_key == "ext":
            ordered = sorted(ordered, key=lambda record: (record["entry"].extension.lower(), record["entry"].filename.lower()), reverse=reverse)
        elif sort_key == "path":
            ordered = sorted(ordered, key=lambda record: record["entry"].path.lower(), reverse=reverse)
        elif sort_key == "name":
            ordered = sorted(ordered, key=lambda record: (record["entry"].filename.lower(), record["entry"].path.lower()), reverse=reverse)
        elif sort_key == "size":
            ordered = sorted(ordered, key=lambda record: record["entry"].size, reverse=reverse)
        elif sort_key == "created":
            ordered = sorted(ordered, key=lambda record: record["entry"].created_at, reverse=reverse)
        elif sort_key == "modified":
            ordered = sorted(ordered, key=lambda record: record["entry"].modified_at, reverse=reverse)
    elif reverse:
        ordered.reverse()

    if limit is not None:
        ordered = ordered[:limit]

    return ordered


def choose_duplicate_keeper(entries: List[FileEntry], strategy: str) -> FileEntry:
    if not entries:
        raise ValueError("entries are required")

    if strategy == "newest":
        return max(entries, key=lambda entry: (entry.modified_at, entry.path.lower()))
    if strategy == "oldest":
        return min(entries, key=lambda entry: (entry.modified_at, entry.path.lower()))
    if strategy == "largest":
        return max(entries, key=lambda entry: (entry.size, entry.path.lower()))
    if strategy == "smallest":
        return min(entries, key=lambda entry: (entry.size, entry.path.lower()))
    return min(entries, key=lambda entry: entry.path.lower())


def _content_matches(path_a: str, path_b: str) -> bool:
    """Byte-for-byte comparison; treats unreadable files as non-matching."""
    try:
        return filecmp.cmp(path_a, path_b, shallow=False)
    except OSError:
        return False


def select_duplicate_records(records, keep_strategy: str = "first path", verify_content: bool = False) -> list[dict]:
    """Return the non-keeper records for each hash group.

    When ``verify_content`` is set, a non-keeper is only selected if it is
    byte-for-byte identical to its group's keeper. This closes the hash-collision
    data-loss window (two different files sharing a digest) before any
    move/delete acts on the selection — callers that mutate the filesystem
    (e.g. the GUI duplicate actions) should pass ``verify_content=True``.
    """
    grouped = defaultdict(list)
    for record in records:
        grouped[record["hash"]].append(record)

    selected = []
    for hash_value, group_records in grouped.items():
        keeper = choose_duplicate_keeper([record["entry"] for record in group_records], keep_strategy)
        for record in group_records:
            if record["entry"].path == keeper.path:
                continue
            if verify_content and not _content_matches(record["entry"].path, keeper.path):
                logger.warning(
                    "Skipping suspected duplicate %s: content differs from keeper %s "
                    "(hash collision or changed file)", record["entry"].path, keeper.path
                )
                continue
            selected.append(record)
    return selected


def serialize_duplicate_record(record: dict) -> dict:
    payload = serialize_file_entry(
        record["entry"],
        record_type="duplicate_entry",
        duplicate_hash=record["hash"],
        duplicate_group_size=record["group_size"],
    )
    return payload


def serialize_duplicate_group_summary(hash_value: str, records: List[dict]) -> dict:
    total_size = sum(record["entry"].size for record in records)
    return {
        "record_type": "duplicate_group_summary",
        "duplicate_hash": hash_value,
        "duplicate_group_size": len(records),
        "group_total_size": total_size,
        "path": "",
        "filename": f"Group {hash_value[:12]}",
        "extension": "",
        "size": total_size,
        "created_at": None,
        "modified_at": None,
        "is_dir": False,
    }


def build_duplicate_export_rows(records, include_group_summary: bool = True) -> list[dict]:
    grouped = defaultdict(list)
    for record in records:
        grouped[record["hash"]].append(record)

    export_rows = []
    for hash_value, group_records in grouped.items():
        if include_group_summary:
            export_rows.append(serialize_duplicate_group_summary(hash_value, group_records))
        export_rows.extend(serialize_duplicate_record(record) for record in group_records)
    return export_rows


def _hash_worker(path, size, mtime, algo, cancel_token):
    """Worker function for threading."""
    if cancel_token and cancel_token.is_set():
        return path, None
    return path, get_file_hash(path, algo, cancel_token)

def find_duplicates(path: str, recursive: bool = True, max_depth: int = -1, progress_callback=None, cancel_token=None) -> Dict[str, List[FileEntry]]:
    # ... (header same)
    logger.info(f"Starting duplicate scan in {path}")
    algo = config.get("hash_algorithm", "md5")
    
    if cancel_token and cancel_token.is_set():
        raise InterruptedError("Cancelled")

    # Step 1: Group by size
    size_map = defaultdict(list)
    count = 0
    # Note: Scanning progress is hard without total count.
    # We could report "Scanned X items" indeterminate.
    for entry in scan_directory(path, recursive, max_depth=max_depth, cancel_token=cancel_token):
        if cancel_token and cancel_token.is_set():
            raise InterruptedError("Cancelled")
            
        if entry.size > 0:
            size_map[entry.size].append(entry)
        count += 1
        if progress_callback and count % 100 == 0:
            progress_callback(count, 0, "Scanning files...")
            
    logger.info(f"Scanned {count} files. Analyzing potential duplicates...")
    
    # Step 2: Filter potential duplicates
    potential_dupes = {size: entries for size, entries in size_map.items() if len(entries) > 1}
    
    # Step 3: Hash and group
    hash_map = defaultdict(list)
    files_to_hash = []
    
    # Check cache first
    for size, entries in potential_dupes.items():
        if cancel_token and cancel_token.is_set():
            raise InterruptedError("Cancelled")
            
        for entry in entries:
            cached_hash = file_cache.get_hash(entry.path, entry.size, entry.modified_at, algo)
            if cached_hash:
                entry.md5 = cached_hash # Using generic field for convenience, or add entry.hash?
                hash_map[cached_hash].append(entry)
            else:
                files_to_hash.append(entry)
                
    # Parallel hashing for uncached files
    if files_to_hash:
        logger.info(f"Hashing {len(files_to_hash)} new files...")
        max_workers = config.get("max_thread_workers", 4)
        total_hashes = len(files_to_hash)
        completed_hashes = 0
        
        # Use ThreadPoolExecutor to allow sharing cancel_token (Event)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_hash_worker, e.path, e.size, e.modified_at, algo, cancel_token): e 
                for e in files_to_hash
            }
            
            for future in as_completed(futures):
                if cancel_token and cancel_token.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise InterruptedError("Cancelled")
                    
                entry = futures[future]
                completed_hashes += 1
                if progress_callback:
                    progress_callback(completed_hashes, total_hashes, "Hashing files")

                try:
                    path, file_hash = future.result()
                    if file_hash:
                        entry.md5 = file_hash
                        # Update cache
                        file_cache.set_hash(entry.path, entry.size, entry.modified_at, file_hash, algo)
                        hash_map[file_hash].append(entry)
                except Exception as e:
                    logger.error(f"Error hashing {entry.path}: {e}")
                    
    # Step 4: Final filter for actual duplicates
    duplicates = {h: entries for h, entries in hash_map.items() if len(entries) > 1}
    logger.info(f"Duplicate scan complete. Found {len(duplicates)} sets.")
    
    return duplicates
