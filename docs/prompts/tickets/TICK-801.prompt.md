# Ticket TICK-801 — Bulk Renamer update functionality

> **Wave 8** | **Domain:** Modules / Renamer | **Depends on:** None
> **Source:** `docs/CONSOLIDATED_SPEC.md` §Renamer, `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `modules/renamer.py`

---

## Your Assignment

```
TICKET_ID: TICK-801
WAVE: 8
TITLE: Bulk Renamer update functionality
```

**Exclusive write files (SOLE writer for Wave 8):**
- `dataforge/modules/renamer.py`
- `dataforge/ui/views/tools.py`

**Read-only references (do not edit):**
- `dataforge/core/services/file_actions.py`
- `dataforge/ui/views/automations.py`
- `docs/GUI_WORKFLOWS.md` ToolsView section

**Test target:** `tests/test_bulk_renamer.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_bulk_renamer.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `modules/renamer.py` section
- `docs/GUI_WORKFLOWS.md` Tools / Automations section
- `docs/ARCHITECTURE.md` §File Operations

---

## Work Package YAML

```yaml
ticket_id: "TICK-801"
title: "Bulk Renamer update functionality"
type: "Feature"
execution_wave: 8
depends_on: []
scope:
  domain: "Modules / Renamer"
  exclusive_write_files:
    - "dataforge/modules/renamer.py"
    - "dataforge/ui/views/tools.py"
  read_only_references:
    - "dataforge/core/services/file_actions.py"
    - "dataforge/ui/views/automations.py"
    - "docs/GUI_WORKFLOWS.md"
architectural_context:
  existing_symbols_to_use:
    - "renamer.py: bulk_rename, preview_rename"
    - "file_actions.py: FileActionService.rename_items_with_regex"
    - "tools.py: ToolsView._init_batch_renamer"
  breaking_changes: "None — additive preview/apply parity, progress/cancel support"
requirements:
  summary: |
    Update Bulk Renamer which is currently thin and has preview→apply drift, no progress/cancel, and unsafe list(scan_directory). The module's bulk_rename still does list(scan_directory) and ToolsView preview uses rename_items_with_rules but apply diverges.

    Fix: make renamer.py streaming (queue.Queue, not list), add progress_callback/cancel_token to bulk_rename and preview_rename, ensure preview and apply use identical FileActionService path (no drift), add collision handling via FileActionService, and add dry_run preview table in ToolsView that is scrollable/checkable with running total (like duplicates preview). ToolsView must use app.run_workflow so STOP works, and must show per-file before/after with conflict warnings.
  source_documents:
    - "docs/CONSOLIDATED_SPEC.md"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
  acceptance_criteria:
    - "GIVEN folder with 1000 files WHEN bulk_rename preview called THEN no list(scan_directory) materialisation, streaming"
    - "GIVEN preview and apply with same regex WHEN called THEN results are identical (no drift)"
    - "GIVEN rename with cancel_token set mid-run WHEN bulk_rename called THEN returns {'cancelled': True} without partial renames left"
    - "GIVEN ToolsView WHEN Batch Renamer tab opened THEN preview table is scrollable, checkable per row, shows before/after + conflict warning + total"
verification:
  test_target: "tests/test_bulk_renamer.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_bulk_renamer.py -q"
```

---

## Implementation Notes

```python
# renamer.py: streaming + cancel/progress
def bulk_rename(root, pattern, repl, dry_run=False, progress_callback=None, cancel_token=None):
    # use queue, check cancel_token per file, call file_actions

# tools.py: preview table with checkboxes, total, uses run_workflow
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-801` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-801
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
- Central touchpoints (`app.py`, `pyproject.toml`, etc.) are single-writer per wave.

## Workflow

```bash
git checkout develop && git pull origin develop
git checkout -b feat/TICK-801-bulk-renamer
# edit only exclusive_write_files
PYTHONPATH=. python -m pytest tests/test_bulk_renamer.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add <exclusive> tests/test_*.py
git commit -m "feat(modules): update bulk renamer streaming + preview parity"
git push -u origin feat/TICK-801-bulk-renamer
```

## Work Package YAML for TICK-801 (from `docs/PARALLEL_BACKLOG.md`)

```yaml
ticket_id: "TICK-801"
title: "Bulk Renamer update functionality"
type: "Feature"
execution_wave: 8
depends_on: []
scope:
  domain: "Modules / Renamer"
  exclusive_write_files:
    - "dataforge/modules/renamer.py"
    - "dataforge/ui/views/tools.py"
  read_only_references:
    - "dataforge/core/services/file_actions.py"
architectural_context:
  existing_symbols_to_use:
    - "renamer.py: bulk_rename"
  breaking_changes: "None"
requirements:
  summary: "Update bulk renamer"
  source_documents:
    - "docs/CONSOLIDATED_SPEC.md"
  acceptance_criteria:
    - "GIVEN folder with 1000 files WHEN bulk_rename preview called THEN streaming"
verification:
  test_target: "tests/test_bulk_renamer.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_bulk_renamer.py -q"
```
