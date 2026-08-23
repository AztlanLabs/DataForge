# Parallel Ticket Prompts — Index

> One file per ticket — pass the file for that ticket to an AI agent. Each agent works on ONE ticket only (one branch = one commit = one PR). Within a Wave, tickets have disjoint writes and can run **in parallel**; across Waves, run **sequentially** (wave gate).

**Generic prompt:** `../parallel-ticket-agent.md` / `../../../.github/prompts/parallel-ticket-agent.prompt.md` — set `{{TICKET_ID}}`.

> **Status 2026-08-23 09:00 UTC — Wave 0 ✅ 5/5, Wave 1 ✅ 9/9, Wave 2 ✅ 5/5, Wave 3 ✅ 4/4, Wave 4 ✅ 2/2, Wave 5 ✅ 11/11, Wave 6 ✅ 1/1, Wave 7 ✅ 8/8 DONE — Wave 8 🔜 READY (8 tickets, 24 disjoint)**
> Wave 0 (69) + Wave 1 (126) + Wave 2 (98) + Wave 3 (130) + Wave 4 (635) + Wave 5 (142, +2 skipped) + Wave 6 (13) + Wave 7 (128, +1 skipped) = 1341 tests green (all `validation_command` green, file parity verified). Wave 7 closed 13 orphaned gaps + 3 proposal features (8/8), Wave 8 now ready for 8 next user issues (renamer, STOP, icons, cache, menus, automation, memory, hardware). See `docs/PARALLEL_BACKLOG.md` Wave 0–7 Reviews (8/8) + Wave 8 Spec.
> **Overall: 45/53 DONE (85%) — 8 remaining (Wave 8).**

## Execution Order (Wave DAG)

### Wave 0 ✅ DONE 2026-08-22 (5/5 — `tests/test_*_contract.py` 69/69, verified)

- **TICK-001** ✅ DONE — Define canonical paths (platformdirs) and single version source | depends: — | writes: `dataforge/core/paths.py [NEW FILE]`, `dataforge/__init__.py`, `dataforge/core/__init__.py` → [`TICK-001.prompt.md`](./TICK-001.prompt.md)
- **TICK-002** ✅ DONE — Expand FileProvider ABC and FileEntry for hardlink/sparse/inode awareness | depends: — | writes: `dataforge/core/provider.py`, `dataforge/core/common.py` → [`TICK-002.prompt.md`](./TICK-002.prompt.md)
- **TICK-003** ✅ DONE — Define engine API schemas (Scan/Search/Dupes/Hash/Integrity) and transport ABC | depends: — | writes: `dataforge/api/__init__.py [NEW FILE]`, `dataforge/api/schema.py [NEW FILE]`, `dataforge/api/transport/__init__.py [NEW FILE]`, `dataforge/api/transport/base.py [NEW FILE]` → [`TICK-003.prompt.md`](./TICK-003.prompt.md)
- **TICK-004** ✅ DONE — Add CONFIG_SCHEMA_VERSION, cache PRAGMA user_version, set_hash_many sig, and adaptive worker defaults | depends: "TICK-001" | writes: `dataforge/core/config.py`, `dataforge/core/cache.py`, `dataforge/engine/__init__.py [NEW FILE]`, `dataforge/engine/migrations/README.md [NEW FILE]` → [`TICK-004.prompt.md`](./TICK-004.prompt.md)
- **TICK-005** ✅ DONE — Define Job model (id, provider, params, cancel_token, progress_callback, results) | depends: "TICK-003" | writes: `dataforge/engine/jobs.py [NEW FILE]`, `dataforge/engine/daemon.py [NEW FILE]` → [`TICK-005.prompt.md`](./TICK-005.prompt.md)

### Wave 1 ✅ DONE 2026-08-22 17:15 UTC (9/9 — 126 tests, 9/9 validation_command green)

