# Roadmap — Sequenced Execution to v0.2.0 / v0.3.0

> **Update 2026-08-23 06:00 UTC — Wave 5 (11/11) + Wave 6 (1/1) DONE, 37/37 tickets, 1213 tests, HEAD `b373e7e`. See `docs/PARALLEL_BACKLOG.md` Wave 5+6 Reviews. 13 orphaned gaps deferred to Wave 7+.**

**Date:** 2026-07-11 · **Updated:** 2026-08-22 · **Last verified:** 2026-07-12  
**Merges:** `ROADMAP.md` + `ROADMAP.md` (no work-stream removed — this is a consolidation). Originals in git history.  
**Target:** `v0.2.0` (WS-A…WS-H) → `v0.3.0` (WS-I, WS-J) · **Current:** `0.1.0` (`pyproject.toml`)

> `AUDIT_REPORT.md` for bug/security detail, `FORENSIC_REVIEW.md` for F/U deep dives. This doc answers “what next, in what order, and when do I cut the release?”

## Release model

Eight sequenced streams for `v0.2.0` (WS-A…WS-H); engine work opens `v0.3.0` (WS-I/WS-J) after. Each stream closes with an `alpha` tag on `develop`; one `develop→main` PR cuts `v0.2.0` through `beta→rc→GA`.

```
main     ●────────────────────●── v0.2.0-beta.1 ─●── rc.1 ─●── v0.2.0 ── … ──●── v0.3.0
          \                   /                                /
develop    ●──●──●──●──●──●──●──●──●──●──●──●──●  (alpha.1…8)  ●──●──●──● (v0.3.0)
           A  A  B  B  C  D  E  F  G  H            I  I  J  J
```

**Releasable =** `pytest -q` green, `version` bumped, `CHANGELOG` moved, `docs` links clean, `sdist` + `build_exe.py release` + `fm`/`run_ui.py` smoke, no HIGH security open (S2 fixed in WS-A).

## Work-streams (ordered)

| WS | Ships | Effort | Status |
|---|---|---|---|
| **A — CI + hardening + doc audit** | `ci.yml`, ruff/black/mypy/coverage, `commit-msg` hook, TSOT path audit, S2 `html.escape` (`forensics.py:581`) | S | ✅ Shipped (`v0.2.0-alpha.1`, 255→301 tests) |
| **B — Security S4–S13** | Trash confinement `recovery.py:205`, cleanup guards `system_cleanup.py:267`, plugin hardening `ui/plugin_loader.py:40`, `0600` reports, `defusedxml`, config validation, decompress caps | M | ✅ Shipped |
| **C — Interaction correctness (2c.1–2c.7)** | File/folder riddle gone, autosave “Saved ✓”, single dark-mode truth, sidebar always visible, scrollable destructive preview, task-named busy, rich help (`views/base.py`, `app.py`, `settings.py`) | M | ✅ Shipped |
| **D — IA / naming / parity (2d.1–2d.5)** | Task-oriented sidebar (Home/Find & Organize/Clean & Optimize/Recover & Investigate/System), Automations merge, `fm devices` GUI (`StorageDevicesView`), labels `Simple/Standard/Everything` | M | ✅ Shipped |
| **E — Motion / empty / error / a11y (2e.1–2e.7)** | Sidebar/view `QPropertyAnimation` (180/160ms OutCubic), `QProgressBar` indeterminate, `ui_reduce_motion`, `focus_ring` `:focus` QSS, `EmptyState`, `friendly_error_message`, `accessibleName`+`⚠` glyph, 18 SVG icons (`resources/icons.py`) | M | ✅ Shipped (`v0.2.0-alpha.5`, 301) |
| **F — Architecture consolidation** | Filter engines `search.py`↔`actions/filters.py`, metadata duality `cleaner.py` vs `metadata.py`, dead `core/provider.py`, error convention | M | ✅ Shipped (TICK-204 metadata single seam) |
| **G — Brand / release polish** | `BR.1` repo description, `CHANGELOG`/`pyproject` version sync, `build_exe` polish | S | ⏳ After F |
| **H — Forensic soundness (`v0.2.0` layer)** | F1 chain-of-custody (`core/audit.py`), F2 provenance, F3/U2 Evidence Mode (`FileActionService` gate), F9 UTC, F4/F21 `secure_delete` move, F13 isolation | L | ✅ Shipped (TICK-304 audit log + CaseContext + Evidence Mode + UTC provenance) |
| **I — Engine correctness (`v0.3.0`)** | F5 raw image (E01/AFF4), F6 carving alignment, F14 streaming, F16 sparse, F20 VSS, F8 ADS/xattrs, F10 Unicode | L | ⏳ After H |
| **J — Engine growth (`v0.3.0`)** | F7 YARA/SSDEEP/NSRL, F15 budget, U1–U11 investigator UX (virtualised timeline, hex inspector, mismatch filter, keyboard nav, etc.) | L | ⏳ After I |

Full per-item Where/Why/How, commit `type(scope)` and version impact remain in `IMPLEMENTATION_PLAN` history and in `AUDIT_REPORT`/`FORENSIC_REVIEW` for the IDs above.

## Backlog index (today’s open items only)

**From `AUDIT_REPORT:Part 4` (R-):** R-CORE-1/2 (logger stdout, config list items) and R-OPS-2 (zip abort) are highest-leverage outside the forensic track. R-CORE-1 fixed in TICK-101, R-OPS-1/3/4 fixed in TICK-105, R-OPS-2 fixed in TICK-201.  
**From `FORENSIC_REVIEW`:** F1–F3/U2/F9 closed by TICK-304 (Wave 3). F4/F21 (`secure_delete` move), F13 (parser isolation) remain for WS-I/J.  
**From `IMPROVEMENT_PLAN:ARCH`:** ARCH.2 metadata single-source closed by TICK-204 (Wave 2). ARCH.1 filter unification remains for WS-G.

## Proposals that extend this roadmap

`docs/proposals/` adds a **native-service track** (I0…N4) — XDG/AppData paths, UDS/Named Pipes + D-Bus/XPC, and `deb/rpm/msi/dmg` packaging — that runs *in parallel* with WS-F…H. See `NATIVE_OS_API_REVIEW §7` and `INSTALL_UPGRADE_LIFECYCLE §9` for the merged I+N ordering (I0 `core/paths.py` must land before any package).