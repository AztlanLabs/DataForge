import os
import subprocess
import sys
import math
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QMenu, QMessageBox, QDialog,
    QLineEdit, QGroupBox, QTextEdit, QApplication, QSizePolicy,
    QGridLayout, QCheckBox, QSpinBox, QComboBox, QLayout
)
from PyQt5.QtCore import Qt, QSize, QRect, QPoint
from PyQt5.QtGui import QPixmap, QImage, QPainter, QFont, QColor

from . import dialogs
from ..core.config import config
from ..core.services import FileActionService
from ..core.logger import logger
from ..core.utils import categorize_extension, CATEGORY_COLORS


# Optional imports for richer previews. Each is wrapped in try/except so
# the preview panel still degrades to a text/info fallback when an
# optional dependency is not installed.
try:
    from pypdf import PdfReader  # type: ignore
    _HAS_PYPDF = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_PYPDF = False

try:
    import mutagen  # type: ignore
    _HAS_MUTAGEN = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_MUTAGEN = False

try:
    import fitz  # type: ignore  # PyMuPDF - renders PDF pages to images
    _HAS_FITZ = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_FITZ = False

try:
    import cv2  # type: ignore  # opencv-python-headless - extracts video frames
    _HAS_CV2 = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_CV2 = False

try:
    from ..modules.file_signatures import identify_file_type  # type: ignore
    _HAS_FILE_SIGS = True
except Exception:  # pragma: no cover - lazily imported module group
    _HAS_FILE_SIGS = False


# Short glyphs drawn onto a generated colored badge when no real thumbnail/
# rendering is available for a file type (see FilePreviewPanel._category_icon).
_CATEGORY_GLYPHS = {
    "Documents": "DOC",
    "Images": "IMG",
    "Videos": "▶",   # ▶
    "Audio": "♪",    # ♪
    "Archives": "ZIP",
    "Code": "<>",
    "Other": "?",
}


_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.ico',
               '.tiff', '.tif', '.svg'}
_TEXT_EXTS = {'.txt', '.py', '.json', '.xml', '.md', '.csv', '.log', '.bat',
              '.sh', '.js', '.css', '.html', '.htm', '.ini', '.cfg', '.toml',
              '.yaml', '.yml', '.c', '.cpp', '.h', '.hpp', '.java', '.rs',
              '.rb', '.go', '.ts', '.tsx', '.jsx', '.sql', '.lua', '.php'}
_PDF_EXTS = {'.pdf'}
_AUDIO_EXTS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.opus'}
_VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.mpg', '.mpeg',
               '.wmv', '.ts', '.3gp', '.flv'}
_ARCHIVE_EXTS = {'.zip', '.rar', '.7z', '.gz', '.tar', '.tgz', '.bz2', '.xz'}
_EXE_EXTS = {'.exe', '.dll', '.so', '.bin', '.elf', '.app'}
_DB_EXTS = {'.db', '.sqlite', '.sqlite3', '.db3'}

def _normalize_tree_path(value):
    if not isinstance(value, str):
        return None

    raw_value = value.strip()
    if not raw_value:
        return None

    normalized_value = os.path.normpath(os.path.abspath(os.path.expanduser(raw_value)))
    if os.path.exists(normalized_value) or os.path.isabs(raw_value):
        return normalized_value
    return None


class HoverTooltip:
    def __init__(self, widget, text):
        if widget is not None and text:
            widget.setToolTip(text)


def attach_tooltips(widget_text_pairs):
    for widget, text in widget_text_pairs:
        if widget is not None and text:
            widget.setToolTip(text)


class CollapsibleCard(QWidget):
    """
    A professional-looking card with a header, toggle button, and collapsible body.
    """
    def __init__(self, master=None, title="", expanded=True):
        super().__init__(master)
        
        self.is_expanded = expanded
        self.title_text = title
        
        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        
        # Inner Frame
        self.inner = QFrame(self)
        self.inner.setFrameShape(QFrame.StyledPanel)
        self.inner_layout = QVBoxLayout(self.inner)
        self.inner_layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(self.inner)
        
        # Header
        self.header = QWidget(self.inner)
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        self.lbl_title = QLabel(title, self.header)
        self.lbl_title.setStyleSheet("font-weight: bold;")
        self.header_layout.addWidget(self.lbl_title)
        
        # Push everything else to the right
        self.header_layout.addStretch(1)
        
        # Controls (horizontal area for additions)
        self.controls = QWidget(self.header)
        self.controls_layout = QHBoxLayout(self.controls)
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_layout.setSpacing(6)
        self.header_layout.addWidget(self.controls)
        
        # Toggle Button
        self.btn_toggle = QPushButton("▼" if expanded else "▶", self.header)
        self.btn_toggle.setFixedWidth(30)
        self.btn_toggle.setStyleSheet("border: none; background: transparent; font-size: 14px; font-weight: bold;")
        self.btn_toggle.clicked.connect(self.toggle)
        self.header_layout.addWidget(self.btn_toggle)
        
        self.inner_layout.addWidget(self.header)
        
        # Body Container
        self.body = QWidget(self.inner)
        self.inner_layout.addWidget(self.body)
        
        self.body.setVisible(expanded)

    def toggle(self):
        self.is_expanded = not self.is_expanded
        self.body.setVisible(self.is_expanded)
        self.btn_toggle.setText("▼" if self.is_expanded else "▶")

    def get_body(self):
        return self.body
    
    def add_widget_to_header(self, widget_cls, **kwargs):
        text = kwargs.pop("text", "")
        w = widget_cls(self.controls)
        if text and hasattr(w, "setText"):
            w.setText(text)
        if hasattr(w, "setSizePolicy"):
            w.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.controls_layout.addWidget(w)
        return w


class FlowLayout(QLayout):
    """
    Lays out child widgets left-to-right, wrapping to a new line when a row
    runs out of horizontal space (button toolbars with a variable/growing
    number of entries should use this instead of QHBoxLayout, which never
    wraps and just overflows past the visible window edge on narrow windows).
    """
    def __init__(self, parent=None, margin=0, hspacing=6, vspacing=6):
        super().__init__(parent)
        self._hspacing = hspacing
        self._vspacing = vspacing
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(left, top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._hspacing
            if next_x - self._hspacing > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y += line_height + self._vspacing
                next_x = x + hint.width() + self._hspacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))

            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + bottom


