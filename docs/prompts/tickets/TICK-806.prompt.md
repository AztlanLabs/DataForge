# Ticket TICK-806 — Automation store custom automations

> **Wave 8** | **Domain:** UI / Automations | **Depends on:** None
> **Source:** `docs/GUI_WORKFLOWS.md` Automations, `docs/APP_REFERENCE.md` Action Builder

---

## Your Assignment

```
TICKET_ID: TICK-806
WAVE: 8
TITLE: Automation store custom automations
```

**Exclusive write files (SOLE writer for Wave 8):**
- `dataforge/ui/views/automations.py`
- `dataforge/ui/views/action_builder.py`
- `dataforge/engine/daemon.py`

**Read-only references (do not edit):**
- `dataforge/core/paths.py`
- `dataforge/core/config.py`
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

**Test target:** `tests/test_automation_store.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_automation_store.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` Automations / Action Builder
- `docs/ARCHITECTURE.md` §Automation
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `ui/views/automations.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-806"
title: "Automation store custom automations"
type: "Feature"
execution_wave: 8
depends_on: []
scope:
  domain: "UI / Automations"
  exclusive_write_files:
    - "dataforge/ui/views/automations.py"
    - "dataforge/ui/views/action_builder.py"
    - "dataforge/engine/daemon.py"
  read_only_references:
    - "dataforge/core/paths.py"
    - "dataforge/core/config.py"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
architectural_context:
  existing_symbols_to_use:
    - "automations.py: AutomationsView"
    - "action_builder.py: ActionBuilderView, ActionStep"
    - "daemon.py: JobQueue"
    - "paths.py: exports_dir"
  breaking_changes: "None — store additive, existing automations still work"
requirements:
  summary: |
    Automation currently has no persistence: ActionBuilder lets user build a chain but confirm_preview is ephemeral, no store. User must be able to store custom automations, select them, modify, update, delete, plus have default examples.

    Add JSON store at exports_dir/automations/*.json via paths.exports_dir, with AutomationsView list/load/save/delete UI: left list of saved automations, right builder, buttons Save, Save As, Delete, Duplicate, and default examples (e.g., Clean Duplicates, Organize by Date, Forensic Triage). Store includes name, steps, created_at, updated_at. ActionBuilderView gets load_automation(data), to_dict(), from_dict().

    Ensure daemon can schedule stored automations via JobQueue if needed (optional).
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
    - "docs/APP_REFERENCE.md"
  acceptance_criteria:
    - "GIVEN no saved automations WHEN AutomationsView opened THEN list shows 3 default examples"
    - "GIVEN custom automation built WHEN Save clicked THEN JSON file created in exports_dir/automations and appears in list"
    - "GIVEN saved automation selected WHEN Modify + Update clicked THEN file updated and list reflects change"
    - "GIVEN saved automation selected WHEN Delete clicked THEN file removed and list updates"
    - "GIVEN app restart WHEN saved automations exist THEN they are loaded from disk"
verification:
  test_target: "tests/test_automation_store.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_automation_store.py -q"
```

---

## Implementation Notes

```python
# automations.py: add list widget, store dir, default examples
# action_builder.py: add to_dict/from_dict, load_automation
# daemon.py: optional schedule hook
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-806` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-806
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
git checkout -b feat/TICK-806-automation-store
PYTHONPATH=. python -m pytest tests/test_automation_store.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add <exclusive> tests/test_*.py
git commit -m "feat(ui): automation store custom"
git push -u origin feat/TICK-806-automation-store
```

## Work Package YAML for TICK-806

```yaml
ticket_id: "TICK-806"
title: "Automation store custom automations"
type: "Feature"
execution_wave: 8
depends_on: []
scope:
  domain: "UI / Automations"
  exclusive_write_files:
    - "dataforge/ui/views/automations.py"
    - "dataforge/ui/views/action_builder.py"
    - "dataforge/engine/daemon.py"
  read_only_references:
    - "dataforge/core/paths.py"
architectural_context:
  existing_symbols_to_use:
    - "automations.py: AutomationsView"
  breaking_changes: "None"
requirements:
  summary: "Store automations"
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN no saved WHEN opened THEN 3 defaults"
verification:
  test_target: "tests/test_automation_store.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_automation_store.py -q"
```
