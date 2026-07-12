# 🔨 DataForge GUI Workflows

*File System Management with Steroids and Superpowers*

**Last verified:** 2026-07-12

> **2026-07-12 update:** WS-E (Motion, Empty/Error, A11y) is now shipped. Sidebar group expand/collapse and view-switch transitions are animated via `QPropertyAnimation` (180ms / 160ms OutCubic — see [`IMPLEMENTATION_PLAN.md` §WS-E](./reviews/IMPLEMENTATION_PLAN.md#ws-e--motion-emptyerror-a11y-phase-2e--v020-alpha5--closed)); the Braille-character busy label is replaced by a native `QProgressBar` in indeterminate mode; **Settings → General → Appearance** now has a Reduce motion checkbox that gates both animations; every interactive widget draws a `focus_ring` border on `:focus`; Search and Duplicates now show a purposeful `EmptyState` (icon + body + action button) instead of a bare "No results" label; `friendly_error_message` translates the common Python exceptions; sidebar buttons, the status bar, and the destructive-preview Proceed button carry `accessibleName`/`accessibleDescription` plus a `⚠` colour-blind glyph; an 18-icon monochrome SVG set ships in `dataforge/ui/resources/icons.py` and is attached to every sidebar view, with the icon tone regenerated on every theme change.

## Desktop Shell — GUI Superpowers

The GUI is launched through:

```bash
python run_ui.py
```

The shell is implemented by `dataforge.ui.app.DataForgeApp` (a `PyQt5.QtWidgets.QMainWindow`) and provides:

- a fixed-width (230px) left navigation rail with **collapsible groups** (the rail itself is not collapsible; each group header toggles its items via `toggle_sidebar_group`, and the collapsed set is persisted in `config["collapsed_groups"]`)
- a theme toggle (light/dark stylesheets) exposed as a sidebar **Dark Mode** checkbox; the Settings view shows a read-only label that mirrors the checkbox (sidebar is the single source of truth, 2c.3)
- contextual help for the active view
- a shared status line
- spinner/progress UI for long-running work
- a cancel button backed by a shared `threading.Event`

## Built-in views

The application registers these built-in screens on startup:

| Sidebar group | Views |
| --- | --- |
| Home | Dashboard |
| Find & Organize | Search, Duplicate Finder, Media Tools, Metadata & EXIF, Automations (Action Builder + Tools sub-tabs) |
| Clean & Optimize | Clean Up Space, Storage & Devices, Performance |
| Recover & Investigate | File Recovery, Forensics |
| System | Hardware Info, Settings, About & Help |

After those are loaded, the app scans `dataforge/ui/plugins/` and registers plugin views that inherit from `BaseView` (they appear under a **Plugins** group).

> **Detail-level gating:** the `settings_ui_tier` setting (now relabelled "Detail level" in Settings, values `Simple` / `Standard` / `Everything`, was `Basic` / `Advanced` / `Expert`) controls *in-view* complexity only — advanced controls stay hidden behind in-view expanders on `Simple` and `Standard`. The sidebar shows every group regardless of tier so users can always discover what DataForge can do. This trade-off (hidden navigation vs. progressive disclosure) is discussed in [`reviews/IMPROVEMENT_PLAN.md`](./reviews/IMPROVEMENT_PLAN.md).

## Background execution model

Long-running work should not execute on the Qt main/UI thread. Views are expected to use:

- `app.run_workflow(...)`
- `app.run_background(...)`

### What the app shell does

- creates a `BackgroundWorker(QThread)` and starts it
- shows spinner/progress UI
- injects `cancel_token` into workers that declare it
- injects `progress_callback` through `run_workflow()` when requested
- marshals results back to the UI thread through Qt signals (`progress_signal`, `status_signal`, `result_signal`, `error_signal`) connected to UI slots, instead of a manual queue-polling loop

### What view workers should support

Where practical, worker functions accept:

- `progress_callback(current, total, step_name)`
- `cancel_token`

This contract is used broadly across search previews, duplicate cleanup, metadata cleaning, dashboard scanning, and media operations.

## Common interaction pattern

Many GUI workflows follow the same shape:

1. collect or scan candidate files
2. build a preview of planned work
3. ask for confirmation
4. execute the real operation
5. summarize successes, failures, and cancellations

That preview-first pattern is one of the main usability and safety conventions in the application.

## View-by-view behavior

## Dashboard

`DashboardView` is the landing screen.

It shows:

- home-disk usage
- host/system information
- configuration summary
- file distribution summaries
- quick statistics
- largest-file summaries

The dashboard paths come from `config["dashboard_paths"]`. The actual scan runs in the background so the UI can remain responsive.

## Search

`SearchView` is the main interactive file-discovery and bulk-action screen.

It supports:

- path selection
- filename, extension, content, size, and age filters
- result previewing in a tree/grid
- export of result sets
- bulk move/copy flows
- delete flows
- rename flows
- archive/zip flows

This view is one of the heaviest users of shared search logic plus `FileActionService`.

## Duplicate Finder

`DuplicatesView` focuses on hash-based duplicate groups.

Typical workflow:

1. scan a target path
2. group duplicate files by hash
3. inspect duplicate groups
4. choose a keep strategy or select specific files
5. delete or move the redundant copies
6. export duplicate reports when needed

It is the GUI companion to the `fm dupes` command.

## Action Builder

`ActionBuilderView` exposes the pipeline engine from `dataforge/core/actions/`.

This view allows the user to compose multi-step workflows from filters and action steps instead of running only one predefined screen flow.

Architecturally, this view is important because it is the repository's workflow-composition surface. It is where new generic pipeline steps belong if the capability should be reusable.

## Automations (Tools sub-tab)

`ToolsView` (embedded as a sub-tab inside the Automations view) is a notebook-based collection of secondary utilities.

### Integrity Monitor

Supports two operations:

- create a snapshot of a file or folder
- verify the current state against a saved snapshot

This wraps the `IntegrityMonitor` module and uses background execution for long-running checks. Snapshots are self-describing (`{"algorithm": ..., "created_at": ..., "files": {...}}`) and use the configured hash algorithm (default `sha256`); legacy flat MD5 snapshots are still verifiable — see [`reviews/AUDIT_FINDINGS.md`](./reviews/AUDIT_FINDINGS.md) (M4).

### Metadata Cleaner

Scans for files with removable metadata, then lets the user clean selected or all results.

This overlaps intentionally with the standalone plugin view.

### Batch Renamer

Loads a set of files, previews rename changes, and applies them in bulk.

### Folder Sync

Analyzes a one-way copy/sync from a source folder into a destination folder, then applies the planned copy actions after preview.

## Media Tools

`MediaView` contains two notebook tabs.

### PDF Tools

- merge multiple PDFs into one output
- split one PDF into one file per page

Both operations use preview-first workflows and run through worker functions that support progress and cancellation.

### Image Batch

- add multiple images
- pick an output format
- resize by percentage
- preview and convert all queued images

The image pane also uses a preview panel for selected files.

## Settings

`SettingsView` is the main runtime-configuration UI, organized into tabs (General, Performance, Exclusions, Dashboard) plus a **Detail level** selector (`Simple` / `Standard` / `Everything`) that gates in-view complexity and notifies the sidebar to rebuild so the rail stays in sync.

It allows the user to manage:

- theme (light/dark) and path display mode (full/relative)
- safe mode / trash behavior
- log level
- default duplicate keep strategy
- hash algorithm (`md5` / `sha1` / `sha256` / `sha512`; default `sha256`)
- size units
- **two** worker-thread budgets: *Hashing/Batch Threads* (`max_thread_workers`) and *Search Threads* (`search_thread_workers`)
- excluded folders and excluded extensions
- dashboard watch paths
- cache clearing (Everything tier)

These values persist through `ConfigManager` into `~/.dataforge/config.json`.

> **Persistence is uniform:** every setting **autosaves** the moment the user changes it, and a transient "Saved ✓" indicator flashes in the Settings header to confirm the write — no Save button, no hidden state. This was previously inconsistent (Performance / Exclusions / Dashboard had ad-hoc Save buttons); the unified behaviour is documented as 2c.2 in [`reviews/IMPROVEMENT_PLAN.md`](./reviews/IMPROVEMENT_PLAN.md).

## Plugin view: Metadata Cleaner

`dataforge/ui/plugins/cleaner_plugin.py` ships with a standalone `MetadataCleanerPlugin`.

The plugin system:

- scans `dataforge/ui/plugins/*.py`
- imports each module
- registers any `BaseView` subclass it finds

Current plugin behavior mirrors the metadata cleaning capability that also exists inside `ToolsView`.

## UI infrastructure worth knowing

Shared widget infrastructure lives in `dataforge/ui/widgets.py`.

Important reusable pieces include:

- `EnhancedTreeview`
- file preview panels
- tooltip helpers
- shared context-menu support

This file is the right place to look before creating new ad hoc table or preview behavior in a single view.

## Recommended extension strategy

Use these heuristics when adding functionality:

- add a **new view** when the feature needs a dedicated top-level user journey
- add a **plugin view** when the feature should be optional or independently packaged
- add a **new Action Builder step** when the behavior should be composable with other pipeline steps
- add or extend a **shared service/module** when the behavior will be used by both CLI and GUI

## Related documents

- [Project overview](../README.md)
- [Architecture](./ARCHITECTURE.md)
- [CLI reference](./CLI_REFERENCE.md)
- [Development guide](./DEVELOPMENT_GUIDE.md)
- [Project review (bugs, security, UX, roadmap)](./reviews/EXECUTIVE_SUMMARY.md)
