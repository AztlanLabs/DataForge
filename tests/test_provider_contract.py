"""TICK-002 contract tests: FileProvider ABC expansion + FileEntry inode fields.

Acceptance criteria under test:
1. LocalProvider() instantiates without TypeError and satisfies the 7-method ABC.
2. FileEntry st_ino/st_dev group hardlinks; st_blocks carries sparse awareness.
3. With no provider selection, scanning defaults to LocalProvider/scan_directory.
"""

import hashlib
import os
import threading

import pytest

from dataforge.core.common import FileEntry
from dataforge.core.config import config
from dataforge.core.hasher import get_file_hash
from dataforge.core.provider import FileProvider, LocalProvider, default_provider
from dataforge.core.scanner import scan_directory

SEVEN_METHODS = (
    "list_files",
    "list_files_parallel",
    "stat",
    "open",
    "hash",
    "hash_many",
    "exists",
)


@pytest.fixture
def clean_config(monkeypatch):
    """Isolate scanner exclusions from the developer's real config.json."""
    monkeypatch.setattr(config, "data", dict(config.DEFAULT_CONFIG))


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "a.txt").write_text("alpha")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("bravo" * 100)
    return tmp_path


def _entry(path, ino=0, dev=0, blocks=0):
    return FileEntry(
        path=path,
        filename=os.path.basename(path),
        extension=".txt",
        size=1,
        created_at=0.0,
        modified_at=0.0,
        st_ino=ino,
        st_dev=dev,
        st_blocks=blocks,
    )


class TestAbcContract:
    def test_local_provider_instantiates_without_typeerror(self):
        provider = LocalProvider()
        assert isinstance(provider, FileProvider)

    def test_seven_method_contract_declared_on_abc(self):
        for name in SEVEN_METHODS:
            assert callable(getattr(FileProvider, name)), f"FileProvider missing {name}"
        provider = LocalProvider()
        for name in SEVEN_METHODS:
            assert callable(getattr(provider, name))

    def test_base_class_not_instantiable(self):
        with pytest.raises(TypeError):
            FileProvider()

    def test_legacy_three_method_subclass_still_instantiable(self):
        class LegacyProvider(FileProvider):
            def list_files(self, path, recursive=True, cancel_token=None, progress_callback=None):
                return iter(())

            def move(self, src, dst):
                pass

            def copy(self, src, dst):
                pass

        legacy = LegacyProvider()
        assert isinstance(legacy, FileProvider)
        with pytest.raises(NotImplementedError):
            legacy.stat("whatever")
        assert list(legacy.list_files_parallel("root")) == []

    def test_every_method_accepts_cancel_token(self):
        provider = LocalProvider()
        token = threading.Event()
        assert provider.exists(__file__, cancel_token=token) is True
        assert provider.hash_many([], cancel_token=token) == {}
        assert list(provider.list_files_parallel(__file__, cancel_token=token)) != []


class TestFileEntryInodeFields:
    def test_defaults_are_zero_and_positional_construction_unbroken(self):
        entry = FileEntry("p", "p", ".txt", 10, 1.0, 2.0)
        assert (entry.st_ino, entry.st_dev, entry.st_blocks) == (0, 0, 0)

    def test_hardlink_key_groups_shared_inode(self):
        first = _entry("/mnt/a.txt", ino=42, dev=2049)
        second = _entry("/mnt/link.txt", ino=42, dev=2049)
        other = _entry("/mnt/b.txt", ino=43, dev=2049)
        groups: dict[tuple[int, int], list[str]] = {}
        for entry in (first, second, other):
            groups.setdefault(entry.hardlink_key, []).append(entry.path)
        assert groups[(2049, 42)] == ["/mnt/a.txt", "/mnt/link.txt"]
        assert groups[(2049, 43)] == ["/mnt/b.txt"]

    def test_distinct_devices_never_share_group(self):
        assert _entry("/x", ino=7, dev=1).hardlink_key != _entry("/x", ino=7, dev=2).hardlink_key

    def test_sparse_blocks_retained(self):
        sparse = _entry("/sparse.img", ino=9, dev=1, blocks=8)
        assert sparse.st_blocks * 512 < sparse.size or sparse.size == 1
        assert sparse.st_blocks == 8


class TestDefaultProvider:
    def test_defaults_to_local_provider(self):
        assert isinstance(default_provider(), LocalProvider)

    def test_list_files_matches_scan_directory(self, tmp_path, clean_config):
        (tmp_path / "a.txt").write_text("alpha")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.txt").write_text("bravo")
        via_provider = sorted(e.path for e in LocalProvider().list_files(str(tmp_path)))
        via_scanner = sorted(e.path for e in scan_directory(str(tmp_path)))
        assert via_provider == via_scanner
        assert len(via_provider) == 2


