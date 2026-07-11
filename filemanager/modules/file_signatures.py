"""
File signature database for data carving and file type identification.

Maps file format names to magic byte headers and footers used for
raw block-level recovery when filesystem metadata is corrupted.
"""

# Each entry: {header: bytes, footer: bytes|None, extensions: [str], max_size: int, description: str}
SIGNATURES = {
    "JPEG": {
        "header": b"\xFF\xD8\xFF",
        "footer": b"\xFF\xD9",
        "extensions": [".jpg", ".jpeg"],
        "max_size": 50 * 1024 * 1024,  # 50 MB
        "description": "JPEG Image",
    },
    "PNG": {
        "header": b"\x89\x50\x4E\x47\x0D\x0A\x1A\x0A",
        "footer": b"\x49\x45\x4E\x44\xAE\x42\x60\x82",
        "extensions": [".png"],
        "max_size": 50 * 1024 * 1024,
        "description": "PNG Image",
    },
    "GIF": {
        "header": b"\x47\x49\x46\x38",
        "footer": b"\x00\x3B",
        "extensions": [".gif"],
        "max_size": 20 * 1024 * 1024,
        "description": "GIF Image",
    },
    "BMP": {
        "header": b"\x42\x4D",
        "footer": None,
        "extensions": [".bmp"],
        "max_size": 50 * 1024 * 1024,
        "description": "BMP Image",
    },
    "TIFF_LE": {
        "header": b"\x49\x49\x2A\x00",
        "footer": None,
        "extensions": [".tiff", ".tif"],
        "max_size": 100 * 1024 * 1024,
        "description": "TIFF Image (Little Endian)",
    },
    "TIFF_BE": {
        "header": b"\x4D\x4D\x00\x2A",
        "footer": None,
        "extensions": [".tiff", ".tif"],
        "max_size": 100 * 1024 * 1024,
        "description": "TIFF Image (Big Endian)",
    },
    "WEBP": {
        "header": b"\x52\x49\x46\x46",  # RIFF (needs secondary check for WEBP)
        "footer": None,
        "extensions": [".webp"],
        "max_size": 50 * 1024 * 1024,
        "description": "WebP Image",
    },
    "PDF": {
        "header": b"\x25\x50\x44\x46",
        "footer": b"\x25\x25\x45\x4F\x46",
        "extensions": [".pdf"],
        "max_size": 500 * 1024 * 1024,
        "description": "PDF Document",
    },
    "ZIP": {
        "header": b"\x50\x4B\x03\x04",
        "footer": b"\x50\x4B\x05\x06",
        "extensions": [".zip", ".docx", ".xlsx", ".pptx", ".odt", ".jar", ".apk"],
        "max_size": 1024 * 1024 * 1024,  # 1 GB
        "description": "ZIP Archive / Office Document",
    },
    "RAR": {
        "header": b"\x52\x61\x72\x21\x1A\x07",
        "footer": None,
        "extensions": [".rar"],
        "max_size": 1024 * 1024 * 1024,
        "description": "RAR Archive",
    },
    "GZIP": {
        "header": b"\x1F\x8B",
        "footer": None,
        "extensions": [".gz", ".tar.gz", ".tgz"],
        "max_size": 1024 * 1024 * 1024,
        "description": "GZIP Compressed",
    },
    "7Z": {
        "header": b"\x37\x7A\xBC\xAF\x27\x1C",
        "footer": None,
        "extensions": [".7z"],
        "max_size": 1024 * 1024 * 1024,
        "description": "7-Zip Archive",
    },
    "MP3": {
        "header": b"\x49\x44\x33",  # ID3 tag
        "footer": None,
        "extensions": [".mp3"],
        "max_size": 50 * 1024 * 1024,
        "description": "MP3 Audio (ID3)",
    },
    "MP3_SYNC": {
        "header": b"\xFF\xFB",  # MPEG sync
        "footer": None,
        "extensions": [".mp3"],
        "max_size": 50 * 1024 * 1024,
        "description": "MP3 Audio (sync frame)",
    },
    "WAV": {
        "header": b"\x52\x49\x46\x46",  # RIFF (needs secondary check for WAVE)
        "footer": None,
        "extensions": [".wav"],
        "max_size": 500 * 1024 * 1024,
        "description": "WAV Audio",
    },
    "FLAC": {
        "header": b"\x66\x4C\x61\x43",
        "footer": None,
        "extensions": [".flac"],
        "max_size": 200 * 1024 * 1024,
        "description": "FLAC Audio",
    },
    "OGG": {
        "header": b"\x4F\x67\x67\x53",
        "footer": None,
        "extensions": [".ogg", ".ogv", ".oga"],
        "max_size": 200 * 1024 * 1024,
        "description": "OGG Container",
    },
    "MP4": {
        "header": b"\x00\x00\x00",  # Varies, but ftyp marker at offset 4
        "footer": None,
        "extensions": [".mp4", ".m4a", ".m4v", ".mov"],
        "max_size": 4 * 1024 * 1024 * 1024,  # 4 GB
        "description": "MP4/MOV Video",
    },
    "AVI": {
        "header": b"\x52\x49\x46\x46",  # RIFF (needs secondary check for AVI)
        "footer": None,
        "extensions": [".avi"],
        "max_size": 4 * 1024 * 1024 * 1024,
        "description": "AVI Video",
    },
    "MKV": {
        "header": b"\x1A\x45\xDF\xA3",
        "footer": None,
        "extensions": [".mkv", ".webm"],
        "max_size": 4 * 1024 * 1024 * 1024,
        "description": "Matroska Video",
    },
    "SQLite": {
        "header": b"\x53\x51\x4C\x69\x74\x65\x20\x66\x6F\x72\x6D\x61\x74\x20\x33\x00",
        "footer": None,
        "extensions": [".db", ".sqlite", ".sqlite3"],
        "max_size": 1024 * 1024 * 1024,
        "description": "SQLite Database",
    },
    "ELF": {
        "header": b"\x7F\x45\x4C\x46",
        "footer": None,
        "extensions": ["", ".so", ".elf"],
        "max_size": 500 * 1024 * 1024,
        "description": "ELF Executable",
    },
    "PE_EXE": {
        "header": b"\x4D\x5A",
        "footer": None,
        "extensions": [".exe", ".dll", ".sys"],
        "max_size": 500 * 1024 * 1024,
        "description": "Windows PE Executable",
    },
}

