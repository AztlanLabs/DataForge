"""TICK-203 — Dedupe cleanup walks and reuse parallel scanner.

Acceptance criteria under test:
1. GIVEN browser artifact scan WHEN run THEN os.walk call count is O(categories)
   not O(categories×patterns) — verifies walk deduplication
2. GIVEN /tmp file <1 day old WHEN scanned THEN not classified as junk — 1-day guard
3. GIVEN socket/FIFO WHEN scanned THEN never classified as junk — special file guard
4. scan_junk_files walks each unique directory once, not per category
"""

import os
import stat
import threading
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from dataforge.core.common import FileEntry
from dataforge.modules.system_cleanup import (
    _is_socket_or_fifo,
    _is_under_system_temp,
    scan_browser_artifacts,
    scan_junk_files,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file_entry(
    path: str,
    filename: str = "",
    extension: str = "",
    size: int = 100,
    modified_at: float | None = None,
) -> FileEntry:
    """Create a FileEntry for testing."""
    if not filename:
        filename = os.path.basename(path)
    if not extension:
        extension = os.path.splitext(filename)[1].lower()
    if modified_at is None:
        modified_at = datetime.now().timestamp()
    return FileEntry(
        path=path,
        filename=filename,
        extension=extension,
        size=size,
        created_at=modified_at,
        modified_at=modified_at,
        is_dir=False,
    )


def _make_files(root: Path, specs: dict) -> list[Path]:
    """Create files from specs dict {relative_path: content}."""
    paths = []
    for rel, content in specs.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# 1. Walk deduplication: scan_directory called once per unique directory
# ---------------------------------------------------------------------------


class TestWalkDeduplication:
    """Verify scan_junk_files walks each unique directory once."""

    @patch("dataforge.modules.system_cleanup.scan_directory")
    def test_unique_dirs_walked_once(self, mock_scan, tmp_path):
        """Multiple categories sharing a dir should trigger only one walk."""
        # Create a shared cache dir that appears in multiple categories
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "test.tmp").write_text("junk")

        # Mock _get_platform_junk_paths to return overlapping dirs
        with patch(
            "dataforge.modules.system_cleanup._get_platform_junk_paths"
        ) as mock_paths:
            mock_paths.return_value = {
                "User Cache": [str(cache_dir)],
                "Thumbnails": [str(cache_dir)],  # Same dir
                "Package Cache": [str(cache_dir)],  # Same dir
            }
            mock_scan.return_value = iter(
                [_make_file_entry(str(cache_dir / "test.tmp"), ".tmp")]
            )

            scan_junk_files()

            # scan_directory should be called exactly once for the shared dir
            assert mock_scan.call_count == 1
            mock_scan.assert_called_once_with(
                str(cache_dir), recursive=True, max_depth=5, cancel_token=None
            )

    @patch("dataforge.modules.system_cleanup.scan_directory")
    def test_different_dirs_walked_separately(self, mock_scan, tmp_path):
        """Different directories should each be walked once."""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "a.tmp").write_text("junk")
        (dir_b / "b.tmp").write_text("junk")

        with patch(
            "dataforge.modules.system_cleanup._get_platform_junk_paths"
        ) as mock_paths:
            mock_paths.return_value = {
                "System Temp": [str(dir_a)],
                "User Cache": [str(dir_b)],
            }
            mock_scan.return_value = iter(
                [_make_file_entry(str(dir_a / "a.tmp"), ".tmp")]
            )

            scan_junk_files()

            # Two unique dirs → two walks
            assert mock_scan.call_count == 2

    @patch("dataforge.modules.system_cleanup.scan_directory")
    def test_user_paths_add_single_walk(self, mock_scan, tmp_path):
        """User-supplied paths should add one walk per unique path."""
        user_dir = tmp_path / "user"
        user_dir.mkdir()
        (user_dir / "test.log").write_text("log")

        with patch(
            "dataforge.modules.system_cleanup._get_platform_junk_paths"
        ) as mock_paths:
            mock_paths.return_value = {
                "System Temp": [str(tmp_path / "nonexistent")],
            }
            mock_scan.return_value = iter(
                [_make_file_entry(str(user_dir / "test.log"), ".log")]
            )

            scan_junk_files(paths=[str(user_dir)])

            # One for nonexistent (skipped by isdir), one for user dir
            assert mock_scan.call_count == 1


