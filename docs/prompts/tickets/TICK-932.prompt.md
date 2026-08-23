# TICK-932 — Operation report contract tests

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-932 |
| Wave | 14 — Verification |
| Priority | P1 — Regression prevention |
| Depends on | Wave 13 |
| Files to create | `tests/test_operation_reports.py` |
| Audit reference | Full audit verification matrix |
| Validation | `python -m pytest tests/test_operation_reports.py -q` |

## Context

No test validates that every operation returns the unified report shape, that cancellation reports accurate counts, or that evidence mode blocks all mutation types. The fixes in Waves 11-12 need permanent verification.

## Objectives

1. Validate report shape for all batch operations.
2. Validate cancellation count accuracy.
3. Validate evidence mode blocks all mutation types.
4. Validate rename confinement.
5. Validate archive temp file uniqueness.

## Unit Tests

Create `tests/test_operation_reports.py`:

| Test function | What it asserts |
|---|---|
| `test_batch_transfer_requested_equals_records` | Transfer 5 items. Assert `outcome.requested == 5` and `len(outcome.records) == 5`. |
| `test_batch_delete_requested_equals_records` | Delete 5 items. Assert counts match. |
| `test_batch_rename_requested_equals_records` | Rename 5 items. Assert counts match. |
| `test_parallel_failure_produces_record` | Transfer 3 items, 1 source missing. Assert 3 records. Assert 1 failure. |
| `test_cancellation_reports_accurate` | Transfer 10 items, cancel after 3. Assert records for all 10. Assert some completed, some skipped. |
| `test_evidence_mode_blocks_delete` | Enable evidence mode. Delete. Assert blocked. |
| `test_evidence_mode_blocks_move` | Enable evidence mode. Move. Assert blocked. |
| `test_evidence_mode_blocks_rename` | Enable evidence mode. Rename. Assert blocked. |
| `test_evidence_mode_blocks_archive` | Enable evidence mode. Archive. Assert blocked. |
| `test_evidence_mode_blocks_metadata_write` | Enable evidence mode. Write metadata. Assert blocked. |
| `test_evidence_mode_blocks_metadata_strip` | Enable evidence mode. Strip metadata. Assert blocked. |
| `test_evidence_mode_allows_scan` | Enable evidence mode. Scan. Assert succeeds. |
| `test_rename_rejects_dotdot` | Rename with `..`. Assert ValueError. |
| `test_rename_rejects_separator` | Rename with `/`. Assert ValueError. |
| `test_archive_temp_unique` | Two archives to same dir. Assert no temp collision. |
| `test_outcome_cancelled_matches_token` | Cancel token set. Assert `outcome.cancelled is True`. |

## Edge Cases

- 0 items (empty batch).
- All items fail.
- Cancel before any item starts.
- Permission error on item.

## Validation Checklist

- [ ] `python -m pytest tests/test_operation_reports.py -q` passes
- [ ] All 16 tests pass
- [ ] Evidence mode blocks all mutation types
- [ ] Cancellation counts are accurate

## Definition of Done

All 16 unit tests pass. Report shape is validated. Evidence mode blocks all mutations. Cancellation is accurate.

## File References

### Files to modify
- `tests/test_operation_reports.py`
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
- `tests/test_operation_reports.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b test/TICK-932-operation-report-contract-tests
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
git commit -m "test(<scope>): <description> (TICK-932)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-932.

### Step 6: Push to remote
```bash
git push origin test/TICK-932-operation-report-contract-tests
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff test/TICK-932-operation-report-contract-tests -m "Merge test/TICK-932 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d test/TICK-932-operation-report-contract-tests
git push origin --delete test/TICK-932-operation-report-contract-tests
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-932 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-932.prompt.md`) after merge.
