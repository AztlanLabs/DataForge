# Ticket TICK-905 — Junk scan SIGSEGV + permission QBackingStore

> **Wave 9** | **Domain:** Modules / System Cleanup | **Depends on:** None
> **Source:** user report `When scanning junk 2026-08-22 21:57:32,186 scanner WARNING Permission denied: /var/tmp/systemd-private-a158b04721ae4c6fa8f12f534f45a5f1-upower.service-6w06JF QBackingStore::endPaint() called with active painter (x3) fish: SIGSEGV` + `dataforge/modules/system_cleanup.py:225 scan_junk_files`, `dataforge/core/scanner.py:189`, `dataforge/ui/views/system_cleanup.py:436`

---

## Your Assignment

```
TICKET_ID: TICK-905
WAVE: 9
TITLE: Junk scan SIGSEGV + permission QBackingStore
```

**Exclusive write files (SOLE writer for Wave 9):**
- `dataforge/modules/system_cleanup.py`
- `dataforge/core/scanner.py`
- `dataforge/ui/views/system_cleanup.py`

**Read-only references (do not edit):**
- `dataforge/ui/job_manager.py`
- `dataforge/core/logger.py`
- `dataforge/ui/widgets.py`
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

**Test target:** `tests/test_junk_scan_stability.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_junk_scan_stability.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` Clean Up Space section
- `docs/ARCHITECTURE.md` §System Cleanup / §Scanner
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `modules/system_cleanup.py`, `core/scanner.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-905"
title: "Junk scan SIGSEGV + permission QBackingStore"
type: "Bugfix"
execution_wave: 9
depends_on: []
scope:
  domain: "Modules / System Cleanup"
  exclusive_write_files:
    - "dataforge/modules/system_cleanup.py"
    - "dataforge/core/scanner.py"
    - "dataforge/ui/views/system_cleanup.py"
  read_only_references:
    - "dataforge/ui/job_manager.py"
    - "dataforge/core/logger.py"
    - "dataforge/ui/widgets.py"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
architectural_context:
  existing_symbols_to_use:
    - "system_cleanup.py: scan_junk_files, scan_browser_artifacts, _is_socket_or_fifo, _is_under_system_temp, scan_directory reuse"
    - "scanner.py: scan_directory, _scan_single_dir, _log_scan_error, queue BFS, acquire_file fallback"
    - "system_cleanup view: SystemCleanupView, _start_junk_scan, _on_junk_scan_complete, _rebuild_junk_tree, EnhancedTreeview refresh"
    - "job_manager.py: ManagedWorker, cancel_token, progress_callback"
    - "widgets.py: EnhancedTreeview, FilePreviewPanel"
  breaking_changes: "None — hardening, no API break"
requirements:
  summary: |
    Junk scan crashes with SIGSEGV and floods QBackingStore paint errors.

    Log:
    ```
    21:57:32,186 WARNING Permission denied: /var/tmp/systemd-private-...-upower.service-...
    QBackingStore::endPaint() called with active painter (x3)
    SIGSEGV
    ```
    And the permission warning comes from scanner WARNING for every /var/tmp/systemd-private* private tmp (systemd creates 0700 private mounts owned by root, 1+ per service). scan_junk_files walks /tmp + /var/tmp (System Temp) with scan_directory(recursive, max_depth=5) which internally uses ThreadPoolExecutor 32 workers + os.scandir each dir. When encountering Permission denied on those private dirs, _log_scan_error fires but _scan_single_dir still tries to iterate and the Parallel BFS next_level collection races with PermissionError futures. More importantly, scanner's _scan_single_dir PermissionError fallback tries `from .acquire import acquire_file` to open the directory as file — acquire_file for dirs returns BytesIO mock which then goes into _build_from_stat with synthetic FileEntry size from BytesIO read length — but that fallback is for files, not dirs, and it injects synthetic entries that later get classified as junk and inserted into EnhancedTreeview.

    Meanwhile UI: SystemCleanupView._on_junk_scan_complete does `self.junk_tree.tree.clear()` + `self.junk_tree.item_map.clear()` then rebuilds tree with GROUP nodes + file leafs inside a tight loop without setUpdatesEnabled(False) guard. The view also has two FilePreviewPanels (junk_preview, browser_preview) that update on selection. The crash's 3x QBackingStore errors indicate repaint() was called while painter active — likely from `_rebuild_junk_tree` calling tree.clear() + insert in loop while QProgressBar status bar + junk tab crossfade (app.py ViewAnim) still painting. The tree is sortingEnabled True, so each insert triggers sort + repaint during paint.

    Fix:

    * scanner.py: make _scan_single_dir handle PermissionError on `os.scandir(dir_path)` at the very top as non-fatal: log warning, invoke on_error, return ([],[]). Do not attempt acquire_file fallback for directory scans — acquire fallback is for stat on individual files that hit PermissionError (entry.stat), not for scandir of a protected dir. The top-level `except OSError as e: _log_scan_error(dir_path, e)` already handles, but the ThreadPool future's `except OSError` in scan_directory's `for fut in as_completed` also logs but then continues; ensure cancelled vs PermissionError not treated as unexpected. Add guard: if dir_path startswith /var/tmp/systemd-private or /tmp/systemd-private or st_mode is 0700 root-owned, skip before submitting to pool (use os.access check or try os.scandir with try/except and skip if PermissionError). This reduces log flood and avoids BFS submission of 20+ private dirs.

    * scanner.py: ensure _build_from_stat is not called for directories — _scan_single_dir only yields FileEntry for files, already. Keep acquire fallback only for file entries where `entry.stat` PermissionError, not for `os.scandir` dir.

    * system_cleanup.py: in scan_junk_files, before walking, filter dir_category_map to skip non-existent or non-readable dirs via `os.access(dir, os.R_OK|os.X_OK)` or try `os.scandir` probe; log debug not warning for private systemd dirs to reduce spam. Ensure cancel_token checked between dir walks and before results classification. Use queue draining with cancel checks.

    * system_cleanup view: harden _rebuild_junk_tree similarly to hardware_view: wrap with `self.junk_tree.tree.setUpdatesEnabled(False)` + `try: clear, insert loop, finally setUpdatesEnabled(True)` + `self.junk_tree.refresh_viewport()` deferred via singleShot, not direct viewport().update() inside paint. Disable sorting during bulk build: `self.junk_tree.tree.setSortingEnabled(False)` before clear/insert, re-enable after. Ensure _start_junk_scan debounces (disable btn_scan while scanning, re-enable on complete/error). Ensure progress_callback not called with step_name that triggers excessive status bar updates during paint — throttle progress to every 10 files.

    * view: ensure no repaint() during mount/crossfade — delay heavy tree rebuild until after `app.switch_view` animation finishes (QTimer.singleShot(app.VIEW_ANIM_MS) for rebuild? Instead rely on setUpdatesEnabled guard which is sufficient).

    Must keep scan_directory streaming queue.BFS + DirEntry.stat reuse intact.

  source_documents:
    - "docs/GUI_WORKFLOWS.md"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
    - "dataforge/modules/system_cleanup.py:225"
    - "dataforge/core/scanner.py:189"
    - "dataforge/ui/views/system_cleanup.py:436"
  acceptance_criteria:
    - "GIVEN scan_junk_files with /var/tmp containing 10 systemd-private 0700 dirs WHEN run THEN no Warning flood (at most debug log), completes without SIGSEGV, skips those dirs gracefully"
    - "GIVEN scanner scan_directory on unreadable dir WHEN called THEN yields no entries, logs warning via _log_scan_error and calls on_error callback, no acquire_file fallback for dir"
    - "GIVEN SystemCleanupView rapid SCAN JUNK clicks (3x) WHEN running THEN button disabled, only one job, no QBackingStore::endPaint warnings, _rebuild_junk_tree uses setUpdatesEnabled guard"
    - "GIVEN junk scan with cancel_token set mid-walk WHEN cancelled THEN returns promptly with InterruptedError handling, no SIGSEGV"
    - "GIVEN existing tests test_system_cleanup_walks.py WHEN fix applied THEN still pass and new test_junk_scan_stability.py passes including permission denied simulation via chmod 000 tmp dir"
verification:
  test_target: "tests/test_junk_scan_stability.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_junk_scan_stability.py -q"
```

