# TICK-916 — File actions: parallel exception indexing, cancellation accounting, temp safety

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-916 |
| Wave | 11 — Critical Stability (P0) |
| Priority | P0 — Silent data loss |
| Depends on | TICK-915 |
| Files to modify | `dataforge/core/services/file_actions.py` |
| Files to create | `tests/test_file_actions_contract.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P0.6, P1.7, P1.20 |
| Validation | `python -m pytest tests/test_file_actions_contract.py -q` |

## Context

**P0.6 — Dropped exceptions:** In `_run_batch_parallel()` at `file_actions.py:315-342`, `futures.pop(fut, None)` at line 323 removes the future from the dict. Then `futures.get(fut, -1)` at line 328 looks it up — but it's already gone, so it returns `-1`. The exception handler at lines 329-341 therefore cannot find the item and produces no failure record. The final filter at line 353 (`records = [r for r in records if r is not None]`) removes the `None` slot. Failed operations disappear from the outcome entirely.

**P1.7 — Rename escape:** `rename_path()` at `operations/files.py:205-233` passes arbitrary `new_name` to `os.path.join()`. Names containing `..` or path separators can move files outside the source directory.

**P1.7 — Predictable temp files:** Archive operations use `destination + ".tmp"` at `file_actions.py:794-835`. Concurrent operations sharing a destination can conflict. A pre-existing symlink at the `.tmp` path can redirect writes.

**P1.20 — Provider unused:** `FileActionService` stores a provider at `file_actions.py:126-143` but all operations use local `os`/`shutil` directly.

## Objectives

1. Every requested item has one outcome record (including failures and cancellations).
2. Failed operations are visible in the outcome and audit log.
3. Cancellation reports accurate completed/failed/unstarted counts.
4. Rename names are confined to the source directory.
5. Temp files are unique and symlink-safe.

## Implementation Guide

### Step 1: Fix future-to-index mapping

Replace the pop-then-lookup pattern. Use a separate `future_to_idx` dict that is not modified during iteration:

```python
future_to_idx = {pool.submit(_do_one, idx, item): idx for idx, item in enumerate(items)}
pending = dict(future_to_idx)

while pending:
    done, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
    for fut in done:
        idx = pending.pop(fut)  # Remove from pending, not from future_to_idx
        if fut.cancelled():
            continue
        exc = fut.exception()
        if exc is not None:
            # idx is valid — create failure record
            ...
```

### Step 2: Ensure one record per item

Pre-populate `records` with sentinel values. After the loop, replace any remaining sentinels with "skipped" or "cancelled" records:

```python
records: list[BatchActionRecord] = [None] * total
# ... fill records during iteration ...
# Fill remaining None slots
for i, rec in enumerate(records):
    if rec is None:
        if cancel_token and cancel_token.is_set():
            records[i] = BatchActionRecord(item=items[i], source_path="", message="Cancelled", result=..., success=False, skipped=True)
        else:
            records[i] = BatchActionRecord(item=items[i], source_path="", message="Not processed", result=..., success=False)
```

### Step 3: Confine rename_path (coordinate with TICK-919)

Note: This step edits `dataforge/core/operations/files.py`. That file is owned by TICK-919 in this wave. Either:
- Remove this step from TICK-916 and defer entirely to TICK-919, OR
- Add `dataforge/core/operations/files.py` to TICK-916's exclusive_write_files and make TICK-919 depend on TICK-916 (sequential).

In `operations/files.py:rename_path()`, validate `new_name`:

```python
if os.path.sep in new_name or new_name in (".", "..") or "/" in new_name:
    raise ValueError(f"Invalid rename target (must be a basename): {new_name!r}")
target = os.path.join(os.path.dirname(source_path), new_name)
if os.path.normpath(target) != os.path.normpath(os.path.join(os.path.dirname(source_path), os.path.basename(target))):
    raise ValueError(f"Rename target escapes source directory: {new_name!r}")
