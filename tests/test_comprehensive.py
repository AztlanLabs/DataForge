"""
Comprehensive tests covering core modules, utilities, scanner, hasher,
cache, config, media_ops, search, duplicates, cleaner, integrity,
reporting, usage, renamer, organizer, actions, and operations.
"""

import csv
import json
import math
import os
import sqlite3
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock, patch
from PIL import Image
try:
    from pypdf import PdfWriter
except ImportError:
    PdfWriter = None

from filemanager.core.common import FileEntry
from filemanager.core.config import ConfigManager
from filemanager.core.hasher import get_file_hash, get_hashes
from filemanager.core.media_ops import merge_pdfs, split_pdf, convert_image
from filemanager.core.scanner import scan_directory
from filemanager.core.utils import format_size, parse_extensions, check_disk_space, safe_zip_write
from filemanager.core.operations.files import (
    OperationResult,
    resolve_collision_path,
    transfer_path,
    delete_path,
    rename_path,
    rename_with_regex,
    render_template_name,
    apply_result_to_entry,
    format_operation_message,
)
from filemanager.core.actions.base import ActionContext, ActionStep
from filemanager.core.actions.filters import SearchFilter, SizeFilter, DateFilter, ImagePropFilter
from filemanager.core.actions.io import MoveStep, CopyStep, DeleteStep, ZipStep
from filemanager.core.actions.modifications import RenameStep, MetaCleanStep
from filemanager.core.services import FileActionService
from filemanager.core.actions.media import ConvertImageStep
from filemanager.modules.search import SearchQuery, search_files, build_search_query, export_result_rows, export_search_results, order_search_results, serialize_file_entry
from filemanager.modules.duplicates import build_duplicate_export_rows, build_duplicate_records, choose_duplicate_keeper, find_duplicates, order_duplicate_records, select_duplicate_records, serialize_duplicate_group_summary, serialize_duplicate_record
from filemanager.modules.cleaner import remove_empty_folders, MetadataCleaner
from filemanager.modules.integrity import IntegrityMonitor
from filemanager.modules.reporting import ReportGenerator
from filemanager.modules.usage import analyze_size, generate_usage_report
from filemanager.modules.renamer import bulk_rename
from filemanager.modules.organizer import Organizer
from filemanager.ui.views.duplicates import DuplicatesView


def _make_entry(path="test.txt", size=100, ext=".txt", mtime=None):
    """Helper to build a FileEntry."""
    return FileEntry(
        path=path,
        filename=os.path.basename(path),
        extension=ext,
        size=size,
        created_at=time.time(),
        modified_at=mtime or time.time(),
        is_dir=False,
    )


def _make_files(root: Path, specs: dict) -> list[Path]:
    paths = []
    for rel, content in specs.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        paths.append(p)
    return paths


# ===========================================================================
# FileEntry / common.py
# ===========================================================================

class TestFileEntry(unittest.TestCase):
    def test_created_dt_property(self):
        from datetime import datetime
        now = time.time()
        e = _make_entry(mtime=now)
        e.created_at = now
        dt = e.created_dt
        self.assertIsInstance(dt, datetime)

    def test_modified_dt_property(self):
        from datetime import datetime
        now = time.time()
        e = _make_entry(mtime=now)
        self.assertIsInstance(e.modified_dt, datetime)

    def test_optional_hashes_default_none(self):
        e = _make_entry()
        self.assertIsNone(e.md5)
        self.assertIsNone(e.sha1)
        self.assertIsNone(e.sha256)


# ===========================================================================
# utils.py
# ===========================================================================

class TestFormatSize(unittest.TestCase):
    def test_none_returns_zero(self):
        self.assertEqual(format_size(None), "0 B")

    def test_zero_auto(self):
        with patch("filemanager.core.utils.config") as mock_cfg:
            mock_cfg.get.return_value = "Auto"
            self.assertEqual(format_size(0), "0 B")

    def test_bytes_mode(self):
        with patch("filemanager.core.utils.config") as mock_cfg:
            mock_cfg.get.return_value = "Bytes"
            result = format_size(1024)
            self.assertIn("1024", result)

    def test_kb_mode(self):
        with patch("filemanager.core.utils.config") as mock_cfg:
            mock_cfg.get.return_value = "KB"
            result = format_size(2048)
            self.assertIn("2.00", result)

    def test_mb_mode(self):
        with patch("filemanager.core.utils.config") as mock_cfg:
            mock_cfg.get.return_value = "MB"
            result = format_size(1048576)
            self.assertIn("1.00", result)

    def test_gb_mode(self):
        with patch("filemanager.core.utils.config") as mock_cfg:
            mock_cfg.get.return_value = "GB"
            result = format_size(1073741824)
            self.assertIn("1.00", result)

    def test_auto_large(self):
        with patch("filemanager.core.utils.config") as mock_cfg:
            mock_cfg.get.return_value = "Auto"
            result = format_size(5 * 1024 * 1024)
            self.assertIn("MB", result)


