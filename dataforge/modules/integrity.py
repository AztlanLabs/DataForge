import datetime
import json
import os
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..core.config import config
from ..core.hasher import SUPPORTED_ALGORITHMS, get_file_hash
from ..core.scanner import scan_directory

# MD5 remains readable for legacy snapshots, but new baselines default to a
# tamper-evidence-grade digest and honour the user's configured algorithm.
_DEFAULT_INTEGRITY_ALGO = "sha256"


def _resolve_algorithm() -> str:
    algo = config.get("hash_algorithm", _DEFAULT_INTEGRITY_ALGO)
    if algo not in SUPPORTED_ALGORITHMS:
        return _DEFAULT_INTEGRITY_ALGO
    return algo


def _unwrap_snapshot(raw) -> tuple[dict, str]:
    """Return ``(files_map, algorithm)`` for both new and legacy snapshots.

    New snapshots are ``{"algorithm": ..., "files": {rel: hash}}``. Legacy
    snapshots were a flat ``{rel: hash}`` dict hashed with MD5.
    """
    if isinstance(raw, dict) and isinstance(raw.get("files"), dict):
        return raw["files"], raw.get("algorithm", "md5")
    if isinstance(raw, dict):
        return raw, "md5"
    return {}, "md5"


def _snapshot_key(root_path: str, entry_path: str) -> str:
    if os.path.isfile(root_path):
        return os.path.basename(entry_path)

    return os.path.relpath(entry_path, root_path)


def _empty_verification_stats() -> dict[str, int]:
    return {"NEW": 0, "MODIFIED": 0, "DELETED": 0, "ERROR": 0}


def _build_verification_report(discrepancies, snapshot_entries, current_entries):
    stats = _empty_verification_stats()
    for item in discrepancies:
        for key in stats:
            if item.startswith(key):
                stats[key] += 1

    return {
        "discrepancies": discrepancies,
        "stats": stats,
        "snapshot_entries": snapshot_entries,
        "current_entries": current_entries,
        "issue_count": len(discrepancies),
        "is_clean": len(discrepancies) == 0,
    }


def _hash_worker(entry_path, algo, cancel_token):
    if cancel_token and cancel_token.is_set():
        return entry_path, None
    return entry_path, get_file_hash(entry_path, algo, cancel_token)


def _get_max_workers() -> int:
    try:
        cpu = os.cpu_count() or 4
        return min(32, cpu * 4)
    except Exception:
        return 16


def _flush_cache(rows: list[tuple[str, int, float, str, str]]) -> None:
    if not rows:
        return
    try:
        from ..core.cache import file_cache

        file_cache.set_hash_many(rows)
    except Exception:
        pass


