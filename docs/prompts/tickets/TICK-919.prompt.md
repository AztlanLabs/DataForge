# TICK-919 — Core operations: unified result contract, rename confinement, transfer safety

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-919 |
| Wave | 12 — Operation Correctness (P1) |
| Priority | P1 — Result accuracy |
| Depends on | Wave 11 (TICK-914–918) complete |
| Files to modify | `dataforge/core/operations/files.py` |
| Files to create | `tests/test_operations_contract.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P1.1, P1.7 |
| Validation | `python -m pytest tests/test_operations_contract.py -q` |

## Context

**P1.1 — Mixed result types:** The codebase returns `OperationResult`, `BatchActionOutcome`, dicts, lists, and strings from different operations. `JobStatus.DONE` means "worker returned" not "operation succeeded". A worker returning `{"success": False}` is still marked DONE by the job layer (`job_manager.py:180-209`, `jobs.py:296-329`). The UI then shows success.

**P1.7 — Rename escape:** `rename_path()` at `operations/files.py:205-233` passes arbitrary `new_name` to `os.path.join()`. If `new_name` is absolute, it replaces the entire path. If it contains `..`, it moves the file outside the source directory.

**P1.7 — Same-file overwrite:** `transfer_path()` does not check if source and destination resolve to the same file.

## Objectives

1. Define one `OperationReport` dataclass for all user-facing operations.
2. Confine rename targets to the source directory.
3. Prevent same-file overwrite in transfers.
4. Ensure `JobStatus.DONE` vs `report.success` are independent.

## Implementation Guide

### Step 1: Define OperationReport

In `operations/files.py` (or `core/common.py`), add:

```python
@dataclass
class OperationReport:
    operation: str
    requested: int
    completed: int
    failed: int
    skipped: int = 0
    cancelled: bool = False
    success: bool = True
    errors: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    dry_run: bool = False
```

### Step 2: Confine rename_path

```python
def rename_path(source_path: str, new_name: str, ...) -> OperationResult:
    # Validate basename
    if os.path.sep in new_name or (os.name == 'nt' and '/' in new_name):
        raise ValueError(f"Invalid rename target (contains path separator): {new_name!r}")
    if new_name in (".", "..", ""):
        raise ValueError(f"Invalid rename target: {new_name!r}")
    target = os.path.join(os.path.dirname(source_path), new_name)
    # Verify confinement
    if os.path.normpath(os.path.dirname(target)) != os.path.normpath(os.path.dirname(source_path)):
        raise ValueError(f"Rename target escapes source directory: {new_name!r}")
    ...
```

### Step 3: Prevent same-file overwrite

In `transfer_path()`, before any copy/move:

```python
if os.path.exists(dest_path):
    if os.path.samefile(source_path, dest_path):
        return OperationResult(action, source_path, dest_path, False, "Source and destination are the same file")
```

## Unit Tests

Create `tests/test_operations_contract.py`:

| Test function | What it asserts |
|---|---|
| `test_rename_rejects_dotdot` | `rename_path(file, "../escape.txt")` raises `ValueError`. |
| `test_rename_rejects_absolute` | `rename_path(file, "/tmp/escape.txt")` raises `ValueError`. |
| `test_rename_rejects_separator` | `rename_path(file, "sub/name.txt")` raises `ValueError`. |
| `test_rename_rejects_empty` | `rename_path(file, "")` raises `ValueError`. |
| `test_rename_accepts_valid_basename` | `rename_path(file, "new_name.txt")` succeeds. File renamed. |
| `test_rename_preserves_directory` | Rename. Assert file stays in same directory. |
| `test_transfer_same_file_no_overwrite` | `transfer_path(file, file, "copy")` returns failure with "same file" message. |
| `test_transfer_different_file_succeeds` | Copy file to different path. Assert destination exists. Source unchanged. |
| `test_operation_report_fields` | Construct `OperationReport`. Assert all fields accessible. Assert `success` defaults True. |
| `test_batch_outcome_requested_equals_records` | Run batch of 5. Assert `outcome.requested == 5` and `len(outcome.records) == 5`. |

## Edge Cases

- Rename to same name (no-op or success).
- Rename file that doesn't exist (error).
- Transfer to directory that doesn't exist (create or error based on policy).
- Transfer with `action="move"` across devices (should use copy+delete fallback).

## Validation Checklist

- [ ] `python -m pytest tests/test_operations_contract.py -q` passes
- [ ] `ruff check dataforge/core/operations/files.py` passes
- [ ] `rename_path` validates basename and confinement
- [ ] `transfer_path` checks same-file
- [ ] `OperationReport` dataclass exists

## Definition of Done

All 10 unit tests pass. Rename is confined. Same-file is detected. Result contract is defined.

## File References

### Files to modify
- `dataforge/core/operations/files.py`
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
- `tests/test_operations_contract.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b feat/TICK-919-operations-result-contract
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
git commit -m "feat(<scope>): <description> (TICK-919)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-919.

### Step 6: Push to remote
```bash
git push origin feat/TICK-919-operations-result-contract
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff feat/TICK-919-operations-result-contract -m "Merge feat/TICK-919 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d feat/TICK-919-operations-result-contract
git push origin --delete feat/TICK-919-operations-result-contract
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-919 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-919.prompt.md`) after merge.
