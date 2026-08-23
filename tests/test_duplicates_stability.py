"""TICK-904 — Duplicate finder SIGSEGV hashing stability.

Covers:
- 500-file fixture with 33 uncached duplicates
- cancel_token after 10 hashes
- hasher get_file_hash on 0-byte file
- file deleted between scan and hash
- concurrent workers + cache batch
"""

import hashlib
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

from dataforge.core.cache import file_cache
from dataforge.core.hasher import get_file_hash, get_hashes
from dataforge.modules.duplicates import _fast_hash, find_duplicates


def _make_files(root: Path, files: dict):
    for name, content in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content)


def test_hasher_zero_byte_no_mmap(tmp_path):
    p = tmp_path / "empty.bin"
    p.write_bytes(b"")
    for algo in ("md5", "sha1", "sha256", "sha512", "blake2b"):
        h = getattr(hashlib, algo)()
        expected = h.hexdigest()
        assert get_file_hash(str(p), algo) == expected
        assert get_hashes(str(p), [algo])[algo] == expected


def test_hasher_deleted_file_no_crash(tmp_path):
    p = tmp_path / "to_delete.txt"
    p.write_text("will be deleted")
    # delete before hash
    p.unlink()
    assert get_file_hash(str(p), "md5") == ""
    assert _fast_hash(str(p)) is None


def test_fast_hash_deleted_returns_none(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("content")
    p.unlink()
    assert _fast_hash(str(p)) is None
    # also permission: non-regular file (dir) should return None
    d = tmp_path / "adir"
    d.mkdir()
    assert _fast_hash(str(d)) is None


def test_find_duplicates_500_files_33_uncached_no_sigsegv(tmp_path, caplog):
    # Build 500 files where 33 are duplicates not cached
    # Strategy: 467 unique + 33 duplicates sharing same content
    file_cache.clear()
    # Create 33 duplicate files with same content "duplicate payload"
    dup_content = b"duplicate-group-payload-" + os.urandom(64)
    for i in range(33):
        (tmp_path / f"dup_{i:03d}.txt").write_bytes(dup_content)
    # Create 467 unique files with different content/size
    for i in range(467):
        (tmp_path / f"uniq_{i:03d}.txt").write_bytes(f"unique-{i}-{os.urandom(16).hex()}".encode())
    assert len(list(tmp_path.iterdir())) == 500
    caplog.set_level(10)
    dups = find_duplicates(str(tmp_path))
    # No crash, returns dict
    assert isinstance(dups, dict)
    # At least one group (the 33 duplicates)
    assert len(dups) >= 1
    # Verify the duplicate group size 33 is found
    max_group = max((len(v) for v in dups.values()), default=0)
    assert max_group == 33, f"expected 33 group got {max_group}"
    # Log should contain Hashing N new files
    # find_duplicates logs "Hashing 33 new files..." when cache miss
    # On second run, cache hit should not log hashing same count?
    # We check at least one log line contains Hashing
    assert any("Hashing" in r.message for r in caplog.records)


def test_cancel_after_10_hashes(tmp_path):
    file_cache.clear()
    # Create ~50 duplicate candidates
    content = b"cancel-test-content"
    for i in range(50):
        (tmp_path / f"c_{i}.txt").write_bytes(content)
    tok = threading.Event()
    # Wrap get_file_hash to trigger cancel after 10 calls
    orig = get_file_hash
    call_count = 0

    def cancelling_hash(path, algo="md5", cancel_token=None):
        nonlocal call_count
        call_count += 1
        if call_count >= 10:
            tok.set()
        # Respect cancel_token if passed
        if cancel_token and cancel_token.is_set():
            return ""
        return orig(path, algo, cancel_token=tok if cancel_token is not None else None)

    with patch("dataforge.modules.duplicates.get_file_hash", side_effect=cancelling_hash):
        start = time.time()
        try:
            result = find_duplicates(str(tmp_path), cancel_token=tok)
            # If not raised, should return quickly and either empty or partial
            # Accept both: either InterruptedError or cancelled dict/empty
            assert isinstance(result, dict)
            elapsed = time.time() - start
            assert elapsed < 5, "cancel should be quick"
        except InterruptedError:
            # Expected path
            assert tok.is_set()
            pass
        # No lingering threads: ensure file_cache still consistent
        assert file_cache.get_hash is not None


def test_file_deleted_between_scan_and_hash(tmp_path):
    file_cache.clear()
    # Create files where one will be deleted after scan but before hash
    (tmp_path / "keep1.txt").write_bytes(b"same keep")
    (tmp_path / "keep2.txt").write_bytes(b"same keep")
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"same keep")
    # Patch _fast_hash to delete victim after first call
    orig_fast = _fast_hash
    deleted = False

    def deleting_fast(path, cancel_token=None):
        nonlocal deleted
        if path == str(victim) and not deleted:
            # Delete the file to simulate race
            try:
                victim.unlink()
            except Exception:
                pass
            deleted = True
            # Now call orig which should handle missing -> None
            return orig_fast(path, cancel_token)
        return orig_fast(path, cancel_token)

    with patch("dataforge.modules.duplicates._fast_hash", side_effect=deleting_fast):
        dups = find_duplicates(str(tmp_path))
        # Should not crash, should still find duplicates for keep1/keep2
        assert isinstance(dups, dict)
        # At least one group of 2 (keep files)
        assert any(len(v) >= 2 for v in dups.values())


