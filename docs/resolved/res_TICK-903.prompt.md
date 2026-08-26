# Ticket TICK-903 — MediaTools PDF/Image rework + preview + malloc fix

> **Wave 9** | **Domain:** Core / Media | **Depends on:** None
> **Source:** user report `When try to merge a pdf crashes. Also need a preview section where user can see pdf currently selected. Move up and move down does not work, also if select a PDF must be able to rearrange pdfs pages as also pdfs files. When try to split does crash also, review entire PDF The current tool of PDF needs a great rework and improvements, needs more features like: Merge, Split, Compress, Convert (PDF to Word, Excel, JPG). Image batch also crashes and need more features. 2026-08-22 21:53:43 img preview worker malloc(): unsorted double linked list corrupted SIGABRT` + `dataforge/core/media_ops.py:1`, `dataforge/ui/views/media.py:1`

---

## Your Assignment

```
TICKET_ID: TICK-903
WAVE: 9
TITLE: MediaTools PDF/Image rework + preview + malloc fix
```

**Exclusive write files (SOLE writer for Wave 9):**
- `dataforge/core/media_ops.py`
- `dataforge/ui/views/media.py`

**Read-only references (do not edit):**
- `dataforge/ui/widgets.py`
- `dataforge/ui/job_manager.py`
- `dataforge/core/logger.py`
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

