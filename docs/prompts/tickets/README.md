# Parallel Ticket Prompts — Index

> One file per ticket — pass the file for that ticket to an AI agent. Each agent works on ONE ticket only (one branch = one commit = one PR). Within a Wave, tickets have disjoint writes and can run **in parallel**; across Waves, run **sequentially** (wave gate).

**Generic prompt:** `../parallel-ticket-agent.md` / `../../../.github/prompts/parallel-ticket-agent.prompt.md` — set `{{TICKET_ID}}`.

> **Status 2026-08-23 12:00 UTC — Wave 0 ✅ 5/5, Wave 1 ✅ 9/9, Wave 2 ✅ 5/5, Wave 3 ✅ 4/4, Wave 4 ✅ 2/2, Wave 5 ✅ 11/11, Wave 6 ✅ 1/1, Wave 7 ✅ 8/8, Wave 8 ✅ 7/8 DONE (1 remaining TICK-804), Wave 9 🔜 0/8 READY, Wave 10 🔜 0/3 READY, Wave 11 🔜 0/5 READY, Wave 12 🔜 0/8 READY, Wave 13 🔜 0/4 READY, Wave 14 🔜 0/5 READY**
> Wave 0 (69) + Wave 1 (126) + Wave 2 (98) + Wave 3 (130) + Wave 4 (635) + Wave 5 (142, +2 skipped) + Wave 6 (13) + Wave 7 (128, +1 skipped) + Wave 8 (65, 7/8) + Wave 9 (0/8) + Wave 10 (0/3) + Wave 11 (0/5) + Wave 12 (0/8) + Wave 13 (0/4) + Wave 14 (0/5) = 1406 tests green + 34 READY (Wave 9-14). See `docs/PARALLEL_BACKLOG.md` Wave 9-14 Concurrency Map.
> **Overall: 52/86 DONE (60%) — 34 remaining (TICK-804 + 901-908 + 911-913 + 914-918 + 919-926 + 927-930 + 931-935).**

## Execution Order (Wave DAG) — Completed tickets archived

> **Note 2026-08-23 11:00 UTC:** All completed tickets (Wave 0–7 45/45 DONE + Wave 8 7/8 DONE) have been **deleted from HEAD** (52 prompt files removed from `docs/prompts/tickets/` and `.github/prompts/tickets/`) and are preserved in git history (`git log --all --oneline --grep=TICK-`). Only open tickets remain as files. See `docs/PARALLEL_BACKLOG.md` Wave 0–10 Reviews for full historical record and `git show <commit>:docs/prompts/tickets/TICK-XXX.prompt.md` to retrieve any deleted prompt.

### Open Tickets — Wave 8 (1 remaining, 1 branch not yet merged)

- **TICK-804** — Settings Performance DB Cache info + size | depends: — | writes: `dataforge/ui/views/settings.py`, `dataforge/core/cache.py`, `dataforge/modules/performance.py` → [`TICK-804.prompt.md`](./TICK-804.prompt.md) *(1 remaining — `feat/TICK-804-cache-info` branch, not yet merged)*

### Open Tickets — Wave 9: Stability Hotfix (8 READY, 8 parallel disjoint)

- **TICK-901** — Hardware QPainter/SIGSEGV deep hardening | writes: `dataforge/ui/views/hardware_view.py`, `dataforge/modules/hardware.py` → [`TICK-901.prompt.md`](./TICK-901.prompt.md) *(viewporter + debounce + cancel)*
- **TICK-902** — Metadata EXIF cross-device & 0 succeeded | writes: `dataforge/modules/metadata.py`, `dataforge/modules/cleaner.py`, `dataforge/ui/views/metadata_view.py` → [`TICK-902.prompt.md`](./TICK-902.prompt.md) *(EXDEV Invalid link)*
- **TICK-903** — MediaTools PDF/Image rework + preview + malloc | writes: `dataforge/core/media_ops.py`, `dataforge/ui/views/media.py` → [`TICK-903.prompt.md`](./TICK-903.prompt.md) *(merge/split/compress/convert)*
- **TICK-904** — Duplicate finder SIGSEGV hashing | writes: `dataforge/modules/duplicates.py`, `dataforge/core/hasher.py` → [`TICK-904.prompt.md`](./TICK-904.prompt.md) *(Hashing 33 SIGSEGV)*
- **TICK-905** — Junk scan SIGSEGV + permission QBackingStore | writes: `dataforge/modules/system_cleanup.py`, `dataforge/core/scanner.py`, `dataforge/ui/views/system_cleanup.py` → [`TICK-905.prompt.md`](./TICK-905.prompt.md) *(systemd-private)*
- **TICK-906** — FilePreviewPanel malloc/QPainter isolation | writes: `dataforge/ui/widgets.py` → [`TICK-906.prompt.md`](./TICK-906.prompt.md) *(unsorted double linked list)*
- **TICK-907** — Automations collapsible store UX | writes: `dataforge/ui/views/automations.py`, `dataforge/ui/views/action_builder.py` → [`TICK-907.prompt.md`](./TICK-907.prompt.md) *(saved space)*
- **TICK-908** — Global cursor pointers + app QPainter hardening | writes: `dataforge/ui/app.py`, `dataforge/ui/views/base.py`, `dataforge/ui/theme_tokens.py` → [`TICK-908.prompt.md`](./TICK-908.prompt.md) *(pointer same)*

