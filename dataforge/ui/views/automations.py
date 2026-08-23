"""
Automations GUI view — TICK-806 + TICK-907 collapsible UX.

Hosts the Automation Store (exports_dir/automations/*.json) alongside the
Action Builder and Tools. Saved Automations is now a CollapsibleCard on top
(vertical QVBoxLayout) instead of a fixed horizontal QSplitter side panel,
to save horizontal space when the user is focused on building actions.

Store file schema: {"name": str, "steps": [{"type": str, "params": dict}, ...],
"created_at": iso, "updated_at": iso}
"""
import datetime
import json
import re
from pathlib import Path

from PyQt5.QtWidgets import (
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QTabWidget, QVBoxLayout, QInputDialog, QLabel
)
from PyQt5.QtCore import Qt

from .base import BaseView
from .action_builder import ActionBuilderView
from .tools import ToolsView
from ..widgets import CollapsibleCard, FlowContainer, FlowLayout
from ...core.config import config
import dataforge.core.paths as _paths


def _sanitize_filename(name: str) -> str:
    s = (name or "").strip()
    if not s:
        s = "automation"
    # Replace invalid chars with underscore, keep alnum, dot, dash, underscore
    s = re.sub(r'[^a-zA-Z0-9._-]', '_', s)
    s = re.sub(r'_+', '_', s).strip('._')
    if not s:
        s = "automation"
    # Limit length
    if len(s) > 80:
        s = s[:80]
    return s


def _store_dir() -> Path:
    try:
        base = Path(_paths.exports_dir)
    except Exception:
        base = Path.home() / "Documents" / "DataForge"
    return base / "automations"


def _automation_path(name: str) -> Path:
    return _store_dir() / f"{_sanitize_filename(name)}.json"


def _now_iso() -> str:
    try:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()
    except Exception:
        return datetime.datetime.utcnow().isoformat() + "Z"


