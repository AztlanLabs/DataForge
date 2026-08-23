# Parallel Ticket Prompts — Index

> One file per ticket — pass the file for that ticket to an AI agent. Each agent works on ONE ticket only (one branch = one commit = one PR). Within a Wave, tickets have disjoint writes and can run **in parallel**; across Waves, run **sequentially** (wave gate).

**Generic prompt:** `../parallel-ticket-agent.md` / `../../../.github/prompts/parallel-ticket-agent.prompt.md` — set `{{TICKET_ID}}`.

> **Status 2026-08-23 10:00 UTC — Wave 0 ✅ 5/5, Wave 1 ✅ 9/9, Wave 2 ✅ 5/5, Wave 3 ✅ 4/4, Wave 4 ✅ 2/2, Wave 5 ✅ 11/11, Wave 6 ✅ 1/1, Wave 7 ✅ 8/8 DONE — Wave 8 ✅ 7/8 DONE (65 tests) — 1 remaining (TICK-804)**
> Wave 0 (69) + Wave 1 (126) + Wave 2 (98) + Wave 3 (130) + Wave 4 (635) + Wave 5 (142, +2 skipped) + Wave 6 (13) + Wave 7 (128, +1 skipped) + Wave 8 (65, 7/8) = 1406 tests green (7/8 `validation_command` green, file parity verified, 1 remaining `feat/TICK-804-cache-info`). Wave 8 closed 7/8 next user issues (renamer, STOP, icons, menus, automation, memory, hardware), `TICK-804` cache info remains. See `docs/PARALLEL_BACKLOG.md` Wave 0–8 Reviews (8/8 + 7/8).
> **Overall: 52/53 DONE (98%) — 1 remaining (TICK-804).**

## Execution Order (Wave DAG) — Completed tickets archived

> **Note 2026-08-23 10:00 UTC:** All completed tickets (Wave 0–7 45/45 DONE + Wave 8 7/8 DONE) have been **deleted from HEAD** (52 prompt files removed from `docs/prompts/tickets/` and `.github/prompts/tickets/`) and are preserved in git history (`git log --all --oneline --grep=TICK-`). Only open tickets remain as files. See `docs/PARALLEL_BACKLOG.md` Wave 0–8 Reviews for full historical record and `git show <commit>:docs/prompts/tickets/TICK-XXX.prompt.md` to retrieve any deleted prompt.

### Open Tickets — Wave 8 (1 remaining, 1 branch not yet merged)

- **TICK-804** — Settings Performance DB Cache info + size | depends: — | writes: `dataforge/ui/views/settings.py`, `dataforge/core/cache.py`, `dataforge/modules/performance.py` → [`TICK-804.prompt.md`](./TICK-804.prompt.md) *(1 remaining — `feat/TICK-804-cache-info` branch, not yet merged)*

> **Recently completed Wave 8 (7/8 DONE, now archived):** `TICK-801` (Bulk Renamer), `TICK-802` (STOP), `TICK-803` (Icons), `TICK-805` (Context Menus), `TICK-806` (Automation Store), `TICK-807` (UI Memory), `TICK-808` (Hardware Crash) — all merged to `origin/develop` `87e4da9` and then deleted from HEAD per cleanup request. Retrieve via `git log --all --grep=TICK-80`.

> **Wave 7 (8/8 DONE) archived:** `TICK-701..708` (R-CORE-2/5, R-CORE-7, F10/F16/F21, F20, U5-U9, FTS index, HTTP gateway, msi/dmg) — all merged to `origin/develop` `fda9b3f` and then deleted. See `PARALLEL_BACKLOG.md` Wave 7 Review.

> **Waves 0–6 (37/37 DONE) archived:** `TICK-001..512` (Wave 0 5/5, Wave 1 9/9, Wave 2 5/5, Wave 3 4/4, Wave 4 2/2, Wave 5 11/11, Wave 6 1/1) — all merged and then deleted. See `PARALLEL_BACKLOG.md` Wave 0–6 Reviews and `git log`.

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
