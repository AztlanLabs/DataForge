import filecmp
import hashlib
import os
import queue
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

from ..core.cache import file_cache
from ..core.common import FileEntry
from ..core.config import config
from ..core.hasher import get_file_hash
from ..core.logger import logger
from ..core.scanner import scan_directory
from .search import serialize_file_entry

KEEP_STRATEGIES = ("first path", "newest", "oldest", "largest", "smallest")


def _get_max_workers() -> int:
    try:
        c = os.cpu_count()
        if c is None:
            c = 4
        return min(32, c * 4)
    except Exception:
        return 16


def _fast_hash(path: str, cancel_token=None) -> str | None:
    """xxhash64(first 4KiB) prefilter — fallback to blake2b 8B if xxhash missing."""
    if cancel_token is not None and cancel_token.is_set():
        return None
    try:
        try:
            import xxhash  # type: ignore

            h = xxhash.xxh64()
            with open(path, "rb") as f:
                data = f.read(4096)
                if data:
                    h.update(data)
            return h.hexdigest()
        except ImportError:
            h2 = hashlib.blake2b(digest_size=8)
            with open(path, "rb") as f:
                data = f.read(4096)
                if data:
                    h2.update(data)
            return h2.hexdigest()
    except OSError:
        return None


def _content_matches(path_a: str, path_b: str) -> bool:
    """Byte-for-byte comparison; treats unreadable files as non-matching."""
    try:
        return filecmp.cmp(path_a, path_b, shallow=False)
    except OSError:
        return False


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


