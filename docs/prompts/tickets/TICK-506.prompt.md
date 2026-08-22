# Ticket TICK-506 — Virtualise timeline for >5k events (U3)

> **Wave 5** | **Domain:** UI / Forensics | **Depends on:** None
> **Source:** `docs/reviews/FORENSIC_REVIEW.md` U3

---

## Your Assignment

```
TICKET_ID: TICK-506
WAVE: 5
TITLE: Virtualise timeline for >5k events (U3)
```

**Exclusive write files (SOLE writer for Wave 5):**
- `dataforge/ui/views/forensics_view.py`

**Read-only references (do not edit):**
- `docs/reviews/FORENSIC_REVIEW.md`
- `docs/GUI_WORKFLOWS.md`

**Test target:** `tests/test_forensics_view.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_forensics_view.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` Forensics view
- `docs/ARCHITECTURE.md` §GUI
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `ui/views/forensics_view.py`
- `docs/DEVELOPMENT_GUIDE.md` GUI run mode
- `docs/CONTRIBUTING.md` §8 (When You Change Code → Update table)

---

## Work Package YAML

```yaml
ticket_id: "TICK-506"
title: "Virtualise timeline for >5k events (U3)"
type: "Feature"
execution_wave: 5
depends_on: []
scope:
  domain: "UI / Forensics"
  exclusive_write_files:
    - "dataforge/ui/views/forensics_view.py"
  read_only_references:
    - "docs/reviews/FORENSIC_REVIEW.md"
    - "docs/GUI_WORKFLOWS.md"
architectural_context:
  existing_symbols_to_use:
    - "forensics_view.py: _build_timeline_tab (lines 801-862)"
    - "forensics_view.py: EnhancedTreeview"
    - "forensics_view.py: events[:5000] hard cap"
  breaking_changes: "None — virtualised view replaces QTreeWidget"
requirements:
  summary: |
    Fix U3: Timeline flat list, no virtualisation >5k events.

    Current behavior:
    - Uses EnhancedTreeview (wraps QTreeWidget) - non-virtualised
    - Creates actual QTreeWidgetItem objects for every row
    - Hard-caps at 5000 items (events[:5000])
    - Cannot handle large datasets efficiently

    Fix: Replace QTreeWidget with virtualised QTreeView + custom model:
    1. Create TimelineModel (QAbstractTableModel) for lazy data loading
    2. Replace EnhancedTreeview with QTreeView + TimelineModel
    3. Remove 5000 item hard cap
    4. Add pagination or infinite scroll for very large datasets
    5. Preserve existing column structure and sorting
  source_documents:
    - "docs/reviews/FORENSIC_REVIEW.md"
  acceptance_criteria:
    - "GIVEN 10k timeline events WHEN displayed THEN no hard cap applied"
    - "GIVEN 100k timeline events WHEN displayed THEN UI remains responsive"
    - "GIVEN timeline events WHEN sorted THEN sorting works correctly"
    - "GIVEN timeline events WHEN filtered THEN filtering works correctly"
verification:
  test_target: "tests/test_forensics_view.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_forensics_view.py -q"
```

---

## Implementation Notes

### TimelineModel
```python
class TimelineModel(QAbstractTableModel):
    """Virtualised model for timeline events."""

    COLUMNS = ["Timestamp", "Type", "Source", "Details"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._events = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._events)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None

        event = self._events[index.row()]
        col = index.column()

        if col == 0:
            return event.get("timestamp", "")
        elif col == 1:
            return event.get("type", "")
        elif col == 2:
            return event.get("source", "")
        elif col == 3:
            return event.get("details", "")
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.COLUMNS[section]
        return None

    def set_events(self, events):
        self.beginResetModel()
        self._events = events
        self.endResetModel()
```

### Updated _build_timeline_tab
```python
def _build_timeline_tab(self):
    """Build timeline tab with virtualised view."""
    # Create model
    self.timeline_model = TimelineModel()

    # Create view
    self.timeline_view = QTreeView()
    self.timeline_view.setModel(self.timeline_model)
    self.timeline_view.setRootIsDecorated(False)
    self.timeline_view.setAlternatingRowColors(True)
    self.timeline_view.setSortingEnabled(True)

    # Layout
    layout = QVBoxLayout()
    layout.addWidget(self.timeline_view)
    self.timeline_tab.setLayout(layout)
```
