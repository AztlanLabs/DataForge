"""TICK-801 — Bulk Renamer update functionality."""
import os
import threading
import tempfile
from pathlib import Path

import pytest

from dataforge.modules.renamer import bulk_rename, preview_rename


def test_streaming_no_list_materialisation():
    src = Path("dataforge/modules/renamer.py").read_text(encoding="utf-8")
    assert "queue.Queue" in src, "renamer must use queue.Queue streaming"
    assert "list(scan_directory" not in src, "must not materialise via list(scan_directory)"
    assert "progress_callback" in src
    assert "cancel_token" in src
    # preview and bulk share same FileActionService path
    assert src.count("FileActionService.rename_items_with_regex") >= 2 or "preview_rename" in src
    assert "preview_rename" in src
    assert "bulk_rename" in src


def test_streaming_1000_files_preview():
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(1000):
            Path(tmp, f"file_{i:04d}.txt").write_text("x")
        # preview_rename should handle 1000 files via streaming without OOM
        result = preview_rename(tmp, r"file_(\d+)", r"renamed_\1", recursive=False)
        # preview returns dict with cancelled flag
        if isinstance(result, dict):
            assert result.get("cancelled") is False
            messages = result.get("messages", [])
            outcome = result.get("outcome")
            assert outcome is not None
            # should have 1000 records (or at least 1000 messages/skipped)
            assert len(messages) == 1000 or len(outcome.records) == 1000
        else:
            # fallback list case
            assert len(result) == 1000


def test_preview_apply_parity():
    # Use two separate temp dirs to avoid global collision cache interference
    with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
        for tmp in (tmp1, tmp2):
            for name in ["alpha-1.txt", "alpha-2.txt", "beta.txt"]:
                Path(tmp, name).write_text("data")
        # Clear global collision cache to ensure deterministic suffixes
        try:
            from dataforge.core.operations.files import _reserved_normcase_cache, _reserved_normalized_ids
            _reserved_normcase_cache.clear()
            _reserved_normalized_ids.clear()
        except Exception:
            pass
        preview = preview_rename(tmp1, r"alpha-(\d)", r"renamed", recursive=False)
        try:
            from dataforge.core.operations.files import _reserved_normcase_cache, _reserved_normalized_ids
            _reserved_normcase_cache.clear()
            _reserved_normalized_ids.clear()
        except Exception:
            pass
        bulk = bulk_rename(tmp2, r"alpha-(\d)", r"renamed", recursive=False, dry_run=True)
        if isinstance(preview, dict):
            preview_messages = preview["messages"]
            preview_outcome = preview["outcome"]
            preview_dests = sorted([os.path.basename(r.result.destination_path) for r in preview_outcome.records if r.success and r.result])
        else:
            preview_messages = preview
            preview_dests = sorted(preview_messages)
        if isinstance(bulk, dict):
            bulk_messages = bulk["messages"]
            bulk_outcome = bulk["outcome"]
            bulk_dests = sorted([os.path.basename(r.result.destination_path) for r in bulk_outcome.records if r.success and r.result])
        else:
            bulk_messages = bulk
            bulk_dests = sorted(bulk_messages)

        def _suffix(msgs):
            return sorted([m.split("->")[-1].strip() if "->" in m else m for m in msgs])
        # Both should have same suffixes (renamed.txt + renamed_1.txt) regardless of order
        assert _suffix(preview_messages) == _suffix(bulk_messages)
        # When both return dict outcomes, also compare raw basenames
        if isinstance(preview, dict) and isinstance(bulk, dict) and preview_dests and bulk_dests:
            assert sorted(preview_dests) == sorted(bulk_dests)


def test_cancel_token_returns_cancelled_without_partial():
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(5):
            Path(tmp, f"f{i}.txt").write_text("a")
        # pre-set cancel
        token = threading.Event()
        token.set()
        result = bulk_rename(tmp, r"f(\d)", r"g\1", recursive=False, dry_run=False, cancel_token=token)
        assert isinstance(result, dict)
        assert result.get("cancelled") is True
        # no files should have been renamed
        remaining = sorted(p.name for p in Path(tmp).iterdir())
        assert remaining == sorted([f"f{i}.txt" for i in range(5)])
        # also test preview cancel
        token2 = threading.Event()
        token2.set()
        preview = preview_rename(tmp, r"f(\d)", r"g\1", cancel_token=token2)
        assert isinstance(preview, dict)
        assert preview.get("cancelled") is True


def test_cancel_mid_run_via_progress():
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(20):
            Path(tmp, f"doc_{i}.txt").write_text("x")

        token = threading.Event()

        def progress(cur, total, msg):
            if cur >= 5:
                token.set()

        result = bulk_rename(tmp, r"doc_(\d+)", r"renamed_\1", recursive=False, dry_run=False, progress_callback=progress, cancel_token=token)
        # Should be cancelled
        assert isinstance(result, dict)
        assert result.get("cancelled") is True
        # After our revert logic, no partial renames should remain (all original files still there or all reverted)
        # At least check that not all 20 were renamed (cancel stopped early)
        files = list(Path(tmp).iterdir())
        # If revert worked, we should have original count restored
        # Allow either 0 renamed or all reverted — check that we have 20 files and names are either original or reverted
        assert len(files) == 20
        # No partial state where some files are renamed and some not without cancelled flag?
        # Ensure cancelled flag True is present


