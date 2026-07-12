import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QLineEdit, QCheckBox, QSpinBox, QSplitter, QGroupBox, QScrollArea
)
from PyQt5.QtCore import Qt

from .base import BaseView
from ..theme_tokens import TOKENS
from ..widgets import EnhancedTreeview, FlowLayout, FlowContainer, ElidingLabel, attach_tooltips
from ...core.scanner import scan_directory
from ...core.actions.base import ActionContext
from ...core.actions.filters import (
    SearchFilter, SizeFilter, DateFilter, ImagePropFilter,
    ExtensionFilter, DuplicateFilter, SignatureMismatchFilter,
    EmptyFileFilter, EmptyFolderFilter,
)
from ...core.actions.modifications import RenameStep, MetaCleanStep, HashLogStep, NormalizeNameStep
from ...core.actions.io import MoveStep, CopyStep, DeleteStep, ZipStep
from ...core.actions.organize import OrganizeStep
from ...core.actions.media import ConvertImageStep

class ActionBuilderView(BaseView):
    TOOLTIP_TEXTS = {
        "recursive": "Include files from subfolders when the pipeline scans the source path.",
        "depth": "Limit recursion depth. Use -1 for unlimited depth.",
        "preview": "Run the full workflow as a dry run and inspect the planned results before changing files.",
        "execute": "Apply the configured workflow to the current source after you have previewed it.",
    }

    def get_title(self):
        return "Action Builder"

    def __init__(self, master, app=None):
        super().__init__(master, app)
        self.steps = []
        self.setup_ui()

    def get_help_text(self):
        return """
# Action Builder Guide

This tool allows you to build complex workflows to organize and modify files.

## 1. Variable Support
In Rename steps, you can use the following variables:
- {name} : Original filename (without extension)
- {ext}  : File extension (without dot)
- {date} : Today's date (YYYY-MM-DD)
- {size} : File size (e.g., 2MB)
- {counter} : Sequential number (001, 002...)

## 2. Filters
Add filters to narrow down which files are processed.
- Name: Matches filename patterns (e.g. *.jpg)
- Size: Filters by min/max size
- Date: Filters by modification time
- Image Prop: Advanced image filtering (dimensions, aspect ratio)
- Extension: Checkbox-based include/exclude by file type
- Duplicate: Keep only duplicate files, or only the non-keeper duplicates
- Signature: Flags files whose content doesn't match their extension
- Empty File: Isolates or excludes zero-byte files
- Empty Folder: Detects (and optionally deletes) empty subfolders

## 3. Actions
Operations to perform on the filtered files.
- Rename: Change filenames using patterns
- Move/Copy: Transfer files to another folder
- Zip: Create archives
- Normalize: Strip leading dots, find/replace, numeric renumbering, case, prefix/suffix
- Organize: Sort files into category subfolders (Documents/Images/Videos/...)
- Convert: Batch convert images
- Hash Log: Compute and log md5/sha1/sha256 hashes

**Tip:** Uses DRY RUN logic first to verify your workflow safely.
"""

    def setup_ui(self):
        # Main Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        
        # 1. Source (Top Configuration)
        src_frame = QGroupBox("1. Configuration", self)
        src_layout = QHBoxLayout(src_frame)
        src_layout.setContentsMargins(10, 5, 10, 5)
        
        src_layout.addWidget(QLabel("Path:"))
        self.entry_path = QLineEdit(src_frame)
        src_layout.addWidget(self.entry_path)
        
        self.btn_browse = QPushButton("Browse", src_frame)
        self.btn_browse.clicked.connect(self.browse_path)
        src_layout.addWidget(self.btn_browse)
        
        self.chk_recursive = QCheckBox("Recursive", src_frame)
        self.chk_recursive.setChecked(True)
        src_layout.addWidget(self.chk_recursive)
        
        src_layout.addWidget(QLabel("Depth:"))
        self.spin_depth = QSpinBox(src_frame)
        self.spin_depth.setRange(-1, 10)
        self.spin_depth.setValue(-1)
        src_layout.addWidget(self.spin_depth)
        
        self.main_layout.addWidget(src_frame)

        # 2. Main Work Area Splitter
        self.work_splitter = QSplitter(Qt.Horizontal, self)
        self.main_layout.addWidget(self.work_splitter, 1)

        # Left side: Workflow steps
        step_widget = QWidget(self.work_splitter)
        step_layout = QVBoxLayout(step_widget)
        step_layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar Library Group Box
        lib_frame = QGroupBox("Add Step", step_widget)
        lib_layout = QVBoxLayout(lib_frame)
        lib_layout.setSpacing(4)

        # Row 1: Filters
        self._add_step_button_group(
            lib_layout, lib_frame, "Filter:", "info",
            [
                ("Name", SearchFilter), ("Size", SizeFilter), ("Date", DateFilter),
                ("Img Prop", ImagePropFilter), ("Extension", ExtensionFilter),
                ("Duplicate", DuplicateFilter), ("Signature", SignatureMismatchFilter),
                ("Empty File", EmptyFileFilter), ("Empty Folder", EmptyFolderFilter),
            ],
        )

        # Row 2: Actions
        self._add_step_button_group(
            lib_layout, lib_frame, "Act:", "warning",
            [
                ("Rename", RenameStep), ("Move", MoveStep), ("Copy", CopyStep),
                ("Zip", ZipStep), ("Normalize", NormalizeNameStep), ("Organize", OrganizeStep),
            ],
        )

        # Row 3: Misc/Media
        self._add_step_button_group(
            lib_layout, lib_frame, "Misc:", "success",
            [
                ("Convert", ConvertImageStep), ("Clean", MetaCleanStep),
                ("Delete", DeleteStep), ("Hash Log", HashLogStep),
            ],
        )

        step_layout.addWidget(lib_frame)

        # Scrollable container for chain steps
        self.scroll_chain = QScrollArea(step_widget)
        self.scroll_chain.setWidgetResizable(True)
        self.scroll_chain.setFrameShape(QFrame.NoFrame)
        self.chain_widget = QWidget()
        self.chain_layout = QVBoxLayout(self.chain_widget)
        self.chain_layout.setContentsMargins(0, 0, 0, 0)
        self.chain_layout.setAlignment(Qt.AlignTop)
        self.scroll_chain.setWidget(self.chain_widget)
        step_layout.addWidget(self.scroll_chain)
        
        step_widget.setMinimumWidth(320)
        self.work_splitter.addWidget(step_widget)

        # Right side: Pipeline log tree
        res_widget = QWidget(self.work_splitter)
        res_widget.setMinimumWidth(280)
        res_layout = QVBoxLayout(res_widget)
        res_layout.setContentsMargins(0, 0, 0, 0)
        
        res_frame = QGroupBox("3. Pipeline Log", res_widget)
        res_frame_layout = QVBoxLayout(res_frame)
        res_frame_layout.setContentsMargins(5, 5, 5, 5)
        
        cols = ("_fullpath", "file", "action", "status")
        self.action_tree = EnhancedTreeview(res_frame, columns=cols, app=self.app)
        self.action_tree.column("_fullpath", width=0, stretch=False)
        self.action_tree.heading("file", text="File")
        self.action_tree.heading("action", text="Action")
        self.action_tree.heading("status", text="Status")
        self.action_tree.column("file", width=300, stretch=True)
        self.action_tree.column("action", width=120, stretch=False)
        self.action_tree.column("status", width=200, stretch=True)
        res_frame_layout.addWidget(self.action_tree)
        res_layout.addWidget(res_frame)
        
        self.work_splitter.addWidget(res_widget)
        self.work_splitter.setSizes([500, 600])
        self.work_splitter.setStretchFactor(0, 1)
        self.work_splitter.setStretchFactor(1, 1)
        self.work_splitter.setChildrenCollapsible(False)

        # 4. Execution Buttons Row
        run_frame = QWidget(self)
        run_layout = QHBoxLayout(run_frame)
        run_layout.setContentsMargins(0, 5, 0, 0)
        run_layout.addStretch()
        
        self.btn_preview = QPushButton("Preview Pipeline", run_frame)
        self.btn_preview.clicked.connect(lambda: self.run_pipeline(dry_run=True))
        run_layout.addWidget(self.btn_preview)
        
        self.btn_execute = QPushButton("EXECUTE PIPELINE", run_frame)
        self.btn_execute.setProperty("variant", "success")
        self.btn_execute.clicked.connect(lambda: self.run_pipeline(dry_run=False))
        run_layout.addWidget(self.btn_execute)
        
        self.main_layout.addWidget(run_frame)
        
        self._init_tooltips()

    def _add_step_button_group(self, parent_layout, parent_widget, label_text, label_variant, entries):
        """
        Renders a category label followed by a FlowLayout of "+ <name>"
        buttons that wrap onto additional lines as needed, instead of a
        QHBoxLayout row that just overflows past the window edge once a
        category has more entries than fit on one line.
        """
        lbl = QLabel(label_text, parent_widget)
        lbl.setProperty("variant", label_variant)
        parent_layout.addWidget(lbl)

        flow_widget = FlowContainer(parent_widget)
        flow = FlowLayout(flow_widget, margin=0, hspacing=4, vspacing=4)
        for text, cls in entries:
            btn = QPushButton(f"+ {text}", flow_widget)
            btn.clicked.connect(lambda checked, c=cls: self.add_step(c))
            flow.addWidget(btn)
        parent_layout.addWidget(flow_widget)

    def _init_tooltips(self):
        attach_tooltips([
            (self.chk_recursive, self.TOOLTIP_TEXTS["recursive"]),
            (self.spin_depth, self.TOOLTIP_TEXTS["depth"]),
            (self.btn_preview, self.TOOLTIP_TEXTS["preview"]),
            (self.btn_execute, self.TOOLTIP_TEXTS["execute"]),
        ])

    def browse_path(self):
        p = self.choose_file_or_directory(
            file_title="Select File for Pipeline",
            directory_title="Select Folder for Pipeline",
            filetypes=[("All Files", "*.*")],
        )
        if p:
            self.entry_path.setText(p)

    def add_step(self, step_class):
        step = step_class()
        self.steps.append(step)
        self.refresh_steps_ui()

    def move_step(self, index, direction):
        new_index = index + direction
        if 0 <= new_index < len(self.steps):
            self.steps[index], self.steps[new_index] = self.steps[new_index], self.steps[index]
            self.refresh_steps_ui()

    def remove_step(self, index):
        del self.steps[index]
        self.refresh_steps_ui()

    def refresh_steps_ui(self):
        # Remove old widgets from layout
        for i in reversed(range(self.chain_layout.count())):
            widget = self.chain_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                
        for i, step in enumerate(self.steps):
            self.render_step_card(i, step)

    def render_step_card(self, index, step):
        card = QFrame(self.chain_widget)
        card.setFrameShape(QFrame.StyledPanel)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(5, 5, 5, 5)
        
        # Header
        header = QWidget(card)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        is_collapsed = getattr(step, "_ui_collapsed", False)
        
        title_lbl = QLabel(f"<b>{index+1}. {step.name}</b>", header)
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        # Controls
        btn_up = QPushButton("↑", header)
        btn_up.setFixedWidth(25)
        btn_up.clicked.connect(lambda checked, idx=index: self.move_step(idx, -1))
        btn_up.setEnabled(index > 0)
        header_layout.addWidget(btn_up)
        
        btn_down = QPushButton("↓", header)
        btn_down.setFixedWidth(25)
        btn_down.clicked.connect(lambda checked, idx=index: self.move_step(idx, 1))
        btn_down.setEnabled(index < len(self.steps) - 1)
        header_layout.addWidget(btn_down)
        
        btn_close = QPushButton("✕", header)
        btn_close.setFixedWidth(25)
        btn_close.setProperty("variant", "danger")
        btn_close.clicked.connect(lambda checked, idx=index: self.remove_step(idx))
        header_layout.addWidget(btn_close)
        
        btn_toggle = QPushButton("▼" if not is_collapsed else "▶", header)
        btn_toggle.setFixedWidth(25)
        btn_toggle.setStyleSheet("border: none; background: transparent; font-weight: bold;")
        header_layout.addWidget(btn_toggle)
        
        card_layout.addWidget(header)

        # Summary row: kept on its own full-width line (rather than squeezed
        # into the header next to the fixed-width control buttons). Uses an
        # eliding single-line label (full text via tooltip) instead of word
        # wrap, since a wrapped label's height doesn't reliably propagate
        # through this many levels of nested layouts (QLabel -> card_layout
        # -> card -> chain_layout -> chain_widget -> QScrollArea).
        summary_lbl = ElidingLabel(step.get_summary(), card)
        summary_lbl.setProperty("class", "muted")
        summary_lbl.setStyleSheet("font-style: italic;")
        card_layout.addWidget(summary_lbl)

        # Body content
        body = QWidget(card)
        body.setVisible(not is_collapsed)
        step.render_ui(body)
        card_layout.addWidget(body)
        
        def toggle():
            col = not getattr(step, "_ui_collapsed", False)
            step._ui_collapsed = col
            body.setVisible(not col)
            summary_lbl.setVisible(col)
            btn_toggle.setText("▼" if not col else "▶")
            
        btn_toggle.clicked.connect(toggle)
        summary_lbl.setVisible(is_collapsed)
        
        self.chain_layout.addWidget(card)

    def run_pipeline(self, dry_run=False):
        src = self.entry_path.text().strip()
        if not src or not os.path.exists(src):
            self.app.show_warning_dialog("Error", "Invalid Source Path")
            return
        if not self.steps:
            self.app.show_warning_dialog("Empty", "Add steps first.")
            return

        self.action_tree.tree.clear()
        self.app.update_status(f"Running Pipeline ({'Preview' if dry_run else 'Execute'})...")
        
        self.app.run_workflow(
            self._execute_pipeline_thread,
            self._on_complete,
            src, 
            self.chk_recursive.isChecked(), 
            self.spin_depth.value(),
            self.steps,
            dry_run,
            progress=True,
            error_title="Pipeline Failed",
        )

    def _execute_pipeline_thread(self, src, recursive, max_depth, steps, dry_run, progress_callback, cancel_token=None):
        try:
            files = []
            count = 0
            for entry in scan_directory(src, recursive, max_depth=max_depth, cancel_token=cancel_token):
                if cancel_token and cancel_token.is_set(): return "Cancelled"
                files.append(entry)
                count += 1
                if progress_callback and count % 50 == 0:
                    progress_callback(count, 0, "Scanning...")
            
            if not files: return "No files found."
            
            context = ActionContext(files, update_progress=progress_callback)
            context.is_dry_run = dry_run
            context.cancel_token = cancel_token
            context.variables["source_path"] = src
            
            total_steps = len(steps)
            for i, step in enumerate(steps):
                if context.should_cancel(): return "Cancelled"
                
                progress_callback(i, total_steps, f"Running Step {i+1}: {step.name}")
                
                try:
                    step.execute(context)
                except Exception as e:
                    context.log("Pipeline", "Error", f"Step {step.name} failed: {e}")
            
            return context.results
            
        except Exception as e:
            return f"Critical Error: {e}"

    def _on_complete(self, result):
        if isinstance(result, str):
            if result == "Cancelled":
                self.app.update_status("Pipeline Cancelled")
            else:
                self.app.show_error_dialog("Pipeline Error", result)
                self.app.update_status("Error")
            return
            
        self.app.update_status(f"Pipeline Completed. {len(result)} log entries.")
        if not result:
            self.app.show_info_dialog("Result", "Pipeline finished with no actions logged.")
            return
             
        for path, action, status in result:
            self.action_tree.insert("", "end", values=(path, os.path.basename(path), action, status))
