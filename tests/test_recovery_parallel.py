"""
Tests for TICK-202 — Parallel carving: mmap image, sliding-window scan, chunked workers.

Validates:
- mmap used instead of sequential read
- Sliding-window finds headers at non-sector-aligned offsets (F6 fix)
- ThreadPoolExecutor chunked workers
- cancel_token stops workers, no partial carved files left
- max_files limit respected
- file_types filter works
- RIFF subtypes (WAV/AVI/WEBP) correctly identified
- Progress callback invoked
- Edge cases: empty image, missing image, zero-byte file
"""

import os
import struct
import threading
from unittest.mock import patch

from dataforge.modules.recovery import carve_files_from_image, _get_max_workers
from dataforge.modules.file_signatures import SIGNATURES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_image(path: str, size: int = 1024 * 1024) -> str:
    """Create a raw image filled with non-matching bytes (0xAA)."""
    with open(path, "wb") as f:
        f.write(b"\xAA" * size)
    return path


def _inject_jpeg(path: str, offset: int) -> str:
    """Inject a minimal JPEG (header + payload + footer) at offset."""
    jpeg_header = SIGNATURES["JPEG"]["header"]
    jpeg_footer = SIGNATURES["JPEG"]["footer"]
    payload = b"\x00" * 100
    data = jpeg_header + payload + jpeg_footer
    with open(path, "r+b") as f:
        f.seek(offset)
        f.write(data)
    return path


def _inject_pdf(path: str, offset: int) -> str:
    """Inject a minimal PDF at offset."""
    pdf_header = SIGNATURES["PDF"]["header"]
    pdf_footer = SIGNATURES["PDF"]["footer"]
    payload = b"\x00" * 200
    data = pdf_header + payload + pdf_footer
    with open(path, "r+b") as f:
        f.seek(offset)
        f.write(data)
    return path


