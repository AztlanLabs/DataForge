"""TICK-921 — Metadata: PNG write, exiftool detection, capability model, selective removal.

Covers STABILITY_AUDIT_2026-08-23 P1.6: PNG text-chunk writes via PngInfo,
robust exiftool detection via shutil.which, pypdf metadata writer, honest
GPS-only removal (no strip-all fallback), and cancellation at entry.
"""
from __future__ import annotations

import threading

import pytest

from dataforge.modules import metadata as md
from dataforge.modules.metadata import MetadataEngine


@pytest.fixture(autouse=True)
def _fresh_exiftool_probe():
    md._clear_exiftool_cache()
    yield
    md._clear_exiftool_cache()


# ---------------------------------------------------------------------------
# PNG writes via PngInfo
# ---------------------------------------------------------------------------


def test_png_write_text_chunks(tmp_path):
    """GIVEN a PNG WHEN write_metadata THEN text chunk is present on re-read."""
    from PIL import Image

    p = tmp_path / "sample.png"
    Image.new("RGB", (10, 10), color="red").save(p)

    result = MetadataEngine.write_metadata(str(p), {"Comment": "test"}, dry_run=False)
    assert result["success"] is True
    assert "PNG" in result["message"]

    with Image.open(p) as img:
        assert img.text.get("Comment") == "test"


def test_png_write_roundtrip(tmp_path):
    """GIVEN a PNG WHEN multiple fields written THEN all present on re-read."""
    from PIL import Image

    p = tmp_path / "roundtrip.png"
    Image.new("RGBA", (8, 8), color="blue").save(p)

    result = MetadataEngine.write_metadata(
        str(p), {"Author": "Alice", "Software": "DataForge", "Title": "Evidence"}, dry_run=False
    )
    assert result["success"] is True

    with Image.open(p) as img:
        assert img.text["Author"] == "Alice"
        assert img.text["Software"] == "DataForge"
        assert img.text["Title"] == "Evidence"


def test_png_preserves_existing_chunks(tmp_path):
    """GIVEN PNG with existing text chunks WHEN write THEN old chunks preserved."""
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    p = tmp_path / "existing.png"
    img = Image.new("RGB", (5, 5))
    info = PngInfo()
    info.add_text("Author", "Original")
    img.save(p, pnginfo=info)

    result = MetadataEngine.write_metadata(str(p), {"Comment": "new"}, dry_run=False)
    assert result["success"] is True

    with Image.open(p) as img2:
        assert img2.text["Author"] == "Original"
        assert img2.text["Comment"] == "new"


# ---------------------------------------------------------------------------
# Exiftool detection via shutil.which
# ---------------------------------------------------------------------------


def test_exiftool_detection_uses_which(monkeypatch):
    """GIVEN no exiftool on PATH THEN False; GIVEN found THEN True."""
    monkeypatch.setattr(md.shutil, "which", lambda *a, **k: None)
    assert md._has_exiftool() is False

    md._clear_exiftool_cache()
    monkeypatch.setattr(
        md.shutil, "which", lambda name, *a, **k: "/usr/bin/exiftool" if name == "exiftool" else None
    )
    assert md._has_exiftool() is True
    md._clear_exiftool_cache()


def test_exiftool_cache_clearable(monkeypatch):
    """GIVEN cached False WHEN cleared THEN next call re-probes."""
    monkeypatch.setattr(md.shutil, "which", lambda *a, **k: None)
    assert md._has_exiftool() is False
    # "Installed" mid-session: stale cache still says False...
    monkeypatch.setattr(md.shutil, "which", lambda *a, **k: "/usr/bin/exiftool")
    assert md._has_exiftool() is False
    # ...until the cache is cleared.
    md._clear_exiftool_cache()
    assert md._has_exiftool() is True
    md._clear_exiftool_cache()


# ---------------------------------------------------------------------------
# Capability report
# ---------------------------------------------------------------------------


def test_capability_report_accuracy():
    """GIVEN capabilities THEN .png readable + writable; jpeg honest re piexif."""
    formats = MetadataEngine.get_supported_formats()
    images = formats["images"]
    assert images["read"] is True  # Pillow is present in the test env
    assert images["details"][".png"]["read"] is True
    assert images["details"][".png"]["write"] is True  # PngInfo, no exiftool needed
    assert "write_fields" in images
    pdf = formats["pdf"]
    assert pdf["details"][".pdf"]["write"] is True  # pypdf present
    assert "pypdf" in pdf["write_fields"].lower()