class TestParseExtensions(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(parse_extensions(""), [])

    def test_with_dots(self):
        result = parse_extensions(".jpg, .png")
        self.assertEqual(result, [".jpg", ".png"])

    def test_without_dots(self):
        result = parse_extensions("jpg,png")
        self.assertEqual(result, [".jpg", ".png"])

    def test_mixed(self):
        result = parse_extensions(".JPG, png, .Pdf")
        self.assertEqual(result, [".jpg", ".png", ".pdf"])

    def test_none_input(self):
        self.assertEqual(parse_extensions(None), [])


class TestCheckDiskSpace(unittest.TestCase):
    def test_sufficient_space(self):
        ok, msg = check_disk_space(tempfile.gettempdir(), 1)
        self.assertTrue(ok)

    def test_nonexistent_path_uses_parent(self):
        ok, msg = check_disk_space(os.path.join(tempfile.gettempdir(), "nonexistent_dir_xyz"), 1)
        self.assertTrue(ok)


class TestSafeZipWrite(unittest.TestCase):
    def test_no_collision(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            zpath = os.path.join(tmp, "test.zip")
            fpath = os.path.join(tmp, "a.txt")
            Path(fpath).write_text("data")
            existing = set()
            with zipfile.ZipFile(zpath, "w") as zf:
                result = safe_zip_write(zf, fpath, "a.txt", existing)
            self.assertEqual(result, "a.txt")
            self.assertIn("a.txt", existing)

    def test_collision_increments(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            zpath = os.path.join(tmp, "test.zip")
            fpath = os.path.join(tmp, "a.txt")
            Path(fpath).write_text("data")
            existing = {"a.txt"}
            with zipfile.ZipFile(zpath, "w") as zf:
                result = safe_zip_write(zf, fpath, "a.txt", existing)
            self.assertEqual(result, "a_1.txt")


# ===========================================================================
# hasher.py
# ===========================================================================

class TestHasher(unittest.TestCase):
    def test_md5_hash(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"hello world")
            path = f.name
        try:
            h = get_file_hash(path, "md5")
            self.assertEqual(len(h), 32)
        finally:
            os.unlink(path)

    def test_sha256_hash(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"test data")
            path = f.name
        try:
            h = get_file_hash(path, "sha256")
            self.assertEqual(len(h), 64)
        finally:
            os.unlink(path)

    def test_unsupported_algo_raises(self):
        with self.assertRaises(ValueError):
            get_file_hash("fake.txt", "crc32")

    def test_nonexistent_file_returns_empty(self):
        h = get_file_hash("nonexistent_file_xyz.txt", "md5")
        self.assertEqual(h, "")

    def test_cancel_token_aborts(self):
        import threading
        cancel = threading.Event()
        cancel.set()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"x" * 1000)
            path = f.name
        try:
            h = get_file_hash(path, "md5", cancel_token=cancel)
            self.assertEqual(h, "")
        finally:
            os.unlink(path)

    def test_get_hashes_multiple(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"multi hash test")
            path = f.name
        try:
            result = get_hashes(path, ["md5", "sha1"])
            self.assertEqual(len(result), 2)
            self.assertEqual(len(result["md5"]), 32)
            self.assertEqual(len(result["sha1"]), 40)
        finally:
            os.unlink(path)

    def test_get_hashes_nonexistent(self):
        result = get_hashes("nonexistent.txt", ["md5"])
        self.assertEqual(result["md5"], "")


# ===========================================================================
# scanner.py
# ===========================================================================

class TestScanner(unittest.TestCase):
    def test_scan_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "hello", "b.dat": "code"})
            with patch("filemanager.core.scanner.config") as mock_cfg:
                mock_cfg.get.side_effect = lambda key, default=None: {
                    "excluded_folders": [],
                    "excluded_extensions": [],
                }.get(key, default)
                entries = list(scan_directory(tmp, recursive=True))
            names = {e.filename for e in entries}
            self.assertIn("a.txt", names)
            self.assertIn("b.dat", names)

    def test_scan_non_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_files(root, {"top.txt": "t", "sub/deep.txt": "d"})
            entries = list(scan_directory(tmp, recursive=False))
            names = {e.filename for e in entries}
            self.assertIn("top.txt", names)
            self.assertNotIn("deep.txt", names)

    def test_scan_max_depth_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_files(root, {"a.txt": "a", "sub/b.txt": "b"})
            entries = list(scan_directory(tmp, recursive=True, max_depth=0))
            names = {e.filename for e in entries}
            self.assertIn("a.txt", names)
            self.assertNotIn("b.txt", names)

    def test_scan_max_depth_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_files(root, {"a.txt": "a", "sub/b.txt": "b", "sub/deep/c.txt": "c"})
            entries = list(scan_directory(tmp, recursive=True, max_depth=1))
            names = {e.filename for e in entries}
            self.assertIn("a.txt", names)
            self.assertIn("b.txt", names)
            self.assertNotIn("c.txt", names)

    def test_cancel_token_stops_scan(self):
        import threading
        cancel = threading.Event()
        cancel.set()
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "hello"})
            entries = list(scan_directory(tmp, recursive=True, cancel_token=cancel))
            self.assertEqual(len(entries), 0)

    def test_fileentry_fields_populated(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"test.txt": "content"})
            entries = list(scan_directory(tmp, recursive=True))
            e = entries[0]
            self.assertEqual(e.filename, "test.txt")
            self.assertEqual(e.extension, ".txt")
            self.assertGreater(e.size, 0)
            self.assertFalse(e.is_dir)

    def test_scan_single_file_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "single.txt"
            target.write_text("content", encoding="utf-8")

            entries = list(scan_directory(str(target), recursive=True))

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].path, str(target))

    def test_inaccessible_dir_skipped(self):
        # Should not raise
        entries = list(scan_directory("/nonexistent_path_xyz_123", recursive=True))
        self.assertEqual(len(entries), 0)


# ===========================================================================
# cache.py
# ===========================================================================

class TestCacheManager(unittest.TestCase):
    def test_set_and_get_hash(self):
        from filemanager.core.cache import CacheManager
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test_cache.db")
            cm = CacheManager(db_path)
            cm.set_hash("/test/file.txt", 100, 12345.0, "abc123", "md5")
            result = cm.get_hash("/test/file.txt", 100, 12345.0, "md5")
            self.assertEqual(result, "abc123")
            cm.close()

    def test_get_hash_miss(self):
        from filemanager.core.cache import CacheManager
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test_cache.db")
            cm = CacheManager(db_path)
            result = cm.get_hash("/no/file.txt", 0, 0.0, "md5")
            self.assertIsNone(result)
            cm.close()

    def test_clear(self):
        from filemanager.core.cache import CacheManager
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test_cache.db")
            cm = CacheManager(db_path)
            cm.set_hash("/a.txt", 10, 1.0, "hash1", "md5")
            cm.clear()
            result = cm.get_hash("/a.txt", 10, 1.0, "md5")
            self.assertIsNone(result)
            cm.close()

    def test_update_existing(self):
        from filemanager.core.cache import CacheManager
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test_cache.db")
            cm = CacheManager(db_path)
            cm.set_hash("/a.txt", 10, 1.0, "old", "md5")
            cm.set_hash("/a.txt", 10, 1.0, "new", "md5")
            result = cm.get_hash("/a.txt", 10, 1.0, "md5")
            self.assertEqual(result, "new")
            cm.close()


# ===========================================================================
# config.py
# ===========================================================================

