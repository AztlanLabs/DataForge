"""
Digital Forensics module.

Automated ingestion pipeline for disk images, cryptographic hash calculation,
OS artifact parsing, keyword searching, and forensic report generation.
"""
import os
import json
import math
import hashlib
import binascii
import subprocess
import platform
import struct
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from ..core.config import config
from ..core.logger import logger
from ..core.scanner import scan_directory
from ..core.hasher import get_file_hash, BLOCK_SIZE
from ..core.utils import format_size


# ---------------------------------------------------------------------------
# Cryptographic hash calculation (batch)
# ---------------------------------------------------------------------------

def _hash_entry_worker(path, algorithms, cancel_token):
    # Always seed the requested algo keys so downstream `entry[algo]` lookups
    # are safe even when hashing fails (missing file, unsupported algo, etc.).
    entry = {"path": path, "filename": os.path.basename(path), "size": 0}
    for algo in algorithms:
        entry[algo] = ""
    try:
        entry["size"] = os.path.getsize(path)
        entry["formatted_size"] = format_size(entry["size"])
        for algo in algorithms:
            entry[algo] = get_file_hash(path, algo=algo, cancel_token=cancel_token)
    except (OSError, ValueError) as exc:
        entry["error"] = str(exc)
    return entry


def calculate_hashes(
    paths,
    algorithms=None,
    progress_callback=None,
    cancel_token=None,
):
    """
    Calculate cryptographic hashes for a list of files, in parallel across
    config["max_thread_workers"] threads (same pool-size setting duplicate
    scanning uses — this is the same "hash many files" work, just for a
    forensic hash manifest instead of duplicate grouping).

    Args:
        paths: list of file paths.
        algorithms: list of hash algorithms (default: ["md5", "sha256"]).
        progress_callback: Progress callback.
        cancel_token: Cancellation event.

    Returns:
        list of dicts with path, filename, size, and hash values, in the
        same order as `paths`.
    """
    if algorithms is None:
        algorithms = ["md5", "sha256"]

    paths = list(paths)
    total = len(paths)
    max_workers = max(1, config.get("max_thread_workers", 4))
    results = [None] * total
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_hash_entry_worker, path, algorithms, cancel_token): idx
            for idx, path in enumerate(paths)
        }
        for future in as_completed(futures):
            idx = futures[future]
            if cancel_token and cancel_token.is_set():
                executor.shutdown(wait=False, cancel_futures=True)
                break
            completed += 1
            if progress_callback:
                progress_callback(completed, total, f"Hashing: {os.path.basename(paths[idx])}")
            try:
                results[idx] = future.result()
            except Exception as exc:
                results[idx] = {"path": paths[idx], "filename": os.path.basename(paths[idx]), "size": 0, "error": str(exc)}

    if progress_callback:
        progress_callback(total, total, "Hashing complete")

    return [r for r in results if r is not None]


def verify_hash(path, expected_hash, algorithm="sha256"):
    """
    Verify a file against a known hash.

    Returns:
        dict with match status and computed hash.
    """
    computed = get_file_hash(path, algo=algorithm)
    return {
        "path": path,
        "algorithm": algorithm,
        "expected": expected_hash,
        "computed": computed,
        "match": computed.lower() == expected_hash.lower(),
    }


# ---------------------------------------------------------------------------
# OS Artifact parsing
# ---------------------------------------------------------------------------

