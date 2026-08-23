# Ticket TICK-908 — Global cursor pointers + app QPainter hardening

> **Wave 9** | **Domain:** UI / Shell | **Depends on:** None
> **Source:** user report `On entire app pointer is the same, needs to add a way to change pointer for select, grab etc... so User knows that some things have actions.` + `dataforge/ui/app.py:1`, `dataforge/ui/views/base.py:1`, `dataforge/ui/theme_tokens.py:1`, `widgets.py`, `QBackingStore` global paint errors

---

## Your Assignment

```
TICKET_ID: TICK-908
WAVE: 9
TITLE: Global cursor pointers + app QPainter hardening
```

**Exclusive write files (SOLE writer for Wave 9):**
- `dataforge/ui/app.py`
- `dataforge/ui/views/base.py`
- `dataforge/ui/theme_tokens.py`

**Read-only references (do not edit):**
- `dataforge/ui/job_manager.py`
- `dataforge/ui/widgets.py`
- `dataforge/core/config.py`
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

**Test target:** `tests/test_cursor_pointers.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_cursor_pointers.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` All views (cursor UX)
- `docs/ARCHITECTURE.md` §UI Shell / §Theme
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `ui/app.py`, `ui/views/base.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-908"
title: "Global cursor pointers + app QPainter hardening"
type: "Feature"
execution_wave: 9
depends_on: []
scope:
  domain: "UI / Shell"
  exclusive_write_files:
    - "dataforge/ui/app.py"
    - "dataforge/ui/views/base.py"
    - "dataforge/ui/theme_tokens.py"
  read_only_references:
    - "dataforge/ui/job_manager.py"
    - "dataforge/ui/widgets.py"
    - "dataforge/core/config.py"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
architectural_context:
  existing_symbols_to_use:
    - "app.py: DataForgeApp, build_navigation_sidebar, switch_view, _animate_opacity, QGraphicsOpacityEffect transient, apply_theme, SIDE BAR"
    - "base.py: BaseView, get_context_actions, mount/unmount"
    - "theme_tokens.py: TOKENS, generate_qss, TYPE_SCALE, generate_palette"
    - "widgets.py: EnhancedTreeview, CollapsibleCard (read-only but cursor affects children)"
    - "job_manager.py: JobManager.is_busy, progress signals"
  breaking_changes: "None — additive cursors, paint guard no API break"
requirements:
  summary: |
    Entire app pointer is same (default ArrowCursor) everywhere, so user cannot tell what has action.

    Requirements:

    * Add semantic cursors across app:
      - Buttons (QPushButton variant primary/warning/danger/info) → PointingHandCursor
      - Clickable list/tree rows (EnhancedTreeview) → PointingHandCursor on hover, or ArrowCursor with hand for selectable items
      - Drag handles / splitters (QSplitter) → SplitVCursor / SplitHCursor
      - CollapsibleCard header toggle → PointingHandCursor
      - Forbidden / disabled (Evidence Mode blocked) → ForbiddenCursor
      - Text editing (QLineEdit, QTextEdit, QSpinBox) → IBeamCursor (already default, keep)
      - Wait/busy (JobManager.is_busy) → WaitCursor on app level via setOverrideCursor + restore
      - Grab/grabbing for move/reorder (Media PDF move up/down, organizer drag) → OpenHandCursor / ClosedHandCursor if drag enabled (currently NoDragDrop disabled, but future)

    * Implement centrally, not per-view bolt-on: add helper in app.py or theme_tokens.py `def apply_cursor(widget, kind: str)` and call from base.py `BaseView` mount to set cursors for known child types via `findChildren`. Or add QSS cursor rule via theme_tokens generate_qss (`QPushButton:hover { cursor: pointer; }` is CSS not QSS — QSS doesn't support cursor, must use `widget.setCursor(Qt.PointingHandCursor)` in Python).

    * Global QPainter hardening (app-level, complements TICK-901/905/906 per-view fixes):
      - The 3x QBackingStore::endPaint active painter warnings in junk scan and the 2x in hardware scan indicate app-level animation (View crossfade QGraphicsOpacityEffect) paints while child widgets also paint. app.py `_animate_opacity` already defers effect removal via QTimer.singleShot(0, setGraphicsEffect(None)), but switch_view still does `effect.setOpacity(0.0)` while status bar progress_bar updates trigger repaint on main window. Need to ensure `DataForgeApp.switch_view` wraps `content_stack.setCurrentWidget` + `view.mount()` inside `self.setUpdatesEnabled(False/True)` or at least ensure no `repaint()` is called during fade.
      - Make `apply_theme` and `toggle_theme` not freeze updates with `w.setUpdatesEnabled(False)` while also holding OverrideCursor — that can deadlock paint. Instead, use `QApplication.setOverrideCursor(Qt.WaitCursor)` only, not updatesEnabled freeze for theme.

    * base.py: add utility `set_pointer(widget, Qt.CursorShape)` and auto-apply in BaseView.__init__ to scan children QPushButton → PointingHand, QSplitter handle → Split, etc. Ensure tooltips remain.

    * theme_tokens.py: add `CURSORS = {"button": Qt.PointingHandCursor, "text": Qt.IBeamCursor, "wait": Qt.WaitCursor, ...}` token table and expose to app.py. Not QSS, but token python dict.

    Keep evidence_mode ForbiddenCursor handling: when job_manager.evidence_mode true and destructive button disabled, set ForbiddenCursor.

  source_documents:
    - "docs/GUI_WORKFLOWS.md"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
    - "dataforge/ui/app.py:1"
    - "dataforge/ui/views/base.py:1"
  acceptance_criteria:
    - "GIVEN app running WHEN hovering over any QPushButton (primary/warning/success) THEN cursor is PointingHandCursor (verified via widget.cursor().shape() == Qt.PointingHandCursor)"
    - "GIVEN tree view row WHEN hovering THEN cursor is PointingHandCursor, not ArrowCursor"
    - "GIVEN JobManager.is_busy true (scan running) WHEN busy THEN app override cursor is WaitCursor and cleared on _on_job_completed"
    - "GIVEN CollapsibleCard header toggle WHEN hovered THEN cursor is PointingHandCursor"
    - "GIVEN switch_view rapid 10x WHEN animating THEN no QBackingStore::endPaint active painter warning on stderr (capture)"
    - "GIVEN view with evidence_mode enabled WHEN destructive button disabled THEN cursor is ForbiddenCursor"
verification:
  test_target: "tests/test_cursor_pointers.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_cursor_pointers.py -q"
```