**Test target:** `tests/test_media_tools.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_media_tools.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` Media Tools section
- `docs/ARCHITECTURE.md` §Media / §Core
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `core/media_ops.py`, `ui/views/media.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-903"
title: "MediaTools PDF/Image rework + preview + malloc fix"
type: "Feature"
execution_wave: 9
depends_on: []
scope:
  domain: "Core / Media"
  exclusive_write_files:
    - "dataforge/core/media_ops.py"
    - "dataforge/ui/views/media.py"
  read_only_references:
    - "dataforge/ui/widgets.py"
    - "dataforge/ui/job_manager.py"
    - "dataforge/core/logger.py"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
architectural_context:
  existing_symbols_to_use:
    - "media_ops.py: merge_pdfs, split_pdf, convert_image, _merge_report, _split_report"
    - "media.py: MediaView, pdf_add/up/down/merge/split, img_add/convert, on_img_select, FilePreviewPanel"
    - "widgets.py: FilePreviewPanel.update_file, EnhancedTreeview"
    - "job_manager.py: run_workflow, cancel_token, progress_callback"
  breaking_changes: "None — additive PDF compress/convert + hardening, move fixes; no breaking rename"
requirements:
  summary: |
    MediaTools is broken and weak:

    * Crashes:
      - `img preview worker malloc(): unsorted double linked list corrupted SIGABRT` when adding images / converting — likely PIL Image not closed in worker thread, or resize with Image.Resampling.LANCZOS on same Image object across threads without copy.
      - PDF merge crashes: `merge_pdfs` opens PdfReader without context, adds pages to one PdfWriter, then writer.write() without checking dry_run cancel or empty list. If input PDF is encrypted/read error, exception bubbles without per-file failed_paths handling, causing JobManager error_signal -> not caught -> SIGABRT in QThread. Also writer holds references to reader pages after reader closes (pypdf pages reference reader stream) → use-after-free.
      - PDF split crashes similarly: `PdfReader(path)` without try, MAX_PDF_PAGES check raises but not caught, and out_path generation uses unsanitized base_name.
      - `convert_image` does `background.paste(img, mask=img.split()[-1])` on RGBA then reuses same `img` variable → double linked list corruption if original is lazy-loaded and not .copy() before thread reuse. Also out_path overwrites source dir without asking dest folder.

    * Missing UX:
      - PDF tab has no preview section: need pane where user sees currently selected PDF (use FilePreviewPanel like Image tab does).
      - Move up/down does not work: _move_item uses `children.index(item)` but get_children() returns iid list, and `move(item, "", new_idx)` expects parent "" but tree is QTreeWidget top-level; TICK-803 style fix needed — verify with EnhancedTreeview.move.
      - Need rearrange not only files but also pages inside a PDF (drag pages to reorder before merge/split). Current tree only shows file path + size, not pages.
      - PDF needs rework: Merge (many→one, already), Split (one→parts, already), **Compress** (reduce size), **Convert** (PDF ↔ Word, Excel, JPG). Currently only merge/split/convert image exists.
      - Image batch crashes + needs more features: resize % only, missing rotate, quality, format options, dest folder, preserve EXIF control.

    Fix:

    * media_ops.py hardening:
      - merge_pdfs: wrap each PdfReader in `with open(path, 'rb') as f: reader = PdfReader(f)` so stream lifetime is per-file and pages are copied via `writer.add_blank_page` + copy content? Or use `writer.add_page(reader.pages[i].extract???` Actually pypdf pages need cloning: do `page = reader.pages[i]; writer.add_page(page)` but ensure reader stays open until writer.write — so collect readers list and close after write. Add per-file try/except with failed_paths, check cancel_token before each file, progress_callback per file. Handle dry_run correctly (no file write). Validate output_path dir exists, ensure not overwriting input.
      - split_pdf: same per-file open, add try for encrypted PDF (decrypt empty), handle MAX_PDF_PAGES with graceful error dict not raise, sanitize out_name via re.sub unsafe chars, ensure output_dir exists, handle dry_run page list without writing, check cancel_token per page.
      - Add compress_pdf(input_path, output_path, quality='medium', dry_run, progress, cancel_token): try pypdf compress via `writer.compress_content_streams()` or fallback to Ghostscript if available, otherwise repack with `writer.add_page` + `page.compress_content_streams()`. Return report with ratio.
      - Add convert_pdf(input_path, output_path, to='jpg'|'docx'|'xlsx', ...): for jpg use pymupdf if available (fitz) to render pages to images; for docx use pdf2docx if available else fallback error with actionable message; for xlsx use tabula/camelot fallback. Each must be lazy-import and return {"success": False, "message": "Missing dep ..."} if lib not installed, not crash.
      - convert_image: fix malloc: open with `with Image.open(path) as im: im_copy = im.copy(); im_copy.load()` then operate on copy, not original lazy stream. Close im explicitly. Handle RGBA→RGB via `im_copy.convert('RGB')` safe. Resize via `im_copy.resize(..., Image.Resampling.LANCZOS)` on copy. Save to dest folder not same as source? Add param output_dir optional; if provided, join there, else same dir but with new name. Use same-dir temp + shutil fallback for EXDEV. Respect cancel_token before save.

    * media.py UX:
      - PDF Tools tab: add QSplitter with left pdf_tree + right pdf_preview (FilePreviewPanel). Wire pdf_tree.tree.itemSelectionChanged -> pdf_preview.update_file(selected path). Show preview for selected PDF.
      - Fix Move Up/Down: debug EnhancedTreeview.move(parent="", index) — test with topLevelItem index, ensure selection_set after move, and that new_idx bounds check uses len(children) correctly. The current code is correct at first glance, so investigate if tree.get_children() returns wrong order after sorting (tree sortingEnabled True breaks manual order). Set sortingEnabled=False for pdf_tree when in manual reorder mode, or call `tree.setSortingEnabled(False)` at init and provide header click to sort.
      - Add page-level rearrange: when a PDF selected, optionally expand its pages as child rows (use pdf_tree.insert parent=file_id with page numbers). Allow drag/reorder of pages via Move Up/Down scoped to parent. On merge, respect file order + page order within file.
      - Add new QGroupBox "PDF Advanced" with buttons: Compress (opens dialog for quality + output), Convert to JPG/Word/Excel (combo + convert button). Wire via run_workflow with preview-confirm.
      - Image Batch: add dest folder Chooser, quality spin, rotate combo, preserve EXIF checkbox. Ensure img_convert_worker uses convert_image with output_dir param, not overwriting inline. Ensure on_img_select uses refresh_viewport pattern correctly.

    Keep preview_confirm flow for destructive ops (merge/split) via BaseView.confirm_preview / handle_preview_outcome if available, else use existing confirm_preview.

  source_documents:
    - "docs/GUI_WORKFLOWS.md"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
    - "dataforge/core/media_ops.py:51"
    - "dataforge/ui/views/media.py:216"
  acceptance_criteria:
    - "GIVEN 3 PDFs listed WHEN Move Up on middle item THEN order changes and persists; WHEN sorted header clicked THEN sorting disabled for manual mode and move still works"
    - "GIVEN PDF selected in tree WHEN selection changes THEN right preview panel shows PDF first page (pymupdf render or pypdf text fallback) without malloc corruption"
    - "GIVEN merge 2 PDFs (one encrypted/bad) WHEN merge_pdfs called dry_run=False THEN success dict with merged=1, failed=1, no crash, output contains only good file"
    - "GIVEN split PDF into pages WHEN split_pdf called THEN pages created in output_dir, dry_run returns page paths without writing, cancel_token aborts mid-split"
    - "GIVEN convert_image on RGBA PNG to JPEG WHEN called from worker thread 10 times rapidly THEN no malloc double linked list corruption, output RGB without crash, copy() pattern used"
    - "GIVEN new compress/convert PDF buttons WHEN clicked with missing dep THEN error dialog says 'Install pymupdf/pdf2docx' not crash"
    - "GIVEN image batch with 5 images + dest folder WHEN Convert All THEN files written to dest folder, not overwriting source, with progress_callback per image"
verification:
  test_target: "tests/test_media_tools.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_media_tools.py -q"
```

---

## Implementation Notes

```python
# media_ops.py — fix reader lifetime vs writer
def merge_pdfs(file_paths, output_path, ...):
    writer = PdfWriter()
    readers = []  # keep open handles
    try:
        for path in file_paths:
            if cancel_token and cancel_token.is_set(): return _merge_report(..., cancelled=True)
            try:
                f = open(path, 'rb')
                readers.append(f)
                reader = PdfReader(f)
                for page in reader.pages:
                    writer.add_page(page)
                merged += 1
            except Exception as e:
                failed_paths.append(path); logger.error(...)
    finally:
        # writer.write after loop then close readers
        with open(output_path, 'wb') as out:
            writer.write(out)
        for f in readers: f.close()

# convert_image — copy before thread
with Image.open(path) as im:
    im.load()
    work = im.copy()  # thread-safe copy
# then operate on work, not im

# media.py — preview splitter
self.pdf_splitter = QSplitter(Qt.Horizontal, tab)
self.pdf_splitter.addWidget(self.pdf_tree)
self.pdf_preview = FilePreviewPanel(self.pdf_splitter)
self.pdf_splitter.addWidget(self.pdf_preview)
self.pdf_tree.tree.itemSelectionChanged.connect(lambda: self.pdf_preview.update_file(self.pdf_tree.get_selected_path() or ""))
# disable sorting for manual reorder
self.pdf_tree.tree.setSortingEnabled(False)
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-903` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-903
WAVE: 9
```

## Required Reading (in order)

1. `docs/CONSOLIDATED_SPEC.md` §2–7
2. `docs/PARALLEL_BACKLOG.md` Concurrency Map + How to Work a Ticket
3. `docs/CONTRIBUTING.md` §3, §8, §10
4. Your Work Package YAML above
5. `read_only_references` files

## File Ownership

- Write only to `exclusive_write_files`. New files carry ` [NEW FILE]`.
- Central touchpoints are single-writer per wave.

## Workflow

```bash
git checkout develop && git pull origin develop
git checkout -b feat/TICK-903-media-rework
PYTHONPATH=. python -m pytest tests/test_media_tools.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add dataforge/core/media_ops.py dataforge/ui/views/media.py tests/test_media_tools.py
git commit -m "feat(media): PDF/Image rework compress convert preview hardening"
git push -u origin feat/TICK-903-media-rework
```

## Work Package YAML for TICK-903

```yaml
ticket_id: "TICK-903"
title: "MediaTools PDF/Image rework + preview + malloc fix"
type: "Feature"
execution_wave: 9
depends_on: []
scope:
  domain: "Core / Media"
  exclusive_write_files:
    - "dataforge/core/media_ops.py"
    - "dataforge/ui/views/media.py"
  read_only_references:
    - "dataforge/ui/widgets.py"
architectural_context:
  existing_symbols_to_use:
    - "media_ops.py: merge_pdfs"
  breaking_changes: "None"
requirements:
  summary: "Rework PDF merge/split/compress/convert + image batch + preview"
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN PDF merge/split THEN no crash"
verification:
  test_target: "tests/test_media_tools.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_media_tools.py -q"
```
