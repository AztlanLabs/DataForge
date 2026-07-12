import os
import re
from collections import defaultdict

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QCheckBox, QComboBox

from .base import ActionStep
from ...core.config import config
from ...core.hasher import get_file_hash
from ...core.utils import CATEGORY_EXTENSIONS, parse_extensions
from ...modules.cleaner import remove_empty_folders
from ...modules.duplicates import KEEP_STRATEGIES, choose_duplicate_keeper
from ...modules.file_signatures import get_signature, identify_file_type
from ...modules.search import build_search_query

class FilterStep(ActionStep):
    """Base class for steps that reduce the list of files."""
    pass

class SearchFilter(FilterStep):
    def execute(self, context):
        pat = self.params.get("pattern", "")
        if not pat: return

        try:
            re.compile(pat, re.IGNORECASE)
            query = build_search_query(name_pattern=pat, use_regex=True)
        except re.error:
            query = build_search_query(name_pattern=pat, use_regex=False)
        
        kept = []
        for f in context.files:
            if query.matches(f):
                kept.append(f)
            else:
                context.log(f.path, "Search Filter", "Excluded")
        context.files = kept

    def render_ui(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(QLabel("Filename Pattern (Regex/Glob):"))
        e = QLineEdit(parent)
        e.setText(self.params.get("pattern", ".*"))
        e.textChanged.connect(lambda text: self.params.update({"pattern": text}))
        layout.addWidget(e)

    def get_summary(self):
        return f"Match: {self.params.get('pattern', '.*')}"

class SizeFilter(FilterStep):
    def execute(self, context):
        try: min_b = float(self.params.get("min_mb", 0)) * 1024 * 1024
        except (ValueError, TypeError): min_b = 0
        try: max_b = float(self.params.get("max_mb", 0)) * 1024 * 1024
        except (ValueError, TypeError): max_b = 0

        query = build_search_query(min_size_bytes=min_b, max_size_bytes=max_b if max_b > 0 else None)
        
        kept = []
        for f in context.files:
            if query.matches(f):
                kept.append(f)
            elif f.size < min_b:
                context.log(f.path, "Size Filter", "Excluded (Too Small)")
            else:
                context.log(f.path, "Size Filter", "Excluded (Too Large)")
        context.files = kept

    def render_ui(self, parent):
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(QLabel("Min MB:"))
        e1 = QLineEdit(parent)
        e1.setFixedWidth(60)
        e1.setText(str(self.params.get("min_mb", "0")))
        e1.textChanged.connect(lambda text: self.params.update({"min_mb": text}))
        layout.addWidget(e1)
        
        layout.addWidget(QLabel("Max MB:"))
        e2 = QLineEdit(parent)
        e2.setFixedWidth(60)
        e2.setText(str(self.params.get("max_mb", "0")))
        e2.textChanged.connect(lambda text: self.params.update({"max_mb": text}))
        layout.addWidget(e2)
        layout.addStretch()

    def get_summary(self):
        return f"Size: {self.params.get('min_mb',0)}-{self.params.get('max_mb','Max')} MB"

class DateFilter(FilterStep):
    def execute(self, context):
        try: days = float(self.params.get("days", 0))
        except (ValueError, TypeError): days = 0
        mode = self.params.get("mode", "Older")
        query = build_search_query(
            older_than_days=days if mode == "Older" else None,
            newer_than_days=days if mode != "Older" else None,
        )
        
        kept = []
        for f in context.files:
            if query.matches(f):
                kept.append(f)
            else:
                context.log(f.path, "Date Filter", "Excluded")
        context.files = kept

    def render_ui(self, parent):
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(QLabel("Files modified"))
        
        mode = QComboBox(parent)
        mode.addItems(["Older", "Newer"])
        mode.setCurrentText(self.params.get("mode", "Older"))
        mode.currentTextChanged.connect(lambda text: self.params.update({"mode": text}))
        layout.addWidget(mode)
        
        layout.addWidget(QLabel("than"))
        e = QLineEdit(parent)
        e.setFixedWidth(50)
        e.setText(str(self.params.get("days", "30")))
        e.textChanged.connect(lambda text: self.params.update({"days": text}))
        layout.addWidget(e)
        layout.addWidget(QLabel("days"))
        layout.addStretch()

    def get_summary(self):
        return f"{self.params.get('mode')} > {self.params.get('days')} days"

class ImagePropFilter(FilterStep):
    def execute(self, context):
        try: min_w = int(self.params.get("min_width", 0))
        except (ValueError, TypeError): min_w = 0
        try: min_h = int(self.params.get("min_height", 0))
        except (ValueError, TypeError): min_h = 0

        kept = []
        try: from PIL import Image
        except ImportError: return # Pass all if no PIL
        
        for f in context.files:
            if f.extension.lower() not in ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff']:
                context.log(f.path, "Image Filter", "Excluded (Not Image)")
                continue
                
            try:
                with Image.open(f.path) as img:
                    w, h = img.size
                    if w >= min_w and h >= min_h:
                        kept.append(f)
                    else:
                        context.log(f.path, "Image Filter", f"Excluded ({w}x{h})")
            except (OSError, ValueError):
                context.log(f.path, "Image Filter", "Excluded (Read Error)")
                
        context.files = kept

    def render_ui(self, parent):
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(QLabel("Min Width:"))
        e1 = QLineEdit(parent)
        e1.setFixedWidth(60)
        e1.setText(str(self.params.get("min_width", "0")))
        e1.textChanged.connect(lambda text: self.params.update({"min_width": text}))
        layout.addWidget(e1)
        
        layout.addWidget(QLabel("Min Height:"))
        e2 = QLineEdit(parent)
        e2.setFixedWidth(60)
        e2.setText(str(self.params.get("min_height", "0")))
        e2.textChanged.connect(lambda text: self.params.update({"min_height": text}))
        layout.addWidget(e2)
        layout.addStretch()

    def get_summary(self):
        return f"Min {self.params.get('min_width')}x{self.params.get('min_height')}"


class ExtensionFilter(FilterStep):
    def execute(self, context):
        selected = set(e.lower() for e in self.params.get("selected", []))
        selected |= set(parse_extensions(self.params.get("custom_extensions", "")))
        mode = self.params.get("mode", "Include")

        kept = []
        for f in context.files:
            match = f.extension.lower() in selected
            keep = match if mode == "Include" else not match
            if keep:
                kept.append(f)
            else:
                context.log(f.path, "Extension Filter", "Excluded")
        context.files = kept

    def render_ui(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)

        mode = QComboBox(parent)
        mode.addItems(["Include", "Exclude"])
        mode.setCurrentText(self.params.get("mode", "Include"))
        mode.currentTextChanged.connect(lambda text: self.params.update({"mode": text}))
        layout.addWidget(mode)

        selected = set(self.params.get("selected", []))

        def toggle(ext, checked):
            current = set(self.params.get("selected", []))
            if checked:
                current.add(ext)
            else:
                current.discard(ext)
            self.params["selected"] = sorted(current)

        for category, exts in CATEGORY_EXTENSIONS.items():
            layout.addWidget(QLabel(f"<b>{category}</b>", parent))
            grid = QWidget(parent)
            grid_layout = QGridLayout(grid)
            grid_layout.setContentsMargins(10, 0, 0, 5)
            for i, ext in enumerate(sorted(exts)):
                chk = QCheckBox(ext, grid)
                chk.setChecked(ext in selected)
                chk.stateChanged.connect(lambda state, e=ext: toggle(e, bool(state)))
                grid_layout.addWidget(chk, i // 6, i % 6)
            layout.addWidget(grid)

        layout.addWidget(QLabel("Other extensions (comma-separated):", parent))
        e = QLineEdit(parent)
        e.setText(self.params.get("custom_extensions", ""))
        e.textChanged.connect(lambda text: self.params.update({"custom_extensions": text}))
        layout.addWidget(e)

    def get_summary(self):
        count = len(self.params.get("selected", [])) + len(parse_extensions(self.params.get("custom_extensions", "")))
        return f"{self.params.get('mode', 'Include')}: {count or 'no'} extension(s)"


class DuplicateFilter(FilterStep):
    def execute(self, context):
        size_map = defaultdict(list)
        for f in context.files:
            if not f.is_dir and f.size > 0:
                size_map[f.size].append(f)
        candidates = [f for group in size_map.values() if len(group) > 1 for f in group]

        algo = config.get("hash_algorithm", "md5")
        hash_map = defaultdict(list)
        for f in candidates:
            if context.should_cancel():
                return
            h = get_file_hash(f.path, algo, context.cancel_token)
            if h:
                hash_map[h].append(f)
        dup_groups = {h: entries for h, entries in hash_map.items() if len(entries) > 1}
        dup_paths = {e.path for entries in dup_groups.values() for e in entries}

        for f in candidates:
            if f.path not in dup_paths:
                context.log(f.path, "Duplicate Filter", "Excluded (Unique Content)")

        mode = self.params.get("mode", "All Duplicates")
        if mode == "All Duplicates":
            kept = [e for entries in dup_groups.values() for e in entries]
        else:
            strategy = self.params.get("keep_strategy", config.get("duplicate_default_keep_strategy", "first path"))
            kept = []
            for entries in dup_groups.values():
                keeper = choose_duplicate_keeper(entries, strategy)
                for e in entries:
                    if e.path == keeper.path:
                        context.log(e.path, "Duplicate Filter", "Excluded (Keeper)")
                    else:
                        kept.append(e)

        context.files = kept

    def render_ui(self, parent):
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)

        mode = QComboBox(parent)
        mode.addItems(["All Duplicates", "Non-Keepers Only"])
        mode.setCurrentText(self.params.get("mode", "All Duplicates"))
        mode.currentTextChanged.connect(lambda text: self.params.update({"mode": text}))
        layout.addWidget(mode)

        layout.addWidget(QLabel("Keep:"))
        strategy = QComboBox(parent)
        strategy.addItems(list(KEEP_STRATEGIES))
        strategy.setCurrentText(self.params.get("keep_strategy", config.get("duplicate_default_keep_strategy", "first path")))
        strategy.currentTextChanged.connect(lambda text: self.params.update({"keep_strategy": text}))
        layout.addWidget(strategy)
        layout.addStretch()

    def get_summary(self):
        mode = self.params.get("mode", "All Duplicates")
        if mode == "Non-Keepers Only":
            return f"{mode} (keep {self.params.get('keep_strategy', 'first path')})"
        return mode


class SignatureMismatchFilter(FilterStep):
    def execute(self, context):
        include_unknown = self.params.get("include_unknown", False)
        kept = []
        for f in context.files:
            if f.is_dir:
                continue
            try:
                with open(f.path, "rb") as fh:
                    header = fh.read(32)
            except OSError:
                context.log(f.path, "Signature Filter", "Excluded (Read Error)")
                continue

            fmt = identify_file_type(header)
            if fmt is None:
                if include_unknown:
                    kept.append(f)
                else:
                    context.log(f.path, "Signature Filter", "Excluded (Unknown Signature)")
                continue

            sig = get_signature(fmt)
            valid_exts = sig["extensions"] if sig else []
            if f.extension.lower() in valid_exts:
                context.log(f.path, "Signature Filter", f"Excluded (Matches {fmt})")
                continue

            context.log(f.path, "Signature Filter", f"Flagged: content looks like {fmt}, extension is {f.extension}")
            kept.append(f)
        context.files = kept

    def render_ui(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        chk = QCheckBox("Also flag files with unrecognized signature", parent)
        chk.setChecked(self.params.get("include_unknown", False))
        chk.stateChanged.connect(lambda state: self.params.update({"include_unknown": bool(state)}))
        layout.addWidget(chk)

    def get_summary(self):
        suffix = " (+unknown)" if self.params.get("include_unknown") else ""
        return f"Flag extension/signature mismatches{suffix}"


class EmptyFileFilter(FilterStep):
    def execute(self, context):
        mode = self.params.get("mode", "Only Empty")
        kept = []
        for f in context.files:
            is_empty = (not f.is_dir) and f.size == 0
            keep = is_empty if mode == "Only Empty" else not is_empty
            if keep:
                kept.append(f)
            else:
                context.log(f.path, "Empty File Filter", "Excluded")
        context.files = kept

    def render_ui(self, parent):
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Mode:"))
        mode = QComboBox(parent)
        mode.addItems(["Only Empty", "Exclude Empty"])
        mode.setCurrentText(self.params.get("mode", "Only Empty"))
        mode.currentTextChanged.connect(lambda text: self.params.update({"mode": text}))
        layout.addWidget(mode)
        layout.addStretch()

    def get_summary(self):
        return self.params.get("mode", "Only Empty")


class EmptyFolderFilter(FilterStep):
    """
    Exception to the usual filter pattern: scan_directory() never yields
    directories, so context.files has nothing to filter here. This step
    instead inspects context.variables["source_path"] directly and leaves
    context.files untouched.
    """
    def execute(self, context):
        source_path = context.variables.get("source_path")
        if not source_path or not os.path.isdir(source_path):
            context.log("System", "Empty Folder Filter", "Skipped: no source path available")
            return

        delete = self.params.get("delete", False)
        effective_dry_run = context.is_dry_run or not delete
        for line in remove_empty_folders(source_path, dry_run=effective_dry_run):
            context.log(source_path, "Empty Folder Filter", line)

    def render_ui(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        chk = QCheckBox("Delete empty folders now (otherwise just log them)", parent)
        chk.setChecked(self.params.get("delete", False))
        chk.stateChanged.connect(lambda state: self.params.update({"delete": bool(state)}))
        layout.addWidget(chk)

    def get_summary(self):
        return "Delete empty folders" if self.params.get("delete") else "Detect empty folders (log only)"