---

## Implementation Notes

```python
# app.py — cursor helper + busy override
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

CURSOR_MAP = {
    "button": Qt.PointingHandCursor,
    "tree": Qt.PointingHandCursor,
    "splitter": Qt.SplitHCursor,
    "header": Qt.PointingHandCursor,
    "text": Qt.IBeamCursor,
    "wait": Qt.WaitCursor,
    "forbidden": Qt.ForbiddenCursor,
}

def apply_cursor(widget, kind):
    try:
        widget.setCursor(CURSOR_MAP[kind])
    except: pass

# In DataForgeApp.__init__ after build_navigation_sidebar:
for btn, _title in self.nav_buttons:
    btn.setCursor(Qt.PointingHandCursor)

# In _on_job_completed / start_progress:
# busy WaitCursor
if self.job_manager.is_busy:
    QApplication.setOverrideCursor(Qt.WaitCursor)
else:
    try: QApplication.restoreOverrideCursor()
    except: pass

# Hardening switch_view paint:
def switch_view(self, title):
    if getattr(self, "_in_switch", False): return
    self._in_switch = True
    try:
        self.content_stack.setCurrentWidget(view)
        view.mount()
        # transient effect only
    finally:
        QTimer.singleShot(self.VIEW_ANIM_MS + 50, lambda: setattr(self, "_in_switch", False))

# base.py — auto cursor on BaseView children
class BaseView(QWidget):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        QTimer.singleShot(0, self._apply_cursors)
    def _apply_cursors(self):
        for btn in self.findChildren(QPushButton):
            if btn.isEnabled(): btn.setCursor(Qt.PointingHandCursor)
            else: btn.setCursor(Qt.ForbiddenCursor)
        for tree in self.findChildren(QTreeWidget):
            tree.viewport().setCursor(Qt.PointingHandCursor)
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-908` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-908
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
git checkout -b feat/TICK-908-cursor-pointers
PYTHONPATH=. python -m pytest tests/test_cursor_pointers.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add dataforge/ui/app.py dataforge/ui/views/base.py dataforge/ui/theme_tokens.py tests/test_cursor_pointers.py
git commit -m "feat(ui): global cursor pointers + app QPainter hardening"
git push -u origin feat/TICK-908-cursor-pointers
```

## Work Package YAML for TICK-908

```yaml
ticket_id: "TICK-908"
title: "Global cursor pointers + app QPainter hardening"
type: "Feature"
execution_wave: 9
depends_on: []
scope:
  domain: "UI / Shell"
  exclusive_write_files:
    - "dataforge/ui/app.py"
    - "dataforge/ui/views/base.py"
    - "dataforge/ui/theme_tokens.py"
  read_only_references:
    - "dataforge/ui/job_manager.py"
architectural_context:
  existing_symbols_to_use:
    - "app.py: DataForgeApp"
  breaking_changes: "None"
requirements:
  summary: "Add semantic cursors + harden global paint"
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN hover button THEN PointingHandCursor"
verification:
  test_target: "tests/test_cursor_pointers.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_cursor_pointers.py -q"
```
