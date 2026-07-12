from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QSpinBox, QPushButton, QLineEdit, QListWidget, QTabWidget, QGroupBox, QMessageBox
)
from .base import BaseView
from .. import dialogs
from ...core.config import config
from ...core.logger import logger
from ...core.cache import file_cache
from ...modules.duplicates import KEEP_STRATEGIES
from ..widgets import attach_tooltips

class SettingsView(BaseView):
    TIER_ORDER = ["Basic", "Advanced", "Expert"]

    TOOLTIP_TEXTS = {
        "settings_tier": "Choose how much of the UI you see. Basic hides rarely-needed options AND the System Maintenance / Advanced Analysis sidebar groups; Advanced unlocks System Maintenance; Expert reveals everything (incl. Metadata Studio, Hardware Diagnostics, Forensics Lab).",
        "duplicate_default_keep_strategy": "The keep strategy pre-selected for new duplicate scans and the Action Builder's Duplicate filter.",
        "hash_algorithm": "Choose the digest used by duplicate detection and cached hashes. Stronger hashes trade speed for collision safety.",
        "max_threads": "Controls parallel hashing/batch work (duplicate scanning, forensic hash manifests, integrity snapshots, metadata batch reads). Set to 1 to run this work single-threaded; raise it for faster disks/CPUs.",
        "search_threads": "Controls parallel keyword search and content-scanning work, independent of the hashing thread budget above.",
        "path_display_mode": "Full always shows the complete path. Relative shows paths relative to each view's scan/source folder, which is shorter and easier to scan when browsing deep folder trees.",
        "save_performance": "Persist the current hashing, size-unit, and worker settings for future scans.",
        "excluded_folders": "Comma-separated folder names to skip everywhere, such as build output or dependency caches.",
        "excluded_extensions": "Comma-separated file extensions to skip during scans, for example .tmp or .log.",
        "save_exclusions": "Save the current exclusion lists so search, duplicates, and dashboard scans all honor them.",
        "dashboard_paths": "These folders feed the dashboard overview and quick statistics cards.",
        "dashboard_add": "Add another folder to the dashboard watch list.",
        "dashboard_remove": "Remove the currently selected dashboard folder from the list.",
        "dashboard_save": "Persist the dashboard watch list so it is restored on the next launch.",
    }

    def get_title(self):
        return "Settings"

    def __init__(self, master, app=None):
        super().__init__(master, app)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        self._tiered_widgets = []

        tier_row = QWidget(self)
        tier_layout = QHBoxLayout(tier_row)
        tier_layout.setContentsMargins(0, 0, 0, 5)
        tier_layout.addWidget(QLabel("Experience Level:", tier_row))
        self.cb_tier = QComboBox(tier_row)
        self.cb_tier.addItems(self.TIER_ORDER)
        self.cb_tier.setCurrentText(config.get("settings_ui_tier", "Basic"))
        self.cb_tier.currentTextChanged.connect(self.apply_tier)
        tier_layout.addWidget(self.cb_tier)
        tier_layout.addStretch()
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
        self.cb_theme = QComboBox(frame_theme)
        self.cb_theme.addItems(["Light (Cosmo)", "Dark (Darkly)"])
        current_theme = config.get("theme", "cosmo")
        if current_theme == "darkly":
            self.cb_theme.setCurrentIndex(1)
        else:
            self.cb_theme.setCurrentIndex(0)
        self.cb_theme.currentTextChanged.connect(self.change_theme)
        theme_layout.addWidget(self.cb_theme)
        theme_layout.addStretch()
        frame_theme_layout.addLayout(theme_layout)

        path_display_layout = QHBoxLayout()
        path_display_layout.addWidget(QLabel("Path Display:", frame_theme))
        self.cb_path_display = QComboBox(frame_theme)
        self.cb_path_display.addItems(["Full", "Relative"])
        self.cb_path_display.setCurrentText(config.get("path_display_mode", "full").capitalize())
        self.cb_path_display.currentTextChanged.connect(
            lambda text: config.set("path_display_mode", text.lower())
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
        self.register_tiered(r2, "Advanced")
        gen_layout.addWidget(frame_safe)

        # Defaults
        frame_defaults = QGroupBox("Defaults", self.tab_gen)
        defaults_layout = QHBoxLayout(frame_defaults)
        defaults_layout.addWidget(QLabel("Default Duplicate Keep Strategy:", frame_defaults))
        self.cb_dup_strategy = QComboBox(frame_defaults)
        self.cb_dup_strategy.addItems(list(KEEP_STRATEGIES))
        self.cb_dup_strategy.setCurrentText(config.get("duplicate_default_keep_strategy", "first path"))
        self.cb_dup_strategy.currentTextChanged.connect(
            lambda text: config.set("duplicate_default_keep_strategy", text)
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
        row_unit_layout.addWidget(self.cb_unit)
        row_unit_layout.addStretch()
        perf_layout.addWidget(row_unit)
        self.register_tiered(row_unit, "Advanced")

        row_threads = QWidget(self.tab_perf)
        row_threads_layout = QHBoxLayout(row_threads)
        row_threads_layout.setContentsMargins(0, 0, 0, 0)
        row_threads_layout.addWidget(QLabel("Hashing/Batch Threads:", row_threads))
        self.max_threads_spinbox = QSpinBox(row_threads)
        self.max_threads_spinbox.setRange(1, 32)
        self.max_threads_spinbox.setValue(config.get("max_thread_workers", 4))
        row_threads_layout.addWidget(self.max_threads_spinbox)
        row_threads_layout.addStretch()
        perf_layout.addWidget(row_threads)
        self.register_tiered(row_threads, "Advanced")

        row_search_threads = QWidget(self.tab_perf)
        row_search_threads_layout = QHBoxLayout(row_search_threads)
        row_search_threads_layout.setContentsMargins(0, 0, 0, 0)
        row_search_threads_layout.addWidget(QLabel("Search Threads:", row_search_threads))
        self.search_threads_spinbox = QSpinBox(row_search_threads)
        self.search_threads_spinbox.setRange(1, 32)
        self.search_threads_spinbox.setValue(config.get("search_thread_workers", 4))
        row_search_threads_layout.addWidget(self.search_threads_spinbox)
        row_search_threads_layout.addStretch()
        perf_layout.addWidget(row_search_threads)
        self.register_tiered(row_search_threads, "Advanced")

        row_save = QWidget(self.tab_perf)
        row_save_layout = QHBoxLayout(row_save)
        row_save_layout.setContentsMargins(0, 0, 0, 0)
        self.save_perf_button = QPushButton("Save Performance", row_save)
        self.save_perf_button.clicked.connect(self.save_perf)
        row_save_layout.addWidget(self.save_perf_button)
        row_save_layout.addStretch()
        perf_layout.addWidget(row_save)

        row_cache = QWidget(self.tab_perf)
        row_cache_layout = QHBoxLayout(row_cache)
        row_cache_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_clear_cache = QPushButton("Clear Cache DB", row_cache)
        self.btn_clear_cache.clicked.connect(self.clear_cache_db)
        self.btn_clear_cache.setProperty("variant", "danger")
        row_cache_layout.addWidget(self.btn_clear_cache)
        row_cache_layout.addStretch()
        perf_layout.addWidget(row_cache)
        self.register_tiered(row_cache, "Expert")

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
        excl_layout.addWidget(self.excl_folders_entry)
        
        excl_layout.addWidget(QLabel("Excluded Extensions (comma separated):"))
        self.excl_ext_entry = QLineEdit(self.tab_excl)
        self.excl_ext_entry.setText(",".join(config.get("excluded_extensions", [])))
        excl_layout.addWidget(self.excl_ext_entry)
        
        self.save_exclusions_button = QPushButton("Save Exclusions", self.tab_excl)
        self.save_exclusions_button.setProperty("variant", "success")
        self.save_exclusions_button.clicked.connect(self.save_exclusions)
        excl_layout.addWidget(self.save_exclusions_button)
        
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
        
        self.dash_save_button = QPushButton("Save Dashboard", d_btns)
        self.dash_save_button.clicked.connect(self.save_dashboard)
        self.dash_save_button.setProperty("variant", "info")
        d_btns_layout.addWidget(self.dash_save_button)
        
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
            self.nb.setTabVisible(self._excl_tab_index, rank >= self.TIER_ORDER.index("Advanced"))
        config.set("settings_ui_tier", tier_name)
        # Rebuild the left navigation so the rail reflects the new tier.
        # Basic -> System Maintenance & Advanced Analysis groups hide;
        # Advanced -> Advanced Analysis group hides; Expert -> everything.
        if getattr(self, "app", None) and hasattr(self.app, "update_sidebar_experience"):
            self.app.update_sidebar_experience()

    def change_theme(self, text):
        if "Dark" in text:
            self.app.theme_chk.setChecked(True)
        else:
            self.app.theme_chk.setChecked(False)

    def save_perf(self):
        config.set("hash_algorithm", self.hash_algo_combo.currentText())
        config.set("max_thread_workers", self.max_threads_spinbox.value())
        config.set("search_thread_workers", self.search_threads_spinbox.value())
        config.set("size_unit", self.cb_unit.currentText())
        logger.info("Performance settings updated.")
        self.app.show_info_dialog("Success", "Performance settings saved.")

    def save_safe(self, event=None):
        config.set("safe_mode", self.chk_safe.isChecked())
        config.set("log_level", self.cb_log.currentText())
        
    def save_exclusions(self):
        folders = [f.strip() for f in self.excl_folders_entry.text().split(',') if f.strip()]
        exts = [e.strip() for e in self.excl_ext_entry.text().split(',') if e.strip()]
        config.set("excluded_folders", folders)
        config.set("excluded_extensions", exts)
        logger.info("Exclusions updated.")
        self.app.show_info_dialog("Success", "Exclusions updated.")

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

    def remove_dash_path(self):
        selected_items = self.dash_list.selectedItems()
        for item in selected_items:
            self.dash_list.takeItem(self.dash_list.row(item))
            
    def save_dashboard(self):
        paths = [self.dash_list.item(i).text() for i in range(self.dash_list.count())]
        config.set("dashboard_paths", paths)
        self.app.show_info_dialog("Success", "Dashboard paths saved.")

    def _init_performance_tooltips(self):
        self._performance_tooltips = attach_tooltips([
            (self.hash_algo_combo, self.TOOLTIP_TEXTS["hash_algorithm"]),
            (self.max_threads_spinbox, self.TOOLTIP_TEXTS["max_threads"]),
            (self.search_threads_spinbox, self.TOOLTIP_TEXTS["search_threads"]),
            (self.save_perf_button, self.TOOLTIP_TEXTS["save_performance"]),
        ])

    def _init_exclusion_tooltips(self):
        self._exclusion_tooltips = attach_tooltips([
            (self.excl_folders_entry, self.TOOLTIP_TEXTS["excluded_folders"]),
            (self.excl_ext_entry, self.TOOLTIP_TEXTS["excluded_extensions"]),
            (self.save_exclusions_button, self.TOOLTIP_TEXTS["save_exclusions"]),
        ])

    def _init_dashboard_tooltips(self):
        self._dashboard_tooltips = attach_tooltips([
            (self.dash_list, self.TOOLTIP_TEXTS["dashboard_paths"]),
            (self.dash_add_button, self.TOOLTIP_TEXTS["dashboard_add"]),
            (self.dash_remove_button, self.TOOLTIP_TEXTS["dashboard_remove"]),
            (self.dash_save_button, self.TOOLTIP_TEXTS["dashboard_save"]),
        ])
