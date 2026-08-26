# Ticket TICK-911 — Global app stability audit + job lifecycle hardening

> **Wave 10** | **Domain:** Core / Engine | **Depends on:** Wave 9 (901-908)
> **Source:** user report `Review entire app for issues like this, due recent changes entire app has broken things like those ones.` + `dataforge/ui/job_manager.py:1`, `dataforge/engine/jobs.py:1`, `dataforge/engine/daemon.py:1`

---

## Your Assignment

```
TICKET_ID: TICK-911
WAVE: 10
TITLE: Global app stability audit + job lifecycle hardening
```

**Exclusive write files (SOLE writer for Wave 10):**
- `dataforge/ui/job_manager.py`
- `dataforge/engine/jobs.py`
- `dataforge/engine/daemon.py`

**Read-only references (do not edit):**
- `dataforge/ui/app.py`
- `dataforge/core/scanner.py`
- `dataforge/core/hasher.py`
- `dataforge/modules/duplicates.py`
- `dataforge/modules/system_cleanup.py`
- `dataforge/modules/metadata.py`
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

**Test target:** `tests/test_global_stability.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_global_stability.py -q`

**Depends on:** ["TICK-901", "TICK-902", "TICK-903", "TICK-904", "TICK-905", "TICK-906", "TICK-907", "TICK-908"]

---

## Relevant Documentation — Must Read Before Coding

