# TICK-921 — Metadata: PNG write, exiftool detection, capability model, selective removal

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-921 |
| Wave | 12 — Operation Correctness (P1) |
| Priority | P1 — Feature gap + misleading errors |
| Depends on | Wave 11 |
| Files to modify | `dataforge/modules/metadata.py`, `dataforge/modules/cleaner.py` |
| Files to create | `tests/test_metadata_capabilities.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P1.6 |
| Validation | `python -m pytest tests/test_metadata_capabilities.py -q` |

## Context

**P1.6 — PNG write not implemented:** `_write_pillow()` at `metadata.py:572-617` only attempts JPEG+piexif. For PNG, it returns `{"success": False, "message": "Install exiftool for write support (Pillow write not supported)."}`. This is misleading — Pillow supports PNG text chunks via `PIL.PngImagePlugin.PngInfo` and eXIf via `exif=` kwarg. The capability was simply never implemented.

**P1.6 — Exiftool detection fragile:** `_has_exiftool()` at `metadata.py:46-61` uses `subprocess.run(["exiftool", "-ver"])` with `@lru_cache(maxsize=1)`. Problems: hardcoded binary name (Windows ships as `exiftool(-k).exe`), cached forever (install mid-session not detected), shells out instead of using `shutil.which()`.

**P1.6 — No PDF writer:** PDF metadata has no fallback writer even though pypdf can `writer.add_metadata()`.

**P1.6 — GPS-only falls back to strip-all:** At `metadata.py:296-316`, when GPS-only is requested without exiftool on non-JPEG images, the code falls through to `_strip_pillow()` which strips ALL metadata.

**P1.6 — Cancellation nonfunctional:** `write_metadata()` and `remove_metadata()` check cancellation only at entry, not during processing.

**P1.6 — Stale display:** After strip/write, the UI does not refresh GPS/timestamps panels (`metadata_view.py:651-666,760-784`).

## Objectives

1. Implement PNG text chunk writes via PngInfo.
2. Rework exiftool detection to use shutil.which with fallbacks.
3. Add format capability report.
4. Add pypdf metadata writer.
5. Fix GPS-only removal to never fall back to strip-all.
6. Make writes atomic.

## Implementation Guide

### Step 1: PNG write via PngInfo

```python
from PIL.PngImagePlugin import PngInfo

def _write_pillow_png(path, fields):
    img = Image.open(path)
    pnginfo = PngInfo()
    for k, v in fields.items():
        pnginfo.add_text(k, str(v))
    img.save(path, pnginfo=pnginfo)
    return {"success": True, "message": f"Wrote {len(fields)} text chunk(s) to PNG."}
```

### Step 2: Exiftool detection

```python
@lru_cache(maxsize=1)
def _has_exiftool():
    return shutil.which("exiftool") is not None

def _clear_exiftool_cache():
    _has_exiftool.cache_clear()
```

### Step 3: Capability report

```python
def get_supported_formats():
    formats = {}
    for ext in _IMAGE_EXTENSIONS:
        formats[ext] = {
            "read": HAS_PILLOW or _has_exiftool(),
            "write": _has_exiftool() or (HAS_PILLOW and ext in (".jpg", ".jpeg")),
            "write_fields": "exiftool: all; pillow: text chunks (PNG), piexif (JPEG)",
        }
    # ... PDF, audio, video
    return formats
```

### Step 4: PDF metadata writer

```python
def _write_pypdf(path, fields):
    reader = PdfReader(path)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    metadata = reader.metadata or {}
    for k, v in fields.items():
        metadata[f"/{k}"] = str(v)
    writer.add_metadata(metadata)
    # Atomic write
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        writer.write(f)
    os.replace(tmp, path)
    return {"success": True, "message": f"Wrote {len(fields)} field(s) to PDF."}
```

### Step 5: Fix GPS-only removal

```python
if fields and ext in _IMAGE_EXTENSIONS and HAS_PILLOW:
    is_gps_only = all("gps" in str(f).lower() for f in fields)
    if is_gps_only:
        if ext in (".jpg", ".jpeg") and has_piexif:
            # piexif selective GPS removal
            ...
        else:
            return {"success": False, "message": "GPS-only strip requires exiftool for this format. Install exiftool."}
            # NEVER fall through to strip-all
