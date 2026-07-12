# Technical Source of Truth

> This is the deepest technical map in the repository.
>
> For faster onboarding, start with:
>
> - [`README.md`](./README.md)
> - [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)
> - [`docs/CLI_REFERENCE.md`](./docs/CLI_REFERENCE.md)
> - [`docs/GUI_WORKFLOWS.md`](./docs/GUI_WORKFLOWS.md)
> - [`docs/DEVELOPMENT_GUIDE.md`](./docs/DEVELOPMENT_GUIDE.md)

## Purpose

This file is the authoritative technical map of the DataForge codebase as it exists today.

It is intended to answer four questions for a new maintainer:

1. What is each file responsible for?
2. How does control move through the system?
3. Which abstractions are real and currently used, versus planned or partially used?
4. Where are the important implementation gaps, duplications, and risks?

This document is based on the current source files in the repository, not on intended behavior.

The GUI was migrated from Tkinter/ttkbootstrap to **PyQt5** and several new modules were added after this document was written. Some GUI/file-by-file sections may not be fully re-audited. A complete review of correctness, security, and staleness is maintained in [`docs/reviews/NOTES_REVIEW.md`](./reviews/NOTES_REVIEW.md). Key points: 254 tests pass, integrity defaults to SHA-256 (not MD5), the scanner no longer follows symlinks, and the SQLite cache is thread-safe. Open findings include forensic-report HTML injection (S2), trash-restore path traversal (S4), and System Cleanup over-classification (S7).

## Scope

Documented as maintained source:

- Root packaging and launch files
- `dataforge/` package
- `tests/` directory

Not treated as maintained source:

- `build/`
- `dist/`
- `__pycache__/`

Those folders are generated artifacts or cache output.

## System Overview

The project is a local desktop and CLI file-management utility with two separate user-facing entrypoints:

- CLI entrypoint: `fm` -> `dataforge.cli:main`
- GUI entrypoint: `run_ui.py` -> `dataforge.ui.app.DataForgeApp`

The codebase has six architectural layers:

1. **Infrastructure and shared primitives** in `dataforge/core/` — data models, scanning, config, caching, hashing, logging, utilities.
2. **Shared file-mutation operations** in `dataforge/core/operations/` — neutral filesystem mutation functions (move, copy, delete, rename, collision resolution).
3. **Service layer** in `dataforge/core/services/` — `FileActionService` provides batched file operations with progress, cancellation, and dry-run support. This is the primary dispatch layer used by modules, views, widgets, and action steps.
4. **Task-oriented business logic** in `dataforge/modules/` — higher-level features (search, duplicates, organizer, renamer, cleaner, integrity, usage, reporting).
5. **Composable action pipeline** in `dataforge/core/actions/` — step-based workflow engine used by the GUI Action Builder.
6. **GUI orchestration and widgets** in `dataforge/ui/` — desktop application shell, views, widgets, plugin loader.

There is also a dual workflow pattern: modules provide direct function-call workflows (used by the CLI and parts of the GUI), while the action pipeline provides a step-chain model (used by the Action Builder view). Both now route filesystem mutations through `FileActionService` → `core/operations/files.py`, which means the mutation rules are centralized even though the orchestration models differ.

## Top-Level Control Flow

### CLI flow

`setup.py` registers `fm=dataforge.cli:main`.

Runtime flow:

1. User runs a Click command.
2. `dataforge/cli.py` parses arguments.
3. The command calls one of the `dataforge.modules.*` functions or classes.
4. Those modules depend on `dataforge.core.scanner.scan_directory`, `core.services.FileActionService`, and related helpers.
5. Output is rendered back to stdout using Click.

CLI commands: `scan`, `dupes`, `search`, `organize`, `rename`, `clean`, `usage`, `integrity create`, `integrity check`.

### GUI flow

`run_ui.py` enables High-DPI scaling, creates a `PyQt5.QtWidgets.QApplication`, and instantiates `DataForgeApp` as its main window.

Runtime flow:

1. `DataForgeApp` builds a fixed-width (230px), non-collapsible sidebar (`QFrame` with grouped nav buttons) plus a `QStackedWidget` content area, a status bar, progress controls, and a cancellation event.
2. Fourteen base views are instantiated eagerly at startup (Dashboard, Search & Organize, Duplicate Finder, Action Builder, Tools & Workflows, Media Tools, System Cleanup, Performance, File Recovery, Metadata Studio, Hardware Diagnostics, Forensics Lab, Settings, About & Help), plus any discovered plugins.
3. Long-running work is pushed to a `BackgroundWorker(QThread)` through `DataForgeApp.run_workflow` or `run_background`.
4. Worker results and progress updates are sent back via Qt signals (`progress_signal`, `status_signal`, `result_signal`, `error_signal`) connected directly to UI update slots — there is no `queue.Queue` or polling loop.
5. `run_workflow` auto-inspects worker function signatures for `progress_callback` and `cancel_token` parameters and injects them automatically.
6. Individual views either call `dataforge.modules.*` directly or build an `ActionContext` plus `ActionStep` chain, routing filesystem mutations through `FileActionService`.

### Dual orchestration models

The repository contains two orchestration models:

- **Module-based**: `modules/organizer.py`, `modules/renamer.py`, `modules/search.py`, `modules/duplicates.py` — direct function calls, used by CLI and most GUI views.
- **Pipeline-based**: `core/actions/*.py` — composable step chains, used by the Action Builder view.

Both models now delegate filesystem mutations to `FileActionService` → `core/operations/files.py`. The orchestration differs but the mutation rules are shared.

## Architectural Facts That Matter

### 1. `FileEntry` is the main metadata carrier

`dataforge/core/common.py` defines `FileEntry`, a dataclass that stores:

- `path: str` — absolute path
- `filename: str`
- `extension: str`
- `size: int`
- `created_at: float`, `modified_at: float` — epoch timestamps
- `is_dir: bool = False`
- `md5`, `sha1`, `sha256` — optional hash strings

Properties: `created_dt` and `modified_dt` return `datetime` objects from the timestamps.

Most of the system passes `FileEntry` objects around once a scan begins.

### 2. Scanning is centralized

`dataforge/core/scanner.py` is the shared directory traversal generator. It yields `FileEntry` objects and supports both directory and single-file paths. `build_file_entry(path)` constructs a single `FileEntry` from OS stat data.

### 3. Config is global and persistent

`dataforge/core/config.py` creates a singleton `ConfigManager` and persists settings to `~/.dataforge/config.json`. Keys: `theme`, `safe_mode`, `excluded_extensions`, `excluded_folders`, `max_thread_workers`, `hash_algorithm`, `log_level`, `size_unit`, `dashboard_paths`.

### 4. Hash caching is persistent

`dataforge/core/cache.py` stores hashes in SQLite at `~/.dataforge/cache.db`. Cache key includes `path`, `size`, `mtime`, and `algo`.

### 5. `FileActionService` is the central batch operations layer

`dataforge/core/services/file_actions.py` provides `FileActionService`, a class of class methods that wrap `core/operations/files.py` with batch execution, progress reporting, cancellation, and dry-run support. It is used by:

- `modules/organizer.py` and `modules/renamer.py` for CLI-facing operations
- `ui/views/search.py`, `ui/views/duplicates.py`, `ui/views/tools.py` for GUI batch actions
- `ui/widgets.py` (`EnhancedTreeview`) for context-menu file operations
- `core/actions/io.py` and `core/actions/modifications.py` for pipeline steps

This is the most important architectural evolution in the codebase: filesystem mutations are now centralized through `FileActionService` → `core/operations/files.py`, even though the calling patterns (module-direct vs. pipeline-step) differ.

### 6. GUI threading is centralized

`dataforge/ui/app.py` owns:

- `BackgroundWorker(QThread)` instances and their Qt signals (`progress_signal`, `status_signal`, `result_signal`, `error_signal`) for cross-thread communication — no `queue.Queue` is used
- `run_workflow` which auto-injects `progress_callback`/`cancel_token` into worker functions
- `post_to_main`, `post_progress`, `post_status` for thread-safe UI updates
- the spinner, progress bar, and cancel event

### 7. Shared GUI helpers are centralized in `BaseView`

`ui/views/base.py` provides shared methods used across all views: `confirm_preview`, `handle_preview_outcome`, `present_batch_outcome`, `summarize_completion`, `batch_outcome_counts`, `validate_regex_pattern`, `validate_filename_candidate`, `choose_file_or_directory`.

### 8. Plugin support is aligned to the GUI plugin directory

The GUI app loads plugins from `dataforge/ui/plugins`, the build scripts bundle that directory, and `PluginLoader` imports plugin modules with the package name `dataforge.ui.plugins.*` so relative imports inside plugins resolve correctly.

### 9. Hover tooltips are shared across all views

`ui/widgets.py` provides `HoverTooltip` and `attach_tooltips()`, used by SearchView, DuplicatesView, ToolsView, ActionBuilderView, MediaView, and SettingsView for in-context guidance.

## File-by-File Source Map

### Root Files

#### `setup.py`

- Package definition using `setuptools.setup` with `find_packages()`.
- Declares console script `fm=dataforge.cli:main`.
- Install requires: `click`, `rich`, `tqdm`.
- Does not include GUI dependencies; `requirements.txt` is broader.

#### `requirements.txt`

Full dependency list: `click`, `rich`, `tqdm`, `pandas`, `PyQt5`, `send2trash`, `pytest`, `pyinstaller`, `Pillow`, `pypdf`, `psutil`, `python-magic`, `PyExifTool`, `mutagen`, `py-cpuinfo`.

#### `run_ui.py`

Desktop GUI bootstrapper. Creates a `PyQt5.QtWidgets.QApplication` with high-DPI scaling enabled, instantiates `DataForgeApp`, calls `.show()`, and runs `app.exec_()`.

#### `build_exe.py`

Programmatic PyInstaller build script. Builds from `run_ui.py`, produces a windowed one-file executable named `DataForge`. Injects data for `dataforge/ui/plugins` and hidden imports for `PyQt5` (`QtCore`, `QtWidgets`, `QtGui`), `PIL`, and `send2trash`.

#### `DataForge.spec`

PyInstaller spec file. Entry script is `run_ui.py`. Includes `dataforge/ui/plugins` as bundled data. `console=False`.

### Package Root

#### `dataforge/__init__.py`

Package marker only. Empty file.

#### `dataforge/cli.py`

Main CLI command surface built with Click.

Commands:

| Command | Key Options |
|---------|-------------|
| `scan` | `--recursive/--no-recursive` |
| `dupes` | `--max-depth`, `--sort` (group/ext/path/name/size/created/modified), `--reverse`, `--limit`, `--format` (text/json/jsonl), `--output`, `--export-format` (csv/json/txt), `--flat-export`, `--count-only` |
| `search` | `--name-glob`, `--name-regex`, `--ext`, `--content`, `--content-regex`, `--case-sensitive`, `--min-size`, `--max-size`, `--newer-than-days`, `--older-than-days`, `--max-depth`, `--sort`, `--reverse`, `--limit`, `--format` (text/json/jsonl), `--error-format` (text/json), `--count-only` |
| `organize` | `--dest` (required), `--action` (move/copy), `--name`, `--ext`, `--dry-run/--execute` |
| `rename` | `--pattern` (required), `--repl` (required), `--dry-run/--execute` |
| `clean` | `--dry-run/--execute` |
| `usage` | (none) |
| `integrity create` | `path`, `snapshot` |
| `integrity check` | `path`, `snapshot` |

How it works:

- `scan` streams entries from `scan_directory`.
- `dupes` calls `find_duplicates`, supports `build_duplicate_records` → `order_duplicate_records` → `build_duplicate_export_rows` → `export_result_rows` for structured/sliced output.
- `search` uses `build_search_query` → `search_files` or `iter_search_files` → `order_search_results` for sliced output. Supports `--name-glob` / `--name-regex` (mutually exclusive). Invalid flag combinations can return JSON errors with `--error-format json`.
- `organize` builds a `SearchQuery` and calls `Organizer.organize_files`.
- `rename` calls `bulk_rename`.
- `clean` calls `remove_empty_folders` from `modules.cleaner`.
- `usage` calls `analyze_size` and `generate_usage_report`.
- `integrity` is a nested Click group for snapshot creation and verification.

### `dataforge/core/`

#### `dataforge/core/__init__.py`

Convenience re-export module. Exports: `FileEntry`, `get_file_hash`, `get_hashes`, `scan_directory`, `logger`, `config`.

#### `dataforge/core/common.py`

Shared data model definitions.

- `FileEntry` dataclass — fields: `path`, `filename`, `extension`, `size`, `created_at`, `modified_at`, `is_dir` (default False), `md5`, `sha1`, `sha256` (optional).
- Properties: `created_dt`, `modified_dt` — return `datetime.fromtimestamp()`.

This is the shared metadata contract used across scanner, search, duplicates, organizer, services, and the action pipeline.

#### `dataforge/core/scanner.py`

Recursive filesystem traversal.

Functions:

- `build_file_entry(path: str) -> FileEntry | None` — constructs a single `FileEntry` from OS stat data. Returns `None` on `OSError`.
- `scan_directory(root_path, recursive=True, max_depth=-1, cancel_token=None)` — generator yielding `FileEntry` objects. Supports single file paths (yields one entry). Honors `excluded_folders` and `excluded_extensions` from config. Depth control: -1 = infinite, 0 = current dir only, N = N levels. Swallows `OSError` on inaccessible directories.

#### `dataforge/core/config.py`

Singleton configuration service.

- `ConfigManager` — singleton via `__new__`. Methods: `load`, `save`, `get(key, default)`, `set(key, value)`.
- `DEFAULT_CONFIG` keys: `theme` ("cosmo"), `safe_mode` (True), `excluded_extensions` ([".tmp", ".log"]), `excluded_folders` ([".git", "node_modules", "__pycache__"]), `max_thread_workers` (4), `hash_algorithm` ("sha256"), `log_level` ("INFO"), `size_unit` ("Auto"), `dashboard_paths` ([~/Documents]).
- Persists to `~/.dataforge/config.json`.
- Global instance: `config`.

#### `dataforge/core/cache.py`

Persistent file-hash cache using SQLite at `~/.dataforge/cache.db`.