### Open Tickets — Wave 10: Quality (3 READY, depends on Wave 9)

- **TICK-911** — Global stability audit + job lifecycle hardening | depends: Wave 9 | writes: `dataforge/ui/job_manager.py`, `dataforge/engine/jobs.py`, `dataforge/engine/daemon.py` → [`TICK-911.prompt.md`](./TICK-911.prompt.md) *(entire app broken review)*
- **TICK-912** — Test consolidation + deprecated prune | depends: Wave 9 | writes: `tests/test_comprehensive.py`, `tests/test_integration.py`, `tests/test_contract_regressions.py`, `tests/test_new_modules.py`, `tests/verify_scenarios.py`, `scripts/tests_consolidate.py` → [`TICK-912.prompt.md`](./TICK-912.prompt.md) *(merge tests)*
- **TICK-913** — Dead code prune + unused paths | depends: Wave 9 | writes: `dataforge/modules/organizer.py`, `dataforge/modules/reporting.py`, `dataforge/modules/usage.py`, `dataforge/modules/password_tools.py`, `dataforge/modules/file_signatures.py`, `dataforge/modules/device_manager.py`, `dataforge/core/utils.py` → [`TICK-913.prompt.md`](./TICK-913.prompt.md) *(dead code)*

### Open Tickets — Wave 11: Critical Stability (5 READY, depends on Wave 9+10)

- **TICK-914** — Progress callback safety + QThread lifecycle | depends: Wave 10 | writes: `dataforge/ui/job_manager.py` → [`TICK-914.prompt.md`](./TICK-914.prompt.md) *(cross-thread widget mutation, deleteLater on running thread)*
- **TICK-915** — Job engine: max_workers, cancellation, state | depends: TICK-914 | writes: `dataforge/engine/jobs.py` → [`TICK-915.prompt.md`](./TICK-915.prompt.md) *(unbounded QThreads, cancelled jobs execute, state races)*
- **TICK-916** — File actions: parallel exceptions, cancellation | depends: TICK-915 | writes: `dataforge/core/services/file_actions.py` → [`TICK-916.prompt.md`](./TICK-916.prompt.md) *(dropped exceptions, temp file safety)*
- **TICK-917** — Evidence mode at mutation boundary + app shutdown | depends: TICK-914 | writes: `dataforge/ui/app.py`, `dataforge/core/case.py` → [`TICK-917.prompt.md`](./TICK-917.prompt.md) *(bypassable evidence mode, no closeEvent)*
- **TICK-918** — Forensics + API schema fixes | depends: TICK-915 | writes: `dataforge/modules/forensics.py`, `dataforge/api/schema.py` → [`TICK-918.prompt.md`](./TICK-918.prompt.md) *(profiling AttributeError, progress sentinel, timeline atime)*

### Open Tickets — Wave 12: Operation Correctness (8 READY, depends on Wave 11)

