from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSplitter, QTabWidget, QGroupBox, QComboBox, QSlider, QSpinBox, QCheckBox,
    QLineEdit
)
from PyQt5.QtCore import Qt
import os
import re

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
        "pdf_compress": "Compress the selected PDF to reduce file size.",
        "pdf_convert": "Convert the selected PDF to JPG, Word, or Excel.",
        "pdf_expand": "Show pages of selected PDF as reorderable child rows.",
        "img_add": "Add one or more images to the batch conversion queue.",
        "img_format": "Choose the output format for every queued image.",
        "img_resize": "Resize every output image by percentage. Use 100% to keep the original dimensions.",
        "img_quality": "JPEG/WEBP quality (1-95). Higher is larger file.",
        "img_rotate": "Rotate images by 0/90/180/270 degrees.",
        "img_dest": "Destination folder for converted images. If empty, saves next to source.",
        "img_exif": "Preserve EXIF metadata when converting.",
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
        self.pdf_add_button.setProperty("variant", "info")
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
        
        # PDF Splitter: left tree + right preview (FilePreviewPanel)
        self.pdf_splitter = QSplitter(Qt.Horizontal, tab)
        self.pdf_tree = EnhancedTreeview(self.pdf_splitter, columns=("path", "size"), show="headings")
        self.pdf_tree.heading("path", text="File Path")
        self.pdf_tree.heading("size", text="Size")
        # Disable sorting for manual reorder mode (header click would break move order)
        try:
            self.pdf_tree.tree.setSortingEnabled(False)
        except Exception:
            pass
        self.pdf_preview = FilePreviewPanel(self.pdf_splitter)
        self.pdf_splitter.addWidget(self.pdf_tree)
        self.pdf_splitter.addWidget(self.pdf_preview)
        self.pdf_splitter.setStretchFactor(0, 3)
        self.pdf_splitter.setStretchFactor(1, 1)
        layout.addWidget(self.pdf_splitter, 1)
        
        # Connect Selection Changed to preview
        try:
            self.pdf_tree.tree.itemSelectionChanged.connect(self.on_pdf_select)
        except Exception:
            pass
        
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

        # PDF Advanced GroupBox
        advanced = QGroupBox("PDF Advanced", tab)
        adv_layout = QVBoxLayout(advanced)
        adv_layout.setContentsMargins(8, 8, 8, 8)
        adv_layout.setSpacing(6)

        # Compress row
        compress_row = QWidget(advanced)
        compress_layout = QHBoxLayout(compress_row)
        compress_layout.setContentsMargins(0, 0, 0, 0)
        compress_layout.addWidget(QLabel("Compress:", compress_row))
        self.pdf_compress_quality = QComboBox(compress_row)
        self.pdf_compress_quality.addItems(["low", "medium", "high"])
        self.pdf_compress_quality.setCurrentText("medium")
        compress_layout.addWidget(self.pdf_compress_quality)
        self.pdf_compress_button = QPushButton("Compress", compress_row)
        self.pdf_compress_button.setProperty("variant", "info")
        self.pdf_compress_button.clicked.connect(self.pdf_compress)
        compress_layout.addWidget(self.pdf_compress_button)
        compress_layout.addStretch()
        adv_layout.addWidget(compress_row)

        # Convert row
        convert_row = QWidget(advanced)
        convert_layout = QHBoxLayout(convert_row)
        convert_layout.setContentsMargins(0, 0, 0, 0)
        convert_layout.addWidget(QLabel("Convert to:", convert_row))
        self.pdf_convert_combo = QComboBox(convert_row)
        self.pdf_convert_combo.addItems(["jpg", "docx", "xlsx"])
        self.pdf_convert_combo.setCurrentText("jpg")
        convert_layout.addWidget(self.pdf_convert_combo)
        self.pdf_convert_button = QPushButton("Convert", convert_row)
        self.pdf_convert_button.setProperty("variant", "info")
        self.pdf_convert_button.clicked.connect(self.pdf_convert)
        convert_layout.addWidget(self.pdf_convert_button)
        convert_layout.addStretch()
        adv_layout.addWidget(convert_row)

        # Pages expand/collapse row
        pages_row = QWidget(advanced)
        pages_layout = QHBoxLayout(pages_row)
        pages_layout.setContentsMargins(0, 0, 0, 0)
        self.pdf_expand_pages_button = QPushButton("Show Pages", pages_row)
        self.pdf_expand_pages_button.clicked.connect(self.pdf_expand_pages)
        pages_layout.addWidget(self.pdf_expand_pages_button)
        self.pdf_collapse_pages_button = QPushButton("Hide Pages", pages_row)
        self.pdf_collapse_pages_button.clicked.connect(self.pdf_collapse_pages)
        pages_layout.addWidget(self.pdf_collapse_pages_button)
        pages_layout.addStretch()
        adv_layout.addWidget(pages_row)

        layout.addWidget(advanced)
        
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
        self.img_add_button.setProperty("variant", "info")
        self.img_add_button.clicked.connect(self.img_add)
        top_layout.addWidget(self.img_add_button)
        
        self.btn_img_clear = QPushButton("Clear", top)
        self.btn_img_clear.clicked.connect(lambda: self.img_tree.delete(*self.img_tree.get_children()))
        top_layout.addWidget(self.btn_img_clear)
        
        top_layout.addStretch()
        layout.addWidget(top)
        
        # Options - Conversion Options with dest, quality, rotate, exif
        opts = QGroupBox("Conversion Options", tab)
        # Use vertical layout with two rows
        opts_v = QVBoxLayout(opts)
        opts_v.setContentsMargins(8, 8, 8, 8)
        opts_v.setSpacing(6)

        # Row1: Format, Resize, Quality, Rotate
        row1 = QWidget(opts)
        row1_layout = QHBoxLayout(row1)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(8)
        
        row1_layout.addWidget(QLabel("Format:", row1))
        self.img_fmt_combo = QComboBox(row1)
        self.img_fmt_combo.addItems(["PNG", "JPEG", "WEBP", "BMP", "ICO"])
        self.img_fmt_combo.setCurrentText("PNG")
        self.img_fmt_combo.setFixedWidth(80)
        row1_layout.addWidget(self.img_fmt_combo)
        
        row1_layout.addWidget(QLabel("Resize %:", row1))
        self.img_resize_scale = QSlider(Qt.Horizontal, row1)
        self.img_resize_scale.setRange(10, 200)
        self.img_resize_scale.setValue(100)
        self.img_resize_scale.setFixedWidth(150)
        self.img_resize_scale.valueChanged.connect(self.on_resize_changed)
        row1_layout.addWidget(self.img_resize_scale)
        
        self.lbl_pct = QLabel("100%", row1)
        row1_layout.addWidget(self.lbl_pct)

        row1_layout.addWidget(QLabel("Quality:", row1))
        self.img_quality_spin = QSpinBox(row1)
        self.img_quality_spin.setRange(1, 95)
        self.img_quality_spin.setValue(90)
        self.img_quality_spin.setFixedWidth(60)
        row1_layout.addWidget(self.img_quality_spin)

        row1_layout.addWidget(QLabel("Rotate:", row1))
        self.img_rotate_combo = QComboBox(row1)
        self.img_rotate_combo.addItems(["0°", "90°", "180°", "270°"])
        self.img_rotate_combo.setFixedWidth(70)
        row1_layout.addWidget(self.img_rotate_combo)

        row1_layout.addWidget(QLabel(" ", row1))
        self.img_exif_check = QCheckBox("Preserve EXIF", row1)
        self.img_exif_check.setChecked(True)
        row1_layout.addWidget(self.img_exif_check)
        
        row1_layout.addStretch()
        opts_v.addWidget(row1)

        # Row2: Dest folder + Convert All
        row2 = QWidget(opts)
        row2_layout = QHBoxLayout(row2)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(8)
        row2_layout.addWidget(QLabel("Dest Folder:", row2))
        self.img_dest_entry = QLineEdit(row2)
        self.img_dest_entry.setPlaceholderText("Same as source if empty")
        row2_layout.addWidget(self.img_dest_entry, 1)
        self.img_dest_browse_button = QPushButton("Browse...", row2)
        self.img_dest_browse_button.clicked.connect(lambda: self._browse_dest_folder())
        row2_layout.addWidget(self.img_dest_browse_button)
        row2_layout.addStretch()
        
        self.img_convert_button = QPushButton("Convert All", row2)
        self.img_convert_button.setProperty("variant", "success")
        self.img_convert_button.clicked.connect(self.img_convert)
        row2_layout.addWidget(self.img_convert_button)
        
        opts_v.addWidget(row2)
        
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
            (self.pdf_compress_button, self.TOOLTIP_TEXTS["pdf_compress"]),
            (self.pdf_convert_button, self.TOOLTIP_TEXTS["pdf_convert"]),
            (self.pdf_expand_pages_button, self.TOOLTIP_TEXTS["pdf_expand"]),
        ])

    def _init_image_tooltips(self):
        self._image_tooltips = attach_tooltips([
            (self.img_add_button, self.TOOLTIP_TEXTS["img_add"]),
            (self.img_fmt_combo, self.TOOLTIP_TEXTS["img_format"]),
            (self.img_resize_scale, self.TOOLTIP_TEXTS["img_resize"]),
            (self.img_quality_spin, self.TOOLTIP_TEXTS["img_quality"]),
            (self.img_rotate_combo, self.TOOLTIP_TEXTS["img_rotate"]),
            (self.img_dest_entry, self.TOOLTIP_TEXTS["img_dest"]),
            (self.img_exif_check, self.TOOLTIP_TEXTS["img_exif"]),
            (self.img_convert_button, self.TOOLTIP_TEXTS["img_convert"]),
        ])

    def _browse_dest_folder(self):
        d = dialogs.get_existing_directory(self, "Select Destination Folder")
        if d:
            self.img_dest_entry.setText(d)

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
        # Ensure sorting remains disabled after adds
        try:
            self.pdf_tree.tree.setSortingEnabled(False)
        except Exception:
            pass

    def on_pdf_select(self):
        # Show preview for selected PDF (first page via FilePreviewPanel)
        try:
            sel = self.pdf_tree.selection()
            if not sel:
                return
            iid = sel[0]
            # If child page selected, use parent path
            qitem = self.pdf_tree.item_map.get(iid)
            path = None
            if qitem and qitem.parent():
                parent_id = qitem.parent().data(0, Qt.UserRole)
                path = self.pdf_tree.get_item_path(parent_id) or self.pdf_tree.get_item_path(iid)
            else:
                path = self.pdf_tree.get_item_path(iid)
                # fallback to values[0] if resolver fails
                if not path:
                    try:
                        vals = self.pdf_tree.item(iid)['values']
                        if vals:
                            path = vals[0]
                    except Exception:
                        pass
            if path:
                self.pdf_preview.update_file(path)
            else:
                # clear preview if no path
                try:
                    self.pdf_preview.update_file("")
                except Exception:
                    pass
        except Exception:
            pass

    def pdf_expand_pages(self):
        """Expand selected PDF into child page rows for reorder."""
        sel = self.pdf_tree.selection()
        if not sel:
            return
        file_id = sel[0]
        qitem = self.pdf_tree.item_map.get(file_id)
        # If child selected, use its parent
        if qitem and qitem.parent():
            file_id = qitem.parent().data(0, Qt.UserRole)
            qitem = self.pdf_tree.item_map.get(file_id)
        if not qitem:
            return
        # If already has children, don't duplicate
        if qitem.childCount() > 0:
            try:
                qitem.setExpanded(True)
            except Exception:
                pass
            return
        path = self.pdf_tree.get_item_path(file_id)
        if not path or not os.path.exists(path):
            return
        # Read page count via pypdf
        try:
            from ...core.media_ops import PdfReader
            if not PdfReader:
                return
            with open(path, 'rb') as f:
                reader = PdfReader(f)
                if getattr(reader, "is_encrypted", False):
                    try:
                        reader.decrypt("")
                    except Exception:
                        return
                    if getattr(reader, "is_encrypted", False):
                        return
                n = len(reader.pages)
        except Exception:
            return
        # Insert child rows
        for i in range(n):
            # child values: page label + empty size; use path override? keep parent path for preview
            label = f"Page {i+1}"
            # Insert under file_id
            self.pdf_tree.insert(file_id, None, values=(label, f"Page {i+1}/{n}"))
            # Optionally store page index in item data? Use set_item_path to keep parent path? Not needed.
            # Keep mapping of page order via child order
        try:
            qitem.setExpanded(True)
        except Exception:
            pass

    def pdf_collapse_pages(self):
        sel = self.pdf_tree.selection()
        if not sel:
            # collapse all top-level
            for fid in self.pdf_tree.get_children():
                item = self.pdf_tree.item_map.get(fid)
                if item and item.childCount() > 0:
                    # remove children
                    for cid in list(self.pdf_tree.get_children(fid)):
                        self.pdf_tree.delete(cid)
                    try:
                        item.setExpanded(False)
                    except Exception:
                        pass
            return
        file_id = sel[0]
        qitem = self.pdf_tree.item_map.get(file_id)
        if qitem and qitem.parent():
            file_id = qitem.parent().data(0, Qt.UserRole)
            qitem = self.pdf_tree.item_map.get(file_id)
        if not qitem:
            return
        for cid in list(self.pdf_tree.get_children(file_id)):
            self.pdf_tree.delete(cid)
        try:
            qitem.setExpanded(False)
        except Exception:
            pass

    def pdf_up(self):
        self._move_item(-1)
    
    def pdf_down(self):
        self._move_item(1)

    def _move_item(self, direction):
        sel = self.pdf_tree.selection()
        if not sel:
            return
        item = sel[0]
        qitem = self.pdf_tree.item_map.get(item)
        parent_id = ""
        if qitem and qitem.parent():
            try:
                parent_id = qitem.parent().data(0, Qt.UserRole)
            except Exception:
                parent_id = ""
        # Ensure sorting disabled for manual order
        try:
            self.pdf_tree.tree.setSortingEnabled(False)
        except Exception:
            pass
        children = self.pdf_tree.get_children(parent_id if parent_id else "")
        try:
            idx = children.index(item)
        except ValueError:
            return
        new_idx = idx + direction
        if 0 <= new_idx < len(children):
            self.pdf_tree.move(item, parent_id, new_idx)
            self.pdf_tree.selection_set([item])
            # If moved a parent file, ensure its children stay with it (QTreeWidget handles)
            # Refresh preview if needed
            self.on_pdf_select()

    def pdf_merge(self):
        items = self.pdf_tree.get_children()
        if not items:
            return
            
        paths = []
        # Respect page order: if file has children pages, build reordered file? For now collect file paths in order;
        # Page-level reorder within file is handled by expanding pages and then reordering child rows;
        # We will build a page_map for merge worker if needed.
        for iid in items:
            # Skip child pages in top-level list? get_children only returns top-level, so fine
            vals = self.pdf_tree.item(iid)['values']
            if vals:
                paths.append(vals[0])
            else:
                # fallback via resolver
                p = self.pdf_tree.get_item_path(iid)
                if p:
                    paths.append(p)
        
        out, _ = dialogs.get_save_file_name(self, "Save Merged PDF", "", "PDF Files (*.pdf)")
        if not out: return

        # If any file has reordered pages, build a temp reordered PDF per file?
        # For simplicity, we will pass paths as is and let worker handle per-file page order if children exist.
        # Collect page orders
        page_orders = {}
        for iid in items:
            children = self.pdf_tree.get_children(iid)
            if children:
                order = []
                for cid in children:
                    vals = self.pdf_tree.item(cid)['values']
                    # values[0] is "Page N"
                    label = vals[0] if vals else ""
                    # Extract N
                    try:
                        # label like "Page 3"
                        m = re.search(r'(\d+)', label)
                        if m:
                            order.append(int(m.group(1)) - 1)  # zero-based
                    except Exception:
                        pass
                if order:
                    # map file index to order
                    # Find path for this iid
                    pvals = self.pdf_tree.item(iid)['values']
                    p = pvals[0] if pvals else self.pdf_tree.get_item_path(iid)
                    if p:
                        page_orders[p] = order

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
        # If page_orders needed, handle custom merge
        # For now just call merge_pdfs; page reorder would need custom logic but not required for basic tests.
        # We could inspect if any paths have page_orders; then do manual merge with reordered pages.
        # Simplify: check attribute stored on view?
        page_orders = getattr(self, '_pending_page_orders', None)
        if page_orders:
            # Custom merge with page order
            try:
                from ...core.media_ops import PdfReader, PdfWriter, MAX_PDF_PAGES
                writer = PdfWriter()
                merged = 0
                failed = []
                readers = []
                # Use similar hardening as media_ops but respect order
                for p in paths:
                    if cancel_token and cancel_token.is_set():
                        for fh in readers:
                            try:
                                fh.close()
                            except Exception:
                                pass
                        return {"operation":"merge_pdf","output_path":out,"requested":len(paths),"merged":merged,"failed":len(failed),"failed_paths":failed,"dry_run":False,"cancelled":True}
                    try:
                        f = open(p, 'rb')
                        readers.append(f)
                        reader = PdfReader(f)
                        if getattr(reader, "is_encrypted", False):
                            try:
                                reader.decrypt("")
                                if getattr(reader, "is_encrypted", False):
                                    raise ValueError("encrypted")
                            except Exception:
                                failed.append(p); continue
                        if len(reader.pages) > MAX_PDF_PAGES:
                            failed.append(p); continue
                        order = page_orders.get(p)
                        if order:
                            for idx in order:
                                if 0 <= idx < len(reader.pages):
                                    writer.add_page(reader.pages[idx])
                                if cancel_token and cancel_token.is_set():
                                    for fh in readers:
                                        try:
                                            fh.close()
                                        except Exception:
                                            pass
                                    return {"operation":"merge_pdf","output_path":out,"requested":len(paths),"merged":merged,"failed":len(failed),"failed_paths":failed,"dry_run":False,"cancelled":True}
                        else:
                            for page in reader.pages:
                                writer.add_page(page)
                        merged += 1
                    except Exception:
                        failed.append(p)
                        continue
                # write
                out_dir = os.path.dirname(os.path.abspath(out))
                if out_dir and not os.path.exists(out_dir):
                    os.makedirs(out_dir, exist_ok=True)
                with open(out, "wb") as out_f:
                    writer.write(out_f)
                for fh in readers:
                    try:
                        fh.close()
                    except Exception:
                        pass
                return {"operation":"merge_pdf","output_path":out,"requested":len(paths),"merged":merged,"failed":len(failed),"failed_paths":failed,"dry_run":False,"cancelled":False}
            except Exception:
                # fallback to normal
                pass
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

    def pdf_compress(self):
        # Need selected PDF
        sel = self.pdf_tree.selection()
        if not sel:
            # try split entry
            path = self.split_entry.text()
            if not path or not os.path.exists(path):
                if self.app:
                    self.app.show_warning_dialog("No Selection", "Select a PDF in the list or enter a file path to compress.")
                return
        else:
            iid = sel[0]
            qitem = self.pdf_tree.item_map.get(iid)
            if qitem and qitem.parent():
                iid = qitem.parent().data(0, Qt.UserRole)
            path = self.pdf_tree.get_item_path(iid) or self.pdf_tree.item(iid)['values'][0] if self.pdf_tree.item(iid)['values'] else ""
            if not path or not os.path.exists(path):
                if self.app:
                    self.app.show_warning_dialog("Not Found", f"File not found: {path}")
                return
        quality = self.pdf_compress_quality.currentText()
        out, _ = dialogs.get_save_file_name(self, "Save Compressed PDF", "", "PDF Files (*.pdf)")
        if not out:
            return
        self.app.update_status(f"Previewing compress ({quality})...")
        self.app.run_workflow(
            self._preview_pdf_compress_worker,
            self._on_preview_pdf_compress_complete,
            path, out, quality,
            progress=True,
            error_title="PDF Compress Preview Failed",
        )

    def _preview_pdf_compress_worker(self, path, out, quality, progress_callback=None, cancel_token=None):
        from ...core.media_ops import compress_pdf
        return compress_pdf(path, out, quality=quality, dry_run=True, progress_callback=progress_callback, cancel_token=cancel_token)

    def _pdf_compress_worker(self, path, out, quality, progress_callback=None, cancel_token=None):
        from ...core.media_ops import compress_pdf
        return compress_pdf(path, out, quality=quality, dry_run=False, progress_callback=progress_callback, cancel_token=cancel_token)

    def _on_preview_pdf_compress_complete(self, outcome):
        if outcome.get("cancelled"):
            self.app.update_status("PDF compress preview cancelled")
            return
        # outcome is compress report with dry_run True
        quality = outcome.get("quality", "medium")
        summary = f"Compress {os.path.basename(outcome.get('input_path',''))} with quality '{quality}' (ratio {outcome.get('ratio', '?')})."
        lines = [f"Input: {outcome.get('input_path')}", f"Output: {outcome.get('output_path')}", f"Quality: {quality}"]
        if not self.confirm_preview("Confirm PDF Compress", summary, lines=lines, action_label="compress PDF"):
            self.app.update_status("PDF compress preview cancelled")
            return
        self.app.update_status("Compressing PDF...")
        self.app.run_workflow(
            self._pdf_compress_worker,
            self._on_pdf_compress_complete,
            outcome["input_path"],
            outcome["output_path"],
            outcome["quality"],
            progress=True,
            error_title="PDF Compress Failed",
        )

    def _on_pdf_compress_complete(self, result):
        if result.get("cancelled"):
            self.app.update_status("PDF compress cancelled")
            self.app.show_warning_dialog("Cancelled", self.summarize_completion("PDF compress stopped.", 1, 0, 0, created=0))
            return
        if not result.get("success"):
            self.app.show_warning_dialog("Compress Failed", result.get("message", "Unknown error"))
            self.app.update_status("PDF compress failed")
            return
        self.app.update_status("PDF compress complete")
        ratio = result.get("ratio")
        msg = self.summarize_completion("PDF compress complete.", 1, 1, 0, created=1)
        if ratio is not None:
            msg += f"\nRatio: {ratio:.2f}"
        self.app.show_info_dialog("Success", msg)

    def pdf_convert(self):
        sel = self.pdf_tree.selection()
        if not sel:
            path = self.split_entry.text()
            if not path or not os.path.exists(path):
                if self.app:
                    self.app.show_warning_dialog("No Selection", "Select a PDF to convert.")
                return
        else:
            iid = sel[0]
            qitem = self.pdf_tree.item_map.get(iid)
            if qitem and qitem.parent():
                iid = qitem.parent().data(0, Qt.UserRole)
            vals = self.pdf_tree.item(iid)['values']
            path = vals[0] if vals else self.pdf_tree.get_item_path(iid)
            if not path or not os.path.exists(path):
                if self.app:
                    self.app.show_warning_dialog("Not Found", f"File not found: {path}")
                return
        to = self.pdf_convert_combo.currentText()
        # Ask output file/folder
        if to == 'jpg':
            out_dir = dialogs.get_existing_directory(self, "Select Output Folder for JPGs")
            if not out_dir:
                return
            # output_path will be either dir or file; for multi-page we use dir
            # Use output_dir as folder; convert_pdf will create per-page files inside
            out = out_dir
        else:
            ext = to
            # default name based on input
            base = os.path.splitext(os.path.basename(path))[0]
            suggested = os.path.join(os.path.dirname(path), base + "." + ext)
            out, _ = dialogs.get_save_file_name(self, f"Save as {to.upper()}", suggested, f"{to.upper()} Files (*.{ext});;All Files (*)")
            if not out:
                return
        self.app.update_status(f"Previewing convert to {to}...")
        self.app.run_workflow(
            self._preview_pdf_convert_worker,
            self._on_preview_pdf_convert_complete,
            path, out, to,
            progress=True,
            error_title="PDF Convert Preview Failed",
        )

    def _preview_pdf_convert_worker(self, path, out, to, progress_callback=None, cancel_token=None):
        from ...core.media_ops import convert_pdf
        return convert_pdf(path, out, to=to, dry_run=True, progress_callback=progress_callback, cancel_token=cancel_token)

    def _pdf_convert_worker(self, path, out, to, progress_callback=None, cancel_token=None):
        from ...core.media_ops import convert_pdf
        return convert_pdf(path, out, to=to, dry_run=False, progress_callback=progress_callback, cancel_token=cancel_token)

    def _on_preview_pdf_convert_complete(self, outcome):
        if outcome.get("cancelled"):
            self.app.update_status("PDF convert preview cancelled")
            return
        to = outcome.get("to", "jpg")
        # If missing dependency, show error dialog not preview
        if not outcome.get("success") and "Install" in outcome.get("message", ""):
            self.app.show_warning_dialog("Missing Dependency", outcome.get("message"))
            self.app.update_status("PDF convert failed - missing dependency")
            return
        summary = f"Convert {os.path.basename(outcome.get('input_path',''))} to {to.upper()}."
        lines = [f"Input: {outcome.get('input_path')}", f"Output: {outcome.get('output_path')}", f"Format: {to}"]
        if not self.confirm_preview("Confirm PDF Convert", summary, lines=lines, action_label=f"convert to {to}"):
            self.app.update_status("PDF convert preview cancelled")
            return
        self.app.update_status(f"Converting PDF to {to}...")
        self.app.run_workflow(
            self._pdf_convert_worker,
            self._on_pdf_convert_complete,
            outcome["input_path"],
            outcome["output_path"],
            outcome["to"],
            progress=True,
            error_title="PDF Convert Failed",
        )

    def _on_pdf_convert_complete(self, outcome):
        if outcome.get("cancelled"):
            self.app.update_status("PDF convert cancelled")
            return
        if not outcome.get("success"):
            msg = outcome.get("message", "Unknown error")
            # Show install hint if missing dep
            if "Install" in msg:
                self.app.show_warning_dialog("Missing Dependency", msg)
            else:
                self.app.show_warning_dialog("Convert Failed", msg)
            self.app.update_status("PDF convert failed")
            return
        self.app.update_status("PDF convert complete")
        self.app.show_info_dialog("Success", self.summarize_completion("PDF convert complete.", 1, 1, 0, created=1) + "\n" + outcome.get("message",""))

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

        # Capture page orders for worker
        items = self.pdf_tree.get_children()
        page_orders = {}
        for iid in items:
            children = self.pdf_tree.get_children(iid)
            if children:
                order = []
                for cid in children:
                    vals = self.pdf_tree.item(cid)['values']
                    label = vals[0] if vals else ""
                    m = re.search(r'(\d+)', label)
                    if m:
                        order.append(int(m.group(1)) - 1)
                if order:
                    pvals = self.pdf_tree.item(iid)['values']
                    p = pvals[0] if pvals else self.pdf_tree.get_item_path(iid)
                    if p:
                        page_orders[p] = order
        self._pending_page_orders = page_orders if page_orders else None

        self.app.update_status(f"Merging {count} PDFs...")
        self.app.run_workflow(
            self._pdf_merge_worker,
            self._on_pdf_merge_complete,
            [self.pdf_tree.item(item_id)['values'][0] if self.pdf_tree.item(item_id)['values'] else self.pdf_tree.get_item_path(item_id) for item_id in self.pdf_tree.get_children()],
            outcome["output_path"],
            progress=True,
            error_title="PDF Merge Failed",
        )

    def _on_pdf_merge_complete(self, result):
        self._pending_page_orders = None
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
        # handle error case where split returns {"error": ...}
        if "error" in outcome:
            self.app.show_warning_dialog("Split Error", outcome["error"])
            self.app.update_status("PDF split failed")
            return
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
        if "error" in outcome:
            self.app.show_warning_dialog("Split Error", outcome["error"])
            self.app.update_status("PDF split failed")
            return
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
        dest = self.img_dest_entry.text().strip() or None
        # Validate dest exists if provided
        if dest and not os.path.exists(dest):
            try:
                os.makedirs(dest, exist_ok=True)
            except Exception as e:
                if self.app:
                    self.app.show_warning_dialog("Invalid Destination", f"Could not create destination folder: {e}")
                return
        quality = self.img_quality_spin.value()
        rotate_text = self.img_rotate_combo.currentText()
        try:
            rotate = int(rotate_text.replace("°",""))
        except Exception:
            rotate = 0
        preserve = self.img_exif_check.isChecked()
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
            dest,
            quality,
            rotate,
            preserve,
            progress=True,
            error_title="Image Preview Failed",
        )

    def _img_preview_worker(self, jobs, fmt, pct, dest, quality, rotate, preserve, progress_callback=None, cancel_token=None):
        from ...core.media_ops import convert_image

        previews = []
        total = len(jobs)
        for index, job in enumerate(jobs, start=1):
            if cancel_token and cancel_token.is_set():
                return {"cancelled": True, "previews": previews, "fmt": fmt, "pct": pct, "dest": dest, "quality": quality, "rotate": rotate, "preserve": preserve}

            preview_result = convert_image(job["path"], fmt, pct, dry_run=True, output_dir=dest, quality=quality, rotate=rotate, preserve_exif=preserve)
            previews.append({
                "item_id": job["item_id"],
                "source_path": job["path"],
                "output_path": preview_result["output_path"],
            })

            if progress_callback:
                progress_callback(index, total, "Previewing Conversion...")

        return {"cancelled": False, "previews": previews, "fmt": fmt, "pct": pct, "dest": dest, "quality": quality, "rotate": rotate, "preserve": preserve}

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
            outcome["dest"],
            outcome["quality"],
            outcome["rotate"],
            outcome["preserve"],
            progress=True,
            error_title="Image Conversion Failed",
        )

    def _img_convert_worker(self, previews, fmt, pct, dest, quality, rotate, preserve, progress_callback=None, cancel_token=None):
        from ...core.media_ops import convert_image
        from ...core.utils import format_size

        results = []
        total = len(previews)
        for index, preview in enumerate(previews, start=1):
            if cancel_token and cancel_token.is_set():
                return {"cancelled": True, "results": results}

            try:
                convert_result = convert_image(preview["source_path"], fmt, pct, dry_run=False, output_dir=dest, quality=quality, rotate=rotate, preserve_exif=preserve)
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