- `CacheManager` — methods: `_init_db`, `get_hash(path, size, mtime, algo)`, `set_hash(path, size, mtime, hash_val, algo)`, `clear`, `close`. All methods are serialized through a `threading.Lock`, and `_init_db` sets `PRAGMA journal_mode=WAL`, so the shared connection is safe under concurrent `BackgroundWorker(QThread)` access.
- Schema: `file_hashes` table with columns `path` (PRIMARY KEY), `size`, `mtime`, `hash`, `algo`.
- `clear` deletes all rows and runs `VACUUM`.
- Global instance: `file_cache`.

#### `dataforge/core/hasher.py`

File hashing utilities.

- `BLOCK_SIZE = 65536` (64 KB chunks).
- `SUPPORTED_ALGORITHMS = ('md5', 'sha1', 'sha256', 'sha512', 'blake2b')`.
- `get_file_hash(filepath, algo='md5', cancel_token=None) -> str` — validates `algo` against `SUPPORTED_ALGORITHMS` (raises `ValueError` otherwise). Returns empty string on read failure.
- `get_hashes(filepath, algos: list) -> dict` — single file pass for multiple algorithms.

#### `dataforge/core/logger.py`

Central logging setup.

- `setup_logger(name='dataforge', log_file=None, level=INFO) -> Logger` — adds console handler (stdout) and optional rotating file handler (5 MB / 3 backups). Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`. Guards against duplicate handlers.
- Default: `logger = setup_logger("dataforge", "~/.dataforge/app.log")`.

#### `dataforge/core/provider.py`

File-provider abstraction for future alternate backends.

- `FileProvider` (ABC) — abstract methods: `list_files`, `move`, `copy`.
- `LocalProvider(FileProvider)` — wraps `scan_directory`, `shutil.move`, `shutil.copy2`.

Reality: this abstraction is not the primary path through the system. Most code uses `os`, `shutil`, and `scan_directory` directly.

#### `dataforge/core/media_ops.py`

Shared media conversion helpers.

Functions:

- `merge_pdfs(file_paths, output_path, dry_run=False, progress_callback=None, cancel_token=None) -> dict` — merges PDFs using `pypdf`. Returns report dict with `operation`, `output_path`, `requested`, `merged`, `failed`, `dry_run`, `cancelled`.
- `split_pdf(path, output_dir, dry_run=False, progress_callback=None, cancel_token=None) -> dict` — splits PDF into single-page files (`{basename}_page_{N}.pdf`). Returns report dict.
- `convert_image(path, target_format, resize_pct=100, dry_run=False) -> dict` — converts images using Pillow. Handles RGBA→RGB for JPEG (white background). Resizes with Lanczos resampling. JPEG quality: 90. Returns report dict.
- Internal report builders: `_merge_report`, `_split_report`, `_convert_report`.

#### `dataforge/core/utils.py`

General helper functions.

- `format_size(size_bytes) -> str` — reads config `size_unit` (Auto/Bytes/KB/MB/GB).
- `parse_extensions(ext_str) -> list` — normalizes comma-separated input to dot-prefixed lowercase extensions.
- `check_disk_space(dest_folder, required_bytes) -> tuple[bool, str]` — uses `shutil.disk_usage`.
- `safe_zip_write(zf, source_path, arcname, existing_names) -> str` — appends `_N` suffix on collision, mutates `existing_names` set.

### `dataforge/core/operations/`

#### `dataforge/core/operations/__init__.py`

Re-exports: `apply_result_to_entry`, `delete_path`, `format_operation_message`, `rename_path`, `rename_with_regex`, `resolve_collision_path`, `render_template_name`, `transfer_path`.

#### `dataforge/core/operations/files.py`

Shared neutral file-mutation layer. This is the single authoritative location for filesystem mutation rules.

Data:

- `OperationResult` dataclass — fields: `action`, `source_path`, `destination_path` (optional), `success`, `message`, `dry_run`.

Functions:

- `resolve_collision_path(destination_path, reserved_paths=None, current_path=None) -> str` — appends `_{N}` suffixes to avoid overwriting. Accepts optional `reserved_paths` set to prevent batch collisions and `current_path` to skip self-collision.
- `transfer_path(source_path, destination_dir, action, dry_run=True, reserved_paths=None) -> OperationResult` — handles move/copy with collision resolution via `shutil.move`/`shutil.copy2`.
- `delete_path(source_path, dry_run=True, safe_mode=True) -> OperationResult` — uses `send2trash` if `safe_mode`, else `os.remove`.
- `rename_path(source_path, new_name, dry_run=True, reserved_paths=None) -> Optional[OperationResult]` — returns `None` if name unchanged. Raises `ValueError` for empty names.
- `rename_with_regex(source_path, pattern, replacement, dry_run=True, reserved_paths=None) -> Optional[OperationResult]` — applies `re.sub(pattern, replacement, basename)` and delegates to `rename_path`; returns `None` when the name is unchanged.
- `render_template_name(template, entry, counter) -> str` — supports `{name}`, `{ext}`, `{date}`, `{size}`, `{counter}` placeholders via `string.Formatter` (literal tokens in the original name are left intact); deterministically reattaches the original extension when the template lacks `{ext}`.
- `apply_result_to_entry(entry, result)` — updates a `FileEntry` to reflect operation outcome (re-stats file).
- `format_operation_message(result) -> str` — returns `result.message`.

### `dataforge/core/services/`

#### `dataforge/core/services/__init__.py`

Re-exports: `BatchActionOutcome`, `BatchActionRecord`, `FileActionService`.

#### `dataforge/core/services/file_actions.py`

Central batch operations layer above `core/operations/files.py`. This is the primary dispatch layer used by modules, views, widgets, and action steps.

Data:

- `BatchActionRecord` dataclass — fields: `item`, `source_path`, `message`, `result` (optional `OperationResult`), `success`, `skipped`.
- `BatchActionOutcome` dataclass — fields: `action`, `records`, `cancelled`. Properties: `successes`, `failures`, `skipped_records`, `requested`.

`FileActionService` class methods:

| Method | Purpose |
|--------|---------|
| `transfer_items(items, destination_dir, action, *, dry_run, progress_callback, cancel_token, path_getter, destination_getter)` | Batch move/copy with per-item destination support |
| `delete_items(items, *, dry_run, safe_mode, progress_callback, cancel_token, path_getter)` | Batch delete (trash or permanent) |
| `rename_items(items, name_getter, *, dry_run, progress_callback, cancel_token, path_getter)` | Batch rename with custom name function |
| `rename_items_with_regex(items, pattern, replacement, *, dry_run, ...)` | Batch regex rename |
| `rename_items_with_template(items, template, *, counter_start=1, dry_run, ...)` | Batch template rename using `render_template_name` |
| `rename_items_with_parts(items, *, find_text, replace_text, prefix, suffix, dry_run, ...)` | Batch find/replace + prefix/suffix rename |
| `archive_items(items, *, mode, destination, compression, dry_run, ...)` | Zip creation (single archive or per-file) |

Static utilities:

- `_run_batch_operation(items, *, action, progress_message, operation, cancel_token, progress_callback, path_getter)` — generic batch runner with cancel/progress support.
- `_log_record(record)` — logs record status.
- `records_for_output(outcome, include_skipped=True)` — filters records for display.
- `apply_successes_to_entries(outcome)` — applies `OperationResult` to `FileEntry` items.
- `messages(outcome, include_skipped=True)` — extracts message strings.
- `log_outcome(outcome, action_label, log_func, include_skipped=True)` — calls log function per record.

### `dataforge/core/actions/`

This package implements a composable workflow engine used by the GUI Action Builder.

#### `dataforge/core/actions/__init__.py`

Package marker only (comment: `# Actions Package`).

