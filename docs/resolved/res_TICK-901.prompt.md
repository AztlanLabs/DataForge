# Ticket TICK-901 — Hardware section QPainter/SIGSEGV deep hardening

> **Wave 9** | **Domain:** UI / Hardware | **Depends on:** None
> **Source:** logs `2026-08-22 21:43:25` + `21:58:33` `QPainter::begin: A paint device can only be painted by one painter at a time` `QBackingStore::endPaint() called with active painter` `SIGSEGV`/`SIGABRT` `hardware_view.py:319 'EnhancedTreeview' object has no attribute 'viewport'`, `dataforge/ui/views/hardware_view.py:1`, `dataforge/modules/hardware.py:1`, `dataforge/ui/app.py:404`

---

## Your Assignment

```
TICKET_ID: TICK-901
WAVE: 9
TITLE: Hardware section QPainter/SIGSEGV deep hardening
```

**Exclusive write files (SOLE writer for Wave 9):**
- `dataforge/ui/views/hardware_view.py`
- `dataforge/modules/hardware.py`

**Read-only references (do not edit):**
- `dataforge/ui/job_manager.py`
- `dataforge/engine/jobs.py`
- `dataforge/ui/widgets.py`
- `dataforge/ui/app.py`
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

**Test target:** `tests/test_hardware_stability.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_hardware_stability.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` Hardware section
- `docs/ARCHITECTURE.md` §Hardware / §UI threading
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `ui/views/hardware_view.py`, `modules/hardware.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-901"
title: "Hardware section QPainter/SIGSEGV deep hardening"
type: "Bugfix"
execution_wave: 9
depends_on: []
scope:
  domain: "UI / Hardware"
  exclusive_write_files:
    - "dataforge/ui/views/hardware_view.py"
    - "dataforge/modules/hardware.py"
  read_only_references:
    - "dataforge/ui/job_manager.py"
    - "dataforge/engine/jobs.py"
    - "dataforge/ui/widgets.py"
    - "dataforge/ui/app.py"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
architectural_context:
  existing_symbols_to_use:
    - "hardware_view.py: HardwareView, mount, _run_scan, _build_overview, _build_detail_tree"
    - "hardware.py: get_hardware_report, get_upgrade_recommendations, _check_cancel, _run_cmd"
    - "widgets.py: EnhancedTreeview, FilePreviewPanel"
    - "app.py: switch_view, _animate_opacity, JobManager bridge"
  breaking_changes: "None — crash fix, no API change"
requirements:
  summary: |
    Hardware section still crashes after TICK-808. User logs:
    ```
    2026-08-22 21:43:23 scan comprehensive
    2026-08-22 21:43:25 get hardware report
    QPainter::begin: A paint device can only be painted by one painter at a time.
    QPainter::setCompositionMode: Painter not active
    fish: SIGSEGV

    2026-08-22 21:58:33 scan comprehensive
    2026-08-22 21:58:35 get hardware report
    QPainter::begin: A paint device can only be painted by one painter at a time.
    QBackingStore::endPaint() called with active painter; did you forget to destroy it or call QPainter::end() on it?
    Traceback: hardware_view.py line 319: QTimer.singleShot(0, lambda: self.detail_tree.viewport().update() if hasattr(self, "detail_tree") and self.detail_tree else None)
    AttributeError: 'EnhancedTreeview' object has no attribute 'viewport'
    fish: SIGABRT
    ```
    Root causes:
    * EnhancedTreeview is a QWidget wrapper around QTreeWidget (widgets.py:423 self.tree is QTreeWidget, viewport() is on self.tree.viewport(), not self). TICK-808 added lambda touching self.detail_tree.viewport() which crashes because wrapper has no viewport. Same bug in _build_overview line 317 overview_layout.parentWidget().update().
    * QPainter recursion: _build_overview/_build_detail_tree call setUpdatesEnabled(False/True) + QTimer.singleShot viewport().update() while app.py transient QGraphicsOpacityEffect (ViewAnim 160ms) is still compositing at 0→1.0 via QPropertyAnimation. Calling viewport().update() during endPaint causes "active painter" + SIGSEGV/SIGABRT when overview cards + detail tree + Performance QProgressBar all paint concurrently with 4 jobs (scan comprehensive + hardware + storage + dashboard).
    * TICK-808 debounce (mount once + _is_scanning guard) is correct but mount() still races when switch_view fires _in_switch QTimer 210ms while mount triggers nested run_workflow → JobManager ManagedWorker → progress_signal → DataForgeApp.update_progress → progress_bar.setRange(0,0) which repaints status bar during crossfade.
    * hardware.py get_hardware_report has no per-step cancel_token checks, no timeout on psutil/lsblk/lspci/dmidecode/ws0; if user switches away, worker keeps hashing while UI detaches, leading to use-after-free.

    Fix:
    * hardware_view.py: replace all self.detail_tree.viewport() with self.detail_tree.tree.viewport() (or self.detail_tree.refresh_viewport() helper). Remove direct viewport().update() lambdas; instead rely on EnhancedTreeview.refresh_viewport() which already uses singleShot(0) correctly and checks _refresh_pending. In _build_overview avoid overview_layout.parentWidget().update(); instead use self.overview_layout.parentWidget() = ov_inner -> ov_inner.update() deferred, or simply don't force update — setUpdatesEnabled(True) already schedules. Ensure _build_overview/_build_detail_tree never call repaint()/update() while updates disabled; use QTimer.singleShot(0, lambda: self.detail_tree.tree.viewport().update() ... is_safe). Add guard hasattr(self.detail_tree,'tree').
    * hardware_view.py: harden mount(): keep debounce but add _mount_scheduled flag so rapid switch_view (10x Hardware) coalesces to one QTimer, not 10 jobs. Make _run_scan capture cancel_token from JobManager (run_workflow injects) and pass to get_hardware_report(cancel_token=, progress_callback=).
    * hardware.py: add _check_cancel(cancel_token) per step in get_hardware_report (cpu, ram, storage, gpu, motherboard, psutil). Make _run_cmd have timeout=5s already, add cancel_token check before each subprocess. Make all psutil calls (cpu_percent, virtual_memory) wrapped with try + timeout via ThreadPoolExecutor 2s fallback so SIGSEGV from hardware polling doesn't crash UI thread. Export get_hardware_report(cancel_token=None, progress_callback=None) and check token between sections.
    * Ensure no QPainter created in hardware.py (no pixmap generation). All UI painting stays on main thread.

    This is SOLE writer to hardware_view.py + hardware.py for Wave 9 (Wave 8 TICK-808 is DONE; this is sequential re-entry, not same wave — so no collision).
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
    - "dataforge/ui/views/hardware_view.py:317-319"
    - "dataforge/modules/hardware.py:1"
  acceptance_criteria:
    - "GIVEN Hardware view opened 20 times rapidly via switch_view WHEN spamming THEN no SIGSEGV/SIGABRT, no QPainter::begin warnings on stderr, and only one hardware job queued (debounce verified via JobManager.list_jobs())"
    - "GIVEN viewport() AttributeError previously at hardware_view.py:319 WHEN _build_overview completes THEN no AttributeError, call uses EnhancedTreeview.refresh_viewport() or tree.viewport() correctly"
    - "GIVEN get_hardware_report with cancel_token set mid-execution WHEN _check_cancel triggers THEN returns {'cancelled': True} and JobManager marks CANCELLED within 500ms"
    - "GIVEN hardware scan while dashboard scan comprehensive running (4 concurrent jobs) WHEN crossfade animation active (ViewAnim 160ms) THEN no QBackingStore::endPaint active painter warning (verified by capturing stderr)"
    - "GIVEN existing tests test_hardware_crash.py WHEN this fix applied THEN still pass and new test_hardware_stability.py passes"
verification:
  test_target: "tests/test_hardware_stability.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_hardware_stability.py -q"
```