- **TICK-101** ✅ DONE — Route console logger to stderr so CLI JSON stays clean | depends: "TICK-004" | writes: `dataforge/core/logger.py` → [`TICK-101.prompt.md`](./TICK-101.prompt.md)
- **TICK-102** ✅ DONE — Replace recursive yield-from walk with parallel BFS + DirEntry.stat reuse + inode fields | depends: "TICK-002" | writes: `dataforge/core/scanner.py` → [`TICK-102.prompt.md`](./TICK-102.prompt.md)
- **TICK-103** ✅ DONE — Switch hasher to 1 MiB blocks + mmap for large files | depends: "TICK-002" | writes: `dataforge/core/hasher.py` → [`TICK-103.prompt.md`](./TICK-103.prompt.md)
- **TICK-104** ✅ DONE — Batch cache writes + WAL pragmas + composite index (impl for TICK-004 contract) | depends: "TICK-004" | writes: `dataforge/core/cache.py` → [`TICK-104.prompt.md`](./TICK-104.prompt.md)
- **TICK-105** ✅ DONE — Fix collision O(N²), prune empty-dest, and case-only rename on case-insensitive FS | depends: "TICK-002" | writes: `dataforge/core/operations/files.py` → [`TICK-105.prompt.md`](./TICK-105.prompt.md)
- **TICK-106** ✅ DONE 2026-08-22 — Make search content path parallel, mmap-based, and shared with forensics | depends: "TICK-003" | writes: `dataforge/modules/search.py` → [`TICK-106.prompt.md`](./TICK-106.prompt.md)
- **TICK-107** ✅ DONE 2026-08-22 — Pipeline dupes: streaming size-map → fast-hash → full-hash with verify | depends: "TICK-003" | writes: `dataforge/modules/duplicates.py` → [`TICK-107.prompt.md`](./TICK-107.prompt.md)
- **TICK-108** ✅ DONE 2026-08-22 — Stream integrity create/verify instead of materializing file lists | depends: "TICK-003" | writes: `dataforge/modules/integrity.py` → [`TICK-108.prompt.md`](./TICK-108.prompt.md)
- **TICK-109** ✅ DONE 2026-08-22 — Make forensics calc_hashes/keyword_search share streaming engine + byte budget | depends: "TICK-003" | writes: `dataforge/modules/forensics.py` → [`TICK-109.prompt.md`](./TICK-109.prompt.md)

### Wave 2 ✅ DONE 2026-08-22 19:00 UTC (5/5 — 98 tests, 5/5 validation_command green)

- **TICK-201** ✅ DONE 2026-08-22 — Parallelize FileActionService + fix single-mode zip abort/partial | depends: "TICK-105", "TICK-102" | writes: `dataforge/core/services/file_actions.py` → [`TICK-201.prompt.md`](./TICK-201.prompt.md)
- **TICK-202** ✅ DONE 2026-08-22 — Parallelize carving: mmap image, sliding-window scan, chunked workers | depends: "TICK-102", "TICK-103" | writes: `dataforge/modules/recovery.py` → [`TICK-202.prompt.md`](./TICK-202.prompt.md)
- **TICK-203** ✅ DONE 2026-08-22 — Dedupe cleanup walks and reuse parallel scanner | depends: "TICK-102" | writes: `dataforge/modules/system_cleanup.py` → [`TICK-203.prompt.md`](./TICK-203.prompt.md)
- **TICK-204** ✅ DONE 2026-08-22 — Consolidate metadata cleaning to MetadataEngine (keep cleaner.py as shim) | depends: "TICK-003" | writes: `dataforge/modules/metadata.py` → [`TICK-204.prompt.md`](./TICK-204.prompt.md)
- **TICK-205** ✅ DONE 2026-08-22 — Implement UDS (Linux/macOS) + Named Pipes (Windows) transports | depends: "TICK-003", "TICK-005" | writes: `dataforge/api/transport/uds.py [NEW FILE]`, `dataforge/api/transport/named_pipe.py [NEW FILE]` → [`TICK-205.prompt.md`](./TICK-205.prompt.md)

### Wave 3 ✅ DONE 2026-08-22 20:00 UTC (4/4 — 130 tests, 4/4 validation_command green)

- **TICK-301** ✅ DONE 2026-08-22 — Wire daemon job queue + client auto-discover (consolidation) | depends: "TICK-205", "TICK-201" | writes: `dataforge/engine/daemon.py`, `dataforge/client/__init__.py [NEW FILE]`, `dataforge/client/sync.py [NEW FILE]`, `dataforge/service/__main__.py [NEW FILE]` → [`TICK-301.prompt.md`](./TICK-301.prompt.md)
- **TICK-302** ✅ DONE 2026-08-22 — Install service lifecycle files (systemd user service + socket, launchd plist, Windows Service) | depends: "TICK-301" | writes: `dataforge/service/linux/dataforge.socket [NEW FILE]`, `dataforge/service/linux/dataforge.service [NEW FILE]`, `dataforge/service/linux/com.dataforge.Engine.service [NEW FILE]`, `dataforge/service/windows/service.py [NEW FILE]`, `dataforge/service/windows/install.py [NEW FILE]`, `dataforge/service/macos/com.dataforge.engine.plist [NEW FILE]` → [`TICK-302.prompt.md`](./TICK-302.prompt.md)
- **TICK-303** ✅ DONE 2026-08-22 — Produce onefile (portable) + onedir (package) + nfpm deb/rpm | depends: "TICK-001" | writes: `build_exe.py`, `packaging/nfpm.yaml [NEW FILE]`, `packaging/README.md [NEW FILE]` → [`TICK-303.prompt.md`](./TICK-303.prompt.md)
- **TICK-304** ✅ DONE 2026-08-22 — Add hash-chained audit log, CaseContext, and Evidence Mode gate (F1–F3/U2 + F9) | depends: "TICK-005", "TICK-109" | writes: `dataforge/core/audit.py [NEW FILE]`, `dataforge/core/case.py [NEW FILE]`, `dataforge/modules/forensics.py` → [`TICK-304.prompt.md`](./TICK-304.prompt.md)

