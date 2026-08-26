"""TICK-925 — UI view state contract (Wave 12).

Acceptance:
- Metadata panels refresh after strip/write (P1.6)
- Path-role maps cleared on tree rebuild (P1.7)
- Extended selection enabled where plural actions exist (P1.7)
- Search results cleared at operation start (P1.7)
- All metadata panels (overview, raw, GPS, timestamps) populated on select
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Offscreen for CI
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QAbstractItemView

from dataforge.core.common import FileEntry
from dataforge.ui.views.metadata_view import MetadataView
from dataforge.ui.views.search import SearchView
from dataforge.ui.views.duplicates import DuplicatesView

_app = QApplication.instance() or QApplication([])


def _make_meta(path, filename="photo.jpg", extension=".jpg"):
    return {
        "path": path,
        "filename": filename,
        "extension": extension,
        "formatted_size": "1.2 MB",
        "handler": "exif",
        "has_gps": True,
        "has_meta": True,
        "gps": {"latitude": 19.4326, "longitude": -99.1332, "altitude": 2240.0},
        "timestamps": {"modified": "2026-08-01 10:00:00"},
        "fields": {"Make": "Canon", "Model": "EOS R5"},
        "image_info": {"width": 4000, "height": 3000},
    }


class TestMetadataRefresh:
    def setup_method(self):
        self.mock_app = MagicMock()
        self.view = MetadataView(None, app=self.mock_app)

    def test_metadata_refresh_after_strip(self):
        """GIVEN a scanned file with metadata WHEN strip completes THEN
        _on_file_select is re-invoked (all panels refreshed)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "photo.jpg")
            iid = self.view.file_tree.insert(
                "", "end", values=("photo.jpg", ".jpg", "1.2 MB", "exif", "Yes", "GPS"), path=path
            )
            self.view.item_metadata_map[iid] = _make_meta(path)
            stripped = _make_meta(path)
            stripped["fields"] = {}
            stripped["gps"] = None
            stripped["has_gps"] = False

            with patch("dataforge.ui.views.metadata_view.MetadataEngine.read_metadata", return_value=stripped), \
                 patch.object(self.view, "_on_file_select") as refresh:
                self.view._on_strip_complete([{"success": True, "path": path}])

            assert refresh.call_count >= 1, "strip must re-refresh the selected file display"
            assert self.view.item_metadata_map[iid]["has_gps"] is False
            assert self.view.item_metadata_map[iid]["gps"] is None

    def test_metadata_refresh_after_write(self):
        """GIVEN a scanned file WHEN write completes THEN GPS/timestamps
        panels refresh via _on_file_select re-invocation."""
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "photo.jpg")
            iid = self.view.file_tree.insert(
                "", "end", values=("photo.jpg", ".jpg", "1.2 MB", "exif", "Yes", "GPS"), path=path
            )
            self.view.item_metadata_map[iid] = _make_meta(path)
            written = _make_meta(path)
            written["gps"] = {"latitude": 10.0, "longitude": 20.0, "altitude": 5.0}

            with patch("dataforge.ui.views.metadata_view.MetadataEngine.read_metadata", return_value=written), \
                 patch.object(self.view, "_on_file_select") as refresh:
                self.view._on_write_complete([{"success": True, "path": path}])

            assert refresh.call_count >= 1, "write must re-refresh the selected file display"
            assert self.view.item_metadata_map[iid]["gps"]["latitude"] == 10.0

    def test_metadata_all_panels_refreshed(self):
        """GIVEN a selected file with GPS/timestamps/fields WHEN _on_file_select
        runs THEN overview, raw, GPS, and timestamps panels are all populated."""
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "photo.jpg")
            Path(path).write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
            iid = self.view.file_tree.insert(
                "", "end", values=("photo.jpg", ".jpg", "1.2 MB", "exif", "Yes", "GPS"), path=path
            )
            self.view.item_metadata_map[iid] = _make_meta(path)
            self.view.file_tree.selection_set([iid])

            self.view._on_file_select()

            assert self.view.overview_tree.tree.topLevelItemCount() > 0
            assert "Canon" in self.view.raw_text.toPlainText()
            assert "19.4326" in self.view.lbl_gps.text()
            assert self.view.ts_tree.tree.topLevelItemCount() > 0

    def test_metadata_no_selection_noop(self):
        """GIVEN no file selected WHEN _on_file_select runs THEN no crash."""
        self.view._on_file_select()


class TestPathRoleCleared:
    def setup_method(self):
        self.mock_app = MagicMock()
        self.view = DuplicatesView(None, app=self.mock_app)
        self.view.entry_path.setText("/tmp")

    def _make_entry(self, path):
        return FileEntry(
            path=path,
            filename=os.path.basename(path),
            extension=os.path.splitext(path)[1] or ".jpg",
            size=1024,
            created_at=0.0,
            modified_at=0.0,
        )

    def test_path_role_cleared_on_rebuild(self):
        """GIVEN a populated duplicate tree WHEN it is rebuilt THEN no stale
        path roles survive (item ids are reused across rebuilds)."""
        self.view.current_results = {
            "abc123": [self._make_entry("/tmp/a.jpg"), self._make_entry("/tmp/b.jpg")],
        }
        self.view._refresh_visible_results()
        old_role = dict(self.view.tree._item_path_role)
        assert old_role, "first build must populate path roles"

        # Rebuild with a *different* group shape so item ids shift roles.
        self.view.current_results = {
            "abc123": [self._make_entry("/tmp/a.jpg")],
            "def456": [self._make_entry("/tmp/c.jpg"), self._make_entry("/tmp/d.jpg")],
        }
        self.view._refresh_visible_results()

        role = self.view.tree._item_path_role
        for iid, path in role.items():
            assert path in ("/tmp/a.jpg", "/tmp/b.jpg", "/tmp/c.jpg", "/tmp/d.jpg"), (
                f"stale path role {iid} -> {path}"
            )
        assert set(role.keys()) <= set(self.view.tree.item_map.keys())

    def test_extended_selection_enabled_duplicates(self):
        """GIVEN the duplicates view THEN its tree allows extended selection."""
        assert self.view.tree.tree.selectionMode() == QAbstractItemView.ExtendedSelection


class TestSearchClear:
    def setup_method(self):
        self.mock_app = MagicMock()
        self.view = SearchView(None, app=self.mock_app)

    def test_search_results_cleared_on_new_search(self):
        """GIVEN prior search results WHEN a new search starts THEN the old
        results and tree are cleared immediately."""
        self.view.entry_path.setText("/tmp")
        self.view.current_results = [
            FileEntry("/tmp/old_a.txt", "old_a.txt", ".txt", 10, 0.0, 0.0)
        ]
        self.view.tree.insert("", "end", values=(".txt", "/tmp/old_a.txt", "10 B"))

        self.view.start_search()

        assert self.view.current_results == [], "stale results must be cleared at start"
        assert self.view.tree.tree.topLevelItemCount() == 0, "tree must be cleared at start"


class TestExtendedSelection:
    def setup_method(self):
        self.mock_app = MagicMock()

    def test_extended_selection_enabled_metadata(self):
        """GIVEN the metadata view THEN the file tree allows extended selection."""
        view = MetadataView(None, app=self.mock_app)
        assert view.file_tree.tree.selectionMode() == QAbstractItemView.ExtendedSelection

    def test_extended_selection_enabled_search(self):
        """GIVEN the search view THEN the result tree allows extended selection."""
        view = SearchView(None, app=self.mock_app)
        assert view.tree.tree.selectionMode() == QAbstractItemView.ExtendedSelection