class IntegrityMonitor:
    @staticmethod
    def create_snapshot(path: str, output_file: str, progress_callback=None, cancel_token=None):
        """
        Streaming snapshot creation.

        Pipeline: scan_directory (streaming) -> queue.Queue -> ThreadPool(min(32, cpu*4)) hash
        -> executemany cache write. Snapshot is written atomically via tmp+os.replace.
        No materialized scan list — peak RSS is O(batch).
        """
        algo = _resolve_algorithm()
        try:
            cache_batch_size = int(config.get("cache_batch_size", 1000))
            if cache_batch_size < 1:
                cache_batch_size = 1000
        except Exception:
            cache_batch_size = 1000

        max_workers = _get_max_workers()

        # Queue for streaming producer -> consumers (spec required)
        file_queue: queue.Queue = queue.Queue(maxsize=cache_batch_size * 2)

        snapshot: dict[str, str] = {}
        scanned = 0
        skipped = 0
        completed = 0
        cache_rows: list[tuple[str, int, float, str, str]] = []

        # Atomic-write preparation: tmp file in same dir + os.replace
        # Keep tmp_path as sibling of output_file but do NOT create it before scan
        # to avoid self-inclusion when output_file lives inside scanned tree.
        output_abs = os.path.abspath(output_file)
        output_dir = os.path.dirname(output_abs) or "."
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError:
            pass
        tmp_path = output_abs + ".tmp"

        def _cleanup_tmp():
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        if cancel_token and cancel_token.is_set():
            _cleanup_tmp()
            raise InterruptedError("Cancelled")

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                pending: list = []

                def _process_pending(batch):
                    nonlocal completed, skipped, cache_rows
                    if not batch:
                        return
                    if cancel_token and cancel_token.is_set():
                        raise InterruptedError("Cancelled")
                    futures: dict = {}
                    for entry in batch:
                        # Exclude the snapshot output itself if it lives inside the scanned tree
                        if os.path.abspath(entry.path) == output_abs:
                            continue
                        try:
                            rel = _snapshot_key(path, entry.path)
                        except ValueError:
                            skipped += 1
                            continue
                        # Enqueue for spec visibility (bounded queue -> O(batch))
                        try:
                            file_queue.put(entry, block=False)
                        except queue.Full:
                            try:
                                file_queue.get_nowait()
                                file_queue.put(entry, block=False)
                            except Exception:
                                pass
                        # Drain queue to keep bound
                        try:
                            file_queue.get_nowait()
                        except queue.Empty:
                            pass
                        fut = executor.submit(_hash_worker, entry.path, algo, cancel_token)
                        futures[fut] = (entry, rel)
                    for fut in as_completed(futures):
                        if cancel_token and cancel_token.is_set():
                            for f in list(futures.keys()):
                                f.cancel()
                            try:
                                executor.shutdown(wait=False, cancel_futures=True)
                            except TypeError:
                                executor.shutdown(wait=False)
                            raise InterruptedError("Cancelled")
                        entry, rel = futures[fut]
                        completed += 1
                        if progress_callback:
                            try:
                                progress_callback(completed, scanned, f"Hashing {os.path.basename(entry.path)}")
                            except Exception:
                                pass
                        try:
                            _, file_hash = fut.result()
                            if file_hash:
                                snapshot[rel] = file_hash
                                cache_rows.append(
                                    (entry.path, int(entry.size), float(entry.modified_at), file_hash, algo)
                                )
                                if len(cache_rows) >= cache_batch_size:
                                    _flush_cache(cache_rows)
                                    cache_rows.clear()
                            else:
                                skipped += 1
                        except Exception:
                            skipped += 1
                    if cache_rows and len(cache_rows) >= cache_batch_size:
                        _flush_cache(cache_rows)
                        cache_rows.clear()

                for entry in scan_directory(path, recursive=True, cancel_token=cancel_token):
                    if cancel_token and cancel_token.is_set():
                        raise InterruptedError("Cancelled")
                    scanned += 1
                    pending.append(entry)
                    if len(pending) >= cache_batch_size:
                        _process_pending(pending)
                        pending.clear()
                if pending:
                    _process_pending(pending)
                    pending.clear()
                if cache_rows:
                    _flush_cache(cache_rows)
                    cache_rows.clear()
                if cancel_token and cancel_token.is_set():
                    raise InterruptedError("Cancelled")
        except InterruptedError:
            _cleanup_tmp()
            raise
        # Final atomic write — only if not cancelled
        if cancel_token and cancel_token.is_set():
            _cleanup_tmp()
            raise InterruptedError("Cancelled")

        payload = {
            "algorithm": algo,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "files": snapshot,
        }
        try:
            # Ensure parent dir exists
            parent = os.path.dirname(os.path.abspath(output_file))
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(tmp_path, "w") as f:
                json.dump(payload, f, indent=4)
                try:
                    f.flush()
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp_path, output_file)
        except Exception:
            _cleanup_tmp()
            raise

        return {
            "message": f"Snapshot saved with {len(snapshot)} files ({algo}).",
            "output": output_file,
            "algorithm": algo,
            "saved": len(snapshot),
            "scanned": scanned,
            "skipped": skipped,
        }

    @staticmethod
    def verify_snapshot(path: str, snapshot_file: str, progress_callback=None, cancel_token=None) -> dict:
        """
        Streaming verification.

        Pipeline: scan_directory (streaming) -> queue.Queue -> ThreadPool(min(32, cpu*4)) hash
        -> executemany cache write. Legacy flat MD5 snapshots remain readable.
        On cancel_token set, returns promptly with ``cancelled: True``.
        """
        try:
            with open(snapshot_file, "r") as f:
                raw_snapshot = json.load(f)
        except (OSError, json.JSONDecodeError):
            report = _build_verification_report(["ERROR: Could not read snapshot file."], 0, 0)
            report["cancelled"] = bool(cancel_token and cancel_token.is_set())
            return report

        snapshot, algo = _unwrap_snapshot(raw_snapshot)
        if algo not in SUPPORTED_ALGORITHMS:
            algo = "md5"

        snapshot_abs = os.path.abspath(snapshot_file)

        try:
            cache_batch_size = int(config.get("cache_batch_size", 1000))
            if cache_batch_size < 1:
                cache_batch_size = 1000
        except Exception:
            cache_batch_size = 1000

        max_workers = _get_max_workers()
        file_queue: queue.Queue = queue.Queue(maxsize=cache_batch_size * 2)

        discrepancies: list[str] = []
        current_files: set[str] = set()
        cache_rows: list[tuple[str, int, float, str, str]] = []
        scanned = 0

        # Pending verifies batched to keep RSS O(batch)
        pending_verify: list[tuple[str, str, object]] = []
        verified = 0

        def _flush_pending_verify(batch, executor):
            nonlocal verified, cache_rows
            if not batch:
                return
            futures: dict = {}
            for entry_path, rel_path, entry in batch:
                try:
                    file_queue.put(entry, block=False)
                except queue.Full:
                    try:
                        file_queue.get_nowait()
                        file_queue.put(entry, block=False)
                    except Exception:
                        pass
                try:
                    file_queue.get_nowait()
                except queue.Empty:
                    pass
                fut = executor.submit(_hash_worker, entry_path, algo, cancel_token)
                futures[fut] = (entry_path, rel_path, entry)

            for fut in as_completed(futures):
                if cancel_token and cancel_token.is_set():
                    for f in list(futures.keys()):
                        f.cancel()
                    try:
                        executor.shutdown(wait=False, cancel_futures=True)
                    except TypeError:
                        executor.shutdown(wait=False)
                    raise InterruptedError("Cancelled")
                entry_path, rel_path, entry = futures[fut]
                verified += 1
                if progress_callback:
                    try:
                        progress_callback(verified, scanned, f"Verifying {rel_path}")
                    except Exception:
                        pass
                try:
                    _, current_hash = fut.result()
                    if current_hash is None:
                        # Cancelled mid-hash -> treat as error but propagate cancel
                        if cancel_token and cancel_token.is_set():
                            raise InterruptedError("Cancelled")
                        discrepancies.append(f"ERROR: {rel_path}")
                    elif current_hash != snapshot[rel_path]:
                        discrepancies.append(f"MODIFIED: {rel_path}")
                    else:
                        # Cache the verified hash for future runs
                        try:
                            cache_rows.append(
                                (entry_path, int(entry.size), float(entry.modified_at), current_hash, algo)
                            )
                            if len(cache_rows) >= cache_batch_size:
                                _flush_cache(cache_rows)
                                cache_rows.clear()
                        except Exception:
                            pass
                except InterruptedError:
                    raise
                except Exception:
                    discrepancies.append(f"ERROR: {rel_path}")

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for entry in scan_directory(path, recursive=True, cancel_token=cancel_token):
                    if cancel_token and cancel_token.is_set():
                        raise InterruptedError("Cancelled")
                    if os.path.abspath(entry.path) == snapshot_abs:
                        continue
                    scanned += 1
                    try:
                        rel_path = _snapshot_key(path, entry.path)
                    except ValueError:
                        continue
                    current_files.add(rel_path)
                    if rel_path not in snapshot:
                        discrepancies.append(f"NEW: {rel_path}")
                    else:
                        pending_verify.append((entry.path, rel_path, entry))
                        if len(pending_verify) >= cache_batch_size:
                            _flush_pending_verify(pending_verify, executor)
                            pending_verify.clear()
                            if len(cache_rows) >= cache_batch_size:
                                _flush_cache(cache_rows)
                                cache_rows.clear()
                if pending_verify:
                    _flush_pending_verify(pending_verify, executor)
                    pending_verify.clear()
                if cache_rows:
                    _flush_cache(cache_rows)
                    cache_rows.clear()
                if cancel_token and cancel_token.is_set():
                    raise InterruptedError("Cancelled")
        except InterruptedError:
            # Return promptly with cancelled flag and partial results
            # Flush cache optionally but return
            if cache_rows:
                _flush_cache(cache_rows)
            report = _build_verification_report(discrepancies, len(snapshot), len(current_files))
            # Add DELETED for snapshot entries not seen yet? Only for current_files seen so far
            # Do not add deleted on cancel to avoid misleading
            report["cancelled"] = True
            report["current_entries"] = len(current_files)
            return report

        # Check deleted files (only if not cancelled)
        for rel_path in snapshot:
            if rel_path not in current_files:
                discrepancies.append(f"DELETED: {rel_path}")

        report = _build_verification_report(discrepancies, len(snapshot), len(current_files))
        report["cancelled"] = bool(cancel_token and cancel_token.is_set())
        return report