#### `dataforge/core/actions/base.py`

Base execution context and step abstraction.

- `ActionContext` — holds the current file list, result log (tuples of path/action/status/original_path), dry-run flag, logger callback, progress callback, cancel token, and shared `variables` dict. Methods: `log`, `progress`, `should_cancel`.
- `ActionStep` (ABC) — base class with `id` (unique), `params` dict, `name` property, `description` property. Abstract: `execute(context)`. Optional: `render_ui(parent)`, `get_summary()`.

#### `dataforge/core/actions/filters.py`

Filter steps that reduce `context.files`.

- `FilterStep` — base class (extends `ActionStep`).
- `SearchFilter` — filters by filename regex or glob pattern. Uses `fnmatch`/`re`.
- `SizeFilter` — filters by min/max MB thresholds.
- `DateFilter` — filters by age in days. Uses `build_search_query` from `modules.search` to construct date-based matching.
- `ImagePropFilter` — filters images by minimum width/height dimensions using Pillow.

Each filter logs excluded files to `context.results`.

#### `dataforge/core/actions/io.py`

Pipeline steps for filesystem side effects. All delegate to `FileActionService`.

- `IOStep` — base class with `browse_dest` helper and `_execute_transfer` method (validates destination, checks disk space, calls `FileActionService.transfer_items`).
- `TransferStep(IOStep)` — base for move/copy with `transfer_action` class variable.
- `MoveStep(TransferStep)` — `transfer_action = "move"`.
- `CopyStep(TransferStep)` — `transfer_action = "copy"`.
- `DeleteStep` — calls `FileActionService.delete_items`, clears `context.files`.
- `ZipStep` — calls `FileActionService.archive_items` with mode (`single`/`individual`) and compression.

#### `dataforge/core/actions/media.py`

Pipeline image-conversion step.

- `ConvertImageStep` — converts supported image files to target format (PNG/JPEG/WEBP/BMP/ICO) with optional resize. Calls `core.media_ops.convert_image`. Updates `FileEntry` path/filename/extension after conversion.

#### `dataforge/core/actions/modifications.py`

Pipeline rename and metadata-cleaning steps. Delegate to `FileActionService` and `MetadataCleaner`.

- `RenameStep` — calls `FileActionService.rename_items_with_template` with pattern and counter_start. Supports `{name}`, `{ext}`, `{date}`, `{size}`, `{counter}` placeholders.
- `MetaCleanStep` — iterates files and calls `MetadataCleaner.remove_metadata` for each (skipped in dry-run).

### `dataforge/modules/`

This package contains higher-level features that power the CLI and parts of the GUI.

#### `dataforge/modules/__init__.py`

Package marker only. Empty file.

#### `dataforge/modules/duplicates.py`

Duplicate-file detection engine with helpers for grouping, sorting, keep-strategy selection, and export serialization.

Constants:

- `KEEP_STRATEGIES = ("first path", "newest", "oldest", "largest", "smallest")`

Core function:

- `find_duplicates(path, recursive=True, max_depth=-1, progress_callback=None, cancel_token=None) -> Dict[str, List[FileEntry]]` — scans files, groups by size, hashes candidates (parallel via `ThreadPoolExecutor`), returns dict of hash → file list for groups with > 1 file. Uses cache database to avoid rehashing.

Helper functions:

- `build_duplicate_records(duplicates) -> list[dict]` — flattens hash groups into records with `hash`, `group_size`, `entry` fields.
- `order_duplicate_records(records, sort_key=None, reverse=False, limit=None) -> list[dict]` — sorts by group/ext/path/name/size/created/modified with optional reverse and limit.
- `choose_duplicate_keeper(entries, strategy) -> FileEntry` — selects which file to keep based on strategy (newest, oldest, largest, smallest, first path). Secondary sort by `path.lower()`.
- `select_duplicate_records(records, keep_strategy="first path") -> list[dict]` — returns non-keeper records for action.
- `serialize_duplicate_record(record) -> dict` — wraps `serialize_file_entry` with `record_type="duplicate_entry"`, `duplicate_hash`, `duplicate_group_size`.
- `serialize_duplicate_group_summary(hash_value, records) -> dict` — returns `record_type="duplicate_group_summary"` with hash, group_size, total_size.
- `build_duplicate_export_rows(records, include_group_summary=True) -> list[dict]` — groups records by hash, returns list with optional group summaries + serialized entries.
- `_hash_worker(path, size, mtime, algo, cancel_token)` — parallel worker returning `(path, hash_result)`.

#### `dataforge/modules/search.py`

Search query object, search engine, and shared serialization/export/ordering utilities used by CLI, SearchView, and DuplicatesView.

Classes:

- `SearchQuery` — encapsulates search criteria with chainable setters:
  - `set_name_pattern(pattern_obj)` — regex or string pattern
  - `set_extensions(exts)` — list or comma-separated string
  - `set_content(text, is_regex=False, case_sensitive=False)` — content search
  - `set_size_range(min_bytes=None, max_bytes=None)`
  - `set_modified_date(after=None, before=None)` — datetime objects
  - `matches(entry) -> bool` — checks all criteria
  - `_check_content(path) -> bool` — reads file up to 10 MB, searches for content pattern

Factory function:

- `build_search_query(*, name_pattern, use_regex, extensions, content_text, content_is_regex, case_sensitive, min_size_bytes, max_size_bytes, newer_than_days, older_than_days) -> SearchQuery` — canonical factory for constructing queries.

Search functions:

- `iter_search_files(root_path, query, recursive=True, max_depth=-1, progress_callback=None, cancel_token=None)` — generator yielding matching `FileEntry` objects. Raises `InterruptedError` if cancelled.
- `search_files(root_path, query, recursive=True, max_depth=-1, progress_callback=None, cancel_token=None) -> List[FileEntry]` — returns list from `iter_search_files`. Reports progress every 50 entries.

Ordering and export:

- `order_search_results(results, sort_key=None, reverse=False, limit=None) -> list[FileEntry]` — sorts by ext/path/name/size/created/modified, applies reverse and limit.
- `serialize_file_entry(entry, **extra_fields) -> dict` — returns dict with path, filename, extension, size, created_at, modified_at, is_dir, plus extra fields.
- `export_result_rows(rows, destination_path, format="csv") -> str` — exports dicts to CSV or JSON.
- `export_search_results(results, destination_path, format="csv") -> str` — wrapper calling `export_result_rows` with serialized entries.

Internal:

- `_glob_to_regex(pattern) -> str` — converts fnmatch patterns to regex.

#### `dataforge/modules/organizer.py`

Search-driven move/copy/delete operations. Static utility class.

