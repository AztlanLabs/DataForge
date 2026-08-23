# 🔨 DataForge Architecture

*File System Management with Steroids and Superpowers*

**Last verified:** 2026-08-23 06:00 UTC *(re-verified against `dataforge/` HEAD `b373e7e`; Wave 5+6 12/12 DONE, 1213 tests — added `core/image_io`/`streams`, `modules/indicators`/`sanitisation`, `engine/parsers`, `logger` chain)*

## System Summary

**DataForge** is a local-first desktop and CLI application for inspecting, organizing, recovering, and analyzing files with enterprise-grade forensic capabilities. It has **two entrypoints** that share the exact same superpowers:

- **CLI**: `dataforge.cli`
- **GUI**: `dataforge.ui.app.DataForgeApp`

Both surfaces ultimately depend on the same lower-level modules and services, which keeps the core behavior relatively centralized even though the user experience is split between command-line and desktop flows.

## Architectural layers

| Layer | Main files | Responsibility |
| --- | --- | --- |
| Entry points | `run_ui.py`, `dataforge/cli.py`, `dataforge/service/__main__.py`, `setup.py` | Start the desktop app, expose CLI commands, run the engine daemon, package the console script |
| Core primitives | `dataforge/core/common.py`, `paths.py`, `scanner.py`, `config.py`, `cache.py`, `logger.py`, `audit.py`, `case.py` | Represent files, resolve canonical per-OS locations (platformdirs + legacy migration), scan disk state, persist settings, cache hashes, log runtime activity, hash-chained audit log, case/evidence context |
| Low-level filesystem operations | `dataforge/core/operations/files.py` | Rename, move, copy, delete, collision handling, archive creation, template naming |
| Shared service layer | `dataforge/core/services/file_actions.py` | Central batch-oriented mutation API used by features and UI views |
| Feature modules | `dataforge/modules/*.py` | Search, duplicates, organize, rename, cleaner, integrity, usage, reporting, plus the newer batch: `system_cleanup`, `performance`, `recovery`, `metadata`, `hardware`, `forensics`, `password_tools`, `device_manager`, `file_signatures` |
| Workflow engine | `dataforge/core/actions/*.py` | Action Builder context, filters, and step execution |
| GUI shell and views | `dataforge/ui/app.py`, `dataforge/ui/views/*.py`, `dataforge/ui/widgets.py` | Desktop shell (**PyQt5**), background execution, view rendering, previews, plugins |
| Design tokens / theming | `dataforge/ui/theme_tokens.py` | Single-source-of-truth colour table (WCAG AA validated), template-driven QSS/palette generation (`generate_qss`, `generate_palette`), type-scale constants, variant-QSS rules |
| Tests | `tests/*.py` | End-to-end, contract, and feature coverage (723 passing) |

## Key abstractions

### `FileEntry`

Defined in `dataforge/core/common.py`, `FileEntry` is the normalized file metadata object passed through scanning, search, duplicate detection, and many UI workflows. It is the closest thing to a shared domain model in the repository.

### `FileActionService`

Defined in `dataforge/core/services/file_actions.py`, this is the most important write-path abstraction in the application.

It centralizes batch-aware versions of:

- move/copy flows
- rename flows
- delete/trash flows
- archive/zip flows

It also returns structured outcomes (`BatchActionOutcome`, `BatchActionRecord`) that the UI can summarize consistently.

### `ActionContext` and `ActionStep`

Defined in `dataforge/core/actions/base.py`, these types power **Action Builder**. They provide a composable pipeline model where steps filter or transform the current working set of `FileEntry` records and append execution results to a shared context object.

### `AuditLog`

Defined in `dataforge/core/audit.py`, this provides an append-only, 0o600 SQLite WAL audit log with SHA-256 hash chaining (`hash(prev||canonical_json)`). It supports `append()`, `verify()` (tamper detection), `tail_hash()`, and `count()`. Used by the forensic report writer to seal chain-of-custody records.

### `CaseContext`

Defined in `dataforge/core/case.py`, this dataclass carries case metadata (`case_id`, `operator`, `host`, `source_sha256`) and an `evidence_mode` flag. When `evidence_mode=True`, `FileActionService` blocks destructive operations (transfer/delete) and `secure_delete` refuses to run. A module-level singleton provides `set_context()`, `get_context()`, `clear_context()`, and `is_evidence_mode()`.

### `BaseView`

Every GUI screen inherits from `dataforge.ui.views.base.BaseView`. The base class provides:

- a common title contract
- mount/unmount lifecycle hooks
- standardized preview/confirmation helpers
- batch-outcome presentation helpers
- shared validation utilities

