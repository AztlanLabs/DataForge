# TICK-931 — GUI thread affinity regression tests

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-931 |
| Wave | 14 — Verification |
| Priority | P1 — Regression prevention |
| Depends on | Wave 13 |
| Files to create | `tests/test_gui_thread_affinity.py` |
| Audit reference | Full audit verification matrix |
| Validation | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_gui_thread_affinity.py -q` |

## Context

No regression test asserts that progress, completion, error, and dialog callbacks execute on the GUI thread. The threading fixes in Wave 11 (TICK-914) need permanent guard rails. Without these tests, future changes can silently reintroduce cross-thread widget mutation.

Note: TICK-914 already creates `tests/test_job_lifecycle_safety.py` with 10 thread-affinity tests. This ticket should NOT duplicate those test names. Instead, extend coverage to dialog callbacks, tree widget access, and multi-job scenarios that TICK-914 does not cover. Consider importing and extending TICK-914's fixtures rather than recreating them.

## Objectives

1. Assert all callback types run on the GUI thread.
2. Assert no duplicate progress delivery.
3. Assert clean shutdown with no QThread warnings.
4. Assert worker functions do not access Qt widgets.

## Implementation Guide

Create `tests/test_gui_thread_affinity.py` using `QApplication`, `DataForgeApp` (or `JobManager` directly), and thread recording.

### Test structure

```python
import sys
import threading
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QThread

@pytest.fixture
def app():
    qapp = QApplication.instance() or QApplication(sys.argv)
    return qapp

@pytest.fixture
def manager(app):
    from dataforge.ui.job_manager import JobManager
    mgr = JobManager()
    return mgr
```

### Recording thread identity

```python
class ThreadRecorder:
    def __init__(self):
        self.progress_threads = []
        self.result_thread = None
        self.error_thread = None
    
    def on_progress(self, current, total, message=""):
        self.progress_threads.append(QThread.currentThread())
    
    def on_result(self, result):
        self.result_thread = QThread.currentThread()
    
    def on_error(self, error):
        self.error_thread = QThread.currentThread()
```

## Unit Tests

| Test function | What it asserts |
|---|---|
| `test_progress_callback_runs_on_gui_thread` | Submit progress=True job. Record thread in progress callback. Assert equals `QApplication.instance().thread()`. |
| `test_result_callback_runs_on_gui_thread` | Submit job. Record thread in on_success. Assert GUI thread. |
| `test_error_callback_runs_on_gui_thread` | Submit job that raises. Record thread in on_error. Assert GUI thread. |
| `test_progress_called_exactly_once_per_event` | Job emits 5 progress events. Count delivered callbacks. Assert == 5. (If TICK-914 already has this, add coalesce test instead: 1000 rapid events delivered throttled.) |
| `test_no_duplicate_progress_per_tick` | Job emits 1 event. Count total progress_signal emissions vs delivered. Assert 1:1. |
| `test_qthread_cleanup_no_warnings` | Submit job, wait for completion. Capture stderr via capsys. Assert no "QThread: Destroyed" warning. Call `QApplication.processEvents()` to flush pending warnings. |
| `test_shutdown_waits_for_workers` | Submit 2-second job. Call shutdown(). Assert returns after job completes. Assert no abort. |
| `test_completion_submits_followup` | In on_success, submit second job. Assert both complete. Assert second callback on GUI thread. |
| `test_worker_is_not_on_gui_thread` | Inside target function, record thread. Assert NOT equal to GUI thread. |
| `test_progress_after_terminal_discarded` | Complete job. Emit late progress. Assert no crash. Assert no update_progress call. |

## Edge Cases

- Job with 0 progress events.
- Job with 1000 rapid progress events (coalescing).
- Job that raises InterruptedError.
- Shutdown with 0 active jobs.
- Shutdown with 8 active jobs.

## Validation Checklist

- [ ] `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_gui_thread_affinity.py -q` passes
- [ ] All 10 tests pass
- [ ] No Qt warnings in stderr
- [ ] Tests run in < 30 seconds

## Definition of Done

All 10 unit tests pass. Every callback type is verified to run on the GUI thread. No duplicate progress. Clean shutdown.

## File References

### Files to modify
- `tests/test_gui_thread_affinity.py`
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
- `tests/test_gui_thread_affinity.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `develop`.

### Step 1: Sync dev first
```bash
git checkout develop
git pull origin develop
```

### Step 2: Branch from dev
```bash
git checkout -b test/TICK-931-gui-thread-affinity-tests
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
git commit -m "test(<scope>): <description> (TICK-931)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-931.

### Step 6: Push to remote
```bash
git push origin test/TICK-931-gui-thread-affinity-tests
```

### Step 7: Merge to dev
```bash
git checkout develop
git pull origin develop
git merge --no-ff test/TICK-931-gui-thread-affinity-tests -m "Merge test/TICK-931 into develop"
git push origin develop
```

### Step 8: Clean up
```bash
git branch -d test/TICK-931-gui-thread-affinity-tests
git push origin --delete test/TICK-931-gui-thread-affinity-tests
```

### Step 9: Reset to dev
```bash
git checkout develop
git pull origin develop
```

### Step 10: Update backlog
Mark TICK-931 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-931.prompt.md`) after merge.