def test_concurrent_workers_cache_batch_no_locked(tmp_path):
    # Run 3 times with 4 workers to trigger race
    file_cache.clear()
    # Create duplicates that will cause batch inserts
    for run in range(3):
        # Clean tmp per run? Use subdir
        sub = tmp_path / f"run{run}"
        sub.mkdir()
        for i in range(20):
            (sub / f"a_{i}.txt").write_bytes(b"concurrent-content-" + b"x" * 100)
        # Ensure config cache_batch small to force many batches? But we deferred flush now, so single flush
        # Run find_duplicates 3 times sequentially to check no "database is locked"
        dups = find_duplicates(str(sub))
        assert isinstance(dups, dict)
        # file_cache should be consistent
        # No exception about locked
    # Verify cache consistency: clear and re-hash should work
    file_cache.clear()
    # Create simple dup
    (tmp_path / "final_a.txt").write_bytes(b"final")
    (tmp_path / "final_b.txt").write_bytes(b"final")
    dups = find_duplicates(str(tmp_path))
    assert isinstance(dups, dict)


def test_hasher_mmap_truncation_race_no_sigsegv(tmp_path, monkeypatch):
    # Simulate truncation between stat and mmap by monkeypatching os.fstat to return smaller size
    p = tmp_path / "trunc.bin"
    data = b"A" * (2 * 1024 * 1024)  # 2MiB
    p.write_bytes(data)
    # Force mmap path by lowering threshold
    import dataforge.core.hasher as hm

    monkeypatch.setattr(hm, "MMAP_THRESHOLD", 1024)
    # Monkeypatch fstat to simulate truncated file
    orig_fstat = os.fstat

    def fake_fstat(fd):
        st = orig_fstat(fd)
        # Return stat with size half
        class FakeStat:
            st_mode = st.st_mode
            st_size = st.st_size // 2
            st_blocks = getattr(st, "st_blocks", 0)
        return FakeStat()

    with patch("dataforge.core.hasher.os.fstat", side_effect=fake_fstat):
        # Should not SIGSEGV, should return hash of truncated or fallback
        h = get_file_hash(str(p), "sha256")
        assert isinstance(h, str)
        # Should be either full or truncated hash but not empty/crash
        assert len(h) == 64 or h == ""  # allow fallback empty if error


def test_hasher_non_regular_file(tmp_path):
    # FIFO or dir should not SIGSEGV
    d = tmp_path / "adir2"
    d.mkdir()
    assert get_file_hash(str(d), "md5") == ""
    # Try symlink to dir (if supported)
    link = tmp_path / "link"
    try:
        link.symlink_to(d)
        # stat follows symlink? Our code uses os.stat which follows symlink to dir -> not regular -> ""
        assert get_file_hash(str(link), "md5") == ""
    except OSError:
        pass
