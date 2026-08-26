# TICK-925 — UI Metadata + Search + Dupes views: stale state refresh, selection mode, path resolvers

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-925 |
| Wave | 12 — Operation Correctness (P1) |
| Priority | P1 — Stale UI state |
| Depends on | TICK-921, TICK-922 |
| Files to modify | `dataforge/ui/views/metadata_view.py`, `dataforge/ui/views/search.py`, `dataforge/ui/views/duplicates.py` |
| Files to create | `tests/test_view_state_contract.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P1.6, P1.7 |
| Validation | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_view_state_contract.py -q` |

## Context

**P1.6 — Stale metadata display:** After strip/write, `_on_file_select()` runs before `item_metadata_map` is reread. Strip never redisplays updated metadata. Write refreshes only overview/raw, not GPS/timestamps (`metadata_view.py:651-666,760-784`).

**P1.7 — Stale duplicate path maps:** `_item_path_role` is not cleared when `tree.clear()` and `item_map.clear()` are called (`duplicates.py:648-674`). IDs are reused and group rows inherit old child paths.

**P1.7 — Single selection for plural actions:** `EnhancedTreeview` does not set `ExtendedSelection` (`widgets.py:452-465`). Most views use default single selection, conflicting with "selected files" plural actions.

**P1.7 — Stale search results:** Search does not clear `current_results` before new results arrive (`search.py:413-485`).

## Objectives

1. Refresh all metadata panels after strip/write.
2. Clear path-role maps on tree rebuild.
3. Enable extended selection where plural actions exist.
4. Clear search results at operation start.

## Implementation Guide

### Step 1: Refresh metadata after strip/write

In `_on_strip_complete()` and `_on_write_complete()`, after success:

```python
# Re-read metadata for the selected file
selected = self.tree.selection()
if selected:
    self._on_file_select(None)  # Trigger full refresh
```

Ensure `_on_file_select` refreshes ALL panels (overview, raw, GPS, timestamps), not just overview.

### Step 2: Clear path-role maps

In `_refresh_visible_results()` and wherever `tree.clear()` is called:

```python
self._item_path_role.clear()
```

### Step 3: Enable extended selection

In views with plural actions (metadata, search, duplicates, recovery):

```python
self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
```

### Step 4: Clear search results

At the start of `start_search()`:

```python
self.current_results = []
self.result_tree.clear()
```

## Unit Tests

Create `tests/test_view_state_contract.py`:

| Test function | What it asserts |
|---|---|
| `test_metadata_refresh_after_strip` | Strip metadata. Assert all panels refreshed (mock `_on_file_select` called). |
| `test_metadata_refresh_after_write` | Write metadata. Assert GPS/timestamps panels updated. |
| `test_path_role_cleared_on_rebuild` | Build duplicate tree. Clear. Rebuild. Assert no stale paths. |
| `test_extended_selection_enabled` | Create metadata view. Assert selection mode is ExtendedSelection. |
| `test_search_results_cleared_on_new_search` | Run search. Start new search. Assert old results cleared. |
| `test_metadata_all_panels_refreshed` | Select file. Assert overview, raw, GPS, timestamps all populated. |

## Edge Cases

- Strip with no file selected (no-op).
- Write with file deleted between preview and execute (error).
- Duplicate tree with 0 groups (empty, no crash).
- Search with 0 results (empty tree, no error).

## Validation Checklist

- [ ] `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_view_state_contract.py -q` passes
- [ ] `ruff check dataforge/ui/views/metadata_view.py dataforge/ui/views/search.py dataforge/ui/views/duplicates.py` passes
- [ ] Metadata panels refresh after strip/write
- [ ] Path-role maps cleared on rebuild
- [ ] Extended selection enabled where needed
- [ ] Search results cleared at start

## Definition of Done

All 6 unit tests pass. Metadata display is fresh. Path maps are clean. Selection mode is correct. Search results are current.

## File References

### Files to modify
- `dataforge/ui/views/metadata_view.py`
- `dataforge/ui/views/search.py`
- `dataforge/ui/views/duplicates.py`
### Test files to create/modify
- `tests/test_*.py` (see Unit Tests section above)

### Audit documentation
- `docs/reviews/STABILITY_AUDIT_2026-08-23.md` — source of all findings
- `docs/PARALLEL_BACKLOG.md` — ticket definitions and wave DAG
- `docs/prompts/tickets/README.md` — ticket index

### Related tickets
- Depends on: TICK-921, TICK-922
- Blocks: see wave DAG in `docs/PARALLEL_BACKLOG.md`

### Test file
- `tests/test_view_state_contract.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `develop`.

### Step 1: Sync dev first
```bash
git checkout develop
git pull origin develop
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-925-ui-metadata-search-dupes-state
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
git commit -m "fix(<scope>): <description> (TICK-925)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-925.

### Step 6: Push to remote
```bash
git push origin fix/TICK-925-ui-metadata-search-dupes-state
```

### Step 7: Merge to dev
```bash
git checkout develop
git pull origin develop
git merge --no-ff fix/TICK-925-ui-metadata-search-dupes-state -m "Merge fix/TICK-925 into develop"
git push origin develop
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-925-ui-metadata-search-dupes-state
git push origin --delete fix/TICK-925-ui-metadata-search-dupes-state
```

### Step 9: Reset to dev
```bash
git checkout develop
git pull origin develop
```

### Step 10: Update backlog
Mark TICK-925 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-925.prompt.md`) after merge.
