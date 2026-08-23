"""TICK-903 — MediaTools PDF/Image rework + preview + malloc fix."""
import os
import threading
import tempfile
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from PIL import Image  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

from dataforge.core import media_ops  # noqa: E402


def _make_pdf(path, pages=1, text=None):
    writer = PdfWriter()
    for i in range(pages):
        writer.add_blank_page(width=200, height=200)
    # optionally we could add text but blank is fine
    with open(path, "wb") as f:
        writer.write(f)
    return path

def _make_encrypted_pdf(path):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("password")
    with open(path, "wb") as f:
        writer.write(f)
    return path

def _make_rgba_image(path):
    img = Image.new("RGBA", (64, 64), (255, 0, 0, 128))
    # Add some pattern
    img2 = Image.new("RGBA", (32, 32), (0, 255, 0, 200))
    img.paste(img2, (16, 16))
    img.save(path, "PNG")
    img.close()
    img2.close()
    return path


def test_merge_two_pdfs_one_bad(tmp_path):
    good = _make_pdf(tmp_path / "good.pdf", pages=2)
    bad = tmp_path / "bad.pdf"
    bad.write_text("not a pdf")
    out = tmp_path / "merged.pdf"
    res = media_ops.merge_pdfs([str(good), str(bad)], str(out), dry_run=False)
    assert res["merged"] == 1
    assert res["failed"] == 1
    assert str(bad) in res["failed_paths"]
    assert not res["cancelled"]
    assert not res["dry_run"]
    assert os.path.exists(str(out))
    # Verify output has 2 pages (only good file)
    r = PdfReader(str(out))
    assert len(r.pages) == 2

def test_merge_encrypted_handled(tmp_path):
    good = _make_pdf(tmp_path / "good2.pdf", pages=1)
    enc = _make_encrypted_pdf(tmp_path / "enc.pdf")
    out = tmp_path / "merged2.pdf"
    res = media_ops.merge_pdfs([str(good), str(enc)], str(out), dry_run=False)
    assert res["merged"] == 1
    assert res["failed"] == 1
    assert str(enc) in res["failed_paths"]
    assert os.path.exists(str(out))
    r = PdfReader(str(out))
    assert len(r.pages) == 1

def test_merge_dry_run_no_write(tmp_path):
    a = _make_pdf(tmp_path / "a.pdf", pages=1)
    b = _make_pdf(tmp_path / "b.pdf", pages=1)
    out = tmp_path / "should_not_exist.pdf"
    res = media_ops.merge_pdfs([str(a), str(b)], str(out), dry_run=True)
    assert res["dry_run"] is True
    assert res["merged"] == 2
    assert not os.path.exists(str(out))

def test_merge_cancel_token(tmp_path):
    a = _make_pdf(tmp_path / "c.pdf", pages=1)
    b = _make_pdf(tmp_path / "d.pdf", pages=1)
    out = tmp_path / "cancel.pdf"
    token = threading.Event()
    token.set()
    res = media_ops.merge_pdfs([str(a), str(b)], str(out), dry_run=False, cancel_token=token)
    assert res["cancelled"] is True

def test_split_creates_pages_and_dry_run(tmp_path):
    src = _make_pdf(tmp_path / "src.pdf", pages=3)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    # dry_run should return paths without writing
    dry = media_ops.split_pdf(str(src), str(out_dir), dry_run=True)
    assert dry["requested"] == 3
    assert len(dry["pages"]) == 3
    assert not any(os.path.exists(p) for p in dry["pages"])
    # real split
    real = media_ops.split_pdf(str(src), str(out_dir), dry_run=False)
    assert real["requested"] == 3
    assert len(real["pages"]) == 3
    for p in real["pages"]:
        assert os.path.exists(p)
        # each should be readable and have 1 page
        r = PdfReader(p)
        assert len(r.pages) == 1

