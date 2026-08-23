# Parallel Ticket Prompts — Index

> One file per ticket — pass the file for that ticket to an AI agent. Each agent works on ONE ticket only (one branch = one commit = one PR). Within a Wave, tickets have disjoint writes and can run **in parallel**; across Waves, run **sequentially** (wave gate).

**Generic prompt:** `../parallel-ticket-agent.md` / `../../../.github/prompts/parallel-ticket-agent.prompt.md` — set `{{TICKET_ID}}`.

> **Status 2026-08-23 11:00 UTC — Wave 0 ✅ 5/5, Wave 1 ✅ 9/9, Wave 2 ✅ 5/5, Wave 3 ✅ 4/4, Wave 4 ✅ 2/2, Wave 5 ✅ 11/11, Wave 6 ✅ 1/1, Wave 7 ✅ 8/8, Wave 8 ✅ 7/8 DONE (1 remaining TICK-804), Wave 9 🔜 0/8 READY, Wave 10 🔜 0/3 READY**
> Wave 0 (69) + Wave 1 (126) + Wave 2 (98) + Wave 3 (130) + Wave 4 (635) + Wave 5 (142, +2 skipped) + Wave 6 (13) + Wave 7 (128, +1 skipped) + Wave 8 (65, 7/8) + Wave 9 (0/8) + Wave 10 (0/3) = 1406 tests green + 11 READY (Wave 9/10 new — user crash/UX/debt backlog). Wave 8 closed 7/8 next issues, `TICK-804` remains; Wave 9 Stability Hotfix + Wave 10 Quality now READY. See `docs/PARALLEL_BACKLOG.md` Wave 9/10 Concurrency Map.
> **Overall: 52/64 DONE (81%) — 12 remaining (TICK-804 + 901-908 + 911-913).**

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

> **Recently completed Wave 8 (7/8 DONE, now archived):** `TICK-801` (Bulk Renamer), `TICK-802` (STOP), `TICK-803` (Icons), `TICK-805` (Context Menus), `TICK-806` (Automation Store), `TICK-807` (UI Memory), `TICK-808` (Hardware Crash) — all merged to `origin/develop` `87e4da9` and then deleted from HEAD per cleanup request. Retrieve via `git log --all --grep=TICK-80`.

> **Wave 7 (8/8 DONE) archived:** `TICK-701..708` (R-CORE-2/5, R-CORE-7, F10/F16/F21, F20, U5-U9, FTS index, HTTP gateway, msi/dmg) — all merged to `origin/develop` `fda9b3f` and then deleted. See `PARALLEL_BACKLOG.md` Wave 7 Review.

> **Waves 0–6 (37/37 DONE) archived:** `TICK-001..512` (Wave 0 5/5, Wave 1 9/9, Wave 2 5/5, Wave 3 4/4, Wave 4 2/2, Wave 5 11/11, Wave 6 1/1) — all merged and then deleted. See `PARALLEL_BACKLOG.md` Wave 0–6 Reviews and `git log`.

## Relevant Documentation Per Ticket

Each per-ticket file now includes a **Relevant Documentation — Must Read Before Coding** section tailored to its `scope` (e.g. `UI` → `GUI_WORKFLOWS.md`, `Core` → `TECHNICAL_SOURCE_OF_TRUTH.md` + `ARCHITECTURE.md`, `Modules` → `CLI_REFERENCE.md` + module-specific GUI workflow). The generic prompt also contains a domain→docs table (`docs/prompts/parallel-ticket-agent.md` §6). Always read the listed docs before editing and update them per `CONTRIBUTING.md §8` after editing.

## How to Use

### Sequential (default, safe)
```
Wave 0 (0.1→0.2→0.3→0.4→0.5) → Wave 1 (9 agents after Wave 0 green) → Wave 2 → Wave 3 → Wave 4 → Wave 5 (11 parallel) → Wave 6 (1 sequential re-entry) → Wave 7 (8 parallel) → Wave 8 (8 parallel) → Wave 9 (Stability Hotfix, 8 parallel) → Wave 10 (Quality, 3 parallel)
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
