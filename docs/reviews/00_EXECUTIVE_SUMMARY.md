# DataForge — Full Project Review (Executive Summary)

**Date:** 2026-07-10
**Reviewed by:** engineering + security + UX pass over the whole repository (`dataforge/`, `tests/`, docs, packaging).
**What this is:** a top-level summary and index for a four-part review. Each part is a standalone file in this folder.

> **Remediation update (2026-07-10):** all correctness findings in report 01 (H1, M1–M6, L1–L9) have since been **fixed** in the source tree. The test suite now runs green — **224 tests pass**. The security items in report 02 that overlap those fixes are also addressed (symlink-following scan, MD5-by-default integrity/dedup, `sha512` crash, unguarded `json.load`, thread-unsafe cache). The forensic-report XSS (S2), trash-restore path trust (S4), and System Cleanup over-classification (S7) are documented risks tracked in report 02; the plaintext below describes the *original* pre-fix state for context.

## The reports

| # | File | Lens | Headline |
| --- | --- | --- | --- |
| 00 | `00_EXECUTIVE_SUMMARY.md` | Overview | This document. |
| 01 | `01_CODE_REVIEW_AND_BUGS.md` | Correctness | 15 findings — **all fixed**; the test suite now passes (224 tests). |
| 02 | `02_SECURITY_AND_FORENSIC_AUDIT.md` | Security / forensics | 13 findings; **MD5-based integrity** and a **forensic-report XSS** most notable. |
| 03 | `03_UIUX_REVIEW.md` | UX / product | Organised by module not task; several core interactions fight the user. |
| 04 | `04_IMPROVEMENTS_AND_ROADMAP.md` | Direction | Repo isn't in git; phased plan from "stabilize" to "grow". |

## What the project is

A capable **Python file-management toolkit** with two front ends over a shared core:
- a **Click CLI** (`fm …`) and a **PyQt5 desktop GUI** (`run_ui.py`),
- ~21k lines of application code across `core/` (scan, config, cache, operations, the central `FileActionService`), `modules/` (search, duplicates, cleanup, recovery, forensics, hardware, metadata, performance, password tooling…), and `ui/` (shell + ~14 views).

The **architecture is genuinely good**: filesystem mutation is centralised through one service, scanning through one function, and the GUI uses a consistent *preview → confirm → execute* pattern with background threads and cancellation. That single-seam design is also what makes the fixes below high-leverage — most can be enforced in one place.

## The five things that matter most

1. **✅ The test suite runs green again.** `tests/test_comprehensive.py` imported a symbol (`rename_with_regex`) that had been removed, so pytest failed at collection and only 77 of ~224 tests were collectable. `rename_with_regex` is now restored in `core/operations/files.py` and three other stale tests were updated to the current API — **`pytest -q` now passes all 224 tests.** *(Was Doc 01/H1.)*

2. **🔴 The repository is not under version control.** No git history, no CI, no diffs. Everything else is riskier than it needs to be because of this. *(Doc 04.)*

3. **◑ Security controls that undercut the product's own promises.** Integrity/tamper-detection used **MD5** and hardcoded it regardless of settings — **now fixed**: integrity honours the configured algorithm (default `sha256`) and writes self-describing snapshots. The **forensic HTML report** still interpolates attacker-controlled filenames/usernames without escaping (stored XSS) — **still open**. *(Doc 02/S1 fixed, S2 open.)*

4. **◑ "Operate on untrusted paths, then destroy things" cluster.** The scanner **no longer follows symlinks** (scope escape + recursion DoS — **fixed**), and duplicate deletion now byte-verifies groups. Still open: **trash-restore trusts attacker-controlled `.trashinfo` paths** (arbitrary write from a malicious USB) and **System Cleanup classifies whole `/tmp` and cache trees as deletable junk**. *(Doc 01/M3 fixed; Doc 02/S4, S7 open.)*

5. **🟠 UX is organised around the developer's modules, not the user's tasks.** Duplicate-sounding destinations ("Tools & Workflows" vs "Action Builder"), a file-vs-folder picker implemented as a Yes/No/Cancel riddle, inconsistent settings persistence, and an "Experience Level" that *hides* whole feature groups with no way to discover them. *(Doc 03.)*

## Quick wins (status)

- ✅ Stray empty `26.1.2` file deleted; root `.gitignore` added. (`git init` + CI still open.)
- ✅ Test suite unbroken — 224 tests pass. (Wiring into CI still open.)
- ✅ `sha512` added to the hasher (the crashing CLI flag now works); `JSONDecodeError` caught on snapshot load.
- ⏳ Escape output in the forensic HTML report. *(still open — Doc 02/S2)*
- ✅ Scan with `follow_symlinks=False`.
- ⏳ Replace the file-vs-folder message-box riddle with two explicit buttons. *(UX — Doc 03)*
- ⏳ Make settings persistence consistent; de-duplicate the dark-mode control. *(UX — Doc 03)*

## Overall assessment

**Solid engineering under a good architecture.** The correctness backlog (report 01) has now been cleared and the suite is green; what remains is an untracked build (no git/CI yet), a few residual security items (forensic-report escaping, trash-restore path trust, cleanup over-classification), and an information architecture built for the code rather than the user. None require a rewrite — they're concentrated at seams the codebase already has (scanner, `FileActionService`, report writer, settings). Put the tree under version control and wire the green suite into CI (doc 04, Phase 0); the rest sequences cleanly from there.

> All findings were derived from reading the current source; the highest-impact ones (broken tests, `sha512` crash, MD5 integrity, report XSS, symlink following) were confirmed by running code or by direct line-level evidence, cited inline in each report.
