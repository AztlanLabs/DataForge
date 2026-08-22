# DataForge Documentation Index

**Last updated:** 2026-08-22 — see [`DOCUMENTATION_AUDIT_2026-08-22.md`](./DOCUMENTATION_AUDIT_2026-08-22.md) for the full audit vs. code.

> **New (principal review):** [`CONSOLIDATED_SPEC.md`](./CONSOLIDATED_SPEC.md) is the single authoritative spec (reconciles all of `docs/` + proposals + reviews). [`PARALLEL_BACKLOG.md`](./PARALLEL_BACKLOG.md) is the DAG backlog for simultaneous agents — start there if you are picking a ticket. Generic parallel-agent prompt: [`.github/prompts/parallel-ticket-agent.prompt.md`](../.github/prompts/parallel-ticket-agent.prompt.md) — copy, set `{{TICKET_ID}}`, and run (one ticket = one branch = one PR, disjoint writes per wave).
>
> **Status 2026-08-22 23:30 UTC — Wave 0 ✅ 5/5, Wave 1 ✅ 9/9, Wave 2 ✅ 5/5, Wave 3 ✅ 4/4 DONE (723 tests) → Wave 4 ⏳ Pending (2 tickets).** See `PARALLEL_BACKLOG.md` Wave 0–3 Reviews.

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

All “current truth” docs above are green against `dataforge/` HEAD at 2026-08-22. They all still point at `~/.dataforge/` — that is correct for HEAD; the XDG migration landed in TICK-001 (Wave 0) via `core/paths.py` with a legacy shim.

## Proposals — future architecture (partially implemented)

> Some proposals below are now partially or fully implemented via the parallel backlog (Wave 0-3). Check `PARALLEL_BACKLOG.md` for current status.

| Proposal | Proposes | Status |
|---|---|---|
| Ridiculously fast | Parallel scanner, batched cache, pipelined engine, job queue | **Partially done** (TICK-102/103/104/107/108/109/201/202/203) |
| Native OS service | UDS/Named Pipes + D-Bus/XPC/COM, hybrid HTTP for remote | **Partially done** (TICK-205 UDS/Pipe, TICK-301 daemon, TICK-302 lifecycle; HTTP gateway pending) |
| Installable package | XDG/AppData, versioned migrations, deb/rpm/msi/dmg, auto-update | **Partially done** (TICK-001 paths, TICK-303 nfpm deb/rpm; msi/dmg/auto-update pending) |


## History & reviews — frozen

Historical audits that produced the current code. Keep as records; don’t edit for `Last verified` — their dates are part of the record.

| Doc | Covers |
|---|---|
| [`reviews/README.md`](./reviews/README.md) | Overview, quick wins, Definition of Done |
| [`reviews/AUDIT_REPORT.md`](./reviews/AUDIT_REPORT.md) | 15 correctness bugs (fixed) + 13 security findings S1–S13 (fixed) |
| [`reviews/FORENSIC_REVIEW.md`](./reviews/FORENSIC_REVIEW.md) | Forensic backlog F1–F21 / U1–U11 (F1–F3/U2/F9 fixed, rest open, WS-I/WS-J) |
| [`reviews/ROADMAP.md`](./reviews/ROADMAP.md) | UX/engineering roadmap (2a–2e shipped, WS-F/H done, WS-G next) |
| [`reviews/ROADMAP.md`](./reviews/ROADMAP.md) | Sequenced work-streams WS-A … WS-J, release mapping |
| [`reviews/AUDIT_REPORT.md`](./reviews/AUDIT_REPORT.md) | Doc-defect audit D1–D7 |
| [`reviews/drafts/FULL_APP_REVIEW.md`](./reviews/drafts/FULL_APP_REVIEW.md) | **DRAFT** line-level review R-CORE/R-OPS (§3+ pending) — not a sign-off |

## Freshness rule

- Current truth: `Last verified: YYYY-MM-DD` + “verified against `dataforge/` HEAD at `<commit>`”.
- Proposals: `Status: PROPOSAL — not yet implemented`.
- History: frozen dates are the record.

Full audit that produced this reorganization: [`DOCUMENTATION_AUDIT_2026-08-22.md`](./DOCUMENTATION_AUDIT_2026-08-22.md). Hardened audit fixing hallucinations, collisions, and missing contracts: [`AUDIT_HARDENED_2026-08-22.md`](./AUDIT_HARDENED_2026-08-22.md) — required reading before parallel execution.
