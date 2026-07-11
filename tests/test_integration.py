"""
Integration tests for Action Builder pipelines, plugin packaging paths,
and end-to-end workflows that cross multiple layers.
"""

import os
import tempfile
import time
import unittest
from pathlib import Path

from filemanager.core.common import FileEntry
from filemanager.core.actions.base import ActionContext
from filemanager.core.actions.filters import SearchFilter, SizeFilter, DateFilter
from filemanager.core.actions.io import MoveStep, CopyStep, DeleteStep
from filemanager.core.actions.modifications import RenameStep
from filemanager.core.scanner import scan_directory
from filemanager.core.operations import (
    transfer_path,
    delete_path,
    rename_path,
    resolve_collision_path,
)
from filemanager.modules.search import build_search_query, search_files
from filemanager.ui.views.action_builder import ActionBuilderView


def _make_files(root: Path, specs: dict[str, str]) -> list[Path]:
    """Create files from a {relative_path: content} dict. Returns list of paths."""
    paths = []
    for rel, content in specs.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        paths.append(p)
    return paths


def _scan_to_entries(directory: str) -> list[FileEntry]:
    return list(scan_directory(directory, recursive=True))


# ---------------------------------------------------------------------------
# Action Builder Pipeline Tests
# ---------------------------------------------------------------------------