class TestConfig(unittest.TestCase):
    def test_config_get_default(self):
        from filemanager.core.config import config
        self.assertIn(config.get("theme"), ["cosmo", "darkly"])

    def test_config_get_nonexistent_key(self):
        from filemanager.core.config import config
        self.assertIsNone(config.get("nonexistent_key_xyz"))

    def test_config_get_with_default(self):
        from filemanager.core.config import config
        result = config.get("nonexistent_key_xyz", "fallback")
        self.assertEqual(result, "fallback")


# ===========================================================================
# SearchQuery / search.py
# ===========================================================================

class TestSearchQuery(unittest.TestCase):
    def test_name_pattern_match(self):
        q = SearchQuery().set_name_pattern(r".*\.txt$")
        e = _make_entry("test.txt")
        self.assertTrue(q.matches(e))

    def test_name_pattern_no_match(self):
        q = SearchQuery().set_name_pattern(r".*\.py$")
        e = _make_entry("test.txt")
        self.assertFalse(q.matches(e))

    def test_extension_filter(self):
        q = SearchQuery().set_extensions(".txt,.py")
        e_txt = _make_entry("a.txt", ext=".txt")
        e_py = _make_entry("b.py", ext=".py")
        e_jpg = _make_entry("c.jpg", ext=".jpg")
        self.assertTrue(q.matches(e_txt))
        self.assertTrue(q.matches(e_py))
        self.assertFalse(q.matches(e_jpg))

    def test_size_range(self):
        q = SearchQuery().set_size_range(50, 200)
        e_small = _make_entry(size=10)
        e_good = _make_entry(size=100)
        e_big = _make_entry(size=500)
        self.assertFalse(q.matches(e_small))
        self.assertTrue(q.matches(e_good))
        self.assertFalse(q.matches(e_big))

    def test_min_size_only(self):
        q = SearchQuery().set_size_range(min_bytes=100)
        self.assertFalse(q.matches(_make_entry(size=50)))
        self.assertTrue(q.matches(_make_entry(size=150)))

    def test_date_filter_after(self):
        from datetime import datetime, timedelta
        now = datetime.now()
        recent = (now - timedelta(hours=1)).timestamp()
        old = (now - timedelta(days=30)).timestamp()

        q = SearchQuery()
        q.set_modified_date(after=now - timedelta(days=1))
        self.assertTrue(q.matches(_make_entry(mtime=recent)))
        self.assertFalse(q.matches(_make_entry(mtime=old)))

    def test_content_search(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world foo bar")
            path = f.name
        try:
            q = SearchQuery()
            q.set_content("foo bar")
            e = _make_entry(path=path, size=20)
            self.assertTrue(q.matches(e))
        finally:
            os.unlink(path)

    def test_content_search_no_match(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            path = f.name
        try:
            q = SearchQuery()
            q.set_content("xyz_nonexistent")
            e = _make_entry(path=path, size=20)
            self.assertFalse(q.matches(e))
        finally:
            os.unlink(path)

    def test_empty_query_matches_all(self):
        q = SearchQuery()
        self.assertTrue(q.matches(_make_entry()))


class TestBuildSearchQuery(unittest.TestCase):
    def test_with_glob_pattern(self):
        q = build_search_query(name_pattern="*.txt")
        e = _make_entry("report.txt")
        self.assertTrue(q.matches(e))

    def test_with_regex_flag(self):
        q = build_search_query(name_pattern=r"report_\d+\.txt", use_regex=True)
        self.assertTrue(q.matches(_make_entry("report_123.txt")))
        self.assertFalse(q.matches(_make_entry("report_abc.txt")))

    def test_size_filters(self):
        q = build_search_query(min_size_bytes=100, max_size_bytes=500)
        self.assertTrue(q.matches(_make_entry(size=200)))
        self.assertFalse(q.matches(_make_entry(size=50)))

    def test_date_filters(self):
        q = build_search_query(newer_than_days=1)
        recent = _make_entry(mtime=time.time())
        self.assertTrue(q.matches(recent))


class TestSearchFiles(unittest.TestCase):
    def test_basic_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "aaa", "b.py": "bbb"})
            q = SearchQuery().set_extensions(".txt")
            results = search_files(tmp, q)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].extension, ".txt")

    def test_single_file_path_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "match.txt"
            target.write_text("hello world", encoding="utf-8")

            q = SearchQuery().set_extensions(".txt")
            results = search_files(str(target), q)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].path, str(target))

    def test_single_file_path_search_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skip.txt"
            target.write_text("hello world", encoding="utf-8")

            q = SearchQuery().set_extensions(".jpg")
            results = search_files(str(target), q)

            self.assertEqual(results, [])

    def test_search_with_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "a", "sub/b.txt": "b"})
            q = SearchQuery().set_extensions(".txt")
            results = search_files(tmp, q, max_depth=0)
            self.assertEqual(len(results), 1)

    def test_search_cancel(self):
        import threading
        cancel = threading.Event()
        cancel.set()
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "a"})
            q = SearchQuery()
            # Cancel set before scan means scanner yields nothing,
            # so search_files returns empty list without raising.
            results = search_files(tmp, q, cancel_token=cancel)
            self.assertEqual(len(results), 0)


class TestOrderSearchResults(unittest.TestCase):
    def test_sort_by_extension(self):
        entries = [
            _make_entry("b.log", ext=".log"),
            _make_entry("a.txt", ext=".txt"),
            _make_entry("c.csv", ext=".csv"),
        ]

        ordered = order_search_results(entries, sort_key="ext")

        self.assertEqual([entry.extension for entry in ordered], [".csv", ".log", ".txt"])

    def test_sort_by_size(self):
        entries = [
            _make_entry("b.txt", size=200),
            _make_entry("a.txt", size=50),
            _make_entry("c.txt", size=100),
        ]

        ordered = order_search_results(entries, sort_key="size")

        self.assertEqual([entry.size for entry in ordered], [50, 100, 200])

    def test_reverse_without_sort(self):
        entries = [
            _make_entry("a.txt"),
            _make_entry("b.txt"),
            _make_entry("c.txt"),
        ]

        ordered = order_search_results(entries, reverse=True)

        self.assertEqual([entry.filename for entry in ordered], ["c.txt", "b.txt", "a.txt"])

    def test_limit_after_sort(self):
        entries = [
            _make_entry("c.txt", size=300),
            _make_entry("a.txt", size=100),
            _make_entry("b.txt", size=200),
        ]

        ordered = order_search_results(entries, sort_key="name", limit=2)

        self.assertEqual([entry.filename for entry in ordered], ["a.txt", "b.txt"])


