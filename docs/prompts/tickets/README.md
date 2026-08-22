# Parallel Ticket Prompts — Index

> One file per ticket — pass the file for that ticket to an AI agent. Each agent works on ONE ticket only (one branch = one commit = one PR). Within a Wave, tickets have disjoint writes and can run **in parallel**; across Waves, run **sequentially** (wave gate).

**Generic prompt:** `../parallel-ticket-agent.md` / `../../../.github/prompts/parallel-ticket-agent.prompt.md` — set `{{TICKET_ID}}`.

> **Status 2026-08-22 22:00 UTC — Wave 0 ✅ 5/5, Wave 1 ✅ 9/9, Wave 2 ✅ 5/5, Wave 3 ✅ 4/4 DONE → Wave 4 🔜, Wave 5 ⏳**
> Wave 0 (69 tests) + Wave 1 (126 tests) + Wave 2 (98 tests) + Wave 3 (130 tests) = 423 tests green.
> **Overall: 23/25 DONE (92%) — 9 remaining (2 Wave 4 + 7 Wave 5).** See `docs/PARALLEL_BACKLOG.md` for full reviews.

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

### Wave 4 🔜 READY 2026-08-22 — Wave 3 ✅ 4/4 gate green, 2 disjoint, unblocked

- **TICK-401** — Replace single BackgroundWorker is_busy with JobManager + virtualized views | depends: "TICK-301", "TICK-304" | writes: `dataforge/ui/app.py`, `dataforge/ui/job_manager.py [NEW FILE]` → [`TICK-401.prompt.md`](./TICK-401.prompt.md)
- **TICK-402** — Centralize version bump (pyproject → __init__ → Info.plist/wxs) | depends: "TICK-001", "TICK-303" | writes: `scripts/bump_version.py [NEW FILE]`, `pyproject.toml` → [`TICK-402.prompt.md`](./TICK-402.prompt.md)

### Wave 5 — Hardening & UX (from AUDIT_REPORT/FORENSIC_REVIEW)

- **TICK-501** — Fix R-CORE-3/4/6: config persistence, cache null-guard, scanner error reporting | depends: — | writes: `dataforge/core/config.py`, `dataforge/core/cache.py`, `dataforge/core/scanner.py` → [`TICK-501.prompt.md`](./TICK-501.prompt.md)
- **TICK-502** — Move secure_delete to dedicated sanitisation module (F4) | depends: "TICK-304" | writes: `dataforge/modules/sanitisation.py [NEW FILE]`, `dataforge/modules/forensics.py` → [`TICK-502.prompt.md`](./TICK-502.prompt.md)
- **TICK-503** — Wire AuditLog into FileActionService (F1) | depends: "TICK-304" | writes: `dataforge/core/services/file_actions.py` → [`TICK-503.prompt.md`](./TICK-503.prompt.md)
- **TICK-504** — Fix tz-naive timestamps in non-forensic modules (F9) | depends: — | writes: `dataforge/modules/system_cleanup.py`, `dataforge/modules/search.py`, `dataforge/modules/recovery.py`, `dataforge/modules/integrity.py`, `dataforge/modules/performance.py`, `dataforge/ui/views/search.py` → [`TICK-504.prompt.md`](./TICK-504.prompt.md)
- **TICK-505** — Fix ingest_disk_image list materialisation (F14) | depends: "TICK-304" | writes: `dataforge/modules/forensics.py` → [`TICK-505.prompt.md`](./TICK-505.prompt.md)
- **TICK-506** — Virtualise timeline for >5k events (U3) | depends: — | writes: `dataforge/ui/views/forensics_view.py` → [`TICK-506.prompt.md`](./TICK-506.prompt.md)
- **TICK-507** — Add hex field inspector / HexView widget (U4) | depends: — | writes: `dataforge/ui/widgets.py` → [`TICK-507.prompt.md`](./TICK-507.prompt.md)

## Relevant Documentation Per Ticket

Each per-ticket file now includes a **Relevant Documentation — Must Read Before Coding** section tailored to its `scope` (e.g. `UI` → `GUI_WORKFLOWS.md`, `Core` → `TECHNICAL_SOURCE_OF_TRUTH.md` + `ARCHITECTURE.md`, `Modules` → `CLI_REFERENCE.md` + module-specific GUI workflow). The generic prompt also contains a domain→docs table (`docs/prompts/parallel-ticket-agent.md` §6). Always read the listed docs before editing and update them per `CONTRIBUTING.md §8` after editing.

## How to Use

### Sequential (default, safe)
```
Wave 0 (0.1→0.2→0.3→0.4→0.5) → Wave 1 (9 agents after Wave 0 green) → Wave 2 → Wave 3 → Wave 4 → Wave 5
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