class _HeightForWidthMixin:
    """
    Qt's height-for-width propagation through more than one level of nested
    layouts (e.g. a wrapping FlowLayout, or a word-wrapped QLabel, sitting
    inside a QWidget/QFrame that is itself inside another layout — the
    Action Builder toolbar and step cards both do this) is unreliable and
    tends to clip wrapped content to a single row's height. Recomputing and
    applying the needed height directly on every resize sidesteps that
    limitation entirely instead of depending on virtual heightForWidth calls
    reaching all the way up an arbitrarily deep widget tree.
    """
    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        if self.layout():
            return self.layout().heightForWidth(width)
        return super().heightForWidth(width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.layout():
            needed = self.layout().heightForWidth(event.size().width())
            if needed >= 0 and needed != self.minimumHeight():
                self.setMinimumHeight(needed)


class FlowContainer(_HeightForWidthMixin, QWidget):
    """QWidget variant, for wrapping a FlowLayout (see Action Builder's toolbar)."""
    pass


class ElidingLabel(QLabel):
    """
    A single-line QLabel that elides ("...") text that doesn't fit its
    current width, showing the full text via tooltip, instead of word-wrapping
    (which requires unreliable height-for-width propagation through nested
    layouts) or silently clipping/overflowing.
    """
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setFullText(text)

    def setFullText(self, text):
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._update_elided_text()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided_text()

    def _update_elided_text(self):
        elided = self.fontMetrics().elidedText(self._full_text, Qt.ElideRight, max(self.width(), 0))
        super().setText(elided)


class NormalizeRulesWidget(QWidget):
    """
    Exposes every core.utils.normalize_filename() knob as bound controls.
    Shared by the Action Builder's NormalizeNameStep and the Batch Renamer tab
    so both behave identically. Widgets write into `params` (a plain dict);
    execute() paths must only ever read `params` via kwargs_from_params(),
    never hold a reference to this widget across the worker-thread boundary.
    """
    def __init__(self, parent=None, params=None):
        super().__init__(parent)
        self.params = params if params is not None else {}

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.chk_strip_dot = QCheckBox("Strip leading '.'", self)
        self.chk_strip_dot.setToolTip("Removes a leading '.' from filenames that have one, e.g. '.file342.txt' -> 'file342.txt'.")
        self.chk_strip_dot.setChecked(self.params.get("strip_leading_dot", False))
        self.chk_strip_dot.stateChanged.connect(lambda v: self.params.update({"strip_leading_dot": bool(v)}))
        layout.addWidget(self.chk_strip_dot, 0, 0)

        layout.addWidget(QLabel("Case:", self), 0, 2)
        self.case_combo = QComboBox(self)
        self.case_combo.addItems(["none", "lower", "upper", "title"])
        self.case_combo.setCurrentText(self.params.get("case_mode", "none"))
        self.case_combo.currentTextChanged.connect(lambda t: self.params.update({"case_mode": t}))
        layout.addWidget(self.case_combo, 0, 3)

        layout.addWidget(QLabel("Find:", self), 1, 0)
        self.find_edit = QLineEdit(self.params.get("find_text", ""), self)
        self.find_edit.textChanged.connect(lambda t: self.params.update({"find_text": t}))
        layout.addWidget(self.find_edit, 1, 1)

        self.chk_use_regex = QCheckBox("Regex", self)
        self.chk_use_regex.setChecked(self.params.get("use_regex", False))
        self.chk_use_regex.stateChanged.connect(lambda v: self.params.update({"use_regex": bool(v)}))
        layout.addWidget(self.chk_use_regex, 1, 2)

        layout.addWidget(QLabel("Replace:", self), 1, 3)
        self.replace_edit = QLineEdit(self.params.get("replace_text", ""), self)
        self.replace_edit.textChanged.connect(lambda t: self.params.update({"replace_text": t}))
        layout.addWidget(self.replace_edit, 1, 4)

        lbl_numeric_pattern = QLabel("Numeric:", self)
        lbl_numeric_pattern.setToolTip("Regex pattern matching the numeric run(s) to replace, e.g. \\d+")
        layout.addWidget(lbl_numeric_pattern, 2, 0)
        self.numeric_pattern_edit = QLineEdit(self.params.get("numeric_pattern", ""), self)
        self.numeric_pattern_edit.setToolTip("Regex pattern matching the numeric run(s) to replace, e.g. \\d+")
        self.numeric_pattern_edit.textChanged.connect(lambda t: self.params.update({"numeric_pattern": t}))
        layout.addWidget(self.numeric_pattern_edit, 2, 1)

        lbl_numeric_replacement = QLabel("Replace with:", self)
        lbl_numeric_replacement.setToolTip("{n} is substituted with the sequential counter, optionally zero-padded.")
        layout.addWidget(lbl_numeric_replacement, 2, 2)
        self.numeric_replacement_edit = QLineEdit(self.params.get("numeric_replacement", ""), self)
        self.numeric_replacement_edit.setToolTip("{n} is substituted with the sequential counter, optionally zero-padded.")
        self.numeric_replacement_edit.textChanged.connect(lambda t: self.params.update({"numeric_replacement": t}))
        layout.addWidget(self.numeric_replacement_edit, 2, 3)

        layout.addWidget(QLabel("Pad width:", self), 2, 4)
        self.numeric_pad_spin = QSpinBox(self)
        self.numeric_pad_spin.setRange(0, 10)
        self.numeric_pad_spin.setValue(int(self.params.get("numeric_pad", 0) or 0))
        self.numeric_pad_spin.valueChanged.connect(lambda v: self.params.update({"numeric_pad": v}))
        layout.addWidget(self.numeric_pad_spin, 2, 5)

        self.chk_collapse = QCheckBox("Collapse separators", self)
        self.chk_collapse.setToolTip("Collapses runs of spaces/underscores/hyphens into a single underscore.")
        self.chk_collapse.setChecked(self.params.get("collapse_separators", False))
        self.chk_collapse.stateChanged.connect(lambda v: self.params.update({"collapse_separators": bool(v)}))
        layout.addWidget(self.chk_collapse, 3, 0)

        layout.addWidget(QLabel("Prefix:", self), 3, 1)
        self.prefix_edit = QLineEdit(self.params.get("prefix", ""), self)
        self.prefix_edit.textChanged.connect(lambda t: self.params.update({"prefix": t}))
        layout.addWidget(self.prefix_edit, 3, 2)

        layout.addWidget(QLabel("Suffix:", self), 3, 3)
        self.suffix_edit = QLineEdit(self.params.get("suffix", ""), self)
        self.suffix_edit.textChanged.connect(lambda t: self.params.update({"suffix": t}))
        layout.addWidget(self.suffix_edit, 3, 4)

    @staticmethod
    def kwargs_from_params(params: dict) -> dict:
        return {
            "strip_leading_dot": params.get("strip_leading_dot", False),
            "find_text": params.get("find_text", ""),
            "replace_text": params.get("replace_text", ""),
            "use_regex": params.get("use_regex", False),
            "numeric_pattern": params.get("numeric_pattern", ""),
            "numeric_replacement": params.get("numeric_replacement", ""),
            "numeric_pad": int(params.get("numeric_pad", 0) or 0),
            "case_mode": params.get("case_mode", "none"),
            "collapse_separators": params.get("collapse_separators", False),
            "prefix": params.get("prefix", ""),
            "suffix": params.get("suffix", ""),
        }


class EnhancedTreeview(QWidget):
    """
    Treeview wrapper using QTreeWidget with sorting, context menu, and compatibility methods.
    """
    def __init__(self, master, columns, app=None, on_file_action=None, **kwargs):
        super().__init__(master)
        self.app = app
        self._on_file_action = on_file_action
        # Optional resolver: a callable (item_id) -> "session-key" that the
        # owning view can map back to a full filesystem path. Trees whose
        # visible columns are not file paths (Forensics hash list, etc.)
        # use this so right-click Open/Copy/Move actions still work.
        self._path_resolver = None
        # When True (set by the owning view) the right-click file-system
        # actions (Open File, Open Location, Rename, Move, Copy, Delete,
        # Exclude Extension) are hidden because the rows do not represent
        # filesystem entries. Pure copy-cell actions remain available.
        self._no_file_actions = False
        self._item_path_role = {}  # item_id -> full path override

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # QTreeWidget
        self.tree = QTreeWidget(self)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        # Elide long cell text from the LEFT (not Qt's default right-elide).
        # File paths put the most useful part — the filename — at the end,
        # so eliding from the right ("C:/very/long/path/pref...") hides
        # exactly the part users need to read; left-eliding ("...file.txt")
        # keeps it visible regardless of column width.
        self.tree.setTextElideMode(Qt.ElideLeft)

        # Connect Context Menu
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)

        # Double Click Action
        self.tree.itemDoubleClicked.connect(self.on_double_click)

        layout.addWidget(self.tree)

        # Set Columns Setup
        self.col_indices = {}
        for idx, col in enumerate(columns):
            self.col_indices[col] = idx
        self.col_indices["#0"] = 0

        self.tree.setColumnCount(len(columns))
        self.tree.setHeaderLabels(list(columns))

        # Track dynamic section commands and mapped items
        self._header_commands = {}
        self.tree.header().sectionClicked.connect(self._on_header_clicked)
        self.item_map = {}

    def set_path_resolver(self, resolver):
        """Register a callable(item_id) -> full path / None so right-click
        file actions work for trees whose visible columns are not file paths
        (e.g. the Forensics hash tree, which only shows a basename)."""
        self._path_resolver = resolver

    def set_item_path(self, item_id, path):
        """Attach (override) the resolved filesystem path for a single row,
        independent of the visible column data."""
        if path:
            self._item_path_role[item_id] = path
        else:
            self._item_path_role.pop(item_id, None)

    def set_no_file_actions(self, flag=True):
        """Hide Open/Rename/Move/Copy/Delete/Exclude actions on the right
        click menu for trees that don't represent filesystem rows."""
        self._no_file_actions = flag

    def _on_header_clicked(self, logical_index):
        cmd = self._header_commands.get(logical_index)
        if cmd:
            cmd()

    def _show_error(self, title, message):
        if self.app:
            self.app.show_error_dialog(title, message)
        else:
            QMessageBox.critical(self, title, message)

    def _show_warning(self, title, message):
        if self.app:
            self.app.show_warning_dialog(title, message)
        else:
            QMessageBox.warning(self, title, message)

    def _show_info(self, title, message):
        if self.app:
            self.app.show_info_dialog(title, message)
        else:
            QMessageBox.information(self, title, message)
        
    # Proxy Compatibility Methods -----------------------
    def heading(self, column, text=None, command=None, **kwargs):
        col_idx = self.col_indices.get(column, 0)
        if text is not None:
            self.tree.headerItem().setText(col_idx, text)
        if command is not None:
            self._header_commands[col_idx] = command
        
    def column(self, column, width=None, minwidth=None, stretch=None, **kwargs):
        col_idx = self.col_indices.get(column, 0)
        if width is not None:
            self.tree.setColumnWidth(col_idx, width)
        if stretch:
            self.tree.header().setSectionResizeMode(col_idx, QHeaderView.Stretch)
        
    def insert(self, parent, index, iid=None, text="", values=(), **kwargs):
        path_override = kwargs.pop("path", None)
        if not iid:
            iid = f"item_{id(self)}_{len(self.item_map)}"

        item = QTreeWidgetItem()
        item.setData(0, Qt.UserRole, iid)

        if values:
            for col_idx, val in enumerate(values):
                if col_idx < self.tree.columnCount():
                    item.setText(col_idx, str(val))
        else:
            item.setText(0, str(text))

        if parent == "" or parent is None:
            self.tree.addTopLevelItem(item)
        else:
            parent_item = self.item_map.get(parent)
            if parent_item:
                parent_item.addChild(item)

        self.item_map[iid] = item
        # Explicit per-row path override (path resolver / set_item_path wins)
        if path_override is not None:
            self._item_path_role[iid] = path_override
        return iid
        
    def delete(self, *items):
        for item_id in items:
            item = self.item_map.pop(item_id, None)
            self._item_path_role.pop(item_id, None)
            if item:
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
                else:
                    index = self.tree.indexOfTopLevelItem(item)
                    if index >= 0:
                        self.tree.takeTopLevelItem(index)
        
    def get_children(self, parent_id=None):
        if not parent_id or parent_id == "":
            children = []
            for idx in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(idx)
                children.append(item.data(0, Qt.UserRole))
            return children
        else:
            parent_item = self.item_map.get(parent_id)
            if not parent_item:
                return []
            children = []
            for idx in range(parent_item.childCount()):
                item = parent_item.child(idx)
                children.append(item.data(0, Qt.UserRole))
            return children
        
    def set(self, item_id, column, value=None):
        item = self.item_map.get(item_id)
        if not item:
            return ""
        col_idx = self.col_indices.get(column, 0)
        if value is not None:
            item.setText(col_idx, str(value))
        else:
            return item.text(col_idx)
        
    def item(self, item_id, option=None, **kwargs):
        item = self.item_map.get(item_id)
        if not item:
            if option == "open":
                return False
            return {'text': '', 'values': []}
        
        if 'open' in kwargs:
            item.setExpanded(bool(kwargs['open']))
            
        if option == "open":
            return item.isExpanded()
            
        col_count = self.tree.columnCount()
        vals = [item.text(col) for col in range(col_count)]
        
        if option == 'values':
            return vals
        elif option == 'text':
            return item.text(0)
            
        return {
            'text': item.text(0),
            'values': vals,
            'open': item.isExpanded()
        }
        
    def selection(self):
        selected_items = self.tree.selectedItems()
        return [item.data(0, Qt.UserRole) for item in selected_items]
        
    def selection_set(self, items):
        self.tree.clearSelection()
        for item_id in items:
            item = self.item_map.get(item_id)
            if item:
                item.setSelected(True)

    def focus(self, item_id=None):
        if item_id is None:
            curr = self.tree.currentItem()
            return curr.data(0, Qt.UserRole) if curr else ""
        item = self.item_map.get(item_id)
        if item:
            self.tree.setCurrentItem(item)

    def see(self, item_id):
        item = self.item_map.get(item_id)
        if item:
            self.tree.scrollToItem(item)
        
    def move(self, item_id, parent_id, index):
        item = self.item_map.get(item_id)
        if not item:
            return
            
        # Remove from previous parent
        old_parent = item.parent()
        if old_parent:
            old_parent.removeChild(item)
        else:
            idx = self.tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self.tree.takeTopLevelItem(idx)
                
        # Insert under new parent
        if parent_id == "" or parent_id is None:
            self.tree.insertTopLevelItem(index, item)
        else:
            parent_item = self.item_map.get(parent_id)
            if parent_item:
                parent_item.insertChild(index, item)
    
    def identify_row(self, y):
        # Kept for compatibility. In Qt, y-coordinate maps to items.
        item = self.tree.itemAt(0, y)
        return item.data(0, Qt.UserRole) if item else ""

    def bind(self, sequence=None, func=None, add=None):
        # Compatibility method. Real Qt actions bound directly in methods.
        pass
        
    def unbind(self, sequence, funcid=None):
        pass

    def restore_selection(self, item_ids):
        self.tree.clearSelection()
        primary = None
        for item_id in item_ids:
            item = self.item_map.get(item_id)
            if item:
                item.setSelected(True)
                if not primary:
                    primary = item
        if primary:
            self.tree.setCurrentItem(primary)
            self.tree.scrollToItem(primary)

    # Clipboard Helpers -------------------
    def clipboard_clear(self):
        QApplication.clipboard().clear()

    def clipboard_append(self, text):
        QApplication.clipboard().setText(text)

    def clipboard_copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)

    # Internal Actions ----------------------
    def sort_by(self, col, descending):
        # Native QTreeWidget sorting
        self.tree.sortItems(self.col_indices.get(col, 0), Qt.DescendingOrder if descending else Qt.AscendingOrder)

    def show_context_menu(self, pos):
        # customContextMenuRequested emits viewport-relative coords, which is
        # exactly what QTreeWidget.itemAt expects — so pos can be passed
        # through directly. Mapping naively to widget coords here breaks
        # the top rows because the QTreeWidget includes the header height
        # in widget coords but not in viewport coords.
        item = self.tree.itemAt(pos)
        if not item:
            return

        iid = item.data(0, Qt.UserRole)
        # Preserve multi-selection when the right-clicked row is already
        # part of it; otherwise fall back to selecting just that row.
        if iid not in self.selection():
            self.selection_set([iid])

        menu = QMenu(self)

        path = self.get_selected_path()
        has_path = bool(path)

        if not self._no_file_actions:
            open_act = menu.addAction("Open File")
            open_act.setEnabled(has_path)
            open_act.triggered.connect(self.open_file)

            open_loc_act = menu.addAction("Open Location")
            open_loc_act.setEnabled(has_path)
            open_loc_act.triggered.connect(self.open_location)

            menu.addSeparator()

            rename_act = menu.addAction("Rename")
            rename_act.setEnabled(has_path)
            rename_act.triggered.connect(self.rename_file)

            move_act = menu.addAction("Move To...")
            move_act.setEnabled(has_path)
            move_act.triggered.connect(self.move_to)

            copy_act = menu.addAction("Copy To...")
            copy_act.setEnabled(has_path)
            copy_act.triggered.connect(self.copy_to)

            delete_act = menu.addAction("Delete")
            delete_act.setEnabled(has_path)
            delete_act.triggered.connect(self.delete_file)

            menu.addSeparator()

        # Dynamic copies of column data
        col_count = self.tree.columnCount()
        idx_to_col = {v: k for k, v in self.col_indices.items()}
        for col_idx in range(col_count):
            col_name = idx_to_col.get(col_idx, f"Col {col_idx}")
            header_text = self.tree.headerItem().text(col_idx)
            if not header_text:
                header_text = col_name.title()
            val = item.text(col_idx)

            label = f"Copy {header_text}"
            act = menu.addAction(label)
            act.triggered.connect(lambda checked, text=val: self.clipboard_copy(text))

        menu.addSeparator()

        if not self._no_file_actions:
            exclude_act = menu.addAction("Exclude Extension")
            exclude_act.setEnabled(has_path)
            exclude_act.triggered.connect(self.exclude_ext)

            menu.addSeparator()

            copy_path_act = menu.addAction("Copy Full Path")
            copy_path_act.setEnabled(has_path)
            copy_path_act.triggered.connect(self.copy_path)

            copy_name_act = menu.addAction("Copy File Name")
            copy_name_act.setEnabled(has_path)
            copy_name_act.triggered.connect(self.copy_name)

        if not has_path and not self._no_file_actions:
            menu.addAction("(No file path on this row)").setEnabled(False)

        menu.exec_(self.tree.viewport().mapToGlobal(pos))

    def on_double_click(self, item, column):
        self.open_file()

    def get_selected_path(self):
        selected = self.selection()
        if not selected:
            return None
        return self.get_item_path(selected[0])

    def get_item_path(self, iid):
        """
        Resolves the real filesystem path for an arbitrary row (not just the
        current selection) — use this instead of reading a "path" column's
        displayed text directly, since that text may be a formatted/relative
        display string (see core.utils.format_display_path) rather than a
        usable path once a row was inserted with an explicit path= override.
        """
        # 1. Explicit per-row path override (set via insert(path=...) /
        #    set_item_path). Highest priority, used by trees whose visible
        #    columns are not paths (or show a formatted/relative string).
        explicit = self._item_path_role.get(iid)
        if explicit and os.path.exists(explicit):
            return explicit
        if explicit and os.path.isabs(explicit):
            return os.path.normpath(explicit)

        # 2. Caller-supplied path resolver (maps item id -> full path).
        if self._path_resolver is not None:
            try:
                resolved = self._path_resolver(iid)
            except Exception:
                resolved = None
            if resolved:
                normalized = _normalize_tree_path(resolved)
                if normalized:
                    return normalized

        # 3. Fall back to scanning the visible row cells for a path.
        item_vals = self.item(iid)['values']
        # Also check the first column text
        first_col = self.item(iid)['text']

        for val in [first_col] + item_vals:
            normalized_path = _normalize_tree_path(val)
            if normalized_path:
                return normalized_path
        return None

    def _no_path_warning(self):
        self._show_warning("No File Path", "This row has no resolvable file path, so the action is unavailable.")

    def open_file(self):
        path = self.get_selected_path()
        if not path:
            self._no_path_warning()
            return
        if not os.path.exists(path):
            self._show_warning("Not Found", f"File does not exist anymore:\n{path}")
            return
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.call(['open', path])
            else:
                subprocess.call(['xdg-open', path])
        except Exception as e:
            self._show_error("Error", f"Could not open file: {e}")

    def open_location(self):
        path = self.get_selected_path()
        if not path:
            self._no_path_warning()
            return
        folder = os.path.dirname(path)
        if not os.path.exists(folder):
            self._show_warning("Not Found", f"Folder does not exist:\n{folder}")
            return
        try:
            if sys.platform == 'win32':
                os.startfile(folder)
            elif sys.platform == 'darwin':
                subprocess.call(['open', folder])
            else:
                subprocess.call(['xdg-open', folder])
        except Exception as e:
            self._show_error("Error", f"Could not open folder: {e}")

    def copy_path(self):
        path = self.get_selected_path()
        if not path:
            self._no_path_warning()
            return
        self.clipboard_copy(path)

    def copy_name(self):
        path = self.get_selected_path()
        if not path:
            self._no_path_warning()
            return
        self.clipboard_copy(os.path.basename(path))

    def _run_or_inline(self, action_fn, on_complete, error_title="Action Failed"):
        """
        Runs `action_fn` (a zero-arg callable performing the actual file
        operation) via the app's background-threading system when available,
        so a single large-file rename/delete/move/copy from this context
        menu doesn't freeze the UI the way the equivalent bulk action (which
        always goes through run_workflow) doesn't. Falls back to a direct
        synchronous call if this tree has no `app` reference.
        """
        if self.app is not None and hasattr(self.app, "run_workflow"):
            self.app.run_workflow(action_fn, on_complete, error_title=error_title)
        else:
            on_complete(action_fn())

    def rename_file(self):
        path = self.get_selected_path()
        if not path:
            self._no_path_warning()
            return

        new_name = self._ask_rename_custom(os.path.basename(path))
        if not new_name:
            return
        if self._on_file_action:
            self._on_file_action("rename", path, new_name=new_name)
            return

        def _do_rename():
            return FileActionService.rename_items([path], lambda _path, _index: new_name, dry_run=False)

        def _on_done(outcome):
            record = outcome.records[0] if outcome.records else None
            if record and record.success:
                self._show_info("Success", "File renamed. Please refresh search.")
            elif record and not record.skipped:
                self._show_error("Error", record.message)

        self._run_or_inline(_do_rename, _on_done, error_title="Rename Failed")

    def _ask_rename_custom(self, old_name):
        dialog = QDialog(self)
        dialog.setWindowTitle("Rename File")
        dialog.resize(500, 200)
        
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel("Current Name:"))
        lbl_current = QLabel(old_name)
        lbl_current.setStyleSheet("font-family: Consolas; font-weight: bold;")
        layout.addWidget(lbl_current)
        
        layout.addWidget(QLabel("New Name:"))
        entry = QLineEdit(dialog)
        entry.setText(old_name)
        entry.selectAll()
        entry.setFocus()
        layout.addWidget(entry)
        
        _, ext = os.path.splitext(old_name)
        if ext:
            layout.addWidget(QLabel(f"Keep extension: {ext}"))
            
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel", dialog)
        btn_cancel.clicked.connect(dialog.reject)
        btn_ok = QPushButton("Rename", dialog)
        btn_ok.clicked.connect(dialog.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)
        
        if dialog.exec_() == QDialog.Accepted:
            return entry.text().strip()
        return None

    def delete_file(self):
        path = self.get_selected_path()
        if not path:
            self._no_path_warning()
            return

        reply = QMessageBox.question(
            self,
            "Delete",
            f"Delete {os.path.basename(path)}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        if self._on_file_action:
            self._on_file_action("delete", path)
            return

        # Capture the item to remove now — by the time a background delete
        # of a large file completes, the user's live selection may differ.
        sel = self.selection()
        item_id = sel[0] if sel else None

        def _do_delete():
            return FileActionService.delete_items([path], dry_run=False, safe_mode=config.get("safe_mode", True))

        def _on_done(outcome):
            record = outcome.records[0] if outcome.records else None
            if record and record.success:
                if item_id:
                    self.delete(item_id)
            elif record:
                self._show_error("Error", record.message)

        self._run_or_inline(_do_delete, _on_done, error_title="Delete Failed")

    def exclude_ext(self):
        path = self.get_selected_path()
        if not path:
            self._no_path_warning()
            return

        _, ext = os.path.splitext(path)
        if not ext:
            self._show_info("No Extension", "This file has no extension to exclude.")
            return
        
        reply = QMessageBox.question(
            self,
            "Exclude",
            f"Exclude all {ext} files?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            current = config.get("excluded_extensions", [])
            if ext not in current:
                current.append(ext)
                config.set("excluded_extensions", current)
                self._show_info("Excluded", f"{ext} added to exclusions. Please refresh.")
                
    def move_to(self):
        path = self.get_selected_path()
        if not path:
            self._no_path_warning()
            return
        dest = dialogs.get_existing_directory(self, "Move to...")
        if not dest:
            return
        if self._on_file_action:
            self._on_file_action("move", path, destination=dest)
            return

        sel = self.selection()
        item_id = sel[0] if sel else None

        def _do_move():
            return FileActionService.transfer_items([path], dest, "move", dry_run=False)

        def _on_done(outcome):
            record = outcome.records[0] if outcome.records else None
            if record and record.success:
                if item_id:
                    self.delete(item_id)
            elif record:
                self._show_error("Error", record.message)

        self._run_or_inline(_do_move, _on_done, error_title="Move Failed")

    def copy_to(self):
        path = self.get_selected_path()
        if not path:
            self._no_path_warning()
            return
        dest = dialogs.get_existing_directory(self, "Copy to...")
        if not dest:
            return
        if self._on_file_action:
            self._on_file_action("copy", path, destination=dest)
            return

        def _do_copy():
            return FileActionService.transfer_items([path], dest, "copy", dry_run=False)

        def _on_done(outcome):
            record = outcome.records[0] if outcome.records else None
            if record and not record.success:
                self._show_error("Error", record.message)

        self._run_or_inline(_do_copy, _on_done, error_title="Copy Failed")


class FilePreviewPanel(QWidget):
    """
    Right-hand content preview for any tree view.

    Supports:
      - images (PNG/JPG/GIF/BMP/WEBP/ICO/TIFF/SVG)      via QPixmap scaling
      - plain text/code (py/json/md/log/ini/...)         via UTF-8 read (4 KB)
      - PDF                                              first-page text via pypdf
      - audio (mp3/flac/ogg/wav/m4a)                    tag dump via mutagen
      - video (mp4/mkv/avi/mov/webm)                    file info + open-in-os button
      - archives (zip/rar/7z/gz/tar)                    top-level entry list
      - executables / databases / unknown identity     magic-byte signature
                                                          + hex lead dump
    Anything else shows file-info + "No Preview Available".

    Larger binary blobs (>40 MB) bypass the binary/heavy preview paths to
    stay snappy inside the UI loop.
    """

    LARGE_FILE_BYTES = 40 * 1024 * 1024
    TEXT_PREVIEW_BYTES = 4 * 1024           # 4 KB text cap
    PDF_PREVIEW_CHARS = 4 * 1024            # 4 KB PDF text cap
    HEX_PREVIEW_BYTES = 128                  # first 128 bytes shown as hex

    def __init__(self, master=None, **kwargs):
        super().__init__(master)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Info Group
        self.f_info = QGroupBox("File Info", self)
        info_layout = QVBoxLayout(self.f_info)

        self.lbl_name = QLabel("No Selection", self.f_info)
        self.lbl_name.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_layout.addWidget(self.lbl_name)

        self.lbl_detail = QLabel("", self.f_info)
        self.lbl_detail.setWordWrap(True)
        info_layout.addWidget(self.lbl_detail)

        layout.addWidget(self.f_info)

        # Content Group
        self.f_content = QGroupBox("Content", self)
        self.content_layout = QVBoxLayout(self.f_content)

        # Shared thumbnail slot: a rendered PDF page, an extracted video
        # frame, or (when neither is available) a generated category badge
        # (see _category_icon). Sits above whatever text/info follows below,
        # so a PDF's page-1 thumbnail can be shown together with its
        # extracted text rather than instead of it.
        self.thumb_lbl = QLabel("", self.f_content)
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        self.thumb_lbl.setVisible(False)
        self.content_layout.addWidget(self.thumb_lbl)

        self.content_lbl = QLabel("", self.f_content)
        self.content_lbl.setAlignment(Qt.AlignCenter)
        self.content_lbl.setStyleSheet("color: #6c757d;")
        self.content_lbl.setWordWrap(True)
        self.content_layout.addWidget(self.content_lbl)

        self.text_edit = QTextEdit(self.f_content)
        self.text_edit.setReadOnly(True)
        self.text_edit.setVisible(False)
        self.text_edit.setStyleSheet(
            "font-family: 'Courier New', Consolas, monospace; font-size: 12px;"
        )
        self.content_layout.addWidget(self.text_edit)

        # Optional action button row (used for video/exe to "Open Externally")
        self.action_row = QWidget(self.f_content)
        self.action_layout = QHBoxLayout(self.action_row)
        self.action_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_open_external = QPushButton("Open Externally", self.action_row)
        self.btn_open_external.clicked.connect(self._open_current_externally)
        self.action_layout.addStretch()
        self.action_layout.addWidget(self.btn_open_external)
        self.action_row.setVisible(False)
        self.content_layout.addWidget(self.action_row)

        layout.addWidget(self.f_content, 1)

        self._current_path = None

    def clear(self):
        self._current_path = None
        self.lbl_name.setText("No Selection")
        self.lbl_detail.setText("")
        self.thumb_lbl.clear()
        self.thumb_lbl.setVisible(False)
        self.content_lbl.clear()
        self.content_lbl.setText("")
        self.content_lbl.setVisible(True)
        self.text_edit.clear()
        self.text_edit.setVisible(False)
        self.action_row.setVisible(False)

    def update_file(self, path, root=None):
        self.clear()
        if not path or not os.path.exists(path):
            self.clear()
            if path:
                self.lbl_name.setText("File Not Found")
                self.content_lbl.setText("File does not exist.")
                self.content_lbl.setVisible(True)
            return

        self._current_path = path

        # Update Info
        try:
            stat = os.stat(path)
            from datetime import datetime
            from ..core.utils import format_size, format_display_path

            name = os.path.basename(path)
            size = format_size(stat.st_size)
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

            self.lbl_name.setText(name)
            # lbl_detail has word-wrap on, so the full/relative path (per the
            # Settings "Path Display" toggle) just wraps instead of needing
            # a crude fixed-length truncation that could hide useful context.
            disp_path = format_display_path(path, root=root)

            info_txt = f"Size: {size}\nDate: {mtime}\nPath: {disp_path}"
            self.lbl_detail.setText(info_txt)
            self.lbl_detail.setToolTip(path)
        except Exception as e:
            self.lbl_detail.setText(f"Error reading stats: {e}")

        # Content preview dispatch. Extension-specific renderers are checked
        # before the _looks_like_text() heuristic: a PDF's raw bytes (header,
        # object dictionaries, xref table) are mostly printable ASCII, so the
        # heuristic previously misfired on many PDFs and routed them to
        # _show_text(), which reads the raw file as UTF-8 — dumping the PDF's
        # binary/compressed stream bytes as replacement-character "garbage"
        # instead of actually parsing the PDF. The heuristic now only
        # applies as a fallback for files with no recognized extension.
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in _IMAGE_EXTS:
                self._show_image(path)
            elif ext in _PDF_EXTS:
                self._show_pdf(path)
            elif ext in _AUDIO_EXTS:
                self._show_audio(path)
            elif ext in _VIDEO_EXTS:
                self._show_video(path, ext)
            elif ext in _ARCHIVE_EXTS:
                self._show_archive(path, ext)
            elif ext in _DB_EXTS:
                self._show_binary_summary(path, ext, kind="Database")
            elif ext in _EXE_EXTS:
                self._show_binary_summary(path, ext, kind="Executable / Library")
            elif ext in _TEXT_EXTS or _looks_like_text(path):
                self._show_text(path)
            else:
                self._show_unknown_or_detected(path, ext)
        except Exception as exc:
            logger.debug(f"preview failed for {path}: {exc}")
            self._set_label_text(f"Preview error: {exc}")

    # ------------------------------------------------------------------
    # Per-type renderers
    # ------------------------------------------------------------------

    def _set_label_text(self, text):
        self.text_edit.setVisible(False)
        self.content_lbl.setPixmap(QPixmap())
        self.content_lbl.setText(text)
        self.content_lbl.setVisible(True)

    def _set_text_preview(self, text):
        self.content_lbl.setVisible(False)
        self.text_edit.setPlainText(text)
        self.text_edit.setVisible(True)

    def _set_thumbnail(self, pixmap):
        """Shows a rendered thumbnail (PDF page, video frame, or category
        badge) above whatever text/info is displayed below it."""
        if pixmap is None or pixmap.isNull():
            self.thumb_lbl.clear()
            self.thumb_lbl.setVisible(False)
            return
        target_width = max(self.f_content.width() - 20, 1)
        scaled = pixmap.scaledToWidth(min(target_width, pixmap.width()), Qt.SmoothTransformation) \
            if pixmap.width() > target_width else pixmap
        self.thumb_lbl.setPixmap(scaled)
        self.thumb_lbl.setVisible(True)

    def _category_icon(self, category, size=96, glyph=None, color=None):
        """
        Generates a flat colored badge (reusing core.utils.CATEGORY_COLORS by
        default) with a short glyph, for file types with no real thumbnail/
        rendering available (video without OpenCV, audio, archives,
        executables, databases, unrecognized binaries). `glyph`/`color` let
        callers override the badge for kinds outside the core category
        taxonomy (e.g. executables/databases, which core.utils treats as
        "Other" for file-organizing purposes but deserve a distinct icon here).
        """
        resolved_color = QColor(color) if color else QColor(CATEGORY_COLORS.get(category, CATEGORY_COLORS["Other"]))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(resolved_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(2, 2, size - 4, size - 4, 14, 14)
        painter.setPen(QColor("#ffffff"))
        font = QFont()
        font.setBold(True)
        font.setPointSize(max(size // 5, 8))
        painter.setFont(font)
        glyph_text = glyph or _CATEGORY_GLYPHS.get(category, category[:3].upper() if category else "?")
        painter.drawText(pixmap.rect(), Qt.AlignCenter, glyph_text)
        painter.end()
        return pixmap

    def _show_image(self, path):
        try:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                self._set_label_text("Image Load Error")
                return
            target = QSize(max(self.f_content.width() - 20, 1),
                           max(self.f_content.height() - 40, 1))
            scaled_pixmap = pixmap.scaled(
                target,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.text_edit.setVisible(False)
            self.content_lbl.setPixmap(scaled_pixmap)
            self.content_lbl.setText("")
            self.content_lbl.setVisible(True)
        except Exception as e:
            self._set_label_text(f"Image Error: {e}")

    def _show_text(self, path):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                txt = f.read(self.TEXT_PREVIEW_BYTES)
            self._set_text_preview(txt)
        except Exception as e:
            self._set_text_preview(f"Read Error: {e}")

    def _render_pdf_thumbnail(self, path):
        """Renders page 1 as an actual image via PyMuPDF. Returns True on
        success. This is the fix for pypdf's text extraction producing
        garbled/empty output on PDFs with unusual fonts/encodings — a real
        page render is unambiguous regardless of what pypdf makes of the
        underlying text-showing operators."""
        if not _HAS_FITZ:
            return False
        try:
            doc = fitz.open(path)
            if doc.page_count == 0:
                doc.close()
                return False
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
            doc.close()
            self._set_thumbnail(QPixmap.fromImage(qimg))
            return True
        except Exception as exc:
            logger.debug(f"PDF thumbnail render failed for {path}: {exc}")
            return False

    def _show_pdf(self, path):
        thumbnail_shown = self._render_pdf_thumbnail(path)

        if not _HAS_PYPDF:
            if thumbnail_shown:
                self._set_label_text("Page 1 shown above. Install `pypdf` for extracted text.")
            else:
                self._set_label_text(
                    "PDF preview requires `pypdf` or `pymupdf`. Click Open Externally to view it."
                )
            self.action_row.setVisible(True)
            return
        try:
            reader = PdfReader(path)
            text_parts = []
            collected = 0
            for page in reader.pages[:25]:
                try:
                    page_text = page.extract_text() or ""
                except Exception:
                    page_text = ""
                text_parts.append(page_text)
                collected += len(page_text)
                if collected >= self.PDF_PREVIEW_CHARS:
                    break
            full_text = "\n".join(text_parts)[:self.PDF_PREVIEW_CHARS]
            if not full_text.strip():
                full_text = f"PDF with {len(reader.pages)} page(s) — no selectable text found (scanned/image PDF)."
                if not thumbnail_shown:
                    full_text += " Use Open Externally."
                self._set_label_text(full_text)
                self.action_row.setVisible(True)
            else:
                header = f"[PDF · {len(reader.pages)} page(s)]\n\n"
                self._set_text_preview(header + full_text)
        except Exception as e:
            if thumbnail_shown:
                self._set_label_text(f"Page 1 shown above. Text extraction failed: {e}")
            else:
                self._set_label_text(f"PDF Read Error: {e}")
            self.action_row.setVisible(True)

    def _show_audio(self, path):
        self._set_thumbnail(self._category_icon("Audio"))
        if not _HAS_MUTAGEN:
            self._set_label_text(
                "Audio tags require `mutagen`. Showing basic file info only."
            )
            self.action_row.setVisible(True)
            return
        try:
            file_info = mutagen.File(path, easy=True)
            if file_info is None:
                self._set_label_text("Audio file — metadata not readable.")
                self.action_row.setVisible(True)
                return
            lines = ["[Audio Metadata]"]
            if hasattr(file_info, "info"):
                info = file_info.info
                if hasattr(info, "length"):
                    lines.append(f"Duration: {self._fmt_duration(info.length)}")
                if hasattr(info, "bitrate"):
                    lines.append(f"Bitrate: {info.bitrate // 1000} kbps")
                if hasattr(info, "sample_rate"):
                    lines.append(f"Sample rate: {info.sample_rate} Hz")
                if hasattr(info, "channels"):
                    lines.append(f"Channels: {info.channels}")
            tags = getattr(file_info, "tags", None)
            if tags:
                lines.append("")
                lines.append("[Tags]")
                for key, val in list(tags.items())[:25]:
                    lines.append(f"{key}: {val}")
            self._set_text_preview("\n".join(lines))
        except Exception as e:
            self._set_label_text(f"Audio metadata error: {e}")
            self.action_row.setVisible(True)

    def _show_video(self, path, ext):
        frame_shown = False
        duration_line = ""
        if _HAS_CV2:
            cap = None
            try:
                cap = cv2.VideoCapture(path)
                if cap.isOpened():
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    if fps and total_frames:
                        duration_line = f"Duration: {self._fmt_duration(total_frames / fps)}\n"
                    # Seek ~10% in for a more representative frame than a
                    # possibly-black/blank very first frame.
                    if total_frames and total_frames > 10:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, min(total_frames * 0.1, total_frames - 1))
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        h, w, ch = frame_rgb.shape
                        qimg = QImage(frame_rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
                        self._set_thumbnail(QPixmap.fromImage(qimg))
                        frame_shown = True
            except Exception as exc:
                logger.debug(f"Video thumbnail extraction failed for {path}: {exc}")
            finally:
                if cap is not None:
                    cap.release()

        if not frame_shown:
            self._set_thumbnail(self._category_icon("Videos"))

        msg = f"File: {os.path.basename(path)}\nContainer: {ext.lstrip('.').upper()}\n{duration_line}"
        if not frame_shown:
            msg += "\nInstall `opencv-python-headless` for a frame thumbnail.\n"
        msg += "\nUse Open Externally to launch your system media player."
        self._set_label_text(msg)
        self.action_row.setVisible(True)

    def _show_archive(self, path, ext):
        import zipfile
        self._set_thumbnail(self._category_icon("Archives"))
        try:
            if ext == ".zip" or ext in {".docx", ".xlsx", ".pptx", ".odt"}:
                with zipfile.ZipFile(path) as zf:
                    names = zf.namelist()[:200]
                    line_count = len(names)
                    sample = "\n".join(names[:200])
                    msg = (
                        f"[Archive · {ext.lstrip('.').upper()}]\n"
                        f"{line_count} entries (showing up to 200):\n\n"
                        f"{sample}"
                    )
                    self._set_text_preview(msg)
            else:
                self._set_label_text(
                    f"Archive ({ext.lstrip('.').upper()}) — list support is "
                    "for .zip and Office containers only here."
                )
                self.action_row.setVisible(True)
        except Exception as e:
            self._set_label_text(f"Archive error: {e}")
            self.action_row.setVisible(True)

    def _show_binary_summary(self, path, ext, kind):
        if "Database" in kind or "SQLite" in kind:
            self._set_thumbnail(self._category_icon("Other", glyph="DB", color="#0ea5e9"))
        else:
            self._set_thumbnail(self._category_icon("Other", glyph="EXE", color="#ef4444"))
        try:
            size = os.path.getsize(path)
            if size > self.LARGE_FILE_BYTES:
                self._set_label_text(f"{kind} (large file — preview skipped)")
                self.action_row.setVisible(True)
                return
            with open(path, "rb") as f:
                header = f.read(64)
            lines = [
                f"[{kind}]",
                f"Magic bytes: {self._hex_dump(header)}",
                f"Detected format: {self._detect_format(header) or 'Unknown'}",
            ]
            self._set_text_preview("\n".join(lines))
        except Exception as e:
            self._set_label_text(f"Preview error: {e}")

    def _show_unknown_or_detected(self, path, ext):
        try:
            size = os.path.getsize(path)
            if size > self.LARGE_FILE_BYTES:
                self._set_label_text(
                    f"File type: .{ext.lstrip('.') or 'no-ext'} (large file — preview skipped)"
                )
                self.action_row.setVisible(True)
                return
            with open(path, "rb") as f:
                header = f.read(64)
            detected = self._detect_format(header)
            # If the magic bytes match a type we already know how to render
            # (e.g. an MP3 file labelled .bin), reroute to the proper renderer.
            if detected == "PDF":
                self._show_pdf(path); return
            if detected in {"JPEG", "PNG", "GIF", "BMP", "WEBP", "TIFF_LE", "TIFF_BE"}:
                self._show_image(path); return
            if detected == "ZIP":
                self._show_archive(path, ".zip"); return
            if detected in {"MP3", "MP3_SYNC", "WAV", "FLAC", "OGG"}:
                self._show_audio(path); return
            if detected == "SQLite":
                self._show_binary_summary(path, ext, kind="SQLite Database"); return
            if detected in {"ELF", "PE_EXE"}:
                self._show_binary_summary(path, ext, kind=detected); return
            if detected in {"MP4", "AVI", "MKV"}:
                self._show_video(path, ext); return

            self._set_thumbnail(self._category_icon(categorize_extension(ext)))
            ext_text = f".{ext.lstrip('.')}" if ext else "(no extension)"
            txt = (
                f"File type: {ext_text}\n"
                f"Detected format: {detected or 'Unknown'}\n"
                f"First bytes:\n{self._hex_dump(header)}"
            )
            if _looks_like_text_bytes(header):
                self._show_text(path)
            else:
                self._set_text_preview(txt)
        except Exception as e:
            self._set_label_text(f"Preview error: {e}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_duration(seconds):
        try:
            s = int(float(seconds))
            m, sec = divmod(s, 60)
            h, m = divmod(m, 60)
            if h:
                return f"{h:d}:{m:02d}:{sec:02d}"
            return f"{m:d}:{sec:02d}"
        except Exception:
            return str(seconds)

    @staticmethod
    def _hex_dump(data):
        hex_part = " ".join(f"{b:02X}" for b in data)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
        return f"{hex_part}   | {ascii_part}"

    @staticmethod
    def _detect_format(header):
        if not _HAS_FILE_SIGS:
            return None
        try:
            return identify_file_type(header)
        except Exception:
            return None

    def _open_current_externally(self):
        if not self._current_path:
            return
        try:
            if sys.platform == 'win32':
                os.startfile(self._current_path)  # type: ignore[attr-defined]
            elif sys.platform == 'darwin':
                subprocess.call(['open', self._current_path])
            else:
                subprocess.call(['xdg-open', self._current_path])
        except Exception as e:
            self._set_label_text(f"Could not open: {e}")


def _looks_like_text_bytes(header):
    if not header:
        return False
    # Binary heuristic: lots of NULs or non-printable bytes => binary.
    binary_chars = sum(1 for b in header if b == 0 or (b < 7 or (b > 14 and b < 32)))
    return binary_chars < max(1, len(header) // 10)


def _looks_like_text(path):
    """Read first 2 KB and apply the binary heuristic to decide whether to
    show the file as plain text even if its extension is unknown."""
    try:
        with open(path, 'rb') as f:
            header = f.read(2048)
        return _looks_like_text_bytes(header)
    except OSError:
        return False
