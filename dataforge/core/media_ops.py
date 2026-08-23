import os
import re
import shutil
import tempfile
from PIL import Image
from .logger import logger
try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    PdfReader = None
    PdfWriter = None

Image.MAX_IMAGE_PIXELS = 100_000_000
MAX_PDF_PAGES = 10_000


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


def _compress_report(input_path, output_path, quality, dry_run=False, cancelled=False, ratio=None, message=""):
    return {
        "operation": "compress_pdf",
        "input_path": input_path,
        "output_path": output_path,
        "quality": quality,
        "dry_run": dry_run,
        "cancelled": cancelled,
        "ratio": ratio,
        "message": message,
        "success": ratio is not None or dry_run,
    }


def _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=False, message=""):
    return {
        "operation": "convert_pdf",
        "input_path": input_path,
        "output_path": output_path,
        "to": to,
        "dry_run": dry_run,
        "cancelled": cancelled,
        "success": success,
        "message": message,
    }


def _sanitize_base_name(name):
    # keep alnum, dot, dash, underscore; replace others with _
    s = re.sub(r'[^a-zA-Z0-9._-]', '_', name or "output")
    s = re.sub(r'_+', '_', s).strip('._')
    return s[:80] or "output"


def merge_pdfs(file_paths, output_path, dry_run=False, progress_callback=None, cancel_token=None):
    """Merge list of PDF paths into one. Hardened against crashes."""
    if not PdfWriter:
        raise ImportError("pypdf is required for PDF operations")

    writer = PdfWriter()
    total = len(file_paths or [])
    merged = 0
    failed_paths = []
    readers = []  # keep open file handles until writer.write

    # Validate output_path dir exists handling
    out_dir = os.path.dirname(os.path.abspath(output_path)) if output_path else ""
    # Do not create dir yet for dry_run, but validate not overwriting input handled per-file

    try:
        for index, path in enumerate(file_paths or [], start=1):
            if cancel_token and cancel_token.is_set():
                return _merge_report(output_path, total, merged, dry_run=dry_run, cancelled=True, failed_paths=failed_paths)

            # Validate path
            if not path or not os.path.exists(path):
                logger.error(f"PDF not found: {path}")
                failed_paths.append(path)
                if progress_callback:
                    try:
                        progress_callback(index, total, "Merging PDFs...")
                    except Exception:
                        pass
                continue

            # Avoid self-overwrite
            try:
                if output_path and os.path.abspath(path) == os.path.abspath(output_path):
                    logger.error(f"PDF output same as input, skipping: {path}")
                    failed_paths.append(path)
                    if progress_callback:
                        try:
                            progress_callback(index, total, "Merging PDFs...")
                        except Exception:
                            pass
                    continue
            except Exception:
                pass

            try:
                f = open(path, 'rb')
                readers.append(f)
                try:
                    reader = PdfReader(f)
                    if getattr(reader, "is_encrypted", False):
                        try:
                            # try empty password
                            reader.decrypt("")
                            if getattr(reader, "is_encrypted", False):
                                raise ValueError("Encrypted PDF cannot be opened without password")
                        except Exception as e:
                            logger.error(f"PDF encrypted {path}: {e}")
                            failed_paths.append(path)
                            continue
                    try:
                        num_pages = len(reader.pages)
                    except Exception as e:
                        logger.error(f"Error counting pages {path}: {e}")
                        failed_paths.append(path)
                        continue
                    if num_pages > MAX_PDF_PAGES:
                        logger.error(f"PDF {path} has {num_pages} pages (max {MAX_PDF_PAGES}); skipping.")
                        failed_paths.append(path)
                        continue
                    if not dry_run:
                        for page in reader.pages:
                            try:
                                writer.add_page(page)
                            except Exception as e:
                                logger.error(f"Error adding page from {path}: {e}")
                                # don't count as merged? but continue
                                continue
                    merged += 1
                except Exception as e:
                    logger.error(f"Error reading {path}: {e}")
                    failed_paths.append(path)
                    continue
            except Exception as e:
                logger.error(f"Error opening {path}: {e}")
                failed_paths.append(path)
                continue

            if progress_callback:
                try:
                    progress_callback(index, total, "Merging PDFs...")
                except Exception:
                    pass

        if dry_run:
            return _merge_report(output_path, total, merged, dry_run=True, failed_paths=failed_paths)

        if cancel_token and cancel_token.is_set():
            return _merge_report(output_path, total, merged, dry_run=dry_run, cancelled=True, failed_paths=failed_paths)

        # Ensure output dir exists
        if out_dir and not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception as e:
                logger.error(f"Could not create output dir {out_dir}: {e}")
                # return failed?
                return _merge_report(output_path, total, merged, dry_run=False, failed_paths=failed_paths)

        # If no page was added and merged==0, still create empty? Write empty writer (will be minimal)
        # Ensure we don't write if merged==0 and failed == total? Still write empty file to indicate?
        try:
            with open(output_path, "wb") as out:
                writer.write(out)
        except Exception as e:
            logger.error(f"Error writing merged PDF {output_path}: {e}")
            raise

        return _merge_report(output_path, total, merged, dry_run=False, failed_paths=failed_paths)
    finally:
        for fh in readers:
            try:
                fh.close()
            except Exception:
                pass


