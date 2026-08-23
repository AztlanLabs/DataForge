# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — Wave 5+6 (Audit & Forensic Gap Closure, 2026-08-23 06:30 UTC, 37/37 DONE, 1213 tests)
- TICK-501: `core/config.py` now preserves unknown keys (e.g. `collapsed_groups`) on reload, `core/cache.py` guards `conn is None` (no `AttributeError` in worker), `core/scanner.py` logs `FileNotFound`/`Permission`/`OSError` with optional `on_error` callback (R-CORE-3/4/6)
- TICK-502: `modules/sanitisation.py` [NEW] moves `secure_delete` out of `forensics.py` (F4) + hardlink-aware `st_nlink>1` warning (F21), `forensics.py` shim re-exports for backward compat
- TICK-503: `core/services/file_actions.py` now `__init__(audit_log, case_context)` + `_record_operation` hash-chained `AuditLog.append` per `transfer`/`delete`/`rename`/`archive` (F1 remainder)
- TICK-504: 6 files (`system_cleanup.py`, `search.py`, `recovery.py`, `integrity.py`, `performance.py`, `ui/views/search.py`) `datetime.now()` → `datetime.now(timezone.utc)` UTC (F9 remainder)
- TICK-506: `ui/views/forensics_view.py` `EnhancedTreeview` → `QTreeView` + `TimelineModel(QAbstractTableModel)` virtualised, `events[:5000]` cap removed (U3)
- TICK-507: `ui/widgets.py` `HexView(QWidget)` with hex/ASCII columns + `QTreeWidget` field inspector for MBR/PE/ELF (U4)
- TICK-508: `core/image_io.py` [NEW] `open_image` + `RawImageReader` gated `pyewf`/`pyaff` fallback, `core/streams.py` [NEW] `list_alternate_streams` ADS/xattr/MotW, `modules/indicators.py` [NEW] `match_path` YARA/SSDEEP/NSRL `HAS_*` gated (F5/F7/F8)
- TICK-509: `ui/plugin_loader.py` `isolation='subprocess'` `ProcessPoolExecutor` + `require_signed` `*.sig` + `AuditLog` `plugin_load*` (F12 remainder)
- TICK-510: `core/logger.py` `ChainToAuditFilter` forwarding `>=INFO` to `AuditLog` when `chain_to_audit=True` + Evidence Mode (F11 remainder)
- TICK-511: `engine/parsers.py` [NEW] `ParserPool` lazy `ProcessPoolExecutor` + `BrokenProcessPool` → `ParseResult(success=False)` (F13)
- TICK-512: `docs/CLI_REFERENCE.md` + `README.md` + `docs/GUI_WORKFLOWS.md` + `ui/views/about.py` platform matrix `Linux ✓`/`macOS ✓`/`Windows ✗ TrashScanUnsupported` + tooltip (U10/U11)
- TICK-505 (Wave 6): `modules/forensics.py` `ingest_disk_image` now `O(batch)` queue incremental consume via `_drain_batch` (F14)