def test_split_sanitize_and_cancel(tmp_path):
    src = _make_pdf(tmp_path / "my file @#$.pdf", pages=2)
    out_dir = tmp_path / "out2"
    # dry check sanitize
    dry = media_ops.split_pdf(str(src), str(out_dir), dry_run=True)
    assert dry["requested"] == 2
    # out_dir not exist yet, dry should still succeed but not create files
    # check sanitized base: "my_file___" ?
    for p in dry["pages"]:
        name = os.path.basename(p)
        # should not contain @ or # or space or $
        assert "@" not in name and "#" not in name and " " not in name and "$" not in name
    # cancel_token aborts mid-split
    src2 = _make_pdf(tmp_path / "big.pdf", pages=5)
    out_dir2 = tmp_path / "out_cancel"
    out_dir2.mkdir()
    token = threading.Event()
    # Simulate cancel after 2 pages via progress_callback setting token
    def progress(cur, total, msg=""):
        if cur >= 2:
            token.set()
    res = media_ops.split_pdf(str(src2), str(out_dir2), dry_run=False, progress_callback=progress, cancel_token=token)
    assert res["cancelled"] is True
    # pages list length should be 3 when cancelled after 2 (we append before check, so includes the page where cancel detected)
    assert 2 <= len(res["pages"]) <= 5
    # Should have at least 1 file exists but not all 5
    existing = [p for p in res["pages"] if os.path.exists(p)]
    assert 1 <= len(existing) < 5

def test_split_encrypted_and_too_large(tmp_path, monkeypatch):
    enc = _make_encrypted_pdf(tmp_path / "enc2.pdf")
    out_dir = tmp_path / "out_enc"
    out_dir.mkdir()
    res = media_ops.split_pdf(str(enc), str(out_dir), dry_run=False)
    # Should return error dict not raise
    assert "error" in res
    assert "Encrypted" in res["error"] or "encrypted" in res["error"].lower()
    # Test MAX_PDF_PAGES graceful: monkeypatch threshold low
    monkeypatch.setattr(media_ops, "MAX_PDF_PAGES", 1)
    src = _make_pdf(tmp_path / "many.pdf", pages=2)
    res2 = media_ops.split_pdf(str(src), str(out_dir), dry_run=False)
    assert "error" in res2
    assert "max" in res2["error"].lower()

def test_convert_image_rgba_threads(tmp_path):
    src = _make_rgba_image(tmp_path / "rgba.png")
    # Call convert_image 10 times rapidly from threads
    outs = []
    errors = []

    def worker(idx):
        try:
            out = media_ops.convert_image(str(src), "JPEG", resize_pct=50, dry_run=False)
            outs.append(out["output_path"])
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"errors: {errors}"
    assert len(outs) == 10
    for p in outs:
        assert os.path.exists(p)
        # verify RGB mode
        with Image.open(p) as im:
            im.load()
            copy = im.copy()
            assert copy.mode == "RGB"
            copy.close()

def test_convert_image_copy_pattern_used():
    import inspect
    src = inspect.getsource(media_ops.convert_image)
    # Must use .copy() pattern for malloc fix
    assert ".copy()" in src
    # Should use with Image.open
    assert "with Image.open" in src
    # Should handle output_dir
    assert "output_dir" in src

def test_convert_image_dest_folder_and_quality(tmp_path):
    # 5 images + dest folder
    dest = tmp_path / "dest"
    dest.mkdir()
    sources = []
    for i in range(5):
        p = tmp_path / f"img{i}.png"
        # create simple image
        im = Image.new("RGB", (20, 20), (i*40, 0, 0))
        im.save(str(p), "PNG")
        im.close()
        sources.append(str(p))

    progress_calls = []

    def progress(cur, total, msg=""):
        progress_calls.append((cur, total))

    for src in sources:
        res = media_ops.convert_image(src, "JPEG", resize_pct=100, dry_run=False, output_dir=str(dest), quality=75, rotate=90, preserve_exif=True, progress_callback=progress)
        assert os.path.exists(res["output_path"])
        # Should be in dest folder, not overwriting source
        assert os.path.dirname(os.path.abspath(res["output_path"])) == os.path.abspath(str(dest))
        # source still exists as PNG (not overwritten)
        assert os.path.exists(src)
        # dest file is JPEG
        with Image.open(res["output_path"]) as im:
            assert im.format == "JPEG"
            # rotated size maybe different due to expand? 20x20 square same
            assert im.size[0] >= 20

    assert len(progress_calls) >= 5
    # ensure 5 files in dest (JPEG may be .jpeg or .jpg depending on target)
    assert len(list(dest.glob("*.jpg")) + list(dest.glob("*.jpeg"))) == 5

def test_convert_image_output_dir_same_as_source(tmp_path):
    src = tmp_path / "orig.png"
    im = Image.new("RGB", (10, 10), (0, 255, 0))
    im.save(str(src), "PNG")
    im.close()
    # No dest -> should save next to source with new name
    res = media_ops.convert_image(str(src), "WEBP", resize_pct=100, dry_run=False)
    assert os.path.exists(res["output_path"])
    assert os.path.dirname(res["output_path"]) == str(tmp_path)
    assert res["output_path"] != str(src)