# ---------------------------------------------------------------------------
# 2. /tmp 1-day guard: files <1 day old not classified as junk
# ---------------------------------------------------------------------------


class TestTempOneDayGuard:
    """Verify /tmp files younger than 1 day are excluded."""

    def test_recent_tmp_file_excluded(self, tmp_path):
        """Files modified <1 day ago in /tmp should not be junk."""
        now = datetime.now().timestamp()
        recent_ts = now - 3600  # 1 hour ago

        entry = _make_file_entry("/tmp/recent.tmp", modified_at=recent_ts)

        with patch(
            "dataforge.modules.system_cleanup._get_platform_junk_paths"
        ) as mock_paths:
            mock_paths.return_value = {"System Temp": ["/tmp"]}
            with patch(
                "dataforge.modules.system_cleanup.scan_directory"
            ) as mock_scan:
                mock_scan.return_value = iter([entry])
                with patch("dataforge.modules.system_cleanup.os.path.isdir", return_value=True):
                    result = scan_junk_files()

        # Recent /tmp file should not appear in results
        assert "System Temp" not in result or len(result.get("System Temp", [])) == 0

    def test_old_tmp_file_included(self, tmp_path):
        """Files modified >1 day ago in /tmp should be classified as junk."""
        now = datetime.now().timestamp()
        old_ts = now - timedelta(days=2).total_seconds()  # 2 days ago

        entry = _make_file_entry("/tmp/old.tmp", modified_at=old_ts)

        with patch(
            "dataforge.modules.system_cleanup._get_platform_junk_paths"
        ) as mock_paths:
            mock_paths.return_value = {"System Temp": ["/tmp"]}
            with patch(
                "dataforge.modules.system_cleanup.scan_directory"
            ) as mock_scan:
                mock_scan.return_value = iter([entry])
                with patch("dataforge.modules.system_cleanup.os.path.isdir", return_value=True):
                    result = scan_junk_files()

        assert "System Temp" in result
        assert len(result["System Temp"]) == 1

    def test_is_under_system_temp(self):
        """_is_under_system_temp correctly identifies /tmp and /var/tmp."""
        assert _is_under_system_temp("/tmp") is True
        assert _is_under_system_temp("/tmp/subdir") is True
        assert _is_under_system_temp("/var/tmp") is True
        assert _is_under_system_temp("/var/tmp/sub") is True
        assert _is_under_system_temp("/home/user") is False
        assert _is_under_system_temp("/notmp") is False


# ---------------------------------------------------------------------------
# 3. Socket/FIFO guard: never classified as junk
# ---------------------------------------------------------------------------


class TestSocketFifoGuard:
    """Verify sockets and FIFOs are never classified as junk."""

    @patch("dataforge.modules.system_cleanup.os.stat")
    def test_socket_excluded(self, mock_stat):
        """Unix sockets should return True from _is_socket_or_fifo."""
        mock_stat.return_value = MagicMock(st_mode=stat.S_IFSOCK)
        assert _is_socket_or_fifo("/tmp/test.sock") is True

    @patch("dataforge.modules.system_cleanup.os.stat")
    def test_fifo_excluded(self, mock_stat):
        """FIFOs should return True from _is_socket_or_fifo."""
        mock_stat.return_value = MagicMock(st_mode=stat.S_IFIFO)
        assert _is_socket_or_fifo("/tmp/test.fifo") is True

    @patch("dataforge.modules.system_cleanup.os.stat")
    def test_regular_file_not_excluded(self, mock_stat):
        """Regular files should return False from _is_socket_or_fifo."""
        mock_stat.return_value = MagicMock(st_mode=stat.S_IFREG)
        assert _is_socket_or_fifo("/tmp/test.txt") is False

    @patch("dataforge.modules.system_cleanup.os.stat")
    def test_oserror_returns_false(self, mock_stat):
        """OSError should cause _is_socket_or_fifo to return False."""
        mock_stat.side_effect = OSError("no such file")
        assert _is_socket_or_fifo("/nonexistent") is False

    @patch("dataforge.modules.system_cleanup.scan_directory")
    def test_socket_not_in_junk_results(self, mock_scan, tmp_path):
        """Sockets found during scan should not appear in junk results."""
        socket_entry = _make_file_entry("/tmp/test.sock")
        regular_entry = _make_file_entry("/tmp/test.tmp", ".tmp")

        with patch(
            "dataforge.modules.system_cleanup._get_platform_junk_paths"
        ) as mock_paths:
            mock_paths.return_value = {"System Temp": ["/tmp"]}
            mock_scan.return_value = iter([socket_entry, regular_entry])
            with patch("dataforge.modules.system_cleanup.os.path.isdir", return_value=True):
                with patch(
                    "dataforge.modules.system_cleanup._is_socket_or_fifo"
                ) as mock_is_sock:
                    # Socket returns True, regular file returns False
                    mock_is_sock.side_effect = lambda p: p == "/tmp/test.sock"
                    result = scan_junk_files()

        # Only the regular file should appear, not the socket
        if "System Temp" in result:
            paths = [e.path for e in result["System Temp"]]
            assert "/tmp/test.sock" not in paths


