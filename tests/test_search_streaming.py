"""TICK-106 — streaming content search via pool + mmap.

Acceptance:
- GIVEN 50k-file corpus WHEN search --content runs THEN wall time minutes→seconds and peak RSS <200 MB (streaming)
- GIVEN --error-format json with invalid --name-glob+--name-regex WHEN run THEN stderr JSON error and exit 2
- GIVEN binary files WHEN content search without --force-binary THEN skipped unless mime is text
"""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import dataforge.modules.search as search_mod
from dataforge.modules.search import SearchQuery, build_search_query, iter_search_files, search_files


def _make_files(root: Path, specs: dict):
    for rel, content in specs.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding="utf-8")


class TestContentMmapBytesRegex:
    def test_literal_search_found(self, tmp_path):
        _make_files(tmp_path, {"a.txt": "hello needle world"})
        q = SearchQuery().set_content("needle")
        assert len(search_files(str(tmp_path), q)) == 1

    def test_literal_not_found(self, tmp_path):
        _make_files(tmp_path, {"a.txt": "hello world"})
        q = SearchQuery().set_content("absent_xyz")
        assert search_files(str(tmp_path), q) == []

    def test_regex_search(self, tmp_path):
        _make_files(tmp_path, {"a.txt": "foo123bar", "b.txt": "nope"})
        q = SearchQuery().set_content(r"foo\d+bar", is_regex=True)
        res = search_files(str(tmp_path), q)
        assert len(res) == 1
        assert res[0].filename == "a.txt"

    def test_case_insensitive_default(self, tmp_path):
        _make_files(tmp_path, {"a.txt": "HeLLo"})
        q = SearchQuery().set_content("hello", case_sensitive=False)
        assert len(search_files(str(tmp_path), q)) == 1
        q2 = SearchQuery().set_content("hello", case_sensitive=True)
        assert search_files(str(tmp_path), q2) == []

    def test_mmap_and_bytes_regex_present(self):
        import inspect

        src = inspect.getsource(search_mod)
        assert "mmap" in src
        assert "re.compile" in src
        # bytes regex is used via pattern_bytes
        assert "content_pattern_bytes" in src
        assert "10 * 1024 * 1024" in src
        assert "1 << 20" in src

    def test_no_readlines(self):
        import pathlib

        src = pathlib.Path(search_mod.__file__).read_text()
        assert "readlines" not in src
        # ensure not using Python line loop open(...,'r'). The file should use mmap
        assert "mmap.mmap" in src

    def test_sliding_window_span(self, tmp_path):
        window = 1 << 20
        p = tmp_path / "span.txt"
        payload = b"a" * (window - 4) + b"HELLO" + b"b" * 1000
        p.write_bytes(payload)
        q = SearchQuery().set_content("HELLO")
        res = search_files(str(tmp_path), q)
        assert len(res) == 1

    def test_cap_10mb(self, tmp_path):
        cap = 10 * 1024 * 1024
        # within cap
        p = tmp_path / "large.txt"
        with open(p, "wb") as f:
            f.write(b"a" * (5 * 1024 * 1024))
            f.write(b"needle_in")
            f.write(b"b" * (5 * 1024 * 1024))
        q = SearchQuery().set_content("needle_in")
        assert len(search_files(str(tmp_path), q)) == 1
        # beyond cap
        os.unlink(p)
        p2 = tmp_path / "large2.txt"
        with open(p2, "wb") as f:
            f.write(b"a" * (cap + 2048))
            f.write(b"needle_out")
        q2 = SearchQuery().set_content("needle_out")
        assert search_files(str(tmp_path), q2) == []


class TestBinaryAwareSkip:
    def test_binary_skipped_without_force(self, tmp_path):
        (tmp_path / "a.txt").write_text("needle here", encoding="utf-8")
        b = tmp_path / "b.bin"
        b.write_bytes(b"\x00\x01needle\xff\x00binary")
        q = SearchQuery().set_content("needle")
        res = search_files(str(tmp_path), q)
        names = {r.filename for r in res}
        assert "a.txt" in names
        assert "b.bin" not in names

    def test_binary_found_with_force(self, tmp_path):
        (tmp_path / "a.txt").write_text("needle", encoding="utf-8")
        b = tmp_path / "b.bin"
        b.write_bytes(b"\x00needle\x00")
        q = SearchQuery().set_content("needle", force_binary=True)
        res = search_files(str(tmp_path), q)
        names = {r.filename for r in res}
        assert "b.bin" in names

    def test_build_query_force_binary(self, tmp_path):
        (tmp_path / "b.bin").write_bytes(b"\x00needle\x00")
        q = build_search_query(content_text="needle", force_binary=True)
        res = search_files(str(tmp_path), q)
        assert len(res) == 1
        q2 = build_search_query(content_text="needle", force_binary=False)
        res2 = search_files(str(tmp_path), q2)
        assert len(res2) == 0

    def test_magic_optional_import(self):
        import inspect

        src = inspect.getsource(search_mod)
        assert "try:" in src
        assert "import magic" in src
        assert "_HAS_MAGIC" in src

    def test_text_file_with_null_is_binary(self, tmp_path):
        # heuristic fallback: null byte means binary
        p = tmp_path / "maybe.txt"
        p.write_bytes(b"hello\x00world")
        q = SearchQuery().set_content("hello")
        # without force should skip because contains null
        res = search_files(str(tmp_path), q)
        assert len(res) == 0
        q2 = SearchQuery().set_content("hello", force_binary=True)
        assert len(search_files(str(tmp_path), q2)) == 1