# ===========================================================================
# operations/files.py
# ===========================================================================

class TestOperations(unittest.TestCase):
    @staticmethod
    def _messy_path(path: str) -> str:
        if os.name == "nt":
            return path.replace("\\", "//")
        return path.replace("/", "//")

    def test_resolve_collision_no_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = resolve_collision_path(os.path.join(tmp, "new.txt"))
            self.assertEqual(os.path.basename(p), "new.txt")

    def test_resolve_collision_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(os.path.join(tmp, "a.txt")).write_text("x")
            p = resolve_collision_path(os.path.join(tmp, "a.txt"))
            self.assertEqual(os.path.basename(p), "a_1.txt")

    def test_resolve_collision_reserved_and_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(os.path.join(tmp, "a.txt")).write_text("x")
            reserved = set()
            p1 = resolve_collision_path(os.path.join(tmp, "a.txt"), reserved)
            p2 = resolve_collision_path(os.path.join(tmp, "a.txt"), reserved)
            self.assertNotEqual(p1, p2)

    def test_transfer_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src.txt")
            Path(src).write_text("data")
            dest_dir = os.path.join(tmp, "dest")
            os.makedirs(dest_dir)
            result = transfer_path(src, dest_dir, "move", dry_run=False)
            self.assertTrue(result.success)
            self.assertFalse(os.path.exists(src))
            self.assertTrue(os.path.exists(os.path.join(dest_dir, "src.txt")))

    def test_transfer_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src.txt")
            Path(src).write_text("data")
            dest_dir = os.path.join(tmp, "dest")
            os.makedirs(dest_dir)
            result = transfer_path(src, dest_dir, "copy", dry_run=False)
            self.assertTrue(result.success)
            self.assertTrue(os.path.exists(src))
            self.assertTrue(os.path.exists(os.path.join(dest_dir, "src.txt")))

    def test_transfer_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src.txt")
            Path(src).write_text("data")
            dest_dir = os.path.join(tmp, "dest")
            os.makedirs(dest_dir)
            result = transfer_path(src, dest_dir, "move", dry_run=True)
            self.assertTrue(result.success)
            self.assertTrue(result.dry_run)
            self.assertTrue(os.path.exists(src))

    def test_transfer_no_dest_raises(self):
        with self.assertRaises(ValueError):
            transfer_path("/fake", "", "move")

    def test_delete_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "a.txt")
            Path(src).write_text("data")
            result = delete_path(src, dry_run=True)
            self.assertTrue(result.success)
            self.assertTrue(os.path.exists(src))

    def test_delete_path_normalizes_slash_heavy_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "delete_me.txt")
            Path(src).write_text("data")

            result = delete_path(self._messy_path(src), dry_run=False, safe_mode=False)

            self.assertTrue(result.success)
            self.assertFalse(os.path.exists(src))

    def test_rename_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "old.txt")
            Path(src).write_text("data")
            result = rename_path(src, "new.txt", dry_run=False)
            self.assertTrue(result.success)
            self.assertTrue(os.path.exists(os.path.join(tmp, "new.txt")))

    def test_rename_path_normalizes_slash_heavy_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "before.txt")
            Path(src).write_text("data")

            result = rename_path(self._messy_path(src), "after.txt", dry_run=False)

            self.assertTrue(result.success)
            self.assertTrue(os.path.exists(os.path.join(tmp, "after.txt")))

    def test_rename_same_name_returns_none(self):
        result = rename_path("/some/path/file.txt", "file.txt")
        self.assertIsNone(result)

    def test_rename_empty_name_raises(self):
        with self.assertRaises(ValueError):
            rename_path("/some/path/file.txt", "")

    def test_rename_with_regex(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "report_2024.txt")
            Path(src).write_text("data")
            result = rename_with_regex(src, r"_(\d+)", "_archived", dry_run=False)
            self.assertTrue(result.success)
            self.assertTrue(os.path.exists(os.path.join(tmp, "report_archived.txt")))

    def test_transfer_path_normalizes_slash_heavy_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src.txt")
            Path(src).write_text("data")
            dest_dir = os.path.join(tmp, "dest")
            os.makedirs(dest_dir)

            result = transfer_path(self._messy_path(src), self._messy_path(dest_dir), "copy", dry_run=False)

            self.assertTrue(result.success)
            self.assertTrue(os.path.exists(src))
            self.assertTrue(os.path.exists(os.path.join(dest_dir, "src.txt")))

    def test_rename_with_regex_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "clean.txt")
            Path(src).write_text("data")
            result = rename_with_regex(src, r"xyz", "abc", dry_run=False)
            # No match means name stays same -> returns None
            self.assertIsNone(result)

    def test_render_template_name(self):
        e = _make_entry("test.txt", ext=".txt")
        name = render_template_name("{name}_{counter}.{ext}", e, 5)
        self.assertEqual(name, "test_005.txt")

    def test_render_template_name_auto_ext(self):
        e = _make_entry("test.txt", ext=".txt")
        name = render_template_name("{name}_v2", e, 1)
        self.assertTrue(name.endswith(".txt"))

    def test_apply_result_to_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "old.txt")
            dest = os.path.join(tmp, "new.txt")
            Path(dest).write_text("data")
            e = _make_entry(src)
            result = OperationResult("rename", src, dest, True, "ok")
            updated = apply_result_to_entry(e, result)
            self.assertEqual(updated.filename, "new.txt")

    def test_apply_result_none_noop(self):
        e = _make_entry()
        same = apply_result_to_entry(e, None)
        self.assertIs(same, e)

    def test_format_operation_message(self):
        r = OperationResult("move", "/a", "/b", True, "Moved: /a -> /b")
        self.assertEqual(format_operation_message(r), "Moved: /a -> /b")


# ===========================================================================
# ActionContext / base.py
# ===========================================================================