### Fixed — Wave 5+6 + UI (2026-08-23, dc44be4 + b78dff9 + 6d56c2c)
- `b78dff9` NTFS/fuse hardening: `core/_metadata_patch.py` [NEW] + `run_ui.py:7` + `__init__.py:3` + `api/schema.py:5` tolerate `OSError 5` on corrupted `.dist-info/entry_points.txt` (`importlib.metadata` → `ImportWarning` + debug log, not crash); new ext4 venv `/home/crowne/.venvs/DataForge`
- `6d56c2c` Settings tier infinite recursion: `views/settings.py:303` `apply_tier` / `ui/app.py:664` `update_sidebar_experience` now guarded `_in_apply_tier`/`_in_sidebar_update` (was `settings→app→settings` loop → `RecursionError` on `excluded_extensions` `json.dump`)
- `dc44be4` Dropdown at top-right: `ui/app.py:404` `add_view` no permanent `QGraphicsOpacityEffect` (transient 0→1 then `setGraphicsEffect(None)`), `theme_tokens.py:393` `QComboBox QAbstractItemView` themed popup, `app.py:683` `switch_view` freezes `setUpdatesEnabled` to avoid blank/see-through composite
- `dc44be4` Tier navbar: restored `GROUP_MIN_TIER` filtering (`Home:Simple`, `Clean & Optimize:Standard`, `Recover & Investigate:Everything`) in `build_navigation_sidebar` so tier hides/shows groups, guarded rebuild
- `dc44be4` STOP button: `ui/job_manager.py:57` `ManagedWorker` now handles `**kwargs` `cancel_token`, chains `progress_callback`, normalizes `InterruptedError`→`cancelled` dict, `is_busy` checks QThreads, `_on_progress` forwards to `DataForgeApp.update_progress`; `recovery.py:575` `run_photorec` `Popen` polling, `hardware.py:45` per-step cancel, `media_ops.py:119` `convert_image` `cancel_token`, `search.py:377`/`duplicates.py:196` `return` on cancel (not `raise`), `views/base.py:77` `InterruptedError`→`Cancelled`, `app.py:827` `show_workflow_error` treats cancel as status not dialog, `app.py:396` `cancel_action` force-hides after 2s
- `dc44be4` Visual artifacts: `performance.py:471` `get_live_resource_snapshot(blocking=False)` `interval=None` for timer ticks (was 400ms main-thread sleep), `performance_view.py:435` non-blocking + viewport updates, `storage_devices.py:89` `run_workflow` async + `viewport().update()`, `theme_tokens.py:444` `QProgressBar::chunk` `6px` + `QFrame StyledPanel` opaque, `app.py:683` `switch_view` transient effect + freeze

### Added
- TICK-002: `FileProvider` ABC expanded to a seven-method, cancel/progress-aware contract (`list_files`, `list_files_parallel`, `stat`, `open`, `hash`, `hash_many`, `exists`) with `LocalProvider` as thin scanner/hasher shim and a `default_provider()` entry point
- TICK-002: `FileEntry` OS-identity fields `st_ino`/`st_dev`/`st_blocks` (default 0) plus `hardlink_key` for hardlink grouping and sparse-file awareness
- Commit convention enforcement via `.githooks/commit-msg`
- Documentation maintenance rules in CONTRIBUTING.md
- GitHub Actions CI (`.github/workflows/ci.yml`): pytest + coverage, ruff, mypy, and pip-audit on every push/PR to `develop`/`main`
- `.pre-commit-config.yaml`: trailing-whitespace/EOF/merge-conflict checks plus `ruff --fix`
- `.github/dependabot.yml`: weekly pip + GitHub Actions update PRs
- ruff, black, mypy, and coverage configuration in `pyproject.toml`
- Regression test guarding the forensic HTML report against `<script>`-tag filenames
- `BaseView.choose_file()` and `BaseView.choose_directory()` — explicit file/folder pickers
- `BaseView.confirm_destructive_preview()` — scrollable, per-row opt-out preview with running total
- `BaseView.whats_this_for()` — inline "What's this?" affordance helper
- Status-bar busy message now names the running task (e.g. "Running: search files…")
- `BaseView._humanize_callable_name()` — helper for the status bar
- `StorageDevicesView` — GUI surface for `fm devices` (mount/type/filesystem/used/total table with a per-row details panel)
- `AutomationsView` — single sidebar entry that merges Tools & Workflows and Action Builder into a 2-tab notebook (Action Builder / Tools)
- pytest-qt smoke test that mounts every registered view and confirms the expected sidebar title
- `dataforge/core/paths.py` (TICK-001) — canonical per-OS locations via platformdirs (XDG on Linux, `~/Library` on macOS, `%LocalAppData%` on Windows) for config/cache/state/logs/runtime/exports, with a one-shot legacy `~/.dataforge` migration shim that backs up to `~/.dataforge.backup.<ts>` and logs `migrated_from_legacy`; opt out via `DATAFORGE_SKIP_LEGACY_MIGRATION=1`
- `dataforge.__version__` (TICK-001) — single version source: `importlib.metadata` with fallback to the `pyproject.toml` `[project] version`
- 13 contract tests in `tests/test_paths_contract.py` covering the paths contract on all three OSes and the migration/version behavior
- TICK-301: `dataforge/engine/daemon.py` — full asyncio event loop + `JobQueue` with `ThreadPoolExecutor`/`ProcessPoolExecutor` for hash work
- TICK-301: `dataforge/client/` — `DataForge.connect()` wrapping `Transport.auto_discover` with `in_process` fallback + synchronous wrapper
- TICK-301: `dataforge/service/__main__.py` — `dataforge-engine` entrypoint for the daemon
- TICK-302: systemd user socket+service (`dataforge/service/linux/`), D-Bus service file, launchd plist (`dataforge/service/macos/`), Windows ServiceFramework (`dataforge/service/windows/`)
- TICK-303: `build_exe.py` `onedir` profile for nfpm packaging; `packaging/nfpm.yaml` + `packaging/README.md` + `packaging/scripts/{postinst,prerm}.sh`
- TICK-303: `packaging/assets/dataforge.desktop` + `dataforge.svg` for Linux desktop integration
- TICK-304: `dataforge/core/audit.py` — append-only 0o600 SQLite WAL audit log with SHA-256 hash chain (`hash(prev||canonical_json)`)
- TICK-304: `dataforge/core/case.py` — `CaseContext` dataclass (case_id, operator, host, source_sha256, evidence_mode) with thread-safe singleton
- TICK-304: `generate_forensic_report` now includes provenance fields (operator, host, source_sha256, case_id, audit_tail_hash, tool_version) and UTC ISO-8601 timestamps
- TICK-304: `FileActionService.transfer_items`/`delete_items` gated by Evidence Mode (returns `success=False` with no FS change)
- TICK-304: `secure_delete` gated by Evidence Mode (refuses to run when `CaseContext.evidence_mode=True`)

