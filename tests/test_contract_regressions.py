import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from dataforge.cli import main
from dataforge.modules.cleaner import remove_empty_folders
from dataforge.modules.organizer import Organizer
from dataforge.modules.renamer import bulk_rename
from dataforge.modules.search import build_search_query, search_files
from dataforge.ui.widgets import HoverTooltip, attach_tooltips
from dataforge.ui.views.search import SearchView
from dataforge.ui.views.action_builder import ActionBuilderView
from dataforge.ui.views.tools import ToolsView
from dataforge.ui.views.media import MediaView
from dataforge.ui.views.duplicates import DuplicatesView
from dataforge.ui.views.settings import SettingsView
from dataforge.ui.plugin_loader import PluginLoader
from dataforge.ui.plugins.cleaner_plugin import MetadataCleanerPlugin
from dataforge.ui.views.base import BaseView


class ContractRegressionTests(unittest.TestCase):
    def test_cli_smoke_import(self):
        self.assertIsNotNone(main)

    def test_choose_file_returns_picked_path(self):
        with patch(
            "dataforge.ui.views.base.dialogs.get_open_file_name",
            return_value=("C:/tmp/file.txt", ""),
        ) as open_file:
            dummy_self = MagicMock()
            self.assertEqual(
                BaseView.choose_file(dummy_self, filetypes=[("All Files", "*.*")]),
                "C:/tmp/file.txt",
            )
        open_file.assert_called_once()

    def test_choose_file_returns_empty_string_on_cancel(self):
        with patch(
            "dataforge.ui.views.base.dialogs.get_open_file_name",
            return_value=("", ""),
        ) as open_file:
            dummy_self = MagicMock()
            self.assertEqual(BaseView.choose_file(dummy_self), "")
        open_file.assert_called_once()

    def test_choose_directory_returns_picked_path(self):
        with patch(
            "dataforge.ui.views.base.dialogs.get_existing_directory",
            return_value="C:/tmp/folder",
        ) as open_dir:
            dummy_self = MagicMock()
            self.assertEqual(
                BaseView.choose_directory(dummy_self, title="Select Folder"),
                "C:/tmp/folder",
            )
        open_dir.assert_called_once()

    def test_choose_directory_returns_empty_string_on_cancel(self):
        with patch(
            "dataforge.ui.views.base.dialogs.get_existing_directory",
            return_value="",
        ) as open_dir:
            dummy_self = MagicMock()
            self.assertEqual(BaseView.choose_directory(dummy_self), "")
        open_dir.assert_called_once()

    def test_choose_file_or_directory_riddle_is_removed(self):
        """The Yes/No/Cancel message-box riddle is gone; the legacy entry
        point must no longer pop a question before opening the picker."""
        with patch("dataforge.ui.views.base.QMessageBox") as MockQMessageBox, \
             patch("dataforge.ui.views.base.dialogs.get_open_file_name", return_value=("", "")) as open_file, \
             patch("dataforge.ui.views.base.dialogs.get_existing_directory", return_value="") as open_dir:
            dummy_self = MagicMock()
            self.assertEqual(
                BaseView.choose_file_or_directory(dummy_self, filetypes=[("All Files", "*.*")]),
                "",
            )
        MockQMessageBox.assert_not_called()
        open_file.assert_not_called()
        open_dir.assert_not_called()

    def test_cli_search_accepts_single_file_path(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "match.txt"
            target.write_text("matched", encoding="utf-8")

            result = runner.invoke(main, ["search", str(target), "--ext", "txt"])

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.output.strip(), str(target))

    def test_cli_search_supports_name_glob(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "report_01.txt").write_text("a", encoding="utf-8")
            (root / "report_02.log").write_text("b", encoding="utf-8")
            (root / "notes.txt").write_text("c", encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--name-glob",
                    "report_*.txt",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.output.strip(), str(root / "report_01.txt"))

    def test_cli_search_supports_name_regex(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "report_123.txt").write_text("a", encoding="utf-8")
            (root / "report_abc.txt").write_text("b", encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--name-regex",
                    r"report_\d+\.txt",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.output.strip(), str(root / "report_123.txt"))

    def test_cli_search_rejects_multiple_name_modes(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--name-glob",
                    "*.txt",
                    "--name-regex",
                    r".*\.txt",
                ],
            )

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Use either --name-glob or --name-regex", result.output)

    def test_cli_search_rejects_multiple_name_modes_with_json_error(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--name-glob",
                    "*.txt",
                    "--name-regex",
                    r".*\.txt",
                    "--error-format",
                    "json",
                ],
            )

            self.assertEqual(result.exit_code, 2)
            lines = result.output.strip().splitlines()
            payload = json.loads(lines[-1])
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["type"], "usage")
            self.assertEqual(payload["error"]["command"], "search")
            self.assertEqual(payload["error"]["exit_code"], 2)
            self.assertIn("Use either --name-glob or --name-regex", payload["error"]["message"])

    def test_cli_search_supports_content_and_max_depth(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            top_level = root / "top.txt"
            nested = root / "nested" / "deep.txt"
            top_level.write_text("needle", encoding="utf-8")
            nested.parent.mkdir()
            nested.write_text("needle", encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--ext",
                    "txt",
                    "--content",
                    "needle",
                    "--max-depth",
                    "0",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.output.strip(), str(top_level))

    def test_cli_search_supports_date_filters(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recent = root / "recent.txt"
            old = root / "old.txt"
            recent.write_text("recent", encoding="utf-8")
            old.write_text("old", encoding="utf-8")

            three_days_ago = time.time() - (3 * 86400)
            os.utime(old, (three_days_ago, three_days_ago))

            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--ext",
                    "txt",
                    "--older-than-days",
                    "1",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.output.strip(), str(old))

    def test_cli_search_can_emit_json(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "match.txt"
            target.write_text("matched content", encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--ext",
                    "txt",
                    "--content",
                    "matched",
                    "--format",
                    "json",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            payload = json.loads(result.output)
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["path"], str(target))
            self.assertEqual(payload[0]["filename"], "match.txt")
            self.assertEqual(payload[0]["extension"], ".txt")
            self.assertEqual(payload[0]["size"], len("matched content"))
            self.assertFalse(payload[0]["is_dir"])

    def test_cli_search_can_emit_jsonl(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first.txt"
            second = Path(temp_dir) / "second.txt"
            first.write_text("shared", encoding="utf-8")
            second.write_text("shared", encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--ext",
                    "txt",
                    "--content",
                    "shared",
                    "--format",
                    "jsonl",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            lines = [json.loads(line) for line in result.output.splitlines() if line.strip()]
            self.assertEqual(len(lines), 2)
            self.assertEqual({entry["filename"] for entry in lines}, {"first.txt", "second.txt"})

    def test_cli_search_supports_sort_and_limit(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "large.txt").write_text("x" * 9, encoding="utf-8")
            (root / "small.txt").write_text("x", encoding="utf-8")
            (root / "medium.txt").write_text("x" * 5, encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--ext",
                    "txt",
                    "--sort",
                    "size",
                    "--limit",
                    "2",
                    "--format",
                    "jsonl",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            lines = [json.loads(line) for line in result.output.splitlines() if line.strip()]
            self.assertEqual([entry["filename"] for entry in lines], ["small.txt", "medium.txt"])

    def test_cli_dupes_supports_sort_limit_and_jsonl(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "small_a.txt").write_text("same-small", encoding="utf-8")
            (root / "small_b.txt").write_text("same-small", encoding="utf-8")
            (root / "large_a.txt").write_text("L" * 32, encoding="utf-8")
            (root / "large_b.txt").write_text("L" * 32, encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "dupes",
                    temp_dir,
                    "--sort",
                    "size",
                    "--reverse",
                    "--limit",
                    "2",
                    "--format",
                    "jsonl",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            lines = [json.loads(line) for line in result.output.splitlines() if line.startswith("{")]
            self.assertEqual(len(lines), 2)
            self.assertEqual([entry["filename"] for entry in lines], ["large_a.txt", "large_b.txt"])

    def test_cli_dupes_can_export_current_slice_to_json(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            export_path = root / "dupes.json"
            (root / "one_a.txt").write_text("same-one", encoding="utf-8")
            (root / "one_b.txt").write_text("same-one", encoding="utf-8")
            (root / "two_a.txt").write_text("same-two content", encoding="utf-8")
            (root / "two_b.txt").write_text("same-two content", encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "dupes",
                    temp_dir,
                    "--sort",
                    "size",
                    "--limit",
                    "2",
                    "--output",
                    str(export_path),
                    "--export-format",
                    "json",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            payload = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload), 3)
            self.assertEqual(payload[0]["record_type"], "duplicate_group_summary")
            self.assertTrue(all("duplicate_hash" in row for row in payload))

    def test_cli_dupes_flat_export_excludes_group_summary_rows(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            export_path = root / "dupes-flat.json"
            (root / "one_a.txt").write_text("same-one", encoding="utf-8")
            (root / "one_b.txt").write_text("same-one", encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "dupes",
                    temp_dir,
                    "--output",
                    str(export_path),
                    "--export-format",
                    "json",
                    "--flat-export",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            payload = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload), 2)
            self.assertTrue(all(row["record_type"] == "duplicate_entry" for row in payload))

    def test_cli_dupes_supports_count_only(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "one_a.txt").write_text("same-one", encoding="utf-8")
            (root / "one_b.txt").write_text("same-one", encoding="utf-8")
            (root / "two_a.txt").write_text("same-two", encoding="utf-8")
            (root / "two_b.txt").write_text("same-two", encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "dupes",
                    temp_dir,
                    "--sort",
                    "size",
                    "--limit",
                    "3",
                    "--count-only",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.output.strip(), "3")

    def test_cli_search_supports_extension_sort(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "b.txt").write_text("x", encoding="utf-8")
            (root / "a.md").write_text("x", encoding="utf-8")
            (root / "c.csv").write_text("x", encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--sort",
                    "ext",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(
                result.output.splitlines(),
                [str(root / "c.csv"), str(root / "a.md"), str(root / "b.txt")],
            )

    def test_cli_search_supports_reverse_sort(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "small.txt").write_text("x", encoding="utf-8")
            (root / "medium.txt").write_text("x" * 5, encoding="utf-8")
            (root / "large.txt").write_text("x" * 9, encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--ext",
                    "txt",
                    "--sort",
                    "size",
                    "--reverse",
                    "--limit",
                    "2",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(
                result.output.splitlines(),
                [str(root / "large.txt"), str(root / "medium.txt")],
            )

    def test_cli_search_count_only_respects_limit(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "one.txt").write_text("shared", encoding="utf-8")
            (root / "two.txt").write_text("shared", encoding="utf-8")
            (root / "three.txt").write_text("shared", encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--ext",
                    "txt",
                    "--limit",
                    "2",
                    "--count-only",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.output.strip(), "2")

    def test_search_view_worker_applies_sort_reverse_and_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "small.txt").write_text("x", encoding="utf-8")
            (root / "medium.txt").write_text("x" * 5, encoding="utf-8")
            (root / "large.txt").write_text("x" * 9, encoding="utf-8")

            query = build_search_query(extensions="txt")
            results = SearchView._run_search_worker(
                object(),
                temp_dir,
                query,
                True,
                -1,
                "size",
                True,
                2,
            )

            self.assertEqual([entry.filename for entry in results], ["large.txt", "medium.txt"])

    def test_search_view_worker_applies_extension_sort(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "b.txt").write_text("x", encoding="utf-8")
            (root / "a.md").write_text("x", encoding="utf-8")
            (root / "c.csv").write_text("x", encoding="utf-8")

            query = build_search_query()
            results = SearchView._run_search_worker(
                object(),
                temp_dir,
                query,
                True,
                -1,
                "ext",
                False,
                None,
            )

            self.assertEqual([entry.filename for entry in results], ["c.csv", "a.md", "b.txt"])

    def test_search_view_slice_summary_includes_sort_reverse_limit(self):
        view = type("DummySearchView", (), {})()
        view.sort_combo = MagicMock()
        view.sort_combo.currentText.return_value = "ext"
        view.chk_reverse = MagicMock()
        view.chk_reverse.isChecked.return_value = True
        view.spin_limit = MagicMock()
        view.spin_limit.value.return_value = 25

        summary = SearchView._build_results_slice_summary(view)

        self.assertEqual(summary, "Slice: sort ext (descending) | limit 25")

    def test_duplicates_view_slice_summary_includes_sort_reverse_limit(self):
        view = type("DummyDuplicatesView", (), {})()
        view.sort_combo = MagicMock()
        view.sort_combo.currentText.return_value = "group"
        view.chk_reverse = MagicMock()
        view.chk_reverse.isChecked.return_value = True
        view.spin_limit = MagicMock()
        view.spin_limit.value.return_value = 10

        summary = DuplicatesView._build_results_slice_summary(view)

        self.assertEqual(summary, "Slice: sort group (descending) | limit 10")

    def test_search_view_reset_slice_clears_controls_and_summary(self):
        sort_combo = MagicMock()
        chk_reverse = MagicMock()
        spin_limit = MagicMock()
        lbl_results_slice = MagicMock()

        view = type("DummySearchView", (), {})()
        view.sort_combo = sort_combo
        view.chk_reverse = chk_reverse
        view.spin_limit = spin_limit
        view.lbl_results_slice = lbl_results_slice
        view._build_results_slice_summary = lambda: "Slice: natural order | full set"

        SearchView.reset_slice(view)

        sort_combo.setCurrentIndex.assert_called_once_with(0)
        chk_reverse.setChecked.assert_called_once_with(False)
        spin_limit.setValue.assert_called_once_with(0)
        lbl_results_slice.setText.assert_called_once_with("Slice: natural order | full set")

    def test_duplicates_view_reset_slice_clears_controls_and_refreshes(self):
        view = type("DummyDuplicatesView", (), {})()
        view.sort_combo = MagicMock()
        view.chk_reverse = MagicMock()
        view.spin_limit = MagicMock()
        view.lbl_results_slice = MagicMock()
        view.visible_records = []
        view._refresh_visible_results = DuplicatesView._refresh_visible_results.__get__(view, type(view))
        view._capture_expanded_group_state = MagicMock()
        view.current_results = {}
        view._rebuild_tree = MagicMock()
        view._build_results_slice_summary = lambda: "Slice: natural order | full set"

        DuplicatesView.reset_slice(view)

        view.sort_combo.setCurrentIndex.assert_called_once_with(0)
        view.chk_reverse.setChecked.assert_called_once_with(False)
        view.spin_limit.setValue.assert_called_once_with(0)

    def test_duplicates_view_refresh_preserves_expanded_group_hashes(self):
        expanded_tree = MagicMock()
        expanded_tree.item.side_effect = lambda item_id, option=None, **kwargs: True if option == "open" and item_id == "group-a" else False

        view = type("DummyDuplicatesView", (), {})()
        view.tree = expanded_tree
        view.group_items = {"group-a": "hash-a", "group-b": "hash-b"}
        view.current_results = {}
        view.sort_combo = MagicMock()
        view.sort_combo.currentText.return_value = ""
        view.chk_reverse = MagicMock()
        view.chk_reverse.isChecked.return_value = False
        view.spin_limit = MagicMock()
        view.spin_limit.value.return_value = 0
        view._rebuild_tree = MagicMock()
        view._build_results_slice_summary = lambda: "Slice: natural order | full set"
        view.lbl_results_slice = MagicMock()
        view._capture_expanded_group_state = DuplicatesView._capture_expanded_group_state.__get__(view, type(view))

        DuplicatesView._refresh_visible_results(view)

        self.assertEqual(view.expanded_group_hashes, {"hash-a"})

    def test_duplicates_view_set_tree_selection_can_expand_only_matched_groups(self):
        view = type("DummyDuplicatesView", (), {})()
        view.tree = MagicMock()
        view.item_records = {
            "item-1": {"hash": "hash-a"},
            "item-2": {"hash": "hash-b"},
        }
        view.group_items = {"group-a": "hash-a", "group-b": "hash-b"}
        view.expanded_group_hashes = {"hash-b"}
        view._restore_expanded_group_state = MagicMock()
        view.on_preview_select = MagicMock()
        view._expand_groups_for_item_ids = DuplicatesView._expand_groups_for_item_ids.__get__(view, type(view))

        DuplicatesView._set_tree_selection(view, ["item-1"], expand_matching_groups_only=True)

        self.assertEqual(view.expanded_group_hashes, {"hash-a"})
        view._restore_expanded_group_state.assert_called_once_with()

    def test_search_view_declares_slice_tooltip_text(self):
        self.assertIn("ext", SearchView.SLICE_TOOLTIPS["sort"])
        self.assertIn("largest files first", SearchView.SLICE_TOOLTIPS["reverse"])
        self.assertIn("full set", SearchView.SLICE_TOOLTIPS["limit"])
        self.assertIn("natural full result set", SearchView.SLICE_TOOLTIPS["reset"])

    def test_reusable_tooltip_helpers_are_exposed(self):
        self.assertTrue(callable(HoverTooltip))
        self.assertTrue(callable(attach_tooltips))

    def test_action_builder_declares_tooltip_text(self):
        self.assertIn("subfolders", ActionBuilderView.TOOLTIP_TEXTS["recursive"])
        self.assertIn("-1", ActionBuilderView.TOOLTIP_TEXTS["depth"])
        self.assertIn("dry run", ActionBuilderView.TOOLTIP_TEXTS["preview"])
        self.assertIn("previewed", ActionBuilderView.TOOLTIP_TEXTS["execute"])

    def test_tools_view_declares_integrity_and_cleaner_tooltip_text(self):
        self.assertIn("snapshot", ToolsView.TOOLTIP_TEXTS["integrity_create"])
        self.assertIn("new, modified, or deleted", ToolsView.TOOLTIP_TEXTS["integrity_verify"])
        self.assertIn("metadata", ToolsView.TOOLTIP_TEXTS["cleaner_path"])
        self.assertIn("-1", ToolsView.TOOLTIP_TEXTS["cleaner_depth"])
        self.assertIn("selected rows", ToolsView.TOOLTIP_TEXTS["cleaner_selected"])

    def test_tools_view_declares_renamer_and_sync_tooltip_text(self):
        self.assertIn("patterns", ToolsView.TOOLTIP_TEXTS["renamer_find"])
        self.assertIn("beginning", ToolsView.TOOLTIP_TEXTS["renamer_prefix"])
        self.assertIn("previewed rename plan", ToolsView.TOOLTIP_TEXTS["renamer_apply"])
        self.assertIn("source folder", ToolsView.TOOLTIP_TEXTS["sync_source"])
        self.assertIn("pending copy actions", ToolsView.TOOLTIP_TEXTS["sync_analyze"])
        self.assertIn("one-way sync", ToolsView.TOOLTIP_TEXTS["sync_execute"])

    def test_media_view_declares_high_friction_tooltip_text(self):
        self.assertIn("exact order", MediaView.TOOLTIP_TEXTS["pdf_add"])
        self.assertIn("dry-run preview", MediaView.TOOLTIP_TEXTS["pdf_merge"])
        self.assertIn("split into separate page files", MediaView.TOOLTIP_TEXTS["pdf_split_file"])
        self.assertIn("output format", MediaView.TOOLTIP_TEXTS["img_format"])
        self.assertIn("100%", MediaView.TOOLTIP_TEXTS["img_resize"])
        self.assertIn("after preview", MediaView.TOOLTIP_TEXTS["img_convert"])

    def test_duplicates_view_declares_action_and_export_tooltip_text(self):
        self.assertIn("size first", DuplicatesView.TOOLTIP_TEXTS["scan_path"])
        self.assertIn("Group sorts", DuplicatesView.TOOLTIP_TEXTS["sort"])
        self.assertIn("Expand every visible duplicate group", DuplicatesView.TOOLTIP_TEXTS["expand_all"])
        self.assertIn("Collapse every visible duplicate group", DuplicatesView.TOOLTIP_TEXTS["collapse_all"])
        self.assertIn("flat file list", DuplicatesView.TOOLTIP_TEXTS["flat_export"])
        self.assertIn("keep", DuplicatesView.TOOLTIP_TEXTS["keep_strategy"])
        self.assertIn("move, copy, or delete", DuplicatesView.TOOLTIP_TEXTS["select_extras"])
        self.assertIn("keep the newest", DuplicatesView.TOOLTIP_TEXTS["keep_newest_delete"])
        self.assertIn("keep the largest", DuplicatesView.TOOLTIP_TEXTS["keep_largest_move"])
        self.assertIn("keep the oldest", DuplicatesView.TOOLTIP_TEXTS["keep_oldest_delete"])
        self.assertIn("keep the smallest", DuplicatesView.TOOLTIP_TEXTS["keep_smallest_move"])
        self.assertIn("Trash", DuplicatesView.TOOLTIP_TEXTS["delete_selected"])
        self.assertIn("CSV or JSON", DuplicatesView.TOOLTIP_TEXTS["export_results"])

    def test_duplicates_view_group_header_label_is_compact_and_descriptive(self):
        label = DuplicatesView._build_group_header_label(
            "abcdef1234567890",
            [{"group_size": 4}, {"group_size": 4}],
        )

        self.assertIn("4 duplicate file(s)", label)
        self.assertIn("abcdef123456", label)

    def test_duplicates_view_expand_all_groups_opens_every_group(self):
        view = type("DummyDuplicatesView", (), {})()
        view.group_items = {"group-a": "hash-a", "group-b": "hash-b"}
        view.tree = MagicMock()

        DuplicatesView.expand_all_groups(view)

        view.tree.item.assert_any_call("group-a", open=True)
        view.tree.item.assert_any_call("group-b", open=True)

    def test_duplicates_view_collapse_all_groups_closes_every_group(self):
        view = type("DummyDuplicatesView", (), {})()
        view.group_items = {"group-a": "hash-a", "group-b": "hash-b"}
        view.tree = MagicMock()

        DuplicatesView.collapse_all_groups(view)

        view.tree.item.assert_any_call("group-a", open=False)
        view.tree.item.assert_any_call("group-b", open=False)

    def test_duplicates_view_rebuild_tree_resolves_format_size(self):
        view = type("DummyDuplicatesView", (), {})()
        view.tree = MagicMock()
        view.item_records = {}
        view.group_items = {}
        view.entry_path = MagicMock()
        view.entry_path.text.return_value = ""

        entry = MagicMock()
        entry.size = 1024
        entry.extension = ".txt"
        entry.path = "/path/to/file.txt"
        
        record = {
            "entry": entry,
            "hash": "hash-abc",
            "group_size": 1
        }
        
        view._group_visible_records = lambda: {"hash-abc": [record]}
        view._build_group_header_label = lambda hash_val, records: "group-label"
        view._restore_expanded_group_state = MagicMock()
        view._rebuild_tree = DuplicatesView._rebuild_tree.__get__(view, type(view))
        
        view._rebuild_tree()
        
        view.tree.insert.assert_any_call(
            "",
            "end",
            values=("GROUP", "hash-abc", "group-label", "1.0 KB"),
            open=False
        )

    def test_settings_view_declares_global_tooltip_text(self):
        self.assertIn("duplicate detection", SettingsView.TOOLTIP_TEXTS["hash_algorithm"])
        self.assertIn("dependency caches", SettingsView.TOOLTIP_TEXTS["excluded_folders"])
        self.assertIn(".tmp", SettingsView.TOOLTIP_TEXTS["excluded_extensions"])
        self.assertIn("watch list", SettingsView.TOOLTIP_TEXTS["dashboard_add"])
        self.assertNotIn("dashboard_save", SettingsView.TOOLTIP_TEXTS)

    def test_settings_autosave_persists_on_change(self):
        """Settings must persist the moment the user changes a value, with
        a transient 'Saved ✓' indicator instead of an interrupting dialog
        or a hidden Save button."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.core.config import config as dfconfig

        existing_app = QApplication.instance()
        app = existing_app if existing_app is not None else QApplication([])

        snapshot = {
            "hash_algorithm": dfconfig.get("hash_algorithm"),
            "size_unit": dfconfig.get("size_unit"),
            "max_thread_workers": dfconfig.get("max_thread_workers"),
            "search_thread_workers": dfconfig.get("search_thread_workers"),
            "excluded_folders": dfconfig.get("excluded_folders"),
            "excluded_extensions": dfconfig.get("excluded_extensions"),
            "path_display_mode": dfconfig.get("path_display_mode"),
            "duplicate_default_keep_strategy": dfconfig.get("duplicate_default_keep_strategy"),
            "dashboard_paths": dfconfig.get("dashboard_paths"),
        }

        try:
            view = SettingsView(None, app=MagicMock())
            self.assertTrue(hasattr(view, "_autosave"))
            self.assertTrue(hasattr(view, "_saved_indicator"))

            view._autosave("hash_algorithm", "sha256")
            self.assertEqual(dfconfig.get("hash_algorithm"), "sha256")

            view._autosave("max_thread_workers", 8)
            self.assertEqual(dfconfig.get("max_thread_workers"), 8)

            view._autosave("excluded_folders", ["build", "node_modules"])
            self.assertEqual(dfconfig.get("excluded_folders"), ["build", "node_modules"])

            view._autosave("excluded_extensions", [".tmp", ".log"])
            self.assertEqual(dfconfig.get("excluded_extensions"), [".tmp", ".log"])

            self.assertEqual(view._saved_indicator.text(), "Saved ✓")

            view._autosave("hash_algorithm", "sha512")
            view._hide_saved_indicator()
            self.assertEqual(view._saved_indicator.text(), "")
        finally:
            for key, value in snapshot.items():
                dfconfig.set(key, value)

    def test_settings_view_theme_label_mirrors_sidebar(self):
        """The Settings theme control must mirror the sidebar Dark Mode
        checkbox — only the sidebar is writable."""
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt

        existing_app = QApplication.instance()
        app = existing_app if existing_app is not None else QApplication([])

        fake_app = MagicMock()
        fake_app.theme_chk.isChecked.return_value = False
        view = SettingsView(None, app=fake_app)
        self.assertTrue(hasattr(view, "lbl_theme"))
        self.assertFalse(hasattr(view, "cb_theme"))
        view._sync_theme_label()
        self.assertEqual(view.lbl_theme.text(), "Light (Cosmo)")

        fake_app.theme_chk.isChecked.return_value = True
        view._sync_theme_label()
        self.assertEqual(view.lbl_theme.text(), "Dark (Darkly)")

    def test_sidebar_does_not_filter_groups_by_tier(self):
        """The sidebar used to hide System Maintenance / Advanced Analysis
        groups from Basic users. That created a discoverability cliff —
        users on Basic could not even see that Forensics Lab existed.
        The sidebar must now show every group regardless of tier; the
        tier only controls in-view complexity."""
        from dataforge.ui.app import DataForgeApp

        self.assertFalse(
            hasattr(DataForgeApp, "GROUP_MIN_TIER"),
            "DataForgeApp.GROUP_MIN_TIER must be removed so the sidebar no "
            "longer hides groups based on Experience Level.",
        )
        self.assertTrue(hasattr(DataForgeApp, "TIER_RANK"))
        self.assertTrue(callable(getattr(DataForgeApp, "build_navigation_sidebar", None)))

    def test_baseview_destructive_preview_is_drillable(self):
        """The destructive preview must let the user opt out per row and
        surface a 'will be affected' total, instead of a truncated text
        message that hid individual rows past the first 8."""
        from PyQt5.QtWidgets import QApplication
        self.assertTrue(callable(getattr(BaseView, "confirm_destructive_preview", None)))
        QApplication.instance() or QApplication([])

    def test_cli_search_help_mentions_extension_sort_examples(self):
        runner = CliRunner()

        result = runner.invoke(main, ["search", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--count-only ignores --format", result.output)
        self.assertIn("Print only the number of matches; overrides", result.output)
        self.assertIn("--format", result.output)
        self.assertIn("fm search PATH --sort ext", result.output)
        self.assertIn("fm search PATH --sort ext --reverse", result.output)
        self.assertIn("fm search PATH --count-only", result.output)
        self.assertIn("fm search PATH --sort size --reverse --limit 20", result.output)

    def test_cli_search_supports_content_regex(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "report.txt"
            target.write_text("Order ID: 4821", encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--ext",
                    "txt",
                    "--content",
                    r"Order ID:\s+\d{4}",
                    "--content-regex",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.output.strip(), str(target))

    def test_cli_search_supports_case_sensitive_content(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "case.txt"
            target.write_text("ExactCase", encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--ext",
                    "txt",
                    "--content",
                    "exactcase",
                    "--case-sensitive",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.output.strip(), "")

            insensitive_result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--ext",
                    "txt",
                    "--content",
                    "exactcase",
                ],
            )

            self.assertEqual(insensitive_result.exit_code, 0)
            self.assertEqual(insensitive_result.output.strip(), str(target))

    def test_cli_search_supports_count_only(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "one.txt").write_text("shared", encoding="utf-8")
            (root / "two.txt").write_text("shared", encoding="utf-8")
            (root / "three.log").write_text("shared", encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--ext",
                    "txt",
                    "--content",
                    "shared",
                    "--count-only",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.output.strip(), "2")

    def test_cli_search_count_only_ignores_output_format(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "match.txt"
            target.write_text("matched", encoding="utf-8")

            result = runner.invoke(
                main,
                [
                    "search",
                    temp_dir,
                    "--ext",
                    "txt",
                    "--format",
                    "jsonl",
                    "--count-only",
                ],
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.output.strip(), "1")

    def test_remove_empty_folders_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            nested_empty = Path(temp_dir) / "outer" / "inner"
            nested_empty.mkdir(parents=True)
            (Path(temp_dir) / "keep").mkdir()
            (Path(temp_dir) / "keep" / "file.txt").write_text("data", encoding="utf-8")

            log = remove_empty_folders(temp_dir, dry_run=False)

            self.assertFalse(nested_empty.exists())
            self.assertFalse((Path(temp_dir) / "outer").exists())
            self.assertTrue(any("Removed empty folder" in line for line in log))

    def test_search_query_uses_fileentry_size_and_modified_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            large_old = Path(temp_dir) / "large_old.txt"
            recent_small = Path(temp_dir) / "recent_small.txt"
            ignored = Path(temp_dir) / "ignored.jpg"

            large_old.write_text("x" * 64, encoding="utf-8")
            recent_small.write_text("tiny", encoding="utf-8")
            ignored.write_text("image", encoding="utf-8")

            two_days_ago = time.time() - (2 * 86400)
            os.utime(large_old, (two_days_ago, two_days_ago))

            query = build_search_query(
                extensions="txt",
                min_size_bytes=32,
                older_than_days=1,
            )
            results = search_files(temp_dir, query)

            self.assertEqual([entry.filename for entry in results], ["large_old.txt"])

    def test_plugin_loader_discovers_internal_cleaner_plugin(self):
        repo_root = Path(__file__).resolve().parents[1]
        plugin_dir = repo_root / "dataforge" / "ui" / "plugins"

        loader = PluginLoader(str(plugin_dir), enabled=True)
        plugin_names = {plugin_cls.__name__ for plugin_cls in loader.load_plugins()}

        self.assertIn("MetadataCleanerPlugin", plugin_names)

    def test_cleaner_plugin_accepts_single_file_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "image.jpg"
            target.write_text("fake image", encoding="utf-8")

            plugin = type("DummyCleanerPlugin", (), {})()
            plugin.path_entry = MagicMock()
            plugin.path_entry.text.return_value = str(target)
            plugin.ext_entry = MagicMock()
            plugin.ext_entry.text.return_value = "jpg"
            plugin.depth_spin = MagicMock()
            plugin.depth_spin.value.return_value = -1
            plugin.tree = MagicMock()
            plugin.tree.get_children.return_value = []
            plugin.app = MagicMock()
            plugin._scan_worker = MagicMock()
            plugin._on_scan_complete = MagicMock()
            plugin.scan_results = []

            MetadataCleanerPlugin.start_scan(plugin)

            plugin.app.show_warning_dialog.assert_not_called()
            plugin.app.run_workflow.assert_called_once_with(
                plugin._scan_worker,
                plugin._on_scan_complete,
                str(target), ["jpg"], -1,
                progress=True,
                error_title="Metadata Scan Failed",
            )

    def test_organizer_copy_collision_policy_is_shared(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "root"
            destination = Path(temp_dir) / "dest"
            (root / "a").mkdir(parents=True)
            (root / "b").mkdir(parents=True)
            (root / "a" / "same.txt").write_text("one", encoding="utf-8")
            (root / "b" / "same.txt").write_text("two", encoding="utf-8")

            query = build_search_query(extensions="txt")
            log = Organizer.organize_files(str(root), query, "copy", str(destination), dry_run=False)

            self.assertTrue((destination / "same.txt").exists())
            self.assertTrue((destination / "same_1.txt").exists())
            self.assertEqual(len([line for line in log if line.startswith("Copied:")]), 2)

    def test_bulk_rename_collision_policy_is_shared(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "alpha-1.txt"
            second = Path(temp_dir) / "alpha-2.txt"
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")

            log = bulk_rename(temp_dir, r"alpha-\d", "renamed", recursive=False, dry_run=False)

            self.assertTrue((Path(temp_dir) / "renamed.txt").exists())
            self.assertTrue((Path(temp_dir) / "renamed_1.txt").exists())
            self.assertEqual(len([line for line in log if line.startswith("Renamed:")]), 2)


if __name__ == "__main__":
    unittest.main()
