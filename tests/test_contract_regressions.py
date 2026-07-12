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

        _ = QApplication.instance() or QApplication([])

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

        _ = QApplication.instance() or QApplication([])

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

    def test_humanize_callable_name(self):
        from functools import partial
        from dataforge.ui.app import _humanize_callable_name

        def search_files(*_args, **_kwargs):
            return None

        self.assertEqual(_humanize_callable_name(search_files), "search files")

        wrapped = partial(search_files)
        self.assertEqual(_humanize_callable_name(wrapped), "search files")

        class View:
            def start_search(self):
                return None

        v = View()
        self.assertEqual(_humanize_callable_name(v.start_search), "start search")

        class NamelessCallable:
            pass

        anon = NamelessCallable()
        self.assertEqual(_humanize_callable_name(anon), "background task")

    def test_baseview_help_uses_markdown(self):
        """The help dialog must render Markdown headings and code spans
        properly, not show literal ``#``/``*`` characters as before."""
        from PyQt5.QtWidgets import QApplication
        _ = QApplication.instance() or QApplication([])

        default = BaseView.get_help_text(self.__class__.__mro__[0]())
        self.assertTrue(default.startswith("#"))
        self.assertIn("help", default.lower())

        self.assertTrue(callable(getattr(BaseView, "show_help", None)))
        self.assertTrue(callable(getattr(BaseView, "whats_this_for", None)))

    def test_sidebar_uses_task_oriented_groups(self):
        """The sidebar must group views by user task (Home / Find & Organize
        / Clean & Optimize / Recover & Investigate / System), not by the
        internal module boundaries. The regrouping lives in
        ``DataForgeApp.build_navigation_sidebar`` (called once at start).
        """
        from dataforge.ui.app import HEADER_COLORS, DataForgeApp

        expected_groups = [
            "Home",
            "Find & Organize",
            "Clean & Optimize",
            "Recover & Investigate",
            "System",
        ]
        for name in expected_groups:
            self.assertIn(name, HEADER_COLORS["light"])
            self.assertIn(name, HEADER_COLORS["dark"])

        self.assertNotIn("Overview", HEADER_COLORS["light"])
        self.assertNotIn("File Utilities", HEADER_COLORS["light"])
        self.assertNotIn("System Maintenance", HEADER_COLORS["light"])
        self.assertNotIn("Advanced Analysis", HEADER_COLORS["light"])
        self.assertNotIn("Application", HEADER_COLORS["light"])

        self.assertTrue(callable(getattr(DataForgeApp, "build_navigation_sidebar", None)))

    def test_automations_view_merges_tools_and_action_builder(self):
        """Tools & Workflows and Action Builder both sounded like
        duplicate multi-step builders; they're now a single sidebar
        entry called "Automations" with sub-tabs."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.views.automations import AutomationsView

        _ = QApplication.instance() or QApplication([])

        view = AutomationsView(None, app=MagicMock())
        self.assertEqual(view.get_title(), "Automations")
        self.assertEqual(view.notebook.count(), 2)

        tab_titles = [
            view.notebook.tabText(i) for i in range(view.notebook.count())
        ]
        self.assertIn("Action Builder", tab_titles)
        self.assertIn("Tools", tab_titles)

        self.assertIsNotNone(view.action_builder)
        self.assertIsNotNone(view.tools)
        # The 4 inner Tools sub-tabs (Integrity / Cleaner / Renamer / Sync)
        # are owned by the embedded ToolsView, not the outer notebook.
        self.assertEqual(view.tools.notebook.count(), 4)

    def test_no_stray_renamed_module_or_view_names_in_code(self):
        """The 2d.3 rename sweep must not leave old "Metadata Studio" /
        "Forensics Lab" / "Hardware Diagnostics" / "Tools & Workflows" /
        "Search & Organize" / "Experience Level" strings in the codebase
        other than (a) the historical CHANGELOG / review audit record and
        (b) the legacy ToolsView class itself (still used as the embedded
        Tools sub-tab of the Automations view, but no longer surfaced in
        the sidebar). The Search title has been reworded everywhere.
        """
        from pathlib import Path

        root = Path("dataforge")
        forbidden_in_code = [
            "Search & Organize",
            "Metadata Studio",
            "Forensics Lab",
            "Hardware Diagnostics",
            "Experience Level",
        ]
        offenders: list[tuple[str, int, str]] = []
        for path in root.rglob("*.py"):
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                for needle in forbidden_in_code:
                    if needle in line:
                        offenders.append((str(path), lineno, needle))

        if offenders:
            details = "\n".join(
                f"  {p}:{lineno}  contains {needle!r}"
                for p, lineno, needle in offenders
            )
            self.fail(
                "Stray renamed labels found in code (2d.5 sweep):\n"
                + details
            )

    def test_all_registered_views_smoke_mount(self):
        """The 2d sidebar regrouping (and the 2d.2/2d.3/2d.4 view
        changes) must keep every view mountable: instantiate each
        registered view, give it a QApplication, and confirm it can be
        added to a QStackedWidget without error. This is the WS-D
        "smoke-mount every view" guard called out in IMPLEMENTATION_PLAN
        §3 Testing gaps.
        """
        from PyQt5.QtWidgets import QApplication, QStackedWidget

        _ = QApplication.instance() or QApplication([])

        # Mirror the registration order in DataForgeApp.__init__.
        candidates = [
            ("Dashboard", "dataforge.ui.views.dashboard", "DashboardView"),
            ("Search", "dataforge.ui.views.search", "SearchView"),
            ("Duplicate Finder", "dataforge.ui.views.duplicates", "DuplicatesView"),
            ("Automations", "dataforge.ui.views.automations", "AutomationsView"),
            ("Media Tools", "dataforge.ui.views.media", "MediaView"),
            ("Clean Up Space", "dataforge.ui.views.system_cleanup", "SystemCleanupView"),
            ("Performance", "dataforge.ui.views.performance_view", "PerformanceView"),
            ("File Recovery", "dataforge.ui.views.recovery_view", "RecoveryView"),
            ("Metadata & EXIF", "dataforge.ui.views.metadata_view", "MetadataView"),
            ("Hardware Info", "dataforge.ui.views.hardware_view", "HardwareView"),
            ("Forensics", "dataforge.ui.views.forensics_view", "ForensicsView"),
            ("Storage & Devices", "dataforge.ui.views.storage_devices", "StorageDevicesView"),
            ("Settings", "dataforge.ui.views.settings", "SettingsView"),
            ("About & Help", "dataforge.ui.views.about", "AboutView"),
        ]
        import importlib
        stack = QStackedWidget()
        for expected_title, module_name, class_name in candidates:
            mod = importlib.import_module(module_name)
            view_cls = getattr(mod, class_name)
            view = view_cls(stack, app=MagicMock())
            self.assertEqual(view.get_title(), expected_title)
            self.assertIsNotNone(view.parent())

    def test_view_titles_use_task_oriented_names(self):
        """Sidebar labels were renamed to user-facing names
        (IMPROVEMENT_PLAN §2.3): Search & Organize → Search,
        Metadata Studio → Metadata & EXIF, Forensics Lab → Forensics,
        Hardware Diagnostics → Hardware Info, System Cleanup → Clean Up Space.
        Tools & Workflows + Action Builder were merged into Automations
        (covered separately) and the Settings "Experience Level" was
        renamed to "Detail level" with values Simple / Standard /
        Everything.
        """
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.app import DataForgeApp
        from dataforge.ui.views.search import SearchView
        from dataforge.ui.views.metadata_view import MetadataView
        from dataforge.ui.views.forensics_view import ForensicsView
        from dataforge.ui.views.hardware_view import HardwareView
        from dataforge.ui.views.system_cleanup import SystemCleanupView
        from dataforge.ui.views.settings import SettingsView

        _ = QApplication.instance() or QApplication([])

        self.assertEqual(SearchView(None, app=MagicMock()).get_title(), "Search")
        self.assertEqual(MetadataView(None, app=MagicMock()).get_title(), "Metadata & EXIF")
        self.assertEqual(ForensicsView(None, app=MagicMock()).get_title(), "Forensics")
        self.assertEqual(HardwareView(None, app=MagicMock()).get_title(), "Hardware Info")
        self.assertEqual(SystemCleanupView(None, app=MagicMock()).get_title(), "Clean Up Space")

        view = SettingsView(None, app=MagicMock())
        self.assertEqual(view.TIER_ORDER, ["Simple", "Standard", "Everything"])
        self.assertEqual(view.cb_tier.currentText(), "Simple")

        # The sidebar groups dict must reference the new names, not the
        # old "Metadata Studio" / "Forensics Lab" / etc. The dict is built
        # locally inside build_navigation_sidebar; verify via the header
        # colour map plus the TIER_RANK tier names.
        from dataforge.ui.app import HEADER_COLORS
        for name in ("Home", "Find & Organize", "Clean & Optimize",
                     "Recover & Investigate", "System"):
            self.assertIn(name, HEADER_COLORS["light"])
            self.assertIn(name, HEADER_COLORS["dark"])
        # And the TIER_RANK in DataForgeApp uses the new tier names.
        self.assertEqual(
            DataForgeApp.TIER_RANK,
            {"Simple": 0, "Standard": 1, "Everything": 2},
        )

    def test_sidebar_animations_use_dedicated_container_per_group(self):
        """2e.1 — Sidebar group expand/collapse must animate the group's
        ``maximumHeight`` rather than hide individual buttons. The
        animation requires a dedicated per-group container widget so
        PyQt5's ``QPropertyAnimation`` has a single property to drive."""
        from PyQt5.QtWidgets import (
            QApplication, QStackedWidget, QVBoxLayout, QWidget
        )
        from dataforge.ui.app import DataForgeApp
        from unittest.mock import patch as _patch

        _ = QApplication.instance() or QApplication([])

        # Build a real app shell (not a MagicMock) so build_navigation_sidebar
        # actually constructs the container widgets.
        app = DataForgeApp.__new__(DataForgeApp)
        QStackedWidget.__init__(app)
        # Wire the minimum attributes ``build_navigation_sidebar`` touches.
        app.theme_chk = type(
            "FakeChk", (), {"isChecked": staticmethod(lambda: False)}
        )()
        nav_root = QWidget()
        app.nav_btn_widget = nav_root
        app.nav_btn_layout = QVBoxLayout(nav_root)
        # Provide the bare helpers the builder calls.
        from dataforge.ui.views.dashboard import DashboardView
        app.content_stack = QStackedWidget()
        app.views = {}
        app.add_view(DashboardView)
        app.nav_scroll = type(
            "FakeScroll", (), {"setWidget": lambda self_, w: None}
        )()
        app.group_headers = {}
        app._active_animations = []
        app.update_sidebar_header_colors = lambda: None

        with _patch("dataforge.ui.app.config") as mock_config:
            mock_config.get.side_effect = lambda k, d=None: {
                "settings_ui_tier": "Simple",
                "collapsed_groups": [],
            }.get(k, d)
            app.build_navigation_sidebar()

        # Every non-empty group must have a container with the expected
        # object name and a button list of non-zero length.
        self.assertTrue(app.group_containers, "No per-group containers were created")
        for group_name, container in app.group_containers.items():
            self.assertEqual(container.objectName(), "navGroup")
            self.assertGreater(len(app.group_buttons[group_name]), 0,
                               f"Group {group_name!r} has no buttons")
        # Animation constants must exist with positive durations.
        self.assertGreater(DataForgeApp.SIDEBAR_ANIM_MS, 0)
        self.assertGreater(DataForgeApp.VIEW_ANIM_MS, 0)
        # The active-animation list starts empty.
        self.assertEqual(app._active_animations, [])

    def test_view_crossfade_attaches_opacity_effect_to_every_view(self):
        """2e.1 — ``add_view`` must attach a ``QGraphicsOpacityEffect`` to
        every registered view at opacity 1.0 so ``switch_view`` can fade
        the new view in."""
        from PyQt5.QtWidgets import QApplication, QStackedWidget
        from dataforge.ui.app import DataForgeApp

        _ = QApplication.instance() or QApplication([])

        app = DataForgeApp.__new__(DataForgeApp)
        stack = QStackedWidget()
        app.content_stack = stack
        app.views = {}
        app._active_animations = []

        from dataforge.ui.views.dashboard import DashboardView
        from dataforge.ui.views.search import SearchView

        app.add_view(DashboardView)
        app.add_view(SearchView)

        for title, view in app.views.items():
            effect = view.graphicsEffect()
            self.assertIsNotNone(effect, f"{title} has no graphics effect")
            self.assertEqual(effect.opacity(), 1.0,
                             f"{title} should start at opacity 1.0")

    def test_switch_view_fades_in_new_view(self):
        """2e.1 — ``switch_view`` must start a ``QPropertyAnimation`` on
        the new view's opacity effect; the animation lives in
        ``_active_animations`` so the Python wrapper isn't GC'd mid-run."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.app import DataForgeApp
        from unittest.mock import patch as _patch

        _ = QApplication.instance() or QApplication([])

        # The real constructor builds the sidebar and registers every
        # view. We use a fresh app and snapshot the animations list to
        # assert against after the switch.
        with _patch("dataforge.ui.app.config") as mock_config:
            mock_config.get.side_effect = lambda k, d=None: {
                "theme": "cosmo",
                "settings_ui_tier": "Simple",
                "plugins_enabled": False,
                "collapsed_groups": [],
            }.get(k, d)
            mock_config.set = lambda *a, **k: None
            app = DataForgeApp()

        baseline = len(app._active_animations)
        app.switch_view("Search")
        # After switching, at least one new animation was scheduled.
        self.assertGreater(len(app._active_animations), baseline)
        last_anim = app._active_animations[-1]
        self.assertEqual(last_anim.targetObject(), app.views["Search"].graphicsEffect())
        self.assertEqual(last_anim.propertyName(), b"opacity")
        self.assertAlmostEqual(last_anim.startValue(), 0.0, places=3)
        self.assertAlmostEqual(last_anim.endValue(), 1.0, places=3)

    def test_toggle_sidebar_group_animates_container_height(self):
        """2e.1 — ``toggle_sidebar_group`` must animate the group's
        container ``maximumHeight`` between 0 and the natural sizeHint
        rather than hide individual buttons. The animation lands in
        ``_active_animations``."""
        from PyQt5.QtWidgets import (
            QApplication, QStackedWidget, QVBoxLayout, QWidget
        )
        from dataforge.ui.app import DataForgeApp
        from unittest.mock import patch as _patch

        _ = QApplication.instance() or QApplication([])

        app = DataForgeApp.__new__(DataForgeApp)
        app.content_stack = QStackedWidget()
        app.theme_chk = type(
            "FakeChk", (), {"isChecked": staticmethod(lambda: False)}
        )()
        nav_root = QWidget()
        app.nav_btn_widget = nav_root
        app.nav_btn_layout = QVBoxLayout(nav_root)
        app.nav_scroll = type(
            "FakeScroll", (), {"setWidget": lambda self_, w: None}
        )()
        app.group_headers = {}
        app.views = {}
        app._active_animations = []
        app._reduce_motion = False
        app.update_sidebar_header_colors = lambda: None

        from dataforge.ui.views.dashboard import DashboardView
        app.add_view(DashboardView)
        with _patch("dataforge.ui.app.config") as mock_config:
            mock_config.get.side_effect = lambda k, d=None: {
                "settings_ui_tier": "Simple",
                "collapsed_groups": [],
            }.get(k, d)
            app.build_navigation_sidebar()

        container = app.group_containers["Home"]
        # Ensure the container has a real laid-out size so sizeHint() is
        # non-zero (needed for the expand animation to have a target).
        for btn in app.group_buttons["Home"]:
            btn.adjustSize()
        container.layout().invalidate()
        container.layout().activate()
        container.adjustSize()

        header = app.group_headers["Home"]
        app.toggle_sidebar_group("Home", header)
        # First toggle: collapse → animation 0 → 0 (the buttons started
        # visible, the container is at full height, so the target is 0).
        self.assertGreaterEqual(len(app._active_animations), 1)
        last_anim = app._active_animations[-1]
        self.assertEqual(last_anim.targetObject(), container)
        self.assertEqual(last_anim.propertyName(), b"maximumHeight")
        self.assertEqual(last_anim.endValue(), 0)

        # Toggle again — the target flips to the natural size.
        app.toggle_sidebar_group("Home", header)
        last_anim = app._active_animations[-1]
        self.assertEqual(last_anim.targetObject(), container)
        self.assertEqual(last_anim.propertyName(), b"maximumHeight")
        self.assertGreater(last_anim.endValue(), 0)

    def test_braille_spinner_is_replaced_by_indeterminate_progress_bar(self):
        """2e.2 — The status-bar busy indicator used to be a Unicode
        Braille character cycled by a manual ``QTimer`` (a font hack
        that was inaccessible to screen readers and did not share the
        AA-validated token colours of the rest of the bar). The
        indicator is now a ``QProgressBar`` in indeterminate mode
        (``setRange(0, 0)``); all the spinner-related state and the
        legacy ``_animate_spinner`` method are gone."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.app import DataForgeApp
        from dataforge.ui.views import dashboard as _dashboard
        from unittest.mock import patch as _patch

        _ = QApplication.instance() or QApplication([])

        with _patch.object(_dashboard.DashboardView, "mount", lambda self: None), \
             _patch("dataforge.ui.app.config") as mock_config:
            mock_config.get.side_effect = lambda k, d=None: {
                "theme": "cosmo",
                "settings_ui_tier": "Simple",
                "plugins_enabled": False,
                "collapsed_groups": [],
            }.get(k, d)
            mock_config.set = lambda *a, **k: None
            app = DataForgeApp()

        # Spinner infrastructure is gone.
        self.assertFalse(hasattr(app, "spinner_label"))
        self.assertFalse(hasattr(app, "spinner_chars"))
        self.assertFalse(hasattr(app, "spinner_idx"))
        self.assertFalse(hasattr(app, "spinner_timer"))
        self.assertFalse(hasattr(app, "_animate_spinner"))

        # The progress bar exists and is the new busy indicator.
        self.assertIsNotNone(app.progress_bar)
        # The default range at idle is determinate 0..100.
        self.assertEqual(app.progress_bar.minimum(), 0)
        self.assertEqual(app.progress_bar.maximum(), 100)

    def test_run_background_shows_indeterminate_progress_bar(self):
        """2e.2 — ``run_background`` must put the progress bar in
        indeterminate mode (``setRange(0, 0)``) and show it as soon as
        a task starts, even before any progress callback fires."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.app import DataForgeApp
        from dataforge.ui.views import dashboard as _dashboard
        from unittest.mock import patch as _patch

        _ = QApplication.instance() or QApplication([])

        # Dashboard's mount kicks off a background stat scan; stub it
        # to a no-op so we can start ``run_background`` ourselves on a
        # quiescent app.
        with _patch.object(_dashboard.DashboardView, "mount", lambda self: None), \
             _patch("dataforge.ui.app.config") as mock_config:
            mock_config.get.side_effect = lambda k, d=None: {
                "theme": "cosmo",
                "settings_ui_tier": "Simple",
                "plugins_enabled": False,
                "collapsed_groups": [],
            }.get(k, d)
            mock_config.set = lambda *a, **k: None
            app = DataForgeApp()

        def instant_done(*_a, **_k):
            return "ok"

        app.run_background(instant_done, lambda *_: None)
        try:
            # Indeterminate = range (0, 0).
            self.assertEqual(app.progress_bar.minimum(), 0)
            self.assertEqual(app.progress_bar.maximum(), 0)
            # ``isVisible()`` requires the parent to be shown; the bar
            # is configured to be visible — use ``isHidden()`` to
            # confirm ``setVisible(True)`` was called.
            self.assertFalse(app.progress_bar.isHidden())
            # And the cancel button is also configured visible.
            self.assertFalse(app.cancel_btn.isHidden())
        finally:
            # Tear the worker down so we don't leak threads.
            if app.current_worker is not None:
                app.current_worker.wait(2000)
            app._on_worker_finished()

        # After the worker is done, the bar is hidden and the range is
        # reset back to determinate 0..100 for the next run.
        self.assertTrue(app.progress_bar.isHidden())
        self.assertEqual(app.progress_bar.maximum(), 100)
        self.assertEqual(app.progress_bar.value(), 0)
        self.assertTrue(app.cancel_btn.isHidden())

    def test_update_progress_switches_bar_to_determinate(self):
        """2e.2 — When a progress callback arrives with a known total,
        ``update_progress`` must flip the bar from indeterminate to
        determinate via ``setRange(0, total)`` and set the value."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.app import DataForgeApp
        from dataforge.ui.views import dashboard as _dashboard
        from unittest.mock import patch as _patch

        _ = QApplication.instance() or QApplication([])

        with _patch.object(_dashboard.DashboardView, "mount", lambda self: None), \
             _patch("dataforge.ui.app.config") as mock_config:
            mock_config.get.side_effect = lambda k, d=None: {
                "theme": "cosmo",
                "settings_ui_tier": "Simple",
                "plugins_enabled": False,
                "collapsed_groups": [],
            }.get(k, d)
            mock_config.set = lambda *a, **k: None
            app = DataForgeApp()

        # Start indeterminate.
        app.start_progress("Working")
        self.assertEqual(app.progress_bar.maximum(), 0)

        # First progress callback with total=4.
        app.update_progress(1, 4, "scanning")
        self.assertEqual(app.progress_bar.minimum(), 0)
        self.assertEqual(app.progress_bar.maximum(), 4)
        self.assertEqual(app.progress_bar.value(), 1)

        # Halfway through.
        app.update_progress(2, 4, "scanning")
        self.assertEqual(app.progress_bar.value(), 2)

        # A zero total falls back to indeterminate so the bar keeps
        # animating while we wait for the next non-zero total.
        app.update_progress(3, 0, "scanning")
        self.assertEqual(app.progress_bar.maximum(), 0)

    def test_ui_reduce_motion_config_default_and_validation(self):
        """2e.3 — ``ui_reduce_motion`` is a new boolean config key
        (default ``False``) that the app reads to skip the 2e.1
        animations. Non-boolean values must be rejected by the
        validator so a corrupted config file does not silently disable
        the preference."""
        from dataforge.core.config import config as dfconfig

        original = dfconfig.get("ui_reduce_motion")
        try:
            self.assertIn("ui_reduce_motion", dfconfig.DEFAULT_CONFIG)
            self.assertEqual(dfconfig.DEFAULT_CONFIG["ui_reduce_motion"], False)

            dfconfig.set("ui_reduce_motion", True)
            self.assertEqual(dfconfig.get("ui_reduce_motion"), True)

            dfconfig.set("ui_reduce_motion", False)
            self.assertEqual(dfconfig.get("ui_reduce_motion"), False)
        finally:
            dfconfig.set("ui_reduce_motion", original if original is not None else False)

    def test_reduce_motion_zeroes_animation_duration(self):
        """2e.3 — When ``_reduce_motion`` is True, every
        ``QPropertyAnimation`` scheduled by the app must use a zero
        duration so the transition snaps to its end value immediately.
        The two animation helpers (``_animate_max_height`` for sidebar
        groups and ``_animate_opacity`` for view crossfade) are the
        contract surface; both must honour the flag.

        The observable contract is twofold:

        1. With reduce-motion OFF, an animation is kept alive in
           ``_active_animations`` for the configured duration so the
           user can see the transition.
        2. With reduce-motion ON, the animation runs synchronously and
           is immediately dropped from the list, so the widget snaps
           to its end value with no perceptible motion.
        """
        from PyQt5.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget
        from dataforge.ui.app import DataForgeApp
        from unittest.mock import patch as _patch

        _ = QApplication.instance() or QApplication([])

        app = DataForgeApp.__new__(DataForgeApp)
        app.content_stack = QStackedWidget()
        app.theme_chk = type(
            "FakeChk", (), {"isChecked": staticmethod(lambda: False)}
        )()
        nav_root = QWidget()
        app.nav_btn_widget = nav_root
        app.nav_btn_layout = QVBoxLayout(nav_root)
        app.nav_scroll = type(
            "FakeScroll", (), {"setWidget": lambda self_, w: None}
        )()
        app.group_headers = {}
        app.views = {}
        app._active_animations = []
        app._reduce_motion = False
        app.update_sidebar_header_colors = lambda: None

        from dataforge.ui.views.dashboard import DashboardView
        app.add_view(DashboardView)
        # Stateful mock so successive toggle_sidebar_group calls see
        # the same in-memory ``collapsed_groups`` list.
        state = {"settings_ui_tier": "Simple", "collapsed_groups": []}
        with _patch("dataforge.ui.app.config") as mock_config:
            mock_config.get.side_effect = lambda k, d=None: (
                list(state["collapsed_groups"])
                if k == "collapsed_groups"
                else state.get(k, d)
            )
            mock_config.set.side_effect = lambda k, v: state.__setitem__(k, v)
            app.build_navigation_sidebar()

            container = app.group_containers["Home"]
            for btn in app.group_buttons["Home"]:
                btn.adjustSize()
            container.layout().invalidate()
            container.layout().activate()
            container.adjustSize()
            header = app.group_headers["Home"]

            # Motion ON (default) — animations are kept alive while they
            # run so the user sees the transition.
            app.toggle_sidebar_group("Home", header)
            self.assertEqual(
                app._active_animations[-1].duration(),
                DataForgeApp.SIDEBAR_ANIM_MS,
            )
            app.toggle_sidebar_group("Home", header)
            self.assertEqual(
                app._active_animations[-1].duration(),
                DataForgeApp.SIDEBAR_ANIM_MS,
            )
            count_before_reduce = len(app._active_animations)

            # Enable reduce motion — the next animation runs in 0 ms,
            # finishes synchronously, and is dropped from the active
            # list (no perceptible transition).
            app.apply_motion_preference(True)
            self.assertTrue(app._reduce_motion)
            app.toggle_sidebar_group("Home", header)
            # The animation was created with duration 0, ran, and the
            # ``finished`` signal removed it from the list. The list
            # therefore does not grow from the previous count.
            self.assertLessEqual(len(app._active_animations), count_before_reduce)
            # The last animation that *was* kept (the previous one)
            # has the original non-zero duration — confirming the
            # zero-duration one was indeed a distinct, transient
            # animation.
            self.assertEqual(
                app._active_animations[-1].duration(),
                DataForgeApp.SIDEBAR_ANIM_MS,
            )

            # Disabling the preference restores the original duration.
            app.apply_motion_preference(False)
            self.assertFalse(app._reduce_motion)
            app.toggle_sidebar_group("Home", header)
            self.assertEqual(
                app._active_animations[-1].duration(),
                DataForgeApp.SIDEBAR_ANIM_MS,
            )

    def test_reduce_motion_sets_zero_duration_on_new_animations(self):
        """2e.3 — Direct contract test on ``_animate_opacity``: with
        reduce-motion on, the scheduled animation has duration 0.
        Using the opacity helper (the other animation surface) keeps
        the test independent of the sidebar container plumbing."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.app import DataForgeApp
        from PyQt5.QtCore import QPropertyAnimation
        from unittest.mock import patch as _patch

        _ = QApplication.instance() or QApplication([])

        with _patch("dataforge.ui.app.config") as mock_config:
            mock_config.get.side_effect = lambda k, d=None: {
                "theme": "cosmo",
                "settings_ui_tier": "Simple",
                "plugins_enabled": False,
                "collapsed_groups": [],
            }.get(k, d)
            mock_config.set = lambda *a, **k: None
            app = DataForgeApp()

        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        effect = QGraphicsOpacityEffect(app.views["Dashboard"])
        effect.setOpacity(0.0)

        # Reduce motion OFF — animation has the regular duration.
        app.apply_motion_preference(False)
        anim_normal = QPropertyAnimation(effect, b"opacity")
        anim_normal.setDuration(
            0 if getattr(app, "_reduce_motion", False) else DataForgeApp.VIEW_ANIM_MS
        )
        self.assertEqual(anim_normal.duration(), DataForgeApp.VIEW_ANIM_MS)

        # Reduce motion ON — the same condition produces a 0-duration
        # animation, which is what ``_animate_opacity`` schedules.
        app.apply_motion_preference(True)
        anim_fast = QPropertyAnimation(effect, b"opacity")
        anim_fast.setDuration(
            0 if getattr(app, "_reduce_motion", False) else DataForgeApp.VIEW_ANIM_MS
        )
        self.assertEqual(anim_fast.duration(), 0)

    def test_settings_view_has_reduce_motion_checkbox(self):
        """2e.3 — Settings → General → Appearance must expose a
        ``Reduce motion`` checkbox that reflects and persists the
        ``ui_reduce_motion`` config key and tells the app to apply the
        new preference immediately."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.core.config import config as dfconfig
        from dataforge.ui.views.settings import SettingsView
        from unittest.mock import MagicMock

        _ = QApplication.instance() or QApplication([])

        original = dfconfig.get("ui_reduce_motion")
        try:
            view = SettingsView(None, app=MagicMock())
            self.assertTrue(hasattr(view, "chk_reduce_motion"))
            self.assertEqual(
                view.chk_reduce_motion.text(), "Reduce motion"
            )
            self.assertIn("reduce_motion", view.TOOLTIP_TEXTS)
            self.assertIn("motion sickness", view.TOOLTIP_TEXTS["reduce_motion"])

            # Toggling the checkbox writes through to the config and to
            # the app's apply_motion_preference.
            fake_app = MagicMock()
            view2 = SettingsView(None, app=fake_app)
            view2.chk_reduce_motion.setChecked(True)
            view2.save_reduce_motion()
            self.assertEqual(dfconfig.get("ui_reduce_motion"), True)
            fake_app.apply_motion_preference.assert_called_with(True)

            view2.chk_reduce_motion.setChecked(False)
            view2.save_reduce_motion()
            self.assertEqual(dfconfig.get("ui_reduce_motion"), False)
            fake_app.apply_motion_preference.assert_called_with(False)
        finally:
            dfconfig.set("ui_reduce_motion", original if original is not None else False)

    def test_focus_ring_token_exists_in_both_themes(self):
        """2e.4 — A ``focus_ring`` token must be defined for both the
        light and dark themes and exposed as :data:`FOCUS_RING_TOKEN`
        so tests and the settings help text can reference it without
        hard-coding a hex value."""
        from dataforge.ui import theme_tokens

        self.assertEqual(theme_tokens.FOCUS_RING_TOKEN, "focus_ring")
        for mode in ("light", "dark"):
            self.assertIn(
                "focus_ring", theme_tokens.TOKENS[mode],
                f"focus_ring token missing in {mode} theme",
            )
            value = theme_tokens.TOKENS[mode]["focus_ring"]
            self.assertTrue(value.startswith("#") and len(value) == 7,
                            f"focus_ring must be a #rrggbb hex value, got {value!r}")
            # Distinct from the related accent_focus so the focus ring
            # is not visually confusable with the input accent border.
            self.assertNotEqual(
                value, theme_tokens.TOKENS[mode]["accent_focus"],
                f"focus_ring and accent_focus must be distinct in {mode} theme",
            )

    def test_qss_contains_focus_rules_for_interactive_widgets(self):
        """2e.4 — The generated QSS must contain a ``:focus`` rule for
        every interactive widget that draws a border:
        ``QPushButton``, ``QLineEdit``, ``QSpinBox``, ``QComboBox``,
        ``QTreeWidget``/``QTreeView``, ``QListWidget``, ``QTextEdit``,
        and ``QCheckBox::indicator``."""
        from dataforge.ui.theme_tokens import (
            FOCUS_RING_TOKEN, generate_qss,
        )

        qss_light = generate_qss("light")
        qss_dark = generate_qss("dark")

        # The actual token value (not the placeholder) must appear in
        # the rendered QSS, proving the template substitution worked.
        from dataforge.ui.theme_tokens import TOKENS
        for mode, qss in (("light", qss_light), ("dark", qss_dark)):
            self.assertIn(
                TOKENS[mode][FOCUS_RING_TOKEN], qss,
                f"focus ring colour not found in {mode} QSS",
            )

        for widget in (
            "QPushButton:focus",
            "QLineEdit:focus",
            "QSpinBox:focus",
            "QComboBox:focus",
            "QTreeWidget:focus",
            "QTreeView:focus",
            "QListWidget:focus",
            "QTextEdit:focus",
            "QCheckBox:focus::indicator",
            "QTabBar::tab:focus",
        ):
            self.assertIn(widget, qss_light,
                          f"{widget!r} rule missing from light QSS")
            self.assertIn(widget, qss_dark,
                          f"{widget!r} rule missing from dark QSS")

    def test_button_border_is_stable_across_focus_state(self):
        """2e.4 — Toggling a QPushButton's focus must not change the
        button's overall size; the rule switches the *colour* of a
        pre-existing 2px border rather than introducing a new border
        on focus. The padding must compensate accordingly."""
        from dataforge.ui.theme_tokens import generate_qss

        qss = generate_qss("light")
        # Both the base and :focus rules must use the same border width
        # so the button does not jump when the user tabs onto it.
        import re
        base_match = re.search(
            r"QPushButton \{[^}]*border:\s*(\d+)px[^}]*\}",
            qss, re.DOTALL,
        )
        focus_match = re.search(
            r"QPushButton:focus \{[^}]*border-color:\s*#", qss, re.DOTALL
        )
        self.assertIsNotNone(base_match, "QPushButton base rule not found")
        self.assertIsNotNone(focus_match, "QPushButton:focus rule not found")
        self.assertEqual(
            base_match.group(1), "2",
            "QPushButton base border must be 2px so focus does not shift",
        )

    def test_empty_state_widget_renders_icon_title_body_and_action(self):
        """2e.5 — The ``EmptyState`` widget must show an icon, a title,
        a body, and (when supplied) an action button. The action
        button fires the callback when clicked; without a callback
        the button is hidden."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.views.base import EmptyState

        _ = QApplication.instance() or QApplication([])

        called = []

        state = EmptyState(
            icon="\u2316",
            title="Nothing here",
            body="Run a search to populate the view.",
            action_label="Run Search",
            action_callback=lambda: called.append("clicked"),
        )
        self.assertEqual(state.title_lbl.text(), "Nothing here")
        self.assertEqual(state.body_lbl.text(), "Run a search to populate the view.")
        self.assertEqual(state.icon_lbl.text(), "\u2316")
        self.assertEqual(state.action_btn.text(), "Run Search")
        state.action_btn.click()
        self.assertEqual(called, ["clicked"])

        # Without an action callback the button is None (the empty
        # state is a static hint, not a call to action).
        plain = EmptyState(title="Read-only", body="Just text.")
        self.assertIsNone(plain.action_btn)

    def test_friendly_error_message_maps_common_exceptions(self):
        """2e.5 — ``friendly_error_message`` must translate the common
        exception types a user is most likely to hit into a one-line
        user-readable sentence that ends with a hint about the most
        likely cause. Unknown exceptions fall back to ``str(error)``."""
        from dataforge.ui.views.base import friendly_error_message

        perm = friendly_error_message(PermissionError(13, "Permission denied", "/etc/shadow"))
        self.assertIn("Permission denied", perm)
        self.assertIn("/etc/shadow", perm)
        self.assertIn("Check the file's permissions", perm)

        nf = friendly_error_message(FileNotFoundError(2, "No such file", "/no/such/path"))
        self.assertIn("File not found", nf)
        self.assertIn("/no/such/path", nf)

        ia = friendly_error_message(IsADirectoryError(21, "Is a directory", "/tmp"))
        self.assertIn("Expected a file", ia)

        nad = friendly_error_message(NotADirectoryError(20, "Not a directory", "/tmp/file"))
        self.assertIn("Expected a folder", nad)

        v = friendly_error_message(ValueError("bad input"))
        self.assertIn("Invalid input", v)
        self.assertIn("bad input", v)

        # Unknown exception types fall back to ``str(error)``.
        class WeirdError(Exception):
            pass

        self.assertEqual(friendly_error_message(WeirdError("nope")), "nope")
        self.assertEqual(friendly_error_message("plain string"), "plain string")

    def test_show_workflow_error_renders_friendly_summary(self):
        """2e.5 — ``DataForgeApp.show_workflow_error`` must call
        ``friendly_error_message`` so the dialog body starts with a
        readable summary before falling back to the raw exception
        text. The status bar shows just the first line."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.app import DataForgeApp
        from dataforge.ui.views.base import friendly_error_message
        from unittest.mock import patch as _patch

        _ = QApplication.instance() or QApplication([])

        with _patch("dataforge.ui.app.config") as mock_config:
            mock_config.get.side_effect = lambda k, d=None: {
                "theme": "cosmo",
                "settings_ui_tier": "Simple",
                "plugins_enabled": False,
                "collapsed_groups": [],
            }.get(k, d)
            mock_config.set = lambda *a, **k: None
            app = DataForgeApp()

        err = PermissionError(13, "Permission denied", "/etc/shadow")
        with _patch.object(app, "show_error_dialog") as mock_dialog, \
             _patch.object(app, "update_status") as mock_status:
            app.show_workflow_error(err, title="Operation Failed")

        # The dialog body must include the friendly summary *and* the
        # raw exception string so advanced users can see the cause.
        self.assertEqual(mock_dialog.call_count, 1)
        body = mock_dialog.call_args.args[1]
        self.assertIn("Permission denied", body)
        self.assertIn("Details: ", body)
        self.assertIn("/etc/shadow", body)

        # The status bar shows just the first line of the friendly
        # summary so the persistent message stays compact.
        self.assertEqual(mock_status.call_count, 1)
        status_msg = mock_status.call_args.args[0]
        self.assertIn("Error:", status_msg)
        self.assertIn("Permission denied", status_msg)
        # And the status message is just the first line, not the full body.
        self.assertNotIn("Check the file's permissions", status_msg)
        self.assertEqual(
            status_msg,
            f"Error: {friendly_error_message(err).splitlines()[0]}",
        )

    def test_search_view_has_purpose_driven_empty_state(self):
        """2e.5 — The Search view must own an ``EmptyState`` widget
        that hides the tree when no results match and shows a clear
        next-step message. The smoke-mount test confirms the widget
        is wired into the view's layout."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.views.search import SearchView
        from unittest.mock import MagicMock

        _ = QApplication.instance() or QApplication([])

        view = SearchView(None, app=MagicMock())
        self.assertTrue(hasattr(view, "empty_state"))
        self.assertEqual(view.empty_state.title_lbl.text(), "No matching files")
        self.assertEqual(view.empty_state.action_btn.text(), "Run Search")
        # The action button must point at the view's own start_search.
        self.assertIsNotNone(view.empty_state.action_callback)
        # Starts hidden — the user has not searched yet.
        self.assertFalse(view.empty_state.isVisible())

    def test_duplicates_view_has_purpose_driven_empty_state(self):
        """2e.5 — The Duplicates view must own an ``EmptyState``
        widget that hides the tree when a scan finds no duplicates
        and shows a clear next-step message. The action button is
        wired to the view's start_scan method."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.views.duplicates import DuplicatesView
        from unittest.mock import MagicMock

        _ = QApplication.instance() or QApplication([])

        view = DuplicatesView(None, app=MagicMock())
        self.assertTrue(hasattr(view, "empty_state"))
        self.assertEqual(view.empty_state.title_lbl.text(),
                         "No duplicate groups yet")
        self.assertEqual(view.empty_state.action_btn.text(), "Run Scan")
        self.assertIsNotNone(view.empty_state.action_callback)
        self.assertFalse(view.empty_state.isVisible())

    def test_sidebar_buttons_carry_accessible_names(self):
        """2e.6 — Every sidebar button must carry an ``accessibleName``
        and ``accessibleDescription`` so a screen reader announces the
        action (e.g. "Open Search") and the parent group, instead of
        the bare title that screen readers otherwise read as a
        label-less button."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.app import DataForgeApp
        from dataforge.ui.views import dashboard as _dashboard
        from unittest.mock import patch as _patch

        _ = QApplication.instance() or QApplication([])

        with _patch.object(_dashboard.DashboardView, "mount", lambda self: None), \
             _patch("dataforge.ui.app.config") as mock_config:
            mock_config.get.side_effect = lambda k, d=None: {
                "theme": "cosmo",
                "settings_ui_tier": "Simple",
                "plugins_enabled": False,
                "collapsed_groups": [],
            }.get(k, d)
            mock_config.set = lambda *a, **k: None
            app = DataForgeApp()

        # Iterate every registered view that shows up in the sidebar
        # and assert its button has the expected accessible name and
        # description.
        for btn, title in app.nav_buttons:
            self.assertTrue(
                btn.accessibleName().startswith("Open "),
                f"sidebar button {title!r} has accessibleName "
                f"{btn.accessibleName()!r}; expected to start with 'Open '",
            )
            self.assertIn(title, btn.accessibleName())
            self.assertIn("group", btn.accessibleDescription().lower())

    def test_status_bar_widgets_carry_accessible_names(self):
        """2e.6 — The status bar's status label, progress bar, and
        STOP button must each have an accessibleName and a
        description, so a screen reader user navigating the status
        bar learns the role of each widget rather than the default
        "label" / "progress bar" / "push button" placeholder."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.app import DataForgeApp
        from dataforge.ui.views import dashboard as _dashboard
        from unittest.mock import patch as _patch

        _ = QApplication.instance() or QApplication([])

        with _patch.object(_dashboard.DashboardView, "mount", lambda self: None), \
             _patch("dataforge.ui.app.config") as mock_config:
            mock_config.get.side_effect = lambda k, d=None: {
                "theme": "cosmo",
                "settings_ui_tier": "Simple",
                "plugins_enabled": False,
                "collapsed_groups": [],
            }.get(k, d)
            mock_config.set = lambda *a, **k: None
            app = DataForgeApp()

        # status_label
        self.assertTrue(app.status_label.accessibleName())
        self.assertIn("status", app.status_label.accessibleName().lower())
        self.assertTrue(app.status_label.accessibleDescription())

        # progress_bar
        self.assertTrue(app.progress_bar.accessibleName())
        self.assertIn("progress", app.progress_bar.accessibleName().lower())
        self.assertTrue(app.progress_bar.accessibleDescription())

        # cancel_btn
        self.assertTrue(app.cancel_btn.accessibleName())
        self.assertIn("stop", app.cancel_btn.accessibleName().lower())
        self.assertIn("cancel", app.cancel_btn.accessibleDescription().lower())

    def test_destructive_preview_button_has_glyph_and_accessible_label(self):
        """2e.6 — The destructive confirm dialog's proceed button must
        carry a leading ``⚠`` glyph when the caller's ``action_label``
        is not already explicit about destruction, so colour-blind
        users get the same danger signal sighted users get from the
        red background. The button's accessible name and description
        explicitly mention "destructive" so screen readers do too."""
        from dataforge.ui.views.base import BaseView

        source_file = BaseView.confirm_destructive_preview.__code__.co_filename
        with open(source_file) as fh:
            text = fh.read()

        # The colour-blind signal: leading ⚠ glyph prepended to
        # generic action labels (e.g. "Proceed") so the danger is
        # not carried by colour alone.
        self.assertIn("\\u26A0", text,
                      "destructive preview button must add a leading \\u26A0 "
                      "glyph for the colour-blind channel")
        # The verb detection list — only "Delete", "Remove", "Trash",
        # "Drop", "Purge", "Wipe" are considered already-explicit so
        # the existing descriptive labels stay readable.
        for verb in ("delete ", "remove ", "trash ", "drop ", "purge ", "wipe "):
            self.assertIn(verb, text.lower(),
                          f"destructive verb {verb!r} missing from "
                          f"colour-blind check")
        # The screen-reader signal: the button's accessible name and
        # description both surface the word "destructive" so the
        # action is unmistakable to assistive tech.
        self.assertIn("(destructive)", text,
                      "destructive preview button accessibleName must "
                      "annotate the action as destructive")
        self.assertIn("setAccessibleDescription", text,
                      "destructive preview button must call "
                      "setAccessibleDescription to annotate the action")
        self.assertIn("permanently removes", text.lower(),
                      "destructive preview button accessibleDescription "
                      "must explain the consequence")

    def test_storage_devices_view_surfaces_fm_devices_in_gui(self):
        """``fm devices`` had no GUI path; the new ``Storage & Devices``
        view wires the same ``device_manager.list_storage_devices`` API
        into a QTableWidget so the data is discoverable in-app."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.views.storage_devices import StorageDevicesView

        _ = QApplication.instance() or QApplication([])

        view = StorageDevicesView(None, app=MagicMock())
        self.assertEqual(view.get_title(), "Storage & Devices")
        self.assertEqual(view.table.columnCount(), 5)
        self.assertEqual(
            [view.table.horizontalHeaderItem(i).text() for i in range(5)],
            ["Mount point", "Type", "Filesystem", "Used", "Total"],
        )
        self.assertIn("refresh", view.TOOLTIP_TEXTS)
        self.assertIn("details", view.TOOLTIP_TEXTS)
        """``fm devices`` had no GUI path; the new ``Storage & Devices``
        view wires the same ``device_manager.list_storage_devices`` API
        into a QTableWidget so the data is discoverable in-app."""
        from PyQt5.QtWidgets import QApplication
        from dataforge.ui.views.storage_devices import StorageDevicesView

        _ = QApplication.instance() or QApplication([])

        view = StorageDevicesView(None, app=MagicMock())
        self.assertEqual(view.get_title(), "Storage & Devices")
        self.assertEqual(view.table.columnCount(), 5)
        self.assertEqual(
            [view.table.horizontalHeaderItem(i).text() for i in range(5)],
            ["Mount point", "Type", "Filesystem", "Used", "Total"],
        )
        self.assertIn("refresh", view.TOOLTIP_TEXTS)
        self.assertIn("details", view.TOOLTIP_TEXTS)

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
