"""
Tests for TICK-504: Fix tz-naive timestamps in non-forensic modules (F9)

Acceptance criteria:
- GIVEN system_cleanup.py WHEN timestamp generated THEN UTC-aware
- GIVEN search.py WHEN timestamp generated THEN UTC-aware
- GIVEN recovery.py WHEN timestamp generated THEN UTC-aware
- GIVEN integrity.py WHEN timestamp generated THEN UTC-aware
- GIVEN performance.py WHEN timestamp generated THEN UTC-aware
- GIVEN ui/views/search.py WHEN timestamp generated THEN UTC-aware

All timestamps should use datetime.now(timezone.utc) for consistency.
"""
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch


class TestSourceContainsUTC(unittest.TestCase):
    """Verify source files contain timezone.utc and no naive datetime.now()."""

    def _read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def _assert_utc_and_no_naive(self, path):
        src = self._read(path)
        # Must contain timezone.utc
        self.assertIn("timezone.utc", src, f"{path} must contain timezone.utc")
        # Must not contain naive datetime.now() without args (excluding timezone.utc calls)
        # Find all datetime.now() occurrences and ensure they include timezone.utc
        # Pattern for naive: datetime.now() or datetime.datetime.now() without args
        naive_patterns = [
            r"datetime\.now\(\)",
            r"datetime\.datetime\.now\(\)",
        ]
        for pat in naive_patterns:
            matches = re.findall(pat, src)
            self.assertEqual(matches, [], f"{path} contains naive {pat}: {matches}")

    def test_system_cleanup_utc(self):
        """GIVEN system_cleanup.py WHEN timestamp generated THEN UTC-aware"""
        p = "dataforge/modules/system_cleanup.py"
        src = self._read(p)
        self.assertIn("from datetime import datetime, timedelta, timezone", src)
        self.assertIn("datetime.now(timezone.utc)", src)
        self._assert_utc_and_no_naive(p)
        # Specifically check both cutoff and now_ts are UTC
        self.assertIn("(datetime.now(timezone.utc) - timedelta(days=min_age_days)).timestamp()", src)
        self.assertIn("now_ts = datetime.now(timezone.utc).timestamp()", src)

    def test_search_utc(self):
        """GIVEN search.py WHEN timestamp generated THEN UTC-aware"""
        p = "dataforge/modules/search.py"
        src = self._read(p)
        self.assertIn("from datetime import datetime, timedelta, timezone", src)
        self.assertIn("datetime.now(timezone.utc)", src)
        self._assert_utc_and_no_naive(p)

    def test_recovery_utc(self):
        """GIVEN recovery.py WHEN timestamp generated THEN UTC-aware"""
        p = "dataforge/modules/recovery.py"
        src = self._read(p)
        self.assertIn("from datetime import datetime, timezone", src)
        self.assertIn("datetime.now(timezone.utc).timestamp()", src)
        self.assertIn("datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()", src)
        self._assert_utc_and_no_naive(p)

    def test_integrity_utc(self):
        """GIVEN integrity.py WHEN timestamp generated THEN UTC-aware"""
        p = "dataforge/modules/integrity.py"
        src = self._read(p)
        self.assertIn("datetime.datetime.now(datetime.timezone.utc).isoformat", src)
        self._assert_utc_and_no_naive(p)

    def test_performance_utc(self):
        """GIVEN performance.py WHEN timestamp generated THEN UTC-aware"""
        p = "dataforge/modules/performance.py"
        src = self._read(p)
        self.assertIn("from datetime import datetime, timezone", src)
        self.assertIn("datetime.now(timezone.utc).isoformat()", src)
        self.assertIn("datetime.fromtimestamp(boot_time, tz=timezone.utc).isoformat()", src)
        self._assert_utc_and_no_naive(p)

    def test_search_view_utc(self):
        """GIVEN ui/views/search.py WHEN timestamp generated THEN UTC-aware"""
        p = "dataforge/ui/views/search.py"
        src = self._read(p)
        self.assertIn("datetime.datetime.now(datetime.timezone.utc).strftime", src)
        self._assert_utc_and_no_naive(p)


