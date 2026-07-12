"""
Unified Metadata Engineering module.

Read, write, edit, and strip metadata across multiple file formats
using a tiered handler approach: ExifTool → Pillow → pypdf → mutagen.
"""
import os
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from functools import lru_cache

from ..core.config import config
from ..core.logger import logger
from ..core.utils import format_size

# ---------------------------------------------------------------------------
# Optional dependency detection
# ---------------------------------------------------------------------------

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    Image.MAX_IMAGE_PIXELS = 100_000_000
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

try:
    from pypdf import PdfReader, PdfWriter
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    import mutagen
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False


@lru_cache(maxsize=1)
def _has_exiftool():
    """Check if the exiftool CLI is available.

    Probed lazily (and memoised) on first real use rather than at import time,
    so simply importing this module — which happens for every GUI/CLI cold
    start — does not shell out to an external binary.
    """
    try:
        result = subprocess.run(
            ["exiftool", "-ver"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


# Supported image extensions for Pillow
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif", ".ico"}
_PDF_EXTENSIONS = {".pdf"}
_AUDIO_EXTENSIONS = {".mp3", ".flac", ".ogg", ".oga", ".m4a", ".mp4", ".wav", ".aac", ".wma", ".opus"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".flv", ".wmv"}


# ---------------------------------------------------------------------------
# Unified metadata reader
# ---------------------------------------------------------------------------

class MetadataEngine:
    """Unified metadata read/write/strip engine with multi-format support."""

    @staticmethod
    def read_metadata(path):
        """
        Read all available metadata from a file.

        Uses the best available handler:
        1. ExifTool (if installed) — 180+ formats
        2. Pillow — images
        3. pypdf — PDFs
        4. mutagen — audio/video

        Args:
            path: Absolute file path.

        Returns:
            dict with metadata fields, format info, and handler used.
        """
        if not os.path.isfile(path):
            return {"error": f"File not found: {path}", "path": path}

        ext = os.path.splitext(path)[1].lower()
        result = {
            "path": path,
            "filename": os.path.basename(path),
            "extension": ext,
            "size": os.path.getsize(path),
            "formatted_size": format_size(os.path.getsize(path)),
            "handler": None,
            "fields": {},
            "has_gps": False,
            "gps": None,
            "timestamps": {},
        }

        # Try ExifTool first (broadest format support)
        if _has_exiftool():
            try:
                exif_data = _read_exiftool(path)
                if exif_data and not exif_data.get("error"):
                    result["handler"] = "exiftool"
                    result["fields"] = exif_data
                    result["has_gps"] = _has_gps_data(exif_data)
                    if result["has_gps"]:
                        result["gps"] = _extract_gps_from_exiftool(exif_data)
                    result["timestamps"] = _extract_timestamps_from_exiftool(exif_data)
                    return result
            except Exception as exc:
                logger.debug(f"ExifTool read failed for {path}: {exc}")

        # Pillow for images
        if ext in _IMAGE_EXTENSIONS and HAS_PILLOW:
            try:
                pil_data = _read_pillow(path)
                if pil_data:
                    result["handler"] = "pillow"
                    result["fields"] = pil_data.get("fields", {})
                    result["has_gps"] = pil_data.get("has_gps", False)
                    result["gps"] = pil_data.get("gps")
                    result["timestamps"] = pil_data.get("timestamps", {})
                    result["image_info"] = pil_data.get("image_info", {})
                    return result
            except Exception as exc:
                logger.debug(f"Pillow read failed for {path}: {exc}")

        # pypdf for PDFs
        if ext in _PDF_EXTENSIONS and HAS_PYPDF:
            try:
                pdf_data = _read_pypdf(path)
                if pdf_data:
                    result["handler"] = "pypdf"
                    result["fields"] = pdf_data.get("fields", {})
                    result["timestamps"] = pdf_data.get("timestamps", {})
                    return result
            except Exception as exc:
                logger.debug(f"pypdf read failed for {path}: {exc}")

        # mutagen for audio/video
        if ext in _AUDIO_EXTENSIONS | _VIDEO_EXTENSIONS and HAS_MUTAGEN:
            try:
                audio_data = _read_mutagen(path)
                if audio_data:
                    result["handler"] = "mutagen"
                    result["fields"] = audio_data.get("fields", {})
                    result["timestamps"] = audio_data.get("timestamps", {})
                    result["audio_info"] = audio_data.get("audio_info", {})
                    return result
            except Exception as exc:
                logger.debug(f"mutagen read failed for {path}: {exc}")

        # Fallback: basic OS metadata
        result["handler"] = "os_stat"
        stat = os.stat(path)
        result["fields"] = {
            "File Size": format_size(stat.st_size),
            "Last Modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "Last Accessed": datetime.fromtimestamp(stat.st_atime).isoformat(),
            "Created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        }
        result["timestamps"] = {
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "accessed": datetime.fromtimestamp(stat.st_atime).isoformat(),
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        }
        return result

    @staticmethod
    def read_metadata_batch(paths, progress_callback=None, cancel_token=None):
        """
        Read metadata from multiple files, in parallel across
        config["max_thread_workers"] threads. Each unit of work is mostly an
        external `exiftool` subprocess call, so the real wall-clock win comes
        from overlapping those subprocess waits (the GIL is released while
        waiting on the child process) rather than CPU-bound parallelism.
        """
        paths = list(paths)
        total = len(paths)
        max_workers = max(1, config.get("max_thread_workers", 4))
        results = [None] * total
        completed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(MetadataEngine.read_metadata, path): idx
                for idx, path in enumerate(paths)
            }
            for future in as_completed(futures):
                idx = futures[future]
                if cancel_token and cancel_token.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                completed += 1
                if progress_callback and completed % 10 == 0:
                    progress_callback(completed, total, f"Reading: {os.path.basename(paths[idx])}")
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    results[idx] = {"path": paths[idx], "error": str(exc)}

        if progress_callback:
            progress_callback(total, total, "Metadata reading complete")

        return [r for r in results if r is not None]

    @staticmethod
    def write_metadata(path, fields, dry_run=True):
        """
        Write metadata fields to a file.

        Args:
            path: File path.
            fields: dict of {field_name: value} to write.
            dry_run: If True, only report what would change.

        Returns:
            dict with success status and message.
        """
        if not os.path.isfile(path):
            return {"success": False, "message": f"File not found: {path}", "dry_run": dry_run}

        if dry_run:
            return {
                "success": True,
                "message": f"Would write {len(fields)} field(s) to {os.path.basename(path)}",
                "dry_run": True,
                "fields": fields,
            }

        # Use ExifTool for writing (most reliable)
        if _has_exiftool():
            return _write_exiftool(path, fields)

        ext = os.path.splitext(path)[1].lower()

        # Pillow for images (limited write support)
        if ext in _IMAGE_EXTENSIONS and HAS_PILLOW:
            return _write_pillow(path, fields)

        # mutagen for audio
        if ext in _AUDIO_EXTENSIONS and HAS_MUTAGEN:
            return _write_mutagen(path, fields)

        return {"success": False, "message": "No write handler available for this format."}

    @staticmethod
    def remove_metadata(path, fields=None, dry_run=True):
        """
        Remove metadata from a file.

        Args:
            path: File path.
            fields: Optional list of specific field names to remove. None = strip all.
            dry_run: If True, only report what would change.

        Returns:
            dict with success status and message.
        """
        if not os.path.isfile(path):
            return {"success": False, "message": f"File not found: {path}"}

        if dry_run:
            scope = f"{len(fields)} field(s)" if fields else "all metadata"
            return {
                "success": True,
                "message": f"Would strip {scope} from {os.path.basename(path)}",
                "dry_run": True,
            }

        # ExifTool: strip all or specific tags
        if _has_exiftool():
            return _strip_exiftool(path, fields)

        ext = os.path.splitext(path)[1].lower()

        # Pillow: strip image metadata
        if ext in _IMAGE_EXTENSIONS and HAS_PILLOW:
            return _strip_pillow(path)

        # pypdf: strip PDF metadata
        if ext in _PDF_EXTENSIONS and HAS_PYPDF:
            return _strip_pypdf(path)

        # mutagen: strip audio metadata
        if ext in _AUDIO_EXTENSIONS and HAS_MUTAGEN:
            return _strip_mutagen(path)

        return {"success": False, "message": "No strip handler available for this format."}

    @staticmethod
    def extract_gps(path):
        """Extract GPS coordinates from a file."""
        meta = MetadataEngine.read_metadata(path)
        return meta.get("gps")

    @staticmethod
    def extract_timestamps(path):
        """Extract all timestamp fields from a file."""
        meta = MetadataEngine.read_metadata(path)
        return meta.get("timestamps", {})

    @staticmethod
    def get_supported_formats():
        """Get list of supported format categories and their capabilities."""
        formats = {
            "images": {
                "extensions": sorted(_IMAGE_EXTENSIONS),
                "read": HAS_PILLOW or _has_exiftool(),
                "write": _has_exiftool(),
                "strip": HAS_PILLOW or _has_exiftool(),
            },
            "pdf": {
                "extensions": sorted(_PDF_EXTENSIONS),
                "read": HAS_PYPDF or _has_exiftool(),
                "write": _has_exiftool(),
                "strip": HAS_PYPDF or _has_exiftool(),
            },
            "audio": {
                "extensions": sorted(_AUDIO_EXTENSIONS),
                "read": HAS_MUTAGEN or _has_exiftool(),
                "write": HAS_MUTAGEN or _has_exiftool(),
                "strip": HAS_MUTAGEN or _has_exiftool(),
            },
            "video": {
                "extensions": sorted(_VIDEO_EXTENSIONS),
                "read": _has_exiftool(),
                "write": _has_exiftool(),
                "strip": _has_exiftool(),
            },
        }
        if _has_exiftool():
            formats["all_exiftool"] = {
                "note": "ExifTool supports 180+ file formats",
                "available": True,
            }
        return formats


# ---------------------------------------------------------------------------
# ExifTool handlers
# ---------------------------------------------------------------------------

def _read_exiftool(path):
    """Read metadata using exiftool CLI."""
    try:
        result = subprocess.run(
            ["exiftool", "-j", "-G", "-n", path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data and isinstance(data, list):
                return data[0]
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        return {"error": str(exc)}
    return None


def _write_exiftool(path, fields):
    """Write metadata using exiftool CLI."""
    args = ["exiftool", "-overwrite_original"]
    for key, value in fields.items():
        args.append(f"-{key}={value}")
    args.append(path)

    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return {"success": True, "message": f"Updated {len(fields)} field(s) via ExifTool."}
        return {"success": False, "message": f"ExifTool error: {result.stderr}"}
    except Exception as exc:
        return {"success": False, "message": f"ExifTool failed: {exc}"}


def _strip_exiftool(path, fields=None):
    """Strip metadata using exiftool CLI."""
    args = ["exiftool", "-overwrite_original"]
    if fields:
        for field in fields:
            args.append(f"-{field}=")
    else:
        args.append("-all=")
    args.append(path)

    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return {"success": True, "message": "Metadata stripped via ExifTool."}
        return {"success": False, "message": f"ExifTool strip error: {result.stderr}"}
    except Exception as exc:
        return {"success": False, "message": f"ExifTool strip failed: {exc}"}


def _has_gps_data(exif_data):
    """Check if exiftool data contains GPS information."""
    for key in exif_data:
        if "GPS" in key.upper():
            return True
    return False


def _extract_gps_from_exiftool(exif_data):
    """Extract GPS coordinates from exiftool JSON data."""
    lat = exif_data.get("Composite:GPSLatitude") or exif_data.get("GPS:GPSLatitude")
    lon = exif_data.get("Composite:GPSLongitude") or exif_data.get("GPS:GPSLongitude")
    alt = exif_data.get("GPS:GPSAltitude")

    if lat is not None and lon is not None:
        return {
            "latitude": float(lat),
            "longitude": float(lon),
            "altitude": float(alt) if alt else None,
        }
    return None


def _extract_timestamps_from_exiftool(exif_data):
    """Extract timestamp fields from exiftool data."""
    timestamps = {}
    ts_keys = [
        "File:FileModifyDate", "File:FileAccessDate", "File:FileInodeChangeDate",
        "EXIF:DateTimeOriginal", "EXIF:CreateDate", "EXIF:ModifyDate",
        "XMP:CreateDate", "XMP:ModifyDate", "XMP:MetadataDate",
        "IPTC:DateCreated", "IPTC:TimeCreated",
    ]
    for key in ts_keys:
        value = exif_data.get(key)
        if value:
            timestamps[key] = str(value)
    return timestamps


# ---------------------------------------------------------------------------
# Pillow handlers
# ---------------------------------------------------------------------------

def _read_pillow(path):
    """Read image metadata using Pillow."""
    if not HAS_PILLOW:
        return None

    result = {"fields": {}, "has_gps": False, "gps": None, "timestamps": {}, "image_info": {}}

    try:
        img = Image.open(path)

        # Basic image info
        result["image_info"] = {
            "format": img.format,
            "mode": img.mode,
            "width": img.size[0],
            "height": img.size[1],
        }

        # EXIF data
        exif_data = img._getexif()
        if exif_data:
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, f"Tag_{tag_id}")
                try:
                    if isinstance(value, bytes):
                        value = value.hex()[:100]
                    result["fields"][tag_name] = str(value)
                except Exception:
                    result["fields"][tag_name] = "(binary data)"

                # GPS
                if tag_name == "GPSInfo" and isinstance(value, dict):
                    result["has_gps"] = True
                    result["gps"] = _parse_pillow_gps(value)

                # Timestamps
                if tag_name in ("DateTime", "DateTimeOriginal", "DateTimeDigitized"):
                    result["timestamps"][tag_name] = str(value)

        img.close()
    except Exception as exc:
        logger.debug(f"Pillow read error for {path}: {exc}")

    return result


def _parse_pillow_gps(gps_info):
    """Parse GPS data from Pillow EXIF GPSInfo dict."""
    def _dms_to_decimal(dms_tuple, ref):
        """Convert (degrees, minutes, seconds) to decimal."""
        try:
            if hasattr(dms_tuple[0], 'numerator'):
                d = float(dms_tuple[0])
                m = float(dms_tuple[1])
                s = float(dms_tuple[2])
            else:
                d, m, s = float(dms_tuple[0]), float(dms_tuple[1]), float(dms_tuple[2])
            decimal = d + m / 60.0 + s / 3600.0
            if ref in ('S', 'W'):
                decimal = -decimal
            return decimal
        except (TypeError, IndexError, ValueError):
            return None

    gps = {}
    lat = gps_info.get(2)  # GPSLatitude
    lat_ref = gps_info.get(1, 'N')  # GPSLatitudeRef
    lon = gps_info.get(4)  # GPSLongitude
    lon_ref = gps_info.get(3, 'E')  # GPSLongitudeRef
    alt = gps_info.get(6)  # GPSAltitude

    if lat:
        gps["latitude"] = _dms_to_decimal(lat, lat_ref)
    if lon:
        gps["longitude"] = _dms_to_decimal(lon, lon_ref)
    if alt:
        try:
            gps["altitude"] = float(alt)
        except (TypeError, ValueError):
            pass

    return gps if gps.get("latitude") is not None else None


def _write_pillow(path, fields):
    """Write image metadata using Pillow (limited)."""
    return {"success": False, "message": "Pillow write not supported. Install exiftool for full write support."}


def _strip_pillow(path):
    """Strip image metadata using Pillow."""
    if not HAS_PILLOW:
        return {"success": False, "message": "Pillow not available."}

    try:
        img = Image.open(path)
        data = list(img.getdata())
        clean_img = Image.new(img.mode, img.size)
        clean_img.putdata(data)

        # Save with no EXIF
        import tempfile
        temp_fd, temp_path = tempfile.mkstemp(suffix=os.path.splitext(path)[1])
        os.close(temp_fd)

        save_kwargs = {}
        if img.format == "JPEG":
            save_kwargs["quality"] = 95
        clean_img.save(temp_path, format=img.format, **save_kwargs)
        img.close()
        clean_img.close()

        os.replace(temp_path, path)
        return {"success": True, "message": "Metadata stripped via Pillow."}
    except Exception as exc:
        return {"success": False, "message": f"Pillow strip failed: {exc}"}


# ---------------------------------------------------------------------------
# pypdf handlers
# ---------------------------------------------------------------------------

def _read_pypdf(path):
    """Read PDF metadata."""
    if not HAS_PYPDF:
        return None

    result = {"fields": {}, "timestamps": {}}

    try:
        reader = PdfReader(path)
        meta = reader.metadata

        if meta:
            for key, value in meta.items():
                clean_key = key.lstrip("/")
                result["fields"][clean_key] = str(value) if value else ""

                if "date" in clean_key.lower() or "time" in clean_key.lower():
                    result["timestamps"][clean_key] = str(value) if value else ""

        result["fields"]["Page Count"] = str(len(reader.pages))
    except Exception as exc:
        logger.debug(f"pypdf read error for {path}: {exc}")

    return result


def _strip_pypdf(path):
    """Strip PDF metadata."""
    if not HAS_PYPDF:
        return {"success": False, "message": "pypdf not available."}

    try:
        reader = PdfReader(path)
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        writer.add_metadata({})

        import tempfile
        temp_fd, temp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(temp_fd)

        with open(temp_path, "wb") as f:
            writer.write(f)

        os.replace(temp_path, path)
        return {"success": True, "message": "PDF metadata stripped."}
    except Exception as exc:
        return {"success": False, "message": f"PDF strip failed: {exc}"}


# ---------------------------------------------------------------------------
# mutagen handlers
# ---------------------------------------------------------------------------

def _read_mutagen(path):
    """Read audio/video metadata using mutagen."""
    if not HAS_MUTAGEN:
        return None

    result = {"fields": {}, "timestamps": {}, "audio_info": {}}

    try:
        audio = mutagen.File(path)
        if audio is None:
            return None

        # Audio technical info
        if hasattr(audio, "info"):
            info = audio.info
            result["audio_info"]["length_seconds"] = getattr(info, "length", None)
            result["audio_info"]["bitrate"] = getattr(info, "bitrate", None)
            result["audio_info"]["sample_rate"] = getattr(info, "sample_rate", None)
            result["audio_info"]["channels"] = getattr(info, "channels", None)

        # Tag data
        if audio.tags:
            for key, value in audio.tags.items():
                try:
                    if isinstance(value, list):
                        result["fields"][str(key)] = str(value[0]) if value else ""
                    else:
                        result["fields"][str(key)] = str(value)
                except Exception:
                    result["fields"][str(key)] = "(binary data)"
    except Exception as exc:
        logger.debug(f"mutagen read error for {path}: {exc}")

    return result


def _write_mutagen(path, fields):
    """Write audio metadata using mutagen."""
    if not HAS_MUTAGEN:
        return {"success": False, "message": "mutagen not available."}

    try:
        audio = mutagen.File(path, easy=True)
        if audio is None:
            return {"success": False, "message": "Unsupported audio format."}

        for key, value in fields.items():
            try:
                audio[key] = value
            except Exception:
                pass

        audio.save()
        return {"success": True, "message": f"Updated {len(fields)} audio tag(s)."}
    except Exception as exc:
        return {"success": False, "message": f"mutagen write failed: {exc}"}


def _strip_mutagen(path):
    """Strip audio metadata using mutagen."""
    if not HAS_MUTAGEN:
        return {"success": False, "message": "mutagen not available."}

    try:
        audio = mutagen.File(path)
        if audio is None:
            return {"success": False, "message": "Unsupported audio format."}

        audio.delete()
        audio.save()
        return {"success": True, "message": "Audio metadata stripped."}
    except Exception as exc:
        return {"success": False, "message": f"mutagen strip failed: {exc}"}