DEFAULT_AUTOMATIONS: list[dict] = [
    {
        "name": "Clean Duplicates",
        "steps": [
            {"type": "DuplicateFilter", "params": {"mode": "All Duplicates"}},
            {"type": "DeleteStep", "params": {}},
        ],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        "name": "Organize by Date",
        "steps": [
            {"type": "DateFilter", "params": {"mode": "Older", "days": "30"}},
            {"type": "OrganizeStep", "params": {"dest": "", "mode": "Move"}},
        ],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
    {
        "name": "Forensic Triage",
        "steps": [
            {"type": "SignatureMismatchFilter", "params": {}},
            {"type": "HashLogStep", "params": {"algo": "sha256"}},
        ],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    },
]


def _ensure_store_defaults() -> None:
    """Ensure store dir exists and contains default examples if empty."""
    store = _store_dir()
    try:
        store.mkdir(parents=True, exist_ok=True)
    except Exception:
        return
    try:
        existing = [p for p in store.glob("*.json") if p.is_file()]
    except Exception:
        existing = []
    if existing:
        return
    # No files — write defaults
    for tmpl in DEFAULT_AUTOMATIONS:
        name = tmpl.get("name", "automation")
        path = _automation_path(name)
        if path.exists():
            continue
        data = dict(tmpl)
        # Refresh timestamps if placeholder
        now = _now_iso()
        if data.get("created_at") == "2026-01-01T00:00:00+00:00":
            data["created_at"] = now
            data["updated_at"] = now
        try:
            # Ensure parent exists
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            continue


def _load_all_automations() -> list[dict]:
    store = _store_dir()
    try:
        store.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    # Ensure defaults if empty
    _ensure_store_defaults()
    out: list[dict] = []
    try:
        for p in sorted(store.glob("*.json")):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                # Ensure name present (fallback to filename)
                if not data.get("name"):
                    data["name"] = p.stem
                # Ensure steps present
                if "steps" not in data:
                    data["steps"] = []
                out.append(data)
            except Exception:
                continue
    except Exception:
        pass
    # Sort by name for stable list order
    out.sort(key=lambda d: d.get("name", "").lower())
    return out


def _get_initial_collapsed() -> bool:
    """Return True if Saved Automations should start collapsed.

    Reads persisted state from ``config.get("ui_checkbox_states")["automations.saved_collapsed"]``
    first, then ``collapsed_groups`` for back-compat. Default is collapsed (True) to save space.
    """
    try:
        cbs = config.get("ui_checkbox_states", {}) or {}
        if isinstance(cbs, dict) and "automations.saved_collapsed" in cbs:
            return bool(cbs["automations.saved_collapsed"])
        # also support alternative key without dot (defensive)
        if isinstance(cbs, dict) and "automations_saved_collapsed" in cbs:
            return bool(cbs["automations_saved_collapsed"])
        # Fallback to collapsed_groups list (app.py style)
        cg = config.get("collapsed_groups", []) or []
        if isinstance(cg, (list, tuple, set)):
            if "automations.saved" in cg or "Saved Automations" in cg or "automations" in cg:
                return True
            # if collapsed_groups exists but does not contain our key and we have no ui_checkbox_states entry,
            # default is still collapsed True (spec default) — do not infer expanded.
    except Exception:
        pass
    return True


class AutomationsView(BaseView):
    def get_title(self):
        return "Automations"

    def __init__(self, master, app=None):
        super().__init__(master, app)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        # Top: CollapsibleCard titled "Saved Automations" (expanded=False by default)
        initial_collapsed = _get_initial_collapsed()
        initial_expanded = not initial_collapsed
        self.card_saved = CollapsibleCard(self, title="Saved Automations", expanded=initial_expanded)
        self.card_saved.setObjectName("savedAutomationsCard")
        outer.addWidget(self.card_saved)

        body = self.card_saved.get_body()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(6, 6, 6, 6)
        body_layout.setSpacing(6)

        # List
        self.list_widget = QListWidget(body)
        self.list_widget.setObjectName("automationList")
        # Compact height — card hides body when collapsed, but keep expanded height reasonable
        self.list_widget.setMinimumHeight(80)
        self.list_widget.setMaximumHeight(180)
        body_layout.addWidget(self.list_widget, 1)

        # Buttons inside FlowContainer for wrapping (Save/Save As/Delete/Duplicate)
        self.btn_save = QPushButton("Save", body)
        self.btn_save.setToolTip("Update selected automation with current builder steps")
        self.btn_save.clicked.connect(self._on_save)

        self.btn_save_as = QPushButton("Save As", body)
        self.btn_save_as.setToolTip("Save current builder as a new automation")
        self.btn_save_as.clicked.connect(self._on_save_as)

        self.btn_delete = QPushButton("Delete", body)
        self.btn_delete.setProperty("variant", "danger")
        self.btn_delete.clicked.connect(self._on_delete)

        self.btn_duplicate = QPushButton("Duplicate", body)
        self.btn_duplicate.clicked.connect(self._on_duplicate)

        flow = FlowContainer(body)
        flow_layout = FlowLayout(flow, margin=0, hspacing=4, vspacing=4)
        flow_layout.addWidget(self.btn_save)
        flow_layout.addWidget(self.btn_save_as)
        flow_layout.addWidget(self.btn_delete)
        flow_layout.addWidget(self.btn_duplicate)
        body_layout.addWidget(flow)

        self.lbl_store_status = QLabel("", body)
        self.lbl_store_status.setProperty("class", "muted")
        self.lbl_store_status.setWordWrap(True)
        body_layout.addWidget(self.lbl_store_status)

        # Persist collapsed state on toggle — after CollapsibleCard's own toggle handler
        try:
            self.card_saved.btn_toggle.clicked.connect(self._on_card_toggled)
        except Exception:
            pass

        # Middle: Action Builder + Tools notebook (preserve existing tabs). Expand to fill.
        self.notebook = QTabWidget(self)
        self.action_builder = ActionBuilderView(self.notebook, app=app)
        self.notebook.addTab(self.action_builder, "Action Builder")

        self.tools = ToolsView(self.notebook, app=app)
        self.notebook.addTab(self.tools, "Tools")

        outer.addWidget(self.notebook, 1)

        # Internal state
        self._current_name: str | None = None

        # Wire selection -> load (must work whether collapsed or not)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._load_selected())

        # Populate store (creates defaults if needed) — also updates card title badge
        self._refresh_list()

        # Auto-select first item and load it into builder for convenience
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
            # _on_selection_changed will load

    # ------------------------------------------------------------------
    # Collapsible persistence helpers
    # ------------------------------------------------------------------
    def _update_card_title(self):
        """Update header to show count badge, e.g. 'Saved Automations (3)'."""
        try:
            cnt = self.list_widget.count()
            title = f"Saved Automations ({cnt})"
            # CollapsibleCard stores title in lbl_title and title_text
            if hasattr(self.card_saved, "lbl_title"):
                self.card_saved.lbl_title.setText(title)
            if hasattr(self.card_saved, "title_text"):
                self.card_saved.title_text = title
        except Exception:
            pass

    def _on_card_toggled(self):
        """Persist collapsed state via config (ui_checkbox_states + collapsed_groups)."""
        try:
            collapsed = not self.card_saved.is_expanded
            cbs = config.get("ui_checkbox_states", {}) or {}
            if not isinstance(cbs, dict):
                cbs = {}
            cbs["automations.saved_collapsed"] = bool(collapsed)
            config.set("ui_checkbox_states", cbs)
            # Also mirror into collapsed_groups for compatibility with app shell
            cg = config.get("collapsed_groups", []) or []
            if not isinstance(cg, list):
                try:
                    cg = list(cg)
                except Exception:
                    cg = []
            key = "automations.saved"
            if collapsed:
                if key not in cg:
                    cg.append(key)
            else:
                if key in cg:
                    cg.remove(key)
            config.set("collapsed_groups", cg)
        except Exception:
            pass

    def _restore_collapsed_state(self):
        """Restore collapsed/expanded from persisted config (called on mount)."""
        try:
            should_collapsed = _get_initial_collapsed()
            should_expanded = not should_collapsed
            if self.card_saved.is_expanded != should_expanded:
                self.card_saved.toggle()
        except Exception:
            pass

    def mount(self):
        super().mount()
        try:
            self._restore_collapsed_state()
            self._refresh_list()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Store helpers (public for tests / daemon)
    # ------------------------------------------------------------------
    def _refresh_list(self):
        """Reload list_widget from disk store."""
        # Preserve selection
        prev = self._selected_name()
        self.list_widget.blockSignals(True)
        try:
            self.list_widget.clear()
            for data in _load_all_automations():
                name = data.get("name", "")
                item = QListWidgetItem(name)
                # Store full data on item for quick access (optional)
                try:
                    item.setData(Qt.UserRole, data)
                except Exception:
                    pass
                self.list_widget.addItem(item)
        finally:
            self.list_widget.blockSignals(False)
        # Restore selection if possible
        if prev:
            for i in range(self.list_widget.count()):
                if self.list_widget.item(i).text() == prev:
                    self.list_widget.setCurrentRow(i)
                    break
        # Update status and card header badge
        try:
            cnt = self.list_widget.count()
            self.lbl_store_status.setText(f"{cnt} automation(s)")
        except Exception:
            pass
        try:
            self._update_card_title()
        except Exception:
            pass

    def _selected_name(self) -> str | None:
        it = self.list_widget.currentItem()
        return it.text() if it is not None else None

    def _selected_path(self) -> Path | None:
        name = self._selected_name()
        if not name:
            return None
        return _automation_path(name)

    def _prompt_name(self, title: str, label: str, initial: str = "") -> str | None:
        text, ok = QInputDialog.getText(self, title, label, text=initial)
        if not ok:
            return None
        text = (text or "").strip()
        if not text:
            try:
                if self.app:
                    self.app.show_warning_dialog("Invalid Name", "Name cannot be empty.")
            except Exception:
                pass
            return None
        return text

    def _on_selection_changed(self, current, previous=None):
        # Load selected automation into builder
        if current is None:
            return
        name = current.text()
        path = _automation_path(name)
        try:
            if path.is_file():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Load into builder
                try:
                    self.action_builder.load_automation(data)
                    self._current_name = name
                except Exception:
                    pass
        except Exception:
            pass

    def _load_selected(self):
        # Alias for double-click
        it = self.list_widget.currentItem()
        if it is None:
            return
        self._on_selection_changed(it, None)

    def _on_save(self):
        """Save current builder steps to selected automation (Update)."""
        name = self._selected_name()
        if not name:
            # No selection — fall back to Save As
            self._on_save_as()
            return
        # Build data from builder + preserve created_at
        builder_data = self.action_builder.to_dict()
        path = _automation_path(name)
        # Preserve created_at if exists
        created_at = None
        try:
            if path.is_file():
                with open(path, "r", encoding="utf-8") as f:
                    old = json.load(f)
                created_at = old.get("created_at")
        except Exception:
            pass
        now = _now_iso()
        out = {
            "name": name,
            "steps": builder_data.get("steps", []),
            "created_at": created_at or now,
            "updated_at": now,
        }
        # Also persist path/recursive/depth if present in builder_data
        for k in ("path", "recursive", "depth"):
            if k in builder_data:
                out[k] = builder_data[k]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)
            self._refresh_list()
            # Keep selection on saved name
            for i in range(self.list_widget.count()):
                if self.list_widget.item(i).text() == name:
                    self.list_widget.setCurrentRow(i)
                    break
            self._current_name = name
            try:
                self.lbl_store_status.setText(f"Saved: {name}")
            except Exception:
                pass
        except Exception as exc:
            try:
                if self.app:
                    self.app.show_error_dialog("Save Failed", str(exc))
            except Exception:
                pass

    def _on_save_as(self):
        """Save builder as new automation (prompt for name)."""
        init = self._selected_name() or ""
        if init:
            init = init + " Copy"
        name = self._prompt_name("Save As", "Automation name:", initial=init)
        if not name:
            return
        path = _automation_path(name)
        if path.exists():
            # Confirm overwrite
            try:
                resp = QMessageBox.question(
                    self, "Overwrite?", f"Automation '{name}' already exists. Overwrite?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if resp != QMessageBox.Yes:
                    return
            except Exception:
                return
        builder_data = self.action_builder.to_dict()
        now = _now_iso()
        out = {
            "name": name,
            "steps": builder_data.get("steps", []),
            "created_at": now,
            "updated_at": now,
        }
        for k in ("path", "recursive", "depth"):
            if k in builder_data:
                out[k] = builder_data[k]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)
            self._refresh_list()
            # Select new item
            for i in range(self.list_widget.count()):
                if self.list_widget.item(i).text() == name:
                    self.list_widget.setCurrentRow(i)
                    break
            self._current_name = name
            try:
                self.lbl_store_status.setText(f"Saved as: {name}")
            except Exception:
                pass
        except Exception as exc:
            try:
                if self.app:
                    self.app.show_error_dialog("Save Failed", str(exc))
            except Exception:
                pass

    def _on_delete(self):
        name = self._selected_name()
        if not name:
            try:
                if self.app:
                    self.app.show_warning_dialog("No Selection", "Select an automation to delete.")
            except Exception:
                pass
            return
        # Confirm
        try:
            resp = QMessageBox.question(
                self, "Delete?", f"Delete automation '{name}'?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                return
        except Exception:
            pass
        path = _automation_path(name)
        try:
            if path.is_file():
                path.unlink()
        except Exception as exc:
            try:
                if self.app:
                    self.app.show_error_dialog("Delete Failed", str(exc))
            except Exception:
                pass
            return
        self._refresh_list()
        # Clear builder? Keep as is or clear steps? Leave builder with last loaded.
        try:
            self.lbl_store_status.setText(f"Deleted: {name}")
        except Exception:
            pass
        self._current_name = None

    def _on_duplicate(self):
        name = self._selected_name()
        if not name:
            try:
                if self.app:
                    self.app.show_warning_dialog("No Selection", "Select an automation to duplicate.")
            except Exception:
                pass
            return
        # Load original
        src_path = _automation_path(name)
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            try:
                if self.app:
                    self.app.show_error_dialog("Duplicate Failed", str(exc))
            except Exception:
                pass
            return
        # Generate new name
        base = name + " Copy"
        new_name = base
        counter = 2
        while _automation_path(new_name).exists():
            new_name = f"{base} {counter}"
            counter += 1
        now = _now_iso()
        out = dict(data)
        out["name"] = new_name
        out["created_at"] = now
        out["updated_at"] = now
        # steps already in data
        dst = _automation_path(new_name)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)
            self._refresh_list()
            # Select duplicate
            for i in range(self.list_widget.count()):
                if self.list_widget.item(i).text() == new_name:
                    self.list_widget.setCurrentRow(i)
                    break
            try:
                self.lbl_store_status.setText(f"Duplicated: {new_name}")
            except Exception:
                pass
        except Exception as exc:
            try:
                if self.app:
                    self.app.show_error_dialog("Duplicate Failed", str(exc))
            except Exception:
                pass

    # Public helpers for tests / daemon
    def get_automation_names(self) -> list[str]:
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]

    def get_store_dir(self) -> Path:
        return _store_dir()


__all__ = ["AutomationsView", "_store_dir", "_load_all_automations", "_ensure_store_defaults", "DEFAULT_AUTOMATIONS"]