### `UiEvent`

`dataforge/ui/app.py` no longer uses a `queue.Queue`-based `UiEvent` marshaling class. Background work now runs on a `BackgroundWorker(QThread)` subclass that emits Qt signals (`progress_signal`, `status_signal`, `result_signal`, `error_signal`), which `DataForgeApp.run_background()` connects directly to UI update slots (`update_progress`, `update_status`, success/error callbacks) on the Qt event loop.

## Main execution flows

### 1. Scan and inspect

Most features begin by scanning a path and turning the result into `FileEntry` objects.

Typical path:

1. user provides a file or folder path
2. `dataforge.core.scanner.scan_directory()` walks the target
3. exclusions from `ConfigManager` are applied
4. `FileEntry` records flow into modules or UI result tables

This shared scan behavior is used by search, duplicates, dashboard summaries, metadata cleaner flows, and several workflow previews.

### 2. CLI flow

The CLI in `dataforge/cli.py` is a thin orchestration layer:

1. Click parses arguments.
2. The command builds a query or options structure.
3. A module or service performs the real work.
4. CLI-specific formatting happens at the end (text, JSON, JSONL, CSV/TXT export).

The CLI is therefore mostly an adapter around `dataforge/modules/` plus some export helpers.

### 3. GUI flow

The GUI shell in `dataforge/ui/app.py` owns:

- view registration and navigation
- theme toggling
- the status/progress bar
- worker-thread lifecycle
- cancellation and result marshaling

Views should not block the Qt (PyQt5) main/UI thread. Long-running work is expected to go through:

- `app.run_workflow(...)` when the worker may support `progress_callback`
- `app.run_background(...)` for more direct background execution

`run_background()` builds a `BackgroundWorker(QThread)`, inspects the target function's signature, and automatically injects:

- `cancel_token` (a shared `threading.Event`) when the target declares it
- `progress_callback` when requested via `run_workflow(progress=True)`

Results, progress, status, and errors are marshaled back to the UI thread through Qt signals (`result_signal`, `progress_signal`, `status_signal`, `error_signal`) connected to UI slots — not through a queue-polling loop. This makes the app shell the operational contract for all long-running view logic.

### 4. File mutation flow

Many destructive or state-changing workflows converge through the same chain:

1. a CLI command or GUI view collects a selection
2. preview logic describes intended changes
3. confirmation occurs
4. `FileActionService` applies the operation
5. the caller updates summaries, tables, or exports based on the structured outcome

This matters because it keeps write behavior more consistent than the read/scan layer, even though multiple views expose similar actions.

### 5. Action Builder flow

Action Builder is a second orchestration model inside the app:

1. the user assembles filters and steps
2. an `ActionContext` is created with the current file set
3. each `ActionStep` runs in sequence
4. the context keeps the current working list plus a result log

This is important for extension because new pipeline steps fit naturally here without requiring a new top-level screen.

## Persistence and runtime state

| Artifact | Location | Purpose |
| --- | --- | --- |
| Config | `~/.dataforge/config.json` | theme, safe mode, exclusions, hash algorithm, two separate worker budgets (`max_thread_workers` for hashing/batch work, `search_thread_workers` for search/keyword scanning), size unit, path display mode, detail level (`Simple` / `Standard` / `Everything`), dashboard paths |
| Hash cache | `~/.dataforge/cache.db` | cached content hashes keyed by path, size, mtime, and algorithm |
| Log file | `~/.dataforge/app.log` | rotating application log |

The app is local-stateful: configuration and caching live in the user profile, not in the project directory.

## GUI composition

The desktop application eagerly registers these built-in views (see `DataForgeApp.__init__` in `dataforge/ui/app.py`):

- Dashboard
- Search
- Duplicate Finder
- Automations (Action Builder + Tools sub-tabs)
- Media Tools
- Clean Up Space
- Performance
- Storage & Devices
- File Recovery
- Metadata & EXIF
- Hardware Info
- Forensics
- Settings
- About & Help

It then loads plugin views from `dataforge/ui/plugins/`.

**Detail-level gating.** The sidebar groups these views into task-oriented sections (Home / Find & Organize / Clean & Optimize / Recover & Investigate / System); every group is always visible. The `settings_ui_tier` setting (now relabelled "Detail level" with values `Simple` / `Standard` / `Everything`, was `Basic` / `Advanced` / `Expert`) controls *in-view* complexity only — advanced controls stay hidden behind in-view expanders on `Simple` and `Standard`. The discoverability cliff of hiding whole groups at `Simple`/`Standard` is gone. See `ROADMAP.md` §6 Phase 2c.4 / Phase 2d for the rationale.

