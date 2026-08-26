"""TICK-920 — Media ops contract: merge/split/compress/convert correctness, image safety, atomic output."""
import os
from unittest.mock import patch

from PIL import Image
from pypdf import PdfReader, PdfWriter

from dataforge.core import media_ops


def _make_pdf(path, pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        writer.write(f)
    return path


def _make_image(path, size=(16, 16), color=(255, 0, 0)):
    im = Image.new("RGB", size, color)
    im.save(str(path), "PNG")
    im.close()
    return path


def test_merge_no_pypdf_returns_report(tmp_path, monkeypatch):
    monkeypatch.setattr(media_ops, "HAS_PYPDF", False)
    out = tmp_path / "merged.pdf"
    res = media_ops.merge_pdfs([str(tmp_path / "a.pdf")], str(out))
    assert isinstance(res, dict)
    assert res["success"] is False
    assert "pypdf" in res["message"]
    assert res["requested"] == 1


def test_merge_zero_valid_inputs(tmp_path):
    bads = []
    for i in range(3):
        p = tmp_path / f"bad{i}.pdf"
        p.write_text("not a pdf")
        bads.append(str(p))
    out = tmp_path / "merged.pdf"
    res = media_ops.merge_pdfs(bads, str(out))
    assert res["success"] is False
    assert res["merged"] == 0
    assert not os.path.exists(str(out))


def test_merge_counts_only_successful_pages(tmp_path):
    a = _make_pdf(tmp_path / "a.pdf", pages=2)
    b = _make_pdf(tmp_path / "b.pdf", pages=3)
    bad = tmp_path / "bad.pdf"
    bad.write_text("not a pdf")
    out = tmp_path / "merged.pdf"
    res = media_ops.merge_pdfs([str(a), str(b), str(bad)], str(out))
    assert res["merged"] == 2
    assert res["failed"] == 1
    assert os.path.exists(str(out))
    reader = PdfReader(str(out))
    assert len(reader.pages) == 5


def test_merge_empty_pdf_not_written(tmp_path):
    src = _make_pdf(tmp_path / "src.pdf", pages=1)
    out = tmp_path / "merged.pdf"
    with patch.object(PdfWriter, "add_page", side_effect=Exception("boom")):
        res = media_ops.merge_pdfs([str(src)], str(out))
    assert res["merged"] == 0
    assert res["success"] is False
    assert not os.path.exists(str(out))


def test_split_generated_after_write(tmp_path):
    src = _make_pdf(tmp_path / "src.pdf", pages=3)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = media_ops.split_pdf(str(src), str(out_dir))
    assert res["success"] is True
    assert len(res["pages"]) == 3
    for p in res["pages"]:
        assert os.path.exists(p)


def test_split_error_shape_matches_report(tmp_path):
    src = _make_pdf(tmp_path / "src.pdf", pages=2)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with patch.object(PdfWriter, "write", side_effect=OSError("disk full")):
        res = media_ops.split_pdf(str(src), str(out_dir))
    assert res["success"] is False
    assert res["errors"]
    for err in res["errors"]:
        assert "requested" in err
        assert "success" in err and err["success"] is False
        assert "message" in err
        assert "error" in err


def test_compress_dry_run_has_estimate_note(tmp_path):
    src = _make_pdf(tmp_path / "src.pdf", pages=2)
    out = tmp_path / "compressed.pdf"
    res = media_ops.compress_pdf(str(src), str(out), quality="low", dry_run=True)
    assert res["dry_run"] is True
    assert res["ratio"] is not None
    assert res["ratio_note"] is not None
    assert not os.path.exists(str(out))


def test_compress_real_compresses(tmp_path):
    src = _make_pdf(tmp_path / "src.pdf", pages=3)
    out = tmp_path / "compressed.pdf"
    res = media_ops.compress_pdf(str(src), str(out), quality="medium")
    assert res["success"] is True
    assert res["ratio"] is not None
    assert os.path.exists(str(out))
    reader = PdfReader(str(out))
    assert len(reader.pages) == 3


def test_image_dry_run_creates_nothing(tmp_path):
    src = _make_image(tmp_path / "img.png")
    dest = tmp_path / "dest"
    res = media_ops.convert_image(str(src), "JPEG", dry_run=True, output_dir=str(dest))
    assert res["dry_run"] is True
    assert not dest.exists()


def test_image_same_format_no_overwrite(tmp_path):
    src = tmp_path / "img.png"
    _make_image(src)
    before = src.read_bytes()
    res = media_ops.convert_image(str(src), "PNG", dry_run=False)
    assert src.read_bytes() == before
    assert res["success"] is False


def test_image_collision_detection(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dest = tmp_path / "dest"
    dir_a.mkdir()
    dir_b.mkdir()
    p1 = dir_a / "img.png"
    p2 = dir_b / "img.png"
    _make_image(p1, color=(255, 0, 0))
    _make_image(p2, color=(0, 255, 0))
    r1 = media_ops.convert_image(str(p1), "PNG", dry_run=False, output_dir=str(dest))
    r2 = media_ops.convert_image(str(p2), "PNG", dry_run=False, output_dir=str(dest))
    assert r1["output_path"] != r2["output_path"]
    assert os.path.exists(r1["output_path"])
    assert os.path.exists(r2["output_path"])


def test_atomic_output_cleanup_on_failure(tmp_path):
    src = _make_pdf(tmp_path / "src.pdf", pages=1)
    out = tmp_path / "compressed.pdf"
    with patch.object(PdfWriter, "write", side_effect=OSError("disk full")):
        res = media_ops.compress_pdf(str(src), str(out))
    assert res["success"] is False
    assert not list(tmp_path.glob("*.dataforge.tmp"))


def test_merge_atomic_output_no_temp_leftover(tmp_path):
    a = _make_pdf(tmp_path / "a.pdf", pages=1)
    b = _make_pdf(tmp_path / "b.pdf", pages=1)
    out = tmp_path / "merged.pdf"
    res = media_ops.merge_pdfs([str(a), str(b)], str(out))
    assert res["success"] is True
    assert os.path.exists(str(out))
    assert not list(tmp_path.glob("*.dataforge.tmp"))