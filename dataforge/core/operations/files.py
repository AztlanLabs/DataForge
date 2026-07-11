from __future__ import annotations

from dataclasses import dataclass
import datetime
import os
import re
import shutil
from typing import Optional, Set

from send2trash import send2trash


@dataclass
class OperationResult:
    action: str
    source_path: str
    destination_path: Optional[str]
    success: bool
    message: str
    dry_run: bool = False


def normalize_path(path: str | os.PathLike | None) -> str:
    if path is None:
        return ""

    raw_path = os.fspath(path).strip()
    if not raw_path:
        return ""

    return os.path.normpath(os.path.abspath(os.path.expanduser(raw_path)))


def resolve_collision_path(destination_path: str, reserved_paths: Optional[Set[str]] = None, current_path: Optional[str] = None) -> str:
    if reserved_paths is None:
        reserved_paths = set()
    candidate = normalize_path(destination_path)
    normalized_current_path = normalize_path(current_path)
    normalized_reserved_paths = {normalize_path(path) for path in reserved_paths}
    base_name = os.path.basename(candidate)
    folder = os.path.dirname(candidate)
    stem, extension = os.path.splitext(base_name)
    counter = 1

    while candidate in normalized_reserved_paths or (os.path.exists(candidate) and candidate != normalized_current_path):
        candidate = os.path.join(folder, f"{stem}_{counter}{extension}")
        counter += 1

    reserved_paths.add(candidate)
    return candidate


def format_operation_message(result: OperationResult) -> str:
    return result.message


def apply_result_to_entry(entry, result: Optional[OperationResult]):
    if not result or not result.success or not result.destination_path:
        return entry

    entry.path = normalize_path(result.destination_path)
    entry.filename = os.path.basename(entry.path)
    entry.extension = os.path.splitext(entry.filename)[1].lower()

    if os.path.exists(entry.path):
        stat = os.stat(entry.path)
        entry.size = stat.st_size
        entry.created_at = stat.st_ctime
        entry.modified_at = stat.st_mtime

    return entry


def transfer_path(
    source_path: str,
    destination_dir: str,
    action: str,
    dry_run: bool = True,
    reserved_paths: Optional[Set[str]] = None,
) -> OperationResult:
    source_path = normalize_path(source_path)
    destination_dir = normalize_path(destination_dir)
    action_name = action.lower()
    if action_name not in {"move", "copy"}:
        raise ValueError(f"Unsupported transfer action: {action}")

    if not destination_dir:
        raise ValueError("destination_dir is required")

    destination_path = resolve_collision_path(
        os.path.join(destination_dir, os.path.basename(source_path)),
        reserved_paths=reserved_paths,
        current_path=source_path,
    )

    verb = "Would move" if dry_run and action_name == "move" else "Would copy" if dry_run else "Moved" if action_name == "move" else "Copied"
    message = f"{verb}: {source_path} -> {destination_path}"

    if dry_run:
        return OperationResult(action_name, source_path, destination_path, True, message, dry_run=True)

    os.makedirs(destination_dir, exist_ok=True)
    try:
        if action_name == "move":
            shutil.move(source_path, destination_path)
        else:
            shutil.copy2(source_path, destination_path)
        return OperationResult(action_name, source_path, destination_path, True, message)
    except OSError as exc:
        return OperationResult(action_name, source_path, destination_path, False, f"ERROR: Could not {action_name} {source_path}: {exc}")


def delete_path(source_path: str, dry_run: bool = True, safe_mode: bool = True) -> OperationResult:
    source_path = normalize_path(source_path)
    mode = "SAFE" if safe_mode else "PERMANENT"
    message = f"Would delete ({mode}): {source_path}" if dry_run else f"Delete ({mode}): {source_path}"

    if dry_run:
        return OperationResult("delete", source_path, None, True, message, dry_run=True)

    try:
        if safe_mode:
            send2trash(source_path)
        else:
            os.remove(source_path)
        status = "Trashed" if safe_mode else "Deleted"
        return OperationResult("delete", source_path, None, True, f"{status}: {source_path}")
    except OSError as exc:
        return OperationResult("delete", source_path, None, False, f"ERROR: Could not delete {source_path}: {exc}")


def rename_path(
    source_path: str,
    new_name: str,
    dry_run: bool = True,
    reserved_paths: Optional[Set[str]] = None,
) -> Optional[OperationResult]:
    source_path = normalize_path(source_path)
    if not new_name:
        raise ValueError("new_name is required")

    current_name = os.path.basename(source_path)
    if new_name == current_name:
        return None

    destination_path = resolve_collision_path(
        os.path.join(os.path.dirname(source_path), new_name),
        reserved_paths=reserved_paths,
        current_path=source_path,
    )
    message = f"Would rename: {current_name} -> {os.path.basename(destination_path)}" if dry_run else f"Renamed: {current_name} -> {os.path.basename(destination_path)}"

    if dry_run:
        return OperationResult("rename", source_path, destination_path, True, message, dry_run=True)

    try:
        os.rename(source_path, destination_path)
        return OperationResult("rename", source_path, destination_path, True, message)
    except OSError as exc:
        return OperationResult("rename", source_path, destination_path, False, f"ERROR: Could not rename {current_name}: {exc}")


def rename_with_regex(
    source_path: str,
    pattern: str,
    replacement: str,
    dry_run: bool = True,
    reserved_paths: Optional[Set[str]] = None,
) -> Optional[OperationResult]:
    """Rename a file by applying a regex substitution to its basename.

    Thin wrapper over :func:`rename_path`: the whole filename (stem + extension)
    is passed through ``re.sub``. Returns ``None`` when the substitution leaves
    the name unchanged, mirroring ``rename_path``.
    """
    source_path = normalize_path(source_path)
    current_name = os.path.basename(source_path)
    new_name = re.sub(pattern, replacement, current_name)

    if not new_name or new_name == current_name:
        return None

    return rename_path(source_path, new_name, dry_run=dry_run, reserved_paths=reserved_paths)


def render_template_name(template: str, entry, counter: int) -> str:
    """Render a filename from a template using explicit field substitution.

    Supported placeholders: ``{name}``, ``{ext}``, ``{date}``, ``{size}``,
    ``{counter}``. Literal occurrences of these tokens inside the original
    filename are never rewritten, and the original extension is reattached
    deterministically when the template does not supply one via ``{ext}``.
    """
    import string

    fields = {
        "name": os.path.splitext(entry.filename)[0],
        "ext": entry.extension.replace(".", ""),
        "date": datetime.date.today().strftime("%Y-%m-%d"),
        "size": str(entry.size),
        "counter": str(counter).zfill(3),
    }

    class _DefaultDict(dict):
        def __missing__(self, key):  # leave unknown {tokens} untouched
            return "{" + key + "}"

    try:
        new_name = string.Formatter().vformat(template, (), _DefaultDict(fields))
    except (ValueError, IndexError, KeyError):
        # Malformed template (e.g. stray brace) — fall back to the raw template.
        new_name = template

    if "{ext}" not in template:
        new_name += entry.extension

    return new_name