"""
Hardware diagnostics module.

Provides detailed system hardware reporting for CPU, RAM, storage,
GPU, network, and motherboard with upgrade recommendations.
"""
import platform
import subprocess
import json

from ..core.utils import format_size

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False


def _run_cmd(cmd, timeout=10):
    """Run a shell command and return stdout or None."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _command_available(cmd):
    try:
        which = "which" if platform.system() != "Windows" else "where"
        result = subprocess.run([which, cmd], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Hardware report
# ---------------------------------------------------------------------------

def get_hardware_report(progress_callback=None, cancel_token=None):
    """
    Generate a comprehensive hardware diagnostic report.

    Returns:
        dict with cpu, ram, storage, gpu, network, motherboard sections.
    """
    report = {
        "system": _get_system_overview(),
        "cpu": _get_cpu_details(),
        "ram": _get_ram_details(),
        "storage": _get_storage_details(),
        "gpu": _get_gpu_details(),
        "network": _get_network_details(),
        "motherboard": _get_motherboard_details(),
    }

    if progress_callback:
        progress_callback(1, 1, "Hardware scan complete")

    return report


def _get_system_overview():
    """Basic system identification."""
    info = {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "hostname": platform.node(),
        "python": platform.python_version(),
    }

    # Linux: get distro info
    if platform.system() == "Linux":
        distro = _run_cmd(["lsb_release", "-d", "-s"])
        if distro:
            info["distro"] = distro
        else:
            # Try /etc/os-release
            try:
                with open("/etc/os-release", "r") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            info["distro"] = line.split("=", 1)[1].strip().strip('"')
                            break
            except OSError:
                pass

    return info


def _get_cpu_details():
    """Detailed CPU information."""
    cpu = {
        "architecture": platform.machine(),
        "processor": platform.processor(),
    }

    if HAS_PSUTIL:
        cpu["physical_cores"] = psutil.cpu_count(logical=False)
        cpu["logical_cores"] = psutil.cpu_count(logical=True)
        try:
            freq = psutil.cpu_freq()
            if freq:
                cpu["frequency_mhz"] = round(freq.current, 1)
                cpu["max_frequency_mhz"] = round(freq.max, 1)
                cpu["min_frequency_mhz"] = round(freq.min, 1)
        except Exception:
            pass

    # Linux: parse /proc/cpuinfo
    if platform.system() == "Linux":
        try:
            with open("/proc/cpuinfo", "r") as f:
                content = f.read()
                for line in content.split("\n"):
                    if "model name" in line:
                        cpu["model"] = line.split(":")[1].strip()
                    elif "cache size" in line:
                        cpu["cache"] = line.split(":")[1].strip()
                    elif "cpu MHz" in line and "current_mhz" not in cpu:
                        cpu["current_mhz"] = line.split(":")[1].strip()
                    elif "flags" in line and "flags" not in cpu:
                        flags = line.split(":")[1].strip().split()
                        cpu["virtualization"] = "vmx" in flags or "svm" in flags
                        cpu["aes"] = "aes" in flags
                        cpu["avx"] = "avx" in flags
                        cpu["avx2"] = "avx2" in flags
        except OSError:
            pass

    return cpu


def _get_ram_details():
    """Detailed RAM information."""
    ram = {}

    if HAS_PSUTIL:
        mem = psutil.virtual_memory()
        ram["total_bytes"] = mem.total
        ram["formatted_total"] = format_size(mem.total)
        ram["available_bytes"] = mem.available
        ram["used_bytes"] = mem.used
        ram["percent_used"] = mem.percent

        swap = psutil.swap_memory()
        ram["swap_total_bytes"] = swap.total
        ram["swap_formatted_total"] = format_size(swap.total)

    # Linux: try dmidecode for RAM type/speed (requires root)
    if platform.system() == "Linux" and _command_available("dmidecode"):
        dmidecode = _run_cmd(["sudo", "dmidecode", "-t", "memory"], timeout=5)
        if dmidecode:
            ram["modules"] = []
            current_module = {}
            for line in dmidecode.split("\n"):
                line = line.strip()
                if line.startswith("Size:") and "No Module" not in line:
                    current_module["size"] = line.split(":", 1)[1].strip()
                elif line.startswith("Type:"):
                    current_module["type"] = line.split(":", 1)[1].strip()
                elif line.startswith("Speed:"):
                    current_module["speed"] = line.split(":", 1)[1].strip()
                elif line.startswith("Manufacturer:"):
                    current_module["manufacturer"] = line.split(":", 1)[1].strip()
                elif line == "" and current_module.get("size"):
                    ram["modules"].append(current_module)
                    current_module = {}

    return ram


def _get_storage_details():
    """Detailed storage information."""
    storage = {"partitions": [], "devices": []}

    if HAS_PSUTIL:
        for partition in psutil.disk_partitions(all=False):
            part_info = {
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "fstype": partition.fstype,
            }
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                part_info.update({
                    "total_bytes": usage.total,
                    "formatted_total": format_size(usage.total),
                    "used_bytes": usage.used,
                    "free_bytes": usage.free,
                    "percent_used": usage.percent,
                })
            except (PermissionError, OSError):
                pass
            storage["partitions"].append(part_info)

    # Linux: lsblk for physical device info
    if platform.system() == "Linux":
        lsblk = _run_cmd(["lsblk", "-J", "-o", "NAME,SIZE,TYPE,ROTA,MODEL,TRAN"])
        if lsblk:
            try:
                data = json.loads(lsblk)
                for device in data.get("blockdevices", []):
                    if device.get("type") == "disk":
                        storage["devices"].append({
                            "name": f"/dev/{device['name']}",
                            "size": device.get("size", ""),
                            "model": device.get("model", "").strip() if device.get("model") else "",
                            "rotational": device.get("rota") == "1" or device.get("rota") is True,
                            "type": "HDD" if (device.get("rota") == "1" or device.get("rota") is True) else "SSD",
                            "transport": device.get("tran", ""),
                        })
            except (json.JSONDecodeError, KeyError):
                pass

    return storage


def _get_gpu_details():
    """GPU information."""
    gpus = []

    # Linux: lspci
    if platform.system() == "Linux":
        lspci = _run_cmd(["lspci"])
        if lspci:
            for line in lspci.split("\n"):
                if "VGA" in line or "3D" in line or "Display" in line:
                    gpus.append({
                        "description": line.split(":", 2)[-1].strip() if ":" in line else line,
                        "source": "lspci",
                    })

        # Try nvidia-smi for NVIDIA GPUs
        nvidia = _run_cmd(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])
        if nvidia:
            for line in nvidia.split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    gpus.append({
                        "name": parts[0],
                        "vram": parts[1],
                        "driver": parts[2],
                        "source": "nvidia-smi",
                    })

    return gpus


def _get_network_details():
    """Network interface details."""
    interfaces = []

    if HAS_PSUTIL:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        for name, addr_list in addrs.items():
            iface = {
                "name": name,
                "is_up": stats.get(name) and stats[name].isup,
                "speed_mbps": stats.get(name) and stats[name].speed,
                "mtu": stats.get(name) and stats[name].mtu,
                "addresses": [],
            }
            for addr in addr_list:
                iface["addresses"].append({
                    "family": str(addr.family),
                    "address": addr.address,
                })
            interfaces.append(iface)

    return interfaces


def _get_motherboard_details():
    """Motherboard/BIOS information (Linux only, may require root)."""
    board = {}

    if platform.system() == "Linux":
        # Try reading DMI data from sysfs (doesn't require root)
        dmi_paths = {
            "board_name": "/sys/devices/virtual/dmi/id/board_name",
            "board_vendor": "/sys/devices/virtual/dmi/id/board_vendor",
            "board_version": "/sys/devices/virtual/dmi/id/board_version",
            "bios_vendor": "/sys/devices/virtual/dmi/id/bios_vendor",
            "bios_version": "/sys/devices/virtual/dmi/id/bios_version",
            "bios_date": "/sys/devices/virtual/dmi/id/bios_date",
        }

        for key, path in dmi_paths.items():
            try:
                with open(path, "r") as f:
                    value = f.read().strip()
                    if value:
                        board[key] = value
            except (OSError, IOError):
                pass

    return board


# ---------------------------------------------------------------------------
# Upgrade recommendations
# ---------------------------------------------------------------------------

def get_upgrade_recommendations(report):
    """
    Generate hardware upgrade recommendations based on the report.

    Args:
        report: dict from get_hardware_report().

    Returns:
        list of recommendation strings.
    """
    recommendations = []

    # RAM
    ram = report.get("ram", {})
    total_ram = ram.get("total_bytes", 0)
    if total_ram and total_ram < 8 * 1024 ** 3:
        recommendations.append(
            f"⚠️ RAM: {format_size(total_ram)} detected. Consider upgrading to at least 16 GB "
            "for smooth multitasking and modern applications."
        )
    elif total_ram and total_ram < 16 * 1024 ** 3:
        recommendations.append(
            f"💡 RAM: {format_size(total_ram)} detected. 32 GB would improve performance for "
            "heavy workloads like video editing or virtual machines."
        )

    ram_usage = ram.get("percent_used", 0)
    if ram_usage > 80:
        recommendations.append(
            f"🔴 RAM usage is at {ram_usage}%. Adding more RAM would significantly improve performance."
        )

    # Storage
    storage = report.get("storage", {})
    for part in storage.get("partitions", []):
        percent = part.get("percent_used", 0)
        if percent > 90:
            recommendations.append(
                f"🔴 Disk {part.get('device', '')} ({part.get('mountpoint', '')}) is {percent}% full. "
                "Consider adding storage or running cleanup."
            )
        elif percent > 75:
            recommendations.append(
                f"⚠️ Disk {part.get('device', '')} is {percent}% full. Monitor usage."
            )

    # SSD check
    for device in storage.get("devices", []):
        if device.get("rotational"):
            recommendations.append(
                f"💡 Storage: {device.get('name', '')} ({device.get('model', '')}) is an HDD. "
                "Upgrading to an SSD would dramatically improve system responsiveness."
            )

    # CPU
    cpu = report.get("cpu", {})
    cores = cpu.get("physical_cores", 0)
    if cores and cores < 4:
        recommendations.append(
            f"⚠️ CPU has only {cores} physical cores. A 6+ core processor would improve "
            "multi-threaded performance."
        )

    return recommendations


def export_hardware_report(report, path, fmt="json"):
    """
    Export hardware report to file.

    Args:
        report: dict from get_hardware_report().
        path: Output file path.
        fmt: "json" or "html".

    Returns:
        str: output path.
    """
    if fmt == "json":
        with open(path, "w") as f:
            json.dump(report, f, indent=2, default=str)
    elif fmt == "html":
        html = _report_to_html(report)
        with open(path, "w") as f:
            f.write(html)

    return path


def _report_to_html(report):
    """Convert hardware report to HTML."""
    sections = []

    sections.append("<html><head><title>Hardware Report</title>")
    sections.append("<style>body{font-family:sans-serif;max-width:900px;margin:auto;padding:20px}")
    sections.append("table{border-collapse:collapse;width:100%;margin:10px 0}")
    sections.append("th,td{border:1px solid #ddd;padding:8px;text-align:left}")
    sections.append("th{background:#f5f5f5}h2{color:#333;border-bottom:2px solid #eee;padding-bottom:5px}")
    sections.append("</style></head><body>")
    sections.append("<h1>Hardware Diagnostic Report</h1>")

    for section_name, section_data in report.items():
        sections.append(f"<h2>{section_name.replace('_', ' ').title()}</h2>")
        if isinstance(section_data, dict):
            sections.append("<table>")
            for key, value in section_data.items():
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, indent=2, default=str)
                sections.append(f"<tr><th>{key}</th><td><pre>{value}</pre></td></tr>")
            sections.append("</table>")
        elif isinstance(section_data, list):
            sections.append("<ul>")
            for item in section_data:
                sections.append(f"<li>{json.dumps(item, default=str) if isinstance(item, dict) else item}</li>")
            sections.append("</ul>")

    sections.append("</body></html>")
    return "\n".join(sections)