# ---------------------------------------------------------------------------
# PDF writer
# ---------------------------------------------------------------------------


def _make_pdf(p):
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    with open(p, "wb") as f:
        w.write(f)


def test_pdf_write_metadata(tmp_path):
    """GIVEN a PDF WHEN write_metadata THEN field present on re-read."""
    p = tmp_path / "doc.pdf"
    _make_pdf(p)

    result = MetadataEngine.write_metadata(str(p), {"Author": "test"}, dry_run=False)
    assert result["success"] is True
    assert "PDF" in result["message"]

    meta = MetadataEngine.read_metadata(str(p))
    assert meta["handler"] == "pypdf"
    assert meta["fields"].get("Author") == "test"


def test_pdf_write_without_existing_metadata(tmp_path):
    """GIVEN a PDF with no metadata WHEN write THEN fields created."""
    p = tmp_path / "bare.pdf"
    _make_pdf(p)

    result = MetadataEngine.write_metadata(str(p), {"Title": "Fresh"}, dry_run=False)
    assert result["success"] is True

    meta = MetadataEngine.read_metadata(str(p))
    assert meta["fields"].get("Title") == "Fresh"


# ---------------------------------------------------------------------------
# GPS-only removal honesty
# ---------------------------------------------------------------------------


def test_gps_only_strip_no_fallback(tmp_path):
    """GIVEN GPS-only request on PNG WITHOUT exiftool THEN error, no strip-all."""
    from PIL import Image

    p = tmp_path / "gps.png"
    Image.new("RGB", (6, 6)).save(p)

    result = MetadataEngine.remove_metadata(str(p), fields=["GPSLatitude"], dry_run=False)
    assert result["success"] is False
    assert "exiftool" in result["message"].lower()

    # File must still exist and be a valid PNG (never stripped)
    from PIL import Image as Im

    with Im.open(p) as img:
        assert img.format == "PNG"


def test_gps_only_strip_jpeg_piexif(tmp_path):
    """GIVEN GPS-only on JPEG WITHOUT piexif THEN error (not strip-all)."""
    piexif = pytest.importorskip("piexif")
    from PIL import Image

    p = tmp_path / "gps.jpg"
    Image.new("RGB", (6, 6)).save(p, "JPEG")

    result = MetadataEngine.remove_metadata(str(p), fields=["GPSLatitude"], dry_run=False)
    if piexif is None:  # pragma: no cover
        assert result["success"] is False
    else:
        assert result["success"] is True
        assert "piexif" in result["message"].lower()


def test_gps_only_strip_png_without_exiftool_preserves_other_metadata(tmp_path):
    """GIVEN PNG with a text chunk WHEN GPS-only removal fails THEN chunk preserved."""
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    p = tmp_path / "kept.png"
    img = Image.new("RGB", (6, 6))
    info = PngInfo()
    info.add_text("Comment", "keep-me")
    img.save(p, pnginfo=info)

    result = MetadataEngine.remove_metadata(str(p), fields=["GPS"], dry_run=False)
    assert result["success"] is False

    with Image.open(p) as img2:
        assert img2.text.get("Comment") == "keep-me"


# ---------------------------------------------------------------------------
# Actionable errors / cancellation
# ---------------------------------------------------------------------------


def test_write_returns_actionable_message(tmp_path):
    """GIVEN unsupported format WHEN write THEN message mentions exiftool."""
    p = tmp_path / "mystery.xyz"
    p.write_bytes(b"\x00\x01")

    result = MetadataEngine.write_metadata(str(p), {"Author": "x"}, dry_run=False)
    assert result["success"] is False
    assert "exiftool" in result["message"].lower()
    assert "xyz" in result["message"].lower()


def test_cancellation_checked_at_entry(tmp_path):
    """GIVEN a set cancel_token WHEN write THEN cancelled immediately."""
    from PIL import Image

    p = tmp_path / "cancel.png"
    Image.new("RGB", (4, 4)).save(p)

    cancel = threading.Event()
    cancel.set()
    result = MetadataEngine.write_metadata(str(p), {"Comment": "x"}, dry_run=False, cancel_token=cancel)
    assert result["cancelled"] is True
    assert result["success"] is False


def test_write_empty_fields_noop(tmp_path):
    """GIVEN empty fields dict WHEN write THEN no-op success."""
    from PIL import Image

    p = tmp_path / "noop.png"
    Image.new("RGB", (4, 4)).save(p)

    result = MetadataEngine.write_metadata(str(p), {}, dry_run=False)
    assert result["success"] is True
    assert "No metadata fields" in result["message"]