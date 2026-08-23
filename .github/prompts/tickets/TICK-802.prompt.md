# Ticket TICK-802 — STOP comprehensive — review entire code cancel paths

> **Wave 8** | **Domain:** Core / Jobs+Scanner | **Depends on:** None
> **Source:** `docs/reviews/AUDIT_REPORT.md` R-CORE/R-OPS, `FORENSIC_REVIEW.md` F13, user report STOP does nothing

---

## Your Assignment

```
TICKET_ID: TICK-802
WAVE: 8
TITLE: STOP comprehensive — review entire code cancel paths
```

**Exclusive write files (SOLE writer for Wave 8):**
- `dataforge/ui/job_manager.py`
- `dataforge/engine/jobs.py`

**Read-only references (do not edit):**
- `dataforge/core/scanner.py`
- `dataforge/core/hasher.py`
- `dataforge/modules/search.py`
- `dataforge/modules/duplicates.py`
- `dataforge/modules/recovery.py`
- `dataforge/core/services/file_actions.py`
- `dataforge/ui/app.py`

**Test target:** `tests/test_stop_comprehensive.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_stop_comprehensive.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/ARCHITECTURE.md` §Engine + JobManager
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `engine/jobs.py`, `ui/job_manager.py`
- `docs/CONTRIBUTING.md` §8

---

## Work Package YAML

```yaml
ticket_id: "TICK-802"
title: "STOP comprehensive — review entire code cancel paths"
type: "Bugfix"
execution_wave: 8
depends_on: []
scope:
  domain: "Core / Jobs+Scanner"
  exclusive_write_files:
    - "dataforge/ui/job_manager.py"
    - "dataforge/engine/jobs.py"
  read_only_references:
    - "dataforge/core/scanner.py"
    - "dataforge/core/hasher.py"
    - "dataforge/modules/search.py"
    - "dataforge/modules/duplicates.py"
    - "dataforge/modules/recovery.py"
    - "dataforge/core/services/file_actions.py"
    - "dataforge/ui/app.py"
architectural_context:
  existing_symbols_to_use:
    - "job_manager.py: JobManager, ManagedWorker, cancel_all, is_busy"
    - "jobs.py: JobQueue, Job, cancel_token, is_cancelled"
  breaking_changes: "None — cancel semantics additive, progress chaining preserved"
requirements:
  summary: |
    STOP sometimes does not stop — review entire cancel path. Current fix in dc44be4 handled **kwargs + progress chaining + photorec/hardware/search/duplicates cancel, but double-execution (JobManager runs job twice: JobQueue ThreadPool + ManagedWorker QThread) still exists and many per-chunk loops only check at batch boundaries. Review every cancel_token.is_set() site: scanner per-file, hasher per-1MiB, search per-50, duplicates per-stage, recovery per-window, file_actions per-item, media_ops, hardware, dashboard/storage/performance views. Ensure every long loop checks at least per-100ms or per-MiB, and that InterruptedError is normalized to {"cancelled": True} not error dialog, and that JobManager.submit no longer double-runs (use JobQueue only for bookkeeping, ManagedWorker as sole executor) or documents why double is intentional and fixes is_busy/progress.

    Also ensure cancel_all cancels both queue futures and QThreads, and that app.cancel_action force-hides after 2s.
  source_documents:
    - "docs/reviews/AUDIT_REPORT.md"
    - "docs/reviews/FORENSIC_REVIEW.md"
  acceptance_criteria:
    - "GIVEN long scan (10k files) WHEN cancel_token set after 100ms THEN job returns within 500ms and UI hides STOP"
    - "GIVEN ManagedWorker target with **kwargs WHEN submit with cancel_token THEN token is received (not missing due to VAR_KEYWORD bug)"
    - "GIVEN JobManager with 2 concurrent jobs WHEN cancel_all called THEN both receive cancel and is_busy becomes False within 1s"
    - "GIVEN existing 412 job_manager tests WHEN this change applied THEN still pass (no double-execution regression)"
verification:
  test_target: "tests/test_stop_comprehensive.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_stop_comprehensive.py -q"
```

---

## Implementation Notes

```python
# job_manager.py: check VAR_KEYWORD already fixed in dc44be4, now fix double execution:
# Option A: keep double but make is_busy check both queue and _workers (done), fix progress bridging (done)
# Option B (preferred for Wave 9 full sweep): make JobQueue a pure registry (no _executor.submit) and let ManagedWorker be sole executor. Document choice.

# jobs.py: ensure cancel() sets status CANCELLED even if RUNNING, and that _run_job checks is_cancelled before/after _invoke_worker
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-802` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-802
WAVE: 8
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
git checkout -b fix/TICK-802-stop-comprehensive
PYTHONPATH=. python -m pytest tests/test_stop_comprehensive.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add <exclusive> tests/test_*.py
git commit -m "fix(core): comprehensive STOP cancel review"
git push -u origin fix/TICK-802-stop-comprehensive
```

## Work Package YAML for TICK-802

```yaml
ticket_id: "TICK-802"
title: "STOP comprehensive — review entire code cancel paths"
type: "Bugfix"
execution_wave: 8
depends_on: []
scope:
  domain: "Core / Jobs+Scanner"
  exclusive_write_files:
    - "dataforge/ui/job_manager.py"
    - "dataforge/engine/jobs.py"
  read_only_references:
    - "dataforge/core/scanner.py"
architectural_context:
  existing_symbols_to_use:
    - "job_manager.py: JobManager"
  breaking_changes: "None"
requirements:
  summary: "Review entire cancel path"
  source_documents:
    - "docs/reviews/AUDIT_REPORT.md"
  acceptance_criteria:
    - "GIVEN long scan WHEN cancel THEN returns within 500ms"
verification:
  test_target: "tests/test_stop_comprehensive.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_stop_comprehensive.py -q"
```
