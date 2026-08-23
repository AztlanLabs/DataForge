# TICK-923 — Cleanup + Recovery: checkbox wiring, type filters, cancellation display, path confinement

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-923 |
| Wave | 12 — Operation Correctness (P1) |
| Priority | P1 — Non-functional controls + incorrect results |
| Depends on | Wave 11 |
| Files to modify | `dataforge/modules/system_cleanup.py`, `dataforge/modules/recovery.py` |
| Files to create | `tests/test_cleanup_recovery_contract.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P1.8, P1.9 |
| Validation | `python -m pytest tests/test_cleanup_recovery_contract.py -q` |

## Context

**P1.8 — Browser checkbox is no-op:** The "Include browser artifacts" checkbox at `system_cleanup.py:111-115` is persisted but `_start_junk_scan()` at `system_cleanup.py:436-487` never reads it. The scan always runs the same way.

**P1.8 — Error callback reversed:** `system_cleanup.py:489-503` calls `show_workflow_error("Junk Scan Failed", error)` but `app.show_workflow_error(error, title)` expects error first, title second.

**P1.8 — Double-counted savings:** Browser and junk categories overlap. Same file can appear in both results.

**P1.9 — PhotoRec ignores types:** `recovery_view.py:544-576` calls `run_photorec(image, output)` without passing selected file types.

**P1.9 — CLI type mismatch:** CLI at `cli.py:400-402` lowercases `--types` values. Module at `recovery.py:387-390` expects uppercase keys like `"JPEG"`.

**P1.9 — Cancellation shown as completion:** `_on_restore_complete` and `_on_carve_complete` do not check for `cancelled` in result.

**P1.9 — Trash path escape:** Generic context actions can resolve `original_path` instead of trash file path.

## Objectives

1. Wire browser checkbox to scan request.
2. Fix error callback argument order.
3. Deduplicate savings by canonical path.
4. Pass file types to PhotoRec.
5. Normalize type identifiers case-insensitively.
6. Display cancellation correctly.
7. Confine Trash actions to trash object paths.

## Implementation Guide

### Step 1: Wire browser checkbox

In `_start_junk_scan()`, read the checkbox and pass to scan:

```python
include_browser = self.browser_chk.isChecked()
extra_paths = []
if include_browser:
    extra_paths.extend(_get_browser_profile_paths())
result = scan_junk_files(extra_paths=extra_paths, ...)
```

### Step 2: Fix error callback

```python
# Before: show_workflow_error("Junk Scan Failed", error)
# After:
self.app.show_workflow_error(error, title="Junk Scan Failed")
```

### Step 3: Deduplicate savings

```python
seen_paths = set()
unique_results = []
for item in results:
    canon = os.path.realpath(item["path"])
    if canon not in seen_paths:
        seen_paths.add(canon)
        unique_results.append(item)
```

### Step 4: Pass types to PhotoRec

```python
selected_types = self._get_selected_file_types()
result = run_photorec(image, output, file_types=selected_types)
```

### Step 5: Normalize type identifiers

```python
def _normalize_type(name: str) -> str:
    return name.upper().strip()
```

### Step 6: Check cancellation in completion handlers

```python
def _on_restore_complete(self, result):
    if isinstance(result, dict) and result.get("cancelled"):
        self.app.update_status("Restore cancelled")
        return
    ...
```

## Unit Tests

Create `tests/test_cleanup_recovery_contract.py`:

| Test function | What it asserts |
|---|---|
| `test_browser_checkbox_wired` | Set checkbox unchecked. Run scan. Assert browser profiles not in scan params. |
| `test_browser_checkbox_checked_includes_profiles` | Set checked. Assert profiles included. |
| `test_error_callback_correct_order` | Trigger scan error. Assert dialog shows correct title and message (not reversed). |
| `test_savings_deduplicated` | Scan with overlapping paths. Assert no duplicate paths in results. |
| `test_photorec_receives_file_types` | Mock `run_photorec`. Assert `file_types` param passed. |
| `test_type_normalization_case_insensitive` | Pass "jpg" to recovery. Assert matched to "JPEG". |
| `test_restore_cancelled_shows_cancelled` | Return cancelled result. Assert status shows "Cancelled". |
| `test_carve_cancelled_shows_cancelled` | Return cancelled result. Assert status shows "Cancelled". |
| `test_trash_action_uses_trash_path` | Select trash row. Assert action uses trash object path, not original_path. |
| `test_junk_scan_min_age_filter` | Set min_age=7. Assert only files older than 7 days returned. |

## Edge Cases

- Browser profile directory doesn't exist (graceful skip).
- PhotoRec not installed (clear error message).
- Recovery of 0 files (empty result, no crash).
- Trash on unsupported platform (clear unsupported message).
- Overlapping junk categories (dedup works).

## Validation Checklist

- [ ] `python -m pytest tests/test_cleanup_recovery_contract.py -q` passes
- [ ] `ruff check dataforge/modules/system_cleanup.py dataforge/modules/recovery.py` passes
- [ ] Browser checkbox changes scan behavior
- [ ] Error callback arguments are in correct order
- [ ] PhotoRec receives file_types
- [ ] Cancellation displays correctly
- [ ] Type identifiers are case-insensitive

## Definition of Done

All 10 unit tests pass. Browser checkbox works. Error messages are correct. Savings are deduplicated. PhotoRec uses selected types. Cancellation is displayed correctly.

## File References

### Files to modify
- `dataforge/modules/system_cleanup.py`
- `dataforge/modules/recovery.py`
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
- `tests/test_cleanup_recovery_contract.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-923-cleanup-recovery-controls-filters
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
git commit -m "fix(<scope>): <description> (TICK-923)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-923.

### Step 6: Push to remote
```bash
git push origin fix/TICK-923-cleanup-recovery-controls-filters
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff fix/TICK-923-cleanup-recovery-controls-filters -m "Merge fix/TICK-923 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-923-cleanup-recovery-controls-filters
git push origin --delete fix/TICK-923-cleanup-recovery-controls-filters
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-923 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-923.prompt.md`) after merge.
