"""TICK-805 — Right click context menus per window (Wave 8).

Acceptance:
- Search right click contains 'Copy Path' + 'Reveal in File Manager' and not 'Show Details'
- Storage right click contains 'Show Details' and not 'Copy Path'
- Generic view without override fallback generic menu still works
- Forensics view custom menu not overwritten by generic
"""
import os
from unittest.mock import MagicMock, patch

# Offscreen for CI
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMenu
from PyQt5.QtCore import QPoint

from dataforge.ui.views.base import BaseView
from dataforge.ui.views.search import SearchView
from dataforge.ui.views.storage_devices import StorageDevicesView
from dataforge.ui.views.forensics_view import ForensicsView
from dataforge.ui.widgets import EnhancedTreeview

_app = QApplication.instance() or QApplication([])


def _labels_from_descriptors(descriptors):
    """Extract label strings from descriptor list (tuple/dict/QAction/None)."""
    labels = []
    for d in descriptors or []:
        if d is None:
            continue
        if isinstance(d, dict):
            if d.get("separator"):
                continue
            lbl = d.get("label") or d.get("text") or ""
            if lbl:
                labels.append(lbl)
            continue
        if hasattr(d, "text") and callable(getattr(d, "text", None)):
            try:
                labels.append(d.text())
                continue
            except Exception:
                pass
        if isinstance(d, (list, tuple)):
            if len(d) == 0:
                continue
            lbl = d[0]
            if lbl is None or (isinstance(lbl, str) and lbl.strip() in ("", "---")):
                continue
            labels.append(str(lbl))
            continue
        if isinstance(d, str):
            if d.strip() in ("", "---"):
                continue
            labels.append(d)
    return labels


def _menu_labels_via_patch(treeview, pos):
    """Call treeview.show_context_menu with QMenu.exec_ patched and return labels shown."""
    captured = {}

    def fake_exec(self, *args, **kwargs):
        # Capture actions on this QMenu instance
        captured["labels"] = [a.text() for a in self.actions() if not a.isSeparator()]
        # Don't actually exec
        return None

    # Also patch the other code path via _show_generic_context_menu which also calls exec_
    with patch.object(QMenu, "exec_", fake_exec):
        # Also patch monkey for storage's QMenu
        with patch("PyQt5.QtWidgets.QMenu.exec_", fake_exec):
            treeview.show_context_menu(pos)
    return captured.get("labels", [])


class TestBaseViewVirtual:
    def test_base_returns_none(self):
        # BaseView is abstract; make concrete subclass
        class Dummy(BaseView):
            def get_title(self):
                return "Dummy"
        d = Dummy(None, app=MagicMock())
        assert d.get_context_actions(MagicMock(), QPoint(0, 0), None, None) is None


class TestSearchContextMenus:
    def setup_method(self):
        self.mock_app = MagicMock()
        self.view = SearchView(None, app=self.mock_app)
        # Insert a row with a resolvable path
        self.iid = self.view.tree.insert("", "end", values=("txt", "/tmp/foo_search.txt", "1 KB"), path="/tmp/foo_search.txt")
        self.item = self.view.tree.item_map[self.iid]
        self.path = self.view.tree.get_item_path(self.iid)

    def test_search_get_context_actions_contains_expected(self):
        # Direct virtual call
        pos = QPoint(10, 10)
        actions = self.view.get_context_actions(self.view.tree, pos, self.item, self.path)
        labels = _labels_from_descriptors(actions)
        assert "Copy Path" in labels, f"expected Copy Path in {labels}"
        assert "Reveal in File Manager" in labels, f"expected Reveal in {labels}"
        assert "Hash" in labels, f"expected Hash in {labels}"
        assert "Open" in labels
        assert "Show Details" not in labels, f"Search should not contain Show Details, got {labels}"

    def test_search_menu_via_show_context_menu_dispatch(self):
        # Use rect center that hits the first item; ensure selection
        # Get pos that corresponds to itemAt
        # QTreeWidget.itemAt needs viewport coords; we can find viewport pos of item
        rect = self.view.tree.tree.visualItemRect(self.item)
        pos = rect.center()
        if pos.isNull():
            pos = QPoint(10, 10)
        labels = _menu_labels_via_patch(self.view.tree, pos)
        # If dispatch works, menu should contain Search actions, not generic alone
        # Generic also has Copy Path-like but via "Copy Full Path"; ensure Search's exact label present
        assert "Copy Path" in labels
        assert "Reveal in File Manager" in labels
        assert "Show Details" not in labels

    def test_search_not_contains_storage_label(self):
        pos = QPoint(10, 10)
        actions = self.view.get_context_actions(self.view.tree, pos, self.item, self.path)
        labels = _labels_from_descriptors(actions)
        # Storage label is Show Details — already checked
        assert not any("Show Details" in lbl for lbl in labels)


