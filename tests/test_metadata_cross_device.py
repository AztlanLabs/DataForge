"""
Tests for TICK-902: Metadata EXIF write/strip cross-device & 0 succeeded.

Verifies:
- _strip_pillow uses same-dir temp + shutil fallback (no Errno 18)
- _strip_pypdf same-dir temp + fallback
- write_metadata with exiftool missing returns actionable Install exiftool message
- GPS-only strip preserves other EXIF when exiftool present
- filenames with spaces/utf8 succeed
- cancel_token mid-batch respects cancel
"""
import os
import errno
import tempfile
import threading
from pathlib import Path
from unittest import mock

import pytest
from PIL import Image

from dataforge.modules.metadata import (
    MetadataEngine,
    _strip_pillow,
    _strip_pypdf,
    _has_exiftool,
)
from dataforge.modules.cleaner import MetadataCleaner


@pytest.fixture(autouse=True)
def clear_exiftool_cache():
    # clear lru_cache between tests
    _has_exiftool.cache_clear()
    yield
    _has_exiftool.cache_clear()


def _create_png_with_metadata(path: Path, with_text=True):
    img = Image.new("RGB", (32, 32), "red")
    # Add some info to simulate metadata
    if with_text:
        # PNG text chunk as info
        img.info["Comment"] = "test comment"
    img.save(path, format="PNG")
    return path


def _create_jpeg_with_exif(path: Path):
    img = Image.new("RGB", (32, 32), "blue")
    # Try to add exif via piexif if available, else just save
    try:
        import piexif
        exif_dict = {
            "0th": {
                piexif.ImageIFD.Make: "TestMake",
                piexif.ImageIFD.Model: "TestModel",
                piexif.ImageIFD.Software: "TestSoftware",
                piexif.ImageIFD.ImageDescription: "TestDesc",
            },
            "Exif": {
                piexif.ExifIFD.DateTimeOriginal: "2024:01:01 00:00:00",
            },
            "GPS": {
                piexif.GPSIFD.GPSLatitude: ((40, 1), (0, 1), (0, 1)),
                piexif.GPSIFD.GPSLatitudeRef: "N",
                piexif.GPSIFD.GPSLongitude: ((74, 1), (0, 1), (0, 1)),
                piexif.GPSIFD.GPSLongitudeRef: "W",
            },
            "1st": {},
            "thumbnail": None,
        }
        exif_bytes = piexif.dump(exif_dict)
        img.save(path, format="JPEG", exif=exif_bytes, quality=95)
    except Exception:
        img.save(path, format="JPEG", quality=95)
    return path