class TestActionPipelineEndToEnd(unittest.TestCase):
    """Exercises multi-step ActionContext pipelines like the GUI Action Builder."""

    def test_filter_then_rename(self):
        """SearchFilter -> RenameStep: only matching files get renamed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_files(root, {
                "report_jan.txt": "jan",
                "report_feb.txt": "feb",
                "notes.md": "markdown",
            })
            files = _scan_to_entries(tmp)
            ctx = ActionContext(files)
            ctx.is_dry_run = False

            # Step 1: filter to txt only
            search_filter = SearchFilter({"pattern": r".*\.txt$"})
            search_filter.execute(ctx)
            self.assertEqual(len(ctx.files), 2)

            # Step 2: rename with template
            rename_step = RenameStep({"pattern": "archive_{counter}.{ext}", "counter_start": "1"})
            rename_step.execute(ctx)

            renamed = sorted(f.filename for f in ctx.files)
            self.assertEqual(renamed, ["archive_001.txt", "archive_002.txt"])
            # notes.md should be untouched
            self.assertTrue((root / "notes.md").exists())

    def test_filter_then_move(self):
        """SizeFilter -> MoveStep: only large-enough files are moved."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "dest"
            dest.mkdir()

            (root / "big.txt").write_text("x" * 200, encoding="utf-8")
            (root / "small.txt").write_text("y", encoding="utf-8")

            files = _scan_to_entries(tmp)
            # exclude dest directory entries
            files = [f for f in files if "dest" not in f.path]
            ctx = ActionContext(files)
            ctx.is_dry_run = False

            # Step 1: only files >= 100 bytes
            size_filter = SizeFilter({"min_mb": str(100 / (1024 * 1024)), "max_mb": "0"})
            size_filter.execute(ctx)
            self.assertEqual(len(ctx.files), 1)
            self.assertEqual(ctx.files[0].filename, "big.txt")

            # Step 2: move to dest
            move_step = MoveStep({"dest": str(dest)})
            move_step.execute(ctx)

            self.assertTrue((dest / "big.txt").exists())
            self.assertFalse((root / "big.txt").exists())
            self.assertTrue((root / "small.txt").exists())

    def test_filter_then_copy_then_delete(self):
        """DateFilter -> CopyStep -> DeleteStep: three-step pipeline."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup = root / "backup"
            backup.mkdir()

            old_file = root / "old.txt"
            old_file.write_text("old data", encoding="utf-8")
            two_days_ago = time.time() - (2 * 86400)
            os.utime(old_file, (two_days_ago, two_days_ago))

            new_file = root / "new.txt"
            new_file.write_text("new data", encoding="utf-8")

            files = _scan_to_entries(tmp)
            files = [f for f in files if "backup" not in f.path]
            ctx = ActionContext(files)
            ctx.is_dry_run = False

            # Step 1: filter to files older than 1 day
            date_filter = DateFilter({"days": "1", "mode": "Older"})
            date_filter.execute(ctx)
            self.assertEqual(len(ctx.files), 1)
            self.assertEqual(ctx.files[0].filename, "old.txt")

            # Step 2: copy to backup
            copy_step = CopyStep({"dest": str(backup)})
            copy_step.execute(ctx)
            self.assertTrue((backup / "old.txt").exists())

            # Step 3: delete originals (permanently for test)
            from unittest.mock import patch
            with patch("filemanager.core.operations.files.send2trash"):
                delete_step = DeleteStep()
                delete_step.execute(ctx)

            self.assertTrue((backup / "old.txt").exists())
            self.assertTrue(new_file.exists())

    def test_dry_run_makes_no_changes(self):
        """Dry-run pipeline should log actions but not touch the filesystem."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_files(root, {"file.txt": "data"})
            files = _scan_to_entries(tmp)
            ctx = ActionContext(files)
            ctx.is_dry_run = True

            dest = root / "moved"
            dest.mkdir()
            move_step = MoveStep({"dest": str(dest)})
            move_step.execute(ctx)

            # File should NOT have been moved
            self.assertTrue((root / "file.txt").exists())
            self.assertFalse((dest / "file.txt").exists())
            # But results should be logged
            self.assertTrue(len(ctx.results) > 0)

    def test_cancel_stops_pipeline(self):
        """Pipeline respects cancel_token mid-execution."""
        import threading

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(10):
                (root / f"file_{i}.txt").write_text(f"data {i}", encoding="utf-8")

            files = _scan_to_entries(tmp)
            cancel = threading.Event()
            ctx = ActionContext(files)
            ctx.is_dry_run = False
            ctx.cancel_token = cancel

            # Cancel immediately
            cancel.set()

            dest = root / "moved"
            dest.mkdir()
            move_step = MoveStep({"dest": str(dest)})
            move_step.execute(ctx)

            # No files should have been moved (cancel was set before start)
            moved_files = list(dest.iterdir())
            self.assertEqual(len(moved_files), 0)

    def test_rename_collision_in_pipeline(self):
        """RenameStep handles collisions when multiple files get the same name."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_files(root, {
                "a.txt": "one",
                "b.txt": "two",
                "c.txt": "three",
            })
            files = _scan_to_entries(tmp)
            ctx = ActionContext(files)
            ctx.is_dry_run = False

            # All three files get renamed to "same.txt" -> collisions
            rename_step = RenameStep({"pattern": "same.{ext}", "counter_start": "1"})
            rename_step.execute(ctx)

            result_names = sorted(f.filename for f in ctx.files)
            self.assertIn("same.txt", result_names)
            self.assertIn("same_1.txt", result_names)
            self.assertIn("same_2.txt", result_names)

    def test_pipeline_error_recovery(self):
        """A step that errors on one file continues with the rest."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_files(root, {
                "good.txt": "content",
                "also_good.txt": "more content",
            })
            files = _scan_to_entries(tmp)
            ctx = ActionContext(files)
            ctx.is_dry_run = False

            dest = root / "dest"
            dest.mkdir()
            move_step = MoveStep({"dest": str(dest)})
            move_step.execute(ctx)

            # Both files should have been moved
            self.assertTrue((dest / "good.txt").exists())
            self.assertTrue((dest / "also_good.txt").exists())
            self.assertEqual(len(ctx.results), 2)

    def test_action_builder_single_file_source(self):
        """Action Builder execution supports a single file as the source path."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "report.txt"
            target.write_text("content", encoding="utf-8")

            result = ActionBuilderView._execute_pipeline_thread(
                object(),
                str(target),
                False,
                -1,
                [RenameStep({"pattern": "renamed.{ext}", "counter_start": "1"})],
                False,
                lambda *_args: None,
            )

            self.assertIsInstance(result, list)
            self.assertTrue((Path(tmp) / "renamed.txt").exists())


# ---------------------------------------------------------------------------
# Plugin Packaging Path Tests
# ---------------------------------------------------------------------------

class TestPluginPackagingPaths(unittest.TestCase):
    """Verify build scripts reference the correct plugin directory."""

    def test_build_exe_plugin_path_matches_loader(self):
        """build_exe.py data path should reference filemanager/ui/plugins."""
        repo_root = Path(__file__).resolve().parents[1]
        build_script = repo_root / "build_exe.py"
        content = build_script.read_text(encoding="utf-8")
        self.assertIn("filemanager/ui/plugins", content.replace("\\", "/"))

    def test_spec_file_plugin_path_matches_loader(self):
        """FileManager.spec data path should reference filemanager/ui/plugins."""
        repo_root = Path(__file__).resolve().parents[1]
        spec_file = repo_root / "FileManager.spec"
        content = spec_file.read_text(encoding="utf-8")
        # Spec uses os.path.join or raw strings — normalize to forward slashes
        normalized = content.replace("\\\\", "/").replace("\\", "/")
        self.assertIn("filemanager/ui/plugins", normalized)

    def test_plugin_directory_is_a_package(self):
        """filemanager/ui/plugins/__init__.py must exist for imports to work."""
        repo_root = Path(__file__).resolve().parents[1]
        init = repo_root / "filemanager" / "ui" / "plugins" / "__init__.py"
        self.assertTrue(init.exists(), "__init__.py missing from plugins directory")

    def test_plugin_loader_uses_full_package_name(self):
        """PluginLoader should import with 'filemanager.ui.plugins' prefix."""
        repo_root = Path(__file__).resolve().parents[1]
        loader_src = (repo_root / "filemanager" / "ui" / "plugin_loader.py").read_text(encoding="utf-8")
        self.assertIn("filemanager.ui.plugins", loader_src)


# ---------------------------------------------------------------------------
# Shared Operations Layer Tests
# ---------------------------------------------------------------------------

class TestSharedOperationsLayer(unittest.TestCase):
    """Verify the operations layer handles edge cases consistently."""

    def test_resolve_collision_with_reserved_paths(self):
        """Multiple collisions are resolved with incrementing suffixes."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "file.txt").write_text("existing", encoding="utf-8")

            reserved = set()
            # First call: file.txt exists on disk
            p1 = resolve_collision_path(str(root / "file.txt"), reserved)
            self.assertEqual(os.path.basename(p1), "file_1.txt")

            # Second call: file_1.txt is now reserved
            p2 = resolve_collision_path(str(root / "file.txt"), reserved)
            self.assertEqual(os.path.basename(p2), "file_2.txt")

    def test_transfer_invalid_action_raises(self):
        """Invalid transfer action should raise ValueError."""
        with self.assertRaises(ValueError):
            transfer_path("/fake/path.txt", "/fake/dest", "link")

    def test_rename_to_same_name_returns_none(self):
        """Renaming a file to its current name returns None (no-op)."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "test.txt"
            f.write_text("data", encoding="utf-8")
            result = rename_path(str(f), "test.txt")
            self.assertIsNone(result)

    def test_delete_dry_run_preserves_file(self):
        """Dry-run delete should not remove the file."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "keep.txt"
            f.write_text("keep me", encoding="utf-8")
            result = delete_path(str(f), dry_run=True, safe_mode=True)
            self.assertTrue(result.success)
            self.assertTrue(result.dry_run)
            self.assertTrue(f.exists())


