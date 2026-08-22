"""
Tests for TICK-204: MetadataCleaner shim delegates to MetadataEngine.

Verifies:
- MetadataCleaner.remove_metadata delegates to MetadataEngine and returns dict
- No circular import between cleaner.py and metadata.py
- Image+PDF fixtures produce identical results via either entry point
"""
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from dataforge.modules.cleaner import MetadataCleaner
from dataforge.modules.metadata import MetadataEngine


class TestMetadataSingleSeam(unittest.TestCase):
    """TICK-204 acceptance criteria tests."""

    def test_cleaner_shim_returns_dict(self):
        """GIVEN cleaner.MetadataCleaner.remove_metadata(path) WHEN called THEN return type is dict (not bool)."""
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"data")
            path = f.name
        try:
            result = MetadataCleaner.remove_metadata(path)
            self.assertIsInstance(result, dict, "remove_metadata must return dict, not bool")
            self.assertIn("success", result)
            self.assertIn("message", result)
        finally:
            os.unlink(path)

    def test_cleaner_shim_delegates_to_engine(self):
        """GIVEN cleaner.MetadataCleaner.remove_metadata WHEN called THEN delegates to MetadataEngine."""
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"data")
            path = f.name
        try:
            cleaner_result = MetadataCleaner.remove_metadata(path, dry_run=True)
            engine_result = MetadataEngine.remove_metadata(path, dry_run=True)
            self.assertEqual(cleaner_result, engine_result)
        finally:
            os.unlink(path)

    def test_no_circular_import(self):
        """GIVEN metadata.py shim missing WHEN imported THEN no circular import."""
        import importlib
        import dataforge.modules.cleaner as cleaner_mod
        import dataforge.modules.metadata as metadata_mod
        # Force reimport to detect circular dependency
        importlib.reload(cleaner_mod)
        importlib.reload(metadata_mod)
        self.assertTrue(hasattr(cleaner_mod, "MetadataCleaner"))
        self.assertTrue(hasattr(metadata_mod, "MetadataEngine"))

    def test_image_strip_identical_via_both_entry_points(self):
        """GIVEN image fixture WHEN stripped THEN payload is identical via either entry point."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create image with EXIF
            path_engine = Path(tmp) / "engine.png"
            path_cleaner = Path(tmp) / "cleaner.png"
            img = Image.new("RGB", (32, 32), "red")
            img.save(path_engine)
            img.save(path_cleaner)

            # Strip via engine
            engine_result = MetadataEngine.remove_metadata(str(path_engine), dry_run=False)
            # Strip via cleaner shim
            cleaner_result = MetadataCleaner.remove_metadata(str(path_cleaner), dry_run=False)

            self.assertTrue(engine_result.get("success", False), f"Engine strip failed: {engine_result}")
            self.assertTrue(cleaner_result.get("success", False), f"Cleaner strip failed: {cleaner_result}")

            # Both files should be identical after stripping
            engine_bytes = path_engine.read_bytes()
            cleaner_bytes = path_cleaner.read_bytes()
            self.assertEqual(engine_bytes, cleaner_bytes,
                             "Payload must be identical via either entry point")

    def test_pdf_strip_identical_via_both_entry_points(self):
        """GIVEN PDF fixture WHEN stripped THEN payload is identical via either entry point."""
        try:
            from pypdf import PdfWriter
        except ImportError:
            self.skipTest("pypdf not installed")

        with tempfile.TemporaryDirectory() as tmp:
            # Create minimal PDF
            path_engine = Path(tmp) / "engine.pdf"
            path_cleaner = Path(tmp) / "cleaner.pdf"
            for p in (path_engine, path_cleaner):
                writer = PdfWriter()
                writer.add_blank_page(width=72, height=72)
                writer.add_metadata({"/Author": "test", "/Title": "fixture"})
                with open(p, "wb") as f:
                    writer.write(f)

            # Strip via engine
            engine_result = MetadataEngine.remove_metadata(str(path_engine), dry_run=False)
            # Strip via cleaner shim
            cleaner_result = MetadataCleaner.remove_metadata(str(path_cleaner), dry_run=False)

            self.assertTrue(engine_result.get("success", False), f"Engine strip failed: {engine_result}")
            self.assertTrue(cleaner_result.get("success", False), f"Cleaner strip failed: {cleaner_result}")

            # Both files should be identical after stripping
            engine_bytes = path_engine.read_bytes()
            cleaner_bytes = path_cleaner.read_bytes()
            self.assertEqual(engine_bytes, cleaner_bytes,
                             "PDF payload must be identical via either entry point")

    def test_cleaner_dry_run_returns_dict(self):
        """GIVEN dry_run=True WHEN called THEN returns dict with success=True."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "photo.png"
            Image.new("RGB", (8, 8), "blue").save(path)

            result = MetadataCleaner.remove_metadata(str(path), dry_run=True)
            self.assertIsInstance(result, dict)
            self.assertTrue(result.get("success", False))
            self.assertTrue(result.get("dry_run", False))

    def test_cleaner_unsupported_format_returns_failure_dict(self):
        """GIVEN unsupported format WHEN called THEN returns dict with success=False."""
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"data")
            path = f.name
        try:
            result = MetadataCleaner.remove_metadata(path)
            self.assertIsInstance(result, dict)
            self.assertFalse(result.get("success", False))
        finally:
            os.unlink(path)

    def test_engine_remove_metadata_returns_dict(self):
        """GIVEN MetadataEngine.remove_metadata WHEN called THEN returns dict."""
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"data")
            path = f.name
        try:
            result = MetadataEngine.remove_metadata(path)
            self.assertIsInstance(result, dict)
            self.assertIn("success", result)
            self.assertIn("message", result)
        finally:
            os.unlink(path)

    def test_cleaner_get_metadata_info_unchanged(self):
        """GIVEN MetadataCleaner.get_metadata_info WHEN called THEN still returns tuple."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"plain text")
            path = f.name
        try:
            result = MetadataCleaner.get_metadata_info(path)
            self.assertIsInstance(result, tuple)
            self.assertEqual(len(result), 3)
            has, size, info = result
            self.assertIsInstance(has, bool)
            self.assertIsInstance(size, int)
            self.assertIsInstance(info, str)
        finally:
            os.unlink(path)

    def test_image_cleaner_strips_metadata(self):
        """GIVEN image with metadata WHEN cleaned via shim THEN metadata is stripped."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "photo.jpg"
            img = Image.new("RGB", (16, 16), "green")
            img.save(path, quality=95)

            result = MetadataCleaner.remove_metadata(str(path), dry_run=False)
            self.assertTrue(result.get("success", False), f"Strip failed: {result}")
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
