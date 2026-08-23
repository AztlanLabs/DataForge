# TICK-914 — Progress callback safety + QThread lifecycle + affinity contract

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-914 |
| Wave | 11 — Critical Stability (P0) |
| Priority | P0 — Crash fix |
| Depends on | Wave 10 (TICK-911, TICK-912, TICK-913) complete |
| Files to modify | `dataforge/ui/job_manager.py` |
| Files to create | `tests/test_job_lifecycle_safety.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P0.1, P0.2, P0.3 |
| Validation | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_job_lifecycle_safety.py -q` |

## Context

The application crashes with SIGSEGV after submitting background jobs. Two root causes:

**Cause 1 — Cross-thread widget mutation (P0.1):** `ManagedWorker.run()` at `job_manager.py:128-140` invokes the caller's `progress_callback` inline on the worker thread. For GUI workflows this callback is `app.post_progress` (`app.py:884-889`), which checks `isinstance(curr_thread, BackgroundWorker)`. Since `ManagedWorker` is not `BackgroundWorker`, the check fails and `update_progress()` runs on the QThread, mutating `QProgressBar` and `QLabel` (`app.py:854-865,393-394`). The same event is then emitted through `progress_signal`, producing a second GUI-thread update. Two unsynchronized updates per tick cause `QWidget::repaint: Recursive repaint detected` and painter corruption.

**Cause 2 — Premature QThread deletion (P0.3):** `finished_signal` is emitted at `job_manager.py:284-285` inside `run()`, before the QThread has returned. The connected cleanup at `job_manager.py:654-660` calls `worker.deleteLater()`. This destroys the QThread while still running, causing `QThread: Destroyed while thread is still running` abort.

**Cause 3 — Implicit affinity contract (P0.2):** Signal connections at `job_manager.py:506-520` use plain closures. PyQt5 currently delivers these on the GUI thread when connected from the GUI thread, but this is implicit behavior. The docstring at `job_manager.py:634-640` incorrectly claims "this slot runs on the main thread (Qt queued connection)".

## Objectives

1. Eliminate all Qt widget mutations from worker threads.
2. Ensure QThread cleanup happens only after native thread termination.
3. Make GUI-thread delivery explicit and testable, not implicit.
4. Coalesce noisy progress updates to prevent repaint storms.
5. Add permanent regression tests that catch thread-affinity violations.

## Implementation Guide

### Step 1: Remove inline callback invocation in ManagedWorker.run()

In `job_manager.py:128-140`, the code chains `orig_cb` before emitting `progress_signal`:

```python
orig_cb = kwargs_copy.get("progress_callback")
def progress_callback(current, total, step_name=""):
    if orig_cb: orig_cb(current, total, step_name)  # REMOVE THIS LINE
    self.progress_signal.emit(current, total, step_name)
```

Change to: emit `progress_signal` only. Never invoke `orig_cb` inline. The signal delivery to the GUI thread is the sole progress path.

### Step 2: Connect cleanup to native QThread.finished

Replace `worker.finished_signal.connect(self._on_worker_finished)` at `job_manager.py:522` with a lambda that captures the job_id:

```python
# Native QThread.finished emits no arguments, but _on_worker_finished expects (job_id: str).
# Use a lambda to capture the job_id at connection time:
worker.finished.connect(lambda jid=job.job_id: self._on_worker_finished(jid))
```

Or use `QObject.sender()` inside the handler to look up the worker. The native signal fires after `run()` returns and the thread has stopped. Do NOT connect directly as `worker.finished.connect(self._on_worker_finished)` — the signature mismatch will raise `TypeError` or silently lose the job_id, leaking `_workers`.

Update `_on_worker_finished` to still accept `(job_id: str)` via the lambda capture.

### Step 3: Add explicit GUI-affine dispatch slots on JobManager

Add decorated `@pyqtSlot` methods on `JobManager` (a QObject living in the GUI thread):

```python
@pyqtSlot(int, int, str)
def _dispatch_progress(self, current, total, message):
    # Runs on GUI thread because JobManager lives in GUI thread
    # Forward to stored per-job on_progress callback
    ...

@pyqtSlot(object)
def _dispatch_result(self, result):
    # Runs on GUI thread
    # Forward to stored per-job on_success callback
    ...

@pyqtSlot(Exception)
def _dispatch_error(self, error):
    # Runs on GUI thread
    # Forward to stored per-job on_error callback
    ...
```

Connect `worker.progress_signal`, `worker.result_signal`, `worker.error_signal` to these slots using `Qt.QueuedConnection` (explicit, not implicit).

### Step 4: Coalesce progress updates

Add a per-job timestamp tracker. In `_dispatch_progress`, skip if less than 100ms since last delivered update for this job (except for 0/total and total/total boundaries).

### Step 5: Add DataForgeApp.closeEvent()

Note: This step edits `dataforge/ui/app.py`. If your ticket's exclusive_write_files lists only `job_manager.py`, either expand it to include `app.py` or move this step to TICK-917 (which already owns `app.py`). Coordinate with the backlog owner.

