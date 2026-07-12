from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSplitter, QTabWidget, QGroupBox, QComboBox, QSlider,
    QLineEdit
)
from PyQt5.QtCore import Qt
import os

from .base import BaseView
from ..theme_tokens import TYPE_SCALE
from .. import dialogs
from ..widgets import EnhancedTreeview, FilePreviewPanel, attach_tooltips

class MediaView(BaseView):
    TOOLTIP_TEXTS = {
        "pdf_add": "Add one or more PDFs to the merge list in the exact order they should be combined.",
        "pdf_merge": "Merge the listed PDFs into one output file after a dry-run preview.",
        "pdf_split_file": "Choose the PDF file that should be split into separate page files.",
        "pdf_split": "Split the selected PDF into one file per page after previewing the output.",
        "img_add": "Add one or more images to the batch conversion queue.",
        "img_format": "Choose the output format for every queued image.",
        "img_resize": "Resize every output image by percentage. Use 100% to keep the original dimensions.",
        "img_convert": "Convert all queued images using the selected format and resize settings after preview.",
    }

    def get_title(self):
        return "Media Tools"

    def __init__(self, master, app=None):
        super().__init__(master, app)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        
        self.notebook = QTabWidget(self)
        self.main_layout.addWidget(self.notebook)
        
        self._init_pdf_tools(self.notebook)
        self._init_image_tools(self.notebook)

    def _init_pdf_tools(self, parent):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Merge Section
        lbl_merge = QLabel("Merge PDFs", tab)
        lbl_merge.setStyleSheet(f"font-weight: bold; font-size: {TYPE_SCALE['subheading']}px;")
        layout.addWidget(lbl_merge)
        
        # Tools row
        bar = QWidget(tab)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 5, 0, 5)
        
        self.pdf_add_button = QPushButton("Add PDFs...", bar)
        self.pdf_add_button.clicked.connect(self.pdf_add)
        bar_layout.addWidget(self.pdf_add_button)
        
        self.btn_pdf_clear = QPushButton("Clear", bar)
        self.btn_pdf_clear.clicked.connect(lambda: self.pdf_tree.delete(*self.pdf_tree.get_children()))
        bar_layout.addWidget(self.btn_pdf_clear)
        
        self.btn_pdf_up = QPushButton("Move Up", bar)
        self.btn_pdf_up.clicked.connect(self.pdf_up)
        bar_layout.addWidget(self.btn_pdf_up)
        
        self.btn_pdf_down = QPushButton("Move Down", bar)
        self.btn_pdf_down.clicked.connect(self.pdf_down)
        bar_layout.addWidget(self.btn_pdf_down)
        
        bar_layout.addStretch()
        
        self.pdf_merge_button = QPushButton("Merge Into One", bar)
        self.pdf_merge_button.setProperty("variant", "warning")
        self.pdf_merge_button.clicked.connect(self.pdf_merge)
        bar_layout.addWidget(self.pdf_merge_button)
        
        layout.addWidget(bar)
        
        self.pdf_tree = EnhancedTreeview(tab, columns=("path", "size"), show="headings")
        self.pdf_tree.heading("path", text="File Path")
        self.pdf_tree.heading("size", text="Size")
        layout.addWidget(self.pdf_tree, 1)
        
        # Separator
        sep = QFrame(tab)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)
        
        # Split Section
        lbl_split = QLabel("Split PDF", tab)
        lbl_split.setStyleSheet(f"font-weight: bold; font-size: {TYPE_SCALE['subheading']}px;")
        layout.addWidget(lbl_split)
        
        row = QWidget(tab)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 5, 0, 5)
        
        row_layout.addWidget(QLabel("File:", row))
        self.split_entry = QLineEdit(row)
        row_layout.addWidget(self.split_entry, 1)
        
        self.pdf_split_browse_button = QPushButton("Browse...", row)
        self.pdf_split_browse_button.clicked.connect(lambda: self.browse_file(self.split_entry, "PDF", "*.pdf"))
        row_layout.addWidget(self.pdf_split_browse_button)
        
        self.pdf_split_button = QPushButton("Split Into Pages", row)
        self.pdf_split_button.setProperty("variant", "warning")
        self.pdf_split_button.clicked.connect(self.pdf_split)
        row_layout.addWidget(self.pdf_split_button)
        
        layout.addWidget(row)
        
        parent.addTab(tab, "PDF Tools")
        self._init_pdf_tooltips()

    def _init_image_tools(self, parent):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        top = QWidget(tab)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 5, 0, 5)
        
        self.img_add_button = QPushButton("Add Images...", top)
        self.img_add_button.clicked.connect(self.img_add)
        top_layout.addWidget(self.img_add_button)
        
        self.btn_img_clear = QPushButton("Clear", top)
        self.btn_img_clear.clicked.connect(lambda: self.img_tree.delete(*self.img_tree.get_children()))
        top_layout.addWidget(self.btn_img_clear)
        
        top_layout.addStretch()
        layout.addWidget(top)
        
        # Options
        opts = QGroupBox("Conversion Options", tab)
        opts_layout = QHBoxLayout(opts)
        
        opts_layout.addWidget(QLabel("Format:", opts))
        self.img_fmt_combo = QComboBox(opts)
        self.img_fmt_combo.addItems(["PNG", "JPEG", "WEBP", "BMP", "ICO"])
        self.img_fmt_combo.setCurrentText("PNG")
        self.img_fmt_combo.setFixedWidth(80)
        opts_layout.addWidget(self.img_fmt_combo)
        
        opts_layout.addWidget(QLabel("Resize %:", opts))
        self.img_resize_scale = QSlider(Qt.Horizontal, opts)
        self.img_resize_scale.setRange(10, 200)
        self.img_resize_scale.setValue(100)
        self.img_resize_scale.setFixedWidth(150)
        self.img_resize_scale.valueChanged.connect(self.on_resize_changed)
        opts_layout.addWidget(self.img_resize_scale)
        
        self.lbl_pct = QLabel("100%", opts)
        opts_layout.addWidget(self.lbl_pct)
        
        opts_layout.addStretch()
        
        self.img_convert_button = QPushButton("Convert All", opts)
        self.img_convert_button.setProperty("variant", "success")
        self.img_convert_button.clicked.connect(self.img_convert)
        opts_layout.addWidget(self.img_convert_button)
        
        layout.addWidget(opts)
        
        # Splitter (PanedWindow)
        self.paned = QSplitter(Qt.Horizontal, tab)
        layout.addWidget(self.paned, 1)
        
        # Tree
        self.img_tree = EnhancedTreeview(self.paned, columns=("path", "size", "status"), show="headings")
        self.img_tree.heading("path", text="File Path")
        self.img_tree.heading("size", text="Size")
        self.img_tree.heading("status", text="Status")
        self.paned.addWidget(self.img_tree)
        
        # Preview
        self.img_preview = FilePreviewPanel(self.paned)
        self.paned.addWidget(self.img_preview)
        
        self.paned.setStretchFactor(0, 3)
        self.paned.setStretchFactor(1, 1)
        
        # Connect Selection Changed
        self.img_tree.tree.itemSelectionChanged.connect(self.on_img_select)
        
        parent.addTab(tab, "Image Batch")
        self._init_image_tooltips()

    def on_resize_changed(self, value):
        self.lbl_pct.setText(f"{value}%")

    def _init_pdf_tooltips(self):
        self._pdf_tooltips = attach_tooltips([
            (self.pdf_add_button, self.TOOLTIP_TEXTS["pdf_add"]),
            (self.pdf_merge_button, self.TOOLTIP_TEXTS["pdf_merge"]),
            (self.split_entry, self.TOOLTIP_TEXTS["pdf_split_file"]),
            (self.pdf_split_browse_button, self.TOOLTIP_TEXTS["pdf_split_file"]),
            (self.pdf_split_button, self.TOOLTIP_TEXTS["pdf_split"]),
        ])

    def _init_image_tooltips(self):
        self._image_tooltips = attach_tooltips([
            (self.img_add_button, self.TOOLTIP_TEXTS["img_add"]),
            (self.img_fmt_combo, self.TOOLTIP_TEXTS["img_format"]),
            (self.img_resize_scale, self.TOOLTIP_TEXTS["img_resize"]),
            (self.img_convert_button, self.TOOLTIP_TEXTS["img_convert"]),
        ])

    # --- PDF Logic ---
    def pdf_add(self):
        files, _ = dialogs.get_open_file_names(self, "Select PDF Files", "", "PDF Files (*.pdf)")
        from ...core.utils import format_size
        for p in files:
            try:
                size = format_size(os.path.getsize(p))
            except OSError:
                size = "Unknown"
            self.pdf_tree.insert("", None, values=(p, size))

    def pdf_up(self):
        self._move_item(-1)
    
    def pdf_down(self):
        self._move_item(1)

    def _move_item(self, direction):
        sel = self.pdf_tree.selection()
        if not sel:
            return
        item = sel[0]
        children = self.pdf_tree.get_children()
        try:
            idx = children.index(item)
        except ValueError:
            return
        new_idx = idx + direction
        if 0 <= new_idx < len(children):
            self.pdf_tree.move(item, "", new_idx)
            self.pdf_tree.selection_set([item])

    def pdf_merge(self):
        items = self.pdf_tree.get_children()
        if not items:
            return
            
        paths = [self.pdf_tree.item(i)['values'][0] for i in items]
        
        out, _ = dialogs.get_save_file_name(self, "Save Merged PDF", "", "PDF Files (*.pdf)")
        if not out: return

        self.app.update_status(f"Previewing merge for {len(paths)} PDFs...")
        self.app.run_workflow(
            self._preview_pdf_merge_worker,
            self._on_preview_pdf_merge_complete,
            paths,
            out,
            progress=True,
            error_title="PDF Merge Preview Failed",
        )

    def _preview_pdf_merge_worker(self, paths, out, progress_callback=None, cancel_token=None):
        from ...core.media_ops import merge_pdfs
        return merge_pdfs(paths, out, dry_run=True, progress_callback=progress_callback, cancel_token=cancel_token)

    def _pdf_merge_worker(self, paths, out, progress_callback=None, cancel_token=None):
        from ...core.media_ops import merge_pdfs
        return merge_pdfs(paths, out, dry_run=False, progress_callback=progress_callback, cancel_token=cancel_token)

    def pdf_split(self):
        path = self.split_entry.text()
        if not path or not os.path.exists(path):
            return
            
        out_dir = dialogs.get_existing_directory(self, "Select Output Folder")
        if not out_dir: return

        self.app.update_status("Previewing PDF split...")
        self.app.run_workflow(
            self._preview_pdf_split_worker,
            self._on_preview_pdf_split_complete,
            path,
            out_dir,
            progress=True,
            error_title="PDF Split Preview Failed",
        )

    def _preview_pdf_split_worker(self, path, out_dir, progress_callback=None, cancel_token=None):
        from ...core.media_ops import split_pdf
        return split_pdf(path, out_dir, dry_run=True, progress_callback=progress_callback, cancel_token=cancel_token)

    def _pdf_split_worker(self, path, out_dir, progress_callback=None, cancel_token=None):
        from ...core.media_ops import split_pdf
        return split_pdf(path, out_dir, dry_run=False, progress_callback=progress_callback, cancel_token=cancel_token)

    def _on_preview_pdf_merge_complete(self, outcome):
        if outcome.get("cancelled"):
            self.app.update_status("PDF merge preview cancelled")
            return

        count = outcome["requested"]
        lines = [f"Would merge {count} PDF file(s) into {os.path.basename(outcome['output_path'])}"]
        if outcome.get("failed_paths"):
            lines.extend(f"Unreadable during preview: {path}" for path in outcome["failed_paths"][:3])
        summary = f"Merge {count} PDF(s) into {os.path.basename(outcome['output_path'])}."
        if not self.confirm_preview("Confirm PDF Merge", summary, lines=lines, action_label=f"merge {count} PDF(s)"):
            self.app.update_status("PDF merge preview cancelled")
            return

        self.app.update_status(f"Merging {count} PDFs...")
        self.app.run_workflow(
            self._pdf_merge_worker,
            self._on_pdf_merge_complete,
            [self.pdf_tree.item(item_id)['values'][0] for item_id in self.pdf_tree.get_children()],
            outcome["output_path"],
            progress=True,
            error_title="PDF Merge Failed",
        )

    def _on_pdf_merge_complete(self, result):
        if result.get("cancelled"):
            self.app.update_status(f"PDF merge cancelled after {result.get('merged', 0)} files")
            requested = result["requested"]
            self.app.show_warning_dialog(
                "Cancelled",
                self.summarize_completion("PDF merge stopped.", requested, result.get("merged", 0), requested - result.get("merged", 0), created=0),
            )
            return

        self.app.update_status("PDF merge complete")
        self.app.show_info_dialog("Success", self.summarize_completion("PDF merge complete.", result["requested"], result.get("merged", 0), result["requested"] - result.get("merged", 0), created=1))

    def _on_preview_pdf_split_complete(self, outcome):
        if outcome.get("cancelled"):
            self.app.update_status("PDF split preview cancelled")
            return

        count = outcome["requested"]
        summary = f"Split {os.path.basename(outcome['source_path'])} into {count} page file(s)."
        if not self.confirm_preview("Confirm PDF Split", summary, lines=outcome["pages"], action_label=f"split into {count} page(s)"):
            self.app.update_status("PDF split preview cancelled")
            return

        self.app.update_status(f"Splitting PDF into {count} pages...")
        self.app.run_workflow(
            self._pdf_split_worker,
            self._on_pdf_split_complete,
            outcome["source_path"],
            outcome["output_dir"],
            progress=True,
            error_title="PDF Split Failed",
        )

    def _on_pdf_split_complete(self, outcome):
        if outcome.get("cancelled"):
            self.app.update_status(f"PDF split cancelled after {len(outcome['pages'])} page(s)")
            requested = outcome["requested"]
            self.app.show_warning_dialog(
                "Cancelled",
                self.summarize_completion("PDF split stopped.", requested, len(outcome["pages"]), requested - len(outcome["pages"]), created=len(outcome["pages"])),
            )
            return

        self.app.update_status(f"PDF split complete ({len(outcome['pages'])} page(s))")
        requested = outcome["requested"]
        self.app.show_info_dialog("Success", self.summarize_completion("PDF split complete.", requested, len(outcome["pages"]), requested - len(outcome["pages"]), created=len(outcome["pages"])))

    # --- Image Logic ---
    def img_add(self):
        files, _ = dialogs.get_open_file_names(
            self,
            "Select Images",
            "",
            "Image Files (*.jpg *.jpeg *.png *.webp *.bmp *.tiff);;All Files (*)"
        )
        from ...core.utils import format_size
        for p in files:
            try:
                size = format_size(os.path.getsize(p))
            except OSError:
                size = "Unknown"
            self.img_tree.insert("", None, values=(p, size, "Pending"))

    def on_img_select(self):
        sel = self.img_tree.selection()
        if sel:
            path = self.img_tree.item(sel[0])['values'][0]
            self.img_preview.update_file(path)

    def img_convert(self):
        items = self.img_tree.get_children()
        if not items: return
        
        fmt = self.img_fmt_combo.currentText()
        pct = self.img_resize_scale.value()
        jobs = []
        for item in items:
            values = self.img_tree.item(item)["values"]
            if not values:
                continue
            jobs.append({
                "item_id": item,
                "path": values[0],
                "size": values[1],
            })
        if not jobs:
            return

        self.app.update_status(f"Previewing conversion for {len(jobs)} images...")
        self.app.run_workflow(
            self._img_preview_worker,
            self._on_img_preview_complete,
            jobs,
            fmt,
            pct,
            progress=True,
            error_title="Image Preview Failed",
        )

    def _img_preview_worker(self, jobs, fmt, pct, progress_callback=None, cancel_token=None):
        from ...core.media_ops import convert_image

        previews = []
        total = len(jobs)
        for index, job in enumerate(jobs, start=1):
            if cancel_token and cancel_token.is_set():
                return {"cancelled": True, "previews": previews, "fmt": fmt, "pct": pct}

            preview_result = convert_image(job["path"], fmt, pct, dry_run=True)
            previews.append({
                "item_id": job["item_id"],
                "source_path": job["path"],
                "output_path": preview_result["output_path"],
            })

            if progress_callback:
                progress_callback(index, total, "Previewing Conversion...")

        return {"cancelled": False, "previews": previews, "fmt": fmt, "pct": pct}

    def _on_img_preview_complete(self, outcome):
        if outcome.get("cancelled"):
            self.app.update_status("Image conversion preview cancelled")
            return

        previews = outcome["previews"]
        if not previews:
            self.app.show_warning_dialog("Nothing To Convert", "No valid image files are available.")
            return

        lines = [f"Would convert: {item['source_path']} -> {item['output_path']}" for item in previews]
        if not self.confirm_preview("Confirm Image Conversion", f"Convert {len(previews)} image(s).", lines=lines, action_label=f"convert {len(previews)} image(s)"):
            self.app.update_status("Image conversion preview cancelled")
            return

        self.app.update_status(f"Converting {len(previews)} images...")
        self.app.run_workflow(
            self._img_convert_worker,
            self._on_img_convert_complete,
            previews,
            outcome["fmt"],
            outcome["pct"],
            progress=True,
            error_title="Image Conversion Failed",
        )

    def _img_convert_worker(self, previews, fmt, pct, progress_callback=None, cancel_token=None):
        from ...core.media_ops import convert_image
        from ...core.utils import format_size

        results = []
        total = len(previews)
        for index, preview in enumerate(previews, start=1):
            if cancel_token and cancel_token.is_set():
                return {"cancelled": True, "results": results}

            try:
                convert_result = convert_image(preview["source_path"], fmt, pct, dry_run=False)
                output_path = convert_result["output_path"]
                results.append({
                    "item_id": preview["item_id"],
                    "path": output_path,
                    "size": format_size(os.path.getsize(output_path)),
                    "status": "Done",
                })
            except Exception as exc:
                results.append({
                    "item_id": preview["item_id"],
                    "path": preview["source_path"],
                    "size": self.img_tree.item(preview["item_id"])["values"][1],
                    "status": f"Error: {exc}",
                })

            if progress_callback:
                progress_callback(index, total, "Converting...")

        return {"cancelled": False, "results": results}

    def _on_img_convert_complete(self, outcome):
        if not outcome:
            self.app.update_status("Batch Complete")
            return

        completed = 0
        failed = 0
        selected_item_ids = []
        for result in outcome["results"]:
            self.img_tree.set(result["item_id"], "path", result["path"])
            self.img_tree.set(result["item_id"], "size", result["size"])
            self.img_tree.set(result["item_id"], "status", result["status"])
            if result["status"] == "Done":
                completed += 1
                selected_item_ids.append(result["item_id"])
            else:
                failed += 1

        self.restore_tree_selection(self.img_tree, selected_item_ids, on_select=self.on_img_select)
        attempted = len(outcome["results"])

        if outcome["cancelled"]:
            self.app.update_status(f"Batch Cancelled ({completed} completed, {failed} failed)")
            self.app.show_warning_dialog("Cancelled", self.summarize_completion("Image conversion stopped.", attempted, completed, failed, created=completed))
        else:
            self.app.update_status(f"Batch Complete ({completed} completed, {failed} failed)")
            self.app.show_info_dialog("Complete", self.summarize_completion("Image conversion complete.", attempted, completed, failed, created=completed))

    def browse_file(self, entry, name, ext):
        p, _ = dialogs.get_open_file_name(self, f"Select {name} File", "", f"{name} Files ({ext});;All Files (*)")
        if p:
            entry.setText(p)
