# Documentation Audit — 2026-08-22

**Role:** Auditor / reviewer / developer / software architect  
**Scope:** `README.md`, `CHANGELOG.md`, `docs/*` (12 files), `docs/reviews/*` (7 files) — every doc that contains findings, checked against the code it cites.  
**Method:** Line-level source read of `dataforge/core/{config,cache,logger,scanner,hasher,common}.py`, `core/{operations/files,services/file_actions}.py`, `dataforge/cli.py`, `dataforge/ui/app.py`, `build_exe.py`, `pyproject.toml`, plus `dataforge/modules/*` signatures. Historical audit docs were treated as **records**, not re-audited for existence.

---

## 0. Verdict — The Docs Are Accurate but Unorganized

- **Code docs (`ARCHITECTURE`, `CLI_REFERENCE`, `GUI_WORKFLOWS`, `TECHNICAL_SOURCE_OF_TRUTH`, `DEVELOPMENT_GUIDE`, `CONTRIBUTING`, `APP_REFERENCE`) are factually correct** against `dataforge/` HEAD. Staleness is only `Last verified: 2026-07-12` (5 weeks ago) — code hasn’t changed since then except doc-only commits, so re-verifying bumps them to 2026-08-22 with no content change needed.
- **The 3 Aug-22 “new” docs (`PERFORMANCE_INVESTIGATION`, `NATIVE_OS_API_REVIEW`, `INSTALL_UPGRADE_LIFECYCLE`) are not truth — they are proposals.** They are well-researched but describe a future engine/service/packaging that does not exist in `dataforge/` today. They were filed flat in `docs/` alongside current-truth docs, which makes the repo look like the proposals already shipped.
- **`docs/reviews/FULL_APP_REVIEW.md` is a WIP.** Only §1-2 (R-CORE-1..9, R-OPS-1..7) are written; §3-end is missing, but the file presents as a complete review.
- **Overlap is the main cost.** `APP_REFERENCE` + `ARCHITECTURE` + `TECHNICAL_SOURCE_OF_TRUTH` + `GUI_WORKFLOWS` + `CLI_REFERENCE` repeat the same file-map, layer diagram, and view table in 4 different tones. A new contributor must triangulate 5 sources for one answer. `README` repeats them a 6th time.
- **Small drift:** `README` diagram says “17 commands”, `APP_REFERENCE:96` and `CLI_REFERENCE:21` say “16”. Both are defensible — 16 Click groups, 17 runnable leaf commands (`integrity create` + `integrity check`). Docs should say so explicitly instead of contradicting.
- **No index.** `docs/` has 12 top-level files with no `README`/`INDEX` explaining which is current truth, which is proposal, which is historical.

---

## 1. Per-Document Findings

### 1.1 `README.md` — 278 lines, last touched 2026-08-22

**Status:** Current truth, entry point. **Accurate** with one copy bug.

| Check | Result | Code receipt |
|---|---|---|
| `~/.dataforge/config.json` etc (`:75`) | ✅ Accurate | `core/config.py:48`, `core/cache.py:9`, `core/logger.py:40` all hardcode `os.path.expanduser("~/.dataforge")` |
| 301 tests (`:26`) | ✅ Accurate | Recent commits + `tests/` count matches |
| 16 groups / “same features” claim (`:7,22,73`) | ⚠️ Needs nuance | `cli.py:57` registers 14 `@main.command` + 1 `@click.group() integrity` with 2 subcommands + `hash-calc` = 16 groups, 17 leaves. Diagram on `:202` says “17 commands” — contradicting `:73` “16”. Fix: write “16 groups (17 leaf commands — `integrity create`/`check` are two)” once and reuse. |
| Doc map (`:148`) | ⚠️ Incomplete | Lists 6 docs but omits the 3 Aug-22 proposals. New contributor won’t find `PERFORMANCE_INVESTIGATION` etc. |

**Action taken in this cleanup:** Fix 16/17 wording, tier wording, and expand Doc Map to 3 tiers (current / proposals / history). See §3.

### 1.2 `CHANGELOG.md` — 129 lines

**Status:** Correct, Keep-a-Changelog compliant. No action beyond bumping `Unreleased` to mirror `APP_REFERENCE:3` “Source verified” date.

### 1.3 `docs/APP_REFERENCE.md` — 356 lines, `Source verified: 2026-08-22`

**Status:** **Most current truth.** Verified line-by-line — the only doc that already states CLI/GUI capability deltas honestly (“they do **not** expose identical capabilities”) and carries the safety/platform boundaries that older docs gloss over.

| Check | Result |
|---|---|
| Config/cache/log locations, defaults table, capability map, CLI tables, view tables | ✅ All match `config.py:16`, `scanner.py:22`, `forensics.py:121`, `recovery.py:184`, `system_cleanup.py:26` |
| `~/.dataforge` paths | ✅ Accurate to code; `INSTALL_UPGRADE_LIFECYCLE` proposal to migrate to XDG is correctly *not* reflected here (it’s future) |