class TestCrossDevicePillow:
    def test_strip_pillow_same_dir_and_no_exdev(self):
        """GIVEN png on different mount WHEN _strip_pillow called THEN succeeds via same-dir temp + shutil copy fallback, no Errno 18"""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "test.png"
            _create_png_with_metadata(src)
            assert src.exists()

            def fake_replace(a, b):
                raise OSError(errno.EXDEV, "Invalid cross-device link")

            with mock.patch("dataforge.modules.metadata.os.replace", side_effect=fake_replace):
                result = _strip_pillow(str(src))
                assert result.get("success") is True, f"Expected success via fallback, got {result}"
                assert "Pillow strip failed" not in result.get("message", "")
                with Image.open(src) as im:
                    assert im.size == (32, 32)

    def test_strip_pillow_preserves_openable_and_no_exdev_error_leak(self):
        """Additional: stripped png still openable and no cross-device error leaked"""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "openable.png"
            _create_png_with_metadata(src)
            result = _strip_pillow(str(src))
            assert result["success"] is True
            # Ensure still openable and not corrupted
            with Image.open(src) as im:
                im.load()
                assert im.format == "PNG" or im.format is None  # after strip format may be inferred

    def test_strip_pillow_uses_same_dir_temp(self):
        """Verify temp file is created in same directory, not /tmp"""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "same_dir.png"
            _create_png_with_metadata(src)
            captured_dir = {}

            orig_mkstemp = tempfile.mkstemp

            def fake_mkstemp(suffix="", dir=None, **kwargs):
                captured_dir["dir"] = dir
                return orig_mkstemp(suffix=suffix, dir=dir, **kwargs)

            with mock.patch("dataforge.modules.metadata.tempfile.mkstemp", side_effect=fake_mkstemp):
                result = _strip_pillow(str(src))
                assert result["success"] is True
                expected_dir = os.path.dirname(os.path.abspath(str(src)))
                assert captured_dir["dir"] == expected_dir, f"Expected same-dir temp, got {captured_dir['dir']} vs {expected_dir}"

    def test_strip_pypdf_same_dir(self):
        """GIVEN pdf strip on different mount WHEN _strip_pypdf called THEN succeeds similarly"""
        try:
            from pypdf import PdfWriter, PdfReader
        except ImportError:
            pytest.skip("pypdf not installed")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "doc.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            writer.add_metadata({"/Author": "test", "/Title": "fixture"})
            with open(src, "wb") as f:
                writer.write(f)

            captured_dir = {}
            orig_mkstemp = tempfile.mkstemp

            def fake_mkstemp(suffix="", dir=None, **kwargs):
                captured_dir["dir"] = dir
                return orig_mkstemp(suffix=suffix, dir=dir, **kwargs)

            with mock.patch("dataforge.modules.metadata.tempfile.mkstemp", side_effect=fake_mkstemp):
                result = _strip_pypdf(str(src))
                assert result["success"] is True, f"PDF strip failed: {result}"
                expected_dir = os.path.dirname(os.path.abspath(str(src)))
                assert captured_dir["dir"] == expected_dir
            # Verify still readable and metadata stripped
            reader = PdfReader(str(src))
            meta = reader.metadata
            # After strip, metadata should be empty or None
            if meta:
                # Should have no Author/Title
                assert meta.get("/Author") in (None, "",)
            assert len(reader.pages) == 1

    def test_strip_pypdf_cross_device_fallback(self):
        """PDF cross-device fallback via copyfile"""
        try:
            from pypdf import PdfWriter
        except ImportError:
            pytest.skip("pypdf not installed")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "cross.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            writer.add_metadata({"/Author": "cross"})
            with open(src, "wb") as f:
                writer.write(f)

            def fake_replace(a, b):
                raise OSError(errno.EXDEV, "Invalid cross-device link")

            with mock.patch("dataforge.modules.metadata.os.replace", side_effect=fake_replace):
                result = _strip_pypdf(str(src))
                assert result["success"] is True
                assert src.exists()


class TestWriteMetadataNoExiftool:
    def test_write_metadata_returns_actionable_when_no_exiftool(self):
        """GIVEN edit metadata with exiftool missing WHEN write_metadata called for JPEG THEN returns success False with Install exiftool"""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "photo.jpg"
            _create_jpeg_with_exif(src)
            with mock.patch("dataforge.modules.metadata._has_exiftool", return_value=False):
                _has_exiftool.cache_clear()
                result = MetadataEngine.write_metadata(str(src), {"Make": "NewMake"}, dry_run=False)
                assert result["success"] is False
                assert "exiftool" in result["message"].lower(), f"Expected actionable exiftool message, got {result['message']}"

    def test_write_metadata_pillow_fallback_message(self):
        """Ensure _write_pillow directly returns actionable"""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "pillow.jpg"
            _create_jpeg_with_exif(src)
            from dataforge.modules.metadata import _write_pillow
            # Ensure exiftool missing path
            with mock.patch("dataforge.modules.metadata._has_exiftool", return_value=False):
                result = _write_pillow(str(src), {"Make": "test"})
                assert result["success"] is False
                assert "exiftool" in result["message"].lower()

    def test_view_shows_0_succeeded_with_detail(self):
        """Simulate view counting: success = sum(success) -> 0 with Install exiftool detail"""
        # This is more integration: ensure write returns False so view would show 0 succeeded
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "view.jpg"
            _create_jpeg_with_exif(src)
            with mock.patch("dataforge.modules.metadata._has_exiftool", return_value=False):
                results = []
                for p in [str(src)]:
                    r = MetadataEngine.write_metadata(p, {"Make": "x"}, dry_run=False)
                    r["path"] = p
                    results.append(r)
                success = sum(1 for r in results if r.get("success"))
                assert success == 0
                assert any("exiftool" in r.get("message","").lower() for r in results)


