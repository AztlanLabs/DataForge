# Improvement Plan — UX, Engineering & Phased Roadmap

**Date:** 2026-07-10 · **Updated:** 2026-07-11 · **Last verified:** 2026-07-11
**Consolidates** the old `03_UIUX_REVIEW.md` + `04_IMPROVEMENTS_AND_ROADMAP.md` + `05_VISUAL_DESIGN_SYSTEM.md` + `06_UIUX_IMPLEMENTATION_PLAN.md` + cross-cutting quality observations from `01_CODE_REVIEW_AND_BUGS.md`. No information was removed — this is a merge, not a rewrite.

---

## 1. Cross-cutting Architecture Issues

*Carried over from the code-review pass. These are structural overlaps that create long-term correctness risk — they belong in the improvement roadmap, not the bug tracker.*

- **Two parallel filter engines.** `modules/search.py` (`SearchQuery`) and `core/actions/filters.py` are independent implementations of the same size/date/name filtering. Consolidate Action Builder filters onto `SearchQuery`.
- **Two metadata-cleaning implementations.** `modules/cleaner.py::MetadataCleaner.remove_metadata` (returns `bool`, re-encodes JPEG) vs `modules/metadata.py::MetadataEngine.remove_metadata` (returns dict, exiftool-backed). Pick one source of truth.
- **`LocalProvider`/`FileProvider` in `core/provider.py` is dead code.** Either adopt it as the IO seam or remove it.
- **Error surfacing is inconsistent** — some modules return `{"error": ...}` dicts, some raise, some `print`. A single result/error convention would make UI and CLI handling uniform.

---

## 2. UX/UI Design Review

*One-line assessment from doc 03:* the app is feature-rich and visually competent, but organised around developer module boundaries, not user tasks. The biggest wins are in information architecture, naming, and interaction consistency.

### 2.1 What's already good
- Grouped, colour-coded left rail with collapsible sections
- Consistent preview → confirm → execute pattern with dry-run and cancellation
- Theme-aware QSS generated from a single semantic token table (`ui/theme_tokens.py`) — 46 colour tokens per theme, all WCAG AA validated (≥4.5:1)
- Checkbox checkmarks, spinbox arrows, and combobox dropdown arrows are themed inline SVGs

### 2.2 Information Architecture — current vs proposed

**Current groups** (`app.py:322-328`): Overview, File Utilities, System Maintenance, Advanced Analysis, Application.

Issues: "Tools & Workflows" vs "Action Builder" both sound like multi-step builders. "Media Tools" under File Utilities but "Metadata Studio" under Advanced Analysis. "Hardware Diagnostics" and "Performance" split across two groups. `fm devices` has no GUI.

**Proposed task-oriented grouping:**

| Group | Views |
| --- | --- |
| **Home** | Dashboard |
| **Find & Organize** | Search, Duplicates, Organize/Rename, Media, Metadata, **Automations** (merged Tools + Action Builder) |
| **Clean & Optimize** | System Cleanup, **Storage & Devices** (new), Performance |
| **Recover & Investigate** | File Recovery, Forensics, Integrity/Hashing |
| **System** | Hardware, Settings, About & Help |

### 2.3 Naming & Labels

| Current | Proposed | Status |
| --- | --- | --- |
| Metadata Studio | Metadata & EXIF | ⏳ |
| Forensics Lab | Forensics | ⏳ |
| Hardware Diagnostics | Hardware Info | ⏳ |
| Tools & Workflows + Action Builder | Automations (with sub-tabs) | ⏳ |
| Search & Organize | Search | ⏳ |
| System Cleanup | Clean Up Space | ⏳ |
| Experience Level: Basic/Advanced/Expert | Detail level: Simple / Standard / Everything | ⏳ |
| Product name (three different names) | DataForge | ✅ Resolved |

### 2.4 Interaction Problems (ranked by friction)

| # | Problem | Risk | Status | Touch points |
| --- | --- | --- | --- | --- |
| 4.1 | File-vs-folder picker uses Yes/No/Cancel riddle | 🔴 | ⏳ | `views/base.py:244-262` |
| 4.2 | Settings persistence inconsistent (some autosave, some need Save button) | 🔴 | ⏳ | `views/settings.py:199-214,237-240,270-273` |
| 4.3 | Experience tier *hides* sidebar groups → discoverability cliff | 🔴 | ⏳ | `app.py:669-681,869-971` |
| 4.4 | Two controls for dark mode (sidebar checkbox + Settings dropdown) | 🟠 | ⏳ | `app.py:731`, `settings.py:75-83` |
| 4.5 | Help rendered as plain text; markdown shows literal `#`/`*` | 🟢 | ⏳ | `views/base.py:37-56` |
| 4.6 | Destructive preview is a truncated text message, not a reviewable list | 🔴 | ⏳ | `views/base.py:58-88` |
| 4.7 | Busy lock shows generic message without naming the running task | 🟠 | ⏳ | `app.py:562-563` |

