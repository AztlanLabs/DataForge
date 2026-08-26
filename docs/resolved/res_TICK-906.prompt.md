# Ticket TICK-906 — FilePreviewPanel & widgets malloc/QPainter isolation

> **Wave 9** | **Domain:** UI / Widgets | **Depends on:** None
> **Source:** user report `On MediaTools 2026-08-22 21:53:43 img preview worker malloc(): unsorted double linked list corrupted SIGABRT` + `dataforge/ui/widgets.py:439 FilePreviewPanel` + `dataforge/ui/views/media.py:184 FilePreviewPanel`, `system_cleanup.py FilePreviewPanel`, `hardware_view.py QPainter active`, `duplicates/widgets`

---

## Your Assignment

```
TICKET_ID: TICK-906
WAVE: 9
TITLE: FilePreviewPanel & widgets malloc/QPainter isolation
```

**Exclusive write files (SOLE writer for Wave 9):**
- `dataforge/ui/widgets.py`

**Read-only references (do not edit):**
- `dataforge/ui/views/media.py`
- `dataforge/ui/views/system_cleanup.py`
- `dataforge/ui/job_manager.py`
- `dataforge/core/media_ops.py`
- `dataforge/core/config.py`
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

**Test target:** `tests/test_widgets_preview.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_widgets_preview.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` Media Tools / Preview section
- `docs/ARCHITECTURE.md` §Widgets / §UI threading
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `ui/widgets.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-906"
title: "FilePreviewPanel & widgets malloc/QPainter isolation"
type: "Bugfix"
execution_wave: 9
depends_on: []
scope:
  domain: "UI / Widgets"
  exclusive_write_files:
    - "dataforge/ui/widgets.py"
  read_only_references:
    - "dataforge/ui/views/media.py"
    - "dataforge/ui/views/system_cleanup.py"
    - "dataforge/ui/job_manager.py"
    - "dataforge/core/media_ops.py"
    - "dataforge/core/config.py"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
architectural_context:
  existing_symbols_to_use:
    - "widgets.py: FilePreviewPanel, EnhancedTreeview, HexView, CollapsibleCard, attach_tooltips"
    - "widgets.py: _HAS_PYPDF, _HAS_FITZ, _HAS_CV2, _HAS_MUTAGEN, FilePreviewPanel.update_file"
    - "app.py: run_workflow, JobManager bridge (read-only)"
    - "media_ops.py: convert_image (read-only — fix in TICK-903)"
  breaking_changes: "None — hardening, no API break"
requirements:
  summary: |
    FilePreviewPanel causes heap corruption:

    ```
    2026-08-22 21:53:43 Submitted job 01M0PC1EQGW0TC90F344FDWEHC: img preview worker
    malloc(): unsorted double linked list corrupted
    SIGABRT
    ```
    And the same log appears for Image batch preview worker. The preview is used in MediaTools (img_preview), SystemCleanup (junk_preview/browser_preview), Metadata (overview_preview) — all share the same FilePreviewPanel class which renders image thumbnails, PDF first page via pymupdf, video frames via cv2, and text previews.

    Suspects in widgets.py FilePreviewPanel:

    * `update_file` is called from worker thread `img preview worker` (media.py _img_preview_worker does convert_image dry_run, but also FilePreviewPanel.update_file is triggered from `on_img_select` which runs on main thread — however TICK-903's media.py also has preview worker that may call widgets code off main thread?). If FilePreviewPanel creates QPixmap/QImage/QPainter on worker thread, that is illegal — QPixmap is not thread-safe, only QImage. The panel currently does `QPixmap.loadFromData`, `QImage`, `QPainter.begin` in update_file which if invoked from ManagedWorker thread will corrupt heap (malloc double linked list) and QBackingStore.

    * PIL Image opened in preview without `.copy()` / `.load()` + not closed, and cv2.VideoCapture not released, causing fd leak + double free when preview worker is cancelled and Image object still lazy.

    * Large image MAX_IMAGE_PIXELS 100M but panel tries to render full-res image into QLabel pixmap without scaling first → OOM + heap corruption.

    * EnhancedTreeview insert refresh uses QTimer.singleShot(0, _do_refresh) that calls `tree.viewport().update()` while an active QPainter from preview panel is still painting → QBackingStore active painter. Need to ensure FilePreviewPanel paint is not re-entered.

    * FilePreviewPanel lacks cancel_token awareness: when user rapidly selects 5 images, 5 preview jobs are submitted but all run, and the stale jobs' QPixmap updates race with newest selection.

    Fix (widgets.py only):

    * FilePreviewPanel.update_file must be main-thread only. If called from non-main thread (QThread.currentThread() != QApplication.instance().thread()), post via `app.post_to_main` or `QTimer.singleShot(0, ...)` to defer to main thread. Add guard at top.
    * Ensure all QPixmap/QPainter creation is on main thread only. For image scaling, use `Image.open` + `im.copy().load()` + `im.thumbnail` on worker thread (if any), but final QPixmap conversion via `QImage` + `QPixmap.fromImage` on main thread. Currently FilePreviewPanel does everything on main thread — keep that, but ensure media.py's `_img_preview_worker` does NOT instantiate QPixmap — it should only do `convert_image` dry_run which is PIL only. Audit FilePreviewPanel not to call convert_image's PIL path that shares Image object across threads.

    * Harden preview worker cancel: add `cancel_token` param to `update_file(path, cancel_token=None)` and check before heavy ops. Keep a generation counter `self._preview_gen +=1` and ignore stale callbacks.

    * Fix heap corruption: in image preview, do `with Image.open(path) as im: im.load(); thumb = im.copy(); thumb.thumbnail((512,512), Image.Resampling.LANCZOS); data = thumb.tobytes?` But for QLabel, convert via QImage: `qimg = QImage(thumb.tobytes(), w, h, QImage.Format_RGB888)` is unsafe if thumb is RGBA. Use `ImageQt` or `qimage = QImage(path)` via file, or `pil_to_qpixmap` helper that correctly handles mode conversion (RGBA→RGB) and ensures data lifetime (copy). Ensure thumb closed after.

    * For PDF preview: lazy import pymupdf only on main thread, and ensure `doc = fitz.open(path); pix = doc[0].get_pixmap(matrix=fitz.Matrix(2,2)); qimg = QImage(pix.samples, pix.w, pix.h, pix.stride, QImage.Format_RGB888)` then `pix = None; doc.close()` explicitly. Not holding doc open.

    * For video preview: `cap = cv2.VideoCapture(path); ret, frame = cap.read(); cap.release()` then convert frame via `cv2.cvtColor` + QImage, release immediately.

    * Add try/except around all QPainter usage: `try: painter = QPainter(pixmap); ...; painter.end()` in finally, never leave active painter on exception. The 3x QBackingStore errors from junk/system suggest FilePreviewPanel's paintEvent left QPainter active.

    * Ensure EnhancedTreeview refresh not called from within FilePreviewPanel paint — use `self.update()` instead of `viewport().update()` when already painting.

    * Add `MAX_DISPLAY_BYTES` style guard: don't render files >50MB as image preview, show info fallback ("File too large for preview").

    Verify no QPixmap created off main thread via `QApplication.instance().thread() == QThread.currentThread()` assert.

  source_documents:
    - "docs/GUI_WORKFLOWS.md"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
    - "dataforge/ui/widgets.py:439"
    - "dataforge/ui/views/media.py:184"
  acceptance_criteria:
    - "GIVEN FilePreviewPanel.update_file called from worker thread WHEN invoked THEN defers to main thread via QTimer/post_to_main, no QPixmap creation off main thread (verified via thread check)"
    - "GIVEN rapidly selecting 10 images (spam selection) WHEN preview generation runs THEN only last selection's pixmap is shown, stale jobs ignored via generation counter, no malloc corruption"
    - "GIVEN large image (20MP) or PDF 100 pages WHEN preview rendered THEN scaled to 512px thumb before QPixmap, no OOM, not rendering full res"
    - "GIVEN no QPainter leak WHEN preview paintEvent runs and raises exception THEN QPainter.end() called in finally, no QBackingStore::endPaint active painter warning"
    - "GIVEN existing tests for widgets + media WHEN fix applied THEN still pass and new test_widgets_preview.py passes"
verification:
  test_target: "tests/test_widgets_preview.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_widgets_preview.py -q"
```

