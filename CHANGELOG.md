# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
  - Consolidated review documentation into `docs/reviews/` (EXECUTIVE_SUMMARY.md, AUDIT_FINDINGS.md, IMPROVEMENT_PLAN.md, NOTES_REVIEW.md)
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
- **S2, S4, S5, S6, S7, S8, S9, S10, S11, S12, S13 (Open)**: Tracked in `docs/reviews/AUDIT_FINDINGS.md`

### Known Issues
- No CI/CD pipeline yet (Phase 0 in roadmap)
- Forensic HTML report vulnerable to XSS (S2)
- Trash restore trusts attacker-controllable `.trashinfo` paths (S4)
- System Cleanup blanket-classifies `/tmp` and cache trees (S7)
- Device Manager has CLI but no GUI view

[Unreleased]: https://github.com/yourusername/DataForge/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yourusername/DataForge/releases/tag/v0.1.0