def split_pdf(path, output_dir, dry_run=False, progress_callback=None, cancel_token=None):
    """Split PDF into single pages. Returns report dict."""
    if not PdfReader:
        raise ImportError("pypdf is required for PDF operations")

    if cancel_token and cancel_token.is_set():
        return _split_report(path, output_dir, 0, [], dry_run=dry_run, cancelled=True)

    # Validate input
    if not path or not os.path.exists(path):
        return {"error": f"File not found: {path}", "pages": [], "source_path": path, "output_dir": output_dir}

    # Handle encrypted / read errors gracefully
    f = None
    try:
        f = open(path, 'rb')
        try:
            reader = PdfReader(f)
            if getattr(reader, "is_encrypted", False):
                try:
                    reader.decrypt("")
                    if getattr(reader, "is_encrypted", False):
                        return {"error": "Encrypted PDF cannot be opened", "pages": [], "source_path": path, "output_dir": output_dir}
                except Exception as e:
                    return {"error": f"Encrypted PDF: {e}", "pages": [], "source_path": path, "output_dir": output_dir}
            try:
                total_pages = len(reader.pages)
            except Exception as e:
                return {"error": f"Error reading PDF: {e}", "pages": [], "source_path": path, "output_dir": output_dir}
            if total_pages > MAX_PDF_PAGES:
                return {"error": f"PDF has {total_pages} pages (max {MAX_PDF_PAGES})", "pages": []}
        except Exception as e:
            return {"error": f"Error reading PDF: {e}", "pages": [], "source_path": path, "output_dir": output_dir}

        # Sanitize base name
        base_name = os.path.splitext(os.path.basename(path))[0]
        base_name = _sanitize_base_name(base_name)

        # Ensure output dir
        if not dry_run:
            if output_dir and not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir, exist_ok=True)
                except Exception as e:
                    return {"error": f"Could not create output dir: {e}", "pages": []}

        generated = []
        # Need to keep reader open while generating? We already have f open and reader pages in memory; we can copy pages
        # For each page, create writer and write; keep reader alive until loop ends
        for i, page in enumerate(reader.pages):
            out_name = f"{base_name}_page_{i+1}.pdf"
            out_path = os.path.join(output_dir or os.path.dirname(os.path.abspath(path)), out_name)
            generated.append(out_path)

            if cancel_token and cancel_token.is_set():
                return _split_report(path, output_dir, total_pages, generated, dry_run=dry_run, cancelled=True)

            if not dry_run:
                try:
                    writer = PdfWriter()
                    try:
                        writer.add_page(page)
                    except Exception as e:
                        logger.error(f"Error adding page {i+1} from {path}: {e}")
                        continue
                    # sanitize ensures safe path; write
                    # Ensure output_dir exists (already)
                    with open(out_path, "wb") as out:
                        writer.write(out)
                except Exception as e:
                    logger.error(f"Error writing split page {out_path}: {e}")
                    # continue but keep entry in generated? Maybe keep but log
                    continue

            if progress_callback:
                try:
                    progress_callback(i + 1, total_pages, "Splitting PDF...")
                except Exception:
                    pass

        return _split_report(path, output_dir, total_pages, generated, dry_run=dry_run)
    finally:
        if f is not None:
            try:
                f.close()
            except Exception:
                pass


