"""TICK-102 — parallel BFS scanner + DirEntry.stat reuse + inode fields.

Acceptance criteria under test:
1. Wall time / stat count: no double-stat (DirEntry.stat reuse) — verifies spec §1.1
2. Hardlink grouping via (st_dev,st_ino)
3. cancel_token stops promptly
4. Keeps excluded_folders/extensions, symlink skipping, max_depth, batch emission
"""

import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from dataforge.core.common import FileEntry
from dataforge.core.scanner import build_file_entry, scan_directory


@pytest.fixture
def clean_config(monkeypatch):
    from dataforge.core.config import config

    monkeypatch.setattr(config, "data", dict(config.DEFAULT_CONFIG))
    # ensure no exclusions unless test sets them
    config.data["excluded_folders"] = []
    config.data["excluded_extensions"] = []


def _make_files(root: Path, specs: dict) -> list[Path]:
    paths = []
    for rel, content in specs.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# 1. Result parity: parallel BFS must yield same files as sequential baseline
#    (explicit count check — covers “keep result count identical” gate)
# ---------------------------------------------------------------------------


class TestParallelParity:
    def test_recursive_yields_all_files(self, tmp_path, clean_config):
        _make_files(
            tmp_path,
            {
                "a.txt": "a",
                "b.txt": "b",
                "sub/c.txt": "c",
                "sub/nested/d.txt": "d",
                "other/e.dat": "e",
            },
        )
        entries = list(scan_directory(str(tmp_path), recursive=True))
        names = sorted(e.filename for e in entries)
        assert names == ["a.txt", "b.txt", "c.txt", "d.txt", "e.dat"]

    def test_non_recursive_only_top_level(self, tmp_path, clean_config):
        _make_files(tmp_path, {"top.txt": "t", "sub/deep.txt": "d"})
        entries = list(scan_directory(str(tmp_path), recursive=False))
        assert {e.filename for e in entries} == {"top.txt"}

    def test_max_depth_controls(self, tmp_path, clean_config):
        _make_files(
            tmp_path,
            {
                "a.txt": "a",
                "sub/b.txt": "b",
                "sub/deep/c.txt": "c",
                "sub/deep/more/d.txt": "d",
            },
        )
        assert {e.filename for e in list(scan_directory(str(tmp_path), max_depth=0))} == {"a.txt"}
        assert {e.filename for e in list(scan_directory(str(tmp_path), max_depth=1))} == {"a.txt", "b.txt"}
        assert {e.filename for e in list(scan_directory(str(tmp_path), max_depth=2))} == {
            "a.txt",
            "b.txt",
            "c.txt",
        }

    def test_single_file_path_yields_one_entry(self, tmp_path, clean_config):
        target = tmp_path / "single.txt"
        target.write_text("hello")
        entries = list(scan_directory(str(target)))
        assert len(entries) == 1
        assert entries[0].path == str(target)
        assert entries[0].st_ino != 0

    def test_batch_emission_1k_via_queue(self, tmp_path, clean_config):
        # Create >1k files to exercise batch queue draining
        specs = {f"file_{i:04d}.txt": "x" for i in range(1200)}
        _make_files(tmp_path, specs)
        entries = list(scan_directory(str(tmp_path)))
        assert len(entries) == 1200
        # All have inode fields
        assert all(e.st_ino != 0 for e in entries)


# ---------------------------------------------------------------------------
# 2. No double-stat: DirEntry.stat reuse
# ---------------------------------------------------------------------------


