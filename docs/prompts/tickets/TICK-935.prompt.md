# TICK-935 — Documentation closeout + backlog status update

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-935 |
| Wave | 14 — Verification |
| Priority | P2 — Documentation |
| Depends on | TICK-931, TICK-932, TICK-933, TICK-934 |
| Files to modify | `docs/PARALLEL_BACKLOG.md`, `docs/prompts/tickets/README.md`, `docs/reviews/STABILITY_AUDIT_2026-08-23.md` |
| Audit reference | Full audit closeout |
| Validation | `python -m pytest --collect-only -q | tail -1` |

## Context

After all Wave 11-14 tickets are complete, the backlog, audit, and documentation need to reflect the current state. Test counts, commit hashes, and resolution references must be updated.

## Objectives

1. Update backlog wave status for Waves 11-14.
2. Update ticket README with final status.
3. Mark audit findings as resolved with commit references.
4. Update test counts in all documentation.
5. Verify documentation matches implementation.

## Implementation Guide

### Step 1: Update PARALLEL_BACKLOG.md

For each completed ticket, update the status line:

```markdown
| `TICK-914` | ... | ✅ DONE 2026-08-23 — `tests/test_job_lifecycle_safety.py` 10/10, progress affinity + QThread lifecycle verified |
```

Update wave status header:

```markdown
> **Wave 11 (Critical Stability): 5/5 DONE — XX tests.** Unblocks Wave 12.
```

### Step 2: Update README.md

Update the ticket index with final status for each ticket.

### Step 3: Update audit document

For each finding in `STABILITY_AUDIT_2026-08-23.md`, add resolution reference:

```markdown
### P0.1 Progress updates mutate Qt widgets from a worker

**Status: RESOLVED — TICK-914**
**Commit: abc1234**
**Test: tests/test_job_lifecycle_safety.py 10/10**
```

### Step 4: Update test counts

Run `python -m pytest --collect-only -q | tail -1` and update all docs with the actual count.

### Step 5: Verify consistency

Check that:
- Every ticket in the backlog has a corresponding prompt file (or is marked DONE with deleted prompt).
- Every wave status matches actual test results.
- Test counts in README match actual suite.

## Validation

```bash
python -m pytest --collect-only -q | tail -1
# Should show total test count matching documentation
```

## Validation Checklist

- [ ] All Wave 11-14 tickets marked DONE in backlog
- [ ] All audit findings have resolution references
- [ ] Test counts match actual suite
- [ ] README matches implementation
- [ ] No stale documentation references

## Definition of Done

Documentation is current. All findings resolved. Test counts accurate. Backlog reflects reality.

## File References

### Files to modify
- `docs/PARALLEL_BACKLOG.md`
- `docs/prompts/tickets/README.md`
- `docs/reviews/STABILITY_AUDIT_2026-08-23.md`
### Test files to create/modify
- `tests/test_*.py` (see Unit Tests section above)

### Audit documentation
- `docs/reviews/STABILITY_AUDIT_2026-08-23.md` — source of all findings
- `docs/PARALLEL_BACKLOG.md` — ticket definitions and wave DAG
- `docs/prompts/tickets/README.md` — ticket index

### Related tickets
- Depends on: TICK-931, TICK-932, TICK-933, TICK-934
- Blocks: see wave DAG in `docs/PARALLEL_BACKLOG.md`

### Test file
- `N/A (documentation only)`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `develop`.

### Step 1: Sync dev first
```bash
git checkout develop
git pull origin develop
```

### Step 2: Branch from dev
```bash
git checkout -b docs/TICK-935-documentation-closeout
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
git commit -m "docs(<scope>): <description> (TICK-935)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-935.

### Step 6: Push to remote
```bash
git push origin docs/TICK-935-documentation-closeout
```

### Step 7: Merge to dev
```bash
git checkout develop
git pull origin develop
git merge --no-ff docs/TICK-935-documentation-closeout -m "Merge docs/TICK-935 into develop"
git push origin develop
```

### Step 8: Clean up
```bash
git branch -d docs/TICK-935-documentation-closeout
git push origin --delete docs/TICK-935-documentation-closeout
```

### Step 9: Reset to dev
```bash
git checkout develop
git pull origin develop
```

### Step 10: Update backlog
Mark TICK-935 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-935.prompt.md`) after merge.