def test_compress_dry_and_real(tmp_path):
    src = _make_pdf(tmp_path / "to_compress.pdf", pages=2)
    out = tmp_path / "compressed.pdf"
    dry = media_ops.compress_pdf(str(src), str(out), quality="low", dry_run=True)
    assert dry["dry_run"] is True
    assert dry["ratio"] is not None
    assert not os.path.exists(str(out))
    real = media_ops.compress_pdf(str(src), str(out), quality="medium", dry_run=False)
    assert not real["cancelled"]
    assert real["ratio"] is not None or real.get("success")
    assert os.path.exists(str(out))
    # ratio should be < 1.5? compressed may be similar size
    if real["ratio"] is not None:
        assert 0 < real["ratio"] < 5

def test_convert_pdf_missing_dep_handling(tmp_path, monkeypatch):
    src = _make_pdf(tmp_path / "conv.pdf", pages=1)
    out_jpg = tmp_path / "out.jpg"
    # Simulate missing pymupdf: monkeypatch import to fail
    import builtins
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in ("pymupdf", "fitz", "pdf2docx", "tabula", "camelot"):
            raise ImportError(f"No module named '{name}'")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        res = media_ops.convert_pdf(str(src), str(out_jpg), to="jpg", dry_run=False)
        assert res["success"] is False
        assert "Install pymupdf" in res["message"]
        # docx missing
        out_docx = tmp_path / "out.docx"
        res2 = media_ops.convert_pdf(str(src), str(out_docx), to="docx", dry_run=False)
        assert res2["success"] is False
        assert "Install pdf2docx" in res2["message"]
        # xlsx missing
        out_xlsx = tmp_path / "out.xlsx"
        res3 = media_ops.convert_pdf(str(src), str(out_xlsx), to="xlsx", dry_run=False)
        assert res3["success"] is False
        assert "Install tabula-py" in res3["message"] or "Install" in res3["message"]

    # dry_run should succeed even without deps? For jpg dry_run uses pypdf count path
    res_dry = media_ops.convert_pdf(str(src), str(out_jpg), to="jpg", dry_run=True)
    assert res_dry["success"] is True or "Would convert" in res_dry["message"]

def test_media_view_pdf_move_and_sorting():
    from dataforge.ui.views.media import MediaView
    view = MediaView(None, app=MagicMock())
    # Ensure sorting disabled
    assert view.pdf_tree.tree.isSortingEnabled() is False
    # Add 3 PDFs via direct insert
    view.pdf_tree.insert("", None, values=("/tmp/a.pdf", "1KB"))
    view.pdf_tree.insert("", None, values=("/tmp/b.pdf", "2KB"))
    view.pdf_tree.insert("", None, values=("/tmp/c.pdf", "3KB"))
    children = view.pdf_tree.get_children()
    assert len(children) == 3
    # Order should be a,b,c
    vals = [view.pdf_tree.item(cid)['values'][0] for cid in children]
    assert vals == ["/tmp/a.pdf", "/tmp/b.pdf", "/tmp/c.pdf"]
    # Select middle item (b)
    mid = children[1]
    view.pdf_tree.selection_set([mid])
    # Move Up
    view.pdf_up()
    children2 = view.pdf_tree.get_children()
    vals2 = [view.pdf_tree.item(cid)['values'][0] for cid in children2]
    assert vals2 == ["/tmp/b.pdf", "/tmp/a.pdf", "/tmp/c.pdf"]
    # Move Down (should go back)
    view.pdf_down()
    children3 = view.pdf_tree.get_children()
    vals3 = [view.pdf_tree.item(cid)['values'][0] for cid in children3]
    assert vals3 == ["/tmp/a.pdf", "/tmp/b.pdf", "/tmp/c.pdf"]
    # Simulate header click trying to sort - ensure sorting stays disabled and move still works
    # Try enabling sorting then header click? Our view disables sorting; even if we sort via tree, manual move should still work after disabling
    try:
        view.pdf_tree.tree.setSortingEnabled(True)
        view.pdf_tree.tree.sortItems(0, 0)
        # Re-disable as MediaView does on move
        view.pdf_tree.tree.setSortingEnabled(False)
    except Exception:
        pass
    # Move middle again should still work
    view.pdf_tree.selection_set([children3[1]])
    view._move_item(-1)
    vals4 = [view.pdf_tree.item(cid)['values'][0] for cid in view.pdf_tree.get_children()]
    assert vals4[0] == "/tmp/b.pdf"

