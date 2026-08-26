# Ticket TICK-902 — Metadata EXIF write/strip cross-device & 0 succeeded

> **Wave 9** | **Domain:** Modules / Metadata | **Depends on:** None
> **Source:** user report `Metadata write completed 0 succeeded, when edit. Cannot strip metadata or gps metadata Stripped 0, failed 1: Pillow strip failed: [Errno 18] Invalid cross-device link: '/tmp/tmp0vofkz5f.png' -> '/home/crowne/Imágenes/Capturas de pantalla/Captura de pantalla_20260810_160718.png'` + `dataforge/modules/metadata.py:538-562 _strip_pillow` + `dataforge/modules/cleaner.py:1` + `dataforge/ui/views/metadata_view.py:618`

---

## Your Assignment

```
TICKET_ID: TICK-902
WAVE: 9
TITLE: Metadata EXIF write/strip cross-device & 0 succeeded
```

**Exclusive write files (SOLE writer for Wave 9):**
- `dataforge/modules/metadata.py`
- `dataforge/modules/cleaner.py`
- `dataforge/ui/views/metadata_view.py`

**Read-only references (do not edit):**
- `dataforge/core/logger.py`
- `dataforge/core/config.py`
- `dataforge/ui/job_manager.py`
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

**Test target:** `tests/test_metadata_cross_device.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_metadata_cross_device.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` Metadata & EXIF section
- `docs/ARCHITECTURE.md` §Metadata
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `modules/metadata.py`, `modules/cleaner.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-902"
title: "Metadata EXIF write/strip cross-device & 0 succeeded"
type: "Bugfix"
execution_wave: 9
depends_on: []
scope:
  domain: "Modules / Metadata"
  exclusive_write_files:
    - "dataforge/modules/metadata.py"
    - "dataforge/modules/cleaner.py"
    - "dataforge/ui/views/metadata_view.py"
  read_only_references:
    - "dataforge/core/logger.py"
    - "dataforge/core/config.py"
    - "dataforge/ui/job_manager.py"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
architectural_context:
  existing_symbols_to_use:
    - "metadata.py: MetadataEngine.read_metadata/write_metadata/remove_metadata, _strip_pillow, _strip_exiftool, _write_exiftool, _has_exiftool"
    - "cleaner.py: MetadataCleaner (thin shim over MetadataEngine)"
    - "metadata_view.py: MetadataView, _strip_worker, _write_worker, _on_strip_complete, _on_write_complete"
  breaking_changes: "None — strip/write fixes, cross-device fallback, progress parity"
requirements:
  summary: |
    Two user-visible failures:

    1) Edit metadata shows `Metadata write completed 0 succeeded` when edit (dry_run vs real path):
       metadata_view.py _write_field collects 1 selected path but MetadataEngine.write_metadata returns success only if exiftool exists; else _write_pillow returns hardcoded {"success": False, "message": "Pillow write not supported"} and _write_mutagen may silently fail. The view counts success = sum(r.get("success")) so shows 0 succeeded even though dialog said Yes. Also write_metadata dry_run path not used in preview-confirm flow for edit (unlike cleaner which has preview_confirm).

    2) Strip fails with cross-device link:
       `Stripped 0, failed 1: Pillow strip failed: [Errno 18] Invalid cross-device link: '/tmp/tmp0vofkz5f.png' -> '/home/crowne/Imágenes/.../Captura...'`
       _strip_pillow does: mkstemp in /tmp (tmp_path) -> clean_img.save(temp_path) -> os.replace(temp_path, path). When path is on different mount (/home on fuseblk /run/media, /tmp on tmpfs), os.replace does cross-device rename → Errno 18. Same bug in _strip_pypdf (temp pdf) and cleaner shim. Also stripping GPS via MetadataEngine.remove_metadata(fields=gps_fields) still calls _strip_exiftool if available, but if exiftool missing falls to _strip_pillow which strips *all* not just GPS, and fails cross-device.

       Additional: strip on screenshot png with Pillow: img.getdata() + Image.new + putdata loses palette/transparency and format for PNG withalpha, and doesn't preserve ICC.

    Fix:
    * metadata.py _strip_pillow: create temp file *in same directory* as source, not system /tmp. Use tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path))) + os.replace stays same-device. If that dir not writable, fallback to /tmp then shutil.copyfile+os.unlink (copy not rename) to avoid EXDEV. Ensure clean_img.save respects original format + preserve exif-less save via img.copy() + info stripping, not getdata loop. Use shutil.copyfile for atomic with SameFileError handling. Wrap in try/finally unlink temp on error.
    * metadata.py _strip_pypdf: same dir temp file + shutil fallback.
    * metadata.py _strip_exiftool: exiftool -overwrite_original already avoids rename, keep, but ensure it handles gps_fields subset correctly (Pillow fallback only when exiftool missing AND ext matches, and for GPS-only strip, do selective tag removal via exiftool: "-GPS*=" not full -all=).
    * metadata.py write_metadata: when exiftool missing, return explicit error "Install exiftool for write support" but metadata_view must surface that as warning, not silent 0. For Pillow write, implement limited JPEG EXIF write via piexif fallback if available, else return success False with actionable message. Ensure metadata_view _write_worker checks cancel_token per path and shows per-file message.
    * metadata.py remove_metadata: add shutil fallback on EXDEV, add cancel_token/progress_callback param pass-through.
    * cleaner.py: keep shim but ensure it delegates with same cross-device safety (imports fixed metadata helpers).
    * metadata_view.py: fix _on_write_complete and _on_strip_complete counting: show success/failed + per-file error list, not just "Stripped: X | Failed: Y". Ensure _strip_selected/_strip_gps_selected pass cancel_token + progress, and GPS-only strip calls remove_metadata(fields=gps_fields) not strip all. Ensure edit flow mirrors cleaner preview-confirm: after _write_worker, refresh preview for selected item via _on_file_select or update item_metadata_map. Add handling for dry_run preview if needed (optional).
    * Handle filenames with spaces/non-ASCII (`Imágenes`, `Capturas de pantalla`) — subprocess.run args must be list with path as separate arg, already is, but ensure Pillow open handles utf8.

    Keep MetadataCleaner as shim (TICK-204) — do not duplicate logic.
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
    - "dataforge/modules/metadata.py:538"
    - "dataforge/modules/cleaner.py:1"
  acceptance_criteria:
    - "GIVEN png on different mount (/home vs /tmp) WHEN _strip_pillow called THEN succeeds via same-dir temp + shutil copy fallback, no Errno 18, file stripped and still openable"
    - "GIVEN pdf strip on different mount WHEN _strip_pypdf called THEN succeeds similarly"
    - "GIVEN edit metadata with exiftool missing WHEN write_metadata called for JPEG THEN returns success False with actionable message, and view shows '0 succeeded' with 'Install exiftool' detail (not silent)"
    - "GIVEN GPS-only strip WHEN exiftool present THEN only GPS tags cleared, other EXIF preserved (verify via read_metadata before/after)"
    - "GIVEN filename with spaces/utf8 'Imágenes/Captura de pantalla_20260810_160718.png' WHEN strip called THEN no file-not-found, succeeds"
    - "GIVEN cross-device + cancel_token set mid-batch WHEN _strip_worker runs 5 files THEN respects cancel and returns partial"
verification:
  test_target: "tests/test_metadata_cross_device.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_metadata_cross_device.py -q"
```

