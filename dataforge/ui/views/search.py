import os
import zipfile
import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QCheckBox, QSpinBox, QComboBox, QSplitter, QGroupBox
)
from PyQt5.QtCore import Qt

from .base import BaseView
from .. import dialogs
from ...core.services import FileActionService
from ..widgets import EnhancedTreeview, FilePreviewPanel, FlowLayout, FlowContainer, attach_tooltips
from ...modules.search import build_search_query, export_search_results, order_search_results, search_files
from ...core.utils import format_size, format_display_path

class SearchView(BaseView):
    SLICE_TOOLTIPS = {
        "sort": "Choose how visible matches are ordered before bulk actions. Try ext to group by file type.",
        "reverse": "Flip the current result order. Useful with size to show the largest files first.",
        "limit": "Only keep the first N ordered matches visible and actionable. Use 0 for the full set.",
        "reset": "Clear sort, reverse, and limit in one click and return to the natural full result set.",
    }

    def get_title(self):
        return "Search"

    def get_help_text(self):
        return """
# Search Guide

Powerful search tool with built-in actions.

## Search Filters
- **Name**: Glob pattern (e.g. *.txt) or enable 'Regex' for power users.
- **Content**: Use 'Contains Text' to grep inside file contents.
- **Advanced**: Filter by file size (MB) or date (days old).
- **Depth**: How many subfolders to drill down (-1 for infinite).
- **Sort/Limit**: Order by type/path/name/size/date, reverse it if needed, and cap the list before bulk actions.

## Bulk Actions
Once files are found, use the 'Bulk Actions' card to:
- Move/Copy/Delete selected items.
- Batch Rename using Regex substitution.
- Create Zip archives instantly.
"""

    def __init__(self, master, app=None):
        super().__init__(master, app)
        self.current_results = []
        
        # Main Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Criteria Group
        self.ctrl_frame = QGroupBox("Search Criteria", self)
        ctrl_layout = QVBoxLayout(self.ctrl_frame)
        ctrl_layout.setSpacing(5)
        
        # Row 1: Path Selection
        frame_path = QWidget(self.ctrl_frame)
        path_layout = QHBoxLayout(frame_path)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.addWidget(QLabel("Path:"))
        self.entry_path = QLineEdit(frame_path)
        path_layout.addWidget(self.entry_path)
        self.btn_browse_file = QPushButton("Browse File…", frame_path)
        self.btn_browse_file.clicked.connect(self.browse_file)
        path_layout.addWidget(self.btn_browse_file)
        self.btn_browse_folder = QPushButton("Browse Folder…", frame_path)
        self.btn_browse_folder.clicked.connect(self.browse_folder)
        path_layout.addWidget(self.btn_browse_folder)
        ctrl_layout.addWidget(frame_path)
        
        # Row 2: Name, Regex, Ext, Depth
        frame_filters = QWidget(self.ctrl_frame)
        filter_layout = QHBoxLayout(frame_filters)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        
        filter_layout.addWidget(QLabel("Name:"))
        self.entry_name = QLineEdit(frame_filters)
        self.entry_name.setPlaceholderText("e.g. *.pdf")
        filter_layout.addWidget(self.entry_name)
        
        self.chk_regex = QCheckBox("Regex", frame_filters)
        filter_layout.addWidget(self.chk_regex)
        
        filter_layout.addWidget(QLabel("Ext (csv):"))
        self.entry_ext = QLineEdit(frame_filters)
        self.entry_ext.setPlaceholderText("txt,log")
        filter_layout.addWidget(self.entry_ext)
        
        filter_layout.addWidget(QLabel("Depth:"))
        self.spin_depth = QSpinBox(frame_filters)
        self.spin_depth.setRange(-1, 10)
        self.spin_depth.setValue(-1)
        filter_layout.addWidget(self.spin_depth)
        ctrl_layout.addWidget(frame_filters)
        
        # Row 3: Size, Days, Sorting, Limit
        frame_adv = FlowContainer(self.ctrl_frame)
        adv_layout = FlowLayout(frame_adv, margin=0, hspacing=8, vspacing=4)


        adv_layout.addWidget(QLabel("Size (MB):"))
        self.entry_min_size = QLineEdit(frame_adv)
        self.entry_min_size.setPlaceholderText("Min")
        self.entry_min_size.setFixedWidth(50)
        adv_layout.addWidget(self.entry_min_size)
        adv_layout.addWidget(QLabel("-"))
        self.entry_max_size = QLineEdit(frame_adv)
        self.entry_max_size.setPlaceholderText("Max")
        self.entry_max_size.setFixedWidth(50)
        adv_layout.addWidget(self.entry_max_size)
        
        adv_layout.addWidget(QLabel("Newer (days):"))
        self.entry_newer = QLineEdit(frame_adv)
        self.entry_newer.setPlaceholderText("Newer")
        self.entry_newer.setFixedWidth(60)
        adv_layout.addWidget(self.entry_newer)
        
        adv_layout.addWidget(QLabel("Older (days):"))
        self.entry_older = QLineEdit(frame_adv)
        self.entry_older.setPlaceholderText("Older")
        self.entry_older.setFixedWidth(60)
        adv_layout.addWidget(self.entry_older)
        
        adv_layout.addWidget(QLabel("Sort:"))
        self.sort_combo = QComboBox(frame_adv)
        self.sort_combo.addItems(["", "ext", "path", "name", "size", "created", "modified"])
        adv_layout.addWidget(self.sort_combo)
        
        self.chk_reverse = QCheckBox("Reverse", frame_adv)
        adv_layout.addWidget(self.chk_reverse)
        
        adv_layout.addWidget(QLabel("Limit:"))
        self.spin_limit = QSpinBox(frame_adv)
        self.spin_limit.setRange(0, 100000)
        self.spin_limit.setValue(0)
        adv_layout.addWidget(self.spin_limit)
        
        self.btn_reset_slice = QPushButton("Reset Slice", frame_adv)
        self.btn_reset_slice.clicked.connect(self.reset_slice)
        adv_layout.addWidget(self.btn_reset_slice)
        ctrl_layout.addWidget(frame_adv)
        
        # Row 4: Contains Text (Grep) + Search Trigger
        frame_grep = QWidget(self.ctrl_frame)
        grep_layout = QHBoxLayout(frame_grep)
        grep_layout.setContentsMargins(0, 0, 0, 0)
        grep_layout.addWidget(QLabel("Contains Text:"))
        self.entry_content = QLineEdit(frame_grep)
        self.entry_content.setPlaceholderText("text to search inside files")
        grep_layout.addWidget(self.entry_content)
        
        self.lbl_results_slice = QLabel("Slice: natural order | full set", frame_grep)
        self.lbl_results_slice.setProperty("class", "muted")
        self.lbl_results_slice.setWordWrap(True)
        grep_layout.addWidget(self.lbl_results_slice)
        
        self.btn_search = QPushButton("Search", frame_grep)
        self.btn_search.clicked.connect(self.start_search)
        grep_layout.addWidget(self.btn_search)
        ctrl_layout.addWidget(frame_grep)
        
        self.main_layout.addWidget(self.ctrl_frame)
        
        # Main Work Splitter (Results Tree left, Preview right)
        self.work_splitter = QSplitter(Qt.Horizontal, self)
        self.main_layout.addWidget(self.work_splitter, 1) # stretch widget
        
        # Left Panel (Tree)
        self.tree_widget = QWidget(self.work_splitter)
        tree_layout = QVBoxLayout(self.tree_widget)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        
        cols = ("ext", "path", "size")
        self.tree = EnhancedTreeview(self.tree_widget, columns=cols, app=self.app)
        self.tree.heading("ext", text="Type")
        self.tree.heading("path", text="Path")
        self.tree.heading("size", text="Size")
        self.tree.column("ext", width=60, stretch=False)
        self.tree.column("path", width=400, stretch=True)
        self.tree.column("size", width=100, stretch=False)
        
        # Connect Selection change
        self.tree.tree.itemSelectionChanged.connect(self.on_preview_select)
        tree_layout.addWidget(self.tree)
        self.work_splitter.addWidget(self.tree_widget)
        
        # Right Panel (Preview)
        self.preview_panel = FilePreviewPanel(self.work_splitter)
        self.work_splitter.addWidget(self.preview_panel)
        self.work_splitter.setSizes([700, 400])
        
        # Actions Group Box
        self.action_frame = QGroupBox("Bulk Actions", self)
        action_layout = QVBoxLayout(self.action_frame)
        action_layout.setSpacing(5)
        
        # Export Actions
        f_export = QWidget(self.action_frame)
        export_layout = QHBoxLayout(f_export)
        export_layout.setContentsMargins(0, 0, 0, 0)
        export_layout.addWidget(QLabel("Export Results:"))
        self.export_format_combo = QComboBox(f_export)
        self.export_format_combo.addItems(["csv", "json"])
        export_layout.addWidget(self.export_format_combo)
        
        self.btn_export = QPushButton("Save Current Results", f_export)
        self.btn_export.clicked.connect(self.export_results)
        export_layout.addWidget(self.btn_export)
        
        self.lbl_export_summary = QLabel("Export not run yet.", f_export)
        self.lbl_export_summary.setProperty("class", "muted")
        self.lbl_export_summary.setWordWrap(True)
        export_layout.addWidget(self.lbl_export_summary)
        export_layout.addStretch()
        action_layout.addWidget(f_export)
        
        # Ops Actions (Move/Copy/Delete)
        f_ops = QWidget(self.action_frame)
        ops_layout = QHBoxLayout(f_ops)
        ops_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_move = QPushButton("Move Selected", f_ops)
        self.btn_move.setProperty("variant", "warning")
        self.btn_move.clicked.connect(lambda: self.organize('move'))
        ops_layout.addWidget(self.btn_move)
        
        self.btn_copy = QPushButton("Copy Selected", f_ops)
        self.btn_copy.setProperty("variant", "info")
        self.btn_copy.clicked.connect(lambda: self.organize('copy'))
        ops_layout.addWidget(self.btn_copy)
        
        self.btn_delete = QPushButton("Delete Selected", f_ops)
        self.btn_delete.setProperty("variant", "danger")
        self.btn_delete.clicked.connect(lambda: self.organize('delete'))
        ops_layout.addWidget(self.btn_delete)
        
        self.lbl_organize_summary = QLabel("Move/copy/delete preview not run yet.", f_ops)
        self.lbl_organize_summary.setProperty("class", "muted")
        self.lbl_organize_summary.setWordWrap(True)
        ops_layout.addWidget(self.lbl_organize_summary)
        ops_layout.addStretch()
        action_layout.addWidget(f_ops)
        
        # Rename Actions
        f_ren = QWidget(self.action_frame)
        ren_layout = QHBoxLayout(f_ren)
        ren_layout.setContentsMargins(0, 0, 0, 0)
        ren_layout.addWidget(QLabel("Rename (Regex):"))
        self.entry_ren_find = QLineEdit(f_ren)
        self.entry_ren_find.setPlaceholderText("Find Pattern")
        ren_layout.addWidget(self.entry_ren_find)
        
        self.entry_ren_repl = QLineEdit(f_ren)
        self.entry_ren_repl.setPlaceholderText("Replace Pattern")
        ren_layout.addWidget(self.entry_ren_repl)
        
        self.btn_rename = QPushButton("Rename All Matches", f_ren)
        self.btn_rename.clicked.connect(self.bulk_rename)
        ren_layout.addWidget(self.btn_rename)
        
        self.lbl_rename_summary = QLabel("Rename preview not run yet.", f_ren)
        self.lbl_rename_summary.setProperty("class", "muted")
        self.lbl_rename_summary.setWordWrap(True)
        ren_layout.addWidget(self.lbl_rename_summary)
        ren_layout.addStretch()
        action_layout.addWidget(f_ren)
        
        # Zip Actions
        f_zip = QWidget(self.action_frame)
        zip_layout = QHBoxLayout(f_zip)
        zip_layout.setContentsMargins(0, 0, 0, 0)
        zip_layout.addWidget(QLabel("Zip (Archive):"))
        self.entry_zip_name = QLineEdit(f_zip)
        self.entry_zip_name.setPlaceholderText("Archive_{date}")
        zip_layout.addWidget(self.entry_zip_name)
        
        self.zip_comp_combo = QComboBox(f_zip)
        self.zip_comp_combo.addItems(["Deflated", "Stored"])
        zip_layout.addWidget(self.zip_comp_combo)
        
        self.btn_zip_sel = QPushButton("Zip Selected", f_zip)
        self.btn_zip_sel.clicked.connect(lambda: self.archive_files('selected'))
        zip_layout.addWidget(self.btn_zip_sel)
        
        self.btn_zip_all = QPushButton("Zip All Found", f_zip)
        self.btn_zip_all.clicked.connect(lambda: self.archive_files('all'))
        zip_layout.addWidget(self.btn_zip_all)
        
        self.lbl_archive_summary = QLabel("Archive preview not run yet.", f_zip)
        self.lbl_archive_summary.setProperty("class", "muted")
        self.lbl_archive_summary.setWordWrap(True)
        zip_layout.addWidget(self.lbl_archive_summary)
        zip_layout.addStretch()
        action_layout.addWidget(f_zip)
        
        self.main_layout.addWidget(self.action_frame)
        
        self._init_slice_tooltips()

    def browse_file(self):
        path = self.choose_file(
            title="Select File to Search",
            filetypes=[("All Files", "*.*")],
        )
        if path:
            self.entry_path.setText(path)

    def browse_folder(self):
        path = self.choose_directory(title="Select Folder to Search")
        if path:
            self.entry_path.setText(path)

    def browse_path(self):
        self.browse_folder()
            
    def on_preview_select(self):
        sel = self.tree.selection()
        if not sel:
            self.preview_panel.clear()
            return

        path = self.tree.get_selected_path()
        if not path:
            return

        self.preview_panel.update_file(path, root=self.entry_path.text().strip())

    def start_search(self):
        path = self.entry_path.text().strip()
        if not path:
            return

        self.lbl_results_slice.setText(self._build_results_slice_summary())
        self.app.update_status(f"Searching in {path}...")

        search_name = self.entry_name.text().strip() or None
        search_exts = self.entry_ext.text().strip() or None
        content_text = self.entry_content.text().strip() or None
            
        min_size_bytes = None
        max_size_bytes = None
        try:
            min_s = self.entry_min_size.text().strip()
            if min_s:
                min_size_bytes = int(float(min_s) * 1024 * 1024)

            max_s = self.entry_max_size.text().strip()
            if max_s:
                max_size_bytes = int(float(max_s) * 1024 * 1024)
        except ValueError:
            self.app.show_error_dialog("Error", "Invalid Size value")
            return

        newer_days = None
        older_days = None
        try:
            newer = self.entry_newer.text().strip()
            if newer:
                newer_days = float(newer)

            older = self.entry_older.text().strip()
            if older:
                older_days = float(older)
        except ValueError:
            self.app.show_error_dialog("Error", "Invalid Days value")
            return

        try:
            query = build_search_query(
                name_pattern=search_name,
                use_regex=self.chk_regex.isChecked(),
                extensions=search_exts,
                content_text=content_text,
                min_size_bytes=min_size_bytes,
                max_size_bytes=max_size_bytes,
                newer_than_days=newer_days,
                older_than_days=older_days,
            )
        except Exception as exc:
            self.app.show_error_dialog("Search Error", str(exc))
            return
            
        # Clear tree
        self.tree.item_map.clear()
        self.tree.tree.clear()
            
        # Run in thread
        self.app.run_workflow(
            self._run_search_worker,
            self.on_search_complete,
            path,
            query,
            True,
            self.spin_depth.value(),
            self.sort_combo.currentText() or None,
            self.chk_reverse.isChecked(),
            self.spin_limit.value() or None,
            progress=True,
            error_title="Search Failed",
        )

    def _run_search_worker(self, path, query, recursive=True, max_depth=-1, sort_key=None, reverse=False, limit=None, progress_callback=None, cancel_token=None):
        results = search_files(
            path,
            query,
            recursive=recursive,
            max_depth=max_depth,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
        )
        return order_search_results(results, sort_key=sort_key, reverse=reverse, limit=limit)

    def _build_results_slice_summary(self):
        sort_key = self.sort_combo.currentText() or "natural order"
        direction = "descending" if self.chk_reverse.isChecked() else "ascending"
        limit = self.spin_limit.value()
        limit_text = f"limit {limit}" if limit > 0 else "full set"

        if sort_key == "natural order":
            return f"Slice: {sort_key} | {limit_text}"

        return f"Slice: sort {sort_key} ({direction}) | {limit_text}"

    def reset_slice(self):
        self.sort_combo.setCurrentIndex(0)
        self.chk_reverse.setChecked(False)
        self.spin_limit.setValue(0)
        self.lbl_results_slice.setText(self._build_results_slice_summary())

    def _init_slice_tooltips(self):
        attach_tooltips([
            (self.sort_combo, self.SLICE_TOOLTIPS["sort"]),
            (self.chk_reverse, self.SLICE_TOOLTIPS["reverse"]),
            (self.spin_limit, self.SLICE_TOOLTIPS["limit"]),
            (self.btn_reset_slice, self.SLICE_TOOLTIPS["reset"]),
        ])
        
    def on_search_complete(self, results):
        self.current_results = list(results)
        count = len(results)
        total_size = sum(e.size for e in results)
        self.lbl_organize_summary.setText("Move/copy/delete preview not run yet.")
        self.lbl_rename_summary.setText("Rename preview not run yet.")
        self.lbl_archive_summary.setText("Archive preview not run yet.")
        self.lbl_export_summary.setText("Export ready for current visible search results.")
        self.lbl_results_slice.setText(f"{self._build_results_slice_summary()} | visible {count}")
        
        self.app.update_status(f"Found {count} files (Total Size: {format_size(total_size)}).")
        root = self.entry_path.text().strip()
        for entry in results:
            self.tree.insert(
                "", "end",
                values=(entry.extension, format_display_path(entry.path, root=root), format_size(entry.size)),
                path=entry.path,
            )

    def export_results(self):
        if not self.current_results:
            self.app.show_warning_dialog("Nothing To Export", "Run a search first so there are visible results to save.")
            self.lbl_export_summary.setText("No current search results to export.")
            return

        export_format = self.export_format_combo.currentText().lower()
        extension = ".json" if export_format == "json" else ".csv"
        filetypes = f"{export_format.upper()} Files (*{extension});;All Files (*.*)"
        destination, _ = dialogs.get_save_file_name(
            self,
            "Save Search Results",
            "",
            filetypes
        )
        if not destination:
            return

        try:
            export_search_results(self.current_results, destination, format=export_format)
        except Exception as exc:
            self.app.show_error_dialog("Export Failed", str(exc))
            self.lbl_export_summary.setText("Export failed.")
            return

        self.app.update_status(f"Saved {len(self.current_results)} search results to {destination}")
        self.lbl_export_summary.setText(f"Saved {len(self.current_results)} result(s) as {export_format.upper()}.")
            
    def organize(self, action):
        selected_ids = self.tree.selection()
        if not selected_ids:
            self.app.show_warning_dialog("Nothing Selected", "Select one or more results first.")
            self.lbl_organize_summary.setText("Select one or more rows to preview move/copy/delete.")
            return

        target_dir = None
        if action != 'delete':
            target_dir = dialogs.get_existing_directory(self, f"Select Target to {action.title()}")
            if not target_dir:
                return

        targets = self._snapshot_rows(selected_ids)
        if not targets:
            self.app.show_warning_dialog("Nothing To Do", "No valid files were selected.")
            self.lbl_organize_summary.setText("No valid files available for move/copy/delete preview.")
            return

        self.lbl_organize_summary.setText(f"Previewing {action} for {len(targets)} file(s)...")
        self.app.update_status(f"Previewing {action} for {len(targets)} files...")
        self.app.run_workflow(
            self._preview_organize_worker,
            self._on_preview_organize_complete,
            targets,
            action,
            target_dir,
            progress=True,
            error_title=f"{action.title()} Preview Failed",
        )

    def bulk_rename(self):
        pat = self.entry_ren_find.text().strip()
        repl = self.entry_ren_repl.text()
        
        if not pat:
             return

        try:
            self.validate_regex_pattern(pat)
        except ValueError as exc:
            self.app.show_error_dialog("Rename Preview Failed", str(exc))
            self.app.update_status("Rename preview blocked by invalid pattern")
            self.lbl_rename_summary.setText("Rename preview blocked by invalid pattern.")
            return
        
        targets = self._snapshot_rows(self.tree.get_children())
        if not targets:
            self.app.show_warning_dialog("Nothing To Do", "No search results are available.")
            self.lbl_rename_summary.setText("No search results available for rename preview.")
            return

        self.lbl_rename_summary.setText(f"Previewing rename for {len(targets)} file(s)...")
        self.app.update_status(f"Previewing rename for {len(targets)} files...")
        self.app.run_workflow(
            self._preview_rename_worker,
            self._on_preview_rename_complete,
            targets,
            pat,
            repl,
            progress=True,
            error_title="Rename Preview Failed",
        )

    def archive_files(self, mode):
        files_to_zip = []
        if mode == 'selected':
            for iid in self.tree.selection():
                path = self.tree.get_item_path(iid)
                if path and os.path.exists(path): files_to_zip.append(path)
        else: # All
            for iid in self.tree.get_children():
                path = self.tree.get_item_path(iid)
                if path and os.path.exists(path): files_to_zip.append(path)
                
        if not files_to_zip:
            self.app.show_warning_dialog("Warning", "No files to zip.")
            self.lbl_archive_summary.setText("No files available for archive preview.")
            return

        name_val = self.entry_zip_name.text().strip()
        if not name_val:
             name_val = f"Archive_{datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')}"
        
        if not name_val.lower().endswith(".zip"):
            name_val += ".zip"
            
        target_dir = dialogs.get_existing_directory(self, "Save Zip To...")
        if not target_dir: return
        
        zip_path = os.path.join(target_dir, name_val)
        comp = zipfile.ZIP_DEFLATED if self.zip_comp_combo.currentText() == "Deflated" else zipfile.ZIP_STORED
        
        self.lbl_archive_summary.setText(f"Previewing archive {name_val} with {len(files_to_zip)} file(s)...")
        self.app.update_status(f"Previewing archive {name_val} with {len(files_to_zip)} files...")

        self.app.run_workflow(
            self._preview_zip_worker,
            self._on_preview_zip_complete,
            files_to_zip,
            zip_path,
            comp,
            name_val,
            progress=True,
            error_title="Zip Preview Failed",
        )

    def _snapshot_rows(self, item_ids):
        targets = []
        for item_id in item_ids:
            values = self.tree.item(item_id)["values"]
            if not values or len(values) < 2:
                continue
            path = self.tree.get_item_path(item_id)
            if not path or not os.path.exists(path):
                continue
            targets.append({
                "item_id": item_id,
                "path": path,
                "ext": values[0],
                "size": values[2],
            })
        return targets

    def _preview_organize_worker(self, targets, action, target_dir, progress_callback=None, cancel_token=None):
        if action == "delete":
            outcome = FileActionService.delete_items(
                targets,
                dry_run=True,
                progress_callback=progress_callback,
                cancel_token=cancel_token,
                path_getter=lambda target: target["path"],
            )
        else:
            outcome = FileActionService.transfer_items(
                targets,
                target_dir,
                action,
                dry_run=True,
                progress_callback=progress_callback,
                cancel_token=cancel_token,
                path_getter=lambda target: target["path"],
            )

        return {"cancelled": outcome.cancelled, "action": action, "records": outcome.records, "target_dir": target_dir}

    def _on_preview_organize_complete(self, outcome):
        previews = outcome["records"]
        action = outcome["action"]
        summary = f"{action.title()} {len(previews)} file(s)."
        lines = [record.message for record in previews]
        if not self.handle_preview_outcome(
            cancelled=outcome.get("cancelled"),
            records=previews,
            title=f"Confirm {action.title()}",
            summary=summary,
            lines=lines,
            action_label=f"{action} {len(previews)} file(s)",
            summary_var=self.lbl_organize_summary,
            ready_text=f"Ready: {len(previews)} | Action: {action.title()}",
            cancelled_summary="Move/copy/delete preview cancelled.",
            cancelled_status="Preview cancelled",
            empty_message="No matching files were available for this action.",
            empty_summary="No changes planned for move/copy/delete.",
            empty_status="No changes planned",
            declined_summary=f"Ready: {len(previews)} | Action: {action.title()} | Not applied",
            declined_status="Preview cancelled",
        ):
            return

        self.app.update_status(f"Running {action} for {len(previews)} files...")
        self.app.run_workflow(
            self._execute_organize_worker,
            self._on_execute_organize_complete,
            previews,
            action,
            outcome["target_dir"],
            progress=True,
            error_title=f"{action.title()} Failed",
        )

    def _execute_organize_worker(self, previews, action, target_dir, progress_callback=None, cancel_token=None):
        targets = [record.item for record in previews]
        if action == "delete":
            outcome = FileActionService.delete_items(
                targets,
                dry_run=False,
                progress_callback=progress_callback,
                cancel_token=cancel_token,
                path_getter=lambda target: target["path"],
            )
        else:
            outcome = FileActionService.transfer_items(
                targets,
                target_dir,
                action,
                dry_run=False,
                progress_callback=progress_callback,
                cancel_token=cancel_token,
                path_getter=lambda target: target["path"],
            )

        return {"cancelled": outcome.cancelled, "action": action, "successes": outcome.successes, "failures": outcome.failures}

    def _on_execute_organize_complete(self, outcome):
        action = outcome["action"]
        successes = outcome["successes"]

        if action in {"move", "delete"}:
            for record in successes:
                self.tree.delete(record.item["item_id"])
        else:
            self.restore_tree_selection(
                self.tree,
                [record.item["item_id"] for record in successes],
                on_select=self.on_preview_select,
            )
        self.present_batch_outcome(
            outcome,
            stopped_label=f"{action.title()} stopped.",
            complete_label=f"{action.title()} complete.",
            summary_var=self.lbl_organize_summary,
            summary_text="Applied: {success} | Failed: {failed} | Action: " + action.title(),
            cancelled_status=f"{action.title()} cancelled ({{success}} completed, {{failed}} failed)",
            complete_status=f"{action.title()} complete ({{success}} succeeded, {{failed}} failed)",
        )

    def _preview_rename_worker(self, targets, pattern, replacement, progress_callback=None, cancel_token=None):
        outcome = FileActionService.rename_items_with_regex(
            targets,
            pattern,
            replacement,
            dry_run=True,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=lambda target: target["path"],
        )
        changed = [record for record in outcome.records if not record.skipped]
        return {
            "cancelled": outcome.cancelled,
            "changed": changed,
            "unchanged": len(outcome.skipped_records),
            "pattern": pattern,
            "replacement": replacement,
        }

    def _on_preview_rename_complete(self, outcome):
        previews = outcome["changed"]
        unchanged = outcome["unchanged"]
        if not previews:
            self.app.show_info_dialog("Rename Preview", "No matching filenames would change.")
            self.app.update_status("No rename changes planned")
            self.lbl_rename_summary.setText(f"Ready: 0 | Unchanged: {unchanged}")
            return

        summary = f"Rename {len(previews)} file(s). Unchanged: {unchanged}."
        lines = [record.message for record in previews]
        if not self.handle_preview_outcome(
            cancelled=outcome.get("cancelled"),
            records=previews,
            title="Confirm Rename",
            summary=summary,
            lines=lines,
            action_label=f"rename {len(previews)} file(s)",
            summary_var=self.lbl_rename_summary,
            ready_text=f"Ready: {len(previews)} | Unchanged: {unchanged}",
            cancelled_summary="Rename preview cancelled.",
            cancelled_status="Rename preview cancelled",
            declined_summary=f"Ready: {len(previews)} | Unchanged: {unchanged} | Not applied",
            declined_status="Rename preview cancelled",
        ):
            return

        self.app.update_status(f"Renaming {len(previews)} files...")
        self.app.run_workflow(
            self._execute_rename_worker,
            self._on_execute_rename_complete,
            previews,
            outcome["pattern"],
            outcome["replacement"],
            progress=True,
            error_title="Rename Failed",
        )

    def _execute_rename_worker(self, previews, pattern, replacement, progress_callback=None, cancel_token=None):
        targets = [record.item for record in previews]
        outcome = FileActionService.rename_items_with_regex(
            targets,
            pattern,
            replacement,
            dry_run=False,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=lambda target: target["path"],
        )
        return {"cancelled": outcome.cancelled, "successes": outcome.successes, "failures": outcome.failures}

    def _on_execute_rename_complete(self, outcome):
        selected_item_ids = []
        root = self.entry_path.text().strip()
        for record in outcome["successes"]:
            item_id = record.item["item_id"]
            result = record.result
            # Keep the resolvable real path (used by get_item_path/preview)
            # in sync with the new destination, not just the displayed text.
            self.tree.set_item_path(item_id, result.destination_path)
            self.tree.set(item_id, "path", format_display_path(result.destination_path, root=root))
            selected_item_ids.append(item_id)

        self.restore_tree_selection(self.tree, selected_item_ids, on_select=self.on_preview_select)
        self.present_batch_outcome(
            outcome,
            stopped_label="Rename stopped.",
            complete_label="Rename complete.",
            summary_var=self.lbl_rename_summary,
            summary_text="Applied: {success} | Failed: {failed}",
            cancelled_status="Rename cancelled ({success} completed, {failed} failed)",
            complete_status="Rename complete ({success} succeeded, {failed} failed)",
        )

    def _preview_zip_worker(self, files, out_path, compression, archive_name, progress_callback=None, cancel_token=None):
        outcome = FileActionService.archive_items(
            files,
            mode="single",
            destination=out_path,
            compression=compression,
            dry_run=True,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=lambda file_path: file_path,
        )
        return {
            "cancelled": outcome.cancelled,
            "archive_name": archive_name,
            "zip_path": out_path,
            "files": files,
            "compression": compression,
            "lines": [record.message for record in outcome.records],
        }

    def _on_preview_zip_complete(self, outcome):
        count = len(outcome["files"])
        summary = f"Create {outcome['archive_name']} with {count} file(s)."
        if not self.handle_preview_outcome(
            cancelled=outcome.get("cancelled"),
            records=outcome["files"],
            title="Confirm Archive",
            summary=summary,
            lines=outcome["lines"],
            action_label=f"archive {count} file(s)",
            summary_var=self.lbl_archive_summary,
            ready_text=f"Ready: {count} file(s) -> {outcome['archive_name']}",
            cancelled_summary="Archive preview cancelled.",
            cancelled_status="Zip preview cancelled",
            empty_message="No files were available for this archive.",
            empty_summary="No files available for archive preview.",
            empty_status="No archive changes planned",
            declined_summary=f"Ready: {count} file(s) -> {outcome['archive_name']} | Not created",
            declined_status="Zip preview cancelled",
        ):
            return

        self.app.update_status(f"Creating archive {outcome['archive_name']}...")
        self.app.run_workflow(
            self._zip_worker,
            self._on_zip_complete,
            outcome["files"],
            outcome["zip_path"],
            outcome["compression"],
            outcome["archive_name"],
            progress=True,
            error_title="Zip Failed",
        )

    def _zip_worker(self, files, out_path, compression, archive_name, progress_callback, cancel_token=None):
        outcome = FileActionService.archive_items(
            files,
            mode="single",
            destination=out_path,
            compression=compression,
            dry_run=False,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=lambda file_path: file_path,
        )
        return {"cancelled": outcome.cancelled, "archive_name": archive_name, "outcome": outcome}

    def _on_zip_complete(self, outcome):
        archive_outcome = outcome["outcome"]
        attempted = archive_outcome.requested
        success_count = len(archive_outcome.successes)
        failure_count = len(archive_outcome.failures)

        if failure_count and not success_count:
            message = archive_outcome.failures[0].message
            self.app.show_error_dialog("Zip Failed", message)
            self.app.update_status(message)
            self.lbl_archive_summary.setText(f"Archive failed: {outcome['archive_name']}")
            return

        if outcome.get("cancelled"):
            self.app.update_status(f"Zip cancelled after {success_count} files.")
            self.lbl_archive_summary.setText(f"Created: 0 archive | Added: {success_count} | Failed: {failure_count}")
            self.app.show_warning_dialog(
                "Cancelled",
                self.summarize_completion(f"Archive creation stopped for {outcome['archive_name']}.", attempted, success_count, failure_count),
            )
            return

        self.app.update_status(
            f"Successfully archived {success_count} files to {outcome['archive_name']}."
        )
        self.lbl_archive_summary.setText(f"Created: 1 archive | Added: {success_count} | Failed: {failure_count}")
        if failure_count:
            summary = self.summarize_completion(
                f"Archive created: {outcome['archive_name']}",
                attempted,
                success_count,
                failure_count,
                created=1,
            )
            details = "\n".join(record.message for record in archive_outcome.failures[:8])
            self.app.show_warning_dialog(
                "Partial Success",
                f"{summary}\n\n{details}",
            )
        else:
            self.app.show_info_dialog(
                "Complete",
                self.summarize_completion(f"Archive created: {outcome['archive_name']}", attempted, success_count, failure_count, created=1),
            )
