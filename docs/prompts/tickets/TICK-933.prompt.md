# TICK-933 — Full workflow integration smoke tests

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-933 |
| Wave | 14 — Verification |
| Priority | P1 — Integration verification |
| Depends on | Wave 13 |
| Files to create | `tests/test_full_workflow.py` |
| Audit reference | Full audit verification matrix |
| Validation | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_full_workflow.py -q` |

## Context

No end-to-end test exercises the complete preview-confirm-execute-result cycle for each view. Individual unit tests pass but the integrated workflow may fail at callback boundaries, state management, or signal delivery.

## Objectives

1. Verify each view has at least one working end-to-end workflow.
2. Verify preview matches execution for destructive operations.
3. Verify results have accurate success/failure state.

## Implementation Guide

Each test creates real temporary fixtures (files, directories), invokes the operation through its public API (not UI), and verifies the complete cycle.

### Test fixtures

```python
@pytest.fixture
def sample_files(tmp_path):
    """Create sample files for testing."""
    files = []
    for i in range(5):
        f = tmp_path / f"file_{i}.txt"
        f.write_text(f"Content {i}")
        files.append(str(f))
    return files

@pytest.fixture
def sample_pdf(tmp_path):
    """Create a minimal PDF for testing."""
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    path = str(tmp_path / "test.pdf")
    with open(path, "wb") as f:
        writer.write(f)
    return path
```

## Unit Tests

Create `tests/test_full_workflow.py`:

| Test function | What it asserts |
|---|---|
| `test_search_preview_execute_cycle` | Create files. Search. Assert results found. Move results. Assert files moved. |
| `test_duplicate_scan_action_cycle` | Create duplicate files. Scan. Assert groups found. Delete extras. Assert 1 copy remains. |
| `test_pdf_merge_cycle` | Create 2 PDFs. Merge. Assert output exists. Assert page count == sum. |
| `test_pdf_split_cycle` | Create multi-page PDF. Split. Assert output files created. |
| `test_pdf_compress_cycle` | Create PDF. Compress. Assert output exists. Assert size <= original. |
| `test_image_convert_cycle` | Create PNG. Convert to JPEG. Assert output exists. Assert opens correctly. |
| `test_metadata_write_read_cycle` | Create JPEG. Write metadata. Read back. Assert fields present. |
| `test_metadata_strip_cycle` | Create JPEG with EXIF. Strip. Read back. Assert EXIF removed. |
| `test_cleanup_scan_clean_cycle` | Create temp files. Scan junk. Assert found. Clean. Assert removed. |
| `test_integrity_create_verify_cycle` | Create file. Create snapshot. Assert verify succeeds. Modify file. Assert verify fails. |
| `test_renamer_preview_apply_cycle` | Create files. Preview rename. Apply. Assert files renamed. |
| `test_action_builder_pipeline_cycle` | Create files. Run filter+copy pipeline. Assert output correct. |

## Edge Cases

- Operation on empty directory.
- Operation on single file.
- Operation with permission errors.
- Operation cancelled mid-way.

## Validation Checklist

- [ ] `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_full_workflow.py -q` passes
- [ ] All 12 tests pass
- [ ] Each test uses real temporary fixtures
- [ ] Each test verifies complete cycle

## Definition of Done

All 12 integration tests pass. Every view has at least one verified end-to-end workflow.

## File References

### Files to modify
- `tests/test_full_workflow.py`
### Test files to create/modify
- `tests/test_*.py` (see Unit Tests section above)

### Audit documentation
- `docs/reviews/STABILITY_AUDIT_2026-08-23.md` — source of all findings
- `docs/PARALLEL_BACKLOG.md` — ticket definitions and wave DAG
- `docs/prompts/tickets/README.md` — ticket index

### Related tickets
- Depends on: Wave 13 (TICK-927-930)
- Blocks: see wave DAG in `docs/PARALLEL_BACKLOG.md`

### Test file
- `tests/test_full_workflow.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b test/TICK-933-full-workflow-integration-tests
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
git commit -m "test(<scope>): <description> (TICK-933)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-933.

### Step 6: Push to remote
```bash
git push origin test/TICK-933-full-workflow-integration-tests
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff test/TICK-933-full-workflow-integration-tests -m "Merge test/TICK-933 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d test/TICK-933-full-workflow-integration-tests
git push origin --delete test/TICK-933-full-workflow-integration-tests
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-933 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-933.prompt.md`) after merge.
