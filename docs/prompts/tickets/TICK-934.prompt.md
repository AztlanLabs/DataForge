# TICK-934 — Fix 5 current stale test fixtures

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-934 |
| Wave | 14 — Verification |
| Priority | P1 — Green build |
| Depends on | Wave 13 |
| Files to modify | `tests/test_comprehensive.py`, `tests/test_contract_regressions.py`, `tests/test_plugin_loader_isolation.py` |
| Audit reference | Current test run: 5 failures |
| Validation | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_comprehensive.py tests/test_contract_regressions.py tests/test_plugin_loader_isolation.py -q` |

## Context

Current test run shows 5 failures:

1. `test_comprehensive.TestPluginLoader.test_loader_returns_list` — plugin dir is mode 0777 on current filesystem, correctly rejected by `plugin_loader.py:482-506`.
2. `test_plugin_loader_isolation.test_inline_returns_same_as_before` — same permission condition.
3. `test_contract_regressions.test_reduce_motion_zeroes_animation_duration` — `DataForgeApp.__new__()` without `QMainWindow.__init__()`. Current code at `app.py:449-453` uses `getattr(self, "_in_build", False)` which requires Qt attribute storage.
4. `test_contract_regressions.test_toggle_sidebar_group_animates_container_height` — same `__init__` issue.
5. `test_contract_regressions.test_switch_view_fades_in_new_view` — animation baseline mismatch. App already has 1 animation from startup, test expects `> baseline` but gets `== baseline`.

## Objectives

1. Fix plugin tests to handle unsafe permissions gracefully.
2. Fix contract regression fixtures to call `QMainWindow.__init__()`.
3. Fix animation baseline test.

## Implementation Guide

### Step 1: Plugin tests

Option A (preferred): Skip on unsafe filesystem:

```python
@pytest.mark.skipif(
    os.stat(plugin_dir).st_mode & 0o777 == 0o777,
    reason="Plugin directory is world-writable (unsafe filesystem)"
)
def test_loader_returns_list(self):
    ...
```

Option B: Create a controlled fixture with secure permissions:

```python
def _make_plugin_dir(tmp_path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir(mode=0o755)
    # Copy plugin files
    return str(plugin_dir)
```

Do NOT weaken the production permission check.

### Step 2: Contract regression fixtures

```python
# Before:
app = DataForgeApp.__new__(DataForgeApp)
app.content_stack = QStackedWidget()
...

# After:
app = DataForgeApp.__new__(DataForgeApp)
QMainWindow.__init__(app)  # Initialize Qt internals
app.content_stack = QStackedWidget()
...
```

Or use `DataForgeApp()` with mocked config (like the animation test already does).

### Step 3: Animation baseline

```python
def test_switch_view_fades_in_new_view(self):
    app = DataForgeApp()
    baseline = len(app._active_animations)
    app.switch_view("Search")
    # Account for startup animation: baseline may be 1, not 0
    self.assertGreaterEqual(len(app._active_animations), baseline)
    # Or assert a specific new animation was added:
    self.assertGreater(len(app._active_animations), baseline)
```

If the startup animation is expected, adjust baseline:

```python
baseline = len(app._active_animations)  # May be 1 from startup
app.switch_view("Search")
self.assertGreater(len(app._active_animations), baseline)
```

## Unit Tests

This ticket fixes existing tests. No new test file needed.

| Test to fix | What to change |
|---|---|
| `test_loader_returns_list` | Skip on world-writable dir OR use controlled fixture. |
| `test_inline_returns_same_as_before` | Same as above. |
| `test_reduce_motion_zeroes_animation_duration` | Call `QMainWindow.__init__()` in fixture. |
| `test_toggle_sidebar_group_animates_container_height` | Call `QMainWindow.__init__()` in fixture. |
| `test_switch_view_fades_in_new_view` | Account for startup animation in baseline. |

## Validation Checklist

- [ ] `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_comprehensive.py -q` passes (0 failures)
- [ ] `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_contract_regressions.py -q` passes (0 failures)
- [ ] `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_plugin_loader_isolation.py -q` passes (0 failures)
- [ ] Full suite: `QT_QPA_PLATFORM=offscreen python -m pytest -q --maxfail=5` passes

## Definition of Done

All 5 previously failing tests pass. Full suite has 0 failures from stale fixtures.

## File References

### Files to modify
- `tests/test_comprehensive.py`
- `tests/test_contract_regressions.py`
- `tests/test_plugin_loader_isolation.py`
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
- `tests/test_comprehensive.py, tests/test_contract_regressions.py, tests/test_plugin_loader_isolation.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `develop`.

### Step 1: Sync dev first
```bash
git checkout develop
git pull origin develop
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-934-fix-stale-test-fixtures
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
git commit -m "fix(<scope>): <description> (TICK-934)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-934.

### Step 6: Push to remote
```bash
git push origin fix/TICK-934-fix-stale-test-fixtures
```

### Step 7: Merge to dev
```bash
git checkout develop
git pull origin develop
git merge --no-ff fix/TICK-934-fix-stale-test-fixtures -m "Merge fix/TICK-934 into develop"
git push origin develop
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-934-fix-stale-test-fixtures
git push origin --delete fix/TICK-934-fix-stale-test-fixtures
```

### Step 9: Reset to dev
```bash
git checkout develop
git pull origin develop
```

### Step 10: Update backlog
Mark TICK-934 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-934.prompt.md`) after merge.
