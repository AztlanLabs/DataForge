"""
Cross-device storage management module.

Enumerates internal drives, external drives, USBs, and mounted volumes
to extend optimization and scanning across all connected storage.
"""
import os
import platform
import subprocess
from pathlib import Path

from ..core.logger import logger
from ..core.scanner import scan_directory
from ..core.utils import format_size

# psutil is optional
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False


# ---------------------------------------------------------------------------
# Device type classification
# ---------------------------------------------------------------------------

DEVICE_TYPE_INTERNAL = "Internal Drive"
DEVICE_TYPE_EXTERNAL = "External Drive"
DEVICE_TYPE_USB = "USB Drive"
DEVICE_TYPE_NETWORK = "Network Share"
DEVICE_TYPE_OPTICAL = "Optical Drive"
DEVICE_TYPE_RAMDISK = "RAM Disk"
DEVICE_TYPE_UNKNOWN = "Unknown"

_REMOVABLE_FSTYPES = {"vfat", "exfat", "ntfs", "fat32", "fat16", "msdos", "udf"}
_NETWORK_FSTYPES = {"nfs", "nfs4", "cifs", "smbfs", "fuse.sshfs", "9p"}
_OPTICAL_FSTYPES = {"iso9660", "udf"}
_RAM_FSTYPES = {"tmpfs", "ramfs", "devtmpfs"}


def _classify_device(partition):
    """Classify a partition as internal, external, USB, network, etc."""
    fstype = getattr(partition, "fstype", "").lower()
    device = getattr(partition, "device", "").lower()
    mountpoint = getattr(partition, "mountpoint", "")
    opts = getattr(partition, "opts", "").lower()

    if fstype in _NETWORK_FSTYPES:
        return DEVICE_TYPE_NETWORK
    if fstype in _OPTICAL_FSTYPES:
        return DEVICE_TYPE_OPTICAL
    if fstype in _RAM_FSTYPES:
        return DEVICE_TYPE_RAMDISK

    # Check for USB/removable indicators
    if "usb" in device or "removable" in opts:
        return DEVICE_TYPE_USB

    # On Linux, check sysfs for removable flag
    if platform.system() == "Linux":
        base_dev = os.path.basename(device.rstrip("0123456789"))
        removable_path = f"/sys/block/{base_dev}/removable"
        try:
            with open(removable_path, "r") as f:
                if f.read().strip() == "1":
                    return DEVICE_TYPE_USB
        except (OSError, IOError):
            pass

    # Check common external mount patterns
    if mountpoint:
        mp = mountpoint.lower()
        if any(marker in mp for marker in ["/media/", "/mnt/", "/run/media/"]):
            return DEVICE_TYPE_EXTERNAL
        if mp.startswith("/") and mp.count("/") == 1:
            return DEVICE_TYPE_INTERNAL

    # Default to internal for standard-looking devices
    if device.startswith("/dev/sd") or device.startswith("/dev/nvme") or device.startswith("/dev/hd"):
        return DEVICE_TYPE_INTERNAL

    return DEVICE_TYPE_UNKNOWN


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_storage_devices():
    """
    Enumerate all connected storage devices with usage statistics.

    Returns:
        list of dicts with device information.
    """
    if not HAS_PSUTIL:
        return _list_devices_fallback()

    devices = []
    seen_devices = set()

    for partition in psutil.disk_partitions(all=False):
        device_key = partition.device
        if device_key in seen_devices:
            continue
        seen_devices.add(device_key)

        device_info = {
            "device": partition.device,
            "mountpoint": partition.mountpoint,
            "fstype": partition.fstype,
            "opts": partition.opts,
            "type": _classify_device(partition),
        }

        try:
            usage = psutil.disk_usage(partition.mountpoint)
            device_info.update({
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "percent_used": usage.percent,
                "formatted_total": format_size(usage.total),
                "formatted_used": format_size(usage.used),
                "formatted_free": format_size(usage.free),
            })
        except (PermissionError, OSError) as exc:
            device_info["error"] = str(exc)

        devices.append(device_info)

    return devices


def _list_devices_fallback():
    """Fallback device listing without psutil using lsblk."""
    devices = []

    if platform.system() != "Linux":
        return devices

    try:
        result = subprocess.run(
            ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,RM"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            for block in data.get("blockdevices", []):
                if block.get("type") == "disk":
                    for child in block.get("children", []):
                        if child.get("mountpoint"):
                            devices.append({
                                "device": f"/dev/{child['name']}",
                                "mountpoint": child["mountpoint"],
                                "fstype": child.get("fstype", ""),
                                "type": DEVICE_TYPE_USB if child.get("rm") else DEVICE_TYPE_INTERNAL,
                                "formatted_total": child.get("size", ""),
                            })
    except Exception as exc:
        logger.debug(f"lsblk fallback failed: {exc}")

    return devices


def get_device_info(mount_point):
    """
    Get detailed information about a specific storage device.

    Args:
        mount_point: The mount point path of the device.

    Returns:
        dict with device details or None if not found.
    """
    if not os.path.isdir(mount_point):
        return None

    info = {
        "mountpoint": mount_point,
        "exists": True,
        "accessible": os.access(mount_point, os.R_OK),
    }

    if HAS_PSUTIL:
        try:
            usage = psutil.disk_usage(mount_point)
            info.update({
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "percent_used": usage.percent,
                "formatted_total": format_size(usage.total),
                "formatted_used": format_size(usage.used),
                "formatted_free": format_size(usage.free),
            })
        except (PermissionError, OSError) as exc:
            info["error"] = str(exc)

        # Find matching partition
        for partition in psutil.disk_partitions(all=False):
            if partition.mountpoint == mount_point:
                info["device"] = partition.device
                info["fstype"] = partition.fstype
                info["opts"] = partition.opts
                info["type"] = _classify_device(partition)
                break
    else:
        # Fallback using shutil
        import shutil
        try:
            total, used, free = shutil.disk_usage(mount_point)
            info.update({
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
                "percent_used": round((used / total) * 100, 1) if total else 0,
                "formatted_total": format_size(total),
                "formatted_used": format_size(used),
                "formatted_free": format_size(free),
            })
        except OSError as exc:
            info["error"] = str(exc)

    return info


def scan_device(mount_point, recursive=True, max_depth=-1, cancel_token=None, progress_callback=None):
    """
    Scan a storage device using the standard scanner.

    Args:
        mount_point: Root path of the device to scan.
        recursive: Whether to scan recursively.
        max_depth: Maximum directory depth (-1 = unlimited).
        cancel_token: threading.Event for cancellation.
        progress_callback: Progress reporting callback.

    Returns:
        list of FileEntry objects.
    """
    entries = []
    count = 0

    for entry in scan_directory(mount_point, recursive=recursive, max_depth=max_depth, cancel_token=cancel_token):
        entries.append(entry)
        count += 1

        if progress_callback and count % 100 == 0:
            progress_callback(count, 0, f"Scanned {count} files on {mount_point}")

    if progress_callback:
        progress_callback(count, count, f"Scan complete: {count} files")

    return entries