- `Organizer.organize_files(root_path, query, action, dest_folder, dry_run=True) -> List[str]` — searches files, calls `FileActionService.transfer_items`. Returns messages.
- `Organizer.delete_files(files, dry_run=True) -> List[str]` — calls `FileActionService.delete_items`. Returns messages.

#### `dataforge/modules/renamer.py`

Regex-based batch renamer.

- `bulk_rename(path, pattern, replacement, recursive=False, dry_run=True) -> List[str]` — scans directory, calls `FileActionService.rename_items_with_regex`. Returns messages.

#### `dataforge/modules/cleaner.py`

Metadata inspection/removal and empty-folder cleanup.

Functions:

- `remove_empty_folders(path, dry_run=True) -> list[str]` — walks directory bottom-up, removes empty folders (skips root). Returns log messages.

Classes:

- `MetadataCleaner` — static utility:
  - `get_metadata_info(path) -> tuple[bool, int, str]` — analyzes images (JPG/JPEG/PNG/WEBP/BMP/TIFF) for EXIF via Pillow, PDFs via `pypdf`. Returns `(has_metadata, size_or_count, description)`.
  - `remove_metadata(path, dry_run=False) -> bool` — strips metadata. For images: saves to new Image with empty EXIF. For PDFs: copies pages to new PdfWriter, clears metadata. Uses temp file + `os.replace` for atomicity.

#### `dataforge/modules/integrity.py`

Snapshot-based file integrity tracking.

- `IntegrityMonitor` — static methods:
  - `create_snapshot(path, output_file, progress_callback=None, cancel_token=None) -> dict` — scans files, hashes with the configured algorithm (default `sha256`), and writes a self-describing JSON snapshot `{"algorithm", "created_at", "files": {rel: hash}}`. Returns report dict with `message`, `output`, `algorithm`, `saved`, `scanned`, `skipped`.
  - `verify_snapshot(path, snapshot_file) -> dict` — loads the snapshot (catching `OSError`/`JSONDecodeError`), reads its stored algorithm (falling back to MD5 for legacy flat snapshots), and compares current state. Detects NEW, MODIFIED, DELETED, ERROR. Returns report dict with `discrepancies`, `stats`, `snapshot_entries`, `current_entries`, `issue_count`, `is_clean`.

Internal helpers: `_snapshot_key`, `_empty_verification_stats`, `_build_verification_report`, `_resolve_algorithm`, `_unwrap_snapshot`.

#### `dataforge/modules/usage.py`

Disk-usage summarization.

- `analyze_size(path) -> dict` — scans directory, aggregates file sizes by immediate containing folder. Returns dict: folder → total_bytes.
- `generate_usage_report(data, limit=20) -> list[str]` — ASCII bar chart of top N folders by size.

#### `dataforge/modules/reporting.py`

Export formats for duplicate scan results.

- `ReportGenerator` — static methods:
  - `duplicates_to_csv(duplicates, output_file)` — exports via `pandas.DataFrame` with columns: hash, path, size_bytes, filename, extension.
  - `duplicates_to_json(duplicates, output_file)` — nested dict: hash → [{path, size, filename}].
  - `duplicates_to_txt(duplicates, output_file)` — text format with hash headers and bulleted file paths.

### `dataforge/ui/`

This package contains the desktop application shell, views, widgets, and plugin loader.

#### `dataforge/ui/app.py`

Main GUI controller and shell.

Constants:

- `HEADER_COLORS` — light/dark color maps for sidebar group header labels (Overview, File Utilities, System Maintenance, Advanced Analysis, Application, Plugins).
- `LIGHT_STYLE`, `DARK_STYLE` — full Qt stylesheets (now generated from `ui/theme_tokens.py::generate_qss()`; the old hand-written blocks have been replaced by a single token-driven template).

Types:

- `BackgroundWorker(QThread)` — runs a target callable off the UI thread; emits `progress_signal`, `status_signal`, `result_signal`, `error_signal` (Qt signals, not a `queue.Queue`).
- Protocol type hints: `ProgressCallback`, `SuccessCallback`, `ErrorCallback`, `BackgroundTarget`.

Class `DataForgeApp(QMainWindow)`:

Layout:

- Root window: `resize(1100, 750)`, `setMinimumSize(700, 450)`.
- `QHBoxLayout` central layout — fixed-width nav `QFrame` (`setFixedWidth(230)`, non-collapsible) + `QStackedWidget` content area (stretch factor 1).
- Nav frame: title label, dark-mode `QCheckBox`, separator, then a scrollable (`QScrollArea`) list of collapsible group headers (Overview, File Utilities, System Maintenance, Advanced Analysis, Application, and Plugins when present) each containing plain-text `QPushButton`s (no icons).
- Status bar: cancel button, spinner label, progress bar, status label.

Key methods:

- `add_view(view_cls)` — instantiates and registers a view by title.
- `build_navigation_sidebar()` — (re)builds the grouped nav buttons; persists per-group collapsed state via `config.get/set("collapsed_groups", ...)`.
- `toggle_sidebar_group(group_name, header_button)` — expands/collapses one nav group (the sidebar itself is fixed-width and does not collapse).
- `switch_view(title)` — unmounts current view, shows new one via `QStackedWidget`, highlights the matching nav button (`setChecked`).
- `update_status(message)` / `update_progress(current, total, step_name)` — update status bar text and progress bar.
- `cancel_action()` — sets `cancel_event` so a running `BackgroundWorker` can stop cooperatively.
- `run_workflow(target, on_success, *args, on_error, progress, error_title)` — inspects the target's signature for `progress_callback`/`cancel_token` params and injects them, then delegates to `run_background`.
- `run_background(target, callback, *args, on_error, show_progress, **extra_kwargs)` — creates and starts a `BackgroundWorker(QThread)`, wiring its signals to UI update slots and the success/error callbacks.
- `run_in_thread()` — thin compatibility wrapper around `run_background`.
- `post_to_main(callback, *args, **kwargs)` — marshals a callback onto the UI thread via the `post_signal` Qt signal (not a queue).
- `post_progress(current, total, step_name)` / `post_status(message)` — safe to call from a `BackgroundWorker` thread; emit the worker's Qt signals when called off-thread, or update the UI directly when called on the UI thread.
- `toggle_theme()` — switches between the light/dark stylesheets (generated from `ui/theme_tokens.py`) and persists `"cosmo"`/`"darkly"` as the saved theme name.
- `show_error_dialog`, `show_warning_dialog`, `show_info_dialog`, `show_workflow_error` — `QMessageBox`-based dialog helpers.
- `make_progress_callback() -> ProgressCallback` — returns `self.post_progress` for injection into worker targets.
- `show_current_help()` — delegates to the current view's `show_help()`.

Plugin loading:

- `PluginLoader` scans `dataforge/ui/plugins` for `.py` files.
- Imports as `dataforge.ui.plugins.<module>` so relative imports resolve correctly.

#### `dataforge/ui/plugin_loader.py`

Dynamic loader for GUI view plugins.

- `PluginLoader(plugin_dir)` — `load_plugins() -> List[Type[BaseView]]`. Scans for `.py` files, imports dynamically, collects `BaseView` subclasses. Skips `__init__.py`. Handles import errors gracefully.

#### `dataforge/ui/widgets.py`

Shared custom GUI widgets.