### Wave 4 ✅ DONE 2026-08-22 22:30 UTC (2/2 — 635 tests, 2/2 validation_command green)

- **TICK-401** ✅ DONE 2026-08-22 — Replace single BackgroundWorker is_busy with JobManager + virtualized views | depends: "TICK-301", "TICK-304" | writes: `dataforge/ui/app.py`, `dataforge/ui/job_manager.py [NEW FILE]` → [`TICK-401.prompt.md`](./TICK-401.prompt.md)
- **TICK-402** ✅ DONE 2026-08-22 — Centralize version bump (pyproject → __init__ → Info.plist/wxs) | depends: "TICK-001", "TICK-303" | writes: `scripts/bump_version.py [NEW FILE]`, `pyproject.toml` → [`TICK-402.prompt.md`](./TICK-402.prompt.md)

### Wave 5 ✅ DONE 2026-08-23 06:00 UTC (11/11 — 142 tests, +2 skipped, 11/11 validation_command green)

- **TICK-501** ✅ DONE 2026-08-23 — Fix R-CORE-3/4/6: config persistence, cache null-guard, scanner error reporting | depends: — | writes: `dataforge/core/config.py`, `dataforge/core/cache.py`, `dataforge/core/scanner.py` → [`TICK-501.prompt.md`](./TICK-501.prompt.md)
- **TICK-502** ✅ DONE 2026-08-23 — Move secure_delete to dedicated sanitisation module (F4) | depends: "TICK-304" | writes: `dataforge/modules/sanitisation.py [NEW FILE]`, `dataforge/modules/forensics.py` *(sole Wave 5 writer to `forensics.py`)* → [`TICK-502.prompt.md`](./TICK-502.prompt.md)
- **TICK-503** ✅ DONE 2026-08-23 — Wire AuditLog into FileActionService (F1) | depends: "TICK-304" | writes: `dataforge/core/services/file_actions.py` → [`TICK-503.prompt.md`](./TICK-503.prompt.md)
- **TICK-504** ✅ DONE 2026-08-23 — Fix tz-naive timestamps in non-forensic modules (F9 remainder) | depends: — | writes: `dataforge/modules/system_cleanup.py`, `dataforge/modules/search.py`, `dataforge/modules/recovery.py`, `dataforge/modules/integrity.py`, `dataforge/modules/performance.py`, `dataforge/ui/views/search.py` → [`TICK-504.prompt.md`](./TICK-504.prompt.md)
- **TICK-506** ✅ DONE 2026-08-23 — Virtualise timeline for >5k events (U3) | depends: — | writes: `dataforge/ui/views/forensics_view.py` → [`TICK-506.prompt.md`](./TICK-506.prompt.md)
- **TICK-507** ✅ DONE 2026-08-23 — Add hex field inspector / HexView widget (U4) | depends: — | writes: `dataforge/ui/widgets.py` → [`TICK-507.prompt.md`](./TICK-507.prompt.md)
- **TICK-508** ✅ DONE 2026-08-23 — Forensic engine: image_io (E01/AFF4) + streams (ADS/xattrs/MotW) + indicators (YARA/SSDEEP/NSRL) (F5 + F7 + F8) | depends: "TICK-002", "TICK-102", "TICK-103" | writes: `dataforge/core/image_io.py [NEW FILE]`, `dataforge/core/streams.py [NEW FILE]`, `dataforge/modules/indicators.py [NEW FILE]` → [`TICK-508.prompt.md`](./TICK-508.prompt.md)
- **TICK-509** ✅ DONE 2026-08-23 — Plugin loader isolation (subprocess + signing) (F12 remainder) | depends: "TICK-401" | writes: `dataforge/ui/plugin_loader.py` → [`TICK-509.prompt.md`](./TICK-509.prompt.md)
- **TICK-510** ✅ DONE 2026-08-23 — Hash-chain app.log (extends AuditLog chain) (F11 remainder) | depends: "TICK-101", "TICK-304" | writes: `dataforge/core/logger.py` → [`TICK-510.prompt.md`](./TICK-510.prompt.md)
- **TICK-511** ✅ DONE 2026-08-23 — Parser ProcessPool isolation (F13) | depends: "TICK-301" | writes: `dataforge/engine/parsers.py [NEW FILE]` → [`TICK-511.prompt.md`](./TICK-511.prompt.md)
- **TICK-512** ✅ DONE 2026-08-23 — Docs cross-platform claim fix for --parse-artifacts + trash (U10 + U11) | depends: "TICK-202" | writes: `docs/CLI_REFERENCE.md`, `README.md`, `docs/GUI_WORKFLOWS.md`, `dataforge/ui/views/about.py` → [`TICK-512.prompt.md`](./TICK-512.prompt.md)

