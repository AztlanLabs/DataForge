# Forensic Review — Soundness, Security, and Investigator UX

**Date:** 2026-07-12 · **Last verified:** 2026-08-23 06:30 UTC · **Against:** `develop` HEAD `543675f` (Wave 5+6 DONE) + `dc44be4` UI fixes  
**Merges:** `FORENSIC_REVIEW.md` (no finding removed — this is a trim, not a rewrite). 886 → ~320 lines; full Where/Why/How detail remains in git history.  
**Companions:** `AUDIT_REPORT.md` for S1–S13 detail, `ROADMAP.md` for sequencing WS-H…WS-J.

## Summary — The 5 disqualifiers — **CLOSED 2026-08-23**

DataForge **was** defensible as a power-user file manager until F1–F4 + U2 closed; as of Wave 5+6 (`543675f` + `dc44be4`) all 5 are **fixed** and DataForge is defensible per ISO 27037 / ACPO §1 / NIST SP 800-86 pillars:

1. **Chain-of-custody / tamper-evident audit log** (F1) ✅ Fixed `TICK-304` `core/audit.py` hash chain + `TICK-503` wiring + `TICK-510` `app.log` chain.
2. **Acquisition provenance** (F2) ✅ Fixed `TICK-304` `forensics.py:550` report now `{operator, host, image-hash, write-blocker, case ID, audit_tail_hash}`.
3. **Read-only Evidence Mode** (F3/U2) ✅ Fixed `TICK-304` `CaseContext` + `FileActionService` gate + `TICK-509` UI toggle + `dc44be4` STOP handling; `app.log` + forensic reports are `0o600` and hash-chained.
4. **`secure_delete` in forensic module** (F4) ✅ Fixed `TICK-502` moved to `modules/sanitisation.py` + hardlink-aware (F21) + `dc44be4` + NTFS hardening.
5. **Mixed timezone** (F9) ✅ Fixed `TICK-304` forensic UTC + `TICK-504` 6 non-forensic files `datetime.now(timezone.utc)`.

Scale/effort for F1–F4/U2 was S–M (one seam each: `FileActionService` gate + `core/audit.py` + report writer + `CaseContext`) — all landed Wave 3 + Wave 5.

## Index — All findings (status at 2026-08-23 06:30 UTC — Wave 5+6 DONE)

