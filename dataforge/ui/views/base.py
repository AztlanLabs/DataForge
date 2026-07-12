from PyQt5.QtWidgets import (
    QWidget, QMessageBox, QTextEdit, QVBoxLayout, QHBoxLayout, QPushButton, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QLabel, QDialogButtonBox,
    QFrame
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from abc import ABCMeta, abstractmethod
import re

from .. import dialogs
from ...core.utils import format_size

class QWidgetABCMeta(type(QWidget), ABCMeta):
    pass


class EmptyState(QFrame):
    """2e.5 — Purposeful empty state for views that have no results yet.

    Replaces the previous behaviour of leaving a blank panel with a
    bare "No results" label, which gave the user no idea *what to do
    next*. The widget shows an icon, a short title, a body sentence
    describing why the view is empty, and an optional action button
    that fires ``action_callback`` when clicked.

    The icon can be either a single Unicode glyph (e.g. ``"\u2316"``
    for a magnifying glass) or a longer text token — kept as text so
    the empty state has no external asset dependencies."""

    def __init__(self, icon="", title="", body="", action_label="",
                 action_callback=None, parent=None):
        super().__init__(parent)
        self.setObjectName("emptyState")
        self.action_callback = action_callback

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignCenter)

        if icon:
            self.icon_lbl = QLabel(icon, self)
            icon_font = QFont()
            icon_font.setPointSize(28)
            self.icon_lbl.setFont(icon_font)
            self.icon_lbl.setAlignment(Qt.AlignCenter)
            self.icon_lbl.setProperty("variant", "muted")
            layout.addWidget(self.icon_lbl)

        if title:
            self.title_lbl = QLabel(title, self)
            title_font = QFont()
            title_font.setBold(True)
            title_font.setPointSize(13)
            self.title_lbl.setFont(title_font)
            self.title_lbl.setAlignment(Qt.AlignCenter)
            self.title_lbl.setWordWrap(True)
            layout.addWidget(self.title_lbl)

        if body:
            self.body_lbl = QLabel(body, self)
            self.body_lbl.setAlignment(Qt.AlignCenter)
            self.body_lbl.setWordWrap(True)
            self.body_lbl.setProperty("variant", "muted")
            layout.addWidget(self.body_lbl)

        if action_label and action_callback is not None:
            self.action_btn = QPushButton(action_label, self)
            self.action_btn.setProperty("variant", "primary")
            self.action_btn.clicked.connect(self.action_callback)
            layout.addWidget(self.action_btn, 0, Qt.AlignCenter)
        else:
            self.action_btn = None


