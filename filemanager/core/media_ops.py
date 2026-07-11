import os
from PIL import Image
from .logger import logger
try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    PdfReader = None
    PdfWriter = None


def _merge_report(output_path, requested, merged, dry_run=False, cancelled=False, failed_paths=None):
    failed_paths = failed_paths or []
    return {
        "operation": "merge_pdf",
        "output_path": output_path,
        "requested": requested,
        "merged": merged,
        "failed": len(failed_paths),
        "failed_paths": failed_paths,
        "dry_run": dry_run,
        "cancelled": cancelled,
    }


def _split_report(source_path, output_dir, requested, generated_paths, dry_run=False, cancelled=False):
    return {
        "operation": "split_pdf",
        "source_path": source_path,
        "output_dir": output_dir,
        "requested": requested,
        "generated": len(generated_paths),
        "pages": generated_paths,
        "dry_run": dry_run,
        "cancelled": cancelled,
    }


def _convert_report(source_path, output_path, target_format, resize_pct, dry_run=False):
    return {
        "operation": "convert_image",
        "source_path": source_path,
        "output_path": output_path,
        "format": target_format,
        "resize_pct": resize_pct,
        "dry_run": dry_run,
    }

def merge_pdfs(file_paths, output_path, dry_run=False, progress_callback=None, cancel_token=None):
    """Merge list of PDF paths into one."""
    if not PdfWriter:
        raise ImportError("pypdf is required for PDF operations")
    
    writer = PdfWriter()
    total = len(file_paths)
    merged = 0
    failed_paths = []

    for index, path in enumerate(file_paths, start=1):
        if cancel_token and cancel_token.is_set():
            return _merge_report(output_path, total, merged, dry_run=dry_run, cancelled=True, failed_paths=failed_paths)

        try:
            reader = PdfReader(path)
            if not dry_run:
                for page in reader.pages:
                    writer.add_page(page)
            merged += 1
        except Exception as e:
            logger.error(f"Error reading {path}: {e}")
            failed_paths.append(path)
        if progress_callback:
            progress_callback(index, total, "Merging PDFs...")
            
    if dry_run:
        return _merge_report(output_path, total, merged, dry_run=True, failed_paths=failed_paths)

    with open(output_path, "wb") as f:
        writer.write(f)
    return _merge_report(output_path, total, merged, dry_run=False, failed_paths=failed_paths)

def split_pdf(path, output_dir, dry_run=False, progress_callback=None, cancel_token=None):
    """Split PDF into single pages."""
    if not PdfReader:
        raise ImportError("pypdf is required for PDF operations")
        
    reader = PdfReader(path)
    base_name = os.path.splitext(os.path.basename(path))[0]
    total_pages = len(reader.pages)
    
    generated = []
    for i, page in enumerate(reader.pages):
        out_name = f"{base_name}_page_{i+1}.pdf"
        out_path = os.path.join(output_dir, out_name)
        generated.append(out_path)

        if cancel_token and cancel_token.is_set():
            return _split_report(path, output_dir, total_pages, generated, dry_run=dry_run, cancelled=True)

        if not dry_run:
            writer = PdfWriter()
            writer.add_page(page)
            with open(out_path, "wb") as f:
                writer.write(f)

        if progress_callback:
            progress_callback(i + 1, len(reader.pages), "Splitting PDF...")
            
    return _split_report(path, output_dir, total_pages, generated, dry_run=dry_run)

def convert_image(path, target_format, resize_pct=100, dry_run=False):
    """
    Convert image format and optionally resize.
    target_format: 'PNG', 'JPEG', 'WEBP'
    """
    try:
        with Image.open(path) as img:
            # Handle RGBA to RGB for JPEG
            if target_format.upper() in ['JPEG', 'JPG'] and img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
                
            # Resize
            if resize_pct != 100:
                w, h = img.size
                new_w = int(w * (resize_pct / 100))
                new_h = int(h * (resize_pct / 100))
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            # Save
            head, tail = os.path.split(path)
            name = os.path.splitext(tail)[0]
            out_name = f"{name}.{target_format.lower()}"
            out_path = os.path.join(head, out_name)

            if dry_run:
                return _convert_report(path, out_path, target_format, resize_pct, dry_run=True)
            
            save_kwargs = {}
            if target_format.upper() == 'JPEG':
                save_kwargs['quality'] = 90
            
            img.save(out_path, format=target_format, **save_kwargs)
            return _convert_report(path, out_path, target_format, resize_pct, dry_run=False)
    except (OSError, ValueError) as e:
        logger.error(f"Error converting {path}: {e}")
        raise
