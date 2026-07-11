import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox
from PyQt5.QtCore import Qt

from .io import IOStep
from ...core.services import FileActionService
from ...core.utils import categorize_extension, check_disk_space


class OrganizeStep(IOStep):
    """Moves/copies files into CATEGORY_EXTENSIONS-based subfolders (Documents/Images/Videos/... /Other)."""

    def execute(self, context):
        base_dest = (self.params.get("dest") or "").strip() or context.variables.get("source_path", "")
        if not base_dest:
            context.log("System", "Organize", "Skipped: no destination configured and no source path available")
            return

        transfer_action = "move" if self.params.get("mode", "Move") == "Move" else "copy"

        def destination_getter(entry):
            return os.path.join(base_dest, categorize_extension(entry.extension))

        if not context.is_dry_run:
            required = sum(f.size for f in context.files)
            ok, message = check_disk_space(base_dest, required)
            if not ok:
                context.log("System", "Organize", f"Failed: {message}")
                return

        outcome = FileActionService.transfer_items(
            context.files,
            None,
            transfer_action,
            dry_run=context.is_dry_run,
            cancel_token=context.cancel_token,
            destination_getter=destination_getter,
        )
        FileActionService.apply_successes_to_entries(outcome)
        FileActionService.log_outcome(outcome, "Organize", context.log)

    def render_ui(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)

        row1 = QWidget(parent)
        row1_layout = QHBoxLayout(row1)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.addWidget(QLabel("Destination (blank = organize in place):"))
        e = QLineEdit(row1)
        e.setText(self.params.get("dest", ""))
        e.textChanged.connect(lambda text: self.params.update({"dest": text}))
        row1_layout.addWidget(e)
        btn = QPushButton("...", row1)
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda: self.browse_dest(e))
        row1_layout.addWidget(btn)
        layout.addWidget(row1)

        row2 = QWidget(parent)
        row2_layout = QHBoxLayout(row2)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        mode = QComboBox(row2)
        mode.addItems(["Move", "Copy"])
        mode.setCurrentText(self.params.get("mode", "Move"))
        mode.currentTextChanged.connect(lambda text: self.params.update({"mode": text}))
        row2_layout.addWidget(mode)
        row2_layout.addStretch()
        layout.addWidget(row2)

    def get_summary(self):
        dest = self.params.get("dest") or "(source path)"
        return f"{self.params.get('mode', 'Move')} into category folders under {dest}"
