# Ticket TICK-803 — Icons for forensic, file recovery, Metadata exif (weird x/?)

> **Wave 8** | **Domain:** UI / Icons | **Depends on:** None
> **Source:** `dataforge/ui/resources/icons.py`, `dataforge/ui/app.py` SIDEBAR_ICON_KEYS

---

## Your Assignment

```
TICKET_ID: TICK-803
WAVE: 8
TITLE: Icons for forensic, file recovery, Metadata exif (weird x/?)
```

**Exclusive write files (SOLE writer for Wave 8):**
- `dataforge/ui/resources/icons.py`
- `dataforge/ui/views/forensics_view.py`
- `dataforge/ui/views/recovery_view.py`
- `dataforge/ui/views/metadata_view.py`

**Read-only references (do not edit):**
- `dataforge/ui/app.py`
- `dataforge/ui/widgets.py`
- `docs/GUI_WORKFLOWS.md`

**Test target:** `tests/test_view_icons.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_view_icons.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` Forensics/Recovery/Metadata sections
- `docs/ARCHITECTURE.md` §GUI
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `ui/resources/icons.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-803"
title: "Icons for forensic, file recovery, Metadata exif (weird x/?)"
type: "Bugfix"
execution_wave: 8
depends_on: []
scope:
  domain: "UI / Icons"
  exclusive_write_files:
    - "dataforge/ui/resources/icons.py"
    - "dataforge/ui/views/forensics_view.py"
    - "dataforge/ui/views/recovery_view.py"
    - "dataforge/ui/views/metadata_view.py"
  read_only_references:
    - "dataforge/ui/app.py"
    - "dataforge/ui/widgets.py"
    - "docs/GUI_WORKFLOWS.md"
architectural_context:
  existing_symbols_to_use:
    - "resources/icons.py: ICON_PATHS, build_icons, _render"
    - "app.py: _apply_button_icon, SIDEBAR_ICON_KEYS"
    - "forensics_view.py: QGraphicsOpacityEffect transient (02db013)"
  breaking_changes: "None — icons additive, QPixmap loadFromData already fixed in f89055b for sidebar, now fix view-internal icons"
requirements:
  summary: |
    Some icons on forensic, file recovery, Metadata exif show weird x/? or missing. Sidebar icons were fixed in f89055b via QPixmap.loadFromData, but view-internal icons (FilePreviewPanel category, forensics tabs, metadata EXIF badges) still use QIcon(data_url) or emoji fallback that Qt cannot render, or have invalid SVG path (e.g., storage vs recovery confusion). Forensic tabs use emoji 💿🔐 etc. not build_icons, recovery view uses text headers, metadata view uses unicode glyphs that render as ? on some fonts.

    Fix: audit every icon in forensics_view, recovery_view, metadata_view, ensure they use build_icons with correct keys (forensics, recovery, metadata) via QPixmap, replace emoji/tabs with setIcon or QLabel pixmap, validate every ICON_PATHS path renders via QIcon.isNull()==False and pixmap not null. Add missing keys if needed (e.g., exif vs metadata alias) and ensure view-internal FilePreviewPanel._CATEGORY_GLYPHS fallback does not show DOC/IMG/▶ but icon.
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
    - "docs/ARCHITECTURE.md"
  acceptance_criteria:
    - "GIVEN forensic view WHEN tabs rendered THEN no tab shows emoji fallback, all have icon pixmap not null"
    - "GIVEN recovery view WHEN file list shown THEN no row shows x/?, all category icons are valid SVG"
    - "GIVEN metadata view WHEN EXIF panel shown THEN no ? glyph, shows forensics icon or metadata icon correctly"
    - "GIVEN headless test for all 18 ICON_PATHS WHEN QIcon built via QPixmap.loadFromData THEN isNull==False and availableSizes not empty (f89055b pattern)"
verification:
  test_target: "tests/test_view_icons.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_view_icons.py -q"
```

---

## Implementation Notes

```python
# For each view, replace QIcon(data_url) with:
pix = QPixmap(); pix.loadFromData(_data_url_to_bytes(url), "SVG"); btn.setIcon(QIcon(pix))
# Audit tab icons: use setIcon via SIDEBAR_ICON_KEYS pattern, not emoji
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-803` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-803
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
git checkout -b fix/TICK-803-view-icons
PYTHONPATH=. python -m pytest tests/test_view_icons.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add <exclusive> tests/test_*.py
git commit -m "fix(ui): view icons forensic/recovery/metadata via QPixmap"
git push -u origin fix/TICK-803-view-icons
```

## Work Package YAML for TICK-803

```yaml
ticket_id: "TICK-803"
title: "Icons for forensic, file recovery, Metadata exif (weird x/?)"
type: "Bugfix"
execution_wave: 8
depends_on: []
scope:
  domain: "UI / Icons"
  exclusive_write_files:
    - "dataforge/ui/resources/icons.py"
    - "dataforge/ui/views/forensics_view.py"
    - "dataforge/ui/views/recovery_view.py"
    - "dataforge/ui/views/metadata_view.py"
  read_only_references:
    - "dataforge/ui/app.py"
architectural_context:
  existing_symbols_to_use:
    - "resources/icons.py: ICON_PATHS"
  breaking_changes: "None"
requirements:
  summary: "Fix view icons"
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN forensic view WHEN tabs rendered THEN no emoji fallback"
verification:
  test_target: "tests/test_view_icons.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_view_icons.py -q"
```
