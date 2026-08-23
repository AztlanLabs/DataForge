# TICK-924 — UI Media: path precedence fix, preview snapshot, collision detection, worker tree access

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-924 |
| Wave | 12 — Operation Correctness (P1) |
| Priority | P1 — Wrong paths + cross-thread access |
| Depends on | TICK-920 |
| Files to modify | `dataforge/ui/views/media.py` |
| Files to create | `tests/test_media_view_contract.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P1.3, P1.4, P1.5 |
| Validation | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_media_view_contract.py -q` |

## Context

**P1.4 — Operator precedence bug:** At `media.py:698`:
```python
path = self.pdf_tree.get_item_path(iid) or self.pdf_tree.item(iid)['values'][0] if self.pdf_tree.item(iid)['values'] else ""
```
This parses as `(A or B) if values else ""`. If `values` is empty, a valid `get_item_path(iid)` result is discarded and path becomes `""`.

**P1.3 — Preview/execute race:** `_on_preview_pdf_merge_complete` at `media.py:871-899` re-reads paths from the tree at execute time. If selection changed during preview, the executed merge differs from what was confirmed.

**P1.5 — Worker tree access:** `_img_convert_worker` at `media.py:1105` reads `self.img_tree.item(preview["item_id"])["values"][1]` from the worker thread. This is a QTreeWidget access from a non-GUI thread.

**P1.5 — No collision detection:** Batch image conversion with multiple source files sharing the same basename and a common destination converges on the same output path. `os.replace()` overwrites silently.

## Objectives

1. Fix path selection precedence.
2. Create immutable preview snapshot for merge.
3. Remove all QTreeWidget access from worker functions.
4. Add collision detection for batch operations.

## Implementation Guide

### Step 1: Fix precedence

```python
# Before (line 698):
path = self.pdf_tree.get_item_path(iid) or self.pdf_tree.item(iid)['values'][0] if self.pdf_tree.item(iid)['values'] else ""

# After:
vals = self.pdf_tree.item(iid)['values']
path = self.pdf_tree.get_item_path(iid) or (vals[0] if vals else "")
```

### Step 2: Immutable preview snapshot

In `_on_preview_pdf_merge_complete`, capture paths at preview time:

```python
self._merge_preview_paths = []
for item_id in self.pdf_tree.get_children():
    vals = self.pdf_tree.item(item_id)['values']
    p = vals[0] if vals else self.pdf_tree.get_item_path(item_id)
    if p:
        self._merge_preview_paths.append(p)
```

In `_pdf_merge_worker`, use `self._merge_preview_paths` instead of re-reading the tree.

### Step 3: Remove worker tree access

Before submitting the image convert job, capture all needed values:

```python
for preview in previews:
    preview["output_size"] = preview.get("size", 0)  # Capture now, don't read from tree later
```

In `_img_convert_worker`, use only the pre-captured values. Never access `self.img_tree`.

### Step 4: Collision detection

```python
output_paths = {}
for preview in previews:
    dest = os.path.join(out_dir, os.path.splitext(preview["filename"])[0] + f".{format}")
    if dest in output_paths:
        return {"success": False, "message": f"Collision: multiple files map to {dest}"}
    output_paths[dest] = preview
```

## Unit Tests

Create `tests/test_media_view_contract.py`:

| Test function | What it asserts |
|---|---|
| `test_path_precedence_with_empty_values` | Mock tree item with empty values but valid `get_item_path`. Assert path resolves correctly. |
| `test_path_precedence_with_values` | Mock tree item with values. Assert values[0] used. |
| `test_merge_preview_captures_paths` | Preview merge. Assert `_merge_preview_paths` populated. |
| `test_merge_execute_uses_preview_paths` | Change tree after preview. Execute merge. Assert uses previewed paths (not current tree). |
| `test_img_convert_no_tree_access_in_worker` | Run image convert. Assert worker thread does not access `img_tree` (mock and verify no calls). |
| `test_batch_collision_detected` | Two files same basename, same dest. Assert collision error returned. |
| `test_batch_unique_basenames_succeed` | Two files different basenames. Assert both convert. |
| `test_merge_empty_paths_aborted` | Preview with 0 valid paths. Assert merge not started. |

## Edge Cases

- Merge with 1 PDF (trivial, should work).
- Image convert to same format (should warn or handle).
- Preview cancelled then execute called (should reject stale execute).
- Tree empty at execute time (should use preview snapshot).

## Validation Checklist

- [ ] `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_media_view_contract.py -q` passes
- [ ] `ruff check dataforge/ui/views/media.py` passes
- [ ] Line 698 precedence fixed
- [ ] `_merge_preview_paths` used at execute time
- [ ] No `self.img_tree` access in `_img_convert_worker`
- [ ] Collision detection exists for batch operations

## Definition of Done

All 8 unit tests pass. Path precedence is correct. Preview snapshot is immutable. Worker has no tree access. Collisions are detected.

## File References

### Files to modify
- `dataforge/ui/views/media.py`
### Test files to create/modify
- `tests/test_*.py` (see Unit Tests section above)

### Audit documentation
- `docs/reviews/STABILITY_AUDIT_2026-08-23.md` — source of all findings
- `docs/PARALLEL_BACKLOG.md` — ticket definitions and wave DAG
- `docs/prompts/tickets/README.md` — ticket index

### Related tickets
- Depends on: TICK-920
- Blocks: see wave DAG in `docs/PARALLEL_BACKLOG.md`

### Test file
- `tests/test_media_view_contract.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-924-ui-media-path-precedence-preview
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
git commit -m "fix(<scope>): <description> (TICK-924)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-924.

### Step 6: Push to remote
```bash
git push origin fix/TICK-924-ui-media-path-precedence-preview
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff fix/TICK-924-ui-media-path-precedence-preview -m "Merge fix/TICK-924 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-924-ui-media-path-precedence-preview
git push origin --delete fix/TICK-924-ui-media-path-precedence-preview
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-924 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-924.prompt.md`) after merge.