**Fixes for each** (see §6 Implementation Status for the file-level backlog):

- **4.1** — Remove the Yes/No/Cancel `QMessageBox`; expose `choose_file(...)` / `choose_directory(...)` entry points.
- **4.2** — Autosave everything; transient "Saved ✓" affordance; delete the three ad-hoc save button colours.
- **4.3** — Show all sidebar groups by default; gate complexity inside views behind "More options" expanders. If tiers kept interim, add "Showing simplified view — [Show all features]" banner.
- **4.4** — One writable control; Settings reflects sidebar state. Optionally add "Follow system" option.
- **4.5** — Switch to `setMarkdown` / `setHtml`; add inline "What's this?" on destructive actions.
- **4.6** — Replace `QMessageBox` with a scrollable, checkable table (per-row opt-out, reclaimed-space total, Cancel default, destructive buttons tinted with `danger` token).
- **4.7** — Replace "Busy: please wait…" with live task name + counts from `progress_signal`.

### 2.5 Accessibility

| Area | Gap | Status |
| --- | --- | --- | --- |
| Contrast | Two colours failed WCAG AA (`#5bc0de` 2.09:1, `#ffc107` 1.63:1) | ✅ Fixed — replaced by AA-validated token table |
| Keyboard focus | `outline: 0` suppression removed; no focus-ring token rule yet | ⏳ Partly done (suppression gone; ring not yet styled) |
| Screen readers | No `setAccessibleName`/`setAccessibleDescription` calls; status not announced | ⏳ Open |
| Colour-only meaning | Group identity conveyed by colour alone | ⏳ Open (icons + text channel planned) |
| Motion | Continuous spinner; no reduce-motion preference | ⏳ Open |

### 2.6 Empty & Error States

- Default empty message is generic: "No matching items were available for this action." → Each view needs a purposeful empty state with an example and primary action.
- Errors surface as raw `str(error)` via `show_workflow_error` → route through friendly messages.
- Windows-only no-ops (e.g. Recycle Bin scan) should state "Not supported on this platform yet."

---

## 3. Visual Design System

### 3.1 Colour System

**Current state (✅ fixed):** a single semantic token module (`ui/theme_tokens.py`) defines 46 colour tokens per theme — all WCAG AA validated (≥4.5:1 for body text). `generate_qss(mode)` produces both themes from one template. Per-widget hex colours migrated to dynamic-property variant rules (`setProperty("variant", "danger")` + `QPushButton[variant="danger"] { … }`). Zero Bootstrap-era or Tailwind-ish legacy hex literals in `ui/**/*.py`.

**Surface brightness fix (✅):** light content surfaces `#ffffff`→`#f7f7f8`; dark base `#1c1c20`, elevated `#26262c`. The "too bright / too crushed" complaint is resolved.

**Semantic token table (AA validated):**

| Token | Light | Dark |
| --- | --- | --- |
| `primary` | `#2563eb` | `#60a5fa` |
| `success` | `#047857` | `#34d399` |
| `warning` | `#b45309` | `#fbbf24` |
| `danger` | `#dc2626` | `#f87171` |
| `info` | `#0369a1` | `#38bdf8` |

### 3.2 Typography (✅)

Named scale constants in `theme_tokens.py` — `caption 11 / body 13 / subheading 15 / heading 18 / display 24`. Every `font-size: Npx` literal across the app maps to a `TYPE_SCALE` constant. Font stacks: `"Segoe UI", "Helvetica Neue", Arial, sans-serif` + `"Courier New", Consolas, monospace` for diagnostic panels.

### 3.3 Iconography

| Item | Status |
| --- | --- |
| Checkbox checkmark SVG glyph | ✅ Done |
| QComboBox dropdown arrow (themed SVG) | ✅ Done |
| Sidebar icon set (16–20 monochrome SVGs) | ⏳ Open — `ui/resources/icons/` doesn't exist yet |
| Destructive-action icons paired with `danger` token | ⏳ Open |

### 3.4 Motion & Animation

