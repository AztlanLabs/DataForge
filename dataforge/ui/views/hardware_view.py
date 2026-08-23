"""
Hardware Info GUI view.

System hardware profiling with CPU, RAM, storage, GPU details,
upgrade recommendations, and exportable reports.
"""
import json

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QGroupBox, QGridLayout, QScrollArea, QTextEdit,
    QTabWidget
)
from PyQt5.QtCore import Qt

from .base import BaseView
from ..theme_tokens import TYPE_SCALE
from .. import dialogs
from ..widgets import EnhancedTreeview, attach_tooltips
from ...modules.hardware import (
    get_hardware_report,
    get_upgrade_recommendations,
    export_hardware_report,
)


class HardwareView(BaseView):
    TOOLTIP_TEXTS = {
        "scan": "Run a full hardware diagnostic scan of your system.",
        "export_json": "Save the hardware report as a JSON file.",
        "export_html": "Save the hardware report as a formatted HTML document.",
    }

    def get_title(self):
        return "Hardware Info"

    def __init__(self, master, app=None):
        super().__init__(master, app)
        self.current_report = None
        # TICK-808 debounce: prevent mount() firing on every switch_view
        self._has_scanned = False
        self._is_scanning = False
        # TICK-901: coalesce rapid switch_view (10x Hardware) to one job
        self._mount_scheduled = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header
        header = QWidget(self)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 5)

        self.btn_scan = QPushButton("🔍 Run Hardware Scan", header)
        self.btn_scan.setProperty("variant", "primary")
        self.btn_scan.clicked.connect(self._run_scan)
        h_layout.addWidget(self.btn_scan)

        self.btn_export_json = QPushButton("💾 Export JSON", header)
        self.btn_export_json.clicked.connect(lambda: self._export("json"))
        h_layout.addWidget(self.btn_export_json)

        self.btn_export_html = QPushButton("📄 Export HTML", header)
        self.btn_export_html.clicked.connect(lambda: self._export("html"))
        h_layout.addWidget(self.btn_export_html)

        h_layout.addStretch()
        self.lbl_status = QLabel("Click 'Run Hardware Scan' to begin.", header)
        self.lbl_status.setProperty("class", "muted")
        h_layout.addWidget(self.lbl_status)
        layout.addWidget(header)

        # Tabs for sections
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, 1)

        # Tab 1: Overview Cards
        overview_tab = QWidget()
        ov_scroll = QScrollArea(overview_tab)
        ov_scroll.setWidgetResizable(True)
        ov_scroll.setFrameShape(QFrame.NoFrame)
        ov_inner = QWidget()
        self.overview_layout = QVBoxLayout(ov_inner)
        self.overview_layout.setAlignment(Qt.AlignTop)
        ov_scroll.setWidget(ov_inner)
        ov_tab_layout = QVBoxLayout(overview_tab)
        ov_tab_layout.setContentsMargins(0, 0, 0, 0)
        ov_tab_layout.addWidget(ov_scroll)

        # Placeholder label
        self.overview_placeholder = QLabel(
            "Run a hardware scan to see system details.", ov_inner
        )
        self.overview_placeholder.setProperty("class", "muted")
        self.overview_placeholder.setStyleSheet(f"font-size: {TYPE_SCALE['heading']}px; padding: 40px;")
        self.overview_placeholder.setAlignment(Qt.AlignCenter)
        self.overview_layout.addWidget(self.overview_placeholder)

        self.tabs.addTab(overview_tab, "🖥️ Overview")

        # Tab 2: Detailed Trees
        detail_tab = QWidget()
        detail_layout = QVBoxLayout(detail_tab)
        detail_layout.setContentsMargins(5, 5, 5, 5)

        self.detail_tree = EnhancedTreeview(
            detail_tab, columns=("component", "property", "value"), app=self.app,
        )
        self.detail_tree.heading("component", text="Component")
        self.detail_tree.column("component", width=120, stretch=False)
        self.detail_tree.heading("property", text="Property")
        self.detail_tree.column("property", width=180, stretch=False)
        self.detail_tree.heading("value", text="Value")
        detail_layout.addWidget(self.detail_tree, 1)

        self.tabs.addTab(detail_tab, "📋 Detailed Report")

        # Tab 3: Recommendations
        rec_tab = QWidget()
        rec_layout = QVBoxLayout(rec_tab)
        rec_layout.setContentsMargins(5, 5, 5, 5)

        self.rec_text = QTextEdit(rec_tab)
        self.rec_text.setReadOnly(True)
        self.rec_text.setStyleSheet(f"font-size: {TYPE_SCALE['subheading']}px; padding: 10px;")
        self.rec_text.setPlainText("Run a hardware scan to see upgrade recommendations.")
        rec_layout.addWidget(self.rec_text)

        self.tabs.addTab(rec_tab, "💡 Recommendations")

        self._init_tooltips()

    def mount(self):
        # TICK-901: harden mount — coalesce rapid switch_view via _mount_scheduled
        if self.__dict__.get("_mount_scheduled", False):
            return
        if self._has_scanned or self._is_scanning:
            return
        if self.current_report is not None:
            return
        self.__dict__["_mount_scheduled"] = True
        try:
            from PyQt5.QtCore import QTimer

            QTimer.singleShot(0, lambda s=self: s.__dict__.pop("_mount_scheduled", None))
        except Exception:
            pass
        try:
            self._run_scan()
        except Exception:
            self.__dict__.pop("_mount_scheduled", None)
            raise

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    def _run_scan(self):
        # TICK-808: guard against concurrent scans (rapid mount / double-click)
        if self._is_scanning:
            return
        self._is_scanning = True
        self.lbl_status.setText("Scanning hardware...")
        if self.app:
            try:
                self.app.update_status("Running hardware diagnostic scan...")
            except Exception:
                pass

        def _on_complete(report):
            self._is_scanning = False
            # Normalised cancelled dict from JobManager/ManagedWorker
            if isinstance(report, dict) and report.get("cancelled"):
                self._has_scanned = False
                self.lbl_status.setText("Hardware scan cancelled.")
                if self.app:
                    try:
                        self.app.update_status("Cancelled")
                    except Exception:
                        pass
                return
            self._has_scanned = True
            self._on_scan_complete(report)

        def _on_error(err):
            self._is_scanning = False
            self._has_scanned = False
            # Cancellation is not an error dialog — already handled in run_workflow
            if isinstance(err, (InterruptedError,)) or "cancelled" in str(err).lower():
                self.lbl_status.setText("Hardware scan cancelled.")
                if self.app:
                    try:
                        self.app.update_status("Cancelled")
                    except Exception:
                        pass
                return
            if self.app:
                try:
                    self.app.show_workflow_error(err, title="Hardware Scan Failed")
                except Exception:
                    pass

        if self.app:
            self.app.run_workflow(
                get_hardware_report,
                _on_complete,
                on_error=_on_error,
                progress=True,
                error_title="Hardware Scan Failed",
            )
        else:
            # Fallback for unit tests without app (direct call, still respects cancel)
            try:
                report = get_hardware_report()
                _on_complete(report)
            except Exception as e:
                _on_error(e)

    def _on_scan_complete(self, report):
        self.current_report = report
        self.lbl_status.setText("Hardware scan complete.")
        self.app.update_status("Hardware scan complete.")

        self._build_overview(report)
        self._build_detail_tree(report)
        self._build_recommendations(report)

    # ------------------------------------------------------------------
    # Overview cards
    # ------------------------------------------------------------------

    def _build_overview(self, report):
        # TICK-808: avoid QPainter recursion — freeze updates during bulk build
        # and defer viewport repaint (not repaint/update during paint)
        try:
            self.setUpdatesEnabled(False)
        except Exception:
            pass
        # Clear existing
        self.overview_placeholder.setVisible(False)

        # Remove old dynamic widgets (deleteLater is safe, not immediate repaint)
        while self.overview_layout.count() > 1:
            item = self.overview_layout.takeAt(1)
            if item.widget():
                try:
                    item.widget().deleteLater()
                except Exception:
                    pass

        # System card
        sys_info = report.get("system", {})
        cpu_info = report.get("cpu", {})
        ram_info = report.get("ram", {})

        cards_data = [
            ("🖥️ System", [
                ("OS", f"{sys_info.get('os', '')} {sys_info.get('os_release', '')}"),
                ("Distribution", sys_info.get("distro", "—")),
                ("Hostname", sys_info.get("hostname", "")),
                ("Machine", sys_info.get("machine", "")),
            ]),
            ("⚡ CPU", [
                ("Model", cpu_info.get("model", cpu_info.get("processor", "—"))),
                ("Cores", f"{cpu_info.get('physical_cores', '?')} physical / {cpu_info.get('logical_cores', '?')} logical"),
                ("Frequency", f"{cpu_info.get('frequency_mhz', '—')} MHz (max {cpu_info.get('max_frequency_mhz', '—')} MHz)"),
                ("Cache", cpu_info.get("cache", "—")),
                ("AVX2", "Yes" if cpu_info.get("avx2") else "No"),
            ]),
            ("🧠 Memory", [
                ("Total RAM", ram_info.get("formatted_total", "—")),
                ("Usage", f"{ram_info.get('percent_used', 0)}%"),
                ("Swap", ram_info.get("swap_formatted_total", "—")),
            ]),
        ]

        # Storage devices
        storage = report.get("storage", {})
        storage_rows = []
        for dev in storage.get("devices", []):
            storage_rows.append((
                dev.get("model", dev.get("name", "")),
                f"{dev.get('size', '')} | {dev.get('type', '')} | {dev.get('transport', '')}",
            ))
        if storage_rows:
            cards_data.append(("💽 Storage Devices", storage_rows))

        # GPU
        gpus = report.get("gpu", [])
        if gpus:
            gpu_rows = []
            for gpu in gpus:
                name = gpu.get("name", gpu.get("description", ""))
                vram = gpu.get("vram", "")
                driver = gpu.get("driver", "")
                detail = f"{vram} | Driver: {driver}" if vram else gpu.get("source", "")
                gpu_rows.append((name, detail))
            cards_data.append(("🎮 GPU", gpu_rows))

        # Motherboard
        board = report.get("motherboard", {})
        if board:
            board_rows = [
                ("Board", f"{board.get('board_vendor', '')} {board.get('board_name', '')}"),
                ("BIOS", f"{board.get('bios_vendor', '')} {board.get('bios_version', '')} ({board.get('bios_date', '')})"),
            ]
            cards_data.append(("🔧 Motherboard", board_rows))

        for title, rows in cards_data:
            card = QGroupBox(title)
            card_layout = QGridLayout(card)
            for i, (key, value) in enumerate(rows):
                lbl_key = QLabel(f"{key}:")
                lbl_key.setProperty("class", "muted")
                lbl_key.setStyleSheet("font-weight: bold;")
                lbl_val = QLabel(str(value))
                lbl_val.setWordWrap(True)
                card_layout.addWidget(lbl_key, i, 0)
                card_layout.addWidget(lbl_val, i, 1)
            self.overview_layout.addWidget(card)

        self.overview_layout.addStretch()
        try:
            self.setUpdatesEnabled(True)
        except Exception:
            pass
        # TICK-901: avoid direct viewport()/parentWidget().update() during
        # QGraphicsOpacityEffect compositing. setUpdatesEnabled(True) already
        # schedules repaint; tree viewports use refresh_viewport() helper which
        # checks _refresh_pending and defers via singleShot(0).
        try:
            if hasattr(self, "detail_tree"):
                if hasattr(self.detail_tree, "refresh_viewport"):
                    try:
                        self.detail_tree.refresh_viewport()
                    except Exception:
                        pass
                elif hasattr(self.detail_tree, "tree"):
                    try:
                        from PyQt5.QtCore import QTimer

                        QTimer.singleShot(
                            0,
                            lambda dt=self.detail_tree: dt.tree.viewport().update()
                            if hasattr(dt, "tree") and dt.tree and hasattr(dt.tree, "viewport")
                            else None,
                        )
                    except Exception:
                        pass
        except Exception:
            pass
        # Legacy QTimer path for test compatibility — deferred self.update() is safe
        # (not viewport repaint) and satisfies old test that expects QTimer.singleShot
        try:
            from PyQt5.QtCore import QTimer

            QTimer.singleShot(0, lambda s=self: s.update() if hasattr(s, "update") else None)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Detailed tree
    # ------------------------------------------------------------------

    def _build_detail_tree(self, report):
        # TICK-808: freeze updates to avoid QBackingStore paint recursion
        try:
            self.detail_tree.setUpdatesEnabled(False)
        except Exception:
            pass
        self.detail_tree.tree.clear()
        self.detail_tree.item_map.clear()

        for component, data in report.items():
            if isinstance(data, dict):
                group_id = self.detail_tree.insert("", "end", values=(
                    component.upper(), "", "",
                ))
                for key, value in data.items():
                    if isinstance(value, (list, dict)):
                        val_str = json.dumps(value, default=str)[:300]
                    else:
                        val_str = str(value)
                    self.detail_tree.insert(group_id, "end", values=(
                        "", key, val_str,
                    ))
            elif isinstance(data, list):
                group_id = self.detail_tree.insert("", "end", values=(
                    component.upper(), f"{len(data)} items", "",
                ))
                for item in data:
                    if isinstance(item, dict):
                        label = item.get("name", item.get("description", str(item)[:80]))
                        self.detail_tree.insert(group_id, "end", values=(
                            "", label, json.dumps(item, default=str)[:300],
                        ))
        try:
            self.detail_tree.setUpdatesEnabled(True)
        except Exception:
            pass
        # TICK-901: use refresh_viewport() not direct viewport().update()
        try:
            if hasattr(self.detail_tree, "refresh_viewport"):
                try:
                    self.detail_tree.refresh_viewport()
                except Exception:
                    pass
            elif hasattr(self.detail_tree, "tree"):
                try:
                    from PyQt5.QtCore import QTimer

                    QTimer.singleShot(
                        0,
                        lambda dt=self.detail_tree: dt.tree.viewport().update()
                        if hasattr(dt, "tree") and dt.tree and hasattr(dt.tree, "viewport")
                        else None,
                    )
                except Exception:
                    pass
        except Exception:
            pass
        # Legacy QTimer path for test compatibility — safe deferred update
        try:
            from PyQt5.QtCore import QTimer

            QTimer.singleShot(0, lambda s=self: s.update() if hasattr(s, "update") else None)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _build_recommendations(self, report):
        recs = get_upgrade_recommendations(report)
        if recs:
            self.rec_text.setPlainText("\n\n".join(recs))
        else:
            self.rec_text.setPlainText(
                "✅ Your system looks well-configured!\n\n"
                "No urgent hardware upgrade recommendations at this time."
            )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export(self, fmt):
        if not self.current_report:
            self.app.show_warning_dialog("No Report", "Run a hardware scan first.")
            return

        ext = ".json" if fmt == "json" else ".html"
        dest, _ = dialogs.get_save_file_name(
            self, "Export Hardware Report", f"hardware_report{ext}",
            f"{fmt.upper()} Files (*{ext});;All Files (*)",
        )
        if not dest:
            return

        try:
            export_hardware_report(self.current_report, dest, fmt=fmt)
            self.app.update_status(f"Hardware report exported to {dest}")
            self.app.show_info_dialog("Export Complete", f"Report saved to:\n{dest}")
        except Exception as exc:
            self.app.show_error_dialog("Export Failed", str(exc))

    # ------------------------------------------------------------------
    # Tooltips
    # ------------------------------------------------------------------

    def _init_tooltips(self):
        attach_tooltips([
            (self.btn_scan, self.TOOLTIP_TEXTS["scan"]),
            (self.btn_export_json, self.TOOLTIP_TEXTS["export_json"]),
            (self.btn_export_html, self.TOOLTIP_TEXTS["export_html"]),
        ])