class TestActionContext(unittest.TestCase):
    def test_log_appends_to_results(self):
        ctx = ActionContext([])
        ctx.log("/a.txt", "Move", "OK")
        self.assertEqual(len(ctx.results), 1)

    def test_should_cancel_false(self):
        ctx = ActionContext([])
        self.assertFalse(ctx.should_cancel())

    def test_should_cancel_true(self):
        import threading
        cancel = threading.Event()
        cancel.set()
        ctx = ActionContext([])
        ctx.cancel_token = cancel
        self.assertTrue(ctx.should_cancel())

    def test_progress_callback(self):
        calls = []
        ctx = ActionContext([], update_progress=lambda c, t, m: calls.append((c, t, m)))
        ctx.progress(5, 10, "test")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], (5, 10, "test"))


# ===========================================================================
# Action Filters
# ===========================================================================

class TestSearchFilterStep(unittest.TestCase):
    def test_filters_by_pattern(self):
        files = [_make_entry("a.txt"), _make_entry("b.py"), _make_entry("c.txt")]
        ctx = ActionContext(files)
        step = SearchFilter({"pattern": r".*\.txt$"})
        step.execute(ctx)
        self.assertEqual(len(ctx.files), 2)

    def test_empty_pattern_keeps_all(self):
        files = [_make_entry("a.txt"), _make_entry("b.py")]
        ctx = ActionContext(files)
        step = SearchFilter({"pattern": ""})
        step.execute(ctx)
        self.assertEqual(len(ctx.files), 2)

    def test_get_summary(self):
        step = SearchFilter({"pattern": "*.log"})
        self.assertIn("*.log", step.get_summary())


class TestSizeFilterStep(unittest.TestCase):
    def test_min_size_filter(self):
        files = [_make_entry(size=10), _make_entry(size=200)]
        ctx = ActionContext(files)
        # 100 bytes in MB
        step = SizeFilter({"min_mb": str(100 / (1024 * 1024)), "max_mb": "0"})
        step.execute(ctx)
        self.assertEqual(len(ctx.files), 1)
        self.assertEqual(ctx.files[0].size, 200)


class TestDateFilterStep(unittest.TestCase):
    def test_older_filter(self):
        old_time = time.time() - (10 * 86400)
        recent_time = time.time()
        files = [_make_entry(mtime=old_time), _make_entry(mtime=recent_time)]
        ctx = ActionContext(files)
        step = DateFilter({"days": "5", "mode": "Older"})
        step.execute(ctx)
        self.assertEqual(len(ctx.files), 1)

    def test_newer_filter(self):
        old_time = time.time() - (10 * 86400)
        recent_time = time.time()
        files = [_make_entry(mtime=old_time), _make_entry(mtime=recent_time)]
        ctx = ActionContext(files)
        step = DateFilter({"days": "5", "mode": "Newer"})
        step.execute(ctx)
        self.assertEqual(len(ctx.files), 1)


# ===========================================================================
# Action IO Steps
# ===========================================================================

class TestZipStep(unittest.TestCase):
    def test_individual_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "hello"})
            files = list(scan_directory(tmp))
            ctx = ActionContext(files)
            ctx.is_dry_run = False
            step = ZipStep({"mode": "Individual"})
            step.execute(ctx)
            self.assertTrue(os.path.exists(os.path.join(tmp, "a.zip")))

    def test_single_archive_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "a", "b.txt": "b"})
            out_zip = os.path.join(tmp, "archive.zip")
            files = list(scan_directory(tmp))
            ctx = ActionContext(files)
            ctx.is_dry_run = False
            step = ZipStep({"mode": "Single Archive", "dest": out_zip})
            step.execute(ctx)
            self.assertTrue(os.path.exists(out_zip))

    def test_zip_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "a"})
            files = list(scan_directory(tmp))
            ctx = ActionContext(files)
            ctx.is_dry_run = True
            step = ZipStep({"mode": "Individual"})
            step.execute(ctx)
            self.assertFalse(os.path.exists(os.path.join(tmp, "a.zip")))
            self.assertGreater(len(ctx.results), 0)


class TestDeleteStep(unittest.TestCase):
    def test_delete_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "data"})
            files = list(scan_directory(tmp))
            ctx = ActionContext(files)
            ctx.is_dry_run = True
            step = DeleteStep()
            step.execute(ctx)
            # Files should still exist after dry run
            self.assertTrue(os.path.exists(os.path.join(tmp, "a.txt")))


class TestFileActionService(unittest.TestCase):
    def test_transfer_items_supports_per_item_destinations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")

            items = [
                {
                    "source_path": str(first),
                    "destination_dir": str(root / "dest" / "a"),
                },
                {
                    "source_path": str(second),
                    "destination_dir": str(root / "dest" / "b"),
                },
            ]

            outcome = FileActionService.transfer_items(
                items,
                None,
                "copy",
                dry_run=False,
                path_getter=lambda item: item["source_path"],
                destination_getter=lambda item: item["destination_dir"],
            )

            self.assertFalse(outcome.cancelled)
            self.assertEqual(len(outcome.successes), 2)
            self.assertTrue((root / "dest" / "a" / "first.txt").exists())
            self.assertTrue((root / "dest" / "b" / "second.txt").exists())

    def test_rename_items_with_parts_supports_collision_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "alpha-1.txt"
            second = root / "alpha-2.txt"
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")

            outcome = FileActionService.rename_items_with_rules(
                [str(first), str(second)],
                find_text="alpha-",
                replace_text="renamed-",
                prefix="",
                suffix="",
                dry_run=True,
            )

            self.assertEqual(len(outcome.successes), 2)
            self.assertEqual(
                [Path(record.result.destination_path).name for record in outcome.successes],
                ["renamed-1.txt", "renamed-2.txt"],
            )

    def test_rename_items_with_parts_reports_invalid_names_as_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sample"
            target.write_text("data", encoding="utf-8")

            outcome = FileActionService.rename_items_with_rules(
                [str(target)],
                find_text="sample",
                replace_text="",
                prefix="",
                suffix="",
                dry_run=True,
            )

            self.assertEqual(len(outcome.failures), 1)
            self.assertIn("Could not prepare rename", outcome.failures[0].message)

    def test_rename_items_with_regex_reports_unchanged_files_as_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "report.txt"
            target.write_text("data", encoding="utf-8")

            outcome = FileActionService.rename_items_with_regex(
                [str(target)],
                r"missing",
                "replacement",
                dry_run=True,
            )

            self.assertEqual(len(outcome.successes), 0)
            self.assertEqual(len(outcome.skipped_records), 1)
            self.assertIn("unchanged", outcome.skipped_records[0].message)