### Changed
- Updated all documentation cross-references after review restructure
- Migrate package metadata (name, version, dependencies, `fm` entry point) from `setup.py` into `pyproject.toml` (PEP 621); `setup.py` is now a thin `setup()` shim
- Pinned lower-bound versions for previously-unconstrained runtime dependencies (click, rich, tqdm, pandas, send2trash, pypdf, pymupdf, opencv-python-headless)
- **WS-C Interaction Correctness**: settings now autosave on every change with a transient "Saved ✓" indicator instead of an interrupting dialog or hidden Save buttons; the Settings theme dropdown is now a read-only label that mirrors the sidebar Dark Mode checkbox (sidebar is the single source of truth); the sidebar shows every group regardless of Experience Level, and the tier now controls only in-view complexity; view help renders Markdown; destructive previews are scrollable checkable tables with running size totals and a danger-tinted Proceed button
- **WS-D IA, Naming & Parity**: sidebar regrouped into task-oriented sections (Home / Find & Organize / Clean & Optimize / Recover & Investigate / System); Tools & Workflows and Action Builder merged into Automations; new Storage & Devices view in the Clean & Optimize group; labels renamed to user-facing names (Search, Duplicate Finder, Media Tools, Metadata & EXIF, Clean Up Space, Performance, File Recovery, Forensics, Hardware Info, Storage & Devices, Automations); the "Experience Level" setting is now "Detail level" with values Simple / Standard / Everything; the `_VALID_TIERS` config enum, TIER_RANK, and the `register_tiered` calls in settings.py all move to the new names in lockstep
- **WS-E Motion, Empty/Error, A11y**: sidebar group expand/collapse and view-switch are now animated via `QPropertyAnimation` (180ms / 160ms with OutCubic easing); the Braille-character busy indicator is replaced by a native `QProgressBar` in indeterminate mode; a new "Reduce motion" setting in Settings → General → Appearance honours the OS-level preference and zeroes both animation durations at runtime; every interactive widget (buttons, inputs, checkboxes, list/tree/tab) now draws a 2px focus ring on the `focus_ring` token that swaps border colour without shifting the content; views (Search, Duplicates) now show a purposeful `EmptyState` with icon, body, and an action button instead of a bare "No results" label; `friendly_error_message` translates the common Python exceptions (PermissionError, FileNotFoundError, IsADirectoryError, NotADirectoryError, OSError, ValueError, TimeoutError, KeyboardInterrupt, MemoryError, RecursionError) into one-line user-readable summaries with hints; sidebar buttons, the status bar, and the destructive preview's Proceed button carry explicit `accessibleName` / `accessibleDescription` so screen readers announce the action; the destructive preview's Proceed button is prefixed with a `⚠` glyph when the caller's label is not already a destructive verb, giving colour-blind users the same danger signal sighted users get from the red background; an 18-icon monochrome SVG set (16x16 viewBox, 1.6px stroke) ships at `dataforge/ui/resources/icons.py` and is attached to every sidebar view plus the expand/collapse chevron and the sun/moon theme toggle, with the icon tone regenerated on every theme change