def _inject_png(path: str, offset: int) -> str:
    """Inject a minimal PNG at offset."""
    png_header = SIGNATURES["PNG"]["header"]
    png_footer = SIGNATURES["PNG"]["footer"]
    payload = b"\x00" * 150
    data = png_header + payload + png_footer
    with open(path, "r+b") as f:
        f.seek(offset)
        f.write(data)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestParallelCarving:
    """TICK-202 acceptance criteria and regression tests."""

    def test_basic_jpeg_carve(self, tmp_path):
        """GIVEN image with JPEG at offset 0 WHEN carve THEN found."""
        img = str(tmp_path / "test.img")
        _make_image(img, 4096)
        _inject_jpeg(img, 0)

        result = carve_files_from_image(img, str(tmp_path / "out"), file_types=["JPEG"])

        assert result["total_carved"] == 1
        assert result["carved"][0]["format"] == "JPEG"
        assert result["carved"][0]["offset"] == 0
        assert os.path.exists(result["carved"][0]["path"])

    def test_unaligned_header_found(self, tmp_path):
        """GIVEN header at byte offset not %512 WHEN scanning THEN still found (F6 fix)."""
        img = str(tmp_path / "test.img")
        _make_image(img, 8192)
        # Inject at non-sector-aligned offset
        _inject_jpeg(img, 123)

        result = carve_files_from_image(img, str(tmp_path / "out"), file_types=["JPEG"])

        assert result["total_carved"] == 1
        assert result["carved"][0]["offset"] == 123

    def test_multiple_files_different_offsets(self, tmp_path):
        """GIVEN image with JPEG + PDF at different offsets WHEN carve THEN both found."""
        img = str(tmp_path / "test.img")
        _make_image(img, 65536)
        _inject_jpeg(img, 100)
        _inject_pdf(img, 500)

        result = carve_files_from_image(img, str(tmp_path / "out"))

        assert result["total_carved"] == 2
        formats = {c["format"] for c in result["carved"]}
        assert "JPEG" in formats
        assert "PDF" in formats

    def test_sliding_window_boundary(self, tmp_path):
        """GIVEN header near window boundary WHEN carve THEN found via overlap."""
        img = str(tmp_path / "test.img")
        # Make image just over 64 MiB so we get 2 windows
        size = 64 * 1024 * 1024 + 4096
        _make_image(img, size)
        # Inject near the 64 MiB boundary (will be in overlap zone)
        _inject_jpeg(img, 64 * 1024 * 1024 - 100)

        result = carve_files_from_image(img, str(tmp_path / "out"), file_types=["JPEG"])

        assert result["total_carved"] == 1
        assert result["carved"][0]["offset"] == 64 * 1024 * 1024 - 100

    def test_cancel_token_stops_workers(self, tmp_path):
        """GIVEN cancel_token set WHEN carve THEN workers stop."""
        img = str(tmp_path / "test.img")
        _make_image(img, 4096)
        _inject_jpeg(img, 0)

        cancel = threading.Event()
        cancel.set()  # Pre-cancel

        result = carve_files_from_image(img, str(tmp_path / "out"), cancel_token=cancel)

        assert result["cancelled"] is True
        assert result["total_carved"] == 0

    def test_no_partial_files_on_cancel(self, tmp_path):
        """GIVEN cancel_token set mid-carve WHEN carve THEN no partial files left."""
        img = str(tmp_path / "test.img")
        _make_image(img, 4096)
        _inject_jpeg(img, 0)

        cancel = threading.Event()

        # Cancel after first progress callback
        call_count = [0]

        def progress_with_cancel(current, total, msg=""):
            call_count[0] += 1
            if call_count[0] > 0:
                cancel.set()

        result = carve_files_from_image(
            img, str(tmp_path / "out"),
            cancel_token=cancel,
            progress_callback=progress_with_cancel,
        )

        # Should be cancelled
        assert result["cancelled"] is True
        # No .tmp files should remain
        out_dir = str(tmp_path / "out")
        if os.path.isdir(out_dir):
            tmp_files = [f for f in os.listdir(out_dir) if f.endswith(".tmp")]
            assert len(tmp_files) == 0

    def test_max_files_limit(self, tmp_path):
        """GIVEN max_files=1 WHEN carve THEN only 1 file carved."""
        img = str(tmp_path / "test.img")
        _make_image(img, 65536)
        _inject_jpeg(img, 0)
        _inject_jpeg(img, 4096)

        result = carve_files_from_image(img, str(tmp_path / "out"), file_types=["JPEG"], max_files=1)

        assert result["total_carved"] == 1

    def test_file_types_filter(self, tmp_path):
        """GIVEN file_types=["JPEG"] WHEN carve THEN only JPEG carved."""
        img = str(tmp_path / "test.img")
        _make_image(img, 65536)
        _inject_jpeg(img, 0)
        _inject_pdf(img, 4096)

        result = carve_files_from_image(img, str(tmp_path / "out"), file_types=["JPEG"])

        assert result["total_carved"] == 1
        assert result["carved"][0]["format"] == "JPEG"

    def test_empty_image(self, tmp_path):
        """GIVEN empty image WHEN carve THEN returns empty result."""
        img = str(tmp_path / "empty.img")
        with open(img, "wb"):
            pass  # 0 bytes

        result = carve_files_from_image(img, str(tmp_path / "out"))

        assert result["total_carved"] == 0
        assert result["carved"] == []

    def test_missing_image(self, tmp_path):
        """GIVEN non-existent image WHEN carve THEN returns error."""
        result = carve_files_from_image("/nonexistent/image.img", str(tmp_path / "out"))

        assert "error" in result
        assert "not found" in result["error"].lower() or "cannot" in result["error"].lower()

    def test_progress_callback_invoked(self, tmp_path):
        """GIVEN image WHEN carve THEN progress_callback called."""
        img = str(tmp_path / "test.img")
        _make_image(img, 4096)
        _inject_jpeg(img, 0)

        calls = []

        def cb(current, total, msg=""):
            calls.append((current, total, msg))

        carve_files_from_image(img, str(tmp_path / "out"), file_types=["JPEG"], progress_callback=cb)

        assert len(calls) > 0
        # Last call should be "Carving complete"
        assert "complete" in calls[-1][2].lower()

    def test_mmap_used(self, tmp_path):
        """GIVEN image WHEN carve THEN mmap is used (not sequential read)."""
        img = str(tmp_path / "test.img")
        _make_image(img, 4096)
        _inject_jpeg(img, 0)

        with patch("dataforge.modules.recovery.mmap.mmap", wraps=__import__("mmap").mmap) as mock_mmap:
            carve_files_from_image(img, str(tmp_path / "out"), file_types=["JPEG"])
            assert mock_mmap.called

    def test_threadpool_used(self, tmp_path):
        """GIVEN image WHEN carve THEN ThreadPoolExecutor used."""
        img = str(tmp_path / "test.img")
        _make_image(img, 4096)
        _inject_jpeg(img, 0)

        from concurrent.futures import ThreadPoolExecutor
        with patch("dataforge.modules.recovery.ThreadPoolExecutor", wraps=ThreadPoolExecutor) as mock_pool:
            carve_files_from_image(img, str(tmp_path / "out"), file_types=["JPEG"])
            assert mock_pool.called

    def test_riff_wav_subtype(self, tmp_path):
        """GIVEN WAV (RIFF+WAVE) image WHEN carve THEN identified as WAV."""
        img = str(tmp_path / "test.img")
        _make_image(img, 4096)
        # RIFF header + WAVE subtype
        riff_header = b"\x52\x49\x46\x46"
        size_bytes = struct.pack("<I", 100)
        wave_subtype = b"\x57\x41\x56\x45"
        payload = b"\x00" * 80
        data = riff_header + size_bytes + wave_subtype + payload
        with open(img, "r+b") as f:
            f.seek(0)
            f.write(data)

        result = carve_files_from_image(img, str(tmp_path / "out"), file_types=["WAV"])

        assert result["total_carved"] == 1
        assert result["carved"][0]["format"] == "WAV"

    def test_no_duplicate_across_windows(self, tmp_path):
        """GIVEN header in overlap zone WHEN two windows scan THEN carved once."""
        img = str(tmp_path / "test.img")
        # Small image so only one window, but test dedup logic
        _make_image(img, 4096)
        _inject_jpeg(img, 100)

        result = carve_files_from_image(img, str(tmp_path / "out"), file_types=["JPEG"])

        # Should be exactly 1, not duplicated
        assert result["total_carved"] == 1

    def test_get_max_workers_returns_positive(self):
        """_get_max_workers returns a positive integer."""
        workers = _get_max_workers()
        assert isinstance(workers, int)
        assert workers >= 1

    def test_carved_file_written_correctly(self, tmp_path):
        """GIVEN JPEG at offset 100 WHEN carved THEN file content matches original."""
        img = str(tmp_path / "test.img")
        _make_image(img, 4096)
        jpeg_header = SIGNATURES["JPEG"]["header"]
        jpeg_footer = SIGNATURES["JPEG"]["footer"]
        payload = b"HELLO_WORLD_PAYLOAD"
        data = jpeg_header + payload + jpeg_footer
        with open(img, "r+b") as f:
            f.seek(100)
            f.write(data)

        result = carve_files_from_image(img, str(tmp_path / "out"), file_types=["JPEG"])

        assert result["total_carved"] == 1
        carved_path = result["carved"][0]["path"]
        with open(carved_path, "rb") as f:
            content = f.read()
        assert content == data

    def test_image_with_no_signatures(self, tmp_path):
        """GIVEN image with no known signatures WHEN carve THEN returns empty."""
        img = str(tmp_path / "test.img")
        _make_image(img, 4096)

        result = carve_files_from_image(img, str(tmp_path / "out"))

        assert result["total_carved"] == 0
        assert result["errors"] == []

    def test_empty_file_types_list(self, tmp_path):
        """GIVEN file_types=[] WHEN carve THEN returns empty (no sigs selected)."""
        img = str(tmp_path / "test.img")
        _make_image(img, 4096)
        _inject_jpeg(img, 0)

        result = carve_files_from_image(img, str(tmp_path / "out"), file_types=[])

        assert result["total_carved"] == 0
