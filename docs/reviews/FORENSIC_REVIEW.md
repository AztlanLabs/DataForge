# Forensic Review — Soundness, Security, and Investigator UX

**Date:** 2026-07-12 · **Last verified:** 2026-07-12 · **Against:** `develop` HEAD  
**Merges:** `FORENSIC_REVIEW.md` (no finding removed — this is a trim, not a rewrite). 886 → ~320 lines; full Where/Why/How detail remains in git history.  
**Companions:** `AUDIT_REPORT.md` for S1–S13 detail, `ROADMAP.md` for sequencing WS-H…WS-J.

## Summary — The 5 disqualifiers

DataForge is **defensible as a power-user file manager with triage features** and **not defensible as a forensic product** until F1–F4 + U2 close (courts / ISO 27037 / ACPO / NIST SP 800-86 pillars):

1. **No chain-of-custody / tamper-evident audit log** (F1). `app.log` is rotatable, world-readable, not hash-chained.
2. **No acquisition provenance** (F2). `forensics.py:550` report is `{report_generated, tool, data}` — no operator/host/image-hash/write-blocker/case ID.
3. **No read-only Evidence Mode** (F3/U2). Same UI can delete the evidence it is investigating — violates ACPO §1.
4. **`secure_delete` in the forensic module** (F4) — a destroy primitive beside carving/timeline is a procurement flag; also not hardlink/reflink-aware (F21).
5. **Mixed timezone** (F9). `build_timeline:754` is UTC ISO-8601, `generate_forensic_report:563` is naive `datetime.now()` local — mixed tz in one artefact.

Scale/effort for F1–F4/U2 is S–M (one seam each: `FileActionService` gate + `core/audit.py` + report writer + `CaseContext`).

## Index — All findings (status at 2026-07-12)

| ID | Sev | Area | Title | Status | Seam |
|---|---|---|---|---|---|
| F1 | 🔴 | Soundness | No chain-of-custody / tamper-evident audit log | Open | `core/audit.py` + `FileActionService` hook |
| F2 | 🔴 | Soundness | No acquisition provenance | Open | `forensics.py` report writer |
| F3 | 🔴 | Soundness | No read-only Evidence Mode | Open | `FileActionService` gate + UI toggle |
| F4 | 🔴 | Soundness | `secure_delete` in forensic module | Open | `modules/sanitisation.py` (move out) |
| F5 | 🟠 | Engine | No raw image (E01/AFF4) lib; requires mount | Open | `core/image_io.py` + libewf/pyaff |
| F6 | 🟠 | Engine | Carving sector-aligned only; misses mid-sector | Open | `recovery.py` rewrite |
| F7 | 🟠 | Engine | No YARA / SSDEEP/TLsh / NSRL pivot | Open | `modules/indicators.py` |
| F8 | 🟠 | Engine | ADS/xattrs/MotW not parsed | Open | `core/streams.py` |
| F9 | 🔴 | Soundness | tz-naive timestamps mixed with UTC | Open | Timestamp standardisation (UTC ISO-8601) |
| F10 | 🟠 | Engine | NFC/NFD + bidi not handled | Open | Scanner + duplicates |
| F11 | 🟠 | Security | `app.log` not hash-chained | Open | `core/logger.py` rewrite (extends F1) |
| F12 | 🟠 | Security | Plugin loader full privileges | Partial | `ui/plugin_loader.py` — owner/world-writable + opt-in done (S5), isolation+signing remain |
| F13 | 🟠 | Security | Parsers in-process, no isolation | Open | `multiprocessing` pool |
| F14 | 🟡 | Perf | `ingest_disk_image` materialises list; double `stat` | Open | Streaming + `FileEntry` |
| F15 | 🟡 | Perf | Keyword worker 10 MB × N, no budget | Open | `forensics.py:keyword_search` |
| F16 | 🔴 | Soundness | Sparse files not detected | Open | Carve + hash pre-check |
| F20 | 🟠 | Engine | Locked/in-use files skipped (no VSS) | Open | `core/acquire.py` |
| F21 | 🟡 | Engine | Hardlink/reflink-unaware `secure_delete`/dedup | Open | F4 seam + dedup `(st_dev,st_ino)` |
| U1 | 🟠 | UX | No case/evidence/operator context | Open | `CaseContext` |
| U2 | 🔴 | UX | No EVIDENCE MODE toggle | Open | Top sticky + `FileActionService` gate (with F3) |
| U3 | 🟠 | UX | Timeline flat list, no virtualisation >5k | Partial | Virtualised `QTreeView` |
| U4 | 🟠 | UX | Hex without field inspector | Partial | `widgets.HexView` |
| U5 | 🟡 | UX | No magic-vs-ext mismatch filter | Open | `profile_directory_types` |
| U6 | 🟡 | UX | Colour-only state (no glyph) | Open | Token table |
| U7 | 🟡 | UX | Preview not correlated to evidence row | Open | `views/base.py` |
| U8 | 🟡 | UX | Drag-and-drop not disabled | Open | `QAbstractItemView.NoDragDrop` |
| U9 | 🟢 | UX | No keyboard timeline nav | Open | Key bindings |
| U10 | 🟡 | Parity | `forensics --parse-artifacts` / trash cross-platform claim vs Linux-only | Open | Docs + capability gating |
| U11 | 🟡 | UX | Windows trash claim vs `TrashScanUnsupported` | Open | Docs or pywin32 path |

> Full Where/Why/How for each F/U — source `path:line`, risk, fix, test — lives in `FORENSIC_REVIEW.md` git history and in `AUDIT_REPORT.md` for the S-linked items. This file keeps the index + viability verdict as the concise reference.

## Viability note (from §1.3)

> “DataForge today is defensible as a **power-user file-management utility with forensic-flavoured triage features** and **not defensible — and not legally marketable — as a forensic product competing with EnCase/FTK/AXIOM/FIM** until F1–F4 and U2 are closed.”

## Next

Sequencing is in `ROADMAP.md` WS-H (`v0.2.0` forensic layer) and WS-I/WS-J (`v0.3.0` engine correctness/growth).
