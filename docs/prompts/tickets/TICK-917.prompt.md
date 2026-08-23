# TICK-917 — Evidence mode at mutation boundary + app shutdown + callback contract

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-917 |
| Wave | 11 — Critical Stability (P0) |
| Priority | P0 — Forensic safety bypass |
| Depends on | TICK-914 |
| Files to modify | `dataforge/ui/app.py`, `dataforge/core/case.py` |
| Files to create | `tests/test_evidence_mode_boundary.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P0.7, P1.1, P1.2 |
| Validation | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_evidence_mode_boundary.py -q` |

## Context

**P0.7 — Bypassable evidence mode:** Evidence mode is enforced in `JobManager` by substring matching the submitted target function name (`job_manager.py:393-399,662-668`). The `_DESTRUCTIVE_KEYWORDS` set contains `delete, remove, strip, clean, move, rename, archive, trash, purge, wipe, secure_delete`. Wrapped workers like `_execute_pipeline_thread`, `_pdf_compress_worker`, `_write_worker`, `_strip_worker` do not contain these keywords in their names, so they bypass the check. Metadata operations at `metadata.py:222-329` do not check evidence mode at all. The `FileActionService` checks a `CaseContext` at `file_actions.py:147-154`, but the UI mode does not reliably establish that context.

**P1.1 — Swallowed exceptions:** `DataForgeApp.run_background()` at `app.py:993-1005` wraps callbacks in try/except and swallows all exceptions. If a completion handler crashes (e.g., `restore_tree_selection` calling `on_select(None)` on a no-arg callback), the user sees no error.

**P1.2 — Callback contract:** `BaseView.restore_tree_selection()` at `base.py:478-483` calls `on_select(None)`. Several callbacks accept no argument: `MediaView.on_img_select` (`media.py:975-979`), `SearchView.on_preview_select` (`search.py:401-411`), `ToolsView.on_cleaner_preview` (`tools.py:797-806`). These raise `TypeError` which is then swallowed.

**No closeEvent:** `DataForgeApp` has no `closeEvent()` override. Closing the window while jobs are active leaves QThreads alive during Qt teardown.

## Objectives

1. Enforce evidence mode at every mutation primitive, not by target-name inspection.
2. Add `DataForgeApp.closeEvent()` that cleanly shuts down all workers.
3. Fix callback contract so `restore_tree_selection` doesn't crash no-arg callbacks.
4. Stop swallowing callback exceptions; log and surface them.

## Implementation Guide

### Step 1: Enforce evidence mode at mutation boundary

In `FileActionService`, every mutation method (`transfer_path`, `delete_path`, `rename_path`, `archive_items`) already checks `CaseContext`. Ensure the UI sets this context:

In `app.py`, when evidence mode is toggled, set the global `CaseContext`:

```python
from dataforge.core.case import CaseContext
CaseContext.get_current().evidence_mode = enabled
```

For metadata operations, add a check at the top of `write_metadata()` and `remove_metadata()`:

```python
from dataforge.core.case import CaseContext
if CaseContext.get_current().evidence_mode:
    return {"success": False, "message": "Blocked by Evidence Mode", "blocked": True}
```

Remove the keyword-based check from `JobManager._is_destructive()` and `submit()`.

### Step 2: Add DataForgeApp.closeEvent()

```python
def closeEvent(self, event):
    self.job_manager.cancel_all()
    # Wait for all workers with timeout
    with self.job_manager._lock:
        workers = list(self.job_manager._workers.values())
    for w in workers:
        if w.isRunning():
            w._cancel_token.set()
            w.wait(3000)  # 3 second timeout per worker
    self.job_manager.shutdown()
    super().closeEvent(event)
```

### Step 3: Fix restore_tree_selection callback

In `base.py:478-483`, check callback signature:

```python
def restore_tree_selection(self, tree, item_ids, on_select=None):
    if hasattr(tree, "restore_selection"):
        tree.restore_selection(item_ids)
    if on_select:
        try:
            sig = inspect.signature(on_select)
            if len(sig.parameters) > 0:
                on_select(None)
            else:
                on_select()
        except Exception:
            pass
```

### Step 4: Stop swallowing callback exceptions

In `app.py:993-1005`, log the exception and show a diagnostic status:

