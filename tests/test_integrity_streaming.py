import hashlib
import json
import os
import threading
import time
from pathlib import Path

import pytest

from dataforge.modules.integrity import IntegrityMonitor


def _make_files(base: Path, mapping: dict[str, str]):
    for rel, content in mapping.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def test_create_and_verify_clean(tmp_path):
    _make_files(tmp_path, {"a.txt": "hello", "b.txt": "world"})
    snap = tmp_path / "snap.json"
    report = IntegrityMonitor.create_snapshot(str(tmp_path), str(snap))
    assert snap.exists()
    assert report["saved"] == 2
    assert report["scanned"] == 2
    verify = IntegrityMonitor.verify_snapshot(str(tmp_path), str(snap))
    assert verify["is_clean"] is True
    assert verify["issue_count"] == 0
    assert verify["cancelled"] is False


def test_snapshot_json_shape_atomic(tmp_path):
    _make_files(tmp_path, {"a.txt": "data"})
    snap = tmp_path / "snap.json"
    IntegrityMonitor.create_snapshot(str(tmp_path), str(snap))
    raw = json.loads(snap.read_text())
    assert "algorithm" in raw
    assert "created_at" in raw
    assert "files" in raw
    assert isinstance(raw["files"], dict)
    # indent 4 check not strict, but json load ok
    assert raw["algorithm"] in ("sha256", "md5", "sha1", "sha512", "blake2b")


def test_legacy_flat_md5_readable(tmp_path):
    _make_files(tmp_path, {"a.txt": "legacy", "b.txt": "data"})
    # create flat md5 legacy snapshot
    flat = {}
    for rel in ["a.txt", "b.txt"]:
        flat[rel] = hashlib.md5((tmp_path / rel).read_bytes()).hexdigest()
    snap = tmp_path / "legacy.json"
    snap.write_text(json.dumps(flat))
    report = IntegrityMonitor.verify_snapshot(str(tmp_path), str(snap))
    assert report["is_clean"] is True
    assert report["snapshot_entries"] == 2
    assert report["cancelled"] is False


def test_legacy_detects_modification(tmp_path):
    _make_files(tmp_path, {"a.txt": "orig"})
    flat = {"a.txt": hashlib.md5(b"orig").hexdigest()}
    snap = tmp_path / "legacy.json"
    snap.write_text(json.dumps(flat))
    (tmp_path / "a.txt").write_text("modified")
    report = IntegrityMonitor.verify_snapshot(str(tmp_path), str(snap))
    assert any("MODIFIED" in d for d in report["discrepancies"])


def test_atomic_no_partial_on_precancel(tmp_path):
    _make_files(tmp_path, {"a.txt": "hello", "b.txt": "world"})
    snap = tmp_path / "snap.json"
    token = threading.Event()
    token.set()
    with pytest.raises(InterruptedError):
        IntegrityMonitor.create_snapshot(str(tmp_path), str(snap), cancel_token=token)
    # No partial file should exist
    assert not snap.exists()
    # tmp file should be cleaned (now snap.json.tmp)
    leftovers = list(tmp_path.glob("*.tmp"))
    assert not any("snap" in p.name for p in leftovers)


def test_atomic_no_partial_on_mid_cancel(tmp_path, monkeypatch):
    # Create many files to allow mid-cancel
    _make_files(tmp_path, {f"f{i}.txt": f"content {i}" for i in range(20)})
    snap = tmp_path / "snap.json"
    token = threading.Event()

    # Monkeypatch _hash_worker to set token after a few calls
    import dataforge.modules.integrity as mod

    orig_worker = mod._hash_worker
    call_count = {"n": 0}

    def slow_worker(entry_path, algo, cancel_token):
        call_count["n"] += 1
        if call_count["n"] == 3:
            token.set()
        # small delay to allow cancel check
        time.sleep(0.02)
        return orig_worker(entry_path, algo, cancel_token)

    monkeypatch.setattr(mod, "_hash_worker", slow_worker)
    with pytest.raises(InterruptedError):
        IntegrityMonitor.create_snapshot(str(tmp_path), str(snap), cancel_token=token)
    assert not snap.exists()
    leftovers = list(tmp_path.glob(".tmp*")) + list(tmp_path.glob("*.tmp"))
    # Filter only snapshot tmp leftovers
    leftovers = [p for p in leftovers if "snap" in p.name]
    assert leftovers == []