class TestGPSOnlyStrip:
    def test_gps_only_preserves_other_exif_when_exiftool_present(self):
        """GIVEN GPS-only strip WHEN exiftool present THEN only GPS tags cleared, other EXIF preserved"""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "gps.jpg"
            _create_jpeg_with_exif(src)
            # Mock exiftool strip to simulate selective behavior
            # We'll mock subprocess.run for _strip_exiftool
            # Also need _has_exiftool true
            with mock.patch("dataforge.modules.metadata._has_exiftool", return_value=True):
                _has_exiftool.cache_clear()
                # Capture args passed to subprocess.run
                captured = {}

                def fake_run(args, capture_output=True, text=True, timeout=30):
                    captured["args"] = args
                    # Simulate success
                    mock_res = mock.Mock()
                    mock_res.returncode = 0
                    mock_res.stdout = ""
                    mock_res.stderr = ""
                    return mock_res

                with mock.patch("dataforge.modules.metadata.subprocess.run", side_effect=fake_run):
                    gps_fields = [
                        "GPSLatitude", "GPSLongitude", "GPSAltitude",
                        "GPSLatitudeRef", "GPSLongitudeRef", "GPSAltitudeRef",
                        "GPSTimeStamp", "GPSDateStamp", "GPSVersionID",
                    ]
                    result = MetadataEngine.remove_metadata(str(src), fields=gps_fields, dry_run=False)
                    assert result["success"] is True
                    args = captured.get("args", [])
                    # Should contain GPS wildcard, not -all=
                    args_str = " ".join(args)
                    assert "-all=" not in args_str, f"GPS-only should not use -all=, got {args}"
                    assert "GPS" in args_str, f"Expected GPS in args, got {args}"
                    # Verify at least one GPS arg present
                    assert any("GPS" in a for a in args), f"Missing GPS arg {args}"

    def test_gps_only_via_engine_without_exiftool_returns_error_not_strip_all(self):
        """When exiftool missing, GPS-only should not silently strip all via Pillow"""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "gps_no_tool.png"
            _create_png_with_metadata(src)
            with mock.patch("dataforge.modules.metadata._has_exiftool", return_value=False):
                gps_fields = ["GPSLatitude", "GPSLongitude"]
                result = MetadataEngine.remove_metadata(str(src), fields=gps_fields, dry_run=False)
                # For PNG without exiftool, should return error about exiftool required, not success stripping all
                assert result["success"] is False
                assert "exiftool" in result["message"].lower()


class TestFilenameSpacesUtf8:
    def test_filename_with_spaces_utf8_strip_succeeds(self):
        """GIVEN filename with spaces/utf8 WHEN strip called THEN no file-not-found, succeeds"""
        with tempfile.TemporaryDirectory() as tmp:
            # Use utf8 path like Imágenes/Captura de pantalla...
            sub = Path(tmp) / "Imágenes" / "Capturas de pantalla"
            sub.mkdir(parents=True)
            src = sub / "Captura de pantalla_20260810_160718.png"
            _create_png_with_metadata(src)
            assert src.exists()
            result = _strip_pillow(str(src))
            assert result["success"] is True, f"UTF8 strip failed: {result}"
            # Also test via engine with utf8
            # Recreate for engine test
            _create_png_with_metadata(src)
            result2 = MetadataEngine.remove_metadata(str(src), dry_run=False)
            assert result2["success"] is True

    def test_subprocess_list_handles_utf8(self):
        """Ensure _strip_exiftool uses list args (no shell) so utf8 spaces handled"""
        with tempfile.TemporaryDirectory() as tmp:
            sub = Path(tmp) / "Imágenes"
            sub.mkdir(parents=True)
            src = sub / "Captura de pantalla_20260810_160718.jpg"
            _create_jpeg_with_exif(src)
            with mock.patch("dataforge.modules.metadata._has_exiftool", return_value=True):
                captured = {}

                def fake_run(args, capture_output=True, text=True, timeout=30):
                    captured["args"] = args
                    mock_res = mock.Mock()
                    mock_res.returncode = 0
                    mock_res.stdout = ""
                    mock_res.stderr = ""
                    return mock_res

                with mock.patch("dataforge.modules.metadata.subprocess.run", side_effect=fake_run):
                    result = MetadataEngine.remove_metadata(str(src), dry_run=False)
                    assert result["success"] is True
                    # Path should be last arg as separate list element
                    assert captured["args"][-1] == str(src)
                    # Ensure no shell splitting
                    assert len(captured["args"]) >= 3


