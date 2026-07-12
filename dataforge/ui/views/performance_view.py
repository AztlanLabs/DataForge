"""
System Performance Monitor GUI view.

Provides real-time system metrics, process monitoring,
startup management, and disk health reporting.
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox, QGridLayout, QTabWidget, QComboBox, QProgressBar,
    QMessageBox
)
from PyQt5.QtCore import Qt, QTimer

from .base import BaseView
from ..theme_tokens import TYPE_SCALE
from ..widgets import EnhancedTreeview, attach_tooltips
from ...core.utils import format_size
from ...modules.performance import (
    check_availability,
    get_system_info,
    get_running_processes,
    get_resource_heavy_processes,
    get_startup_items,
    get_disk_health,
    get_live_resource_snapshot,
)


class PerformanceView(BaseView):
    TOOLTIP_TEXTS = {
        "refresh": "Refresh system information and resource usage.",
        "sort_by": "Sort process list by CPU usage, memory usage, name, or PID.",
        "kill_process": "Terminate the selected process. Use with caution — killing system processes can cause instability.",
        "refresh_health": "Read S.M.A.R.T. disk health data. Requires smartmontools to be installed.",
        "auto_refresh": "Toggle automatic refresh of resource metrics every 3 seconds.",
    }

    def get_title(self):
        return "Performance"

    def __init__(self, master, app=None):
        super().__init__(master, app)

        self.auto_refresh_active = False
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._auto_refresh_tick)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        if not check_availability():
            no_psutil = QLabel(
                "⚠️ The 'psutil' package is not installed.\n"
                "Install it with: pip install psutil\n\n"
                "Performance monitoring features are unavailable.",
                self,
            )
            no_psutil.setProperty("variant", "danger")
            no_psutil.setStyleSheet(f"font-size: {TYPE_SCALE['heading']}px; padding: 40px;")
            no_psutil.setAlignment(Qt.AlignCenter)
            no_psutil.setWordWrap(True)
            layout.addWidget(no_psutil)
            return

        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, 1)

        # ===== Tab 1: System Overview =====
        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        overview_layout.setContentsMargins(5, 5, 5, 5)

        # Header with refresh
        header = QWidget(overview_tab)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 5)

        self.btn_refresh = QPushButton("🔄 Refresh", header)
        self.btn_refresh.clicked.connect(self._refresh_overview)
        header_layout.addWidget(self.btn_refresh)

        self.btn_auto_refresh = QPushButton("▶ Auto-Refresh", header)
        self.btn_auto_refresh.setCheckable(True)
        self.btn_auto_refresh.clicked.connect(self._toggle_auto_refresh)
        header_layout.addWidget(self.btn_auto_refresh)
        header_layout.addStretch()

        self.lbl_uptime = QLabel("Uptime: —", header)
        self.lbl_uptime.setProperty("class", "muted")
        header_layout.addWidget(self.lbl_uptime)
        overview_layout.addWidget(header)

        # Resource meters grid
        meters_group = QGroupBox("Resource Usage", overview_tab)
        meters_grid = QGridLayout(meters_group)
        meters_grid.setSpacing(15)

        # CPU Meter
        self.lbl_cpu_title = QLabel("CPU")
        self.lbl_cpu_title.setStyleSheet(f"font-weight: bold; font-size: {TYPE_SCALE['subheading']}px;")
        meters_grid.addWidget(self.lbl_cpu_title, 0, 0)
        self.cpu_bar = QProgressBar(meters_group)
        self.cpu_bar.setMaximum(100)
        self.cpu_bar.setTextVisible(True)
        self.cpu_bar.setMinimumHeight(25)
        meters_grid.addWidget(self.cpu_bar, 1, 0)
        self.lbl_cpu_detail = QLabel("—")
        self.lbl_cpu_detail.setProperty("class", "muted")
        self.lbl_cpu_detail.setStyleSheet(f"font-size: {TYPE_SCALE['caption']}px;")
        self.lbl_cpu_detail.setWordWrap(True)
        meters_grid.addWidget(self.lbl_cpu_detail, 2, 0)

        # RAM Meter
        self.lbl_ram_title = QLabel("RAM")
        self.lbl_ram_title.setStyleSheet(f"font-weight: bold; font-size: {TYPE_SCALE['subheading']}px;")
        meters_grid.addWidget(self.lbl_ram_title, 0, 1)
        self.ram_bar = QProgressBar(meters_group)
        self.ram_bar.setMaximum(100)
        self.ram_bar.setTextVisible(True)
        self.ram_bar.setMinimumHeight(25)
        meters_grid.addWidget(self.ram_bar, 1, 1)
        self.lbl_ram_detail = QLabel("—")
        self.lbl_ram_detail.setProperty("class", "muted")
        self.lbl_ram_detail.setStyleSheet(f"font-size: {TYPE_SCALE['caption']}px;")
        self.lbl_ram_detail.setWordWrap(True)
        meters_grid.addWidget(self.lbl_ram_detail, 2, 1)

        # Swap Meter
        self.lbl_swap_title = QLabel("Swap")
        self.lbl_swap_title.setStyleSheet(f"font-weight: bold; font-size: {TYPE_SCALE['subheading']}px;")
        meters_grid.addWidget(self.lbl_swap_title, 0, 2)
        self.swap_bar = QProgressBar(meters_group)
        self.swap_bar.setMaximum(100)
        self.swap_bar.setTextVisible(True)
        self.swap_bar.setMinimumHeight(25)
        meters_grid.addWidget(self.swap_bar, 1, 2)
        self.lbl_swap_detail = QLabel("—")
        self.lbl_swap_detail.setProperty("class", "muted")
        self.lbl_swap_detail.setStyleSheet(f"font-size: {TYPE_SCALE['caption']}px;")
        self.lbl_swap_detail.setWordWrap(True)
        meters_grid.addWidget(self.lbl_swap_detail, 2, 2)

        overview_layout.addWidget(meters_group)

        # System info card
        self.sys_info_group = QGroupBox("System Information", overview_tab)
        self.sys_info_layout = QGridLayout(self.sys_info_group)
        self.sys_info_layout.setColumnStretch(1, 1)
        self.sys_info_layout.setColumnStretch(3, 1)

        self.sys_labels = {}
        info_fields = [
            ("OS", 0, 0), ("Machine", 0, 2),
            ("CPU Model", 1, 0), ("CPU Cores", 1, 2),
            ("CPU Frequency", 2, 0), ("Hostname", 2, 2),
            ("Python", 3, 0), ("Total RAM", 3, 2),
        ]
        for label_text, row, col in info_fields:
            lbl_name = QLabel(f"{label_text}:", self.sys_info_group)
            lbl_name.setProperty("class", "muted")
            lbl_name.setStyleSheet("font-weight: bold;")
            lbl_value = QLabel("—", self.sys_info_group)
            lbl_value.setWordWrap(True)
            self.sys_info_layout.addWidget(lbl_name, row, col)
            self.sys_info_layout.addWidget(lbl_value, row, col + 1)
            self.sys_labels[label_text] = lbl_value

        overview_layout.addWidget(self.sys_info_group)

        # Disk info
        self.disk_group = QGroupBox("Disk Partitions", overview_tab)
        disk_layout = QVBoxLayout(self.disk_group)
        self.disk_tree = EnhancedTreeview(
            self.disk_group,
            columns=("device", "mount", "fstype", "total", "used", "free", "percent"),
            app=self.app,
        )
        self.disk_tree.heading("device", text="Device")
        self.disk_tree.heading("mount", text="Mount Point")
        self.disk_tree.heading("fstype", text="FS Type")
        self.disk_tree.heading("total", text="Total")
        self.disk_tree.heading("used", text="Used")
        self.disk_tree.heading("free", text="Free")
        self.disk_tree.heading("percent", text="Used %")
        self.disk_tree.column("percent", width=70, stretch=False)
        disk_layout.addWidget(self.disk_tree)
        overview_layout.addWidget(self.disk_group)

        self.tabs.addTab(overview_tab, "📊 System Overview")

        # ===== Tab 2: Process Monitor =====
        process_tab = QWidget()
        proc_layout = QVBoxLayout(process_tab)
        proc_layout.setContentsMargins(5, 5, 5, 5)

        # Controls
        proc_header = QWidget(process_tab)
        proc_header_layout = QHBoxLayout(proc_header)
        proc_header_layout.setContentsMargins(0, 0, 0, 5)

        proc_header_layout.addWidget(QLabel("Sort by:"))
        self.sort_combo = QComboBox(proc_header)
        self.sort_combo.addItems(["memory", "cpu", "name", "pid"])
        proc_header_layout.addWidget(self.sort_combo)

        self.btn_refresh_proc = QPushButton("🔄 Refresh", proc_header)
        self.btn_refresh_proc.clicked.connect(self._refresh_processes)
        proc_header_layout.addWidget(self.btn_refresh_proc)

        self.btn_heavy = QPushButton("🔥 Heavy Only", proc_header)
        self.btn_heavy.clicked.connect(self._show_heavy_processes)
        proc_header_layout.addWidget(self.btn_heavy)

        self.btn_kill = QPushButton("⛔ Kill Process", proc_header)
        self.btn_kill.setProperty("variant", "danger")
        self.btn_kill.clicked.connect(self._kill_selected_process)
        proc_header_layout.addWidget(self.btn_kill)
        proc_header_layout.addStretch()

        self.lbl_proc_count = QLabel("Processes: —", proc_header)
        self.lbl_proc_count.setProperty("class", "muted")
        proc_header_layout.addWidget(self.lbl_proc_count)
        proc_layout.addWidget(proc_header)

        # Process tree
        self.proc_tree = EnhancedTreeview(
            process_tab,
            columns=("pid", "name", "user", "cpu", "memory", "mem_bytes", "status"),
            app=self.app,
        )
        self.proc_tree.heading("pid", text="PID")
        self.proc_tree.column("pid", width=60, stretch=False)
        self.proc_tree.heading("name", text="Process Name")
        self.proc_tree.heading("user", text="User")
        self.proc_tree.column("user", width=80, stretch=False)
        self.proc_tree.heading("cpu", text="CPU %")
        self.proc_tree.column("cpu", width=60, stretch=False)
        self.proc_tree.heading("memory", text="Mem %")
        self.proc_tree.column("memory", width=60, stretch=False)
        self.proc_tree.heading("mem_bytes", text="Mem Size")
        self.proc_tree.column("mem_bytes", width=80, stretch=False)
        self.proc_tree.heading("status", text="Status")
        self.proc_tree.column("status", width=70, stretch=False)
        proc_layout.addWidget(self.proc_tree, 1)

        self.tabs.addTab(process_tab, "⚙️ Processes")

        # ===== Tab 3: Startup Manager =====
        startup_tab = QWidget()
        startup_layout = QVBoxLayout(startup_tab)
        startup_layout.setContentsMargins(5, 5, 5, 5)

        startup_header = QWidget(startup_tab)
        sh_layout = QHBoxLayout(startup_header)
        sh_layout.setContentsMargins(0, 0, 0, 5)

        self.btn_refresh_startup = QPushButton("🔄 Refresh Startup Items", startup_header)
        self.btn_refresh_startup.clicked.connect(self._refresh_startup)
        sh_layout.addWidget(self.btn_refresh_startup)
        sh_layout.addStretch()
        self.lbl_startup_count = QLabel("Startup items: —", startup_header)
        self.lbl_startup_count.setProperty("class", "muted")
        sh_layout.addWidget(self.lbl_startup_count)
        startup_layout.addWidget(startup_header)

        self.startup_tree = EnhancedTreeview(
            startup_tab,
            columns=("name", "type", "scope", "enabled", "command"),
            app=self.app,
        )
        self.startup_tree.heading("name", text="Name")
        self.startup_tree.heading("type", text="Type")
        self.startup_tree.column("type", width=90, stretch=False)
        self.startup_tree.heading("scope", text="Scope")
        self.startup_tree.column("scope", width=70, stretch=False)
        self.startup_tree.heading("enabled", text="Enabled")
        self.startup_tree.column("enabled", width=70, stretch=False)
        self.startup_tree.heading("command", text="Command / Path")
        startup_layout.addWidget(self.startup_tree, 1)

        self.tabs.addTab(startup_tab, "🚀 Startup")

        # ===== Tab 4: Disk Health =====
        health_tab = QWidget()
        health_layout = QVBoxLayout(health_tab)
        health_layout.setContentsMargins(5, 5, 5, 5)

        health_header = QWidget(health_tab)
        hh_layout = QHBoxLayout(health_header)
        hh_layout.setContentsMargins(0, 0, 0, 5)

        self.btn_refresh_health = QPushButton("🔄 Check Disk Health", health_header)
        self.btn_refresh_health.clicked.connect(self._refresh_disk_health)
        hh_layout.addWidget(self.btn_refresh_health)
        hh_layout.addStretch()
        self.lbl_health_status = QLabel("Click to check S.M.A.R.T. health data.", health_header)
        self.lbl_health_status.setProperty("class", "muted")
        hh_layout.addWidget(self.lbl_health_status)
        health_layout.addWidget(health_header)

        self.health_tree = EnhancedTreeview(
            health_tab,
            columns=("device", "status", "temperature", "details"),
            app=self.app,
        )
        self.health_tree.heading("device", text="Device")
        self.health_tree.heading("status", text="Health Status")
        self.health_tree.column("status", width=100, stretch=False)
        self.health_tree.heading("temperature", text="Temp (°C)")
        self.health_tree.column("temperature", width=80, stretch=False)
        self.health_tree.heading("details", text="Details")
        health_layout.addWidget(self.health_tree, 1)

        self.tabs.addTab(health_tab, "💊 Disk Health")

        self._init_tooltips()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def mount(self):
        self._refresh_overview()

    def unmount(self):
        if self.auto_refresh_active:
            self._toggle_auto_refresh()

    # ------------------------------------------------------------------
    # System Overview
    # ------------------------------------------------------------------

    def _refresh_overview(self):
        self.app.run_workflow(
            self._collect_overview_data,
            self._on_overview_data,
            error_title="System Info Error",
        )

    def _collect_overview_data(self):
        info = get_system_info()
        snapshot = get_live_resource_snapshot()
        return {"info": info, "snapshot": snapshot}

    def _on_overview_data(self, data):
        info = data["info"]
        snap = data["snapshot"]

        # Update CPU bar
        cpu_pct = int(snap.get("cpu_percent", 0))
        self.cpu_bar.setValue(cpu_pct)
        self.cpu_bar.setFormat(f"{cpu_pct}%")
        cores = snap.get("cpu_per_core", [])
        if cores:
            core_str = " | ".join(f"{c:.0f}%" for c in cores[:8])
            if len(cores) > 8:
                core_str += f" (+{len(cores)-8} more)"
            self.lbl_cpu_detail.setText(f"Per-core: {core_str}")

        # Update RAM bar
        mem = snap.get("memory", {})
        ram_pct = int(mem.get("percent", 0))
        self.ram_bar.setValue(ram_pct)
        self.ram_bar.setFormat(f"{ram_pct}% ({format_size(mem.get('used', 0))} / {format_size(mem.get('total', 0))})")
        self.lbl_ram_detail.setText(f"Available: {format_size(mem.get('total', 0) - mem.get('used', 0))}")

        # Update Swap bar
        swap = snap.get("swap", {})
        swap_pct = int(swap.get("percent", 0))
        self.swap_bar.setValue(swap_pct)
        self.swap_bar.setFormat(f"{swap_pct}%")
        self.lbl_swap_detail.setText(
            f"{format_size(swap.get('used', 0))} / {format_size(swap.get('total', 0))}"
        )

        # System info labels
        os_info = info.get("os", {})
        cpu_info = info.get("cpu", {})
        mem_info = info.get("memory", {})

        self.sys_labels["OS"].setText(f"{os_info.get('system', '')} {os_info.get('release', '')}")
        self.sys_labels["Machine"].setText(os_info.get("machine", ""))
        self.sys_labels["CPU Model"].setText(cpu_info.get("model", os_info.get("processor", "—")))
        self.sys_labels["CPU Cores"].setText(
            f"{cpu_info.get('physical_cores', '?')} physical / {cpu_info.get('logical_cores', '?')} logical"
        )
        freq = cpu_info.get("current_frequency_mhz")
        max_freq = cpu_info.get("max_frequency_mhz")
        freq_str = f"{freq:.0f} MHz" if freq else "—"
        if max_freq and max_freq != freq:
            freq_str += f" (max {max_freq:.0f} MHz)"
        self.sys_labels["CPU Frequency"].setText(freq_str)
        self.sys_labels["Hostname"].setText(os_info.get("hostname", ""))
        self.sys_labels["Python"].setText(os_info.get("python_version", ""))
        self.sys_labels["Total RAM"].setText(format_size(mem_info.get("total_bytes", 0)))

        # Uptime
        uptime = info.get("uptime", {})
        self.lbl_uptime.setText(f"Uptime: {uptime.get('uptime_formatted', '—')}")

        # Disk tree
        self.disk_tree.tree.clear()
        self.disk_tree.item_map.clear()
        for disk in info.get("disks", []):
            self.disk_tree.insert("", "end", values=(
                disk.get("device", ""),
                disk.get("mountpoint", ""),
                disk.get("fstype", ""),
                format_size(disk.get("total_bytes", 0)),
                format_size(disk.get("used_bytes", 0)),
                format_size(disk.get("free_bytes", 0)),
                f"{disk.get('percent_used', 0)}%",
            ))

    # ------------------------------------------------------------------
    # Auto-refresh
    # ------------------------------------------------------------------

    def _toggle_auto_refresh(self):
        self.auto_refresh_active = not self.auto_refresh_active
        if self.auto_refresh_active:
            self.btn_auto_refresh.setText("⏸ Stop Auto")
            self.btn_auto_refresh.setChecked(True)
            self.refresh_timer.start(3000)
        else:
            self.btn_auto_refresh.setText("▶ Auto-Refresh")
            self.btn_auto_refresh.setChecked(False)
            self.refresh_timer.stop()

    def _auto_refresh_tick(self):
        if not self.auto_refresh_active:
            return
        # Only refresh the meters (lightweight)
        try:
            snap = get_live_resource_snapshot()
            if "error" in snap:
                return
            cpu_pct = int(snap.get("cpu_percent", 0))
            self.cpu_bar.setValue(cpu_pct)
            self.cpu_bar.setFormat(f"{cpu_pct}%")

            mem = snap.get("memory", {})
            ram_pct = int(mem.get("percent", 0))
            self.ram_bar.setValue(ram_pct)
            self.ram_bar.setFormat(f"{ram_pct}%")

            swap = snap.get("swap", {})
            swap_pct = int(swap.get("percent", 0))
            self.swap_bar.setValue(swap_pct)
            self.swap_bar.setFormat(f"{swap_pct}%")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Process Monitor
    # ------------------------------------------------------------------

    def _refresh_processes(self):
        sort = self.sort_combo.currentText()
        self.app.run_workflow(
            get_running_processes,
            self._on_processes_loaded,
            sort,
            50,
            error_title="Process List Error",
        )

    def _on_processes_loaded(self, processes):
        self.proc_tree.tree.clear()
        self.proc_tree.item_map.clear()

        for proc in processes:
            self.proc_tree.insert("", "end", values=(
                proc["pid"],
                proc["name"],
                proc.get("username", ""),
                f"{proc['cpu_percent']:.1f}",
                f"{proc['memory_percent']:.1f}",
                format_size(proc.get("memory_bytes", 0)),
                proc.get("status", ""),
            ))

        self.lbl_proc_count.setText(f"Processes: {len(processes)}")

    def _show_heavy_processes(self):
        self.app.run_workflow(
            get_resource_heavy_processes,
            self._on_processes_loaded,
            error_title="Process List Error",
        )

    def _kill_selected_process(self):
        selection = self.proc_tree.selection()
        if not selection:
            self.app.show_warning_dialog("No Selection", "Select a process to kill.")
            return

        item = self.proc_tree.item(selection[0])
        values = item.get("values", [])
        if not values:
            return

        pid = int(values[0])
        name = values[1]

        reply = QMessageBox.question(
            self,
            "Kill Process",
            f"Terminate process '{name}' (PID {pid})?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            import psutil
            proc = psutil.Process(pid)
            proc.terminate()
            self.app.update_status(f"Process '{name}' (PID {pid}) terminated.")
            self._refresh_processes()
        except Exception as exc:
            self.app.show_error_dialog("Kill Failed", str(exc))

    # ------------------------------------------------------------------
    # Startup Manager
    # ------------------------------------------------------------------

    def _refresh_startup(self):
        self.app.run_workflow(
            get_startup_items,
            self._on_startup_loaded,
            error_title="Startup Items Error",
        )

    def _on_startup_loaded(self, items):
        self.startup_tree.tree.clear()
        self.startup_tree.item_map.clear()

        for item in items:
            self.startup_tree.insert("", "end", values=(
                item.get("name", ""),
                item.get("type", ""),
                item.get("scope", ""),
                "Yes" if item.get("enabled") else "No",
                item.get("command", item.get("path", "")),
            ))

        self.lbl_startup_count.setText(f"Startup items: {len(items)}")

    # ------------------------------------------------------------------
    # Disk Health
    # ------------------------------------------------------------------

    def _refresh_disk_health(self):
        self.lbl_health_status.setText("Checking disk health...")
        self.app.run_workflow(
            get_disk_health,
            self._on_disk_health,
            error_title="Disk Health Error",
        )

    def _on_disk_health(self, health):
        self.health_tree.tree.clear()
        self.health_tree.item_map.clear()

        if "error" in health:
            self.lbl_health_status.setText(health["error"])
            return

        for device, info in health.items():
            status = "✅ PASSED" if info.get("healthy") else "❌ FAILED" if "healthy" in info else "⚠️ Unknown"
            temp = str(info.get("temperature_c", "—"))
            details = info.get("error", "OK")

            self.health_tree.insert("", "end", values=(
                device, status, temp, details,
            ))

        self.lbl_health_status.setText(f"Checked {len(health)} device(s).")

    # ------------------------------------------------------------------
    # Tooltips
    # ------------------------------------------------------------------

    def _init_tooltips(self):
        widgets = [
            (self.btn_refresh, self.TOOLTIP_TEXTS["refresh"]),
            (self.btn_auto_refresh, self.TOOLTIP_TEXTS["auto_refresh"]),
            (self.sort_combo, self.TOOLTIP_TEXTS["sort_by"]),
            (self.btn_kill, self.TOOLTIP_TEXTS["kill_process"]),
            (self.btn_refresh_health, self.TOOLTIP_TEXTS["refresh_health"]),
        ]
        attach_tooltips(widgets)