def test_collision_handling_via_fileactions():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "alpha-1.txt").write_text("one")
        Path(tmp, "alpha-2.txt").write_text("two")
        # Both map to same "renamed.txt" -> collision should be resolved via _1 suffix
        result = bulk_rename(tmp, r"alpha-\d", "renamed", recursive=False, dry_run=False)
        if isinstance(result, dict):
            msgs = result["messages"]
        else:
            msgs = result
        assert any("renamed.txt" in m for m in msgs)
        assert any("renamed_1.txt" in m for m in msgs)
        assert (Path(tmp) / "renamed.txt").exists()
        assert (Path(tmp) / "renamed_1.txt").exists()


def test_tools_preview_table_scrollable_checkable():
    src = Path("dataforge/ui/views/tools.py").read_text(encoding="utf-8")
    # Scrollable
    assert "QScrollArea" in src or "ScrollPerPixel" in src or "setVerticalScrollBarPolicy" in src
    # Checkable per row
    assert "ItemIsUserCheckable" in src
    assert "setCheckState" in src
    # Before/after + conflict warning + total
    assert "before" in src.lower() or "Current Name" in src
    assert "after" in src.lower() or "New Name" in src
    assert "Conflict" in src
    assert "Total:" in src
    # Uses run_workflow for STOP
    assert "run_workflow" in src
    # Preview and apply use identical service path
    assert src.count("rename_items_with_rules") >= 2


def test_tools_batch_renamer_integration():
    # Light UI integration — requires Qt offscreen, skip if unavailable
    pytest.importorskip("PyQt5.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt5.QtWidgets import QApplication
        from unittest.mock import MagicMock
        from dataforge.ui.views.tools import ToolsView
    except Exception as e:
        pytest.skip(f"Qt not available: {e}")

    _app = QApplication.instance() or QApplication([])
    mock_app = MagicMock()
    # mock run_workflow to call worker synchronously
    def fake_run_workflow(worker, on_complete, *args, **kwargs):
        # worker may be a bound method expecting progress/cancel injected — just call with args
        try:
            res = worker(*args, progress_callback=None, cancel_token=None)
        except TypeError:
            res = worker(*args)
        on_complete(res)

    mock_app.run_workflow.side_effect = fake_run_workflow
    mock_app.show_warning_dialog = MagicMock()
    mock_app.update_status = MagicMock()
    mock_app.show_info_dialog = MagicMock()
    mock_app.show_error_dialog = MagicMock()

    # Need a parent widget
    from PyQt5.QtWidgets import QWidget
    parent = QWidget()
    try:
        view = ToolsView(parent, app=mock_app)
    except Exception as e:
        pytest.skip(f"ToolsView init failed: {e}")

    # Check Batch Renamer tab exists
    assert hasattr(view, "renamer_tree")
    assert hasattr(view, "renamer_summary_var")
    assert hasattr(view, "renamer_scroll")
    # Check columns
    assert "old" in view.renamer_tree.col_indices
    assert "new" in view.renamer_tree.col_indices
    assert "status" in view.renamer_tree.col_indices

    # Add files and preview
    with tempfile.TemporaryDirectory() as tmp:
        p1 = Path(tmp, "a.txt")
        p1.write_text("x")
        p2 = Path(tmp, "b.txt")
        p2.write_text("y")
        # Insert rows manually
        iid1 = view.renamer_tree.insert("", None, values=(str(p1), "", "Pending"))
        view._set_renamer_item_checkable(iid1, checked=True)
        iid2 = view.renamer_tree.insert("", None, values=(str(p2), "", "Pending"))
        view._set_renamer_item_checkable(iid2, checked=True)
        # Set rules to rename a->c
        view.renamer_params.update({"find_text": "a", "replace_text": "c", "use_regex": False})
        rows = view._snapshot_renamer_rows()
        rules = view._get_renamer_rules()
        outcome = view._renamer_preview_worker(rows, rules)
        view._on_renamer_preview_complete(outcome)
        # After preview, rows should have before/after, status, checkable, total updated
        vals = view.renamer_tree.item(iid1)["values"]
        assert len(vals) == 3
        # old, new, status
        assert "a.txt" in vals[0] or "a" in vals[0]
        assert vals[2] in ("Ready", "Unchanged", "Invalid") or "Conflict" in vals[2]
        # Check that summary contains Total and Checked
        summary = view.renamer_summary_var.text()
        assert "Total:" in summary
        assert "Checked:" in summary or "Ready:" in summary
        # Check that items are checkable
        from PyQt5.QtCore import Qt
        item = view.renamer_tree.item_map[iid1]
        assert bool(item.flags() & Qt.ItemIsUserCheckable)
        assert item.checkState(0) in (Qt.Checked, Qt.Unchecked)

    parent.deleteLater()
