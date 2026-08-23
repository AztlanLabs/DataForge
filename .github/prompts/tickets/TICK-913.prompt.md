# Ticket TICK-913 — Dead code prune + unused paths

> **Wave 10** | **Domain:** Core / Debt | **Depends on:** Wave 9 (901-908)
> **Source:** user report `Also saw that are code dead, remove dead code.` + `dataforge/modules/organizer.py:1`, `dataforge/modules/reporting.py:1`, `dataforge/modules/usage.py:1`, `dataforge/modules/password_tools.py:1`, `dataforge/core/utils.py:1`, `vulture`/`coverage` audit

---

## Your Assignment

```
TICKET_ID: TICK-913
WAVE: 10
TITLE: Dead code prune + unused paths
```

**Exclusive write files (SOLE writer for Wave 10):**
- `dataforge/modules/organizer.py`
- `dataforge/modules/reporting.py`
- `dataforge/modules/usage.py`
- `dataforge/modules/password_tools.py`
- `dataforge/modules/file_signatures.py`
- `dataforge/modules/device_manager.py`
- `dataforge/core/utils.py`

**Read-only references (do not edit):**
- `dataforge/cli.py`
- `dataforge/ui/views/forensics_view.py`
- `dataforge/ui/widgets.py`
- `dataforge/core/config.py`
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

**Test target:** `tests/test_dead_code_prune.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_dead_code_prune.py -q`

**Depends on:** ["TICK-901", "TICK-902", "TICK-903", "TICK-904", "TICK-905", "TICK-906", "TICK-907", "TICK-908"]

---

## Relevant Documentation — Must Read Before Coding

- `docs/ARCHITECTURE.md` §Modules / §Core
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`
- `docs/CONSOLIDATED_SPEC.md` §3

---

## Work Package YAML

```yaml
ticket_id: "TICK-913"
title: "Dead code prune + unused paths"
type: "Refactor"
execution_wave: 10
depends_on: ["TICK-901", "TICK-902", "TICK-903", "TICK-904", "TICK-905", "TICK-906", "TICK-907", "TICK-908"]
scope:
  domain: "Core / Debt"
  exclusive_write_files:
    - "dataforge/modules/organizer.py"
    - "dataforge/modules/reporting.py"
    - "dataforge/modules/usage.py"
    - "dataforge/modules/password_tools.py"
    - "dataforge/modules/file_signatures.py"
    - "dataforge/modules/device_manager.py"
    - "dataforge/core/utils.py"
  read_only_references:
    - "dataforge/cli.py"
    - "dataforge/ui/views/forensics_view.py"
    - "dataforge/ui/widgets.py"
    - "dataforge/core/config.py"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
architectural_context:
  existing_symbols_to_use:
    - "organizer.py: Organizer.organize_files/delete_files (only used in cli.py, maybe dead if cli uses FileActionService directly)"
    - "reporting.py: ReportGenerator duplicates_to_csv/json/txt (uses pandas, dead if export_result_rows replaced)"
    - "usage.py: analyze_size/generate_usage_report (used once in cli.py)"
    - "password_tools.py: contains crypto helpers, used in forensics_view"
    - "file_signatures.py: identify_file_type, get_all_categories (used in widgets preview)"
    - "device_manager.py: device enumeration (used in storage_devices view)"
    - "utils.py: format_size, categorize_extension, parse_extensions, CATEGORY_COLORS, normalize_filename, format_display_path"
    - "cli.py: imports organizer/usage/reporting (read-only to check liveness)"
  breaking_changes: "None — removal guarded, thin shim保留, no public API break without deprecation"