def friendly_error_message(error):
    """2e.5 — Turn a Python exception into a short, user-readable
    sentence that ends with a hint about the most likely cause.

    The previous ``show_workflow_error`` surfaced the raw ``str(error)``
    which dumped stack-trace-style messages like
    ``PermissionError: [Errno 13] Permission denied: '/root/.ssh'`` —
    technically accurate but leaving the user to guess whether the
    problem was the path, the permissions, or something else. The
    helper below maps the common cases to a one-line summary the
    user can act on, and falls back to ``str(error)`` for everything
    else."""
    if isinstance(error, PermissionError):
        return (
            f"Permission denied: {error.filename or 'a file or folder'}\n\n"
            "DataForge cannot read or write to this location. "
            "Check the file's permissions, or pick a different path."
        )
    if isinstance(error, FileNotFoundError):
        return (
            f"File not found: {error.filename or 'the requested path'}\n\n"
            "The path may have been moved or deleted while the scan was running. "
            "Try again with an existing folder."
        )
    if isinstance(error, IsADirectoryError):
        return (
            f"Expected a file but found a folder: {error.filename}\n\n"
            "Pick a single file, not a directory."
        )
    if isinstance(error, NotADirectoryError):
        return (
            f"Expected a folder but found a file: {error.filename}\n\n"
            "Pick a directory, not a single file."
        )
    if isinstance(error, OSError):
        return (
            f"Could not access the path: {error}\n\n"
            "The filesystem may be busy, the disk may be full, or the "
            "path may be on a disconnected network share."
        )
    if isinstance(error, ValueError):
        return (
            f"Invalid input: {error}\n\n"
            "Double-check the values you entered and try again."
        )
    if isinstance(error, TimeoutError):
        return (
            f"The operation timed out: {error}\n\n"
            "The target may be unreachable or under heavy load. "
            "Try again, or pick a smaller scope."
        )
    if isinstance(error, KeyboardInterrupt):
        return "The operation was cancelled."
    if isinstance(error, MemoryError):
        return (
            "The system ran out of memory while processing this operation.\n\n"
            "Close other applications, lower the thread count in Settings, "
            "or work on a smaller scope."
        )
    if isinstance(error, RecursionError):
        return (
            "DataForge hit a recursion limit while processing this operation.\n\n"
            "This usually means a deeply-nested folder structure or a symlink loop. "
            "Report this as a bug if the path is not unusual."
        )
    return str(error)


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

    def make_empty_state(self, icon="", title="", body="", action_label="",
                          action_callback=None):
        """Convenience for ``EmptyState`` so views do not need to
        import the class directly. Returns a freshly-built widget
        ready to be added to the view's layout."""
        return EmptyState(
            icon=icon, title=title, body=body,
            action_label=action_label, action_callback=action_callback,
            parent=self,
        )
        
    def get_help_text(self) -> str:
        """Return Markdown help for this view. The default is a small
        skeleton; views override this with their own content. Markdown is
        rendered as rich text inside ``show_help`` so headings, lists, and
        inline ``code`` are no longer shown as literal ``#`` / ``*``
        characters."""
        return "# No help available\n\nThis view has no help text yet."

    def show_help(self):
        """Displays a rich-text help dialog rendered from the Markdown
        returned by ``get_help_text``.

        Markdown headings/lists/``code`` now render properly instead of
        showing literal ``#``/``*`` characters. The dialog title includes
        the view name so multiple help windows can be told apart at a
        glance; the close button is the default so Esc dismisses it."""
        help_text = self.get_help_text()

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Help: {self.get_title()}")
        dialog.resize(720, 520)

        layout = QVBoxLayout(dialog)

        txt = QTextEdit(dialog)
        txt.setReadOnly(True)
        if hasattr(txt, "setMarkdown"):
            txt.setMarkdown(help_text)
        else:
            txt.setPlainText(help_text)
        layout.addWidget(txt, 1)

        btn = QPushButton("Close", dialog)
        btn.setDefault(True)
        btn.setAutoDefault(True)
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)

        dialog.exec_()

    @staticmethod
    def whats_this_for(widget, hint_text):
        """Attach a small inline "What's this?" hint next to ``widget``.

        The hint is rendered as a small clickable label that pops a
        tooltip-style dialog with the help text. Used on destructive
        actions whose consequence isn't obvious from the label alone."""
        from PyQt5.QtWidgets import QToolButton
        btn = QToolButton(widget.parent() if widget.parent() else widget)
        btn.setText("?")
        btn.setToolTip(hint_text)
        btn.setFixedSize(20, 20)
        btn.setProperty("variant", "info")
        return btn

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
        # 2e.6 — colour-blind channel. The proceed button is rendered
        # with the ``danger`` variant (red background) which carries
        # the destructive signal for sighted users; colour-blind users
        # get the same signal from a leading ⚠ glyph and an explicit
        # "destructive" accessible description. The glyph is only
        # prepended when the label does not already start with a
        # destructive verb (e.g. "Delete", "Remove") so the existing
        # descriptive labels stay readable.
        destructive_verbs = ("delete ", "remove ", "trash ", "drop ", "purge ", "wipe ")
        is_explicit = action_label.lower().startswith(destructive_verbs)
        button_text = action_label if is_explicit else f"\u26A0  {action_label}"
        proceed_btn = button_box.addButton(button_text, QDialogButtonBox.AcceptRole)
        proceed_btn.setProperty("variant", "danger")
        proceed_btn.setAutoDefault(False)
        proceed_btn.setAccessibleName(f"{action_label} (destructive)")
        proceed_btn.setAccessibleDescription(
            "This action permanently removes the selected items. "
            "Use only after reviewing the preview list above."
        )
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
