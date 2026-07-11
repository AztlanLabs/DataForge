import os
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class FileEntry:
    """Represents a scanned file with relevant metadata."""
    path: str
    filename: str
    extension: str
    size: int
    created_at: float
    modified_at: float
    is_dir: bool = False
    
    # Hashes (calculated lazily or on demand)
    md5: Optional[str] = None
    sha1: Optional[str] = None
    sha256: Optional[str] = None

    @property
    def created_dt(self) -> datetime:
        return datetime.fromtimestamp(self.created_at)

    @property
    def modified_dt(self) -> datetime:
        return datetime.fromtimestamp(self.modified_at)