```

### Step 4: Secure temp files

Replace `destination + ".tmp"` with `tempfile.mkstemp(dir=os.path.dirname(destination), suffix=".tmp")`:

```python
import tempfile
fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(destination) or ".", suffix=".dataforge.tmp")
try:
    with os.fdopen(fd, 'wb') as f:
        # write archive
    os.replace(tmp_path, destination)
except:
    os.unlink(tmp_path)
    raise
```

Note: The Context mentions P1.20 provider (FileActionService stores provider but never uses it).
This ticket does NOT wire the provider — that is a separate concern (TICK-928 handles provider dispatch).
If you choose to wire it, add a dedicated step; otherwise remove the provider bullet from Context.

## Unit Tests

Create `tests/test_file_actions_contract.py`:

| Test function | What it asserts |
|---|---|
| `test_parallel_failure_produces_record` | Transfer 3 items where 1 source doesn't exist. Assert outcome has 3 records. Assert 1 failure record with "ERROR" in message. |
| `test_parallel_exception_indexing` | Inject a worker exception (mock operation to raise). Assert the failure record has the correct source_path (not empty or wrong). |
| `test_cancellation_reports_accurate_counts` | Start a transfer of 10 items. Cancel after 3 complete. Assert outcome has records for all 10. Assert some are completed and some are cancelled/skipped. |
| `test_requested_equals_input_count` | Run batch with 5 items. Assert `len(outcome.records) == 5`. |
| `test_rename_rejects_dotdot` | Call `rename_path(file, "../escape.txt")`. Assert raises `ValueError`. |
| `test_rename_rejects_separator` | Call `rename_path(file, "sub/name.txt")`. Assert raises `ValueError`. |
| `test_rename_accepts_valid_basename` | Call `rename_path(file, "new_name.txt")`. Assert succeeds. |
| `test_archive_temp_is_unique` | Archive two sets to same directory. Assert temp files don't collide. Assert no symlink following. |
| `test_archive_temp_cleaned_on_failure` | Force archive to fail mid-write. Assert temp file is removed. |
| `test_outcome_cancelled_field_matches_token` | Cancel token set. Assert `outcome.cancelled is True`. |

## Edge Cases

- 0 items (empty batch, returns empty outcome).
- All items fail (outcome has all failure records, success=False).
- Cancel token set before any item starts (all skipped).
- Item raises `PermissionError` (recorded as failure, not swallowed).
- Item raises `OSError` with errno=EXDEV (cross-device, should use fallback).

## Validation Checklist

- [ ] `python -m pytest tests/test_file_actions_contract.py -q` passes
- [ ] `ruff check dataforge/core/services/file_actions.py` passes
- [ ] No `futures.pop(fut, None)` followed by `futures.get(fut)` pattern remains
- [ ] `rename_path` validates basename
- [ ] Archive uses `tempfile.mkstemp`
- [ ] Every batch outcome has `len(records) == requested`

## Definition of Done

All 10 unit tests pass. Every batch operation produces one record per item. Failures are visible. Rename is confined. Temp files are secure.

## File References

### Files to modify
- `dataforge/core/services/file_actions.py`
### Test files to create/modify
- `tests/test_*.py` (see Unit Tests section above)

### Audit documentation
- `docs/reviews/STABILITY_AUDIT_2026-08-23.md` — source of all findings
- `docs/PARALLEL_BACKLOG.md` — ticket definitions and wave DAG
- `docs/prompts/tickets/README.md` — ticket index

### Related tickets
- Depends on: TICK-915
- Blocks: see wave DAG in `docs/PARALLEL_BACKLOG.md`

### Test file
- `tests/test_file_actions_contract.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-916-file-actions-parallel-exceptions
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
git commit -m "fix(<scope>): <description> (TICK-916)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-916.

### Step 6: Push to remote
```bash
git push origin fix/TICK-916-file-actions-parallel-exceptions
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff fix/TICK-916-file-actions-parallel-exceptions -m "Merge fix/TICK-916 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-916-file-actions-parallel-exceptions
git push origin --delete fix/TICK-916-file-actions-parallel-exceptions
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-916 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-916.prompt.md`) after merge.