---

## Implementation Notes

```python
# widgets.py — main thread guard + generation counter
class FilePreviewPanel(QWidget):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._gen = 0

    def update_file(self, path, cancel_token=None):
        # main-thread only guard
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QThread
        if QApplication.instance() and QThread.currentThread() != QApplication.instance().thread():
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.update_file(path, cancel_token))
            return
        self._gen += 1
        gen = self._gen
        # ... heavy ops check if gen != self._gen: return (stale)
        # PIL: with Image.open(path) as im: im.load(); thumb = im.copy(); thumb.thumbnail((512,512), ...)
        # convert to QImage on main thread only:
        # qimg = QImage(thumb.tobytes(), w, h, bytesPerLine, QImage.Format_RGB888).copy() # copy to own data
        # pixmap = QPixmap.fromImage(qimg)
        # ensure painter end:
        # painter = QPainter(pixmap)
        # try: ... finally: painter.end()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            # draw pixmap
            pass
        finally:
            painter.end()
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-906` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-906
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
git checkout -b fix/TICK-906-widgets-preview-malloc
PYTHONPATH=. python -m pytest tests/test_widgets_preview.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add dataforge/ui/widgets.py tests/test_widgets_preview.py
git commit -m "fix(ui): FilePreviewPanel malloc QPainter isolation"
git push -u origin fix/TICK-906-widgets-preview-malloc
```

## Work Package YAML for TICK-906

```yaml
ticket_id: "TICK-906"
title: "FilePreviewPanel & widgets malloc/QPainter isolation"
type: "Bugfix"
execution_wave: 9
depends_on: []
scope:
  domain: "UI / Widgets"
  exclusive_write_files:
    - "dataforge/ui/widgets.py"
  read_only_references:
    - "dataforge/ui/views/media.py"
architectural_context:
  existing_symbols_to_use:
    - "widgets.py: FilePreviewPanel"
  breaking_changes: "None"
requirements:
  summary: "Fix preview malloc double linked list + QPainter active"
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN preview off main thread THEN defers"
verification:
  test_target: "tests/test_widgets_preview.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_widgets_preview.py -q"
```