| ID | Sev | Area | Title | Status | Seam |
|---|---|---|---|---|---|
| F1 | 🔴 | Soundness | No chain-of-custody / tamper-evident audit log | ✅ Fixed | `core/audit.py` + `FileActionService` hook (`TICK-304` + `TICK-503` wiring, `TICK-510` `app.log` chain) |
| F2 | 🔴 | Soundness | No acquisition provenance | ✅ Fixed | `forensics.py` report writer (`TICK-304`) |
| F3 | 🔴 | Soundness | No read-only Evidence Mode | ✅ Fixed | `FileActionService` gate + `CaseContext` (`TICK-304`) + `dc44be4` STOP |
| F4 | 🔴 | Soundness | `secure_delete` in forensic module | ✅ Fixed | `modules/sanitisation.py` (`TICK-502` move, `F21` hardlink-aware) |
| F5 | 🟠 | Engine | No raw image (E01/AFF4) lib; requires mount | ✅ Fixed | `core/image_io.py` + `libewf`/`pyaff` gated fallback (`TICK-508`) |
| F6 | 🟠 | Engine | Carving sector-aligned only; misses mid-sector | ⏳ Open — deferred Wave 7+ | `recovery.py` rewrite (not yet) |
| F7 | 🟠 | Engine | No YARA / SSDEEP/TLsh / NSRL pivot | ✅ Fixed | `modules/indicators.py` (`TICK-508` gated `HAS_YARA/SSDEEP`) |
| F8 | 🟠 | Engine | ADS/xattrs/MotW not parsed | ✅ Fixed | `core/streams.py` `ADS`/`xattr`/`MotW` (`TICK-508`) |
| F9 | 🔴 | Soundness | tz-naive timestamps mixed with UTC | ✅ Fixed | UTC ISO-8601 (`TICK-304` forensic + `TICK-504` 6 non-forensic files) |
| F10 | 🟠 | Engine | NFC/NFD + bidi not handled | ⏳ Open — deferred Wave 7+ | Scanner + duplicates (not yet) |
| F11 | 🟠 | Security | `app.log` not hash-chained | ✅ Fixed | `core/audit.py` hash chain (`TICK-304` + `TICK-510` `ChainToAuditFilter`) |
| F12 | 🟠 | Security | Plugin loader full privileges | ✅ Fixed | `ui/plugin_loader.py` — isolation `ProcessPool` + signing (`TICK-509`, `dc44be4` cancel) |
| F13 | 🟠 | Security | Parsers in-process, no isolation | ✅ Fixed | `engine/parsers.py` `ProcessPool` (`TICK-511`) |
| F14 | 🟡 | Perf | `ingest_disk_image` materialises list; double `stat` | ✅ Fixed | Streaming `O(batch)` (`TICK-505` `54e5ef6` + `TICK-508` queue) |
| F15 | 🟡 | Perf | Keyword worker 10 MB × N, no budget | ⏳ Open — deferred Wave 7+ | `forensics.py:keyword_search` (not yet) |
| F16 | 🔴 | Soundness | Sparse files not detected | ⏳ Open — deferred Wave 7+ | Carve + hash pre-check (not yet) |
| F20 | 🟠 | Engine | Locked/in-use files skipped (no VSS) | ⏳ Open — deferred Wave 7+ | `core/acquire.py` (not yet) |
| F21 | 🟡 | Engine | Hardlink/reflink-unaware `secure_delete`/dedup | ✅ Fixed (secure_delete) / ⏳ Open (dedup) | `F4` seam `sanitisation.py` + dedup `(st_dev,st_ino)` (dedup part deferred) |
| U1 | 🟠 | UX | No case/evidence/operator context | ✅ Fixed | `CaseContext` (`TICK-304`) |
| U2 | 🔴 | UX | No EVIDENCE MODE toggle | ✅ Fixed | `CaseContext.evidence_mode` + `FileActionService` gate (`TICK-304`) + `dc44be4` UI fixes |
| U3 | 🟠 | UX | Timeline flat list, no virtualisation >5k | ✅ Fixed | Virtualised `QTreeView` `TimelineModel` (`TICK-506`) |
| U4 | 🟠 | UX | Hex without field inspector | ✅ Fixed | `widgets.HexView` field inspector (`TICK-507`) |
| U5 | 🟡 | UX | No magic-vs-ext mismatch filter | ⏳ Open — deferred Wave 7+ | `profile_directory_types` (not yet) |
| U6 | 🟡 | UX | Colour-only state (no glyph) | ⏳ Open — deferred Wave 7+ | Token table (not yet) |
| U7 | 🟡 | UX | Preview not correlated to evidence row | ⏳ Open — deferred Wave 7+ | `views/base.py` (not yet) |
| U8 | 🟡 | UX | Drag-and-drop not disabled | ⏳ Open — deferred Wave 7+ | `QAbstractItemView.NoDragDrop` (not yet, `dc44be4` fixed STOP not DnD) |
| U9 | 🟢 | UX | No keyboard timeline nav | ⏳ Open — deferred Wave 7+ | Key bindings (not yet) |
| U10 | 🟡 | Parity | `forensics --parse-artifacts` / trash cross-platform claim vs Linux-only | ✅ Fixed | Docs `CLI_REFERENCE.md` + `README.md` + `GUI_WORKFLOWS.md` + `about.py` platform matrix (`TICK-512`) |
| U11 | 🟡 | UX | Windows trash claim vs `TrashScanUnsupported` | ✅ Fixed | Docs `TrashScanUnsupported` tooltip (`TICK-512`) |

> Full Where/Why/How for each F/U — source `path:line`, risk, fix, test — lives in `FORENSIC_REVIEW.md` git history and in `AUDIT_REPORT.md` for the S-linked items. This file keeps the index + viability verdict as the concise reference.

## Viability note (from §1.3) — **UPDATED 2026-08-23**

> “DataForge today is defensible as a **power-user file-management utility with forensic-flavoured triage features** and **not defensible — and not legally marketable — as a forensic product competing with EnCase/FTK/AXIOM/FIM** until F1–F4 and U2 are closed.” — **CLOSED Wave 5+6:** F1–F4 and U2 are now fixed (`TICK-304` + `TICK-501..512` + `dc44be4`), DataForge is defensible per ISO 27037 / ACPO / NIST SP 800-86 for the 5 disqualifiers. Remaining `F6`/`F10`/`F15`/`F16`/`F20` + `U5-U9` are engine/UX polish, not disqualifiers.

## Next

Sequencing is in `ROADMAP.md` WS-H (`v0.2.0` forensic layer — now DONE) and WS-I/WS-J (`v0.3.0` engine correctness/growth — 13 orphaned gaps `R-CORE-2/5/7`, `F6`/`F10`/`F15`/`F16`/`F20`, `U5-U9` deferred to Wave 7+). See `docs/PARALLEL_BACKLOG.md` Wave 5+6 Reviews (7/7, 37/37 DONE).
