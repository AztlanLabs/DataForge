"""
System performance monitoring and analysis module.

Provides CPU, RAM, disk, process, and startup item insights
for system optimization and hardware upgrade guidance.
"""
import os
import platform
import subprocess
import time
from pathlib import Path
from datetime import datetime

from ..core.logger import logger

# psutil is an optional dependency — degrade gracefully
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False


def check_availability():
    """Check if psutil is available for performance monitoring."""
    return HAS_PSUTIL


# ---------------------------------------------------------------------------
# System information
# ---------------------------------------------------------------------------

def get_system_info():
    """
    Gather comprehensive system information.

    Returns:
        dict with cpu, memory, disk, os, and network sections.
    """
    info = {
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "hostname": platform.node(),
        },
        "cpu": _get_cpu_info(),
        "memory": _get_memory_info(),
        "disks": _get_disk_info(),
        "network": _get_network_info(),
        "uptime": _get_uptime(),
    }
    return info


def _get_cpu_info():
    """Get CPU details."""
    info = {
        "physical_cores": None,
        "logical_cores": None,
        "max_frequency_mhz": None,
        "current_frequency_mhz": None,
        "usage_percent": None,
        "per_core_percent": [],
        "architecture": platform.machine(),
    }

    if not HAS_PSUTIL:
        return info

    info["physical_cores"] = psutil.cpu_count(logical=False)
    info["logical_cores"] = psutil.cpu_count(logical=True)
    info["usage_percent"] = psutil.cpu_percent(interval=0.5)
    info["per_core_percent"] = psutil.cpu_percent(interval=0.1, percpu=True)

    try:
        freq = psutil.cpu_freq()
        if freq:
            info["max_frequency_mhz"] = round(freq.max, 1)
            info["current_frequency_mhz"] = round(freq.current, 1)
    except Exception:
        pass

    # Try to get CPU model name
    try:
        if platform.system() == "Linux":
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        info["model"] = line.split(":")[1].strip()
                        break
        elif platform.system() == "Darwin":
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                info["model"] = result.stdout.strip()
    except Exception:
        pass

    return info


def _get_memory_info():
    """Get RAM details."""
    info = {
        "total_bytes": None,
        "available_bytes": None,
        "used_bytes": None,
        "percent_used": None,
        "swap_total_bytes": None,
        "swap_used_bytes": None,
        "swap_percent": None,
    }

    if not HAS_PSUTIL:
        return info

    mem = psutil.virtual_memory()
    info["total_bytes"] = mem.total
    info["available_bytes"] = mem.available
    info["used_bytes"] = mem.used
    info["percent_used"] = mem.percent

    swap = psutil.swap_memory()
    info["swap_total_bytes"] = swap.total
    info["swap_used_bytes"] = swap.used
    info["swap_percent"] = swap.percent

    return info


def _get_disk_info():
    """Get disk partition details."""
    disks = []

    if not HAS_PSUTIL:
        return disks

    for partition in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            disks.append({
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "fstype": partition.fstype,
                "opts": partition.opts,
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "percent_used": usage.percent,
            })
        except (PermissionError, OSError):
            disks.append({
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "fstype": partition.fstype,
                "opts": partition.opts,
                "error": "Access denied",
            })

    return disks


def _get_network_info():
    """Get network interface details."""
    interfaces = []

    if not HAS_PSUTIL:
        return interfaces

    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        for iface, addr_list in addrs.items():
            iface_info = {
                "name": iface,
                "is_up": stats.get(iface, None) and stats[iface].isup,
                "speed_mbps": stats.get(iface, None) and stats[iface].speed,
                "addresses": [],
            }

            for addr in addr_list:
                iface_info["addresses"].append({
                    "family": str(addr.family),
                    "address": addr.address,
                    "netmask": addr.netmask,
                })

            interfaces.append(iface_info)
    except Exception:
        pass

    return interfaces


def _get_uptime():
    """Get system uptime."""
    if not HAS_PSUTIL:
        return None

    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)

    return {
        "boot_time": datetime.fromtimestamp(boot_time).isoformat(),
        "uptime_seconds": int(uptime_seconds),
        "uptime_formatted": f"{days}d {hours}h {minutes}m",
    }


# ---------------------------------------------------------------------------
# Process monitoring
# ---------------------------------------------------------------------------

