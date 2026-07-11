from .config import config
import math
import os
import re

# Shared file-category map, reused by the Dashboard view and the Action
# Builder's "Organize by Category" step so both stay in sync.
CATEGORY_EXTENSIONS = {
    "Documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                  ".txt", ".rtf", ".odt", ".ods", ".csv", ".md"},
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg",
               ".ico", ".tiff", ".raw", ".psd"},
    "Videos": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Code": {".py", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".cs",
             ".html", ".css", ".json", ".xml", ".yaml", ".yml", ".sql",
             ".rb", ".go", ".rs", ".php", ".sh", ".bat"},
}

CATEGORY_COLORS = {
    "Documents": "#0d6efd",
    "Images": "#28a745",
    "Videos": "#ffc107",
    "Audio": "#17a2b8",
    "Archives": "#dc3545",
    "Code": "#6c757d",
    "Other": "#343a40",
}


def categorize_extension(ext: str) -> str:
    """Map a file extension to one of CATEGORY_EXTENSIONS, defaulting to 'Other'."""
    ext_lower = (ext or "").lower()
    for category, exts in CATEGORY_EXTENSIONS.items():
        if ext_lower in exts:
            return category
    return "Other"


def normalize_filename(
    name: str,
    index: int = 0,
    *,
    strip_leading_dot: bool = False,
    find_text: str = "",
    replace_text: str = "",
    use_regex: bool = False,
    numeric_pattern: str = "",
    numeric_replacement: str = "",
    numeric_pad: int = 0,
    case_mode: str = "none",
    collapse_separators: bool = False,
    prefix: str = "",
    suffix: str = "",
) -> str:
    """
    Compute a normalized filename from `name`, applying the requested
    transforms in a fixed, predictable order. Shared by the Action Builder's
    NormalizeNameStep and the Batch Renamer tab so both behave identically.

    - strip_leading_dot: turns ".file342.txt" into "file342.txt".
    - find_text/replace_text/use_regex: substring or regex replace on the stem.
    - numeric_pattern/numeric_replacement/numeric_pad: regex-driven replacement
      of numeric runs (or any custom pattern). `{n}` in numeric_replacement is
      substituted with `index`, zero-padded to `numeric_pad` digits if set.
    - case_mode: "none", "lower", "upper", or "title".
    - collapse_separators: collapses runs of spaces/underscores/hyphens to "_".
    - prefix/suffix: added to the stem before the extension is reattached.
    """
    if strip_leading_dot and name.startswith(".") and len(name) > 1:
        name = name[1:]

    stem, ext = os.path.splitext(name)

    if find_text:
        try:
            if use_regex:
                stem = re.sub(find_text, replace_text, stem)
            else:
                stem = stem.replace(find_text, replace_text)
        except re.error:
            pass

    if numeric_pattern:
        counter_text = str(index).zfill(numeric_pad) if numeric_pad else str(index)
        replacement = numeric_replacement.replace("{n}", counter_text)
        try:
            stem = re.sub(numeric_pattern, replacement, stem)
        except re.error:
            pass

    if case_mode == "lower":
        stem = stem.lower()
    elif case_mode == "upper":
        stem = stem.upper()
    elif case_mode == "title":
        stem = stem.title()

    if collapse_separators:
        stem = re.sub(r"[ _\-]+", "_", stem).strip("_")

    return f"{prefix}{stem}{suffix}{ext}"


def format_size(size_bytes):
    """
    Format size based on config 'size_unit' (Auto, Bytes, KB, MB, GB).
    """
    if size_bytes is None: return "0 B"
    
    unit = config.get("size_unit", "Auto")
    
    if unit == "Bytes":
        return f"{size_bytes} B"
    elif unit == "KB":
        return f"{size_bytes / 1024:.2f} KB"
    elif unit == "MB":
        return f"{size_bytes / (1024**2):.2f} MB"
    elif unit == "GB":
        return f"{size_bytes / (1024**3):.2f} GB"
    else: # Auto
        if size_bytes == 0:
            return "0 B"
        size_name = ("B", "KB", "MB", "GB", "TB", "PB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return "%s %s" % (s, size_name[i])

def format_display_path(path, root=None):
    """
    Formats a path for display based on config 'path_display_mode'
    ("full" or "relative"), the shared source of truth for path rendering
    across every tree/label in the app (Search, Duplicates, Preview panel,
    etc.) so the Settings toggle actually affects the whole app at once.

    - "full": returns `path` unchanged.
    - "relative": returns `path` relative to `root` (e.g. the scan folder
      the view is currently working from) when `root` is given and `path`
      is actually under it; otherwise falls back to the full path, since a
      path outside the known root has no meaningful relative form.

    Callers that show paths inside a tree column should also rely on that
    column's Qt.ElideLeft text-elide mode (see EnhancedTreeview) so the
    filename at the end of the string stays visible even when the full
    string doesn't fit the column — this function controls WHAT string is
    shown, eliding controls how an overly-long one gets visually truncated.
    """
    if not path:
        return path

    mode = config.get("path_display_mode", "full")
    if mode != "relative" or not root:
        return path

    try:
        rel = os.path.relpath(path, root)
    except ValueError:
        # Different drive on Windows, or other path-comparison failure.
        return path

    if rel.startswith(".."):
        # `path` isn't actually under `root` — a relative form would be
        # confusing (or nonsensical), so show the full path instead.
        return path

    return rel


def parse_extensions(ext_str):
    """
    Robustly parse comma-separated extensions (e.g. '.jpg, png, .pdf').
    Returns list of lower-case extensions starting with dot.
    """
    if not ext_str: return []
    parts = [x.strip() for x in ext_str.split(',') if x.strip()]
    cleaned = []
    for p in parts:
        if not p.startswith('.'):
            p = '.' + p
        cleaned.append(p.lower())
    return cleaned

def check_disk_space(dest_folder, required_bytes):
    """
    Check if destination has enough free space.
    Returns (True, msg) or (False, error_msg).
    """
    try:
        if not os.path.exists(dest_folder):
             # Try parent if dest doesn't exist yet
             dest_folder = os.path.dirname(dest_folder)
             
        import shutil
        total, used, free = shutil.disk_usage(dest_folder)
        
        if free < required_bytes:
            req_mb = required_bytes / (1024*1024)
            free_mb = free / (1024*1024)
            return False, f"Not enough space. Required: {req_mb:.2f} MB, Free: {free_mb:.2f} MB"
        return True, "OK"
    except Exception as e:
        # If check fails, we assume OK or warn?
        # Safe is to warn but maybe allow?
        return True, f"Could not check space: {e}"

def safe_zip_write(zf, source_path, arcname, existing_names):
    """
    Write file to zip, appending _N if filename exists in existing_names.
    Updates existing_names set in place.
    """
    base_arcname = arcname
    counter = 1
    while arcname in existing_names:
        name, ext = os.path.splitext(base_arcname)
        arcname = f"{name}_{counter}{ext}"
        counter += 1
    
    zf.write(source_path, arcname)
    existing_names.add(arcname)
    return arcname