class TestNoDoubleStat:
    def test_build_file_entry_not_called_for_dir_walk(self, tmp_path, clean_config):
        _make_files(tmp_path, {"a.txt": "a", "sub/b.txt": "b"})
        with patch("dataforge.core.scanner.build_file_entry") as mock_build:
            # build_file_entry should NOT be used for directory walk (stat reuse path)
            # Single-file path below does use it; dir walk must not
            mock_build.side_effect = lambda p: FileEntry(p, "x", ".txt", 1, 0, 0)
            entries = list(scan_directory(str(tmp_path)))
            # If build_file_entry were used per file, mock would have been called
            assert mock_build.call_count == 0
            assert len(entries) == 2

    def test_build_file_entry_used_for_single_file_path(self, tmp_path, clean_config):
        target = tmp_path / "only.txt"
        target.write_text("data")
        with patch("dataforge.core.scanner.build_file_entry", wraps=build_file_entry) as wrapped:
            entries = list(scan_directory(str(target)))
            assert len(entries) == 1
            assert wrapped.call_count == 1

    def test_stat_syscall_count_halved(self, tmp_path, clean_config):
        # Count os.stat calls — DirEntry.stat does NOT go through os.stat, so count should be low
        _make_files(tmp_path, {"a.txt": "a", "b.txt": "b", "sub/c.txt": "c"})
        original_stat = os.stat
        calls = []

        def counting_stat(path, *args, **kwargs):
            calls.append(path)
            return original_stat(path, *args, **kwargs)

        with patch("dataforge.core.scanner.os.stat", side_effect=counting_stat):
            # os.stat is used for initial root checks (isfile/isdir/scandir validation) but NOT per file
            entries = list(scan_directory(str(tmp_path)))
            assert len(entries) == 3
            # Per-file os.stat would be 3+; with DirEntry reuse it is at most root validation (2-3)
            # Allow up to 5 for isfile/isdir/scandir checks + single-file fallback
            assert len(calls) <= 5, f"os.stat called {len(calls)} times, expected no per-file double-stat: {calls}"

    def test_entry_stat_populates_inode_fields(self, tmp_path, clean_config):
        _make_files(tmp_path, {"a.txt": "hello world"})
        entries = list(scan_directory(str(tmp_path)))
        e = entries[0]
        st = os.stat(str(tmp_path / "a.txt"), follow_symlinks=False)
        assert e.st_ino == st.st_ino
        assert e.st_dev == st.st_dev
        # st_blocks may be 0 on some FS, but attribute must exist and match
        assert e.st_blocks == getattr(st, "st_blocks", 0)
        assert e.size == st.st_size

    def test_build_file_entry_populates_inode_fields(self, tmp_path):
        p = tmp_path / "inode.txt"
        p.write_text("data")
        entry = build_file_entry(str(p))
        assert entry is not None
        st = os.stat(str(p), follow_symlinks=False)
        assert entry.st_ino == st.st_ino
        assert entry.st_dev == st.st_dev
        assert entry.st_blocks == getattr(st, "st_blocks", 0)


# ---------------------------------------------------------------------------
# 3. Hardlink grouping via (st_dev, st_ino)
# ---------------------------------------------------------------------------


class TestHardlinkInodeGrouping:
    def test_hardlinks_share_inode_and_dev(self, tmp_path, clean_config):
        if not hasattr(os, "link"):
            pytest.skip("os.link not available")
        src = tmp_path / "original.txt"
        src.write_text("hardlink content")
        link = tmp_path / "hardlink.txt"
        try:
            os.link(str(src), str(link))
        except OSError as e:
            pytest.skip(f"hardlink not supported: {e}")

        entries = list(scan_directory(str(tmp_path)))
        assert len(entries) == 2
        by_path = {Path(e.path).name: e for e in entries}
        a = by_path["original.txt"]
        b = by_path["hardlink.txt"]
        assert a.st_ino == b.st_ino
        assert a.st_dev == b.st_dev
        assert a.hardlink_key == b.hardlink_key
        # Downstream dedup grouping
        groups: dict[tuple[int, int], list[str]] = {}
        for e in entries:
            groups.setdefault(e.hardlink_key, []).append(e.path)
        assert len(groups[a.hardlink_key]) == 2

    def test_distinct_files_have_distinct_hardlink_keys(self, tmp_path, clean_config):
        _make_files(tmp_path, {"a.txt": "alpha", "b.txt": "bravo"})
        entries = list(scan_directory(str(tmp_path)))
        assert len(entries) == 2
        assert entries[0].hardlink_key != entries[1].hardlink_key


# ---------------------------------------------------------------------------
# 4. cancel_token stops promptly
# ---------------------------------------------------------------------------


class TestCancelToken:
    def test_preset_cancel_yields_nothing(self, tmp_path, clean_config):
        _make_files(tmp_path, {"a.txt": "a", "b.txt": "b"})
        tok = threading.Event()
        tok.set()
        assert list(scan_directory(str(tmp_path), cancel_token=tok)) == []
        assert list(scan_directory(str(tmp_path / "a.txt"), cancel_token=tok)) == []

    def test_mid_walk_cancel_stops(self, tmp_path, clean_config):
        # Create enough files that walk takes multiple queue drains
        specs = {f"f_{i:03d}.txt": "x" for i in range(50)}
        _make_files(tmp_path, specs)
        # Subdirs to force BFS levels
        for d in range(5):
            sub = tmp_path / f"dir_{d}"
            sub.mkdir(exist_ok=True)
            for i in range(10):
                (sub / f"nested_{i}.txt").write_text("y")

        tok = threading.Event()

        # Generator that cancels after 5 entries
        gen = scan_directory(str(tmp_path), cancel_token=tok)
        collected = []
        for idx, entry in enumerate(gen):
            collected.append(entry)
            if idx == 4:
                tok.set()
                # Next iteration should stop; allow a few more yields due to buffering?
                # Spec says "yields no further entries" after set — our impl checks before yield
                break
        # Continue draining should yield nothing
        remaining = list(gen)
        assert remaining == []
        # Ensure we stopped early (total files is 100, we got <= ~1005 due to batch)
        total_files = 50 + 50
        assert len(collected) < total_files

    def test_single_file_cancel_before(self, tmp_path, clean_config):
        target = tmp_path / "a.txt"
        target.write_text("data")
        tok = threading.Event()
        tok.set()
        assert list(scan_directory(str(target), cancel_token=tok)) == []


