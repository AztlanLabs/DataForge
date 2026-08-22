# DataForge Documentation Index

**Last updated:** 2026-08-22 — see [`DOCUMENTATION_AUDIT_2026-08-22.md`](./DOCUMENTATION_AUDIT_2026-08-22.md) for the full audit vs. code.

> **New (principal review):** [`CONSOLIDATED_SPEC.md`](./CONSOLIDATED_SPEC.md) is the single authoritative spec (reconciles all of `docs/` + proposals + reviews). [`PARALLEL_BACKLOG.md`](./PARALLEL_BACKLOG.md) is the DAG backlog for simultaneous agents — start there if you are picking a ticket. Generic parallel-agent prompt: [`.github/prompts/parallel-ticket-agent.prompt.md`](../.github/prompts/parallel-ticket-agent.prompt.md) — copy, set `{{TICKET_ID}}`, and run (one ticket = one branch = one PR, disjoint writes per wave).
>
> **Status 2026-08-22 16:15 UTC — Wave 0 ✅ 5/5 DONE, Wave 1 2/9 DONE (TICK-101, TICK-103) → Wave 1 remaining 7 can run in parallel.** See `PARALLEL_BACKLOG.md` Wave 0 + Wave 1 Reviews.

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

All “current truth” docs above are green against `dataforge/` HEAD at 2026-08-22. They all still point at `~/.dataforge/` — that is correct for HEAD; the XDG migration is a *proposal* (next section) not yet merged.

## Proposals — future architecture (not yet implemented)

> Do not treat these as shipped. They are design docs against HEAD at 2026-08-22.

| Proposal | Proposes | File |
|---|---|---|
| Ridiculously fast | Parallel scanner, batched cache, pipelined engine, job queue | [`proposals/PERFORMANCE_INVESTIGATION.md`](./proposals/PERFORMANCE_INVESTIGATION.md) · tickets → [`proposals/PERFORMANCE_TICKETS.md`](./proposals/PERFORMANCE_TICKETS.md) |
| Native OS service | UDS/Named Pipes + D-Bus/XPC/COM, hybrid HTTP for remote | [`proposals/NATIVE_OS_API_REVIEW.md`](./proposals/NATIVE_OS_API_REVIEW.md) |
| Installable package | XDG/AppData, versioned migrations, deb/rpm/msi/dmg, auto-update | [`proposals/INSTALL_UPGRADE_LIFECYCLE.md`](./proposals/INSTALL_UPGRADE_LIFECYCLE.md) |

Read in that order. Each carries a `Status: PROPOSAL` banner. `PERFORMANCE §3` FastAPI sketch is superseded by `NATIVE_OS_API §3`.

## History & reviews — frozen

Historical audits that produced the current code. Keep as records; don’t edit for `Last verified` — their dates are part of the record.

| Doc | Covers |
|---|---|
| [`reviews/README.md`](./reviews/README.md) | Overview, quick wins, Definition of Done |
| [`reviews/AUDIT_REPORT.md`](./reviews/AUDIT_REPORT.md) | 15 correctness bugs (fixed) + 13 security findings S1–S13 (fixed) |
| [`reviews/FORENSIC_REVIEW.md`](./reviews/FORENSIC_REVIEW.md) | Forensic backlog F1–F21 / U1–U11 (still open, WS-H … WS-J) |
| [`reviews/ROADMAP.md`](./reviews/ROADMAP.md) | UX/engineering roadmap (2a–2e shipped, WS-F open) |
| [`reviews/ROADMAP.md`](./reviews/ROADMAP.md) | Sequenced work-streams WS-A … WS-J, release mapping |
| [`reviews/AUDIT_REPORT.md`](./reviews/AUDIT_REPORT.md) | Doc-defect audit D1–D7 |
| [`reviews/drafts/FULL_APP_REVIEW.md`](./reviews/drafts/FULL_APP_REVIEW.md) | **DRAFT** line-level review R-CORE/R-OPS (§3+ pending) — not a sign-off |

## Freshness rule

- Current truth: `Last verified: YYYY-MM-DD` + “verified against `dataforge/` HEAD at `<commit>`”.
- Proposals: `Status: PROPOSAL — not yet implemented`.
- History: frozen dates are the record.

Full audit that produced this reorganization: [`DOCUMENTATION_AUDIT_2026-08-22.md`](./DOCUMENTATION_AUDIT_2026-08-22.md). Hardened audit fixing hallucinations, collisions, and missing contracts: [`AUDIT_HARDENED_2026-08-22.md`](./AUDIT_HARDENED_2026-08-22.md) — required reading before parallel execution.
