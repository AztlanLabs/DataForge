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

    # OS identity (TICK-002): 0 means "unknown / not populated yet".
    # st_ino + st_dev group hardlinks (equal pair == same underlying file);
    # st_blocks exposes allocated blocks so sparse files can be detected.
    st_ino: int = 0
    st_dev: int = 0
    st_blocks: int = 0

    @property
    def hardlink_key(self) -> tuple[int, int]:
        """Identity of the underlying inode — equal keys are hardlinks."""
        return (self.st_dev, self.st_ino)

    @property
    def created_dt(self) -> datetime:
        return datetime.fromtimestamp(self.created_at)

    @property
    def modified_dt(self) -> datetime:
        return datetime.fromtimestamp(self.modified_at)
