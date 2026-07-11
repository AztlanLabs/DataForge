"""
System Cleanup & Optimization module.

Identifies and manages junk files, temporary data, system caches,
redundant logs, and browser artifacts for storage reclamation.
"""
import os
import platform
import glob
import shutil
from pathlib import Path
from datetime import datetime, timedelta

from ..core.common import FileEntry
from ..core.scanner import build_file_entry, scan_directory
from ..core.logger import logger
from ..core.utils import format_size


# ---------------------------------------------------------------------------
# Junk-file category definitions (platform-aware)
# ---------------------------------------------------------------------------

def _home():
    return Path.home()


def _linux_junk_paths():
    h = _home()
    return {
        "System Temp": ["/tmp", "/var/tmp"],
        "User Cache": [str(h / ".cache")],
        "Thumbnails": [str(h / ".cache" / "thumbnails")],
        "Trash": [
            str(h / ".local" / "share" / "Trash" / "files"),
            str(h / ".local" / "share" / "Trash" / "info"),
        ],
        "Log Files": ["/var/log"],
        "Package Cache": [
            "/var/cache/apt/archives",            # Debian/Ubuntu
            "/var/cache/pacman/pkg",               # Arch
            str(h / ".cache" / "pip"),             # pip
        ],
        "Crash Reports": [
            "/var/crash",
            str(h / ".cache" / "crash"),
        ],
    }


def _windows_junk_paths():
    h = _home()
    temp = os.environ.get("TEMP", str(h / "AppData" / "Local" / "Temp"))
    local = os.environ.get("LOCALAPPDATA", str(h / "AppData" / "Local"))
    return {
        "System Temp": [temp, "C:\\Windows\\Temp"],
        "User Cache": [str(Path(local) / "Temp")],
        "Thumbnails": [str(Path(local) / "Microsoft" / "Windows" / "Explorer")],
        "Trash": [],  # Recycle bin handled separately on Windows
        "Log Files": ["C:\\Windows\\Logs"],
        "Package Cache": [],
        "Crash Reports": [str(Path(local) / "CrashDumps")],
    }


JUNK_EXTENSIONS = {
    ".tmp", ".temp", ".bak", ".old", ".swp", ".swo",
    ".log", ".dmp", ".crash", ".~", ".pyc", ".pyo",
    ".thumbs", ".ds_store", ".crdownload", ".part",
}

JUNK_FILENAMES = {
    "thumbs.db", "desktop.ini", ".ds_store",
    "debug.log", "error.log", "npm-debug.log",
    "yarn-error.log", "yarn-debug.log",
}


def _get_platform_junk_paths():
    system = platform.system()
    if system == "Linux":
        return _linux_junk_paths()
    elif system == "Windows":
        return _windows_junk_paths()
    elif system == "Darwin":
        # macOS: reuse Linux-like paths with additions
        paths = _linux_junk_paths()
        h = _home()
        paths["User Cache"] = [str(h / "Library" / "Caches")]
        paths["Log Files"].append(str(h / "Library" / "Logs"))
        paths["Trash"] = [str(h / ".Trash")]
        return paths
    return _linux_junk_paths()


# ---------------------------------------------------------------------------
# Browser artifact definitions
# ---------------------------------------------------------------------------

