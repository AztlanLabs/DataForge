# Ticket TICK-805 — Right click context menus per window

> **Wave 8** | **Domain:** UI / Context Menus | **Depends on:** None
> **Source:** `docs/GUI_WORKFLOWS.md` BaseView, user report right click same everywhere

---

## Your Assignment

```
TICKET_ID: TICK-805
WAVE: 8
TITLE: Right click context menus per window
```

**Exclusive write files (SOLE writer for Wave 8):**
- `dataforge/ui/views/base.py`
- `dataforge/ui/widgets.py`
- `dataforge/ui/views/search.py`
- `dataforge/ui/views/storage_devices.py`

**Read-only references (do not edit):**
- `dataforge/ui/app.py`
- `docs/GUI_WORKFLOWS.md`

**Test target:** `tests/test_context_menus.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_context_menus.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` all views
- `docs/ARCHITECTURE.md` §GUI
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `ui/views/base.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-805"
title: "Right click context menus per window"
type: "Feature"
execution_wave: 8
depends_on: []
scope:
  domain: "UI / Context Menus"
  exclusive_write_files:
    - "dataforge/ui/views/base.py"
    - "dataforge/ui/widgets.py"
    - "dataforge/ui/views/search.py"
    - "dataforge/ui/views/storage_devices.py"
  read_only_references:
    - "dataforge/ui/app.py"
    - "docs/GUI_WORKFLOWS.md"
architectural_context:
  existing_symbols_to_use:
    - "base.py: BaseView, get_context_actions"
    - "widgets.py: EnhancedTreeview, show_context_menu"
    - "search.py: SearchView"
  breaking_changes: "None — menus additive, no API break"
requirements:
  summary: |
    Right click currently shows same menu (Open/Rename/Move/Copy/Delete/Exclude + Copy col) on every view via widgets.EnhancedTreeview.show_context_menu. It should be per-window: Search should offer Copy Path + Reveal in File Manager + Hash, Storage should offer Mount/Unmount/Details, System Cleanup should offer Exclude/Clean, etc.

    Fix: make BaseView.get_context_actions() virtual per view (already exists but not overridden), and widgets.EnhancedTreeview.show_context_menu dispatch to view.get_context_actions() if view has override, else fallback to generic. Implement overrides in search.py (Copy Path, Reveal, Hash, Open) and storage_devices.py (Show Details, Copy Mount, Open in File Manager). Ensure forensics/recovery/metadata keep their custom menus (not overwritten). Add test that right click on search yields Search actions, on storage yields Storage actions, not same.
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN Search view WHEN right click on row THEN menu contains 'Copy Path' and 'Reveal in File Manager' and not 'Show Details (Storage)'"
    - "GIVEN Storage view WHEN right click on row THEN menu contains 'Show Details' and not 'Copy Path (Search)'"
    - "GIVEN generic view without override WHEN right click THEN fallback generic menu still works"
    - "GIVEN forensics view custom menu WHEN right click THEN not overwritten by generic"
verification:
  test_target: "tests/test_context_menus.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_context_menus.py -q"
```

---

## Implementation Notes

```python
# base.py: define get_context_actions(self, pos) -> list[QAction]
# widgets.py: show_context_menu checks if view has get_context_actions and uses it
# search.py: override get_context_actions to return Search-specific
# storage_devices.py: override for Storage
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-805` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-805
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
git checkout -b feat/TICK-805-context-menus
PYTHONPATH=. python -m pytest tests/test_context_menus.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add <exclusive> tests/test_*.py
git commit -m "feat(ui): per-window context menus"
git push -u origin feat/TICK-805-context-menus
```

## Work Package YAML for TICK-805

```yaml
ticket_id: "TICK-805"
title: "Right click context menus per window"
type: "Feature"
execution_wave: 8
depends_on: []
scope:
  domain: "UI / Context Menus"
  exclusive_write_files:
    - "dataforge/ui/views/base.py"
    - "dataforge/ui/views/search.py"
    - "dataforge/ui/views/storage_devices.py"
    - "dataforge/ui/widgets.py"
  read_only_references:
    - "dataforge/ui/app.py"
architectural_context:
  existing_symbols_to_use:
    - "base.py: BaseView"
  breaking_changes: "None"
requirements:
  summary: "Per-window menus"
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN Search WHEN right click THEN Search menu"
verification:
  test_target: "tests/test_context_menus.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_context_menus.py -q"
```
