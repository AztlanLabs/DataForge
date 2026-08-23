import concurrent.futures
import logging
import os
import queue
import stat as stat_mod
import unicodedata
from typing import Callable, Generator, Optional

from .common import FileEntry, is_bidi_suspicious, is_reflink_suspicious, is_sparse

logger = logging.getLogger(__name__)


def _current_config():
    """Return the current ConfigManager singleton, handling reload."""
    try:
        import importlib

        mod = importlib.import_module("dataforge.core.config")
        cfg = getattr(mod, "config", None)
        if cfg is not None:
            return cfg
    except Exception:
        pass
    # Fallback: try ConfigManager singleton
    try:
        from .config import ConfigManager

        inst = ConfigManager._instance
        if inst is not None:
            return inst
    except Exception:
        pass
    # Last resort: direct import (may be stale but better than None)
    from .config import config as _cfg

    return _cfg


class _ConfigProxy:
    """Proxy that always delegates to the current config singleton.

    This keeps ``dataforge.core.scanner.config`` patchable via
    ``patch("dataforge.core.scanner.config")`` while ensuring normal
    operation always sees the latest config after a reload.
    """

    def get(self, *args, **kwargs):
        return _current_config().get(*args, **kwargs)


# Backwards-compatible alias for tests that patch ``scanner.config``.
config = _ConfigProxy()


def _get_max_workers() -> int:
    try:
        c = os.cpu_count()
        if c is None:
            c = 4
        return min(32, c * 4)
    except Exception:
        return 16


def _build_from_stat(path: str, filename: str, extension: str, st: os.stat_result) -> FileEntry:
    # F10: NFC normalization + bidi detection
    try:
        normalized = unicodedata.normalize("NFC", path)
    except Exception:
        normalized = path
    try:
        bidi = is_bidi_suspicious(path) or is_bidi_suspicious(filename)
    except Exception:
        bidi = False
    # F16: sparse detection via st_blocks*512 < st_size
    try:
        st_blocks = getattr(st, "st_blocks", 0)
        sparse_flag = is_sparse(st_blocks, st.st_size)
    except Exception:
        st_blocks = getattr(st, "st_blocks", 0)
        sparse_flag = False
    # F21: reflink detection via FIEMAP shared extents
    reflink_flag = False
    try:
        # Use helper that attempts FIEMAP ioctl; cheap fallback if not Linux or not supported
        reflink_flag = is_reflink_suspicious(path, st_blocks, st.st_size)
    except Exception:
        reflink_flag = False

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
        st_blocks=st_blocks,
        normalized_path=normalized,
        bidi_suspicious=bidi,
        sparse=sparse_flag,
        reflink_suspicious=reflink_flag,
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
    on_error: Optional[Callable[[str, Exception], None]] = None,
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
                except OSError as e:
                    _log_scan_error(entry.path, e, on_error)
                    continue

                # Directory handling — use follow_symlinks=False to avoid double stat
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError as e:
                    _log_scan_error(entry.path, e, on_error)
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
                except OSError as e:
                    _log_scan_error(entry.path, e, on_error)
                    continue
                if not is_file:
                    continue
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError as e:
                    _log_scan_error(entry.path, e, on_error)
                    continue
                # Build FileEntry directly from DirEntry.stat — no double stat
                # F10/F16/F21 handling is inside _build_from_stat
                files.append(
                    _build_from_stat(
                        path=entry.path,
                        filename=entry.name,
                        extension=os.path.splitext(entry.name)[1].lower(),
                        st=st,
                    )
                )
    except OSError as e:
        _log_scan_error(dir_path, e, on_error)
    return files, subdirs


def _log_scan_error(path: str, exc: Exception, on_error=None) -> None:
    """Log a scan OSError with specific handling and invoke optional callback."""
    if isinstance(exc, FileNotFoundError):
        logger.warning("Path not found: %s", path)
    elif isinstance(exc, PermissionError):
        logger.warning("Permission denied: %s", path)
    else:
        logger.warning("OS error scanning %s: %s", path, exc)
    if on_error is not None:
        try:
            on_error(path, exc)
        except Exception:
            pass


def scan_directory(
    root_path: str,
    recursive: bool = True,
    max_depth: int = -1,
    cancel_token=None,
    on_error: Optional[Callable[[str, Exception], None]] = None,
) -> Generator[FileEntry, None, None]:
    """
    Generator that yields FileEntry objects for files in the directory.
    max_depth: -1 for infinite, 0 for current dir only, N for N levels deep.

    Parallel BFS implementation:
    - Work-queue of dirs processed via ThreadPoolExecutor(min(32, cpu*4))
    - Each dir scanned with os.scandir; FileEntry built from entry.stat(follow_symlinks=False)
    - Populates st_ino/st_dev/st_blocks for hardlink/sparse awareness
    - F10: NFC-normalizes path -> FileEntry.normalized_path and flags bidi_suspicious
    - F16: sparse detection via st_blocks*512 < st_size
    - F21: reflink detection via FIEMAP shared extents
    - Batch emission (1k) via queue.Queue
    - Honors excluded_folders/extensions and cancel_token promptly
    - OSError during scan is logged (warning) and forwarded to on_error if provided
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
        except OSError as e:
            _log_scan_error(root_path, e, on_error)
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
    except OSError as e:
        _log_scan_error(root_path, e, on_error)
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
                executor.submit(
                    _scan_single_dir, d, depth, excl_folders, excl_exts, cancel_token, on_error
                ): (d, depth)
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
                except OSError as e:
                    _log_scan_error(futures[fut][0], e, on_error)
                    continue
                except Exception as e:
                    logger.warning("Unexpected error scanning %s: %s", futures[fut][0], e)
                    if on_error is not None:
                        try:
                            on_error(futures[fut][0], e)
                        except Exception:
                            pass
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
