"""TICK-924 — UI Media: path precedence, immutable preview snapshot, worker tree safety, collision detection."""
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from dataforge.ui.views.media import MediaView  # noqa: E402


def _view():
    return MediaView(None, app=MagicMock())


def test_path_precedence_with_empty_values():
    view = _view()
    view.pdf_tree.get_item_path = MagicMock(return_value="/real/path/file.pdf")
    view.pdf_tree.item = MagicMock(return_value={"values": []})
    assert view._pdf_item_path("iid1") == "/real/path/file.pdf"


def test_path_precedence_with_values():
    view = _view()
    view.pdf_tree.get_item_path = MagicMock(return_value="")
    view.pdf_tree.item = MagicMock(return_value={"values": ["/shown/path/a.pdf", "1KB"]})
    assert view._pdf_item_path("iid1") == "/shown/path/a.pdf"


def test_merge_preview_captures_paths():
    view = _view()
    view.pdf_tree.get_children = MagicMock(return_value=["a", "b"])
    view.pdf_tree.item = MagicMock(side_effect=lambda iid: {"values": [f"/tmp/{iid}.pdf", "1KB"]})
    view.pdf_tree.get_item_path = MagicMock(return_value="")
    view.confirm_preview = MagicMock(return_value=True)
    outcome = {"requested": 2, "output_path": "/tmp/merged.pdf", "failed_paths": []}
    view._on_preview_pdf_merge_complete(outcome)
    assert view._merge_preview_paths == ["/tmp/a.pdf", "/tmp/b.pdf"]
    view.app.run_workflow.assert_called_once()


def test_merge_execute_uses_preview_paths():
    view = _view()
    view.pdf_tree.get_children = MagicMock(return_value=["a", "b"])
    view.pdf_tree.item = MagicMock(side_effect=lambda iid: {"values": [f"/tmp/{iid}.pdf", "1KB"]})
    view.pdf_tree.get_item_path = MagicMock(return_value="")
    view.confirm_preview = MagicMock(return_value=True)
    outcome = {"requested": 2, "output_path": "/tmp/merged.pdf", "failed_paths": []}
    view._on_preview_pdf_merge_complete(outcome)
    # Tree changes after the preview/confirm
    view.pdf_tree.get_children = MagicMock(return_value=[])
    view.pdf_tree.item = MagicMock(return_value={"values": []})
    args = view.app.run_workflow.call_args[0]
    assert args[0].__func__ is MediaView._pdf_merge_worker
    assert args[2] == ["/tmp/a.pdf", "/tmp/b.pdf"]


def test_img_convert_no_tree_access_in_worker():
    view = _view()
    view.img_tree = MagicMock()
    previews = [
        {"item_id": "x1", "source_path": "/tmp/a.png", "output_path": "/tmp/out/a.png", "size": "1KB"},
    ]
    with patch("dataforge.core.media_ops.convert_image", side_effect=OSError("boom")):
        result = view._img_convert_worker(previews, "PNG", 100, "/tmp/out", 90, 0, True)
    assert len(result["results"]) == 1
    assert result["results"][0]["size"] == "1KB"
    assert result["results"][0]["status"].startswith("Error")
    view.img_tree.item.assert_not_called()


def test_batch_collision_detected():
    view = _view()
    previews = [
        {"item_id": "x1", "source_path": "/tmp/a/img.png", "output_path": "/tmp/out/img.png", "size": "1KB"},
        {"item_id": "x2", "source_path": "/tmp/b/img.png", "output_path": "/tmp/out/img.png", "size": "1KB"},
    ]
    result = view._img_convert_worker(previews, "PNG", 100, "/tmp/out", 90, 0, True)
    assert result.get("collision") is True
    assert "Collision" in result["message"]


def test_batch_unique_basenames_succeed(tmp_path):
    view = _view()
    out_a = tmp_path / "a.png"
    out_b = tmp_path / "b.png"
    out_a.write_bytes(b"x")
    out_b.write_bytes(b"x")
    previews = [
        {"item_id": "x1", "source_path": "/tmp/a.png", "output_path": str(out_a), "size": "1KB"},
        {"item_id": "x2", "source_path": "/tmp/b.png", "output_path": str(out_b), "size": "1KB"},
    ]
    mapping = {p["source_path"]: p["output_path"] for p in previews}
    with patch("dataforge.core.media_ops.convert_image", side_effect=lambda *a, **k: {"output_path": mapping.get(a[0], "")}):
        result = view._img_convert_worker(previews, "PNG", 100, str(tmp_path), 90, 0, True)
    assert result.get("collision") is None
    assert len(result["results"]) == 2
    assert all(r["status"] == "Done" for r in result["results"])


def test_merge_empty_paths_aborted():
    view = _view()
    view.pdf_tree.get_children = MagicMock(return_value=["a"])
    view.pdf_tree.item = MagicMock(return_value={"values": []})
    view.pdf_tree.get_item_path = MagicMock(return_value="")
    view.confirm_preview = MagicMock(return_value=True)
    outcome = {"requested": 1, "output_path": "/tmp/merged.pdf", "failed_paths": []}
    view._on_preview_pdf_merge_complete(outcome)
    assert view._merge_preview_paths == []
    view.app.run_workflow.assert_not_called()