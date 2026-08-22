# Audit Report — Bugs, Security, Doc Defects, and New Line-Level Findings

**Date:** 2026-07-10 · **Updated:** 2026-08-22 · **Last verified:** 2026-08-22  
**Merges:** `AUDIT_REPORT.md` + `AUDIT_REPORT.md` + `drafts/FULL_APP_REVIEW.md` (R-CORE/R-OPS, §1–2). No finding removed — this is a consolidation. Originals are kept in git history.  
**Scope:** Entire `dataforge/` HEAD at 2026-08-22.

> See `FORENSIC_REVIEW.md` for the separate forensic backlog (F/U). See `ROADMAP.md` for sequencing.

**Legend:** 🔴 High (data loss/crash/security) · 🟠 Medium · 🟡 Low · 🔵 Info · ✅ Fixed · ⏳ Open

---

## Part 1 — Correctness Bugs (all fixed, kept as changelog)

> Every item below is **fixed** and green at 301 tests.

| ID | Title | Fix (seam) |
|---|---|---|
| **H1** | `rename_with_regex` missing → pytest collected 77/224 | Restored wrapper `operations/files.py:163` (`re.sub`→`rename_path`) |
| **M1** | `fm hash-calc --algo sha512` → `KeyError` | `core/hasher.py:6` now `sha512`/`blake2b` |
| **M2** | `verify_snapshot` on truncated JSON → `JSONDecodeError` uncaught | Catches `(OSError, JSONDecodeError)` |
| **M3** | Scanner followed symlinks → DoS/scope escape | `scanner.py:57` `follow_symlinks=False`, skips `is_symlink()` |
| **M4** | Integrity hardcoded MD5 | `integrity.py:16` reads `config.hash_algorithm`, self-describing snapshot, legacy flat-MD5 still readable |
| **M5** | SQLite cache `database is locked` | `cache.py:13` `threading.Lock` + `WAL` per method |
| **M6** | Dedup deleted on hash equality (MD5 default) | `config` default `sha256`; `duplicates.py:82` `verify_content=True` byte-compares non-keepers |
| **L1** | Bare `except:` → bad input coerced to 0 | Catches `(ValueError, TypeError)` in `actions/filters.py`, `media.py` |
| **L2** | `print()` on error (`media_ops`, `plugin_loader`) | `logger.error` |
| **L3** | `convert_image` no-op `except: raise` | `(OSError, ValueError)` + log |
| **L4** | `metadata.py` probed `exiftool -ver` at import | `@lru_cache` lazy probe `_has_exiftool()` |
| **L5** | `render_template_name` naive `str.replace` | `string.Formatter().vformat` |
| **L6** | `requirements.txt` mixed runtime/dev | Split `requirements.txt` + `requirements-dev.txt` |
| **L7** | Stray `26.1.2` | Deleted + `.gitignore` |
| **L8** | Windows trash `[]` silently | Raises `TrashScanUnsupported` (`recovery.py:184`) |
| **L9** | `_run_john_dictionary` always `success: True` | Derives from return code |

**Architecture notes moved to ROADMAP:** two filter engines (`search.py` vs `actions/filters.py`), two metadata cleaners (`cleaner.py` vs `metadata.py`), dead `FileProvider` (`core/provider.py`). Tracked as WS-F ARCH.1–3.

---

## Part 2 — Security & Forensic Findings (S1–S13, all fixed in WS-A/B)

**Threat framing:** App operates on untrusted data + performs privileged/destructive actions.

| ID | Severity | Title | Status |
|---|---|---|---|
| S1 | 🔴 | MD5 for integrity/dedup | ✅ `config` default `sha256`, `integrity.py:16` |
| S2 | 🔴 | Forensic HTML XSS (unescaped artefact names) | ✅ `forensics.py:581` `html.escape`, test `test_forensic_report_html_escapes_script_filename` |
| S3 | 🟠 | Symlink scope escape | ✅ `scanner.py:57` |
| S4 | 🟠 | `restore_from_trash` trusts `.trashinfo` → arbitrary write | ✅ `recovery.py:205` `_is_safe_restore_path`, confined `restore_root` fallback; residual audit hook → F19 |
| S5 | 🟠 | Plugin loader execs arbitrary `.py` | ✅ `ui/plugin_loader.py:40` opt-in, owner/world-writable checks; isolation → F12 |
| S6 | 🟠 | `secure_delete` false assurance + trash fallback | ✅ `forensics.py:912` best-effort caveat, no trash fallback; placement → F4/F21 |
| S7 | 🟠 | Cleanup blanket-classifies system/temp | ✅ `system_cleanup.py:267` skip sockets/FIFOs, `273` 1-day min-age for `/tmp`, `277` user-supplied path no longer blanket |
| S8 | 🟠 | Credential hygiene (`0600`, password leak) | ✅ `password_tools.py` `0600`, masked display |
| S9 | 🟡 | XML without `defusedxml` (billion-laughs) | ✅ `forensics.py:1048` `defusedxml` |
| S10 | 🟡 | No config validation (blind merge) | ✅ `config.py:73` type/range/enum, `test_config_merge_validates_and_clamps_bad_values` |
| S11 | 🟡 | Untrusted file open via `xdg-open` | ✅ `widgets.py:860` executable-open confirm |
| S12 | 🟡 | Reports world-readable | ✅ `forensics.py:550` `0o600` via `os.open`; chain → F1/F11 |
| S13 | 🟡 | Decompression bombs (Pillow/PDF) | ✅ `Image.MAX_IMAGE_PIXELS`, PDF cap; isolation → F13 |