def get_running_processes(sort_by="memory", limit=50):
    """
    Get list of running processes sorted by resource usage.

    Args:
        sort_by: "memory", "cpu", "name", or "pid"
        limit: Maximum number of processes to return.

    Returns:
        list of dicts with process information.
    """
    if not HAS_PSUTIL:
        return []

    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent',
                                      'memory_info', 'status', 'create_time']):
        try:
            info = proc.info
            processes.append({
                "pid": info["pid"],
                "name": info["name"],
                "username": info.get("username", ""),
                "cpu_percent": info.get("cpu_percent", 0.0) or 0.0,
                "memory_percent": round(info.get("memory_percent", 0.0) or 0.0, 2),
                "memory_bytes": info.get("memory_info", None) and info["memory_info"].rss or 0,
                "status": info.get("status", ""),
                "created": info.get("create_time", 0),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    sort_keys = {
        "memory": lambda p: p["memory_percent"],
        "cpu": lambda p: p["cpu_percent"],
        "name": lambda p: p["name"].lower(),
        "pid": lambda p: p["pid"],
    }
    key_fn = sort_keys.get(sort_by, sort_keys["memory"])
    reverse = sort_by in ("memory", "cpu")
    processes.sort(key=key_fn, reverse=reverse)

    return processes[:limit]


def get_resource_heavy_processes(threshold_cpu=5.0, threshold_mem=5.0):
    """
    Get processes using significant CPU or memory.

    Args:
        threshold_cpu: Minimum CPU% to include.
        threshold_mem: Minimum memory% to include.

    Returns:
        list of dicts with process information.
    """
    if not HAS_PSUTIL:
        return []

    # First call to establish CPU measurement baseline
    for proc in psutil.process_iter(['cpu_percent']):
        pass
    time.sleep(0.3)

    heavy = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'memory_info']):
        try:
            info = proc.info
            cpu = info.get("cpu_percent", 0) or 0
            mem = info.get("memory_percent", 0) or 0

            if cpu >= threshold_cpu or mem >= threshold_mem:
                heavy.append({
                    "pid": info["pid"],
                    "name": info["name"],
                    "cpu_percent": cpu,
                    "memory_percent": round(mem, 2),
                    "memory_bytes": info.get("memory_info", None) and info["memory_info"].rss or 0,
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    heavy.sort(key=lambda p: p["cpu_percent"] + p["memory_percent"], reverse=True)
    return heavy


# ---------------------------------------------------------------------------
# Startup items (Linux-focused)
# ---------------------------------------------------------------------------

def get_startup_items():
    """
    Detect autostart / startup items.

    Returns:
        list of dicts with startup entry information.
    """
    items = []

    system = platform.system()

    if system == "Linux":
        # XDG autostart directories
        autostart_dirs = [
            str(Path.home() / ".config" / "autostart"),
            "/etc/xdg/autostart",
        ]

        for adir in autostart_dirs:
            if not os.path.isdir(adir):
                continue

            for fname in os.listdir(adir):
                if not fname.endswith(".desktop"):
                    continue

                fpath = os.path.join(adir, fname)
                entry = _parse_desktop_entry(fpath)
                if entry:
                    entry["source"] = adir
                    entry["scope"] = "user" if ".config" in adir else "system"
                    items.append(entry)

        # systemd user services
        try:
            result = subprocess.run(
                ["systemctl", "--user", "list-unit-files", "--type=service", "--no-pager", "--plain"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n")[1:]:
                    parts = line.split()
                    if len(parts) >= 2:
                        items.append({
                            "name": parts[0],
                            "type": "systemd-user",
                            "enabled": parts[1] == "enabled",
                            "scope": "user",
                            "source": "systemd",
                        })
        except Exception:
            pass

    return items


def _parse_desktop_entry(path):
    """Parse a .desktop file for autostart info."""
    entry = {
        "name": os.path.basename(path),
        "type": "desktop",
        "path": path,
        "enabled": True,
    }

    try:
        with open(path, "r", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("Name="):
                    entry["name"] = line[5:]
                elif line.startswith("Exec="):
                    entry["command"] = line[5:]
                elif line.startswith("Comment="):
                    entry["description"] = line[8:]
                elif line.startswith("Hidden=true"):
                    entry["enabled"] = False
                elif line.startswith("X-GNOME-Autostart-enabled=false"):
                    entry["enabled"] = False
    except (OSError, IOError):
        return None

    return entry


# ---------------------------------------------------------------------------
# Disk health (S.M.A.R.T.)
# ---------------------------------------------------------------------------

def get_disk_health():
    """
    Get S.M.A.R.T. disk health data (requires smartctl).

    Returns:
        dict with per-device health information.
    """
    health = {}

    if not _command_available("smartctl"):
        return {"error": "smartctl not installed. Install smartmontools for disk health data."}

    if not HAS_PSUTIL:
        return {"error": "psutil required for disk enumeration."}

    for partition in psutil.disk_partitions(all=False):
        device = partition.device
        # Strip partition number to get base device
        base_device = device.rstrip("0123456789")
        if base_device in health:
            continue

        try:
            result = subprocess.run(
                ["smartctl", "-H", "-A", base_device],
                capture_output=True, text=True, timeout=15,
            )
            output = result.stdout

            device_health = {
                "device": base_device,
                "healthy": "PASSED" in output,
                "raw_output": output[:2000],  # Cap output size
            }

            # Parse temperature if present
            for line in output.split("\n"):
                if "Temperature_Celsius" in line or "Airflow_Temperature" in line:
                    parts = line.split()
                    if parts:
                        try:
                            device_health["temperature_c"] = int(parts[-1])
                        except (ValueError, IndexError):
                            pass

            health[base_device] = device_health
        except (subprocess.TimeoutExpired, OSError, PermissionError) as exc:
            health[base_device] = {"device": base_device, "error": str(exc)}

    return health


# ---------------------------------------------------------------------------
# Utility
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


def get_live_resource_snapshot():
    """
    Get a point-in-time snapshot of CPU, RAM, and disk usage.

    Returns:
        dict with current resource utilization.
    """
    if not HAS_PSUTIL:
        return {"error": "psutil required"}

    return {
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "cpu_per_core": psutil.cpu_percent(interval=0.1, percpu=True),
        "memory": {
            "total": psutil.virtual_memory().total,
            "used": psutil.virtual_memory().used,
            "percent": psutil.virtual_memory().percent,
        },
        "swap": {
            "total": psutil.swap_memory().total,
            "used": psutil.swap_memory().used,
            "percent": psutil.swap_memory().percent,
        },
        "timestamp": datetime.now().isoformat(),
    }
