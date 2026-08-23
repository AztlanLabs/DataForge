# TICK-920 — Media ops: PDF merge/split/compress/convert correctness, image safety, atomic output

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-920 |
| Wave | 12 — Operation Correctness (P1) |
| Priority | P1 — Incorrect results + data loss |
| Depends on | Wave 11 |
| Files to modify | `dataforge/core/media_ops.py` |
| Files to create | `tests/test_media_ops_contract.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P1.4, P1.5 |
| Validation | `python -m pytest tests/test_media_ops_contract.py -q` |

## Context

**P1.4 — Merge bugs:**
- `merge_pdfs` at `media_ops.py:89-92` raises `ImportError` when pypdf missing instead of returning a report dict.
- Writes empty PDF when 0 files merged (`media_ops.py:198-205`).
- Counts file as merged even when all page additions fail (`media_ops.py:159-167`).

**P1.4 — Split bugs:**
- Records output paths before successful write (`media_ops.py:265-296`).
- Error dicts have ad-hoc shape missing `requested`/`dry_run` keys (`media_ops.py:224-260`).

**P1.4 — Compress bugs:**
- `quality` only affects fabricated dry-run ratio (`media_ops.py:305-325`).
- `hasattr(writer, "compress_content_streams")` is always False — dead code (`media_ops.py:377-380`).
- Final replacement failure still produces success-shaped report (`media_ops.py:398-410`).

**P1.4 — Convert bugs:**
- PDF conversion writes directly to final path, can leave partial page sets on cancellation (`media_ops.py:514-619`).

**P1.5 — Image bugs:**
- `convert_image()` creates `dest_dir` before checking `dry_run` (`media_ops.py:742-778`).
- Same-format conversion can overwrite source (`media_ops.py:742-765,843-869`).
- Batch outputs with same basename overwrite each other.

## Objectives

1. All entry points return report dicts (never raise for missing deps).
2. Merge: only write output when >= 1 file contributed pages.
3. Split: record paths after successful write. Unify report shapes.
4. Compress: fix stream compression or label as lossless rewrite.
5. Image: no side effects during dry run. No same-file overwrite. Collision detection.
6. All outputs: atomic temp-file replacement.

## Implementation Guide

### Step 1: Graceful dependency handling

Every entry point starts with:

```python
if not HAS_PYPDF:
    return {"success": False, "message": "Install pypdf: pip install pypdf", "operation": "merge", "requested": len(paths), "completed": 0, "failed": len(paths)}  # Use "merge" to match _merge_report
```

### Step 2: Merge correctness

Track `pages_added` per file. Only count as merged if `pages_added > 0`. Only write output if `total_pages_added > 0`:

```python
merged = 0
for path in paths:
    try:
        reader = PdfReader(path)
        pages = 0
        for page in reader.pages:
            writer.add_page(page)
            pages += 1
        if pages > 0:
            merged += 1
    except Exception as exc:
        failed_paths.append((path, str(exc)))

if merged == 0:
    return {"success": False, "message": "No files contributed pages", "requested": len(paths), "completed": 0, "failed": len(paths)}
```

### Step 3: Split correctness

Append to `generated` only after successful write:

```python
try:
    with open(out_path, "wb") as f:
        single_writer.write(f)
    generated.append(out_path)
except Exception as exc:
    errors.append({"path": out_path, "error": str(exc)})
```

### Step 4: Compress fix

Replace dead `hasattr(writer, "compress_content_streams")` with per-page compression:

```python
for page in writer.pages:
    try:
        page.compress_content_streams()
    except Exception:
        pass  # Some pages may not support compression
```

Label dry-run ratio as estimate:

```python
return {"success": True, "dry_run": True, "ratio": estimated_ratio, "ratio_note": "estimate based on lossless rewrite", ...}
```

### Step 5: Image dry-run safety

```python
if dry_run:
    return {"success": True, "dry_run": True, "message": f"Would convert to {dest_format}", "output_path": dest_path}

