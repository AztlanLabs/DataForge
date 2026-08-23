import os
import subprocess
import sys
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QMenu, QMessageBox, QDialog,
    QLineEdit, QGroupBox, QTextEdit, QApplication, QSizePolicy,
    QGridLayout, QCheckBox, QSpinBox, QComboBox, QLayout, QAbstractItemView
)
from PyQt5.QtCore import Qt, QSize, QRect, QPoint, QThread, QTimer
from PyQt5.QtGui import QPixmap, QImage, QPainter, QFont, QColor, QTextCharFormat, QTextCursor

from . import dialogs
from ..core.config import config
from .theme_tokens import TOKENS, TYPE_SCALE
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
    import pymupdf as fitz  # type: ignore  # PyMuPDF - renders PDF pages to images (use pymupdf, fitz shim is deprecated)
    _HAS_FITZ = True
except Exception:  # pragma: no cover - optional dependency
    try:
        import fitz as fitz  # type: ignore  # fallback for old installs
        _HAS_FITZ = True
    except Exception:  # pragma: no cover
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
        self.btn_toggle.setStyleSheet(f"border: none; background: transparent; font-size: {TYPE_SCALE['subheading']}px; font-weight: bold;")
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
    def __init__(self, master, columns, app=None, on_file_action=None, view=None, **kwargs):
        super().__init__(master)
        self.app = app
        self._on_file_action = on_file_action
        # TICK-805: owning view for per-window context menus. When provided,
        # show_context_menu dispatches to view.get_context_actions(). When
        # None, the view is resolved by walking the parent chain (find BaseView).
        self._view = view
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

        # QTreeWidget — ensure viewport repaints correctly after bulk inserts
        # and when parent view is faded (avoid black/see-through for 1s).
        self.tree = QTreeWidget(self)
        try:
            self.tree.setAutoFillBackground(True)
            self.tree.viewport().setAutoFillBackground(True)
        except Exception:
            pass
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        # U8: disable drag-and-drop (QTreeWidget allows DnD by default)
        self.tree.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.tree.setDefaultDropAction(Qt.IgnoreAction)
        self.tree.setDragEnabled(False)
        self.tree.setAcceptDrops(False)
        self.tree.setDropIndicatorShown(False)
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
        # Schedule viewport refresh after bulk inserts — coalesced to one
        # singleShot per event loop to avoid black/see-through for 1s when
        # parent view is faded or when splitter sizes are initially 0.
        try:
            if not getattr(self, "_refresh_pending", False):
                self._refresh_pending = True

                def _do_refresh(s=self):
                    try:
                        s._refresh_pending = False
                        # TICK-906: avoid QBackingStore active painter while FilePreviewPanel paints
                        try:
                            vp = s.tree.viewport()
                            if hasattr(vp, "paintingActive") and vp.paintingActive():
                                s.update()
                            else:
                                vp.update()
                        except Exception:
                            try:
                                s.tree.viewport().update()
                            except Exception:
                                pass
                        try:
                            s.tree.update()
                        except Exception:
                            pass
                        try:
                            s.update()
                        except Exception:
                            pass
                    except Exception:
                        pass

                from PyQt5.QtCore import QTimer

                QTimer.singleShot(0, _do_refresh)
        except Exception:
            pass
        return iid

    def refresh_viewport(self):
        """Schedule viewport repaint after bulk inserts — avoids black/see-through
        glitch when parent view is faded via QGraphicsOpacityEffect. Uses
        singleShot(0) so it runs after layout, not during paint."""
        # TICK-906: use self.update() when viewport is painting to avoid QBackingStore active painter
        def _safe_viewport_update(s=self):
            try:
                vp = s.tree.viewport()
                if hasattr(vp, "paintingActive") and vp.paintingActive():
                    s.update()
                else:
                    vp.update()
            except Exception:
                try:
                    s.update()
                except Exception:
                    pass
        def _safe_tree_update(s=self):
            try:
                s.tree.update()
            except Exception:
                pass
        try:
            from PyQt5.QtCore import QTimer

            QTimer.singleShot(0, _safe_viewport_update)
            QTimer.singleShot(0, _safe_tree_update)
        except Exception:
            try:
                _safe_viewport_update()
            except Exception:
                pass
        
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

    def _get_view(self):
        """TICK-805: resolve owning BaseView for per-window menus."""
        if getattr(self, "_view", None) is not None:
            return self._view
        # Walk parent chain looking for BaseView
        parent = self.parent()
        visited = set()
        while parent is not None and id(parent) not in visited:
            visited.add(id(parent))
            try:
                # Lazy import to avoid circular
                from .views.base import BaseView
                if isinstance(parent, BaseView):
                    return parent
            except Exception:
                pass
            # Also check attribute view_name as heuristic for BaseView subclass
            if hasattr(parent, "get_context_actions") and hasattr(parent, "get_title"):
                # Likely a BaseView; return it
                try:
                    from .views.base import BaseView
                    if isinstance(parent, BaseView):
                        return parent
                except Exception:
                    return parent
            try:
                parent = parent.parent() if hasattr(parent, "parent") else None
            except Exception:
                break
        return None

    def _populate_menu_from_descriptors(self, menu, descriptors, item, path):
        """Populate *menu* from view-provided descriptors (TICK-805)."""
        # descriptors is list; each may be QAction, tuple, dict, None/separator
        for desc in descriptors:
            if desc is None:
                menu.addSeparator()
                continue
            if isinstance(desc, dict):
                if desc.get("separator"):
                    menu.addSeparator()
                    continue
                label = desc.get("label") or desc.get("text") or ""
                if not label:
                    continue
                enabled = desc.get("enabled", True)
                callback = desc.get("callback") or desc.get("slot") or desc.get("action")
                act = menu.addAction(label)
                act.setEnabled(bool(enabled))
                if callable(callback):
                    # capture callback correctly
                    act.triggered.connect(lambda checked, cb=callback: cb())
                continue
            # QAction instance
            if hasattr(desc, "triggered") and hasattr(desc, "setEnabled"):
                # QAction
                try:
                    menu.addAction(desc)
                    continue
                except Exception:
                    pass
            if isinstance(desc, (list, tuple)):
                if len(desc) == 0:
                    continue
                label = desc[0]
                if label is None:
                    menu.addSeparator()
                    continue
                if isinstance(label, str) and label.strip() == "---":
                    menu.addSeparator()
                    continue
                # tuple forms: (label, callback) or (label, callback, enabled)
                cb = desc[1] if len(desc) > 1 else None
                enabled = desc[2] if len(desc) > 2 else True
                act = menu.addAction(str(label))
                act.setEnabled(bool(enabled))
                if callable(cb):
                    act.triggered.connect(lambda checked, c=cb: c())
                continue
            # fallback: string label
            if isinstance(desc, str):
                if desc.strip() == "---":
                    menu.addSeparator()
                else:
                    menu.addAction(desc)

    def _show_generic_context_menu(self, pos, item, iid, path):
        """Generic fallback menu (Open/Rename/Move/Copy/Delete/Exclude + Copy col)."""
        menu = QMenu(self)
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

        path = self.get_selected_path()

        # TICK-805: per-window dispatch — if owning view overrides
        # get_context_actions, use its menu instead of the generic one.
        view = self._get_view()
        if view is not None:
            try:
                from .views.base import BaseView
                is_overridden = type(view).get_context_actions is not BaseView.get_context_actions
            except Exception:
                is_overridden = hasattr(view, "get_context_actions")
            if is_overridden:
                try:
                    import inspect
                    sig = inspect.signature(view.get_context_actions)
                    params = list(sig.parameters.keys())
                    # Dispatch with best matching signature
                    if len(params) >= 4:
                        actions = view.get_context_actions(self, pos, item, path)
                    elif len(params) == 2:
                        actions = view.get_context_actions(self, pos)
                    elif len(params) == 1:
                        actions = view.get_context_actions(pos)
                    else:
                        actions = view.get_context_actions(self, pos, item, path)
                    if actions is not None:
                        # View wants to control the menu (even if empty)
                        menu = QMenu(self)
                        if actions:
                            self._populate_menu_from_descriptors(menu, actions, item, path)
                        # If view returned empty list, show empty menu (separatorless) vs fallback
                        # For forensics/etc that want fallback, they return None
                        menu.exec_(self.tree.viewport().mapToGlobal(pos))
                        return
                except Exception as exc:
                    try:
                        from ..core.logger import logger
                        logger.debug(f"get_context_actions dispatch failed: {exc}")
                    except Exception:
                        pass
                    # fall through to generic on error

        # Fallback generic
        self._show_generic_context_menu(pos, item, iid, path)

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
        if _is_executable_file(path):
            reply = QMessageBox.question(
                self, "Open Executable?",
                f"This file appears to be an executable:\n{path}\n\n"
                "Opening untrusted executables can be dangerous. "
                "Open anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
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


class HexView(QWidget):
    """Hex viewer with field inspector for forensic analysis.

    Displays hex dump with offset, hex bytes, ASCII columns, and a
    field inspector that interprets common forensic structures
    (MBR, GPT, PE, ELF, ZIP, PNG, etc.) selected byte contexts.
    """

    # Responsive cap — only this many bytes are rendered at once so a
    # multi-megabyte file does not freeze the UI. Users can navigate via
    # byte offset.
    MAX_DISPLAY_BYTES = 64 * 1024  # 64 KiB = 4096 rows x16
    BYTES_PER_ROW = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: bytes = b""
        self._offset: int = 0  # base file offset of _data[0]
        self._selected_byte: int = -1  # index into _data, -1 = none
        self._bytes_per_row: int = self.BYTES_PER_ROW
        self._max_display_bytes: int = self.MAX_DISPLAY_BYTES
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(5, 5, 5, 5)
        outer.setSpacing(5)

        # Top bar: offset display + navigation + size
        top = QWidget(self)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        self.offset_label = QLabel("Offset: 0x00000000", top)
        self.offset_label.setStyleSheet("font-family: 'Courier New', Consolas, monospace;")
        self.offset_label.setToolTip("Current base offset / selected byte offset")
        top_layout.addWidget(self.offset_label)

        self.size_label = QLabel("Size: 0 bytes", top)
        self.size_label.setProperty("class", "muted")
        top_layout.addWidget(self.size_label)

        top_layout.addStretch(1)

        top_layout.addWidget(QLabel("Jump to byte:", top))
        self.spin_offset = QSpinBox(top)
        self.spin_offset.setRange(0, 0)
        self.spin_offset.setSingleStep(16)
        self.spin_offset.setToolTip("Jump to byte offset (decimal index into loaded data)")
        self.spin_offset.valueChanged.connect(self._on_spin_offset_changed)
        top_layout.addWidget(self.spin_offset)

        self.lbl_selected = QLabel("No selection", top)
        self.lbl_selected.setStyleSheet("font-family: 'Courier New', Consolas, monospace;")
        top_layout.addWidget(self.lbl_selected)

        outer.addWidget(top)

        # Middle: hex display + field inspector
        middle = QWidget(self)
        mid_layout = QHBoxLayout(middle)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(8)

        self.hex_display = QTextEdit(middle)
        self.hex_display.setReadOnly(True)
        self.hex_display.setFont(QFont("Courier New", 10))
        self.hex_display.setLineWrapMode(QTextEdit.NoWrap)
        self.hex_display.setStyleSheet(
            "font-family: 'Courier New', Consolas, monospace;"
        )
        # Clicking inside hex view updates selection via cursor position
        # We hook cursorPositionChanged after initial setup to avoid recursion
        mid_layout.addWidget(self.hex_display, 2)

        self.field_inspector = QTreeWidget(middle)
        self.field_inspector.setHeaderLabels(["Field", "Value", "Description"])
        self.field_inspector.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.field_inspector.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.field_inspector.header().setSectionResizeMode(2, QHeaderView.Stretch)
        # U8: disable DnD for field inspector
        self.field_inspector.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.field_inspector.setDefaultDropAction(Qt.IgnoreAction)
        self.field_inspector.setDragEnabled(False)
        self.field_inspector.setAcceptDrops(False)
        self.field_inspector.setDropIndicatorShown(False)
        mid_layout.addWidget(self.field_inspector, 1)

        outer.addWidget(middle, 1)

        self.info_label = QLabel("", self)
        self.info_label.setProperty("class", "muted")
        self.info_label.setWordWrap(True)
        outer.addWidget(self.info_label)

        # Internal flag to avoid recursing on cursor changes caused by highlighting
        self._highlighting = False
        try:
            self.hex_display.cursorPositionChanged.connect(self._on_cursor_changed)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_data(self, data: bytes, offset: int = 0):
        """Set the data to display.

        Args:
            data: raw bytes to visualise.
            offset: base file offset for the first byte (displayed in the offset column).
        """
        if data is None:
            data = b""
        # Ensure bytes
        if not isinstance(data, (bytes, bytearray)):
            data = bytes(data)
        else:
            data = bytes(data)
        self._data = data
        self._offset = int(offset) if offset is not None else 0
        self._selected_byte = -1
        self.offset_label.setText(f"Offset: 0x{self._offset:08x}")
        self.size_label.setText(f"Size: {len(self._data)} bytes")
        max_off = max(0, len(self._data) - 1)
        # Update spin range without triggering selection
        try:
            self.spin_offset.blockSignals(True)
            self.spin_offset.setRange(0, max_off if self._data else 0)
            self.spin_offset.setValue(0)
        finally:
            self.spin_offset.blockSignals(False)
        self.lbl_selected.setText("No selection")
        self._update_display()
        self._update_field_inspector(-1)

    def load_file(self, path: str, max_bytes: int = 0, offset: int = 0):
        """Convenience: load up to max_bytes from a file at offset and display."""
        if not path or not os.path.isfile(path):
            self.set_data(b"", offset=offset)
            self.hex_display.setPlainText(f"Error: file not found: {path}")
            return
        try:
            size = os.path.getsize(path)
            if max_bytes and max_bytes > 0:
                read_len = max_bytes
            else:
                read_len = min(size, 1024 * 1024)  # default 1 MiB cap for UI
            with open(path, "rb") as f:
                f.seek(offset)
                data = f.read(read_len)
            self.set_data(data, offset=offset)
            truncated = size > offset + len(data)
            self.info_label.setText(
                f"File: {os.path.basename(path)} | Read {len(data)} / {size} bytes at 0x{offset:08x}"
                + (" (truncated)" if truncated else "")
            )
        except Exception as exc:
            self.set_data(b"", offset=offset)
            self.hex_display.setPlainText(f"Error: {exc}")

    def get_data(self) -> bytes:
        return self._data

    def get_offset(self) -> int:
        return self._offset

    def get_selected_byte(self) -> int:
        return self._selected_byte

    def get_bytes_per_row(self) -> int:
        return self._bytes_per_row

    def get_hex_lines(self):
        """Return current hex dump lines (for testing without parsing QTextEdit)."""
        lines = []
        display_len = min(len(self._data), self._max_display_bytes)
        for i in range(0, display_len, self._bytes_per_row):
            chunk = self._data[i:i + self._bytes_per_row]
            offset_str = f"{self._offset + i:08x}"
            hex_str = " ".join(f"{b:02x}" for b in chunk)
            hex_padded = f"{hex_str:<48s}"
            ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{offset_str}  {hex_padded}  |{ascii_str}|")
        if len(self._data) > self._max_display_bytes:
            lines.append(f"... truncated: {len(self._data) - self._max_display_bytes} more bytes not shown")
        return lines

    def select_byte(self, index: int):
        """Select a byte index (0-based into _data) and highlight."""
        if not isinstance(index, int):
            try:
                index = int(index)
            except Exception:
                return
        if index < 0 or index >= len(self._data):
            self._selected_byte = -1
            self.lbl_selected.setText("No selection")
            self.hex_display.setExtraSelections([])
            self._update_field_inspector(-1)
            return
        self._selected_byte = index
        abs_off = self._offset + index
        byte_val = self._data[index]
        char = chr(byte_val) if 32 <= byte_val < 127 else "."
        self.lbl_selected.setText(f"Sel: 0x{abs_off:08x} ({index}) = 0x{byte_val:02x} '{char}'")
        self.offset_label.setText(f"Offset: 0x{abs_off:08x}")
        # Keep spin in sync without loop
        try:
            self.spin_offset.blockSignals(True)
            self.spin_offset.setValue(index)
        finally:
            self.spin_offset.blockSignals(False)
        self._highlight_selection()
        self._update_field_inspector(index)

    def set_offset(self, offset: int):
        """Set base offset and refresh display."""
        self._offset = int(offset)
        self.offset_label.setText(f"Offset: 0x{self._offset:08x}")
        self._update_display()
        if self._selected_byte >= 0:
            self._highlight_selection()
            self._update_field_inspector(self._selected_byte)

    def set_bytes_per_row(self, n: int):
        if n in (8, 16, 32):
            self._bytes_per_row = n
            self._update_display()
            if self._selected_byte >= 0:
                self._highlight_selection()

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------
    def _update_display(self):
        lines = self.get_hex_lines()
        # Block cursor signal while replacing text to avoid spurious _on_cursor_changed
        try:
            self.hex_display.blockSignals(True)
            self.hex_display.setPlainText("\n".join(lines))
        finally:
            self.hex_display.blockSignals(False)
        # Info about truncation
        if len(self._data) > self._max_display_bytes:
            self.info_label.setText(
                f"Showing {self._max_display_bytes} / {len(self._data)} bytes. Use offset / load with offset to view more."
            )
        else:
            if not self.info_label.text().startswith("File:"):
                self.info_label.setText("" if len(self._data) < 1024 else f"{len(self._data)} bytes loaded")
        # Re-apply highlight if selection still valid
        if self._selected_byte >= 0 and self._selected_byte < self._max_display_bytes:
            self._highlight_selection()
        else:
            self.hex_display.setExtraSelections([])

    def _highlight_selection(self):
        if self._highlighting:
            return
        if self._selected_byte < 0 or self._selected_byte >= len(self._data):
            self.hex_display.setExtraSelections([])
            return
        if self._selected_byte >= self._max_display_bytes:
            self.hex_display.setExtraSelections([])
            return
        self._highlighting = True
        try:
            row = self._selected_byte // self._bytes_per_row
            col = self._selected_byte % self._bytes_per_row
            text = self.hex_display.toPlainText()
            if not text:
                return
            lines = text.split("\n")
            if row >= len(lines):
                return
            # Compute start offset of the row in the document
            # Each prior line + '\n' (1 char)
            line_start = 0
            for r in range(row):
                # +1 for newline; but last line may not have newline — we added split, so consistent
                line_start += len(lines[r]) + 1
            # Within the line: offset 8 chars + 2 spaces =10, hex area 48, then "  |" (2+1) etc
            # hex column for this byte
            hex_pos = line_start + 10 + col * 3
            ascii_pos = line_start + 10 + 48 + 2 + 1 + col
            doc_len = len(text)
            if hex_pos < 0 or hex_pos + 2 > doc_len:
                return
            if ascii_pos < 0 or ascii_pos + 1 > doc_len:
                return
            fmt = QTextCharFormat()
            fmt.setBackground(QColor("#ffeb3b"))  # forensic highlight yellow
            fmt.setForeground(QColor("#000000"))
            selections = []
            # Hex byte (2 chars)
            c1 = self.hex_display.textCursor()
            c1.setPosition(hex_pos)
            c1.setPosition(hex_pos + 2, QTextCursor.KeepAnchor)
            e1 = QTextEdit.ExtraSelection()
            e1.cursor = c1
            e1.format = fmt
            selections.append(e1)
            # ASCII char (1 char) — verify line has that many ascii chars
            # For partial last row, ascii length may be shorter than col+1
            chunk_len = min(self._bytes_per_row, self._max_display_bytes - row * self._bytes_per_row, len(self._data) - row * self._bytes_per_row)
            if col < chunk_len:
                c2 = self.hex_display.textCursor()
                c2.setPosition(ascii_pos)
                c2.setPosition(ascii_pos + 1, QTextCursor.KeepAnchor)
                e2 = QTextEdit.ExtraSelection()
                e2.cursor = c2
                e2.format = fmt
                selections.append(e2)
            self.hex_display.setExtraSelections(selections)
            # Ensure selection is visible (scroll)
            # Move cursor to hex_pos to bring into view without changing selection highlight logic
            # We keep extra selections, cursor itself can stay anywhere
        finally:
            self._highlighting = False

    # ------------------------------------------------------------------
    # Navigation handlers
    # ------------------------------------------------------------------
    def _on_spin_offset_changed(self, val: int):
        if 0 <= val < len(self._data):
            self.select_byte(val)

    def _on_cursor_changed(self):
        if self._highlighting:
            return
        if not self._data:
            return
        # Map cursor position back to byte offset for click-to-select
        try:
            cursor = self.hex_display.textCursor()
            pos = cursor.position()
            text = self.hex_display.toPlainText()
            if not text:
                return
            lines = text.split("\n")
            # Find which row the cursor is in
            cur_start = 0
            row = -1
            col = -1
            for r, line in enumerate(lines):
                line_end = cur_start + len(line)
                if cur_start <= pos <= line_end:
                    row = r
                    # Determine if pos is inside hex area or ascii area
                    rel = pos - cur_start
                    if 10 <= rel < 10 + 48:
                        # Inside hex area — map to byte col
                        # Each hex byte occupies 3 chars except last may be 2
                        # Approx col = (rel -10)//3, but clamp
                        col = (rel - 10) // 3
                        if col >= self._bytes_per_row:
                            col = -1
                        # If cursor on space between bytes, snap to left byte
                        # Check that hex_pos for that col indeed maps to rel
                        # If rel is on a space (e.g., 12,15), we still select preceding byte
                        # So col computed as above is fine
                    elif 10 + 48 + 2 + 1 <= rel < 10 + 48 + 2 + 1 + self._bytes_per_row:
                        col = rel - (10 + 48 + 2 + 1)
                    else:
                        col = -1
                    break
                cur_start = line_end + 1  # + newline
            if row >= 0 and col >= 0:
                idx = row * self._bytes_per_row + col
                if 0 <= idx < len(self._data) and idx < self._max_display_bytes:
                    # Avoid feedback loop if already selected
                    if idx != self._selected_byte:
                        # Use block to avoid recursive cursor signals when we highlight
                        self.select_byte(idx)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Field inspector
    # ------------------------------------------------------------------
    def _update_field_inspector(self, offset: int):
        self.field_inspector.clear()
        if not self._data:
            self.field_inspector.addTopLevelItem(QTreeWidgetItem(["(no data)", "", "Load a file or set bytes to inspect"]))
            return
        if offset < 0 or offset >= len(self._data):
            # File-level overview when no byte selected — show header signatures
            root = QTreeWidgetItem(["File", f"{len(self._data)} bytes at 0x{self._offset:08x}", "Base offset + size"])
            self.field_inspector.addTopLevelItem(root)
            # Common file signatures at offset 0
            self._add_file_signatures(self.field_inspector, base=0)
            # If file is medium, show stats
            self.field_inspector.expandAll()
            return

        items = []
        b = self._data[offset]
        items.append(QTreeWidgetItem(["Byte", f"0x{b:02x}", f"{b}  '{chr(b) if 32 <= b < 127 else '.'}'"]))

        # Multi-byte interpretations
        if offset + 1 < len(self._data):
            u16_le = int.from_bytes(self._data[offset:offset+2], "little")
            u16_be = int.from_bytes(self._data[offset:offset+2], "big")
            items.append(QTreeWidgetItem(["UInt16 LE", f"0x{u16_le:04x}", f"{u16_le}"]))
            items.append(QTreeWidgetItem(["UInt16 BE", f"0x{u16_be:04x}", f"{u16_be}"]))
            i16_le = int.from_bytes(self._data[offset:offset+2], "little", signed=True)
            items.append(QTreeWidgetItem(["Int16 LE", f"{i16_le}", f"0x{u16_le:04x}"]))
        if offset + 3 < len(self._data):
            u32_le = int.from_bytes(self._data[offset:offset+4], "little")
            u32_be = int.from_bytes(self._data[offset:offset+4], "big")
            items.append(QTreeWidgetItem(["UInt32 LE", f"0x{u32_le:08x}", f"{u32_le}"]))
            items.append(QTreeWidgetItem(["UInt32 BE", f"0x{u32_be:08x}", f"{u32_be}"]))
            i32_le = int.from_bytes(self._data[offset:offset+4], "little", signed=True)
            items.append(QTreeWidgetItem(["Int32 LE", f"{i32_le}", "signed"]))
            try:
                import struct as _struct
                f_le = _struct.unpack_from("<f", self._data, offset)[0]
                f_be = _struct.unpack_from(">f", self._data, offset)[0]
                items.append(QTreeWidgetItem(["Float32 LE", f"{f_le:.6g}", f"0x{u32_le:08x}"]))
                items.append(QTreeWidgetItem(["Float32 BE", f"{f_be:.6g}", f"0x{u32_be:08x}"]))
            except Exception:
                pass
        if offset + 7 < len(self._data):
            u64_le = int.from_bytes(self._data[offset:offset+8], "little")
            u64_be = int.from_bytes(self._data[offset:offset+8], "big")
            items.append(QTreeWidgetItem(["UInt64 LE", f"0x{u64_le:016x}", f"{u64_le}"]))
            items.append(QTreeWidgetItem(["UInt64 BE", f"0x{u64_be:016x}", f"{u64_be}"]))
            try:
                import struct as _struct
                d_le = _struct.unpack_from("<d", self._data, offset)[0]
                items.append(QTreeWidgetItem(["Float64 LE", f"{d_le:.6g}", "double"]))
            except Exception:
                pass

        # ASCII string preview (next up to 32 bytes)
        nxt = self._data[offset: offset+32]
        ascii_preview = "".join(chr(x) if 32 <= x < 127 else "." for x in nxt)
        items.append(QTreeWidgetItem(["ASCII preview", ascii_preview[:32], f"{len(nxt)} bytes from offset"]))

        # Offset info
        abs_off = self._offset + offset
        items.append(QTreeWidgetItem(["File offset", f"0x{abs_off:08x} ({abs_off})", f"Base 0x{self._offset:08x} + {offset}"]))
        items.append(QTreeWidgetItem(["Row / Col", f"row {offset // self._bytes_per_row}, col {offset % self._bytes_per_row}", f"{self._bytes_per_row} bytes/row"]))

        # Forensic structure interpretation at this offset or file start
        # If at file start, show file-level structures
        if offset == 0:
            struct_items = self._inspect_file_start()
            if struct_items:
                for it in struct_items:
                    items.append(it)
        else:
            # Check for structures that might start at this offset (e.g., PE at e_lfanew, GPT at 512)
            extra = self._inspect_at_offset(offset)
            for it in extra:
                items.append(it)

        self.field_inspector.addTopLevelItems(items)
        self.field_inspector.expandAll()

    def _add_file_signatures(self, tree: QTreeWidget, base: int = 0):
        """Add top-level file signature items (called for overview)."""
        for it in self._inspect_file_start():
            tree.addTopLevelItem(it)

    def _inspect_file_start(self):
        """Inspect file start for common forensic structures. Returns list[QTreeWidgetItem]."""
        out = []
        d = self._data
        n = len(d)

        # MBR
        if n >= 512:
            sig = d[510:512]
            out.append(QTreeWidgetItem(["MBR Signature", sig.hex() if len(sig)==2 else "(short)", "0x55AA = valid MBR boot signature" if sig == b"\x55\xaa" else "Missing/invalid MBR signature (expected 55 AA)"]))
            if sig == b"\x55\xaa":
                # Partition table
                for i in range(4):
                    off = 446 + i*16
                    if off + 16 <= n:
                        entry = d[off:off+16]
                        status = entry[0]
                        ptype = entry[4]
                        lba = int.from_bytes(entry[8:12], "little")
                        sectors = int.from_bytes(entry[12:16], "little")
                        desc = f"Status 0x{status:02x}, LBA {lba}, Sectors {sectors}"
                        out.append(QTreeWidgetItem([f"Partition {i+1}", f"Type 0x{ptype:02x} {self._mbr_type_name(ptype)}", desc]))
            # GPT at LBA1
            if n >= 1024:
                gpt_sig = d[512:520]
                out.append(QTreeWidgetItem(["GPT Signature", gpt_sig.hex(), "EFI PART = valid GPT header" if gpt_sig == b"EFI PART" else "No GPT signature at LBA1 (512)"]))

        # ELF
        if n >= 4 and d[0:4] == b"\x7fELF":
            out.append(QTreeWidgetItem(["ELF Magic", "7f 45 4c 46", "ELF executable/object"]))
            if n >= 16:
                ei_class = d[4]
                ei_data = d[5]
                cls = {1: "32-bit", 2: "64-bit"}.get(ei_class, f"unknown ({ei_class})")
                data = {1: "LE", 2: "BE"}.get(ei_data, f"unknown ({ei_data})")
                out.append(QTreeWidgetItem(["ELF Class/Data", f"{cls} / {data}", f"EI_CLASS={ei_class}, EI_DATA={ei_data}"]))
            if n >= 20:
                try:
                    e_type = int.from_bytes(d[16:18], "little")
                    e_machine = int.from_bytes(d[18:20], "little")
                    out.append(QTreeWidgetItem(["ELF Type/Machine", f"type={e_type} machine={e_machine}", self._elf_type_name(e_type) + " / " + self._elf_machine_name(e_machine)]))
                except Exception:
                    pass

        # PE (MZ + PE)
        if n >= 2 and d[0:2] == b"MZ":
            out.append(QTreeWidgetItem(["DOS Magic", "MZ", "DOS/PE executable"]))
            if n >= 64:
                try:
                    e_lfanew = int.from_bytes(d[60:64], "little")
                    out.append(QTreeWidgetItem(["e_lfanew", f"0x{e_lfanew:08x} ({e_lfanew})", "Offset to PE header"]))
                    if e_lfanew + 6 <= n and d[e_lfanew:e_lfanew+2] == b"PE":
                        sig = d[e_lfanew:e_lfanew+4]
                        out.append(QTreeWidgetItem(["PE Signature", sig.hex(), "PE\\x00\\x00 — valid PE" if sig == b"PE\x00\x00" else "PE signature"]))
                        if e_lfanew + 6 <= n:
                            machine = int.from_bytes(d[e_lfanew+4:e_lfanew+6], "little")
                            out.append(QTreeWidgetItem(["PE Machine", f"0x{machine:04x}", self._pe_machine_name(machine)]))
                        if e_lfanew + 20 <= n:
                            num_sec = int.from_bytes(d[e_lfanew+6:e_lfanew+8], "little")
                            out.append(QTreeWidgetItem(["PE Sections", f"{num_sec}", "NumberOfSections"]))
                except Exception:
                    pass

        # Common file signatures (PNG, ZIP, JPEG, PDF, etc.)
        sig_map = [
            (b"\x89PNG\r\n\x1a\n", "PNG", "PNG image"),
            (b"PK\x03\x04", "ZIP", "ZIP archive / Office"),
            (b"PK\x05\x06", "ZIP EOCD", "ZIP end of central dir"),
            (b"PK\x07\x08", "ZIP span", "ZIP spanned"),
            (b"\xff\xd8\xff", "JPEG", "JPEG image"),
            (b"%PDF", "PDF", "PDF document"),
            (b"GIF87a", "GIF87a", "GIF image"),
            (b"GIF89a", "GIF89a", "GIF image"),
            (b"\x1f\x8b", "GZIP", "GZIP archive"),
            (b"BZ", "BZIP2", "BZIP2 archive"),
            (b"SQLite format 3\x00", "SQLite", "SQLite database"),
            (b"\x7fELF", "ELF", "ELF binary"),
            (b"MZ", "MZ", "DOS/PE binary"),
        ]
        for magic, name, desc in sig_map:
            if d.startswith(magic):
                # Already handled for some above; dedup
                if not any(name in it.text(0) for it in out):
                    out.append(QTreeWidgetItem([f"Signature: {name}", magic.hex(), desc]))

        if not out:
            out.append(QTreeWidgetItem(["Signature", "(unknown)", "No known file signature at offset 0"]))

        return out

    def _inspect_at_offset(self, offset: int):
        out = []
        d = self._data
        n = len(d)
        # GPT header might be at 512 regardless of selected offset
        if offset == 512 and n >= 520 and d[512:520] == b"EFI PART":
            out.append(QTreeWidgetItem(["GPT at 512", "EFI PART", "GPT header signature"]))
            if n >= 512+92:
                try:
                    hdr_size = int.from_bytes(d[512+12:512+16], "little")
                    num_entries = int.from_bytes(d[512+80:512+84], "little")
                    entry_size = int.from_bytes(d[512+84:512+88], "little")
                    out.append(QTreeWidgetItem(["GPT HeaderSize", f"{hdr_size}", "bytes"]))
                    out.append(QTreeWidgetItem(["GPT Entries", f"{num_entries} x {entry_size} bytes", "Partition entries"]))
                except Exception:
                    pass
        # PE signature at this offset
        if offset + 4 <= n and d[offset:offset+4] == b"PE\x00\x00":
            out.append(QTreeWidgetItem(["PE Signature here", "PE\\x00\\x00", "PE header at this offset"]))
        if offset + 2 <= n and d[offset:offset+2] == b"MZ":
            out.append(QTreeWidgetItem(["MZ here", "MZ", "DOS header at this offset"]))
        if offset + 4 <= n and d[offset:offset+4] == b"\x7fELF":
            out.append(QTreeWidgetItem(["ELF here", "7f454c46", "ELF at this offset"]))
        return out

    @staticmethod
    def _mbr_type_name(ptype: int) -> str:
        table = {0x00: "Empty", 0x07: "NTFS/HPFS", 0x0b: "FAT32", 0x0c: "FAT32 LBA", 0x83: "Linux", 0x82: "Linux swap", 0xee: "GPT protective", 0xef: "EFI System"}
        return table.get(ptype, "")

    @staticmethod
    def _pe_machine_name(machine: int) -> str:
        table = {0x014c: "i386", 0x8664: "AMD64", 0x0200: "IA64", 0x01c0: "ARM", 0xaa64: "ARM64", 0x0ebc: "EBC"}
        return table.get(machine, f"machine 0x{machine:04x}")

    @staticmethod
    def _elf_type_name(t: int) -> str:
        return {0: "None", 1: "REL", 2: "EXEC", 3: "DYN", 4: "CORE"}.get(t, str(t))

    @staticmethod
    def _elf_machine_name(m: int) -> str:
        return {3: "x86", 62: "x86-64", 40: "ARM", 183: "AArch64", 8: "MIPS"}.get(m, str(m))


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
    # TICK-906: guards for malloc/QPainter — large-file + thumbnail cap
    PREVIEW_MAX_BYTES = 50 * 1024 * 1024
    PREVIEW_MAX_DIM = 512

    def __init__(self, master=None, **kwargs):
        super().__init__(master)
        # TICK-906: generation counter for stale-preview discard + main-thread guard
        self._gen = 0
        self._preview_gen = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Info Group
        self.f_info = QGroupBox("File Info", self)
        info_layout = QVBoxLayout(self.f_info)

        self.lbl_name = QLabel("No Selection", self.f_info)
        self.lbl_name.setStyleSheet(f"font-weight: bold; font-size: {TYPE_SCALE['subheading']}px;")
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
        self.content_lbl.setProperty("class", "muted")
        self.content_lbl.setWordWrap(True)
        self.content_layout.addWidget(self.content_lbl)

        self.text_edit = QTextEdit(self.f_content)
        self.text_edit.setReadOnly(True)
        self.text_edit.setVisible(False)
        self.text_edit.setStyleSheet(
            f"font-family: 'Courier New', Consolas, monospace; font-size: {TYPE_SCALE['body']}px;"
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

    def _is_stale(self, gen):
        try:
            return gen != getattr(self, "_gen", gen)
        except Exception:
            return False

    def paintEvent(self, event):
        # TICK-906: ensure QPainter always ended, even if exception occurs during paint
        # FilePreviewPanel previously left QPainter active when drawing category badge/thumbnail
        # leading to QBackingStore::endPaint warnings and heap corruption under rapid selection.
        painter = None
        try:
            painter = QPainter(self)
            # No custom paint — children (QLabel/QTextEdit) handle their own rendering.
            # The painter is created to test leak handling; immediately end before super.
            # This ensures that if an exception occurs below, the active painter is cleaned.
            if painter.isActive():
                # Keep painter active briefly to simulate real paint, then end in finally
                pass
        except Exception:
            pass
        finally:
            if painter is not None:
                try:
                    if painter.isActive():
                        painter.end()
                except Exception:
                    try:
                        painter.end()
                    except Exception:
                        pass
        try:
            super().paintEvent(event)
        except Exception:
            pass
        # Extra safety: ensure no dangling painter after super (super should have handled its own)
        # If we are still in a paint, Qt handles it; we just guarantee our painter ended.

    def update_file(self, path, root=None, cancel_token=None):
        # TICK-906: main-thread guard — QPixmap/QImage/QPainter are not
        # thread-safe. If called off the GUI thread, defer to main thread.
        # Supports legacy callers: update_file(path, root) and new
        # update_file(path, cancel_token) or update_file(path, root, cancel_token).
        if cancel_token is None and root is not None and not isinstance(root, (str, type(None))):
            # overload: second arg is actually cancel_token (has is_set)
            if hasattr(root, "is_set"):
                cancel_token = root
                root = None
        try:
            app = QApplication.instance()
            if app is not None and QThread.currentThread() != app.thread():
                # defer to main thread via singleShot(0)
                QTimer.singleShot(0, lambda p=path, r=root, c=cancel_token, s=self: s.update_file(p, r, c))
                return
        except Exception:
            pass
        # cancel check before increment? keep generation semantics even for cancelled
        if cancel_token is not None:
            try:
                if cancel_token.is_set():
                    return
            except Exception:
                pass
        # generation counter — stale previews ignored
        try:
            self._gen += 1
        except Exception:
            self._gen = 1
        self._preview_gen = self._gen
        gen = self._gen
        # TICK-906: keep refs for stale/cancel checks inside helpers
        self._active_gen = gen
        self._active_cancel = cancel_token

        self.clear()
        if not path or not os.path.exists(path):
            self.clear()
            if path:
                self.lbl_name.setText("File Not Found")
                self.content_lbl.setText("File does not exist.")
                self.content_lbl.setVisible(True)
            return

        self._current_path = path
        # stale/cancel check before heavy I/O
        if self._is_stale(gen):
            return
        if cancel_token is not None:
            try:
                if cancel_token.is_set():
                    return
            except Exception:
                pass

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
        # TICK-906: ensure QPainter always ends even on exception (QBackingStore leak)
        # Thread check — QPixmap/QPainter must be on main thread
        try:
            app = QApplication.instance()
            if app is not None and QThread.currentThread() != app.thread():
                # create fallback empty pixmap on wrong thread without painter
                fallback = QPixmap(size, size)
                fallback.fill(Qt.transparent)
                return fallback
        except Exception:
            pass
        resolved_color = QColor(color) if color else QColor(CATEGORY_COLORS.get(category, CATEGORY_COLORS["Other"]))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = None
        try:
            painter = QPainter(pixmap)
            try:
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
            except Exception as _e:
                try:
                    logger.debug(f"category_icon painter error: {_e}")
                except Exception:
                    pass
            finally:
                try:
                    if painter is not None and painter.isActive():
                        painter.end()
                except Exception:
                    try:
                        if painter is not None:
                            painter.end()
                    except Exception:
                        pass
        except Exception as _e:
            try:
                logger.debug(f"category_icon init/alloc error: {_e}")
            except Exception:
                pass
            if painter is not None:
                try:
                    if painter.isActive():
                        painter.end()
                except Exception:
                    pass
        return pixmap

    def _show_image(self, path):
        # TICK-906: safe image preview — PIL thumbnail on main thread, scaled before QPixmap
        # gen for stale check
        gen = getattr(self, "_gen", getattr(self, "_preview_gen", 0))
        active_cancel = getattr(self, "_active_cancel", None)
        try:
            # large-file guard (>50MB)
            try:
                fsize = os.path.getsize(path)
                if fsize > getattr(self, "PREVIEW_MAX_BYTES", 50 * 1024 * 1024):
                    self._set_label_text("File too large for preview")
                    return
            except Exception:
                pass
            if self._is_stale(gen):
                return
            if active_cancel is not None:
                try:
                    if active_cancel.is_set():
                        return
                except Exception:
                    pass
            # Verify main thread for QPixmap/QImage creation
            try:
                app = QApplication.instance()
                if app is not None and QThread.currentThread() != app.thread():
                    # If somehow off-thread, defer (should already be guarded in update_file)
                    self._set_label_text("Preview deferred to main thread")
                    return
            except Exception:
                pass
            # Use PIL for safe thumbnail before QPixmap — avoids OOM on 20MP images
            try:
                from PIL import Image  # lazy
            except Exception:
                # Fallback to QPixmap if PIL unavailable — but limit via QImage scaled
                pixmap = QPixmap(path)
                if pixmap.isNull():
                    self._set_label_text("Image Load Error")
                    return
                if pixmap.width() > self.PREVIEW_MAX_DIM or pixmap.height() > self.PREVIEW_MAX_DIM:
                    pixmap = pixmap.scaled(self.PREVIEW_MAX_DIM, self.PREVIEW_MAX_DIM, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                if self._is_stale(gen):
                    return
                target = QSize(max(self.f_content.width() - 20, 1), max(self.f_content.height() - 40, 1))
                scaled = pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation) if pixmap.width() > target.width() or pixmap.height() > target.height() else pixmap
                self.text_edit.setVisible(False)
                self.content_lbl.setPixmap(scaled)
                self.content_lbl.setText("")
                self.content_lbl.setVisible(True)
                return
            # PIL path — .copy()+.load() avoids lazy fd leak, thumbnail caps to 512
            thumb = None
            qimg = None
            try:
                with Image.open(path) as im:
                    try:
                        im.load()
                    except Exception:
                        pass
                    # thread-safe copy that owns data, allows original to close
                    try:
                        thumb = im.copy()
                        thumb.load()
                    except Exception:
                        thumb = im.copy() if hasattr(im, "copy") else im
                    # Ensure thumb doesn't keep reference to original fp
                # Now thumb is independent; thumbnail to PREVIEW_MAX_DIM
                try:
                    thumb.thumbnail((self.PREVIEW_MAX_DIM, self.PREVIEW_MAX_DIM), Image.Resampling.LANCZOS)
                except Exception:
                    try:
                        thumb.thumbnail((self.PREVIEW_MAX_DIM, self.PREVIEW_MAX_DIM), Image.LANCZOS)
                    except Exception:
                        pass
                if self._is_stale(gen):
                    try:
                        if thumb:
                            thumb.close()
                    except Exception:
                        pass
                    return
                if active_cancel is not None:
                    try:
                        if active_cancel.is_set():
                            try:
                                if thumb:
                                    thumb.close()
                            except Exception:
                                pass
                            return
                    except Exception:
                        pass
                # Normalize mode for QImage conversion
                try:
                    if thumb.mode not in ("RGB", "RGBA"):
                        # Preserve alpha if present else convert to RGB
                        if "A" in thumb.mode:
                            thumb = thumb.convert("RGBA")
                        else:
                            thumb = thumb.convert("RGB")
                except Exception:
                    try:
                        thumb = thumb.convert("RGB")
                    except Exception:
                        pass
                w, h = thumb.size
                if w == 0 or h == 0:
                    try:
                        thumb.close()
                    except Exception:
                        pass
                    self._set_label_text("Image Load Error")
                    return
                # Convert to QImage via tobject + copy() to own data (avoids dangling buffer)
                try:
                    if thumb.mode == "RGBA":
                        data = thumb.tobytes("raw", "RGBA")
                        qimg = QImage(data, w, h, 4 * w, QImage.Format_RGBA8888).copy()
                    else:
                        if thumb.mode != "RGB":
                            thumb = thumb.convert("RGB")
                        data = thumb.tobytes("raw", "RGB")
                        qimg = QImage(data, w, h, 3 * w, QImage.Format_RGB888).copy()
                except Exception as conv_e:
                    try:
                        thumb.close()
                    except Exception:
                        pass
                    self._set_label_text(f"Image Error: {conv_e}")
                    return
            finally:
                try:
                    if thumb is not None:
                        thumb.close()
                except Exception:
                    pass
            if qimg is None or qimg.isNull():
                self._set_label_text("Image Load Error")
                return
            if self._is_stale(gen):
                return
            if active_cancel is not None:
                try:
                    if active_cancel.is_set():
                        return
                except Exception:
                    pass
            # Main-thread QPixmap creation — QImage.copy() already owns data
            try:
                app = QApplication.instance()
                if app is not None and QThread.currentThread() != app.thread():
                    return
            except Exception:
                pass
            pixmap = QPixmap.fromImage(qimg)
            if pixmap.isNull():
                self._set_label_text("Image Load Error")
                return
            # Scale to container if needed but thumb already 512 cap; still fit width
            try:
                target = QSize(max(self.f_content.width() - 20, 1), max(self.f_content.height() - 40, 1))
                if pixmap.width() > target.width() or pixmap.height() > target.height():
                    pixmap = pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            except Exception:
                pass
            if self._is_stale(gen):
                return
            self.text_edit.setVisible(False)
            self.content_lbl.setPixmap(pixmap)
            self.content_lbl.setText("")
            self.content_lbl.setVisible(True)
        except Exception as e:
            # Ensure no active QPainter leak and no stale overwrite
            if getattr(self, "_gen", 0) != gen:
                return
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
        # TICK-906: harden — main-thread only, explicit close, copy, stale guard
        gen = getattr(self, "_gen", getattr(self, "_preview_gen", 0))
        active_cancel = getattr(self, "_active_cancel", None)
        if not _HAS_FITZ:
            return False
        # large file guard
        try:
            if os.path.getsize(path) > getattr(self, "PREVIEW_MAX_BYTES", 50 * 1024 * 1024):
                return False
        except Exception:
            pass
        # thread guard — lazy import only on main thread
        try:
            app = QApplication.instance()
            if app is not None and QThread.currentThread() != app.thread():
                return False
        except Exception:
            pass
        if self._is_stale(gen):
            return False
        if active_cancel is not None:
            try:
                if active_cancel.is_set():
                    return False
            except Exception:
                pass
        # lazy import fitz on main thread only
        try:
            import pymupdf as fitz_local  # type: ignore
        except Exception:
            try:
                import fitz as fitz_local  # type: ignore
            except Exception:
                return False
        doc = None
        pix = None
        try:
            doc = fitz_local.open(path)
            if doc.page_count == 0:
                return False
            if self._is_stale(gen):
                return False
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz_local.Matrix(2.0, 2.0))
            fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
            # QImage copy owns data — ensures pix.samples can be freed
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
            if self._is_stale(gen):
                return False
            if active_cancel is not None:
                try:
                    if active_cancel.is_set():
                        return False
                except Exception:
                    pass
            # main-thread QPixmap
            try:
                app = QApplication.instance()
                if app is not None and QThread.currentThread() != app.thread():
                    return False
            except Exception:
                pass
            self._set_thumbnail(QPixmap.fromImage(qimg))
            return True
        except Exception as exc:
            logger.debug(f"PDF thumbnail render failed for {path}: {exc}")
            return False
        finally:
            try:
                pix = None
            except Exception:
                pass
            if doc is not None:
                try:
                    doc.close()
                except Exception:
                    pass

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
        # TICK-906: hardened — explicit release, stale guard, main-thread QImage copy
        gen = getattr(self, "_gen", getattr(self, "_preview_gen", 0))
        active_cancel = getattr(self, "_active_cancel", None)
        frame_shown = False
        duration_line = ""
        skip_cv2 = False
        try:
            if os.path.getsize(path) > getattr(self, "PREVIEW_MAX_BYTES", 50 * 1024 * 1024):
                skip_cv2 = True
        except Exception:
            pass
        if self._is_stale(gen):
            skip_cv2 = True
        if active_cancel is not None:
            try:
                if active_cancel.is_set():
                    skip_cv2 = True
            except Exception:
                pass
        if not skip_cv2 and _HAS_CV2:
            cap = None
            try:
                cap = cv2.VideoCapture(path)
                if cap.isOpened():
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    if fps and total_frames:
                        duration_line = f"Duration: {self._fmt_duration(total_frames / fps)}\n"
                    if not self._is_stale(gen):
                        if total_frames and total_frames > 10:
                            cap.set(cv2.CAP_PROP_POS_FRAMES, min(total_frames * 0.1, total_frames - 1))
                        ok, frame = cap.read()
                        if ok and frame is not None:
                            if not self._is_stale(gen):
                                app = QApplication.instance()
                                if app is None or QThread.currentThread() == app.thread():
                                    try:
                                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                        h, w, ch = frame_rgb.shape
                                        qimg = QImage(frame_rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
                                        if not self._is_stale(gen):
                                            self._set_thumbnail(QPixmap.fromImage(qimg))
                                            frame_shown = True
                                    except Exception:
                                        frame_shown = False
            except Exception as exc:
                logger.debug(f"Video thumbnail extraction failed for {path}: {exc}")
            finally:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass

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
            self._set_thumbnail(self._category_icon("Other", glyph="DB", color=TOKENS["light"]["info"]))
        else:
            self._set_thumbnail(self._category_icon("Other", glyph="EXE", color=TOKENS["light"]["danger"]))
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
        if _is_executable_file(self._current_path):
            reply = QMessageBox.question(
                self, "Open Executable?",
                f"This file appears to be an executable:\n{self._current_path}\n\n"
                "Opening untrusted executables can be dangerous. "
                "Open anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
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


_EXECUTABLE_EXTENSIONS = {
    ".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".pif",
    ".sh", ".bash", ".csh", ".ksh", ".fish",
    ".app", ".dmg", ".pkg", ".deb", ".rpm",
    ".py", ".pyw", ".rb", ".pl",
}


def _is_executable_file(path):
    _, ext = os.path.splitext(path)
    if ext.lower() in _EXECUTABLE_EXTENSIONS:
        return True
    if sys.platform != "win32":
        try:
            return os.access(path, os.X_OK) and os.path.isfile(path)
        except OSError:
            pass
    return False


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


# TICK-906: preserve original _category_icon for testing before icons.py patch
try:
    FilePreviewPanel._original_category_icon = FilePreviewPanel._category_icon  # type: ignore[attr-defined]
except Exception:
    pass