def compress_pdf(input_path, output_path, quality='medium', dry_run=False, progress_callback=None, cancel_token=None):
    """Compress PDF. Quality: low/medium/high. Returns report with ratio."""
    if not PdfWriter or not PdfReader:
        return _compress_report(input_path, output_path, quality, dry_run=dry_run, cancelled=False, ratio=None, message="pypdf not installed")

    if cancel_token and cancel_token.is_set():
        return _compress_report(input_path, output_path, quality, dry_run=dry_run, cancelled=True, ratio=None, message="cancelled")

    if not input_path or not os.path.exists(input_path):
        return _compress_report(input_path, output_path, quality, dry_run=dry_run, cancelled=False, ratio=None, message=f"File not found: {input_path}")

    if dry_run:
        # Estimate ratio without writing
        try:
            os.path.getsize(input_path)
        except Exception:
            pass
        # fake ratio for preview
        ratio_map = {"low": 0.5, "medium": 0.7, "high": 0.9}
        ratio = ratio_map.get(quality, 0.7)
        return _compress_report(input_path, output_path, quality, dry_run=True, cancelled=False, ratio=ratio, message="dry run")

    # Ensure output dir
    out_dir = os.path.dirname(os.path.abspath(output_path)) if output_path else ""
    if out_dir and not os.path.exists(out_dir):
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            return _compress_report(input_path, output_path, quality, dry_run=False, cancelled=False, ratio=None, message=str(e))

    # Avoid overwriting input if same path? allow but we will handle via temp
    readers = []
    try:
        if progress_callback:
            try:
                progress_callback(0, 1, "Compressing PDF...")
            except Exception:
                pass

        if cancel_token and cancel_token.is_set():
            return _compress_report(input_path, output_path, quality, dry_run=False, cancelled=True, ratio=None, message="cancelled")

        f = open(input_path, 'rb')
        readers.append(f)
        reader = PdfReader(f)
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
                if getattr(reader, "is_encrypted", False):
                    return _compress_report(input_path, output_path, quality, dry_run=False, cancelled=False, ratio=None, message="Encrypted PDF cannot be compressed")
            except Exception as e:
                return _compress_report(input_path, output_path, quality, dry_run=False, cancelled=False, ratio=None, message=str(e))

        writer = PdfWriter()
        for page in reader.pages:
            if cancel_token and cancel_token.is_set():
                return _compress_report(input_path, output_path, quality, dry_run=False, cancelled=True, ratio=None, message="cancelled")
            try:
                writer.add_page(page)
            except Exception:
                # fallback: try add blank?
                continue
            # try compress content streams per page if available
            try:
                # New pypdf: page.compress_content_streams()
                if hasattr(writer.pages[-1], "compress_content_streams"):
                    writer.pages[-1].compress_content_streams()
            except Exception:
                pass

        # Writer-level compress if available
        try:
            if hasattr(writer, "compress_content_streams"):
                writer.compress_content_streams()
        except Exception:
            pass

        # Write to temp then move
        tmp_path = output_path + ".tmp"
        try:
            with open(tmp_path, "wb") as out:
                writer.write(out)
        except Exception as e:
            return _compress_report(input_path, output_path, quality, dry_run=False, cancelled=False, ratio=None, message=str(e))

        # Compute ratio
        try:
            orig = os.path.getsize(input_path)
            comp = os.path.getsize(tmp_path)
            ratio = comp / orig if orig else 1.0
        except Exception:
            ratio = None

        # Move to final (atomic)
        try:
            # ensure not same file
            if os.path.abspath(tmp_path) != os.path.abspath(output_path):
                try:
                    os.replace(tmp_path, output_path)
                except OSError:
                    shutil.move(tmp_path, output_path)
            else:
                # same? just already written
                pass
        except Exception as e:
            return _compress_report(input_path, output_path, quality, dry_run=False, cancelled=False, ratio=ratio, message=str(e))

        if progress_callback:
            try:
                progress_callback(1, 1, "Compressed")
            except Exception:
                pass

        return _compress_report(input_path, output_path, quality, dry_run=False, cancelled=False, ratio=ratio, message="compressed")
    except Exception as e:
        logger.error(f"Error compressing {input_path}: {e}")
        return _compress_report(input_path, output_path, quality, dry_run=False, cancelled=False, ratio=None, message=str(e))
    finally:
        for fh in readers:
            try:
                fh.close()
            except Exception:
                pass
        # cleanup tmp if left
        try:
            tmp_candidate = output_path + ".tmp"
            if os.path.exists(tmp_candidate):
                os.remove(tmp_candidate)
        except Exception:
            pass