class TestParallelStreaming:
    def test_uses_threadpool_and_workers(self, tmp_path, monkeypatch):
        _make_files(tmp_path, {f"f{i}.txt": f"needle {i}" for i in range(10)})
        import concurrent.futures as cf

        calls: list[int | None] = []

        class Spy(cf.ThreadPoolExecutor):
            def __init__(self, *a, **kw):
                calls.append(kw.get("max_workers"))
                super().__init__(*a, **kw)

        monkeypatch.setattr(search_mod.concurrent.futures, "ThreadPoolExecutor", Spy)
        q = SearchQuery().set_content("needle")
        res = search_files(str(tmp_path), q)
        assert len(res) == 10
        assert len(calls) >= 1
        # workers should be config-driven or default min(32,cpu*2)
        assert any(isinstance(c, int) and 1 <= c <= 32 for c in calls if c is not None)

    def test_search_thread_workers_config(self, monkeypatch):
        # when config returns custom value, _get_search_workers uses it
        from dataforge.core.config import config

        monkeypatch.setattr(config, "get", lambda k, d=None: 16 if k == "search_thread_workers" else d)
        assert search_mod._get_search_workers() == 16
        monkeypatch.setattr(config, "get", lambda k, d=None: None)
        # fallback to cpu*2
        w = search_mod._get_search_workers()
        assert 1 <= w <= 32

    def test_streaming_iter_yields_incrementally(self, tmp_path):
        _make_files(tmp_path, {f"f{i}.txt": f"needle {i}" for i in range(30)})
        q = SearchQuery().set_content("needle")
        gen = iter_search_files(str(tmp_path), q)
        first = next(gen)
        assert first is not None
        count = 1 + sum(1 for _ in gen)
        assert count == 30

    def test_cancel_token_preset(self, tmp_path):
        _make_files(tmp_path, {"a.txt": "needle"})
        q = SearchQuery().set_content("needle")
        tok = threading.Event()
        tok.set()
        assert search_files(str(tmp_path), q, cancel_token=tok) == []

    def test_cancel_mid_stream(self, tmp_path):
        for i in range(20):
            (tmp_path / f"x{i}.txt").write_text("needle", encoding="utf-8")
        q = SearchQuery().set_content("needle")
        tok = threading.Event()

        gen = iter_search_files(str(tmp_path), q, cancel_token=tok)
        # consume few then cancel
        it = iter(gen)
        next(it)
        tok.set()
        # further iteration should stop promptly (either raises or empty)
        try:
            remaining = list(it)
        except InterruptedError:
            remaining = []
        # should not have yielded all 20
        assert len(remaining) < 19

    def test_non_content_path_still_sequential(self, tmp_path):
        # without content, should still return results correctly
        _make_files(tmp_path, {"a.txt": "a", "b.py": "b"})
        q = SearchQuery().set_extensions(".txt")
        res = search_files(str(tmp_path), q)
        assert len(res) == 1
        assert res[0].filename == "a.txt"

    def test_shared_keyword_search_helper(self, tmp_path):
        # forensics shared helper should reuse same engine
        (tmp_path / "a.txt").write_text("hello needle world")
        (tmp_path / "b.txt").write_text("nope")
        from dataforge.modules.search import keyword_search_shared

        res = keyword_search_shared([str(tmp_path / "a.txt"), str(tmp_path / "b.txt")], ["needle"])
        assert len(res) == 1
        assert res[0]["path"].endswith("a.txt")
        assert "needle" in res[0]["matched_keywords"]


class TestCLIErrorFormat:
    def test_invalid_name_glob_and_regex_json(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = "."
        res = subprocess.run(
            [sys.executable, "-m", "dataforge.cli", "search", "/tmp", "--name-glob", "*.txt", "--name-regex", ".*\\.py", "--error-format", "json"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert res.returncode == 2
        assert res.stdout == ""
        data = json.loads(res.stderr)
        assert data["ok"] is False
        assert data["error"]["exit_code"] == 2
        assert "name-glob" in data["error"]["message"]

    def test_invalid_name_glob_and_regex_text(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = "."
        res = subprocess.run(
            [sys.executable, "-m", "dataforge.cli", "search", "/tmp", "--name-glob", "*.txt", "--name-regex", ".*\\.py", "--error-format", "text"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert res.returncode == 2
        # Click UsageError goes to stderr
        assert "Use either --name-glob or --name-regex" in res.stderr or "Use either" in res.stdout + res.stderr