# ===========================================================================
# media_ops.py
# ===========================================================================

class TestMediaOps(unittest.TestCase):
    @unittest.skipIf(PdfWriter is None, "pypdf not installed")
    def test_merge_pdfs_dry_run_returns_structured_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_a = Path(tmp) / "a.pdf"
            src_b = Path(tmp) / "b.pdf"
            output = Path(tmp) / "merged.pdf"

            for path in (src_a, src_b):
                writer = PdfWriter()
                writer.add_blank_page(width=72, height=72)
                with open(path, "wb") as handle:
                    writer.write(handle)

            report = merge_pdfs([str(src_a), str(src_b)], str(output), dry_run=True)

            self.assertEqual(report["requested"], 2)
            self.assertEqual(report["merged"], 2)
            self.assertEqual(report["output_path"], str(output))
            self.assertFalse(Path(output).exists())

    def test_convert_image_dry_run_returns_output_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "sample.png"
            Image.new("RGB", (10, 10), "red").save(src)

            report = convert_image(str(src), "JPEG", 100, dry_run=True)

            self.assertTrue(report["output_path"].endswith("sample.jpeg"))
            self.assertEqual(report["source_path"], str(src))
            self.assertFalse(os.path.exists(report["output_path"]))

    @unittest.skipIf(PdfWriter is None, "pypdf not installed")
    def test_split_pdf_dry_run_returns_planned_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "source.pdf"
            out_dir = Path(tmp) / "pages"
            out_dir.mkdir()

            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            writer.add_blank_page(width=72, height=72)
            with open(pdf_path, "wb") as handle:
                writer.write(handle)

            report = split_pdf(str(pdf_path), str(out_dir), dry_run=True)

            self.assertEqual(report["requested"], 2)
            self.assertEqual(len(report["pages"]), 2)
            self.assertEqual(report["source_path"], str(pdf_path))
            self.assertEqual(report["output_dir"], str(out_dir))
            self.assertTrue(all(page.endswith(".pdf") for page in report["pages"]))
            self.assertFalse(any(Path(page).exists() for page in report["pages"]))


# ===========================================================================
# cleaner.py
# ===========================================================================

class TestRemoveEmptyFolders(unittest.TestCase):
    def test_removes_empty_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "empty1"))
            os.makedirs(os.path.join(tmp, "empty2"))
            log = remove_empty_folders(tmp, dry_run=False)
            self.assertEqual(len(log), 2)
            self.assertFalse(os.path.exists(os.path.join(tmp, "empty1")))

    def test_dry_run_keeps_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "empty"))
            log = remove_empty_folders(tmp, dry_run=True)
            self.assertTrue(any("DRY-RUN" in l for l in log))
            self.assertTrue(os.path.exists(os.path.join(tmp, "empty")))

    def test_non_empty_folder_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "notempty")
            os.makedirs(sub)
            Path(os.path.join(sub, "a.txt")).write_text("data")
            log = remove_empty_folders(tmp, dry_run=False)
            self.assertTrue(os.path.exists(sub))


class TestMetadataCleaner(unittest.TestCase):
    def test_no_metadata_for_txt(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"plain text")
            path = f.name
        try:
            has, size, info = MetadataCleaner.get_metadata_info(path)
            self.assertFalse(has)
        finally:
            os.unlink(path)

    def test_remove_metadata_unsupported_returns_false(self):
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"data")
            path = f.name
        try:
            result = MetadataCleaner.remove_metadata(path)
            self.assertFalse(result)
        finally:
            os.unlink(path)

    def test_remove_metadata_dry_run_supported_returns_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "photo.png"
            image = Image.new("RGB", (8, 8), "blue")
            image.save(path)

            result = MetadataCleaner.remove_metadata(str(path), dry_run=True)

            self.assertTrue(result)
            self.assertTrue(path.exists())


# ===========================================================================
# integrity.py
# ===========================================================================

class TestIntegrity(unittest.TestCase):
    def test_create_and_verify_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "hello", "b.txt": "world"})
            snap = os.path.join(tmp, "snap.json")
            create_report = IntegrityMonitor.create_snapshot(tmp, snap)
            self.assertTrue(os.path.exists(snap))
            self.assertEqual(create_report["saved"], 2)
            report = IntegrityMonitor.verify_snapshot(tmp, snap)
            issues = report["discrepancies"]
            # snap.json itself will show as NEW since it wasn't in original scan
            news = [i for i in issues if i.startswith("NEW")]
            mods = [i for i in issues if i.startswith("MODIFIED")]
            self.assertEqual(len(mods), 0)

    def test_detect_modification(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = os.path.join(tmp, "a.txt")
            Path(file_path).write_text("original")
            snap = os.path.join(tmp, "snap.json")
            IntegrityMonitor.create_snapshot(tmp, snap)
            # Modify the file
            Path(file_path).write_text("modified content")
            issues = IntegrityMonitor.verify_snapshot(tmp, snap)["discrepancies"]
            modified = [i for i in issues if "MODIFIED" in i and "a.txt" in i]
            self.assertTrue(len(modified) > 0)

    def test_detect_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "data", "b.txt": "data2"})
            snap = os.path.join(tmp, "snap.json")
            IntegrityMonitor.create_snapshot(tmp, snap)
            os.unlink(os.path.join(tmp, "b.txt"))
            issues = IntegrityMonitor.verify_snapshot(tmp, snap)["discrepancies"]
            deleted = [i for i in issues if "DELETED" in i and "b.txt" in i]
            self.assertTrue(len(deleted) > 0)

    def test_detect_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "data"})
            snap = os.path.join(tmp, "snap.json")
            IntegrityMonitor.create_snapshot(tmp, snap)
            Path(os.path.join(tmp, "new.txt")).write_text("new data")
            issues = IntegrityMonitor.verify_snapshot(tmp, snap)["discrepancies"]
            new = [i for i in issues if "NEW" in i and "new.txt" in i]
            self.assertTrue(len(new) > 0)

    def test_verify_snapshot_returns_structured_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "data"})
            snap = os.path.join(tmp, "snap.json")
            IntegrityMonitor.create_snapshot(tmp, snap)
            Path(os.path.join(tmp, "new.txt")).write_text("new data")

            report = IntegrityMonitor.verify_snapshot(tmp, snap)

            self.assertIn("discrepancies", report)
            self.assertIn("stats", report)
            self.assertIn("snapshot_entries", report)
            self.assertIn("current_entries", report)
            self.assertEqual(
                report["stats"]["NEW"],
                len([item for item in report["discrepancies"] if item.startswith("NEW:")]),
            )
            self.assertEqual(report["issue_count"], len(report["discrepancies"]))

    def test_single_file_snapshot_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "tracked.txt"
            target.write_text("original", encoding="utf-8")
            snap = os.path.join(tmp, "snap.json")

            create_report = IntegrityMonitor.create_snapshot(str(target), snap)
            report = IntegrityMonitor.verify_snapshot(str(target), snap)

            self.assertEqual(create_report["saved"], 1)
            self.assertEqual(report["discrepancies"], [])
            self.assertTrue(report["is_clean"])

    def test_create_snapshot_returns_structured_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "data", "b.txt": "more"})
            snap = os.path.join(tmp, "snap.json")

            report = IntegrityMonitor.create_snapshot(tmp, snap)

            self.assertIn("message", report)
            self.assertIn("output", report)
            self.assertIn("saved", report)
            self.assertIn("scanned", report)
            self.assertIn("skipped", report)
            self.assertEqual(report["saved"], 2)
            self.assertEqual(report["scanned"], 2)


