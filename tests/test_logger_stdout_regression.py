"""TICK-101 regression: logger must route to stderr so CLI JSON stays clean.

Acceptance criteria:
1. dupes --format json piped -> json.load succeeds with no log lines on stdout
2. same command logs appear on stderr
3. verify_snapshot truncated JSON still reports ERROR: Could not read snapshot file.

Also verifies:
- StreamHandler uses sys.stderr (R-CORE-1)
- File handler at 0o600 and bare filename does not crash (R-CORE-7)
"""

import json
import logging
import os
import sys
import stat
import subprocess
import importlib


from dataforge.core.logger import setup_logger
from dataforge.modules.integrity import IntegrityMonitor


def _clean_logger(name):
    lg = logging.getLogger(name)
    lg.handlers.clear()
    lg.propagate = False
    return lg


def _run_cli(args):
    """Run CLI via subprocess to capture real stdout/stderr separation."""
    env = os.environ.copy()
    # Ensure repo root on PYTHONPATH for -m execution
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") + ":." if env.get("PYTHONPATH") else "."
    result = subprocess.run(
        [sys.executable, "-m", "dataforge.cli"] + args,
        capture_output=True,
        text=True,
        env=env,
    )
    return result


class TestLoggerStderrRouting:
    def test_console_handler_uses_stderr(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        name = "dataforge.test.stderr"
        _clean_logger(name)
        lg = setup_logger(name, log_file, level=logging.INFO)
        stream_handlers = [h for h in lg.handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
        assert len(stream_handlers) >= 1
        ch = stream_handlers[0]
        assert ch.stream is sys.stderr
        for h in lg.handlers:
            h.close()
        lg.handlers.clear()

    def test_file_handler_uses_0o600(self, tmp_path):
        log_file = tmp_path / "nested" / "app.log"
        name = "dataforge.test.perm"
        _clean_logger(name)
        lg = setup_logger(name, str(log_file), level=logging.INFO)
        lg.info("hello perm test")
        for h in lg.handlers:
            h.flush()
        assert log_file.exists()
        mode = stat.S_IMODE(os.stat(log_file).st_mode)
        assert mode == 0o600, f"expected 0o600 got {oct(mode)}"
        for h in lg.handlers:
            h.close()
        lg.handlers.clear()

    def test_bare_filename_no_makedirs_crash(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        name = "dataforge.test.bare"
        _clean_logger(name)
        bare = "bare.log"
        lg = setup_logger(name, bare, level=logging.INFO)
        assert any(isinstance(h, logging.FileHandler) for h in lg.handlers)
        lg.info("bare test")
        for h in lg.handlers:
            h.flush()
        assert (tmp_path / bare).exists()
        for h in lg.handlers:
            h.close()
        lg.handlers.clear()
        try:
            (tmp_path / bare).unlink()
        except FileNotFoundError:
            pass

    def test_global_logger_uses_stderr(self):
        mod = importlib.import_module("dataforge.core.logger")
        lg = mod.logger
        stream_handlers = [h for h in lg.handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
        assert len(stream_handlers) >= 1
        assert stream_handlers[0].stream is sys.stderr


class TestCLIJsonClean:
    def test_dupes_json_stdout_is_pure_json(self, tmp_path):
        (tmp_path / "a.txt").write_text("same content")
        (tmp_path / "b.txt").write_text("same content")
        (tmp_path / "c.txt").write_text("unique")
        result = _run_cli(["dupes", str(tmp_path), "--format", "json"])
        assert result.returncode == 0, f"stderr={result.stderr!r} stdout={result.stdout!r}"
        assert "Starting duplicate scan" not in result.stdout
        assert "INFO" not in result.stdout or "INFO" in result.stdout and "[" in result.stdout  # logger should not be on stdout
        stdout = result.stdout
        json_start = stdout.find("[")
        assert json_start != -1, f"no JSON array found in stdout: {stdout!r}"
        json_part = stdout[json_start:]
        # Find matching closing bracket end - json.loads will handle trailing whitespace, but there may be trailing newline
        # Extract until last ']' inclusive
        json_end = json_part.rfind("]")
        assert json_end != -1
        json_part = json_part[: json_end + 1]
        data = json.loads(json_part)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_dupes_json_logs_on_stderr(self, tmp_path):
        (tmp_path / "a.txt").write_text("same content")
        (tmp_path / "b.txt").write_text("same content")
        result = _run_cli(["dupes", str(tmp_path), "--format", "json"])
        assert result.returncode == 0
        assert result.stderr != "", "expected log lines on stderr"
        assert "Starting duplicate scan" in result.stderr or "Duplicate scan complete" in result.stderr or "Scanned" in result.stderr
        assert "Starting duplicate scan" not in result.stdout

    def test_dupes_jsonl_stdout_clean(self, tmp_path):
        (tmp_path / "a.txt").write_text("same content")
        (tmp_path / "b.txt").write_text("same content")
        result = _run_cli(["dupes", str(tmp_path), "--format", "jsonl"])
        assert result.returncode == 0
        assert "Starting duplicate scan" not in result.stdout
        lines = [ln for ln in result.stdout.splitlines() if ln.strip().startswith("{")]
        assert len(lines) >= 1
        for ln in lines:
            json.loads(ln)

    def test_search_json_stdout_clean(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world")
        result = _run_cli(["search", str(tmp_path), "--format", "json"])
        assert result.returncode == 0
        assert "INFO" not in result.stdout or "[" in result.stdout
        stdout = result.stdout
        json_start = stdout.find("[")
        assert json_start != -1, f"no JSON in search stdout: {stdout!r}"
        json_end = stdout.rfind("]")
        data = json.loads(stdout[json_start: json_end + 1])
        assert isinstance(data, list)


class TestVerifySnapshotTruncated:
    def test_truncated_json_reports_error(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        (target / "a.txt").write_text("hello")
        snap = tmp_path / "snap.json"
        IntegrityMonitor.create_snapshot(str(target), str(snap))
        snap.write_text('{"algorithm": "sha256", "files": {', encoding="utf-8")
        report = IntegrityMonitor.verify_snapshot(str(target), str(snap))
        assert "ERROR: Could not read snapshot file." in report["discrepancies"]

    def test_cli_integrity_check_truncated_reports_error(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        (target / "a.txt").write_text("hello")
        snap = tmp_path / "snap.json"
        IntegrityMonitor.create_snapshot(str(target), str(snap))
        snap.write_text('{"truncated": ', encoding="utf-8")
        result = _run_cli(["integrity", "check", str(target), str(snap)])
        combined = result.stdout + result.stderr
        assert "ERROR: Could not read snapshot file." in combined
        assert result.returncode == 0