def find_duplicates(path: str, recursive: bool = True, max_depth: int = -1, progress_callback=None, cancel_token=None, verify_content: bool = False) -> Dict[str, List[FileEntry]]:
    logger.info(f"Starting duplicate scan in {path}")
    algo = config.get("hash_algorithm", "sha256")

    if cancel_token and cancel_token.is_set():
        return {}

    # Streaming size-map via queue.Queue — O(batch) not O(n)
    # scanner thread(s) -> queue.Queue[FileEntry] -> size-map
    entry_queue: queue.Queue = queue.Queue()
    BATCH_SIZE = 1000
    size_map: Dict[int, List[FileEntry]] = defaultdict(list)
    seen_inodes: set[tuple[int, int]] = set()
    count = 0

    def _drain_queue_to_size_map():
        while not entry_queue.empty():
            if cancel_token is not None and cancel_token.is_set():
                # discard remaining to stop promptly
                while not entry_queue.empty():
                    try:
                        entry_queue.get_nowait()
                    except queue.Empty:
                        break
                return True  # cancelled
            try:
                e = entry_queue.get_nowait()
            except queue.Empty:
                break
            # hardlink dedup: (st_dev, st_ino) equal -> counted once
            key = e.hardlink_key
            # only dedup when inode is populated (non-zero)
            if key != (0, 0):
                if key in seen_inodes:
                    continue
                seen_inodes.add(key)
            size_map[e.size].append(e)
        return False

    # Streaming scan — do not materialize scanner output
    for entry in scan_directory(path, recursive, max_depth=max_depth, cancel_token=cancel_token):
        if cancel_token and cancel_token.is_set():
            return {}

        # skip empty files (size 0 cannot be duplicate in useful sense)
        if entry.size == 0:
            count += 1
            continue
        entry_queue.put(entry)
        count += 1
        if progress_callback and count % 100 == 0:
            progress_callback(count, 0, "Scanning files...")
        if entry_queue.qsize() >= BATCH_SIZE:
            if _drain_queue_to_size_map():
                return {}

    # drain remainder
    if _drain_queue_to_size_map():
        return {}

    logger.info(f"Scanned {count} files. Analyzing potential duplicates...")

    # Filter potential duplicates by size
    potential_dupes = {size: entries for size, entries in size_map.items() if len(entries) > 1}
    if not potential_dupes:
        return {}

    if cancel_token and cancel_token.is_set():
        return {}

    max_workers = _get_max_workers()

    # Stage 2: fast-hash (xxhash64 first 4KiB) prefilter via ThreadPool(min(32,cpu*4))
    fast_map: Dict[str, List[FileEntry]] = defaultdict(list)
    # flatten potential entries for fast hashing
    all_potential: List[FileEntry] = []
    for entries in potential_dupes.values():
        all_potential.extend(entries)

    # fast hash in parallel
    if all_potential:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fast_hash, e.path, cancel_token): e for e in all_potential}
            for fut in as_completed(futures):
                if cancel_token and cancel_token.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    return {}
                entry = futures[fut]
                try:
                    fh = fut.result()
                    if fh is None:
                        continue
                    fast_map[fh].append(entry)
                except Exception:
                    continue

    # only keep fast groups with collisions
    fast_candidates: List[FileEntry] = []
    for fh, entries in fast_map.items():
        if len(entries) > 1:
            fast_candidates.extend(entries)

    if not fast_candidates:
        return {}

    if cancel_token and cancel_token.is_set():
        return {}

    # Stage 3: full hash (sha256 etc.) only on fast collisions
    hash_map: Dict[str, List[FileEntry]] = defaultdict(list)
    files_to_hash: List[FileEntry] = []
    # cache probe
    for entry in fast_candidates:
        if cancel_token and cancel_token.is_set():
            return {}
        cached = file_cache.get_hash(entry.path, entry.size, entry.modified_at, algo)
        if cached:
            hash_map[cached].append(entry)
        else:
            files_to_hash.append(entry)

    if files_to_hash:
        logger.info(f"Hashing {len(files_to_hash)} new files...")
        total_hashes = len(files_to_hash)
        completed = 0
        pending_rows: List[tuple] = []
        cache_batch = int(config.get("cache_batch_size", 1000) or 1000)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_hash_worker, e.path, e.size, e.modified_at, algo, cancel_token): e
                for e in files_to_hash
            }
            for fut in as_completed(futures):
                if cancel_token and cancel_token.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    # flush pending batch before abort if needed
                    if pending_rows:
                        try:
                            file_cache.set_hash_many(pending_rows)
                        except Exception:
                            pass
                    return {}
                entry = futures[fut]
                completed += 1
                if progress_callback:
                    progress_callback(completed, total_hashes, "Hashing files")
                try:
                    _path, file_hash = fut.result()
                    if file_hash:
                        hash_map[file_hash].append(entry)
                        pending_rows.append((entry.path, entry.size, entry.modified_at, file_hash, algo))
                        if len(pending_rows) >= cache_batch:
                            try:
                                file_cache.set_hash_many(pending_rows)
                            except Exception as e:
                                logger.error(f"Batch cache write failed: {e}")
                            pending_rows.clear()
                except Exception as e:
                    logger.error(f"Error hashing {entry.path}: {e}")
        if pending_rows:
            try:
                file_cache.set_hash_many(pending_rows)
            except Exception as e:
                logger.error(f"Batch cache write failed: {e}")

    # Final filter; optional verify_content byte-compare on close hashes
    duplicates = {h: entries for h, entries in hash_map.items() if len(entries) > 1}

    if verify_content and duplicates:
        verified: Dict[str, List[FileEntry]] = {}
        for h, entries in duplicates.items():
            if cancel_token and cancel_token.is_set():
                return {}
            # group by content equality to keeper
            # keep only entries byte-identical to first
            keeper = entries[0]
            same: List[FileEntry] = [keeper]
            for other in entries[1:]:
                if _content_matches(other.path, keeper.path):
                    same.append(other)
                else:
                    logger.warning(
                        "Skipping suspected duplicate %s: content differs from keeper %s (hash collision or changed file)",
                        other.path,
                        keeper.path,
                    )
            if len(same) > 1:
                verified[h] = same
        duplicates = verified

    logger.info(f"Duplicate scan complete. Found {len(duplicates)} sets.")

    return duplicates