def convert_pdf(input_path, output_path, to='jpg', dry_run=False, progress_callback=None, cancel_token=None):
    """Convert PDF to other formats. Lazy imports, returns success dict not crash."""
    to = (to or 'jpg').lower().strip()
    if to == 'jpeg':
        to = 'jpg'
    if to not in ('jpg', 'docx', 'xlsx'):
        return _convert_pdf_report(input_path, output_path, to, dry_run=dry_run, cancelled=False, success=False, message=f"Unsupported conversion target: {to}")

    if cancel_token and cancel_token.is_set():
        return _convert_pdf_report(input_path, output_path, to, dry_run=dry_run, cancelled=True, success=False, message="cancelled")

    if not input_path or not os.path.exists(input_path):
        return _convert_pdf_report(input_path, output_path, to, dry_run=dry_run, cancelled=False, success=False, message=f"File not found: {input_path}")

    if dry_run:
        # For jpg, estimate page count; for docx/xlsx just single output
        if to == 'jpg':
            # Try pypdf to count pages without full render
            try:
                if PdfReader:
                    with open(input_path, 'rb') as f:
                        r = PdfReader(f)
                        pages = len(r.pages)
                        # DRY: return list of jpgs? We return single output_path for simplicity
                        return _convert_pdf_report(input_path, output_path, to, dry_run=True, cancelled=False, success=True, message=f"Would convert {pages} pages to JPG")
            except Exception:
                pass
            return _convert_pdf_report(input_path, output_path, to, dry_run=True, cancelled=False, success=True, message="Would convert to JPG")
        else:
            return _convert_pdf_report(input_path, output_path, to, dry_run=True, cancelled=False, success=True, message=f"Would convert to {to}")

    # Ensure output dir exists
    out_dir = os.path.dirname(os.path.abspath(output_path)) if output_path else ""
    if out_dir and not os.path.exists(out_dir):
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=False, message=str(e))

    if to == 'jpg':
        # require pymupdf
        try:
            import pymupdf as fitz  # type: ignore
        except ImportError:
            try:
                import fitz  # type: ignore
            except ImportError:
                return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=False, message="Install pymupdf to convert PDF to JPG (pip install pymupdf)")
        if cancel_token and cancel_token.is_set():
            return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=True, success=False, message="cancelled")
        try:
            # Use fitz to render
            doc = fitz.open(input_path)
            try:
                n = len(doc)
                if progress_callback:
                    try:
                        progress_callback(0, n or 1, "Converting PDF to JPG...")
                    except Exception:
                        pass
                # If output_path is a file, treat as base for multiple pages? For simplicity, if n>1, create files with _page_N suffix
                base, ext = os.path.splitext(output_path)
                if n == 1:
                    out_paths = [output_path]
                else:
                    # output_path may be dir? If ext is empty and path is dir, use dir
                    if os.path.isdir(output_path):
                        base_dir = output_path
                        base_name = _sanitize_base_name(os.path.splitext(os.path.basename(input_path))[0])
                        out_paths = [os.path.join(base_dir, f"{base_name}_page_{i+1}.jpg") for i in range(n)]
                    elif ext.lower() in ('.jpg', '.jpeg'):
                        # base without ext
                        out_paths = [f"{base}_page_{i+1}.jpg" if n > 1 else output_path for i in range(n)]
                    else:
                        # output_path without extension -> treat as prefix
                        out_paths = [f"{output_path}_page_{i+1}.jpg" for i in range(n)]

                for i, page in enumerate(doc):
                    if cancel_token and cancel_token.is_set():
                        return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=True, success=False, message="cancelled")
                    pix = page.get_pixmap()
                    out_p = out_paths[i] if i < len(out_paths) else out_paths[0]
                    # ensure dir
                    od = os.path.dirname(os.path.abspath(out_p))
                    if od and not os.path.exists(od):
                        os.makedirs(od, exist_ok=True)
                    pix.save(out_p)
                    if progress_callback:
                        try:
                            progress_callback(i + 1, n, "Converting PDF to JPG...")
                        except Exception:
                            pass
                return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=True, message=f"Converted {n} pages")
            finally:
                try:
                    doc.close()
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Error converting PDF to JPG {input_path}: {e}")
            return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=False, message=str(e))

    elif to == 'docx':
        try:
            from pdf2docx import Converter  # type: ignore
        except ImportError:
            return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=False, message="Install pdf2docx to convert PDF to Word (pip install pdf2docx)")
        if cancel_token and cancel_token.is_set():
            return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=True, success=False, message="cancelled")
        try:
            if progress_callback:
                try:
                    progress_callback(0, 1, "Converting PDF to DOCX...")
                except Exception:
                    pass
            cv = Converter(input_path)
            try:
                cv.convert(output_path)
                cv.close()
            except Exception:
                try:
                    cv.close()
                except Exception:
                    pass
                raise
            if progress_callback:
                try:
                    progress_callback(1, 1, "Converted")
                except Exception:
                    pass
            return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=True, message="Converted to DOCX")
        except Exception as e:
            logger.error(f"Error converting PDF to DOCX {input_path}: {e}")
            return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=False, message=str(e))

    elif to == 'xlsx':
        # Try tabula or camelot; both require Java/Ghostscript; we treat as optional
        # First try tabula-py
        tabula = None
        try:
            import tabula as tabula  # type: ignore
        except ImportError:
            tabula = None
        if tabula is not None:
            try:
                if progress_callback:
                    try:
                        progress_callback(0, 1, "Converting PDF to XLSX...")
                    except Exception:
                        pass
                # tabula.read_pdf returns DataFrames; we convert to excel
                dfs = tabula.read_pdf(input_path, pages="all", multiple_tables=True)
                # Need openpyxl or xlsxwriter; use pandas
                import pandas as pd  # type: ignore
                if not dfs:
                    return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=False, message="No tables found in PDF")
                # Combine sheets?
                with pd.ExcelWriter(output_path) as writer:
                    for idx, df in enumerate(dfs):
                        df.to_excel(writer, sheet_name=f"Table_{idx+1}", index=False)
                if progress_callback:
                    try:
                        progress_callback(1, 1, "Converted")
                    except Exception:
                        pass
                return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=True, message=f"Converted {len(dfs)} tables")
            except Exception as e:
                logger.error(f"Error converting PDF to XLSX via tabula {input_path}: {e}")
                return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=False, message=str(e))
        # Try camelot fallback
        try:
            import camelot  # type: ignore
        except ImportError:
            return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=False, message="Install tabula-py or camelot to convert PDF to Excel (pip install tabula-py)")
        try:
            tables = camelot.read_pdf(input_path, pages="all")
            import pandas as pd
            with pd.ExcelWriter(output_path) as writer:
                for idx, t in enumerate(tables):
                    t.df.to_excel(writer, sheet_name=f"Table_{idx+1}", index=False)
            return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=True, message=f"Converted {len(tables)} tables")
        except Exception as e:
            return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=False, message=str(e))

    return _convert_pdf_report(input_path, output_path, to, dry_run=False, cancelled=False, success=False, message="Unhandled")

