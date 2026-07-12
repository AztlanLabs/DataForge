from PyQt5.QtWidgets import (
    QWidget, QMessageBox, QTextEdit, QVBoxLayout, QHBoxLayout, QPushButton, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QLabel, QDialogButtonBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from abc import ABCMeta, abstractmethod
import re

from .. import dialogs
from ...core.utils import format_size

class QWidgetABCMeta(type(QWidget), ABCMeta):
    pass

class BaseView(QWidget, metaclass=QWidgetABCMeta):
    def __init__(self, master=None, app=None):
        super().__init__(master)
        self.app = app

    @abstractmethod
    def get_title(self) -> str:
        pass


    @property
    def view_name(self) -> str:
        return self.get_title()

    def mount(self):
        """Called when view is shown."""
        pass

    def unmount(self):
        """Called when view is hidden."""
        pass
        
    def get_help_text(self) -> str:
        """Return markdown-like or plain text help for this view."""
        return "No help available for this view."

    def show_help(self):
        """Displays help dialog."""
        help_text = self.get_help_text()
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Help: {self.get_title()}")
        dialog.resize(600, 400)
        
        layout = QVBoxLayout(dialog)
        
        txt = QTextEdit(dialog)
        txt.setReadOnly(True)
        txt.setPlainText(help_text)
        layout.addWidget(txt)
        
        btn = QPushButton("Close", dialog)
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)
        
        dialog.exec_()

    @staticmethod
    def build_preview_message(summary, lines=None, action_label="continue", limit=8):
        lines = lines or []
        body = [
            "Preview only. No changes have been made.",
            "",
            summary,
        ]

        if lines:
            body.append("")
            body.append("Planned changes:")
            body.extend(lines[:limit])
            extra = len(lines) - limit
            if extra > 0:
                body.append(f"... and {extra} more")

        body.append("")
        body.append(f"Proceed with {action_label}?")
        return "\n".join(body)

    def confirm_preview(self, title, summary, lines=None, action_label="continue", limit=8):
        msg = self.build_preview_message(summary, lines=lines, action_label=action_label, limit=limit)
        reply = QMessageBox.question(
            self,
            title,
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return reply == QMessageBox.Yes

    def confirm_destructive_preview(
        self,
        title,
        summary,
        items,
        action_label="Proceed",
        empty_message="No items to act on.",
    ):
        """Show a scrollable, per-row opt-out preview of a destructive op.

        Each entry in ``items`` is a dict with optional keys:
            - ``label`` (str, required) — the row's primary text
            - ``detail`` (str) — secondary text shown right-aligned
            - ``size_bytes`` (int) — included in the running total

        Returns the list of items the user kept checked, in original order.
        An empty list means the user cancelled or unchecked everything.

        Replaces the previous QMessageBox with the first 8 lines + "… and
        N more", which truncated destructive previews so the user could
        not review individual rows."""
        if not items:
            QMessageBox.information(self, title, empty_message)
            return []

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(720, 480)
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)

        summary_label = QLabel(summary, dialog)
        summary_label.setWordWrap(True)
        summary_label.setProperty("variant", "warning")
        layout.addWidget(summary_label)

        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_label = QLabel("Untick a row to skip it:", dialog)
        toggle_row.addWidget(toggle_label)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        table = QTableWidget(len(items), 3, dialog)
        table.setHorizontalHeaderLabels(["", "Item", "Detail"])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        for row, item in enumerate(items):
            chk = QTableWidgetItem()
            chk.setFlags(chk.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked)
            table.setItem(row, 0, chk)

            label_item = QTableWidgetItem(str(item.get("label", "")))
            label_font = QFont()
            label_font.setBold(False)
            label_item.setFont(label_font)
            table.setItem(row, 1, label_item)

            detail_text = str(item.get("detail", ""))
            if "size_bytes" in item and item["size_bytes"] is not None:
                size_text = format_size(int(item["size_bytes"]))
                detail_text = f"{detail_text}  ·  {size_text}" if detail_text else size_text
            table.setItem(row, 2, QTableWidgetItem(detail_text))

        layout.addWidget(table, 1)

        total_label = QLabel("", dialog)
        total_label.setProperty("variant", "danger")
        total_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        total_row = QHBoxLayout()
        total_row.addStretch()
        total_row.addWidget(total_label)
        layout.addLayout(total_row)

        def _refresh_total():
            checked = 0
            total_bytes = 0
            for row, item in enumerate(items):
                if table.item(row, 0).checkState() == Qt.Checked:
                    checked += 1
                    size = item.get("size_bytes")
                    if size is not None:
                        total_bytes += int(size)
            if total_bytes:
                total_label.setText(
                    f"{checked} of {len(items)} items selected · {format_size(total_bytes)} will be affected"
                )
            else:
                total_label.setText(f"{checked} of {len(items)} items selected")

        _refresh_total()
        table.itemChanged.connect(lambda _item: _refresh_total())

        button_box = QDialogButtonBox(dialog)
        cancel_btn = button_box.addButton("Cancel", QDialogButtonBox.RejectRole)
        cancel_btn.setDefault(True)
        cancel_btn.setAutoDefault(True)
        proceed_btn = button_box.addButton(action_label, QDialogButtonBox.AcceptRole)
        proceed_btn.setProperty("variant", "danger")
        proceed_btn.setAutoDefault(False)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        result = dialog.exec_()
        if result != QDialog.Accepted:
            return []

        kept = []
        for row, item in enumerate(items):
            if table.item(row, 0).checkState() == Qt.Checked:
                kept.append(item)
        return kept

    @staticmethod
    def summarize_completion(action_label, attempted, succeeded, failed=0, skipped=0, created=None):
        parts = [f"Attempted: {attempted}", f"Succeeded: {succeeded}"]
        if created is not None:
            parts.append(f"Created: {created}")
        if failed:
            parts.append(f"Failed: {failed}")
        if skipped:
            parts.append(f"Skipped: {skipped}")
        return f"{action_label}\n" + "\n".join(parts)

    @staticmethod
    def validate_regex_pattern(pattern):
        if not pattern:
            raise ValueError("A regex pattern is required.")
        try:
            return re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern: {exc}") from exc

    @staticmethod
    def validate_filename_candidate(name):
        if not name or not name.strip():
            raise ValueError("Generated filename is empty.")
        invalid_chars = set('<>:"/\\|?*')
        if any(char in invalid_chars for char in name):
            raise ValueError(f"Generated filename contains invalid characters: {name}")
        if name in {".", ".."}:
            raise ValueError(f"Generated filename is not valid: {name}")
        return name

    def restore_tree_selection(self, tree, item_ids, on_select=None):
        # We will re-implement tree selection restoration in the PyQt5 treeview wrapper.
        if hasattr(tree, "restore_selection"):
            tree.restore_selection(item_ids)
        if on_select:
            on_select(None)

    @staticmethod
    def batch_outcome_counts(outcome):
        success_count = len(outcome.get("successes", []))
        failure_count = len(outcome.get("failures", []))
        return success_count + failure_count, success_count, failure_count

    @staticmethod
    def batch_failure_details(records, limit=8):
        return "\n".join(
            getattr(record, "message", "")
            for record in records[:limit]
            if getattr(record, "message", "")
        )

    def present_batch_outcome(
        self,
        outcome,
        *,
        stopped_label,
        complete_label,
        summary_var=None,
        summary_text=None,
        cancelled_status=None,
        complete_status=None,
        success_dialog_title="Complete",
        partial_dialog_title="Partial Success",
        cancelled_dialog_title="Cancelled",
        created=None,
    ):
        attempted, success_count, failure_count = self.batch_outcome_counts(outcome)
        if summary_var is not None and summary_text is not None:
            if hasattr(summary_var, "setText"):
                summary_var.setText(summary_text.format(success=success_count, failed=failure_count))
            elif hasattr(summary_var, "set"):
                summary_var.set(summary_text.format(success=success_count, failed=failure_count))

        if outcome.get("cancelled"):
            if cancelled_status:
                self.app.update_status(cancelled_status.format(success=success_count, failed=failure_count))
            self.app.show_warning_dialog(
                cancelled_dialog_title,
                self.summarize_completion(stopped_label, attempted, success_count, failure_count, created=created),
            )
            return

        if complete_status:
            self.app.update_status(complete_status.format(success=success_count, failed=failure_count))

        summary = self.summarize_completion(complete_label, attempted, success_count, failure_count, created=created)
        if failure_count:
            details = self.batch_failure_details(outcome.get("failures", []))
            self.app.show_warning_dialog(partial_dialog_title, f"{summary}\n\n{details}" if details else summary)
            return

        self.app.show_info_dialog(success_dialog_title, summary)

    def handle_preview_outcome(
        self,
        *,
        cancelled,
        records,
        title,
        summary,
        lines,
        action_label,
        summary_var=None,
        ready_text=None,
        cancelled_summary=None,
        cancelled_status=None,
        empty_title="Nothing To Do",
        empty_message="No matching items were available for this action.",
        empty_summary=None,
        empty_status=None,
        declined_summary=None,
        declined_status=None,
        limit=8,
    ):
        if cancelled:
            if cancelled_status:
                self.app.update_status(cancelled_status)
            if summary_var is not None and cancelled_summary is not None:
                if hasattr(summary_var, "setText"):
                    summary_var.setText(cancelled_summary)
                elif hasattr(summary_var, "set"):
                    summary_var.set(cancelled_summary)
            return False

        if not records:
            self.app.show_warning_dialog(empty_title, empty_message)
            if empty_status:
                self.app.update_status(empty_status)
            if summary_var is not None and empty_summary is not None:
                if hasattr(summary_var, "setText"):
                    summary_var.setText(empty_summary)
                elif hasattr(summary_var, "set"):
                    summary_var.set(empty_summary)
            return False

        if summary_var is not None and ready_text is not None:
            if hasattr(summary_var, "setText"):
                summary_var.setText(ready_text)
            elif hasattr(summary_var, "set"):
                summary_var.set(ready_text)

        if not self.confirm_preview(title, summary, lines=lines, action_label=action_label, limit=limit):
            if declined_status:
                self.app.update_status(declined_status)
            if summary_var is not None and declined_summary is not None:
                if hasattr(summary_var, "setText"):
                    summary_var.setText(declined_summary)
                elif hasattr(summary_var, "set"):
                    summary_var.set(declined_summary)
            return False

        return True

    def choose_file(self, title="Select File", filetypes=None, directory=""):
        """Open a single-file picker. Returns the chosen path or an empty
        string if the user cancelled. The Yes/No/Cancel
        ``choose_file_or_directory`` message-box riddle is gone; callers
        that need to support both files and folders must expose two
        separate buttons that call ``choose_file`` and
        ``choose_directory`` respectively."""
        filter_str = ";;".join(f"{label} ({pattern})" for label, pattern in (filetypes or [])) or ""
        path, _ = dialogs.get_open_file_name(self, title, directory=directory, filter=filter_str)
        return path or ""

    def choose_directory(self, title="Select Folder", directory=""):
        """Open a directory picker. Returns the chosen path or an empty
        string if the user cancelled."""
        path = dialogs.get_existing_directory(self, title, directory=directory)
        return path or ""

    def choose_file_or_directory(self, file_title="Select File", directory_title="Select Folder", filetypes=None):
        """Deprecated. The Yes/No/Cancel riddle that forced the user to
        decide between picking a file or a folder before the picker
        opened has been removed. This stub remains only so the contract
        test can verify the deprecation; all in-app call sites now use
        ``choose_file`` or ``choose_directory`` directly."""
        return ""
