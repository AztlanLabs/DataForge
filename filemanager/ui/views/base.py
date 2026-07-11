from PyQt5.QtWidgets import QWidget, QMessageBox, QTextEdit, QVBoxLayout, QPushButton, QDialog
from PyQt5.QtCore import Qt
from abc import ABCMeta, abstractmethod
import re

from .. import dialogs

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

    def choose_file_or_directory(self, file_title="Select File", directory_title="Select Folder", filetypes=None):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Browse Path")
        msg_box.setText("Select a file?\n\nChoose Yes for a file, No for a folder, or Cancel to keep the current path.")
        yes_btn = msg_box.addButton(QMessageBox.Yes)
        no_btn = msg_box.addButton(QMessageBox.No)
        cancel_btn = msg_box.addButton(QMessageBox.Cancel)
        msg_box.setDefaultButton(QMessageBox.Cancel)
        
        msg_box.exec_()
        clicked = msg_box.clickedButton()
        
        if clicked == yes_btn:
            path, _ = dialogs.get_open_file_name(self, file_title)
            return path
        elif clicked == no_btn:
            path = dialogs.get_existing_directory(self, directory_title)
            return path
        return ""
