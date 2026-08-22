import os
from PIL import Image
from ..core.logger import logger
from .metadata import MetadataEngine

Image.MAX_IMAGE_PIXELS = 100_000_000


def remove_empty_folders(path, dry_run=True):
    """
    Remove empty folders under the given path (bottom-up).
    Returns a list of log messages describing what was (or would be) removed.
    """
    log = []
    for dirpath, dirnames, filenames in os.walk(path, topdown=False):
        if dirpath == path:
            continue
        if not os.listdir(dirpath):
            if dry_run:
                log.append(f"[DRY-RUN] Would remove empty folder: {dirpath}")
            else:
                try:
                    os.rmdir(dirpath)
                    log.append(f"Removed empty folder: {dirpath}")
                except OSError as e:
                    log.append(f"Error removing {dirpath}: {e}")
    return log


class MetadataCleaner:
    @staticmethod
    def get_metadata_info(path):
        """
        Analyzes file for metadata.
        Returns (has_metadata: bool, size_bytes: int, info: str)
        """
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.tiff', '.webp']:
                try:
                    with Image.open(path) as img:
                        exif = img.getexif()
                        if exif:
                            count = len(exif)
                            return (True, count, f"{count} tags (EXIF)")
                        if img.info:
                             # Ignore structural or non-sensitive keys
                             ignored = ['dpi', 'compression', 'srgb', 'gamma', 'aspect', 
                                        'adobe', 'adobe_transform', 'progression', 'interlace']
                             keys = [k for k in img.info.keys() if k.lower() not in ignored]
                             if keys:
                                 return (True, len(keys), f"Keys: {', '.join(keys)}")
                except Exception:
                    return (False, 0, "Error reading")
            
            elif ext == '.pdf':
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(path)
                    meta = reader.metadata
                    if meta:
                        # meta is a dictionary-like object
                        count = len(meta) if meta else 0
                        if count > 0:
                             return (True, count, f"PDF Meta: {count} keys")
                except Exception as e:
                    return (False, 0, f"Error: {e}")
            
        except Exception as e:
            logger.error(f"Error analyzing {path}: {e}")
            
        return (False, 0, "")

    @staticmethod
    def remove_metadata(path, dry_run=False):
        """
        Removes metadata from file.
        Delegates to MetadataEngine.remove_metadata.
        Returns dict with 'success' key (bool) and 'message' key (str).
        """
        return MetadataEngine.remove_metadata(path, dry_run=dry_run)
