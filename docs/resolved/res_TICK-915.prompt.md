# TICK-915 — Job engine: max_workers enforcement, cancellation guard, state ownership

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-915 |
| Wave | 11 — Critical Stability (P0) |
| Priority | P0 — Data loss / resource exhaustion |
| Depends on | TICK-914 |
| Files to modify | `dataforge/engine/jobs.py` |
| Files to create | `tests/test_job_engine_contract.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P0.4, P0.5, P0.9, P0.10, P1.20 |
| Validation | `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_job_engine_contract.py -q` |

## Context

**P0.4 — Unbounded workers:** `JobManager` creates `JobQueue(max_workers=4)` but submits with `execute=False` (`job_manager.py:400-408`), then immediately starts a `ManagedWorker` QThread per job (`job_manager.py:524-528`). The `ThreadPoolExecutor` inside `JobQueue` is never used for UI jobs. `max_workers` has no effect. Burst submissions spawn unbounded QThreads.

**P0.5 — Cancelled jobs execute:** `JobQueue.cancel()` marks a job cancelled (`jobs.py:436-450`), but `ManagedWorker.run()` at `job_manager.py:102-120` only checks cancellation for the RUNNING transition. If the job is already CANCELLED when `run()` starts, it still invokes the target at line 142.

**P0.10 — State races:** `ManagedWorker.run()` mutates `Job.status`, `results`, `error`, `events` directly (`job_manager.py:98-211`). Manager callbacks mutate the same fields under `JobQueue._lock` (`job_manager.py:430-500`). No synchronization between the two.

**P0.9 — Progress sentinel:** `JobEvent.total` requires `ge=0` (`schema.py:194`). Daemon emits `progress_callback(len(entries), -1, ...)` (`daemon.py:376`). `JobQueue._progress()` constructs the event without converting (`jobs.py:184-200`).

**P1.20 — TypeError retry:** `_invoke_worker()` at `jobs.py:223-263` retries a target under multiple calling conventions after any `TypeError`. A target that mutates state and then raises `TypeError` can run multiple times.

**P1.20 — Shutdown leaks:** `shutdown()` at `jobs.py:469-470` calls `executor.shutdown()` but does not transition pending `Job` objects to CANCELLED. `_futures` retains every completed future reference.

## Objectives

1. Enforce `max_workers` so UI jobs respect the configured concurrency limit.
2. Prevent cancelled queued jobs from invoking their target.
3. Establish single ownership of `Job` state transitions.
4. Eliminate `TypeError` retry; inspect signature once.
5. Fix shutdown to terminalize all pending jobs and release references.
6. Fix progress sentinel to accept unknown totals.

## Implementation Guide

### Step 1: Enforce max_workers

Option A (preferred): Make `JobQueue` the actual executor. Remove `execute=False` path. Let `JobQueue._run_job` run via `ThreadPoolExecutor`. Bridge completion to Qt signals via a thin adapter.

Option B (minimal): Add a semaphore or queue in `JobManager`. When submitting, if active worker count >= max_workers, queue the job. When a worker finishes (`_on_worker_finished`), dequeue and start the next.

### Step 2: Guard cancelled jobs

In `ManagedWorker.run()`, after the status update block (`job_manager.py:100-118`), add:

```python
if self._job is not None and self._job.status == JobStatus.CANCELLED:
    self.result_signal.emit({"cancelled": True, "message": "cancelled before start"})
    return
```

This must come before `self._target(...)` invocation at line 142.

### Step 3: Single state ownership

All `Job` field mutations must go through `JobQueue._lock`. Remove direct mutations from `ManagedWorker.run()`. Instead, have the worker emit signals; the manager applies state changes under lock in its slots (connected in TICK-914).

### Step 4: Inspect signature once

In `_invoke_worker()`, inspect the target signature once at the start. Build one kwargs dict. Call the target once. Remove the retry loop at `jobs.py:223-263`.

### Step 5: Fix shutdown

In `JobQueue.shutdown()`:

```python
def shutdown(self, wait=True, cancel_futures=False):
    with self._lock:
        for job in self._jobs.values():
            if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                job.cancel()
    self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)
    with self._lock:
        self._futures.clear()
