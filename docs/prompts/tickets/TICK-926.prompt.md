# TICK-926 — UI Cleanup + Recovery + Tools + Forensics views: controls, actions, safety

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-926 |
| Wave | 12 — Operation Correctness (P1) |
| Priority | P1 — Non-functional controls + incorrect actions |
| Depends on | TICK-923 |
| Files to modify | `dataforge/ui/views/system_cleanup.py`, `dataforge/ui/views/recovery_view.py`, `dataforge/ui/views/tools.py`, `dataforge/ui/views/forensics_view.py` |
| Files to create | `tests/test_view_actions_contract.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P1.8, P1.9, P1.10, P1.11, P1.12 |
| Validation | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_view_actions_contract.py -q` |

## Context

**P1.8 — Cleanup:** Browser checkbox not wired. Error callback reversed. Generic context menus on non-file trees.

**P1.9 — Recovery:** PhotoRec ignores selected file types. Hash verification uses basename matching (`forensics_view.py:2062-2091`) instead of selected row's path. Cancellation shown as completion.

**P1.10 — Forensics:** Integrity snapshot does not recurse directories. Timeline atime is actually mtime.

**P1.11 — Action Builder:** Step exceptions logged but execution continues (`action_builder.py:424-435`). Completion handler reports "Pipeline Completed" (`action_builder.py:440-455`). Worker receives live mutable step objects (`action_builder.py:382-435`).

**P1.12 — Tools:** Renamer applies live UI rules instead of confirmed preview rules (`tools.py:649-685,1040-1065`). Folder sync compares only mtime without fingerprinting (`tools.py:687-730,1121-1193`).

## Objectives

1. Wire all cleanup checkboxes to scan parameters.
2. Pass selected file types to PhotoRec.
3. Fix hash verification to use absolute path.
4. Clone renamer rules at preview time.
5. Add preview fingerprint to folder sync.
6. Make Action Builder report step failures and clone steps.
7. Disable generic context menus on non-file trees.

## Implementation Guide

### Step 1: Wire cleanup checkboxes

In `_start_junk_scan()`, read each checkbox and pass to scan:

```python
include_browser = self.browser_chk.isChecked()
selected_cats = [cat for cat, chk in self._category_checkboxes.items() if chk.isChecked()]
```

### Step 2: PhotoRec file types

```python
selected_types = self._get_selected_file_types()
result = run_photorec(image, output, file_types=selected_types)
```

### Step 3: Hash verification path

```python
# Before: basename matching
# After: use selected item's absolute path
item_id = self.hash_tree.selection()[0]
path = self._hash_path_by_item.get(item_id) or self.hash_tree.get_item_path(item_id)
```

### Step 4: Clone renamer rules

At preview time, serialize rules:

```python
self._previewed_rules = copy.deepcopy(self.rules_widget.get_rules())
```

At execute time, use `self._previewed_rules` instead of re-reading from UI.

### Step 5: Folder sync fingerprint

```python
self._sync_fingerprint = {
    "source": source_path,
    "dest": dest_path,
    "source_mtime": os.path.getmtime(source_path),
    "dest_mtime": os.path.getmtime(dest_path),
}
```

At execute time, verify fingerprint matches.

### Step 6: Action Builder step cloning

```python
import copy
steps_snapshot = copy.deepcopy(self.steps)
self.app.run_workflow(self._execute_pipeline_thread, ..., steps_snapshot, ...)
```

In `_execute_pipeline_thread`, track step failures:

```python
for i, step in enumerate(steps_snapshot):
    try:
        step.execute(context)
    except Exception as exc:
        context.log("Pipeline", "Error", f"Step {step.name} failed: {exc}")
        if not context.is_dry_run:
            return {"success": False, "message": f"Step {step.name} failed: {exc}", "failed_step": i}
```

### Step 7: Disable generic context menus on non-file trees

```python
# In views with report/device trees:
self.report_tree.set_no_file_actions(True)
```

## Unit Tests

Create `tests/test_view_actions_contract.py`:

| Test function | What it asserts |
|---|---|
| `test_cleanup_browser_checkbox_wired` | Toggle checkbox. Assert scan params change. |
| `test_photorec_receives_types` | Mock run_photorec. Assert file_types passed. |
| `test_hash_verify_uses_absolute_path` | Select row. Assert verification uses full path, not basename. |
| `test_renamer_uses_preview_rules` | Preview rules A. Change UI to rules B. Execute. Assert uses rules A. |
| `test_sync_fingerprint_checked` | Preview sync. Change source. Execute. Assert stale fingerprint rejected. |
| `test_action_builder_clones_steps` | Start pipeline. Change steps during execution. Assert pipeline uses original steps. |
| `test_action_builder_reports_step_failure` | Pipeline with failing step. Assert result has `success: False` and `failed_step`. |
| `test_non_file_tree_no_file_actions` | Create report tree. Assert context menu has no Move/Copy/Delete. |

## Edge Cases

- PhotoRec not installed (clear error).
- Renamer with 0 rules (no-op).
- Sync with identical source/dest (no-op or error).
- Pipeline with 0 steps (rejected at UI level).
- Hash verify on deleted file (error).

## Validation Checklist

- [ ] `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_view_actions_contract.py -q` passes
- [ ] `ruff check` on all 4 view files passes
- [ ] Cleanup checkboxes wired
- [ ] PhotoRec receives file types
- [ ] Hash verification uses absolute path
- [ ] Renamer uses previewed rules
- [ ] Action Builder clones steps and reports failures
- [ ] Non-file trees have no file actions

## Definition of Done

All 8 unit tests pass. All controls are wired. Actions use correct data. Steps are cloned. Failures are reported.

## File References

### Files to modify
- `dataforge/ui/views/system_cleanup.py`
- `dataforge/ui/views/recovery_view.py`
- `dataforge/ui/views/tools.py`
- `dataforge/ui/views/forensics_view.py`
### Test files to create/modify
- `tests/test_*.py` (see Unit Tests section above)

### Audit documentation
- `docs/reviews/STABILITY_AUDIT_2026-08-23.md` — source of all findings
- `docs/PARALLEL_BACKLOG.md` — ticket definitions and wave DAG
- `docs/prompts/tickets/README.md` — ticket index

### Related tickets
- Depends on: TICK-923
- Blocks: see wave DAG in `docs/PARALLEL_BACKLOG.md`

### Test file
- `tests/test_view_actions_contract.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-926-ui-cleanup-recovery-tools-forensics
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
git commit -m "fix(<scope>): <description> (TICK-926)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-926.

### Step 6: Push to remote
```bash
git push origin fix/TICK-926-ui-cleanup-recovery-tools-forensics
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff fix/TICK-926-ui-cleanup-recovery-tools-forensics -m "Merge fix/TICK-926 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-926-ui-cleanup-recovery-tools-forensics
git push origin --delete fix/TICK-926-ui-cleanup-recovery-tools-forensics
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-926 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-926.prompt.md`) after merge.