Classes:

- `HoverTooltip(widget, text)` — floating label appearing on Enter, hidden on Leave/Click.
- `attach_tooltips(widget_text_pairs) -> list[HoverTooltip]` — batch tooltip creation. Used by SearchView, DuplicatesView, ToolsView, ActionBuilderView, MediaView, SettingsView.

- `CollapsibleCard(master, title, expanded=True)` — card frame with toggle-able body (▼/▶ unicode). Methods: `toggle()`, `get_body()`, `add_widget_to_header(widget_cls, **kwargs)`.

- `EnhancedTreeview(master, columns, app=None, on_file_action=None)` — wraps `Treeview` + scrollbars. Features:
  - Column-sorting by click header (numeric then text fallback).
  - Context menu: Open File, Open Location, Rename, Move To, Copy To, Delete, Exclude Extension, Copy Path, Copy Name.
  - Rename uses a custom dialog with pre-filled name and validation.
  - File operations delegate to `FileActionService` or `on_file_action` callback.
  - Proxy methods: `heading`, `column`, `insert`, `delete`, `get_children`, `set`, `item`, `selection`, `selection_set`, `focus`, `see`, `move`, `identify_row`, `bind`, `unbind`.

- `FilePreviewPanel(master)` — two-section frame (Info + Content). `update_file(path)` shows:
  - Images: Pillow thumbnail via `ImageTk`.
  - Text files: `tk.Text` widget with scrollbars, 4 KB limit.
  - Other files: "No Preview Available".

#### `dataforge/ui/views/base.py`

Abstract base class for all GUI views.

- `BaseView(QWidget, metaclass=QWidgetABCMeta)` — lifecycle: `mount()`, `unmount()`. Abstract: `get_title()`.

Help system:

- `get_help_text() -> str` — default "No help available".
- `show_help()` — Toplevel window with formatted text (bold/header tags).

Shared static/instance helpers:

- `build_preview_message(summary, lines, action_label, limit=8)` — formatted preview text with truncated planned changes.
- `confirm_preview(title, summary, lines, action_label, limit)` — `messagebox.askyesno` using built preview message.
- `handle_preview_outcome(cancelled, records, title, summary, lines, ...)` — centralized preview-stage branching: cancelled, empty, or confirm-declined all return `False`; proceeding returns `True`.
- `present_batch_outcome(outcome, ...)` — centralized result dialog: cancelled, partial (failures), or full success.
- `summarize_completion(action_label, attempted, succeeded, failed, skipped, created)` — formatted summary string.
- `batch_outcome_counts(outcome) -> tuple` — `(total, successes, failures)`.
- `batch_failure_details(records, limit=8) -> str` — joined error messages.
- `validate_regex_pattern(pattern)` — try compile, raise `ValueError` on error.
- `validate_filename_candidate(name)` — checks empty, invalid chars, "." or "..".
- `restore_tree_selection(tree, item_ids, on_select)` — set selection, focus, see.
- `choose_file_or_directory(file_title, directory_title, filetypes)` — Yes=file, No=folder chooser.

#### `dataforge/ui/views/dashboard.py`

Overview screen with comprehensive system, disk, file, and configuration information.

- `DashboardView(BaseView)` — title: "Dashboard".

Layout (4 rows inside a `QScrollArea`, each row a `QHBoxLayout` of `QGroupBox` cards):

- **Row 1**: Disk Usage (`QProgressBar` with color-coded stylesheet by usage %) + System Info (OS, Machine, Home, Python version, Config dir).
- **Row 2**: File Distribution (top extensions) + Quick Stats — populated asynchronously after a background scan.
- **Row 3**: Storage by Category (Documents/Images/Videos/Audio/Archives/Code/Other) + Largest Files.
- **Row 4**: Configuration Summary (theme, safe mode, hash algo, max threads, size unit, excluded extensions/dirs — 4-row/2-column grid).

Key internals:

- `CATEGORY_MAP` — dict mapping category names to file extension sets.
- `CATEGORY_COLORS` — dict mapping categories to hex color strings used for the storage-by-category bars.
- `_categorize_ext(ext)` — looks up `CATEGORY_MAP`, defaulting to `"Other"`.
- `_scan_comprehensive(paths)` — runs off the UI thread via `self.app.run_background`; counts extensions, tracks category sizes, finds largest files.
- `mount()` triggers `refresh_stats()`, so data refreshes every time the view is selected.

#### `dataforge/ui/views/search.py`

Search and bulk-action view. Title: "Search & Organize".

- `SearchView(BaseView)` — builds `SearchQuery` from form state, displays results in `EnhancedTreeview`, supports bulk actions.

Search features:

- Path (file or folder), name pattern (glob/regex), extensions, depth, size range, date range.
- Sort/reverse/limit slice controls with tooltips (`SLICE_TOOLTIPS`).
- Content search.
- One-click Reset Slice control.
- Slice summary label showing active sort/reverse/limit/visible-count state.

Bulk actions (all follow preview → confirm → execute pattern via `FileActionService`):

- Move selected, Copy selected, Delete selected.
- Regex rename (find/replace).
- Archive (zip selected or all, single/individual mode).
- Export results (CSV/JSON via `export_search_results`).

Workflow methods:

- `start_search()` → `_run_search_worker` → `on_search_complete`.
- `organize(action)` → `_preview_organize_worker` (dry_run) → `_on_preview_organize_complete` → `_execute_organize_worker` → `_on_execute_organize_complete`.
- `bulk_rename()` → `_preview_rename_worker` → `_on_preview_rename_complete` → `_execute_rename_worker` → `_on_execute_rename_complete`.
- `archive_files(mode)` → `_preview_zip_worker` → `_on_preview_zip_complete` → `_zip_worker` → `_on_zip_complete`.

Uses `handle_preview_outcome` and `present_batch_outcome` from `BaseView` for consistent UX.

#### `dataforge/ui/views/duplicates.py`

Duplicate finder with grouped display, keep-strategy actions, and export. Title: "Duplicate Finder".

- `DuplicatesView(BaseView)` — wraps `modules.duplicates.find_duplicates` with rich GUI.

Features:

- Scan configuration: path, depth, hash algorithm, sort/reverse/limit.
- Results displayed under collapsible per-hash group headers.
- Expand All / Collapse All controls.
- Preserves expanded group state across sort/reverse/limit refreshes.
- Keep-strategy selection from `KEEP_STRATEGIES`.
- Select Extras / Clear Selection buttons.

One-click keep-and-act flows:

- Keep Newest + Delete Rest
- Keep Oldest + Delete Rest
- Keep Largest + Move Rest
- Keep Smallest + Move Rest
- Manual move/copy/delete of selected items.

Export:

- CSV/JSON via `build_duplicate_export_rows` → `export_result_rows`.
- Flat Export toggle (omits `duplicate_group_summary` rows).

Attributes: `current_results`, `visible_records`, `item_records`, `group_items`, `expanded_group_hashes`.

Internal methods: `_refresh_visible_results`, `_rebuild_tree`, `_capture_expanded_group_state`, `_set_tree_selection`, `_drop_processed_entries`, `select_extras`, `run_keep_action`.

#### `dataforge/ui/views/action_builder.py`