---

## Implementation Notes

```python
# hardware_view.py — fix viewport access + debounce
# BEFORE (crash):
#   QTimer.singleShot(0, lambda: self.detail_tree.viewport().update() ...)
# AFTER:
try:
    self.detail_tree.refresh_viewport()  # or self.detail_tree.tree.viewport().update()
except Exception:
    pass

# _build_overview: remove overview_layout.parentWidget().update() direct call;
# use self.setUpdatesEnabled pattern only, no manual repaint during paint
def mount(self):
    if getattr(self, "_mount_scheduled", False):
        return
    if self._has_scanned or self._is_scanning:
        return
    self._mount_scheduled = True
    from PyQt5.QtCore import QTimer
    QTimer.singleShot(0, lambda: (setattr(self, "_mount_scheduled", False), self._run_scan()))

# hardware.py — add cancel_token checks per section
def get_hardware_report(cancel_token=None, progress_callback=None):
    def _check():
        if cancel_token and cancel_token.is_set():
            raise InterruptedError("cancelled")
    _check(); cpu = _get_cpu(...); progress_callback(...); _check(); ram = ...
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-901` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-901
WAVE: 9
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
git checkout -b fix/TICK-901-hardware-qpainter-hardening
PYTHONPATH=. python -m pytest tests/test_hardware_stability.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add dataforge/ui/views/hardware_view.py dataforge/modules/hardware.py tests/test_hardware_stability.py
git commit -m "fix(ui): hardware QPainter SIGSEGV deep hardening"
git push -u origin fix/TICK-901-hardware-qpainter-hardening
```

## Work Package YAML for TICK-901

```yaml
ticket_id: "TICK-901"
title: "Hardware section QPainter/SIGSEGV deep hardening"
type: "Bugfix"
execution_wave: 9
depends_on: []
scope:
  domain: "UI / Hardware"
  exclusive_write_files:
    - "dataforge/ui/views/hardware_view.py"
    - "dataforge/modules/hardware.py"
  read_only_references:
    - "dataforge/ui/job_manager.py"
architectural_context:
  existing_symbols_to_use:
    - "hardware_view.py: HardwareView"
  breaking_changes: "None"
requirements:
  summary: "Fix hardware QPainter viewport SIGABRT"
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN rapid Hardware switches THEN no SIGSEGV"
verification:
  test_target: "tests/test_hardware_stability.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_hardware_stability.py -q"
```