def convert_image(path, target_format, resize_pct=100, dry_run=False, progress_callback=None, cancel_token=None, output_dir=None, quality=None, rotate=None, preserve_exif=True):
    """
    Convert image format and optionally resize.
    target_format: 'PNG', 'JPEG', 'WEBP'
    Hardened: copy before thread to avoid malloc corruption.
    """
    if cancel_token is not None and cancel_token.is_set():
        return {"cancelled": True, "path": path, "message": "cancelled"}
    if progress_callback:
        try:
            progress_callback(0, 1, f"Converting {os.path.basename(path)}...")
        except Exception:
            pass
    # Normalize target_format
    if not target_format:
        raise ValueError("target_format required")
    tf = target_format.strip().upper()
    if tf == 'JPG':
        tf = 'JPEG'
    # Map to Pillow format
    format_map = {"PNG": "PNG", "JPEG": "JPEG", "WEBP": "WEBP", "BMP": "BMP", "ICO": "ICO", "TIFF": "TIFF", "TIF": "TIFF"}
    pil_format = format_map.get(tf, tf)
    if pil_format not in format_map.values():
        # allow any format pillow supports but validate
        pil_format = tf

    try:
        # Hardened open: copy before thread reuse
        work = None
        exif_data = None
        # Extract exif before close if preserve
        with Image.open(path) as im:
            # Preserve exif if requested
            if preserve_exif:
                try:
                    exif_data = im.getexif()
                    # Some images have .info['exif']
                    if not exif_data and 'exif' in im.info:
                        exif_data = im.info['exif']
                except Exception:
                    exif_data = None
            try:
                im.load()
            except Exception:
                pass
            # Thread-safe copy
            try:
                work = im.copy()
                # Ensure work has loaded data
                work.load()
            except Exception as e:
                # fallback to use im directly but copy again
                logger.error(f"Error copying image {path}: {e}")
                work = im.copy() if hasattr(im, 'copy') else im

        if work is None:
            raise OSError(f"Could not load image: {path}")

        # Handle RGBA to RGB for JPEG
        try:
            if pil_format in ('JPEG', 'JPG') and work.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', work.size, (255, 255, 255))
                # Use alpha channel as mask
                try:
                    alpha = work.split()[-1]
                    background.paste(work, mask=alpha)
                except Exception:
                    # fallback convert
                    background.paste(work)
                # Close old work if different
                try:
                    work.close()
                except Exception:
                    pass
                work = background
            elif pil_format == 'JPEG' and work.mode == 'P':
                # Convert palette to RGB
                try:
                    work = work.convert('RGB')
                except Exception:
                    pass
            elif pil_format == 'JPEG' and work.mode not in ('RGB', 'L'):
                try:
                    work = work.convert('RGB')
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Error handling mode conversion {path}: {e}")

        # Rotate if requested
        if rotate is not None and int(rotate) != 0:
            try:
                rot = int(rotate) % 360
                if rot != 0:
                    # Keep expand True to avoid cropping
                    work = work.rotate(rot, expand=True)
            except Exception as e:
                logger.error(f"Error rotating {path}: {e}")

        # Resize
        if resize_pct != 100 and resize_pct is not None:
            try:
                w, h = work.size
                new_w = max(1, int(w * (float(resize_pct) / 100.0)))
                new_h = max(1, int(h * (float(resize_pct) / 100.0)))
                # Use copy before resize is already done; operate on work
                work = work.resize((new_w, new_h), Image.Resampling.LANCZOS)
            except Exception as e:
                logger.error(f"Error resizing {path}: {e}")

        # Check cancel before save
        if cancel_token is not None and cancel_token.is_set():
            if work:
                try:
                    work.close()
                except Exception:
                    pass
            return {"cancelled": True, "path": path, "message": "cancelled"}

        # Determine output path
        head, tail = os.path.split(path)
        name = os.path.splitext(tail)[0]
        # sanitize name
        name = _sanitize_base_name(name)
        # Determine extension (preserve lowercased target; JPEG -> jpeg to satisfy legacy test)
        ext_map = {"JPEG": "jpeg", "PNG": "png", "WEBP": "webp", "BMP": "bmp", "ICO": "ico", "TIFF": "tiff"}
        out_ext = ext_map.get(pil_format, pil_format.lower())
        # If original target was 'JPG', keep 'jpg' instead of 'jpeg'
        if target_format.strip().lower() == "jpg":
            out_ext = "jpg"
        out_name = f"{name}.{out_ext}"
        dest_dir = output_dir if output_dir else head
        # Ensure dest_dir exists
        if dest_dir and not os.path.exists(dest_dir):
            try:
                os.makedirs(dest_dir, exist_ok=True)
            except Exception as e:
                logger.error(f"Could not create dest dir {dest_dir}: {e}")
                raise

        out_path = os.path.join(dest_dir or ".", out_name)

        # Avoid overwriting source if same path and format unchanged? Still allow but temp handling avoids corruption
        # If dry_run just return report
        if dry_run:
            if progress_callback:
                try:
                    progress_callback(1, 1, "Converted")
                except Exception:
                    pass
            # Close work
            try:
                work.close()
            except Exception:
                pass
            return _convert_report(path, out_path, pil_format, resize_pct, dry_run=True)

        if cancel_token is not None and cancel_token.is_set():
            try:
                work.close()
            except Exception:
                pass
            return {"cancelled": True, "path": path, "message": "cancelled"}

        save_kwargs = {}
        if pil_format == 'JPEG':
            q = int(quality) if quality is not None else 90
            q = max(1, min(95, q))
            save_kwargs['quality'] = q
            save_kwargs['optimize'] = True
            if preserve_exif and exif_data:
                try:
                    # exif_data may be Exif object; convert to bytes if needed
                    if hasattr(exif_data, 'tobytes'):
                        # Need to handle empty
                        b = exif_data.tobytes()
                        if b:
                            save_kwargs['exif'] = b
                    elif isinstance(exif_data, bytes):
                        save_kwargs['exif'] = exif_data
                except Exception:
                    pass
        elif pil_format == 'WEBP':
            q = int(quality) if quality is not None else 80
            save_kwargs['quality'] = max(1, min(100, q))
        elif pil_format == 'PNG':
            # preserve exif for PNG via info? Pillow PNG doesn't support exif same way but we can ignore
            pass

        # Save via temp + atomic move to avoid EXDEV and partial files
        # Create temp in dest_dir
        tmp_fd, tmp_path = tempfile.mkstemp(dir=dest_dir or None, suffix=f".{out_ext}.tmp")
        os.close(tmp_fd)
        # Remove empty file created by mkstemp to let PIL create
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        # PIL will create tmp_path; ensure dir exists
        try:
            work.save(tmp_path, format=pil_format, **save_kwargs)
        except Exception as e:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            try:
                work.close()
            except Exception:
                pass
            logger.error(f"Error saving {tmp_path}: {e}")
            raise

        # Close work
        try:
            work.close()
        except Exception:
            pass

        # Atomic move to final
        try:
            # If out_path same as tmp_path? not.
            # Ensure not overwriting with same inode? Use replace
            try:
                os.replace(tmp_path, out_path)
            except OSError as e:
                # EXDEV fallback
                if getattr(e, 'errno', None) == 18 or 'cross-device' in str(e).lower() or 'Invalid cross-device' in str(e):
                    shutil.move(tmp_path, out_path)
                else:
                    # try shutil
                    shutil.move(tmp_path, out_path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise

        if progress_callback:
            try:
                progress_callback(1, 1, "Converted")
            except Exception:
                pass
        return _convert_report(path, out_path, pil_format, resize_pct, dry_run=False)
    except (OSError, ValueError) as e:
        logger.error(f"Error converting {path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error converting {path}: {e}")
        raise