**Superseded detail:** Forensic checklist rows (Evidence Mode, provenance, UTC, chain-of-custody, VSS) now live fully in `FORENSIC_REVIEW.md` F1–F21/U1–U11, which **supersedes** the table below for those items.

---

## Part 3 — Doc Defects (D1–D7, from NOTES_REVIEW, all fixed)

> All admonition blocks were removed from source docs and consolidated here as the record. Status cells reflect closure, not the original “open”.

| ID | Where (original) | Defect | Status |
|---|---|---|---|
| D1 | `README:125` anchor `AUDIT_REPORT.md` | Broken link after review restructure | ✅ Fixed |
| D2 | `README:125` / `DEVELOPMENT_GUIDE:57` “254 tests” | Stale count (actual 254→301 at time, now 301) | ✅ Fixed |
| D3 | `TECHNICAL_SOURCE…` dead `docs/reviews/01/` links | Moved review dir | ✅ Fixed |
| D4–D5 | `TECHNICAL_SOURCE…` ~16 unprefixed `core/`/`modules/` | Missing `dataforge/` prefix | ✅ Fixed (WS-A, 17 refs) |
| D6–D7 | `ARCHITECTURE`/`CONTRIBUTING` datestamp drift | No `Last verified` scheme | ✅ Fixed (`Last verified: 2026-08-22` + `DOCUMENTATION_AUDIT_2026-08-22`) |

---

## Part 4 — New Line-Level Findings (R-CORE / R-OPS, from FULL_APP_REVIEW §1–2, still open)

> Fresh 2026-08-22 read. These are **not** covered by S/D/H/M. IDs `R-<section>-<n>`.

| ID | Severity | Title | Status |
|---|---|---|---|
| R-CORE-1 | 🟠 | Logger to `stdout` corrupts `fm … --format json` (`logger.py:23` `StreamHandler(sys.stdout)`) | ✅ Fixed (TICK-101) |
| R-CORE-2 | 🟠 | Config `excluded_extensions`/`excluded_folders` validate `list` only, not items → `endswith`/set crash on every `scan_directory` | ⏳ Open |
| R-CORE-3 | 🟡 | `collapsed_groups` dropped on reload (`config.py:77` iterates `DEFAULT_CONFIG` only) → sidebar state never persists | ⏳ Open |
| R-CORE-4 | 🟡 | `cache.py:43` `conn=None` crash if init failed (`AttributeError` in worker) | ⏳ Open |
| R-CORE-5 | 🟡 | Per-file `commit()` (fsync) in `cache.py:51` → large scans I/O-bound | ⏳ Open (proposal: `set_hash_many` batch in `proposals/PERFORMANCE_INVESTIGATION`) |
| R-CORE-6 | 🟡 | `scanner.py:80` swallows `FileNotFoundError` → “no results” vs “no such path” indistinguishable | ⏳ Open |
| R-CORE-7 | 🟡 | `logger.py:30` `makedirs("")` crash on bare filename | ⏳ Open |
| R-CORE-8 | 🔵 | `hasher.py:32` `get_hashes()` no algo allow-list | Info — latent |
| R-OPS-1 | 🟡 | `operations/files.py:39` `normalized_reserved_paths` rebuilt per item → O(N²) on large batches | ✅ Fixed (TICK-105) |
| R-OPS-2 | 🟠 | `services/file_actions.py:357` single-mode zip: one bad file aborts whole batch, partial `.zip` left, remaining items no records, cancel leaves partial | ✅ Fixed (TICK-201) |
| R-OPS-3 | 🟡 | `archive_items` truncates existing zip without collision check | ✅ Fixed (TICK-105) |
| R-OPS-4 | 🟡 | `files.py:102` `makedirs` before first success → empty dest dirs on failure | ✅ Fixed (TICK-105) |

**Not yet reviewed:** R-sections 3+ (modules, UI, packaging, tests) — see `drafts/FULL_APP_REVIEW.md`. Remaining forensic gaps F1–F21/U1–U11 are in `FORENSIC_REVIEW.md`.

---

## Recommended order

S1–S13 are **done**. R-CORE-1, R-OPS-1/2/3/4 are **done** (TICK-101, TICK-105, TICK-201). F1–F3/U2/F9 are **done** (TICK-304). Next tranche is WS-G (brand/release polish) and remaining forensic gaps F4/F21/F13 (WS-I/J) — sequenced in `ROADMAP.md`.