```python
def _on_success(result):
    ...
    try:
        if callback:
            callback(result)
    except Exception as exc:
        logger.error("Completion callback failed: %s", exc, exc_info=True)
        self.update_status(f"Callback error: {exc}")
    ...
```

## Unit Tests

Create `tests/test_evidence_mode_boundary.py`:

| Test function | What it asserts |
|---|---|
| `test_evidence_mode_blocks_metadata_write` | Enable evidence mode. Call `MetadataEngine.write_metadata()`. Assert returns `{"blocked": True}`. |
| `test_evidence_mode_blocks_metadata_strip` | Enable evidence mode. Call `MetadataEngine.remove_metadata()`. Assert blocked. |
| `test_evidence_mode_blocks_file_delete` | Enable evidence mode. Call `FileActionService.delete_items()`. Assert blocked. |
| `test_evidence_mode_blocks_file_move` | Enable evidence mode. Call `FileActionService.transfer_items()`. Assert blocked. |
| `test_evidence_mode_blocks_rename` | Enable evidence mode. Call rename. Assert blocked. |
| `test_evidence_mode_blocks_archive` | Enable evidence mode. Call archive. Assert blocked. |
| `test_evidence_mode_blocks_pipeline_delete_step` | Enable evidence mode. Run pipeline with DeleteStep. Assert delete blocked, pipeline reports failure. |
| `test_evidence_mode_allows_read_operations` | Enable evidence mode. Run scan, search, hash. Assert all succeed. |
| `test_close_event_waits_for_workers` | Submit a 2-second job. Call `closeEvent()`. Assert it returns only after job completes (within timeout). |
| `test_close_event_cancels_pending_jobs` | Submit 3 jobs. Call `closeEvent()`. Assert all jobs reach terminal state. |
| `test_restore_tree_selection_no_arg_callback` | Call `restore_tree_selection(tree, ids, on_select=lambda: None)`. Assert no TypeError. |
| `test_callback_exception_logged_not_swallowed` | Submit job with callback that raises. Assert logger.error is called. Assert status shows error. |

## Edge Cases

- Evidence mode toggled while a job is running (in-flight job should complete, next job blocked).
- closeEvent called twice (idempotent).
- Callback raises `SystemExit` (should not be caught).
- Evidence mode with CaseContext not initialized (should initialize gracefully).

## Validation Checklist

- [ ] `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_evidence_mode_boundary.py -q` passes
- [ ] `ruff check dataforge/ui/app.py dataforge/core/case.py` passes
- [ ] No `_is_destructive` keyword check remains in `job_manager.py`
- [ ] `write_metadata` checks `CaseContext.evidence_mode`
- [ ] `remove_metadata` checks `CaseContext.evidence_mode`
- [ ] `DataForgeApp.closeEvent` exists
- [ ] `restore_tree_selection` handles no-arg callbacks

## Definition of Done

All 12 unit tests pass. Evidence mode blocks all mutation types at the primitive level. App shuts down cleanly. Callback contract is safe. Exceptions are logged, not swallowed.

## File References

### Files to modify
- `dataforge/ui/app.py`
- `dataforge/core/case.py`
### Test files to create/modify
- `tests/test_*.py` (see Unit Tests section above)

### Audit documentation
- `docs/reviews/STABILITY_AUDIT_2026-08-23.md` — source of all findings
- `docs/PARALLEL_BACKLOG.md` — ticket definitions and wave DAG
- `docs/prompts/tickets/README.md` — ticket index

### Related tickets
- Depends on: TICK-914
- Blocks: see wave DAG in `docs/PARALLEL_BACKLOG.md`

### Test file
- `tests/test_evidence_mode_boundary.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-917-evidence-mode-mutation-boundary
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
git commit -m "fix(<scope>): <description> (TICK-917)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-917.

### Step 6: Push to remote
```bash
git push origin fix/TICK-917-evidence-mode-mutation-boundary
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff fix/TICK-917-evidence-mode-mutation-boundary -m "Merge fix/TICK-917 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-917-evidence-mode-mutation-boundary
git push origin --delete fix/TICK-917-evidence-mode-mutation-boundary
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-917 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-917.prompt.md`) after merge.