requirements:
  summary: |
    Codebase has dead/unreachable paths after Waves 0-9:

    * Inspect exclusive files via `vulture dataforge --min-confidence 80` and `coverage` and `grep -R "from.*organizer\|import.*organizer"` to determine liveness.

    Known dead candidates:

    - `reporting.py` uses `pandas` but export path now uses `export_result_rows` (core/search). If cli `dataforge report` command not wired (check cli.py), then ReportGenerator is dead. If still wired, keep but remove pandas hard dep (make lazy).

    - `organizer.py` Organizer class: `organize_files` calls `search_files` + `FileActionService.transfer_items` + `FileActionService.messages` which no longer exists (FileActionService.messages was renamed to something else? Check FileActionService API — it returns BatchActionOutcome, not messages list). This class likely broken/dead after TICK-201 parallel batch ops.

    - `usage.py` analyze_size: duplicates `system_cleanup.estimate_cleanup_savings` + duplicates `engine/index` FTS; but cli `dataforge usage` may still call it. Check if cli `usage` command exists; if not, keep as helper but remove bar chart code that is never shown in GUI (GUI uses Performance view, not usage).

    - `password_tools.py`, `file_signatures.py`, `device_manager.py`: likely live (forensics, widgets, storage). Verify via grep; if live keep but prune unused helpers inside (e.g., password_tools has 17k lines, likely has unused legacy hash tools).

    - `utils.py` has many helpers: `categorize_extension`, `CATEGORY_COLORS`, `normalize_filename`, `format_size`, `parse_extensions`, `format_display_path`. Some may be unused after recent refactors (e.g., normalize_filename used only in renamer, format_display_path maybe dead after EnhancedTreeview path resolver).

    Tasks:

    * Run vulture/coverage to list dead symbols in exclusive files.

    * For each file:
      - If entire module is import-unreachable (no `import organizer` except cli and cli path is deprecated), either delete file and update cli import to direct FileActionService, or keep thin re-export shim for backward compat with deprecation warning.
      - If only some functions dead (e.g., reporting.duplicates_to.txt), remove them and their pandas import hard dep, make it optional.
      - For utils.py, remove truly unused defs but keep `format_size`, `normalize_filename`, `categorize_extension` which are live.

    * Do not break existing tests: ensure `pytest -q` still passes. Keep public symbols that tests import.

    * Provide `tests/test_dead_code_prune.py` that verifies removed symbols are gone (import fails or vulture clean) and kept symbols still work.

    * Document in `utils.py` header which functions are live.

    This is SOLE writer to those 7 files for Wave 10; no other Wave 10 ticket touches them (TICK-911 engine, TICK-912 tests). Disjoint guarantee satisfied.

  source_documents:
    - "docs/ARCHITECTURE.md"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
    - "dataforge/modules/organizer.py:1"
    - "dataforge/modules/reporting.py:1"
    - "dataforge/core/utils.py:1"
  acceptance_criteria:
    - "GIVEN vulture scan on exclusive files WHEN run THEN 0 dead defs reported above 80 confidence (or allowlist in vulture whitelist commented)"
    - "GIVEN removed dead symbols WHEN grep for their names THEN no import path remains, and `python -c 'import dataforge.modules.reporting'` either succeeds with reduced API or shim warning"
    - "GIVEN kept symbols (format_size, normalize_filename, file_signatures.identify) WHEN imported THEN work as before"
    - "GIVEN cli imports WHEN changed THEN `dataforge --help` still lists same commands, no import error"
    - "GIVEN full suite WHEN run THEN pytest -q passes, no test imports removed symbol"
verification:
  test_target: "tests/test_dead_code_prune.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_dead_code_prune.py -q"
```

---

## Implementation Notes

```python
# Example prune — keep live, remove dead, make pandas lazy

# utils.py — audit which helpers are actually imported
# grep -R "from.*utils import" => keep only those
# e.g., if format_display_path not imported anywhere, remove it

# reporting.py — make pandas optional
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

def duplicates_to_csv(...):
    if not HAS_PANDAS:
        # fallback to csv module
        import csv
        ...

# organizer.py — if dead, either delete file or keep shim:
# Option A: delete file and fix cli.py (but cli.py is read-only this ticket, so keep shim)
import warnings
warnings.warn("Organizer is deprecated, use FileActionService directly", DeprecationWarning)

# vulture whitelist: add # noqa or `whitelist.py` for false positives
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-913` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-913
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
git checkout -b refactor/TICK-913-dead-code-prune
PYTHONPATH=. python -m pytest tests/test_dead_code_prune.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add dataforge/modules/organizer.py dataforge/modules/reporting.py dataforge/modules/usage.py dataforge/modules/password_tools.py dataforge/modules/file_signatures.py dataforge/modules/device_manager.py dataforge/core/utils.py tests/test_dead_code_prune.py
git commit -m "refactor(core): prune dead code + unused paths"
git push -u origin refactor/TICK-913-dead-code-prune
```

## Work Package YAML for TICK-913

```yaml
ticket_id: "TICK-913"
title: "Dead code prune + unused paths"
type: "Refactor"
execution_wave: 10
depends_on: ["TICK-901", "TICK-902", "TICK-903", "TICK-904", "TICK-905", "TICK-906", "TICK-907", "TICK-908"]
scope:
  domain: "Core / Debt"
  exclusive_write_files:
    - "dataforge/modules/organizer.py"
    - "dataforge/modules/reporting.py"
    - "dataforge/modules/usage.py"
    - "dataforge/modules/password_tools.py"
    - "dataforge/modules/file_signatures.py"
    - "dataforge/modules/device_manager.py"
    - "dataforge/core/utils.py"
  read_only_references:
    - "dataforge/cli.py"
architectural_context:
  existing_symbols_to_use:
    - "utils.py: format_size"
  breaking_changes: "None"
requirements:
  summary: "Prune dead code via vulture/coverage"
  source_documents:
    - "docs/ARCHITECTURE.md"
  acceptance_criteria:
    - "GIVEN vulture THEN 0 dead"
verification:
  test_target: "tests/test_dead_code_prune.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_dead_code_prune.py -q"
```
