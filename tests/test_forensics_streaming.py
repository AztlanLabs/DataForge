"""
Tests for TICK-109 — forensics streaming engine + byte budget.
Covers all acceptance_criteria:
 - 4 workers × 10 MB byte-budgeted streaming (not f.read(10MB) unbounded)
 - ingest_disk_image has no file_paths list, uses streaming queue
 - build_timeline reuses FileEntry timestamps (no second stat)
"""
import inspect
import os
import time
from pathlib import Path


def test_calculate_hashes_reuses_mmap_path():
    src = Path("dataforge/modules/forensics.py").read_text()
    # Must delegate to get_file_hash (TICK-103 mmap impl)
    assert "get_file_hash" in src, "calculate_hashes should reuse get_file_hash"
    # Verify worker calls get_file_hash
    from dataforge.modules.forensics import _hash_entry_worker
    src_worker = inspect.getsource(_hash_entry_worker)
    assert "get_file_hash" in src_worker
    # Hasher itself should have mmap path
    hasher_src = Path("dataforge/core/hasher.py").read_text()
    assert "mmap" in hasher_src
    assert "MMAP_THRESHOLD" in hasher_src or "1 << 20" in hasher_src


def test_keyword_search_budgeted_streaming():
    src = Path("dataforge/modules/forensics.py").read_text()
    # Old unbounded pattern must be gone
    assert "f.read(10 * 1024 * 1024)" not in src, "must not use unbounded f.read(10MB)"
    # Must have bounded queue and byte budget
    assert "queue.Queue" in src, "must use queue.Queue for streaming"
    assert "byte_budget" in src, "must compute byte_budget = 10 MB * workers"
    assert "10 * 1024 * 1024" in src
    # Streaming worker should use 1 MiB chunk
    assert "1 * 1024 * 1024" in src
    # Check worker is chunked
    from dataforge.modules.forensics import _keyword_search_worker
    w_src = inspect.getsource(_keyword_search_worker)
    assert "chunk_size" in w_src or "1 * 1024" in w_src
    assert "prev_tail" in w_src or "overlap" in w_src, "must handle keyword spanning chunk"
    # Check keyword_search uses bounded queue
    from dataforge.modules.forensics import keyword_search
    ks_src = inspect.getsource(keyword_search)
    assert "queue.Queue" in ks_src
    assert "byte_budget" in ks_src
    assert "search_thread_workers" in ks_src


def test_keyword_search_functional(tmp_path):
    from dataforge.modules.forensics import keyword_search

    # Create files
    file_a = tmp_path / "a.txt"
    file_a.write_text("hello secret world")
    file_b = tmp_path / "b.bin"
    file_b.write_bytes(b"\x00\xff secret \x00 keyword")
    file_c = tmp_path / "c.txt"
    file_c.write_text("nothing here")

    # Case-insensitive
    hits = keyword_search([str(file_a), str(file_b), str(file_c)], ["SeCrEt"], case_sensitive=False)
    paths = {h["path"] for h in hits}
    assert str(file_a) in paths
    assert str(file_b) in paths
    assert str(file_c) not in paths
    for h in hits:
        assert "matched_keywords" in h
        assert "match_count" in h

    # Case-sensitive should not match SeCrEt vs secret
    hits_cs = keyword_search([str(file_a)], ["SeCrEt"], case_sensitive=True)
    assert hits_cs == []

    # Keyword spanning 1 MiB boundary — craft file where keyword straddles chunk
    # Chunk is 1 MiB; we write 1MiB -2 bytes + "KEYWORD" bridging boundary
    large = tmp_path / "large.txt"
    chunk = 1 * 1024 * 1024
    # Fill first chunk with 'A', then boundary with keyword split
    with open(large, "wb") as f:
        f.write(b"A" * (chunk - 2))
        f.write(b"KEYWORD")  # 2 bytes of tail + 5 bytes of next chunk
        f.write(b"B" * 100)
    hits2 = keyword_search([str(large)], ["KEYWORD"])
    assert any(h["path"] == str(large) for h in hits2), "should find keyword spanning chunk boundary"


def test_keyword_search_10mb_cap(tmp_path):
    from dataforge.modules.forensics import keyword_search

    # Create file >10MB, keyword at 11MB should not be found
    big = tmp_path / "big.bin"
    with open(big, "wb") as f:
        f.write(b"x" * (10 * 1024 * 1024 + 1024))
        f.write(b"SECRETKEY")
    # Write keyword just beyond 10MB limit — should be capped and not found
    # To ensure, we truncate and test both positions
    # First test keyword within limit (at 1MB) should be found
    within = tmp_path / "within.txt"
    with open(within, "wb") as f:
        f.write(b"y" * (1 * 1024 * 1024))
        f.write(b"WITHINKEY")
        f.write(b"z" * 100)
    hits_w = keyword_search([str(within)], ["WITHINKEY"])
    assert len(hits_w) == 1

    # Now test beyond 10MB — create file where keyword only appears after 10MB
    beyond = tmp_path / "beyond.bin"
    with open(beyond, "wb") as f:
        f.write(b"q" * (10 * 1024 * 1024 + 500))
        f.write(b"BEYONDKEY")
    hits_b = keyword_search([str(beyond)], ["BEYONDKEY"])
    assert len(hits_b) == 0, "keyword beyond 10 MB cap should not be found"