def test_cancel_verify_returns_cancelled_flag(tmp_path, monkeypatch):
    _make_files(tmp_path, {f"f{i}.txt": f"content {i}" for i in range(30)})
    snap = tmp_path / "snap.json"
    IntegrityMonitor.create_snapshot(str(tmp_path), str(snap))

    import dataforge.modules.integrity as mod

    orig_worker = mod._hash_worker

    def slow_worker(entry_path, algo, cancel_token):
        time.sleep(0.06)
        return orig_worker(entry_path, algo, cancel_token)

    monkeypatch.setattr(mod, "_hash_worker", slow_worker)
    token = threading.Event()

    # Start verify in thread and cancel shortly after
    result_holder = {}

    def run_verify():
        result_holder["report"] = IntegrityMonitor.verify_snapshot(
            str(tmp_path), str(snap), cancel_token=token
        )

    t = threading.Thread(target=run_verify)
    t.start()
    time.sleep(0.02)
    token.set()
    t.join(timeout=2)
    assert not t.is_alive(), "verify did not return promptly on cancel"
    report = result_holder.get("report")
    assert report is not None
    assert report.get("cancelled") is True


def test_cancel_verify_precancel_returns_cancelled(tmp_path):
    _make_files(tmp_path, {"a.txt": "hello"})
    snap = tmp_path / "snap.json"
    IntegrityMonitor.create_snapshot(str(tmp_path), str(snap))
    token = threading.Event()
    token.set()
    report = IntegrityMonitor.verify_snapshot(str(tmp_path), str(snap), cancel_token=token)
    # Should return promptly with cancelled True (or at least not hang)
    assert report.get("cancelled") is True


def test_streaming_code_uses_queue_threadpool_atomic():
    src = Path("dataforge/modules/integrity.py").read_text()
    assert "queue.Queue" in src, "must use queue.Queue for streaming"
    assert "ThreadPoolExecutor" in src, "must use ThreadPoolExecutor"
    assert "os.replace" in src, "must use atomic tmp+os.replace"
    assert "set_hash_many" in src or "executemany" in src, "must batch cache writes"
    assert "min(32" in src, "must use min(32,cpu*4) workers"
    assert "list(scan_directory" not in src, "must not materialize list(scan_directory)"


def test_executemany_cache_write_called(tmp_path, monkeypatch):
    _make_files(tmp_path, {f"f{i}.txt": f"c{i}" for i in range(5)})
    snap = tmp_path / "snap.json"
    from dataforge.core.cache import file_cache

    calls = []

    orig = file_cache.set_hash_many

    def spy(rows):
        calls.append(list(rows))
        return orig(rows)

    monkeypatch.setattr(file_cache, "set_hash_many", spy)
    IntegrityMonitor.create_snapshot(str(tmp_path), str(snap))
    # At least one batch write should have happened
    assert len(calls) >= 1
    # Verify snapshot still valid
    report = IntegrityMonitor.verify_snapshot(str(tmp_path), str(snap))
    assert report["is_clean"]


def test_verify_detects_new_deleted_modified(tmp_path):
    _make_files(tmp_path, {"a.txt": "data", "b.txt": "data2"})
    snap = tmp_path / "snap.json"
    IntegrityMonitor.create_snapshot(str(tmp_path), str(snap))
    # new
    Path(tmp_path / "new.txt").write_text("new")
    # modified
    Path(tmp_path / "a.txt").write_text("changed")
    # deleted
    os.unlink(tmp_path / "b.txt")
    report = IntegrityMonitor.verify_snapshot(str(tmp_path), str(snap))
    dis = report["discrepancies"]
    assert any(d.startswith("NEW:") and "new.txt" in d for d in dis)
    assert any(d.startswith("MODIFIED:") and "a.txt" in d for d in dis)
    assert any(d.startswith("DELETED:") and "b.txt" in d for d in dis)


def test_single_file_snapshot(tmp_path):
    target = tmp_path / "tracked.txt"
    target.write_text("original")
    snap = tmp_path / "snap.json"
    r = IntegrityMonitor.create_snapshot(str(target), str(snap))
    assert r["saved"] == 1
    report = IntegrityMonitor.verify_snapshot(str(target), str(snap))
    assert report["is_clean"]
    assert report["cancelled"] is False


def test_truncated_snapshot_error(tmp_path):
    _make_files(tmp_path, {"a.txt": "hello"})
    snap = tmp_path / "snap.json"
    snap.write_text("{ truncated json")
    report = IntegrityMonitor.verify_snapshot(str(tmp_path), str(snap))
    assert any("ERROR" in d for d in report["discrepancies"])


def test_progress_callback_invoked(tmp_path):
    _make_files(tmp_path, {"a.txt": "hello", "b.txt": "world"})
    snap = tmp_path / "snap.json"
    calls = []

    def cb(done, total, msg):
        calls.append((done, total, msg))

    IntegrityMonitor.create_snapshot(str(tmp_path), str(snap), progress_callback=cb)
    assert len(calls) >= 2

    calls_v = []

    def cb2(done, total, msg):
        calls_v.append((done, total, msg))

    IntegrityMonitor.verify_snapshot(str(tmp_path), str(snap), progress_callback=cb2)
    assert len(calls_v) >= 1
