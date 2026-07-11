import os
from .common import FileEntry
from .config import config


def build_file_entry(path: str):
    try:
        stat = os.stat(path)
    except OSError:
        return None

    return FileEntry(
        path=path,
        filename=os.path.basename(path),
        extension=os.path.splitext(path)[1].lower(),
        size=stat.st_size,
        created_at=stat.st_ctime,
        modified_at=stat.st_mtime,
        is_dir=False,
    )

def scan_directory(root_path: str, recursive: bool = True, max_depth: int = -1, cancel_token=None):
    """
    Generator that yields FileEntry objects for files in the directory.
    max_depth: -1 for infinite, 0 for current dir only, N for N levels deep.
    """
    if cancel_token and cancel_token.is_set():
        return

    # If recursive is explicitly False, override depth to 0
    if not recursive:
        max_depth = 0

    # Load Exclusions
    excl_folders = set(config.get("excluded_folders", []))
    excl_exts = tuple(config.get("excluded_extensions", []))

    if os.path.isfile(root_path):
        if os.path.basename(root_path).lower().endswith(excl_exts):
            return

        entry = build_file_entry(root_path)
        if entry is not None:
            yield entry
        return

    try:
        with os.scandir(root_path) as it:
            for entry in it:
                if cancel_token and cancel_token.is_set():
                    return

                # Never follow symlinks: a link to an ancestor causes unbounded
                # recursion, and a link outside the chosen root silently pulls
                # external files into search/duplicate/cleanup/organize results
                # (and thus into destructive actions). Skip them entirely.
                if entry.is_symlink():
                    continue

                # Exclusions
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in excl_folders:
                        continue
                else:
                     # File
                     if entry.name.lower().endswith(excl_exts):
                         continue

                if entry.is_file(follow_symlinks=False):
                    file_entry = build_file_entry(entry.path)
                    if file_entry is not None:
                        yield file_entry
                elif entry.is_dir(follow_symlinks=False):
                    # Check recursion criteria
                    can_recurse = (max_depth == -1) or (max_depth > 0)

                    if can_recurse:
                        next_depth = -1 if max_depth == -1 else max_depth - 1
                        yield from scan_directory(entry.path, recursive=True, max_depth=next_depth, cancel_token=cancel_token)
    except OSError:
        # Skip directories we can't access
        pass
