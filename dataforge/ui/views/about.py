"""
About & Help view.

Displays application info, versioning, system diagnostics,
and feature guides for all capabilities in the app.
"""
import os
import platform
import sys
import psutil

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame,
    QScrollArea, QGridLayout, QGroupBox
)
from PyQt5.QtCore import Qt

from .base import BaseView
from ..theme_tokens import TYPE_SCALE
from ..widgets import CollapsibleCard

class AboutView(BaseView):
    def get_title(self) -> str:
        return "About & Help"

    def __init__(self, master, app=None):
        super().__init__(master, app)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Scrollable container for the entire page
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(15)

        # 1. Header Banner
        banner_frame = QFrame(scroll_content)
        banner_frame.setFrameShape(QFrame.StyledPanel)
        banner_frame.setStyleSheet(
            "QFrame { background-color: #1e1b4b; border-radius: 8px; border: 1px solid #312e81; }"
        )
        banner_layout = QVBoxLayout(banner_frame)
        banner_layout.setContentsMargins(20, 20, 20, 20)

        lbl_app_title = QLabel("DataForge — File & System Intelligence", banner_frame)
        lbl_app_title.setStyleSheet(f"color: #e0e7ff; font-size: {TYPE_SCALE['display']}px; font-weight: bold; background: transparent;")
        banner_layout.addWidget(lbl_app_title)

        lbl_app_version = QLabel("Development build (release 1.0, 64-bit)", banner_frame)
        lbl_app_version.setStyleSheet(f"color: #818cf8; font-size: {TYPE_SCALE['body']}px; background: transparent;")
        banner_layout.addWidget(lbl_app_version)

        lbl_app_desc = QLabel(
            "An all-in-one system diagnostics, file organizer, storage structures analyzer, "
            "metadata studio, and digital forensics application.", banner_frame
        )
        lbl_app_desc.setStyleSheet(f"color: #c7d2fe; font-size: {TYPE_SCALE['body']}px; background: transparent;")
        lbl_app_desc.setWordWrap(True)
        banner_layout.addWidget(lbl_app_desc)

        scroll_layout.addWidget(banner_frame)

        # 2. System Diagnostics Panel
        sys_group = QGroupBox("System Diagnostics", scroll_content)
        sys_grid = QGridLayout(sys_group)
        sys_grid.setContentsMargins(15, 15, 15, 15)
        sys_grid.setHorizontalSpacing(20)
        sys_grid.setVerticalSpacing(10)

        # Collect platform info
        try:
            mem = psutil.virtual_memory()
            total_ram = f"{mem.total / (1024**3):.1f} GB"
        except Exception:
            total_ram = "Unknown"

        diagnostics = [
            ("Operating System:", f"{platform.system()} {platform.release()} ({platform.machine()})"),
            ("Kernel Version:", platform.version().split(" ")[0]),
            ("CPU Architecture:", platform.processor() or platform.machine()),
            ("Logical CPU Cores:", str(os.cpu_count() or "Unknown")),
            ("Installed RAM:", total_ram),
            ("Python Version:", sys.version.split(" ")[0]),
            ("PyQt5 Version:", "5.15.x (Qt 5.15.x)"),
            ("Config Directory:", os.path.expanduser("~/.dataforge")),
        ]

        for i, (label, val) in enumerate(diagnostics):
            lbl_name = QLabel(label, sys_group)
            lbl_name.setStyleSheet("font-weight: bold;")
            lbl_name.setProperty("class", "muted")
            lbl_val = QLabel(val, sys_group)
            lbl_val.setStyleSheet("font-family: Consolas, monospace;")
            lbl_val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            
            sys_grid.addWidget(lbl_name, i // 2, (i % 2) * 2)
            sys_grid.addWidget(lbl_val, i // 2, (i % 2) * 2 + 1)

        scroll_layout.addWidget(sys_group)

        # 3. Help Topics & User Guide
        help_group = QGroupBox("Application Features Guide", scroll_content)
        help_layout = QVBoxLayout(help_group)
        help_layout.setContentsMargins(10, 15, 10, 10)
        help_layout.setSpacing(8)

        guides = [
            ("Dashboard Overview", 
             "The Dashboard gives you an immediate look at your system storage structures. "
             "It lists active internal and external partitions, shows disk utilization, "
             "and displays quick shortcuts to launch optimization and forensics workflows."),
            
            ("Search & Organize", 
             "A high-speed, multithreaded directory scanner. Supports literal and regex search patterns. "
             "Once matching files are found, you can apply bulk operations such as copying, moving, "
             "renaming, deleting, or archiving them. Uses a dual-pane preview splitter to inspect "
             "text/image contents before applying changes."),
            
            ("Duplicate Finder", 
             "Locate space-consuming duplicate files across drives using quick size checks or deep cryptographic hashes "
             "(MD5, SHA-1, or SHA-256). Spacing controls and alignment improvements keep options readable. "
             "Supports group-level file deletion, automated parent directories filtering, and content previews."),
            
            ("System Cleanup & Browser Privacy", 
             "Reclaim gigabytes of drive space by sweeping temporary folders, system logs, thumbnails, and package caches. "
             "The Browser Privacy tab scans Chrome, Firefox, Brave, Edge, and other browser configurations for "
             "tracking cookies, browsing histories, and session databases. Both features feature horizontal split-pane "
             "file preview panels to view files before erasing them."),
            
            ("System Performance Monitor", 
             "A real-time systems monitor displaying CPU utilization, RAM usage, and active swap spaces. "
             "Features a sortable process table to kill resource-heavy apps, a startup configuration editor "
             "to adjust autostart applications, and a S.M.A.R.T. storage health diagnostics viewer."),
            
            ("File Recovery & Carving", 
             "Allows you to quickly undelete files from trash bins, or perform raw block-level carving "
             "from physical device blocks when partition tables are corrupted. Built-in carving matches "
             "common headers/footers (JPEG, PNG, ZIP, PDF). Also integrates photorec/testdisk command-line tool. "
             "Both trash and deep carving results feature integrated file previews."),
            
            ("Metadata Studio", 
             "A unified metadata reader and writer. It parses EXIF, tags, modifications, GPS positions, and timestamps. "
             "Uses PyExifTool (if installed) or Pillow/mutagen pure-Python fallbacks. Features selective EXIF stripping "
             "to anonymize images, XMP edit history timeline plots, and batch field writing."),
            
            ("Hardware Diagnostics", 
             "Reads hardware details (motherboard, chipset, BIOS, CPU architecture, RAM, and network speeds) "
             "to compile a comprehensive system report. Includes an Upgrade Advisor that identifies potential bottle-necks "
             "and suggests hardware component upgrades."),
            
            ("Forensics Lab", 
             "Contains advanced digital forensics workflows including cryptographic hash calculations, SAM/shadow password "
             "hash extractions, and OS artifact parsing (WTMP logins, cron jobs, etc.). Also supports mounting and "
             "fully ingesting raw disk images.")
        ]

        for title, desc in guides:
            card = CollapsibleCard(help_group, title=title, expanded=False)
            card_layout = QVBoxLayout(card.get_body())
            card_layout.setContentsMargins(5, 5, 5, 5)
            
            lbl_desc = QLabel(desc, card.get_body())
            lbl_desc.setWordWrap(True)
            lbl_desc.setProperty("class", "muted")
            lbl_desc.setStyleSheet(f"font-size: {TYPE_SCALE['body']}px; line-height: 1.4;")
            card_layout.addWidget(lbl_desc)
            
            help_layout.addWidget(card)

        scroll_layout.addWidget(help_group)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

    def get_help_text(self) -> str:
        return (
            "About & Help View\n\n"
            "This view contains general information about the application, your current system diagnostics, "
            "and a quick start guide for each of the tools included in the suite.\n\n"
            "If you need deep forensics or cleanup assistance, open the corresponding guides under the "
            "Application Features Guide section."
        )
