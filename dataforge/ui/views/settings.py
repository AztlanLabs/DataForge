from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QSpinBox, QPushButton, QLineEdit, QListWidget, QTabWidget, QGroupBox, QMessageBox
)
from PyQt5.QtCore import QTimer
from .base import BaseView
from .. import dialogs
from ...core.config import config
from ...core.logger import logger
from ...core.cache import file_cache
from ...modules.duplicates import KEEP_STRATEGIES
from ..widgets import attach_tooltips

class SettingsView(BaseView):
    TIER_ORDER = ["Simple", "Standard", "Everything"]

    TOOLTIP_TEXTS = {
        "settings_tier": "Choose how much of the UI you see. Simple keeps only the most common controls; Standard unlocks additional performance and search settings; Everything reveals every advanced control and panel (incl. hardware diagnostics, full metadata, and forensic options).",
        "duplicate_default_keep_strategy": "The keep strategy pre-selected for new duplicate scans and the Action Builder's Duplicate filter.",
        "hash_algorithm": "Choose the digest used by duplicate detection and cached hashes. Stronger hashes trade speed for collision safety.",
        "max_threads": "Controls parallel hashing/batch work (duplicate scanning, forensic hash manifests, integrity snapshots, metadata batch reads). Set to 1 to run this work single-threaded; raise it for faster disks/CPUs.",
        "search_threads": "Controls parallel keyword search and content-scanning work, independent of the hashing thread budget above.",
        "path_display_mode": "Full always shows the complete path. Relative shows paths relative to each view's scan/source folder, which is shorter and easier to scan when browsing deep folder trees.",
        "excluded_folders": "Comma-separated folder names to skip everywhere, such as build output or dependency caches.",
        "excluded_extensions": "Comma-separated file extensions to skip during scans, for example .tmp or .log.",
        "dashboard_paths": "These folders feed the dashboard overview and quick statistics cards.",
        "dashboard_add": "Add another folder to the dashboard watch list.",
        "dashboard_remove": "Remove the currently selected dashboard folder from the list.",
    }

    def get_title(self):
        return "Settings"

    def __init__(self, master, app=None):
        super().__init__(master, app)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        self._tiered_widgets = []
        self._suppress_autosave = False
        self._saved_indicator = QLabel("", self)
        self._saved_indicator.setProperty("variant", "success")
        self._saved_indicator.setVisible(False)
        self._saved_timer = QTimer(self)
        self._saved_timer.setSingleShot(True)
        self._saved_timer.timeout.connect(self._hide_saved_indicator)

        tier_row = QWidget(self)
        tier_layout = QHBoxLayout(tier_row)
        tier_layout.setContentsMargins(0, 0, 0, 5)
        tier_layout.addWidget(QLabel("Detail level:", tier_row))
        self.cb_tier = QComboBox(tier_row)
        self.cb_tier.addItems(self.TIER_ORDER)
        self.cb_tier.setCurrentText(config.get("settings_ui_tier", "Simple"))
        self.cb_tier.currentTextChanged.connect(self.apply_tier)
        tier_layout.addWidget(self.cb_tier)
        tier_layout.addStretch()
        tier_layout.addWidget(self._saved_indicator)
        self.main_layout.addWidget(tier_row)
        attach_tooltips([(self.cb_tier, self.TOOLTIP_TEXTS["settings_tier"])])

        self.nb = QTabWidget(self)
        self.main_layout.addWidget(self.nb)
        
        # --- Tab 1: General (Appearance & Safety) ---
        self.tab_gen = QWidget()
        gen_layout = QVBoxLayout(self.tab_gen)
        gen_layout.setContentsMargins(10, 10, 10, 10)
        gen_layout.setSpacing(15)
        self.nb.addTab(self.tab_gen, "General")
        
        # Appearance
        frame_theme = QGroupBox("Appearance", self.tab_gen)
        frame_theme_layout = QVBoxLayout(frame_theme)

        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Theme:", frame_theme))
        self.lbl_theme = QLabel("", frame_theme)
        self.lbl_theme.setProperty("variant", "primary")
        theme_layout.addWidget(self.lbl_theme)
        theme_hint = QLabel("  (change in the sidebar)", frame_theme)
        theme_hint.setProperty("variant", "muted")
        theme_layout.addWidget(theme_hint)
        theme_layout.addStretch()
        frame_theme_layout.addLayout(theme_layout)
        if getattr(self, "app", None) and hasattr(self.app, "theme_chk"):
            self.app.theme_chk.stateChanged.connect(self._sync_theme_label)
            self._sync_theme_label(self.app.theme_chk.checkState())
        else:
            self.lbl_theme.setText("Light (Cosmo)")

        path_display_layout = QHBoxLayout()
        path_display_layout.addWidget(QLabel("Path Display:", frame_theme))
        self.cb_path_display = QComboBox(frame_theme)
        self.cb_path_display.addItems(["Full", "Relative"])
        self.cb_path_display.setCurrentText(config.get("path_display_mode", "full").capitalize())
        self.cb_path_display.currentTextChanged.connect(
            lambda text: self._autosave("path_display_mode", text.lower())
        )
        path_display_layout.addWidget(self.cb_path_display)
        path_display_layout.addStretch()
        frame_theme_layout.addLayout(path_display_layout)
        attach_tooltips([(self.cb_path_display, self.TOOLTIP_TEXTS["path_display_mode"])])

        gen_layout.addWidget(frame_theme)

        # Safety & System
        frame_safe = QGroupBox("Safety & System", self.tab_gen)
        safe_layout = QVBoxLayout(frame_safe)
        
        self.chk_safe = QCheckBox("Enable Safe Mode (Trash)", frame_safe)
        self.chk_safe.setChecked(config.get("safe_mode", True))
        self.chk_safe.stateChanged.connect(self.save_safe)
        safe_layout.addWidget(self.chk_safe)
        
        r2 = QWidget(frame_safe)
        r2_layout = QHBoxLayout(r2)
        r2_layout.setContentsMargins(0, 0, 0, 0)
        r2_layout.addWidget(QLabel("Log Level:", r2))
        self.cb_log = QComboBox(r2)
        self.cb_log.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.cb_log.setCurrentText(config.get("log_level", "INFO"))
        self.cb_log.currentTextChanged.connect(self.save_safe)
        r2_layout.addWidget(self.cb_log)
        r2_layout.addStretch()

        safe_layout.addWidget(r2)
        self.register_tiered(r2, "Standard")
        gen_layout.addWidget(frame_safe)

        # Defaults
        frame_defaults = QGroupBox("Defaults", self.tab_gen)
        defaults_layout = QHBoxLayout(frame_defaults)
        defaults_layout.addWidget(QLabel("Default Duplicate Keep Strategy:", frame_defaults))
        self.cb_dup_strategy = QComboBox(frame_defaults)
        self.cb_dup_strategy.addItems(list(KEEP_STRATEGIES))
        self.cb_dup_strategy.setCurrentText(config.get("duplicate_default_keep_strategy", "first path"))
        self.cb_dup_strategy.currentTextChanged.connect(
            lambda text: self._autosave("duplicate_default_keep_strategy", text)
        )
        defaults_layout.addWidget(self.cb_dup_strategy)
        defaults_layout.addStretch()
        gen_layout.addWidget(frame_defaults)
        attach_tooltips([(self.cb_dup_strategy, self.TOOLTIP_TEXTS["duplicate_default_keep_strategy"])])

        gen_layout.addStretch()

        # --- Tab 2: Performance ---
        self.tab_perf = QWidget()
        perf_layout = QVBoxLayout(self.tab_perf)
        perf_layout.setContentsMargins(10, 10, 10, 10)
        self.nb.addTab(self.tab_perf, "Performance")

        row_hash = QWidget(self.tab_perf)
        row_hash_layout = QHBoxLayout(row_hash)
        row_hash_layout.setContentsMargins(0, 0, 0, 0)
        row_hash_layout.addWidget(QLabel("Hash Algorithm:", row_hash))
        self.hash_algo_combo = QComboBox(row_hash)
        self.hash_algo_combo.addItems(["md5", "sha1", "sha256", "sha512"])
        self.hash_algo_combo.setCurrentText(config.get("hash_algorithm", "md5"))
        self.hash_algo_combo.currentTextChanged.connect(
            lambda text: self._autosave("hash_algorithm", text)
        )
        row_hash_layout.addWidget(self.hash_algo_combo)
        row_hash_layout.addStretch()
        perf_layout.addWidget(row_hash)

        row_unit = QWidget(self.tab_perf)
        row_unit_layout = QHBoxLayout(row_unit)
        row_unit_layout.setContentsMargins(0, 0, 0, 0)
        row_unit_layout.addWidget(QLabel("Size Unit:", row_unit))
        self.cb_unit = QComboBox(row_unit)
        self.cb_unit.addItems(["Auto", "Bytes", "KB", "MB", "GB"])
        self.cb_unit.setCurrentText(config.get("size_unit", "Auto"))
        self.cb_unit.currentTextChanged.connect(
            lambda text: self._autosave("size_unit", text)
        )
        row_unit_layout.addWidget(self.cb_unit)
        row_unit_layout.addStretch()
        perf_layout.addWidget(row_unit)
        self.register_tiered(row_unit, "Standard")

        row_threads = QWidget(self.tab_perf)
        row_threads_layout = QHBoxLayout(row_threads)
        row_threads_layout.setContentsMargins(0, 0, 0, 0)
        row_threads_layout.addWidget(QLabel("Hashing/Batch Threads:", row_threads))
        self.max_threads_spinbox = QSpinBox(row_threads)
        self.max_threads_spinbox.setRange(1, 32)
        self.max_threads_spinbox.setValue(config.get("max_thread_workers", 4))
        self.max_threads_spinbox.valueChanged.connect(
            lambda value: self._autosave("max_thread_workers", value)
        )
        row_threads_layout.addWidget(self.max_threads_spinbox)
        row_threads_layout.addStretch()
        perf_layout.addWidget(row_threads)
        self.register_tiered(row_threads, "Standard")

        row_search_threads = QWidget(self.tab_perf)
        row_search_threads_layout = QHBoxLayout(row_search_threads)
        row_search_threads_layout.setContentsMargins(0, 0, 0, 0)
        row_search_threads_layout.addWidget(QLabel("Search Threads:", row_search_threads))
        self.search_threads_spinbox = QSpinBox(row_search_threads)
        self.search_threads_spinbox.setRange(1, 32)
        self.search_threads_spinbox.setValue(config.get("search_thread_workers", 4))
        self.search_threads_spinbox.valueChanged.connect(
            lambda value: self._autosave("search_thread_workers", value)
        )
        row_search_threads_layout.addWidget(self.search_threads_spinbox)
        row_search_threads_layout.addStretch()
        perf_layout.addWidget(row_search_threads)
        self.register_tiered(row_search_threads, "Standard")

        row_cache = QWidget(self.tab_perf)
        row_cache_layout = QHBoxLayout(row_cache)
        row_cache_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_clear_cache = QPushButton("Clear Cache DB", row_cache)
        self.btn_clear_cache.clicked.connect(self.clear_cache_db)
        self.btn_clear_cache.setProperty("variant", "danger")
        row_cache_layout.addWidget(self.btn_clear_cache)
        row_cache_layout.addStretch()
        perf_layout.addWidget(row_cache)
        self.register_tiered(row_cache, "Everything")

        perf_layout.addStretch(1)

        self._init_performance_tooltips()

        # --- Tab 3: Exclusions ---
        self.tab_excl = QWidget()
        excl_layout = QVBoxLayout(self.tab_excl)
        excl_layout.setContentsMargins(10, 10, 10, 10)
        self.nb.addTab(self.tab_excl, "Exclusions")
        self._excl_tab_index = self.nb.indexOf(self.tab_excl)
        
        excl_layout.addWidget(QLabel("Excluded Folders (comma separated):"))
        self.excl_folders_entry = QLineEdit(self.tab_excl)
        self.excl_folders_entry.setText(",".join(config.get("excluded_folders", [])))
        self.excl_folders_entry.editingFinished.connect(self._save_excluded_folders)
        excl_layout.addWidget(self.excl_folders_entry)

        excl_layout.addWidget(QLabel("Excluded Extensions (comma separated):"))
        self.excl_ext_entry = QLineEdit(self.tab_excl)
        self.excl_ext_entry.setText(",".join(config.get("excluded_extensions", [])))
        self.excl_ext_entry.editingFinished.connect(self._save_excluded_extensions)
        excl_layout.addWidget(self.excl_ext_entry)

        excl_layout.addStretch()
        self._init_exclusion_tooltips()

        # --- Tab 4: Dashboard ---
        self.tab_dash = QWidget()
        dash_layout = QVBoxLayout(self.tab_dash)
        dash_layout.setContentsMargins(10, 10, 10, 10)
        self.nb.addTab(self.tab_dash, "Dashboard")
        
        dash_layout.addWidget(QLabel("Scan Locations:"))
        
        self.dash_list = QListWidget(self.tab_dash)
        dash_layout.addWidget(self.dash_list, 1)
        
        d_btns = QWidget(self.tab_dash)
        d_btns_layout = QHBoxLayout(d_btns)
        d_btns_layout.setContentsMargins(0, 0, 0, 0)

        self.dash_add_button = QPushButton("Add Folder", d_btns)
        self.dash_add_button.clicked.connect(self.add_dash_path)
        d_btns_layout.addWidget(self.dash_add_button)

        self.dash_remove_button = QPushButton("Remove Selected", d_btns)
        self.dash_remove_button.clicked.connect(self.remove_dash_path)
        d_btns_layout.addWidget(self.dash_remove_button)

        d_btns_layout.addStretch()

        dash_layout.addWidget(d_btns)
        self._init_dashboard_tooltips()

        # Load dashboard paths
        dpaths = config.get("dashboard_paths", [])
        if isinstance(dpaths, list):
            for dp in dpaths:
                self.dash_list.addItem(dp)

        self.apply_tier(self.cb_tier.currentText())

    def register_tiered(self, widget, min_tier):
        self._tiered_widgets.append((widget, min_tier))

    def apply_tier(self, tier_name):
        rank = self.TIER_ORDER.index(tier_name)
        for widget, min_tier in self._tiered_widgets:
            widget.setVisible(self.TIER_ORDER.index(min_tier) <= rank)
        if hasattr(self, "_excl_tab_index"):
            self.nb.setTabVisible(self._excl_tab_index, rank >= self.TIER_ORDER.index("Standard"))
        config.set("settings_ui_tier", tier_name)
        # Tier now controls in-view complexity (advanced controls stay
        # hidden behind tiered rows and the Exclusions tab), NOT the
        # sidebar. The sidebar shows every group regardless of tier so
        # users can always discover what DataForge can do.
        if getattr(self, "app", None) and hasattr(self.app, "update_sidebar_experience"):
            self.app.update_sidebar_experience()

    def _sync_theme_label(self, _state=None):
        """Mirror the sidebar Dark Mode checkbox as a read-only label.

        The previous design had a second QComboBox here that also wrote to
        config — when the user changed the theme, both the sidebar and the
        Settings dropdown fought over the same key and the dropdown was
        always one click out of sync. The sidebar checkbox is now the only
        writable control; this label reflects its state for visibility."""
        if not getattr(self, "lbl_theme", None):
            return
        is_dark = bool(self.app.theme_chk.isChecked()) if getattr(self, "app", None) else False
        self.lbl_theme.setText("Dark (Darkly)" if is_dark else "Light (Cosmo)")

    def _autosave(self, key, value):
        """Persist a single setting and flash a transient 'Saved ✓' indicator.

        The previous design forced the user to click one of three ad-hoc Save
        buttons (Save Performance / Save Exclusions / Save Dashboard) and then
        dismiss a modal confirmation dialog. That hid whether the change had
        actually taken effect and required two interactions to use. Every
        setting now persists the moment it changes; the indicator gives
        unobtrusive feedback instead of an interrupting dialog."""
        if self._suppress_autosave:
            return
        config.set(key, value)
        logger.debug("Setting autosaved: %s=%r", key, value)
        self._flash_saved_indicator()

    def _save_excluded_folders(self):
        folders = [f.strip() for f in self.excl_folders_entry.text().split(',') if f.strip()]
        self._autosave("excluded_folders", folders)

    def _save_excluded_extensions(self):
        exts = [e.strip() for e in self.excl_ext_entry.text().split(',') if e.strip()]
        self._autosave("excluded_extensions", exts)

    def _flash_saved_indicator(self, duration_ms=1500):
        self._saved_indicator.setText("Saved ✓")
        self._saved_indicator.setVisible(True)
        self._saved_timer.start(duration_ms)

    def _hide_saved_indicator(self):
        self._saved_indicator.setVisible(False)
        self._saved_indicator.setText("")

    def save_safe(self, event=None):
        config.set("safe_mode", self.chk_safe.isChecked())
        config.set("log_level", self.cb_log.currentText())
        self._flash_saved_indicator()

    def clear_cache_db(self):
        reply = QMessageBox.question(
            self,
            "Confirm",
            "Are you sure you want to clear the file cache? This will force scanning of all files again.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            file_cache.clear()
            self.app.show_info_dialog("Success", "Cache cleared.")

    def add_dash_path(self):
        path = dialogs.get_existing_directory(self, "Select Folder to Watch")
        if path:
            existing = [self.dash_list.item(i).text() for i in range(self.dash_list.count())]
            if path not in existing:
                self.dash_list.addItem(path)
                paths = [self.dash_list.item(i).text() for i in range(self.dash_list.count())]
                self._autosave("dashboard_paths", paths)

    def remove_dash_path(self):
        selected_items = self.dash_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            self.dash_list.takeItem(self.dash_list.row(item))
        paths = [self.dash_list.item(i).text() for i in range(self.dash_list.count())]
        self._autosave("dashboard_paths", paths)

    def _init_performance_tooltips(self):
        self._performance_tooltips = attach_tooltips([
            (self.hash_algo_combo, self.TOOLTIP_TEXTS["hash_algorithm"]),
            (self.max_threads_spinbox, self.TOOLTIP_TEXTS["max_threads"]),
            (self.search_threads_spinbox, self.TOOLTIP_TEXTS["search_threads"]),
        ])

    def _init_exclusion_tooltips(self):
        self._exclusion_tooltips = attach_tooltips([
            (self.excl_folders_entry, self.TOOLTIP_TEXTS["excluded_folders"]),
            (self.excl_ext_entry, self.TOOLTIP_TEXTS["excluded_extensions"]),
        ])

    def _init_dashboard_tooltips(self):
        self._dashboard_tooltips = attach_tooltips([
            (self.dash_list, self.TOOLTIP_TEXTS["dashboard_paths"]),
            (self.dash_add_button, self.TOOLTIP_TEXTS["dashboard_add"]),
            (self.dash_remove_button, self.TOOLTIP_TEXTS["dashboard_remove"]),
        ])