| Item | Status |
| --- | --- |
| Sidebar group expand/collapse animation (QPropertyAnimation) | ⏳ Open — import exists but never instantiated |
| View-switch crossfade (QGraphicsOpacityEffect) | ⏳ Open |
| Braille-character spinner replaced by QProgressBar indeterminate | ⏳ Open — `spinner_chars` hack still active at `app.py:220-234` |
| "Reduce motion" preference setting | ⏳ Open |
| Focus-ring token + :focus outline rules | ⏳ Open — `outline: 0` is gone, but no replacement rule yet |

---

## 4. Engineering Improvements

### 4.1 Repository & Process

| Item | Status |
| --- | --- |
| Under version control (git + `.gitignore`) | ✅ Done |
| Test suite green — 255 tests pass | ✅ Done |
| CI (GitHub Actions) running pytest/lint/type-check on push | ⏳ Open |
| Linting (ruff + black) | ⏳ Open |
| Type checking (mypy/pyright) | ⏳ Open |
| Pre-commit hooks | ⏳ Open |
| Coverage reporting | ⏳ Open |
| Migrate to `pyproject.toml` | ⏳ Open |
| Pin security-relevant libs + `pip-audit`/Dependabot | ⏳ Open |

### 4.2 Architecture Improvements

- **Consolidate filter engines** — Action Builder filters → thin wrappers over `SearchQuery` (M).
- **Pick one metadata cleaner** — choose the exiftool-backed engine as single source of truth (M).
- **Shared rename options object** — three rename orchestrations all delegate to `FileActionService` but entry points should share one options object (M).
- **Adopt or delete `LocalProvider`** — it's dead infrastructure (M).
- **Root-confinement guard in `FileActionService`** — so no consumer can act outside the user-selected root even via non-scanner paths (⏳).
- **Audit log hook in `FileActionService`** — every delete/move/rename appended to tamper-evident log (M).
- **Stream carving instead of buffering** — cap and stream rather than reading up to `max_size` into RAM (M).

### 4.3 Testing Gaps

- ✅ Hash algorithm matrix (incl. sha512/unsupported) — guards M1.
- ✅ Corrupt/empty integrity snapshot → structured error — guards M2.
- ✅ Symlink loop & out-of-tree symlink — guards M3/S3.
- ✅ Token-regression suite (`tests/test_theme_tokens.py` — 30 tests) — guards 2b.1.
- ⏳ Malicious `.trashinfo` with absolute/`..` Path → restore confined — guards S4.
- ✅ Forensic HTML report with `<script>` in filename → output escaped — guards S2.
- ⏳ System cleanup never flags user-supplied folder as blanket junk — guards S7.
- ⏳ Config with out-of-range/unknown keys → clamped/ignored — guards S10.
- ⏳ GUI smoke test (pytest-qt) — constructs each view and mounts/unmounts it.
- ⏳ Settings persistence round-trip test — guards 2c.2.

---

## 5. Phased Roadmap

### Phase 0 — Stabilize (1 sprint) 🔴

✅ git init + `.gitignore` · ✅ unbreak test suite (H1) · ✅ fix crashes (M1–M3) · ✅ lock cache (M5).
✅ CI running pytest + ruff + mypy + coverage + pip-audit · ✅ escape forensic report (S2).

### Phase 1 — Trust & Safety (1–2 sprints) 🟠

✅ SHA-256 default + integrity algo stored · ✅ dedup byte-compare · ✅ symlink confinement in scanner.
⏳ trash-restore confinement (S4) · ⏳ cleanup allow-listing (S7) · ⏳ secret hygiene (S8) · ⏳ config validation (S10) · ✅ regression test for S2 · ⏳ regression tests for S4/S7.

### Phase 2 — Coherence (2–3 sprints)

✅ **Sprint A** — surface brightness, combo arrow, outline:0 removal, design-token module, type scale, per-widget colour migration. 255 tests green, zero legacy hex.

⏳ **Sprint B (2c)** — 7 interaction fixes: path picker, settings persistence, dark-mode dedup, progressive disclosure, destructive checklist, named busy task, rich help.

⏳ **Sprint C (2d+2e)** — IA/naming, devices GUI, sidebar animation, Braille spinner replacement, reduce-motion, focus-ring, empty/error states, screen-reader support, icon set.

### Phase 3 — Grow (ongoing)

Task-first dashboard · scheduled cleanup/integrity · saved searches/automations · undo · reporting polish · i18n · plugin trust model.

---

## 6. Implementation Status — Per-Item Backlog