def _browser_profiles():
    """Return known browser profile paths per platform."""
    h = _home()
    system = platform.system()

    browsers = {}

    if system == "Linux":
        browsers["Google Chrome"] = {
            "base": str(h / ".config" / "google-chrome"),
            "cache": str(h / ".cache" / "google-chrome"),
        }
        browsers["Firefox"] = {
            "base": str(h / ".mozilla" / "firefox"),
            "cache": str(h / ".cache" / "mozilla" / "firefox"),
        }
        browsers["Brave"] = {
            "base": str(h / ".config" / "BraveSoftware" / "Brave-Browser"),
            "cache": str(h / ".cache" / "BraveSoftware" / "Brave-Browser"),
        }
        browsers["Microsoft Edge"] = {
            "base": str(h / ".config" / "microsoft-edge"),
            "cache": str(h / ".cache" / "microsoft-edge"),
        }
        browsers["Chromium"] = {
            "base": str(h / ".config" / "chromium"),
            "cache": str(h / ".cache" / "chromium"),
        }
    elif system == "Windows":
        local = os.environ.get("LOCALAPPDATA", str(h / "AppData" / "Local"))
        browsers["Google Chrome"] = {
            "base": str(Path(local) / "Google" / "Chrome" / "User Data"),
            "cache": str(Path(local) / "Google" / "Chrome" / "User Data"),
        }
        browsers["Firefox"] = {
            "base": str(h / "AppData" / "Roaming" / "Mozilla" / "Firefox"),
            "cache": str(Path(local) / "Mozilla" / "Firefox"),
        }
        browsers["Microsoft Edge"] = {
            "base": str(Path(local) / "Microsoft" / "Edge" / "User Data"),
            "cache": str(Path(local) / "Microsoft" / "Edge" / "User Data"),
        }
        browsers["Brave"] = {
            "base": str(Path(local) / "BraveSoftware" / "Brave-Browser" / "User Data"),
            "cache": str(Path(local) / "BraveSoftware" / "Brave-Browser" / "User Data"),
        }
    elif system == "Darwin":
        browsers["Google Chrome"] = {
            "base": str(h / "Library" / "Application Support" / "Google" / "Chrome"),
            "cache": str(h / "Library" / "Caches" / "Google" / "Chrome"),
        }
        browsers["Firefox"] = {
            "base": str(h / "Library" / "Application Support" / "Firefox"),
            "cache": str(h / "Library" / "Caches" / "Firefox"),
        }
        browsers["Brave"] = {
            "base": str(h / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser"),
            "cache": str(h / "Library" / "Caches" / "BraveSoftware" / "Brave-Browser"),
        }
        browsers["Safari"] = {
            "base": str(h / "Library" / "Safari"),
            "cache": str(h / "Library" / "Caches" / "com.apple.Safari"),
        }

    return browsers


BROWSER_ARTIFACT_PATTERNS = {
    "cookies": ["Cookies", "cookies.sqlite", "Cookies-journal"],
    "history": ["History", "places.sqlite", "History-journal"],
    "cache": ["Cache", "cache2", "Cache_Data", "Code Cache", "GPUCache"],
    "sessions": ["Sessions", "Session Storage", "sessionstore.jsonlz4"],
    "temp": ["*.tmp", "*.crdownload", "*.part"],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_junk_files(
    paths=None,
    categories=None,
    include_hidden=False,
    min_age_days=0,
    progress_callback=None,
    cancel_token=None,
):
    """
    Scan for junk/temporary files across system directories.

    Args:
        paths: Optional list of additional paths to scan.
        categories: Optional list of category names to include (None = all).
        include_hidden: Include hidden files in results.
        min_age_days: Only include files older than N days.
        progress_callback: Called with (current, total, step_name).
        cancel_token: threading.Event checked for cancellation.

    Returns:
        dict of {category_name: [FileEntry, ...]}
    """
    platform_paths = _get_platform_junk_paths()

    if categories:
        platform_paths = {k: v for k, v in platform_paths.items() if k in categories}

    results = {}
    cutoff_time = None
    if min_age_days > 0:
        cutoff_time = (datetime.now() - timedelta(days=min_age_days)).timestamp()

    all_categories = list(platform_paths.keys())
    total_categories = len(all_categories)

    for idx, category in enumerate(all_categories):
        if cancel_token and cancel_token.is_set():
            break

        if progress_callback:
            progress_callback(idx, total_categories, f"Scanning: {category}")

        category_files = []
        scan_dirs = platform_paths[category]

        # Add user-specified paths to the first category
        if paths and idx == 0:
            scan_dirs = list(scan_dirs) + list(paths)

        for scan_dir in scan_dirs:
            if cancel_token and cancel_token.is_set():
                break

            if not os.path.isdir(scan_dir):
                continue

            try:
                for entry in scan_directory(scan_dir, recursive=True, max_depth=5, cancel_token=cancel_token):
                    if entry.is_dir:
                        continue

                    # Apply age filter
                    if cutoff_time and entry.modified_at > cutoff_time:
                        continue

                    # Check if file matches junk patterns
                    is_junk = (
                        entry.extension.lower() in JUNK_EXTENSIONS
                        or entry.filename.lower() in JUNK_FILENAMES
                        or category in ("System Temp", "User Cache", "Thumbnails", "Trash", "Crash Reports")
                    )

                    if is_junk:
                        category_files.append(entry)
            except (PermissionError, OSError) as exc:
                logger.debug(f"Cannot scan {scan_dir}: {exc}")

        if category_files:
            results[category] = category_files

    if progress_callback:
        progress_callback(total_categories, total_categories, "Scan complete")

    return results


def scan_browser_artifacts(
    browsers=None,
    progress_callback=None,
    cancel_token=None,
):
    """
    Detect browser tracking artifacts (cookies, history, cache, sessions).

    Args:
        browsers: Optional list of browser names to scan (None = all detected).
        progress_callback: Called with (current, total, step_name).
        cancel_token: threading.Event checked for cancellation.

    Returns:
        dict of {browser_name: {artifact_type: [path, ...]}}
    """
    profiles = _browser_profiles()

    if browsers:
        profiles = {k: v for k, v in profiles.items() if k in browsers}

    results = {}
    browser_list = list(profiles.keys())
    total = len(browser_list)

    for idx, browser_name in enumerate(browser_list):
        if cancel_token and cancel_token.is_set():
            break

        if progress_callback:
            progress_callback(idx, total, f"Scanning: {browser_name}")

        browser_info = profiles[browser_name]
        base_path = browser_info.get("base", "")
        cache_path = browser_info.get("cache", "")

        if not os.path.isdir(base_path) and not os.path.isdir(cache_path):
            continue

        browser_artifacts = {}

        for artifact_type, patterns in BROWSER_ARTIFACT_PATTERNS.items():
            found_paths = []

            for search_base in [base_path, cache_path]:
                if not os.path.isdir(search_base):
                    continue

                for pattern in patterns:
                    if "*" in pattern:
                        # Glob pattern
                        for match in glob.glob(os.path.join(search_base, "**", pattern), recursive=True):
                            if os.path.exists(match):
                                found_paths.append(match)
                    else:
                        # Walk and find exact name matches
                        try:
                            for root, dirs, files in os.walk(search_base):
                                # Limit depth to 4 levels
                                depth = root[len(search_base):].count(os.sep)
                                if depth > 4:
                                    dirs.clear()
                                    continue

                                for name in files + dirs:
                                    if name == pattern:
                                        found_paths.append(os.path.join(root, name))
                        except (PermissionError, OSError):
                            pass

            if found_paths:
                browser_artifacts[artifact_type] = sorted(set(found_paths))

        if browser_artifacts:
            results[browser_name] = browser_artifacts

    if progress_callback:
        progress_callback(total, total, "Browser scan complete")

    return results


def estimate_cleanup_savings(scan_results):
    """
    Calculate total reclaimable space from scan results.

    Args:
        scan_results: dict from scan_junk_files()

    Returns:
        dict with per-category and total size information.
    """
    savings = {
        "categories": {},
        "total_files": 0,
        "total_size": 0,
    }

    for category, entries in scan_results.items():
        cat_size = sum(e.size for e in entries)
        cat_count = len(entries)
        savings["categories"][category] = {
            "count": cat_count,
            "size": cat_size,
            "formatted_size": format_size(cat_size),
        }
        savings["total_files"] += cat_count
        savings["total_size"] += cat_size

    savings["formatted_total"] = format_size(savings["total_size"])
    return savings


def estimate_browser_savings(browser_results):
    """
    Calculate space used by browser artifacts.

    Args:
        browser_results: dict from scan_browser_artifacts()

    Returns:
        dict with per-browser size information.
    """
    savings = {
        "browsers": {},
        "total_size": 0,
    }

    for browser, artifacts in browser_results.items():
        browser_size = 0
        browser_count = 0
        for artifact_type, paths in artifacts.items():
            for p in paths:
                try:
                    if os.path.isfile(p):
                        browser_size += os.path.getsize(p)
                        browser_count += 1
                    elif os.path.isdir(p):
                        for root, dirs, files in os.walk(p):
                            for f in files:
                                try:
                                    browser_size += os.path.getsize(os.path.join(root, f))
                                    browser_count += 1
                                except OSError:
                                    pass
                except OSError:
                    pass

        savings["browsers"][browser] = {
            "count": browser_count,
            "size": browser_size,
            "formatted_size": format_size(browser_size),
        }
        savings["total_size"] += browser_size

    savings["formatted_total"] = format_size(savings["total_size"])
    return savings