# ---------------------------------------------------------------------------
# 5. Exclusions, symlinks, is_dir, extension handling
# ---------------------------------------------------------------------------


class TestExclusionsAndSymlinks:
    def test_excluded_folders_honored(self, tmp_path, clean_config):
        from dataforge.core.config import config

        _make_files(tmp_path, {"keep.txt": "k", ".git/ignore.txt": "i", "node_modules/pkg/file.txt": "p"})
        config.data["excluded_folders"] = [".git", "node_modules"]
        entries = list(scan_directory(str(tmp_path)))
        names = {e.filename for e in entries}
        assert "keep.txt" in names
        assert "ignore.txt" not in names
        assert "file.txt" not in names

    def test_excluded_extensions_honored(self, tmp_path, clean_config):
        from dataforge.core.config import config

        _make_files(tmp_path, {"keep.txt": "k", "skip.tmp": "s", "skip.log": "s2"})
        config.data["excluded_extensions"] = [".tmp", ".log"]
        entries = list(scan_directory(str(tmp_path)))
        names = {e.filename for e in entries}
        assert "keep.txt" in names
        assert "skip.tmp" not in names
        assert "skip.log" not in names

    def test_symlinks_skipped(self, tmp_path, clean_config):
        real = tmp_path / "real.txt"
        real.write_text("real")
        link = tmp_path / "link.txt"
        try:
            os.symlink(str(real), str(link))
        except OSError:
            pytest.skip("symlink not supported")
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "file.txt").write_text("f")
        linkdir = tmp_path / "linkdir"
        try:
            os.symlink(str(sub), str(linkdir))
        except OSError:
            pass
        entries = list(scan_directory(str(tmp_path)))
        names = {Path(e.path).name for e in entries}
        assert "real.txt" in names
        assert "link.txt" not in names
        assert "file.txt" in names
        # linkdir should not be recursed, so no duplicate file.txt via linkdir
        assert len([e for e in entries if e.filename == "file.txt"]) == 1

    def test_inaccessible_dir_swallowed(self, clean_config):
        entries = list(scan_directory("/nonexistent_path_xyz_12345", recursive=True))
        assert entries == []

    def test_fileentry_extension_lowercased(self, tmp_path, clean_config):
        (tmp_path / "UPPER.TXT").write_text("data")
        entries = list(scan_directory(str(tmp_path)))
        assert entries[0].extension == ".txt"


# ---------------------------------------------------------------------------
# 6. ThreadPool and queue.Queue usage (spec guard)
# ---------------------------------------------------------------------------


class TestParallelInternals:
    def test_uses_threadpool_and_queue(self, tmp_path, clean_config):
        _make_files(tmp_path, {"a.txt": "a"})
        import dataforge.core.scanner as scanner_mod

        with patch.object(scanner_mod.concurrent.futures, "ThreadPoolExecutor", wraps=scanner_mod.concurrent.futures.ThreadPoolExecutor) as mock_pool, patch.object(
            scanner_mod.queue, "Queue", wraps=scanner_mod.queue.Queue
        ) as mock_queue:
            list(scan_directory(str(tmp_path)))
            assert mock_pool.called, "ThreadPoolExecutor not used"
            # Verify max_workers = min(32, cpu*4)
            _, kwargs = mock_pool.call_args
            expected = min(32, (os.cpu_count() or 4) * 4)
            assert kwargs.get("max_workers", mock_pool.call_args[0][0] if mock_pool.call_args[0] else None) == expected or mock_pool.call_args[1].get("max_workers") == expected
            assert mock_queue.called, "queue.Queue not used for batch emission"

    def test_queue_batch_size_constant(self):
        import dataforge.core.scanner as scanner_mod
        import inspect

        src = inspect.getsource(scanner_mod.scan_directory)
        assert "BATCH_SIZE" in src or "1000" in src
        assert "queue.Queue" in src
        assert "ThreadPoolExecutor" in src
        assert "entry.stat" in src or "entry.stat(" in src
