"""
Storage & Devices GUI view.

Surfaces ``fm devices`` in the GUI: lists every connected storage
device with filesystem, total/used/free space, and mount point, and
shows the full per-device breakdown (type, options, percentage used)
on demand. The same code path (``device_manager.list_storage_devices``
/ ``get_device_info``) drives the CLI ``fm devices`` command so the
two stay in lockstep.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PyQt5.QtCore import Qt

from .base import BaseView
from ..theme_tokens import TYPE_SCALE
from ...modules.device_manager import (
    list_storage_devices,
    get_device_info,
    DEVICE_TYPE_UNKNOWN,
)


_EM_DASH = "\u2014"


class StorageDevicesView(BaseView):
    TOOLTIP_TEXTS = {
        "refresh": "Re-scan the system for connected storage devices and update the table.",
        "details": "Show a detailed breakdown (filesystem options, raw bytes, percent used) for the selected device.",
    }

    def get_title(self):
        return "Storage & Devices"

    def __init__(self, master, app=None):
        super().__init__(master, app)
        self.devices = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        header = QWidget(self)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 5)

        self.btn_refresh = QPushButton("\U0001f504 Refresh", header)
        self.btn_refresh.setProperty("variant", "primary")
        self.btn_refresh.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.btn_refresh.clicked.connect(self._refresh)
        h_layout.addWidget(self.btn_refresh)

        self.btn_details = QPushButton("\U0001f4c4 Show Details", header)
        self.btn_details.clicked.connect(self._show_details)
        h_layout.addWidget(self.btn_details)

        h_layout.addStretch()
        self.lbl_status = QLabel("Click 'Refresh' to list storage devices.", header)
        self.lbl_status.setProperty("class", "muted")
        h_layout.addWidget(self.lbl_status)
        layout.addWidget(header)

        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Mount point", "Type", "Filesystem", "Used", "Total",
        ])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.doubleClicked.connect(self._show_details)
        layout.addWidget(self.table, 1)

        self.details_panel = QLabel("", self)
        self.details_panel.setProperty("class", "muted")
        self.details_panel.setStyleSheet(f"font-size: {TYPE_SCALE['body']}px; padding: 8px;")
        self.details_panel.setWordWrap(True)
        self.details_panel.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.details_panel.setVisible(False)
        layout.addWidget(self.details_panel)

        self._init_tooltips()

    def mount(self):
        if not self.devices:
            self._refresh()

    def _refresh(self):
        self.lbl_status.setText("Scanning storage devices...")
        try:
            self.devices = list_storage_devices()
        except Exception as exc:
            self.devices = []
            self.lbl_status.setText(f"Scan failed: {exc}")
            return
        self._populate_table()
        if not self.devices:
            self.lbl_status.setText("No storage devices detected.")
        else:
            self.lbl_status.setText(f"{len(self.devices)} storage device(s) detected.")

    def _populate_table(self):
        self.table.setRowCount(0)
        for dev in self.devices:
            row = self.table.rowCount()
            self.table.insertRow(row)
            mount = dev.get("mountpoint", _EM_DASH)
            dev_type = dev.get("type", DEVICE_TYPE_UNKNOWN)
            fstype = dev.get("fstype", _EM_DASH)
            used = dev.get("formatted_used", _EM_DASH)
            total = dev.get("formatted_total", _EM_DASH)
            self.table.setItem(row, 0, QTableWidgetItem(mount))
            self.table.setItem(row, 1, QTableWidgetItem(dev_type))
            self.table.setItem(row, 2, QTableWidgetItem(fstype))
            self.table.setItem(row, 3, QTableWidgetItem(used))
            self.table.setItem(row, 4, QTableWidgetItem(total))

    def _show_details(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.devices):
            return
        mount = self.devices[row].get("mountpoint", "")
        info = get_device_info(mount) or self.devices[row]
        if not info:
            return
        self.details_panel.setVisible(True)
        self.details_panel.setText(self._format_details(info))

    def _format_details(self, info):
        rows = []
        for key in ("mountpoint", "device", "type", "fstype", "opts"):
            value = info.get(key, _EM_DASH)
            rows.append(f"<b>{key}:</b> {value}")
        if "formatted_total" in info:
            rows.append(
                f"<b>Usage:</b> {info.get('formatted_used', _EM_DASH)} used "
                f"/ {info.get('formatted_total', _EM_DASH)} total "
                f"({info.get('percent_used', 0)}%)"
            )
        if "error" in info:
            rows.append(f"<b>Note:</b> {info['error']}")
        return "<br>".join(rows)

    def _init_tooltips(self):
        from ..widgets import attach_tooltips
        attach_tooltips([
            (self.btn_refresh, self.TOOLTIP_TEXTS["refresh"]),
            (self.btn_details, self.TOOLTIP_TEXTS["details"]),
        ])


__all__ = ["StorageDevicesView"]