### ✅ Phase 2a — Quick Visual Wins

| # | Done | Item | Risk |
| --- | --- | --- | --- |
| 2a.1 | ✅ | Surface-brightness fix (`#ffffff`→`#f7f7f8`; dark base `#1c1c20`, elevated `#26262c`) | 🟢 |
| 2a.2 | ✅ | Checkbox checkmark SVG glyph + QComboBox themed dropdown arrow | 🟠 |
| 2a.3 | ✅ | Remove `outline: 0` focus suppression | 🟠 |

### ✅ Phase 2b — Design Tokens & Typography

| # | Done | Item | Risk |
| --- | --- | --- | --- |
| 2b.1 | ✅ | Token module `ui/theme_tokens.py` + `generate_qss`/`generate_palette` (replaces two 200-line QSS blocks) | 🟠 |
| 2b.2 | ✅ | Per-widget colour migration to dynamic-property `variant` rules (zero legacy hex) | 🟠 |
| 2b.3 | ✅ | Type-scale constants — all `font-size: Npx` literals mapped to `TYPE_SCALE` | 🟢 |

### ⏳ Phase 2c — Interaction Correctness

| # | Done | Item | Risk | Touch points |
| --- | --- | --- | --- | --- |
| 2c.1 | ⏳ | Kill file-vs-folder riddle (Yes/No/Cancel `QMessageBox`) | 🔴 | `views/base.py:244-262` |
| 2c.2 | ⏳ | Unify settings persistence (autosave + "Saved ✓") | 🔴 | `views/settings.py:199-273` |
| 2c.3 | ⏳ | De-duplicate dark-mode control (one writable, one reads state) | 🟠 | `app.py:731`, `settings.py:75-83` |
| 2c.4 | ⏳ | Progressive disclosure instead of tier-hiding (show all groups) | 🔴 | `app.py:669-681,869-971` |
| 2c.5 | ⏳ | Destructive preview as scrollable checklist (per-row opt-out) | 🔴 | `views/base.py` |
| 2c.6 | ⏳ | Name the running task in the status bar | 🟠 | `app.py:562-563,1102-1146` |
| 2c.7 | ⏳ | Rich-text help + inline "What's this?" | 🟢 | `views/base.py:37-56` |

### ⏳ Phase 2d — Information Architecture, Naming & Parity

| # | Done | Item | Risk |
| --- | --- | --- | --- |
| 2d.1 | ⏳ | Rework sidebar grouping to task-oriented (Home / Find & Organize / Clean & Optimize / Recover & Investigate / System) | 🟠 |
| 2d.2 | ⏳ | Merge Tools & Workflows + Action Builder → "Automations" with sub-tabs | 🟠 |
| 2d.3 | ⏳ | Rename labels: Studio→"Metadata & EXIF", Lab→"Forensics", Diagnostics→"Hardware Info", Search & Organize→"Search", Cleanup→"Clean Up Space", Experience Level→"Detail level" | 🟢 |
| 2d.4 | ⏳ | Surface `fm devices` in the GUI as "Storage & Devices" view | 🟠 |
| 2d.5 | ⏳ | Stray-name consistency sweep (residual "File Manager"/"filemanager-utils") | 🟢 |

### ⏳ Phase 2e — Motion, Empty/Error States, Accessibility Polish

| # | Done | Item | Risk |
| --- | --- | --- | --- |
| 2e.1 | ⏳ | Animate sidebar collapse + view-switch crossfade (dead QPropertyAnimation import) | 🟢 |
| 2e.2 | ⏳ | Replace Braille-character spinner with QProgressBar indeterminate | 🟠 |
| 2e.3 | ⏳ | "Reduce motion" settings flag | 🟢 |
| 2e.4 | ⏳ | Focus-ring token + :focus outline/accelerators | 🟠 |
| 2e.5 | ⏳ | Purposeful per-view empty states; friendly error messages | 🟢 |
| 2e.6 | ⏳ | Screen-reader accessible names + colour-blind channel (icons + spacing) | 🟢 |
| 2e.7 | ⏳ | Sidebar icon set (16–20 monochrome SVGs under `ui/resources/icons/`) | 🟠 |

---

## Explicitly Out of Scope

- Security items S4/S7 (trash-restore, cleanup over-classification) — tracked in [`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md). S2 (forensic XSS) is fixed.
- Custom webfont, general animation framework, logo-asset production — rejected as inappropriate for a file-management utility.
- Product rename — already complete (DataForge). 2d.5 is only a consistency sweep.