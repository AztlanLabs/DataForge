"""Tests for TICK-105: collision O(N²), prune empty-dest, case-only rename."""

import os
import threading

import pytest

from dataforge.core.operations import files
from dataforge.core.operations.files import (
    normalize_path,
    rename_path,
    resolve_collision_path,
    transfer_path,
)


@pytest.fixture(autouse=True)
def _clear_collision_cache():
    """Ensure each test starts with empty collision caches."""
    files._reserved_normcase_cache.clear()
    files._reserved_normalized_ids.clear()
    yield
    files._reserved_normcase_cache.clear()
    files._reserved_normalized_ids.clear()


# ---- R-OPS-1: O(N) not O(N²) -------------------------------------------------

def test_resolve_collision_is_on_not_on2(monkeypatch):
    """GIVEN 5k-item move WHEN resolve_collision_path called THEN O(N)."""
    orig = files.normalize_path
    count = {"n": 0}

    def counting(path):
        count["n"] += 1
        return orig(path)

    monkeypatch.setattr(files, "normalize_path", counting)

    reserved: set[str] = set()
    N = 5000
    for i in range(N):
        # Use deterministic expanded paths to avoid filesystem touch
        resolve_collision_path(f"/tmp/dest/file_{i}.txt", reserved_paths=reserved)

    # Each call normalizes destination_path + current_path (2). Old O(N²) would
    # be ~12.5M (sum 0..N-1). We allow generous O(N) budget: < 3*N.
    # With 2 per call = 10k, we assert < 20000.
    assert count["n"] < 20000, f"normalize_path called {count['n']} times, expected O(N) <20000 for N={N}"

    # All candidates must be unique and reserved size == N
    assert len(reserved) == N


def test_resolve_collision_thread_safe():
    """Reserved set updates are lock-protected; concurrent callers get unique paths."""
    reserved: set[str] = set()
    results: list[str] = []
    errors: list[Exception] = []

    def worker(idx: int):
        try:
            r = resolve_collision_path("/tmp/dest/shared.txt", reserved_paths=reserved)
            results.append(r)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 50
    assert len(set(results)) == 50
    assert len(reserved) == 50


# ---- R-OPS-4: prune empty destination ----------------------------------------

def test_transfer_prunes_empty_dest_on_total_failure(tmp_path):
    """GIVEN all transfers fail WHEN transfer_path called THEN no empty dir remains."""
    dest = tmp_path / "new_dest_prune"
    assert not dest.exists()

    # Use non-existent sources so each transfer fails (copy needs source)
    reserved: set[str] = set()
    for i in range(3):
        fake_src = str(tmp_path / f"nonexistent_{i}.txt")
        result = transfer_path(fake_src, str(dest), "copy", dry_run=False, reserved_paths=reserved)
        assert not result.success

    # After total failure the destination dir must not remain as empty folder
    assert not dest.exists(), "empty destination dir should be pruned when all transfers fail"


def test_transfer_keeps_dest_when_one_succeeds(tmp_path):
    """When at least one transfer succeeds the destination dir must remain."""
    dest = tmp_path / "dest_keep"
    src_ok = tmp_path / "ok.txt"
    src_ok.write_text("hello")

    # First transfer succeeds
    r1 = transfer_path(str(src_ok), str(dest), "copy", dry_run=False, reserved_paths=set())
    assert r1.success
    assert dest.exists()
    assert (dest / "ok.txt").exists() or os.path.exists(r1.destination_path)

    # Second transfer fails but dest must stay because it now has content
    fake_src = str(tmp_path / "missing.txt")
    r2 = transfer_path(fake_src, str(dest), "copy", dry_run=False, reserved_paths=set())
    assert not r2.success
    assert dest.exists()


def test_transfer_dry_run_does_not_create_dir(tmp_path):
    dest = tmp_path / "dry_dest"
    src = tmp_path / "src.txt"
    src.write_text("x")
    result = transfer_path(str(src), str(dest), "copy", dry_run=True)
    assert result.success
    assert not dest.exists()


# ---- R-OPS-6 / R-OPS-3: case-only rename on case-insensitive FS --------------

def test_case_only_rename_on_case_insensitive_fs(tmp_path, monkeypatch):
    """GIVEN FOO.txt → foo.txt on case-insensitive FS THEN result is foo.txt not foo_1.txt."""
    src = tmp_path / "FOO.txt"
    src.write_text("hello")

    # Simulate case-insensitive filesystem: normcase lowercases, exists is case-insensitive
    monkeypatch.setattr(os.path, "normcase", lambda p: p.lower() if isinstance(p, str) else p)

    orig_exists = os.path.exists

    def fake_exists(p):
        # Case-insensitive existence: compare lower
        try:
            if os.path.normcase(os.path.abspath(p)) == os.path.normcase(str(src)):
                return True
            # Also handle the candidate foo.txt mapping to same file
            if os.path.normcase(p) == os.path.normcase(str(tmp_path / "foo.txt")):
                # On case-insensitive FS the file FOO.txt makes foo.txt appear to exist
                return True
        except Exception:
            pass
        return orig_exists(p)

    monkeypatch.setattr(os.path, "exists", fake_exists)

    reserved: set[str] = set()
    candidate = str(tmp_path / "foo.txt")
    result = resolve_collision_path(candidate, reserved_paths=reserved, current_path=str(src))

    assert os.path.basename(result) == "foo.txt", f"expected foo.txt, got {result}"
    assert result == normalize_path(candidate)


def test_rename_path_case_only_via_resolve(tmp_path, monkeypatch):
    """rename_path FOO.txt -> foo.txt should not add _1 suffix on case-insensitive FS."""
    src = tmp_path / "FOO.txt"
    src.write_text("data")
    monkeypatch.setattr(os.path, "normcase", lambda p: p.lower() if isinstance(p, str) else p)
    orig_exists = os.path.exists

    def fake_exists(p):
        if os.path.normcase(p) == os.path.normcase(str(src)):
            return True
        if os.path.normcase(p) == os.path.normcase(str(tmp_path / "foo.txt")):
            return True
        return orig_exists(p)

    monkeypatch.setattr(os.path, "exists", fake_exists)

    result = rename_path(str(src), "foo.txt", dry_run=True, reserved_paths=set())
    assert result is not None
    assert os.path.basename(result.destination_path) == "foo.txt"


def test_reserved_case_insensitive_collision(tmp_path, monkeypatch):
    """Two different sources colliding to same normcase name should get suffix."""
    monkeypatch.setattr(os.path, "normcase", lambda p: p.lower() if isinstance(p, str) else p)
    # No real files need to exist; reserved set drives collision
    reserved: set[str] = set()
    # First file reserves Foo.txt
    r1 = resolve_collision_path(str(tmp_path / "Foo.txt"), reserved_paths=reserved)
    assert os.path.basename(r1) == "Foo.txt"
    # Second file wants foo.txt (same normcase) -> must collide to foo_1.txt
    r2 = resolve_collision_path(str(tmp_path / "foo.txt"), reserved_paths=reserved)
    assert os.path.basename(r2) == "foo_1.txt"