## Extension points

### UI plugins

`dataforge/ui/plugin_loader.py` scans `dataforge/ui/plugins/`, imports `dataforge.ui.plugins.*`, and registers `BaseView` subclasses. Opt-in via `plugins_enabled` + S5 world/owner-writable checks; optional `isolation='subprocess'` probes each import in `ProcessPoolExecutor(min(2,cpu_count()-1))` + `multiprocessing.Queue` (+ `subprocess.run` fallback) and discards worker on timeout/crash; optional `require_signed=True` verifies detached `plugin.sig` against `~/.local/share/DataForge/plugins-trusted.gpg` (`python-gnupg`) or `plugins-trusted.sha256` and raises `PluginSignatureMissingError` / `PluginSignatureInvalidError`; each outcome appends to `AuditLog` (`plugin_load` / `plugin_load_signed` / `plugin_load_unsigned_refused` / `plugin_load_failed`).

Current bundled plugin:

- `MetadataCleanerPlugin`

### New workflow steps

New Action Builder capabilities should be added in `dataforge/core/actions/` as additional `ActionStep` subclasses.

### Shared file operations

New destructive workflows should prefer the existing service and low-level file operation utilities instead of inventing a new filesystem mutation path.

### Search-based features

If a new feature starts from file discovery, it should usually build on:

- `build_search_query()`
- `iter_search_files()`
- `search_files()`

## Architectural strengths

- **Shared core logic across CLI and GUI** reduces duplicated business rules.
- **Central file action service** gives the project one main write path.
- **Background execution contract in the GUI shell** keeps long-running work off the UI thread.
- **Persistent config and hash cache** improve repeat use.
- **Plugin and pipeline models** provide two different extension strategies.

## Maintenance considerations

- The repository root contains a nested application root (`DataForge/`), so command examples and tooling must be explicit about where they run.
- `setup.py` only lists a minimal dependency set, while `requirements.txt` contains the full GUI/media/test toolchain. Treat `requirements.txt` as the authoritative development environment definition.
- Some feature overlap is intentional but real: metadata cleaning exists both inside the Automations view and as a standalone plugin view. As of TICK-204 (Wave 2), `cleaner.py::MetadataCleaner` is a thin shim delegating to `metadata.py::MetadataEngine` — the duality is resolved at the code level.
- The Action Builder filters (`dataforge/core/actions/filters.py`) are an independent implementation of the same size/date/name filtering as `dataforge/modules/search.py::SearchQuery`; the two can drift.
- `dataforge/core/provider.py` (`FileProvider`/`LocalProvider`) carries the TICK-002 seven-method contract (cancel/progress aware) but no active caller yet — engine integration pending.
- `dataforge/client/` provides `DataForge.connect()` for auto-discovering the engine daemon via UDS/Named Pipe/HTTP, with an `in_process` fallback (TICK-301).
- `dataforge/service/` ships lifecycle files for systemd (Linux), launchd (macOS), and Windows Service (TICK-302), plus `__main__.py` as the `dataforge-engine` entrypoint.
- Generated build output exists in-repo (`build/`, `dist/`), but it is not maintained source.

Correctness and security caveats from the 2026-07-10 review are tracked in [`docs/reviews/AUDIT_REPORT.md`](./reviews/AUDIT_REPORT.md) and [`AUDIT_REPORT.md`](./reviews/AUDIT_REPORT.md). Key points: the scanner no longer follows symlinks, the cache is thread-safe, integrity/dedup default to SHA-256, and the forensic-report HTML injection (S2) is fixed. S1–S13 are **fixed** as of WS-B, including trash-restore path confinement (S4, `recovery.py:205`) and System Cleanup safeguards (S7, `system_cleanup.py:267`). Forensic-soundness findings F1–F3/U2/F9 are **fixed** as of TICK-304 (hash-chained audit log, CaseContext, Evidence Mode, UTC provenance). Residual forensic work (F4/F21 `secure_delete` move, F13 parser isolation) is tracked as F4–F21 in [`FORENSIC_REVIEW.md`](./reviews/FORENSIC_REVIEW.md).

## Related documents

- [Project overview](../README.md)
- [CLI reference](./CLI_REFERENCE.md)
- [GUI workflows](./GUI_WORKFLOWS.md)
- [Development guide](./DEVELOPMENT_GUIDE.md)
- [Technical Source of Truth](./TECHNICAL_SOURCE_OF_TRUTH.md)
- [Project review (bugs, security, UX, roadmap)](./reviews/README.md)
