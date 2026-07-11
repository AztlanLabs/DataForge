# 🔨 DataForge

## File System Management with Steroids and Superpowers

**Professional file and system intelligence platform** for power users, developers, and digital forensics specialists. Unified CLI + desktop experience for file discovery, organization, recovery, and forensic analysis.

DataForge provides both a **terminal interface** (`fm` CLI) and **interactive desktop application** (PyQt5 GUI) — same powerful toolkit, two workflows. Built around shared core services so your logic runs consistently anywhere.

> **What's inside:** Enterprise-grade duplicate detection, forensic carving, integrity verification, automated cleanup, media batch processing, hardware diagnostics, artifact parsing, and workflow automation — all in one streamlined, production-tested toolkit.

<div align="center">
  <img src="DataForgeLogo.jpeg" alt="DataForge Logo - File & System Intelligence" width="300" />
</div>

> [!NOTE]
> **This project recently went through a large, multi-part change:** the GUI was migrated from Tkinter/ttkbootstrap to **PyQt5**, and a batch of new modules (hardware, forensics, recovery, metadata, performance, system cleanup, password tools, device manager, file signatures) were added. Documentation, packaging metadata, and CLI wiring have since been reconciled to match — a couple of smaller items are still open. See [Known incomplete / in-progress changes](#known-incomplete--in-progress-changes) for the current, verified list.

## Why DataForge? (The Superpowers)

| Superpower | What You Get |
|---|---|
| **🎯 Find the noise** | Locate duplicates by content hash, search by name/size/age/content, parse forensic artifacts in seconds — find what matters, fast |
| **🧹 Clean and organize** | Batch operations, integrity snapshots, automated cleanup by category, one-click categorized organization — organize chaos in minutes |
| **🔍 Go deep into data** | Forensic file carving, GPS metadata stripping, disk SMART health, password strength analysis, trash recovery — extract what's hidden |
| **⚡ Unified interface** | Terminal and desktop — choose your workflow. Same features, same results, same safety standards — no tool switching |
| **🧩 Extensible** | Action Builder pipeline for custom multi-step workflows; plugin system for custom views; scriptable CLI — build your own workflows |
| **🛡️ Production-ready** | 224 passing tests, thread-safe batch operations, dry-run previews, cancellation support, detailed logging — trust the tool |
| **🚀 Automation at scale** | Parallel hashing, batch operations on thousands of files, configurable worker threads, progress tracking, cancellation — process like a pro |
| **🔐 Enterprise features** | Role-based experience levels (Basic/Advanced/Expert), audit logging, integrity verification, forensic reports — audit-ready |

## Rewrite track

 A new Tauri-based rewrite now exists at [`../FileManager_Tauri`](../FileManager_Tauri). The current Python application remains the functional source of truth while features are migrated into the new desktop stack in phases, and the Tauri app now includes Rust-backed search/discovery, dashboard snapshot metrics, organize preview, duplicate scanning with configurable hash/worker settings, integrity snapshot/verify, browse/save path dialogs, settings import/export with theme presets, image conversion with queued file picking, async background execution for long-running tasks, and a shared bottom status/progress bar modeled after the original desktop shell.

## What DataForge Does (The Arsenal)

### 🧹 Cleanup & Organization (On Steroids)
- **Duplicate detection** — find identical files by content hash, export reports, auto-select keep strategy, batch delete/move — **reclaim gigabytes in seconds**
- **Junk removal** — scan and remove cache, temp, logs, and crash reports by category (system temp, user cache, thumbnails, trash) — **one command to clean it all**
- **Storage analysis** — disk usage reports with top folders and size distributions — **understand where your space went**
- **Empty folder cleanup** — recursive empty-directory removal — **restore folder hygiene**

### 🔍 Discovery & Search (Supercharged)
- **Advanced search** — by filename (glob/regex), extension, size range, modification date, file contents (with regex) — **find anything, anywhere**
- **Batch organization** — move or copy search results to a target location with collision handling — **organize at scale**
- **Export results** — CSV, JSON, JSONL formats for downstream processing — **integrate with your tools**

### 📝 File Operations (Batch Mode)
- **Batch rename** — regex replacement, template-based naming (`{date}`, `{counter}`, `{ext}`), find/replace with prefix/suffix — **rename thousands at once**
- **Archive creation** — zip selected or all results with configurable compression; per-file or single archive mode — **compress intelligently**
- **Media tools** — merge/split PDFs, batch convert and resize images (PNG/JPEG/WEBP/BMP) — **transform media in bulk**

### 🔐 Data Integrity & Recovery (Fort Knox Edition)
- **Integrity snapshots** — create SHA-256 baselines (MD5 legacy supported), verify changes (NEW/MODIFIED/DELETED detection) — **detect tampering**
- **Trash recovery** — restore deleted files from system trash or external media — **get files back**
- **File carving** — recover files from disk images by signature (JPEG, PNG, PDF, ZIP, and 30+ more types) — **resurrect lost data**
- **Metadata cleaning** — strip EXIF (including GPS), PDF metadata, and other embedded data — **sanitize before sharing**

### 🔬 Forensics & System Analysis (Full Arsenal)
- **OS artifact parsing** — registry, logs, temporary artifacts analysis — **uncover system secrets**
- **Keyword search** — full-text search across a directory or disk image — **hunt for evidence**
- **Hash calculation** — MD5, SHA-1, SHA-256, SHA-512 cryptographic file hashing with caching — **verify file integrity**
- **File signatures** — identify file types by magic bytes across 40+ categories — **know what you're looking at**
- **Hardware diagnostics** — CPU, RAM, motherboard, storage, GPU profiles; SMART disk health; upgrade recommendations — **assess your machine**
- **System performance** — top processes by memory, startup items, disk health status — **optimize and monitor**
- **Device manager** — list connected storage (internal, USB, network, optical) with per-device usage — **track all your storage**

### 🚀 Automation & Extensibility (Power User Paradise)
- **Action Builder** — compose reusable multi-step pipelines (filter → rename → move → archive) with drag-reorder UI — **automate complex workflows**
- **Plugin system** — extend the GUI with custom views; bundled example: Metadata Cleaner plugin — **customize it your way**
- **CLI scripting** — JSON/JSONL output, dry-run modes, all operations scriptable via `fm` command — **integrate anywhere**

## System at a Glance

| Area | Details |
| --- | --- |
| **Product** | 🔨 **DataForge** — File system management with steroids and superpowers (code: `filemanager/` — package rename pending) |
| **CLI** | `fm` command → `filemanager.cli:main` (17 commands, all powers available) |
| **GUI** | `python run_ui.py` → `filemanager.ui.app.FileManagerApp` (PyQt5, 14 views, drag-reorder pipeline) |
| **Config** | `~/.filemanager/config.json` (theme, performance, exclusions, dashboard paths, experience levels) |
| **Cache** | `~/.filemanager/cache.db` (SQLite hash cache, thread-safe with WAL, parallel hashing) |
| **Logging** | `~/.filemanager/app.log` (rotating, 5 MB / 3 backups, full audit trail) |
| **Architecture** | Layered: core primitives → operations → service layer → modules → GUI/CLI orchestration (shared logic, zero duplication) |
| **Tests** | 224 passing (`pytest`, full coverage across all feature layers, production-grade quality) |
| **Build** | `setup.py` (CLI/core), `build_exe.py` (PyInstaller → standalone desktop bundles, one-file release mode) |

## Quick Start

**For GUI users:** just install and run. **For developers/automation:** CLI all the way.

### Install

```bash
cd FileManager
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

### Launch

**Desktop GUI:**
```bash
python run_ui.py
```
Browse for duplicates, organize files, inspect hardware — all from a clean, tabbed interface.

**Terminal CLI:**
```bash
fm --help
fm search ~/Documents --name-glob "*.pdf"
fm dupes ~/Downloads --sort size --limit 20
fm forensics --list-types
fm cleanup --category "User Cache" --dry-run
```

No install? Use:
```bash
PYTHONPATH=. python -m filemanager.cli --help
```

### Verify the Build

```bash
PYTHONPATH=. pytest -q  # 224 tests pass
```

> [!NOTE]
> **Full test suite passes — 224 tests.** All correctness fixes are verified. See [`docs/reviews/01_CODE_REVIEW_AND_BUGS.md`](./docs/reviews/01_CODE_REVIEW_AND_BUGS.md) for the comprehensive audit.

### Build desktop executables

```bash
python build_exe.py release
python build_exe.py debug
```

## Common Use Cases

| You Are | Try This |
|---------|----------|
| **Storage cleanup expert** | `fm cleanup --category "User Cache" --min-age 30 --dry-run` then `--execute` |
| **Mac/Linux user with bloat** | GUI: System Cleanup view → select junk categories → review → clean |
| **Photo manager** | GUI: Duplicate Finder → scan photos folder → sort by size → keep largest |
| **System forensics analyst** | `fm forensics ~/Evidence --search-keyword "confidential"` + `fm hash-calc --algo sha256` |
| **IT auditor** | `fm integrity create /critical_data snapshot.json` → `fm integrity check /critical_data snapshot.json` (detect tampering) |
| **DevOps automating cleanup** | `fm dupes --format jsonl \| jq '.path' \| xargs rm` (scripted duplicate removal) |
| **Data hoarder organizing chaos** | GUI: Search & Organize → glob pattern → preview → move to categorized folders |
| **Incident responder** | `fm recover --carve /dev/sdb1 --out ~/Recovered --types jpg,png,pdf` |
| **Metadata scrubber** | `fm metadata photo.jpg --strip-gps` (remove location before sharing) |
| **Workflow builder** | GUI: Action Builder → filter by date → rename template → move to archive → zip |

## Documentation Map

**Getting Started:**
- [`docs/DEVELOPMENT_GUIDE.md`](./docs/DEVELOPMENT_GUIDE.md) - setup, testing, packaging, onboarding paths
- [`docs/CLI_REFERENCE.md`](./docs/CLI_REFERENCE.md) - complete CLI command reference with examples

**Deeper Dives:**
- [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) - layered design, control flow, shared abstractions, extension points
- [`docs/GUI_WORKFLOWS.md`](./docs/GUI_WORKFLOWS.md) - view-by-view desktop workflows, threading, background execution model
- [`TECHNICAL_SOURCE_OF_TRUTH.md`](./TECHNICAL_SOURCE_OF_TRUTH.md) - authoritative file-by-file source map for maintainers

### Project Review & Audit (2026-07-10)

A comprehensive engineering, security, and UX audit lives under [`docs/reviews/`](./docs/reviews/):

- **[`00_EXECUTIVE_SUMMARY.md`](./docs/reviews/00_EXECUTIVE_SUMMARY.md)** — start here: overview, findings index, remediation status
- **[`01_CODE_REVIEW_AND_BUGS.md`](./docs/reviews/01_CODE_REVIEW_AND_BUGS.md)** — 224 tests pass; all correctness bugs fixed (MD5→SHA-256, symlink scope escape, cache threading, JSON error handling, sha512 crash)
- **[`02_SECURITY_AND_FORENSIC_AUDIT.md`](./docs/reviews/02_SECURITY_AND_FORENSIC_AUDIT.md)** — application and forensics security hardening; open issues (HTML injection, path traversal, over-classification)
- **[`03_UIUX_REVIEW.md`](./docs/reviews/03_UIUX_REVIEW.md)** — UX improvements: naming, information architecture, interactions, accessibility
- **[`04_IMPROVEMENTS_AND_ROADMAP.md`](./docs/reviews/04_IMPROVEMENTS_AND_ROADMAP.md)** — engineering practices, architecture modernization, planned features

## Directory Structure

| Path | Purpose |
| --- | --- |
| **`run_ui.py`** | Desktop GUI entry point (PyQt5 application launcher) |
| **`build_exe.py`** | PyInstaller bundler for standalone executables (release/debug) |
| **`filemanager/cli.py`** | 17 CLI commands via Click (scan, dupes, search, organize, rename, clean, usage, integrity, cleanup, performance, recover, metadata, hardware, forensics, hash-calc, devices) |
| **`filemanager/core/`** | Shared foundation: file model, scanner, config, cache, hasher, logger, operations layer |
| **`filemanager/core/services/`** | `FileActionService` — centralized batch file operations (move, copy, delete, rename, archive with progress/cancel/dry-run) |
| **`filemanager/core/actions/`** | Action Builder pipeline engine: filters, IO steps, transformations, media operations |
| **`filemanager/modules/`** | Feature implementations (search, duplicates, organizer, cleaner, integrity, usage, reporting, forensics, hardware, recovery, metadata, performance, system_cleanup, password_tools, device_manager, file_signatures) |
| **`filemanager/ui/`** | PyQt5 desktop shell, 14 built-in views, widget library, plugin loader |
| **`filemanager/ui/views/`** | Dashboard, Search, Duplicates, Action Builder, Tools, Media, System Cleanup, Performance, Recovery, Metadata, Hardware, Forensics, Settings, About |
| **`filemanager/ui/plugins/`** | Plugin system; bundled example: Metadata Cleaner plugin |
| **`tests/`** | 224 passing tests: comprehensive, integration, contract, new-modules suites |
| **`docs/`** | Architecture, CLI reference, GUI workflows, development guide, audit reviews |
| **`build/`, `dist/`** | Generated build artifacts (output only, not maintained source) |

## Architecture: Why It's Supercharged

DataForge is built in strict layers so the **same superpower logic runs in CLI and GUI** without duplication:

```
┌─────────────────────────────────────────────────────────────┐
│  CLI Superpowers           │  GUI Superpowers               │
│  🔨 17 commands            │  ⚡ 14 views + plugins         │
│  ⚙️ Scriptable             │  🎨 Interactive               │
│  📊 JSON/JSONL output      │  🎯 Visual workflow builder   │
└─────────┬────────────────────────────────────────┬─────────┘
          │    (Both access the same superpower core)        │
┌─────────▼────────────────────────────────────────▼─────────┐
│  🔍 Forensics  🧹 Cleanup  📦 Recovery  🎬 Media  ⚙️ Ops   │
│  (Shared Feature Modules — where the real magic lives)     │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  🚀 FileActionService — Batch Operations (move/copy/delete)│
│     ⚡ Parallel execution  🔄 Progress tracking            │
│     ✓ Dry-run preview     ⏸️ Cancellation support         │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  🛠️ Core Operations │ 🔎 Scanner │ ⚙️ Config │ 💾 Cache    │
│  (The foundation that makes it all work)                   │
└─────────────────────────────────────────────────────────────┘
```

**Why this supercharged architecture matters:**
- **Superpower consistency** — a forensic search works identically from `fm forensics --search-keyword` and the GUI Forensics view
- **Maintenance superpowers** — a bug fix or new feature in deduplication logic instantly benefits CLI, desktop, and Action Builder
- **Testing superpowers** — test the logic once, verify all three interfaces automatically
- **Extensibility superpowers** — new pipeline steps, new CLI commands, and new GUI views can be built faster

The **two user interfaces are thin adapters** — all the real superpowers live in shared modules, services, and the core operations layer.

## Project Status

### ✅ Fixed in the 2026-07-10 Audit Pass

- **Correctness** — 224 tests pass (was failing at collection). All correctness bugs fixed: MD5→SHA-256 defaults, symlink-loop scope escape, thread-safe cache, JSON error handling, SHA-512 crash, etc.
- **Security findings** — classified and tracked (open security items in audit report; fixable at identified seams)
- **Documentation** — ARCHITECTURE, CLI_REFERENCE, GUI_WORKFLOWS, DEVELOPMENT_GUIDE all verified against current PyQt5 source
- **Packaging** — setup.py and build_exe.py verified; release bundle working

### 🔄 Open / Future

- **Version control** — No git/CI yet. Putting the tree under git and running tests in CI is the highest-leverage next step (Phase 0 in audit roadmap).
- **Package namespace** — Internal code uses `filemanager/` package; product name is now DataForge. Package rename pending.
- **Device Manager GUI** — CLI has `fm devices`; no dedicated GUI view yet (lower priority, works via CLI).
- **Numbered release** — No public release number yet. `setup.py` has internal version `0.1.0` (development marker).
- **Debug build artifacts** — `build/debug` and `dist/debug` predate the PyQt5 migration; `build/release` is current. Run `python build_exe.py debug` to refresh.

### 📋 Security & Audit

Three open security findings (all detailed in audit report with severity, fix strategy):
- **S2** — Forensic HTML report does not escape interpolated data (stored XSS risk)
- **S4** — Trash restore trusts attacker-controlled `.trashinfo` paths (path-traversal risk)
- **S7** — System Cleanup blanket-classifies `/tmp` and cache trees as junk (data-loss risk under misuse)

See [`docs/reviews/02_SECURITY_AND_FORENSIC_AUDIT.md`](./docs/reviews/02_SECURITY_AND_FORENSIC_AUDIT.md) for severity, impact, and fixes.

## Developer & Deployment Notes

- **Nested repo** — Application code lives under `./FileManager/` subdirectory. Commands run from there.
- **Dependency split** — `setup.py` = CLI + core only. `requirements.txt` = full stack (GUI/media). Install both for development.
- **User data** — `~/.filemanager/config.json`, cache.db, app.log — all created on first run, no migration needed.
- **Build artifacts** — `build/` and `dist/` are generated; don't maintain them. `release` profile is current; refresh `debug` via `python build_exe.py debug`.
- **Next milestone** — Put under version control + wire CI/CD (see [`docs/reviews/04_IMPROVEMENTS_AND_ROADMAP.md`](./docs/reviews/04_IMPROVEMENTS_AND_ROADMAP.md), Phase 0).

---

## Contributing

DataForge is an open-source project. The audit and roadmap under [`docs/reviews/`](./docs/reviews/) identifies gaps, security enhancements, and feature requests. PRs are welcome — start with the [Development Guide](./docs/DEVELOPMENT_GUIDE.md) and the [Architecture](./docs/ARCHITECTURE.md) reference.

**For questions:**
- File an issue in the repository
- Check the [audit findings](./docs/reviews/01_CODE_REVIEW_AND_BUGS.md) — your question may be answered there
- Review the [CLI reference](./docs/CLI_REFERENCE.md) and [GUI workflows](./docs/GUI_WORKFLOWS.md) for usage

---

**DataForge: Professional File & System Intelligence** — unified CLI and desktop toolkit for discovery, organization, forensics, and recovery.
