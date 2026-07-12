import os
from functools import partial

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QLineEdit, QCheckBox, QSpinBox, QComboBox, QSplitter, QGroupBox,
    QGridLayout
)
from PyQt5.QtCore import Qt

from .base import BaseView
from .. import dialogs
from ..theme_tokens import TOKENS
from ..widgets import EnhancedTreeview, FilePreviewPanel, CollapsibleCard, attach_tooltips
from ...core.config import config
from ...core.services import FileActionService
from ...core.utils import format_size, format_display_path
from ...modules.duplicates import (
    KEEP_STRATEGIES,
    build_duplicate_export_rows,
    build_duplicate_records,
    choose_duplicate_keeper,
    find_duplicates,
    order_duplicate_records,
    select_duplicate_records,
    serialize_duplicate_record,
)
from ...modules.search import export_result_rows


class DuplicatesView(BaseView):
    TOOLTIP_TEXTS = {
        "scan_path": "Choose the folder to scan for duplicate content. The finder groups files by size first, then by hash.",
        "depth": "Limit how deep the duplicate scan walks into subfolders. Use -1 for the full tree.",
        "hash_algorithm": "Pick the digest used to confirm duplicate content. Stronger hashes are safer but slower.",
        "sort": "Choose how duplicate rows are ordered before selection, export, and one-click actions. Group sorts by duplicate-set size.",
        "reverse": "Flip the current duplicate row order. Useful with size or modified dates to bring the biggest or newest files first.",
        "limit": "Only keep the first N duplicate rows visible and actionable. Use 0 for the full result set.",
        "reset": "Clear duplicate sort, reverse, and limit controls in one click.",
        "expand_all": "Expand every visible duplicate group so you can scan the full result tree at once.",
        "collapse_all": "Collapse every visible duplicate group to focus on the group summaries first.",
        "flat_export": "Exclude duplicate group summary rows from CSV or JSON exports when downstream tools expect a flat file list.",
        "keep_strategy": "Choose which file to keep in each duplicate group before selecting the extras to manage.",
        "select_extras": "Select every duplicate except the chosen keeper in each group so you can move, copy, or delete the extras in bulk.",
        "clear_selection": "Clear the current duplicate selection without rerunning the scan.",
        "keep_newest_delete": "Automatically keep the newest file in each visible duplicate group and delete the rest after preview.",
        "keep_largest_move": "Automatically keep the largest file in each visible duplicate group and move the rest after preview.",
        "keep_oldest_delete": "Automatically keep the oldest file in each visible duplicate group and delete the rest after preview.",
        "keep_smallest_move": "Automatically keep the smallest file in each visible duplicate group and move the rest after preview.",
        "copy_selected": "Copy the selected duplicate files into another folder after previewing the plan.",
        "move_selected": "Move the selected duplicate files out of the current groups after previewing the plan.",
        "delete_selected": "Send the selected duplicate files to Trash or delete them permanently, depending on Safe Mode.",
        "export_results": "Save the current duplicate groups to CSV or JSON for review outside the app.",
    }

    KEEP_STRATEGIES = list(KEEP_STRATEGIES)

    def get_title(self):
        return "Duplicate Finder"

    def __init__(self, master, app=None):
        super().__init__(master, app)
        self.current_results = {}
        self.visible_records = []
        self.item_records = {}
        self.group_items = {}
        self.expanded_group_hashes = set()

        # Main Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # Collapsible Scan Configuration Card
        self.card_scan = CollapsibleCard(self, title="Scan Configuration")
        self.main_layout.addWidget(self.card_scan)

        c_body = self.card_scan.get_body()
        c_body_layout = QVBoxLayout(c_body)
        c_body_layout.setContentsMargins(0, 5, 0, 0)
        c_body_layout.setSpacing(5)

        # Path Frame
        path_frame = QWidget(c_body)
        path_layout = QHBoxLayout(path_frame)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.addWidget(QLabel("Scan Path:"))
        self.entry_path = QLineEdit(path_frame)
        path_layout.addWidget(self.entry_path)
        self.btn_browse = QPushButton("Browse", path_frame)
        self.btn_browse.clicked.connect(self.browse)
        path_layout.addWidget(self.btn_browse)
        c_body_layout.addWidget(path_frame)

        # Options Frame
        opt_frame = QWidget(c_body)
        opt_layout = QHBoxLayout(opt_frame)
        opt_layout.setContentsMargins(0, 0, 0, 0)
        opt_layout.setSpacing(10)

        opt_layout.addWidget(QLabel("Depth:"))
        self.spin_depth = QSpinBox(opt_frame)
        self.spin_depth.setRange(-1, 999)
        self.spin_depth.setValue(-1)
        opt_layout.addWidget(self.spin_depth)

        opt_layout.addWidget(QLabel("Hash:"))
        self.hash_algo_combo = QComboBox(opt_frame)
        self.hash_algo_combo.addItems(["md5", "sha1", "sha256"])
        self.hash_algo_combo.setCurrentText(config.get("hash_algorithm", "md5"))
        opt_layout.addWidget(self.hash_algo_combo)

        opt_layout.addWidget(QLabel("Sort:"))
        self.sort_combo = QComboBox(opt_frame)
        self.sort_combo.addItems(["", "group", "ext", "path", "name", "size", "created", "modified"])
        self.sort_combo.currentTextChanged.connect(self._refresh_visible_results)
        opt_layout.addWidget(self.sort_combo)

        self.chk_reverse = QCheckBox("Reverse", opt_frame)
        self.chk_reverse.clicked.connect(self._refresh_visible_results)
        opt_layout.addWidget(self.chk_reverse)

        opt_layout.addWidget(QLabel("Limit:"))
        self.spin_limit = QSpinBox(opt_frame)
        self.spin_limit.setRange(0, 100000)
        self.spin_limit.setValue(0)
        self.spin_limit.valueChanged.connect(self._refresh_visible_results)
        opt_layout.addWidget(self.spin_limit)

        self.btn_reset_slice = QPushButton("Reset Slice", opt_frame)
        self.btn_reset_slice.clicked.connect(self.reset_slice)
        opt_layout.addWidget(self.btn_reset_slice)
        
        opt_layout.addStretch(1)
        c_body_layout.addWidget(opt_frame)

        # Run Button in header of Collapsible Card
        self.btn_run = self.card_scan.add_widget_to_header(
            QPushButton,
            text="RUN SCAN",
        )
        self.btn_run.setProperty("variant", "warning")
        self.btn_run.clicked.connect(self.start_scan)

        # Scan summaries
        self.lbl_scan_summary = QLabel("No duplicate scan run yet.", c_body)
        self.lbl_scan_summary.setProperty("class", "muted")
        self.lbl_scan_summary.setWordWrap(True)
        c_body_layout.addWidget(self.lbl_scan_summary)

        self.lbl_results_slice = QLabel("Slice: natural order | full set", c_body)
        self.lbl_results_slice.setProperty("class", "muted")
        self.lbl_results_slice.setWordWrap(True)
        c_body_layout.addWidget(self.lbl_results_slice)

        # Main Paned Splitter
        self.work_splitter = QSplitter(Qt.Horizontal, self)
        self.main_layout.addWidget(self.work_splitter, 1)

        # Left Frame
        self.tree_widget = QWidget(self.work_splitter)
        tree_layout = QVBoxLayout(self.tree_widget)
        tree_layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        tree_toolbar = QWidget(self.tree_widget)
        toolbar_layout = QHBoxLayout(tree_toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 5)
        self.btn_expand_all = QPushButton("Expand All", tree_toolbar)
        self.btn_expand_all.clicked.connect(self.expand_all_groups)
        toolbar_layout.addWidget(self.btn_expand_all)

        self.btn_collapse_all = QPushButton("Collapse All", tree_toolbar)
        self.btn_collapse_all.clicked.connect(self.collapse_all_groups)
        toolbar_layout.addWidget(self.btn_collapse_all)
        toolbar_layout.addStretch()
        tree_layout.addWidget(tree_toolbar)

        # Enhanced Tree View
        self.tree = EnhancedTreeview(self.tree_widget, columns=("type", "hash", "path", "size"), app=self.app)
        self.tree.heading("type", text="Type")
        self.tree.column("type", width=60, stretch=False)
        self.tree.heading("hash", text="Hash Group")
        self.tree.heading("path", text="File Path")
        self.tree.heading("size", text="Size")
        self.tree.tree.itemSelectionChanged.connect(self.on_preview_select)
        tree_layout.addWidget(self.tree)
        self.work_splitter.addWidget(self.tree_widget)

        # Preview Panel
        self.preview_panel = FilePreviewPanel(self.work_splitter)
        self.work_splitter.addWidget(self.preview_panel)
        self.work_splitter.setSizes([700, 400])

        # Action Group Box
        self.action_frame = QGroupBox("Duplicate Actions", self)
        action_layout = QVBoxLayout(self.action_frame)
        action_layout.setSpacing(5)

        # Keeper Selector toolbar
        selector_frame = QWidget(self.action_frame)
        selector_layout = QVBoxLayout(selector_frame)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(6)
        
        # Row 1: ComboBox and basic selection buttons
        row1_widget = QWidget(selector_frame)
        row1_layout = QHBoxLayout(row1_widget)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.addWidget(QLabel("Keep:", row1_widget))
        self.keep_strategy_combo = QComboBox(row1_widget)
        self.keep_strategy_combo.addItems(self.KEEP_STRATEGIES)
        self.keep_strategy_combo.setCurrentText(config.get("duplicate_default_keep_strategy", "first path"))
        row1_layout.addWidget(self.keep_strategy_combo)

        self.btn_select_extras = QPushButton("Select Extras", row1_widget)
        self.btn_select_extras.clicked.connect(self.select_extras)
        row1_layout.addWidget(self.btn_select_extras)

        self.btn_clear_selection = QPushButton("Clear Selection", row1_widget)
        self.btn_clear_selection.clicked.connect(self.clear_selection)
        row1_layout.addWidget(self.btn_clear_selection)
        row1_layout.addStretch()
        selector_layout.addWidget(row1_widget)

        # Row 2: Keep Delete Actions
        row2_widget = QWidget(selector_frame)
        row2_layout = QHBoxLayout(row2_widget)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_keep_newest_del = QPushButton("Keep Newest + Delete Rest", row2_widget)
        self.btn_keep_newest_del.setProperty("variant", "danger")
        self.btn_keep_newest_del.clicked.connect(lambda: self.run_keep_action("newest", "delete"))
        row2_layout.addWidget(self.btn_keep_newest_del)

        self.btn_keep_oldest_del = QPushButton("Keep Oldest + Delete Rest", row2_widget)
        self.btn_keep_oldest_del.setProperty("variant", "danger")
        self.btn_keep_oldest_del.clicked.connect(lambda: self.run_keep_action("oldest", "delete"))
        row2_layout.addWidget(self.btn_keep_oldest_del)
        row2_layout.addStretch()
        selector_layout.addWidget(row2_widget)

        # Row 3: Keep Move Actions
        row3_widget = QWidget(selector_frame)
        row3_layout = QHBoxLayout(row3_widget)
        row3_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_keep_largest_mov = QPushButton("Keep Largest + Move Rest", row3_widget)
        self.btn_keep_largest_mov.setProperty("variant", "warning")
        self.btn_keep_largest_mov.clicked.connect(lambda: self.run_keep_action("largest", "move"))
        row3_layout.addWidget(self.btn_keep_largest_mov)

        self.btn_keep_smallest_mov = QPushButton("Keep Smallest + Move Rest", row3_widget)
        self.btn_keep_smallest_mov.setProperty("variant", "warning")
        self.btn_keep_smallest_mov.clicked.connect(lambda: self.run_keep_action("smallest", "move"))
        row3_layout.addWidget(self.btn_keep_smallest_mov)
        row3_layout.addStretch()
        selector_layout.addWidget(row3_widget)
        action_layout.addWidget(selector_frame)

        # Standard selection operations
        action_buttons = QWidget(self.action_frame)
        buttons_layout = QHBoxLayout(action_buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_copy = QPushButton("Copy Selected", action_buttons)
        self.btn_copy.clicked.connect(lambda: self.run_duplicate_action("copy"))
        buttons_layout.addWidget(self.btn_copy)

        self.btn_move = QPushButton("Move Selected", action_buttons)
        self.btn_move.clicked.connect(lambda: self.run_duplicate_action("move"))
        buttons_layout.addWidget(self.btn_move)

        self.btn_delete = QPushButton("Delete Selected", action_buttons)
        self.btn_delete.clicked.connect(lambda: self.run_duplicate_action("delete"))
        buttons_layout.addWidget(self.btn_delete)
        buttons_layout.addStretch()
        action_layout.addWidget(action_buttons)

        # Export Options
        export_frame = QWidget(self.action_frame)
        export_layout = QHBoxLayout(export_frame)
        export_layout.setContentsMargins(0, 0, 0, 0)
        export_layout.addWidget(QLabel("Export Results:"))
        
        self.export_format_combo = QComboBox(export_frame)
        self.export_format_combo.addItems(["csv", "json"])
        export_layout.addWidget(self.export_format_combo)

        self.chk_flat_export = QCheckBox("Flat Export", export_frame)
        export_layout.addWidget(self.chk_flat_export)

        self.btn_export = QPushButton("Save Duplicate Results", export_frame)
        self.btn_export.clicked.connect(self.export_results)
        export_layout.addWidget(self.btn_export)
        export_layout.addStretch()
        action_layout.addWidget(export_frame)

        # Action status label
        self.lbl_action_summary = QLabel("Choose a keep strategy, then select extras or export current duplicate groups.", self.action_frame)
        self.lbl_action_summary.setProperty("class", "muted")
        self.lbl_action_summary.setWordWrap(True)
        action_layout.addWidget(self.lbl_action_summary)

        self.main_layout.addWidget(self.action_frame)

        self._init_tooltips()

    def browse(self):
        path = dialogs.get_existing_directory(self, "Select Scan Folder")
        if path:
            self.entry_path.setText(path)

    def start_scan(self):
        path = self.entry_path.text().strip()
        if not path:
            return

        config.set("hash_algorithm", self.hash_algo_combo.currentText())
        self.current_results = {}
        self.visible_records = []
        self.item_records = {}
        self.group_items = {}
        self.expanded_group_hashes = set()
        self.tree.tree.clear()
        
        self.lbl_scan_summary.setText("Scanning for duplicates...")
        self.lbl_results_slice.setText(self._build_results_slice_summary())
        self.lbl_action_summary.setText("Scanning duplicate groups before actions become available.")
        self.app.update_status(f"Scanning for duplicates in {path}...")

        self.app.run_workflow(
            find_duplicates,
            self.on_scan_complete,
            path,
            True,
            self.spin_depth.value(),
            progress=True,
            error_title="Duplicate Scan Failed",
        )

    def on_scan_complete(self, results):
        self.current_results = {hash_value: list(entries) for hash_value, entries in results.items()}
        self._refresh_visible_results()

        if not results:
            self.lbl_scan_summary.setText("No duplicate groups found.")
            self.lbl_results_slice.setText(f"{self._build_results_slice_summary()} | visible 0")
            self.lbl_action_summary.setText("Nothing to manage or export until a scan finds duplicates.")
            self.app.update_status("No duplicates found.")
            self.app.show_info_dialog("Result", "No duplicates found.")
            return

        duplicates_count = sum(len(entries) for entries in results.values())
        total_size = sum(sum(entry.size for entry in entries) for entries in results.values())
        self.lbl_scan_summary.setText(
            f"Groups: {len(results)} | Files: {duplicates_count} | Footprint: {format_size(total_size)}"
        )
        self.lbl_results_slice.setText(f"{self._build_results_slice_summary()} | visible {len(self.visible_records)}")
        self.lbl_action_summary.setText("Choose a keep strategy, select extra copies, then preview move/copy/delete or export.")
        self.app.update_status(f"Found {len(results)} duplicate groups ({duplicates_count} files total, {format_size(total_size)}).")

    def on_preview_select(self):
        selection = self.tree.selection()
        if not selection:
            self.preview_panel.clear()
            return

        path = self.tree.get_selected_path()
        if not path:
            return
        self.preview_panel.update_file(path, root=self.entry_path.text().strip())

    def select_extras(self):
        if not self.current_results:
            self.app.show_warning_dialog("Nothing To Select", "Run a duplicate scan first.")
            self.lbl_action_summary.setText("No duplicate groups available for keep-strategy selection.")
            return

        strategy = self.keep_strategy_combo.currentText() or self.KEEP_STRATEGIES[0]
        selected_records = select_duplicate_records(self.visible_records, keep_strategy=strategy)
        selected_ids = [item_id for item_id, record in self.item_records.items() if record in selected_records]

        if not selected_ids:
            self.app.show_info_dialog("Nothing Selected", "Every duplicate group only has its keeper left.")
            self.lbl_action_summary.setText("No extra duplicates remain to select.")
            return

        self._set_tree_selection(selected_ids, expand_matching_groups_only=True)
        self.lbl_action_summary.setText(f"Selected {len(selected_ids)} duplicate file(s) using keep strategy '{strategy}'.")

    def clear_selection(self):
        self.tree.tree.clearSelection()
        self.preview_panel.clear()
        self.lbl_action_summary.setText("Selection cleared.")

    def run_keep_action(self, keep_strategy, action):
        if not self.visible_records:
            self.app.show_warning_dialog("Nothing To Do", "Run a duplicate scan first.")
            self.lbl_action_summary.setText("No visible duplicate rows available for the one-click action.")
            return

        # One-click keep+act flows straight into a move/delete, so byte-verify
        # each non-keeper against its keeper before it can be acted on.
        selected_records = select_duplicate_records(self.visible_records, keep_strategy=keep_strategy, verify_content=True)
        selected_ids = [item_id for item_id, record in self.item_records.items() if record in selected_records]
        if not selected_ids:
            self.app.show_info_dialog("Nothing To Do", "No duplicate extras are visible in the current slice.")
            self.lbl_action_summary.setText("No duplicate extras are visible in the current slice.")
            return

        self.keep_strategy_combo.setCurrentText(keep_strategy)
        self._set_tree_selection(selected_ids, expand_matching_groups_only=True)
        self.lbl_action_summary.setText(f"Prepared keep {keep_strategy} + {action} for {len(selected_ids)} visible duplicate file(s).")
        self.run_duplicate_action(action)

    def run_duplicate_action(self, action):
        targets = self._selected_targets()
        if not targets:
            self.app.show_warning_dialog("Nothing Selected", "Select duplicate rows first or use Select Extras.")
            self.lbl_action_summary.setText("No duplicate rows selected for preview.")
            return

        target_dir = None
        if action != "delete":
            target_dir = dialogs.get_existing_directory(self, f"Select Target to {action.title()}")
            if not target_dir:
                return

        self.lbl_action_summary.setText(f"Previewing {action} for {len(targets)} duplicate file(s)...")
        self.app.update_status(f"Previewing duplicate {action} for {len(targets)} files...")
        self.app.run_workflow(
            self._preview_duplicate_action_worker,
            self._on_preview_duplicate_action_complete,
            targets,
            action,
            target_dir,
            progress=True,
            error_title=f"Duplicate {action.title()} Failed",
        )

    def export_results(self):
        rows = self._build_export_rows()
        if not rows:
            self.app.show_warning_dialog("Nothing To Export", "Run a duplicate scan first so there are groups to save.")
            self.lbl_action_summary.setText("No duplicate groups available to export.")
            return

        export_format = self.export_format_combo.currentText().lower()
        extension = ".json" if export_format == "json" else ".csv"
        filetypes = f"{export_format.upper()} Files (*{extension});;All Files (*.*)"
        destination, _ = dialogs.get_save_file_name(
            self,
            "Save Duplicate Results",
            "",
            filetypes
        )
        if not destination:
            return

        try:
            export_result_rows(rows, destination, format=export_format)
        except Exception as exc:
            self.app.show_error_dialog("Export Failed", str(exc))
            self.lbl_action_summary.setText("Duplicate export failed.")
            return

        self.app.update_status(f"Saved {len(rows)} duplicate rows to {destination}")
        self.lbl_action_summary.setText(f"Saved {len(rows)} duplicate row(s) as {export_format.upper()}.")

    def _selected_targets(self):
        targets = []
        for item_id in self.tree.selection():
            record = self.item_records.get(item_id)
            if not record:
                continue
            entry = record["entry"]
            if not os.path.exists(entry.path):
                continue
            targets.append({
                "item_id": item_id,
                "hash": record["hash"],
                "entry": entry,
                "source_path": entry.path,
            })
        return targets

    def _visible_records_to_tree_ids(self, records):
        record_ids = {id(record) for record in records}
        return [item_id for item_id, record in self.item_records.items() if id(record) in record_ids]

    def _set_tree_selection(self, item_ids, expand_matching_groups_only=False):
        if not item_ids:
            return
        if expand_matching_groups_only:
            self._expand_groups_for_item_ids(item_ids, collapse_others=True)
        self.tree.selection_set(item_ids)
        primary = item_ids[0]
        self.tree.focus(primary)
        self.tree.see(primary)
        self.on_preview_select()

    def _capture_expanded_group_state(self):
        expanded_hashes = set()
        for item_id, hash_value in self.group_items.items():
            if self.tree.item(item_id, "open"):
                expanded_hashes.add(hash_value)
        self.expanded_group_hashes = expanded_hashes

    def _preview_duplicate_action_worker(self, targets, action, target_dir, progress_callback=None, cancel_token=None):
        if action == "delete":
            outcome = FileActionService.delete_items(
                targets,
                dry_run=True,
                progress_callback=progress_callback,
                cancel_token=cancel_token,
                path_getter=lambda target: target["source_path"],
            )
        else:
            outcome = FileActionService.transfer_items(
                targets,
                target_dir,
                action,
                dry_run=True,
                progress_callback=progress_callback,
                cancel_token=cancel_token,
                path_getter=lambda target: target["source_path"],
            )

        return {"cancelled": outcome.cancelled, "action": action, "records": outcome.records, "target_dir": target_dir}

    def _on_preview_duplicate_action_complete(self, outcome):
        previews = outcome["records"]
        action = outcome["action"]
        summary = f"{action.title()} {len(previews)} duplicate file(s)."
        lines = [record.message for record in previews]
        if not self.handle_preview_outcome(
            cancelled=outcome.get("cancelled"),
            records=previews,
            title=f"Confirm {action.title()}",
            summary=summary,
            lines=lines,
            action_label=f"{action} {len(previews)} duplicate file(s)",
            summary_var=self.lbl_action_summary,
            ready_text=f"Ready: {len(previews)} | Action: {action.title()}",
            cancelled_summary="Duplicate action preview cancelled.",
            cancelled_status="Duplicate action preview cancelled",
            empty_message="No duplicate files were available for this action.",
            empty_summary="No duplicate files available for this action.",
            declined_summary=f"Ready: {len(previews)} | Action: {action.title()} | Not applied",
            declined_status="Duplicate action cancelled",
        ):
            return

        self.app.update_status(f"Running duplicate {action} for {len(previews)} files...")
        self.app.run_workflow(
            self._execute_duplicate_action_worker,
            self._on_execute_duplicate_action_complete,
            previews,
            action,
            outcome["target_dir"],
            progress=True,
            error_title=f"Duplicate {action.title()} Failed",
        )

    def _execute_duplicate_action_worker(self, previews, action, target_dir, progress_callback=None, cancel_token=None):
        targets = [record.item for record in previews]
        if action == "delete":
            outcome = FileActionService.delete_items(
                targets,
                dry_run=False,
                progress_callback=progress_callback,
                cancel_token=cancel_token,
                path_getter=lambda target: target["source_path"],
            )
        else:
            outcome = FileActionService.transfer_items(
                targets,
                target_dir,
                action,
                dry_run=False,
                progress_callback=progress_callback,
                cancel_token=cancel_token,
                path_getter=lambda target: target["source_path"],
            )

        return {"cancelled": outcome.cancelled, "action": action, "successes": outcome.successes, "failures": outcome.failures}

    def _on_execute_duplicate_action_complete(self, outcome):
        action = outcome["action"]
        successes = outcome["successes"]

        if action in {"move", "delete"}:
            self._drop_processed_entries(successes)
            self._refresh_visible_results()
        else:
            self._set_tree_selection([record.item["item_id"] for record in successes])
        self.present_batch_outcome(
            outcome,
            stopped_label=f"Duplicate {action.title()} stopped.",
            complete_label=f"Duplicate {action.title()} complete.",
            summary_var=self.lbl_action_summary,
            summary_text="Applied: {success} | Failed: {failed} | Action: " + action.title(),
            cancelled_status=f"Duplicate {action} cancelled ({{success}} completed, {{failed}} failed)",
            complete_status=f"Duplicate {action} complete ({{success}} succeeded, {{failed}} failed)",
        )

    def _drop_processed_entries(self, successes):
        removed_paths_by_hash = {}
        for record in successes:
            hash_value = record.item["hash"]
            removed_paths_by_hash.setdefault(hash_value, set()).add(record.item["source_path"])

        for hash_value, removed_paths in removed_paths_by_hash.items():
            remaining = [entry for entry in self.current_results.get(hash_value, []) if entry.path not in removed_paths]
            if len(remaining) > 1:
                self.current_results[hash_value] = remaining
            else:
                self.current_results.pop(hash_value, None)

        if not self.current_results:
            self.lbl_scan_summary.setText("No duplicate groups remain in the current result set.")
            self.lbl_action_summary.setText("Rescan to find more duplicates or export before applying actions next time.")
            self.lbl_results_slice.setText(f"{self._build_results_slice_summary()} | visible 0")

    def _rebuild_tree(self):
        self.tree.item_map.clear()
        self.tree.tree.clear()
        self.item_records = {}
        self.group_items = {}

        for hash_value, records in self._group_visible_records().items():
            total_size_bytes = sum(record["entry"].size for record in records)
            label = self._build_group_header_label(hash_value, records)
            group_item_id = self.tree.insert(
                "",
                "end",
                values=("GROUP", hash_value, label, format_size(total_size_bytes)),
                open=False,
            )
            self.group_items[group_item_id] = hash_value
            root = self.entry_path.text().strip()
            for record in records:
                entry = record["entry"]
                item_id = self.tree.insert(
                    group_item_id, "end",
                    values=(entry.extension, record["hash"], format_display_path(entry.path, root=root), format_size(entry.size)),
                    path=entry.path,
                )
                self.item_records[item_id] = record

        self._restore_expanded_group_state()

    def _build_export_rows(self):
        include_group_summary = not self.chk_flat_export.isChecked()
        return build_duplicate_export_rows(self.visible_records, include_group_summary=include_group_summary)

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
        self._refresh_visible_results()

    def _refresh_visible_results(self):
        self._capture_expanded_group_state()
        records = build_duplicate_records(self.current_results)
        self.visible_records = order_duplicate_records(
            records,
            sort_key=self.sort_combo.currentText() or None,
            reverse=self.chk_reverse.isChecked(),
            limit=self.spin_limit.value() or None,
        )
        self._rebuild_tree()
        self.lbl_results_slice.setText(f"{self._build_results_slice_summary()} | visible {len(self.visible_records)}")

    def expand_all_groups(self):
        self.expanded_group_hashes = set(self.group_items.values())
        for item_id in self.group_items:
            self.tree.item(item_id, open=True)

    def collapse_all_groups(self):
        self.expanded_group_hashes = set()
        for item_id in self.group_items:
            self.tree.item(item_id, open=False)

    def _restore_expanded_group_state(self):
        for item_id, hash_value in self.group_items.items():
            self.tree.item(item_id, open=hash_value in self.expanded_group_hashes)

    def _expand_groups_for_item_ids(self, item_ids, collapse_others=False):
        target_hashes = {
            self.item_records[item_id]["hash"]
            for item_id in item_ids
            if item_id in self.item_records
        }
        if collapse_others:
            self.expanded_group_hashes = set(target_hashes)
        else:
            self.expanded_group_hashes.update(target_hashes)
        self._restore_expanded_group_state()

    def _group_visible_records(self):
        grouped = {}
        for record in self.visible_records:
            grouped.setdefault(record["hash"], []).append(record)
        return grouped

    @staticmethod
    def _build_group_header_label(hash_value, records):
        group_size = records[0]["group_size"] if records else 0
        return f"{group_size} duplicate file(s) in group {hash_value[:12]}..."

    def _init_tooltips(self):
        attach_tooltips([
            (self.entry_path, self.TOOLTIP_TEXTS["scan_path"]),
            (self.spin_depth, self.TOOLTIP_TEXTS["depth"]),
            (self.hash_algo_combo, self.TOOLTIP_TEXTS["hash_algorithm"]),
            (self.sort_combo, self.TOOLTIP_TEXTS["sort"]),
            (self.chk_reverse, self.TOOLTIP_TEXTS["reverse"]),
            (self.spin_limit, self.TOOLTIP_TEXTS["limit"]),
            (self.btn_reset_slice, self.TOOLTIP_TEXTS["reset"]),
            (self.btn_expand_all, self.TOOLTIP_TEXTS["expand_all"]),
            (self.btn_collapse_all, self.TOOLTIP_TEXTS["collapse_all"]),
            (self.chk_flat_export, self.TOOLTIP_TEXTS["flat_export"]),
            (self.keep_strategy_combo, self.TOOLTIP_TEXTS["keep_strategy"]),
            (self.btn_select_extras, self.TOOLTIP_TEXTS["select_extras"]),
            (self.btn_clear_selection, self.TOOLTIP_TEXTS["clear_selection"]),
            (self.btn_keep_newest_del, self.TOOLTIP_TEXTS["keep_newest_delete"]),
            (self.btn_keep_largest_mov, self.TOOLTIP_TEXTS["keep_largest_move"]),
            (self.btn_keep_oldest_del, self.TOOLTIP_TEXTS["keep_oldest_delete"]),
            (self.btn_keep_smallest_mov, self.TOOLTIP_TEXTS["keep_smallest_move"]),
            (self.btn_copy, self.TOOLTIP_TEXTS["copy_selected"]),
            (self.btn_move, self.TOOLTIP_TEXTS["move_selected"]),
            (self.btn_delete, self.TOOLTIP_TEXTS["delete_selected"]),
            (self.btn_export, self.TOOLTIP_TEXTS["export_results"]),
        ])
