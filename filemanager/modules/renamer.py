from typing import List
from ..core.scanner import scan_directory
from ..core.services import FileActionService

def bulk_rename(path: str, pattern: str, replacement: str, recursive: bool = False, dry_run: bool = True) -> List[str]:
    """
    Rename files matching a regex pattern.
    """
    # We shouldn't use the generator directly if we're renaming as we iterate, 
    # but separate scan and rename is safer.
    files = list(scan_directory(path, recursive))

    outcome = FileActionService.rename_items_with_regex(files, pattern, replacement, dry_run=dry_run)
    return FileActionService.messages(outcome, include_skipped=False)