### Fixed
- Broken links in ARCHITECTURE.md and TECHNICAL_SOURCE_OF_TRUTH.md
- Stale path prefixes (missing `dataforge/` prefix)
- Removed unused imports, dead variable assignments, and ambiguous single-letter loop variables flagged by ruff across `dataforge/` and `tests/`
- `fm devices` used a backslash escape sequence inside f-string braces, which is a `SyntaxError` on Python <3.12 despite the documented Python 3.10+ minimum
- **2c.1**: Killed the file-vs-folder Yes/No/Cancel `QMessageBox` riddle — every affected view (Search, Action Builder, Metadata, Tools, Cleaner Plugin) now exposes separate "Browse File…" and "Browse Folder…" buttons that call `BaseView.choose_file()` / `choose_directory()` directly
- **2c.2**: Settings persistence was inconsistent (some fields autosaved, others needed hidden Save buttons followed by a modal "Success" dialog); every setting now autosaves the moment it changes
- **2c.3**: The Settings theme `QComboBox` and the sidebar Dark Mode `QCheckBox` both wrote to the same key and could fall out of sync; the dropdown is now a read-only label that mirrors the checkbox
- **2c.4**: The Experience Level setting hid entire sidebar groups (System Maintenance, Advanced Analysis) from Basic users, creating a discoverability cliff where users could not see that Forensics Lab existed; every group is now always visible
- **2c.6**: The status bar showed a generic "Busy: please wait…" message that did not name the running task
- **2d.4**: `fm devices` had no GUI path — the same `device_manager.list_storage_devices` API is now exposed in the GUI as the **Storage & Devices** view (Clean & Optimize group)
- **2d.5**: Final name-sweep dropped the last stragglers of the old "Metadata Studio" / "Forensics Lab" / "Hardware Diagnostics" / "Search & Organize" / "Experience Level" labels from view module docstrings, code comments, README, ARCHITECTURE.md, GUI_WORKFLOWS.md, and TECHNICAL_SOURCE_OF_TRUTH.md; a regression test walks `dataforge/` and fails if any of the old names ever reappear in Python code
- **2e.1**: Sidebar group expand/collapse and view-switch transitions were instant; both are now animated with `QPropertyAnimation` (180ms sidebar / 160ms view, OutCubic easing) via per-group container widgets and per-view `QGraphicsOpacityEffect`s
- **2e.2**: The status-bar busy indicator was a Braille-character label cycled by a manual `QTimer` (inaccessible to screen readers, font-dependent); it is now a native `QProgressBar` that switches between indeterminate (`setRange(0, 0)`) and determinate modes, sharing the rest of the bar's AA-validated token colours
- **2e.4**: There was no visible keyboard focus indicator beyond the OS default (suppressed by the dark Fusion palette); every interactive widget now draws a 2px `focus_ring` border on `:focus` without shifting the content (the default border is pre-allocated as transparent so toggling focus only changes colour)

### Security
- **S2 (Fixed)**: Forensic HTML report was vulnerable to stored HTML/JS injection — every interpolated value is now passed through `html.escape()`
- **S4 (Fixed)**: Trash restore trusted the `original_path` from a `.trashinfo` file directly as a move destination — paths with `..` traversal or targeting a system directory now redirect into a confined `restore_root` (defaults to `~/Recovered`)
- **S5 (Fixed)**: Plugin loader executed any `.py` file in the plugins directory with no signing, manifest, or sandbox — loading is now opt-in (`config["plugins_enabled"]`, default off) and checks directory/file permissions before exec'ing
- **S6 (Fixed)**: `secure_delete()` overstated its guarantee and silently fell back to `send2trash` on unlink failure — now documented as best-effort with no trash fallback
- **S7 (Fixed)**: System Cleanup blanket-classified every file under System Temp/User Cache/etc. as junk, including user-supplied paths — user-supplied paths now only match by extension/filename; sockets/FIFOs are always skipped; `/tmp` and `/var/tmp` get a 1-day minimum-age filter
- **S8 (Fixed)**: Cracked-hash files were written with default permissions and displayed passwords leaked their first two characters — hash files are now `0600`, passwords fully masked
- **S9 (Fixed)**: `collect_recent_documents()` parsed untrusted XML with stdlib `xml.etree.ElementTree` (entity-expansion DoS) — switched to `defusedxml.ElementTree`
- **S10 (Fixed)**: Config loading blind-merged `config.json` with no validation — values are now type/range/enum-checked, unknown keys dropped, invalid values replaced with defaults
- **S11 (Fixed)**: Scanned/recovered files were opened via the OS handler with no check — executables (by extension or Unix execute bit) now prompt for confirmation first
- **S12 (Fixed)**: Forensic report and keyword-index files were written with default (often world-readable) permissions — now written `0600`
- **S13 (Fixed)**: No cap on decoded image pixels or PDF page counts — added `Image.MAX_IMAGE_PIXELS` and a `MAX_PDF_PAGES` limit against decompression-bomb inputs