---

## Implementation Notes

```python
# metadata.py — same-dir temp + shutil fallback
import tempfile, shutil, os
def _strip_pillow(path):
    try:
        img = Image.open(path)
        data = list(img.getdata())  # existing logic
        clean = Image.new(img.mode, img.size); clean.putdata(data)
        # FIX:
        dir_ = os.path.dirname(os.path.abspath(path)) or "."
        fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(path)[1], dir=dir_)
        os.close(fd)
        try:
            clean.save(tmp, format=img.format)
            try:
                os.replace(tmp, path)  # same-device atomic
            except OSError as e:
                if e.errno == 18:  # EXDEV
                    shutil.copyfile(tmp, path)
                    os.unlink(tmp)
                else: raise
        finally:
            try: os.unlink(tmp)
            except: pass
    except Exception as exc:
        return {"success": False, "message": f"Pillow strip failed: {exc}"}

# Also fix _strip_pypdf similarly
# For write: if not _has_exiftool(): return {"success": False, "message": "Install exiftool..."}
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-902` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-902
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
git checkout -b fix/TICK-902-metadata-cross-device
PYTHONPATH=. python -m pytest tests/test_metadata_cross_device.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add dataforge/modules/metadata.py dataforge/modules/cleaner.py dataforge/ui/views/metadata_view.py tests/test_metadata_cross_device.py
git commit -m "fix(modules): metadata EXIF cross-device strip + 0 succeeded"
git push -u origin fix/TICK-902-metadata-cross-device
```

## Work Package YAML for TICK-902

```yaml
ticket_id: "TICK-902"
title: "Metadata EXIF write/strip cross-device & 0 succeeded"
type: "Bugfix"
execution_wave: 9
depends_on: []
scope:
  domain: "Modules / Metadata"
  exclusive_write_files:
    - "dataforge/modules/metadata.py"
    - "dataforge/modules/cleaner.py"
    - "dataforge/ui/views/metadata_view.py"
  read_only_references:
    - "dataforge/core/logger.py"
architectural_context:
  existing_symbols_to_use:
    - "metadata.py: MetadataEngine"
  breaking_changes: "None"
requirements:
  summary: "Fix cross-device strip + write 0 succeeded"
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN cross-device png THEN strip succeeds"
verification:
  test_target: "tests/test_metadata_cross_device.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_metadata_cross_device.py -q"
```
