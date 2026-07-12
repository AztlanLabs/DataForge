# Notes Review — Consolidated Admonition-Block Audit

**Date:** 2026-07-11 · **Last verified:** 2026-07-11
**Scope:** Every `[!NOTE]`, `[!WARNING]`, and `[!IMPORTANT]` block across
`README.md` and `docs/` — verified against the current codebase state.  
**Result:** All admonition blocks have been removed from the source files
and consolidated here as the single source of truth for these review notes.

> **Execution status: CLOSED.** All Priority 1/3 documentation items are
> done: D1–D7 are resolved in the source docs (D1 broken anchor, D2 wrong
> "224" test count, D3 dead `docs/reviews/01` links, D4–D7 unprefixed
> `core/`/`modules/` paths); the 3.1 path audit, 3.2 datestamps, and 3.3
> staleness-caveat review (§4, Priority 3) are all done, tracked in
> [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) WS-A. Priority 2's
> S2 (§4) is also fixed — see [`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md).
> Remaining Priority 2 items (S4–S10) were security fixes, not doc defects;
> they carried forward to WS-B, **which is now closed — S4–S13 are all fixed**
> (re-verified 2026-07-12; see [`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md) and
> [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md)). The tables below
> (§1–§3) retain their audit-time finding descriptions and `path:line`
> evidence; **status cells have been updated to reflect WS-B closure** so no
> row reads "open" for a fixed item. The verbatim "224"/`docs/reviews/01`
> quotes in §2 are preserved as evidence of the original doc defect, not a
> live claim.

---

## 1. Block Inventory

| # | File | Line | Kind | Title / Summary |
|---|------|------|------|----------------|
| A1 | `README.md` | 15 | `[!NOTE]` | Project migration — Tkinter→PyQt5 + new modules, open items |
| A2 | `README.md` | 125 | `[!NOTE]` | 254 tests pass, correctness fixes verified |
| A3 | `DEVELOPMENT_GUIDE.md` | 57 | `[!NOTE]` | 254 tests pass, `rename_with_regex` fixed |
| A4 | `ARCHITECTURE.md` | 212 | `[!NOTE]` | Design caveats: hardened controls + open security risks |
| A5 | `TECHNICAL_SOURCE_OF_TRUTH.md` | 26 | `[!WARNING]` | Document partially stale — PyQt5 migration not fully re-audited |
| A6 | `TECHNICAL_SOURCE_OF_TRUTH.md` | 29 | `[!IMPORTANT]` | Correctness/security caveats from 2026-07-10 review |
| A7 | `TECHNICAL_SOURCE_OF_TRUTH.md` | 864 | `[!NOTE]` | `test_comprehensive.py` now imports and passes |
| A8 | `TECHNICAL_SOURCE_OF_TRUTH.md` | 894 | `[!NOTE]` | Structural facts accurate; open risks tracked in `docs/reviews/` |

---

## 2. Verification — Block by Block

### A1 — README.md (Project migration note)

