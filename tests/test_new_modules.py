"""
Unit and integration tests for the new system diagnostics, cleanup, recovery,
metadata engineering, and forensics backend modules.
"""
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from dataforge.modules.system_cleanup import (
    scan_junk_files,
    estimate_cleanup_savings,
)
from dataforge.modules.performance import (
    get_system_info,
    get_running_processes,
)
from dataforge.modules.recovery import (
    scan_trash,
)
from dataforge.modules.metadata import MetadataEngine
from dataforge.modules.hardware import get_hardware_report
from dataforge.modules.forensics import (
    calculate_hashes,
    parse_os_artifacts,
    generate_forensic_report,
)
from dataforge.modules.password_tools import analyze_password_strength


class TestNewModules(unittest.TestCase):

    def test_junk_scan_and_savings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            # Create dummy junk files
            (temp_path / "dummy.tmp").write_text("junk content", encoding="utf-8")
            (temp_path / "dummy.bak").write_text("more junk", encoding="utf-8")
            (temp_path / "normal.txt").write_text("important", encoding="utf-8")

            # Scan with Log Files category so files inside tmpdir are filtered by extension/pattern,
            # rather than everything inside a System Temp directory being treated as junk automatically.
            results = scan_junk_files(paths=[tmpdir], categories=["Log Files"])
            estimate_cleanup_savings(results)

            self.assertIn("Log Files", results)
            paths = [e.path for e in results["Log Files"]]
            # Note: dummy.bak has a junk extension, but normal.txt does not
            self.assertTrue(any("dummy.bak" in p for p in paths))
            self.assertFalse(any("normal.txt" in p for p in paths))

    def test_performance_info(self):
        info = get_system_info()
        self.assertIn("os", info)
        self.assertIn("cpu", info)
        self.assertIn("memory", info)

        processes = get_running_processes(limit=5)
        self.assertTrue(len(processes) <= 5)
        if processes:
            self.assertIn("pid", processes[0])
            self.assertIn("name", processes[0])

    def test_trash_scanner(self):
        # Should not crash on platform runs
        try:
            results = scan_trash()
            self.assertIsInstance(results, list)
        except Exception as e:
            self.fail(f"scan_trash raised an exception: {e}")

    def test_password_strength(self):
        # Test basic strength analyzer
        results = analyze_password_strength(["weak", "Password123!", "SuperSecureP@ssw0rd2026!"])
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["strength"], "Very Weak")
        self.assertIn(results[2]["strength"], ["Strong", "Very Strong"])

    def test_metadata_supported_formats(self):
        formats = MetadataEngine.get_supported_formats()
        self.assertIn("images", formats)
        self.assertIn("pdf", formats)
        self.assertIn("audio", formats)

    def test_hardware_report(self):
        report = get_hardware_report()
        self.assertIn("system", report)
        self.assertIn("cpu", report)
        self.assertIn("ram", report)
        self.assertIn("storage", report)

    def test_cryptographic_hashes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.txt"
            file_path.write_text("Hello World", encoding="utf-8")

            results = calculate_hashes([str(file_path)], algorithms=["md5", "sha256"])
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["filename"], "test.txt")
            # MD5 of "Hello World" is b10a8db164e0754105b7a99be72e3fe5
            self.assertEqual(results[0]["md5"], "b10a8db164e0754105b7a99be72e3fe5")
            # SHA-256 of "Hello World" is a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e
            self.assertEqual(results[0]["sha256"], "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e")

    @patch("os.path.isdir", return_value=True)
    @patch("os.path.exists", return_value=True)
    @patch("os.path.isfile", return_value=True)
    def test_forensics_artifact_parsing_linux(self, mock_isfile, mock_exists, mock_isdir):
        # Mock reading of files
        def mock_open_fn(file, *args, **kwargs):
            m = MagicMock()
            m.__enter__.return_value = m
            if "passwd" in str(file):
                lines = ["root:x:0:0:root:/root:/bin/bash"]
                m.__iter__.return_value = lines
                m.readlines.return_value = lines
            elif "auth.log" in str(file):
                lines = ["Jun  2 00:00:00 host sshd[123]: Accepted publickey for root"]
                m.__iter__.return_value = lines
                m.readlines.return_value = lines
            elif "bash_history" in str(file):
                lines = ["ls -la", "cd /tmp"]
                m.__iter__.return_value = lines
                m.readlines.return_value = lines
            else:
                m.__iter__.return_value = []
                m.readlines.return_value = []
            return m

        with patch("builtins.open", mock_open_fn):
            # Parse artifacts on mocked directories
            artifacts = parse_os_artifacts("/mock/root")
            self.assertIn("users", artifacts)
            self.assertIn("auth_logs", artifacts)
            self.assertIn("shell_history", artifacts)
            self.assertTrue(len(artifacts["users"]) > 0)
            self.assertEqual(artifacts["users"][0]["username"], "root")

    def test_forensic_report_html_escapes_script_filename(self):
        malicious = "<script>alert(1)</script>.txt"
        results = {
            "file_count": 1,
            "hashes": [{
                "filename": malicious,
                "formatted_size": "1 B",
                "md5": "0" * 32,
                "sha256": "0" * 64,
            }],
            "artifacts": {
                "users": [{
                    "username": malicious,
                    "uid": 0,
                    "home": "/root",
                    "shell": "/bin/bash",
                }],
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "report.html")
            generate_forensic_report(results, out_path, fmt="html")
            html_content = Path(out_path).read_text(encoding="utf-8")
            self.assertNotIn("<script>alert(1)</script>", html_content)
            self.assertIn("&lt;script&gt;", html_content)

    def test_about_view(self):
        from PyQt5.QtWidgets import QApplication, QWidget
        from dataforge.ui.views.about import AboutView

        app = QApplication.instance()
        if not app:
            app = QApplication([])

        parent = QWidget()
        view = AboutView(parent)
        self.assertEqual(view.get_title(), "About & Help")
        self.assertTrue(len(view.get_help_text()) > 0)


if __name__ == "__main__":
    unittest.main()
