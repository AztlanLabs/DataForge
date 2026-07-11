from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QGroupBox, QSpinBox, QCheckBox, QSplitter, QTabWidget, QGridLayout
)
from PyQt5.QtCore import Qt
from functools import partial
import os

from .base import BaseView
from .. import dialogs
from ...core.scanner import scan_directory
from ...core.services import FileActionService
from ...modules import integrity
from ...modules.cleaner import MetadataCleaner
from ..widgets import EnhancedTreeview, FilePreviewPanel, CollapsibleCard, NormalizeRulesWidget, attach_tooltips

class ToolsView(BaseView):
    TOOLTIP_TEXTS = {
        "integrity_source": "Select the file or folder to snapshot or verify. Single-file integrity checks are supported.",
        "integrity_output": "Choose where the snapshot JSON will be written so it can be reused later for verification.",
        "integrity_create": "Capture the current file hashes and metadata into a snapshot file.",
        "integrity_verify": "Compare the current filesystem state against a saved snapshot and report new, modified, or deleted files.",
        "cleaner_path": "Choose the file or folder to scan for removable metadata.",
        "cleaner_depth": "Limit how deep the scan descends into subfolders. Use -1 for no depth limit.",
        "cleaner_scan": "Scan the selected files for metadata before deciding what to clean.",
        "cleaner_selected": "Remove metadata only from the currently selected rows in the scan results.",
        "cleaner_all": "Remove metadata from every scanned result that supports cleaning.",
        "renamer_find": "Find text or patterns in the current filenames before previewing the rename plan.",
        "renamer_replace": "Replace the matched text with this value during preview and apply.",
        "renamer_prefix": "Add text to the beginning of each filename during preview and apply.",
        "renamer_suffix": "Add text to the end of each filename before the extension.",
        "renamer_strip_dot": "Remove a leading '.' from filenames that have one, e.g. '.file342.txt' -> 'file342.txt'.",
        "renamer_regex": "Treat Find as a regular expression instead of plain text.",
        "renamer_case": "Force the filename stem to lower/upper/title case, or leave it unchanged.",
        "renamer_numeric": "Replace numeric runs (or any regex match) with {n}, the sequential index, optionally zero-padded.",
        "renamer_collapse": "Collapse repeated spaces/underscores/hyphens into a single underscore.",
        "renamer_add": "Load one or more files into the batch renamer list.",
        "renamer_add_folder": "Scan a folder and load every file it contains into the batch renamer list.",
        "renamer_preview": "Build the proposed rename plan without changing files.",
        "renamer_apply": "Apply the currently previewed rename plan to the listed files.",
        "sync_source": "Choose the source folder whose files should be compared and copied outward.",
        "sync_dest": "Choose the destination folder that will receive missing or updated files.",
        "sync_analyze": "Compare source and destination first so you can inspect pending copy actions.",
        "sync_execute": "Perform the one-way sync using the current source and destination settings.",
    }

    def get_title(self):
        return "Tools & Workflows"

    def __init__(self, master, app=None):
        super().__init__(master, app)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        
        self.notebook = QTabWidget(self)
        self.main_layout.addWidget(self.notebook)
        
        # Tab 1: Integrity Monitor
        self.frame_integrity = QWidget()
        self.setup_integrity_tools()
        self.notebook.addTab(self.frame_integrity, "Integrity Monitor")
        
        # Tab 2: Metadata Cleaner
        self.frame_cleaner = QWidget()
        self._init_metadata_cleaner(self.frame_cleaner)
        self.notebook.addTab(self.frame_cleaner, "Metadata Cleaner")
        
        # Tab 3: Batch Renamer
        self.frame_renamer = QWidget()
        self._init_batch_renamer(self.frame_renamer)
        self.notebook.addTab(self.frame_renamer, "Batch Renamer")
        
        # Tab 4: Folder Sync
        self.frame_sync = QWidget()
        self._init_folder_sync(self.frame_sync)
        self.notebook.addTab(self.frame_sync, "Folder Sync")

    def setup_integrity_tools(self):
        layout = QVBoxLayout(self.frame_integrity)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Create Snapshot Labelframe
        f1 = QGroupBox("Create Snapshot", self.frame_integrity)
        f1_layout = QGridLayout(f1)
        
        f1_layout.addWidget(QLabel("Path:", f1), 0, 0)
        self.snap_folder = QLineEdit(f1)
        f1_layout.addWidget(self.snap_folder, 0, 1)
        self.snap_browse_button = QPushButton("Browse", f1)
        self.snap_browse_button.clicked.connect(lambda: self.browse_path(
            self.snap_folder,
            file_title="Select File to Snapshot",
            directory_title="Select Folder to Snapshot"
        ))
        f1_layout.addWidget(self.snap_browse_button, 0, 2)
        
        f1_layout.addWidget(QLabel("Output (.json):", f1), 1, 0)
        self.snap_out = QLineEdit(f1)
        f1_layout.addWidget(self.snap_out, 1, 1)
        self.snap_save_button = QPushButton("Save As", f1)
        self.snap_save_button.clicked.connect(lambda: self.save_file(self.snap_out))
        f1_layout.addWidget(self.snap_save_button, 1, 2)
        
        self.snap_create_button = QPushButton("Create", f1)
        self.snap_create_button.setStyleSheet("background-color: #0275d8; color: white;")
        self.snap_create_button.clicked.connect(self.create_snapshot)
        f1_layout.addWidget(self.snap_create_button, 2, 0, 1, 3)
        
        layout.addWidget(f1)
        
        self.integrity_create_summary = QLabel("Snapshot summary will appear here.", self.frame_integrity)
        self.integrity_create_summary.setStyleSheet("color: gray;")
        self.integrity_create_summary.setWordWrap(True)
        layout.addWidget(self.integrity_create_summary)
        
        # Verify Labelframe
        f2 = QGroupBox("Verify Integrity", self.frame_integrity)
        f2_layout = QGridLayout(f2)
        
        f2_layout.addWidget(QLabel("Target Path:", f2), 0, 0)
        self.verify_folder = QLineEdit(f2)
        f2_layout.addWidget(self.verify_folder, 0, 1)
        self.verify_browse_button = QPushButton("Browse", f2)
        self.verify_browse_button.clicked.connect(lambda: self.browse_path(
            self.verify_folder,
            file_title="Select File to Verify",
            directory_title="Select Folder to Verify"
        ))
        f2_layout.addWidget(self.verify_browse_button, 0, 2)
        
        f2_layout.addWidget(QLabel("Snapshot File:", f2), 1, 0)
        self.verify_file = QLineEdit(f2)
        f2_layout.addWidget(self.verify_file, 1, 1)
        self.verify_file_button = QPushButton("Browse", f2)
        self.verify_file_button.clicked.connect(lambda: self.open_file(self.verify_file))
        f2_layout.addWidget(self.verify_file_button, 1, 2)
        
        self.verify_button = QPushButton("Verify Integrity", f2)
        self.verify_button.setStyleSheet("background-color: #f0ad4e; color: white;")
        self.verify_button.clicked.connect(self.verify_snapshot)
        f2_layout.addWidget(self.verify_button, 2, 0, 1, 3)
        
        layout.addWidget(f2)
        
        self.integrity_verify_summary = QLabel("Verification summary will appear here.", self.frame_integrity)
        self.integrity_verify_summary.setStyleSheet("color: gray;")
        self.integrity_verify_summary.setWordWrap(True)
        layout.addWidget(self.integrity_verify_summary)
        
        layout.addStretch()
        self._init_integrity_tooltips()

    def browse_dir(self, entry):
        p = dialogs.get_existing_directory(self, "Select Folder")
        if p:
            entry.setText(p)

    def browse_path(self, entry, file_title="Select File", directory_title="Select Folder", filetypes=None):
        p = self.choose_file_or_directory(
            file_title=file_title,
            directory_title=directory_title,
            filetypes=filetypes,
        )
        if p:
            entry.setText(p)

    def save_file(self, entry):
        p, _ = dialogs.get_save_file_name(self, "Save Snapshot As", "", "JSON Files (*.json)")
        if p:
            entry.setText(p)

    def open_file(self, entry):
        p, _ = dialogs.get_open_file_name(self, "Open Snapshot File", "", "JSON Files (*.json)")
        if p:
            entry.setText(p)

    def create_snapshot(self):
        folder = self.snap_folder.text()
        out = self.snap_out.text()
        if not folder or not out: 
            self.app.show_warning_dialog("Missing Info", "Please select folder and output file.")
            return

        self.integrity_create_summary.setText("Creating snapshot...")
        self.app.update_status("Creating snapshot...")

        self.app.run_workflow(
            self._create_snapshot_worker,
            self._on_create_snapshot_complete,
            folder,
            out,
            progress=True,
            error_title="Snapshot Creation Failed",
        )

    def verify_snapshot(self):
        folder = self.verify_folder.text()
        snap = self.verify_file.text()
        if not folder or not snap:
            self.app.show_warning_dialog("Missing Info", "Please select folder and snapshot file.")
            return

        self.integrity_verify_summary.setText("Verifying snapshot...")
        self.app.update_status("Verifying snapshot...")
        self.app.run_background(
            integrity.IntegrityMonitor.verify_snapshot,
            self._on_verify_complete,
            folder,
            snap,
            show_progress=True,
            on_error=partial(self.app.show_workflow_error, title="Integrity Verification Failed"),
        )

    def _on_verify_complete(self, report):
        if not isinstance(report, dict) or "discrepancies" not in report or "stats" not in report:
            self.app.show_error_dialog("Integrity Verification Failed", str(report))
            self.app.update_status(f"Error: {report}")
            self.integrity_verify_summary.setText("Verification failed.")
            return

        stats = report["stats"]
        discrepancies = report["discrepancies"]
        
        msg = f"Modified: {stats['MODIFIED']}\n" \
              f"Deleted: {stats['DELETED']}\n" \
              f"New: {stats['NEW']}"
        findings = report["issue_count"]
        summary = self.summarize_completion(
            "Integrity verification complete.",
            max(report["snapshot_entries"], report["current_entries"]),
            0 if findings else max(report["snapshot_entries"], report["current_entries"], 1),
            findings,
        )
        self.integrity_verify_summary.setText(
            f"Snapshot: {report['snapshot_entries']} | Current: {report['current_entries']} | Issues: {findings}"
        )
              
        self.app.update_status("Verification Complete")
        if discrepancies:
            NetworkDetails = "\n".join(discrepancies[:20])
            if len(discrepancies) > 20:
                NetworkDetails += "\n..."
            self.app.show_warning_dialog("Integrity Issues Found", f"{summary}\n\n{msg}\n\nDetails:\n{NetworkDetails}")
        else:
            self.app.show_info_dialog("Integrity Check", f"{self.summarize_completion('Integrity verification complete.', 1, 1, 0)}\n\nNo discrepancies found. System is clean.")

    # -------------------------------------------------------------------------
    # TAB 2: Metadata Cleaner (Standalone)
    # -------------------------------------------------------------------------
    def _init_metadata_cleaner(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Scan Input (Card)
        card_scan = CollapsibleCard(parent, title="Scan Options")
        layout.addWidget(card_scan)
        
        s_body = card_scan.get_body()
        s_body_layout = QGridLayout(s_body)
        s_body_layout.setContentsMargins(0, 5, 0, 0)
        
        s_body_layout.addWidget(QLabel("Path:", s_body), 0, 0)
        self.cleaner_path_entry = QLineEdit(s_body)
        s_body_layout.addWidget(self.cleaner_path_entry, 0, 1)
        self.cleaner_browse_button = QPushButton("Browse", s_body)
        self.cleaner_browse_button.clicked.connect(lambda: self.browse_path(
            self.cleaner_path_entry,
            file_title="Select File to Scan",
            directory_title="Select Folder to Scan"
        ))
        s_body_layout.addWidget(self.cleaner_browse_button, 0, 2)
        
        s_body_layout.addWidget(QLabel("Extensions (comma sep):", s_body), 1, 0)
        self.cleaner_exts_entry = QLineEdit(s_body)
        self.cleaner_exts_entry.setText(".pdf, .jpg, .png")
        s_body_layout.addWidget(self.cleaner_exts_entry, 1, 1)
        
        s_body_layout.addWidget(QLabel("Max Depth:", s_body), 2, 0)
        self.cleaner_depth_spinbox = QSpinBox(s_body)
        self.cleaner_depth_spinbox.setRange(-1, 999)
        self.cleaner_depth_spinbox.setValue(3)
        s_body_layout.addWidget(self.cleaner_depth_spinbox, 2, 1)
        
        # Cleaner Buttons Row
        cleaner_btn_row = QWidget(s_body)
        cleaner_btn_layout = QHBoxLayout(cleaner_btn_row)
        cleaner_btn_layout.setContentsMargins(0, 5, 0, 0)
        
        self.cleaner_scan_button = QPushButton("SCAN FOR METADATA", cleaner_btn_row)
        self.cleaner_scan_button.setStyleSheet("background-color: #5bc0de; color: white;")
        self.cleaner_scan_button.clicked.connect(self.cleaner_start_scan)
        cleaner_btn_layout.addWidget(self.cleaner_scan_button)
        
        self.cleaner_selected_button = QPushButton("Clean Selected", cleaner_btn_row)
        self.cleaner_selected_button.setStyleSheet("background-color: #f0ad4e; color: white;")
        self.cleaner_selected_button.clicked.connect(self.cleaner_execute)
        cleaner_btn_layout.addWidget(self.cleaner_selected_button)
        
        self.cleaner_all_button = QPushButton("Clean All", cleaner_btn_row)
        self.cleaner_all_button.setStyleSheet("background-color: #d9534f; color: white;")
        self.cleaner_all_button.clicked.connect(self.cleaner_execute_all)
        cleaner_btn_layout.addWidget(self.cleaner_all_button)
        
        s_body_layout.addWidget(cleaner_btn_row, 3, 0, 1, 3)

        # Paned Window (Splitter)
        self.paned_meta = QSplitter(Qt.Horizontal, parent)
        layout.addWidget(self.paned_meta, 1)
        
        # Left: Tree
        self.f_tree_meta = QWidget(self.paned_meta)
        tree_layout = QVBoxLayout(self.f_tree_meta)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        
        self.cleaner_tree = EnhancedTreeview(self.f_tree_meta, columns=("path", "size", "has_meta", "info"), show="headings")
        self.cleaner_tree.heading("path", text="File Path")
        self.cleaner_tree.heading("size", text="Size")
        self.cleaner_tree.heading("has_meta", text="Metadata?")
        self.cleaner_tree.heading("info", text="Info")
        self.cleaner_tree.column("size", width=80)
        self.cleaner_tree.column("has_meta", width=60)
        tree_layout.addWidget(self.cleaner_tree)
        self.paned_meta.addWidget(self.f_tree_meta)
        
        self.cleaner_tree.tree.itemSelectionChanged.connect(self.on_cleaner_preview)
        
        # Right: Preview
        self.cleaner_preview = FilePreviewPanel(self.paned_meta)
        self.paned_meta.addWidget(self.cleaner_preview)
        
        self.paned_meta.setStretchFactor(0, 3)
        self.paned_meta.setStretchFactor(1, 1)
        
        self._init_metadata_cleaner_tooltips()

    def _init_integrity_tooltips(self):
        self._integrity_tooltips = attach_tooltips([
            (self.snap_folder, self.TOOLTIP_TEXTS["integrity_source"]),
            (self.snap_browse_button, self.TOOLTIP_TEXTS["integrity_source"]),
            (self.snap_out, self.TOOLTIP_TEXTS["integrity_output"]),
            (self.snap_save_button, self.TOOLTIP_TEXTS["integrity_output"]),
            (self.snap_create_button, self.TOOLTIP_TEXTS["integrity_create"]),
            (self.verify_folder, self.TOOLTIP_TEXTS["integrity_source"]),
            (self.verify_browse_button, self.TOOLTIP_TEXTS["integrity_source"]),
            (self.verify_file, self.TOOLTIP_TEXTS["integrity_output"]),
            (self.verify_file_button, self.TOOLTIP_TEXTS["integrity_output"]),
            (self.verify_button, self.TOOLTIP_TEXTS["integrity_verify"]),
        ])

    def _init_metadata_cleaner_tooltips(self):
        self._metadata_tooltips = attach_tooltips([
            (self.cleaner_path_entry, self.TOOLTIP_TEXTS["cleaner_path"]),
            (self.cleaner_browse_button, self.TOOLTIP_TEXTS["cleaner_path"]),
            (self.cleaner_depth_spinbox, self.TOOLTIP_TEXTS["cleaner_depth"]),
            (self.cleaner_scan_button, self.TOOLTIP_TEXTS["cleaner_scan"]),
            (self.cleaner_selected_button, self.TOOLTIP_TEXTS["cleaner_selected"]),
            (self.cleaner_all_button, self.TOOLTIP_TEXTS["cleaner_all"]),
        ])

    def _init_batch_renamer_tooltips(self):
        rules = self.renamer_rules_widget
        self._renamer_tooltips = attach_tooltips([
            (rules.find_edit, self.TOOLTIP_TEXTS["renamer_find"]),
            (rules.replace_edit, self.TOOLTIP_TEXTS["renamer_replace"]),
            (rules.prefix_edit, self.TOOLTIP_TEXTS["renamer_prefix"]),
            (rules.suffix_edit, self.TOOLTIP_TEXTS["renamer_suffix"]),
            (rules.chk_strip_dot, self.TOOLTIP_TEXTS["renamer_strip_dot"]),
            (rules.chk_use_regex, self.TOOLTIP_TEXTS["renamer_regex"]),
            (rules.case_combo, self.TOOLTIP_TEXTS["renamer_case"]),
            (rules.numeric_pattern_edit, self.TOOLTIP_TEXTS["renamer_numeric"]),
            (rules.numeric_replacement_edit, self.TOOLTIP_TEXTS["renamer_numeric"]),
            (rules.numeric_pad_spin, self.TOOLTIP_TEXTS["renamer_numeric"]),
            (rules.chk_collapse, self.TOOLTIP_TEXTS["renamer_collapse"]),
            (self.renamer_add_button, self.TOOLTIP_TEXTS["renamer_add"]),
            (self.renamer_add_folder_button, self.TOOLTIP_TEXTS["renamer_add_folder"]),
            (self.renamer_preview_button, self.TOOLTIP_TEXTS["renamer_preview"]),
            (self.renamer_apply_button, self.TOOLTIP_TEXTS["renamer_apply"]),
        ])

    def _init_folder_sync_tooltips(self):
        self._sync_tooltips = attach_tooltips([
            (self.sync_src_entry, self.TOOLTIP_TEXTS["sync_source"]),
            (self.sync_src_browse_button, self.TOOLTIP_TEXTS["sync_source"]),
            (self.sync_dst_entry, self.TOOLTIP_TEXTS["sync_dest"]),
            (self.sync_dst_browse_button, self.TOOLTIP_TEXTS["sync_dest"]),
            (self.sync_analyze_button, self.TOOLTIP_TEXTS["sync_analyze"]),
            (self.sync_execute_button, self.TOOLTIP_TEXTS["sync_execute"]),
        ])

    def _init_batch_renamer(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(10, 10, 10, 10)

        card_rules = CollapsibleCard(parent, title="Renaming Rules", expanded=True)
        layout.addWidget(card_rules)

        r_body = card_rules.get_body()
        r_body_layout = QVBoxLayout(r_body)
        r_body_layout.setContentsMargins(0, 5, 0, 0)

        self.renamer_params = {}
        self.renamer_rules_widget = NormalizeRulesWidget(r_body, params=self.renamer_params)
        r_body_layout.addWidget(self.renamer_rules_widget)

        # Renamer Buttons Row 1: source selection
        renamer_add_row = QWidget(r_body)
        renamer_add_layout = QHBoxLayout(renamer_add_row)
        renamer_add_layout.setContentsMargins(0, 5, 0, 0)

        self.renamer_add_button = QPushButton("Add Files...", renamer_add_row)
        self.renamer_add_button.clicked.connect(self.renamer_add_files)
        renamer_add_layout.addWidget(self.renamer_add_button)

        self.renamer_add_folder_button = QPushButton("Add Folder...", renamer_add_row)
        self.renamer_add_folder_button.clicked.connect(self.renamer_add_folder)
        renamer_add_layout.addWidget(self.renamer_add_folder_button)

        self.renamer_recursive_chk = QCheckBox("Recursive", renamer_add_row)
        self.renamer_recursive_chk.setChecked(True)
        renamer_add_layout.addWidget(self.renamer_recursive_chk)

        renamer_add_layout.addWidget(QLabel("Depth:", renamer_add_row))
        self.renamer_depth_spin = QSpinBox(renamer_add_row)
        self.renamer_depth_spin.setRange(-1, 999)
        self.renamer_depth_spin.setValue(-1)
        renamer_add_layout.addWidget(self.renamer_depth_spin)
        renamer_add_layout.addStretch()

        r_body_layout.addWidget(renamer_add_row)

        # Renamer Buttons Row 2: preview/apply
        renamer_btn_row = QWidget(r_body)
        renamer_btn_layout = QHBoxLayout(renamer_btn_row)
        renamer_btn_layout.setContentsMargins(0, 5, 0, 0)

        self.btn_ren_clear = QPushButton("Clear", renamer_btn_row)
        self.btn_ren_clear.clicked.connect(self.renamer_clear)
        renamer_btn_layout.addWidget(self.btn_ren_clear)

        self.renamer_preview_button = QPushButton("Preview", renamer_btn_row)
        self.renamer_preview_button.clicked.connect(self.renamer_preview)
        renamer_btn_layout.addWidget(self.renamer_preview_button)

        self.renamer_apply_button = QPushButton("APPLY", renamer_btn_row)
        self.renamer_apply_button.setStyleSheet("background-color: #5cb85c; color: white;")
        self.renamer_apply_button.clicked.connect(self.renamer_execute)
        renamer_btn_layout.addWidget(self.renamer_apply_button)
        renamer_btn_layout.addStretch()

        r_body_layout.addWidget(renamer_btn_row)

        self.renamer_summary_var = QLabel("Preview not run yet.", parent)
        self.renamer_summary_var.setStyleSheet("color: gray;")
        self.renamer_summary_var.setWordWrap(True)
        layout.addWidget(self.renamer_summary_var)

        cols = ("old", "new", "status")
        self.renamer_tree = EnhancedTreeview(parent, columns=cols, show="headings")
        self.renamer_tree.heading("old", text="Current Name")
        self.renamer_tree.heading("new", text="New Name")
        self.renamer_tree.heading("status", text="Status")
        layout.addWidget(self.renamer_tree, 1)

        self._init_batch_renamer_tooltips()

    def _init_folder_sync(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(10, 10, 10, 10)
        
        card_sync = CollapsibleCard(parent, title="Sync Configuration")
        layout.addWidget(card_sync)
        
        s_body = card_sync.get_body()
        s_body_layout = QGridLayout(s_body)
        s_body_layout.setContentsMargins(0, 5, 0, 0)
        
        s_body_layout.addWidget(QLabel("Source:", s_body), 0, 0)
        self.sync_src_entry = QLineEdit(s_body)
        s_body_layout.addWidget(self.sync_src_entry, 0, 1)
        self.sync_src_browse_button = QPushButton("Browse", s_body)
        self.sync_src_browse_button.clicked.connect(lambda: self.browse_dir(self.sync_src_entry))
        s_body_layout.addWidget(self.sync_src_browse_button, 0, 2)
        
        s_body_layout.addWidget(QLabel("Dest:", s_body), 1, 0)
        self.sync_dst_entry = QLineEdit(s_body)
        s_body_layout.addWidget(self.sync_dst_entry, 1, 1)
        self.sync_dst_browse_button = QPushButton("Browse", s_body)
        self.sync_dst_browse_button.clicked.connect(lambda: self.browse_dir(self.sync_dst_entry))
        s_body_layout.addWidget(self.sync_dst_browse_button, 1, 2)
        
        # Sync Buttons Row
        sync_btn_row = QWidget(s_body)
        sync_btn_layout = QHBoxLayout(sync_btn_row)
        sync_btn_layout.setContentsMargins(0, 5, 0, 0)
        
        self.sync_analyze_button = QPushButton("ANALYZE", sync_btn_row)
        self.sync_analyze_button.setStyleSheet("background-color: #5bc0de; color: white;")
        self.sync_analyze_button.clicked.connect(self.sync_analyze)
        sync_btn_layout.addWidget(self.sync_analyze_button)
        
        self.sync_execute_button = QPushButton("SYNC NOW", sync_btn_row)
        self.sync_execute_button.setStyleSheet("background-color: #d9534f; color: white;")
        self.sync_execute_button.clicked.connect(self.sync_execute)
        sync_btn_layout.addWidget(self.sync_execute_button)
        
        s_body_layout.addWidget(sync_btn_row, 2, 0, 1, 3)
        
        self.sync_summary_var = QLabel("Analyze to preview pending copy actions.", parent)
        self.sync_summary_var.setStyleSheet("color: gray;")
        self.sync_summary_var.setWordWrap(True)
        layout.addWidget(self.sync_summary_var)
        
        self.sync_tree = EnhancedTreeview(parent, columns=("file", "action"), show="headings")
        self.sync_tree.heading("file", text="File Relative Path")
        self.sync_tree.heading("action", text="Action Needed")
        layout.addWidget(self.sync_tree, 1)
        
        self._init_folder_sync_tooltips()

    # --- Renamer Logic ---
    def renamer_add_files(self):
        files, _ = dialogs.get_open_file_names(self, "Select Files")
        for f in files:
            self.renamer_tree.insert("", None, values=(f, "", "Pending"))
        if files:
            self.renamer_summary_var.setText(f"Loaded {len(self.renamer_tree.get_children())} file(s). Run Preview to see proposed names.")

    def renamer_add_folder(self):
        folder = dialogs.get_existing_directory(self, "Select Folder to Add")
        if not folder:
            return
        self.app.run_workflow(
            self._renamer_scan_folder_worker,
            self._on_renamer_scan_folder_complete,
            folder,
            self.renamer_recursive_chk.isChecked(),
            self.renamer_depth_spin.value(),
            progress=True,
            error_title="Folder Scan Failed",
        )

    def _renamer_scan_folder_worker(self, folder, recursive, depth, progress_callback=None, cancel_token=None):
        paths = []
        for entry in scan_directory(folder, recursive, max_depth=depth, cancel_token=cancel_token):
            if cancel_token and cancel_token.is_set():
                return {"cancelled": True, "paths": paths}
            paths.append(entry.path)
        return {"cancelled": False, "paths": paths}

    def _on_renamer_scan_folder_complete(self, outcome):
        if outcome.get("cancelled"):
            self.app.update_status("Folder scan cancelled")
            return
        for p in outcome["paths"]:
            self.renamer_tree.insert("", None, values=(p, "", "Pending"))
        self.renamer_summary_var.setText(f"Loaded {len(self.renamer_tree.get_children())} file(s). Run Preview to see proposed names.")

    def renamer_clear(self):
        self.renamer_tree.delete(*self.renamer_tree.get_children())
        self.renamer_summary_var.setText("Preview not run yet.")
            
    def renamer_preview(self):
        rows = self._snapshot_renamer_rows()
        if not rows:
            self.app.show_warning_dialog("Nothing To Preview", "Add one or more files first.")
            return

        rules = self._get_renamer_rules()
        self.app.update_status(f"Previewing rename for {len(rows)} files...")
        self.app.run_workflow(
            self._renamer_preview_worker,
            self._on_renamer_preview_complete,
            rows,
            rules,
            progress=True,
            error_title="Rename Preview Failed",
        )

    def renamer_execute(self):
        previews = self._collect_ready_renamer_rows()
        if not previews:
            self.app.show_warning_dialog("Preview Required", "Run Preview first so the rename plan is visible before applying it.")
            return

        summary = f"Rename {len(previews)} file(s)."
        lines = [f"Would rename: {os.path.basename(item['old_path'])} -> {item['new_name']}" for item in previews]
        if not self.confirm_preview("Confirm Rename", summary, lines=lines, action_label=f"rename {len(previews)} file(s)"):
            self.app.update_status("Rename preview cancelled")
            return

        self.app.update_status(f"Renaming {len(previews)} files...")
        self.app.run_workflow(
            self._renamer_execute_worker,
            self._on_renamer_execute_complete,
            previews,
            progress=True,
            error_title="Rename Failed",
        )

    # --- Sync Logic ---
    def sync_analyze(self):
        src = self.sync_src_entry.text()
        dst = self.sync_dst_entry.text()
        if not src or not dst:
            self.app.show_warning_dialog("Missing Info", "Select both source and destination folders.")
            return

        self.sync_tree.delete(*self.sync_tree.get_children())
        self.sync_summary_var.setText("Analyzing source and destination...")
        self.app.update_status("Analyzing sync differences...")
        self.app.run_workflow(
            self._sync_analyze_worker,
            self._on_sync_analyze_complete,
            src,
            dst,
            progress=True,
            error_title="Sync Analysis Failed",
        )
        
    def sync_execute(self):
        src = self.sync_src_entry.text()
        dst = self.sync_dst_entry.text()

        operations = self._snapshot_sync_rows()
        if not operations:
            self.app.show_warning_dialog("Nothing To Sync", "Run Analyze first, or there are no pending copy actions.")
            return

        lines = [f"Would copy: {item['rel_path']} ({item['action']})" for item in operations]
        if not self.confirm_preview("Confirm Sync", f"Sync {len(operations)} file(s).", lines=lines, action_label=f"sync {len(operations)} file(s)"):
            self.app.update_status("Sync preview cancelled")
            return

        self.app.update_status(f"Syncing {len(operations)} files...")
        self.app.run_workflow(
            self._sync_execute_worker,
            self._on_sync_execute_complete,
            src,
            dst,
            operations,
            progress=True,
            error_title="Sync Failed",
        )

    # --- Cleaner methods ---
    def cleaner_start_scan(self):
        from ...core.utils import parse_extensions
        path = self.cleaner_path_entry.text()
        if not path or not os.path.exists(path):
            self.app.show_warning_dialog("Error", "Invalid path")
            return
            
        exts = parse_extensions(self.cleaner_exts_entry.text())
        depth = self.cleaner_depth_spinbox.value()
        
        self.cleaner_tree.delete(*self.cleaner_tree.get_children())
        self.app.update_status("Scanning for files with metadata...")

        self.app.run_workflow(
            self._cleaner_scan_worker,
            self._on_cleaner_scan_complete,
            path, exts, depth,
            progress=True,
            error_title="Metadata Scan Failed",
        )
        
    def _cleaner_scan_worker(self, path, exts, depth, progress_callback, cancel_token=None):
        from ...modules.search import build_search_query, search_files
        query = build_search_query(extensions=exts)
        results = search_files(path, query, recursive=True, max_depth=depth, cancel_token=cancel_token)
        
        analyzed = []
        total = len(results)
        
        for i, entry in enumerate(results):
            if cancel_token and cancel_token.is_set(): return "Cancelled"
            
            has_meta, meta_size, meta_info = MetadataCleaner.get_metadata_info(entry.path)
            if has_meta:
                analyzed.append({
                    "entry": entry,
                    "meta_flag": "YES",
                    "meta_info": meta_info
                })
                
            if progress_callback and i % 10 == 0:
                progress_callback(i, total, "Analyzing Metadata...")
                
        return analyzed

    def _on_cleaner_scan_complete(self, results):
        from ...core.utils import format_size
        if results == "Cancelled":
            self.app.update_status("Scan Cancelled")
            return
            
        total_size = sum(item["entry"].size for item in results)
        
        self.app.update_status(f"Found {len(results)} files with metadata (Total Size: {format_size(total_size)}).")
        
        for item in results:
            entry = item["entry"]
            self.cleaner_tree.insert("", None, values=(
                entry.path, 
                format_size(entry.size), 
                item["meta_flag"], 
                item["meta_info"]
            ))

    def on_cleaner_preview(self):
        sel = self.cleaner_tree.selection()
        if not sel: 
            self.cleaner_preview.clear()
            return
            
        vals = self.cleaner_tree.item(sel[0])['values']
        if not vals: return
        path = vals[0]
        self.cleaner_preview.update_file(path)

    def cleaner_execute_all(self):
        items = self.cleaner_tree.get_children()
        if not items: return
        targets = self._snapshot_cleaner_rows(items)
        if not targets:
            return

        lines = [f"Would clean metadata: {target['path']}" for target in targets]
        if not self.confirm_preview("Confirm Metadata Cleanup", f"Clean metadata for {len(targets)} file(s).", lines=lines, action_label=f"clean {len(targets)} file(s)"):
            self.app.update_status("Metadata cleanup preview cancelled")
            return

        self.app.update_status("Cleaning all files...")

        self.app.run_workflow(
            self._cleaner_execute_worker,
            self._on_cleaner_execute_all_complete,
            targets,
            progress=True,
            error_title="Metadata Cleanup Failed",
        )

    def cleaner_execute(self):
        sel = self.cleaner_tree.selection()
        if not sel: return
        targets = self._snapshot_cleaner_rows(sel)
        if not targets:
            return

        lines = [f"Would clean metadata: {target['path']}" for target in targets]
        if not self.confirm_preview("Confirm Metadata Cleanup", f"Clean metadata for {len(targets)} file(s).", lines=lines, action_label=f"clean {len(targets)} file(s)"):
            self.app.update_status("Metadata cleanup preview cancelled")
            return
        
        self.app.update_status("Cleaning selected files...")

        self.app.run_workflow(
            self._cleaner_execute_worker,
            self._on_cleaner_execute_complete,
            targets,
            progress=True,
            error_title="Metadata Cleanup Failed",
        )

    def _snapshot_cleaner_rows(self, item_ids):
        targets = []
        for item_id in item_ids:
            values = self.cleaner_tree.item(item_id)["values"]
            if not values:
                continue
            targets.append({
                "item_id": item_id,
                "path": values[0],
                "size": values[1],
            })
        return targets

    def _cleaner_execute_worker(self, targets, progress_callback=None, cancel_token=None):
        cleaned = []
        failed = []
        total = len(targets)

        for index, target in enumerate(targets, start=1):
            if cancel_token and cancel_token.is_set():
                return {"cancelled": True, "cleaned": cleaned, "failed": failed}

            if MetadataCleaner.remove_metadata(target["path"], dry_run=False):
                cleaned.append(target)
            else:
                failed.append(target)

            if progress_callback:
                progress_callback(index, total, "Cleaning...")

        return {"cancelled": False, "cleaned": cleaned, "failed": failed}

    def _create_snapshot_worker(self, folder, out, progress_callback, cancel_token=None):
        return integrity.IntegrityMonitor.create_snapshot(
            folder,
            out,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
        )

    def _on_create_snapshot_complete(self, result):
        summary = self.summarize_completion(
            "Snapshot created.",
            result["scanned"],
            result["saved"],
            result["skipped"],
            created=1,
        )
        self.integrity_create_summary.setText(
            f"Scanned: {result['scanned']} | Saved: {result['saved']} | Skipped: {result['skipped']}"
        )
        self.app.update_status(f"Snapshot created: {result['message']}")
        self.app.show_info_dialog("Snapshot Created", f"{summary}\n\nOutput: {result['output']}")

    def _on_cleaner_execute_all_complete(self, outcome):
        self._on_cleaner_execute_complete(outcome, clear_preview=True)

    def _on_cleaner_execute_complete(self, outcome, clear_preview=False):
        cleaned = outcome["cleaned"]
        failed = outcome["failed"]
        selected_item_ids = [target["item_id"] for target in cleaned]

        for target in cleaned:
            self.cleaner_tree.set(target["item_id"], "has_meta", "Cleaned")
            self.cleaner_tree.set(target["item_id"], "info", "")

        for target in failed:
            self.cleaner_tree.set(target["item_id"], "has_meta", "Error")
            self.cleaner_tree.set(target["item_id"], "info", "Failed")

        cleaned_count = len(cleaned)
        failed_count = len(failed)
        attempted = cleaned_count + failed_count

        if clear_preview:
            self.cleaner_preview.clear()
        else:
            self.restore_tree_selection(self.cleaner_tree, selected_item_ids, on_select=self.on_cleaner_preview)

        if outcome["cancelled"]:
            self.app.update_status(f"Cleaning cancelled ({cleaned_count} cleaned, {failed_count} failed)")
            self.app.show_warning_dialog("Cancelled", self.summarize_completion("Metadata cleanup stopped.", attempted, cleaned_count, failed_count))
            return

        self.app.update_status(f"Cleaned {cleaned_count} files ({failed_count} failed).")
        if failed_count:
            self.app.show_warning_dialog("Result", self.summarize_completion("Metadata cleanup complete.", attempted, cleaned_count, failed_count))
        else:
            self.app.show_info_dialog("Success", self.summarize_completion("Metadata cleanup complete.", attempted, cleaned_count, failed_count))

    def _snapshot_renamer_rows(self):
        rows = []
        for item_id in self.renamer_tree.get_children():
            values = self.renamer_tree.item(item_id)["values"]
            if not values:
                continue
            rows.append({
                "item_id": item_id,
                "old_path": values[0],
                "new_name": values[1],
                "status": values[2],
            })
        return rows

    def _get_renamer_rules(self):
        return NormalizeRulesWidget.kwargs_from_params(self.renamer_params)

    def _renamer_preview_worker(self, rows, rules, progress_callback=None, cancel_token=None):
        outcome = FileActionService.rename_items_with_rules(
            rows,
            **rules,
            dry_run=True,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=lambda row: row["old_path"],
        )
        return {"cancelled": outcome.cancelled, "records": outcome.records}

    def _on_renamer_preview_complete(self, outcome):
        if outcome.get("cancelled"):
            self.app.update_status("Rename preview cancelled")
            self.renamer_summary_var.setText("Rename preview cancelled.")
            return

        ready = 0
        unchanged = 0
        invalid = 0
        for record in outcome["records"]:
            row = record.item
            new_name = os.path.basename(row["old_path"])
            status = record.message
            if record.skipped:
                status = "Unchanged"
                unchanged += 1
            elif record.success:
                new_name = os.path.basename(record.result.destination_path)
                try:
                    self.validate_filename_candidate(new_name)
                    status = "Ready"
                    ready += 1
                except ValueError as exc:
                    status = f"Invalid: {exc}"
                    invalid += 1
            else:
                invalid += 1
            
            self.renamer_tree.set(row["item_id"], "new", new_name)
            self.renamer_tree.set(row["item_id"], "status", status)

        self.renamer_summary_var.setText(f"Ready: {ready} | Unchanged: {unchanged} | Invalid: {invalid}")
        self.app.update_status(f"Rename preview ready ({ready} file(s) would change, {invalid} invalid)")

    def _collect_ready_renamer_rows(self):
        return [row for row in self._snapshot_renamer_rows() if row["status"] == "Ready"]

    def _renamer_execute_worker(self, previews, progress_callback=None, cancel_token=None):
        outcome = FileActionService.rename_items(
            previews,
            lambda preview, _index: preview["new_name"],
            dry_run=False,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=lambda preview: preview["old_path"],
        )
        return {"cancelled": outcome.cancelled, "successes": outcome.successes, "failures": outcome.failures}

    def _on_renamer_execute_complete(self, outcome):
        selected_item_ids = []
        for record in outcome["successes"]:
            result = record.result
            new_name = os.path.basename(result.destination_path)
            self.renamer_tree.set(record.item["item_id"], "old", result.destination_path)
            self.renamer_tree.set(record.item["item_id"], "new", new_name)
            self.renamer_tree.set(record.item["item_id"], "status", "Done")
            selected_item_ids.append(record.item["item_id"])

        for record in outcome["failures"]:
            preview = record.item
            self.renamer_tree.set(preview["item_id"], "status", record.message)

        self.restore_tree_selection(self.renamer_tree, selected_item_ids)
        self.present_batch_outcome(
            outcome,
            stopped_label="Rename stopped.",
            complete_label="Rename complete.",
            summary_var=self.renamer_summary_var,
            summary_text="Applied: {success} | Failed: {failed}",
            cancelled_status="Rename cancelled ({success} completed, {failed} failed)",
            complete_status="Rename complete ({success} succeeded, {failed} failed)",
            success_dialog_title="Success",
        )

    def _sync_analyze_worker(self, src, dst, progress_callback=None, cancel_token=None):
        src_files = {}
        for entry in scan_directory(src, recursive=True, cancel_token=cancel_token):
            if cancel_token and cancel_token.is_set():
                return {"cancelled": True, "operations": []}
            src_files[os.path.relpath(entry.path, src)] = entry.modified_at

        dst_files = {}
        if os.path.exists(dst):
            for entry in scan_directory(dst, recursive=True, cancel_token=cancel_token):
                if cancel_token and cancel_token.is_set():
                    return {"cancelled": True, "operations": []}
                dst_files[os.path.relpath(entry.path, dst)] = entry.modified_at

        operations = []
        total = len(src_files)
        for index, (rel_path, mtime) in enumerate(src_files.items(), start=1):
            if cancel_token and cancel_token.is_set():
                return {"cancelled": True, "operations": operations}

            if rel_path not in dst_files:
                operations.append({"rel_path": rel_path, "action": "Copy (New)"})
            elif mtime > dst_files[rel_path]:
                operations.append({"rel_path": rel_path, "action": "Copy (Newer)"})

            if progress_callback and total:
                progress_callback(index, total, "Analyzing Sync...")

        return {"cancelled": False, "operations": operations}

    def _on_sync_analyze_complete(self, outcome):
        if outcome.get("cancelled"):
            self.app.update_status("Sync analysis cancelled")
            self.sync_summary_var.setText("Sync analysis cancelled.")
            return

        new_count = sum(1 for operation in outcome["operations"] if operation["action"] == "Copy (New)")
        newer_count = sum(1 for operation in outcome["operations"] if operation["action"] == "Copy (Newer)")
        for operation in outcome["operations"]:
            self.sync_tree.insert("", None, values=(operation["rel_path"], operation["action"]))

        self.sync_summary_var.setText(f"Pending: {len(outcome['operations'])} | New: {new_count} | Updated: {newer_count}")
        self.app.update_status(f"Sync analysis complete ({len(outcome['operations'])} file(s) need action)")

    def _snapshot_sync_rows(self):
        operations = []
        for item_id in self.sync_tree.get_children():
            values = self.sync_tree.item(item_id)["values"]
            if not values:
                continue
            operations.append({"item_id": item_id, "rel_path": values[0], "action": values[1]})
        return operations

    def _sync_execute_worker(self, src, dst, operations, progress_callback=None, cancel_token=None):
        sync_items = [
            {
                "operation": operation,
                "source_path": os.path.join(src, operation["rel_path"]),
                "destination_dir": os.path.dirname(os.path.join(dst, operation["rel_path"])),
            }
            for operation in operations
        ]
        outcome = FileActionService.transfer_items(
            sync_items,
            None,
            "copy",
            dry_run=False,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=lambda item: item["source_path"],
            destination_getter=lambda item: item["destination_dir"],
        )
        return {"cancelled": outcome.cancelled, "successes": outcome.successes, "failures": outcome.failures}

    def _on_sync_execute_complete(self, outcome):
        for record in outcome["successes"]:
            self.sync_tree.delete(record.item["operation"]["item_id"])

        remaining = len(self.sync_tree.get_children())
        self.present_batch_outcome(
            outcome,
            stopped_label="Sync stopped.",
            complete_label="Sync complete.",
            summary_var=self.sync_summary_var,
            summary_text=f"Applied: {{success}} | Failed: {{failed}} | Remaining: {remaining}",
            cancelled_status="Sync cancelled ({success} completed, {failed} failed)",
            complete_status="Sync complete ({success} succeeded, {failed} failed)",
            success_dialog_title="Sync",
        )
