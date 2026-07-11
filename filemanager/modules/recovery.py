"""
Advanced File Recovery module.

Supports trash recovery (recently deleted files), and raw disk carving
via external tools (photorec/testdisk) or built-in header/footer scanning.
"""
import os
import platform
import subprocess
import shutil
import configparser
from pathlib import Path
from datetime import datetime

from ..core.common import FileEntry
from ..core.scanner import build_file_entry
from ..core.logger import logger
from ..core.utils import format_size
from .file_signatures import SIGNATURES, identify_file_type


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


def restore_from_trash(items, progress_callback=None, cancel_token=None):
    """
    Restore files from trash to their original locations.

    Args:
        items: list of trash item dicts from scan_trash().
        progress_callback: Progress reporting callback.
        cancel_token: threading.Event for cancellation.

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

        try:
            # Create parent directory if needed
            parent = os.path.dirname(original_path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)

            # Handle collision
            dest = original_path
            if os.path.exists(dest):
                base, ext = os.path.splitext(dest)
                counter = 1
                while os.path.exists(dest):
                    dest = f"{base}_restored_{counter}{ext}"
                    counter += 1

            shutil.move(trash_path, dest)

            # Remove .trashinfo file
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

    # Select signatures to search for
    if file_types:
        sigs = {k: v for k, v in SIGNATURES.items() if k in file_types}
    else:
        sigs = dict(SIGNATURES)

    carved = []
    errors = []
    block_size = 512  # Standard sector size
    file_counter = 0

    try:
        file_size = os.path.getsize(image_path)
        total_blocks = file_size // block_size

        with open(image_path, "rb") as f:
            offset = 0
            block_num = 0

            while True:
                if cancel_token and cancel_token.is_set():
                    break

                if file_counter >= max_files:
                    break

                if progress_callback and block_num % 10000 == 0:
                    progress_callback(block_num, total_blocks, f"Scanning block {block_num}")

                # Read a block plus header-check buffer
                header_buf = f.read(block_size + 16)
                if not header_buf or len(header_buf) < 4:
                    break

                # Check for magic byte matches
                matched_format = identify_file_type(header_buf[:16])

                if matched_format and matched_format in sigs:
                    sig = sigs[matched_format]
                    max_size = sig["max_size"]
                    footer = sig.get("footer")
                    ext = sig["extensions"][0] if sig["extensions"] else ""

                    # Seek back and read the full potential file
                    f.seek(offset)
                    file_data = f.read(min(max_size, file_size - offset))

                    if footer:
                        # Find footer position
                        footer_pos = file_data.find(footer, len(sig["header"]))
                        if footer_pos != -1:
                            file_data = file_data[:footer_pos + len(footer)]
                    else:
                        # Without footer, use a heuristic size (look for next header or use max)
                        file_data = file_data[:max_size]

                    # Write carved file
                    file_counter += 1
                    out_name = f"carved_{file_counter:06d}_{matched_format}{ext}"
                    out_path = os.path.join(output_dir, out_name)

                    try:
                        with open(out_path, "wb") as out_f:
                            out_f.write(file_data)

                        carved.append({
                            "path": out_path,
                            "format": matched_format,
                            "size": len(file_data),
                            "offset": offset,
                            "formatted_size": format_size(len(file_data)),
                        })
                    except OSError as exc:
                        errors.append(f"Write error at offset {offset}: {exc}")

                    # Skip past this file
                    next_offset = offset + len(file_data)
                    f.seek(next_offset)
                    offset = next_offset
                    block_num = offset // block_size
                    continue

                # Move to next block
                offset += block_size
                f.seek(offset)
                block_num += 1

    except (OSError, IOError) as exc:
        errors.append(f"Read error: {exc}")

    if progress_callback:
        progress_callback(total_blocks, total_blocks, "Carving complete")

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

    if progress_callback:
        progress_callback(0, 0, "Starting PhotoRec recovery...")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour max
        )

        # Count recovered files
        recovered_files = []
        if os.path.isdir(output_dir):
            for root, dirs, files in os.walk(output_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    recovered_files.append({
                        "path": fpath,
                        "filename": fname,
                        "size": os.path.getsize(fpath),
                    })

        return {
            "recovered": recovered_files,
            "total_recovered": len(recovered_files),
            "output_dir": output_dir,
            "returncode": result.returncode,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
        }
    except subprocess.TimeoutExpired:
        return {"error": "PhotoRec timed out after 1 hour."}
    except OSError as exc:
        return {"error": f"Failed to run photorec: {exc}"}


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
    cutoff = datetime.now().timestamp() - (max_age_hours * 3600)

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
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "note": "Empty directory — may indicate recent file deletion",
                })
        except OSError:
            pass

    return results