# ===========================================================================
# reporting.py
# ===========================================================================

class TestReporting(unittest.TestCase):
    def _sample_duplicates(self):
        e1 = _make_entry("/a/file.txt", size=100, ext=".txt")
        e2 = _make_entry("/b/file.txt", size=100, ext=".txt")
        return {"abc123": [e1, e2]}

    def test_csv_export(self):
        dupes = self._sample_duplicates()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            ReportGenerator.duplicates_to_csv(dupes, path)
            content = Path(path).read_text()
            self.assertIn("abc123", content)
        finally:
            os.unlink(path)

    def test_json_export(self):
        dupes = self._sample_duplicates()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ReportGenerator.duplicates_to_json(dupes, path)
            data = json.loads(Path(path).read_text())
            self.assertIn("abc123", data)
        finally:
            os.unlink(path)

    def test_txt_export(self):
        dupes = self._sample_duplicates()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name
        try:
            ReportGenerator.duplicates_to_txt(dupes, path)
            content = Path(path).read_text()
            self.assertIn("abc123", content)
        finally:
            os.unlink(path)


# ===========================================================================
# usage.py
# ===========================================================================

class TestUsage(unittest.TestCase):
    def test_analyze_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "x" * 100, "b.txt": "y" * 50})
            result = analyze_size(tmp)
            self.assertIsInstance(result, dict)
            total = sum(result.values())
            self.assertGreater(total, 0)

    def test_generate_report(self):
        data = {"/folder1": 1000, "/folder2": 500}
        lines = generate_usage_report(data)
        self.assertGreater(len(lines), 0)

    def test_generate_report_empty(self):
        lines = generate_usage_report({})
        self.assertIn("No files found.", lines)


# ===========================================================================
# renamer.py
# ===========================================================================

class TestBulkRename(unittest.TestCase):
    def test_rename_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"report_old.txt": "data"})
            log = bulk_rename(tmp, r"old", "new", dry_run=True)
            self.assertTrue(any("Would rename" in l for l in log))
            self.assertTrue(os.path.exists(os.path.join(tmp, "report_old.txt")))

    def test_rename_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"report_old.txt": "data"})
            log = bulk_rename(tmp, r"old", "new", dry_run=False)
            self.assertTrue(os.path.exists(os.path.join(tmp, "report_new.txt")))


# ===========================================================================
# organizer.py
# ===========================================================================

class TestOrganizer(unittest.TestCase):
    def test_organize_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_files(root, {"a.txt": "aaa"})
            dest = str(root / "dest")
            os.makedirs(dest)
            q = SearchQuery().set_extensions(".txt")
            log = Organizer.organize_files(str(root), q, "copy", dest, dry_run=False)
            self.assertTrue(os.path.exists(os.path.join(dest, "a.txt")))

    def test_organize_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_files(root, {"a.txt": "aaa"})
            dest = str(root / "dest")
            os.makedirs(dest)
            q = SearchQuery().set_extensions(".txt")
            log = Organizer.organize_files(str(root), q, "move", dest, dry_run=True)
            self.assertTrue(os.path.exists(str(root / "a.txt")))

    def test_delete_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {"a.txt": "data"})
            entries = list(scan_directory(tmp))
            with patch("filemanager.core.operations.files.send2trash"):
                log = Organizer.delete_files(entries, dry_run=False)
            self.assertGreater(len(log), 0)


# ===========================================================================
# duplicates.py
# ===========================================================================