def test_media_view_pdf_preview_updates():
    from dataforge.ui.views.media import MediaView
    view = MediaView(None, app=MagicMock())
    # Insert a PDF
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.close()
    _make_pdf(tmp.name, pages=1)
    iid = view.pdf_tree.insert("", None, values=(tmp.name, "1KB"))
    # Mock preview
    with patch.object(view.pdf_preview, "update_file") as mock_update:
        view.pdf_tree.selection_set([iid])
        view.on_pdf_select()
        mock_update.assert_called()
        # Check called with correct path
        called_path = mock_update.call_args[0][0]
        assert called_path == tmp.name or tmp.name in called_path
    os.unlink(tmp.name)

def test_media_view_page_expand_and_move(tmp_path):
    from dataforge.ui.views.media import MediaView
    view = MediaView(None, app=MagicMock())
    src = _make_pdf(tmp_path / "pages.pdf", pages=3)
    iid = view.pdf_tree.insert("", None, values=(str(src), "1KB"))
    view.pdf_tree.selection_set([iid])
    view.pdf_expand_pages()
    children = view.pdf_tree.get_children(iid)
    assert len(children) == 3
    # Check labels
    labels = [view.pdf_tree.item(cid)['values'][0] for cid in children]
    assert labels == ["Page 1", "Page 2", "Page 3"]
    # Move middle page up
    mid = children[1]
    view.pdf_tree.selection_set([mid])
    view.pdf_up()
    children2 = view.pdf_tree.get_children(iid)
    labels2 = [view.pdf_tree.item(cid)['values'][0] for cid in children2]
    assert labels2 == ["Page 2", "Page 1", "Page 3"]
    # Collapse
    view.pdf_tree.selection_set([iid])
    view.pdf_collapse_pages()
    assert len(view.pdf_tree.get_children(iid)) == 0

def test_media_view_has_advanced_and_image_options():
    from dataforge.ui.views.media import MediaView
    view = MediaView(None, app=MagicMock())
    # PDF Advanced
    assert hasattr(view, "pdf_compress_button")
    assert hasattr(view, "pdf_convert_button")
    assert hasattr(view, "pdf_compress_quality")
    assert hasattr(view, "pdf_convert_combo")
    assert view.pdf_compress_quality.count() == 3
    assert view.pdf_convert_combo.count() == 3
    # Image batch new options
    assert hasattr(view, "img_dest_entry")
    assert hasattr(view, "img_quality_spin")
    assert hasattr(view, "img_rotate_combo")
    assert hasattr(view, "img_exif_check")
    # Check defaults
    assert view.img_quality_spin.value() == 90
    assert view.img_exif_check.isChecked() is True
    # New preview splitter exists
    assert hasattr(view, "pdf_splitter")
    assert hasattr(view, "pdf_preview")

def test_media_ops_compress_and_convert_buttons_missing_dep_dialog():
    # This tests UI path: compress/convert with missing dep shows Install message not crash
    from dataforge.ui.views.media import MediaView
    app = MagicMock()
    view = MediaView(None, app=app)
    # Mock dialogs to return paths
    tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_pdf.close()
    _make_pdf(tmp_pdf.name, pages=1)
    iid = view.pdf_tree.insert("", None, values=(tmp_pdf.name, "1KB"))
    view.pdf_tree.selection_set([iid])
    # Mock convert to trigger missing dep
    with patch("dataforge.core.media_ops.convert_pdf") as mock_convert:
        mock_convert.return_value = {"success": False, "message": "Install pymupdf to convert PDF to JPG (pip install pymupdf)", "to": "jpg", "input_path": tmp_pdf.name, "output_path": "/tmp/out.jpg", "cancelled": False}
        # Need to simulate _on_preview_pdf_convert_complete with missing dep
        # First preview dry_run returns missing dep
        with patch.object(view, "confirm_preview"):
            view._on_preview_pdf_convert_complete(mock_convert.return_value)
            # Should show warning dialog with Install
            app.show_warning_dialog.assert_called()
            args, kwargs = app.show_warning_dialog.call_args
            assert "Install pymupdf" in str(args) or "Install pymupdf" in str(kwargs)
    os.unlink(tmp_pdf.name)
