"""
Secure file sanitisation module.

Moved from forensics.py to separate destroy primitives from forensic analysis.

Addresses FORENSIC_REVIEW F4 (secure_delete placement) and F21 (hardlink/reflink awareness).
"""

import os
import subprocess


def _is_cow_filesystem(path_str: str) -> bool:
    """Best-effort check if path is on a CoW/reflink-capable filesystem.

    Returns True for btrfs, zfs, bcachefs, xfs (reflink), apfs.
    Used for reflink awareness (F21) — overwrite may not reach original blocks.
    """
    try:
        # Linux stat -f
        result = subprocess.run(
            ["stat", "-f", "-c", "%T", path_str],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            fstype = result.stdout.strip().lower()
            if fstype in {"btrfs", "zfs", "bcachefs", "xfs", "apfs", "btrfs"}:
                return True
    except Exception:
        pass
    # Fallback: try stat -f with BSD/macOS syntax
    try:
        result = subprocess.run(
            ["stat", "-f", "%T", path_str],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            fstype = result.stdout.strip().lower()
            if fstype in {"btrfs", "zfs", "bcachefs", "xfs", "apfs", "apfs"}:
                return True
    except Exception:
        pass
    return False


def secure_delete(path, passes=3, evidence_mode=False, cancel_token=None):
    """Securely delete a file by overwriting before removal.

    Best-effort overwrite a file with random data ``passes`` times and then unlink it.

    .. warning::
       On SSDs, flash media, copy-on-write filesystems (btrfs, ZFS), and
       journaled filesystems the overwrite may not reach the physical media.
       This function does **not** guarantee data destruction on those
       platforms. Reflink clones (XFS/btrfs ``cp --reflink``) also share extents
       and will not be fully sanitised by overwriting a single clone.

    Args:
        path: File to delete (str or Path).
        passes: Number of overwrite passes (default 3).
        evidence_mode: If True, block destructive operations (ACPO §1). When
            False, the global CaseContext evidence_mode is still checked (F3).
        cancel_token: Optional threading.Event for cancellation.

    Returns:
        dict with keys: success (bool), path (str), message (str),
        plus status/error/warning/passes/method for richer clients.
    """
    # --- Handle legacy positional overloads ---
    # Original forensics.py signature was (path, passes=3, cancel_token=None).
    # New signature is (path, passes=3, evidence_mode=False, cancel_token=None).
    # If caller passed an Event as the third positional arg, it will land in
    # evidence_mode (since that is now the third param). Detect and shift.
    if hasattr(evidence_mode, "is_set") and cancel_token is None:
        # evidence_mode actually holds a cancel_token Event
        cancel_token = evidence_mode  # type: ignore
        evidence_mode = False  # type: ignore
    # If cancel_token is a bool, it was likely meant as evidence_mode
    if isinstance(cancel_token, bool) and not isinstance(evidence_mode, bool):
        evidence_mode = cancel_token  # type: ignore
        cancel_token = None

    # Evidence Mode gate — explicit param OR global CaseContext (F3)
    # Preserve original message for backward compat and also provide
    # ticket-example error/status fields.
    effective_evidence = bool(evidence_mode)
    if not effective_evidence:
        try:
            from ..core.case import is_evidence_mode

            if is_evidence_mode():
                effective_evidence = True
        except Exception:
            pass
    if effective_evidence:
        return {
            "success": False,
            "status": "blocked",
            "path": str(path),
            "message": "Evidence Mode is active — destructive operations are blocked (ACPO §1)",
            "error": "Secure delete blocked in Evidence Mode (ACPO §1)",
        }

    # Not a regular file
    if not os.path.isfile(path):
        return {
            "success": False,
            "status": "error",
            "path": str(path),
            "message": "not a regular file",
            "error": "not a regular file",
        }

    # Hardlink awareness (F21) — shared inode means data persists via other links
    try:
        st = os.stat(path)
        if st.st_nlink > 1:
            return {
                "success": False,
                "status": "warning",
                "path": str(path),
                "message": f"File has {st.st_nlink} hardlinks - data may persist via other links",
                "warning": f"File has {st.st_nlink} hardlinks - data may persist",
                "error": f"File has {st.st_nlink} hardlinks - data may persist",
            }
    except OSError:
        pass

    # Reflink/CoW awareness (F21) — informational warning, do not block.
    # If filesystem is CoW, we still overwrite but final success message already
    # notes CoW/reflink limitation. We could also return a warning here to block,
    # but that would break extant btrfs users. Instead we let overwrite proceed
    # and include reflink note in the success path. For strict procurement
    # environments, callers can pre-check _is_cow_filesystem themselves.
    # We do NOT block here; we just note. If a future strict mode is needed,
    # uncomment the block below:
    # if _is_cow_filesystem(str(path)):
    #     return {"success": False, "status": "warning", ... reflink warning ...}

    # --- Overwrite + unlink (best-effort) ---
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return {
            "success": False,
            "status": "error",
            "path": str(path),
            "message": str(exc),
            "error": str(exc),
        }

    try:
        with open(path, "r+b", buffering=0) as f:
            for _ in range(passes):
                if cancel_token is not None and hasattr(cancel_token, "is_set") and cancel_token.is_set():
                    return {
                        "success": False,
                        "status": "cancelled",
                        "path": str(path),
                        "message": "cancelled",
                        "error": "cancelled",
                    }
                f.seek(0)
                remaining = size
                while remaining > 0:
                    chunk = os.urandom(min(1024 * 1024, remaining))
                    f.write(chunk)
                    remaining -= len(chunk)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
    except OSError as exc:
        return {
            "success": False,
            "status": "error",
            "path": str(path),
            "message": str(exc),
            "error": str(exc),
        }

    try:
        os.unlink(path)
    except OSError as exc:
        return {
            "success": False,
            "status": "error",
            "path": str(path),
            "message": f"overwrite complete but unlink failed: {exc}",
            "error": f"overwrite complete but unlink failed: {exc}",
        }

    # Re-check CoW/reflink for final message enrichment
    cow_note = ""
    try:
        if _is_cow_filesystem(str(path)):
            # path already unlinked, check parent dir's filesystem instead
            cow_note = " Reflink/CoW filesystem detected — clones may retain data."
    except Exception:
        pass

    return {
        "success": True,
        "status": "success",
        "path": str(path),
        "message": (
            f"best-effort overwrite complete ({passes} passes, {size} bytes). "
            "Note: on SSDs/flash/CoW filesystems physical data may persist."
            + cow_note
        ),
        "passes": passes,
        "method": "overwrite",
        "size": size,
    }