os.makedirs(dest_dir, exist_ok=True)  # Only reached when NOT dry_run
```

### Step 6: Atomic output (use mkstemp for symlink safety + EXDEV fallback)

```python
import tempfile, shutil
fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(dest_path) or ".", suffix=".dataforge.tmp")
try:
    with os.fdopen(fd, "wb") as f:
        writer.write(f)
    try:
        os.replace(tmp_path, dest_path)
    except OSError as exc:
        import errno
        if exc.errno == errno.EXDEV:
            shutil.move(tmp_path, dest_path)
        else:
            raise
except:
    if os.path.exists(tmp_path):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    raise
```

Note: Use `tempfile.mkstemp` (not `dest + ".dataforge.tmp"` string concat) for symlink safety. Same pattern as TICK-916 Step 4.

## Unit Tests

Create `tests/test_media_ops_contract.py`:

| Test function | What it asserts |
|---|---|
| `test_merge_no_pypdf_returns_report` | Mock `HAS_PYPDF=False`. Assert returns dict with `success: False`, not raises. |
| `test_merge_zero_valid_inputs` | Merge 3 invalid files. Assert no output file. Assert `success: False`. |
| `test_merge_counts_only_successful_pages` | Merge 2 good + 1 bad. Assert `merged == 2`. |
| `test_merge_empty_pdf_not_written` | 0 merged. Assert output file does not exist. |
| `test_split_generated_after_write` | Split PDF. Assert `generated` paths all exist on disk. |
| `test_split_error_shape_matches_report` | Force write failure. Assert error dict has unified keys (`requested`, `success`, `message`) matching success report shape (not ad-hoc `{"error": ...}`). |
| `test_compress_dry_run_has_estimate_note` | Compress dry_run. Assert `ratio_note` field exists. |
| `test_compress_real_compresses` | Compress real. Assert `success: True` and `ratio is not None`. Do NOT assert output is smaller — lossless rewrite may be larger. |
| `test_image_dry_run_creates_nothing` | Convert image dry_run. Assert dest_dir does not exist. |
| `test_image_same_format_no_overwrite` | Convert PNG to same dir as PNG. Assert source unchanged. |
| `test_image_collision_detection` | Two files same basename, same dest dir. Assert collision error or unique names. |
| `test_atomic_output_cleanup_on_failure` | Force write failure. Assert `.dataforge.tmp` file is cleaned up. |

## Edge Cases

- Merge with 1 encrypted PDF (should skip with error, not crash).
- Split single-page PDF (1 output file).
- Compress already-minimal PDF (ratio ~1.0).
- Image convert RGBA to JPEG (should handle alpha).
- Convert to same format with quality change.

## Validation Checklist

- [ ] `python -m pytest tests/test_media_ops_contract.py -q` passes
- [ ] `ruff check dataforge/core/media_ops.py` passes
- [ ] No `raise ImportError` in merge/split/compress/convert entry points
- [ ] No directory creation before dry_run check
- [ ] All outputs use temp + replace pattern
- [ ] `compress_content_streams` called per page (not on writer)

## Definition of Done

All 12 unit tests pass. All media operations return report dicts. Merge/split/compress produce correct results. Image dry run is side-effect-free. Outputs are atomic.

## File References

### Files to modify
- `dataforge/core/media_ops.py`
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
- `tests/test_media_ops_contract.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-920-media-ops-pdf-image-correctness
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
git commit -m "fix(<scope>): <description> (TICK-920)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-920.

### Step 6: Push to remote
```bash
git push origin fix/TICK-920-media-ops-pdf-image-correctness
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff fix/TICK-920-media-ops-pdf-image-correctness -m "Merge fix/TICK-920 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-920-media-ops-pdf-image-correctness
git push origin --delete fix/TICK-920-media-ops-pdf-image-correctness
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-920 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-920.prompt.md`) after merge.
