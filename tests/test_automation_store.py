"""TICK-806 — Automation store custom automations (Wave 8)."""
import json
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMessageBox

_app = QApplication.instance() or QApplication([])


def _sanitize(name: str) -> str:
    import re
    s = re.sub(r'[^a-zA-Z0-9._-]', '_', (name or "").strip() or "automation")
    s = re.sub(r'_+', '_', s).strip('._')
    return s[:80] or "automation"


@pytest.fixture
def tmp_exports(tmp_path, monkeypatch):
    # Patch all places that read exports_dir
    monkeypatch.setattr("dataforge.core.paths.exports_dir", tmp_path)
    # Also patch the already-imported modules' reference
    try:
        import dataforge.ui.views.automations as autom_mod
        monkeypatch.setattr(autom_mod._paths, "exports_dir", tmp_path, raising=False)
    except Exception:
        pass
    try:
        import dataforge.core.paths as paths_mod
        monkeypatch.setattr(paths_mod, "exports_dir", tmp_path, raising=False)
    except Exception:
        pass
    # Ensure empty automations dir
    autom_dir = tmp_path / "automations"
    if autom_dir.exists():
        for p in autom_dir.glob("*.json"):
            try:
                p.unlink()
            except Exception:
                pass
    return tmp_path


def test_no_saved_shows_3_defaults(tmp_exports):
    from dataforge.ui.views.automations import AutomationsView
    view = AutomationsView(None, app=MagicMock())
    assert view.list_widget.count() == 3
    names = [view.list_widget.item(i).text() for i in range(view.list_widget.count())]
    assert "Clean Duplicates" in names
    assert "Organize by Date" in names
    assert "Forensic Triage" in names
    # Files created on disk
    for n in names:
        assert (tmp_exports / "automations" / f"{_sanitize(n)}.json").exists()


def test_save_creates_json_and_appears_in_list(tmp_exports):
    from dataforge.ui.views.automations import AutomationsView
    view = AutomationsView(None, app=MagicMock())
    # Build custom automation via builder
    view.action_builder.from_dict({"steps": [{"type": "DeleteStep", "params": {}}]})
    # Save As
    with patch("dataforge.ui.views.automations.QInputDialog.getText", return_value=("My Custom", True)):
        view._on_save_as()
    sanitized = _sanitize("My Custom")
    assert (tmp_exports / "automations" / f"{sanitized}.json").exists()
    assert view.list_widget.count() == 4
    names = [view.list_widget.item(i).text() for i in range(view.list_widget.count())]
    assert "My Custom" in names
    # Content
    data = json.loads((tmp_exports / "automations" / f"{sanitized}.json").read_text(encoding="utf-8"))
    assert data["name"] == "My Custom"
    assert isinstance(data["steps"], list)
    assert any(s.get("type") == "DeleteStep" for s in data["steps"])
    assert "created_at" in data and "updated_at" in data


def test_modify_update(tmp_exports):
    from dataforge.ui.views.automations import AutomationsView
    view = AutomationsView(None, app=MagicMock())
    # Select first default
    view.list_widget.setCurrentRow(0)
    orig_name = view.list_widget.currentItem().text()
    # Modify builder: add MoveStep
    view.action_builder.from_dict({"steps": [{"type": "MoveStep", "params": {"dest": "/tmp"}}]})
    # Update (Save)
    view._on_save()
    path = tmp_exports / "automations" / f"{_sanitize(orig_name)}.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert any(s.get("type") == "MoveStep" for s in data["steps"])
    # List still same count but reflects change
    assert view.list_widget.count() == 3
    # updated_at should be recent iso format
    assert "updated_at" in data


def test_delete(tmp_exports):
    from dataforge.ui.views.automations import AutomationsView
    view = AutomationsView(None, app=MagicMock())
    assert view.list_widget.count() == 3
    view.list_widget.setCurrentRow(1)
    name = view.list_widget.currentItem().text()
    sanitized = _sanitize(name)
    assert (tmp_exports / "automations" / f"{sanitized}.json").exists()
    with patch("dataforge.ui.views.automations.QMessageBox.question", return_value=QMessageBox.Yes):
        view._on_delete()
    assert not (tmp_exports / "automations" / f"{sanitized}.json").exists()
    assert view.list_widget.count() == 2
    names = [view.list_widget.item(i).text() for i in range(view.list_widget.count())]
    assert name not in names


def test_app_restart_loads_from_disk(tmp_exports):
    from dataforge.ui.views.automations import AutomationsView
    view1 = AutomationsView(None, app=MagicMock())
    view1.action_builder.from_dict({"steps": [{"type": "CopyStep", "params": {"dest": "/tmp"}}]})
    with patch("dataforge.ui.views.automations.QInputDialog.getText", return_value=("Persisted", True)):
        view1._on_save_as()
    assert view1.list_widget.count() == 4
    # Simulate restart: new view instance with same tmp_exports
    view2 = AutomationsView(None, app=MagicMock())
    assert view2.list_widget.count() == 4
    names = [view2.list_widget.item(i).text() for i in range(view2.list_widget.count())]
    assert "Persisted" in names
    # Verify builder loads correctly when selecting
    for i in range(view2.list_widget.count()):
        if view2.list_widget.item(i).text() == "Persisted":
            view2.list_widget.setCurrentRow(i)
            break
    # Builder should have the steps after selection change (via _on_selection_changed)
    assert any(s.__class__.__name__ == "CopyStep" for s in view2.action_builder.steps)