- **TICK-919** — Core operations: result contract, rename confinement | depends: Wave 11 | writes: `dataforge/core/operations/files.py` → [`TICK-919.prompt.md`](./TICK-919.prompt.md) *(unified report, path escape prevention)*
- **TICK-920** — Media ops: PDF/image correctness, atomic output | depends: Wave 11 | writes: `dataforge/core/media_ops.py` → [`TICK-920.prompt.md`](./TICK-920.prompt.md) *(merge/split/compress/convert bugs)*
- **TICK-921** — Metadata: PNG write, exiftool detection, capabilities | depends: Wave 11 | writes: `dataforge/modules/metadata.py`, `dataforge/modules/cleaner.py` → [`TICK-921.prompt.md`](./TICK-921.prompt.md) *(PNG PngInfo, capability model)*
- **TICK-922** — Search + Duplicates: stale state, validation | depends: Wave 11 | writes: `dataforge/modules/search.py`, `dataforge/modules/duplicates.py` → [`TICK-922.prompt.md`](./TICK-922.prompt.md) *(stale results, input validation)*
- **TICK-923** — Cleanup + Recovery: controls, type filters | depends: Wave 11 | writes: `dataforge/modules/system_cleanup.py`, `dataforge/modules/recovery.py` → [`TICK-923.prompt.md`](./TICK-923.prompt.md) *(checkbox wiring, PhotoRec types)*
- **TICK-924** — UI Media: path precedence, preview snapshot | depends: TICK-920 | writes: `dataforge/ui/views/media.py` → [`TICK-924.prompt.md`](./TICK-924.prompt.md) *(operator precedence, tree access from worker)*
- **TICK-925** — UI Metadata+Search+Dupes: stale state, selection | depends: TICK-921, TICK-922 | writes: `dataforge/ui/views/metadata_view.py`, `dataforge/ui/views/search.py`, `dataforge/ui/views/duplicates.py` → [`TICK-925.prompt.md`](./TICK-925.prompt.md) *(refresh, path resolvers, selection mode)*
- **TICK-926** — UI Cleanup+Recovery+Tools+Forensics views | depends: TICK-923 | writes: `dataforge/ui/views/system_cleanup.py`, `dataforge/ui/views/recovery_view.py`, `dataforge/ui/views/tools.py`, `dataforge/ui/views/forensics_view.py` → [`TICK-926.prompt.md`](./TICK-926.prompt.md) *(checkboxes, PhotoRec, renamer, Action Builder)*

### Open Tickets — Wave 13: Platform, API, CLI, Packaging (4 READY, depends on Wave 12)

- **TICK-927** — Dependencies + acquire + package extras | depends: Wave 12 | writes: `dataforge/core/acquire.py`, `pyproject.toml`, `requirements.txt` → [`TICK-927.prompt.md`](./TICK-927.prompt.md) *(optional imports, temp cleanup, extras)*
- **TICK-928** — Daemon API fields + HTTP auth + events | depends: Wave 12 | writes: `dataforge/engine/daemon.py`, `dataforge/api/transport/http_gateway.py` → [`TICK-928.prompt.md`](./TICK-928.prompt.md) *(implement or remove fields, auth)*
- **TICK-929** — Service arguments + transport fixes | depends: Wave 12 | writes: `dataforge/service/__main__.py`, `dataforge/service/linux/dataforge.service`, `dataforge/api/transport/uds.py`, `dataforge/api/transport/named_pipe.py` → [`TICK-929.prompt.md`](./TICK-929.prompt.md) *(--dbus, SDDL, iterator fix)*
- **TICK-930** — Packaging: build verification | depends: Wave 12 | writes: `build_exe.py`, `buildspec/release/DataForge.spec`, `buildspec/debug/DataForge-debug.spec`, `packaging/wix/Product.wxs`, `packaging/nfpm.yaml` → [`TICK-930.prompt.md`](./TICK-930.prompt.md) *(platform maps, spec fixes)*

### Open Tickets — Wave 14: Verification, Tests, Documentation (5 READY, depends on Wave 13)

