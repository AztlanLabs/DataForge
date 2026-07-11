import os
import shutil
import platform
from collections import Counter
from functools import partial

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QScrollArea, QGroupBox, QGridLayout, QProgressBar
)
from PyQt5.QtCore import Qt

from .base import BaseView
from ...modules.usage import analyze_size
from ...core.config import config
from ...core.utils import format_size, categorize_extension, CATEGORY_COLORS

class DashboardView(BaseView):
    def get_title(self):
        return "Dashboard"
        
    def __init__(self, master, app=None):
        super().__init__(master, app)
        
        # Main Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Header Row
        hdr = QWidget(self)
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(0, 0, 0, 10)
        
        self.lbl_title = QLabel("\u2302 System Dashboard", hdr)
        self.lbl_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        hdr_layout.addWidget(self.lbl_title)
        
        hdr_layout.addStretch()
        
        self.btn_refresh = QPushButton("\u21BB Refresh", hdr)
        self.btn_refresh.clicked.connect(self.refresh_stats)
        hdr_layout.addWidget(self.btn_refresh)
        self.main_layout.addWidget(hdr)
        
        # Scrollable body
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.main_layout.addWidget(self.scroll)
        
        body_widget = QWidget()
        self.body_layout = QVBoxLayout(body_widget)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(15)
        self.scroll.setWidget(body_widget)
        
        # ── Row 1: Disk Usage + System Info ──
        row1 = QWidget(body_widget)
        row1_layout = QHBoxLayout(row1)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(10)
        
        # Disk Usage Card
        self.f_disk = QGroupBox("Disk Usage", row1)
        self.disk_layout = QVBoxLayout(self.f_disk)
        self.disk_progress = QProgressBar(self.f_disk)
        self.disk_progress.setMaximum(100)
        self.disk_layout.addWidget(self.disk_progress)
        self.lbl_disk_info = QLabel("Loading...", self.f_disk)
        self.lbl_disk_info.setAlignment(Qt.AlignCenter)
        self.disk_layout.addWidget(self.lbl_disk_info)
        row1_layout.addWidget(self.f_disk, 1)
        
        # System Info Card
        self.f_sys = QGroupBox("System Info", row1)
        self.sys_layout = QGridLayout(self.f_sys)
        row1_layout.addWidget(self.f_sys, 1)
        
        self.body_layout.addWidget(row1)
        
        # ── Row 2: File Distribution + Quick Stats ──
        row2 = QWidget(body_widget)
        row2_layout = QHBoxLayout(row2)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(10)
        
        # File Distribution
        self.f_types = QGroupBox("File Distribution", row2)
        self.type_layout = QVBoxLayout(self.f_types)
        row2_layout.addWidget(self.f_types, 1)
        
        # Quick Stats
        self.f_quick = QGroupBox("Quick Stats", row2)
        self.quick_layout = QGridLayout(self.f_quick)
        row2_layout.addWidget(self.f_quick, 1)
        
        self.body_layout.addWidget(row2)
        
        # ── Row 3: Storage Breakdown + Recent / Large Files ──
        row3 = QWidget(body_widget)
        row3_layout = QHBoxLayout(row3)
        row3_layout.setContentsMargins(0, 0, 0, 0)
        row3_layout.setSpacing(10)
        
        # Storage by Category
        self.f_storage = QGroupBox("Storage by Category", row3)
        self.storage_layout = QVBoxLayout(self.f_storage)
        row3_layout.addWidget(self.f_storage, 1)
        
        # Large Files
        self.f_large = QGroupBox("Largest Files", row3)
        self.large_layout = QVBoxLayout(self.f_large)
        row3_layout.addWidget(self.f_large, 1)
        
        self.body_layout.addWidget(row3)
        
        # ── Row 4: Config Summary ──
        self.f_config = QGroupBox("Configuration Summary", body_widget)
        self.config_layout = QGridLayout(self.f_config)
        self.body_layout.addWidget(self.f_config)

    def mount(self):
        self.refresh_stats()

    def refresh_stats(self):
        home = os.path.expanduser("~")
        
        # ── Disk Usage ──
        try:
            total, used, free = shutil.disk_usage(home)
            pct = int((used / total) * 100)
            self.disk_progress.setValue(pct)
            
            # Color-coded progress based on usage
            if pct > 90:
                style = "QProgressBar::chunk { background-color: #dc3545; }"
            elif pct > 70:
                style = "QProgressBar::chunk { background-color: #ffc107; }"
            else:
                style = "QProgressBar::chunk { background-color: #28a745; }"
            self.disk_progress.setStyleSheet(style)
            
            self.lbl_disk_info.setText(
                f"Used: {format_size(used)}  |  Free: {format_size(free)}  |  Total: {format_size(total)}"
            )
        except Exception as e:
            self.lbl_disk_info.setText(f"Disk error: {e}")
        
        # ── System Info ──
        # Clear sys layout
        for i in reversed(range(self.sys_layout.count())):
            self.sys_layout.itemAt(i).widget().setParent(None)
        
        sys_items = [
            ("OS", f"{platform.system()} {platform.release()}"),
            ("Machine", platform.machine()),
            ("Home", home),
            ("Python", platform.python_version()),
            ("Config Dir", os.path.join(home, ".dataforge")),
        ]
        
        for idx, (lbl_txt, val_txt) in enumerate(sys_items):
            lbl = QLabel(f"<b>{lbl_txt}:</b>")
            lbl.setFixedWidth(100)
            val = QLabel(val_txt)
            val.setWordWrap(True)
            self.sys_layout.addWidget(lbl, idx, 0)
            self.sys_layout.addWidget(val, idx, 1)
        
        # ── Configuration Summary ──
        # Clear config layout
        for i in reversed(range(self.config_layout.count())):
            self.config_layout.itemAt(i).widget().setParent(None)
            
        cfg_items = [
            ("Theme", config.get("theme", "cosmo")),
            ("Safe Mode", "Enabled (Trash)" if config.get("safe_mode", True) else "Disabled"),
            ("Hash Algorithm", config.get("hash_algorithm", "md5").upper()),
            ("Max Threads", str(config.get("max_thread_workers", 4))),
            ("Size Unit", config.get("size_unit", "Auto")),
            ("Excluded Ext", ", ".join(config.get("excluded_extensions", [])) or "None"),
            ("Excluded Dirs", ", ".join(config.get("excluded_folders", [])) or "None"),
        ]
        
        for idx, (lbl_txt, val_txt) in enumerate(cfg_items):
            lbl = QLabel(f"<b>{lbl_txt}:</b>")
            val = QLabel(val_txt)
            row = idx % 4
            col = (idx // 4) * 2
            self.config_layout.addWidget(lbl, row, col)
            self.config_layout.addWidget(val, row, col + 1)
            
        # ── File Distribution + Stats (background scan) ──
        paths = config.get("dashboard_paths", [])
        if not paths:
            paths = [os.path.join(home, "Documents")]
            
        # Clear old widgets from lists
        for layout in [self.type_layout, self.quick_layout, self.storage_layout, self.large_layout]:
            for i in reversed(range(layout.count())):
                layout.itemAt(i).widget().setParent(None)
                
        lbl_status = QLabel(f"Scanning {len(paths)} locations...")
        self.type_layout.addWidget(lbl_status)
        
        self.app.run_background(
            self._scan_comprehensive,
            self._on_scan_complete,
            paths,
            show_progress=True,
            on_error=partial(self.app.show_workflow_error, title="Dashboard Scan Failed"),
        )

    def _categorize_ext(self, ext):
        return categorize_extension(ext)

    def _scan_comprehensive(self, paths):
        ext_counts = Counter()
        category_sizes = Counter()
        total_files = 0
        total_size = 0
        dir_count = 0
        largest_files = []
        max_scan = 10000
        
        for path in paths:
            if not os.path.exists(path):
                continue
            try:
                for root, dirs, files in os.walk(path):
                    dir_count += len(dirs)
                    for f in files:
                        fp = os.path.join(root, f)
                        ext = os.path.splitext(f)[1].lower()
                        if not ext:
                            ext = "No Ext"
                        ext_counts[ext] += 1
                        
                        try:
                            fsize = os.path.getsize(fp)
                        except OSError:
                            fsize = 0
                        
                        total_size += fsize
                        total_files += 1
                        
                        cat = self._categorize_ext(ext)
                        category_sizes[cat] += fsize
                        
                        if len(largest_files) < 10:
                            largest_files.append((fsize, fp))
                            largest_files.sort(reverse=True, key=lambda x: x[0])
                        elif fsize > largest_files[-1][0]:
                            largest_files[-1] = (fsize, fp)
                            largest_files.sort(reverse=True, key=lambda x: x[0])
                        
                        if total_files >= max_scan:
                            break
                    if total_files >= max_scan:
                        break
                if total_files >= max_scan:
                    break
            except OSError:
                continue
        
        return {
            "ext_counts": ext_counts,
            "category_sizes": category_sizes,
            "total_files": total_files,
            "total_size": total_size,
            "dir_count": dir_count,
            "largest_files": largest_files,
        }

    def _on_scan_complete(self, data):
        ext_counts = data["ext_counts"]
        category_sizes = data["category_sizes"]
        total_files = data["total_files"]
        total_size = data["total_size"]
        dir_count = data["dir_count"]
        largest_files = data["largest_files"]
        
        # Clear temporary scanner label
        for i in reversed(range(self.type_layout.count())):
            self.type_layout.itemAt(i).widget().setParent(None)
            
        sample_note = " (sample)" if total_files >= 10000 else ""
        lbl_status = QLabel(f"Scanned {total_files} files{sample_note}")
        self.type_layout.addWidget(lbl_status)
        
        # ── File Distribution (top 8 extensions) ──
        top = ext_counts.most_common(8)
        if not top:
            self.type_layout.addWidget(QLabel("No files found."))
        else:
            max_c = top[0][1] if top else 1
            for ext, count in top:
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 2, 0, 2)
                
                lbl_ext = QLabel(ext)
                lbl_ext.setFixedWidth(50)
                lbl_ext.setStyleSheet("font-family: Consolas;")
                row_layout.addWidget(lbl_ext)
                
                p = QProgressBar(row)
                p.setMaximum(max_c)
                p.setValue(count)
                p.setTextVisible(False)
                p.setFixedHeight(12)
                row_layout.addWidget(p)
                
                lbl_cnt = QLabel(str(count))
                lbl_cnt.setFixedWidth(50)
                lbl_cnt.setAlignment(Qt.AlignRight)
                row_layout.addWidget(lbl_cnt)
                
                self.type_layout.addWidget(row)
        
        # ── Quick Stats ──
        stats = [
            ("\U0001F4C1", "Total Files", f"{total_files:,}"),
            ("\U0001F4C2", "Directories", f"{dir_count:,}"),
            ("\U0001F4BE", "Total Size", format_size(total_size)),
            ("\U0001F4CA", "Extensions", f"{len(ext_counts)} types"),
            ("\U0001F4C4", "Avg Size", format_size(total_size // max(total_files, 1))),
            ("\U0001F3AF", "Top Type", top[0][0] if top else "N/A"),
        ]
        
        for idx, (icon, label, value) in enumerate(stats):
            lbl = QLabel(f"<b>{icon} {label}:</b>")
            val = QLabel(value)
            self.quick_layout.addWidget(lbl, idx, 0)
            self.quick_layout.addWidget(val, idx, 1)
            
        # ── Storage by Category ──
        if category_sizes:
            max_cat_size = max(category_sizes.values()) if category_sizes else 1
            for cat in ["Documents", "Images", "Videos", "Audio", "Archives", "Code", "Other"]:
                cat_size = category_sizes.get(cat, 0)
                if cat_size == 0:
                    continue
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 2, 0, 2)
                
                lbl_cat = QLabel(cat)
                lbl_cat.setFixedWidth(80)
                row_layout.addWidget(lbl_cat)
                
                p = QProgressBar(row)
                p.setMaximum(max_cat_size)
                p.setValue(cat_size)
                p.setTextVisible(False)
                p.setFixedHeight(12)
                
                color = CATEGORY_COLORS.get(cat, "#17a2b8")
                p.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; }}")
                row_layout.addWidget(p)
                
                lbl_size = QLabel(format_size(cat_size))
                lbl_size.setFixedWidth(80)
                lbl_size.setAlignment(Qt.AlignRight)
                row_layout.addWidget(lbl_size)
                
                self.storage_layout.addWidget(row)
        else:
            self.storage_layout.addWidget(QLabel("No data."))
            
        # ── Largest Files ──
        if largest_files:
            for size, path in largest_files[:8]:
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 2, 0, 2)
                
                fname = os.path.basename(path)
                if len(fname) > 30:
                    fname = fname[:27] + "..."
                lbl_file = QLabel(fname)
                lbl_file.setToolTip(path)
                row_layout.addWidget(lbl_file)
                
                lbl_size = QLabel(format_size(size))
                lbl_size.setObjectName("dashboardFileSize")
                lbl_size.setAlignment(Qt.AlignRight)
                row_layout.addWidget(lbl_size)
                
                self.large_layout.addWidget(row)
        else:
            self.large_layout.addWidget(QLabel("No files found."))
