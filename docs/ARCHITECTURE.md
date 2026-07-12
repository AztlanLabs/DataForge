# 🔨 DataForge Architecture

*File System Management with Steroids and Superpowers*

**Last verified:** 2026-07-11

## System Summary

**DataForge** is a local-first desktop and CLI application for inspecting, organizing, recovering, and analyzing files with enterprise-grade forensic capabilities. It has **two entrypoints** that share the exact same superpowers:

- **CLI**: `dataforge.cli`
- **GUI**: `dataforge.ui.app.DataForgeApp`

Both surfaces ultimately depend on the same lower-level modules and services, which keeps the core behavior relatively centralized even though the user experience is split between command-line and desktop flows.

## Architectural layers

| Layer | Main files | Responsibility |
| --- | --- | --- |
| Entry points | `run_ui.py`, `dataforge/cli.py`, `setup.py` | Start the desktop app, expose CLI commands, package the console script |
| Core primitives | `dataforge/core/common.py`, `scanner.py`, `config.py`, `cache.py`, `logger.py` | Represent files, scan disk state, persist settings, cache hashes, log runtime activity |
| Low-level filesystem operations | `dataforge/core/operations/files.py` | Rename, move, copy, delete, collision handling, archive creation, template naming |
| Shared service layer | `dataforge/core/services/file_actions.py` | Central batch-oriented mutation API used by features and UI views |
| Feature modules | `dataforge/modules/*.py` | Search, duplicates, organize, rename, cleaner, integrity, usage, reporting, plus the newer batch: `system_cleanup`, `performance`, `recovery`, `metadata`, `hardware`, `forensics`, `password_tools`, `device_manager`, `file_signatures` |
| Workflow engine | `dataforge/core/actions/*.py` | Action Builder context, filters, and step execution |
| GUI shell and views | `dataforge/ui/app.py`, `dataforge/ui/views/*.py`, `dataforge/ui/widgets.py` | Desktop shell (**PyQt5**), background execution, view rendering, previews, plugins |
| Design tokens / theming | `dataforge/ui/theme_tokens.py` | Single-source-of-truth colour table (WCAG AA validated), template-driven QSS/palette generation (`generate_qss`, `generate_palette`), type-scale constants, variant-QSS rules |
| Tests | `tests/*.py` | End-to-end, contract, and feature coverage |

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
| Config | `~/.dataforge/config.json` | theme, safe mode, exclusions, hash algorithm, two separate worker budgets (`max_thread_workers` for hashing/batch work, `search_thread_workers` for search/keyword scanning), size unit, path display mode, experience tier, dashboard paths |
| Hash cache | `~/.dataforge/cache.db` | cached content hashes keyed by path, size, mtime, and algorithm |
| Log file | `~/.dataforge/app.log` | rotating application log |

The app is local-stateful: configuration and caching live in the user profile, not in the project directory.

## GUI composition

The desktop application eagerly registers these built-in views (see `DataForgeApp.__init__` in `dataforge/ui/app.py`):

- Dashboard
- Search & Organize
- Duplicate Finder
- Action Builder
- Tools & Workflows
- Media Tools
- System Cleanup
- Performance
- File Recovery
- Metadata Studio
- Hardware Diagnostics
- Forensics Lab
- Settings
- About & Help

It then loads plugin views from `dataforge/ui/plugins/`.

**Experience-level gating.** The sidebar groups these views and shows/hides whole groups based on the `settings_ui_tier` setting (`Basic` / `Advanced` / `Expert`). At `Basic`, the *System Maintenance* and *Advanced Analysis* groups (System Cleanup, Performance, File Recovery, Metadata Studio, Hardware Diagnostics, Forensics Lab) are hidden; `Advanced` reveals System Maintenance; `Expert` shows everything. (See `GROUP_MIN_TIER` in `ui/app.py`. The usability trade-off of hiding navigation is discussed in [`../docs/reviews/IMPROVEMENT_PLAN.md`](./reviews/IMPROVEMENT_PLAN.md).)

## Extension points

### UI plugins

`dataforge/ui/plugin_loader.py` scans Python files in `dataforge/ui/plugins/`, imports them, and registers any `BaseView` subclass it finds.

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
- Some feature overlap is intentional but real: metadata cleaning exists both inside `Tools & Workflows` and as a standalone plugin view (and in two different implementations — `dataforge/modules/cleaner.py::MetadataCleaner` vs `dataforge/modules/metadata.py::MetadataEngine`).
- The Action Builder filters (`dataforge/core/actions/filters.py`) are an independent implementation of the same size/date/name filtering as `dataforge/modules/search.py::SearchQuery`; the two can drift.
- `dataforge/core/provider.py` (`FileProvider`/`LocalProvider`) is defined but unused — dead abstraction.
- Generated build output exists in-repo (`build/`, `dist/`), but it is not maintained source.

Correctness and security caveats from the 2026-07-10 review are tracked in [`docs/reviews/NOTES_REVIEW.md`](./reviews/NOTES_REVIEW.md). Key points: the scanner no longer follows symlinks, the cache is thread-safe, integrity/dedup default to SHA-256, and the forensic-report HTML injection (S2) is fixed. Open risks include trash-restore path traversal (S4) and System Cleanup over-classification (S7).

## Related documents

- [Project overview](../README.md)
- [CLI reference](./CLI_REFERENCE.md)
- [GUI workflows](./GUI_WORKFLOWS.md)
- [Development guide](./DEVELOPMENT_GUIDE.md)
- [Technical Source of Truth](./TECHNICAL_SOURCE_OF_TRUTH.md)
- [Project review (bugs, security, UX, roadmap)](./reviews/EXECUTIVE_SUMMARY.md)