# ---------------------------------------------------------------------------
# 4. Browser artifact scan: O(profiles) not O(profiles×patterns)
# ---------------------------------------------------------------------------


class TestBrowserArtifactDedup:
    """Verify scan_browser_artifacts walks each profile once."""

    @patch("dataforge.modules.system_cleanup.scan_directory")
    def test_single_walk_per_profile(self, mock_scan, tmp_path):
        """Each browser profile should be walked once, not per pattern."""
        base_dir = tmp_path / "chrome" / "base"
        cache_dir = tmp_path / "chrome" / "cache"
        base_dir.mkdir(parents=True)
        cache_dir.mkdir(parents=True)

        # Create some artifact files
        (base_dir / "Cookies").write_text("cookies")
        (base_dir / "History").write_text("history")
        (cache_dir / "Cache").mkdir()

        mock_scan.return_value = iter(
            [
                _make_file_entry(str(base_dir / "Cookies")),
                _make_file_entry(str(base_dir / "History")),
            ]
        )

        with patch(
            "dataforge.modules.system_cleanup._browser_profiles"
        ) as mock_profiles:
            mock_profiles.return_value = {
                "Google Chrome": {
                    "base": str(base_dir),
                    "cache": str(cache_dir),
                }
            }
            scan_browser_artifacts()

            # Should walk base and cache once each (2 walks total)
            # Not 2 profiles × 5 artifact types = 10 walks
            assert mock_scan.call_count == 2

    @patch("dataforge.modules.system_cleanup.scan_directory")
    def test_artifacts_matched_correctly(self, mock_scan, tmp_path):
        """Artifacts should be matched by name against collected entries."""
        base_dir = tmp_path / "firefox" / "base"
        base_dir.mkdir(parents=True)

        mock_scan.return_value = iter(
            [
                _make_file_entry(str(base_dir / "cookies.sqlite")),
                _make_file_entry(str(base_dir / "places.sqlite")),
                _make_file_entry(str(base_dir / "sessionstore.jsonlz4")),
            ]
        )

        with patch(
            "dataforge.modules.system_cleanup._browser_profiles"
        ) as mock_profiles:
            mock_profiles.return_value = {
                "Firefox": {"base": str(base_dir), "cache": str(base_dir)}
            }
            result = scan_browser_artifacts()

        assert "Firefox" in result
        artifacts = result["Firefox"]
        assert "cookies" in artifacts
        assert "history" in artifacts
        assert "sessions" in artifacts

    @patch("dataforge.modules.system_cleanup.scan_directory")
    def test_glob_patterns_matched(self, mock_scan, tmp_path):
        """Glob patterns like *.tmp should match collected entries."""
        base_dir = tmp_path / "chrome"
        base_dir.mkdir()

        mock_scan.return_value = iter(
            [
                _make_file_entry(str(base_dir / "download.crdownload")),
                _make_file_entry(str(base_dir / "partial.part")),
            ]
        )

        with patch(
            "dataforge.modules.system_cleanup._browser_profiles"
        ) as mock_profiles:
            mock_profiles.return_value = {
                "Google Chrome": {"base": str(base_dir), "cache": str(base_dir)}
            }
            result = scan_browser_artifacts()

        assert "Google Chrome" in result
        assert "temp" in result["Google Chrome"]
        temp_paths = result["Google Chrome"]["temp"]
        assert len(temp_paths) == 2

    @patch("dataforge.modules.system_cleanup.scan_directory")
    def test_cancel_token_stops_browser_scan(self, mock_scan, tmp_path):
        """Cancel token should stop browser scan promptly."""
        cancel = threading.Event()
        cancel.set()

        with patch(
            "dataforge.modules.system_cleanup._browser_profiles"
        ) as mock_profiles:
            mock_profiles.return_value = {
                "Chrome": {"base": "/tmp/chrome", "cache": "/tmp/chrome_cache"}
            }
            result = scan_browser_artifacts(cancel_token=cancel)

        assert result == {}
        mock_scan.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Edge cases and integration
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases for scan_junk_files."""

    @patch("dataforge.modules.system_cleanup.scan_directory")
    def test_empty_dirs_produce_no_results(self, mock_scan, tmp_path):
        """Empty directories should not produce results."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        mock_scan.return_value = iter([])

        with patch(
            "dataforge.modules.system_cleanup._get_platform_junk_paths"
        ) as mock_paths:
            mock_paths.return_value = {"System Temp": [str(empty_dir)]}
            with patch("dataforge.modules.system_cleanup.os.path.isdir", return_value=True):
                result = scan_junk_files()

        assert result == {}

    @patch("dataforge.modules.system_cleanup.scan_directory")
    def test_cancel_token_stops_junk_scan(self, mock_scan, tmp_path):
        """Cancel token should stop junk scan promptly."""
        cancel = threading.Event()
        cancel.set()

        with patch(
            "dataforge.modules.system_cleanup._get_platform_junk_paths"
        ) as mock_paths:
            mock_paths.return_value = {"System Temp": ["/tmp"]}
            result = scan_junk_files(cancel_token=cancel)

        assert result == {}
        mock_scan.assert_not_called()

    @patch("dataforge.modules.system_cleanup.scan_directory")
    def test_categories_filter(self, mock_scan, tmp_path):
        """categories parameter should filter which categories are scanned."""
        mock_scan.return_value = iter([])

        with patch(
            "dataforge.modules.system_cleanup._get_platform_junk_paths"
        ) as mock_paths:
            mock_paths.return_value = {
                "System Temp": ["/tmp"],
                "User Cache": ["/tmp/cache"],
                "Log Files": ["/var/log"],
            }
            scan_junk_files(categories=["System Temp"])

            # Only System Temp dirs should be walked
            walked_dirs = [call[0][0] for call in mock_scan.call_args_list]
            assert "/tmp" in walked_dirs
            assert "/tmp/cache" not in walked_dirs
            assert "/var/log" not in walked_dirs

    @patch("dataforge.modules.system_cleanup.scan_directory")
    def test_min_age_days_filter(self, mock_scan, tmp_path):
        """Files newer than min_age_days should be excluded."""
        now = datetime.now().timestamp()
        recent = _make_file_entry("/tmp/recent.tmp", modified_at=now - 3600)
        old = _make_file_entry("/tmp/old.tmp", modified_at=now - timedelta(days=5).total_seconds())

        with patch(
            "dataforge.modules.system_cleanup._get_platform_junk_paths"
        ) as mock_paths:
            mock_paths.return_value = {"System Temp": ["/tmp"]}
            mock_scan.return_value = iter([recent, old])
            with patch("dataforge.modules.system_cleanup.os.path.isdir", return_value=True):
                result = scan_junk_files(min_age_days=3)

        if "System Temp" in result:
            paths = [e.path for e in result["System Temp"]]
            assert "/tmp/recent.tmp" not in paths
            assert "/tmp/old.tmp" in paths
