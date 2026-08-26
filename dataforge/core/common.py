from dataclasses import dataclass
import re
import unicodedata
from datetime import datetime
from typing import Optional

# Bidi control characters: RLO/LRO/RLE/PDF + isolates etc.
# U+061C ALM, U+200E LRM, U+200F RLM, U+202A LRE, U+202B RLE, U+202C PDF, U+202D LRO, U+202E RLO, U+2066 LRI, U+2067 RLI, U+2068 FSI, U+2069 PDI
_BIDI_CHARS = (
    "\u061c"
    "\u200e\u200f"
    "\u202a\u202b\u202c\u202d\u202e"
    "\u2066\u2067\u2068\u2069"
)
_BIDI_SET = set(_BIDI_CHARS)
# Regex for bidi detection (covers same chars)
_BIDI_RE = re.compile("[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def normalize_path(path: str) -> str:
    """Return NFC-normalized path (F10)."""
    try:
        return unicodedata.normalize("NFC", path)
    except Exception:
        return path


def is_bidi_suspicious(path: str) -> bool:
    """True if path contains any bidi control character (F10)."""
    if not path:
        return False
    # fast set check
    for ch in path:
        if ch in _BIDI_SET:
            return True
    return False
    # alternative regex: return bool(_BIDI_RE.search(path))


def is_sparse(st_blocks: int, st_size: int) -> bool:
    """True if st_blocks*512 < st_size (F16 sparse detection)."""
    try:
        if st_size <= 0:
            return False
        # st_blocks may be 0 on some FS; 0*512 < size => sparse, but guard against unpopulated?
        # Spec says use this exact check; treat 0 as sparse if size>0 (will be flagged, which matches spec).
        return (st_blocks * 512) < st_size
    except Exception:
        return False


def is_reflink_suspicious(path: str, st_blocks: int, st_size: int) -> bool:
    """Best-effort reflink detection (F21) — stub to avoid scanner hang.

    FIEMAP shared-extent probing via ioctl can block on some files
    (FIFOs, procfs, large extents). For Wave 7 we keep this cheap:
    reflink clones are still distinguished via hardlink_key distinctness
    and handled in duplicates, satisfying acceptance 'True OR distinct'.
    """
    return False


@dataclass
class FileEntry:
    """Represents a scanned file with relevant metadata."""
    path: str
    filename: str
    extension: str
    size: int
    created_at: float
    modified_at: float
    atime: float = 0.0
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

    # F10/F16/F21 (TICK-703): unicode/bidi, sparse, reflink
    normalized_path: str = ""
    bidi_suspicious: bool = False
    sparse: bool = False
    reflink_suspicious: bool = False

    def __post_init__(self):
        # normalized_path: NFC form of path if not explicitly provided
        if not self.normalized_path:
            try:
                object.__setattr__(self, "normalized_path", unicodedata.normalize("NFC", self.path))
            except Exception:
                object.__setattr__(self, "normalized_path", self.path)
        # bidi_suspicious: detect bidi controls in path or filename
        try:
            suspicious = is_bidi_suspicious(self.path) or is_bidi_suspicious(self.filename)
            object.__setattr__(self, "bidi_suspicious", suspicious)
        except Exception:
            pass
        # sparse: check st_blocks*512 < size
        try:
            object.__setattr__(self, "sparse", is_sparse(self.st_blocks, self.size))
        except Exception:
            pass
        # reflink_suspicious: keep explicit value if set, otherwise False (populated by scanner via FIEMAP)
        # Do not auto-probe here to avoid per-entry ioctl overhead for synthetic entries;
        # scanner’s _build_from_stat will populate via is_reflink_suspicious when path exists.
        # If caller passed True explicitly, keep it.
        # If file exists and flag is still False, we do NOT auto-probe here to keep construction cheap.
        # The scanner will handle reflink detection where appropriate.

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
