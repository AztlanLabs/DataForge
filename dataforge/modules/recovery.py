"""
Advanced File Recovery module.

Supports trash recovery (recently deleted files), and raw disk carving
via external tools (photorec/testdisk) or built-in header/footer scanning.
"""
import mmap
import os
import platform
import subprocess
import shutil
import tempfile
import threading
import configparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timezone

from ..core.logger import logger
from ..core.utils import format_size
from .file_signatures import SIGNATURES

# F20 acquire fallback — graceful if acquire module missing
try:
    from ..core.acquire import HAS_VSS, acquire_file  # noqa: F401
except Exception:  # pragma: no cover
    HAS_VSS = False

    import contextlib

    @contextlib.contextmanager
    def acquire_file(path, mode="rb"):  # type: ignore[no-redef]
        f = open(path, mode)
        try:
            yield f
        finally:
            try:
                f.close()
            except Exception:
                pass


def _get_max_workers() -> int:
    """Return adaptive thread pool size (same formula as scanner/duplicates)."""
    try:
        c = os.cpu_count()
        if c is None:
            c = 4
        return min(32, c * 4)
    except Exception:
        return 16


# ---------------------------------------------------------------------------
# External tool detection
# ---------------------------------------------------------------------------

def _command_available(cmd):
    """Check if a CLI command is available on the system."""
    try:
        result = subprocess.run(
            ["which", cmd] if platform.system() != "Windows" else ["where", cmd],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def check_photorec_available():
    """Check if photorec is installed."""
    return _command_available("photorec")


def check_testdisk_available():
    """Check if testdisk is installed."""
    return _command_available("testdisk")


_TYPE_ALIASES = {"JPG": "JPEG"}


def _normalize_type(name: str) -> str:
    """Normalize a file-type identifier for case-insensitive matching (TICK-923).

    Signature keys are uppercase (``"JPEG"``); CLI and UI callers may pass
    ``"jpg"``, ``"Jpg"`` or ``" jpeg "`` — all normalize to ``"JPEG"``.
    """
    normalized = name.upper().strip()
    return _TYPE_ALIASES.get(normalized, normalized)


# ---------------------------------------------------------------------------
# Trash recovery
# ---------------------------------------------------------------------------

def scan_trash(paths=None, progress_callback=None, cancel_token=None):
    """
    Scan system Trash/Recycle Bin for recoverable files.

    Args:
        paths: Optional list of mount points to scan for .Trash-* directories.
        progress_callback: Progress reporting callback.
        cancel_token: threading.Event for cancellation.

    Returns:
        list of dicts: {path, original_path, deletion_date, size, filename, info_file}
    """
    system = platform.system()
    results = []

    if system == "Linux" or system == "Darwin":
        results.extend(_scan_linux_trash(paths, progress_callback, cancel_token))
    elif system == "Windows":
        results.extend(_scan_windows_trash(progress_callback, cancel_token))

    return results


def _scan_linux_trash(extra_paths=None, progress_callback=None, cancel_token=None):
    """Scan Linux/macOS trash locations."""
    results = []
    home = Path.home()

    # Standard XDG trash
    trash_dirs = [
        home / ".local" / "share" / "Trash",
    ]

    # macOS trash
    if platform.system() == "Darwin":
        trash_dirs.append(home / ".Trash")

    # External drive trash (.Trash-UID)
    uid = os.getuid() if hasattr(os, "getuid") else None
    if extra_paths:
        for mount_path in extra_paths:
            if uid is not None:
                trash_dirs.append(Path(mount_path) / f".Trash-{uid}")

    # Also check common mount points
    for mount_base in ["/media", "/mnt", "/run/media"]:
        if os.path.isdir(mount_base):
            try:
                for user_dir in os.listdir(mount_base):
                    user_mount = os.path.join(mount_base, user_dir)
                    if os.path.isdir(user_mount):
                        for vol in os.listdir(user_mount):
                            vol_path = os.path.join(user_mount, vol)
                            if uid is not None:
                                trash_dirs.append(Path(vol_path) / f".Trash-{uid}")
            except (PermissionError, OSError):
                pass

    total = len(trash_dirs)

    for idx, trash_dir in enumerate(trash_dirs):
        if cancel_token and cancel_token.is_set():
            break

        if progress_callback:
            progress_callback(idx, total, f"Scanning: {trash_dir}")

        files_dir = trash_dir / "files"
        info_dir = trash_dir / "info"

        if not files_dir.is_dir():
            continue

        try:
            for fname in os.listdir(files_dir):
                if cancel_token and cancel_token.is_set():
                    break

                file_path = files_dir / fname
                info_file = info_dir / f"{fname}.trashinfo"

                # Parse .trashinfo for original path and deletion date
                original_path = None
                deletion_date = None

                if info_file.is_file():
                    try:
                        config = configparser.ConfigParser()
                        # F20: use acquire_file fallback for locked trashinfo
                        _read_ok = False
                        try:
                            with acquire_file(str(info_file), "r") as af:
                                config.read_file(af)
                                _read_ok = True
                        except Exception:
                            _read_ok = False
                        if not _read_ok:
                            config.read(str(info_file))
                        original_path = config.get("Trash Info", "Path", fallback=None)
                        date_str = config.get("Trash Info", "DeletionDate", fallback=None)
                        if date_str:
                            try:
                                deletion_date = datetime.fromisoformat(date_str).isoformat()
                            except (ValueError, TypeError):
                                deletion_date = date_str

                        # URL-decode the path
                        if original_path:
                            from urllib.parse import unquote
                            original_path = unquote(original_path)
                    except Exception:
                        pass

                try:
                    stat = os.stat(str(file_path))
                    size = stat.st_size
                except OSError:
                    size = 0

                results.append({
                    "path": str(file_path),
                    "filename": fname,
                    "original_path": original_path or f"(unknown — {fname})",
                    "deletion_date": deletion_date,
                    "size": size,
                    "is_dir": file_path.is_dir(),
                    "info_file": str(info_file) if info_file.is_file() else None,
                    "trash_location": str(trash_dir),
                    "formatted_size": format_size(size),
                })
        except (PermissionError, OSError) as exc:
            logger.debug(f"Cannot scan trash at {trash_dir}: {exc}")

    if progress_callback:
        progress_callback(total, total, "Trash scan complete")

    return results


class TrashScanUnsupported(RuntimeError):
    """Raised when trash scanning is not implemented for the current platform."""


def _scan_windows_trash(progress_callback=None, cancel_token=None):
    """Scan Windows Recycle Bin (not yet implemented).

    Rather than silently returning an empty list — which the UI would render as
    a successful scan that found nothing — this signals that the capability is
    unavailable so the caller can tell the user, instead of implying the
    Recycle Bin is empty.
    """
    logger.warning("Windows Recycle Bin recovery is not implemented (requires pywin32 / $Recycle.Bin $I parsing).")
    raise TrashScanUnsupported(
        "Recycle Bin recovery is not supported on Windows yet. "
        "Install pywin32 or use a dedicated recovery tool."
    )


_SYSTEM_DIRS = {
    "/bin", "/sbin", "/lib", "/lib64", "/usr", "/etc", "/proc",
    "/sys", "/dev", "/boot", "/root", "/var", "/run",
}


def _is_safe_restore_path(original_path):
    """Validate a restore destination from .trashinfo metadata.

    Returns (is_safe: bool, reason: str). A path is unsafe when it contains
    traversal components (``..``), targets a system directory, or is not
    absolute.
    """
    if not original_path or original_path.startswith("(unknown"):
        return False, "Original path unknown"

    p = Path(original_path)
    if not p.is_absolute():
        return False, "Path is not absolute"

    parts = p.parts
    if ".." in parts:
        return False, "Path contains traversal component (..)"

    for sys_dir in _SYSTEM_DIRS:
        if str(p).startswith(sys_dir + "/") or str(p) == sys_dir:
            return False, f"Path targets system directory ({sys_dir})"

    return True, "ok"


def restore_from_trash(items, progress_callback=None, cancel_token=None, restore_root=None):
    """
    Restore files from trash to their original locations.

    Args:
        items: list of trash item dicts from scan_trash().
        progress_callback: Progress reporting callback.
        cancel_token: threading.Event for cancellation.
        restore_root: Directory to confine restores into when the original
            path fails validation (absolute-path check, traversal, or a
            system directory). Defaults to ``~/Recovered``.

    Returns:
        dict with restored, failed, and cancelled counts.
    """
    restored = []
    failed = []
    total = len(items)

    for idx, item in enumerate(items):
        if cancel_token and cancel_token.is_set():
            return {"restored": restored, "failed": failed, "cancelled": True}

        if progress_callback:
            progress_callback(idx, total, f"Restoring: {item['filename']}")

        trash_path = item["path"]
        original_path = item.get("original_path", "")

        if not original_path or original_path.startswith("(unknown"):
            failed.append({"item": item, "error": "Original path unknown"})
            continue

        if not os.path.exists(trash_path):
            failed.append({"item": item, "error": "Trash file not found"})
            continue

        is_safe, reason = _is_safe_restore_path(original_path)

        if not is_safe:
            safe_root = restore_root or os.path.join(os.path.expanduser("~"), "Recovered")
            safe_name = Path(original_path).name
            dest = os.path.join(safe_root, safe_name)
            logger.warning(
                f"Unsafe restore path ({reason}): {original_path} — "
                f"redirecting to {dest}"
            )
        else:
            dest = original_path

        try:
            parent = os.path.dirname(dest)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)

            if os.path.exists(dest):
                base, ext = os.path.splitext(dest)
                counter = 1
                while os.path.exists(dest):
                    dest = f"{base}_restored_{counter}{ext}"
                    counter += 1

            shutil.move(trash_path, dest)

            info_file = item.get("info_file")
            if info_file and os.path.exists(info_file):
                os.remove(info_file)

            restored.append({"item": item, "restored_to": dest})
        except (OSError, shutil.Error) as exc:
            failed.append({"item": item, "error": str(exc)})

    if progress_callback:
        progress_callback(total, total, "Restore complete")

    return {"restored": restored, "failed": failed, "cancelled": False}