class TestRuntimeUTCTimestamps(unittest.TestCase):
    """Runtime checks that generated timestamps are UTC-aware (+00:00)."""

    def test_integrity_snapshot_created_at_is_utc(self):
        """GIVEN integrity snapshot WHEN created THEN created_at is UTC ISO-8601."""
        from dataforge.modules.integrity import IntegrityMonitor

        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, "src")
            os.makedirs(src_dir)
            # create a file to snapshot
            with open(os.path.join(src_dir, "a.txt"), "w") as f:
                f.write("hello")
            out = os.path.join(tmp, "snap.json")
            IntegrityMonitor.create_snapshot(src_dir, out)
            self.assertTrue(os.path.exists(out))
            import json
            with open(out) as f:
                payload = json.load(f)
            ts = payload["created_at"]
            self.assertIn("+00:00", ts, f"created_at must be UTC, got {ts}")
            dt = datetime.fromisoformat(ts)
            self.assertIsNotNone(dt.tzinfo, "created_at tzinfo must not be None")
            self.assertEqual(dt.tzinfo, timezone.utc)

    def test_performance_live_snapshot_is_utc(self):
        """GIVEN performance live snapshot WHEN generated THEN timestamp is UTC."""
        from dataforge.modules.performance import get_live_resource_snapshot
        snap = get_live_resource_snapshot()
        if "error" in snap:
            self.skipTest("psutil not available")
        ts = snap.get("timestamp")
        self.assertIsNotNone(ts)
        self.assertIn("+00:00", ts, f"timestamp must be UTC, got {ts}")
        dt = datetime.fromisoformat(ts)
        self.assertIsNotNone(dt.tzinfo)

    def test_performance_uptime_boot_time_is_utc(self):
        """GIVEN performance uptime WHEN queried THEN boot_time is UTC."""
        from dataforge.modules.performance import _get_uptime
        up = _get_uptime()
        if up is None:
            self.skipTest("psutil not available")
        ts = up.get("boot_time")
        self.assertIsNotNone(ts)
        self.assertIn("+00:00", ts, f"boot_time must be UTC, got {ts}")
        dt = datetime.fromisoformat(ts)
        self.assertIsNotNone(dt.tzinfo)

    def test_recovery_scan_recently_deleted_is_utc(self):
        """GIVEN recovery scan_recently_deleted WHEN run THEN modified is UTC."""
        from dataforge.modules.recovery import scan_recently_deleted

        with tempfile.TemporaryDirectory() as tmp:
            # create an empty subdirectory (will be reported as recently modified)
            empty_dir = os.path.join(tmp, "empty")
            os.makedirs(empty_dir)
            # ensure mtime is now
            os.utime(empty_dir, None)
            results = scan_recently_deleted(tmp, max_age_hours=24)
            # Should find at least the empty dir
            self.assertGreaterEqual(len(results), 1)
            for r in results:
                mod = r.get("modified")
                self.assertIsNotNone(mod)
                self.assertIn("+00:00", mod, f"modified must be UTC, got {mod}")
                dt = datetime.fromisoformat(mod)
                self.assertIsNotNone(dt.tzinfo)

    def test_search_build_query_uses_utc(self):
        """GIVEN search build_search_query WHEN called THEN uses UTC."""
        from dataforge.modules import search as search_mod

        # Patch the datetime in search module to verify it is called with timezone.utc
        with patch.object(search_mod, "datetime") as mock_dt:
            # mock datetime.now to return a known UTC time
            fake_now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = fake_now
            # Need timedelta to remain real; but build_search_query uses datetime.now and timedelta
            # So we also need to ensure timedelta still works — we mocked datetime class, but timedelta is separate import
            # Instead, patch where datetime.now is used via MagicMock
            # Simpler: patch dataforge.modules.search.datetime
            # We'll do a second approach below if this doesn't capture

            # Create a real timedelta behaviour via the mock's side effect
            # Actually easier: just call real function and compare timestamp proximity to UTC now
            pass

        # Real call: verify timestamp is close to UTC now
        from dataforge.modules.search import build_search_query
        before = datetime.now(timezone.utc) - timedelta(days=1)
        q = build_search_query(newer_than_days=1)
        after_ts = q.modified_after
        self.assertIsNotNone(after_ts)
        # after_ts should be roughly before.timestamp() within 2 seconds
        self.assertAlmostEqual(after_ts, before.timestamp(), delta=2.0)

        # Verify that datetime.now was called with timezone.utc by patching and checking call args
        with patch("dataforge.modules.search.datetime") as mock_datetime:
            fake = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = fake
            # need timedelta to be real for subtraction: mock_datetime.__sub__ not needed
            # build_search_query does: now = datetime.now(); after = now - timedelta(...)
            # If we mocked datetime.now to return fake, then after will be fake - timedelta
            q2 = build_search_query(newer_than_days=2)
            mock_datetime.now.assert_called_with(timezone.utc)
            # Verify after timestamp corresponds to fake - 2 days
            expected = (fake - timedelta(days=2)).timestamp()
            self.assertAlmostEqual(q2.modified_after, expected, delta=0.1)

    def test_system_cleanup_uses_utc_via_patch(self):
        """GIVEN system_cleanup WHEN scan_junk_files called THEN uses UTC."""
        from dataforge.modules import system_cleanup as sc_mod
        # Verify datetime.now called with timezone.utc
        with patch("dataforge.modules.system_cleanup.datetime") as mock_dt:
            fake_now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = fake_now
            # Need timedelta to work: timedelta is imported separately, not via datetime
            # So mock only affects datetime.now
            # Create dummy dir structure
            with tempfile.TemporaryDirectory() as tmp:
                # Create a file so scan doesn't fail
                open(os.path.join(tmp, "a.tmp"), "w").close()
                # Call with custom paths to avoid scanning real system dirs
                try:
                    sc_mod.scan_junk_files(paths=[tmp], categories=["System Temp"], min_age_days=1)
                except Exception:
                    pass
                # Check that datetime.now was called with timezone.utc (at least once)
                # It is called twice: for cutoff and now_ts
                calls = mock_dt.now.call_args_list
                self.assertGreaterEqual(len(calls), 1)
                for c in calls:
                    self.assertEqual(c.args[0], timezone.utc)
                    self.assertEqual(c.kwargs, {})

    def test_recovery_cutoff_uses_utc_via_patch(self):
        """GIVEN recovery WHEN scan_recently_deleted called THEN uses UTC."""
        from dataforge.modules import recovery as rec_mod
        with patch("dataforge.modules.recovery.datetime") as mock_dt:
            fake_now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = fake_now
            mock_dt.fromtimestamp.side_effect = lambda ts, tz=None: datetime.fromtimestamp(ts, tz=tz) if tz else datetime.fromtimestamp(ts)
            with tempfile.TemporaryDirectory() as tmp:
                empty = os.path.join(tmp, "empty")
                os.makedirs(empty)
                try:
                    rec_mod.scan_recently_deleted(tmp, max_age_hours=24)
                except Exception:
                    pass
                mock_dt.now.assert_called_with(timezone.utc)
                # fromtimestamp should be called with tz=timezone.utc
                found = False
                for call in mock_dt.fromtimestamp.call_args_list:
                    args, kwargs = call
                    if kwargs.get("tz") == timezone.utc or (len(args) > 1 and args[1] == timezone.utc):
                        found = True
                self.assertTrue(found, "fromtimestamp should be called with tz=timezone.utc")


if __name__ == "__main__":
    unittest.main()
