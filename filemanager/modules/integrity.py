import datetime
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..core.config import config
from ..core.scanner import scan_directory
from ..core.hasher import get_file_hash, SUPPORTED_ALGORITHMS


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


class IntegrityMonitor:
    @staticmethod
    def create_snapshot(path: str, output_file: str, progress_callback=None, cancel_token=None):
        """
        Scan directory, hash all files (in parallel across
        config["max_thread_workers"] threads — the same pool-size setting
        used by duplicate scanning and forensic hash manifests, since this
        is the same "hash many files" workload), and save to JSON.
        """
        snapshot = {}
        algo = _resolve_algorithm()
        entries = list(scan_directory(path, recursive=True, cancel_token=cancel_token))
        total = len(entries)
        skipped = 0

        rel_path_map = {}
        for entry in entries:
            try:
                rel_path_map[entry.path] = _snapshot_key(path, entry.path)
            except ValueError:
                # Path issue (e.g. different drive)
                skipped += 1

        max_workers = max(1, config.get("max_thread_workers", 4))
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_hash_worker, entry_path, algo, cancel_token): entry_path
                for entry_path in rel_path_map
            }
            for future in as_completed(futures):
                entry_path = futures[future]
                if cancel_token and cancel_token.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise InterruptedError("Cancelled")

                completed += 1
                if progress_callback:
                    progress_callback(completed, total, f"Hashing {os.path.basename(entry_path)}")

                try:
                    _, file_hash = future.result()
                    if file_hash:
                        snapshot[rel_path_map[entry_path]] = file_hash
                    else:
                        skipped += 1
                except Exception:
                    skipped += 1

        payload = {
            "algorithm": algo,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "files": snapshot,
        }
        with open(output_file, 'w') as f:
            json.dump(payload, f, indent=4)

        return {
            "message": f"Snapshot saved with {len(snapshot)} files ({algo}).",
            "output": output_file,
            "algorithm": algo,
            "saved": len(snapshot),
            "scanned": total,
            "skipped": skipped,
        }

    @staticmethod
    def verify_snapshot(path: str, snapshot_file: str, progress_callback=None, cancel_token=None) -> dict:
        """
        Compare current state of 'path' against 'snapshot_file' (hashing in
        parallel across config["max_thread_workers"] threads).
        Returns a structured report containing discrepancies and counts.
        """
        try:
            with open(snapshot_file, 'r') as f:
                raw_snapshot = json.load(f)
        except (OSError, json.JSONDecodeError):
            return _build_verification_report(["ERROR: Could not read snapshot file."], 0, 0)

        snapshot, algo = _unwrap_snapshot(raw_snapshot)
        if algo not in SUPPORTED_ALGORITHMS:
            algo = "md5"

        discrepancies = []
        current_files = set()
        entries = list(scan_directory(path, recursive=True, cancel_token=cancel_token))
        total = len(entries)

        to_verify = []
        for entry in entries:
            rel_path = _snapshot_key(path, entry.path)
            current_files.add(rel_path)
            if rel_path not in snapshot:
                discrepancies.append(f"NEW: {rel_path}")
            else:
                to_verify.append((entry.path, rel_path))

        max_workers = max(1, config.get("max_thread_workers", 4))
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_hash_worker, entry_path, algo, cancel_token): rel_path
                for entry_path, rel_path in to_verify
            }
            for future in as_completed(futures):
                rel_path = futures[future]
                if cancel_token and cancel_token.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise InterruptedError("Cancelled")

                completed += 1
                if progress_callback:
                    progress_callback(completed, total, f"Verifying {rel_path}")

                try:
                    _, current_hash = future.result()
                    if current_hash != snapshot[rel_path]:
                        discrepancies.append(f"MODIFIED: {rel_path}")
                except Exception:
                    discrepancies.append(f"ERROR: {rel_path}")

        # Check deleted files
        for rel_path in snapshot:
            if rel_path not in current_files:
                discrepancies.append(f"DELETED: {rel_path}")

        return _build_verification_report(discrepancies, len(snapshot), len(current_files))