- **TICK-931** — GUI thread affinity regression tests | depends: Wave 13 | writes: `tests/test_gui_thread_affinity.py` → [`TICK-931.prompt.md`](./TICK-931.prompt.md) *(thread affinity assertions)*
- **TICK-932** — Operation report contract tests | depends: Wave 13 | writes: `tests/test_operation_reports.py` → [`TICK-932.prompt.md`](./TICK-932.prompt.md) *(result shape, cancellation, evidence mode)*
- **TICK-933** — Full workflow integration smoke tests | depends: Wave 13 | writes: `tests/test_full_workflow.py` → [`TICK-933.prompt.md`](./TICK-933.prompt.md) *(end-to-end for every view)*
- **TICK-934** — Fix current stale test fixtures | depends: Wave 13 | writes: `tests/test_comprehensive.py`, `tests/test_contract_regressions.py`, `tests/test_plugin_loader_isolation.py` → [`TICK-934.prompt.md`](./TICK-934.prompt.md) *(5 current failures)*
- **TICK-935** — Documentation closeout | depends: TICK-931-934 | writes: `docs/PARALLEL_BACKLOG.md`, `docs/prompts/tickets/README.md`, `docs/reviews/STABILITY_AUDIT_2026-08-23.md` → [`TICK-935.prompt.md`](./TICK-935.prompt.md) *(status update, audit close)*

> **Recently completed Wave 8 (7/8 DONE, now archived):** `TICK-801` (Bulk Renamer), `TICK-802` (STOP), `TICK-803` (Icons), `TICK-805` (Context Menus), `TICK-806` (Automation Store), `TICK-807` (UI Memory), `TICK-808` (Hardware Crash) — all merged to `origin/develop` `87e4da9` and then deleted from HEAD per cleanup request. Retrieve via `git log --all --grep=TICK-80`.

> **Wave 7 (8/8 DONE) archived:** `TICK-701..708` (R-CORE-2/5, R-CORE-7, F10/F16/F21, F20, U5-U9, FTS index, HTTP gateway, msi/dmg) — all merged to `origin/develop` `fda9b3f` and then deleted. See `PARALLEL_BACKLOG.md` Wave 7 Review.

> **Waves 0–6 (37/37 DONE) archived:** `TICK-001..512` (Wave 0 5/5, Wave 1 9/9, Wave 2 5/5, Wave 3 4/4, Wave 4 2/2, Wave 5 11/11, Wave 6 1/1) — all merged and then deleted. See `PARALLEL_BACKLOG.md` Wave 0–6 Reviews and `git log`.

## Relevant Documentation Per Ticket

Each per-ticket file now includes a **Relevant Documentation — Must Read Before Coding** section tailored to its `scope` (e.g. `UI` → `GUI_WORKFLOWS.md`, `Core` → `TECHNICAL_SOURCE_OF_TRUTH.md` + `ARCHITECTURE.md`, `Modules` → `CLI_REFERENCE.md` + module-specific GUI workflow). The generic prompt also contains a domain→docs table (`docs/prompts/parallel-ticket-agent.md` §6). Always read the listed docs before editing and update them per `CONTRIBUTING.md §8` after editing.

## How to Use

### Sequential (default, safe)
```
Wave 0 → Wave 1 → Wave 2 → Wave 3 → Wave 4 → Wave 5 → Wave 6 → Wave 7 → Wave 8 → Wave 9 (8 parallel) → Wave 10 (3 parallel) → Wave 11 (5 sequential: 914→915→916, 914→917, 915→918) → Wave 12 (8: 919-923 parallel, 924 after 920, 925 after 921+922, 926 after 923) → Wave 13 (4 parallel) → Wave 14 (5: 931-934 parallel, 935 after all)
```

### Parallel within a Wave
```bash
# Terminal A
cat docs/prompts/tickets/TICK-901.prompt.md | pbcopy  # pass to agent A
# Terminal B (concurrent, same Wave, different file)
cat docs/prompts/tickets/TICK-902.prompt.md | pbcopy  # pass to agent B
# Both agents run concurrently — no file collision by design (hardened disjoint guarantee)
```

### Example — assign TICK-901
```bash
git checkout develop && git pull origin develop
git checkout -b fix/TICK-901-hardware-qpainter-hardening
# give agent docs/prompts/tickets/TICK-901.prompt.md
```

See `docs/PARALLEL_BACKLOG.md#how-to-work-a-ticket--sequential-and-parallel-execution-guide` for full rebase/CI/DOD checklist.

## Alias Map
`PERF-100→TICK-004`, `PERF-101→TICK-102`, `PERF-102→TICK-103`, `PERF-103→TICK-104`, `PERF-104→TICK-107`, `PERF-105→TICK-106`, `PERF-106→TICK-108`, `PERF-107→TICK-109`, `PERF-108→TICK-202`, `PERF-109→TICK-203`, `PERF-110→TICK-201`, `PERF-111→TICK-105`, `PERF-112→TICK-401` — never run twin same wave.
