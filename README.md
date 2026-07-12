# 🔨 DataForge

## File System Management with Steroids and Superpowers

**Professional file and system intelligence platform** for power users, developers, and digital forensics specialists. Unified CLI + desktop experience for file discovery, organization, recovery, and forensic analysis.

DataForge provides both a **terminal interface** (`fm` CLI) and **interactive desktop application** (PyQt5 GUI) — same powerful toolkit, two workflows. Built around shared core services so your logic runs consistently anywhere.

> **What's inside:** Enterprise-grade duplicate detection, forensic carving, integrity verification, automated cleanup, media batch processing, hardware diagnostics, artifact parsing, and workflow automation — all in one streamlined, production-tested toolkit.

<div align="center">
  <img src="DataForgeLogo.jpeg" alt="DataForge Logo - File & System Intelligence" width="300" />
</div>

The GUI was migrated from Tkinter/ttkbootstrap to **PyQt5**, and new modules (hardware, forensics, recovery, metadata, performance, system cleanup, password tools, device manager, file signatures) were added. Documentation, packaging metadata, and CLI wiring have been reconciled to match. Remaining open items and a full audit are tracked in [`docs/reviews/NOTES_REVIEW.md`](./docs/reviews/NOTES_REVIEW.md).

## Why DataForge? (The Superpowers)

| Superpower | What You Get |
|---|---|
| **🎯 Find the noise** | Locate duplicates by content hash, search by name/size/age/content, parse forensic artifacts in seconds — find what matters, fast |
| **🧹 Clean and organize** | Batch operations, integrity snapshots, automated cleanup by category, one-click categorized organization — organize chaos in minutes |
| **🔍 Go deep into data** | Forensic file carving, GPS metadata stripping, disk SMART health, password strength analysis, trash recovery — extract what's hidden |
| **⚡ Unified interface** | Terminal and desktop — choose your workflow. Same features, same results, same safety standards — no tool switching |
| **🧩 Extensible** | Action Builder pipeline for custom multi-step workflows; plugin system for custom views; scriptable CLI — build your own workflows |
| **🛡️ Production-ready** | 254 passing tests, thread-safe batch operations, dry-run previews, cancellation support, detailed logging — trust the tool |
| **🚀 Automation at scale** | Parallel hashing, batch operations on thousands of files, configurable worker threads, progress tracking, cancellation — process like a pro |
| **🔐 Enterprise features** | Role-based experience levels (Basic/Advanced/Expert), audit logging, integrity verification, forensic reports — audit-ready |

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
| **Product** | 🔨 **DataForge** — File system management with steroids and superpowers (code: `dataforge/`) |
| **CLI** | `fm` command → `dataforge.cli:main` (17 commands, all powers available) |
| **GUI** | `python run_ui.py` → `dataforge.ui.app.DataForgeApp` (PyQt5, 14 views, drag-reorder pipeline) |
| **Config** | `~/.dataforge/config.json` (theme, performance, exclusions, dashboard paths, experience levels) |
| **Cache** | `~/.dataforge/cache.db` (SQLite hash cache, thread-safe with WAL, parallel hashing) |
| **Logging** | `~/.dataforge/app.log` (rotating, 5 MB / 3 backups, full audit trail) |
| **Architecture** | Layered: core primitives → operations → service layer → modules → GUI/CLI orchestration (shared logic, zero duplication) |
| **Tests** | 254 passing (`pytest`, full coverage across all feature layers, production-grade quality) |
| **Build** | `setup.py` (CLI/core), `build_exe.py` (PyInstaller → standalone desktop bundles, one-file release mode) |

## Quick Start

**For GUI users:** just install and run. **For developers/automation:** CLI all the way.

### Install

```bash
cd DataForge
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
PYTHONPATH=. python -m dataforge.cli --help
```

### Verify the Build

```bash
PYTHONPATH=. pytest -q  # 254 tests pass
```

Full test suite passes — 254 tests. All correctness fixes are verified. See [`docs/reviews/AUDIT_FINDINGS.md`](./docs/reviews/AUDIT_FINDINGS.md) and [`docs/reviews/NOTES_REVIEW.md`](./docs/reviews/NOTES_REVIEW.md) for the full audit.

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
- [`docs/TECHNICAL_SOURCE_OF_TRUTH.md`](./docs/TECHNICAL_SOURCE_OF_TRUTH.md) - authoritative file-by-file source map for maintainers

**Contributing:**
- [`docs/COMMIT_CONVENTION.md`](./docs/COMMIT_CONVENTION.md) - standardized commit message format and enforcement hook
- [`docs/VERSIONING.md`](./docs/VERSIONING.md) - semantic versioning rules and release process

### Project Review & Audit (2026-07-10)

A comprehensive engineering, security, and UX audit lives under [`docs/reviews/`](./docs/reviews/):

- **[`EXECUTIVE_SUMMARY.md`](./docs/reviews/EXECUTIVE_SUMMARY.md)** — start here: overview, findings index, remediation status, brand identity
- **[`AUDIT_FINDINGS.md`](./docs/reviews/AUDIT_FINDINGS.md)** — all code-correctness bugs (15 findings, all fixed) and security/forensic findings (13 findings, 2 fixed); forensic-soundness checklist, remediation order
- **[`IMPROVEMENT_PLAN.md`](./docs/reviews/IMPROVEMENT_PLAN.md)** — UX/UI review, visual design system, engineering improvements, phased roadmap with per-item implementation status (Phase 2a+2b shipped; 2c/2d/2e open)