### Wave 6 ✅ DONE 2026-08-23 06:00 UTC (1/1 — 13 tests, 1/1 validation_command green)

- **TICK-505** ✅ DONE 2026-08-23 — Fix ingest_disk_image list materialisation (F14) | depends: "TICK-502", "TICK-304" | writes: `dataforge/modules/forensics.py` *(sole Wave 6 writer — sequential re-entry after TICK-502 Wave 5)* → [`TICK-505.prompt.md`](./TICK-505.prompt.md)

### Wave 7 ✅ DONE 2026-08-23 09:00 UTC (8/8 — 128 tests, +1 skipped, 8/8 validation_command green)

- **TICK-701** ✅ DONE 2026-08-23 — R-CORE-2/5: config item validation + cache batch commit | depends: — | writes: `dataforge/core/config.py`, `dataforge/core/cache.py` → [`TICK-701.prompt.md`](./TICK-701.prompt.md)
- **TICK-702** ✅ DONE 2026-08-23 — R-CORE-7: logger makedirs bare filename guard | depends: — | writes: `dataforge/core/logger.py` → [`TICK-702.prompt.md`](./TICK-702.prompt.md)
- **TICK-703** ✅ DONE 2026-08-23 — F10/F16/F21: Unicode NFC/NFD + bidi, sparse, reflink dedup | depends: — | writes: `dataforge/core/common.py`, `dataforge/core/scanner.py`, `dataforge/core/hasher.py`, `dataforge/modules/duplicates.py` → [`TICK-703.prompt.md`](./TICK-703.prompt.md)
- **TICK-704** ✅ DONE 2026-08-23 — F20: locked/in-use files skipped (VSS / acquire) | depends: — | writes: `dataforge/core/acquire.py [NEW FILE]`, `dataforge/modules/recovery.py` → [`TICK-704.prompt.md`](./TICK-704.prompt.md)
- **TICK-705** ✅ DONE 2026-08-23 — U5-U9: UX polish — mismatch, glyph, preview, DnD, keyboard | depends: — | writes: `dataforge/ui/theme_tokens.py`, `dataforge/ui/views/base.py`, `dataforge/ui/widgets.py`, `dataforge/ui/views/forensics_view.py`, `dataforge/modules/forensics.py` → [`TICK-705.prompt.md`](./TICK-705.prompt.md)
- **TICK-706** ✅ DONE 2026-08-23 — Engine FTS index + incremental watch (PERF E) | depends: — | writes: `dataforge/engine/index.py [NEW FILE]` → [`TICK-706.prompt.md`](./TICK-706.prompt.md)
- **TICK-707** ✅ DONE 2026-08-23 — HTTP gateway + D-Bus/XPC/COM (NATIVE N2/N3) | depends: — | writes: `dataforge/api/transport/http_gateway.py [NEW FILE]` → [`TICK-707.prompt.md`](./TICK-707.prompt.md)
- **TICK-708** ✅ DONE 2026-08-23 — Packaging msi/dmg + version sync + native helper (I2+N4) | depends: — | writes: `packaging/wix/Product.wxs [NEW FILE]`, `packaging/dmg/create-dmg.sh [NEW FILE]`, `pyproject.toml`, `dataforge/__init__.py` → [`TICK-708.prompt.md`](./TICK-708.prompt.md)

### Wave 8 🔜 READY 2026-08-23 — Wave 7 gate, 8 disjoint, unblocked (user-reported 2026-08-23)

> **Goal:** Next user issues: bulk renamer, STOP comprehensive, view icons, cache info, context menus, automation store, UI memory, hardware crash.