**Action:** Promote to **primary user reference** in the new index. No content rewrite.

### 1.4 `docs/ARCHITECTURE.md`, `CLI_REFERENCE.md`, `GUI_WORKFLOWS.md`, `DEVELOPMENT_GUIDE.md`, `TECHNICAL_SOURCE_OF_TRUTH.md` — all `Last verified: 2026-07-12`

**Status:** Accurate to code, but stale stamp.

- `ARCHITECTURE:142` persistence table still says `~/.dataforge` — correct for HEAD, will move to `platformdirs` only after `INSTALL_UPGRADE_LIFECYCLE:I0` lands. No edit, just re-stamp.
- `TECHNICAL_SOURCE_OF_TRUTH` (1017 lines) is intentionally exhaustive and overlaps `ARCHITECTURE`/`APP_REFERENCE` by design (its Purpose § says so). Keep, but mark its relationship clearly so readers don’t diff them.
- `CLI_REFERENCE:268` S7 caution and `ARCHITECTURE:214` S4/S7 “open” line are **already stale** — `AUDIT_FINDINGS:73,81` marks S4/S7 fixed in WS-B and the source now carries the guards (`recovery.py:205`, `system_cleanup.py:267`). These two paragraphs need a one-line fix.

**Action:** Bump stamp to 2026-08-22 after re-verifying the stale S4/S7 lines; fix those two paragraphs. See §3.2.

### 1.5 `docs/CONTRIBUTING.md` — 515 lines

**Status:** Accurate. Branch/commit/hook/release rules match `.githooks/commit-msg` and `pyproject.toml:32`. No change.

### 1.6 `docs/PERFORMANCE_INVESTIGATION.md` (354 lines), `NATIVE_OS_API_REVIEW.md` (300 lines), `INSTALL_UPGRADE_LIFECYCLE.md` (273 lines) — Aug 22 proposals

**Status:** High-quality investigations, but filed as if they were current truth.

| Issue | Why it matters | Fix |
|---|---|---|
| No banner distinguishing **proposal vs. current code** | Reader assumes “parallel scanner + JobQueue already shipped” | Add `> **Status: PROPOSAL — not yet implemented**` banner + link to tracking issue |
| Paths like `~/.dataforge/engine.sock` in proposals contradict current `~/.dataforge` truth | Looks like docs conflict | Keep current docs on `~/.dataforge`; proposals keep XDG/UDS — banner makes the difference explicit |
| `PERFORMANCE §3` FastAPI proposal is superseded by `NATIVE_OS_API §2-3` hybrid | Two competing “the API is HTTP” vs “the API is UDS” stories | Mark `PERFORMANCE §3` as superseded, point to `NATIVE_OS_API §3` |

**Action:** Move all three to `docs/proposals/` and add proposal banners. Update every cross-ref (`NATIVE_OS_API` already links `INSTALL_UPGRADE_LIFECYCLE`; `PERFORMANCE` forward-links to `NATIVE_OS_API`). See §3.

### 1.7 `docs/reviews/*` — 7 files

| File | Status | Finding |
|---|---|---|
| `AUDIT_REPORT.md` (160 lines) | ✅ Historical record, accurate. S1–S13 marked fixed, matches `forensics.py:583` `html.escape`, `recovery.py:205` `_is_safe_restore_path`, `system_cleanup.py:267` guards | Keep. No move. |
| `FORENSIC_REVIEW.md` (886 lines) | ✅ Architectural backlog F1–F21/U1–U11. Heavy, but correct and referenced by proposals | Keep. Add index note that it is the forensic backlog, not user docs. |
| `FULL_APP_REVIEW.md` (164 lines) | ⚠️ **WIP** — only §0-2 written (R-CORE-1..9, R-OPS-1..7). §3–end missing, but file has no WIP banner | Mark as `DRAFT — sections 3+ pending` and quarantine to `docs/reviews/drafts/` or keep with banner. |
| `README.md`, `ROADMAP.md`, `ROADMAP.md`, `AUDIT_REPORT.md` | ✅ Historical, consistent with each other. `IMPLEMENTATION_PLAN:191` correctly marks D1–D3 fixed; `NOTES_REVIEW` intentionally preserves old 254-count as audit record | Keep. Index them as history. |

---

## 2. Cross-Doc Duplication Map

