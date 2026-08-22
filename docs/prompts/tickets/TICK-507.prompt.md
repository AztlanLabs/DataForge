# Ticket TICK-507 — Add hex field inspector / HexView widget (U4)

> **Wave 5** | **Domain:** UI / Widgets | **Depends on:** None
> **Source:** `docs/reviews/FORENSIC_REVIEW.md` U4

---

## Your Assignment

```
TICKET_ID: TICK-507
WAVE: 5
TITLE: Add hex field inspector / HexView widget (U4)
```

**Exclusive write files (SOLE writer for Wave 5):**
- `dataforge/ui/widgets.py`

**Read-only references (do not edit):**
- `docs/reviews/FORENSIC_REVIEW.md`
- `docs/GUI_WORKFLOWS.md`

**Test target:** `tests/test_hex_view.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_hex_view.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` Forensics view
- `docs/ARCHITECTURE.md` §GUI
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `ui/widgets.py`
- `docs/DEVELOPMENT_GUIDE.md` GUI run mode
- `docs/CONTRIBUTING.md` §8 (When You Change Code → Update table)

---

## Work Package YAML

```yaml
ticket_id: "TICK-507"
title: "Add hex field inspector / HexView widget (U4)"
type: "Feature"
execution_wave: 5
depends_on: []
scope:
  domain: "UI / Widgets"
  exclusive_write_files:
    - "dataforge/ui/widgets.py"
  read_only_references:
    - "docs/reviews/FORENSIC_REVIEW.md"
    - "docs/GUI_WORKFLOWS.md"
architectural_context:
  existing_symbols_to_use:
    - "widgets.py: existing widget classes"
  breaking_changes: "None — new widget added"
requirements:
  summary: |
    Fix U4: Hex without field inspector.

    Current behavior:
    - Hex viewer is plain QTextEdit displaying raw xxd-style hex dump
    - No dedicated HexView widget class exists
    - No field inspector, struct viewer, or binary structure interpretation

    Fix: Create HexView widget with field inspector:
    1. Create HexView class (QWidget)
    2. Display hex dump with offset, hex bytes, ASCII columns
    3. Add field inspector panel for structured data interpretation
    4. Support common forensic structures (MBR, GPT, PE, ELF, etc.)
    5. Add selection highlighting between hex and ASCII columns
    6. Add byte offset display and navigation
  source_documents:
    - "docs/reviews/FORENSIC_REVIEW.md"
  acceptance_criteria:
    - "GIVEN HexView widget WHEN created THEN displays hex dump correctly"
    - "GIVEN HexView widget WHEN byte selected THEN highlights in both hex and ASCII"
    - "GIVEN HexView widget WHEN field inspected THEN shows structured interpretation"
    - "GIVEN HexView widget WHEN large file loaded THEN remains responsive"
verification:
  test_target: "tests/test_hex_view.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_hex_view.py -q"
```

---

## Implementation Notes

### HexView widget
```python
class HexView(QWidget):
    """Hex viewer with field inspector for forensic analysis."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = b""
        self._offset = 0
        self._selected_byte = -1
        self._setup_ui()

    def _setup_ui(self):
        """Setup the hex view UI."""
        layout = QHBoxLayout(self)

        # Hex display
        self.hex_display = QTextEdit()
        self.hex_display.setReadOnly(True)
        self.hex_display.setFont(QFont("Courier New", 10))

        # Field inspector
        self.field_inspector = QTreeWidget()
        self.field_inspector.setHeaderLabels(["Field", "Value", "Description"])

        layout.addWidget(self.hex_display, 2)
        layout.addWidget(self.field_inspector, 1)

    def set_data(self, data: bytes, offset: int = 0):
        """Set the data to display."""
        self._data = data
        self._offset = offset
        self._update_display()

    def _update_display(self):
        """Update the hex display."""
        lines = []
        for i in range(0, len(self._data), 16):
            chunk = self._data[i:i+16]
            offset_str = f"{self._offset + i:08x}"
            hex_str = " ".join(f"{b:02x}" for b in chunk)
            ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{offset_str}  {hex_str:<48s}  |{ascii_str}|")

        self.hex_display.setPlainText("\n".join(lines))

    def _update_field_inspector(self, offset: int):
        """Update field inspector for selected offset."""
        self.field_inspector.clear()

        if offset < 0 or offset >= len(self._data):
            return

        # Add common forensic fields
        items = []

        # Byte value
        byte_val = self._data[offset]
        items.append(QTreeWidgetItem(["Byte", f"0x{byte_val:02x}", f"{byte_val}"]))

        # If at start of file, show common structures
        if offset == 0:
            # Check for MBR
            if len(self._data) >= 512:
                items.append(QTreeWidgetItem(["MBR Signature", "0x55AA", "Master Boot Record"]))

            # Check for PE
            if len(self._data) >= 64:
                pe_offset = int.from_bytes(self._data[60:64], 'little')
                if pe_offset < len(self._data) - 4:
                    if self._data[pe_offset:pe_offset+4] == b'PE\x00\x00':
                        items.append(QTreeWidgetItem(["PE Signature", "PE", "Portable Executable"]))

        self.field_inspector.addTopLevelItems(items)
        self.field_inspector.expandAll()
```

### Integration with forensics_view.py
```python
# In forensics_view.py, replace QTextEdit with HexView:
from dataforge.ui.widgets import HexView

# In _build_hex_tab:
self.hex_view = HexView()
# ... connect to file selection
```