```

## Unit Tests

Create `tests/test_metadata_capabilities.py`:

| Test function | What it asserts |
|---|---|
| `test_png_write_text_chunks` | Write `{"Comment": "test"}` to PNG. Re-read. Assert text chunk present. |
| `test_png_write_roundtrip` | Write multiple fields. Read back. Assert all present. |
| `test_exiftool_detection_uses_which` | Mock `shutil.which` returning None. Assert `_has_exiftool() == False`. Mock returning path. Assert True. |
| `test_exiftool_cache_clearable` | Call `_clear_exiftool_cache()`. Assert next call re-probes. |
| `test_capability_report_accuracy` | Call `get_supported_formats()`. Assert `.png` has `read: True`. Assert write depends on exiftool. |
| `test_pdf_write_metadata` | Write `{"Author": "test"}` to PDF. Read back. Assert present. |
| `test_gps_only_strip_no_fallback` | Strip GPS from PNG without exiftool. Assert returns error (not strip-all). |
| `test_gps_only_strip_jpeg_piexif` | Strip GPS from JPEG with piexif. Assert GPS removed, other EXIF preserved. |
| `test_write_returns_actionable_message` | Write to unsupported format. Assert message mentions exiftool and format. |
| `test_cancellation_checked_at_entry` | Call with set cancel_token. Assert returns cancelled immediately. |

## Edge Cases

- Write to read-only file (permission error).
- Write empty fields dict (no-op or success).
- PNG with existing text chunks (preserve + update).
- PDF with no existing metadata (create new).
- Exiftool installed mid-session (cache clear allows detection).

## Validation Checklist

- [ ] `python -m pytest tests/test_metadata_capabilities.py -q` passes
- [ ] `ruff check dataforge/modules/metadata.py dataforge/modules/cleaner.py` passes
- [ ] `_write_pillow` handles PNG via PngInfo
- [ ] `_has_exiftool` uses `shutil.which`
- [ ] `get_supported_formats` returns accurate capabilities
- [ ] GPS-only strip never falls back to strip-all
- [ ] `_write_pypdf` exists

## Definition of Done

All 10 unit tests pass. PNG writes work. Exiftool detection is robust. Capability report is accurate. GPS-only removal is honest. PDF metadata is writable.

## File References

### Files to modify
- `dataforge/modules/metadata.py`
- `dataforge/modules/cleaner.py`
### Test files to create/modify
- `tests/test_*.py` (see Unit Tests section above)

### Audit documentation
- `docs/reviews/STABILITY_AUDIT_2026-08-23.md` — source of all findings
- `docs/PARALLEL_BACKLOG.md` — ticket definitions and wave DAG
- `docs/prompts/tickets/README.md` — ticket index

### Related tickets
- Depends on: Wave 11 (TICK-914-918)
- Blocks: see wave DAG in `docs/PARALLEL_BACKLOG.md`

### Test file
- `tests/test_metadata_capabilities.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `develop`.

### Step 1: Sync dev first
```bash
git checkout develop
git pull origin develop
```

### Step 2: Branch from dev
```bash
git checkout -b feat/TICK-921-metadata-png-write-capabilities
```

### Step 3: Implement changes
Edit the files listed above. Run tests frequently:
```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_*.py -q
ruff check <modified files>
```

### Step 4: Verify changes
```bash
git status
git diff
git diff --stat
```
Confirm all intended files are tracked. No untracked changes to unrelated files.

### Step 5: Commit
```bash
git add <modified files>
git commit -m "feat(<scope>): <description> (TICK-921)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-921.

### Step 6: Push to remote
```bash
git push origin feat/TICK-921-metadata-png-write-capabilities
```

### Step 7: Merge to dev
```bash
git checkout develop
git pull origin develop
git merge --no-ff feat/TICK-921-metadata-png-write-capabilities -m "Merge feat/TICK-921 into develop"
git push origin develop
```

### Step 8: Clean up
```bash
git branch -d feat/TICK-921-metadata-png-write-capabilities
git push origin --delete feat/TICK-921-metadata-png-write-capabilities
```

### Step 9: Reset to dev
```bash
git checkout develop
git pull origin develop
```

### Step 10: Update backlog
Mark TICK-921 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-921.prompt.md`) after merge.
