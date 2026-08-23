# Ticket TICK-807 — Memory remember checkboxes/selections/names

> **Wave 8** | **Domain:** Core / Persistence | **Depends on:** None
> **Source:** `docs/GUI_WORKFLOWS.md` all views, `docs/ARCHITECTURE.md` persistence

---

## Your Assignment

```
TICKET_ID: TICK-807
WAVE: 8
TITLE: Memory remember checkboxes/selections/names
```

**Exclusive write files (SOLE writer for Wave 8):**
- `dataforge/core/config.py`
- `dataforge/core/paths.py`
- `dataforge/ui/views/system_cleanup.py`

**Read-only references (do not edit):**
- `dataforge/ui/app.py`
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

**Test target:** `tests/test_ui_memory.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_ui_memory.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` all views
- `docs/ARCHITECTURE.md` §Persistence
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `core/config.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-807"
title: "Memory remember checkboxes/selections/names"
type: "Feature"
execution_wave: 8
depends_on: []
scope:
  domain: "Core / Persistence"
  exclusive_write_files:
    - "dataforge/core/config.py"
    - "dataforge/core/paths.py"
    - "dataforge/ui/views/system_cleanup.py"
  read_only_references:
    - "dataforge/ui/app.py"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
architectural_context:
  existing_symbols_to_use:
    - "config.py: ConfigManager, DEFAULT_CONFIG, _merge_validated"
    - "paths.py: config_file, config_dir"
    - "system_cleanup.py: SystemCleanupView"
  breaking_changes: "None — new config keys additive, migration handled"
requirements:
  summary: |
    Need of memory: user checkboxes, selections, names etc. should be remembered across restarts, but not everything is worth storing. Review what is worth to store and what not.

    Worth storing: last used paths (dashboard_paths already), filter names, checkbox states for include_browser, duplicate keep strategy, search recursive flag, tier, collapsed_groups (already), recent automations, window geometry. Not worth storing: transient progress, one-off file lists, sensitive paths like password tool.

    Implement: add to config.py DEFAULT_CONFIG new keys ui_last_paths (dict view->path), ui_checkbox_states (dict), ui_filter_names (dict), ui_recent_searches (list), plus migration. Provide ui_state helper in paths.py for recent.json. Exemplar implementation in system_cleanup.py: save/load chk_include_browser, tab index, etc. via config.set on change and restore on mount. Document policy in docs/TECHNICAL_SOURCE_OF_TRUTH.md which keys are persisted vs transient.
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
    - "docs/ARCHITECTURE.md"
  acceptance_criteria:
    - "GIVEN SystemCleanup checkbox changed WHEN app restarted THEN checkbox state restored (via config)"
    - "GIVEN search path entered WHEN restarted THEN last path remembered in ui_last_paths"
    - "GIVEN config file with old version WHEN load THEN new ui_* keys added via migration without dropping existing"
    - "GIVEN transient progress value WHEN stored THEN not persisted (excluded from config)"
verification:
  test_target: "tests/test_ui_memory.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_ui_memory.py -q"
```

---

## Implementation Notes

```python
# config.py: add DEFAULT_CONFIG keys + migration
# paths.py: helper for ui_state
# system_cleanup.py: save/load checkbox states
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-807` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-807
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
git checkout -b feat/TICK-807-ui-memory
PYTHONPATH=. python -m pytest tests/test_ui_memory.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add <exclusive> tests/test_*.py
git commit -m "feat(core): remember UI state"
git push -u origin feat/TICK-807-ui-memory
```

## Work Package YAML for TICK-807

```yaml
ticket_id: "TICK-807"
title: "Memory remember checkboxes/selections/names"
type: "Feature"
execution_wave: 8
depends_on: []
scope:
  domain: "Core / Persistence"
  exclusive_write_files:
    - "dataforge/core/config.py"
    - "dataforge/core/paths.py"
    - "dataforge/ui/views/system_cleanup.py"
  read_only_references:
    - "dataforge/ui/app.py"
architectural_context:
  existing_symbols_to_use:
    - "config.py: ConfigManager"
  breaking_changes: "None"
requirements:
  summary: "Remember UI state"
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN checkbox changed WHEN restarted THEN restored"
verification:
  test_target: "tests/test_ui_memory.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_ui_memory.py -q"
```
