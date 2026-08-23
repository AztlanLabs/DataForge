"""
System Cleanup & Optimization GUI view.

Provides junk file scanning, browser artifact detection, and cleanup
with preview-confirm-execute workflow following BaseView patterns.
"""
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QCheckBox, QSpinBox, QSplitter, QGroupBox, QGridLayout,
    QLineEdit, QTabWidget
)
from PyQt5.QtCore import Qt

from ..theme_tokens import TYPE_SCALE

from .base import BaseView
from .. import dialogs
from ...core.config import config
from ..widgets import EnhancedTreeview, CollapsibleCard, attach_tooltips, FilePreviewPanel
from ...core.utils import format_size
from ...core.services import FileActionService
from ...modules.system_cleanup import (
    scan_junk_files,
    scan_browser_artifacts,
    estimate_cleanup_savings,
    estimate_browser_savings,
)


class SystemCleanupView(BaseView):
    TOOLTIP_TEXTS = {
        "scan_path": "Optionally add extra folders to include in the junk-file scan alongside standard system paths.",
        "min_age": "Only include files older than this many days. Use 0 to include all files regardless of age.",
        "scan_junk": "Scan system directories for temporary files, caches, logs, and other reclaimable storage.",
        "scan_browser": "Detect browser tracking artifacts: cookies, history databases, cache directories, and session data.",
        "select_all": "Select all items in the results tree for cleanup.",
        "deselect_all": "Clear the current selection without removing any files.",
        "clean_selected": "Delete the selected junk files. Uses Safe Mode (Trash) if enabled in Settings.",
        "category_filter": "Toggle specific junk categories to include or exclude from the scan.",
    }

    def get_title(self):
        return "Clean Up Space"

    def __init__(self, master, app=None):
        super().__init__(master, app)
        self.junk_results = {}
        self.browser_results = {}
        self.item_entries = {}  # tree item_id -> FileEntry

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Tabs: Junk Files | Browser Privacy
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, 1)

        # ===== Tab 1: Junk File Cleanup =====
        junk_tab = QWidget()
        junk_layout = QVBoxLayout(junk_tab)
        junk_layout.setContentsMargins(5, 5, 5, 5)

        # Scan Configuration Card
        self.card_scan = CollapsibleCard(junk_tab, title="Scan Configuration")
        junk_layout.addWidget(self.card_scan)

        c_body = self.card_scan.get_body()
        c_body_layout = QVBoxLayout(c_body)
        c_body_layout.setContentsMargins(0, 5, 0, 0)
        c_body_layout.setSpacing(6)

        # Extra path input
        path_frame = QWidget(c_body)
        path_layout = QHBoxLayout(path_frame)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.addWidget(QLabel("Extra Path:"))
        self.entry_path = QLineEdit(path_frame)
        self.entry_path.setPlaceholderText("(Optional) Additional folder to scan...")
        path_layout.addWidget(self.entry_path)
        self.btn_browse = QPushButton("Browse", path_frame)
        self.btn_browse.clicked.connect(self._browse_path)
        path_layout.addWidget(self.btn_browse)
        c_body_layout.addWidget(path_frame)

        # Options row
        opts_frame = QWidget(c_body)
        opts_layout = QHBoxLayout(opts_frame)
        opts_layout.setContentsMargins(0, 0, 0, 0)
        opts_layout.addWidget(QLabel("Min Age (days):"))
        self.spin_age = QSpinBox(opts_frame)
        self.spin_age.setRange(0, 3650)
        self.spin_age.setValue(0)
        opts_layout.addWidget(self.spin_age)
        opts_layout.addStretch()
        c_body_layout.addWidget(opts_frame)

        # Category checkboxes
        cat_group = QGroupBox("Categories to Scan", c_body)
        cat_grid = QGridLayout(cat_group)
        self.category_checks = {}
        categories = ["System Temp", "User Cache", "Thumbnails", "Trash", "Log Files", "Package Cache", "Crash Reports"]
        for i, cat in enumerate(categories):
            chk = QCheckBox(cat, cat_group)
            chk.setChecked(True)
            cat_grid.addWidget(chk, i // 3, i % 3)
            self.category_checks[cat] = chk
        c_body_layout.addWidget(cat_group)

        # TICK-807 — include browser checkbox (remembered via ui_checkbox_states)
        self.chk_include_browser = QCheckBox("Include browser artifacts", c_body)
        self.chk_include_browser.setChecked(False)
        self.chk_include_browser.setToolTip("When checked, junk scan also includes browser cache/cookies (stored in ui_checkbox_states).")
        c_body_layout.addWidget(self.chk_include_browser)

        # Scan button in header
        self.btn_scan = self.card_scan.add_widget_to_header(
            QPushButton, text="SCAN JUNK",
        )
        self.btn_scan.setProperty("variant", "warning")
        self.btn_scan.clicked.connect(self._start_junk_scan)

        # Summary label
        self.lbl_junk_summary = QLabel("No junk scan run yet.", c_body)
        self.lbl_junk_summary.setProperty("class", "muted")
        self.lbl_junk_summary.setWordWrap(True)
        c_body_layout.addWidget(self.lbl_junk_summary)

        # Savings display
        self.savings_frame = QFrame(junk_tab)
        self.savings_frame.setFrameShape(QFrame.StyledPanel)
        savings_layout = QHBoxLayout(self.savings_frame)
        savings_layout.setContentsMargins(10, 8, 10, 8)

        self.lbl_total_savings = QLabel("Reclaimable: —")
        self.lbl_total_savings.setProperty("variant", "success")
        self.lbl_total_savings.setStyleSheet(f"font-size: {TYPE_SCALE['heading']}px; font-weight: bold;")
        savings_layout.addWidget(self.lbl_total_savings)

        self.lbl_file_count = QLabel("Files: —")
        self.lbl_file_count.setProperty("class", "muted")
        self.lbl_file_count.setStyleSheet(f"font-size: {TYPE_SCALE['subheading']}px;")
        savings_layout.addWidget(self.lbl_file_count)
        savings_layout.addStretch()
        junk_layout.addWidget(self.savings_frame)

        # Results tree & Preview Splitter
        self.junk_splitter = QSplitter(Qt.Horizontal, junk_tab)
        
        self.junk_tree = EnhancedTreeview(self.junk_splitter, columns=("type", "category", "path", "size"), app=self.app)
        self.junk_tree.heading("type", text="Type")
        self.junk_tree.column("type", width=60, stretch=False)
        self.junk_tree.heading("category", text="Category")
        self.junk_tree.column("category", width=120, stretch=False)
        self.junk_tree.heading("path", text="File Path")
        self.junk_tree.heading("size", text="Size")
        self.junk_tree.column("size", width=80, stretch=False)
        
        self.junk_tree.tree.itemSelectionChanged.connect(self._on_junk_selection_changed)
        self.junk_splitter.addWidget(self.junk_tree)
        
        self.junk_preview = FilePreviewPanel(self.junk_splitter)
        self.junk_splitter.addWidget(self.junk_preview)
        self.junk_splitter.setSizes([600, 300])
        
        junk_layout.addWidget(self.junk_splitter, 1)

        # Action buttons
        action_frame = QWidget(junk_tab)
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(0, 5, 0, 0)

        self.btn_select_all = QPushButton("Select All", action_frame)
        self.btn_select_all.clicked.connect(self._select_all_junk)
        action_layout.addWidget(self.btn_select_all)

        self.btn_deselect = QPushButton("Deselect All", action_frame)
        self.btn_deselect.clicked.connect(self._deselect_all_junk)
        action_layout.addWidget(self.btn_deselect)

        self.btn_clean = QPushButton("🗑 Clean Selected", action_frame)
        self.btn_clean.setProperty("variant", "danger")
        self.btn_clean.clicked.connect(self._clean_selected)
        action_layout.addWidget(self.btn_clean)

        action_layout.addStretch()

        self.lbl_action_status = QLabel("Scan for junk files to begin cleanup.", action_frame)
        self.lbl_action_status.setProperty("class", "muted")
        action_layout.addWidget(self.lbl_action_status)
        junk_layout.addWidget(action_frame)

        self.tabs.addTab(junk_tab, "🧹 Junk Files")

        # ===== Tab 2: Browser Privacy =====
        browser_tab = QWidget()
        browser_layout = QVBoxLayout(browser_tab)
        browser_layout.setContentsMargins(5, 5, 5, 5)

        # Browser scan card
        self.card_browser = CollapsibleCard(browser_tab, title="Browser Privacy Scanner")
        browser_layout.addWidget(self.card_browser)

        b_body = self.card_browser.get_body()
        b_body_layout = QVBoxLayout(b_body)
        b_body_layout.setContentsMargins(0, 5, 0, 0)

        self.lbl_browser_summary = QLabel("Scan to detect browser tracking artifacts.", b_body)
        self.lbl_browser_summary.setProperty("class", "muted")
        self.lbl_browser_summary.setWordWrap(True)
        b_body_layout.addWidget(self.lbl_browser_summary)

        self.btn_browser_scan = self.card_browser.add_widget_to_header(
            QPushButton, text="SCAN BROWSERS",
        )
        self.btn_browser_scan.setProperty("variant", "primary")
        self.btn_browser_scan.clicked.connect(self._start_browser_scan)

        # Browser savings
        self.browser_savings_frame = QFrame(browser_tab)
        self.browser_savings_frame.setFrameShape(QFrame.StyledPanel)
        bsav_layout = QHBoxLayout(self.browser_savings_frame)
        bsav_layout.setContentsMargins(10, 8, 10, 8)
        self.lbl_browser_savings = QLabel("Browser artifacts: —")
        self.lbl_browser_savings.setProperty("variant", "primary")
        self.lbl_browser_savings.setStyleSheet(f"font-size: {TYPE_SCALE['heading']}px; font-weight: bold;")
        bsav_layout.addWidget(self.lbl_browser_savings)
        bsav_layout.addStretch()
        browser_layout.addWidget(self.browser_savings_frame)

        # Browser results tree & Preview Splitter
        self.browser_splitter = QSplitter(Qt.Horizontal, browser_tab)
        
        self.browser_tree = EnhancedTreeview(
            self.browser_splitter, columns=("type", "browser", "artifact", "path"), app=self.app
        )
        self.browser_tree.heading("type", text="Type")
        self.browser_tree.column("type", width=60, stretch=False)
        self.browser_tree.heading("browser", text="Browser")
        self.browser_tree.column("browser", width=120, stretch=False)
        self.browser_tree.heading("artifact", text="Artifact Type")
        self.browser_tree.column("artifact", width=110, stretch=False)
        self.browser_tree.heading("path", text="Path")
        
        self.browser_tree.tree.itemSelectionChanged.connect(self._on_browser_selection_changed)
        self.browser_splitter.addWidget(self.browser_tree)
        
        self.browser_preview = FilePreviewPanel(self.browser_splitter)
        self.browser_splitter.addWidget(self.browser_preview)
        self.browser_splitter.setSizes([600, 300])
        
        browser_layout.addWidget(self.browser_splitter, 1)

        self.tabs.addTab(browser_tab, "🔒 Browser Privacy")

        self._init_tooltips()
        # TICK-807 — restore UI memory after widgets exist
        self._load_ui_memory()
        self._connect_ui_memory_signals()

    # ------------------------------------------------------------------
    # TICK-807 — UI memory (persisted via config, not transient)
    # ------------------------------------------------------------------
    def mount(self):
        super().mount()
        self._load_ui_memory()

    def _load_ui_memory(self):
        """Restore checkbox/selection/tab/path state from config (persisted)."""
        try:
            # ui_last_paths: view -> path
            last_paths = config.get("ui_last_paths", {}) or {}
            if isinstance(last_paths, dict):
                p = last_paths.get("system_cleanup") or last_paths.get("system_cleanup.extra_path") or ""
                if isinstance(p, str) and p:
                    # block signals to avoid saving during restore
                    self.entry_path.blockSignals(True)
                    self.entry_path.setText(p)
                    self.entry_path.blockSignals(False)
            # ui_filter_names: e.g., min_age
            filter_names = config.get("ui_filter_names", {}) or {}
            if isinstance(filter_names, dict):
                v = filter_names.get("system_cleanup.min_age")
                if isinstance(v, str) and v.isdigit():
                    try:
                        self.spin_age.blockSignals(True)
                        self.spin_age.setValue(int(v))
                        self.spin_age.blockSignals(False)
                    except Exception:
                        pass
                # also handle int directly if stored as int
                fv = filter_names.get("system_cleanup.min_age_int")
                if isinstance(fv, int):
                    try:
                        self.spin_age.blockSignals(True)
                        self.spin_age.setValue(fv)
                        self.spin_age.blockSignals(False)
                    except Exception:
                        pass
            # direct int storage for spin
            checkbox_states = config.get("ui_checkbox_states", {}) or {}
            if isinstance(checkbox_states, dict):
                # include_browser
                if "system_cleanup.include_browser" in checkbox_states:
                    v = checkbox_states["system_cleanup.include_browser"]
                    if isinstance(v, bool):
                        self.chk_include_browser.blockSignals(True)
                        self.chk_include_browser.setChecked(v)
                        self.chk_include_browser.blockSignals(False)
                # categories
                for cat, chk in self.category_checks.items():
                    key = f"system_cleanup.category.{cat}"
                    if key in checkbox_states and isinstance(checkbox_states[key], bool):
                        chk.blockSignals(True)
                        chk.setChecked(checkbox_states[key])
                        chk.blockSignals(False)
                # tab index (stored as int in checkbox_states or window_geometry)
                tab_key = "system_cleanup.tab_index"
                if tab_key in checkbox_states and isinstance(checkbox_states[tab_key], int):
                    idx = checkbox_states[tab_key]
                    if 0 <= idx < self.tabs.count():
                        self.tabs.blockSignals(True)
                        self.tabs.setCurrentIndex(idx)
                        self.tabs.blockSignals(False)
            # window_geometry may also hold tab index
            geom = config.get("window_geometry", {}) or {}
            if isinstance(geom, dict) and "system_cleanup.tab_index" in geom:
                idx = geom["system_cleanup.tab_index"]
                if isinstance(idx, int) and 0 <= idx < self.tabs.count():
                    self.tabs.blockSignals(True)
                    self.tabs.setCurrentIndex(idx)
                    self.tabs.blockSignals(False)
            # spin_age also stored directly as int under ui_checkbox_states or window_geometry
            if isinstance(checkbox_states, dict) and "system_cleanup.min_age" in checkbox_states:
                v = checkbox_states["system_cleanup.min_age"]
                if isinstance(v, int):
                    self.spin_age.blockSignals(True)
                    self.spin_age.setValue(v)
                    self.spin_age.blockSignals(False)
        except Exception:
            pass

    def _connect_ui_memory_signals(self):
        """Connect widget changes to config persistence (transient progress not saved)."""
        try:
            self.entry_path.textChanged.connect(self._on_extra_path_changed)
            self.spin_age.valueChanged.connect(self._on_min_age_changed)
            self.chk_include_browser.stateChanged.connect(self._on_include_browser_changed)
            for cat, chk in self.category_checks.items():
                # capture cat
                chk.stateChanged.connect(lambda _v, c=cat: self._on_category_changed(c))
            self.tabs.currentChanged.connect(self._on_tab_changed)
        except Exception:
            pass

    def _on_extra_path_changed(self, text):
        try:
            last = config.get("ui_last_paths", {}) or {}
            if not isinstance(last, dict):
                last = {}
            last["system_cleanup"] = str(text or "")
            # also store filter name for entry
            filters = config.get("ui_filter_names", {}) or {}
            if not isinstance(filters, dict):
                filters = {}
            filters["system_cleanup.extra_path"] = str(text or "")
            config.set("ui_last_paths", last)
            config.set("ui_filter_names", filters)
        except Exception:
            pass

    def _on_min_age_changed(self, value):
        try:
            # store as filter and checkbox state (both are valid persisted locations)
            filters = config.get("ui_filter_names", {}) or {}
            if not isinstance(filters, dict):
                filters = {}
            filters["system_cleanup.min_age"] = str(value)
            config.set("ui_filter_names", filters)
            # also store int in checkbox_states for easy retrieval
            cbs = config.get("ui_checkbox_states", {}) or {}
            if not isinstance(cbs, dict):
                cbs = {}
            cbs["system_cleanup.min_age"] = int(value)
            config.set("ui_checkbox_states", cbs)
        except Exception:
            pass

    def _on_include_browser_changed(self, _state):
        try:
            cbs = config.get("ui_checkbox_states", {}) or {}
            if not isinstance(cbs, dict):
                cbs = {}
            cbs["system_cleanup.include_browser"] = bool(self.chk_include_browser.isChecked())
            config.set("ui_checkbox_states", cbs)
        except Exception:
            pass

    def _on_category_changed(self, cat):
        try:
            cbs = config.get("ui_checkbox_states", {}) or {}
            if not isinstance(cbs, dict):
                cbs = {}
            chk = self.category_checks.get(cat)
            if chk is not None:
                cbs[f"system_cleanup.category.{cat}"] = bool(chk.isChecked())
                config.set("ui_checkbox_states", cbs)
        except Exception:
            pass

    def _on_tab_changed(self, index):
        try:
            cbs = config.get("ui_checkbox_states", {}) or {}
            if not isinstance(cbs, dict):
                cbs = {}
            cbs["system_cleanup.tab_index"] = int(index)
            config.set("ui_checkbox_states", cbs)
            geom = config.get("window_geometry", {}) or {}
            if not isinstance(geom, dict):
                geom = {}
            geom["system_cleanup.tab_index"] = int(index)
            config.set("window_geometry", geom)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Junk scan
    # ------------------------------------------------------------------

    def _browse_path(self):
        path = dialogs.get_existing_directory(self, "Select Extra Folder to Scan")
        if path:
            self.entry_path.setText(path)

    def _start_junk_scan(self):
        # TICK-905: debounce — disable button while scanning, ignore rapid 3x clicks
        try:
            if not self.btn_scan.isEnabled():
                return
        except Exception:
            pass
        selected_cats = [name for name, chk in self.category_checks.items() if chk.isChecked()]
        if not selected_cats:
            self.app.show_warning_dialog("No Categories", "Select at least one junk category to scan.")
            return

        extra_path = self.entry_path.text().strip()
        extra_paths = [extra_path] if extra_path and os.path.isdir(extra_path) else None

        self.junk_results = {}
        self.item_entries = {}
        # TICK-905: clear with updates disabled to avoid repaint during mount/crossfade
        try:
            self.junk_tree.tree.setUpdatesEnabled(False)
            self.junk_tree.tree.clear()
            self.junk_tree.item_map.clear()
        finally:
            try:
                self.junk_tree.tree.setUpdatesEnabled(True)
            except Exception:
                pass
            try:
                self.junk_tree.refresh_viewport()
            except Exception:
                pass
        self.lbl_junk_summary.setText("Scanning for junk files...")
        self.lbl_total_savings.setText("Reclaimable: scanning...")
        self.lbl_file_count.setText("Files: scanning...")
        self.app.update_status("Scanning for junk files...")
        try:
            self.btn_scan.setEnabled(False)
            self.btn_scan.setText("SCANNING...")
        except Exception:
            pass

        self.app.run_workflow(
            scan_junk_files,
            self._on_junk_scan_complete,
            extra_paths,
            selected_cats,
            False,
            self.spin_age.value(),
            progress=True,
            error_title="Junk Scan Failed",
            on_error=self._on_junk_scan_error,
        )

    def _on_junk_scan_error(self, error):
        # TICK-905: re-enable button on error/cancel path
        try:
            self.btn_scan.setEnabled(True)
            self.btn_scan.setText("SCAN JUNK")
        except Exception:
            pass
        try:
            # Delegate to app's default error handler
            self.app.show_workflow_error("Junk Scan Failed", error)
        except Exception:
            try:
                self.app.show_error_dialog("Junk Scan Failed", str(error))
            except Exception:
                pass

    def _on_junk_scan_complete(self, results):
        # TICK-905: always re-enable scan button (success or empty)
        try:
            self.btn_scan.setEnabled(True)
            self.btn_scan.setText("SCAN JUNK")
        except Exception:
            pass
        # Handle cancellation dicts from worker
        if isinstance(results, dict) and results.get("cancelled"):
            self.lbl_junk_summary.setText("Scan cancelled.")
            self.lbl_total_savings.setText("Reclaimable: —")
            self.lbl_file_count.setText("Files: —")
            self.lbl_action_status.setText("Scan cancelled.")
            try:
                self.app.update_status("Junk scan cancelled.")
            except Exception:
                pass
            return
        self.junk_results = results if isinstance(results, dict) else {}

        if not results:
            self.lbl_junk_summary.setText("No junk files found. Your system looks clean!")
            self.lbl_total_savings.setText("Reclaimable: 0 B")
            self.lbl_file_count.setText("Files: 0")
            self.lbl_action_status.setText("No junk files to clean up.")
            self.app.update_status("Junk scan complete — no files found.")
            return

        savings = estimate_cleanup_savings(results)
        self.lbl_total_savings.setText(f"Reclaimable: {savings['formatted_total']}")
        self.lbl_file_count.setText(f"Files: {savings['total_files']}")

        # Category breakdown summary
        parts = []
        for cat, info in savings["categories"].items():
            parts.append(f"{cat}: {info['count']} files ({info['formatted_size']})")
        self.lbl_junk_summary.setText(" | ".join(parts))

        # Build tree
        self._rebuild_junk_tree()

        self.lbl_action_status.setText("Select files and click Clean to remove them.")
        self.app.update_status(
            f"Found {savings['total_files']} junk files ({savings['formatted_total']} reclaimable)."
        )

    def _rebuild_junk_tree(self):
        # TICK-905: harden bulk insert — disable updates + sorting, refresh viewport deferred
        try:
            self.junk_tree.tree.setSortingEnabled(False)
        except Exception:
            pass
        try:
            self.junk_tree.tree.setUpdatesEnabled(False)
        except Exception:
            pass
        try:
            self.junk_tree.tree.clear()
            self.junk_tree.item_map.clear()
            self.item_entries = {}

            for category, entries in self.junk_results.items():
                total_size = sum(e.size for e in entries)
                group_id = self.junk_tree.insert(
                    "", "end",
                    values=("GROUP", category, f"{len(entries)} files", format_size(total_size)),
                    open=False,
                )
                for entry in entries:
                    item_id = self.junk_tree.insert(
                        group_id, "end",
                        values=(entry.extension, category, entry.path, format_size(entry.size)),
                    )
                    self.item_entries[item_id] = entry
        finally:
            try:
                self.junk_tree.tree.setUpdatesEnabled(True)
            except Exception:
                pass
            try:
                self.junk_tree.tree.setSortingEnabled(True)
            except Exception:
                pass
            try:
                self.junk_tree.refresh_viewport()
            except Exception:
                try:
                    from PyQt5.QtCore import QTimer
                    QTimer.singleShot(0, lambda: self.junk_tree.tree.viewport().update())
                except Exception:
                    pass

    def _on_junk_selection_changed(self):
        sel = self.junk_tree.selection()
        if not sel:
            self.junk_preview.clear()
            return
        item_id = sel[0]
        entry = self.item_entries.get(item_id)
        if entry and os.path.exists(entry.path):
            self.junk_preview.update_file(entry.path)
        else:
            self.junk_preview.clear()

    def _on_browser_selection_changed(self):
        sel = self.browser_tree.selection()
        if not sel:
            self.browser_preview.clear()
            return
        item_id = sel[0]
        item = self.browser_tree.item(item_id)
        vals = item.get('values', [])
        if not vals or len(vals) < 4:
            self.browser_preview.clear()
            return
        type_val = vals[0]
        path_val = vals[3]
        if type_val not in ("BROWSER", "TYPE") and path_val and os.path.exists(path_val):
            self.browser_preview.update_file(path_val)
        else:
            self.browser_preview.clear()

    def _select_all_junk(self):
        all_ids = list(self.item_entries.keys())
        if all_ids:
            self.junk_tree.selection_set(all_ids)
            self.lbl_action_status.setText(f"Selected {len(all_ids)} files.")

    def _deselect_all_junk(self):
        self.junk_tree.tree.clearSelection()
        self.lbl_action_status.setText("Selection cleared.")

    def _clean_selected(self):
        selected = self.junk_tree.selection()
        targets = []
        for item_id in selected:
            entry = self.item_entries.get(item_id)
            if entry and os.path.exists(entry.path):
                targets.append({
                    "item_id": item_id,
                    "entry": entry,
                    "source_path": entry.path,
                })

        if not targets:
            self.app.show_warning_dialog("Nothing Selected", "Select junk files to clean first.")
            return

        self.app.run_workflow(
            self._preview_clean_worker,
            self._on_preview_clean_complete,
            targets,
            progress=True,
            error_title="Cleanup Preview Failed",
        )

    def _preview_clean_worker(self, targets, progress_callback=None, cancel_token=None):
        outcome = FileActionService.delete_items(
            targets,
            dry_run=True,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=lambda t: t["source_path"],
        )
        return {"cancelled": outcome.cancelled, "records": outcome.records}

    def _on_preview_clean_complete(self, outcome):
        previews = outcome["records"]
        lines = [r.message for r in previews]
        total_size = sum(r.item["entry"].size for r in previews if r.item.get("entry"))
        summary = f"Clean {len(previews)} junk files ({format_size(total_size)})"

        if not self.handle_preview_outcome(
            cancelled=outcome.get("cancelled"),
            records=previews,
            title="Confirm Cleanup",
            summary=summary,
            lines=lines,
            action_label=f"delete {len(previews)} junk files",
            summary_var=self.lbl_action_status,
            ready_text=f"Ready: {len(previews)} files for cleanup",
            cancelled_summary="Cleanup cancelled.",
            cancelled_status="Cleanup cancelled",
            empty_message="No junk files available for cleanup.",
            empty_summary="No junk files to clean.",
            declined_summary="Cleanup declined.",
            declined_status="Cleanup declined",
        ):
            return

        self.app.run_workflow(
            self._execute_clean_worker,
            self._on_execute_clean_complete,
            previews,
            progress=True,
            error_title="Cleanup Failed",
        )

    def _execute_clean_worker(self, previews, progress_callback=None, cancel_token=None):
        targets = [r.item for r in previews]
        outcome = FileActionService.delete_items(
            targets,
            dry_run=False,
            progress_callback=progress_callback,
            cancel_token=cancel_token,
            path_getter=lambda t: t["source_path"],
        )
        return {
            "cancelled": outcome.cancelled,
            "successes": outcome.successes,
            "failures": outcome.failures,
        }

    def _on_execute_clean_complete(self, outcome):
        successes = outcome.get("successes", [])

        # Remove cleaned items from results
        cleaned_paths = {r.item["source_path"] for r in successes}
        for category in list(self.junk_results.keys()):
            self.junk_results[category] = [
                e for e in self.junk_results[category] if e.path not in cleaned_paths
            ]
            if not self.junk_results[category]:
                del self.junk_results[category]

        self._rebuild_junk_tree()

        # Update savings display
        if self.junk_results:
            savings = estimate_cleanup_savings(self.junk_results)
            self.lbl_total_savings.setText(f"Reclaimable: {savings['formatted_total']}")
            self.lbl_file_count.setText(f"Files: {savings['total_files']}")
        else:
            self.lbl_total_savings.setText("Reclaimable: 0 B")
            self.lbl_file_count.setText("Files: 0")

        self.present_batch_outcome(
            outcome,
            stopped_label="Cleanup stopped.",
            complete_label="Cleanup complete.",
            summary_var=self.lbl_action_status,
            summary_text="Cleaned: {success} | Failed: {failed}",
            cancelled_status="Cleanup cancelled ({success} cleaned, {failed} failed)",
            complete_status="Cleanup complete ({success} cleaned, {failed} failed)",
        )

    # ------------------------------------------------------------------
    # Browser scan
    # ------------------------------------------------------------------

    def _start_browser_scan(self):
        self.browser_results = {}
        self.browser_tree.tree.clear()
        self.browser_tree.item_map.clear()
        self.lbl_browser_summary.setText("Scanning browsers...")
        self.app.update_status("Scanning browser artifacts...")

        self.app.run_workflow(
            scan_browser_artifacts,
            self._on_browser_scan_complete,
            progress=True,
            error_title="Browser Scan Failed",
        )

    def _on_browser_scan_complete(self, results):
        self.browser_results = results

        if not results:
            self.lbl_browser_summary.setText("No browser artifacts detected.")
            self.lbl_browser_savings.setText("Browser artifacts: 0 B")
            self.app.update_status("Browser scan complete — no artifacts found.")
            return

        savings = estimate_browser_savings(results)
        self.lbl_browser_savings.setText(f"Browser artifacts: {savings['formatted_total']}")

        # Build browser tree
        self.browser_tree.tree.clear()
        self.browser_tree.item_map.clear()

        for browser, artifacts in results.items():
            browser_id = self.browser_tree.insert(
                "", "end",
                values=("BROWSER", browser, "", ""),
                open=True,
            )
            for artifact_type, paths in artifacts.items():
                type_id = self.browser_tree.insert(
                    browser_id, "end",
                    values=("TYPE", browser, artifact_type, f"{len(paths)} item(s)"),
                )
                for p in paths:
                    self.browser_tree.insert(
                        type_id, "end",
                        values=("", browser, artifact_type, p),
                    )

        browser_names = ", ".join(results.keys())
        self.lbl_browser_summary.setText(f"Detected artifacts in: {browser_names}")
        self.app.update_status(f"Found browser artifacts in {len(results)} browser(s).")

    # ------------------------------------------------------------------
    # Tooltips
    # ------------------------------------------------------------------

    def _init_tooltips(self):
        attach_tooltips([
            (self.entry_path, self.TOOLTIP_TEXTS["scan_path"]),
            (self.spin_age, self.TOOLTIP_TEXTS["min_age"]),
            (self.btn_scan, self.TOOLTIP_TEXTS["scan_junk"]),
            (self.btn_browser_scan, self.TOOLTIP_TEXTS["scan_browser"]),
            (self.btn_select_all, self.TOOLTIP_TEXTS["select_all"]),
            (self.btn_deselect, self.TOOLTIP_TEXTS["deselect_all"]),
            (self.btn_clean, self.TOOLTIP_TEXTS["clean_selected"]),
        ])
