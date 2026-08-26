# TICK-922 — Search + Duplicates: stale state, input validation, content verification, cache

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-922 |
| Wave | 12 — Operation Correctness (P1) |
| Priority | P1 — Incorrect results + stale data |
| Depends on | Wave 11 |
| Files to modify | `dataforge/modules/search.py`, `dataforge/modules/duplicates.py` |
| Files to create | `tests/test_search_dupes_contract.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P1.7 |
| Validation | `python -m pytest tests/test_search_dupes_contract.py -q` |

## Context

**P1.7 — Stale search results:** `search.py:413-485` does not clear `current_results` before a new search completes. Export and actions can operate on previous results while a new search is running.

**P1.7 — No input validation:** Search accepts invalid paths, negative size values, min > max, and empty patterns without validation.

**P1.7 — Duplicate Select Extras without verification:** `duplicates.py:396-437` selects extras based on scan hashes alone. Only one-click flows pass `verify_content=True`. Manual Select Extras + delete uses unverified hashes.

**P1.7 — Stale cache:** Cache key at `cache.py:182-208` is path+size+mtime+algorithm. A replacement file with unchanged size and timestamp reuses a stale hash.

**P1.7 — Stale path-role maps:** `duplicates.py:648-674` does not clear `_item_path_role` when tree is rebuilt. IDs are reused and group rows can inherit old child paths.

## Objectives

1. Clear stale results at operation start.
2. Validate all inputs before submitting jobs.
3. Verify content before every destructive duplicate action.
4. Invalidate cache when inode changes.
5. Clear path-role maps on tree rebuild.

## Implementation Guide

### Step 1: Clear stale results

At the start of `start_search()`:

```python
self.current_results = []
self.result_tree.clear()
```

### Step 2: Validate inputs

```python
def _validate_search_params(path, min_size, max_size, ...):
    if not path or not os.path.exists(path):
        raise ValueError(f"Invalid search path: {path}")
    if min_size is not None and min_size < 0:
        raise ValueError(f"min_size must be >= 0: {min_size}")
    if max_size is not None and max_size < 0:
        raise ValueError(f"max_size must be >= 0: {max_size}")
    if min_size is not None and max_size is not None and min_size > max_size:
        raise ValueError(f"min_size ({min_size}) > max_size ({max_size})")
```

### Step 3: Verify content before destructive actions

In `run_duplicate_action()` and `_execute_duplicate_action_worker()`, always pass `verify_content=True` to the module:

```python
result = select_duplicate_records(records, verify_content=True)
```

### Step 4: Cache invalidation

Add inode to cache key:

```python
cache_key = f"{path}:{size}:{mtime}:{os.stat(path).st_ino}:{algorithm}"
```

### Step 5: Clear path-role maps

In `_refresh_visible_results()` and when `tree.clear()` is called:

```python
self._item_path_role.clear()
```

## Unit Tests

Create `tests/test_search_dupes_contract.py`:

| Test function | What it asserts |
|---|---|
| `test_search_clears_previous_results` | Run search, get results. Run new search. Assert old results cleared before new arrive. |
| `test_search_invalid_path_raises` | Search with non-existent path. Assert raises ValueError. |
| `test_search_negative_min_size_raises` | Search with min_size=-1. Assert raises ValueError. |
| `test_search_min_greater_than_max_raises` | Search with min=1000, max=100. Assert raises ValueError. |
| `test_search_valid_params_succeeds` | Search with valid params. Assert no error. |
| `test_duplicate_select_extras_verifies_content` | Mock file content change after scan. Select extras. Assert changed file not selected (hash mismatch). |
| `test_cache_invalidated_on_inode_change` | Create file, hash it. Replace with different file same size/mtime. Assert hash is recomputed (not cached). |
| `test_path_role_cleared_on_rebuild` | Build duplicate tree. Clear and rebuild. Assert no stale paths in `_item_path_role`. |
| `test_search_empty_pattern_matches_all` | Search with empty name pattern. Assert returns all files. |
| `test_duplicate_action_always_verifies` | Call duplicate action. Assert `verify_content=True` passed to module. |

## Edge Cases

- Search on empty directory (0 results, no error).
- Search with only min_size set (no max).
- Search with only max_size set (no min).
- Duplicate group with 1 file (no extras to select).
- Cache with file deleted between hash and action.

## Validation Checklist

- [ ] `python -m pytest tests/test_search_dupes_contract.py -q` passes
- [ ] `ruff check dataforge/modules/search.py dataforge/modules/duplicates.py` passes
- [ ] `current_results` cleared at search start
- [ ] Input validation exists for path, size ranges
- [ ] `verify_content=True` in all destructive duplicate paths
- [ ] Cache key includes inode
- [ ] `_item_path_role` cleared on rebuild

## Definition of Done

All 10 unit tests pass. Stale results are cleared. Inputs are validated. Content is verified before destruction. Cache is inode-aware. Path maps are clean.

## File References

### Files to modify
- `dataforge/modules/search.py`
- `dataforge/modules/duplicates.py`
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
- `tests/test_search_dupes_contract.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `develop`.

### Step 1: Sync dev first
```bash
git checkout develop
git pull origin develop
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-922-search-dupes-stale-state-validation
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
git commit -m "fix(<scope>): <description> (TICK-922)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-922.

### Step 6: Push to remote
```bash
git push origin fix/TICK-922-search-dupes-stale-state-validation
```

### Step 7: Merge to dev
```bash
git checkout develop
git pull origin develop
git merge --no-ff fix/TICK-922-search-dupes-stale-state-validation -m "Merge fix/TICK-922 into develop"
git push origin develop
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-922-search-dupes-stale-state-validation
git push origin --delete fix/TICK-922-search-dupes-stale-state-validation
```

### Step 9: Reset to dev
```bash
git checkout develop
git pull origin develop
```

### Step 10: Update backlog
Mark TICK-922 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-922.prompt.md`) after merge.
