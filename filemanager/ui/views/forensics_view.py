"""
Forensics Lab GUI view.

Multi-tab forensic analysis workbench with disk image ingestion,
hash calculator, OS artifact parser, and password tools.
"""
import os
import json

# NOTE: `json` is used by the Integrity tab to write/read baseline snapshots.
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QGroupBox, QGridLayout, QTabWidget, QLineEdit, QTextEdit,
    QCheckBox, QComboBox, QMessageBox, QSpinBox, QSplitter
)
from PyQt5.QtCore import Qt

from .base import BaseView
from .. import dialogs
from ..widgets import EnhancedTreeview, CollapsibleCard, attach_tooltips
from ...core.utils import format_size
from ...modules.forensics import (
    calculate_hashes,
    verify_hash,
    parse_os_artifacts,
    keyword_search,
    ingest_disk_image,
    generate_forensic_report,
    identify_file_by_signature,
    profile_directory_types,
    calculate_entropy,
    calculate_entropy_batch,
    build_timeline,
    hex_dump,
    detect_steganography,
    secure_delete,
    snapshot_file_state,
    verify_file_state,
    collect_recent_documents,
)
from ...modules.password_tools import (
    extract_password_hashes,
    generate_crackable_hash,
    run_dictionary_attack,
    analyze_password_strength,
    check_hashcat_available,
    check_john_available,
    check_zip2john_available,
    check_pdf2john_available,
    list_common_wordlists,
)


