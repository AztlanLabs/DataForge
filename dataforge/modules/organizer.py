from typing import List
from ..core.common import FileEntry
from ..core.services import FileActionService
from .search import SearchQuery, search_files

class Organizer:
    @staticmethod
    def organize_files(
        root_path: str, 
        query: SearchQuery, 
        action: str, 
        dest_folder: str, 
        dry_run: bool = True
    ) -> List[str]:
        """
        Organize files matching the query into the destination folder.
        Actions: 'move', 'copy'.
        """
        files = search_files(root_path, query, recursive=True)
        outcome = FileActionService.transfer_items(files, dest_folder, action, dry_run=dry_run)
        return FileActionService.messages(outcome)

    @staticmethod
    def delete_files(files: List[FileEntry], dry_run: bool = True) -> List[str]:
        """Safe delete implementation."""
        outcome = FileActionService.delete_items(files, dry_run=dry_run)
        return FileActionService.messages(outcome)
