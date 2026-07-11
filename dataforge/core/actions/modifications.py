import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox
from PyQt5.QtCore import Qt

from .base import ActionStep
from ...core.config import config
from ...core.hasher import get_hashes
from ...core.services import FileActionService
from ...modules.cleaner import MetadataCleaner

class RenameStep(ActionStep):
    def execute(self, context):
        pattern = self.params.get("pattern", "{name}")
        counter_start = int(self.params.get("counter_start", 1))
        outcome = FileActionService.rename_items_with_template(
            context.files,
            pattern,
            counter_start=counter_start,
            dry_run=context.is_dry_run,
            cancel_token=context.cancel_token,
        )
        FileActionService.apply_successes_to_entries(outcome)
        FileActionService.log_outcome(outcome, "Rename", context.log, include_skipped=False)

    def render_ui(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(QLabel("Rename Pattern:"))
        lbl_hint = QLabel("Vars: {name}, {ext}, {date}, {counter}")
        lbl_hint.setStyleSheet("font-size: 11px; color: #6c757d;")
        layout.addWidget(lbl_hint)
        
        e = QLineEdit(parent)
        e.setText(self.params.get("pattern", "{name}_{counter}.{ext}"))
        e.textChanged.connect(lambda text: self.params.update({"pattern": text}))
        layout.addWidget(e)
        
        f = QWidget(parent)
        f_layout = QHBoxLayout(f)
        f_layout.setContentsMargins(0, 0, 0, 0)
        f_layout.addWidget(QLabel("Start Count:"))
        es = QLineEdit(f)
        es.setFixedWidth(60)
        es.setText(str(self.params.get("counter_start", "1")))
        es.textChanged.connect(lambda text: self.params.update({"counter_start": text}))
        f_layout.addWidget(es)
        f_layout.addStretch()
        layout.addWidget(f)

    def get_summary(self):
        return f"Pattern: {self.params.get('pattern')}"

class MetaCleanStep(ActionStep):
    def execute(self, context):
        for f in context.files:
            if context.should_cancel(): return
            
            if not context.is_dry_run:
                if MetadataCleaner.remove_metadata(f.path):
                    context.log(f.path, "Clean Metadata", "Cleaned")
                else:
                    context.log(f.path, "Clean Metadata", "Skipped/Failed")
            else:
                context.log(f.path, "Clean Metadata", "Would Clean")

    def get_summary(self):
        return "Strip EXIF/Metadata"


class HashLogStep(ActionStep):
    def execute(self, context):
        algos = self.params.get("algos") or [config.get("hash_algorithm", "md5")]
        for f in context.files:
            if context.should_cancel():
                return
            if context.is_dry_run:
                context.log(f.path, "Hash Log", f"Would compute {'/'.join(algos)}")
                continue

            hashes = get_hashes(f.path, algos)
            summary = ", ".join(f"{a}={h}" for a, h in hashes.items() if h)
            context.log(f.path, "Hash Log", summary or "Error computing hash")
            context.variables.setdefault("hash_log", []).append({"path": f.path, **hashes})

    def render_ui(self, parent):
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)

        default_algo = config.get("hash_algorithm", "md5")
        selected = set(self.params.get("algos") or [default_algo])

        def toggle(algo, checked):
            current = set(self.params.get("algos") or [])
            if checked:
                current.add(algo)
            else:
                current.discard(algo)
            self.params["algos"] = sorted(current)

        for algo in ("md5", "sha1", "sha256"):
            chk = QCheckBox(algo, parent)
            chk.setChecked(algo in selected)
            chk.stateChanged.connect(lambda state, a=algo: toggle(a, bool(state)))
            layout.addWidget(chk)
        layout.addStretch()

    def get_summary(self):
        algos = self.params.get("algos") or [config.get("hash_algorithm", "md5")]
        return f"Hash: {', '.join(algos)}"


class NormalizeNameStep(ActionStep):
    def execute(self, context):
        from ...ui.widgets import NormalizeRulesWidget
        kwargs = NormalizeRulesWidget.kwargs_from_params(self.params)
        outcome = FileActionService.rename_items_with_rules(
            context.files,
            **kwargs,
            dry_run=context.is_dry_run,
            cancel_token=context.cancel_token,
        )
        FileActionService.apply_successes_to_entries(outcome)
        FileActionService.log_outcome(outcome, "Normalize Name", context.log, include_skipped=False)

    def render_ui(self, parent):
        from ...ui.widgets import NormalizeRulesWidget
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(NormalizeRulesWidget(parent, params=self.params))

    def get_summary(self):
        p = self.params
        bits = []
        if p.get("strip_leading_dot"):
            bits.append("strip-dot")
        if p.get("find_text"):
            bits.append("find/replace")
        if p.get("numeric_pattern"):
            bits.append("numeric")
        if p.get("case_mode", "none") != "none":
            bits.append(p["case_mode"])
        return ", ".join(bits) or "No rules configured"