- `docs/CONSOLIDATED_SPEC.md` §2–7
- `docs/ARCHITECTURE.md` §Engine / §Jobs / §UI threading
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `engine/jobs.py`, `ui/job_manager.py`, `engine/daemon.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-911"
title: "Global app stability audit + job lifecycle hardening"
type: "Bugfix"
execution_wave: 10
depends_on: ["TICK-901", "TICK-902", "TICK-903", "TICK-904", "TICK-905", "TICK-906", "TICK-907", "TICK-908"]
scope:
  domain: "Core / Engine"
  exclusive_write_files:
    - "dataforge/ui/job_manager.py"
    - "dataforge/engine/jobs.py"
    - "dataforge/engine/daemon.py"
  read_only_references:
    - "dataforge/ui/app.py"
    - "dataforge/core/scanner.py"
    - "dataforge/core/hasher.py"
    - "dataforge/modules/duplicates.py"
    - "dataforge/modules/system_cleanup.py"
    - "dataforge/modules/metadata.py"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
architectural_context:
  existing_symbols_to_use:
    - "jobs.py: Job, JobQueue, QUEUE_DEPTH, JobStatus, JobEvent, submit/get/cancel/list_jobs"
    - "job_manager.py: JobManager, ManagedWorker, is_busy, cancel_all, submit, _is_destructive, progress_signal"
    - "daemon.py: EngineDaemon, Daemon, JobQueue bridge, auto_discover transports"
    - "app.py: DataForgeApp.run_workflow, run_background, cancel_action, _on_job_completed (read-only)"
  breaking_changes: "None — hardening, no API break"
requirements:
  summary: |
    Recent Wave 7/8 changes broke the entire app with SIGSEGV/SIGABRT/malloc double-free across Hardware, MediaTools, Duplicate finder, Junk scan. The common thread is job lifecycle and paint/threading races introduced by parallel BFS scanner (TICK-102), batch cache (TICK-104), forensics streaming (TICK-109/304), JobManager queue (TICK-401), and QGraphicsOpacityEffect crossfade (app.py ViewAnim). This ticket is the global sweep that did not fit into per-module hotfixes (901-908).

    Audit entire app for:

    * Double-submit: JobManager currently uses JobQueue as registry (execute=False) + ManagedWorker QThread (TICK-802 fix). Verify no view still calls `JobQueue.submit(execute=True)` directly or spawns raw QThread+JobQueue simultaneously. Grep for `JobQueue().submit` and `QThread(` outside job_manager.

    * Cancel token propagation: every long-running target must accept `cancel_token: threading.Event` and `progress_callback`. Views that call `app.run_workflow(target, on_success, arg1, arg2, progress=True)` must have target sig with both params, even if via **kwargs VAR_KEYWORD already handled, but ensure hasher, scanner, duplicates, system_cleanup, metadata, media_ops all check token frequently (per 1k batch or per file). Missing checks cause STOP to appear stuck and then force-hide to trigger while worker still holds mmap/pixmap → SIGSEGV.

    * Progress signal flood: app.py update_progress → progress_bar.setRange/setValue triggers paint on every progress_callback. When 32 ThreadPool workers all call progress_callback, status bar repaints 32x per second during crossfade → QBackingStore active painter. Throttle progress in JobManager: coalesce to 100ms or every 10 items.

    * Daemon Engine reuse: engine/jobs.py JobQueue currently uses ThreadPoolExecutor 4; but daemon.py also has its own JobQueue for FastAPI/UDS transport. Ensure they don't share same queue depth logic causing queue full rejection that view treats as silent None.

    * Evidence mode bypass: JobManager._is_destructive checks target name only, but FileActionService direct calls from widgets.py EnhancedTreeview (rename/delete/move) bypass JobManager entirely and thus bypass evidence_mode check. Ensure those file actions also check `config.get("evidence_mode")` or `app.evidence_mode`.

    * Shutdown leak: JobManager.shutdown(wait=True) vs app close not calling it → dangling threads on exit.

    Fix:

    * jobs.py: add invariant tests for queue depth (8), ULID uniqueness under burst submit 20 jobs, cancel while QUEUED → CANCELLED without RUNNING, and that get_hash many etc not deadlock. Add `JobQueue.submit` validation that `execute` param is explicit (no default that hides double-execute). Add docstring.

    * job_manager.py: add progress coalescing (time-based 100ms), ensure `progress_callback` chaining preserves caller callback + signal, and that cancel_token set also sets Job.status=CANCELLED synchronously (already but verify). Add `submit` guard: if queue._queued_count >= QUEUE_DEPTH then reject with error callback "Too many jobs, try again". Add `shutdown` called from DataForgeApp.closeEvent (read-only check but job_manager can expose method). Add evidence_mode check also for targets that are FileActionService methods called via widgets (by inspecting target.__qualname__).

    * daemon.py: ensure it imports JobQueue correctly, supports cancel_token per job, and that `Daemon` is still side-effect-free on import.

    * Produce a small fuzz harness in test: submit 20 jobs with varying cancel patterns + progress flood, verify no SIGSEGV, is_busy eventually False.

  source_documents:
    - "docs/CONSOLIDATED_SPEC.md"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
    - "dataforge/ui/job_manager.py:1"
    - "dataforge/engine/jobs.py:1"
  acceptance_criteria:
    - "GIVEN 20 concurrent jobs (scan + hash + junk + dup) submitted via JobManager WHEN running with cancel bursts THEN no double execution (each target call count ==1), is_busy eventually False within 3s, no dangling QThreads"
    - "GIVEN progress_callback called 1000 times per second via 32 workers WHEN throttled THEN app.update_progress called at most 10 times per second (100ms coalesce) and no QBackingStore warnings"
    - "GIVEN JobQueue depth 8 WHEN submitting 9th job while 8 queued THEN 9th rejected with on_error 'queue full' and not lost"
    - "GIVEN evidence_mode true WHEN EnhancedTreeview rename/delete called via FileActionService directly THEN blocked with PermissionError Evidence Mode (not via JobManager bypass)"
    - "GIVEN daemon import WHEN imported THEN no server start, side-effect-free, and Job import works"
verification:
  test_target: "tests/test_global_stability.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_global_stability.py -q"
```

---

## Implementation Notes

```python
# job_manager.py — coalesce progress
import time
class ManagedWorker(QThread):
    def run(self):
        last_emit = 0
        def progress_callback(c,t,m=""):
            nonlocal last_emit
            now = time.time()
            if now - last_emit < 0.1 and t>0 and c != t:
                return  # throttle
            last_emit = now
            self.progress_signal.emit(c,t,m)
            if orig_cb: orig_cb(c,t,m)

# jobs.py — explicit execute param
def submit(self, target, params=None, progress_callback=None, execute: bool = False):
    # if execute True, run via ThreadPool, else registry only
    ...

# app.py read-only but job_manager exposes shutdown for closeEvent
# Ensure daemon side-effect free:
# if __name__ == "__main__" guard already
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-911` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-911
WAVE: 10
```

## Required Reading (in order)

1. `docs/CONSOLIDATED_SPEC.md` §2–7
2. `docs/PARALLEL_BACKLOG.md` Concurrency Map + How to Work a Ticket
3. `docs/CONTRIBUTING.md` §3, §8, §10
4. Your Work Package YAML above
5. `read_only_references` files

## File Ownership

- Write only to `exclusive_write_files`. New files carry ` [NEW FILE]`.
- Central touchpoints are single-writer per wave.

## Workflow

```bash
git checkout develop && git pull origin develop
git checkout -b fix/TICK-911-global-stability-audit
PYTHONPATH=. python -m pytest tests/test_global_stability.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add dataforge/ui/job_manager.py dataforge/engine/jobs.py dataforge/engine/daemon.py tests/test_global_stability.py
git commit -m "fix(engine): global job lifecycle stability audit"
git push -u origin fix/TICK-911-global-stability-audit
```

## Work Package YAML for TICK-911

```yaml
ticket_id: "TICK-911"
title: "Global app stability audit + job lifecycle hardening"
type: "Bugfix"
execution_wave: 10
depends_on: ["TICK-901", "TICK-902", "TICK-903", "TICK-904", "TICK-905", "TICK-906", "TICK-907", "TICK-908"]
scope:
  domain: "Core / Engine"
  exclusive_write_files:
    - "dataforge/ui/job_manager.py"
    - "dataforge/engine/jobs.py"
    - "dataforge/engine/daemon.py"
  read_only_references:
    - "dataforge/ui/app.py"
architectural_context:
  existing_symbols_to_use:
    - "jobs.py: Job, JobQueue"
  breaking_changes: "None"
requirements:
  summary: "Audit entire app for job/paint races"
  source_documents:
    - "docs/CONSOLIDATED_SPEC.md"
  acceptance_criteria:
    - "GIVEN 20 jobs burst THEN no double exec"
verification:
  test_target: "tests/test_global_stability.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_global_stability.py -q"
```
