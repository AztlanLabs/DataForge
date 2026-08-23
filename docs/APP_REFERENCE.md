# DataForge Application Reference

**Source verified:** 2026-08-23 06:30 UTC — Wave 5 (11/11) + Wave 6 (1/1) DONE, 1213 tests + dc44be4 UI fixes (dropdown, tier, STOP, artifacts), HEAD `b373e7e`

DataForge is a local-first file, storage, recovery, and system-inspection application. It has two interfaces:

- The `fm` command-line interface for scripted and terminal workflows.
- A PyQt5 desktop application for interactive inspection, previews, and batch workflows.

The interfaces share many core modules, but they do **not** expose identical capabilities. This document is the consolidated reference for the application as implemented in `dataforge/`.

## Contents

- [Install and launch](#install-and-launch)
- [Safety model](#safety-model)
- [Interfaces and capability map](#interfaces-and-capability-map)
- [Command-line reference](#command-line-reference)
- [Desktop application](#desktop-application)
- [Core behavior](#core-behavior)
- [Features by module](#features-by-module)
- [Configuration and local data](#configuration-and-local-data)
- [Dependencies and external tools](#dependencies-and-external-tools)
- [Platform support and limitations](#platform-support-and-limitations)
- [Architecture and extension](#architecture-and-extension)
- [Development, testing, and packaging](#development-testing-and-packaging)

## Install and launch

### Full application

The full desktop, media, and CLI installation uses `requirements.txt` plus an editable package install:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Launch the desktop application:

```bash
python run_ui.py
```

Launch the CLI:

```bash
fm --help
```

Without an editable install, run the CLI from the repository root:

```bash
PYTHONPATH=. python -m dataforge.cli --help
```

### Core/CLI package

`pyproject.toml` declares the console script and its core dependencies. PyQt5, Pillow, PDF, and OpenCV dependencies are intentionally supplied through `requirements.txt`, because they are needed for the desktop/media experience rather than the base console entry point.

## Safety model

DataForge can move, copy, rename, trash, permanently delete, overwrite metadata, and write recovery or report output. Treat it as an operator tool, not a backup system.

- The default for CLI `organize`, `rename`, `clean`, and `cleanup` is `--dry-run`. Pass `--execute` only after reviewing the preview.
- GUI bulk actions use a preview, confirmation, execution, and outcome-summary flow.
- `safe_mode` is enabled by default. The central delete service uses `send2trash` while it is enabled; disabling it permits direct deletion for that service.
- Destination-name collisions are resolved by suffixing names such as `_1`, rather than overwriting an existing file, in the central move/copy/rename path.
- Cancellation is cooperative. Long-running workers stop only where their implementation checks the supplied cancellation token.
- Integrity snapshots, recovery results, forensic exports, media output, and metadata changes are separate write paths. Review their destinations and keep original evidence read-only when forensic preservation matters.
- Secure deletion is best effort only. It cannot guarantee erasure on SSDs, flash media, copy-on-write, or journaled filesystems.

Always work from copies when performing recovery, carving, forensic examination, or irreversible metadata removal.

## Interfaces and capability map

| Area | CLI | Desktop GUI | Notes |
| --- | --- | --- | --- |
| Scan, search, duplicate detection | Yes | Yes | Shared scanner/search/duplicate modules. |
| Move, copy, delete, rename, ZIP | Search/organize/rename paths | Yes | GUI provides selection and preview workflows. |
| Empty-folder cleanup and disk usage | Yes | Indirect/related views | CLI exposes `clean` and `usage`. |
| Integrity snapshots | Yes | Yes, Automations > Tools | SHA-256 is the default configured algorithm. |
| System cleanup | Yes | Yes | CLI covers category cleanup; GUI also exposes browser-artifact inspection. |
| Metadata read/edit/removal | Yes | Yes | GUI has a dedicated metadata view plus metadata cleaner tooling. |
| Trash recovery and signature carving | Yes | Yes | Windows Recycle Bin scanning is not implemented. |
| Hardware, performance, devices | Yes | Yes | Some collection methods are Linux-specific. |
| OS artifacts, keyword search, hashes | Yes | Yes | OS-artifact parsing is primarily Linux-layout oriented. |
| PDF/image batch tools | No | Yes | PDF merge/split and image conversion are GUI/action-pipeline features. |
| Action Builder, folder sync | No | Yes | GUI-only workflow composition tools. |
| Password tools, extended forensic tools | No | Yes | Available from the Forensics view where supported. |
| Plugins | No | Yes | Disabled unless `plugins_enabled` is enabled. |

## Command-line reference

The `fm` CLI has 16 top-level commands or command groups. Run `fm COMMAND --help` for Click-generated option help.

### Discovery and organization

| Command | Purpose | Key behavior |
| --- | --- | --- |
| `fm scan PATH` | List files found by the shared scanner. | `--recursive` is on by default. |
| `fm search PATH` | Find files by name, extension, content, size, age, or depth. | Supports `--format text|json|jsonl`, sorting, limits, and `--count-only`. |
| `fm dupes PATH` | Find same-content files. | Groups same-size candidates by configured hash; supports export and keep-strategy-compatible sorting. |
| `fm organize PATH --dest DEST` | Move or copy matching files. | Filters by filename regex and extensions; default action is copy and default mode is dry run. |
| `fm rename PATH --pattern REGEX --repl TEXT` | Rename files in the specified directory. | Non-recursive; default mode is dry run. |
| `fm clean PATH` | Remove empty folders. | Walks bottom-up, never removes the supplied root, and defaults to dry run. |
| `fm usage PATH` | Print folder-size summary. | Groups scanned file sizes by immediate containing folder. |

Examples:

```bash
fm search ~/Documents --name-glob "*.pdf" --sort size --reverse --limit 20
fm dupes ~/Photos --output duplicates.csv --export-format csv
fm organize ~/Downloads --dest ~/Sorted --action move --ext pdf,docx --execute
fm rename ~/Scans --pattern " " --repl "_" --execute
```

Search content matching reads at most 10 MiB per candidate file. `--name-glob` and `--name-regex` cannot be combined. Use `fm search ... --error-format json` when an automation needs a machine-readable usage error.

### Integrity and cleanup

| Command | Purpose | Key behavior |
| --- | --- | --- |
| `fm integrity create PATH SNAPSHOT` | Create a JSON hash baseline. | New snapshots contain `algorithm`, `created_at`, and relative file hashes. |
| `fm integrity check PATH SNAPSHOT` | Compare a tree with a baseline. | Reports new, modified, deleted, and unreadable files. Legacy flat MD5 snapshots remain readable. |
| `fm cleanup` | Find and optionally remove junk files. | Categories include system temp, user cache, thumbnails, trash, logs, package cache, and crash reports. |

`fm cleanup --path PATH` does not classify every file under that path as junk. User-supplied paths match only known junk extensions or filenames. Built-in cache/trash-style category paths have broader classification. Sockets and FIFOs are skipped, and built-in `/tmp` and `/var/tmp` files must be at least one day old.

```bash
fm integrity create ~/Records records-snapshot.json
fm integrity check ~/Records records-snapshot.json
fm cleanup --category "User Cache" --min-age 30 --dry-run
```

### System, recovery, and investigation

| Command | Purpose | Key behavior |
| --- | --- | --- |
| `fm performance` | Show OS, CPU, RAM, and uptime overview. | Use `--processes`, `--startup`, or `--disk-health` for a focused report. |
| `fm devices` | List mounted storage and usage. | `--info MOUNTPOINT` returns one mount's details. |
| `fm hardware` | Produce hardware profile and upgrade recommendations. | `--export json|html --out PATH` writes a report. |
| `fm recover` | Scan trash or carve recognized signatures from a raw image/device. | Use `--trash` or `--carve IMAGE --out DIRECTORY`; `--types` filters carving signatures. |
| `fm metadata PATH` | Read, edit, remove all, or remove GPS metadata. | Requires a file, not a directory. |
| `fm forensics` | Parse OS artifacts, keyword-search files, or list signature categories. | `PATH` is optional only with `--list-types`. |
| `fm hash-calc PATH...` | Calculate one selected hash per file. | Supports MD5, SHA-1, SHA-256, and SHA-512; default is SHA-256. |

```bash
fm performance --processes
fm devices --info /mnt/data
fm metadata photo.jpg --strip-gps
fm recover --carve evidence.img --out ~/Recovered --types JPEG,PDF
fm forensics ~/Evidence --search-keyword "confidential"
fm hash-calc image.dd --algo sha256
```

Trash restoration uses the path recorded in `.trashinfo` when it is an absolute, non-traversing, non-system path. Unsafe recorded paths are redirected beneath `~/Recovered` by default. The CLI restores every scanned item after confirmation; it does not offer per-item selection.

## Desktop application

The PyQt5 application has a fixed-width navigation rail, shared status/progress controls, a cancel button, light/dark theme support, reduced-motion support, keyboard focus styling, accessible labels, and a `Simple` / `Standard` / `Everything` detail level. The detail level controls in-view disclosure; it does not hide navigation groups.

Long-running work runs through a `QThread` worker. Views can receive progress updates and a cooperative cancellation event without blocking the GUI thread.

### Views

| Navigation group | View | Main capabilities |
| --- | --- | --- |
| Home | Dashboard | Disk usage, host details, configuration, file distribution, categories, and largest files for configured dashboard paths. |
| Find & Organize | Search | Filename/content/size/date search; result export; selected move, copy, delete, rename, and ZIP actions. |
| Find & Organize | Duplicate Finder | Hash grouping, keep strategies, extra-copy selection, move/delete, and CSV/JSON export. |
| Find & Organize | Media Tools | PDF merge/split; image conversion and resize queue. |
| Find & Organize | Metadata & EXIF | Inspect, edit, and strip metadata. |
| Find & Organize | Automations | Action Builder plus the embedded Tools tab. |
| Clean & Optimize | Clean Up Space | Junk-category scans, cleanup previews, and browser-artifact discovery. |
| Clean & Optimize | Storage & Devices | Mounted-device list and mount details. |
| Clean & Optimize | Performance | System overview, processes, startup entries, and SMART information where available. |
| Recover & Investigate | File Recovery | Trash inspection/restore, signature carving, and PhotoRec availability/workflow support. |
| Recover & Investigate | Forensics | Artifact parsing, keyword search, hashes, file signatures, reports, and supported advanced analysis tools. |
| System | Hardware Info | CPU, RAM, motherboard, GPU, storage, and upgrade guidance. |
| System | Settings | Persistent application configuration. |
| System | About & Help | Application information and user guidance. |

### Automations

The Action Builder scans a source path, creates an `ActionContext`, then runs selected steps in order. It supports dry-run previews and execution.

- Filters: name/glob or regex, size, date/age, and image dimensions.
- Actions: move, copy, delete, ZIP, template rename, metadata cleanup, and image conversion.
- Template rename placeholders: `{name}`, `{ext}`, `{date}`, `{size}`, and `{counter}`.

The Tools sub-tab provides integrity monitoring, metadata cleaning, batch rename, and one-way folder synchronization. Folder sync analyzes source and destination first, then copies planned files after confirmation.

### Plugins

Desktop plugins are Python files under `dataforge/ui/plugins/`. The bundled `MetadataCleanerPlugin` is an example and overlaps with the built-in metadata tooling.

- Enable plugin execution with `plugins_enabled` in Settings/configuration.
- Plugins execute in the application process and must be trusted.
- On Unix, the loader rejects a world-writable plugin directory and plugin files not owned by the current user.
- On Windows, those Unix ownership/permission checks are not applicable.
- A plugin must define a `BaseView` subclass to be registered.

## Core behavior

### Scanning and file model

`FileEntry` is the common file metadata model. It carries an absolute path, filename, extension, byte size, creation/modification timestamps, directory flag, and optional hash fields.

The shared scanner accepts a file or directory, applies configured excluded folders/extensions, supports maximum depth, catches inaccessible paths, and skips symlinks rather than following them. A path excluded by name or extension will not appear in scans that use this scanner.

### Hashing and duplicates

Supported hashing algorithms are MD5, SHA-1, SHA-256, SHA-512, and BLAKE2b. The configured default is SHA-256. Duplicate detection first groups by size, then hashes candidates in parallel, using the persistent cache when a path's size, modification time, and algorithm match a cached value.

Duplicate keep strategies are `first path`, `newest`, `oldest`, `largest`, and `smallest`. They select the file to retain; the caller chooses whether to move or delete the remaining records.

### Shared batch actions

`FileActionService` is the primary batch write service. It supports move/copy, delete/trash, regex/template/parts renames, and ZIP creation. Its outcomes record per-item success, failure, skip, and cancellation state for a consistent UI or caller summary.

Not every module uses this service. For example, recovery, metadata engines, integrity snapshots, forensic output, and some reports have dedicated write behavior. New destructive workflows should use the shared service unless their behavior genuinely requires a specialized path.

## Features by module

| Module family | Capabilities |
| --- | --- |
| `modules.search` | Query by name, extension, content, size, and modified date; stream/list results; sort and export CSV/JSON. |
| `modules.duplicates` | Parallel hash-based duplicate detection, keeper selection, ordering, serialized records, and exports. |
| `modules.organizer`, `renamer`, `cleaner`, `usage` | Search-driven transfer, regex rename, empty-folder removal, metadata cleanup, and disk-usage summaries. |
| `modules.integrity`, `reporting` | Hash snapshots/verification and duplicate report formats. |
| `modules.system_cleanup` | Platform junk-category scanning, cleanup-size estimates, and browser cookie/history/cache/session artifact discovery. |
| `modules.performance`, `hardware`, `device_manager` | Process, startup, SMART, OS/resource, hardware, GPU/storage, and mounted-device diagnostics. |
| `modules.metadata` | Metadata handlers, ExifTool integration when available, read/write/strip, and GPS removal. |
| `modules.recovery`, `file_signatures` | XDG/macOS trash scanning, constrained restore, signature-based carving, and PhotoRec/TestDisk discovery. |
| `modules.forensics`, `password_tools` | OS artifacts, keyword search, file hashes, timelines, entropy/hex/steganography helpers, reports, secure-delete helper, and wrappers for supported password-auditing tools. |
| `core.media_ops` | PDF merge/split through `pypdf`; image conversion/resizing through Pillow. |

## Configuration and local data

All per-user state is stored under `~/.dataforge/`, not in the repository:

| Artifact | Purpose |
| --- | --- |
| `config.json` | Validated persistent settings. Unknown keys are discarded on load. |
| `cache.db` | SQLite/WAL hash cache shared by hashing and duplicate detection. |
| `app.log` | Rotating application log: 5 MiB per file, with three backups. |

Default configuration keys:

| Key | Default | Purpose |
| --- | --- | --- |
| `theme` | `cosmo` | Light/dark UI selection (`darkly` is used for dark mode). |
| `safe_mode` | `true` | Trash through `send2trash` for central delete actions. |
| `excluded_extensions` | `.tmp`, `.log` | Scanner exclusions. |
| `excluded_folders` | `.git`, `node_modules`, `__pycache__` | Scanner exclusions. |
| `max_thread_workers` | `4` | Hashing and batch-operation worker budget. |
| `search_thread_workers` | `4` | Search worker budget. |
| `hash_algorithm` | `sha256` | Default hash for duplicate/integrity flows. |
| `log_level` | `INFO` | Application log verbosity. |
| `size_unit` | `Auto` | Display unit. |
| `path_display_mode` | `full` | Full or relative path display. |
| `dashboard_paths` | `~/Documents` | Paths summarized by Dashboard. |
| `settings_ui_tier` | `Simple` | In-view detail level. |
| `duplicate_default_keep_strategy` | `first path` | Duplicate selection default. |
| `plugins_enabled` | `false` | Enables desktop plugin execution. |
| `ui_reduce_motion` | `false` | Disables view/sidebar animations when true. |

## Dependencies and external tools

Core declared dependencies include Click, Rich, tqdm, Send2Trash, psutil, python-magic, PyExifTool, mutagen, py-cpuinfo, and defusedxml. The full runtime requirements additionally include pandas, PyQt5, Pillow, pypdf, PyMuPDF, and OpenCV.

Some capabilities are conditional on locally installed executables or libraries:

| Tool | Used for | Behavior when unavailable |
| --- | --- | --- |
| ExifTool | Broad metadata read/write/strip support. | Native/fallback handlers support a narrower set of formats. |
| PhotoRec / TestDisk | Recovery discovery and PhotoRec workflows. | Built-in signature carving remains available. |
| `smartctl` | SMART disk-health checks. | Health report returns an unavailable/error result. |
| `systemctl` | Linux startup-item discovery. | Startup coverage is limited outside Linux/systemd. |
| `lsblk`, `lspci`, `nvidia-smi`, `dmidecode` | Linux hardware/device details. | Reports use available cross-platform/fallback information. |
| Hashcat, John, zip2john, pdf2john | Password-tool integrations in the Forensics UI. | Password-analysis actions cannot run without their tools. |

## Platform support and limitations

DataForge is cross-platform at the Python/file-operation layer, but several diagnostics and forensic features depend on operating-system layouts and tools.

- **Linux:** broadest support for cleanup categories, startup items, SMART/hardware utilities, mounted-device fallback, and OS-artifact layouts.
- **macOS:** XDG-style/home trash scanning includes `~/.Trash`; cleanup paths include `Library` locations. Linux-specific diagnostics may be unavailable.
- **Windows:** standard scanning, search, metadata, and many file operations work. Recycle Bin scanning/restoration is explicitly unsupported and reports that limitation instead of an empty result.
- **Forensic artifacts:** OS-artifact parsers target Linux paths such as `/etc`, `/var/log`, shell histories, cron, dpkg, and systemd data. They are not a Windows Registry or macOS forensic suite.
- **Disk images:** forensic ingest accepts a mounted directory as a source. It does not mount raw disk-image files. Raw carving accepts a readable image/device path and scans bytes for supported signatures.
- **Carving:** header/footer signature carving can recover recognizable byte ranges but does not reconstruct fragmented files or prove evidentiary completeness.
- **Filesystem semantics:** deletion, trash behavior, metadata support, permissions, timestamps, mount discovery, and external tools vary by platform and filesystem.

## Architecture and extension

The maintained source is in `dataforge/`; `build/`, `dist/`, and `__pycache__/` are generated output.

```text
CLI (`fm`) and GUI (`run_ui.py`)
                |
      feature modules and GUI views
                |
Action Builder -> FileActionService -> filesystem operations
                |
 scanner, FileEntry, config, hash cache, logger, utilities
```

Key extension points:

- Add reusable discovery behavior in `dataforge/modules/search.py` and build from `SearchQuery`.
- Add low-level move/copy/delete/rename/archive behavior in `dataforge/core/operations/files.py`, then expose it through `FileActionService`.
- Add composable GUI workflow steps as `ActionStep` subclasses under `dataforge/core/actions/`.
- Add a top-level desktop journey as a `BaseView` in `dataforge/ui/views/`.
- Add an optional trusted desktop view as a plugin in `dataforge/ui/plugins/`.
- Keep lengthy GUI work behind `DataForgeApp.run_workflow()` or `run_background()` and support `progress_callback` and `cancel_token` where practical.

## Development, testing, and packaging

Install the complete development environment:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
```

Run the collected pytest suite from the repository root:

```bash
PYTHONPATH=. pytest -q
```

Quality tooling configured in `pyproject.toml` and development requirements includes Ruff, mypy, coverage, pre-commit, and pip-audit.

Build desktop executables with PyInstaller:

```bash
python build_exe.py release
python build_exe.py debug
python build_exe.py all
```

- `release` produces a windowed, one-file executable in `dist/release/`.
- `debug` produces a console, one-directory executable in `dist/debug/`.
- Build specifications are generated under `buildspec/`; artifacts under `build/` and `dist/` are output, not maintained source.

## Related documentation

- [Architecture](ARCHITECTURE.md) for layer and control-flow detail.
- [CLI reference](CLI_REFERENCE.md) for command examples and options.
- [GUI workflows](GUI_WORKFLOWS.md) for screen-level interaction flows.
- [Development guide](DEVELOPMENT_GUIDE.md) for contributor setup.
- [Technical source of truth](TECHNICAL_SOURCE_OF_TRUTH.md) for file-by-file implementation mapping.
- [Review documents](reviews/) for historical audit findings and roadmap material.