## Directory Structure

| Path | Purpose |
| --- | --- |
| **`run_ui.py`** | Desktop GUI entry point (PyQt5 application launcher) |
| **`build_exe.py`** | PyInstaller bundler for standalone executables (release/debug) |
| **`dataforge/cli.py`** | 17 CLI commands via Click (scan, dupes, search, organize, rename, clean, usage, integrity, cleanup, performance, recover, metadata, hardware, forensics, hash-calc, devices) |
| **`dataforge/core/`** | Shared foundation: file model, scanner, config, cache, hasher, logger, operations layer |
| **`dataforge/core/services/`** | `FileActionService` — centralized batch file operations (move, copy, delete, rename, archive with progress/cancel/dry-run) |
| **`dataforge/core/actions/`** | Action Builder pipeline engine: filters, IO steps, transformations, media operations |
| **`dataforge/modules/`** | Feature implementations (search, duplicates, organizer, cleaner, integrity, usage, reporting, forensics, hardware, recovery, metadata, performance, system_cleanup, password_tools, device_manager, file_signatures) |
| **`dataforge/ui/`** | PyQt5 desktop shell, 14 built-in views, widget library, plugin loader, design-token module (`theme_tokens.py`) |
| **`dataforge/ui/views/`** | Dashboard, Search, Duplicates, Action Builder, Tools, Media, System Cleanup, Performance, Recovery, Metadata, Hardware, Forensics, Settings, About |
| **`dataforge/ui/plugins/`** | Plugin system; bundled example: Metadata Cleaner plugin |
| **`tests/`** | 254 passing tests: comprehensive, integration, contract, new-modules suites, token-regression guard |
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

- **Correctness** — 254 tests pass. All correctness bugs fixed: MD5→SHA-256 defaults, symlink-loop scope escape, thread-safe cache, JSON error handling, SHA-512 crash, etc.
- **UI/UX overhaul** — Phase 2a/2b shipped: surface brightness fix, themed checkboxes/combos, design-token module (`ui/theme_tokens.py`) with AA-validated colours replacing three legacy colour vocabularies, type-scale constants, per-widget colour migration.
- **Security findings** — classified and tracked (open security items in audit report; fixable at identified seams)
- **Documentation** — ARCHITECTURE, CLI_REFERENCE, GUI_WORKFLOWS, DEVELOPMENT_GUIDE all verified against current PyQt5 source
- **Packaging** — setup.py and build_exe.py verified; release bundle working

### 🔄 Open / Future

- **CI** — The tree is under git, but tests don't run in CI yet. Wiring CI is the highest-leverage next step (Phase 0 in audit roadmap).
- **Device Manager GUI** — CLI has `fm devices`; no dedicated GUI view yet (lower priority, works via CLI).
- **Numbered release** — No public release number yet. `setup.py` has internal version `0.1.0` (development marker).
- **Debug build artifacts** — `build/debug` and `dist/debug` predate the PyQt5 migration; `build/release` is current. Run `python build_exe.py debug` to refresh.

### 📋 Security & Audit

Three open security findings (all detailed in audit report with severity, fix strategy):
- **S2** — Forensic HTML report does not escape interpolated data (stored XSS risk)
- **S4** — Trash restore trusts attacker-controlled `.trashinfo` paths (path-traversal risk)
- **S7** — System Cleanup blanket-classifies `/tmp` and cache trees as junk (data-loss risk under misuse)

See [`docs/reviews/AUDIT_FINDINGS.md`](./docs/reviews/AUDIT_FINDINGS.md) for severity, impact, and fixes.

## Developer & Deployment Notes

- **Repo layout** — The Python package lives in `dataforge/` at the repository root. Run commands from the repo root.
- **Dependency split** — `setup.py` = CLI + core only. `requirements.txt` = full stack (GUI/media). Install both for development.
- **User data** — `~/.dataforge/config.json`, cache.db, app.log — all created on first run, no migration needed.
- **Build artifacts** — `build/` and `dist/` are generated; don't maintain them. `release` profile is current; refresh `debug` via `python build_exe.py debug`.
- **Next milestone** — Put under version control + wire CI/CD (see [`docs/reviews/IMPROVEMENT_PLAN.md`](./docs/reviews/IMPROVEMENT_PLAN.md), Phase 0).

---

## Contributing

DataForge is an open-source project. The audit and roadmap under [`docs/reviews/`](./docs/reviews/) identifies gaps, security enhancements, and feature requests. PRs are welcome — start with the [Development Guide](./docs/DEVELOPMENT_GUIDE.md) and the [Architecture](./docs/ARCHITECTURE.md) reference.

**For questions:**
- File an issue in the repository
- Check the [audit findings](./docs/reviews/AUDIT_FINDINGS.md) — your question may be answered there
- Review the [CLI reference](./docs/CLI_REFERENCE.md) and [GUI workflows](./docs/GUI_WORKFLOWS.md) for usage

---

**DataForge: Professional File & System Intelligence** — unified CLI and desktop toolkit for discovery, organization, forensics, and recovery.
