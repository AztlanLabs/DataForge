from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QGroupBox, QSpinBox, QMessageBox, QGridLayout
)
from PyQt5.QtCore import Qt
import os

from ..views.base import BaseView
from ..widgets import EnhancedTreeview
from ...modules.search import build_search_query, search_files
from ...modules.cleaner import MetadataCleaner

class MetadataCleanerPlugin(BaseView):
    def get_title(self):
        return "Metadata Cleaner Plugin"

    def __init__(self, master, app=None):
        super().__init__(master, app)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        
        # 1. Search Criteria
        ctrl_frame = QGroupBox("Step 1: Find Files", self)
        ctrl_layout = QGridLayout(ctrl_frame)
        
        ctrl_layout.addWidget(QLabel("Path:", ctrl_frame), 0, 0)
        self.path_entry = QLineEdit(ctrl_frame)
        ctrl_layout.addWidget(self.path_entry, 0, 1)
        self.btn_browse = QPushButton("Browse", ctrl_frame)
        self.btn_browse.clicked.connect(self.browse)
        ctrl_layout.addWidget(self.btn_browse, 0, 2)
        
        ctrl_layout.addWidget(QLabel("Depth:", ctrl_frame), 0, 3)
        self.depth_spin = QSpinBox(ctrl_frame)
        self.depth_spin.setRange(-1, 10)
        self.depth_spin.setValue(-1)
        self.depth_spin.setFixedWidth(60)
        ctrl_layout.addWidget(self.depth_spin, 0, 4)
        
        ctrl_layout.addWidget(QLabel("Extensions (comma-sep):", ctrl_frame), 1, 0)
        self.ext_entry = QLineEdit(ctrl_frame)
        self.ext_entry.setText("jpg,jpeg,png")
        ctrl_layout.addWidget(self.ext_entry, 1, 1, 1, 3)
        
        self.btn_scan = QPushButton("Scan for Metadata", ctrl_frame)
        self.btn_scan.setStyleSheet("background-color: #0275d8; color: white;")
        self.btn_scan.clicked.connect(self.start_scan)
        ctrl_layout.addWidget(self.btn_scan, 1, 4)
        
        self.main_layout.addWidget(ctrl_frame)
        
        # 2. Results
        res_frame = QGroupBox("Step 2: Review & Clean", self)
        res_layout = QVBoxLayout(res_frame)
        
        self.tree = EnhancedTreeview(
            res_frame, 
            columns=("path", "size", "meta_flag", "meta_info"), 
            show="headings", 
            app=app
        )
        self.tree.heading("path", text="File Path")
        self.tree.heading("size", text="File Size")
        self.tree.heading("meta_flag", text="Has Metadata")
        self.tree.heading("meta_info", text="Metadata Info")
        
        self.tree.column("size", width=80)
        self.tree.column("meta_flag", width=80)
        
        res_layout.addWidget(self.tree, 1)
        
        # Actions
        act_frame = QWidget(res_frame)
        act_layout = QHBoxLayout(act_frame)
        act_layout.setContentsMargins(0, 5, 0, 5)
        
        act_layout.addStretch()
        
        self.btn_clean_sel = QPushButton("Clean Selected", act_frame)
        self.btn_clean_sel.setStyleSheet("background-color: #f0ad4e; color: white;")
        self.btn_clean_sel.clicked.connect(self.clean_selected)
        act_layout.addWidget(self.btn_clean_sel)
        
        self.btn_clean_all = QPushButton("Clean ALL Found", act_frame)
        self.btn_clean_all.setStyleSheet("background-color: #d9534f; color: white;")
        self.btn_clean_all.clicked.connect(self.clean_all)
        act_layout.addWidget(self.btn_clean_all)
        
        res_layout.addWidget(act_frame)
        self.main_layout.addWidget(res_frame, 1)
        
        self.scan_results = []

    def browse(self):
        p = self.choose_file_or_directory(
            file_title="Select File to Scan",
            directory_title="Select Folder to Scan",
            filetypes=[("Supported Files", "*.jpg *.jpeg *.png *.pdf"), ("All Files", "*.*")],
        )
        if p:
            self.path_entry.setText(p)

    def start_scan(self):
        path = self.path_entry.text()
        if not path or not os.path.exists(path):
            self.app.show_warning_dialog("Error", "Invalid path")
            return
            
        exts = [e.strip() for e in self.ext_entry.text().split(',') if e.strip()]
        depth = self.depth_spin.value()
        
        self.tree.delete(*self.tree.get_children())
        self.scan_results = []
        self.app.update_status("Scanning for files...")
        
        self.app.run_workflow(
            self._scan_worker,
            self._on_scan_complete,
            path, exts, depth,
            progress=True,
            error_title="Metadata Scan Failed",
        )
        
    def _scan_worker(self, path, exts, depth, progress_callback, cancel_token=None):
        query = build_search_query(extensions=exts)
        results = search_files(path, query, recursive=True, max_depth=depth, cancel_token=cancel_token)
        
        analyzed = []
        total = len(results)
        
        for i, entry in enumerate(results):
            if cancel_token and cancel_token.is_set(): return "Cancelled"
            
            # Analyze
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

    def _on_scan_complete(self, results):
        if results == "Cancelled":
            self.app.update_status("Scan Cancelled")
            return
            
        self.scan_results = results
        self.app.update_status(f"Found {len(results)} files with metadata.")
        
        for item in results:
            entry = item["entry"]
            self.tree.insert("", None, values=(
                entry.path, 
                entry.size, 
                item["meta_flag"], 
                item["meta_info"]
            ))

    def clean_selected(self):
        selected = self.tree.selection()
        if not selected: return
        targets = self._snapshot_rows(selected)
        if not targets:
            return
        
        reply = QMessageBox.question(
            self,
            "Confirm",
            f"Clean metadata from {len(targets)} files? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.app.update_status("Cleaning selected files...")

        self.app.run_workflow(
            self._clean_worker,
            self._on_clean_selected_complete,
            targets,
            progress=True,
            error_title="Metadata Cleanup Failed",
        )

    def clean_all(self):
        if not self.scan_results: return
        targets = self._snapshot_rows(self.tree.get_children())
        if not targets:
            return
        
        reply = QMessageBox.question(
            self,
            "WARNING",
            "Remove metadata from ALL files in the list? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        self.app.update_status("Cleaning all files...")
            
        self.app.run_workflow(
            self._clean_worker,
            self._on_clean_all_complete,
            targets,
            progress=True,
            error_title="Metadata Cleanup Failed",
        )

    def _snapshot_rows(self, item_ids):
        targets = []
        for iid in item_ids:
            values = self.tree.item(iid)["values"]
            if not values:
                continue
            targets.append({
                "item_id": iid,
                "path": values[0],
                "size": values[1],
            })
        return targets

    def _clean_worker(self, targets, progress_callback=None, cancel_token=None):
        cleaned = []
        failed = []
        total = len(targets)

        for index, target in enumerate(targets, start=1):
            if cancel_token and cancel_token.is_set():
                return {"cancelled": True, "cleaned": cleaned, "failed": failed}

            if MetadataCleaner.remove_metadata(target["path"]):
                cleaned.append(target)
            else:
                failed.append(target)

            if progress_callback:
                progress_callback(index, total, "Cleaning...")

        return {"cancelled": False, "cleaned": cleaned, "failed": failed}

    def _on_clean_complete(self, outcome, scope):
        cleaned = outcome["cleaned"]
        failed = outcome["failed"]

        for target in cleaned:
            self.tree.set(target["item_id"], "meta_flag", "CLEANED")
            self.tree.set(target["item_id"], "meta_info", "Removed")

        for target in failed:
            self.tree.set(target["item_id"], "meta_flag", "ERROR")
            self.tree.set(target["item_id"], "meta_info", "Failed")

        cleaned_count = len(cleaned)
        failed_count = len(failed)
        if outcome["cancelled"]:
            self.app.update_status(f"Cleaning cancelled ({cleaned_count} cleaned, {failed_count} failed)")
            self.app.show_warning_dialog("Cancelled", f"Cleaning stopped after {cleaned_count} files.")
            return

        self.app.update_status(f"Cleaned {cleaned_count} files ({failed_count} failed).")
        if scope == "all":
            self.app.show_info_dialog("Complete", f"Cleaned {cleaned_count} files. Failed: {failed_count}.")
        else:
            self.app.show_info_dialog("Result", f"Successfully cleaned {cleaned_count} files. Failed: {failed_count}.")

    def _on_clean_selected_complete(self, outcome):
        self._on_clean_complete(outcome, "selected")

    def _on_clean_all_complete(self, outcome):
        self._on_clean_complete(outcome, "all")