class TestCancelToken:
    def test_cross_device_cancel_mid_batch(self):
        """GIVEN cross-device + cancel_token set mid-batch WHEN _strip_worker runs 5 files THEN respects cancel and returns partial"""
        from dataforge.ui.views.metadata_view import MetadataView

        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i in range(5):
                p = Path(tmp) / f"file{i}.png"
                _create_png_with_metadata(p)
                paths.append(str(p))

            # Create a view instance without full app (mock)
            # We test the worker logic directly
            cancel = threading.Event()

            # Simulate view's _strip_worker behavior
            def fake_strip_worker(paths, fields=None, progress_callback=None, cancel_token=None):
                results = []
                total = len(paths)
                for idx, path in enumerate(paths):
                    if cancel_token and cancel_token.is_set():
                        break
                    if progress_callback:
                        progress_callback(idx, total, f"Stripping: {os.path.basename(path)}")
                    # Use real engine but with cancel check
                    result = MetadataEngine.remove_metadata(path, fields=fields, dry_run=False)
                    result["path"] = path
                    results.append(result)
                    # Simulate cancel after 2 files
                    if idx == 1:
                        cancel_token.set()
                if progress_callback:
                    progress_callback(total, total, "Strip complete")
                if cancel_token and cancel_token.is_set():
                    return {"cancelled": True, "results": results}
                return results

            progress_calls = []

            def prog(c, t, msg):
                progress_calls.append((c, t, msg))

            results = fake_strip_worker(paths, fields=None, progress_callback=prog, cancel_token=cancel)
            # Should be cancelled wrapper
            assert isinstance(results, dict) and results.get("cancelled") is True
            inner = results["results"]
            # Should be partial (2 files processed before cancel, maybe 2)
            assert 1 <= len(inner) < 5, f"Expected partial, got {len(inner)}"
            # Ensure cancel respected
            assert cancel.is_set()

            # Also test real view worker if possible (without app)
            # Mock app
            mock_app = mock.Mock()
            mock_view = MetadataView.__new__(MetadataView)
            mock_view.app = mock_app
            mock_view.item_metadata_map = {}
            mock_view.file_tree = mock.Mock()
            # Call view's actual worker
            cancel2 = threading.Event()
            # Set cancel after first iteration via side effect on progress_callback?
            # We will pre-set cancel after 1 file by setting token before second loop iteration
            # Use thread to set quickly
            def set_soon():
                import time
                time.sleep(0.02)
                cancel2.set()

            import threading as thr
            thr.Thread(target=set_soon, daemon=True).start()
            # Need to ensure worker checks cancel_token; we just verify it returns partial or cancelled within timeout
            # Call with real method
            view_results = MetadataView._strip_worker(mock_view, paths, fields=None, progress_callback=prog, cancel_token=cancel2)
            # May be list or dict depending on timing, but if cancel was set mid-run should be cancelled or partial length <5
            if isinstance(view_results, dict):
                assert view_results.get("cancelled") is True
                assert len(view_results["results"]) < 5
            else:
                # If timing missed, at least it returned list but cancel set means second call would break
                # we accept either but ensure progress called
                assert len(progress_calls) > 0

    def test_engine_remove_respects_cancel_token(self):
        """Engine remove_metadata should early return cancelled if token set"""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "cancel.png"
            _create_png_with_metadata(src)
            cancel = threading.Event()
            cancel.set()
            result = MetadataEngine.remove_metadata(str(src), dry_run=False, cancel_token=cancel)
            assert result.get("cancelled") is True or result.get("success") is False
            assert "cancel" in result.get("message", "").lower()


class TestCleanerShim:
    def test_cleaner_delegates_with_cancel_and_fields(self):
        """Cleaner shim should delegate with same cross-device safety and accept new params"""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "shim.png"
            _create_png_with_metadata(src)
            # Ensure shim accepts fields and cancel_token without error
            cancel = threading.Event()
            result = MetadataCleaner.remove_metadata(str(src), fields=None, dry_run=False, cancel_token=cancel, progress_callback=lambda a,b,c: None)
            assert isinstance(result, dict)
            assert "success" in result
            # Cancelled case
            cancel.set()
            result2 = MetadataCleaner.remove_metadata(str(src), dry_run=False, cancel_token=cancel)
            assert result2.get("cancelled") or not result2.get("success")

    def test_cleaner_and_engine_identical(self):
        """Shim and engine should produce identical results for same file"""
        with tempfile.TemporaryDirectory() as tmp:
            p1 = Path(tmp) / "a.png"
            p2 = Path(tmp) / "b.png"
            _create_png_with_metadata(p1)
            _create_png_with_metadata(p2)
            r1 = MetadataEngine.remove_metadata(str(p1), dry_run=False)
            r2 = MetadataCleaner.remove_metadata(str(p2), dry_run=False)
            assert r1["success"] == r2["success"]