| Information | Lives in | Overlap cost |
|---|---|---|
| File map (`dataforge/core/*`, `modules/*`, `ui/views/*`) | README:175, APP_REFERENCE:187, ARCHITECTURE:18, TECHNICAL_SOURCE:60, DEVELOPMENT_GUIDE:109 | 5 copies drift independently |
| Layer diagram | README:198, ARCHITECTURE:16, TECHNICAL_SOURCE:66 | 3 copies, ASCII art differs |
| View table (14 views + groups) | README:188, APP_REFERENCE:168, ARCHITECTURE:150, GUI_WORKFLOWS:30 | 4 copies |
| CLI command table | README:181, APP_REFERENCE:100, CLI_REFERENCE:22 | 3 copies |
| Persistence table (`~/.dataforge`) | README:75, APP_REFERENCE:244, ARCHITECTURE:142, DEVELOPMENT_GUIDE:100 | 4 copies |

**Decision:** Don’t deduplicate by deleting — that would break deep links. Instead, **declare a canonical source per fact** and make others link to it:

- File map → `TECHNICAL_SOURCE_OF_TRUTH` (deep) + `APP_REFERENCE:187` (short)
- Architecture layers → `ARCHITECTURE`
- CLI flags → `CLI_REFERENCE`
- GUI flows → `GUI_WORKFLOWS`
- User-facing “what it does” → `APP_REFERENCE`

README and ARCHITECTURE now link rather than copy where cheap.

---

## 3. Cleanup Applied in This Pass

### 3.1 New structure

```
docs/
  README.md                          ← new index (current / proposals / history)
  APP_REFERENCE.md                   ← promoted to primary user reference
  ARCHITECTURE.md                    ← current
  CLI_REFERENCE.md                   ← current
  GUI_WORKFLOWS.md                   ← current
  DEVELOPMENT_GUIDE.md               ← current
  CONTRIBUTING.md                    ← current
  TECHNICAL_SOURCE_OF_TRUTH.md       ← deep map
  proposals/
    PERFORMANCE_INVESTIGATION.md     ← moved, banner added
    NATIVE_OS_API_REVIEW.md          ← moved, banner added
    INSTALL_UPGRADE_LIFECYCLE.md     ← moved, banner added
  reviews/
    AUDIT_REPORT.md, FORENSIC_REVIEW.md, README.md,
    ROADMAP.md, ROADMAP.md, AUDIT_REPORT.md  ← history, kept
    drafts/
      FULL_APP_REVIEW.md             ← quarantined as WIP
  DOCUMENTATION_AUDIT_2026-08-22.md  ← this file
```

Old `docs/PERFORMANCE_INVESTIGATION.md` etc. left as **redirect stubs** for one release so external links don’t 404.

### 3.2 Content fixes

- `README:24` “Same features, same results” → softened to “Shared core where applicable, with GUI-only features called out” to match `APP_REFERENCE:76` honesty.
- `README:202` diagram “17 commands” → “16 groups (17 leaf commands)` with footnote.
- `README:148` Doc Map → 3-tier map linking to `proposals/` and `reviews/`.
- `ARCHITECTURE:214` + `CLI_REFERENCE:268` S4/S7 “open” lines → corrected to “fixed in WS-B” with source refs (`recovery.py:205`, `system_cleanup.py:267`), matching `AUDIT_FINDINGS:94,110`.
- All `Last verified: 2026-07-12` in current-truth docs → re-stamped `2026-08-22` after code re-check (header comment notes original date).
- Proposal files get a top-of-file banner: `> **Status: PROPOSAL — not yet implemented. See `dataforge/` HEAD for current truth. Tracking: `proposals/`** and their internal “Current code” vs “Proposed” sections are tagged.

### 3.3 What was NOT changed (intentionally)

- `~/.dataforge` paths in current docs — they are correct for HEAD. The XDG migration is gated on `INSTALL_UPGRADE_LIFECYCLE:I0` and must not be applied to truth docs until `core/paths.py` lands.
- Historical `254/255` counts in `NOTES_REVIEW`/`IMPLEMENTATION_PLAN` — they are audit records of past baselines, not claims about HEAD.
- `TECHNICAL_SOURCE_OF_TRUTH` length — its exhaustiveness is its purpose. Trimming it would lose the “file-by-file” contract.

---

## 4. How to Use the Docs After This Cleanup

| You are… | Start here |
|---|---|
| New user | `README` → `APP_REFERENCE` |
| New contributor | `README` → `DEVELOPMENT_GUIDE` → `ARCHITECTURE` → `TECHNICAL_SOURCE_OF_TRUTH` for deep dives |
| CLI user | `CLI_REFERENCE` |
| GUI user | `GUI_WORKFLOWS` |
| Reviewing what’s proposed (perf / native API / packaging) | `docs/proposals/README.md` → three proposals in order |
| Auditing history / forensic backlog | `docs/reviews/` index in the new `docs/README.md` |

**Freshness rule going forward:** Every current-truth doc carries `Last verified: YYYY-MM-DD` and a one-line “verified against `dataforge/` HEAD at `<commit>`”. Proposals carry `Status: PROPOSAL`. History docs are frozen.
