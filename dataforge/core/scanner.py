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


def _is_private_systemd_dir(path: str) -> bool:
    """Return True for systemd private tmp dirs that should be skipped quietly."""
    try:
        # systemd creates /tmp/systemd-private-<hash>-<service>-<suffix> and /var/tmp/systemd-private-*
        # owned 0700 root, many per service. Floods warning if scanned.
        if "/systemd-private" in path:
            return True
        if path.startswith("/var/tmp/systemd-private") or path.startswith("/tmp/systemd-private"):
            return True
    except Exception:
        pass
    return False


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
        atime=st.st_atime,
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
    # TICK-905: skip private systemd dirs quietly before scandir to avoid warning flood
    if _is_private_systemd_dir(dir_path):
        logger.debug(f"Skipping private systemd dir {dir_path}")
        if on_error is not None:
            try:
                on_error(dir_path, PermissionError(f"private systemd tmp: {dir_path}"))
            except Exception:
                pass
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
                    # TICK-905: skip private systemd dirs entirely
                    if _is_private_systemd_dir(entry.path):
                        logger.debug(f"Skipping private systemd subdir {entry.path}")
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
                except PermissionError as e:
                    # F20: try acquire_file fallback before skipping
                    _acquired = False
                    try:
                        from .acquire import acquire_file  # lazy to avoid circular
                    except Exception:
                        acquire_file = None  # type: ignore
                    if acquire_file is not None:
                        try:
                            with acquire_file(entry.path, "rb") as af:
                                try:
                                    fst = os.fstat(af.fileno())
                                except Exception:
                                    # Fallback to os.stat if fstat fails (e.g., BytesIO mock)
                                    try:
                                        fst = os.stat(entry.path, follow_symlinks=False)
                                    except OSError:
                                        fst = None  # type: ignore
                                if fst is not None:
                                    logger.warning(
                                        "Permission denied for %s, acquired via fallback", entry.path
                                    )
                                    if on_error is not None:
                                        try:
                                            on_error(entry.path, e)
                                        except Exception:
                                            pass
                                    files.append(
                                        _build_from_stat(
                                            path=entry.path,
                                            filename=entry.name,
                                            extension=os.path.splitext(entry.name)[1].lower(),
                                            st=fst,
                                        )
                                    )
                                    _acquired = True
                                else:
                                    # Fallback: build with available info (size 0)
                                    # Create synthetic stat-like object
                                    logger.warning(
                                        "Acquire fallback for %s succeeded but stat unavailable, using size 0",
                                        entry.path,
                                    )
                                    # Use size from file read if possible
                                    try:
                                        # Try to get size via seek/tell
                                        pos = af.tell() if hasattr(af, "tell") else 0
                                        try:
                                            af.seek(0, os.SEEK_END)  # type: ignore
                                            sz = af.tell()  # type: ignore
                                            af.seek(pos)  # type: ignore
                                        except Exception:
                                            # Try read length
                                            try:
                                                data = af.read()  # type: ignore
                                                sz = len(data) if data is not None else 0
                                                try:
                                                    af.seek(0)  # type: ignore
                                                except Exception:
                                                    pass
                                            except Exception:
                                                sz = 0
                                    except Exception:
                                        sz = 0
                                    # Build FileEntry with synthetic values
                                    files.append(
                                        FileEntry(
                                            path=entry.path,
                                            filename=entry.name,
                                            extension=os.path.splitext(entry.name)[1].lower(),
                                            size=sz,
                                            created_at=0,
                                            modified_at=0,
                                            is_dir=False,
                                        )
                                    )
                                    _acquired = True
                        except PermissionError as ae:
                            logger.warning(
                                "Acquire fallback failed for %s: %s (original: %s)", entry.path, ae, e
                            )
                        except OSError as ae:
                            logger.warning(
                                "Acquire fallback failed for %s: %s (original: %s)", entry.path, ae, e
                            )
                        except Exception as ae:
                            logger.warning(
                                "Acquire fallback error for %s: %s (original: %s)", entry.path, ae, e
                            )
                    if _acquired:
                        continue
                    _log_scan_error(entry.path, e, on_error)
                    continue
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
    except PermissionError as e:
        # TICK-905: PermissionError on scandir is non-fatal dir skip, no acquire_file fallback
        _log_scan_error(dir_path, e, on_error)
        return [], []
    except OSError as e:
        _log_scan_error(dir_path, e, on_error)
        return [], []
    return files, subdirs


def _log_scan_error(path: str, exc: Exception, on_error=None) -> None:
    """Log a scan OSError with specific handling and invoke optional callback."""
    # TICK-905: private systemd dirs log at debug to avoid warning flood
    is_private = _is_private_systemd_dir(path)
    if isinstance(exc, FileNotFoundError):
        logger.warning("Path not found: %s", path)
    elif isinstance(exc, PermissionError):
        if is_private:
            logger.debug("Permission denied (private systemd, skipped): %s", path)
        else:
            logger.warning("Permission denied: %s", path)
    else:
        if is_private:
            logger.debug("OS error scanning private dir %s: %s", path, exc)
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

            # TICK-905: pre-filter private systemd dirs before submitting to pool
            filtered_level: list[tuple[str, int]] = []
            for d, depth in current_level:
                if _is_private_systemd_dir(d):
                    logger.debug(f"Skipping private systemd dir before submit: {d}")
                    if on_error is not None:
                        try:
                            on_error(d, PermissionError(f"private systemd tmp: {d}"))
                        except Exception:
                            pass
                    continue
                # Also skip non-readable dirs via os.access probe to avoid warning flood
                try:
                    if not os.access(d, os.R_OK | os.X_OK):
                        # Confirm with scandir probe to avoid false positive on weird perms
                        try:
                            with os.scandir(d):
                                pass
                        except PermissionError:
                            logger.debug(f"Skipping unreadable dir {d}")
                            if on_error is not None:
                                try:
                                    on_error(d, PermissionError(f"unreadable: {d}"))
                                except Exception:
                                    pass
                            continue
                        except OSError:
                            logger.debug(f"Skipping unreadable dir {d}")
                            continue
                except Exception:
                    pass
                filtered_level.append((d, depth))
            if not filtered_level:
                # All dirs filtered, drain and exit loop, next_level will be empty
                current_level = []
                continue
            current_level = filtered_level

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