# ---------------------------------------------------------------------------
# Raw disk carving (built-in Python implementation)
# ---------------------------------------------------------------------------

def carve_files_from_image(
    image_path,
    output_dir,
    file_types=None,
    max_files=1000,
    progress_callback=None,
    cancel_token=None,
):
    """
    Carve files from a raw disk image or device by scanning for magic byte headers.

    Uses mmap + sliding-window scan with parallel chunk workers for ~8× speedup
    on large images. Fixes F6 sector-alignment miss by scanning every byte offset
    (not just sector boundaries).

    Args:
        image_path: Path to a raw disk image file (.dd, .img, .raw).
        output_dir: Directory to write carved files.
        file_types: Optional list of format names to carve (e.g., ["JPEG", "PDF"]).
                    None means all supported types.
        max_files: Maximum number of files to carve.
        progress_callback: Progress callback.
        cancel_token: Cancellation event.

    Returns:
        dict with carved files list, stats, and errors.
    """
    if not os.path.exists(image_path):
        return {"error": f"Image not found: {image_path}", "carved": []}

    os.makedirs(output_dir, exist_ok=True)

    # Select signatures to search for — type identifiers are matched
    # case-insensitively (TICK-923 / P1.9: CLI lowercases, UI uses mixed case).
    if file_types is not None:
        normalized_types = {_normalize_type(t) for t in file_types}
        sigs = {k: v for k, v in SIGNATURES.items() if k in normalized_types}
    else:
        sigs = dict(SIGNATURES)

    if not sigs:
        return {"carved": [], "total_carved": 0, "errors": [], "image_path": image_path, "output_dir": output_dir, "cancelled": False}

    # Compute overlap = max(header_len + footer_len) across all signatures
    max_overlap = 0
    for sig in sigs.values():
        h_len = len(sig["header"])
        f_len = len(sig["footer"]) if sig["footer"] else 0
        max_overlap = max(max_overlap, h_len + f_len)
    # Ensure at least 512 bytes overlap for sector-boundary safety
    max_overlap = max(max_overlap, 512)

    window_size = 64 * 1024 * 1024  # 64 MiB
    max_workers = _get_max_workers()

    carved = []
    errors = []
    carved_offsets = set()  # dedup by offset across overlapping windows
    carved_ranges = []  # list of (start, end) for already-carved regions
    file_counter = [0]  # mutable counter shared under lock
    counter_lock = threading.Lock()

    try:
        file_size = os.path.getsize(image_path)
    except OSError as exc:
        return {"error": f"Cannot stat image: {exc}", "carved": []}

    if file_size == 0:
        return {"carved": [], "total_carved": 0, "errors": [], "image_path": image_path, "output_dir": output_dir, "cancelled": False}

    def _carve_one(mm: mmap.mmap, offset: int, fmt_name: str, sig: dict, img_size: int) -> dict | None:
        """Carve a single file from mmap at the given offset. Returns result dict or None."""
        if cancel_token and cancel_token.is_set():
            return None
        max_size = sig["max_size"]
        footer = sig.get("footer")
        ext = sig["extensions"][0] if sig["extensions"] else ""

        end = min(offset + max_size, img_size)
        file_data = mm[offset:end]

        if footer:
            footer_pos = file_data.find(footer, len(sig["header"]))
            if footer_pos != -1:
                file_data = file_data[:footer_pos + len(footer)]
        else:
            file_data = file_data[:max_size]

        if not file_data:
            return None

        with counter_lock:
            if file_counter[0] >= max_files:
                return None
            file_counter[0] += 1
            idx = file_counter[0]

        out_name = f"carved_{idx:06d}_{fmt_name}{ext}"
        out_path = os.path.join(output_dir, out_name)

        try:
            # Write to temp then atomic move — no partial files on cancel
            fd, tmp_path = tempfile.mkstemp(dir=output_dir, suffix=".tmp")
            try:
                os.write(fd, file_data)
                os.close(fd)
                fd = -1
                os.replace(tmp_path, out_path)
            except OSError:
                if fd >= 0:
                    os.close(fd)
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as exc:
            return {"error": f"Write error at offset {offset}: {exc}"}

        return {
            "path": out_path,
            "format": fmt_name,
            "size": len(file_data),
            "offset": offset,
            "formatted_size": format_size(len(file_data)),
        }

    def _scan_window(mm: mmap.mmap, win_start: int, win_end: int, img_size: int) -> list[dict]:
        """Scan one window for all signature headers. Returns list of carve results."""
        results: list[dict] = []
        if cancel_token and cancel_token.is_set():
            return results

        chunk = mm[win_start:win_end]
        # Scan for each signature
        for fmt_name, sig in sigs.items():
            if cancel_token and cancel_token.is_set():
                break
            header = sig["header"]
            search_from = 0
            while search_from < len(chunk):
                if cancel_token and cancel_token.is_set():
                    break
                pos = chunk.find(header, search_from)
                if pos == -1:
                    break
                abs_offset = win_start + pos

                # Check if this offset falls inside an already-carved range
                skip = False
                with counter_lock:
                    if abs_offset in carved_offsets:
                        skip = True
                    else:
                        for r_start, r_end in carved_ranges:
                            if r_start <= abs_offset < r_end:
                                skip = True
                                search_from = r_end - win_start
                                break
                if skip:
                    if search_from <= pos:
                        search_from = pos + 1
                    continue

                with counter_lock:
                    carved_offsets.add(abs_offset)

                # Secondary check for RIFF-based formats
                if header == b"\x52\x49\x46\x46" and len(chunk) > pos + 12:
                    subtype = chunk[pos + 8:pos + 12]
                    from .file_signatures import RIFF_SUBTYPES
                    if RIFF_SUBTYPES.get(subtype) != fmt_name:
                        search_from = pos + 1
                        continue

                result = _carve_one(mm, abs_offset, fmt_name, sig, img_size)
                if result is not None:
                    results.append(result)
                    # Track carved range and skip past it
                    carve_end = abs_offset + result["size"]
                    with counter_lock:
                        carved_ranges.append((abs_offset, carve_end))
                    search_from = carve_end - win_start
                else:
                    search_from = pos + 1
        return results

    try:
        # F20: use acquire_file for locked images (VSS on Windows)
        with acquire_file(image_path, "rb") as f:
            try:
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            except (OSError, ValueError) as exc:
                return {"error": f"mmap failed: {exc}", "carved": []}

            try:
                # Build window ranges with overlap
                windows = []
                pos = 0
                while pos < file_size:
                    win_end = min(pos + window_size, file_size)
                    windows.append((pos, win_end))
                    if win_end >= file_size:
                        break
                    pos += window_size - max_overlap

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(_scan_window, mm, ws, we, file_size): (ws, we)
                        for ws, we in windows
                    }

                    for fut in as_completed(futures):
                        if cancel_token and cancel_token.is_set():
                            for _ff in futures:
                                _ff.cancel()
                            break

                        ws, _ = futures[fut]
                        if progress_callback:
                            progress_callback(ws, file_size, f"Scanning offset {format_size(ws)}")

                        try:
                            window_results = fut.result()
                            for r in window_results:
                                if "error" in r:
                                    errors.append(r["error"])
                                else:
                                    carved.append(r)
                        except Exception as exc:
                            errors.append(f"Worker error at offset {ws}: {exc}")

            finally:
                mm.close()

    except (OSError, IOError) as exc:
        errors.append(f"Read error: {exc}")

    if progress_callback:
        progress_callback(file_size, file_size, "Carving complete")

    return {
        "carved": carved,
        "total_carved": len(carved),
        "errors": errors,
        "image_path": image_path,
        "output_dir": output_dir,
        "cancelled": cancel_token.is_set() if cancel_token else False,
    }