```

### Step 6: Fix progress sentinel

In `_progress()` at `jobs.py:184-200`, convert `-1` to `None`:

```python
def _progress(current, total, message=""):
    if job.is_cancelled():
        return
    safe_total = None if total is not None and total < 0 else total
    evt = JobEvent(job_id=job.job_id, type="progress", current=current, total=safe_total, message=message)
    ...
```

## Unit Tests

Create `tests/test_job_engine_contract.py`:

| Test function | What it asserts |
|---|---|
| `test_max_workers_limits_concurrency` | Set max_workers=1. Submit 5 blocking jobs. Assert at most 1 runs at a time (check `active_job_count` or use a shared counter with threading.Lock). |
| `test_cancelled_queued_job_never_invokes_target` | Cancel a job before it starts. Assert target call count == 0 (use a mock/call counter). |
| `test_cancelled_running_job_stops_gracefully` | Cancel a running job that checks token. Assert it returns cancelled result. |
| `test_exactly_one_terminal_event_per_job` | Run a job to completion. Count events with type=="status" and terminal status. Assert == 1. |
| `test_typeerror_retry_does_not_re_execute` | Submit a target that mutates a counter then raises TypeError. Assert counter == 1 (not > 1). |
| `test_shutdown_transitions_pending_to_cancelled` | Queue 3 jobs. Shutdown. Assert all 3 have status CANCELLED. |
| `test_shutdown_clears_futures` | Queue and complete 3 jobs. Shutdown. Assert `_futures` is empty. |
| `test_progress_negative_total_becomes_none` | Emit progress with total=-1. Assert `JobEvent.total is None`. |
| `test_progress_zero_total_preserved` | Emit progress with total=0. Assert `JobEvent.total == 0`. |
| `test_job_status_transitions_are_deterministic` | Run, complete, fail, cancel jobs. Assert status sequence is QUEUED→RUNNING→DONE/FAILED/CANCELLED (no duplicates, no skips). |

## Edge Cases

- Submit job with max_workers=0 (should reject or use 1).
- Cancel job that is already DONE (no-op, returns False).
- Shutdown with cancel_futures=True while jobs are running.
- Target that raises `KeyboardInterrupt` (normalize to cancelled).
- Target that returns `{"cancelled": True}` without token being set (treat as cancelled).

## Validation Checklist

- [ ] `python -m pytest tests/test_job_engine_contract.py -q` passes
- [ ] `ruff check dataforge/engine/jobs.py` passes
- [ ] No `TypeError` retry loop remains in `_invoke_worker`
- [ ] `shutdown()` transitions pending jobs to CANCELLED
- [ ] `_futures` is cleared after shutdown
- [ ] `JobEvent` accepts `total=None`
- [ ] Cancelled queued job never reaches target invocation

## Definition of Done

All 10 unit tests pass. max_workers is enforced. Cancelled jobs never execute. State transitions are deterministic. Shutdown is clean. Progress sentinel is fixed.

## File References

### Files to modify
- `dataforge/engine/jobs.py`
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
- `tests/test_job_engine_contract.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-915-job-engine-max-workers-cancellation
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
git commit -m "fix(<scope>): <description> (TICK-915)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-915.

### Step 6: Push to remote
```bash
git push origin fix/TICK-915-job-engine-max-workers-cancellation
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff fix/TICK-915-job-engine-max-workers-cancellation -m "Merge fix/TICK-915 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-915-job-engine-max-workers-cancellation
git push origin --delete fix/TICK-915-job-engine-max-workers-cancellation
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-915 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-915.prompt.md`) after merge.