def test_keyword_search_global_budget_four_workers(tmp_path):
    """4 workers × 10 MB → 40 MB budget, streaming keeps peak low."""
    from dataforge.modules.forensics import keyword_search
    src = Path("dataforge/modules/forensics.py").read_text()
    # Verify budget calc present
    assert "10 * 1024 * 1024 * max_workers" in src or "byte_budget = 10 * 1024" in src
    # Functional: 8 files × 2 MB each with 4 workers — should complete without OOM
    files = []
    for i in range(8):
        p = tmp_path / f"f{i}.txt"
        p.write_bytes(b"a" * (2 * 1024 * 1024) + b"budgettest")
        files.append(str(p))
    hits = keyword_search(files, ["budgettest"])
    assert len(hits) == 8


def test_ingest_no_file_paths_and_uses_queue():
    src = Path("dataforge/modules/forensics.py").read_text()
    # The ticket mandates grep -n file_paths must have zero hits
    assert "file_paths" not in src, "ingest_disk_image must not contain file_paths variable"
    # Must use streaming queue
    assert "stream_queue" in src or "streaming queue" in src.lower()
    assert "queue.Queue" in src
    # ingest must import/call scan_directory and not materialize list via file_paths
    from dataforge.modules.forensics import ingest_disk_image
    ing_src = inspect.getsource(ingest_disk_image)
    assert "scan_directory" in ing_src
    assert "file_paths" not in ing_src
    assert "Queue" in ing_src or "queue" in ing_src


def test_ingest_streaming_functional(tmp_path):
    from dataforge.modules.forensics import ingest_disk_image

    # Create fake image as directory
    img = tmp_path / "image"
    img.mkdir()
    (img / "file1.txt").write_text("hello world secret")
    (img / "file2.txt").write_text("another file")
    sub = img / "subdir"
    sub.mkdir()
    (sub / "file3.txt").write_text("keyword here: SECRET")

    out = tmp_path / "out"
    out.mkdir()

    results = ingest_disk_image(
        str(img),
        str(out),
        options={"extract_metadata": True, "hash_files": True, "keyword_index": True, "keywords": ["secret"]},
    )
    assert results["file_count"] == 3
    assert len(results["hashes"]) == 3
    # keyword search is case-insensitive lowercasing inside keyword_search — secret matches 2 files?
    # file1 has secret, file3 has SECRET but keyword is lowercased secret -> should match both case-insensitive
    assert len(results["keyword_hits"]) >= 1
    # Check manifests written
    assert (out / "hash_manifest.json").exists()
    assert (out / "os_artifacts.json").exists()
    assert (out / "keyword_results.json").exists()


def test_build_timeline_reuses_fileentry_no_stat(tmp_path):
    """Verify build_timeline does not call os.stat — reuses FileEntry."""
    from dataforge.modules import forensics as fm

    src = inspect.getsource(fm.build_timeline)
    # No os.stat in this function (comments sanitized to stat syscall)
    assert "os.stat" not in src, "build_timeline must not call os.stat, reuse FileEntry"

    # Functional check with monkeypatched os.stat counting
    orig_stat = os.stat
    calls = {"count": 0}

    def counting_stat(path, *a, **kw):
        calls["count"] += 1
        return orig_stat(path, *a, **kw)

    # Prepare files with known timestamps
    d = tmp_path / "tl"
    d.mkdir()
    f1 = d / "a.txt"
    f2 = d / "b.txt"
    f1.write_text("a")
    f2.write_text("b")
    # Set distinct mtimes
    now = time.time()
    os.utime(f1, (now - 100, now - 100))
    os.utime(f2, (now - 10, now - 10))

    # Patch os.stat globally during build_timeline
    import unittest.mock as mock

    with mock.patch("dataforge.modules.forensics.os.stat", side_effect=counting_stat) as m:
        # Note: forensics module imported os directly, but mock patch above targets that module's os
        # Also need to ensure scan_directory path not patched? scan_directory uses entry.stat internally
        events = fm.build_timeline(str(d), sort_key="mtime")
        # build_timeline itself should not have called os.stat for files
        # Filter out directory stats (scanner legitimately stats the root dir)
        file_calls = [c for c in m.call_args_list if str(c[0][0]).endswith(".txt")]
        assert len(file_calls) == 0, f"build_timeline called os.stat for files {file_calls}, expected 0 (reuses FileEntry)"

    assert len(events) == 2
    # Most recent first (b.txt newer)
    assert events[0]["path"] == str(f2)
    assert events[1]["path"] == str(f1)
    # Check timestamps come from FileEntry (modified_at) not fresh stat
    assert "timestamp_iso" in events[0]
    assert "mtime" in events[0]
    assert events[0]["size"] == os.path.getsize(str(f2))


def test_build_timeline_sort_keys(tmp_path):
    from dataforge.modules.forensics import build_timeline

    d = tmp_path / "tl2"
    d.mkdir()
    for name in ["x.txt", "y.txt"]:
        (d / name).write_text(name)
    # Should handle all valid sort keys without calling os.stat
    for key in ["mtime", "ctime", "atime"]:
        events = build_timeline(str(d), sort_key=key)
        assert len(events) == 2

    # Invalid key defaults to mtime
    events = build_timeline(str(d), sort_key="invalid")
    assert len(events) == 2


def test_calculate_hashes_mmap_correctness(tmp_path):
    from dataforge.modules.forensics import calculate_hashes
    from dataforge.core.hasher import get_file_hash
    import hashlib

    f = tmp_path / "hashme.bin"
    data = os.urandom(2 * 1024 * 1024)
    f.write_bytes(data)
    # Single file via calculate_hashes
    res = calculate_hashes([str(f)], algorithms=["md5", "sha256"])
    assert len(res) == 1
    assert res[0]["md5"] == hashlib.md5(data).hexdigest()
    assert res[0]["sha256"] == hashlib.sha256(data).hexdigest()
    # Should match direct get_file_hash
    assert res[0]["md5"] == get_file_hash(str(f), algo="md5")