class ForensicsView(BaseView):
    TOOLTIP_TEXTS = {
        "ingest_path": "Path to a mounted disk image directory or filesystem root for analysis.",
        "output_dir": "Directory where forensic reports and extracted data will be saved.",
        "ingest_start": "Run the automated forensic ingestion pipeline on the target.",
        "hash_files": "Select files to calculate cryptographic hashes (MD5, SHA-256, etc.).",
        "verify_hash": "Verify a file against a known hash value.",
        "artifact_path": "Root directory of the filesystem to parse for OS artifacts.",
        "parse_artifacts": "Extract user accounts, logs, history, cron jobs, and other OS artifacts.",
        "hash_source": "Path to a file containing password hashes (e.g., /etc/shadow, .zip, .pdf).",
        "strength_check": "Analyze the strength of passwords.",
    }

    def get_title(self):
        return "Forensics Lab"

    def __init__(self, master, app=None):
        super().__init__(master, app)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Warning banner
        warning = QLabel(
            "⚠️ Forensics Lab — Use responsibly. Some features require elevated "
            "privileges and carry legal implications. Never analyze data you don't "
            "have authorization to examine.",
            self,
        )
        warning.setStyleSheet(
            "background-color: #fef3c7; color: #92400e; padding: 8px; "
            "border: 1px solid #f59e0b; border-radius: 4px; font-weight: bold;"
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, 1)

        # ===== Tab 1: Disk Image Analysis =====
        self._build_ingestion_tab()

        # ===== Tab 2: Hash Calculator =====
        self._build_hash_tab()

        # ===== Tab 3: OS Artifact Parser =====
        self._build_artifact_tab()

        # ===== Tab 4: Password Tools =====
        self._build_password_tab()

        # ===== Tab 5: File Type Profiler =====
        self._build_filetype_tab()

        # ===== Tab 6: Entropy Analyzer =====
        self._build_entropy_tab()

        # ===== Tab 7: Timeline Builder =====
        self._build_timeline_tab()

        # ===== Tab 8: Hex Viewer =====
        self._build_hex_tab()

        # ===== Tab 9: Steganography Detector =====
        self._build_stego_tab()

        # ===== Tab 10: Secure Delete =====
        self._build_secure_delete_tab()

        # ===== Tab 11: Integrity Snapshot =====
        self._build_integrity_tab()

        self._init_tooltips()

    # ------------------------------------------------------------------
    # Tab 1: Disk Image Ingestion
    # ------------------------------------------------------------------

    def _build_ingestion_tab(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(5, 5, 5, 5)

        # Config
        card = CollapsibleCard(tab, title="Ingestion Configuration")
        tab_layout.addWidget(card)

        body = card.get_body()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 5, 0, 0)
        body_layout.setSpacing(6)

        # Image path
        p_frame = QWidget(body)
        p_layout = QHBoxLayout(p_frame)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.addWidget(QLabel("Target Path:"))
        self.ingest_path = QLineEdit(p_frame)
        self.ingest_path.setPlaceholderText("/path/to/mounted/image or /mnt/evidence")
        p_layout.addWidget(self.ingest_path)
        btn_browse = QPushButton("Browse", p_frame)
        btn_browse.clicked.connect(lambda: self._browse_to(self.ingest_path))
        p_layout.addWidget(btn_browse)
        body_layout.addWidget(p_frame)

        # Output dir
        o_frame = QWidget(body)
        o_layout = QHBoxLayout(o_frame)
        o_layout.setContentsMargins(0, 0, 0, 0)
        o_layout.addWidget(QLabel("Output Dir:"))
        self.ingest_output = QLineEdit(o_frame)
        self.ingest_output.setPlaceholderText("/path/to/forensic/output")
        o_layout.addWidget(self.ingest_output)
        btn_out = QPushButton("Browse", o_frame)
        btn_out.clicked.connect(lambda: self._browse_to(self.ingest_output))
        o_layout.addWidget(btn_out)
        body_layout.addWidget(o_frame)

        # Options
        opt_group = QGroupBox("Pipeline Options", body)
        opt_grid = QGridLayout(opt_group)
        self.chk_hash = QCheckBox("Calculate Hashes (MD5 + SHA-256)", opt_group)
        self.chk_hash.setChecked(True)
        opt_grid.addWidget(self.chk_hash, 0, 0)
        self.chk_artifacts = QCheckBox("Parse OS Artifacts", opt_group)
        self.chk_artifacts.setChecked(True)
        opt_grid.addWidget(self.chk_artifacts, 0, 1)
        self.chk_keywords = QCheckBox("Keyword Index", opt_group)
        opt_grid.addWidget(self.chk_keywords, 1, 0)
        self.keywords_entry = QLineEdit(opt_group)
        self.keywords_entry.setPlaceholderText("password,secret,confidential (comma-separated)")
        opt_grid.addWidget(self.keywords_entry, 1, 1)
        body_layout.addWidget(opt_group)

        # Run button
        self.btn_ingest = card.add_widget_to_header(QPushButton, text="RUN INGESTION")
        self.btn_ingest.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold;")
        self.btn_ingest.clicked.connect(self._start_ingestion)

        self.lbl_ingest_status = QLabel("Configure target and options, then run ingestion.", body)
        self.lbl_ingest_status.setStyleSheet("color: #6c757d;")
        self.lbl_ingest_status.setWordWrap(True)
        body_layout.addWidget(self.lbl_ingest_status)

        # Results
        self.ingest_tree = EnhancedTreeview(
            tab, columns=("category", "count", "details"), app=self.app,
        )
        self.ingest_tree.heading("category", text="Category")
        self.ingest_tree.heading("count", text="Count")
        self.ingest_tree.column("count", width=70, stretch=False)
        self.ingest_tree.heading("details", text="Details")
        # Summary rows don't represent filesystem entries — hide Open/Rename/
        # Move/Copy/Delete so right-click doesn't offer dead actions.
        self.ingest_tree.set_no_file_actions(True)
        tab_layout.addWidget(self.ingest_tree, 1)

        # Export
        export_frame = QWidget(tab)
        ef_layout = QHBoxLayout(export_frame)
        ef_layout.setContentsMargins(0, 5, 0, 0)
        self.btn_export_report = QPushButton("📄 Export Forensic Report", export_frame)
        self.btn_export_report.clicked.connect(self._export_report)
        ef_layout.addWidget(self.btn_export_report)
        ef_layout.addStretch()
        tab_layout.addWidget(export_frame)

        self.tabs.addTab(tab, "💿 Disk Analysis")
        self.last_ingest_results = None

    # ------------------------------------------------------------------
    # Tab 2: Hash Calculator
    # ------------------------------------------------------------------

    def _build_hash_tab(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(5, 5, 5, 5)

        # Controls
        header = QWidget(tab)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 5)

        self.btn_add_hash_files = QPushButton("📁 Add Files", header)
        self.btn_add_hash_files.clicked.connect(self._add_hash_files)
        h_layout.addWidget(self.btn_add_hash_files)

        self.btn_add_hash_dir = QPushButton("📂 Add Folder", header)
        self.btn_add_hash_dir.clicked.connect(self._add_hash_dir)
        h_layout.addWidget(self.btn_add_hash_dir)

        h_layout.addWidget(QLabel("Algorithms:"))
        self.chk_md5 = QCheckBox("MD5", header)
        self.chk_md5.setChecked(True)
        h_layout.addWidget(self.chk_md5)
        self.chk_sha1 = QCheckBox("SHA-1", header)
        h_layout.addWidget(self.chk_sha1)
        self.chk_sha256 = QCheckBox("SHA-256", header)
        self.chk_sha256.setChecked(True)
        h_layout.addWidget(self.chk_sha256)
        self.chk_sha512 = QCheckBox("SHA-512", header)
        h_layout.addWidget(self.chk_sha512)

        self.btn_calc_hash = QPushButton("🔐 Calculate", header)
        self.btn_calc_hash.setStyleSheet("background-color: #10b981; color: white; font-weight: bold;")
        self.btn_calc_hash.clicked.connect(self._calculate_hashes)
        h_layout.addWidget(self.btn_calc_hash)

        h_layout.addStretch()
        tab_layout.addWidget(header)

        # File list & results
        self.hash_tree = EnhancedTreeview(
            tab,
            columns=("filename", "size", "md5", "sha1", "sha256", "sha512"),
            app=self.app,
        )
        self.hash_tree.heading("filename", text="File")
        self.hash_tree.heading("size", text="Size")
        self.hash_tree.column("size", width=70, stretch=False)
        self.hash_tree.heading("md5", text="MD5")
        self.hash_tree.heading("sha1", text="SHA-1")
        self.hash_tree.heading("sha256", text="SHA-256")
        self.hash_tree.heading("sha512", text="SHA-512")
        tab_layout.addWidget(self.hash_tree, 1)

        # Verify section
        verify_group = QGroupBox("Verify Hash", tab)
        v_layout = QHBoxLayout(verify_group)
        v_layout.addWidget(QLabel("Expected Hash:"))
        self.verify_hash_input = QLineEdit(verify_group)
        self.verify_hash_input.setPlaceholderText("Paste expected hash value here")
        v_layout.addWidget(self.verify_hash_input)
        v_layout.addWidget(QLabel("Algorithm:"))
        self.verify_algo = QComboBox(verify_group)
        self.verify_algo.addItems(["sha256", "md5", "sha1", "sha512"])
        v_layout.addWidget(self.verify_algo)
        self.btn_verify = QPushButton("✓ Verify", verify_group)
        self.btn_verify.clicked.connect(self._verify_selected_hash)
        v_layout.addWidget(self.btn_verify)
        tab_layout.addWidget(verify_group)

        self.hash_files_list = []
        self._hash_path_by_item = {}  # tree item_id -> full path
        self.hash_tree.set_path_resolver(self._resolve_hash_path)
        self.tabs.addTab(tab, "🔐 Hash Calculator")

    # ------------------------------------------------------------------
    # Tab 3: OS Artifact Parser
    # ------------------------------------------------------------------

    def _build_artifact_tab(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(5, 5, 5, 5)

        # Path selector
        header = QWidget(tab)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 5)
        h_layout.addWidget(QLabel("Filesystem Root:"))
        self.artifact_path = QLineEdit(header)
        self.artifact_path.setPlaceholderText("/  or  /mnt/evidence")
        self.artifact_path.setText("/")
        h_layout.addWidget(self.artifact_path)
        btn_browse = QPushButton("Browse", header)
        btn_browse.clicked.connect(lambda: self._browse_to(self.artifact_path))
        h_layout.addWidget(btn_browse)
        self.btn_parse = QPushButton("🔍 Parse Artifacts", header)
        self.btn_parse.setStyleSheet("background-color: #f59e0b; color: black; font-weight: bold;")
        self.btn_parse.clicked.connect(self._parse_artifacts)
        h_layout.addWidget(self.btn_parse)
        tab_layout.addWidget(header)

        # Results tree
        self.artifact_tree = EnhancedTreeview(
            tab, columns=("category", "key", "value"), app=self.app,
        )
        self.artifact_tree.heading("category", text="Category")
        self.artifact_tree.column("category", width=140, stretch=False)
        self.artifact_tree.heading("key", text="Detail")
        self.artifact_tree.heading("value", text="Value")
        # Artifacts (users, cron, logins...) aren't filesystem rows.
        self.artifact_tree.set_no_file_actions(True)
        tab_layout.addWidget(self.artifact_tree, 1)

        self.lbl_artifact_status = QLabel("", tab)
        self.lbl_artifact_status.setStyleSheet("color: #6b7280;")
        tab_layout.addWidget(self.lbl_artifact_status)

        self.tabs.addTab(tab, "🔎 OS Artifacts")

    # ------------------------------------------------------------------
    # Tab 4: Password Tools
    # ------------------------------------------------------------------

    def _build_password_tab(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(5, 5, 5, 5)

        # Hash extraction
        extract_group = QGroupBox("Password Hash Extraction", tab)
        eg_layout = QVBoxLayout(extract_group)

        ef_frame = QWidget(extract_group)
        ef_layout = QHBoxLayout(ef_frame)
        ef_layout.setContentsMargins(0, 0, 0, 0)
        ef_layout.addWidget(QLabel("Source:"))
        self.pwd_source = QLineEdit(ef_frame)
        self.pwd_source.setPlaceholderText("/etc/shadow  or  archive.zip  or  document.pdf")
        ef_layout.addWidget(self.pwd_source)
        btn_browse_pwd = QPushButton("Browse", ef_frame)
        btn_browse_pwd.clicked.connect(lambda: self._browse_file_to(self.pwd_source))
        ef_layout.addWidget(btn_browse_pwd)
        self.btn_extract = QPushButton("🔓 Extract Hashes", ef_frame)
        self.btn_extract.setStyleSheet("background-color: #8b5cf6; color: white; font-weight: bold;")
        self.btn_extract.clicked.connect(self._extract_hashes)
        ef_layout.addWidget(self.btn_extract)
        eg_layout.addWidget(ef_frame)

        self.pwd_tree = EnhancedTreeview(
            extract_group, columns=("type", "source", "user", "hash_type", "detail"), app=self.app,
        )
        self.pwd_tree.heading("type", text="Type")
        self.pwd_tree.column("type", width=60, stretch=False)
        self.pwd_tree.heading("source", text="Source")
        self.pwd_tree.column("source", width=120, stretch=False)
        self.pwd_tree.heading("user", text="User")
        self.pwd_tree.column("user", width=80, stretch=False)
        self.pwd_tree.heading("hash_type", text="Hash Type")
        self.pwd_tree.column("hash_type", width=80, stretch=False)
        self.pwd_tree.heading("detail", text="Hash / Detail")
        # Password hash records shouldn't be 'moved/copied/deleted' from here.
        self.pwd_tree.set_no_file_actions(True)
        eg_layout.addWidget(self.pwd_tree)
        tab_layout.addWidget(extract_group)

        # Password strength
        strength_group = QGroupBox("Password Strength Analyzer", tab)
        sg_layout = QVBoxLayout(strength_group)

        sf_frame = QWidget(strength_group)
        sf_layout = QHBoxLayout(sf_frame)
        sf_layout.setContentsMargins(0, 0, 0, 0)
        sf_layout.addWidget(QLabel("Password:"))
        self.strength_input = QLineEdit(sf_frame)
        self.strength_input.setPlaceholderText("Enter password to analyze")
        self.strength_input.setEchoMode(QLineEdit.Password)
        sf_layout.addWidget(self.strength_input)
        self.btn_strength = QPushButton("📊 Analyze", sf_frame)
        self.btn_strength.clicked.connect(self._analyze_strength)
        sf_layout.addWidget(self.btn_strength)
        sg_layout.addWidget(sf_frame)

        self.strength_result = QLabel("", strength_group)
        self.strength_result.setWordWrap(True)
        self.strength_result.setStyleSheet("font-size: 13px; padding: 10px;")
        sg_layout.addWidget(self.strength_result)

        tab_layout.addWidget(strength_group)

        # Dictionary attack
        attack_group = QGroupBox("Dictionary Attack (hashcat / john)", tab)
        ag_layout = QGridLayout(attack_group)

        ag_layout.addWidget(QLabel("Hash file:"), 0, 0)
        self.attack_hash_file = QLineEdit(attack_group)
        self.attack_hash_file.setPlaceholderText("Generate from the Source above, or browse to an existing hash file")
        ag_layout.addWidget(self.attack_hash_file, 0, 1, 1, 2)
        self.btn_generate_hash = QPushButton("Generate from Source", attack_group)
        self.btn_generate_hash.clicked.connect(self._generate_crack_hash)
        ag_layout.addWidget(self.btn_generate_hash, 0, 3)
        btn_browse_hash = QPushButton("Browse", attack_group)
        btn_browse_hash.clicked.connect(lambda: self._browse_file_to(self.attack_hash_file))
        ag_layout.addWidget(btn_browse_hash, 0, 4)

        ag_layout.addWidget(QLabel("Wordlist:"), 1, 0)
        self.attack_wordlist = QLineEdit(attack_group)
        self.attack_wordlist.setPlaceholderText("Your own dictionary file, or pick a detected system wordlist ->")
        ag_layout.addWidget(self.attack_wordlist, 1, 1, 1, 2)
        self.wordlist_combo = QComboBox(attack_group)
        self._populate_wordlist_combo()
        self.wordlist_combo.currentIndexChanged.connect(self._on_wordlist_combo_changed)
        ag_layout.addWidget(self.wordlist_combo, 1, 3)
        btn_browse_wordlist = QPushButton("Browse", attack_group)
        btn_browse_wordlist.clicked.connect(lambda: self._browse_file_to(self.attack_wordlist))
        ag_layout.addWidget(btn_browse_wordlist, 1, 4)

        ag_layout.addWidget(QLabel("Tool:"), 2, 0)
        self.attack_tool_combo = QComboBox(attack_group)
        self.attack_tool_combo.addItems(["auto", "hashcat", "john"])
        ag_layout.addWidget(self.attack_tool_combo, 2, 1)

        ag_layout.addWidget(QLabel("Hash mode/format (optional):"), 2, 2)
        self.attack_hash_type = QLineEdit(attack_group)
        self.attack_hash_type.setPlaceholderText("e.g. 17200 (hashcat -m) or ZIP (john --format)")
        ag_layout.addWidget(self.attack_hash_type, 2, 3, 1, 2)

        self.btn_run_attack = QPushButton("⚔️ Run Dictionary Attack", attack_group)
        self.btn_run_attack.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold;")
        self.btn_run_attack.clicked.connect(self._run_dict_attack)
        ag_layout.addWidget(self.btn_run_attack, 3, 0, 1, 5)

        self.attack_result = QTextEdit(attack_group)
        self.attack_result.setReadOnly(True)
        self.attack_result.setMaximumHeight(120)
        self.attack_result.setPlaceholderText(
            "Attack output will appear here. Use the Stop button in the status bar to cancel a running attack."
        )
        ag_layout.addWidget(self.attack_result, 4, 0, 1, 5)

        tab_layout.addWidget(attack_group)

        # Tool availability
        tools_info = []
        for label, available in [
            ("hashcat", check_hashcat_available()),
            ("john", check_john_available()),
            ("zip2john", check_zip2john_available()),
            ("pdf2john", check_pdf2john_available()),
        ]:
            tools_info.append(f"{'✅' if available else '❌'} {label}")

        lbl_tools = QLabel(f"Available tools: {' | '.join(tools_info)}", tab)
        lbl_tools.setStyleSheet("color: #9ca3af; font-size: 11px;")
        tab_layout.addWidget(lbl_tools)

        self.tabs.addTab(tab, "🔑 Password Tools")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _browse_to(self, line_edit):
        path = dialogs.get_existing_directory(self, "Select Directory")
        if path:
            line_edit.setText(path)

    def _browse_file_to(self, line_edit):
        path, _ = dialogs.get_open_file_name(self, "Select File")
        if path:
            line_edit.setText(path)

    # ------------------------------------------------------------------
    # Tab 5: File Type Profiler (magic-byte signature analysis)
    # ------------------------------------------------------------------

    def _build_filetype_tab(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(5, 5, 5, 5)

        header = QWidget(tab)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 5)
        h_layout.addWidget(QLabel("Target Directory:"))
        self.ftype_path = QLineEdit(header)
        self.ftype_path.setPlaceholderText("/path/to/evidence or folder to classify")
        h_layout.addWidget(self.ftype_path)
        btn_browse = QPushButton("Browse", header)
        btn_browse.clicked.connect(lambda: self._browse_to(self.ftype_path))
        h_layout.addWidget(btn_browse)
        self.btn_ftype = QPushButton("🔍 Profile Types", header)
        self.btn_ftype.setStyleSheet("background-color: #0ea5e9; color: white; font-weight: bold;")
        self.btn_ftype.clicked.connect(self._profile_filetypes)
        h_layout.addWidget(self.btn_ftype)
        tab_layout.addWidget(header)

        # Summary label
        self.lbl_ftype_summary = QLabel("Classify every file by magic bytes — ignores extensions.", tab)
        self.lbl_ftype_summary.setStyleSheet("color: #6b7280;")
        self.lbl_ftype_summary.setWordWrap(True)
        tab_layout.addWidget(self.lbl_ftype_summary)

        # Counts tree (top) + file rows tree (bottom)
        ftype_split = QSplitter(Qt.Vertical, tab)
        self.ftype_count_tree = EnhancedTreeview(
            ftype_split, columns=("format", "count", "description"), app=self.app,
        )
        self.ftype_count_tree.heading("format", text="Format")
        self.ftype_count_tree.heading("count", text="Count")
        self.ftype_count_tree.column("count", width=70, stretch=False)
        self.ftype_count_tree.heading("description", text="Description")
        self.ftype_count_tree.set_no_file_actions(True)
        ftype_split.addWidget(self.ftype_count_tree)

        self.ftype_row_tree = EnhancedTreeview(
            ftype_split, columns=("filename", "extension", "size", "format", "description"), app=self.app,
        )
        self.ftype_row_tree.heading("filename", text="Filename")
        self.ftype_row_tree.heading("extension", text="Ext")
        self.ftype_row_tree.column("extension", width=60, stretch=False)
        self.ftype_row_tree.heading("size", text="Size")
        self.ftype_row_tree.column("size", width=70, stretch=False)
        self.ftype_row_tree.heading("format", text="Detected Format")
        self.ftype_row_tree.heading("description", text="Description")
        # Map item_id -> full path so right-click open/copy works on rows.
        self._ftype_path_by_item = {}
        self.ftype_row_tree.set_path_resolver(self._resolve_ftype_path)
        ftype_split.addWidget(self.ftype_row_tree)
        ftype_split.setSizes([200, 400])
        tab_layout.addWidget(ftype_split, 1)

        self.tabs.addTab(tab, "🧬 File Types")

    def _resolve_ftype_path(self, item_id):
        return self._ftype_path_by_item.get(item_id)

    def _profile_filetypes(self):
        path = self.ftype_path.text().strip()
        if not path or not os.path.isdir(path):
            self.app.show_warning_dialog("Invalid Path", "Enter a valid directory to classify.")
            return
        self.lbl_ftype_summary.setText("Profiling file types...")
        self.app.update_status("Profiling file types...")
        self.app.run_workflow(
            profile_directory_types,
            self._on_ftypes_profiled,
            path,
            progress=True,
            error_title="File Type Profiling Failed",
        )

    def _on_ftypes_profiled(self, result):
        self.ftype_count_tree.tree.clear()
        self.ftype_count_tree.item_map.clear()
        self.ftype_row_tree.tree.clear()
        self.ftype_row_tree.item_map.clear()
        self._ftype_path_by_item.clear()

        total = result.get("total", 0)
        by_format = result.get("by_format", {})
        for fmt, count in sorted(by_format.items(), key=lambda kv: kv[1], reverse=True):
            self.ftype_count_tree.insert("", "end", values=(fmt, count, ""))

        rows = result.get("rows", [])
        for r in rows:
            iid = self.ftype_row_tree.insert("", "end", values=(
                r.get("filename", ""),
                r.get("extension", ""),
                format_size(r.get("size", 0)),
                r.get("format", ""),
                r.get("description", ""),
            ))
            self._ftype_path_by_item[iid] = r.get("path", "")
            self.ftype_row_tree.set_item_path(iid, r.get("path"))

        self.lbl_ftype_summary.setText(
            f"Classified {total} files across {len(by_format)} formats."
        )
        self.app.update_status(f"File type profiling complete: {total} files.")

    # ------------------------------------------------------------------
    # Tab 6: Entropy Analyzer (encrypted/packed/compressed detection)
    # ------------------------------------------------------------------

    def _build_entropy_tab(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(5, 5, 5, 5)

        header = QWidget(tab)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 5)
        self.btn_ent_files = QPushButton("📁 Add Files", header)
        self.btn_ent_files.clicked.connect(self._add_entropy_files)
        h_layout.addWidget(self.btn_ent_files)
        self.btn_ent_dir = QPushButton("📂 Add Folder", header)
        self.btn_ent_dir.clicked.connect(self._add_entropy_dir)
        h_layout.addWidget(self.btn_ent_dir)
        h_layout.addWidget(QLabel("Max bytes/sample:"))
        self.spin_ent_bytes = QSpinBox(header)
        self.spin_ent_bytes.setRange(64, 100 * 1024 * 1024)
        self.spin_ent_bytes.setValue(1024 * 1024)
        self.spin_ent_bytes.setSingleStep(1024)
        h_layout.addWidget(self.spin_ent_bytes)
        self.btn_ent_calc = QPushButton("📊 Compute Entropy", header)
        self.btn_ent_calc.setStyleSheet("background-color: #6366f1; color: white; font-weight: bold;")
        self.btn_ent_calc.clicked.connect(self._compute_entropy)
        h_layout.addWidget(self.btn_ent_calc)
        h_layout.addStretch()
        tab_layout.addWidget(header)

        self.lbl_entropy_status = QLabel(
            "High entropy (>7.5) hints at encryption, packing, or compression.",
            tab,
        )
        self.lbl_entropy_status.setStyleSheet("color: #6b7280;")
        self.lbl_entropy_status.setWordWrap(True)
        tab_layout.addWidget(self.lbl_entropy_status)

        self.entropy_tree = EnhancedTreeview(
            tab, columns=("filename", "size", "entropy", "verdict"), app=self.app,
        )
        self.entropy_tree.heading("filename", text="File")
        self.entropy_tree.heading("size", text="Size")
        self.entropy_tree.column("size", width=80, stretch=False)
        self.entropy_tree.heading("entropy", text="Entropy")
        self.entropy_tree.column("entropy", width=80, stretch=False)
        self.entropy_tree.heading("verdict", text="Verdict")
        self._entropy_path_by_item = {}
        self.entropy_tree.set_path_resolver(self._resolve_entropy_path)
        tab_layout.addWidget(self.entropy_tree, 1)

        # Single-file quick entropy probe
        single = QGroupBox("Quick Single-File Probe", tab)
        sg_layout = QHBoxLayout(single)
        sg_layout.addWidget(QLabel("File:"))
        self.ent_single_path = QLineEdit(single)
        self.ent_single_path.setPlaceholderText("/path/to/file")
        sg_layout.addWidget(self.ent_single_path)
        btn_single_b = QPushButton("Browse", single)
        btn_single_b.clicked.connect(lambda: self._browse_file_to(self.ent_single_path))
        sg_layout.addWidget(btn_single_b)
        self.btn_ent_single = QPushButton("Probe", single)
        self.btn_ent_single.clicked.connect(self._probe_single_entropy)
        sg_layout.addWidget(self.btn_ent_single)
        self.ent_single_result = QLabel("", single)
        self.ent_single_result.setWordWrap(True)
        sg_layout.addWidget(self.ent_single_result)
        tab_layout.addWidget(single)

        self.entropy_files_list = []
        self.tabs.addTab(tab, "📈 Entropy")

    def _resolve_entropy_path(self, item_id):
        return self._entropy_path_by_item.get(item_id)

    def _add_entropy_files(self):
        files, _ = dialogs.get_open_file_names(self, "Select Files for Entropy Analysis")
        if files:
            self.entropy_files_list.extend(files)
            self._render_entropy_pending(files)

    def _add_entropy_dir(self):
        path = dialogs.get_existing_directory(self, "Select Folder for Entropy Analysis")
        if path:
            added = []
            for root, _dirs, files in os.walk(path):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    self.entropy_files_list.append(fpath)
                    added.append(fpath)
            self._render_entropy_pending(added)

    def _render_entropy_pending(self, paths):
        for f in paths:
            iid = self.entropy_tree.insert("", "end", values=(
                os.path.basename(f), format_size(os.path.getsize(f)) if os.path.exists(f) else "?",
                "—", "pending",
            ))
            self._entropy_path_by_item[iid] = f
            self.entropy_tree.set_item_path(iid, f)

    def _compute_entropy(self):
        if not self.entropy_files_list:
            self.app.show_warning_dialog("No Files", "Add files first.")
            return
        max_bytes = self.spin_ent_bytes.value()
        self.lbl_entropy_status.setText("Computing entropy...")
        self.app.update_status("Computing entropy...")
        self.app.run_workflow(
            calculate_entropy_batch,
            self._on_entropy_computed,
            list(self.entropy_files_list), max_bytes,
            progress=True,
            error_title="Entropy Analysis Failed",
        )

    def _on_entropy_computed(self, results):
        self.entropy_tree.tree.clear()
        self.entropy_tree.item_map.clear()
        self._entropy_path_by_item.clear()
        for r in results:
            if "error" in r:
                iid = self.entropy_tree.insert("", "end", values=(
                    os.path.basename(r.get("path", "")), "?", "ERR", r["error"],
                ))
                self._entropy_path_by_item[iid] = r.get("path", "")
                continue
            iid = self.entropy_tree.insert("", "end", values=(
                r.get("filename", ""), format_size(r.get("sample_size", 0)),
                f"{r.get('entropy', 0):.4f}", r.get("verdict", ""),
            ))
            self._entropy_path_by_item[iid] = r.get("path", "")
            self.entropy_tree.set_item_path(iid, r.get("path"))
        self.lbl_entropy_status.setText(f"Entropy computed for {len(results)} files.")
        self.app.update_status(f"Entropy analysis complete: {len(results)} files.")

    def _probe_single_entropy(self):
        path = self.ent_single_path.text().strip()
        if not path or not os.path.isfile(path):
            self.app.show_warning_dialog("Invalid Path", "Enter a valid file path.")
            return
        result = calculate_entropy(path)
        if "error" in result:
            self.ent_single_result.setText(f"Error: {result['error']}")
            return
        color = "#dc2626" if result["entropy"] >= 7.5 else ("#f59e0b" if result["entropy"] >= 4.5 else "#059669")
        self.ent_single_result.setText(
            f"<b style='color:{color}'>Entropy: {result['entropy']:.4f} bits/byte</b> "
            f"(sample {result['sample_size']} bytes)\nVerdict: {result['verdict']}"
        )
        self.ent_single_result.setTextFormat(Qt.RichText)

    # ------------------------------------------------------------------
    # Tab 7: Timeline Builder
    # ------------------------------------------------------------------

    def _build_timeline_tab(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(5, 5, 5, 5)

        header = QWidget(tab)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 5)
        h_layout.addWidget(QLabel("Root:"))
        self.timeline_path = QLineEdit(header)
        self.timeline_path.setPlaceholderText("/path/to/evidence")
        h_layout.addWidget(self.timeline_path)
        btn_browse = QPushButton("Browse", header)
        btn_browse.clicked.connect(lambda: self._browse_to(self.timeline_path))
        h_layout.addWidget(btn_browse)
        h_layout.addWidget(QLabel("Sort by:"))
        self.timeline_sort = QComboBox(header)
        self.timeline_sort.addItems(["mtime", "atime", "ctime"])
        h_layout.addWidget(self.timeline_sort)
        self.btn_timeline = QPushButton("🕰 Build Timeline", header)
        self.btn_timeline.setStyleSheet("background-color: #f59e0b; color: black; font-weight: bold;")
        self.btn_timeline.clicked.connect(self._build_timeline)
        h_layout.addWidget(self.btn_timeline)
        tab_layout.addWidget(header)

        self.lbl_timeline_status = QLabel("Builds a UTC timestamped event list for every file.", tab)
        self.lbl_timeline_status.setStyleSheet("color: #6b7280;")
        self.lbl_timeline_status.setWordWrap(True)
        tab_layout.addWidget(self.lbl_timeline_status)

        self.timeline_tree = EnhancedTreeview(
            tab, columns=("timestamp", "filename", "size", "ext", "uid", "gid", "mode"), app=self.app,
        )
        self.timeline_tree.heading("timestamp", text="Timestamp (UTC)")
        self.timeline_tree.column("timestamp", width=200, stretch=False)
        self.timeline_tree.heading("filename", text="Filename")
        self.timeline_tree.heading("size", text="Size")
        self.timeline_tree.column("size", width=70, stretch=False)
        self.timeline_tree.heading("ext", text="Ext")
        self.timeline_tree.column("ext", width=60, stretch=False)
        self.timeline_tree.heading("uid", text="UID")
        self.timeline_tree.column("uid", width=60, stretch=False)
        self.timeline_tree.heading("gid", text="GID")
        self.timeline_tree.column("gid", width=60, stretch=False)
        self.timeline_tree.heading("mode", text="Mode")
        self.timeline_tree.column("mode", width=80, stretch=False)
        self._timeline_path_by_item = {}
        self.timeline_tree.set_path_resolver(self._resolve_timeline_path)
        tab_layout.addWidget(self.timeline_tree, 1)

        self.tabs.addTab(tab, "🕰 Timeline")

    def _resolve_timeline_path(self, item_id):
        return self._timeline_path_by_item.get(item_id)

    def _build_timeline(self):
        path = self.timeline_path.text().strip()
        if not path or not os.path.isdir(path):
            self.app.show_warning_dialog("Invalid Path", "Enter a valid directory.")
            return
        sort_key = self.timeline_sort.currentText()
        self.lbl_timeline_status.setText("Building timeline...")
        self.app.update_status("Building timeline...")
        self.app.run_workflow(
            build_timeline,
            self._on_timeline_built,
            path, sort_key,
            progress=True,
            error_title="Timeline Build Failed",
        )

    def _on_timeline_built(self, events):
        self.timeline_tree.tree.clear()
        self.timeline_tree.item_map.clear()
        self._timeline_path_by_item.clear()
        for ev in events[:5000]:
            iid = self.timeline_tree.insert("", "end", values=(
                ev.get("timestamp_iso", ""),
                ev.get("filename", ""),
                format_size(ev.get("size", 0)),
                ev.get("extension", ""),
                str(ev.get("owner_uid", "")),
                str(ev.get("owner_gid", "")),
                ev.get("mode", ""),
            ))
            self._timeline_path_by_item[iid] = ev.get("path", "")
            self.timeline_tree.set_item_path(iid, ev.get("path"))
        shown = min(len(events), 5000)
        self.lbl_timeline_status.setText(
            f"{len(events)} events total (showing {shown}). Newest first."
        )
        self.app.update_status(f"Timeline built: {len(events)} events.")

    # ------------------------------------------------------------------
    # Tab 8: Hex Viewer
    # ------------------------------------------------------------------

    def _build_hex_tab(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(5, 5, 5, 5)

        header = QWidget(tab)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 5)
        h_layout.addWidget(QLabel("File:"))
        self.hex_path = QLineEdit(header)
        self.hex_path.setPlaceholderText("/path/to/file")
        h_layout.addWidget(self.hex_path)
        btn_browse = QPushButton("Browse", header)
        btn_browse.clicked.connect(lambda: self._browse_file_to(self.hex_path))
        h_layout.addWidget(btn_browse)
        h_layout.addWidget(QLabel("Bytes:"))
        self.spin_hex_bytes = QSpinBox(header)
        self.spin_hex_bytes.setRange(16, 1024 * 1024)
        self.spin_hex_bytes.setValue(4096)
        self.spin_hex_bytes.setSingleStep(256)
        h_layout.addWidget(self.spin_hex_bytes)
        h_layout.addWidget(QLabel("Offset:"))
        self.spin_hex_offset = QSpinBox(header)
        self.spin_hex_offset.setRange(0, 2147483647)
        self.spin_hex_offset.setValue(0)
        self.spin_hex_offset.setSingleStep(4096)
        h_layout.addWidget(self.spin_hex_offset)
        self.btn_hex_view = QPushButton("👁 View Hex", header)
        self.btn_hex_view.setStyleSheet("background-color: #10b981; color: white; font-weight: bold;")
        self.btn_hex_view.clicked.connect(self._view_hex)
        h_layout.addWidget(self.btn_hex_view)
        tab_layout.addWidget(header)

        self.hex_view = QTextEdit(tab)
        self.hex_view.setReadOnly(True)
        self.hex_view.setStyleSheet(
            "font-family: 'Courier New', Consolas, monospace; font-size: 12px;"
        )
        tab_layout.addWidget(self.hex_view, 1)

        self.lbl_hex_info = QLabel("", tab)
        self.lbl_hex_info.setStyleSheet("color: #6b7280;")
        self.lbl_hex_info.setWordWrap(True)
        tab_layout.addWidget(self.lbl_hex_info)

        self.tabs.addTab(tab, "👁 Hex Viewer")

    def _view_hex(self):
        path = self.hex_path.text().strip()
        if not path or not os.path.isfile(path):
            self.app.show_warning_dialog("Invalid Path", "Enter a valid file path.")
            return
        max_bytes = self.spin_hex_bytes.value()
        offset = self.spin_hex_offset.value()
        result = hex_dump(path, max_bytes=max_bytes, offset=offset)
        if "error" in result:
            self.hex_view.setPlainText(f"Error: {result['error']}")
            return
        self.hex_view.setPlainText("\n".join(result.get("lines", [])))
        self.lbl_hex_info.setText(
            f"Size: {format_size(result.get('size', 0))} | "
            f"Read: {result.get('bytes_read', 0)} bytes | "
            f"Offset: {result.get('offset', 0)}"
            + (" | (truncated — increase byte limit to see more)" if result.get("truncated") else "")
        )

    # ------------------------------------------------------------------
    # Tab 9: Steganography Detector (LSB hint analysis)
    # ------------------------------------------------------------------

    def _build_stego_tab(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(5, 5, 5, 5)

        info = QLabel(
            "⚠️ This is a triage-only LSB heuristic: it does not extract data "
            "nor prove steganography exists. It flags PNG/BMP/TIFF images whose "
            "LSB channel distribution looks uniform (a hallmark of overwritten "
            "hidden data).",
            tab,
        )
        info.setWordWrap(True)
        info.setStyleSheet("background-color: #fef3c7; color: #92400e; padding: 8px; border-radius: 4px;")
        tab_layout.addWidget(info)

        header = QWidget(tab)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 5)
        h_layout.addWidget(QLabel("Image:"))
        self.stego_path = QLineEdit(header)
        self.stego_path.setPlaceholderText("/path/to/image.png")
        h_layout.addWidget(self.stego_path)
        btn_browse = QPushButton("Browse", header)
        btn_browse.clicked.connect(lambda: self._browse_file_to(self.stego_path))
        h_layout.addWidget(btn_browse)
        self.btn_stego = QPushButton("🕵 Analyze", header)
        self.btn_stego.setStyleSheet("background-color: #8b5cf6; color: white; font-weight: bold;")
        self.btn_stego.clicked.connect(self._analyze_stego)
        h_layout.addWidget(self.btn_stego)
        tab_layout.addWidget(header)

        self.stego_result = QTextEdit(tab)
        self.stego_result.setReadOnly(True)
        self.stego_result.setStyleSheet(
            "font-family: 'Courier New', Consolas, monospace; font-size: 12px;"
        )
        tab_layout.addWidget(self.stego_result, 1)

        self.tabs.addTab(tab, "🕵 Steganography")

    def _analyze_stego(self):
        path = self.stego_path.text().strip()
        if not path or not os.path.isfile(path):
            self.app.show_warning_dialog("Invalid Path", "Enter a valid image path.")
            return
        result = detect_steganography(path)
        if not result.get("supported"):
            self.stego_result.setPlainText(
                f"Analysis not supported for this file.\nReason: {result.get('reason', 'unknown')}"
            )
            return
        blocks = []
        blocks.append(f"File: {result.get('filename', '')}")
        blocks.append(f"Dimensions: {result.get('dimensions', '')}")
        blocks.append(f"Pixels sampled: {result.get('pixels_sampled', 0)}")
        blocks.append(f"LSB ones ratio: {result.get('lsb_one_ratio', 0):.4f} (ideal random ~0.5000)")
        blocks.append(f"LSB swap ratio: {result.get('lsb_swap_ratio', 0):.4f}")
        blocks.append("")
        marker = "🚩" if result.get("suspicious") else "✅"
        blocks.append(f"{marker} Verdict: {result.get('verdict', '')}")
        self.stego_result.setPlainText("\n".join(blocks))

    # ------------------------------------------------------------------
    # Tab 10: Secure Delete
    # ------------------------------------------------------------------

    def _build_secure_delete_tab(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(5, 5, 5, 5)

        warn = QLabel(
            "⚠️ Secure Delete overwrites the file with random data multiple "
            "times before unlinking it. This is irreversible once complete. "
            "Use only on data you are legally authorized to destroy.",
            tab,
        )
        warn.setWordWrap(True)
        warn.setStyleSheet("background-color: #fee2e2; color: #991b1b; padding: 8px; border-radius: 4px;")
        tab_layout.addWidget(warn)

        header = QWidget(tab)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 5)
        h_layout.addWidget(QLabel("File:"))
        self.secure_path = QLineEdit(header)
        self.secure_path.setPlaceholderText("/path/to/file to securely delete")
        h_layout.addWidget(self.secure_path)
        btn_browse = QPushButton("Browse", header)
        btn_browse.clicked.connect(lambda: self._browse_file_to(self.secure_path))
        h_layout.addWidget(btn_browse)
        h_layout.addWidget(QLabel("Passes:"))
        self.spin_secure_passes = QSpinBox(header)
        self.spin_secure_passes.setRange(1, 35)
        self.spin_secure_passes.setValue(3)
        h_layout.addWidget(self.spin_secure_passes)
        self.btn_secure_delete = QPushButton("🗑 Secure Delete", header)
        self.btn_secure_delete.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold;")
        self.btn_secure_delete.clicked.connect(self._do_secure_delete)
        h_layout.addWidget(self.btn_secure_delete)
        tab_layout.addWidget(header)

        self.secure_result = QTextEdit(tab)
        self.secure_result.setReadOnly(True)
        self.secure_result.setStyleSheet(
            "font-family: 'Courier New', Consolas, monospace; font-size: 12px;"
        )
        tab_layout.addWidget(self.secure_result, 1)

        self.tabs.addTab(tab, "🗑 Secure Delete")

    def _do_secure_delete(self):
        path = self.secure_path.text().strip()
        if not path or not os.path.isfile(path):
            self.app.show_warning_dialog("Invalid Path", "Enter a valid file path.")
            return
        passes = self.spin_secure_passes.value()
        reply = QMessageBox.question(
            self, "Confirm Secure Delete",
            f"Permanently overwrite and delete:\n{path}\n\nPasses: {passes}\n\n"
            "This cannot be undone. Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.app.run_workflow(
            secure_delete,
            self._on_secure_deleted,
            path, passes,
            error_title="Secure Delete Failed",
        )

    def _on_secure_deleted(self, result):
        if result.get("success"):
            self.secure_result.setPlainText(
                f"✅ {result.get('message', 'Deleted')}\nPath: {result.get('path', '')}"
            )
        else:
            self.secure_result.setPlainText(
                f"❌ {result.get('message', 'Failed')}\nPath: {result.get('path', '')}"
            )

    # ------------------------------------------------------------------
    # Tab 11: Integrity Snapshot (baseline tamper detection)
    # ------------------------------------------------------------------

    def _build_integrity_tab(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(5, 5, 5, 5)

        # Mode selector
        mode_row = QWidget(tab)
        m_layout = QHBoxLayout(mode_row)
        m_layout.setContentsMargins(0, 0, 0, 5)
        m_layout.addWidget(QLabel("Mode:"))
        self.integrity_mode = QComboBox(mode_row)
        self.integrity_mode.addItems(["Create Snapshot", "Verify Snapshot"])
        m_layout.addWidget(self.integrity_mode)
        m_layout.addWidget(QLabel("Path(s) / Snapshot file:"))
        self.integrity_path = QLineEdit(mode_row)
        self.integrity_path.setPlaceholderText("dir or file paths (comma separated) for create; snapshot .json for verify")
        m_layout.addWidget(self.integrity_path)
        btn_browse_dir = QPushButton("Browse Dir", mode_row)
        btn_browse_dir.clicked.connect(lambda: self._browse_to(self.integrity_path))
        m_layout.addWidget(btn_browse_dir)
        btn_browse_file = QPushButton("Browse File", mode_row)
        btn_browse_file.clicked.connect(lambda: self._browse_file_to(self.integrity_path))
        m_layout.addWidget(btn_browse_file)
        self.btn_integrity_run = QPushButton("Run", mode_row)
        self.btn_integrity_run.setStyleSheet("background-color: #10b981; color: white; font-weight: bold;")
        self.btn_integrity_run.clicked.connect(self._run_integrity)
        m_layout.addWidget(self.btn_integrity_run)
        tab_layout.addWidget(mode_row)

        self.integrity_tree = EnhancedTreeview(
            tab, columns=("path", "status", "detail"), app=self.app,
        )
        self.integrity_tree.heading("path", text="Path")
        self.integrity_tree.heading("status", text="Status")
        self.integrity_tree.column("status", width=100, stretch=False)
        self.integrity_tree.heading("detail", text="Detail")
        self.integrity_tree.set_no_file_actions(True)
        tab_layout.addWidget(self.integrity_tree, 1)

        self.lbl_integrity_status = QLabel(
            "Create a cryptographic baseline, then later re-verify to detect tampering.",
            tab,
        )
        self.lbl_integrity_status.setStyleSheet("color: #6b7280;")
        self.lbl_integrity_status.setWordWrap(True)
        tab_layout.addWidget(self.lbl_integrity_status)

        self.tabs.addTab(tab, "🛡 Integrity")

    def _run_integrity(self):
        mode = self.integrity_mode.currentText()
        raw = self.integrity_path.text().strip()
        if not raw:
            self.app.show_warning_dialog("No Path", "Enter a path or snapshot file.")
            return

        if mode == "Create Snapshot":
            paths = [p.strip() for p in raw.split(",") if p.strip()]
            existing = [p for p in paths if os.path.exists(p)]
            if not existing:
                self.app.show_warning_dialog("No Files", "None of the given paths exist.")
                return
            dest, _ = dialogs.get_save_file_name(
                self, "Save Integrity Snapshot", "integrity_snapshot.json",
                "JSON Files (*.json);;All Files (*)",
            )
            if not dest:
                return
            self.lbl_integrity_status.setText("Building snapshot...")
            self.app.update_status("Building integrity snapshot...")

            def _worker(paths=existing, dest=dest, progress_callback=None, cancel_token=None):
                snap = snapshot_file_state(paths, progress_callback=progress_callback, cancel_token=cancel_token)
                with open(dest, "w") as f:
                    json.dump(snap, f, indent=2, default=str)
                return snap

            self.app.run_workflow(
                _worker,
                lambda snap: self._on_snapshot_created(snap, dest),
                error_title="Snapshot Failed",
            )
        else:
            if not os.path.isfile(raw):
                self.app.show_warning_dialog("No Snapshot", "Enter a path to a snapshot .json file.")
                return
            try:
                with open(raw, "r") as f:
                    snap = json.load(f)
            except Exception as exc:
                self.app.show_error_dialog("Load Failed", str(exc))
                return
            self.lbl_integrity_status.setText("Verifying snapshot...")
            self.app.update_status("Verifying integrity snapshot...")
            self.app.run_workflow(
                verify_file_state,
                self._on_snapshot_verified,
                snap,
                progress=True,
                error_title="Verification Failed",
            )

    def _on_snapshot_created(self, snap, dest):
        self.integrity_tree.tree.clear()
        self.integrity_tree.item_map.clear()
        for entry in snap.get("entries", []):
            self.integrity_tree.insert("", "end", values=(
                entry.get("path", ""), "Baseline", f"{len(snap.get('algorithm', []))} hashes saved",
            ))
        self.lbl_integrity_status.setText(
            f"Snapshot saved: {dest} ({len(snap.get('entries', []))} entries)"
        )
        self.app.update_status("Integrity snapshot created.")

    def _on_snapshot_verified(self, results):
        self.integrity_tree.tree.clear()
        self.integrity_tree.item_map.clear()
        ok = 0
        changed = 0
        missing = 0
        for entry, diff in results:
            if diff is None:
                status = "✅ OK"
                ok += 1
                detail = ""
            elif diff.get("missing"):
                status = "❌ Missing"
                missing += 1
                detail = "file no longer exists"
            else:
                status = "⚠️ Changed"
                changed += 1
                parts = []
                for k, (old, new) in diff.items():
                    parts.append(f"{k}: {old} → {new}")
                detail = "; ".join(parts)
            self.integrity_tree.insert("", "end", values=(
                entry.get("path", ""), status, detail,
            ))
        self.lbl_integrity_status.setText(
            f"Verified: {ok} OK | {changed} changed | {missing} missing."
        )
        self.app.update_status("Integrity verification complete.")

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def _start_ingestion(self):
        target = self.ingest_path.text().strip()
        output = self.ingest_output.text().strip()

        if not target:
            self.app.show_warning_dialog("Missing Target", "Specify a target path.")
            return
        if not output:
            self.app.show_warning_dialog("Missing Output", "Specify an output directory.")
            return

        reply = QMessageBox.question(
            self, "Confirm Ingestion",
            f"Run forensic ingestion on:\n{target}\n\nOutput to:\n{output}\n\nThis may take a while.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        options = {
            "hash_files": self.chk_hash.isChecked(),
            "extract_metadata": self.chk_artifacts.isChecked(),
            "keyword_index": self.chk_keywords.isChecked(),
            "keywords": [
                kw.strip() for kw in self.keywords_entry.text().split(",") if kw.strip()
            ],
        }

        self.lbl_ingest_status.setText("Running forensic ingestion pipeline...")
        self.app.update_status("Forensic ingestion in progress...")

        self.app.run_workflow(
            ingest_disk_image,
            self._on_ingestion_complete,
            target, output, options,
            progress=True,
            error_title="Ingestion Failed",
        )

    def _on_ingestion_complete(self, results):
        self.last_ingest_results = results

        self.ingest_tree.tree.clear()
        self.ingest_tree.item_map.clear()

        self.ingest_tree.insert("", "end", values=("Files Enumerated", results.get("file_count", 0), ""))

        hashes = results.get("hashes", [])
        self.ingest_tree.insert("", "end", values=("Files Hashed", len(hashes), ""))

        artifacts = results.get("artifacts", {})
        for cat, data in artifacts.items():
            count = len(data) if isinstance(data, list) else 1
            self.ingest_tree.insert("", "end", values=(f"Artifact: {cat}", count, ""))

        keywords = results.get("keyword_hits", [])
        if keywords:
            self.ingest_tree.insert("", "end", values=("Keyword Hits", len(keywords), ""))

        errors = results.get("errors", [])
        if errors:
            self.ingest_tree.insert("", "end", values=("Errors", len(errors), "; ".join(errors[:3])))

        self.lbl_ingest_status.setText(
            f"Ingestion complete. {results.get('file_count', 0)} files processed. "
            f"Output: {results.get('output_dir', '')}"
        )
        self.app.update_status("Forensic ingestion complete.")

    def _export_report(self):
        if not self.last_ingest_results:
            self.app.show_warning_dialog("No Data", "Run an ingestion first.")
            return

        dest, _ = dialogs.get_save_file_name(
            self, "Export Forensic Report", "forensic_report.html",
            "HTML Files (*.html);;JSON Files (*.json);;All Files (*)",
        )
        if not dest:
            return

        fmt = "html" if dest.endswith(".html") else "json"
        try:
            generate_forensic_report(self.last_ingest_results, dest, fmt=fmt)
            self.app.show_info_dialog("Export Complete", f"Report saved to:\n{dest}")
        except Exception as exc:
            self.app.show_error_dialog("Export Failed", str(exc))

    # ------------------------------------------------------------------
    # Hash Calculator
    # ------------------------------------------------------------------

    def _add_hash_files(self):
        files, _ = dialogs.get_open_file_names(self, "Select Files to Hash")
        if files:
            self.hash_files_list.extend(files)
            for f in files:
                iid = self.hash_tree.insert("", "end", values=(
                    os.path.basename(f), format_size(os.path.getsize(f)),
                    "—", "—", "—", "—",
                ))
                self._hash_path_by_item[iid] = f
                self.hash_tree.set_item_path(iid, f)

    def _add_hash_dir(self):
        path = dialogs.get_existing_directory(self, "Select Folder")
        if path:
            for root, dirs, files in os.walk(path):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    self.hash_files_list.append(fpath)
                    try:
                        size = format_size(os.path.getsize(fpath))
                    except OSError:
                        size = "?"
                    iid = self.hash_tree.insert("", "end", values=(
                        fname, size, "—", "—", "—", "—",
                    ))
                    self._hash_path_by_item[iid] = fpath
                    self.hash_tree.set_item_path(iid, fpath)

    def _resolve_hash_path(self, item_id):
        return self._hash_path_by_item.get(item_id)

    def _calculate_hashes(self):
        if not self.hash_files_list:
            self.app.show_warning_dialog("No Files", "Add files to hash first.")
            return

        algorithms = []
        if self.chk_md5.isChecked():
            algorithms.append("md5")
        if self.chk_sha1.isChecked():
            algorithms.append("sha1")
        if self.chk_sha256.isChecked():
            algorithms.append("sha256")
        if self.chk_sha512.isChecked():
            algorithms.append("sha512")

        if not algorithms:
            self.app.show_warning_dialog("No Algorithms", "Select at least one hash algorithm.")
            return

        self.app.run_workflow(
            calculate_hashes,
            self._on_hashes_calculated,
            list(self.hash_files_list), algorithms,
            progress=True,
            error_title="Hash Calculation Failed",
        )

    def _on_hashes_calculated(self, results):
        self.hash_tree.tree.clear()
        self.hash_tree.item_map.clear()
        self._hash_path_by_item.clear()

        for entry in results:
            iid = self.hash_tree.insert("", "end", values=(
                entry.get("filename", ""),
                entry.get("formatted_size", ""),
                entry.get("md5", "—"),
                entry.get("sha1", "—"),
                entry.get("sha256", "—")[:32] + "..." if entry.get("sha256") else "—",
                entry.get("sha512", "—")[:32] + "..." if entry.get("sha512") else "—",
            ))
            self._hash_path_by_item[iid] = entry.get("path", "")
            self.hash_tree.set_item_path(iid, entry.get("path"))

        self.app.update_status(f"Hashed {len(results)} files.")

    def _verify_selected_hash(self):
        selection = self.hash_tree.selection()
        if not selection:
            self.app.show_warning_dialog("No Selection", "Select a file from the hash list.")
            return

        expected = self.verify_hash_input.text().strip()
        if not expected:
            self.app.show_warning_dialog("No Hash", "Enter the expected hash value.")
            return

        item = self.hash_tree.item(selection[0])
        values = item.get("values", [])
        if not values:
            return

        filename = values[0]
        # Find matching file path
        path = None
        for fpath in self.hash_files_list:
            if os.path.basename(fpath) == filename:
                path = fpath
                break

        if not path:
            self.app.show_warning_dialog("File Not Found", f"Cannot find path for {filename}")
            return

        algo = self.verify_algo.currentText()
        result = verify_hash(path, expected, algorithm=algo)

        if result["match"]:
            self.app.show_info_dialog(
                "✅ Hash Match",
                f"File: {filename}\nAlgorithm: {algo}\nHash MATCHES the expected value.",
            )
        else:
            self.app.show_warning_dialog(
                "❌ Hash Mismatch",
                f"File: {filename}\nAlgorithm: {algo}\n\n"
                f"Expected: {expected[:64]}...\n"
                f"Computed: {result['computed'][:64]}...\n\n"
                "The file may have been modified!",
            )

    # ------------------------------------------------------------------
    # OS Artifacts
    # ------------------------------------------------------------------

    def _parse_artifacts(self):
        root = self.artifact_path.text().strip()
        if not root or not os.path.isdir(root):
            self.app.show_warning_dialog("Invalid Path", "Enter a valid filesystem root path.")
            return

        self.lbl_artifact_status.setText("Parsing OS artifacts...")
        self.app.update_status("Parsing OS artifacts...")

        self.app.run_workflow(
            parse_os_artifacts,
            self._on_artifacts_parsed,
            root,
            progress=True,
            error_title="Artifact Parsing Failed",
        )

    def _on_artifacts_parsed(self, artifacts):
        self.artifact_tree.tree.clear()
        self.artifact_tree.item_map.clear()

        for category, data in artifacts.items():
            if not data:
                continue

            cat_display = category.replace("_", " ").title()

            if isinstance(data, list):
                group_id = self.artifact_tree.insert("", "end", values=(
                    cat_display, f"{len(data)} entries", "",
                ), open=False)

                for item in data[:100]:
                    if isinstance(item, dict):
                        key = item.get("username", item.get("name", item.get("source", "")))
                        value = json.dumps(item, default=str)[:200]
                    else:
                        key = str(item)[:80]
                        value = ""
                    self.artifact_tree.insert(group_id, "end", values=("", key, value))
            elif isinstance(data, dict):
                group_id = self.artifact_tree.insert("", "end", values=(cat_display, "", ""))
                for key, value in data.items():
                    val_str = json.dumps(value, default=str)[:200] if isinstance(value, (dict, list)) else str(value)
                    self.artifact_tree.insert(group_id, "end", values=("", key, val_str))

        total_items = sum(len(v) if isinstance(v, list) else 1 for v in artifacts.values() if v)
        self.lbl_artifact_status.setText(
            f"Parsed {len(artifacts)} categories, {total_items} total artifacts."
        )
        self.app.update_status("OS artifact parsing complete.")

    # ------------------------------------------------------------------
    # Password Tools
    # ------------------------------------------------------------------

    def _extract_hashes(self):
        source = self.pwd_source.text().strip()
        if not source or not os.path.exists(source):
            self.app.show_warning_dialog("Invalid Source", "Enter a valid file path.")
            return

        reply = QMessageBox.question(
            self, "Extract Password Hashes",
            f"Extract password hashes from:\n{source}\n\n"
            "This will read the file to identify hash formats. Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            results = extract_password_hashes(source)
        except Exception as exc:
            self.app.show_error_dialog("Extraction Failed", str(exc))
            return

        self.pwd_tree.tree.clear()
        self.pwd_tree.item_map.clear()

        for item in results:
            if "error" in item:
                self.pwd_tree.insert("", "end", values=(
                    "ERROR", source, "", "", item["error"],
                ))
            else:
                self.pwd_tree.insert("", "end", values=(
                    item.get("type", "hash"),
                    os.path.basename(item.get("source", source)),
                    item.get("username", ""),
                    item.get("hash_type", ""),
                    item.get("hash", str(item))[:80],
                ))

    def _analyze_strength(self):
        pwd = self.strength_input.text()
        if not pwd:
            self.app.show_warning_dialog("Empty Password", "Enter a password to analyze.")
            return

        results = analyze_password_strength([pwd])
        if results:
            r = results[0]
            color = {
                "Very Weak": "#dc2626", "Weak": "#ef4444",
                "Fair": "#f59e0b", "Good": "#10b981",
                "Strong": "#059669", "Very Strong": "#047857",
            }.get(r["strength"], "#6b7280")

            issues = "\n".join(f"  ⚠️ {issue}" for issue in r.get("issues", []))
            self.strength_result.setText(
                f"Strength: <b style='color:{color}'>{r['strength']}</b> "
                f"(Score: {r['score']}/7)\n"
                f"Length: {r['length']} | Upper: {'✅' if r['has_upper'] else '❌'} | "
                f"Lower: {'✅' if r['has_lower'] else '❌'} | "
                f"Digits: {'✅' if r['has_digit'] else '❌'} | "
                f"Special: {'✅' if r['has_special'] else '❌'}"
                + (f"\n\nIssues:\n{issues}" if issues else "")
            )
            self.strength_result.setTextFormat(Qt.RichText)

    # --- Dictionary attack ---
    def _populate_wordlist_combo(self):
        self.wordlist_combo.clear()
        self.wordlist_combo.addItem("Quick pick a detected wordlist...")
        detected = list_common_wordlists()
        for path in detected:
            self.wordlist_combo.addItem(path)
        if not detected:
            self.wordlist_combo.addItem("(none detected — use Browse)")
            self.wordlist_combo.setEnabled(False)

    def _on_wordlist_combo_changed(self, index):
        if index <= 0:
            return
        path = self.wordlist_combo.currentText()
        if os.path.isfile(path):
            self.attack_wordlist.setText(path)

    def _generate_crack_hash(self):
        source = self.pwd_source.text().strip()
        if not source or not os.path.exists(source):
            self.app.show_warning_dialog(
                "Invalid Source", "Enter a valid ZIP or PDF path in the Source field above."
            )
            return
        self.app.update_status("Generating crackable hash...")
        self.app.run_workflow(
            generate_crackable_hash, self._on_hash_generated,
            source,
            error_title="Hash Generation Failed",
        )

    def _on_hash_generated(self, result):
        if "error" in result:
            self.app.show_error_dialog("Hash Generation Failed", result["error"])
            return
        self.attack_hash_file.setText(result["hash_file"])
        self.app.update_status(f"Hash file generated via {os.path.basename(result['tool_used'])}.")

    def _run_dict_attack(self):
        hash_file = self.attack_hash_file.text().strip()
        wordlist = self.attack_wordlist.text().strip()
        if not hash_file or not os.path.isfile(hash_file):
            self.app.show_warning_dialog("Missing Hash File", "Generate or browse to a hash file first.")
            return
        if not wordlist or not os.path.isfile(wordlist):
            self.app.show_warning_dialog(
                "Missing Wordlist", "Choose your own dictionary file, or pick a detected system wordlist."
            )
            return

        tool = self.attack_tool_combo.currentText()
        hash_type = self.attack_hash_type.text().strip() or None

        self.attack_result.clear()
        self.app.update_status(f"Running dictionary attack ({tool})...")
        self.app.run_workflow(
            run_dictionary_attack, self._on_dict_attack_complete,
            hash_file, wordlist, hash_type, tool,
            progress=True,
            error_title="Dictionary Attack Failed",
        )

    def _on_dict_attack_complete(self, result):
        if "error" in result:
            if result.get("cancelled"):
                self.app.update_status("Dictionary attack cancelled.")
                self.attack_result.setPlainText("Cancelled by user.")
            else:
                self.app.show_error_dialog("Dictionary Attack Failed", result["error"])
            return

        cracked = (result.get("cracked") or "").strip()
        lines = [f"Tool: {result.get('tool')}", f"Return code: {result.get('returncode')}", ""]
        lines.append(f"Cracked:\n{cracked}" if cracked else "No password found in this wordlist.")
        stderr = (result.get("stderr") or "").strip()
        if stderr:
            lines.append(f"\nstderr: {stderr}")
        self.attack_result.setPlainText("\n".join(lines))
        self.app.update_status("Dictionary attack complete.")

    # ------------------------------------------------------------------
    # Tooltips
    # ------------------------------------------------------------------

    def _init_tooltips(self):
        attach_tooltips([
            (self.ingest_path, self.TOOLTIP_TEXTS["ingest_path"]),
            (self.ingest_output, self.TOOLTIP_TEXTS["output_dir"]),
            (self.btn_ingest, self.TOOLTIP_TEXTS["ingest_start"]),
            (self.btn_add_hash_files, self.TOOLTIP_TEXTS["hash_files"]),
            (self.btn_verify, self.TOOLTIP_TEXTS["verify_hash"]),
            (self.artifact_path, self.TOOLTIP_TEXTS["artifact_path"]),
            (self.btn_parse, self.TOOLTIP_TEXTS["parse_artifacts"]),
            (self.pwd_source, self.TOOLTIP_TEXTS["hash_source"]),
            (self.btn_strength, self.TOOLTIP_TEXTS["strength_check"]),
        ])
