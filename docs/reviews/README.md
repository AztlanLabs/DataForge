# Reviews — Index

**Last updated:** 2026-08-22 — covers findings as of `dataforge/` HEAD. All “fixed” claims were re-verified against source at that date.

This directory is the historical audit trail. Current user docs live in `docs/` (see `../README.md`).

| Doc | What it is | When to read it |
|---|---|---|
| [`AUDIT_REPORT.md`](./AUDIT_REPORT.md) | **All code + security findings in one place** — correctness bugs H1/M1–M6/L1–L9, security S1–S13 (all fixed), doc defects D1–D7, plus new line-level findings R-CORE/R-OPS (WIP) | “What was broken and is it fixed?” |
| [`FORENSIC_REVIEW.md`](./FORENSIC_REVIEW.md) | Forensic-soundness + investigator UX (F1–F21, U1–U11) vs. EnCase/FTK/AXIOM/FIM, ACPO/ISO 27037/NIST SP 800-86 | “Is it defensible as a forensic product?” |
| [`ROADMAP.md`](./ROADMAP.md) | **Single sequenced plan** — UX/engineering roadmap + work-streams WS-A…WS-J, release gating to `v0.2.0`/`v0.3.0` | “What do I build next, in what order?” |
| `drafts/FULL_APP_REVIEW.md` | Original WIP source for R-CORE/R-OPS — kept as draft until §3+ complete | — |

## Status at a glance (2026-08-22)

- **Correctness:** H1/M1–M6/L1–L9 + S1–S13 → **all fixed**, 723 tests green (`AUDIT_REPORT:Part 1–2`).
- **Doc defects:** D1–D7 → fixed (`AUDIT_REPORT:Part 3`).
- **Line-level findings:** R-CORE-1, R-OPS-1/2/3/4 → **fixed** (TICK-101, TICK-105, TICK-201). R-CORE-2 remains.
- **Forensic backlog:** F1–F3/U2/F9 → **fixed** (TICK-304: audit log, CaseContext, Evidence Mode, UTC provenance). F4/F21/F13 remain (`FORENSIC_REVIEW`).
- **Parallel backlog:** Wave 0–3 complete (23/25 tickets, 92%). Wave 4 (TICK-401/402) pending.
- **Next ship:** WS-G (brand/release polish) — last phase before v0.2.0 in `ROADMAP`.

## How findings are written

Every item follows **Where / Why / How** (`CONTRIBUTING.md §8`): exact `path:line`, risk if left unfixed, concrete fix + seam + test. Severities: 🔴 High (data loss/crash/security), 🟠 Medium, 🟡 Low, 🔵 Info.

## Retired names

`AUDIT_REPORT.md` + `AUDIT_REPORT.md` + `drafts/FULL_APP_REVIEW` → `AUDIT_REPORT.md` (merged, no info lost)  
`ROADMAP.md` + `ROADMAP.md` → `ROADMAP.md`  
`README.md` → this index (overview folded)  
`FORENSIC_REVIEW.md` → `FORENSIC_REVIEW.md` (trimmed, same findings)

> **2026-08-23 — Wave 5 (11/11) + Wave 6 (1/1) DONE:** `AUDIT_REPORT.md` Part 4 `R-CORE-3/4/6` + `FORENSIC_REVIEW.md` `F1/F4/F5/F7/F8/F9/F11/F12/F13/F14/U3/U4/U10/U11` closed. See `docs/PARALLEL_BACKLOG.md`.