---

## Implementation Notes

```python
# scanner.py — guard private systemd dirs, not acquire for dirs
def _scan_single_dir(...):
    try:
        with os.scandir(dir_path) as it:
            ...
    except PermissionError as e:
        _log_scan_error(dir_path, e, on_error)
        return [], []  # not file acquire fallback
    except OSError as e:
        _log_scan_error(dir_path, e, on_error)
        return [], []

# scan_junk_files — probe before walk
for scan_dir in unique_dirs:
    try:
        with os.scandir(scan_dir): pass
    except PermissionError:
        logger.debug(f"Skipping unreadable {scan_dir}")
        continue

# system_cleanup view — harden rebuild
def _rebuild_junk_tree(self):
    try:
        self.junk_tree.tree.setSortingEnabled(False)
        self.junk_tree.tree.setUpdatesEnabled(False)
        self.junk_tree.tree.clear(); self.junk_tree.item_map.clear()
        for cat, entries in self.junk_results.items():
            # inserts
        ...
    finally:
        self.junk_tree.tree.setUpdatesEnabled(True)
        self.junk_tree.tree.setSortingEnabled(True)
        self.junk_tree.refresh_viewport()
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-905` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-905
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
git checkout -b fix/TICK-905-junk-scan-sigsegv
PYTHONPATH=. python -m pytest tests/test_junk_scan_stability.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add dataforge/modules/system_cleanup.py dataforge/core/scanner.py dataforge/ui/views/system_cleanup.py tests/test_junk_scan_stability.py
git commit -m "fix(system): junk scan SIGSEGV permission + QBackingStore hardening"
git push -u origin fix/TICK-905-junk-scan-sigsegv
```

## Work Package YAML for TICK-905

```yaml
ticket_id: "TICK-905"
title: "Junk scan SIGSEGV + permission QBackingStore"
type: "Bugfix"
execution_wave: 9
depends_on: []
scope:
  domain: "Modules / System Cleanup"
  exclusive_write_files:
    - "dataforge/modules/system_cleanup.py"
    - "dataforge/core/scanner.py"
    - "dataforge/ui/views/system_cleanup.py"
  read_only_references:
    - "dataforge/ui/job_manager.py"
architectural_context:
  existing_symbols_to_use:
    - "system_cleanup.py: scan_junk_files"
  breaking_changes: "None"
requirements:
  summary: "Fix junk scan SIGSEGV on permission denied private tmp"
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN systemd-private dirs THEN skip without SIGSEGV"
verification:
  test_target: "tests/test_junk_scan_stability.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_junk_scan_stability.py -q"
```
