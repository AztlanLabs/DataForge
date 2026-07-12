# Implementation Plan — Sequenced Execution & Release Roadmap

**Date:** 2026-07-11 · **Last verified:** 2026-07-11
**Target release:** `v0.2.0` · **Current version:** `0.1.0` (`setup.py`)

---

## 1. Purpose & How to Use This Document

The `docs/reviews/` audit produced three evidence trackers and one notes file. They
say *what* is wrong and *why* — but the open work is scattered across all of them
with no single ordering and no link to how DataForge actually ships. **This document
is the one sequenced execution + release plan.** It answers: *what do I do next, in
what order, which commits, and when do I cut the release?*

It does not replace the trackers — it **links into** them:

| Read this for… | Document |
| --- | --- |
| Bug/security detail, line-level evidence, fixes | [`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md) |
| UX/engineering rationale, per-item backlog | [`IMPROVEMENT_PLAN.md`](./IMPROVEMENT_PLAN.md) |
| Doc-defect audit (D1–D7) | [`NOTES_REVIEW.md`](./NOTES_REVIEW.md) |
| Status overview, brand, Definition of Done | [`EXECUTIVE_SUMMARY.md`](./EXECUTIVE_SUMMARY.md) |
| Commit format, branch model, versioning, release checklist | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) §2, §3, §6, §7 |

### 1.1 Documentation standard — every item answers Where / Why / How

This is the required framing for every finding, work-stream, and task in *all*
review documents (see [`../CONTRIBUTING.md`](../CONTRIBUTING.md) §8):

- **Where** — the exact location: `path:line`, component, or doc section.
- **Why** — the impact if left unfixed: the risk, defect, or user cost that
  justifies the work. Never "because the review said so."
- **How** — the concrete approach: the fix, the seam it lands at, and the test
  that proves it.

Each work-stream in [§4](#4-work-streams--the-ordered-how) is written to this
standard. Per-item Where/Why/How lives in the linked trackers.

### 1.2 Provenance — these findings are code-verified, not assumed

The backlog below was **checked against the current source tree**, not copied on
trust from the review files. Verified open, with evidence:

| ID | Verified open at | Evidence |
| --- | --- | --- |
| S2 | `dataforge/modules/forensics.py:581-625` | interpolated values, no `html.escape()` |
| S4 | `dataforge/modules/recovery.py:225-250` | `original_path` → `shutil.move` + `os.makedirs` |
| S5 | `dataforge/ui/plugin_loader.py:38-51` | `exec_module()`, no signing/sandbox |
| S7 | `dataforge/modules/system_cleanup.py:249` | blanket junk classification |
| S8 | `dataforge/modules/password_tools.py:246` | `open(hash_file, "w")`, no `0o600` |
| S9 | `dataforge/modules/forensics.py:1033` | `xml.etree.ElementTree`, no `defusedxml` |
| S10 | `dataforge/core/config.py` | blind merge, zero validation |

Also verified: NOTES_REVIEW **D1–D3 are already resolved in the source docs** — the
broken anchor, `"224"` count, and dead `docs/reviews/01` refs now survive *only
inside NOTES_REVIEW.md itself* as its audit record. Still open: `TECHNICAL_SOURCE_OF_TRUTH.md`
carries ~16 unprefixed `core/`/`modules/` path references (D4/D5). Baseline:
`PYTHONPATH=. pytest -q` → **254 passed**.

> **Rule of engagement:** every task below maps to a Conventional Commit
> (`type(scope): description`, see [CONTRIBUTING §3](../CONTRIBUTING.md)) with a stated
> version impact. All work lands on `develop`; a single `develop`→`main` PR cuts `v0.2.0`.

---

## 2. Release Strategy — the "When"

### 2.1 Model

The entire backlog ships as **one `v0.2.0` release** (MINOR — the backlog contains
`feat` work: task-oriented IA, Automations merge, `fm devices` GUI). Work is grouped
into **seven sequenced work-streams (WS-A … WS-G)**. Each stream lands on `develop`
and is closed by an **alpha tag** when the suite is green. When *all* streams are
merged and the release checklist passes, **one** `develop`→`main` PR promotes the
release through beta → rc → GA.

```
main     ●───────────────────────────────●── v0.2.0-beta.1 ─●── rc.1 ─●── v0.2.0
          \                              /
develop    ●──●──●──●──●──●──●──●──●──●──●   (alpha.1 … alpha.7)
           A  A  B  B  C  D  E  F  G  ↑
                                      release PR opens here
```

### 2.2 When to commit to `develop` — commit-as-you-complete

- **Commit the moment a logical task is complete.** Do not batch several tasks into
  one commit, and never leave a finished task uncommitted. One Conventional Commit
  per logical change, on a `feat/…` | `fix/…` | `chore/…` | `refactor/…` branch off
  `develop` (see [CONTRIBUTING §2–3](../CONTRIBUTING.md)). This is a standing rule,
  not a per-release one — it also governs the documentation work in this plan.
- Merge the branch back into `develop` when **its own tests are green**.
- **Tag `v0.2.0-alpha.N` on `develop` at the close of each work-stream**, once
  `PYTHONPATH=. pytest -q` passes for the whole suite. That tag is the "this stream
  is done / cut an alpha" signal. Alpha tags are allowed on `develop` only
  (see [CONTRIBUTING §2](../CONTRIBUTING.md) branch table).

```bash
# commit a completed task, then close the stream on develop
git commit -m "fix(modules): html-escape interpolated values in forensic report"
# … remaining stream tasks, each its own commit …
git checkout develop
PYTHONPATH=. pytest -q            # whole suite must pass
git tag v0.2.0-alpha.N
git push origin develop --tags
```

### 2.3 When to open the release PR — `develop` → `main`

Open the `develop`→`main` PR **only when every work-stream (A–G) is merged** and the
[CONTRIBUTING §7](../CONTRIBUTING.md) pre-merge checklist passes:

**Definition of releasable (mirrors CONTRIBUTING §7):**

- [ ] `PYTHONPATH=. pytest -q` — all tests pass
- [ ] `setup.py version=` bumped to `0.2.0`
- [ ] `CHANGELOG.md` — `[Unreleased]` entries moved under a `[0.2.0]` heading
- [ ] `docs/` cross-references verified (no broken links)
- [ ] `python setup.py sdist` succeeds
- [ ] `python build_exe.py release` succeeds
- [ ] Smoke test: `fm dupes --help`, `fm search --help`, `fm devices --help`, GUI launches
- [ ] **No HIGH-severity open security findings** → **S2 must be fixed** (it is, in WS-A)

The PR then walks the stable-channel tags on `main`
(`v0.2.0-beta.1` → soak → `v0.2.0-rc.1` → `v0.2.0` GA). Full commands in
[§5 Release Runbook](#5-release-execution-runbook).

---

## 3. Consolidated Backlog — Single Index

Every open item across the four reviews, mapped to a commit type, version impact,
and work-stream. Per-item **Where/Why/How** detail lives in the linked tracker cell.
This is the "tackle any of them" master list.

### Security — from [`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md) Part 2