# Secondary headers for RIFF-based formats (WAV, AVI, WEBP)
RIFF_SUBTYPES = {
    b"WAVE": "WAV",
    b"AVI ": "AVI",
    b"WEBP": "WEBP",
}


def identify_file_type(header_bytes):
    """
    Identify a file's type from its first N bytes.

    Args:
        header_bytes: First 16+ bytes of the file.

    Returns:
        Format name string, or None if unrecognized.
    """
    if not header_bytes or len(header_bytes) < 4:
        return None

    # Check RIFF subtypes first (WAV, AVI, WEBP share RIFF header)
    if header_bytes[:4] == b"\x52\x49\x46\x46" and len(header_bytes) >= 12:
        subtype = header_bytes[8:12]
        riff_match = RIFF_SUBTYPES.get(subtype)
        if riff_match:
            return riff_match

    # MP4/MOV check: look for 'ftyp' at offset 4
    if len(header_bytes) >= 8 and header_bytes[4:8] == b"ftyp":
        return "MP4"

    # Check all signatures (longest match first for precision)
    best_match = None
    best_len = 0

    for fmt_name, sig in SIGNATURES.items():
        h = sig["header"]
        if len(h) > len(header_bytes):
            continue
        if header_bytes[:len(h)] == h and len(h) > best_len:
            # Skip RIFF-based formats (already handled above)
            if h == b"\x52\x49\x46\x46":
                continue
            # Skip generic MP4 header (already handled above)
            if fmt_name == "MP4":
                continue
            best_match = fmt_name
            best_len = len(h)

    return best_match


def get_signature(format_name):
    """Get the signature definition for a format name."""
    return SIGNATURES.get(format_name)


def get_all_categories():
    """Get format names grouped by type category."""
    categories = {
        "Images": ["JPEG", "PNG", "GIF", "BMP", "TIFF_LE", "TIFF_BE", "WEBP"],
        "Documents": ["PDF", "ZIP"],
        "Audio": ["MP3", "MP3_SYNC", "WAV", "FLAC", "OGG"],
        "Video": ["MP4", "AVI", "MKV"],
        "Archives": ["ZIP", "RAR", "GZIP", "7Z"],
        "Databases": ["SQLite"],
        "Executables": ["ELF", "PE_EXE"],
    }
    return categories