In `app.py`, override `closeEvent()`:

```python
def closeEvent(self, event):
    self.job_manager.shutdown()  # cancel all + wait
    super().closeEvent(event)
```

Ensure `JobManager.shutdown()` waits for all `ManagedWorker` threads by calling `worker.wait()` on each.

### Step 6: Guard against post-terminal events

In `_dispatch_progress`, `_dispatch_result`, `_dispatch_error`: check if the job is already in a terminal state (DONE/FAILED/CANCELLED). If so, discard the event.

## Unit Tests

Create `tests/test_job_lifecycle_safety.py` with the following test functions:

| Test function | What it asserts |
|---|---|
| `test_progress_callback_runs_on_gui_thread` | Submit a progress=True job. Record `QThread.currentThread()` inside the progress callback. Assert it equals `QApplication.instance().thread()`. |
| `test_result_callback_runs_on_gui_thread` | Submit a job. Record thread in `on_success`. Assert GUI thread. |
| `test_error_callback_runs_on_gui_thread` | Submit a job that raises. Record thread in `on_error`. Assert GUI thread. |
| `test_progress_called_exactly_once_per_event` | Submit a job that emits 5 progress events. Count `update_progress` calls via mock. Assert count == 5. |
| `test_no_duplicate_progress_per_tick` | Submit a job. Count total progress signal emissions vs delivered callbacks. Assert 1:1 (no double delivery). |
| `test_qthread_cleanup_after_native_finish` | Submit a job, wait for completion. Assert no `QThread: Destroyed` warnings in stderr. Use `capsys` on stderr with `QT_QPA_PLATFORM=offscreen`. Call `QApplication.processEvents()` to ensure pending events are processed. |
| `test_shutdown_waits_for_active_workers` | Submit a long-running job. Call `shutdown()`. Assert it returns only after the worker finishes. Assert no abort/warning. |
| `test_completion_callback_submits_followup_job` | In `on_success`, submit a second job. Assert both complete. Assert second job's callback runs on GUI thread. |
| `test_worker_does_not_touch_widgets` | Submit a job. Inside the target function, assert `QApplication.instance().thread() != QThread.currentThread()` (worker is NOT on GUI thread). |
| `test_progress_after_terminal_is_discarded` | Complete a job, then directly call `_dispatch_progress` after setting terminal status. Assert no crash and no update_progress call. Requires `QSignalSpy` or direct method call (late emit via signal after DONE may already be discarded). |

## Edge Cases

- Job that emits 0 progress events (no progress delivery, no crash).
- Job that emits 1000 rapid progress events (coalescing works, no repaint storm).
- Job that raises `InterruptedError` (cancellation path, no error dialog).
- Job submitted during another job's completion callback (reentrant submission).
- Shutdown called with 0 active jobs (immediate return).
- Shutdown called with 8 active jobs (all terminate).

## Validation Checklist

- [ ] `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_job_lifecycle_safety.py -q` passes
- [ ] `ruff check dataforge/ui/job_manager.py` passes
- [ ] No `orig_cb` invocation remains in `ManagedWorker.run()`
- [ ] `finished_signal` is not connected to cleanup (use native `finished`)
- [ ] `_on_worker_finished` is connected via `worker.finished.connect()`
- [ ] `DataForgeApp.closeEvent` exists and calls `shutdown()`
- [ ] `JobManager.shutdown()` calls `worker.wait()` on all active workers
- [ ] No `QThread: Destroyed` or `Recursive repaint` in test stderr

## Definition of Done

All 10 unit tests pass. No Qt warnings in stderr. `ruff` clean. The `orig_cb` chaining is removed. Cleanup uses native `QThread.finished`. `closeEvent` exists. Progress is coalesced. Every callback entry point has an explicit affinity contract.

## File References

### Files to modify
- `dataforge/ui/job_manager.py`
### Test files to create/modify
- `tests/test_*.py` (see Unit Tests section above)

### Audit documentation
- `docs/reviews/STABILITY_AUDIT_2026-08-23.md` — source of all findings
- `docs/PARALLEL_BACKLOG.md` — ticket definitions and wave DAG
- `docs/prompts/tickets/README.md` — ticket index

### Related tickets
- Depends on: Wave 10 (TICK-911, TICK-912, TICK-913)
- Blocks: see wave DAG in `docs/PARALLEL_BACKLOG.md`

### Test file
- `tests/test_job_lifecycle_safety.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-914-progress-callback-qthread-lifecycle
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
git commit -m "fix(<scope>): <description> (TICK-914)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-914.

### Step 6: Push to remote
```bash
git push origin fix/TICK-914-progress-callback-qthread-lifecycle
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff fix/TICK-914-progress-callback-qthread-lifecycle -m "Merge fix/TICK-914 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-914-progress-callback-qthread-lifecycle
git push origin --delete fix/TICK-914-progress-callback-qthread-lifecycle
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-914 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-914.prompt.md`) after merge.