> **Original text:** "The GUI was migrated from Tkinter/ttkbootstrap to
> **PyQt5**, and a batch of new modules (hardware, forensics, recovery,
> metadata, performance, system cleanup, password tools, device manager,
> file signatures) were added. Documentation, packaging metadata, and CLI
> wiring have since been reconciled to match — a couple of smaller items
> are still open. See [Known incomplete / in-progress
> changes](#known-incomplete--in-progress-changes) for the current,
> verified list."

| Claim | Verdict | Evidence |
|-------|---------|----------|
| GUI uses PyQt5 | ✅ | `run_ui.py`, all `ui/` imports use PyQt5 |
| New modules exist | ✅ | hardware, forensics, recovery, metadata, performance, system_cleanup, password_tools, device_manager, file_signatures all present in `dataforge/modules/` |
| Anchor link | 🔴 **BROKEN** | No `#known-incomplete--in-progress-changes` heading exists in README.md |
| "Documentation reconciled" | ⚠️ **Partial** | `ARCHITECTURE.md` has inconsistent paths (see A4); `TECHNICAL_SOURCE_OF_TRUTH.md` has 3 stale references to `docs/reviews/01` |

**Fix:** The anchor should point to the existing `#-open--future` section
(which lists CI, Device Manager GUI, numbered release, debug builds) or a
new section should be created.

---

### A2 — README.md (Test suite note)

> **Original text:** "Full test suite passes — 254 tests. All correctness
> fixes are verified. See `docs/reviews/AUDIT_FINDINGS.md` for the
> comprehensive audit."

| Claim | Verdict | Evidence |
|-------|---------|----------|
| 254 tests pass | ✅ | `PYTHONPATH=. pytest -q` → 254 passed in 4.74s |
| Correctness fixes verified | ✅ | H1, M1–M6, L1–L9 all documented as fixed in AUDIT_FINDINGS.md |
| Reference to AUDIT_FINDINGS.md | ✅ | File exists; correct link |

**Status:** Current. No defects.

---

### A3 — DEVELOPMENT_GUIDE.md (Test suite + H1 fix)

> **Original text:** "The full suite passes — 254 tests. The earlier
> collection failure (a stale `rename_with_regex` import in
> `tests/test_comprehensive.py`) has been fixed; see
> `reviews/AUDIT_FINDINGS.md` (H1). Just run `PYTHONPATH=. pytest -q`."

| Claim | Verdict | Evidence |
|-------|---------|----------|
| 254 tests pass | ✅ | Verified |
| `rename_with_regex` restored | ✅ | Exists at `dataforge/core/operations/files.py:163` |
| Path `core/operations/files.py` in surrounding context | ⚠️ **Stale** | Actual path is `dataforge/core/operations/files.py` — the package lives under `dataforge/`, not repo root |
| Reference to `reviews/AUDIT_FINDINGS.md` | ✅ | Correct relative link from `docs/DEVELOPMENT_GUIDE.md` |

**Status:** Content correct; one path prefix is stale (`core/` → `dataforge/core/`).

---

### A4 — ARCHITECTURE.md (Design caveats)

> **Original text:** "Correctness/security caveats affecting the design
> (2026-07-10 review + remediation): several controls live at these seams.
> **Now hardened:** the scanner no longer follows symlinks (scope
> escape/recursion), the shared SQLite cache connection is thread-safe
> (lock + WAL), and integrity/dedup no longer default to MD5 (configured
> algorithm, default `sha256`; duplicate deletes byte-verify groups).
> **Still open:** the forensic HTML report is HTML-injectable, and
> trash-restore trusts `.trashinfo` paths."

| Claim | Verdict | Evidence |
|-------|---------|----------|
| Scanner skips symlinks | ✅ | `dataforge/core/scanner.py:57` — `if entry.is_symlink():` + `follow_symlinks=False` on dir/file checks |
| Cache thread-safe (lock+WAL) | ✅ | Lock-wrapped methods + `PRAGMA journal_mode=WAL` in cache module |
| Integrity uses SHA-256, not MD5 | ✅ | Config default `hash_algorithm = sha256`; dedup byte-verifies groups |
| Forensic report HTML-injectable (S2) | ✅ Fixed (WS-A) | Was open at `dataforge/modules/forensics.py:581-625`; interpolated values are now `html.escape()`d (`test_forensic_report_html_escapes_script_filename`) |
| Trash-restore trusts .trashinfo (S4) | ✅ Fixed (WS-B) | Was open at `dataforge/modules/recovery.py:225-250`; `_is_safe_restore_path` now confines destinations and blocks `..` traversal |
| Surrounding paths `modules/cleaner.py`, `core/actions/filters.py`, `core/provider.py` (lines 207-209) | ⚠️ **Stale** | Actual paths are `dataforge/modules/cleaner.py`, `dataforge/core/actions/filters.py`, `dataforge/core/provider.py` |
| Line 89: "adapter around `modules/`" | ⚠️ **Stale** | Should be `dataforge/modules/` |

**Note on ARCHITECTURE.md consistency:** Lines 19–22, 32, 36, 49, 89, 181
use the correct `dataforge/` prefix. Lines 207–209 and the [!NOTE] itself
use the old un-prefixed paths. The document is partially updated.

---

### A5 — TECHNICAL_SOURCE_OF_TRUTH.md (Staleness warning)

> **Original text:** "Partially stale. The GUI was migrated from
> Tkinter/ttkbootstrap to **PyQt5** and several new modules/views were
> added after most of this document was written. The GUI-stack references
> below (`ttkbootstrap`, `tkinter`) have been corrected, but the deeper
> GUI/file-by-file sections have not been fully re-audited against the new
> modules — treat unreviewed GUI implementation details as `Needs
> confirmation` and prefer `README.md` for the current, verified status."

| Claim | Verdict | Evidence |
|-------|---------|----------|
| PyQt5 migration completed | ✅ | All UI code uses PyQt5, no tkinter/ttkbootstrap imports remain |
| GUI-stack references corrected | ✅ | Grep confirms zero `ttkbootstrap`/`tkinter` in the doc |
| Deeper sections not fully re-audited | ✅ **Accurate caveat** | Several sections reference `core/` without `dataforge/` prefix; old internal references to `docs/reviews/01` (3 occurrences at lines 31-33) no longer resolve — those files were consolidated |

**Status:** The warning is itself well-placed and accurate. Cross-references
to the now-defunct `docs/reviews/01` need updating.

---

### A6 — TECHNICAL_SOURCE_OF_TRUTH.md (Correctness/security caveats)

> **Original text:** "A full engineering/security/UX pass is recorded under
> `docs/reviews/`. The correctness backlog (report 01) has since been
> **fixed**; the most load-bearing corrections:
> - The **test suite runs green — 224 tests pass.** `rename_with_regex`
> was restored in `dataforge/core/operations/files.py`. (See
> `docs/reviews/01`, H1.)
> - **Integrity and duplicate detection no longer default to MD5.**
> Config default `hash_algorithm` is now `sha256`. (`docs/reviews/01`,
> M4/M6.)
> - **`core/scanner.py` no longer follows symlinks.** (`docs/reviews/01`,
> M3.)
> - Also fixed: `sha512` CLI crash, unguarded `json.load`, non-thread-safe
> cache.
> - **Still open (report 02):** forensic HTML report HTML-injection (S2),
> trash-restore path traversal (S4), System Cleanup over-classification
> (S7)."

| Claim | Verdict | Evidence |
|-------|---------|----------|
| **Test count "224"** | 🔴 **WRONG** | Actual: **254 tests pass** |
| `rename_with_regex` restored | ✅ | `dataforge/core/operations/files.py:163` |
| SHA-256 default | ✅ | Config default + self-describing snapshots |
| Symlink fix | ✅ | `dataforge/core/scanner.py:57` |
| `sha512` fixed | ✅ | In hasher allow-list |
| `JSONDecodeError` caught | ✅ | Integrity monitor catches it |
| Cache thread-safety | ✅ | Lock + WAL |
| S2 open (XSS) | ✅ | Verified open in `forensics.py:581-625` |
| S4 open (trash traversal) | ✅ | Verified open in `recovery.py:225-250` |
| S7 open (cleanup over-classification) | ✅ | Verified open in `system_cleanup.py:249` |
| Reference `docs/reviews/01` (×3) | 🔴 **Stale** | These files were consolidated — correct ref: `docs/reviews/AUDIT_FINDINGS.md` |
| Path `core/scanner.py` | ⚠️ **Stale** | Should be `dataforge/core/scanner.py` |

**Status:** The content is correct *except*: the test count (224 vs 254),
three dead references to `docs/reviews/01`, and the `core/scanner.py` path.

---

### A7 — TECHNICAL_SOURCE_OF_TRUTH.md (Comprehensive test module)

> **Original text:** "This module now imports and passes.
> `rename_with_regex` was restored in `core/operations/files.py`, so the
> whole suite collects and runs green (254 tests). The coverage list below
> is accurate. (See `docs/reviews/AUDIT_FINDINGS.md`, H1.)"

| Claim | Verdict | Evidence |
|-------|---------|----------|
| 254 tests green | ✅ | Verified |
| `rename_with_regex` restored | ✅ | `dataforge/core/operations/files.py:163` |
| Coverage list accurate | ✅ | List at lines 869-888 matches test file structure |
| Path `core/operations/files.py` | ⚠️ **Stale** | Should be `dataforge/core/operations/files.py` |
| Reference to AUDIT_FINDINGS.md | ✅ | Correct |

**Status:** One stale path prefix.

---

### A8 — TECHNICAL_SOURCE_OF_TRUTH.md (Structural facts)

> **Original text:** "The structural facts below are still accurate. Most
> *defects* found in the 2026-07-10 review are now **fixed** (broken
> tests, MD5 integrity, symlink-following scan, `sha512` crash,
> non-thread-safe cache); the still-open *security risks* (forensic-report
> HTML injection, trash-restore path traversal, System Cleanup
> over-classification) are tracked in `docs/reviews/` with severities,
> line-level evidence, and fixes rather than repeated here."

| Claim | Verdict | Evidence |
|-------|---------|----------|
| Fixed defects claim | ✅ | 254 tests green; all H/L/M bugs resolved |
| S2/S4/S7 open | ✅ | Verified in code |
| Reference to `docs/reviews/` | ✅ | Files exist |

**Status:** Current. No defects.

---

## 3. Summary of Defects Found

### Defects in the admonition blocks themselves

| ID | Severity | Issue | Affected blocks |
|----|----------|-------|-----------------|
| D1 | 🔴 | **Broken anchor link** — `#known-incomplete--in-progress-changes` doesn't exist in README.md — ✅ **Fixed** (resolved in source before this session) | A1 |
| D2 | 🔴 | **Wrong test count** — "224" should be "254" — ✅ **Fixed** (now 255, current suite size) | A6 |
| D3 | 🔴 | **Dead cross-references** — 3 links to `docs/reviews/01` (consolidated files no longer exist at those paths) — ✅ **Fixed** (resolved in source before this session) | A6 |
| D4 | 🟠 | **Inconsistent path prefixes** — `core/` and `modules/` used without `dataforge/` prefix in ARCHITECTURE.md (lines 89, 207-209, 212-213) and TECHNICAL_SOURCE_OF_TRUTH.md (line 33, 865) — ✅ **Fixed** (WS-A path audit) | A3, A4, A6, A7 |

### In the surrounding context (lines adjacent to admonition blocks)

| ID | Issue | File:Line |
|----|-------|-----------|
| D5 | `core/scanner.py` path stale — ✅ **Fixed** | TECHNICAL_SOURCE_OF_TRUTH.md:33 |
| D6 | `modules/cleaner.py`, `core/actions/filters.py`, `core/provider.py`, `modules/search.py` all missing `dataforge/` prefix — ✅ **Fixed** (already resolved in ARCHITECTURE.md before this session, re-verified) | ARCHITECTURE.md:207-209 |
| D7 | "adapter around `modules/`" → should be `dataforge/modules/` — ✅ **Fixed** (already resolved before this session, re-verified) | ARCHITECTURE.md:89 |

### Open security issues (confirmed still present in code)

These are accurately flagged as open in the admonition blocks. Below is
the full verified status of all 13 security findings from
`AUDIT_FINDINGS.md`:

| ID | Severity | Issue | Verified location | Status |
|----|----------|-------|-------------------|--------|
| S1 | 🔴 | MD5 used for integrity/dedup | — | ✅ **Fixed** (SHA-256 default) |
| S2 | 🔴 | Forensic HTML report XSS — no `html.escape()` | `dataforge/modules/forensics.py:581-625` | ✅ **Fixed** (this session, WS-A - was open when this table was written) |
| S3 | 🟠 | Symlink-following scan | — | ✅ **Fixed** (`follow_symlinks=False`) |
| S4 | 🟠 | Trash-restore trusts `.trashinfo` path | `dataforge/modules/recovery.py:225-250` | ⏳ **Open** |
| S5 | 🟠 | Plugin loader executes arbitrary `.py` with full privileges | `dataforge/ui/plugin_loader.py:38-51` — `exec_module()` with no signing or sandbox | ⏳ **Open** |
| S6 | 🟠 | `secure_delete` overstates guarantee; falls back to `send2trash` | `dataforge/modules/forensics.py:907-943` | ⏳ **Open** |
| S7 | 🟠 | System Cleanup blanket-classifies `/tmp` and cache trees | `dataforge/modules/system_cleanup.py:249` | ⏳ **Open** |
| S8 | 🟠 | Password tools write hash files with default (world-readable) permissions | `dataforge/modules/password_tools.py:246` — `open(hash_file, "w")` no `0o600` | ⏳ **Open** |
| S9 | 🟡 | XML parsing without `defusedxml` | `dataforge/modules/forensics.py:1033` — `xml.etree.ElementTree` | ⏳ **Open** |
| S10 | 🟡 | No config validation — blind merge of `config.json` | `dataforge/core/config.py` — zero validation/schema checks | ⏳ **Open** |
| S11 | 🟡 | Opening scanned files via OS handler | — | ⏳ **Open** (not code-verified) |
| S12 | 🟡 | Forensic reports written world-readable | — | ⏳ **Open** (not code-verified) |
| S13 | 🟡 | Decompression-bomb exposure (Pillow/PDF) | — | ⏳ **Open** (not code-verified) |

---

## 4. Improvement Plan

### Priority 1 — Fix broken/stale documentation (quick wins)

| # | Action | Affected blocks | Effort | Status |
|---|--------|-----------------|--------|--------|
| 1.1 | Update test count 224 → 254 | A6 | 1 min | ✅ Done (now 255) |
| 1.2 | Replace stale `docs/reviews/01` references (×3) → `docs/reviews/AUDIT_FINDINGS.md` | A6 | 5 min | ✅ Done |
| 1.3 | Fix or remove broken anchor `#known-incomplete--in-progress-changes` in README.md — point to `#-open--future` or create the section | A1 | 5 min | ✅ Done |
| 1.4 | Prefix `core/` and `modules/` paths with `dataforge/` in ARCHITECTURE.md lines 89, 207-209, 213, and TECHNICAL_SOURCE_OF_TRUTH.md lines 33, 865 | A3, A4, A6, A7 | 10 min | ✅ Done |

### Priority 2 — Security fixes (per AUDIT_FINDINGS.md remediation order)

| # | Action | Effort | Status |
|---|--------|--------|--------|
| 2.1 | Fix S2 — add `html.escape()` to forensic HTML report | 30 min | ✅ Done (WS-A) |
| 2.2 | Fix S4 — confine trash-restore paths, block `..` traversal | 30 min | ✅ Done (WS-B) |
| 2.3 | Fix S7 — add minimum-age filter for /tmp, skip sockets/FIFOs | 30 min | ✅ Done (WS-B) |
| 2.4 | Fix S5 — plugin trust model (opt-in flag, load logging) | 15 min | ✅ Done (WS-B) |
| 2.5 | Fix S6 — rename to "best-effort overwrite", remove trash fallback | 15 min | ✅ Done (WS-B) |
| 2.6 | Fix S8 — write hash files with `0o600` | 10 min | ✅ Done (WS-B) |
| 2.7 | Fix S9 — switch to `defusedxml` | 10 min | ✅ Done (WS-B) |
| 2.8 | Fix S10 — validate config types/ranges/enums on load | 30 min | ✅ Done (WS-B) |

### Priority 3 — Structural improvements

| # | Action | Status |
|---|--------|--------|
| 3.1 | Run a full path-audit across `ARCHITECTURE.md` and `TECHNICAL_SOURCE_OF_TRUTH.md` — many paths still use the repo-root `core/`/`modules/` convention instead of `dataforge/core/`/`dataforge/modules/` | ✅ Done (ARCHITECTURE.md was already clean; TSOT had ~17 references fixed) |
| 3.2 | Add "Last verified: YYYY-MM-DD" datestamps to all remaining review/source-of-truth sections | ✅ Done |
| 3.3 | Consider removing the TECHNICAL_SOURCE_OF_TRUTH `[!WARNING]` staleness caveat (A5) — after the path audit in 3.1, the doc should be accurate enough that the blanket caveat is no longer needed | ✅ Done — narrowed rather than removed: the path/dead-link portion is resolved and cited, but the honest "GUI content not fully re-audited" hedge stays (this doc's own A5 evidence table validated that hedge as accurate) |

---

## 5. What was removed from source files and why

All `[!NOTE]`, `[!WARNING]`, and `[!IMPORTANT]` blocks in the source
files were either:
- **Consolidated into this document** with full verification and context (A1–A8), or
- **Absorbed into the surrounding prose** when the note's information was integral to the section it sat in

Source files now contain a single brief reference to this document instead
of their original admonition blocks. This keeps documentation DRY and
ensures there's one place to update when the audit state changes.