def test_action_builder_serialization(tmp_exports):
    from dataforge.ui.views.action_builder import ActionBuilderView
    view = ActionBuilderView(None, app=MagicMock())
    view.from_dict({"steps": [{"type": "SearchFilter", "params": {"pattern": "*.txt"}}, {"type": "DeleteStep", "params": {}}]})
    assert len(view.steps) == 2
    assert view.steps[0].__class__.__name__ == "SearchFilter"
    assert view.steps[0].params.get("pattern") == "*.txt"
    d = view.to_dict()
    assert d["steps"][0]["type"] == "SearchFilter"
    assert d["steps"][0]["params"]["pattern"] == "*.txt"
    # load_automation wrapper
    view2 = ActionBuilderView(None, app=MagicMock())
    view2.load_automation({"name": "Wrap", "steps": [{"type": "MoveStep", "params": {"dest": "/tmp"}}], "created_at": "now", "updated_at": "now"})
    assert len(view2.steps) == 1
    assert view2.steps[0].__class__.__name__ == "MoveStep"
    # roundtrip via from_dict
    view3 = ActionBuilderView(None, app=MagicMock())
    view3.from_dict(d)
    assert len(view3.steps) == 2
    assert view3.steps[1].__class__.__name__ == "DeleteStep"


def test_action_builder_to_dict_from_dict_with_path(tmp_exports):
    from dataforge.ui.views.action_builder import ActionBuilderView
    view = ActionBuilderView(None, app=MagicMock())
    view.entry_path.setText("/tmp/source")
    view.chk_recursive.setChecked(False)
    view.spin_depth.setValue(3)
    view.from_dict({"steps": [{"type": "SizeFilter", "params": {"min_mb": "1"}}]})
    d = view.to_dict()
    assert "steps" in d
    # from_dict should restore path etc if present
    view2 = ActionBuilderView(None, app=MagicMock())
    view2.from_dict({"path": "/tmp/other", "recursive": True, "depth": 2, "steps": []})
    assert view2.entry_path.text() == "/tmp/other"
    assert view2.chk_recursive.isChecked() is True
    assert view2.spin_depth.value() == 2


def test_daemon_list_and_schedule(tmp_exports):
    # Ensure defaults exist via AutomationsView
    from dataforge.ui.views.automations import AutomationsView
    _ = AutomationsView(None, app=MagicMock())
    from dataforge.engine.daemon import Daemon
    daemon = Daemon()
    autos = daemon.list_automations()
    assert len(autos) == 3
    names = [a.get("name") for a in autos]
    assert "Clean Duplicates" in names
    # get single
    data = daemon.get_automation("Clean Duplicates")
    assert data is not None
    assert data["name"] == "Clean Duplicates"
    # schedule
    result = daemon.schedule_automation("Clean Duplicates", source=str(tmp_exports), dry_run=True)
    assert "job_id" in result
    # check job exists
    job = daemon.get(result["job_id"])
    assert job is not None


def test_duplicate_creates_copy(tmp_exports):
    from dataforge.ui.views.automations import AutomationsView
    view = AutomationsView(None, app=MagicMock())
    view.list_widget.setCurrentRow(0)
    orig = view.list_widget.currentItem().text()
    view._on_duplicate()
    assert view.list_widget.count() == 4
    names = [view.list_widget.item(i).text() for i in range(view.list_widget.count())]
    assert any("Copy" in n for n in names)
    # Original still exists
    assert orig in names


def test_store_includes_timestamps(tmp_exports):
    from dataforge.ui.views.automations import AutomationsView
    view = AutomationsView(None, app=MagicMock())
    view.action_builder.from_dict({"steps": []})
    with patch("dataforge.ui.views.automations.QInputDialog.getText", return_value=("TS Test", True)):
        view._on_save_as()
    data = json.loads((tmp_exports / "automations" / f"{_sanitize('TS Test')}.json").read_text(encoding="utf-8"))
    assert "created_at" in data
    assert "updated_at" in data
    # Update should keep created_at but change updated_at
    import time
    old_created = data["created_at"]
    old_updated = data["updated_at"]
    time.sleep(0.01)
    view.list_widget.setCurrentRow(view.list_widget.count() - 1)  # TS Test
    view.action_builder.from_dict({"steps": [{"type": "ZipStep", "params": {}}]})
    view._on_save()
    data2 = json.loads((tmp_exports / "automations" / f"{_sanitize('TS Test')}.json").read_text(encoding="utf-8"))
    assert data2["created_at"] == old_created
    assert data2["updated_at"] != old_updated
