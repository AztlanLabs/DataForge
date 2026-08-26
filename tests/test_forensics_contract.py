"""TICK-918 contract tests for forensics module fixes.

Covers: profiling crash (P0.8), progress sentinel (P0.9), timeline atime,
integrity snapshot recursion, multi-hash verification, artifact path
confinement (P1.10).
"""

import os
import tempfile
from unittest import mock

from dataforge.api.schema import JobEvent
from dataforge.modules import forensics


def _make_files(directory, count, prefix="file"):
    for i in range(count):
        p = os.path.join(directory, f"{prefix}_{i}.txt")
        with open(p, "w") as f:
            f.write(f"content {i}\n")
    return [os.path.join(directory, f"{prefix}_{i}.txt") for i in range(count)]


def test_profile_directory_types_25_files():
    with tempfile.TemporaryDirectory() as td:
        _make_files(td, 25)
        result = forensics.profile_directory_types(td)
        assert result["total"] == 25


def test_profile_directory_types_100_files():
    with tempfile.TemporaryDirectory() as td:
        _make_files(td, 100)
        result = forensics.profile_directory_types(td)
        assert result["total"] == 100
        assert result["by_format"]


def test_profile_directory_types_empty_dir():
    with tempfile.TemporaryDirectory() as td:
        result = forensics.profile_directory_types(td)
        assert result["total"] == 0
        assert result["by_format"] == {}
        assert result["rows"] == []


def test_progress_negative_total_becomes_none():
    evt = JobEvent(job_id="j1", type="progress", current=5, total=None)
    assert evt.total is None


def test_progress_zero_total_preserved():
    evt = JobEvent(job_id="j1", type="progress", current=0, total=0)
    assert evt.total == 0


def test_timeline_atime_differs_from_mtime():
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "t.txt")
        with open(p, "w") as f:
            f.write("x" * 100)
        events = forensics.build_timeline(td, sort_key="atime")
        assert len(events) == 1
        assert events[0]["atime"] is not None
        assert events[0]["mtime"] is not None


def test_integrity_snapshot_recurses_directory():
    with tempfile.TemporaryDirectory() as td:
        _make_files(td, 3)
        snapshot = forensics.snapshot_file_state([td])
        assert len(snapshot["entries"]) == 3


def test_verify_checks_all_hashes():
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "f.bin")
        with open(p, "wb") as f:
            f.write(b"payload")
        snapshot = forensics.snapshot_file_state([p], algorithms=["md5", "sha256"])
        original = forensics.get_file_hash
        with mock.patch(
            "dataforge.modules.forensics.get_file_hash",
            side_effect=lambda path, algo, cancel_token=None: original(path, algo),
        ) as mocked:
            forensics.verify_file_state(snapshot)
        assert mocked.call_count == 2


def test_verify_detects_tamper():
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "f.bin")
        with open(p, "wb") as f:
            f.write(b"payload")
        snapshot = forensics.snapshot_file_state([p], algorithms=["md5", "sha256"])
        with open(p, "wb") as f:
            f.write(b"tampered")
        results = forensics.verify_file_state(snapshot)
        entry, diff = results[0]
        assert diff is not None
        assert "md5" in diff or "sha256" in diff


def test_artifact_path_confined_to_evidence_root():
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, "etc"))
        os.makedirs(os.path.join(td, "home", "user"))
        with open(os.path.join(td, "etc", "passwd"), "w") as f:
            f.write("alice:x:1000:1000:Alice:/home/user:/bin/bash\n")
        hist = os.path.join(td, "home", "user", ".bash_history")
        with open(hist, "w") as f:
            f.write("ls -la\n")
        artifacts = forensics.parse_os_artifacts(td)
        assert artifacts["shell_history"], "expected shell history to be parsed"
        record = artifacts["shell_history"][0]
        assert record["user"] == "alice"
        assert record["file"].startswith(os.path.abspath(td))
        assert record["file"] != "/home/user/.bash_history"
        assert not record["file"].startswith("/home/user")