class TestLocalProviderShim:
    def test_stat_mirrors_os_stat(self, tree):
        target = str(tree / "a.txt")
        assert LocalProvider().stat(target).st_size == os.stat(target).st_size

    def test_stat_missing_raises_oserror(self, tmp_path):
        with pytest.raises(OSError):
            LocalProvider().stat(str(tmp_path / "missing.bin"))

    def test_exists_true_false_and_cancel(self, tree):
        provider = LocalProvider()
        cancelled = threading.Event()
        cancelled.set()
        assert provider.exists(str(tree / "a.txt")) is True
        assert provider.exists(str(tree / "missing.bin")) is False
        assert provider.exists(str(tree / "a.txt"), cancel_token=cancelled) is False

    def test_open_reads_bytes(self, tree):
        with LocalProvider().open(str(tree / "a.txt")) as handle:
            assert handle.read() == b"alpha"

    @pytest.mark.parametrize("algo", ["md5", "sha256"])
    def test_hash_matches_hasher(self, tree, algo):
        target = str(tree / "a.txt")
        assert LocalProvider().hash(target, algo) == get_file_hash(target, algo)
        assert LocalProvider().hash(target, algo) == getattr(hashlib, algo)(b"alpha").hexdigest()

    def test_hash_missing_returns_empty_string(self, tmp_path):
        assert LocalProvider().hash(str(tmp_path / "missing.bin"), "md5") == ""

    def test_hash_bad_algorithm_raises(self, tree):
        with pytest.raises(ValueError):
            LocalProvider().hash(str(tree / "a.txt"), "crc32")

    def test_hash_many_covers_all_paths_with_progress(self, tree):
        provider = LocalProvider()
        paths = [str(tree / "a.txt"), str(tree / "sub" / "b.txt")]
        calls: list[tuple[int, int]] = []
        digests = provider.hash_many(paths, algo="md5", progress_callback=lambda d, t: calls.append((d, t)))
        assert set(digests) == set(paths)
        assert digests[paths[0]] == get_file_hash(paths[0], "md5")
        assert calls == [(1, 2), (2, 2)]

    def test_hash_many_dedupes_repeated_paths(self, tree):
        provider = LocalProvider()
        target = str(tree / "a.txt")
        calls: list[tuple[int, int]] = []
        digests = provider.hash_many([target, target], algo="md5", progress_callback=lambda d, t: calls.append((d, t)))
        assert list(digests) == [target]
        assert calls == [(1, 2)]

    def test_hash_many_cancel_midway_marks_rest_empty(self, tree):
        provider = LocalProvider()
        paths = [str(tree / "a.txt"), str(tree / "sub" / "b.txt")]
        token = threading.Event()

        def stop_after_first(done, _total):
            if done == 1:
                token.set()

        digests = provider.hash_many(paths, algo="md5", cancel_token=token, progress_callback=stop_after_first)
        assert digests[paths[0]] == hashlib.md5(b"alpha").hexdigest()
        assert digests[paths[1]] == ""

    def test_list_files_streams_progress_with_unknown_total(self, tree, clean_config):
        calls: list[tuple[int, int]] = []
        entries = list(LocalProvider().list_files(str(tree), progress_callback=lambda d, t: calls.append((d, t))))
        assert len(entries) == 2
        assert calls == [(1, -1), (2, -1)]
        assert sorted(e.filename for e in entries) == ["a.txt", "b.txt"]

    def test_list_files_preset_cancel_yields_nothing(self, tree, clean_config):
        token = threading.Event()
        token.set()
        assert list(LocalProvider().list_files(str(tree), cancel_token=token)) == []
        assert list(scan_directory(str(tree), cancel_token=token)) == []

    def test_list_files_parallel_falls_back_to_list_files(self, tree, clean_config):
        provider = LocalProvider()
        parallel = sorted(e.path for e in provider.list_files_parallel(str(tree)))
        sequential = sorted(e.path for e in provider.list_files(str(tree)))
        assert parallel == sequential

    def test_move_and_copy_shims_preserved(self, tmp_path):
        provider = LocalProvider()
        src = tmp_path / "src.txt"
        src.write_text("payload")
        dst_copy = tmp_path / "nested" / "copy.txt"
        dst_copy.parent.mkdir()
        provider.copy(str(src), str(dst_copy))
        assert dst_copy.read_text() == "payload"
        dst_move = tmp_path / "moved.txt"
        provider.move(str(src), str(dst_move))
        assert not src.exists() and dst_move.read_text() == "payload"