GUI workflow designer for chained action steps. Title: "Action Builder".

- `ActionBuilderView(BaseView)` — lets users add filter/action steps, builds `ActionStep` chains, executes against scanned files.

Step library buttons:

- Filters: Name (`SearchFilter`), Size (`SizeFilter`), Date (`DateFilter`), Image Properties (`ImagePropFilter`).
- Actions: Rename (`RenameStep`), Move (`MoveStep`), Copy (`CopyStep`), Zip (`ZipStep`).
- Misc: Convert (`ConvertImageStep`), Clean (`MetaCleanStep`), Delete (`DeleteStep`).

UI:

- Configuration card: path, recursive toggle, depth spinbox.
- Two-pane: Left = Workflow Steps (reorderable cards with collapse/expand), Right = Pipeline Log (tree).
- Execution: Preview Pipeline (dry_run=True) and Execute Pipeline (dry_run=False) buttons.

Pipeline execution:

- `run_pipeline(dry_run)` → `_execute_pipeline_thread` — scans source, creates `ActionContext`, executes each step in sequence.
- Results logged as tuples in the pipeline log tree.

#### `dataforge/ui/views/tools.py`

Multi-tool notebook with four tabs. Title: "Tools & Workflows".

- `ToolsView(BaseView)` — `QTabWidget` with `TOOLTIP_TEXTS` for all controls.

**Tab 1: Integrity Monitor**
- Create Snapshot: path, output file, Create button → `IntegrityMonitor.create_snapshot`.
- Verify Integrity: target path, snapshot file, Verify button → `IntegrityMonitor.verify_snapshot`.
- Summary labels.

**Tab 2: Metadata Cleaner**
- Scan: path, extensions, max depth → `build_search_query` + `search_files` → `MetadataCleaner.get_metadata_info` per file.
- Tree display (path, size, has_meta, info) + preview panel.
- Clean Selected / Clean All → `MetadataCleaner.remove_metadata`.

**Tab 3: Batch Renamer**
- Config card: find, replace, prefix, suffix fields.
- Tree (old name, new name, status).
- Preview and Apply buttons → `FileActionService.rename_items_with_parts`.
- Add Files, Clear buttons.

**Tab 4: Folder Sync**
- Source and destination paths, Analyze and Sync Now buttons.
- Compares source/destination directory trees.
- Copy via `FileActionService.transfer_items` with per-item `destination_getter` for nested paths.
- Tree display (relative path, action).

Tooltip initialization: `_init_integrity_tooltips()`, `_init_metadata_cleaner_tooltips()`, `_init_batch_renamer_tooltips()`, `_init_folder_sync_tooltips()`.

#### `dataforge/ui/views/settings.py`

GUI editor for persisted configuration. Title: "Settings".

- `SettingsView(BaseView)` — `QTabWidget` with 4 tabs and `TOOLTIP_TEXTS`.

**Tab 1: General** — theme dropdown (bound to live theme change), safe mode checkbox, log level combobox.

**Tab 2: Performance** — hash algorithm combobox, size unit combobox, max threads spinbox. Save Performance button. Clear Cache DB button (confirms before clearing `file_cache`).

**Tab 3: Exclusions** — comma-separated excluded folders and extensions text entries. Save Exclusions button.

**Tab 4: Dashboard** — listbox of dashboard scan paths with Add Folder / Remove Selected / Save Dashboard controls.

#### `dataforge/ui/views/media.py`

Media batch tools for PDF and image operations. Title: "Media Tools".

- `MediaView(BaseView)` — `QTabWidget` with 2 tabs and `TOOLTIP_TEXTS`.

**Tab 1: PDF Tools**
- Merge section: Add PDFs, Clear, Move Up/Down, Merge Into One. Tree display (path, size). Preview → confirm → execute via `media_ops.merge_pdfs`.
- Split section: file input, Browse, Split Into Pages. Preview → confirm → execute via `media_ops.split_pdf`.

**Tab 2: Image Batch**
- Toolbar: Add Images, Clear.
- Options: format dropdown (PNG/JPEG/WEBP/BMP/ICO), resize % slider (10-200), Convert All button.
- Tree (path, size, status) + preview panel.
- Preview → confirm → execute via `media_ops.convert_image` per image.
- Updates tree rows with completion status via queued UI callbacks.

### GUI Plugin Files

#### `dataforge/ui/plugins/__init__.py`

Package marker only (comment: `# GUI plugins package.`).

#### `dataforge/ui/plugins/cleaner_plugin.py`

Standalone metadata-cleaner view as a plugin. Title: "Metadata Cleaner".

- `MetadataCleanerPlugin(BaseView)` — searches files by extension, analyzes metadata via `MetadataCleaner.get_metadata_info`, allows cleaning selected or all listed files via `MetadataCleaner.remove_metadata`.
- Two-step UI: Step 1 = path/depth/extensions/scan, Step 2 = results tree + clean buttons.
- Loadable through `PluginLoader` when GUI scans `dataforge/ui/plugins`.

### Tests

#### `tests/verify_scenarios.py`

End-to-end verification script using `unittest` and a temporary local test directory. Scenarios: duplicates, search, cleaner, renamer, integrity.

#### `tests/test_contract_regressions.py`

Contract regression tests ensuring public interfaces remain stable:

- CLI smoke import, browse helper API
- CLI search: `--name-glob`, `--name-regex`, mutually exclusive name modes (text and JSON errors), content + max-depth, date filters, JSON/JSONL output, sort/limit, extension sort, reverse sort, count-only with limit
- CLI dupes: sort/limit/jsonl, export to JSON, flat export, count-only
- Search view worker: sort/reverse/limit
- File action service: rename-with-parts, batch outcome helpers
- Plugin discovery

#### `tests/test_integration.py`

Integration and cross-layer tests:

- `TestActionPipelineEndToEnd` — filter → rename, filter → move, filter → copy → delete, dry-run, cancel, collision, error recovery, single-file source.
- `TestPluginPackagingPaths` — build_exe plugin path matches loader, spec file path matches, plugin directory is a package, loader uses full package name.
- `TestSharedOperationsLayer` — collision with reserved paths, invalid action raises, same-name rename returns None, dry-run delete preserves file.
- `TestSearchOperationsIntegration` — search then move results, size filter accuracy.

#### `tests/test_comprehensive.py`

This module now imports and passes — `rename_with_regex` was restored in `dataforge/core/operations/files.py`. The whole suite collects and runs green (254 tests). The coverage list below is accurate. See [`docs/reviews/NOTES_REVIEW.md`](./reviews/NOTES_REVIEW.md) for verification details.

Comprehensive unit and functional test suite covering every layer:

