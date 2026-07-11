"""
File Recovery GUI view.

Two-tab interface for Trash Recovery (recently deleted files)
and Deep Recovery (raw disk carving from images/devices).
"""
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QCheckBox, QSpinBox, QGroupBox, QGridLayout, QTabWidget,
    QLineEdit, QComboBox, QMessageBox, QSplitter
)
from PyQt5.QtCore import Qt

from .base import BaseView
from .. import dialogs
from ..widgets import EnhancedTreeview, CollapsibleCard, attach_tooltips, FilePreviewPanel
from ...core.utils import format_size
from ...modules.recovery import (
    scan_trash,
    restore_from_trash,
    carve_files_from_image,
    check_photorec_available,
    run_photorec,
)
from ...modules.file_signatures import get_all_categories


class RecoveryView(BaseView):
    TOOLTIP_TEXTS = {
        "scan_trash": "Scan system Trash directories for recently deleted files that can be restored.",
        "restore_selected": "Restore the selected files to their original locations.",
        "restore_all": "Restore all deleted files found in the trash scan.",
        "image_path": "Path to a raw disk image (.dd, .img, .raw) or block device for file carving.",
        "output_dir": "Directory where carved/recovered files will be saved.",
        "max_files": "Maximum number of files to carve from the image. Higher values take longer.",
        "carve_start": "Begin carving files from the disk image using magic byte signature matching.",
        "photorec_start": "Use PhotoRec (professional tool) for recovery. Requires testdisk to be installed.",
    }

    def get_title(self):
        return "File Recovery"

    def __init__(self, master, app=None):
        super().__init__(master, app)
        self.trash_items = []
        self.trash_item_map = {}  # tree item_id -> trash item dict
        self.deep_item_map = {}   # tree item_id -> carved item dict

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, 1)

        # ===== Tab 1: Trash Recovery =====
        trash_tab = QWidget()
        trash_layout = QVBoxLayout(trash_tab)
        trash_layout.setContentsMargins(5, 5, 5, 5)

        # Scan card
        self.card_trash = CollapsibleCard(trash_tab, title="Trash Scanner")
        trash_layout.addWidget(self.card_trash)

        t_body = self.card_trash.get_body()
        t_body_layout = QVBoxLayout(t_body)
        t_body_layout.setContentsMargins(0, 5, 0, 0)

        self.lbl_trash_summary = QLabel(
            "Scan system Trash to find recently deleted files. "
            "Files can be restored to their original locations.",
            t_body,
        )
        self.lbl_trash_summary.setStyleSheet("color: #6c757d;")
        self.lbl_trash_summary.setWordWrap(True)
        t_body_layout.addWidget(self.lbl_trash_summary)

        self.btn_scan_trash = self.card_trash.add_widget_to_header(
            QPushButton, text="SCAN TRASH",
        )
        self.btn_scan_trash.setStyleSheet("background-color: #10b981; color: white; font-weight: bold;")
        self.btn_scan_trash.clicked.connect(self._start_trash_scan)

        # Summary bar
        summary_frame = QFrame(trash_tab)
        summary_frame.setFrameShape(QFrame.StyledPanel)
        sf_layout = QHBoxLayout(summary_frame)
        sf_layout.setContentsMargins(10, 8, 10, 8)
        self.lbl_trash_count = QLabel("Files in trash: —")
        self.lbl_trash_count.setStyleSheet("font-size: 15px; font-weight: bold; color: #3b82f6;")
        sf_layout.addWidget(self.lbl_trash_count)
        self.lbl_trash_size = QLabel("Total size: —")
        self.lbl_trash_size.setStyleSheet("font-size: 14px; color: #6b7280;")
        sf_layout.addWidget(self.lbl_trash_size)
        sf_layout.addStretch()
        trash_layout.addWidget(summary_frame)

        # Trash splitter
        self.trash_splitter = QSplitter(Qt.Horizontal, trash_tab)
        
        # Trash results tree
        self.trash_tree = EnhancedTreeview(
            self.trash_splitter,
            columns=("filename", "original_path", "deletion_date", "size", "location"),
            app=self.app,
        )
        self.trash_tree.heading("filename", text="Filename")
        self.trash_tree.heading("original_path", text="Original Path")
        self.trash_tree.heading("deletion_date", text="Deleted")
        self.trash_tree.column("deletion_date", width=140, stretch=False)
        self.trash_tree.heading("size", text="Size")
        self.trash_tree.column("size", width=80, stretch=False)
        self.trash_tree.heading("location", text="Trash Location")
        
        self.trash_tree.tree.itemSelectionChanged.connect(self._on_trash_selection_changed)
        self.trash_splitter.addWidget(self.trash_tree)
        
        # Preview panel
        self.trash_preview = FilePreviewPanel(self.trash_splitter)
        self.trash_splitter.addWidget(self.trash_preview)
        self.trash_splitter.setSizes([600, 300])
        
        trash_layout.addWidget(self.trash_splitter, 1)

        # Action buttons
        trash_actions = QWidget(trash_tab)
        ta_layout = QHBoxLayout(trash_actions)
        ta_layout.setContentsMargins(0, 5, 0, 0)

        self.btn_restore_selected = QPushButton("♻️ Restore Selected", trash_actions)
        self.btn_restore_selected.setStyleSheet("background-color: #10b981; color: white; font-weight: bold;")
        self.btn_restore_selected.clicked.connect(self._restore_selected)
        ta_layout.addWidget(self.btn_restore_selected)

        self.btn_restore_all = QPushButton("♻️ Restore All", trash_actions)
        self.btn_restore_all.clicked.connect(self._restore_all)
        ta_layout.addWidget(self.btn_restore_all)

        ta_layout.addStretch()
        self.lbl_restore_status = QLabel("", trash_actions)
        self.lbl_restore_status.setStyleSheet("color: #6c757d;")
        ta_layout.addWidget(self.lbl_restore_status)
        trash_layout.addWidget(trash_actions)

        self.tabs.addTab(trash_tab, "🗑 Trash Recovery")

        # ===== Tab 2: Deep Recovery =====
        deep_tab = QWidget()
        deep_layout = QVBoxLayout(deep_tab)
        deep_layout.setContentsMargins(5, 5, 5, 5)

        # Configuration card
        self.card_deep = CollapsibleCard(deep_tab, title="Deep Recovery Configuration")
        deep_layout.addWidget(self.card_deep)

        d_body = self.card_deep.get_body()
        d_body_layout = QVBoxLayout(d_body)
        d_body_layout.setContentsMargins(0, 5, 0, 0)
        d_body_layout.setSpacing(6)

        # Image path
        img_frame = QWidget(d_body)
        img_layout = QHBoxLayout(img_frame)
        img_layout.setContentsMargins(0, 0, 0, 0)
        img_layout.addWidget(QLabel("Image/Device:"))
        self.entry_image = QLineEdit(img_frame)
        self.entry_image.setPlaceholderText("/path/to/disk.img or /dev/sdb")
        img_layout.addWidget(self.entry_image)
        self.btn_browse_image = QPushButton("Browse", img_frame)
        self.btn_browse_image.clicked.connect(self._browse_image)
        img_layout.addWidget(self.btn_browse_image)
        d_body_layout.addWidget(img_frame)

        # Output directory
        out_frame = QWidget(d_body)
        out_layout = QHBoxLayout(out_frame)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.addWidget(QLabel("Output Dir:"))
        self.entry_output = QLineEdit(out_frame)
        self.entry_output.setPlaceholderText("/path/to/recovery/output")
        out_layout.addWidget(self.entry_output)
        self.btn_browse_output = QPushButton("Browse", out_frame)
        self.btn_browse_output.clicked.connect(self._browse_output)
        out_layout.addWidget(self.btn_browse_output)
        d_body_layout.addWidget(out_frame)

        # Options
        opts_frame = QWidget(d_body)
        opts_layout = QHBoxLayout(opts_frame)
        opts_layout.setContentsMargins(0, 0, 0, 0)
        opts_layout.addWidget(QLabel("Max Files:"))
        self.spin_max_files = QSpinBox(opts_frame)
        self.spin_max_files.setRange(1, 100000)
        self.spin_max_files.setValue(1000)
        opts_layout.addWidget(self.spin_max_files)
        opts_layout.addStretch()
        d_body_layout.addWidget(opts_frame)

        # File type filter
        type_group = QGroupBox("File Types to Recover", d_body)
        type_grid = QGridLayout(type_group)
        self.type_checks = {}
        categories = get_all_categories()
        col = 0
        for cat_name, formats in categories.items():
            chk = QCheckBox(f"{cat_name} ({len(formats)})", type_group)
            chk.setChecked(cat_name in ("Images", "Documents"))
            type_grid.addWidget(chk, col // 3, col % 3)
            self.type_checks[cat_name] = (chk, formats)
            col += 1
        d_body_layout.addWidget(type_group)

        # Carve buttons
        btn_frame = QWidget(d_body)
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_carve = QPushButton("🔍 Carve Files (Built-in)", btn_frame)
        self.btn_carve.setStyleSheet("background-color: #f59e0b; color: black; font-weight: bold;")
        self.btn_carve.clicked.connect(self._start_carve)
        btn_layout.addWidget(self.btn_carve)

        self.btn_photorec = QPushButton("⚡ PhotoRec Recovery", btn_frame)
        photorec_available = check_photorec_available()
        if photorec_available:
            self.btn_photorec.setStyleSheet("background-color: #8b5cf6; color: white; font-weight: bold;")
        else:
            self.btn_photorec.setEnabled(False)
            self.btn_photorec.setToolTip("photorec not installed. Install testdisk: sudo apt install testdisk")
        self.btn_photorec.clicked.connect(self._start_photorec)
        btn_layout.addWidget(self.btn_photorec)

        btn_layout.addStretch()
        d_body_layout.addWidget(btn_frame)

        # Deep recovery summary
        self.lbl_deep_summary = QLabel("Configure image path and file types, then start recovery.", d_body)
        self.lbl_deep_summary.setStyleSheet("color: #6c757d;")
        self.lbl_deep_summary.setWordWrap(True)
        d_body_layout.addWidget(self.lbl_deep_summary)

        # Deep splitter
        self.deep_splitter = QSplitter(Qt.Horizontal, deep_tab)
        
        # Results tree
        self.deep_tree = EnhancedTreeview(
            self.deep_splitter,
            columns=("format", "filename", "size", "offset"),
            app=self.app,
        )
        self.deep_tree.heading("format", text="Format")
        self.deep_tree.column("format", width=80, stretch=False)
        self.deep_tree.heading("filename", text="Recovered File")
        self.deep_tree.heading("size", text="Size")
        self.deep_tree.column("size", width=80, stretch=False)
        self.deep_tree.heading("offset", text="Disk Offset")
        self.deep_tree.column("offset", width=100, stretch=False)
        
        self.deep_tree.tree.itemSelectionChanged.connect(self._on_deep_selection_changed)
        self.deep_splitter.addWidget(self.deep_tree)
        
        # Preview panel
        self.deep_preview = FilePreviewPanel(self.deep_splitter)
        self.deep_splitter.addWidget(self.deep_preview)
        self.deep_splitter.setSizes([600, 300])
        
        deep_layout.addWidget(self.deep_splitter, 1)

        self.tabs.addTab(deep_tab, "💾 Deep Recovery")

        self._init_tooltips()

    # ------------------------------------------------------------------
    # Trash recovery
    # ------------------------------------------------------------------

    def _start_trash_scan(self):
        self.trash_items = []
        self.trash_item_map = {}
        self.trash_tree.tree.clear()
        self.trash_tree.item_map.clear()
        self.lbl_trash_summary.setText("Scanning trash directories...")
        self.app.update_status("Scanning trash...")

        self.app.run_workflow(
            scan_trash,
            self._on_trash_scan_complete,
            progress=True,
            error_title="Trash Scan Failed",
        )

    def _on_trash_scan_complete(self, results):
        self.trash_items = results

        if not results:
            self.lbl_trash_summary.setText("No files found in system trash.")
            self.lbl_trash_count.setText("Files in trash: 0")
            self.lbl_trash_size.setText("Total size: 0 B")
            self.app.update_status("Trash scan complete — no files found.")
            return

        total_size = sum(item["size"] for item in results)
        self.lbl_trash_count.setText(f"Files in trash: {len(results)}")
        self.lbl_trash_size.setText(f"Total size: {format_size(total_size)}")
        self.lbl_trash_summary.setText(
            f"Found {len(results)} deleted files ({format_size(total_size)}) across trash directories."
        )

        # Build tree
        self.trash_tree.tree.clear()
        self.trash_tree.item_map.clear()
        self.trash_item_map = {}

        for item in results:
            item_id = self.trash_tree.insert("", "end", values=(
                item["filename"],
                item["original_path"],
                item.get("deletion_date", "—"),
                item["formatted_size"],
                item.get("trash_location", ""),
            ))
            self.trash_item_map[item_id] = item

        self.app.update_status(f"Found {len(results)} files in trash ({format_size(total_size)}).")

    def _restore_selected(self):
        selection = self.trash_tree.selection()
        items_to_restore = [self.trash_item_map[iid] for iid in selection if iid in self.trash_item_map]
        self._run_restore(items_to_restore)

    def _restore_all(self):
        self._run_restore(list(self.trash_items))

    def _run_restore(self, items):
        if not items:
            self.app.show_warning_dialog("Nothing to Restore", "Select files to restore first.")
            return

        summary = f"Restore {len(items)} file(s) to their original locations?"
        lines = [f"  {item['filename']} → {item['original_path']}" for item in items[:8]]
        if len(items) > 8:
            lines.append(f"  ... and {len(items) - 8} more")

        if not self.confirm_preview("Confirm Restore", summary, lines, f"restore {len(items)} files"):
            self.lbl_restore_status.setText("Restore cancelled.")
            return

        self.app.run_workflow(
            restore_from_trash,
            self._on_restore_complete,
            items,
            progress=True,
            error_title="Restore Failed",
        )

    def _on_restore_complete(self, result):
        restored = result.get("restored", [])
        failed = result.get("failed", [])

        if restored:
            # Remove restored items from tree
            restored_paths = {r["item"]["path"] for r in restored}
            self.trash_items = [i for i in self.trash_items if i["path"] not in restored_paths]
            self._on_trash_scan_complete(self.trash_items)

        self.lbl_restore_status.setText(f"Restored: {len(restored)} | Failed: {len(failed)}")
        self.app.update_status(f"Restore complete: {len(restored)} restored, {len(failed)} failed.")

        if failed:
            error_msgs = [f["error"] for f in failed[:5]]
            self.app.show_warning_dialog(
                "Partial Restore",
                f"Restored {len(restored)} files.\n{len(failed)} failed:\n" + "\n".join(error_msgs),
            )
        elif restored:
            self.app.show_info_dialog("Restore Complete", f"Successfully restored {len(restored)} files.")

    # ------------------------------------------------------------------
    # Deep recovery
    # ------------------------------------------------------------------

    def _browse_image(self):
        path, _ = dialogs.get_open_file_name(
            self, "Select Disk Image",
            "", "Disk Images (*.img *.dd *.raw *.iso *.e01);;All Files (*)",
        )
        if path:
            self.entry_image.setText(path)

    def _browse_output(self):
        path = dialogs.get_existing_directory(self, "Select Output Directory")
        if path:
            self.entry_output.setText(path)

    def _get_selected_file_types(self):
        types = []
        for cat_name, (chk, formats) in self.type_checks.items():
            if chk.isChecked():
                types.extend(formats)
        return list(set(types)) or None

    def _start_carve(self):
        image = self.entry_image.text().strip()
        output = self.entry_output.text().strip()

        if not image:
            self.app.show_warning_dialog("Missing Image", "Specify a disk image or device path.")
            return
        if not output:
            self.app.show_warning_dialog("Missing Output", "Specify an output directory.")
            return

        file_types = self._get_selected_file_types()
        max_files = self.spin_max_files.value()

        self.deep_tree.tree.clear()
        self.deep_tree.item_map.clear()
        self.lbl_deep_summary.setText("Carving files from disk image...")
        self.app.update_status("Starting file carving...")

        self.app.run_workflow(
            carve_files_from_image,
            self._on_carve_complete,
            image, output, file_types, max_files,
            progress=True,
            error_title="Carving Failed",
        )

    def _on_carve_complete(self, result):
        if "error" in result:
            self.lbl_deep_summary.setText(f"Error: {result['error']}")
            return

        carved = result.get("carved", [])
        errors = result.get("errors", [])

        self.deep_tree.tree.clear()
        self.deep_tree.item_map.clear()
        self.deep_item_map = {}

        for item in carved:
            item_id = self.deep_tree.insert("", "end", values=(
                item["format"],
                os.path.basename(item["path"]),
                item["formatted_size"],
                f"0x{item['offset']:X}",
            ))
            self.deep_item_map[item_id] = item

        self.lbl_deep_summary.setText(
            f"Carved {len(carved)} file(s) from {result['image_path']}. "
            f"Output: {result['output_dir']}"
            + (f" | {len(errors)} errors" if errors else "")
        )
        self.app.update_status(f"Carving complete: {len(carved)} files recovered.")

        if carved:
            self.app.show_info_dialog(
                "Carving Complete",
                f"Recovered {len(carved)} files to:\n{result['output_dir']}",
            )

    def _start_photorec(self):
        image = self.entry_image.text().strip()
        output = self.entry_output.text().strip()

        if not image:
            self.app.show_warning_dialog("Missing Image", "Specify a disk image or device path.")
            return
        if not output:
            self.app.show_warning_dialog("Missing Output", "Specify an output directory.")
            return

        reply = QMessageBox.question(
            self,
            "Run PhotoRec",
            f"PhotoRec will attempt deep recovery from:\n{image}\n\n"
            f"Results will be saved to:\n{output}\n\n"
            "This may take a long time for large images. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.lbl_deep_summary.setText("Running PhotoRec recovery (this may take a while)...")
        self.app.update_status("PhotoRec recovery in progress...")

        self.app.run_workflow(
            run_photorec,
            self._on_photorec_complete,
            image, output,
            progress=True,
            error_title="PhotoRec Failed",
        )

    def _on_photorec_complete(self, result):
        if "error" in result:
            self.lbl_deep_summary.setText(f"PhotoRec error: {result['error']}")
            self.app.show_error_dialog("PhotoRec Error", result["error"])
            return

        recovered = result.get("recovered", [])

        self.deep_tree.tree.clear()
        self.deep_tree.item_map.clear()
        self.deep_item_map = {}

        for item in recovered:
            ext = os.path.splitext(item["filename"])[1]
            item_id = self.deep_tree.insert("", "end", values=(
                ext, item["filename"], format_size(item["size"]), "",
            ))
            self.deep_item_map[item_id] = item

        self.lbl_deep_summary.setText(
            f"PhotoRec recovered {len(recovered)} file(s) to {result['output_dir']}."
        )
        self.app.update_status(f"PhotoRec complete: {len(recovered)} files recovered.")

    def _on_trash_selection_changed(self):
        sel = self.trash_tree.selection()
        if not sel:
            self.trash_preview.clear()
            return
        item_id = sel[0]
        item = self.trash_item_map.get(item_id)
        if item and "path" in item and os.path.exists(item["path"]):
            self.trash_preview.update_file(item["path"])
        else:
            self.trash_preview.clear()

    def _on_deep_selection_changed(self):
        sel = self.deep_tree.selection()
        if not sel:
            self.deep_preview.clear()
            return
        item_id = sel[0]
        item = self.deep_item_map.get(item_id)
        if item and "path" in item and os.path.exists(item["path"]):
            self.deep_preview.update_file(item["path"])
        else:
            self.deep_preview.clear()

    # ------------------------------------------------------------------
    # Tooltips
    # ------------------------------------------------------------------

    def _init_tooltips(self):
        attach_tooltips([
            (self.btn_scan_trash, self.TOOLTIP_TEXTS["scan_trash"]),
            (self.btn_restore_selected, self.TOOLTIP_TEXTS["restore_selected"]),
            (self.btn_restore_all, self.TOOLTIP_TEXTS["restore_all"]),
            (self.entry_image, self.TOOLTIP_TEXTS["image_path"]),
            (self.entry_output, self.TOOLTIP_TEXTS["output_dir"]),
            (self.spin_max_files, self.TOOLTIP_TEXTS["max_files"]),
            (self.btn_carve, self.TOOLTIP_TEXTS["carve_start"]),
            (self.btn_photorec, self.TOOLTIP_TEXTS["photorec_start"]),
        ])