# ---------------------------------------------------------------------------
# External tool wrappers (photorec)
# ---------------------------------------------------------------------------

def run_photorec(
    device_or_image,
    output_dir,
    file_types=None,
    progress_callback=None,
    cancel_token=None,
):
    """
    Run PhotoRec for professional-grade file recovery.

    Requires photorec to be installed (part of testdisk package).

    Args:
        device_or_image: Path to device or disk image.
        output_dir: Output directory for recovered files.
        file_types: Optional list of file families to recover.
        progress_callback: Progress callback.
        cancel_token: Cancellation event.

    Returns:
        dict with recovery results.
    """
    if not check_photorec_available():
        return {"error": "photorec is not installed. Install testdisk: sudo apt install testdisk"}

    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        "photorec",
        "/d", output_dir,
        "/cmd", device_or_image,
        "search",
    ]

    # TICK-923 / P1.9: honor the selected file types via PhotoRec's fileopt
    # command (family codes are lowercase — e.g. "JPEG" -> "jpg").
    if file_types:
        families = ",".join(_normalize_type(t).lower() for t in file_types)
        cmd = [
            "photorec",
            "/d", output_dir,
            "/cmd", device_or_image,
            f"fileopt,ext,keep,{families}",
            "search",
        ]

    if progress_callback:
        progress_callback(0, 0, "Starting PhotoRec recovery...")

    # Cancellable Popen with polling (was subprocess.run timeout=3600 uncancellable)
    import time as _time

    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Poll for completion or cancel
        start = _time.monotonic()
        while proc.poll() is None:
            if cancel_token is not None and cancel_token.is_set():
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=2)
                except Exception:
                    pass
                return {"cancelled": True, "message": "PhotoRec cancelled", "output_dir": output_dir}
            if _time.monotonic() - start > 3600:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                return {"error": "PhotoRec timed out after 1 hour.", "output_dir": output_dir}
            _time.sleep(0.2)
            if progress_callback:
                try:
                    progress_callback(0, 0, "PhotoRec running...")
                except Exception:
                    pass
        # Process finished
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except Exception:
            stdout, stderr = "", ""
        # Count recovered files (check cancel first)
        if cancel_token is not None and cancel_token.is_set():
            return {"cancelled": True, "message": "PhotoRec cancelled", "output_dir": output_dir}
        recovered_files = []
        if os.path.isdir(output_dir):
            for root, dirs, files in os.walk(output_dir):
                if cancel_token is not None and cancel_token.is_set():
                    return {"cancelled": True, "message": "PhotoRec cancelled", "output_dir": output_dir}
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        fsize = os.path.getsize(fpath)
                    except OSError:
                        fsize = 0
                    recovered_files.append({
                        "path": fpath,
                        "filename": fname,
                        "size": fsize,
                    })

        return {
            "recovered": recovered_files,
            "total_recovered": len(recovered_files),
            "output_dir": output_dir,
            "returncode": proc.returncode if proc else -1,
            "stdout": (stdout or "")[:5000],
            "stderr": (stderr or "")[:2000],
        }
    except OSError as exc:
        return {"error": f"Failed to run photorec: {exc}"}
    finally:
        if proc is not None:
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Quick file undelete (filesystem-level)
# ---------------------------------------------------------------------------

def scan_recently_deleted(directory, max_age_hours=24, progress_callback=None, cancel_token=None):
    """
    Find files that may be recently deleted by scanning for orphaned inodes
    or recently modified directories. This is a best-effort heuristic.

    For actual deleted file recovery, use scan_trash() or carve_files_from_image().

    Args:
        directory: Directory to scan.
        max_age_hours: Only consider changes within this many hours.
        progress_callback: Progress callback.
        cancel_token: Cancellation event.

    Returns:
        list of recently modified directories (potential deletion sites).
    """
    results = []
    cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)

    count = 0
    for root, dirs, files in os.walk(directory):
        if cancel_token and cancel_token.is_set():
            break

        count += 1
        if progress_callback and count % 100 == 0:
            progress_callback(count, 0, f"Scanning: {root}")

        try:
            stat = os.stat(root)
            # Directory was recently modified (file added or removed)
            if stat.st_mtime >= cutoff and not files:
                results.append({
                    "path": root,
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "note": "Empty directory — may indicate recent file deletion",
                })
        except OSError:
            pass

    return results