| ID | Severity | Title | Commit type | Ver | WS |
| --- | --- | --- | --- | --- | --- |
| S2 | 🔴 High | Forensic HTML report XSS (no `html.escape`) | `fix(modules)` | PATCH | **A** |
| S4 | 🟠 Med | Trash-restore trusts `.trashinfo` path → arbitrary write | `fix(modules)` | PATCH | B |
| S7 | 🟠 Med | System Cleanup blanket-classifies `/tmp`/cache as junk | `fix(modules)` | PATCH | B |
| S5 | 🟠 Med | Plugin loader executes arbitrary local Python | `fix(ui)` | PATCH | B |
| S6 | 🟠 Med | `secure_delete` overstates guarantee; trash fallback | `fix(modules)` | PATCH | B |
| S8 | 🟠 Med | Credential material world-readable; password leak | `fix(modules)` | PATCH | B |
| S9 | 🟡 Low | Unhardened XML parsing (billion-laughs) | `fix(modules)` | PATCH | B |
| S10 | 🟡 Low | No config validation; blind merge of `config.json` | `fix(core)` | PATCH | B |
| S11 | 🟡 Low | Opening scanned files via OS handler | `fix(ui)` | PATCH | B |
| S12 | 🟡 Low | Forensic outputs world-readable | `fix(modules)` | PATCH | B |
| S13 | 🟡 Low | Decompression-bomb exposure (Pillow/PDF) | `fix(modules)` | PATCH | B |