class TestDuplicates(unittest.TestCase):
    def test_find_duplicates_with_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Create two files with identical content
            _make_files(Path(tmp), {
                "a.txt": "identical content here",
                "b.txt": "identical content here",
                "c.txt": "different content",
            })
            dupes = find_duplicates(tmp)
            # Should find one duplicate group (a.txt and b.txt)
            self.assertGreater(len(dupes), 0)
            for h, entries in dupes.items():
                self.assertGreaterEqual(len(entries), 2)

    def test_find_no_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_files(Path(tmp), {
                "a.txt": "unique content 1",
                "b.txt": "unique content 22",
            })
            dupes = find_duplicates(tmp)
            self.assertEqual(len(dupes), 0)

    def test_duplicates_with_progress(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(5):
                Path(os.path.join(tmp, f"f{i}.txt")).write_text("same")
            dupes = find_duplicates(tmp, progress_callback=lambda c, t, m: calls.append(1))
            self.assertGreater(len(dupes), 0)

    def test_duplicate_keeper_strategy_prefers_newest(self):
        older = _make_entry("older.txt", mtime=time.time() - 50)
        newer = _make_entry("newer.txt", mtime=time.time())

        keeper = choose_duplicate_keeper([older, newer], "newest")

        self.assertEqual(keeper.path, "newer.txt")

    def test_duplicate_keeper_strategy_prefers_smallest(self):
        large = _make_entry("large.txt", size=50)
        small = _make_entry("small.txt", size=10)

        keeper = choose_duplicate_keeper([large, small], "smallest")

        self.assertEqual(keeper.path, "small.txt")

    def test_order_duplicate_records_supports_group_sort_and_limit(self):
        a = _make_entry("a.txt", size=10)
        b = _make_entry("b.txt", size=10)
        c = _make_entry("c.txt", size=5)
        records = build_duplicate_records({"hash-two": [a, b], "hash-one": [c, _make_entry("d.txt", size=5), _make_entry("e.txt", size=5)]})

        ordered = order_duplicate_records(records, sort_key="group", reverse=True, limit=2)

        self.assertEqual(len(ordered), 2)
        self.assertTrue(all(record["group_size"] == 3 for record in ordered))

    def test_select_duplicate_records_skips_keeper_per_group(self):
        older = _make_entry("older.txt", mtime=time.time() - 60)
        newer = _make_entry("newer.txt", mtime=time.time())
        records = build_duplicate_records({"hash-a": [older, newer]})

        selected = select_duplicate_records(records, keep_strategy="newest")

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["entry"].path, "older.txt")

    def test_serialize_duplicate_record_includes_group_metadata(self):
        entry = _make_entry("dup.txt", size=12)
        record = build_duplicate_records({"hash-a": [entry, _make_entry("dup2.txt", size=12)]})[0]

        payload = serialize_duplicate_record(record)

        self.assertEqual(payload["duplicate_hash"], "hash-a")
        self.assertEqual(payload["duplicate_group_size"], 2)

    def test_serialize_duplicate_group_summary_marks_summary_rows(self):
        records = build_duplicate_records({"hash-a": [_make_entry("dup.txt", size=12), _make_entry("dup2.txt", size=12)]})

        payload = serialize_duplicate_group_summary("hash-a", records)

        self.assertEqual(payload["record_type"], "duplicate_group_summary")
        self.assertEqual(payload["duplicate_group_size"], 2)
        self.assertEqual(payload["group_total_size"], 24)

    def test_build_duplicate_export_rows_includes_summary_before_members(self):
        records = build_duplicate_records({"hash-a": [_make_entry("dup.txt", size=12), _make_entry("dup2.txt", size=12)]})

        rows = build_duplicate_export_rows(records, include_group_summary=True)

        self.assertEqual(rows[0]["record_type"], "duplicate_group_summary")
        self.assertEqual(rows[1]["record_type"], "duplicate_entry")
        self.assertEqual(rows[2]["record_type"], "duplicate_entry")

    def test_build_duplicate_export_rows_can_exclude_summary_rows(self):
        records = build_duplicate_records({"hash-a": [_make_entry("dup.txt", size=12), _make_entry("dup2.txt", size=12)]})

        rows = build_duplicate_export_rows(records, include_group_summary=False)

        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["record_type"] == "duplicate_entry" for row in rows))


class TestResultExport(unittest.TestCase):
    def test_export_search_results_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = _make_entry(path=os.path.join(tmp, "match.txt"), ext=".txt")
            destination = os.path.join(tmp, "results.json")

            export_search_results([entry], destination, format="json")

            payload = json.loads(Path(destination).read_text(encoding="utf-8"))
            self.assertEqual(payload[0]["filename"], "match.txt")
            self.assertEqual(payload[0]["extension"], ".txt")

    def test_export_result_rows_csv_supports_extra_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = _make_entry(path=os.path.join(tmp, "dup.txt"), ext=".txt")
            destination = os.path.join(tmp, "duplicates.csv")

            export_result_rows(
                [serialize_file_entry(entry, duplicate_hash="abc123", duplicate_group_size=2)],
                destination,
                format="csv",
            )

            with open(destination, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(rows[0]["filename"], "dup.txt")
            self.assertEqual(rows[0]["duplicate_hash"], "abc123")
            self.assertEqual(rows[0]["duplicate_group_size"], "2")


# ===========================================================================
# MetaCleanStep (modifications.py)
# ===========================================================================

class TestMetaCleanStep(unittest.TestCase):
    def test_dry_run_logs_would_clean(self):
        e = _make_entry("image.jpg", ext=".jpg")
        ctx = ActionContext([e])
        ctx.is_dry_run = True
        step = MetaCleanStep()
        step.execute(ctx)
        self.assertTrue(any("Would Clean" in r[2] for r in ctx.results))


# ===========================================================================
# ConvertImageStep
# ===========================================================================

class TestConvertImageStep(unittest.TestCase):
    def test_skips_non_image(self):
        e = _make_entry("doc.pdf", ext=".pdf")
        ctx = ActionContext([e])
        ctx.is_dry_run = False
        step = ConvertImageStep({"format": "PNG", "resize": 100})
        step.execute(ctx)
        self.assertTrue(any("Skipped" in r[2] for r in ctx.results))

    def test_dry_run_logs(self):
        e = _make_entry("photo.jpg", ext=".jpg")
        ctx = ActionContext([e])
        ctx.is_dry_run = True
        step = ConvertImageStep({"format": "PNG", "resize": 50})
        step.execute(ctx)
        self.assertTrue(any("Would convert" in r[2] for r in ctx.results))


# ===========================================================================
# Plugin loader
# ===========================================================================

class TestPluginLoader(unittest.TestCase):
    def test_loader_returns_list(self):
        from filemanager.ui.plugin_loader import PluginLoader
        repo_root = Path(__file__).resolve().parents[1]
        plugin_dir = str(repo_root / "filemanager" / "ui" / "plugins")
        loader = PluginLoader(plugin_dir)
        plugins = loader.load_plugins()
        self.assertIsInstance(plugins, list)
        self.assertGreater(len(plugins), 0)

    def test_loader_nonexistent_dir(self):
        from filemanager.ui.plugin_loader import PluginLoader
        loader = PluginLoader("/nonexistent/path")
        plugins = loader.load_plugins()
        self.assertEqual(len(plugins), 0)


if __name__ == "__main__":
    unittest.main()
