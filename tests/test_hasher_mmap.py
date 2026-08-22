import hashlib
import os
import threading

import pytest

from dataforge.core.hasher import (
    BLOCK_SIZE,
    MMAP_THRESHOLD,
    SUPPORTED_ALGORITHMS,
    _get_block_size,
    get_file_hash,
    get_hashes,
)


def _hash_direct(path: str, algo: str) -> str:
    h = getattr(hashlib, algo)()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


class TestHasherMmap:
    def test_block_size_is_1mib(self):
        assert BLOCK_SIZE == 1 << 20
        assert _get_block_size() == 1 << 20

    def test_supported_algorithms_unchanged(self):
        assert SUPPORTED_ALGORITHMS == ('md5', 'sha1', 'sha256', 'sha512', 'blake2b')

    def test_block_size_from_config(self, tmp_path, monkeypatch):
        # Simulate custom config value by monkeypatching _get_block_size via config
        from dataforge.core.config import config as cfg_instance

        # Patch config.get to return a different valid size
        monkeypatch.setattr(cfg_instance, "get", lambda k, d=None: 512 * 1024 if k == "hash_block_size" else d)
        assert _get_block_size() == 512 * 1024
        # invalid value falls back to default (too small -> fallback)
        monkeypatch.setattr(cfg_instance, "get", lambda k, d=None: 123 if k == "hash_block_size" else d)
        assert _get_block_size() == 1 << 20
        # restore to default size for subsequent tests
        monkeypatch.setattr(cfg_instance, "get", lambda k, d=None: (1 << 20) if k == "hash_block_size" else d)
        assert _get_block_size() == 1 << 20

    def test_unsupported_algo_raises(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_bytes(b"hello")
        with pytest.raises(ValueError):
            get_file_hash(str(p), algo="crc32")
        with pytest.raises(ValueError):
            get_file_hash(str(p), algo="xxhash")
        with pytest.raises(ValueError):
            get_hashes(str(p), ["md5", "crc32"])
        with pytest.raises(ValueError):
            get_hashes(str(p), ["notalgo"])

    def test_small_file_hash_matches_direct(self, tmp_path):
        p = tmp_path / "small.bin"
        data = os.urandom(64 * 1024)
        p.write_bytes(data)
        for algo in SUPPORTED_ALGORITHMS:
            expected = _hash_direct(str(p), algo)
            assert get_file_hash(str(p), algo) == expected

    def test_small_file_streaming_path(self, tmp_path):
        # File under MMAP_THRESHOLD should use streaming path and still match
        p = tmp_path / "under.bin"
        p.write_bytes(b"a" * (1024 * 1024))  # 1 MiB
        assert p.stat().st_size < MMAP_THRESHOLD
        assert get_file_hash(str(p), "sha256") == _hash_direct(str(p), "sha256")

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.bin"
        p.write_bytes(b"")
        for algo in SUPPORTED_ALGORITHMS:
            h = getattr(hashlib, algo)()
            assert get_file_hash(str(p), algo) == h.hexdigest()
            assert get_hashes(str(p), [algo])[algo] == h.hexdigest()

    def test_nonexistent_returns_empty(self):
        assert get_file_hash("nonexistent_file_xyz_12345.txt", "md5") == ""
        assert get_hashes("nonexistent_file_xyz_12345.txt", ["md5", "sha256"]) == {"md5": "", "sha256": ""}

    def test_get_hashes_single_read_matches_separate(self, tmp_path):
        p = tmp_path / "multi.bin"
        p.write_bytes(b"multi hash test content " * 1000)
        algos = ["md5", "sha256"]
        combined = get_hashes(str(p), algos)
        for algo in algos:
            assert combined[algo] == get_file_hash(str(p), algo)
        # Also test all algos at once
        all_algos = list(SUPPORTED_ALGORITHMS)
        combined_all = get_hashes(str(p), all_algos)
        for algo in all_algos:
            assert combined_all[algo] == get_file_hash(str(p), algo)

    def test_get_hashes_empty_algos(self, tmp_path):
        p = tmp_path / "x.bin"
        p.write_bytes(b"data")
        assert get_hashes(str(p), []) == {}

    def test_cancel_token_aborts_before_start(self, tmp_path):
        p = tmp_path / "cancel.bin"
        p.write_bytes(b"x" * (2 * 1024 * 1024))
        cancel = threading.Event()
        cancel.set()
        assert get_file_hash(str(p), "sha256", cancel_token=cancel) == ""
        assert get_hashes(str(p), ["md5", "sha256"], cancel_token=cancel) == {"md5": "", "sha256": ""}

    def test_cancel_token_aborts_mid_file_via_chunk_hook(self, tmp_path, monkeypatch):
        # Force small block size so we have many chunks to allow mid-file cancel
        p = tmp_path / "mid.bin"
        p.write_bytes(b"a" * (5 * 1024 * 1024))  # 5 MiB
        # Patch threshold to force mmap path for this 5 MiB file
        import dataforge.core.hasher as hasher_mod
        monkeypatch.setattr(hasher_mod, "MMAP_THRESHOLD", 1 * 1024 * 1024)
        # Patch block size to 1 MiB default still gives 5 chunks
        cancel = threading.Event()

        # Monkeypatch hashlib.sha256 to set cancel after first update
        original_sha256 = hashlib.sha256

        call_count = 0

        class CancellingHasher:
            def __init__(self):
                self._h = original_sha256()

            def update(self, data):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    cancel.set()
                self._h.update(data)

            def hexdigest(self):
                return self._h.hexdigest()

        monkeypatch.setattr(hashlib, "sha256", CancellingHasher)
        result = get_file_hash(str(p), "sha256", cancel_token=cancel)
        # Should have aborted and returned ""
        assert result == ""

    def test_large_file_mmap_path_matches_direct(self, tmp_path, monkeypatch):
        # Create a file just over the threshold (lower threshold for test speed)
        import dataforge.core.hasher as hasher_mod
        monkeypatch.setattr(hasher_mod, "MMAP_THRESHOLD", 1 * 1024 * 1024)
        p = tmp_path / "large.bin"
        # 2 MiB file — above 1 MiB threshold
        data = os.urandom(2 * 1024 * 1024)
        p.write_bytes(data)
        for algo in ["md5", "sha256", "sha512"]:
            assert get_file_hash(str(p), algo) == _hash_direct(str(p), algo)
            combined = get_hashes(str(p), [algo])
            assert combined[algo] == _hash_direct(str(p), algo)

    def test_real_large_file_above_16mib(self, tmp_path):
        # Create a real >16 MiB file (17 MiB) to hit the production mmap path without monkeypatch
        p = tmp_path / "real_large.bin"
        # Use deterministic pattern to avoid huge random generation time
        chunk = b"0123456789ABCDEF" * 65536  # 1 MiB chunk
        with open(p, "wb") as f:
            for _ in range(17):
                f.write(chunk)
        assert p.stat().st_size > MMAP_THRESHOLD
        # Verify hash correctness via direct hashlib
        assert get_file_hash(str(p), "sha256") == _hash_direct(str(p), "sha256")
        assert get_hashes(str(p), ["md5", "sha256"])["sha256"] == _hash_direct(str(p), "sha256")

    def test_mmap_advise_does_not_break(self, tmp_path, monkeypatch):
        # Ensure posix_fadvise/madvise failures are swallowed
        import dataforge.core.hasher as hasher_mod
        monkeypatch.setattr(hasher_mod, "MMAP_THRESHOLD", 1 * 1024)
        p = tmp_path / "advise.bin"
        p.write_bytes(b"b" * 4096)
        # Force posix_fadvise to raise OSError
        if hasattr(os, "posix_fadvise"):
            monkeypatch.setattr(os, "posix_fadvise", lambda *a, **k: (_ for _ in ()).throw(OSError("advise fail")))
        # Should still hash correctly
        assert get_file_hash(str(p), "md5") == _hash_direct(str(p), "md5")
