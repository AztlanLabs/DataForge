# DataForge Documentation Index

**Last updated:** 2026-08-23 09:00 UTC — see [`DOCUMENTATION_AUDIT_2026-08-22.md`](./DOCUMENTATION_AUDIT_2026-08-22.md) for the full audit vs. code. Wave 5 (11/11) + Wave 6 (1/1) + Wave 7 (8/8) DONE `45/45`; Wave 8 (8 tickets, 24 files) 🔜 READY.

> **New (principal review):** [`CONSOLIDATED_SPEC.md`](./CONSOLIDATED_SPEC.md) is the single authoritative spec (reconciles all of `docs/` + proposals + reviews). [`PARALLEL_BACKLOG.md`](./PARALLEL_BACKLOG.md) is the DAG backlog for simultaneous agents — start there if you are picking a ticket. Generic parallel-agent prompt: [`.github/prompts/parallel-ticket-agent.prompt.md`](../.github/prompts/parallel-ticket-agent.prompt.md) — copy, set `{{TICKET_ID}}`, and run (one ticket = one branch = one PR, disjoint writes per wave).
>
> **Status 2026-08-23 09:00 UTC — Wave 0 ✅ 5/5, Wave 1 ✅ 9/9, Wave 2 ✅ 5/5, Wave 3 ✅ 4/4, Wave 4 ✅ 2/2, Wave 5 ✅ 11/11, Wave 6 ✅ 1/1 DONE (1213 tests) → Wave 7 🔜 READY (8 tickets) — Wave 8 🔜 READY (8 tickets: renamer, STOP, icons, cache, menus, automation, memory, hardware).** See `PARALLEL_BACKLOG.md` Wave 0–6 Reviews + Wave 7/8 Spec.

## Current truth — read these

| Doc | What it is | When to read |
|---|---|---|
| [`APP_REFERENCE.md`](./APP_REFERENCE.md) | **Primary user reference** — features, safety, CLI/GUI, config, deps, platform limits. Source verified 2026-08-22 | First stop for “what does DataForge do?” |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Layer diagram, abstractions (`FileEntry`, `FileActionService`, `ActionContext`), flows | “How is it built?” |
| [`CLI_REFERENCE.md`](./CLI_REFERENCE.md) | Every `fm` flag with examples (16 groups / 17 leaf commands) | Scripting / automation |
| [`GUI_WORKFLOWS.md`](./GUI_WORKFLOWS.md) | Shell, threading model, 14 views view-by-view | Desktop work / adding a view |
| [`TECHNICAL_SOURCE_OF_TRUTH.md`](./TECHNICAL_SOURCE_OF_TRUTH.md) | File-by-file source map (1017 lines, exhaustive) | Deep maintainer dive |
| [`DEVELOPMENT_GUIDE.md`](./DEVELOPMENT_GUIDE.md) | Setup, run modes, packaging, runtime artifacts, onboarding order | New contributor |
| [`CONTRIBUTING.md`](./CONTRIBUTING.md) | Commit convention, branching, versioning, release runbook | Before your first commit |
| `../README.md` | Project overview, superpowers, quick start, system-at-a-glance | Entry point |
| `../CHANGELOG.md` | Keep-a-Changelog history | Release notes |

All “current truth” docs above are green against `dataforge/` HEAD at `b373e7e` (2026-08-23 09:00 UTC, Wave 5+6 DONE). XDG migration `TICK-001`, Wave 7 `TICK-701..708` (config/cache, logger, unicode/sparse, VSS, UX polish, FTS, HTTP, msi/dmg), forensic engine `TICK-508` (`image_io`/`streams`/`indicators`), plugin isolation `TICK-509`, logger chain `TICK-510`, parser pool `TICK-511` all verified.

## Proposals — future architecture (partially implemented)

> Some proposals below are now partially or fully implemented via the parallel backlog (Wave 0-6). Check `PARALLEL_BACKLOG.md` for current status.

| Proposal | Proposes | Status |
|---|---|---|
| Ridiculously fast | Parallel scanner, batched cache, pipelined engine, job queue | **Done** (TICK-102/103/104/107/108/109/201/202/203/505 F14 streaming) |
| Native OS service | UDS/Named Pipes + D-Bus/XPC/COM, hybrid HTTP for remote | **Partially done** (TICK-205 UDS/Pipe, TICK-301 daemon, TICK-302 lifecycle; HTTP gateway pending) |
| Installable package | XDG/AppData, versioned migrations, deb/rpm/msi/dmg, auto-update | **Partially done** (TICK-001 paths, TICK-303 nfpm deb/rpm; msi/dmg/auto-update pending) |
| Forensic soundness | Chain-of-custody, Evidence Mode, sanitisation, parser isolation, forensic engine | **Done** (TICK-304 F1/F2/F3/U2, TICK-502 F4, TICK-503 F1 wiring, TICK-508 F5/F7/F8, TICK-509 F12, TICK-510 F11, TICK-511 F13, TICK-504 F9, TICK-512 U10/U11) |


## History & reviews — frozen

Historical audits that produced the current code. Keep as records; don’t edit for `Last verified` — their dates are part of the record.

| Doc | Covers |
|---|---|
| [`reviews/README.md`](./reviews/README.md) | Overview, quick wins, Definition of Done |
| [`reviews/AUDIT_REPORT.md`](./reviews/AUDIT_REPORT.md) | 15 correctness bugs (fixed) + 13 security findings S1–S13 (fixed) |
| [`reviews/FORENSIC_REVIEW.md`](./reviews/FORENSIC_REVIEW.md) | Forensic backlog F1–F21 / U1–U11 (F1–F5/F7/F8/F9/F11/F12/F13/F14/U3/U4/U10/U11 fixed via Wave 5/6; F6/F10/F15/F16/F20/U5-U9 deferred) |
| [`reviews/ROADMAP.md`](./reviews/ROADMAP.md) | UX/engineering roadmap (2a–2e shipped, WS-F/H done, WS-G next) |
| [`reviews/ROADMAP.md`](./reviews/ROADMAP.md) | Sequenced work-streams WS-A … WS-J, release mapping |
| [`reviews/AUDIT_REPORT.md`](./reviews/AUDIT_REPORT.md) | Doc-defect audit D1–D7 |
| [`reviews/drafts/FULL_APP_REVIEW.md`](./reviews/drafts/FULL_APP_REVIEW.md) | **DRAFT** line-level review R-CORE/R-OPS (§3+ pending) — not a sign-off |

## Freshness rule

- Current truth: `Last verified: YYYY-MM-DD` + “verified against `dataforge/` HEAD at `<commit>`”.
- Proposals: `Status: PROPOSAL — not yet implemented`.
- History: frozen dates are the record.

Full audit that produced this reorganization: [`DOCUMENTATION_AUDIT_2026-08-22.md`](./DOCUMENTATION_AUDIT_2026-08-22.md). Hardened audit fixing hallucinations, collisions, and missing contracts: [`AUDIT_HARDENED_2026-08-22.md`](./AUDIT_HARDENED_2026-08-22.md) — required reading before parallel execution.
