# Ticket TICK-808 — Hardware section crash SIGSEGV (scan comprehensive + storage + hardware)

> **Wave 8** | **Domain:** UI / Hardware | **Depends on:** None
> **Source:** `dataforge/ui/views/hardware_view.py`, `dataforge/modules/hardware.py`, log `19:58:21-19:58:52` SIGSEGV

---

## Your Assignment

```
TICKET_ID: TICK-808
WAVE: 8
TITLE: Hardware section crash SIGSEGV (scan comprehensive + storage + hardware)
```

**Exclusive write files (SOLE writer for Wave 8):**
- `dataforge/ui/views/hardware_view.py`
- `dataforge/modules/hardware.py`
- `dataforge/ui/app.py`

**Read-only references (do not edit):**
- `dataforge/ui/job_manager.py`
- `dataforge/engine/jobs.py`
- `dataforge/modules/performance.py`

**Test target:** `tests/test_hardware_crash.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_hardware_crash.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` Hardware section
- `docs/ARCHITECTURE.md` §Hardware
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `ui/views/hardware_view.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-808"
title: "Hardware section crash SIGSEGV (scan comprehensive + storage + hardware)"
type: "Bugfix"
execution_wave: 8
depends_on: []
scope:
  domain: "UI / Hardware"
  exclusive_write_files:
    - "dataforge/ui/views/hardware_view.py"
    - "dataforge/modules/hardware.py"
    - "dataforge/ui/app.py"
  read_only_references:
    - "dataforge/ui/job_manager.py"
    - "dataforge/engine/jobs.py"
    - "dataforge/modules/performance.py"
architectural_context:
  existing_symbols_to_use:
    - "hardware_view.py: HardwareView, mount, _run_scan"
    - "hardware.py: get_hardware_report"
    - "app.py: switch_view, JobManager, _animate_opacity"
  breaking_changes: "None — crash fix, no API change"
requirements:
  summary: |
    Suddenly crashes when opening Hardware section. Log shows 4 jobs submitted at startup: scan comprehensive (Dashboard), Scan storage devices, collect overview data (Performance), get hardware report (Hardware) → all via run_workflow at app.__init__+mount simultaneously, ThreadPool+QGraphicsOpacityEffect transient fix 02db013 races, plus HardwareView.mount() fires on every switch_view without debounce, and hardware.py _get_* does psutil/lsblk/lspci/dmidecode without timeout/cancel.

    Fix: debounce HardwareView.mount (once + manual Refresh), make hardware.py get_hardware_report check cancel_token per step (already in dc44be4 but ensure), add timeout to _run_cmd (already 10s), make app.py build_navigation_sidebar guard _in_sidebar_update and ensure JobManager not GC mid-flight, and add hardware_view _run_scan to use cancel_token and progress. Also fix QPainter recursion: ensure hardware_view _build_overview does not call update()/repaint() during paint, use viewport().update() after.

    Must handle SIGSEGV from QBackingStore::endPaint with active painter — ensure no QPainter::begin without end, no repaint() during paint, and setGraphicsEffect removal is deferred via QTimer.singleShot.

    The log shows fish Job 1 terminated by SIGSEGV after get hardware report — likely due to concurrent QPainter from Performance and Hardware both updating progress bars while crossfade compositing.
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
  acceptance_criteria:
    - "GIVEN Hardware view opened 10 times rapidly WHEN switching THEN no SIGSEGV, no QPainter errors"
    - "GIVEN Dashboard + Storage + Performance + Hardware jobs submitted at startup WHEN cancel_token set THEN all respect cancel and is_busy becomes False within 1s"
    - "GIVEN Hardware scan with cancel WHEN _run_scan called THEN respects cancel_token and returns {'cancelled': True}"
    - "GIVEN existing hardware tests WHEN this change applied THEN still pass"
verification:
  test_target: "tests/test_hardware_crash.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_hardware_crash.py -q"
```

---

## Implementation Notes

```python
# hardware_view.py: debounce mount, add cancel_token, fix QPainter
def mount(self):
    if self._has_scanned:
        return
    self._run_scan()

# hardware.py: ensure _check_cancel per step (already)
# app.py: ensure switch_view debounces and JobManager not GC
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-808` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-808
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
git checkout -b fix/TICK-808-hardware-crash
PYTHONPATH=. python -m pytest tests/test_hardware_crash.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add <exclusive> tests/test_*.py
git commit -m "fix(ui): hardware crash SIGSEGV"
git push -u origin fix/TICK-808-hardware-crash
```

## Work Package YAML for TICK-808

```yaml
ticket_id: "TICK-808"
title: "Hardware section crash SIGSEGV (scan comprehensive + storage + hardware)"
type: "Bugfix"
execution_wave: 8
depends_on: []
scope:
  domain: "UI / Hardware"
  exclusive_write_files:
    - "dataforge/ui/views/hardware_view.py"
    - "dataforge/modules/hardware.py"
    - "dataforge/ui/app.py"
  read_only_references:
    - "dataforge/ui/job_manager.py"
architectural_context:
  existing_symbols_to_use:
    - "hardware_view.py: HardwareView"
  breaking_changes: "None"
requirements:
  summary: "Fix hardware crash"
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN Hardware opened 10 times rapidly WHEN switching THEN no SIGSEGV"
verification:
  test_target: "tests/test_hardware_crash.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_hardware_crash.py -q"
```
