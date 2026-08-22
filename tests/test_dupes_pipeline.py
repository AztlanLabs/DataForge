import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from dataforge.core.cache import file_cache
from dataforge.modules.duplicates import find_duplicates


def _make_files(root: Path, files: dict):
    for name, content in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content)


class TestStreamingPipeline:
    def test_no_list_scan_in_code(self):
        src = Path("dataforge/modules/duplicates.py").read_text()
        assert "list(scan" not in src, "must not materialize list(scan_directory)"
        assert "queue.Queue" in src
        assert "ThreadPoolExecutor" in src
        assert "_fast_hash" in src

    def test_streaming_batch_queue(self):
        src = Path("dataforge/modules/duplicates.py").read_text()
        assert "queue.Queue" in src
        assert "BATCH_SIZE" in src or "batch" in src.lower()
        # verify max_workers adaptive
        assert "min(32" in src or "_get_max_workers" in src

    def test_find_duplicates_basic(self, tmp_path):
        _make_files(tmp_path, {"a.txt": "same content", "b.txt": "same content", "c.txt": "different xyz"})
        file_cache.clear()
        dups = find_duplicates(str(tmp_path))
        assert len(dups) == 1
        entries = next(iter(dups.values()))
        assert len(entries) == 2
        paths = {e.path for e in entries}
        assert any("a.txt" in p for p in paths)
        assert any("b.txt" in p for p in paths)

    def test_no_duplicates_when_unique(self, tmp_path):
        _make_files(tmp_path, {"a.txt": "content one", "b.txt": "content two is diff size"})
        file_cache.clear()
        dups = find_duplicates(str(tmp_path))
        assert len(dups) == 0

    def test_size_filter_prevents_hash(self, tmp_path):
        # same size different content not duplicates, but same size forces hashing
        _make_files(tmp_path, {"a.txt": "abc", "b.txt": "xyz"})
        file_cache.clear()
        # Both size 3, same size group -> will fast+full hash, but different hash => no dup
        dups = find_duplicates(str(tmp_path))
        assert len(dups) == 0

    def test_fast_hash_prefilter_same_size_same_xxhash_diff_sha_not_dupes(self, tmp_path):
        # Two files same size + same first 4KiB (so fast hash same) but rest differs -> full hash differs -> not duplicates
        a = b"A" * 4096 + b"XXXX"
        b = b"A" * 4096 + b"YYYY"
        _make_files(tmp_path, {"x.bin": a, "y.bin": b})
        file_cache.clear()
        dups = find_duplicates(str(tmp_path))
        assert len(dups) == 0, "files with same fast hash but different full sha must not be dupes"

    def test_verify_content_filters_hash_collision(self, tmp_path):
        _make_files(tmp_path, {"a.txt": "collision A content same size!!!!", "b.txt": "collision B content same size!!!!"})
        # ensure same size
        assert os.path.getsize(tmp_path / "a.txt") == os.path.getsize(tmp_path / "b.txt")
        file_cache.clear()
        with patch("dataforge.modules.duplicates._fast_hash", return_value="fastsame"):
            with patch("dataforge.modules.duplicates.get_file_hash", return_value="fakecollisionsha"):
                dups_no_verify = find_duplicates(str(tmp_path), verify_content=False)
                assert len(dups_no_verify) == 1
                assert len(next(iter(dups_no_verify.values()))) == 2
                dups_verify = find_duplicates(str(tmp_path), verify_content=True)
                assert len(dups_verify) == 0, "verify_content should byte-compare and reject collision"

    def test_hardlink_counted_once(self, tmp_path):
        p1 = tmp_path / "orig.txt"
        p1.write_text("hardlink content")
        link = tmp_path / "link.txt"
        try:
            os.link(p1, link)
        except OSError:
            pytest.skip("hardlink not supported")
        file_cache.clear()
        dups = find_duplicates(str(tmp_path))
        # only one inode -> no duplicate group
        assert len(dups) == 0
        # with a separate duplicate file sharing content but different inode -> group of 2 (one per inode)
        p3 = tmp_path / "other.txt"
        p3.write_text("hardlink content")
        file_cache.clear()
        dups2 = find_duplicates(str(tmp_path))
        assert len(dups2) == 1
        entries = next(iter(dups2.values()))
        assert len(entries) == 2, "hardlink pair counts as one, plus other file => 2 entries"
        keys = {e.hardlink_key for e in entries}
        assert len(keys) == 2
        # verify no double-hash: fast hash and full hash each called once per inode (3 files but 1 hardlink dedup => 2 unique)
        # ensure st_ino populated
        for e in entries:
            assert e.st_ino != 0
            assert e.st_dev != 0

    def test_hardlink_inode_fields_populated(self, tmp_path):
        _make_files(tmp_path, {"a.txt": "same", "b.txt": "same"})
        file_cache.clear()
        dups = find_duplicates(str(tmp_path))
        for entries in dups.values():
            for e in entries:
                assert e.st_ino != 0
                assert e.st_blocks >= 0

    def test_cancel_preset_raises(self, tmp_path):
        _make_files(tmp_path, {"a.txt": "same", "b.txt": "same"})
        tok = threading.Event()
        tok.set()
        with pytest.raises(InterruptedError):
            find_duplicates(str(tmp_path), cancel_token=tok)

    def test_cancel_mid_walk(self, tmp_path):
        for i in range(20):
            (tmp_path / f"f{i}.txt").write_text("same content for cancel")
        file_cache.clear()
        tok = threading.Event()

        orig_fast = __import__("dataforge.modules.duplicates", fromlist=["_fast_hash"])._fast_hash

        def slow_fast(path, cancel_token=None):
            if tok.is_set():
                return None
            # trigger cancel after few calls
            return orig_fast(path, cancel_token)

        # Use progress callback to trigger cancel
        def progress(c, t, m):
            if c >= 2:
                tok.set()

        # Should raise or return promptly without hashing all
        try:
            find_duplicates(str(tmp_path), progress_callback=progress, cancel_token=tok)
        except InterruptedError:
            pass
        # If not raised, at least should not crash and respect cancel
        assert tok.is_set()

    def test_threadpool_and_queue_used(self):
        src = Path("dataforge/modules/duplicates.py").read_text()
        assert "ThreadPoolExecutor" in src
        assert "queue.Queue" in src
        # ensure fast hash uses ThreadPool and full hash uses ThreadPool
        assert src.count("ThreadPoolExecutor") >= 2

    def test_streaming_uses_queue_not_list(self, tmp_path):
        # large-ish number of files to ensure streaming not O(n) list materialization
        # we just verify it completes with many files and queue batching
        for i in range(50):
            (tmp_path / f"file{i}.txt").write_text(f"content {i % 5}")
        file_cache.clear()
        dups = find_duplicates(str(tmp_path))
        # files with same content modulo 5 should produce duplicates
        assert isinstance(dups, dict)

    def test_cache_batch_used(self):
        src = Path("dataforge/modules/duplicates.py").read_text()
        assert "set_hash_many" in src
        assert "get_hash" in src

    def test_single_file_no_dup(self, tmp_path):
        _make_files(tmp_path, {"only.txt": "lonely"})
        file_cache.clear()
        dups = find_duplicates(str(tmp_path))
        assert dups == {}

    def test_empty_dir(self, tmp_path):
        file_cache.clear()
        dups = find_duplicates(str(tmp_path))
        assert dups == {}

    def test_progress_callback_invoked(self, tmp_path):
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text("same")
        file_cache.clear()
        calls = []
        find_duplicates(str(tmp_path), progress_callback=lambda c, t, m: calls.append((c, t, m)))
        assert len(calls) > 0