class TestStorageContextMenus:
    def setup_method(self):
        self.mock_app = MagicMock()
        self.view = StorageDevicesView(None, app=self.mock_app)
        # Populate devices
        self.view.devices = [
            {"mountpoint": "/tmp", "type": "fixed", "fstype": "ext4", "formatted_used": "1 GB", "formatted_total": "10 GB", "percent_used": 10},
            {"mountpoint": "/mnt/data", "type": "removable", "fstype": "vfat", "formatted_used": "2 GB", "formatted_total": "32 GB", "percent_used": 6},
        ]
        self.view._populate_table()
        # Select first row
        self.view.table.selectRow(0)
        self.item = self.view.table.item(0, 0)
        self.pos = self.view.table.viewport().rect().center()

    def test_storage_get_context_actions_contains_show_details(self):
        # Locate mount from devices
        pos = QPoint(5, 5)
        # For storage, get_context_actions expects treeview=self.table
        actions = self.view.get_context_actions(self.view.table, pos, self.item, "/tmp")
        labels = _labels_from_descriptors(actions)
        assert "Show Details" in labels, f"expected Show Details in {labels}"
        assert "Copy Mount Point" in labels
        assert "Open in File Manager" in labels
        assert "Copy Path" not in labels, f"Storage should not contain Copy Path, got {labels}"

    def test_storage_menu_via_table_context(self):
        # Patch QMenu.exec_ for storage table
        captured = {}

        def fake_exec(self, *args, **kwargs):
            captured["labels"] = [a.text() for a in self.actions() if not a.isSeparator()]
            return None

        # Need to patch both import locations
        with patch.object(QMenu, "exec_", fake_exec):
            # itemAt pos should hit first row
            rect = self.view.table.visualItemRect(self.item)
            pos = rect.center() if not rect.isNull() else QPoint(5, 5)
            self.view._show_table_context_menu(pos)
        labels = captured.get("labels", [])
        assert "Show Details" in labels
        assert "Copy Path" not in labels

    def test_storage_not_contains_search_label(self):
        pos = QPoint(5, 5)
        actions = self.view.get_context_actions(self.view.table, pos, self.item, "/tmp")
        labels = _labels_from_descriptors(actions)
        assert not any(lbl == "Copy Path" for lbl in labels)


class TestGenericFallback:
    def test_generic_view_without_override_returns_none(self):
        class GenericView(BaseView):
            def get_title(self):
                return "Generic"

        mock_app = MagicMock()
        gv = GenericView(None, app=mock_app)
        assert gv.get_context_actions(MagicMock(), QPoint(0, 0), None, None) is None

    def test_generic_enhanced_treeview_fallback_still_works(self):
        class GenericView(BaseView):
            def get_title(self):
                return "Generic"

        mock_app = MagicMock()
        gv = GenericView(None, app=mock_app)
        # Create tree with parent as the view so _get_view can find it via parent chain
        # Or pass view explicitly
        parent = gv  # BaseView is QWidget, can be parent
        tree = EnhancedTreeview(parent, columns=("a", "path"), app=mock_app, view=gv)
        iid = tree.insert("", "end", values=("hello", "/tmp/generic.txt"), path="/tmp/generic.txt")
        item = tree.item_map[iid]
        rect = tree.tree.visualItemRect(item)
        pos = rect.center() if not rect.isNull() else QPoint(5, 5)

        captured = {}

        def fake_exec(self, *args, **kwargs):
            captured["labels"] = [a.text() for a in self.actions() if not a.isSeparator()]
            return None

        with patch.object(QMenu, "exec_", fake_exec):
            tree.show_context_menu(pos)
        labels = captured.get("labels", [])
        # Generic fallback must contain Open File and Copy column actions
        assert "Open File" in labels or "Open" in labels
        assert any("Copy" in lbl for lbl in labels), f"generic should contain Copy actions, got {labels}"
        # Should not contain Search/Storage specific labels as sole
        # Generic has Copy Full Path / Copy File Name, not Copy Path alone
        # Ensure fallback is not empty
        assert len(labels) > 0

    def test_generic_with_no_file_actions_still_shows_copy(self):
        class GenericView(BaseView):
            def get_title(self):
                return "Generic"

        mock_app = MagicMock()
        gv = GenericView(None, app=mock_app)
        tree = EnhancedTreeview(gv, columns=("key", "value"), app=mock_app, view=gv)
        tree.set_no_file_actions(True)
        iid = tree.insert("", "end", values=("k1", "v1"), path=None)
        item = tree.item_map[iid]
        rect = tree.tree.visualItemRect(item)
        pos = rect.center() if not rect.isNull() else QPoint(5, 5)
        captured = {}

        def fake_exec(self, *args, **kwargs):
            captured["labels"] = [a.text() for a in self.actions() if not a.isSeparator()]
            return None

        with patch.object(QMenu, "exec_", fake_exec):
            tree.show_context_menu(pos)
        labels = captured.get("labels", [])
        # With _no_file_actions, file actions hidden, but copy column remains
        assert any("Copy" in lbl for lbl in labels)
        assert "Open File" not in labels


class TestForensicsNotOverwritten:
    def test_forensics_does_not_override(self):
        mock_app = MagicMock()
        fv = ForensicsView(None, app=mock_app)
        # ForensicsView should not override get_context_actions (inherits base None)
        from dataforge.ui.views.base import BaseView as BV
        assert type(fv).get_context_actions is BV.get_context_actions
        assert fv.get_context_actions(MagicMock(), QPoint(0, 0), None, None) is None

    def test_forensics_tree_uses_generic_with_no_file_actions(self):
        mock_app = MagicMock()
        fv = ForensicsView(None, app=mock_app)
        # artifact_tree is EnhancedTreeview with _no_file_actions True
        tree = fv.artifact_tree
        # Should be configured to hide file actions
        assert tree._no_file_actions is True
        # Insert dummy artifact row
        iid = tree.insert("", "end", values=("users", "root", "uid0"))
        item = tree.item_map[iid]
        rect = tree.tree.visualItemRect(item)
        pos = rect.center() if not rect.isNull() else QPoint(5, 5)
        captured = {}

        def fake_exec(self, *args, **kwargs):
            captured["labels"] = [a.text() for a in self.actions() if not a.isSeparator()]
            return None

        with patch.object(QMenu, "exec_", fake_exec):
            tree.show_context_menu(pos)
        labels = captured.get("labels", [])
        # Should be generic fallback without Open File (since _no_file_actions)
        assert "Open File" not in labels
        assert any("Copy" in lbl for lbl in labels)
        # Must not be overwritten by Search/Storage menus
        assert "Copy Path" not in labels
        assert "Show Details" not in labels