### Documentation — from [`NOTES_REVIEW.md`](./NOTES_REVIEW.md) §3–4

| ID | Title | Commit type | Ver | WS |
| --- | --- | --- | --- | --- |
| D4/D5 | TSOT `dataforge/` path-prefix audit (~16 unprefixed refs) | `docs` | — | A |
| — (3.1) | Full path-audit sweep of ARCHITECTURE + TSOT | `docs` | — | A |
| — (3.2) | Add "Last verified: YYYY-MM-DD" datestamps to review/source docs | `docs` | — | A |
| — (3.3) | Drop the TSOT A5 staleness `[!WARNING]` caveat after audit | `docs` | — | A |
| — | Reconcile/close NOTES_REVIEW.md (D1–D3 already fixed in source) | `docs` | — | A |

> **Note:** NOTES_REVIEW D1 (broken anchor), D2 (test count "224"), D3 (dead
> `docs/reviews/01` refs) are **already resolved in the source docs** — those strings
> now survive only *inside NOTES_REVIEW.md itself* as its audit record (verified,
> see [§1.2](#12-provenance--these-findings-are-code-verified-not-assumed)). WS-A
> closes the file out rather than re-fixing them.

### Engineering & Process — from [`IMPROVEMENT_PLAN.md`](./IMPROVEMENT_PLAN.md) §4.1

| Item | Title | Commit type | Ver | WS |
| --- | --- | --- | --- | --- |
| P0.1 | CI (GitHub Actions): pytest + ruff + mypy + coverage on push/PR | `chore(repo)` | — | A |
| P0.2 | Linting/formatting config (ruff + black) | `chore(build)` | — | A |
| P0.3 | Type-check config (mypy/pyright) | `chore(build)` | — | A |
| P0.4 | Pre-commit hooks | `chore(repo)` | — | A |
| P0.5 | Coverage reporting | `chore(repo)` | — | A |
| P0.6 | Migrate `setup.py` → `pyproject.toml` | `chore(build)` | — | A |
| P0.7 | Pin security libs + `pip-audit`/Dependabot | `chore(build)` | — | A |

### Interaction Correctness — [`IMPROVEMENT_PLAN.md`](./IMPROVEMENT_PLAN.md) §6 Phase 2c

| ID | Title | Commit type | Ver | WS |
| --- | --- | --- | --- | --- |
| 2c.1 | Kill file-vs-folder Yes/No/Cancel riddle | `fix(ui)` | PATCH | C |
| 2c.2 | Unify settings persistence (autosave + "Saved ✓") | `fix(ui)` | PATCH | C |
| 2c.3 | De-duplicate dark-mode control | `fix(ui)` | PATCH | C |
| 2c.4 | Progressive disclosure instead of tier-hiding | `feat(ui)` | MINOR | C |
| 2c.5 | Destructive preview as scrollable checklist | `feat(ui)` | MINOR | C |
| 2c.6 | Name the running task in the status bar | `fix(ui)` | PATCH | C |
| 2c.7 | Rich-text help + inline "What's this?" | `feat(ui)` | MINOR | C |

### IA, Naming & Parity — [`IMPROVEMENT_PLAN.md`](./IMPROVEMENT_PLAN.md) §6 Phase 2d

| ID | Title | Commit type | Ver | WS |
| --- | --- | --- | --- | --- |
| 2d.1 | Task-oriented sidebar grouping | `refactor(ui)` | — | D |
| 2d.2 | Merge Tools + Action Builder → "Automations" | `feat(ui)` | MINOR | D |
| 2d.3 | Rename labels (Studio→Metadata & EXIF, etc.) | `refactor(ui)` | — | D |
| 2d.4 | `fm devices` GUI → "Storage & Devices" view | `feat(ui)` | MINOR | D |
| 2d.5 | Stray-name consistency sweep | `refactor` | — | D |

### Motion, Empty/Error, A11y — [`IMPROVEMENT_PLAN.md`](./IMPROVEMENT_PLAN.md) §6 Phase 2e

| ID | Title | Commit type | Ver | WS |
| --- | --- | --- | --- | --- |
| 2e.1 | Sidebar collapse + view-switch crossfade animation | `feat(ui)` | MINOR | E |
| 2e.2 | Replace Braille spinner with QProgressBar indeterminate | `fix(ui)` | PATCH | E |
| 2e.3 | "Reduce motion" settings flag | `feat(ui)` | MINOR | E |
| 2e.4 | Focus-ring token + `:focus` outline rules | `feat(design)` | MINOR | E |
| 2e.5 | Purposeful empty states + friendly errors | `feat(ui)` | MINOR | E |
| 2e.6 | Screen-reader accessible names + colour-blind channel | `feat(ui)` | MINOR | E |
| 2e.7 | Sidebar icon set (16–20 monochrome SVGs) | `feat(design)` | MINOR | E |

### Architecture Consolidation — [`IMPROVEMENT_PLAN.md`](./IMPROVEMENT_PLAN.md) §1, §4.2

| Item | Title | Commit type | Ver | WS |
| --- | --- | --- | --- | --- |
| ARCH.1 | Consolidate two filter engines onto `SearchQuery` | `refactor(actions)` | — | F |
| ARCH.2 | Pick one metadata cleaner (exiftool-backed) | `refactor(modules)` | — | F |
| ARCH.3 | Adopt or delete `LocalProvider`/`FileProvider` | `refactor(core)` | — | F |
| ARCH.4 | Root-confinement guard in `FileActionService` | `feat(core)` | MINOR | F |
| ARCH.5 | Tamper-evident audit-log hook in `FileActionService` | `feat(core)` | MINOR | F |
| ARCH.6 | Stream carving instead of buffering to RAM | `refactor(modules)` | — | F |

### Brand & DoD — [`EXECUTIVE_SUMMARY.md`](./EXECUTIVE_SUMMARY.md) "Open Brand Tasks"

| Item | Title | Commit type | Ver | WS |
| --- | --- | --- | --- | --- |
| BR.1 | GitHub description + topics (forensics, automation, data-discovery) | — (repo settings) | — | G |
| BR.2 | `setup.py` description updated with tagline | `chore(build)` | — | G |
| BR.3 | GUI About shows "DataForge" + tagline | `feat(ui)` | MINOR | G |
| BR.4 | Final Definition-of-Done sweep | `docs` | — | G |

### Testing gaps — [`IMPROVEMENT_PLAN.md`](./IMPROVEMENT_PLAN.md) §4.3 (land with their WS)

| Guard | For | WS |
| --- | --- | --- |
| Forensic HTML report escapes `<script>` filename | S2 | A |
| Malicious `.trashinfo` (absolute/`..`) → restore confined | S4 | B |
| Cleanup never flags user folder as blanket junk | S7 | B |
| Config out-of-range/unknown keys → clamped/ignored | S10 | B |
| Settings persistence round-trip | 2c.2 | C |
| GUI smoke test (pytest-qt) mounts each view | 2d/2e | D/E |

---

## 4. Work-Streams — the Ordered "How"

Streams run **in order** (stabilize-first). Each closes with an alpha tag on
`develop` once `PYTHONPATH=. pytest -q` is green. Every stream is stated as
**Where / Why / How** ([§1.1](#11-documentation-standard--every-item-answers-where--why--how)).

### WS-A — Stabilize & Doc Truth → `v0.2.0-alpha.1`

- **Where:** `.github/workflows/`, `pyproject.toml`, `.githooks/`,
  `dataforge/modules/forensics.py:581-625`, `docs/TECHNICAL_SOURCE_OF_TRUTH.md`,
  `docs/reviews/NOTES_REVIEW.md`. Items P0.1–P0.7, S2, D4/D5, NOTES_REVIEW 3.1–3.3.
- **Why:** there is no automated green-gate, so regressions can land silently; S2 is
  a HIGH finding that makes court-grade forensic output unsafe and **blocks the
  release**; and the docs still misstate paths, eroding trust in the source map.
- **How:** add a GitHub Actions workflow running `pytest`+`ruff`+`mypy`+coverage on
  push/PR to `develop`+`main`; add ruff/black/mypy config, pre-commit hooks, and
  migrate packaging to `pyproject.toml` with `pip-audit`/Dependabot; `html.escape()`
  every interpolated value in the forensic report + a `<script>`-filename regression
  test; run the `dataforge/` path audit over TSOT and retire the A5 staleness caveat.

**Representative commits:**
```
chore(repo): add GitHub Actions CI (pytest + ruff + mypy + coverage)
chore(build): add ruff + black config and mypy settings
chore(repo): add pre-commit hook config
chore(build): migrate setup.py metadata to pyproject.toml
chore(build): pin security libs and enable pip-audit / Dependabot
fix(modules): html-escape interpolated values in forensic report
test(modules): guard forensic report against script-tag filename
docs: prefix core and modules paths with dataforge in source-of-truth
docs: add last-verified datestamps and retire staleness caveat
```
**Version impact:** PATCH (from S2). **Gate:** CI must be green before WS-B opens.

### WS-B — Trust & Safety (remaining security) → `v0.2.0-alpha.2`

- **Where:** `dataforge/modules/recovery.py:225-250` (S4),
  `system_cleanup.py:249` (S7), `dataforge/ui/plugin_loader.py:38-51` (S5),
  `forensics.py` (S6/S9/S12/S13), `password_tools.py:246` (S8),
  `dataforge/core/config.py` (S10). Items S4–S13.
- **Why:** these are live abuse paths — arbitrary file write from a crafted
  `.trashinfo`, blanket deletion of `/tmp` and cache trees, in-process execution of
  unsigned plugins, false destruction guarantees, world-readable secrets, XML
  entity-expansion DoS, and unvalidated config merge. Each can cause data loss,
  code execution, or disclosure on untrusted input.
- **How:** work AUDIT_FINDINGS "Recommended remediation order" — S4→S7→S5→S6→S8→
  S9→S10→S11→S12→S13 — one `fix(...)` per finding, each paired with the regression
  test named in [§3 Testing gaps]. Forensic-soundness (UTC timestamps, provenance)
  noted here; the audit-log + root-confinement seam-controls land in WS-F on
  already-hardened code.

**Representative commits:**
```
fix(modules): confine trash-restore paths and block traversal
test(modules): guard trash-restore against crafted trashinfo paths
fix(modules): allow-list cleanup targets and skip sockets and fifos
fix(ui): gate plugin loading behind opt-in flag with load logging
fix(modules): make secure_delete best-effort and drop trash fallback
fix(modules): write credential and hash files with 0600 permissions
fix(modules): parse xml with defusedxml to block entity expansion
fix(core): validate config types ranges and enums on load
fix(ui): confirm before opening executables via the OS handler
fix(modules): write forensic report artefacts with 0600 permissions
fix(modules): cap image pixels and pdf pages against decompression bombs
```
**Version impact:** PATCH (cumulative).

### WS-C — Interaction Correctness (Phase 2c) → `v0.2.0-alpha.3`

- **Where:** `dataforge/ui/views/base.py` (2c.1/2c.5/2c.7),
  `views/settings.py:199-273` (2c.2), `app.py` dark-mode + tier + busy-bar
  (2c.3/2c.4/2c.6). Items 2c.1–2c.7.
- **Why:** these are the highest-friction trust defects — a Yes/No/Cancel riddle for
  file-vs-folder, settings that silently do or don't persist, features hidden behind
  experience tiers, and a truncated destructive preview the user can't review row by
  row. They directly undermine confidence in destructive operations.
- **How:** replace the message-box riddle with `choose_file`/`choose_directory`
  entry points; autosave settings with a transient "Saved ✓"; make one dark-mode
  control writable and mirror it; show all sidebar groups and gate complexity behind
  "More options"; render destructive preview as a scrollable checkable table; name
  the running task in the busy bar; render help as markdown. Add a settings
  round-trip test.

**Representative commits:**
```
fix(ui): replace file-or-folder message box with explicit pickers
fix(ui): autosave settings with a transient saved indicator
fix(ui): make one dark-mode control writable and mirror the other
feat(ui): show all sidebar groups behind progressive disclosure
feat(ui): render destructive preview as a scrollable checklist
fix(ui): name the running task and counts in the busy status bar
feat(ui): render help as markdown with inline whats-this affordance
test(ui): round-trip settings persistence
```
**Version impact:** MINOR (2c.4/2c.5/2c.7 are `feat`).

### WS-D — IA, Naming & Parity (Phase 2d) → `v0.2.0-alpha.4`

- **Where:** `dataforge/ui/app.py:322-328` (sidebar groups), view labels across
  `dataforge/ui/views/`, new "Storage & Devices" view over `fm devices`. Items 2d.1–2d.5.
- **Why:** navigation is organised around developer module boundaries, not user
  tasks — duplicate-sounding destinations, split Hardware/Performance, and `fm devices`
  with no GUI path. This is the parity/coherence gap and the reason the release is a
  MINOR.
- **How:** regroup the sidebar into Home / Find & Organize / Clean & Optimize /
  Recover & Investigate / System; merge Tools + Action Builder into "Automations"
  with sub-tabs; apply the label renames from IMPROVEMENT_PLAN §2.3; add the Storage
  & Devices view; sweep residual "File Manager"/"filemanager-utils" names. Add a
  pytest-qt smoke test mounting every view.

**Representative commits:**
```
refactor(ui): regroup sidebar into task-oriented sections
feat(ui): merge tools and action builder into automations
refactor(ui): rename module labels to task-oriented names
feat(ui): add storage and devices view surfacing fm devices
refactor: sweep residual file-manager naming across the app
test(ui): smoke-mount every view with pytest-qt
```
**Version impact:** MINOR.

### WS-E — Motion, Empty/Error, A11y (Phase 2e) → `v0.2.0-alpha.5`

- **Where:** `dataforge/ui/app.py:220-234` (Braille spinner), `theme_tokens.py`
  (focus-ring), views (empty/error states, accessible names), new
  `dataforge/ui/resources/icons/`. Items 2e.1–2e.7.
- **Why:** the spinner is a character hack, there is no focus-ring rule after
  `outline:0` was removed, empty/error states are generic, group identity is
  colour-only, and there is no reduce-motion or screen-reader support — accessibility
  and polish gaps that exclude keyboard and assistive-tech users.
- **How:** animate sidebar collapse + view crossfade; replace the spinner with an
  indeterminate `QProgressBar`; add a reduce-motion flag; add a focus-ring token and
  `:focus` rules; give each view a purposeful empty state and friendly errors; add
  accessible names and a non-colour channel (icons + spacing); ship a monochrome
  sidebar icon set.

**Representative commits:**
```
feat(ui): animate sidebar collapse and view-switch crossfade
fix(ui): replace braille spinner with indeterminate progress bar
feat(ui): add reduce-motion preference
feat(design): add focus-ring token and focus outline rules
feat(ui): add per-view empty states and friendly error messages
feat(ui): add accessible names and colour-blind icon channel
feat(design): add monochrome sidebar icon set
```
**Version impact:** MINOR.

### WS-F — Architecture Consolidation → `v0.2.0-alpha.6`

- **Where:** `modules/search.py` + `core/actions/filters.py` (ARCH.1),
  `modules/cleaner.py` + `modules/metadata.py` (ARCH.2), `core/provider.py` (ARCH.3),
  `core/services/` `FileActionService` (ARCH.4/ARCH.5), carving in `modules/forensics.py`
  (ARCH.6). Items ARCH.1–ARCH.6.
- **Why:** two filter engines and two metadata cleaners are duplicate sources of
  truth that create long-term correctness risk; `LocalProvider` is dead
  infrastructure; and the service seam is the right single place to enforce
  root-confinement and a tamper-evident audit log. Landing these after security means
  the new controls sit on hardened code.
- **How:** route Action Builder filters through `SearchQuery`; pick the exiftool
  engine as the one metadata cleaner; adopt-or-delete `LocalProvider`; add a
  root-confinement guard and an append-only audit-log hook in `FileActionService`;
  stream carving instead of buffering to RAM. Keep the existing suites green through
  each refactor.

**Representative commits:**
```
refactor(actions): route action-builder filters through search-query
refactor(modules): make exiftool the single metadata cleaner
refactor(core): remove dead local-provider seam
feat(core): enforce root confinement in file-action service
feat(core): append every mutation to a tamper-evident audit log
refactor(modules): stream carving instead of buffering to memory
```
**Version impact:** MINOR (ARCH.4/ARCH.5 are `feat`).

### WS-G — Brand & Release Polish → `v0.2.0-alpha.7`

- **Where:** GitHub repo settings, `setup.py` description, GUI About dialog,
  `EXECUTIVE_SUMMARY.md` Definition of Done. Items BR.1–BR.4.
- **Why:** the brand tasks and DoD are the last open items on the healthy-project
  checklist; leaving them undone means the release ships with mismatched metadata and
  an unfinished DoD.
- **How:** update the GitHub description/topics (repo setting, not a commit); update
  the `setup.py` description with the tagline; show "DataForge" + tagline in About;
  tick off the Definition of Done. Then open the release PR.

**Representative commits:**
```
chore(build): update setup.py description with the DataForge tagline
feat(ui): show DataForge name and tagline in the about dialog
docs: tick off definition of done and open brand tasks
```
BR.1 (GitHub description/topics) is a repo-settings action, not a commit.
**Version impact:** MINOR (BR.3).

**After WS-G closes `alpha.7`, open the release PR** (see §2.3 and §5).

---

## 5. Release Execution Runbook

Once all seven alpha streams are merged and the §2.3 checklist passes
(commands from [CONTRIBUTING §6–7](../CONTRIBUTING.md)):

```bash
# 1. Prep on develop
git checkout develop
PYTHONPATH=. pytest -q
# bump setup.py version= to 0.2.0
# move CHANGELOG [Unreleased] entries under a new [0.2.0] - 2026-XX-XX heading
git add setup.py CHANGELOG.md
git commit -m "chore(release): bump to 0.2.0"

# 2. Release PR develop -> main, then beta/rc/GA on main
git checkout main
git merge develop --no-ff
git tag v0.2.0-beta.1
git push origin main --tags
# soak / smoke test; fix-forward on develop and re-merge if needed
git tag v0.2.0-rc.1 && git push origin main --tags
git tag v0.2.0     && git push origin main --tags   # GA

# 3. Back-merge and open next cycle
git checkout develop && git merge main && git push origin develop
# bump setup.py to 0.2.1.dev
```

Pre-tag gate for every stable tag: `python setup.py sdist` and
`python build_exe.py release` succeed; `fm dupes/search/devices --help` and the GUI
launch; no HIGH-severity open security finding.

---

## 6. Verification & Test Mapping

**Green-gate (every stream):** no `alpha.N` tag is cut until `PYTHONPATH=. pytest -q`
passes for the whole suite ([CONTRIBUTING §5](../CONTRIBUTING.md)).

| WS | Regression / smoke tests |
| --- | --- |
| A | Forensic report escapes `<script>` filename (S2); CI runs the full suite on push |
| B | `.trashinfo` traversal confined (S4); cleanup spares user folders (S7); config clamps bad keys (S10) |
| C | Settings persistence round-trip (2c.2) |
| D | pytest-qt mounts every view incl. Storage & Devices (2d.4); `fm devices --help` smoke |
| E | pytest-qt mounts views with animations/empty states; reduce-motion honored |
| F | Existing filter/metadata/service suites stay green after consolidation; audit-log append verified |
| G | GUI About renders tagline; `python setup.py sdist` + `build_exe` succeed |

**Release verification:** the §2.3 "Definition of releasable" checklist gates the
`develop`→`main` PR; the §5 pre-tag gate gates each stable tag.

---

## 7. Status Tracking

Update the `WS` streams here as they close; the detailed per-item status stays in
[`IMPROVEMENT_PLAN.md`](./IMPROVEMENT_PLAN.md) §6 and
[`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md).

| Stream | Scope | Tag | Status |
| --- | --- | --- | --- |
| WS-A | Stabilize & Doc Truth (CI, tooling, S2, doc audit) | `v0.2.0-alpha.1` | ⏳ Not started |
| WS-B | Trust & Safety (S4–S13) | `v0.2.0-alpha.2` | ⏳ Not started |
| WS-C | Interaction Correctness (2c) | `v0.2.0-alpha.3` | ⏳ Not started |
| WS-D | IA, Naming & Parity (2d) | `v0.2.0-alpha.4` | ⏳ Not started |
| WS-E | Motion, Empty/Error, A11y (2e) | `v0.2.0-alpha.5` | ⏳ Not started |
| WS-F | Architecture Consolidation | `v0.2.0-alpha.6` | ⏳ Not started |
| WS-G | Brand & Release Polish | `v0.2.0-alpha.7` | ⏳ Not started |
| — | Release PR `develop`→`main` | `v0.2.0` GA | ⏳ Gated on A–G |