## [0.1.0] - 2026-07-11

### Added
- **Design Token System** (`ui/theme_tokens.py`)
  - 46 WCAG AA-validated colour tokens per theme (≥4.5:1 contrast)
  - Template-driven QSS generation (`generate_qss`)
  - Palette generation for Qt (`generate_palette`)
  - Named type-scale constants (caption, body, subheading, heading, display)
  - SVG glyph helpers for checkbox, spinbox, and combobox indicators
  
- **Documentation Overhaul**
  - Unified CONTRIBUTING.md with commit conventions, versioning, and release process
  - Consolidated review documentation into `docs/reviews/` (README.md, AUDIT_REPORT.md, ROADMAP.md, AUDIT_REPORT.md)
  - Updated all architecture and workflow docs to reflect PyQt5 migration
  
- **Testing Infrastructure**
  - 254 passing tests across comprehensive, integration, contract, and new-modules suites
  - 30 token-regression tests guarding the design system
  
- **Security Hardening**
  - SHA-256 as default hash algorithm (was MD5)
  - Self-describing integrity snapshots with algorithm metadata
  - Symlink-following disabled in scanner (`follow_symlinks=False`)
  - Thread-safe SQLite cache with WAL mode and locking
  - Byte-verification for duplicate deletion
  
- **Core Functionality**
  - Restored `rename_with_regex` in `core/operations/files.py`
  - Added `sha512` and `blake2b` support to hasher
  - Added `JSONDecodeError` handling for integrity snapshots
  - Fixed Windows Recycle Bin scan (raises `TrashScanUnsupported`)
  - Improved error reporting (replaced `print()` with `logger.error()`)
  - Lazy-loading for exiftool version probe

### Changed
- **UI Framework Migration**: Migrated from Tkinter/ttkbootstrap to PyQt5
- **Theming**: Replaced hand-written QSS blocks with token-driven generation
- **Surface Brightness**: Light content `#ffffff`→`#f7f7f8`; dark base `#1c1c20`, elevated `#26262c`
- **Focus Handling**: Removed `outline: 0` suppression
- **Dependency Split**: Separated `requirements.txt` (runtime) from `requirements-dev.txt` (build/test)
- **Product Name**: Rebranded from "FileManager" to "DataForge"

### Fixed
- **H1**: Test suite collection failure (stale `rename_with_regex` import)
- **M1**: `fm hash-calc --algo sha512` crash (KeyError)
- **M2**: Integrity snapshot verification crash on truncated files
- **M3**: Symlink-following recursion DoS and scope escape
- **M4**: Integrity hashing hardcoded MD5 regardless of config
- **M5**: Shared SQLite cache concurrency issues (`database is locked`)
- **M6**: Duplicate detection deleted on hash equality without byte verification
- **L1-L9**: Various low-severity correctness and hygiene issues

### Security
- **S1 (Fixed)**: MD5 used for integrity/dedup → now SHA-256 default
- **S3 (Fixed)**: Symlink-following scan → now disabled
- **S2, S4, S5, S6, S7, S8, S9, S10, S11, S12, S13 (Open)**: Tracked in `docs/reviews/AUDIT_REPORT.md`

### Known Issues
- No CI/CD pipeline yet (Phase 0 in roadmap)
- Forensic HTML report vulnerable to XSS (S2)
- Trash restore trusts attacker-controllable `.trashinfo` paths (S4)
- System Cleanup blanket-classifies `/tmp` and cache trees (S7)
- Device Manager has CLI but no GUI view

[Unreleased]: https://github.com/yourusername/DataForge/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/DataForge/releases/tag/v0.1.0
