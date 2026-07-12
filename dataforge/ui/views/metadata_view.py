"""
Metadata Studio GUI view.

Three-panel interface for reading, inspecting, editing, and stripping
metadata across 180+ file formats with GPS and timestamp visualization.
"""
import os
import json

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox, QTabWidget, QSplitter, QTextEdit,
    QLineEdit, QMessageBox
)
from PyQt5.QtCore import Qt

from .base import BaseView
from ..theme_tokens import TYPE_SCALE
from .. import dialogs
from ..widgets import EnhancedTreeview, FilePreviewPanel, CollapsibleCard, attach_tooltips
from ...core.scanner import scan_directory
from ...modules.metadata import MetadataEngine
from ...modules.search import export_result_rows


class MetadataView(BaseView):
    TOOLTIP_TEXTS = {
        "scan_path": "Choose a file or folder to scan for metadata. Subfolders are included up to the specified depth.",
        "ext_filter": "Comma-separated file extensions to scan (e.g., .jpg,.png,.pdf). Leave empty for all files.",
        "depth": "Maximum subdirectory depth for scanning. -1 scans the full tree.",
        "scan_btn": "Scan for files and read their metadata. This may take time for large directories.",
        "read_selected": "Read full metadata for the selected file in the results tree.",
        "strip_selected": "Strip all metadata from the selected file(s). Follows preview-confirm-execute.",
        "strip_gps": "Strip only GPS/location data from the selected file(s).",
        "edit_field": "Edit a specific metadata field. Enter field name and new value.",
        "export_meta": "Export metadata report for all scanned files as CSV or JSON.",
    }

    def get_title(self):
        return "Metadata Studio"

    def __init__(self, master, app=None):
        super().__init__(master, app)
        self.scanned_metadata = []  # list of metadata dicts
        self.item_metadata_map = {}  # tree item_id -> metadata dict

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Scan configuration card
        self.card_config = CollapsibleCard(self, title="File Scanner")
        layout.addWidget(self.card_config)

        c_body = self.card_config.get_body()
        c_layout = QVBoxLayout(c_body)
        c_layout.setContentsMargins(0, 5, 0, 0)
        c_layout.setSpacing(6)

        # Path row
        path_frame = QWidget(c_body)
        path_layout = QHBoxLayout(path_frame)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.addWidget(QLabel("Path:"))
        self.entry_path = QLineEdit(path_frame)
        self.entry_path.setPlaceholderText("/path/to/files or a single file")
        path_layout.addWidget(self.entry_path)
        self.btn_browse = QPushButton("Browse", path_frame)
        self.btn_browse.clicked.connect(self._browse)
        path_layout.addWidget(self.btn_browse)
        c_layout.addWidget(path_frame)

        # Options row
        opt_frame = QWidget(c_body)
        opt_layout = QHBoxLayout(opt_frame)
        opt_layout.setContentsMargins(0, 0, 0, 0)
        opt_layout.addWidget(QLabel("Extensions:"))
        self.entry_ext = QLineEdit(opt_frame)
        self.entry_ext.setPlaceholderText(".jpg,.png,.pdf,.mp3")
        self.entry_ext.setMaximumWidth(200)
        opt_layout.addWidget(self.entry_ext)
        opt_layout.addWidget(QLabel("Depth:"))
        from PyQt5.QtWidgets import QSpinBox
        self.spin_depth = QSpinBox(opt_frame)
        self.spin_depth.setRange(-1, 999)
        self.spin_depth.setValue(-1)
        opt_layout.addWidget(self.spin_depth)
        opt_layout.addStretch()
        c_layout.addWidget(opt_frame)

        # Scan button in header
        self.btn_scan = self.card_config.add_widget_to_header(
            QPushButton, text="SCAN METADATA",
        )
        self.btn_scan.setProperty("variant", "primary")
        self.btn_scan.setStyleSheet("font-weight: bold;")
        self.btn_scan.clicked.connect(self._start_scan)

        self.lbl_scan_summary = QLabel("No metadata scan run yet.", c_body)
        self.lbl_scan_summary.setProperty("class", "muted")
        self.lbl_scan_summary.setWordWrap(True)
        c_layout.addWidget(self.lbl_scan_summary)

        # Format support info
        formats = MetadataEngine.get_supported_formats()
        support_parts = []
        for cat, info in formats.items():
            if cat == "all_exiftool":
                continue
            read = "✅" if info.get("read") else "❌"
            write = "✅" if info.get("write") else "❌"
            support_parts.append(f"{cat.title()}: R{read} W{write}")
        has_exiftool = formats.get("all_exiftool", {}).get("available", False)
        exiftool_str = "✅ ExifTool (180+ formats)" if has_exiftool else "❌ ExifTool not installed"
        support_text = f"Format support: {' | '.join(support_parts)} | {exiftool_str}"
        lbl_support = QLabel(support_text, c_body)
        lbl_support.setProperty("class", "muted")
        lbl_support.setStyleSheet(f"font-size: {TYPE_SCALE['caption']}px;")
        lbl_support.setWordWrap(True)
        c_layout.addWidget(lbl_support)

        # Main splitter
        self.splitter = QSplitter(Qt.Horizontal, self)
        layout.addWidget(self.splitter, 1)

        # Left: File results tree
        left_widget = QWidget(self.splitter)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.file_tree = EnhancedTreeview(
            left_widget,
            columns=("filename", "extension", "size", "handler", "has_meta", "has_gps"),
            app=self.app,
        )
        self.file_tree.heading("filename", text="Filename")
        self.file_tree.heading("extension", text="Ext")
        self.file_tree.column("extension", width=50, stretch=False)
        self.file_tree.heading("size", text="Size")
        self.file_tree.column("size", width=70, stretch=False)
        self.file_tree.heading("handler", text="Handler")
        self.file_tree.column("handler", width=70, stretch=False)
        self.file_tree.heading("has_meta", text="Metadata")
        self.file_tree.column("has_meta", width=70, stretch=False)
        self.file_tree.heading("has_gps", text="GPS")
        self.file_tree.column("has_gps", width=50, stretch=False)
        self.file_tree.tree.itemSelectionChanged.connect(self._on_file_select)
        left_layout.addWidget(self.file_tree)
        self.splitter.addWidget(left_widget)

        # Right: Metadata inspector tabs
        right_widget = QWidget(self.splitter)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.detail_tabs = QTabWidget(right_widget)
        right_layout.addWidget(self.detail_tabs)

        # Tab: Overview
        overview_tab = QWidget()
        ov_layout = QVBoxLayout(overview_tab)
        ov_layout.setContentsMargins(0, 0, 0, 0)
        # Vertical splitter so users can see the metadata field/value table
        # on top and a live content preview of the selected file below.
        self.overview_splitter = QSplitter(Qt.Vertical, overview_tab)
        ov_layout.addWidget(self.overview_splitter, 1)

        self.overview_tree = EnhancedTreeview(
            overview_tab, columns=("field", "value"), app=self.app,
        )
        self.overview_tree.heading("field", text="Field")
        self.overview_tree.column("field", width=180, stretch=False)
        self.overview_tree.heading("value", text="Value")
        self.overview_splitter.addWidget(self.overview_tree)

        self.overview_preview = FilePreviewPanel(overview_tab)
        self.overview_splitter.addWidget(self.overview_preview)
        self.overview_splitter.setSizes([320, 240])
        self.detail_tabs.addTab(overview_tab, "📋 Overview")

        # Tab: Raw JSON
        raw_tab = QWidget()
        raw_layout = QVBoxLayout(raw_tab)
        self.raw_text = QTextEdit(raw_tab)
        self.raw_text.setReadOnly(True)
        self.raw_text.setStyleSheet(f"font-family: 'Courier New', Consolas, monospace; font-size: {TYPE_SCALE['body']}px;")
        raw_layout.addWidget(self.raw_text)
        self.detail_tabs.addTab(raw_tab, "{ } Raw Data")

        # Tab: GPS
        gps_tab = QWidget()
        gps_layout = QVBoxLayout(gps_tab)
        self.lbl_gps = QLabel("Select a file with GPS data to view coordinates.", gps_tab)
        self.lbl_gps.setStyleSheet(f"font-size: {TYPE_SCALE['subheading']}px; padding: 20px;")
        self.lbl_gps.setAlignment(Qt.AlignCenter)
        self.lbl_gps.setWordWrap(True)
        gps_layout.addWidget(self.lbl_gps)
        self.detail_tabs.addTab(gps_tab, "📍 GPS")

        # Tab: Timestamps
        ts_tab = QWidget()
        ts_layout = QVBoxLayout(ts_tab)
        self.ts_tree = EnhancedTreeview(
            ts_tab, columns=("source", "timestamp"), app=self.app,
        )
        self.ts_tree.heading("source", text="Source")
        self.ts_tree.column("source", width=200, stretch=False)
        self.ts_tree.heading("timestamp", text="Date/Time")
        ts_layout.addWidget(self.ts_tree)
        self.detail_tabs.addTab(ts_tab, "🕐 Timestamps")

        self.splitter.addWidget(right_widget)
        self.splitter.setSizes([500, 500])

        # Action toolbar
        action_frame = QGroupBox("Metadata Actions", self)
        action_layout = QHBoxLayout(action_frame)

        self.btn_strip_all = QPushButton("🗑 Strip All Metadata", action_frame)
        self.btn_strip_all.setProperty("variant", "danger")
        self.btn_strip_all.clicked.connect(self._strip_selected)
        action_layout.addWidget(self.btn_strip_all)

        self.btn_strip_gps = QPushButton("📍 Strip GPS Only", action_frame)
        self.btn_strip_gps.clicked.connect(self._strip_gps_selected)
        action_layout.addWidget(self.btn_strip_gps)

        # Edit field
        action_layout.addWidget(QLabel("Edit:"))
        self.edit_field = QLineEdit(action_frame)
        self.edit_field.setPlaceholderText("Field name")
        self.edit_field.setMaximumWidth(120)
        action_layout.addWidget(self.edit_field)
        self.edit_value = QLineEdit(action_frame)
        self.edit_value.setPlaceholderText("New value")
        self.edit_value.setMaximumWidth(150)
        action_layout.addWidget(self.edit_value)
        self.btn_edit = QPushButton("✏️ Write", action_frame)
        self.btn_edit.clicked.connect(self._write_field)
        action_layout.addWidget(self.btn_edit)

        # Export
        self.btn_export = QPushButton("💾 Export Report", action_frame)
        self.btn_export.clicked.connect(self._export_metadata)
        action_layout.addWidget(self.btn_export)

        action_layout.addStretch()
        self.lbl_action_status = QLabel("", action_frame)
        self.lbl_action_status.setProperty("class", "muted")
        action_layout.addWidget(self.lbl_action_status)

        layout.addWidget(action_frame)

        self._init_tooltips()

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def _browse(self):
        path = self.choose_file_or_directory(
            file_title="Select File for Metadata",
            directory_title="Select Folder to Scan",
        )
        if path:
            self.entry_path.setText(path)

    def _start_scan(self):
        path = self.entry_path.text().strip()
        if not path:
            self.app.show_warning_dialog("No Path", "Enter a file or folder path to scan.")
            return

        self.scanned_metadata = []
        self.item_metadata_map = {}
        self.file_tree.tree.clear()
        self.file_tree.item_map.clear()
        self.lbl_scan_summary.setText("Scanning for metadata...")
        self.app.update_status("Scanning for metadata...")

        ext_str = self.entry_ext.text().strip()
        depth = self.spin_depth.value()

        self.app.run_workflow(
            self._scan_worker,
            self._on_scan_complete,
            path, ext_str, depth,
            progress=True,
            error_title="Metadata Scan Failed",
        )

    def _scan_worker(self, path, ext_str, depth, progress_callback=None, cancel_token=None):
        """Scan files and read metadata."""
        # Collect file paths
        paths = []

        if os.path.isfile(path):
            paths = [path]
        elif os.path.isdir(path):
            # Use search module for filtering
            for entry in scan_directory(path, recursive=True, max_depth=depth, cancel_token=cancel_token):
                if entry.is_dir:
                    continue
                if ext_str:
                    exts = [e.strip().lower() for e in ext_str.split(",") if e.strip()]
                    exts = [e if e.startswith(".") else f".{e}" for e in exts]
                    if entry.extension.lower() not in exts:
                        continue
                paths.append(entry.path)

        if progress_callback:
            progress_callback(0, len(paths), f"Reading metadata from {len(paths)} files...")

        # Read metadata
        results = MetadataEngine.read_metadata_batch(
            paths, progress_callback=progress_callback, cancel_token=cancel_token,
        )

        return results

    def _on_scan_complete(self, results):
        self.scanned_metadata = results

        if not results:
            self.lbl_scan_summary.setText("No files found matching criteria.")
            self.app.update_status("Metadata scan complete — no files found.")
            return

        # Count stats
        with_meta = sum(1 for r in results if r.get("fields"))
        with_gps = sum(1 for r in results if r.get("has_gps"))
        handlers = {}
        for r in results:
            h = r.get("handler", "unknown")
            handlers[h] = handlers.get(h, 0) + 1

        handler_str = ", ".join(f"{k}: {v}" for k, v in handlers.items())
        self.lbl_scan_summary.setText(
            f"Scanned {len(results)} files | With metadata: {with_meta} | "
            f"With GPS: {with_gps} | Handlers: {handler_str}"
        )

        # Build file tree
        self.file_tree.tree.clear()
        self.file_tree.item_map.clear()
        self.item_metadata_map = {}

        for meta in results:
            has_meta = "Yes" if meta.get("fields") else "No"
            has_gps = "📍" if meta.get("has_gps") else ""

            item_id = self.file_tree.insert("", "end", values=(
                meta.get("filename", ""),
                meta.get("extension", ""),
                meta.get("formatted_size", ""),
                meta.get("handler", "—"),
                has_meta,
                has_gps,
            ))
            self.item_metadata_map[item_id] = meta

        self.app.update_status(
            f"Metadata scan complete: {len(results)} files, {with_meta} with metadata, {with_gps} with GPS."
        )

    # ------------------------------------------------------------------
    # Detail display
    # ------------------------------------------------------------------

    def _on_file_select(self):
        selection = self.file_tree.selection()
        if not selection:
            self.overview_preview.clear()
            return

        meta = self.item_metadata_map.get(selection[0])
        if not meta:
            self.overview_preview.clear()
            return

        self._display_overview(meta)
        self._display_raw(meta)
        self._display_gps(meta)
        self._display_timestamps(meta)

        if hasattr(self, "overview_preview"):
            path = meta.get("path") or ""
            if path and os.path.exists(path):
                self.overview_preview.update_file(path)
            else:
                self.overview_preview.clear()

    def _display_overview(self, meta):
        self.overview_tree.tree.clear()
        self.overview_tree.item_map.clear()

        # File info
        self.overview_tree.insert("", "end", values=("File", meta.get("filename", "")))
        self.overview_tree.insert("", "end", values=("Size", meta.get("formatted_size", "")))
        self.overview_tree.insert("", "end", values=("Handler", meta.get("handler", "")))
        self.overview_tree.insert("", "end", values=("Has GPS", "Yes" if meta.get("has_gps") else "No"))

        # Image info
        img_info = meta.get("image_info", {})
        if img_info:
            self.overview_tree.insert("", "end", values=("—", "— Image Info —"))
            for key, value in img_info.items():
                self.overview_tree.insert("", "end", values=(key.title(), str(value)))

        # Audio info
        audio_info = meta.get("audio_info", {})
        if audio_info:
            self.overview_tree.insert("", "end", values=("—", "— Audio Info —"))
            for key, value in audio_info.items():
                if value is not None:
                    self.overview_tree.insert("", "end", values=(key.replace("_", " ").title(), str(value)))

        # Metadata fields (top 50)
        fields = meta.get("fields", {})
        if fields:
            self.overview_tree.insert("", "end", values=("—", f"— Metadata ({len(fields)} fields) —"))
            for key, value in list(fields.items())[:50]:
                display_val = str(value)[:200]
                self.overview_tree.insert("", "end", values=(key, display_val))

    def _display_raw(self, meta):
        try:
            raw = json.dumps(meta, indent=2, default=str, ensure_ascii=False)
        except Exception:
            raw = str(meta)
        self.raw_text.setPlainText(raw)

    def _display_gps(self, meta):
        gps = meta.get("gps")
        if gps and gps.get("latitude") is not None:
            lat = gps["latitude"]
            lon = gps["longitude"]
            alt = gps.get("altitude")
            alt_str = f"\nAltitude: {alt:.1f}m" if alt else ""
            self.lbl_gps.setText(
                f"📍 GPS Coordinates Found\n\n"
                f"Latitude: {lat:.6f}\n"
                f"Longitude: {lon:.6f}"
                f"{alt_str}\n\n"
                f"Google Maps: https://maps.google.com/?q={lat},{lon}\n"
                f"OpenStreetMap: https://www.openstreetmap.org/?mlat={lat}&mlon={lon}"
            )
        else:
            self.lbl_gps.setText("No GPS data found in this file.")

    def _display_timestamps(self, meta):
        self.ts_tree.tree.clear()
        self.ts_tree.item_map.clear()

        timestamps = meta.get("timestamps", {})
        if timestamps:
            for source, ts in timestamps.items():
                self.ts_tree.insert("", "end", values=(source, str(ts)))
        else:
            self.ts_tree.insert("", "end", values=("—", "No timestamp data found"))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _get_selected_paths(self):
        selection = self.file_tree.selection()
        paths = []
        for iid in selection:
            meta = self.item_metadata_map.get(iid)
            if meta and meta.get("path"):
                paths.append(meta["path"])
        return paths

    def _strip_selected(self):
        paths = self._get_selected_paths()
        if not paths:
            self.app.show_warning_dialog("No Selection", "Select files to strip metadata from.")
            return

        summary = f"Strip all metadata from {len(paths)} file(s)?"
        lines = [f"  {os.path.basename(p)}" for p in paths[:8]]
        if len(paths) > 8:
            lines.append(f"  ... and {len(paths) - 8} more")

        if not self.confirm_preview("Confirm Strip", summary, lines, f"strip metadata from {len(paths)} files"):
            return

        self.app.run_workflow(
            self._strip_worker,
            self._on_strip_complete,
            paths, None,
            progress=True,
            error_title="Metadata Strip Failed",
        )

    def _strip_gps_selected(self):
        paths = self._get_selected_paths()
        if not paths:
            self.app.show_warning_dialog("No Selection", "Select files to strip GPS data from.")
            return

        if not self.confirm_preview(
            "Confirm GPS Strip",
            f"Strip GPS/location data from {len(paths)} file(s)?",
            [os.path.basename(p) for p in paths[:5]],
            f"strip GPS from {len(paths)} files",
        ):
            return

        gps_fields = [
            "GPSLatitude", "GPSLongitude", "GPSAltitude",
            "GPSLatitudeRef", "GPSLongitudeRef", "GPSAltitudeRef",
            "GPSTimeStamp", "GPSDateStamp", "GPSVersionID",
        ]

        self.app.run_workflow(
            self._strip_worker,
            self._on_strip_complete,
            paths, gps_fields,
            progress=True,
            error_title="GPS Strip Failed",
        )

    def _strip_worker(self, paths, fields=None, progress_callback=None, cancel_token=None):
        results = []
        total = len(paths)
        for idx, path in enumerate(paths):
            if cancel_token and cancel_token.is_set():
                break
            if progress_callback:
                progress_callback(idx, total, f"Stripping: {os.path.basename(path)}")
            result = MetadataEngine.remove_metadata(path, fields=fields, dry_run=False)
            result["path"] = path
            results.append(result)
        if progress_callback:
            progress_callback(total, total, "Strip complete")
        return results

    def _on_strip_complete(self, results):
        success = sum(1 for r in results if r.get("success"))
        failed = len(results) - success
        self.lbl_action_status.setText(f"Stripped: {success} | Failed: {failed}")
        self.app.update_status(f"Metadata strip complete: {success} succeeded, {failed} failed.")

        if failed:
            errors = [r.get("message", "") for r in results if not r.get("success")][:5]
            self.app.show_warning_dialog("Partial Success", f"Stripped {success}, failed {failed}:\n" + "\n".join(errors))
        else:
            self.app.show_info_dialog("Strip Complete", f"Metadata stripped from {success} file(s).")

    def _write_field(self):
        paths = self._get_selected_paths()
        field_name = self.edit_field.text().strip()
        field_value = self.edit_value.text().strip()

        if not paths:
            self.app.show_warning_dialog("No Selection", "Select a file to edit.")
            return
        if not field_name:
            self.app.show_warning_dialog("No Field", "Enter a metadata field name.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Edit",
            f"Set '{field_name}' = '{field_value}' on {len(paths)} file(s)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.app.run_workflow(
            self._write_worker,
            self._on_write_complete,
            paths, {field_name: field_value},
            error_title="Metadata Write Failed",
        )

    def _write_worker(self, paths, fields, progress_callback=None, cancel_token=None):
        results = []
        for path in paths:
            if cancel_token and cancel_token.is_set():
                break
            result = MetadataEngine.write_metadata(path, fields, dry_run=False)
            result["path"] = path
            results.append(result)
        return results

    def _on_write_complete(self, results):
        success = sum(1 for r in results if r.get("success"))
        self.lbl_action_status.setText(f"Written: {success} / {len(results)}")
        self.app.update_status(f"Metadata write complete: {success} succeeded.")

    def _export_metadata(self):
        if not self.scanned_metadata:
            self.app.show_warning_dialog("Nothing to Export", "Run a metadata scan first.")
            return

        dest, _ = dialogs.get_save_file_name(
            self, "Export Metadata Report", "",
            "JSON Files (*.json);;CSV Files (*.csv);;All Files (*)",
        )
        if not dest:
            return

        try:
            fmt = "json" if dest.endswith(".json") else "csv"

            # Build export rows
            rows = []
            for meta in self.scanned_metadata:
                row = {
                    "path": meta.get("path", ""),
                    "filename": meta.get("filename", ""),
                    "extension": meta.get("extension", ""),
                    "size": meta.get("size", 0),
                    "handler": meta.get("handler", ""),
                    "has_gps": meta.get("has_gps", False),
                    "field_count": len(meta.get("fields", {})),
                }
                # Add GPS
                gps = meta.get("gps")
                if gps:
                    row["gps_latitude"] = gps.get("latitude")
                    row["gps_longitude"] = gps.get("longitude")
                rows.append(row)

            export_result_rows(rows, dest, format=fmt)

            self.app.update_status(f"Exported {len(rows)} metadata records to {dest}")
            self.lbl_action_status.setText(f"Exported {len(rows)} records as {fmt.upper()}.")
        except Exception as exc:
            self.app.show_error_dialog("Export Failed", str(exc))

    # ------------------------------------------------------------------
    # Tooltips
    # ------------------------------------------------------------------

    def _init_tooltips(self):
        attach_tooltips([
            (self.entry_path, self.TOOLTIP_TEXTS["scan_path"]),
            (self.entry_ext, self.TOOLTIP_TEXTS["ext_filter"]),
            (self.spin_depth, self.TOOLTIP_TEXTS["depth"]),
            (self.btn_scan, self.TOOLTIP_TEXTS["scan_btn"]),
            (self.btn_strip_all, self.TOOLTIP_TEXTS["strip_selected"]),
            (self.btn_strip_gps, self.TOOLTIP_TEXTS["strip_gps"]),
            (self.btn_edit, self.TOOLTIP_TEXTS["edit_field"]),
            (self.btn_export, self.TOOLTIP_TEXTS["export_meta"]),
        ])