- `FileEntry` (datetime properties, hash defaults)
- `format_size` (all unit modes, auto scaling)
- `parse_extensions` (empty, dotted, undotted, mixed case, None)
- `check_disk_space`, `safe_zip_write`
- `get_file_hash` / `get_hashes` (md5, sha1, sha256, cancel, missing, unsupported)
- `scan_directory` (recursive, non-recursive, max_depth 0/1, cancel, inaccessible, field population, single file)
- `CacheManager` (set/get/clear/update)
- `ConfigManager` (defaults, missing key, fallback)
- `SearchQuery` (all criteria), `build_search_query`
- `search_files` (basic, depth, cancel)
- Shared operations (collision, transfer, delete, rename, regex rename, template render, apply_result, format_message)
- `ActionContext`, action filters (`SearchFilter`, `SizeFilter`, `DateFilter`)
- Action IO steps (`ZipStep`, `DeleteStep` dry-run)
- `MetaCleanStep`, `ConvertImageStep`
- `remove_empty_folders`, `MetadataCleaner`
- `IntegrityMonitor` (create + verify, detect modification/deletion/new)
- `ReportGenerator` (CSV, JSON, TXT)
- `analyze_size`, `generate_usage_report`
- `bulk_rename`, `Organizer`, `find_duplicates`
- `PluginLoader`

## Structural Truths and Risks

These are concrete structural facts about the codebase, not opinions.

The structural facts below are still accurate. Most *defects* from the 2026-07-10 review are now **fixed**; still-open *security risks* are tracked in [`docs/reviews/NOTES_REVIEW.md`](./reviews/NOTES_REVIEW.md) with severities and line-level evidence.

### File mutation is centralized through two layers

All filesystem mutations now flow through `FileActionService` → `core/operations/files.py`:

- `modules/organizer.py` calls `FileActionService.transfer_items` / `delete_items`
- `modules/renamer.py` calls `FileActionService.rename_items_with_regex`
- `core/actions/io.py` calls `FileActionService.transfer_items` / `delete_items` / `archive_items`
- `core/actions/modifications.py` calls `FileActionService.rename_items_with_template`
- `ui/views/search.py` calls `FileActionService` for all bulk operations
- `ui/views/duplicates.py` calls `FileActionService` for move/copy/delete
- `ui/views/tools.py` calls `FileActionService` for batch rename and folder sync
- `ui/widgets.py` calls `FileActionService` for context-menu operations

This is a significant architectural improvement: mutation rules (collision handling, dry-run, safe delete) are defined once.

### Business capabilities still have multiple calling patterns

While mutations are centralized, the **orchestration** still differs across callers:

| Capability | Module path | Action pipeline path | GUI-direct path |
|---|---|---|---|
| Rename | `modules/renamer.py` → `FileActionService` | `RenameStep` → `FileActionService` | ToolsView batch renamer → `FileActionService` |
| Move/Copy | `modules/organizer.py` → `FileActionService` | `MoveStep`/`CopyStep` → `FileActionService` | SearchView organize → `FileActionService` |
| Delete | `modules/organizer.py` → `FileActionService` | `DeleteStep` → `FileActionService` | SearchView/DuplicatesView → `FileActionService` |
| Search/filter | `modules/search.py` | `SearchFilter`/`SizeFilter`/`DateFilter` (independent) | SearchView (uses modules) |
| Metadata clean | `modules/cleaner.py` | `MetaCleanStep` (uses modules) | ToolsView/CleanerPlugin (uses modules) |

The pipeline filters (`SearchFilter`, `SizeFilter`, `DateFilter`) are independent implementations, not wrappers over `SearchQuery`. This is a remaining structural overlap.

### GUI threading is consistent

All views use `app.run_workflow()` which auto-injects `progress_callback` and `cancel_token`, ensuring consistent threading, progress reporting, and cancellation across the application.

### Preview → Confirm → Execute is the standard GUI pattern

All GUI bulk operations follow: dry-run preview → user confirmation → execute. This is orchestrated through `BaseView.handle_preview_outcome` and `BaseView.present_batch_outcome`.

### CLI and tests share the same module contracts

- `cli.py` imports directly from `modules.*` and uses the same function signatures as tests.
- `cleaner.py` exposes both `remove_empty_folders` and `MetadataCleaner`.
- Both CLI and GUI share `build_search_query` for query construction.

### Plugin discovery is aligned

- `DataForgeApp` loads from `dataforge/ui/plugins`
- `PluginLoader` imports as `dataforge.ui.plugins.<module>`
- Build scripts bundle the correct path
- Covered by regression tests

### 10. Design tokens are the single source of truth for colour

`dataforge/ui/theme_tokens.py` (added Phase 2b — 2026-07-11) — semantic colour tokens with validated AA contrast, a template-driven `generate_qss(mode)` function that replaces the two ~200-line hand-written `LIGHT_STYLE`/`DARK_STYLE` blocks in `app.py`, `generate_palette(mode)` for `QPalette`, `TYPE_SCALE` named font-size constants, and SVG glyph helpers for checkbox/spinbox/combobox indicators. All per-widget hardcoded hex colours across the views have been migrated to Qt dynamic-property variant rules (`setProperty("variant", "danger")` etc.) driven by the token module.

### `LocalProvider` is unused infrastructure

`core/provider.py` defines `FileProvider` (ABC) and `LocalProvider`, but these are not used by any active code path. All code uses `os`, `shutil`, `scan_directory`, and `FileActionService` directly.

## Practical Mental Model for Maintainers

If you need to understand the system quickly, use this reading order:

1. `dataforge/core/common.py` → `FileEntry` data model
2. `dataforge/core/scanner.py` → how files are discovered
3. `dataforge/core/operations/files.py` → how files are mutated
4. `dataforge/core/services/file_actions.py` → how mutations are batched (the central dispatch)
5. `dataforge/cli.py` → CLI surface
6. `dataforge/ui/app.py` → GUI shell, threading model, event queue
7. `dataforge/ui/views/base.py` → shared GUI helpers
8. `dataforge/modules/search.py` → search engine + shared serialization/export utilities
9. `dataforge/modules/duplicates.py` → duplicate engine + keep-strategy utilities
10. `dataforge/core/actions/base.py` + `dataforge/ui/views/action_builder.py` → pipeline model

## Change Guidance

When modifying this repository, assume these rules unless you verify otherwise:

1. **Mutations go through FileActionService** — any new file operation should use `FileActionService` methods, not direct `shutil`/`os` calls.
2. **Operations go through core/operations/files.py** — `FileActionService` delegates here. New mutation types should be added at this level.
3. **Rename exists in three orchestration patterns** — modules (regex), actions (template), tools (parts). All delegate to `FileActionService`.
4. **Search/filter logic has two implementations** — `modules/search.py` (used by CLI/GUI) and `core/actions/filters.py` (independent, used by Action Builder).
5. **Config and cache are persistent** on the user's machine under `~/.dataforge/`.
6. **GUI views use preview → confirm → execute** — new views should follow the same pattern using `BaseView` helpers.
7. **GUI threading uses run_workflow** — new background work should use `app.run_workflow(target, on_success)`, not raw threading.
8. **Tooltips use attach_tooltips** — new views with help text should use `ui.widgets.attach_tooltips`.

## Summary

The current repository is best understood as:

- A usable file-management application with both CLI and desktop interfaces.
- Built on a shared `FileEntry` → `scanner` → `operations` → `FileActionService` foundation.
- With centralized filesystem mutation rules but multiple orchestration patterns (module-direct, pipeline-step, GUI-direct).
- GUI threading, preview/confirm workflows, and batch outcome reporting are standardized through `DataForgeApp` and `BaseView` helpers.
- The pipeline filters are the main remaining structural overlap with `modules/search.py`.
- `LocalProvider` is the main dead abstraction.
