"""TICK-922 contract tests for search + duplicates fixes.

Covers: stale search results, input validation, duplicate content
verification, inode-aware cache, path-role cleanup (P1.7).
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Offscreen for CI
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from dataforge.core.cache import CacheManager
from dataforge.core.common import FileEntry
from dataforge.core.hasher import get_file_hash
from dataforge.modules.search import build_search_query, search_files
from dataforge.ui.views.duplicates import DuplicatesView
from dataforge.ui.views.search import SearchView

_app = QApplication.instance() or QApplication([])


def _entry(path, content=b"same"):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_bytes(content)
    st = os.stat(p)
    return FileEntry(
        path=str(p),
        filename=p.name,
        extension=p.suffix,
        size=st.st_size,
        created_at=st.st_ctime,
        modified_at=st.st_mtime,
    )


# ---------------------------------------------------------------------------
# Search: stale results + input validation
# ---------------------------------------------------------------------------

def test_search_clears_previous_results(tmp_path):
    view = SearchView(None, app=MagicMock())
    view.entry_path.setText(str(tmp_path))
    view.current_results = ["stale result"]
    view.tree.insert("", "end", values=("txt", "stale.txt", "1 KB"), path=str(tmp_path / "stale.txt"))
    assert view.current_results
    view.start_search()
    assert view.current_results == []
    assert view.app.run_workflow.called


def test_search_invalid_path_raises(tmp_path):
    view = SearchView(None, app=MagicMock())
    view.entry_path.setText(str(tmp_path / "does_not_exist"))
    view.start_search()
    args = view.app.show_error_dialog.call_args
    assert args is not None
    assert "Search Error" in args[0]
    assert view.app.run_workflow.called is False


def test_search_negative_min_size_raises(tmp_path):
    view = SearchView(None, app=MagicMock())
    view.entry_path.setText(str(tmp_path))
    view.entry_min_size.setText("-1")
    view.start_search()
    args = view.app.show_error_dialog.call_args
    assert args is not None
    assert "min_size" in args[0][1]
    assert view.app.run_workflow.called is False


def test_search_min_greater_than_max_raises(tmp_path):
    view = SearchView(None, app=MagicMock())
    view.entry_path.setText(str(tmp_path))
    view.entry_min_size.setText("1000")
    view.entry_max_size.setText("100")
    view.start_search()
    args = view.app.show_error_dialog.call_args
    assert args is not None
    assert "min_size" in args[0][1]
    assert view.app.run_workflow.called is False


def test_search_valid_params_succeeds(tmp_path):
    view = SearchView(None, app=MagicMock())
    view.entry_path.setText(str(tmp_path))
    view.entry_min_size.setText("0")
    view.start_search()
    assert view.app.show_error_dialog.called is False
    assert view.app.run_workflow.called


def test_search_empty_pattern_matches_all(tmp_path):
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text(f"content {i}")
    query = build_search_query(name_pattern=None)
    results = search_files(str(tmp_path), query)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# Duplicates: content verification + path-role cleanup
# ---------------------------------------------------------------------------

def test_duplicate_select_extras_verifies_content(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    _entry(str(a), b"identical")
    _entry(str(b), b"identical")
    entry_a = _entry(str(a))
    entry_b = _entry(str(b))
    view = DuplicatesView(None, app=MagicMock())
    view.preview_panel = MagicMock()
    view.entry_path.setText(str(tmp_path))
    view.current_results = {"deadbeef": [entry_a, entry_b]}
    view._refresh_visible_results()
    # Tamper with b after the scan: content no longer matches its keeper.
    b.write_bytes(b"TAMPERED CONTENT")
    view.select_extras()
    selected_ids = set(view.tree.selection())
    selected_paths = {
        view.item_records[iid]["entry"].path for iid in selected_ids
        if iid in view.item_records
    }
    assert str(b) not in selected_paths, "changed file must not be selected"


def test_duplicate_action_always_verifies(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    _entry(str(a), b"same")
    _entry(str(b), b"same")
    view = DuplicatesView(None, app=MagicMock())
    view.preview_panel = MagicMock()
    view.entry_path.setText(str(tmp_path))
    view.current_results = {"deadbeef": [_entry(str(a)), _entry(str(b))]}
    view._refresh_visible_results()
    with patch("dataforge.ui.views.duplicates.select_duplicate_records", return_value=[]) as mocked:
        view.select_extras()
    assert mocked.called
    assert mocked.call_args.kwargs.get("verify_content") is True


def test_manual_selection_targets_byte_verified(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    _entry(str(a), b"same")
    _entry(str(b), b"same")
    group_hash = get_file_hash(str(a), "sha256")
    view = DuplicatesView(None, app=MagicMock())
    view.entry_path.setText(str(tmp_path))
    view.hash_algo_combo.setCurrentText("sha256")
    view.current_results = {group_hash: [_entry(str(a)), _entry(str(b))]}
    view._refresh_visible_results()
    id_a = next(iid for iid, rec in view.item_records.items() if rec["entry"].path == str(a))
    id_b = next(iid for iid, rec in view.item_records.items() if rec["entry"].path == str(b))
    view.tree.selection_set([id_a, id_b])
    # Tamper with b after scan: it must be dropped from destructive targets
    # while the unchanged a still passes re-verification.
    b.write_bytes(b"TAMPERED")
    targets = view._selected_targets()
    paths = {t["source_path"] for t in targets}
    assert str(a) in paths
    assert str(b) not in paths


def test_path_role_cleared_on_rebuild(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    c = tmp_path / "c.txt"
    _entry(str(a), b"same")
    _entry(str(b), b"same")
    view = DuplicatesView(None, app=MagicMock())
    view.entry_path.setText(str(tmp_path))
    view.current_results = {"deadbeef": [_entry(str(a)), _entry(str(b))]}
    view._refresh_visible_results()
    assert view.tree._item_path_role, "expected path roles populated during rebuild"
    # Rebuild with fewer rows: item ids are reused (item_map length resets),
    # so reused ids must resolve to the NEW paths, never the old ones.
    _entry(str(c), b"other")
    view.current_results = {"cafebabe": [_entry(str(c))]}
    view._refresh_visible_results()
    assert set(view.tree._item_path_role.values()) == {str(c)}, "stale path roles must not survive a rebuild"


# ---------------------------------------------------------------------------
# Cache: inode-aware invalidation
# ---------------------------------------------------------------------------

def test_cache_invalidated_on_inode_change(tmp_path):
    cm = CacheManager(db_path=str(tmp_path / "cache.db"))
    p = tmp_path / "f.bin"
    p.write_bytes(b"AAA")
    st = os.stat(p)
    cm.set_hash(str(p), st.st_size, st.st_mtime, "hash_old", "md5", inode=st.st_ino)
    cm.flush()
    assert cm.get_hash(str(p), st.st_size, st.st_mtime, "md5", inode=st.st_ino) == "hash_old"
    # Replace the file with a different one of the SAME size and mtime but a
    # new inode (rename swap guarantees a distinct inode while old is live).
    p2 = tmp_path / "f2.bin"
    p2.write_bytes(b"BBB")
    os.utime(p2, (st.st_atime, st.st_mtime))
    new_st = os.stat(p2)
    assert new_st.st_ino != st.st_ino
    os.replace(p2, p)
    replaced_st = os.stat(p)
    assert replaced_st.st_ino == new_st.st_ino
    assert replaced_st.st_size == st.st_size
    assert replaced_st.st_mtime == st.st_mtime
    assert cm.get_hash(str(p), replaced_st.st_size, replaced_st.st_mtime, "md5", inode=replaced_st.st_ino) is None