def parse_os_artifacts(root_path, progress_callback=None, cancel_token=None):
    """
    Parse operating system artifacts for forensic analysis.

    Args:
        root_path: Root of mounted filesystem or live system path.
        progress_callback: Progress callback.
        cancel_token: Cancellation event.

    Returns:
        dict with categorized artifact data.
    """
    artifacts = {
        "users": [],
        "auth_logs": [],
        "shell_history": [],
        "cron_jobs": [],
        "installed_packages": [],
        "network_config": [],
        "recent_logins": [],
        "system_services": [],
    }

    system = platform.system()
    total_steps = 8

    # --- Step 1: Users ---
    if progress_callback:
        progress_callback(0, total_steps, "Parsing user accounts...")

    passwd_path = os.path.join(root_path, "etc", "passwd")
    if os.path.isfile(passwd_path):
        try:
            with open(passwd_path, "r") as f:
                for line in f:
                    parts = line.strip().split(":")
                    if len(parts) >= 7:
                        artifacts["users"].append({
                            "username": parts[0],
                            "uid": parts[2],
                            "gid": parts[3],
                            "info": parts[4],
                            "home": parts[5],
                            "shell": parts[6],
                        })
        except (OSError, IOError) as exc:
            logger.debug(f"Cannot read {passwd_path}: {exc}")

    # --- Step 2: Auth logs ---
    if progress_callback:
        progress_callback(1, total_steps, "Parsing auth logs...")

    auth_paths = [
        os.path.join(root_path, "var", "log", "auth.log"),
        os.path.join(root_path, "var", "log", "secure"),
    ]
    for auth_path in auth_paths:
        if os.path.isfile(auth_path):
            try:
                with open(auth_path, "r", errors="replace") as f:
                    lines = f.readlines()
                    # Last 200 lines
                    for line in lines[-200:]:
                        line = line.strip()
                        if any(kw in line.lower() for kw in ["failed", "accepted", "session opened", "sudo"]):
                            artifacts["auth_logs"].append(line)
            except (OSError, IOError):
                pass

    # --- Step 3: Shell history ---
    if progress_callback:
        progress_callback(2, total_steps, "Parsing shell history...")

    for user_entry in artifacts["users"]:
        home = user_entry.get("home", "")
        if not home.startswith("/"):
            home = os.path.join(root_path, home.lstrip("/"))

        history_files = [
            os.path.join(home, ".bash_history"),
            os.path.join(home, ".zsh_history"),
            os.path.join(home, ".fish_history"),
        ]
        for hist_file in history_files:
            if os.path.isfile(hist_file):
                try:
                    with open(hist_file, "r", errors="replace") as f:
                        lines = f.readlines()
                        artifacts["shell_history"].append({
                            "user": user_entry["username"],
                            "file": hist_file,
                            "line_count": len(lines),
                            "recent": [l.strip() for l in lines[-50:]],
                        })
                except (OSError, IOError):
                    pass

    # --- Step 4: Cron jobs ---
    if progress_callback:
        progress_callback(3, total_steps, "Parsing cron jobs...")

    cron_dirs = [
        os.path.join(root_path, "etc", "crontab"),
        os.path.join(root_path, "var", "spool", "cron"),
        os.path.join(root_path, "etc", "cron.d"),
    ]
    for cron_path in cron_dirs:
        if os.path.isfile(cron_path):
            try:
                with open(cron_path, "r", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            artifacts["cron_jobs"].append({
                                "source": cron_path,
                                "entry": line,
                            })
            except (OSError, IOError):
                pass
        elif os.path.isdir(cron_path):
            try:
                for fname in os.listdir(cron_path):
                    fpath = os.path.join(cron_path, fname)
                    if os.path.isfile(fpath):
                        with open(fpath, "r", errors="replace") as f:
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith("#"):
                                    artifacts["cron_jobs"].append({
                                        "source": fpath,
                                        "entry": line,
                                    })
            except (OSError, IOError):
                pass

    # --- Step 5: Installed packages ---
    if progress_callback:
        progress_callback(4, total_steps, "Parsing installed packages...")

    dpkg_status = os.path.join(root_path, "var", "lib", "dpkg", "status")
    if os.path.isfile(dpkg_status):
        try:
            with open(dpkg_status, "r", errors="replace") as f:
                pkg = {}
                for line in f:
                    if line.startswith("Package:"):
                        pkg["name"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Version:"):
                        pkg["version"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Status:"):
                        pkg["status"] = line.split(":", 1)[1].strip()
                    elif line.strip() == "" and pkg.get("name"):
                        artifacts["installed_packages"].append(pkg)
                        pkg = {}
        except (OSError, IOError):
            pass

    # --- Step 6: Network config ---
    if progress_callback:
        progress_callback(5, total_steps, "Parsing network configuration...")

    net_paths = [
        os.path.join(root_path, "etc", "hostname"),
        os.path.join(root_path, "etc", "hosts"),
        os.path.join(root_path, "etc", "resolv.conf"),
    ]
    for net_path in net_paths:
        if os.path.isfile(net_path):
            try:
                with open(net_path, "r", errors="replace") as f:
                    artifacts["network_config"].append({
                        "file": net_path,
                        "content": f.read()[:5000],
                    })
            except (OSError, IOError):
                pass

    # --- Step 7: Recent logins ---
    if progress_callback:
        progress_callback(6, total_steps, "Parsing recent logins...")

    wtmp_path = os.path.join(root_path, "var", "log", "wtmp")
    if os.path.isfile(wtmp_path):
        last_output = _run_cmd(["last", "-f", wtmp_path, "-n", "50"])
        if last_output:
            artifacts["recent_logins"] = [
                line.strip() for line in last_output.split("\n")
                if line.strip() and "wtmp begins" not in line
            ]

    # --- Step 8: System services ---
    if progress_callback:
        progress_callback(7, total_steps, "Parsing system services...")

    systemd_path = os.path.join(root_path, "etc", "systemd", "system")
    if os.path.isdir(systemd_path):
        try:
            for fname in os.listdir(systemd_path):
                if fname.endswith(".service"):
                    artifacts["system_services"].append({
                        "name": fname,
                        "path": os.path.join(systemd_path, fname),
                    })
        except (OSError, IOError):
            pass

    if progress_callback:
        progress_callback(total_steps, total_steps, "Artifact parsing complete")

    return artifacts


def _run_cmd(cmd, timeout=10):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Keyword search (binary-safe)
# ---------------------------------------------------------------------------

def _keyword_search_worker(path, keywords, case_sensitive, cancel_token):
    if cancel_token and cancel_token.is_set():
        return None
    try:
        with open(path, "rb") as f:
            content = f.read(10 * 1024 * 1024)  # 10 MB limit

        search_content = content if case_sensitive else content.lower()
        matched = [kw for kw in keywords if kw.encode("utf-8", errors="ignore") in search_content]

        if matched:
            return {
                "path": path,
                "filename": os.path.basename(path),
                "size": os.path.getsize(path),
                "matched_keywords": matched,
                "match_count": len(matched),
            }
    except (OSError, IOError):
        pass
    return None


def keyword_search(
    paths,
    keywords,
    case_sensitive=False,
    progress_callback=None,
    cancel_token=None,
):
    """
    Search for keywords across files (binary-safe content search), in
    parallel across config["search_thread_workers"] threads — a separate
    budget from the hashing pool (config["max_thread_workers"]), since
    search and batch-hashing are different workloads a user may want to
    scale independently.

    Args:
        paths: list of file paths to search.
        keywords: list of keyword strings to find.
        case_sensitive: Whether search is case-sensitive.
        progress_callback: Progress callback.
        cancel_token: Cancellation event.

    Returns:
        list of dicts with file path, matched keywords, and context, in the
        same relative order as `paths`.
    """
    paths = list(paths)
    total = len(paths)
    if not case_sensitive:
        keywords = [kw.lower() for kw in keywords]

    max_workers = max(1, config.get("search_thread_workers", 4))
    results = [None] * total
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_keyword_search_worker, path, keywords, case_sensitive, cancel_token): idx
            for idx, path in enumerate(paths)
        }
        for future in as_completed(futures):
            idx = futures[future]
            if cancel_token and cancel_token.is_set():
                executor.shutdown(wait=False, cancel_futures=True)
                break
            completed += 1
            if progress_callback and completed % 50 == 0:
                progress_callback(completed, total, f"Searching: {os.path.basename(paths[idx])}")
            try:
                results[idx] = future.result()
            except Exception:
                results[idx] = None

    if progress_callback:
        progress_callback(total, total, "Keyword search complete")

    return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# Disk image ingestion
# ---------------------------------------------------------------------------

def ingest_disk_image(
    image_path,
    output_dir,
    options=None,
    progress_callback=None,
    cancel_token=None,
):
    """
    Automated forensic ingestion pipeline for disk images.

    Steps: enumerate files → extract metadata → hash files → index keywords

    Args:
        image_path: Path to disk image (or mounted directory for analysis).
        output_dir: Directory for output reports.
        options: dict of options (extract_metadata, hash_files, keyword_index, carve_deleted).
        progress_callback: Progress callback.
        cancel_token: Cancellation event.

    Returns:
        dict with ingestion results.
    """
    if options is None:
        options = {
            "extract_metadata": True,
            "hash_files": True,
            "keyword_index": False,
            "keywords": [],
        }

    os.makedirs(output_dir, exist_ok=True)

    results = {
        "image_path": image_path,
        "output_dir": output_dir,
        "file_count": 0,
        "hashes": [],
        "artifacts": {},
        "keyword_hits": [],
        "errors": [],
    }

    # For now, we treat the image_path as a mounted directory
    # (Full raw image mounting would require loop devices and root access)
    scan_path = image_path

    if not os.path.isdir(scan_path):
        results["errors"].append(f"Path is not a directory: {scan_path}")
        return results

    # Step 1: Enumerate files
    if progress_callback:
        progress_callback(0, 4, "Enumerating files...")

    file_paths = []
    for entry in scan_directory(scan_path, recursive=True, max_depth=-1, cancel_token=cancel_token):
        if not entry.is_dir:
            file_paths.append(entry.path)
    results["file_count"] = len(file_paths)

    # Step 2: Hash files
    if options.get("hash_files") and file_paths:
        if progress_callback:
            progress_callback(1, 4, "Calculating hashes...")

        hash_results = calculate_hashes(
            file_paths,
            algorithms=["md5", "sha256"],
            progress_callback=progress_callback,
            cancel_token=cancel_token,
        )
        results["hashes"] = hash_results

        # Save hash manifest
        hash_file = os.path.join(output_dir, "hash_manifest.json")
        with open(hash_file, "w") as f:
            json.dump(hash_results, f, indent=2, default=str)

    # Step 3: Parse OS artifacts
    if options.get("extract_metadata"):
        if progress_callback:
            progress_callback(2, 4, "Parsing OS artifacts...")

        artifacts = parse_os_artifacts(scan_path, cancel_token=cancel_token)
        results["artifacts"] = artifacts

        # Save artifacts
        artifact_file = os.path.join(output_dir, "os_artifacts.json")
        with open(artifact_file, "w") as f:
            json.dump(artifacts, f, indent=2, default=str)

    # Step 4: Keyword search
    if options.get("keyword_index") and options.get("keywords"):
        if progress_callback:
            progress_callback(3, 4, "Indexing keywords...")

        keyword_hits = keyword_search(
            file_paths, options["keywords"],
            progress_callback=progress_callback,
            cancel_token=cancel_token,
        )
        results["keyword_hits"] = keyword_hits

        # Save keyword results
        keyword_file = os.path.join(output_dir, "keyword_results.json")
        with open(keyword_file, "w") as f:
            json.dump(keyword_hits, f, indent=2, default=str)

    if progress_callback:
        progress_callback(4, 4, "Ingestion complete")

    return results


# ---------------------------------------------------------------------------
# Forensic report generation
# ---------------------------------------------------------------------------

def generate_forensic_report(results, output_path, fmt="json"):
    """
    Generate a forensic analysis report.

    Args:
        results: dict from ingest_disk_image() or other analysis.
        output_path: Output file path.
        fmt: "json" or "html".

    Returns:
        str: output path.
    """
    report = {
        "report_generated": datetime.now().isoformat(),
        "tool": "DataForge Forensics Module",
        "data": results,
    }

    if fmt == "json":
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
    elif fmt == "html":
        html = _forensic_report_html(report)
        with open(output_path, "w") as f:
            f.write(html)

    return output_path


def _forensic_report_html(report):
    """Generate HTML forensic report."""
    lines = [
        "<html><head><title>Forensic Analysis Report</title>",
        "<style>body{font-family:sans-serif;max-width:1000px;margin:auto;padding:20px}",
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:6px;text-align:left}",
        "th{background:#f5f5f5}h2{color:#333}pre{background:#f5f5f5;padding:10px;overflow-x:auto}",
        ".warning{color:#d97706}.danger{color:#dc2626}.success{color:#059669}",
        "</style></head><body>",
        "<h1>🔬 Forensic Analysis Report</h1>",
        f"<p>Generated: {report['report_generated']}</p>",
        f"<p>Tool: {report['tool']}</p>",
        "<hr>",
    ]

    data = report.get("data", {})

    if data.get("file_count"):
        lines.append(f"<h2>Files Analyzed: {data['file_count']}</h2>")

    if data.get("hashes"):
        lines.append(f"<h2>Hash Manifest ({len(data['hashes'])} files)</h2>")
        lines.append("<table><tr><th>File</th><th>Size</th><th>MD5</th><th>SHA-256</th></tr>")
        for h in data["hashes"][:100]:
            lines.append(
                f"<tr><td>{h.get('filename','')}</td><td>{h.get('formatted_size','')}</td>"
                f"<td><code>{h.get('md5','')[:16]}...</code></td>"
                f"<td><code>{h.get('sha256','')[:16]}...</code></td></tr>"
            )
        lines.append("</table>")

    if data.get("artifacts"):
        artifacts = data["artifacts"]
        if artifacts.get("users"):
            lines.append(f"<h2>User Accounts ({len(artifacts['users'])})</h2>")
            lines.append("<table><tr><th>Username</th><th>UID</th><th>Home</th><th>Shell</th></tr>")
            for user in artifacts["users"]:
                lines.append(
                    f"<tr><td>{user['username']}</td><td>{user['uid']}</td>"
                    f"<td>{user['home']}</td><td>{user['shell']}</td></tr>"
                )
            lines.append("</table>")

    lines.append("</body></html>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File type profiler (magic bytes)
# ---------------------------------------------------------------------------

def identify_file_by_signature(path):
    """Read first 64 bytes of a file and identify its type using the
    bundled file-signature database. Returns (format_name, description)
    or (None, "Unknown")."""
    from .file_signatures import identify_file_type, get_signature
    try:
        with open(path, "rb") as f:
            header = f.read(64)
    except OSError:
        return None, "Unreadable"
    fmt = identify_file_type(header)
    if fmt:
        sig = get_signature(fmt)
        desc = sig.get("description", fmt) if sig else fmt
        return fmt, desc
    return None, "Unknown"


def profile_directory_types(path, progress_callback=None, cancel_token=None):
    """Walk a directory and group every file by detected magic-byte type.
    Useful for triage on large evidence sets (e.g. 'how many PDFs vs EXEs
    do we actually have, regardless of extension')."""
    summary = Counter()
    rows = []
    total = 0
    for entry in scan_directory(path, recursive=True, max_depth=-1, cancel_token=cancel_token):
        if entry.is_dir:
            continue
        total += 1
        fmt, desc = identify_file_by_signature(entry.path)
        summary[fmt or "Unknown"] += 1
        rows.append({
            "path": entry.path,
            "filename": os.path.basename(entry.path),
            "extension": entry.extension,
            "size": entry.size,
            "format": fmt or "Unknown",
            "description": desc,
        })
        if progress_callback and total % 25 == 0:
            progress_callback(total, total, f"Classifying: {entry.name}")
    if progress_callback:
        progress_callback(total, total, f"Classified {total} files")
    return {"total": total, "by_format": dict(summary), "rows": rows}


# ---------------------------------------------------------------------------
# Shannon entropy analyzer (encrypted / packed / compressed detection)
# ---------------------------------------------------------------------------

def calculate_entropy(path, max_bytes=10 * 1024 * 1024):
    """Calculate Shannon entropy (0..8 bits) of the first up to `max_bytes`
    bytes of a file.

    Interpretation guide:
      - ~0 bit/byte   : constant data (e.g. zeros)
      - < 4.5         : likely plain text / structured data
      - 4.5 .. 7.5    : natural plaintext, archives, code
      - 7.5 .. 8.0    : high-entropy (encrypted, packed, compressed media)

    Returns: dict with entropy, sample_size, and a verdict label.
    """
    freq = [0] * 256
    try:
        with open(path, "rb") as f:
            chunk = f.read(max_bytes)
    except OSError as exc:
        return {"path": path, "error": str(exc)}
    if not chunk:
        return {
            "path": path,
            "entropy": 0.0,
            "sample_size": 0,
            "verdict": "empty",
        }
    for b in chunk:
        freq[b] += 1
    length = len(chunk)
    entropy = 0.0
    for count in freq:
        if not count:
            continue
        p = count / length
        entropy -= p * math.log2(p)
    if entropy >= 7.95:
        verdict = "very high (likely encrypted/packed)"
    elif entropy >= 7.5:
        verdict = "high (compressed/encrypted/media)"
    elif entropy >= 4.5:
        verdict = "moderate (natural text/archives/code)"
    else:
        verdict = "low (structured/sparse data)"
    return {
        "path": path,
        "filename": os.path.basename(path),
        "entropy": round(entropy, 4),
        "sample_size": length,
        "verdict": verdict,
    }


def calculate_entropy_batch(paths, max_bytes=1 * 1024 * 1024,
                            progress_callback=None, cancel_token=None):
    """Compute entropy for many files at once."""
    results = []
    total = len(paths)
    for idx, path in enumerate(paths, start=1):
        if cancel_token and cancel_token.is_set():
            break
        if progress_callback and idx % 10 == 0:
            progress_callback(idx, total, f"Entropy: {os.path.basename(path)}")
        results.append(calculate_entropy(path, max_bytes=max_bytes))
    if progress_callback:
        progress_callback(total, total, "Entropy analysis complete")
    return results


# ---------------------------------------------------------------------------
# Timeline builder (correlated file timestamps)
# ---------------------------------------------------------------------------

def build_timeline(path, sort_key="mtime", progress_callback=None, cancel_token=None):
    """Walk a path and return a timeline of every file keyed by timestamp.
    Useful for reconstructing who created/accessed what and when."""
    valid_keys = {"mtime", "atime", "ctime"}
    if sort_key not in valid_keys:
        sort_key = "mtime"

    events = []
    seen = 0
    for entry in scan_directory(path, recursive=True, max_depth=-1, cancel_token=cancel_token):
        if entry.is_dir:
            continue
        seen += 1
        try:
            stat = os.stat(entry.path)
            ts = getattr(stat, f"st_{sort_key}")
        except OSError:
            continue
        events.append({
            "path": entry.path,
            "filename": os.path.basename(entry.path),
            "extension": entry.extension,
            "size": entry.size,
            "timestamp_iso": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "timestamp_unix": ts,
            "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "atime": datetime.fromtimestamp(stat.st_atime, tz=timezone.utc).isoformat(),
            "ctime": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
            "owner_uid": getattr(stat, "st_uid", None),
            "owner_gid": getattr(stat, "st_gid", None),
            "mode": oct(getattr(stat, "st_mode", 0))[-7:],
        })
        if progress_callback and seen % 25 == 0:
            progress_callback(seen, seen, f"Building timeline: {entry.name}")
    events.sort(key=lambda ev: ev["timestamp_unix"], reverse=True)
    if progress_callback:
        progress_callback(len(events), len(events), "Timeline ready")
    return events


# ---------------------------------------------------------------------------
# Hex viewer (read-only dump with offsets)
# ---------------------------------------------------------------------------

def hex_dump(path, max_bytes=4096, offset=0):
    """Read up to `max_bytes` starting at `offset` and return a hex+offset
    dump in the classic xxd-style format.

    Returns dict with:
      data           : the raw bytes read
      ascii          : ascii preview string
      lines          : formatted "00000000: AA BB .. | ...|" rows
      truncated      : True when the file is larger than offset+max_bytes
    """
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return {"path": path, "error": str(exc)}

    truncated = False
    if offset > 0 and offset >= size:
        return {"path": path, "error": "offset beyond file size", "size": size}
    if (offset + max_bytes) < size:
        truncated = True
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read(max_bytes)
    except OSError as exc:
        return {"path": path, "error": str(exc)}

    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        # Pad hex groups to keep alignment
        hex_part = hex_part.ljust(48, " ")
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{offset + i:08X}:  {hex_part}  | {ascii_part}")
    return {
        "path": path,
        "filename": os.path.basename(path),
        "size": size,
        "offset": offset,
        "bytes_read": len(data),
        "truncated": truncated,
        "lines": lines,
        "ascii": "".join(chr(b) if 32 <= b < 127 else "." for b in data)[:512],
    }


# ---------------------------------------------------------------------------
# Steganography hint detector (LSB analysis for PNG / BMP)
# ---------------------------------------------------------------------------

def detect_steganography(path, threshold_ratio=0.05):
    """Very lightweight steganography *hint* detector for PNG/BMP images.

    A high ratio of near-identical color pairs whose lower bits alternate
    LSB patterns (i.e. bytes whose last 2 bits look like 01/10 of a pair)
    can hint that the LSB channel has been overwritten with hidden data.
    This does NOT extract anything; it is a triage hint only.
    """
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return {
            "supported": False,
            "reason": "Pillow not available",
            "path": path,
        }
    try:
        with Image.open(path) as im:
            if im.format not in {"PNG", "BMP", "TIFF"}:
                return {"supported": False, "reason": "format not analysed", "path": path}
            im = im.convert("RGB")
            width, height = im.size
            # Sampling the first up to 100k pixels is enough for a hint.
            sample_count = min(width * height, 100_000)
            pixels = list(im.getdata())[:sample_count]
        ones = 0
        lsb_swaps = 0
        prev = None
        for px in pixels:
            r, g, b = px[:3]
            ones += (r & 1) + (g & 1) + (b & 1)
            if prev is not None:
                if (r ^ prev[0]) in {1, 2} or (g ^ prev[1]) in {1, 2} or (b ^ prev[2]) in {1, 2}:
                    lsb_swaps += 1
            prev = px
        total_bits = sample_count * 3
        one_ratio = ones / total_bits if total_bits else 0
        swap_ratio = lsb_swaps / max(sample_count - 1, 1)
        suspicious = abs(one_ratio - 0.5) < threshold_ratio and swap_ratio > 0.4
        return {
            "supported": True,
            "path": path,
            "filename": os.path.basename(path),
            "dimensions": f"{width}x{height}",
            "pixels_sampled": sample_count,
            "lsb_one_ratio": round(one_ratio, 4),
            "lsb_swap_ratio": round(swap_ratio, 4),
            "suspicious": suspicious,
            "verdict": (
                "LSB channel looks natural"
                if not suspicious else
                "LSB channel has uniform distribution consistent with hidden data — investigate further"
            ),
        }
    except Exception as exc:
        return {"supported": False, "path": path, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Secure delete (overwrite + delete)
# ---------------------------------------------------------------------------

def secure_delete(path, passes=3, cancel_token=None):
    """Overwrite a file with random data `passes` times and then unlink it.
    Falls back to send2trash if available so it can be recovered if the
    user realises they got the wrong file."""
    if not os.path.isfile(path):
        return {"success": False, "message": "not a regular file"}
    size = os.path.getsize(path)
    try:
        with open(path, "r+b", buffering=0) as f:
            for _ in range(passes):
                if cancel_token and cancel_token.is_set():
                    return {"success": False, "message": "cancelled", "path": path}
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
        return {"success": False, "message": str(exc), "path": path}
    try:
        os.unlink(path)
    except OSError as exc:
        try:
            from send2trash import send2trash  # type: ignore
            send2trash(path)
        except Exception:
            return {"success": False, "message": str(exc), "path": path}
    return {"success": True, "path": path, "message": f"securely deleted ({passes} passes, {size} bytes)"}


# ---------------------------------------------------------------------------
# File state snapshot (integrity baseline)
# ---------------------------------------------------------------------------

def snapshot_file_state(paths, algorithms=None, progress_callback=None, cancel_token=None):
    """Build a fingerprinting snapshot of one or more paths: mtime, size,
    CRC32, MD5, SHA-256. Used for change detection and tamper alerting
    (a 'baseline' you can later re-verify)."""
    if algorithms is None:
        algorithms = ["md5", "sha256"]

    hashes = calculate_hashes(
        paths, algorithms=algorithms,
        progress_callback=progress_callback, cancel_token=cancel_token,
    )
    snapshot = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": algorithms,
        "entries": [],
    }
    for h in hashes:
        try:
            stat = os.stat(h.get("path", ""))
        except OSError:
            stat = None
        entry = {
            "path": h.get("path"),
            "filename": h.get("filename"),
            "size": h.get("size"),
            "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat() if stat else None,
            "crc32": _crc32(h.get("path")),
        }
        for algo in algorithms:
            entry[algo] = h.get(algo)
        snapshot["entries"].append(entry)
    return snapshot


def _crc32(path):
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            return f"{binascii.crc32(f.read()):08X}"
    except OSError:
        return None


def verify_file_state(snapshot, progress_callback=None, cancel_token=None):
    """Re-walk a snapshot produced by `snapshot_file_state` and verify every
    entry still has the same size/mtime/hash. Returns list of (entry, changed)
    pairs where `changed` is None when file matches, or a dict describing the
    discrepancy."""
    results = []
    for entry in snapshot.get("entries", []):
        path = entry.get("path")
        if not path or not os.path.exists(path):
            results.append((entry, {"missing": True}))
            continue
        try:
            stat = os.stat(path)
        except OSError:
            results.append((entry, {"missing": True}))
            continue
        diff = {}
        if "size" in entry and entry["size"] != stat.st_size:
            diff["size"] = (entry["size"], stat.st_size)
        algo = (snapshot.get("algorithm") or ["md5"])[0]
        computed = get_file_hash(path, algo=algo, cancel_token=cancel_token)
        if computed and entry.get(algo) and computed != entry[algo]:
            diff[algo] = (entry[algo], computed)
        results.append((entry, diff or None))
        if progress_callback:
            progress_callback(len(results), len(snapshot.get("entries", [])), os.path.basename(path))
    return results


# ---------------------------------------------------------------------------
# Browser/program history parsers — cross-platform console-style summaries
# ---------------------------------------------------------------------------

def collect_recent_documents(platform_system=None):
    """Return a list of recent documents opened locally for forensic
    triage. Windows/.local/share/recently-used.xbel and macOS'
    ~/Library/Application Support/ are heaviest; on Linux this looks at
    ~/.local/share/recently-used.xbel. Returns a list of dicts with the
    target URI/path and last-modified timestamp."""
    import xml.etree.ElementTree as ET

    platform_system = platform_system or platform.system()
    candidates = []
    home = os.path.expanduser("~")
    if platform_system == "Darwin":
        candidates.append(os.path.join(home, "Library", "Application Support", "com.apple.sharedfilelist.com.apple.LSSharedFileList.RecentDocuments.sfl3"))
    elif platform_system == "Windows":
        local_appdata = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        candidates.append(os.path.join(local_appdata, "Microsoft", "Windows", "Recent"))
    else:
        candidates.append(os.path.join(home, ".local", "share", "recently-used.xbel"))

    out = []
    for c in candidates:
        if os.path.isfile(c) and c.endswith(".xbel"):
            try:
                tree = ET.parse(c)
                root = tree.getroot()
                # xbel bookmarks
                ns = {"": "http://www.python.org/topics/xml/xbel/"}
                for bm in root.findall(".//bookmark"):
                    href = bm.attrib.get("href")
                    added = bm.attrib.get("added")
                    modified = bm.attrib.get("modified")
                    out.append({
                        "source": c,
                        "uri": href,
                        "added": added,
                        "modified": modified,
                    })
            except Exception as exc:
                logger.debug(f"recent-doc parse error for {c}: {exc}")
    return out