- **TICK-801** — Bulk Renamer update functionality | depends: — | writes: `dataforge/modules/renamer.py`, `dataforge/ui/views/tools.py` → [`TICK-801.prompt.md`](./TICK-801.prompt.md)
- **TICK-802** — STOP comprehensive — review entire code cancel paths | depends: — | writes: `dataforge/ui/job_manager.py`, `dataforge/engine/jobs.py` → [`TICK-802.prompt.md`](./TICK-802.prompt.md)
- **TICK-803** — Icons for forensic, file recovery, Metadata exif (weird x/?) | depends: — | writes: `dataforge/ui/resources/icons.py`, `dataforge/ui/views/forensics_view.py`, `dataforge/ui/views/recovery_view.py`, `dataforge/ui/views/metadata_view.py` → [`TICK-803.prompt.md`](./TICK-803.prompt.md)
- **TICK-804** — Settings Performance DB Cache info + size | depends: — | writes: `dataforge/ui/views/settings.py`, `dataforge/core/cache.py`, `dataforge/modules/performance.py` → [`TICK-804.prompt.md`](./TICK-804.prompt.md)
- **TICK-805** — Right click context menus per window | depends: — | writes: `dataforge/ui/views/base.py`, `dataforge/ui/widgets.py`, `dataforge/ui/views/search.py`, `dataforge/ui/views/storage_devices.py` → [`TICK-805.prompt.md`](./TICK-805.prompt.md)
- **TICK-806** — Automation store custom automations | depends: — | writes: `dataforge/ui/views/automations.py`, `dataforge/ui/views/action_builder.py`, `dataforge/engine/daemon.py` → [`TICK-806.prompt.md`](./TICK-806.prompt.md)
- **TICK-807** — Memory remember checkboxes/selections/names | depends: — | writes: `dataforge/core/config.py`, `dataforge/core/paths.py`, `dataforge/ui/views/system_cleanup.py` → [`TICK-807.prompt.md`](./TICK-807.prompt.md)
- **TICK-808** — Hardware section crash SIGSEGV (scan comprehensive + storage + hardware) | depends: — | writes: `dataforge/ui/views/hardware_view.py`, `dataforge/modules/hardware.py`, `dataforge/ui/app.py` → [`TICK-808.prompt.md`](./TICK-808.prompt.md)

## Relevant Documentation Per Ticket

Each per-ticket file now includes a **Relevant Documentation — Must Read Before Coding** section tailored to its `scope` (e.g. `UI` → `GUI_WORKFLOWS.md`, `Core` → `TECHNICAL_SOURCE_OF_TRUTH.md` + `ARCHITECTURE.md`, `Modules` → `CLI_REFERENCE.md` + module-specific GUI workflow). The generic prompt also contains a domain→docs table (`docs/prompts/parallel-ticket-agent.md` §6). Always read the listed docs before editing and update them per `CONTRIBUTING.md §8` after editing.

## How to Use

### Sequential (default, safe)
```
Wave 0 (0.1→0.2→0.3→0.4→0.5) → Wave 1 (9 agents after Wave 0 green) → Wave 2 → Wave 3 → Wave 4 → Wave 5 (11 parallel) → Wave 6 (1 sequential re-entry) → Wave 7 (8 parallel) → Wave 8 (8 parallel) → Wave 9+ (STOP full sweep)
```

### Parallel within a Wave
```bash
# Terminal A
cat docs/prompts/tickets/TICK-101.prompt.md | pbcopy  # pass to agent A
# Terminal B (concurrent, same Wave, different file)
cat docs/prompts/tickets/TICK-102.prompt.md | pbcopy  # pass to agent B
# Both agents run concurrently — no file collision by design (hardened disjoint guarantee)
```

### Example — assign TICK-102
```bash
git checkout develop && git pull origin develop
git checkout -b feat/TICK-102-parallel-scanner
# give agent docs/prompts/tickets/TICK-102.prompt.md
```

See `docs/PARALLEL_BACKLOG.md#how-to-work-a-ticket--sequential-and-parallel-execution-guide` for full rebase/CI/DOD checklist.

## Alias Map
`PERF-100→TICK-004`, `PERF-101→TICK-102`, `PERF-102→TICK-103`, `PERF-103→TICK-104`, `PERF-104→TICK-107`, `PERF-105→TICK-106`, `PERF-106→TICK-108`, `PERF-107→TICK-109`, `PERF-108→TICK-202`, `PERF-109→TICK-203`, `PERF-110→TICK-201`, `PERF-111→TICK-105`, `PERF-112→TICK-401` — never run twin same wave.
