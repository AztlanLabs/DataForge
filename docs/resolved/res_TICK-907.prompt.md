# Ticket TICK-907 — Automations saved store collapsible UX

> **Wave 9** | **Domain:** UI / Automations | **Depends on:** None
> **Source:** user report `On Automation. Saved Automation section takes to much space, do not need to much space for this part, Can be on top section close to configuration, as collapsible and expanded section, if needed.` + `dataforge/ui/views/automations.py:159`, `dataforge/ui/views/action_builder.py:1`

---

## Your Assignment

```
TICKET_ID: TICK-907
WAVE: 9
TITLE: Automations saved store collapsible UX
```

**Exclusive write files (SOLE writer for Wave 9):**
- `dataforge/ui/views/automations.py`
- `dataforge/ui/views/action_builder.py`

**Read-only references (do not edit):**
- `dataforge/core/paths.py`
- `dataforge/engine/daemon.py`
- `dataforge/ui/widgets.py`
- `dataforge/ui/theme_tokens.py`
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

**Test target:** `tests/test_automations_layout.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_automations_layout.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` Automations section
- `docs/ARCHITECTURE.md` §Automations
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `ui/views/automations.py`, `ui/views/action_builder.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-907"
title: "Automations saved store collapsible UX"
type: "Feature"
execution_wave: 9
depends_on: []
scope:
  domain: "UI / Automations"
  exclusive_write_files:
    - "dataforge/ui/views/automations.py"
    - "dataforge/ui/views/action_builder.py"
  read_only_references:
    - "dataforge/core/paths.py"
    - "dataforge/engine/daemon.py"
    - "dataforge/ui/widgets.py"
    - "dataforge/ui/theme_tokens.py"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
architectural_context:
  existing_symbols_to_use:
    - "automations.py: AutomationsView, _store_dir, _load_all_automations, DEFAULT_AUTOMATIONS, _sanitize_filename"
    - "automations.py: AutomationsView.__init__, outer QSplitter horizontal (left store 250px + right notebook), list_widget, btn_save/save_as/delete/duplicate"
    - "action_builder.py: ActionBuilderView, to_dict/from_dict/load_automation"
    - "widgets.py: CollapsibleCard, EnhancedTreeview, FlowContainer"
    - "daemon.py: JobQueue persist hook for scheduled runs (read-only)"
  breaking_changes: "None — layout only, stored automations JSON unchanged"
requirements:
  summary: |
    Saved Automations panel wastes horizontal space.

    Current: `AutomationsView.__init__` builds a horizontal QSplitter with left store panel (220-320px fixed, list + 2 button rows + status) and right notebook (Action Builder + Tools). The left panel is always visible, taking ~25% width even when user is focused on building actions. User wants Saved Automations close to configuration, not side-by-side, and collapsible/expandable only when needed.

    Fix:

    * Redesign AutomationsView layout from horizontal QSplitter to vertical stacking with collapsible:
      - Top: CollapsibleCard titled "Saved Automations" (expanded=False by default, or expanded if user has >0 custom save? Default collapsed to save space, but respect ui_checkbox_states persistence). Inside card body: the existing QListWidget + button rows (Save/Save As/Delete/Duplicate) in a compact FlowLayout, and status label. The card sits *above* the Action Builder, close to configuration, not side-by-side. When collapsed, it shows only header with count badge (e.g., "Saved Automations (3)"). When expanded, it reveals list.
      - Middle: Action Builder + Tools notebook (preserve existing tabs). Make notebook expand to fill remaining vertical space (stretch 1).
      - Remove the horizontal QSplitter entirely or keep a thin vertical splitter between card and notebook if needed for resizable, but default is vertical QVBoxLayout with CollapsibleCard top.

    * Persistence: remember collapsed state via `config.get("ui_checkbox_states")["automations.saved_collapsed"]` or `collapsed_groups` — on toggle, save. On mount, restore. Similarly, selected automation still loads into builder on selection change.

    * Keep all existing public helpers: get_automation_names(), get_store_dir(), _refresh_list(), _on_save etc. No store JSON change.

    * Ensure action_builder.py does not need major change, but if its toolbar overflows, wrap with FlowContainer already.

    * Touch ups: reduce list_widget height when collapsed (card hides body), ensure keyboard navigation still works, and that Save/Save As still prompt correctly when collapsed.

    This is SOLE writer to automations.py + action_builder.py for Wave 9 (previous TICK-806 owns automations store JSON, but layout change is new wave sequential).

  source_documents:
    - "docs/GUI_WORKFLOWS.md"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
    - "dataforge/ui/views/automations.py:159"
    - "dataforge/ui/views/action_builder.py:1"
  acceptance_criteria:
    - "GIVEN Automations view opened WHEN default THEN Saved Automations card is collapsed (not taking 250px side space), header shows count, click expands to show list"
    - "GIVEN collapsed state toggled WHEN view remounted THEN state persists via config (ui_checkbox_states/collapsed_groups)"
    - "GIVEN saved automation selected WHEN expanded list item clicked THEN builder loads automation steps as before (load_automation called)"
    - "GIVEN Save/Save As/Delete/Duplicate buttons WHEN clicked while collapsed THEN still operate and status label updates"
    - "GIVEN outer layout WHEN measured THEN no horizontal QSplitter left panel 220-320px remains; instead vertical QVBoxLayout with CollapsibleCard top near configuration"
verification:
  test_target: "tests/test_automations_layout.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_automations_layout.py -q"
```

---

## Implementation Notes

```python
# automations.py — layout change from horizontal splitter to vertical collapsible

# BEFORE:
# outer.addWidget(self.splitter, 1)
# self.splitter = QSplitter(Qt.Horizontal)
# left panel (list) + right notebook

# AFTER:
outer = QVBoxLayout(self)
# Top collapsible
self.card_saved = CollapsibleCard(self, title="Saved Automations", expanded=False)
body = self.card_saved.get_body()
body_layout = QVBoxLayout(body)
body_layout.addWidget(self.list_widget)
# button rows inside FlowContainer for wrapping
flow = FlowContainer(body)
# add Save/Save As/Delete/Duplicate to flow
body_layout.addWidget(flow)
body_layout.addWidget(self.lbl_store_status)
outer.addWidget(self.card_saved)
# Middle notebook fills
outer.addWidget(self.notebook, 1)
# persist collapsed state
self.card_saved.btn_toggle.clicked.connect(lambda: config.set("ui_checkbox_states", {..., "automations.saved_collapsed": not self.card_saved.is_expanded}))
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-907` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-907
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
git checkout -b feat/TICK-907-automations-collapsible
PYTHONPATH=. python -m pytest tests/test_automations_layout.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add dataforge/ui/views/automations.py dataforge/ui/views/action_builder.py tests/test_automations_layout.py
git commit -m "feat(ui): automations saved store collapsible top"
git push -u origin feat/TICK-907-automations-collapsible
```

## Work Package YAML for TICK-907

```yaml
ticket_id: "TICK-907"
title: "Automations saved store collapsible UX"
type: "Feature"
execution_wave: 9
depends_on: []
scope:
  domain: "UI / Automations"
  exclusive_write_files:
    - "dataforge/ui/views/automations.py"
    - "dataforge/ui/views/action_builder.py"
  read_only_references:
    - "dataforge/core/paths.py"
architectural_context:
  existing_symbols_to_use:
    - "automations.py: AutomationsView"
  breaking_changes: "None"
requirements:
  summary: "Move Saved Automations to collapsible top near config"
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN view opened THEN saved card collapsed by default"
verification:
  test_target: "tests/test_automations_layout.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_automations_layout.py -q"
```
