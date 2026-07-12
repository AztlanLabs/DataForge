"""
Hardware Diagnostics GUI view.

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header
        header = QWidget(self)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 5)

        self.btn_scan = QPushButton("🔍 Run Hardware Scan", header)
        self.btn_scan.setProperty("variant", "primary")
        self.btn_scan.setStyleSheet("font-weight: bold; padding: 8px 16px;")
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
        if not self.current_report:
            self._run_scan()

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    def _run_scan(self):
        self.lbl_status.setText("Scanning hardware...")
        self.app.update_status("Running hardware diagnostic scan...")

        self.app.run_workflow(
            get_hardware_report,
            self._on_scan_complete,
            progress=True,
            error_title="Hardware Scan Failed",
        )

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
        # Clear existing
        self.overview_placeholder.setVisible(False)

        # Remove old dynamic widgets
        while self.overview_layout.count() > 1:
            item = self.overview_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

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

    # ------------------------------------------------------------------
    # Detailed tree
    # ------------------------------------------------------------------

    def _build_detail_tree(self, report):
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
