import os
import zipfile
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox
from PyQt5.QtCore import Qt

from .base import ActionStep
from ...ui import dialogs
from ...core.config import config
from ...core.services import FileActionService
from ...core.utils import check_disk_space

class IOStep(ActionStep):
    """Base for IO steps requiring destination."""
    def browse_dest(self, entry_widget):
        p = dialogs.get_existing_directory(None, "Select Directory")
        if p:
            entry_widget.setText(p)

    def _execute_transfer(self, context, action: str):
        dest = self.params.get("dest", "")
        if not dest:
            return

        if not context.is_dry_run:
            required_bytes = sum(file_entry.size for file_entry in context.files)
            ok, message = check_disk_space(dest, required_bytes)
            if not ok:
                context.log("System", "Disk Check", f"Failed: {message}")
                return
            os.makedirs(dest, exist_ok=True)

        outcome = FileActionService.transfer_items(
            context.files,
            dest,
            action,
            dry_run=context.is_dry_run,
            cancel_token=context.cancel_token,
        )
        FileActionService.apply_successes_to_entries(outcome)
        FileActionService.log_outcome(outcome, action.title(), context.log)


class TransferStep(IOStep):
    transfer_action = ""

    def execute(self, context):
        self._execute_transfer(context, self.transfer_action)

    def render_ui(self, parent):
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(QLabel("Destination:"))
        
        e = QLineEdit(parent)
        e.setText(self.params.get("dest", ""))
        e.textChanged.connect(lambda text: self.params.update({"dest": text}))
        layout.addWidget(e)

        btn = QPushButton("...", parent)
        btn.setFixedWidth(30)
        btn.clicked.connect(lambda: self.browse_dest(e))
        layout.addWidget(btn)

    def get_summary(self):
        return f"To: {self.params.get('dest')}"

class MoveStep(TransferStep):
    transfer_action = "move"

class CopyStep(TransferStep):
    transfer_action = "copy"

class DeleteStep(ActionStep):
    def execute(self, context):
        outcome = FileActionService.delete_items(
            context.files,
            dry_run=context.is_dry_run,
            safe_mode=config.get("safe_mode", True),
            cancel_token=context.cancel_token,
        )
        FileActionService.log_outcome(outcome, "Delete", context.log)
        context.files = []

    def get_summary(self):
        return "Delete/Trash"

class ZipStep(ActionStep):
    def execute(self, context):
        mode = self.params.get("mode", "Individual")
        dest = self.params.get("dest", "archive.zip")
        comp = zipfile.ZIP_DEFLATED if self.params.get("compression") == "Deflated" else zipfile.ZIP_STORED
        archive_mode = "single" if mode == "Single Archive" else "individual"
        outcome = FileActionService.archive_items(
            context.files,
            mode=archive_mode,
            destination=dest if archive_mode == "single" else None,
            compression=comp,
            dry_run=context.is_dry_run,
            cancel_token=context.cancel_token,
        )
        FileActionService.log_outcome(outcome, "Zip", context.log)

    def render_ui(self, parent):
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        
        mode = QComboBox(parent)
        mode.addItems(["Individual", "Single Archive"])
        mode.setCurrentText(self.params.get("mode", "Individual"))
        mode.currentTextChanged.connect(lambda text: self.params.update({"mode": text}))
        layout.addWidget(mode)
        
        layout.addWidget(QLabel("Name:"))
        e = QLineEdit(parent)
        e.setText(self.params.get("dest", "archive.zip"))
        e.textChanged.connect(lambda text: self.params.update({"dest": text}))
        layout.addWidget(e)

    def get_summary(self):
         return f"{self.params.get('mode')}"