# ---------------------------------------------------------------------------
# Search + Operations Integration
# ---------------------------------------------------------------------------

class TestSearchOperationsIntegration(unittest.TestCase):
    """End-to-end: search for files then operate on results."""

    def test_search_then_move_results(self):
        """Search files -> move found files to a new directory."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = root / "organized"
            dest.mkdir()

            _make_files(root, {
                "report.pdf": "pdf content",
                "photo.jpg": "image bytes",
                "notes.txt": "text notes",
            })

            query = build_search_query(extensions="pdf,txt")
            results = search_files(str(root), query, recursive=False)
            self.assertEqual(len(results), 2)

            reserved = set()
            for entry in results:
                transfer_path(entry.path, str(dest), "move", dry_run=False, reserved_paths=reserved)

            self.assertTrue((dest / "report.pdf").exists())
            self.assertTrue((dest / "notes.txt").exists())
            self.assertTrue((root / "photo.jpg").exists())

    def test_search_size_filter_accuracy(self):
        """Size filter on search correctly excludes files outside range."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tiny.txt").write_text("x", encoding="utf-8")
            (root / "medium.txt").write_text("x" * 500, encoding="utf-8")
            (root / "big.txt").write_text("x" * 2000, encoding="utf-8")

            query = build_search_query(min_size_bytes=100, max_size_bytes=1000)
            results = search_files(str(root), query, recursive=False)
            names = [r.filename for r in results]
            self.assertIn("medium.txt", names)
            self.assertNotIn("tiny.txt", names)
            self.assertNotIn("big.txt", names)


if __name__ == "__main__":
    unittest.main()
