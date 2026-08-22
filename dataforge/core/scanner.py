import concurrent.futures
import os
import queue
import stat as stat_mod
from typing import Generator, Optional

from .common import FileEntry
from .config import config


def _get_max_workers() -> int:
    try:
        c = os.cpu_count()
        if c is None:
            c = 4
        return min(32, c * 4)
    except Exception:
        return 16


def _build_from_stat(path: str, filename: str, extension: str, st: os.stat_result) -> FileEntry:
    return FileEntry(
        path=path,
        filename=filename,
        extension=extension,
        size=st.st_size,
        created_at=st.st_ctime,
        modified_at=st.st_mtime,
        is_dir=False,
        st_ino=getattr(st, "st_ino", 0),
        st_dev=getattr(st, "st_dev", 0),
        st_blocks=getattr(st, "st_blocks", 0),
    )


def build_file_entry(path: str) -> Optional[FileEntry]:
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError:
        return None
    # Only regular files are returned; dirs are not built via this helper
    try:
        if not stat_mod.S_ISREG(st.st_mode):
            # For single-file root_path that is a dir, caller handles dir branch;
            # but if someone calls build_file_entry on a dir, return entry as file-like?
            # Keep original behaviour: return entry even for dir? Original always set is_dir=False.
            # We keep returning for regular files only; non-reg still yields with size etc.
            # To preserve backward compat, don't reject non-reg — just build.
            pass
    except Exception:
        pass
    return _build_from_stat(
        path=path,
        filename=os.path.basename(path),
        extension=os.path.splitext(path)[1].lower(),
        st=st,
    )


def _scan_single_dir(
    dir_path: str,
    depth_remaining: int,
    excl_folders: set,
    excl_exts: tuple,
    cancel_token=None,
) -> tuple[list[FileEntry], list[tuple[str, int]]]:
    files: list[FileEntry] = []
    subdirs: list[tuple[str, int]] = []
    if cancel_token is not None and cancel_token.is_set():
        return files, subdirs
    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                if cancel_token is not None and cancel_token.is_set():
                    break
                # Never follow symlinks
                try:
                    if entry.is_symlink():
                        continue
                except OSError:
                    continue

                # Directory handling — use follow_symlinks=False to avoid double stat
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue

                if is_dir:
                    if entry.name in excl_folders:
                        continue
                    # Depth gating
                    if depth_remaining == 0:
                        continue
                    can_recurse = (depth_remaining == -1) or (depth_remaining > 0)
                    if can_recurse:
                        next_depth = -1 if depth_remaining == -1 else depth_remaining - 1
                        subdirs.append((entry.path, next_depth))
                    continue

                # File handling
                if excl_exts and entry.name.lower().endswith(excl_exts):
                    continue
                try:
                    is_file = entry.is_file(follow_symlinks=False)
                except OSError:
                    continue
                if not is_file:
                    continue
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                # Build FileEntry directly from DirEntry.stat — no double stat
                files.append(
                    _build_from_stat(
                        path=entry.path,
                        filename=entry.name,
                        extension=os.path.splitext(entry.name)[1].lower(),
                        st=st,
                    )
                )
    except OSError:
        pass
    return files, subdirs


def scan_directory(
    root_path: str, recursive: bool = True, max_depth: int = -1, cancel_token=None
) -> Generator[FileEntry, None, None]:
    """
    Generator that yields FileEntry objects for files in the directory.
    max_depth: -1 for infinite, 0 for current dir only, N for N levels deep.

    Parallel BFS implementation:
    - Work-queue of dirs processed via ThreadPoolExecutor(min(32, cpu*4))
    - Each dir scanned with os.scandir; FileEntry built from entry.stat(follow_symlinks=False)
    - Populates st_ino/st_dev/st_blocks for hardlink/sparse awareness
    - Batch emission (1k) via queue.Queue
    - Honors excluded_folders/extensions and cancel_token promptly
    """
    if cancel_token is not None and cancel_token.is_set():
        return

    if not recursive:
        max_depth = 0

    excl_folders = set(config.get("excluded_folders", []))
    raw_exts = config.get("excluded_extensions", [])
    # Normalize to lower-case tuple for endswith
    if isinstance(raw_exts, (list, tuple)):
        excl_exts = tuple(str(e).lower() for e in raw_exts if isinstance(e, str) and e)
    else:
        excl_exts = tuple()

    # Single-file path fast path — uses stat reuse (no DirEntry) but populates inode fields
    if os.path.isfile(root_path):
        if excl_exts and os.path.basename(root_path).lower().endswith(excl_exts):
            return
        # Symlink to file should be skipped like in dir walk? Original yielded it.
        # Keep symlink check for consistency with dir walk: skip symlinked file roots.
        try:
            if os.path.islink(root_path):
                return
        except OSError:
            pass
        entry = build_file_entry(root_path)
        if entry is not None:
            yield entry
        return

    # Verify root is a directory; if not, try scandir to trigger OSError handling and return
    try:
        # Use scandir to validate existence and readability without extra stat
        with os.scandir(root_path):
            pass
    except OSError:
        return
    if not os.path.isdir(root_path):
        return

    max_workers = _get_max_workers()
    # Batch emission queue (1k) — spec requires queue.Queue
    batch_queue: queue.Queue = queue.Queue()
    BATCH_SIZE = 1000

    def _drain_queue():
        while not batch_queue.empty():
            if cancel_token is not None and cancel_token.is_set():
                # Discard remaining to stop promptly
                while not batch_queue.empty():
                    try:
                        batch_queue.get_nowait()
                    except queue.Empty:
                        break
                return
            try:
                yield batch_queue.get_nowait()
            except queue.Empty:
                break

    current_level: list[tuple[str, int]] = [(root_path, max_depth)]

    # Use ThreadPoolExecutor for parallel BFS per level
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        while current_level:
            if cancel_token is not None and cancel_token.is_set():
                # Cancel pending futures and drain
                return

            futures = {
                executor.submit(_scan_single_dir, d, depth, excl_folders, excl_exts, cancel_token): (d, depth)
                for d, depth in current_level
            }
            next_level: list[tuple[str, int]] = []

            for fut in concurrent.futures.as_completed(futures):
                if cancel_token is not None and cancel_token.is_set():
                    # Cancel remaining futures
                    for f in futures:
                        f.cancel()
                    return
                try:
                    files, subdirs = fut.result()
                except Exception:
                    continue
                # Enqueue files into batch queue
                for fe in files:
                    batch_queue.put(fe)
                    if batch_queue.qsize() >= BATCH_SIZE:
                        yield from _drain_queue()
                next_level.extend(subdirs)

            # Also check cancel before next level
            if cancel_token is not None and cancel_token.is_set():
                return
            current_level = next_level

    # Drain any remaining
    yield from _drain_queue()
