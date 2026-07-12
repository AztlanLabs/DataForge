# Forensic, Security & UI/UX Architectural Review

**Date:** 2026-07-12 · **Last verified:** 2026-07-12 · **Reviewed against:** source tree at HEAD of `develop`
**Scope:** forensic-soundness, security posture, and investigator-facing UX/UI of the current DataForge codebase, evaluated against the enterprise forensic market (EnCase, FTK, Magnet AXIOM, CrowdStrike FIM) and against ACPO / RFC 3227 / ISO/IEC 27037 / NIST SP 800-86 expectations.
**Stance:** analytically neutral, evidence-based. Each finding is anchored to source by `path:line` and follows the Where / Why / How standard mandated by [`CONTRIBUTING.md` §8](../CONTRIBUTING.md).
**Companion documents:**
- Per-finding bug/security detail — [`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md)
- UX rationale per-item — [`IMPROVEMENT_PLAN.md`](./IMPROVEMENT_PLAN.md)
- Sequencing + release mapping — [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md)
- Code-verified evidence table — [`IMPLEMENTATION_PLAN.md` §1.2](./IMPLEMENTATION_PLAN.md)

> **Provenance rule.** Every finding below was checked against the current source
> tree at the date above. References to older findings cite the live `audit`
> directory entry where the legacy finding still exists, but the line-level
> evidence quoted here was re-verified at review time.

---

## 0. Summary table

| ID | Severity | Area | Title | Status | Owner seam |
| --- | --- | --- | --- | --- | --- |
| F1 | 🔴 Critical | Forensic soundness | No chain-of-custody / tamper-evident audit log | Open | New `core/audit.py` + `FileActionService` hook |
| F2 | 🔴 Critical | Forensic soundness | No acquisition provenance in reports or manifests | Open | `modules/forensics.py` report writer |
| F3 | 🔴 Critical | Forensic soundness | No read-only "Evidence Mode"; destructive ops one click from evidence | Open | `FileActionService` gate + UI toggle |
| F4 | 🔴 Critical | Forensic soundness | `secure_delete` lives inside the forensic module | Open | Remove or quarantine |
| F5 | 🟠 High | Forensic engine | No raw image (E01/AFF4) lib; requires user to mount first | Open | New `core/image_io.py` + libewf/pyaff |
| F6 | 🟠 High | Forensic engine | Carving is sector-aligned header-only scanning; misses mid-sector headers | Open | `modules/recovery.py` rewrite |
| F7 | 🟠 High | Forensic engine | No YARA, no SSDEEP/TLsh, no known-hash (NSRL) pivot | Open | New `modules/indicators.py` + cache schema |
| F8 | 🟠 High | Forensic engine | ADS / xattrs / Mark-of-the-Web not parsed | Open | Cross-platform `core/streams.py` |
| F9 | 🔴 High | Forensic soundness | tz-naive timestamps in reports; UTC/local mixed in one artefact | Open | Forensic timestamp standardisation |
| F10 | 🟠 High | Forensic engine | Filename handling ignores NFC/NFD normalisation and bidi controls | Open | Scanner + duplicates |
| F11 | 🟠 High | Backend security | Audit log (`app.log`) is rotatable, world-readable, not hash-chained | Open | `core/logger.py` rewrite |
| F12 | 🟠 High | Backend security | Plugin loader executes arbitrary local Python with full app privileges | Partial | `ui/plugin_loader.py` (S5) — owner/world-writable checks + opt-in landed; isolation + signing remain |
| F13 | 🟠 High | Backend security | Untrusted parsers run in-process — no CPU/mem/`seccomp` isolation | Open | `multiprocessing` worker pool |
| F14 | 🟡 Medium | Engine perf | `ingest_disk_image` materialises file list; doubles `os.stat` in timeline | Open | Streaming + `FileEntry` schema |
| F15 | 🟡 Medium | Engine perf | Keyword worker buffers 10 MB × N threads; no global byte budget | Open | `modules/forensics.py:keyword_search` |
| F16 | 🔴 High | Forensic soundness | Sparse files not detected; hash manifest treated as `st_size` bytes | Open | Carve + hash pre-check |
| F20 | 🟠 High | Forensic engine | Locked / in-use files silently skipped; no Volume Shadow Copy or raw-volume acquisition | Open | New `core/acquire.py` + scanner/hasher `access_error` |
| F21 | 🟡 Medium | Forensic engine | `secure_delete` and dedup are not hardlink/reflink-aware (collateral loss / false destruction) | Open | `st_nlink` guard in F4 seam + dedup `(st_dev, st_ino)` grouping |
| U1 | 🟠 High | UI/UX | No case / evidence item / operator context (every artefact is unattributed) | Open | New `CaseContext` |
| U2 | 🔴 High | UI/UX | No EVIDENCE MODE toggle; investigation and clobber sessions share UI | Open | Top-of-window sticky + `FileActionService` gate |
| U3 | 🟠 High | UI/UX | Timeline tab renders as a flat list; no virtualisation past ~5,000 events (fatigue risk) | Partial | Virtualised `QTreeView` + swimlane (flat Timeline tab exists) |
| U4 | 🟠 High | UI/UX | Inline Hex tab exists but no recognised-field inspector for top 10 file types | Partial | `widgets.HexView` field inspector (S11 open-handler fixed) |
| U5 | 🟡 Medium | UI/UX | "Suspicious mismatches" filter absent (magic-byte vs extension) | Open | Filter on `profile_directory_types` rows |
| U6 | 🟡 Medium | UI/UX | State conveyed by colour alone; no glyph paired with semantic colour | Open | Token table extension |
| U7 | 🟡 Medium | UI/UX | Destructive preview does not correlate source evidence row to mutation step | Open | `views/base.py` preview rework |
| U8 | 🟡 Medium | UI/UX | Drag-and-drop on evidence trees not disabled in Qt defaults | Open | `QAbstractItemView.NoDragDrop` |
| U9 | 🟢 Low | UI/UX | No keyboard-first timeline scrub (`j`/`k`/`r`/`g`); mouse-only nav | Open | Timeline key bindings |
| U10 | 🟡 Medium | UX / API parity | `fm forensics --parse-artifacts` and trash recovery marketed cross-platform, only Linux works | Open | README + capability gating |
| U11 | 🟡 Medium | UX | "Recover deleted files from the system trash" claimed on Windows; raises `TrashScanUnsupported` | Open | Either ship pywin32 path or scope the README |

> Severities follow the same legend used in [`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md). 🔴 = disqualifying for forensic use; 🟠 = real risk in production; 🟡 = hardening or usability; 🟢 = polish.

---

## 1. Current state assessment & viability

### 1.1 What the product is, today

A Python file-management utility whose architecture is genuinely above the median for hobby tooling: filesystem mutation is centralised through
`FileActionService` (`dataforge/core/services/file_actions.py`), scanning through one function
(`dataforge/core/scanner.py`), hashing defaults to SHA-256
([AUDIT_FINDINGS.md S1](./AUDIT_FINDINGS.md)), the SQLite cache is WAL-locked
(M5), and the scanner skips symlinks (S3/M3 fixed). The CLI is a thin Click
adapter; the GUI is PyQt5 with a consistent preview → confirm → execute
pattern routed through `FileActionService`.

### 1.2 What the product claims

From [`README.md`](../../README.md):

- "**Professional file and system intelligence platform** for … digital forensics specialists" (line 5)
- "Enterprise-grade … forensic carving, integrity verification …" (line 9)
- "File carving — recover files from disk images by signature (JPEG, PNG, PDF, ZIP, and 30+ more types) — **resurrect lost data**" (line 51)
- "Recover deleted files from the system trash or external media — **get files back**" (line 50)

### 1.3 Defensible as a forensic product? — No, today.

The codebase fails the load-bearing pillars that courts and ISO/IEC 27037,
ACPO, RFC 3227, and NIST SP 800-86 require. The five disqualifying gaps
(also in [`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md) "Forensic-soundness
checklist"):

1. **No chain-of-custody / tamper-evident audit log** (F1). Every read,
   copy, export, hash, and report emission must produce an entry that an
   opposing expert cannot forge. The audit table currently lists this as
   "❌". The forensics checklist also lists "Read-only evidence handling"
   as Partial and "Chain-of-custody / audit log" as `None`.

2. **No acquisition provenance** (F2). `dataforge/modules/forensics.py:550`:
   `generate_forensic_report` writes a JSON object containing only
   `report_generated`, `tool`, `data`. No operator ID, no host name, no
   image hash, no write-blocker assertion, no case ID. See F2 below for
   line-level evidence.

3. **No read-only "Evidence Mode"** (F3, U2). `secure_delete`
   (`dataforge/modules/forensics.py:912-958`), the entire `FileActionService`
   write path, and the metadata cleaner are all one toolbar click away from
   the same GUI that "investigates" evidence. There is no seam that hard-
   mounts the tool in read-only state during an investigation.

4. **Inconsistent timestamps** (F9). `build_timeline`
   (`dataforge/modules/forensics.py:754-791`) emits UTC ISO-8601, but
   `generate_forensic_report` (line 563) uses `datetime.now().isoformat()`
   — naive local. Mixed tz in one forensic artefact is enough to draw a
   challenge to operator discipline.

5. **`secure_delete` lives in the forensic module** (F4). A "destroy"
   function sitting beside carving and timeline generation is a product-
   design red flag that any procurement review will catch.

### 1.4 Defensible as a power-user file-management utility? — Yes, with caveats.

For its file-management / dedup / integrity / search surface, DataForge is
competent and usefully distinct. The "with caveats" set:

- Three marketed capabilities are misleading today (U10, U11, and the
  "30+ types" carving claim — see F6 for why carving success rate will not
  match the marketing).
- The two highest-blast-radius security findings for any deployment where an
  evidence USB stick is share input — S4 (trash-restore path traversal) and S5
  (plugin loader executes arbitrary local Python) — are now **closed in WS-B**
  ([`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md), [`IMPLEMENTATION_PLAN.md` §4](./IMPLEMENTATION_PLAN.md)).
  What remains is architectural, not the original abuse path: parser/plugin
  process isolation and signing (F12) and a chain-of-custody hook on restore
  (F19). Both are tracked below.

### 1.5 False-positive / false-claim risks in production

| Claim | Source | Reality | Finding |
| --- | --- | --- | --- |
| "Recover deleted files from the system trash or external media" | README:50 | `_scan_windows_trash` raises `TrashScanUnsupported` (`recovery.py:184-196`) | U11 |
| "File carving … 30+ types" | README:51 | Carver matches only at 512-byte sector boundaries (`recovery.py:373`); many headers will be missed | F6 |
| "Detect tampering" | README:49 | `IntegrityMonitor` detects NEW/MODIFIED/DELETED; does not detect tampering with the snapshot itself (no hash-chain, and `create_snapshot` still writes via plain `open` while reports are now `0600`) | F1 / F11 (report-perms half fixed under S12) |
| "OS artifact parsing" cross-platform | README:55 | `parse_os_artifacts` (`forensics.py:121-329`) only reads `/etc/passwd`, `/var/log/*`, shell history, cron, dpkg, systemd — Windows returns the empty artefact dict | U10 |
| Entropy verdict "likely encrypted/packed" at ≥ 7.95 | `forensics.py:717-724` | xz/zstd/JPEG >1 MB/MP4 fragments/PNG optimised all score 7.5-8.0; presents false positives to triage | F-cluster (engine) |

### 1.6 Viability verdict (one sentence)

DataForge today is **defensible as a power-user file-management utility with
forensic-flavoured triage features** and **not defensible — and not legally
marketable — as a forensic product competing with EnCase/FTK/AXIOM/FIM**
until F1–F4 and U2 are closed.

---

## 2. Core logic & forensic engine improvements

### F1 — Chain-of-custody / tamper-evident audit log

> ⏳ status: Open · Risk: 🔴 Critical · Effort: S · Targets release v0.2.0

- **Where.** Audit log does not exist. Application log is `~/.dataforge/app.log`
  via `dataforge/core/logger.py` — a rotating file (5 MB × 3 backups), default
  world-readable; not hash-chained; not append-only; can be truncated by any
  process that owns the user. Audit log hook is listed as Phase 2 architecture
  work in [`IMPROVEMENT_PLAN.md` §4.2](./IMPROVEMENT_PLAN.md) but not built.
- **Why.** Chain-of-custody / tamper-evidence is the load-bearing
  expectation of every forensic standard (ACPO Principle 2; ISO/IEC 27037
  §6.4; NIST SP 800-86 §3.1). Without an append-only, hash-chained audit
  trail covering every file touch and every report emission, opposing
  expert testimony will exclude results in any contested proceeding, and a
  procurement RFP evaluator will mark DataForge "fail" on integrity.
  `forensics.py:550` writes report files at `0o600` (good — added per the
  S12 hardening pass), but `integrity.create_snapshot` writes via plain
  `open` — even the partial hardening is inconsistent across report-emitting
  sites, and neither path is chained into an audit trail.
- **How.** Build a new `dataforge/core/audit.py` with this contract:
  - Append-only file opened with `os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)` from a directory owned `0700` by the running user.
  - Each entry is JSON `{ts_utc, op, src, dst, actor, case_id, prev_hash, entry_hash}` where `entry_hash = HMAC_SHA256(session_key, prev_hash || canonical_json(fields_minus_entry_hash))`.
  - `session_key` is generated at app boot from `os.urandom(32)` and lives in process memory only.
  - At start, recompute the chain backwards. If the existing file's last
    `entry_hash` does not match the recomputed value, **refuse to start** and
    surface "Audit log tampered or truncated."
  - Hook the chain at two seams only:
    `FileActionService._run_batch_operation` (every move/copy/delete/rename/archive)
    and a new `core/reports.py::write_report(path, content)` (every report, snapshot, manifest, keyword file).
  - Refuse to run forensic ops if the audit log is not writable or its chain
    is broken.
  - Test: `tests/test_audit.py` — tamper with one byte of the log, assert app refuses start; verify HMAC chain validates after 10k entries; verify world-readable bit is not set (`stat -c %a`).

### F2 — Acquisition provenance in reports and manifests

> ⏳ Open · 🔴 Critical · Effort: S · Release v0.2.0

- **Where.** `dataforge/modules/forensics.py:550-578`
  (`generate_forensic_report`) and `dataforge/modules/forensics.py:431-543`
  (`ingest_disk_image`).
  The report object is `{"report_generated": ..., "tool": "DataForge Forensics
  Module", "data": results}` — no operator, no host, no image hash, no
  write-blocker assertion, no case ID. `ingest_disk_image` hashes only the
  files inside the mounted tree (line 496), **not the source image itself**.
- **Why.** Acquisition provenance is what ties a derived artefact to a
  physical source. Without the source image hash, you cannot prove a hash
  manifest came from a specific image — only from "a directory that looked
  like one." A procurement reviewer and any contested case requires the
  source hash.
- **How.**
  - Extend the report dict to include `{operator, host, os_release, kernel_version, source_path, source_sha256, source_size, source_ro_mode, case_id, audit_log_tail_hash, tool_version}`.
  - Add `hash_source_image(path)` in `core/image_io.py` that streams SHA-256 of the raw image (or, for E01, of the logical reassembled stream) — documented as a *mandatory* pre-acquisition step.
  - Reject `ingest_disk_image` if `source_sha256` is missing.
  - Test: `tests/test_forensics_provenance.py` — assert all new keys present; assert mismatch between actual and recorded `source_sha256` causes `verify_snapshot` to fail.

### F3 — EVIDENCE MODE: read-only investigation toggle (with U2)

> ⏳ Open · 🔴 Critical · Effort: M · Release v0.2.0

- **Where.** No toggle exists. The centralised write path is
  `dataforge/core/services/file_actions.py:FileActionService._run_batch_operation`.
  `secure_delete` (`forensics.py:912-958`) and `MetadataCleaner.remove_metadata`
  (`modules/cleaner.py`) bypass via different paths.
- **Why.** In an investigation session, every mutation of evidence destroys
  admissibility. Today, the same UI that builds timelines can one-click
  delete a file via the context menu. ACPO Principle 1 ("No action taken
  should change data which may subsequently be relied upon in court") is
  violated by the tool's own design, not by user discipline.
- **How.**
  - Add a top-level `CaseContext` (see U1) with an `evidence_mode: bool` flag, sticky in the UI window chrome.
  - When `evidence_mode` is on, `FileActionService._run_batch_operation` returns
    `OperationResult(success=False, message="Write blocked in EVIDENCE MODE")`
    for every operation that would mutate the source tree. Use a single guard at the method head, not at each operation site.
  - Gate `MetadataCleaner.remove_metadata`, `secure_delete`, and the Cleaner
    pipeline `MetaCleanStep` (`core/actions/modifications.py`) at the same
    `CaseContext.evidence_mode` flag.
  - UI: a persistent label in the status bar reads `EVIDENCE MODE — writes blocked`; every destructive button is `setEnabled(False)`; the toggle emits an audit entry when changed.
  - Test: `tests/test_evidence_mode.py` — flip `CaseContext.evidence_mode` and assert every `FileActionService` mutator returns `success=False` with no filesystem change.

### F4 — `secure_delete` placement

> ⏳ Open · 🔴 Critical · Effort: S · Release v0.2.0

- **Where.** `dataforge/modules/forensics.py:912-958` (`secure_delete`).
  Also flagged in S6 ([`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md)) as "false
  assurance" — overwrite-in-place doesn't work on SSDs/flash/CoW/journaled FS.
- **Why.** Including a "destroy" routine inside the forensic module encourages
  its use during investigation; SSD/CoW realities mean the data may persist,
  but the APPEARANCE of destruction will draw an obstruction allegation in
  court. Even with the docstring caveat (already added, lines 916-921),
  presence in `modules/forensics.py` is a procurement flag.
- **How.**
  - Move `secure_delete` to a new `modules/sanitisation.py` outside the forensics import path, gated under a separate CLI subcommand `fm sanitize` (not `fm forensics`), with a mandatory confirm and an audit-log entry before any write.
  - Rename internal label to "best-effort overwrite" (already done in docstring) and surface that name in the UI/menu — never "secure delete."
  - Refuse to operate when `CaseContext.evidence_mode` is set.
  - Make the overwrite hardlink/reflink-aware — see **F21**. The point-fix for
    the SSD/CoW false-assurance (S6) landed in WS-B, but the hardlink case
    (overwrite destroys data reachable by another link; unlink leaves it intact)
    is a distinct correctness gap that this seam must also close.
  - Test: `tests/test_sanitisation.py` — assert that the forensics module no longer imports `secure_delete`; assert that under evidence mode, `sanitize` returns `"blocked"`.

### F5 — Raw image support (E01 / AFF4 / dd) without requiring mount

> ⏳ Open · 🟠 High · Effort: L · Release v0.3.0

- **Where.** `dataforge/modules/forensics.py:473-475` admits "Full raw image
  mounting would require loop devices and root access." The current code path
  only operates on `os.path.isdir(scan_path)`.
- **Why.** A forensic tool that requires the user to mount the evidence
  image before analysis breaks write-blocker discipline (loop mounts are
  read-write by default), requires root (excluding non-root examiners), and
  fails entirely on Windows. Professional tools bundle `libewf`/`pyaff` to
  read E01/AFF4 directly. Without this, the product is not deployable in
  real forensic workflows.
- **How.**
  - Add `dataforge/core/image_io.py` exposing `open_image(path) -> FileLike` that dispatches on magic bytes: E01 (`4C 00 00 00 ... 41 4E 00 ...`) → `pyewf` (`libewf-python`); AFF4 → `pyaff4`; raw dd → `os.open(path, os.O_RDONLY)`.
  - Verify read-only assertion: for raw dd on Linux, verify `blockdev --getro <dev>` returns 1; refuse otherwise.
  - `Ingest_disk_image` accepts the `FileLike`, not a directory, and runs every scanner / hasher / keyword worker against the resulting stream.
  - Document the required kernel capability (`CAP_SYS_RAWIO` only for the read-only probe; *never* open block devices `r+b`).
  - Test: `tests/test_image_io.py` — open a 10 MB dd fixture, a synthetic E01 fixture (via `ewfexport`), and assert SHA-256 of `FileLike.read()` matches raw SHA-256.

### F6 — Carving alignment, sliding-window scan, streaming write

> ⏳ Open · 🟠 High · Effort: M · Release v0.3.0

- **Where.** `dataforge/modules/recovery.py:312-440` (`carve_files_from_image`).
  Specifically: line 370 `header_buf = f.read(block_size + 16)` matches only
  at sector boundaries (512-byte increments). Line 385
  `file_data = f.read(min(max_size, file_size - offset))` reads the entire
  candidate file into RAM in one shot. Line 394 truncates to `max_size` for
  footer-less types.
- **Why.** Real carving tools (scalpel, photorec) use sliding-window
  multi-pattern matchers and validate structure. Sector-aligned scanning
  misses any header that sits mid-sector — extremely common with slack-space
  carving. The 30+ types marketing claim is technically true by signature
  count but operationally misleading without alignment-free matching.
- **How.**
  - Refactor `carve_files_from_image` to read a 4 MB sliding buffer with a `Boyer-Moore-Horspool` matcher (or single `BytesIO` + Aho-Corasick over all signatures at once) — `pyahocorasick` is a zero-dep wheel option.
  - On match at arbitrary offset, stream the candidate to the output file in 64 KB chunks until footer (or `max_size`) — never buffer the whole file.
  - Validate pixels (Pillow `Image.verify()` for JPEG/PNG, `pypdf.PdfReader` for PDF) before writing — false positives in carving drop ~80% with one cheap validation pass.
  - Emit audit log entry per carved file with offset + source hash.
  - Test: `tests/test_carving.py` — embed a JPEG with its SOI 200 bytes into a sector (offset 712); assert carver finds it; assert a "decompression-bomb" PNG fixture (declared 50000×50000) is rejected by `Image.verify()` and never written.

### F7 — YARA, SSDEEP/TLsh, NSRL known-good pivot

> ⏳ Open · 🟠 High · Effort: L · Release v0.3.0

- **Where.** `dataforge/modules/forensics.py:369-424`
  (`keyword_search`) is byte-substring matching against a UTF-8 encoding of
  the keyword against the first 10 MB. No fuzzy hashing, no indicator
  matching, no known-hash pivot.
- **Why.** Without YARA, the tool cannot apply industry-standard indicator
  rules. Without SSDEEP/TLsh, the tool cannot find *similar* (not identical)
  files — the single most useful function for malware triage and known-bad-
  document pivoting, which `find_duplicates` cannot do (it only finds
  bit-identical files). Without NSRL/known-good, an investigator drowns in
  OS binaries in every timeline.
- **How.**
  - **YARA.** Bundle `yara-python`. Curated rule directory `dataforge/rules/` ships a minimal pack; user can add. API: `yara_scan(paths, rules_namespace, progress_callback, cancel_token) -> list` using `rules.match(filepath=p, externals={filename, filesize, ext})` — never `data=` (mmap-bypass on Windows can be unsafe). Compile rules once per session with `yara.compile(filepaths=...)`; refuse user-supplied rules without a 5s compile timeout (regex DoS).
  - **TLsh (preferred over ssdeep — Python wheels exist, permissive licence).** Compute TLSH for every file ≥ 256 B during a scan, persist alongside SHA-256 in `core/cache.py` (extend schema with `tlsh TEXT`). Query via bucketized leading 16 bits of the TLSH hash for O(1) candidate lookup, then rank by `tlsh.compare`. Thresholds to document: < 30 near-duplicate, 30–100 related-family, > 100 unrelated.
  - **NSRL.** New `core/hashsets.py::load_nsrl(path)` ingests the RDS hash set into a separate `hashsets` SQLite table. `filter_known_good(file_paths) -> list` removes NSRL hits from timeline default view. Update in batches at install, not at runtime.
  - Test: `tests/test_indicators.py`, `tests/test_tlsh.py`, `tests/test_nsrl.py`.

### F8 — ADS, xattrs, Mark-of-the-Web

> ⏳ Open · 🟠 High · Effort: M · Release v0.3.0

- **Where.** `dataforge/core/scanner.py` and `dataforge/modules/forensics.py`
  have no concept of NTFS Alternate Data Streams, Linux/macOS extended
  attributes, or macOS `com.apple.quarantine` (Mark-of-the-Web analog).
- **Why.** On Windows evidence, ADS is where malware hides payloads, where
  `Zone.Identifier` records the Mark-of-the-Web verdict increasingly cited
  in court, and where illicit exfiltration content is stashed. Without ADS
  enumeration, the timeline will omit the most forensically relevant data
  and present a false "complete" picture — **this alone makes the tool
  dangerous to use on Windows evidence**.
- **How.**
  - New `dataforge/core/streams.py`:
    - Windows: `enumerate_streams(path)` via `FindFirstStreamW` (use `pywin32` or fall back to `Get-Item -Stream *`); `read_stream(path, stream_name)`.
    - Linux: `os.listxattr(path)`, `os.getxattr(path, attr)`. Surface `user.*`, `security.*`, `trusted.*` separately.
    - macOS: same listxattr API plus treat `com.apple.quarantine` specifically.
  - Each stream becomes its own `FileEntry` with `entry.path = path + ":" + stream_name` (Windows) or `path + "#" + attr` (Unix), flagged `is_ads=True` for the timeline view.
  - Hash each stream separately; ADS hashing of `Zone.Identifier` is itself evidence.
  - Test: `tests/test_streams.py` using `setxattr` on Linux and a Windows-specific skip if `pywin32` is absent.

### F9 — Forensic timestamp standardisation (UTC everywhere)

> ⏳ Open · 🔴 High · Effort: S · Release v0.2.0

- **Where.** Mixed tz in source:
  - `dataforge/modules/forensics.py:563` `datetime.now().isoformat()` (naive local) for `report_generated`.
  - `dataforge/modules/forensics.py:777-781` `datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()` (UTC) for timeline.
  - `dataforge/modules/recovery.py:143`, `:539` (`datetime.now().timestamp()`), and `:556` (`datetime.fromtimestamp(stat.st_mtime).isoformat()`) are naive local.
- **Why.** Mixed tz in one forensic artefact is enough to draw a court
  challenge to operator discipline. The audit table lists "Deterministic,
  timezone-aware timestamps" as ⚠️ Partial.
- **How.**
  - New helper `core/dt.py::utc_now_iso() -> str` returning `datetime.now(timezone.utc).isoformat()`. Replace all `datetime.now()` and bare `datetime.fromtimestamp(ts)` call-sites in `modules/forensics.py`, `modules/recovery.py`, `modules/integrity.py`, `core/logger.py`.
  - Set `os.environ["TZ"] = "UTC"` at app boot in `dataforge/__init__.py` as belt-and-braces (does not affect `tz=timezone.utc` callers).
  - Reports display a header `All timestamps UTC ISO-8601 (offset +00:00).`
  - Test: `tests/test_utc.py` — assert every emitted ISO timestamp ends with `+00:00`; assert `UTC` env is set at first import.

### F10 — Filename Unicode normalisation & homograph handling

> ⏳ Open · 🟠 High · Effort: M · Release v0.2.0

- **Where.** `dataforge/core/scanner.py:14-15` uses `os.path.basename`
  and `os.path.splitext`. `dataforge/modules/duplicates.py` and
  `search.py` use `.lower()` for case-insensitive grouping.
- **Why.** (a) Turkish dotless-i, Greek/Cyrillic confusables, and
  NFC vs NFD normalisation collisions (macOS stores NFD; Linux stores
  NFC; cross-FS copy produces a duplicate hit on the same name).
  (b) Filenames containing U+202E (RIGHT-TO-LEFT OVERRIDE) can render
  an extension backwards — `report[rtlo].exe` displays as `reportexe.` —
  the canonical homograph attack on investigators. Without handling,
  dedup correctness fails and timeline displays are deceptive.
- **How.**
  - For *comparison only*, normalise filenames with `unicodedata.normalize("NFC", name)` in duplicates and search; keep raw bytes on display alongside the character view so the investigator sees both.
  - Add `core/filename_safety.py::is_suspicious_filename(name) -> tuple[bool, list[str]]` returning flags for bidi controls (`U+202A..U+202E`, `U+2066..U+2069`), confusables (via `unicodedata` confusables table), overlong UTF-8 sequences, and NUL bytes.
  - `build_timeline` emits `is_suspicious: True, suspicious_reasons: [...]` in the event dict; timeline view (U3) flags these red.
  - Test: `tests/test_filename_unicode.py` — assert `café (NFC)` matches `café (NFD)` for grouping but not for display; assert a `U+202E` filename is flagged.

### F11 — Tamper-evident audit log replacement for `app.log`

> ⏳ Open · 🟠 High · Effort: M · Release v0.2.0

- **Where.** `dataforge/core/logger.py` — rotating file handler
  (5 MB / 3 backups), no `0o600`, no hash chaining. Open as S12 in
  [`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md).
- **Why.** The operator's attacker-of-interest can trivially truncate
  `app.log`. Rotating handlers discard entries. World-readable means any
  local process can read the audit trail.
- **How.**
  - Split `core/logger.py` into two paths:
    - Application log (`app.log`) — kept rotatable, **not** used as audit trail, owned `0o600`.
    - Audit log (`audit.jsonl`) — append-only, hash-chained as in F1.
  - Audit log lives in `~/.dataforge/audit/` with directory `0700`; the file is `0600`; never rotates.
  - The audit trail supersedes any reliance on `app.log` for evidence-integrity claims.
  - Test: `tests/test_audit_log_tamper.py` — truncate `audit.jsonl`, assert app refuses to start.

### F12 — Plugin loader privilege boundary (S5 escalation)

> 🟡 Partial · 🟠 High · Effort: M · Release v0.2.0

- **Where.** `dataforge/ui/plugin_loader.py:40-75` (S5,
  [`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md)). WS-B **partially hardened** this:
  loading is now opt-in behind an `enabled` flag (line 26-28), the plugins
  directory is rejected if group/world-writable (`_check_plugin_dir_permissions`),
  and each `*.py` is skipped unless owned by the running UID
  (`_check_plugin_file_owner`). **What remains open:** the surviving `glob("*.py")`
  (line 40) is still imported in-process with `spec.loader.exec_module(module)`
  (line 63) — no signing, no manifest, no sandbox, and the audit-log record of
  each load (F11) is not yet wired.
- **Why.** On a shared investigator workstation a malicious plugin dropped by
  another user — or by a scanned evidence artifact if the user ever points
  `--path` at an attacker-controlled tree — gets full app privileges, can
  read the audit key from process memory, and can unlink reports.
- **How.**
  - Load plugins from a single directory `~/.dataforge/plugins/` owned `0700` by the running user; refuse to load if the directory is group/world writable or not owned by the running UID.
  - Require a signed `manifest.json` per plugin with `sha256` of the `.py`; verify against a trusted list (start with empty list — first-party bundled `cleaner_plugin.py` gets added by default).
  - Log every plugin load in the F11 audit log with path + hash + signature result.
  - Long-term: run plugins in a `subprocess`-isolated worker with reduced privileges (matches F13).
  - Test: `tests/test_plugin_trust.py` — drop a malicious plugin in a world-writable dir; assert loader refuses; assert unsigned plugin is skipped; assert audit trail contains a "plugin load denied" entry.

### F13 — Untrusted-parser process isolation

> ⏳ Open · 🟠 High · Effort: M · Release v0.3.0

- **Where.** `Pillow.Image.open`, `pypdf.PdfReader`, `mutagen.File`,
  `defusedxml.ElementTree.parse` are all called in-process on
  attacker-controllable files
  (`modules/forensics.py`, `modules/cleaner.py`, `modules/metadata.py`,
  `core/media_ops.py`). Pillow has had RCE CVEs historically
  (CVE-2023-50447 etc.).
- **Why.** For a forensic tool, in-process parsing of evidence files
  means one malicious file compromises the entire investigation and the
  audit key. S13 ([`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md)) is a subset
  of this; the broader category is parser-process isolation.
- **How.**
  - Introduce a `core/parse_worker.py` `ProcessPoolExecutor` with each worker calling `resource.setrlimit(RLIMIT_CPU, ...)` and `RLIMIT_AS` per call; on Linux add a `seccomp`` filter that allows only `read/write/exit`.
  - `Image.open`, `PdfReader`, `mutagen.File`, and `ET.parse` are wrapped to delegate to the worker pool via a `parse_in_worker(path, parser_name, **kwargs)` helper.
  - Per-call CPU cap: 30s; per-call memory cap: 256 MB default (configurable).
  - Test: `tests/test_parse_worker.py` — feed a Pillow decompression-bomb fixture (declared 50000×50000 PNG, < 4 KB compressed), assert worker is killed by `RLIMIT_AS`; feed a `PdfReader` 100k-page PDF, assert worker is killed by `RLIMIT_CPU`.

### F14 — Streaming ingest and `FileEntry` MACB extension

> ⏳ Open · 🟡 Medium · Effort: M · Release v0.2.0

- **Where.** `dataforge/modules/forensics.py:485-489` materialises
  `file_paths`. `dataforge/modules/forensics.py:768` calls `os.stat` again
  inside the timeline loop — duplicating the stat `scan_directory` already
  did.
- **Why.** On a 50 M-file volume, materialising strings is ~5-10 GB of
  memory; doubling syscalls halves throughput.
- **How.**
  - Pass the scan generator directly to a streaming hasher (`calculate_hashes` should accept an iterable, not a list).
  - Extend `dataforge/core/common.py::FileEntry` with `atime, ctime, btime, owner_uid, owner_gid, mode` populated by `build_file_entry`.
  - Rename `FileEntry.created_at` → `FileEntry.ctime` (this is a documentation correctness fix: `scanner.py:17` currently sets `created_at=stat.st_ctime` — on Linux ext4, st_ctime is metadata-change time, **not** creation time; the field is mislabeled and will produce a court-usable error in expert testimony).
  - Use the existing batch `ThreadPoolExecutor.map` for streaming with fixed prefetch depth.
  - Test: `tests/test_streaming_ingest.py` — assert peak RSS under ~500 MB for a 1 million FileEntry generator.

### F15 — Keyword worker memory budget

> ⏳ Open · 🟡 Medium · Effort: S · Release v0.2.0

- **Where.** `dataforge/modules/forensics.py:351` reads 10 MB per worker
  *into worker memory*; `config["search_thread_workers"]` is user-tunable.
- **Why.** With `max_workers=32` (a plausible power user setting), in-flight
  buffers total 320 MB; on a constrained examiner laptop that is a clear
  regression.
- **How.**
  - Add a `threading.BoundedSemaphore(max_concurrent_bytes)` sized to
    `min(psutil.virtual_memory().total // 4, 256 * 1024 * 1024)`.
  - Each worker acquires `min(file_size, 10 MB)` bytes from the semaphore and releases on return.
  - Set `search_thread_workers` floor at 1, ceiling at `max(1, mem_budget // 64_MB)`.
  - Test: `tests/test_keyword_search_budget.py` — assert that with `search_thread_workers=32` and 10k files, peak RSS stays under the budget.

### F16 — Sparse file detection

> ⏳ Open · 🔴 High · Effort: S · Release v0.2.0

- **Where.** `dataforge/core/scanner.py:16` populates `size=stat.st_size`
  (logical size, ignoring sparseness); no `st_blocks` check anywhere.
  `dataforge/core/hasher.py:19-28` reads the full byte stream in fixed 64 KB
  chunks and will hash zero regions of sparse files as actual zeros —
  different from hashing the original content.
- **Why.** `os.stat().st_blocks * 512` is the physical block count; if
  `st_blocks * 512 < st_size`, the file is sparse. A 1 TB logically-sized
  sparse file will exhaust memory in hashers (size-keyed buffers) and
  produce a hash that does not match any real content.
- **How.**
  - Add `FileEntry.is_sparse: bool` set by `build_file_entry` when `stat.st_blocks * 512 < stat.st_size` and `stat.st_size > 1 MB`.
  - `get_file_hash` short-circuits sparse files: it streams the file (still produces a deterministic zero-fill hash for that file's logical-size content) AND records the sparse flag in the manifest entry.
  - Carver refuses sparse files with a clear surfaced reason.
  - Timeline marks sparse files with a ⚠ icon.
  - Test: `tests/test_sparse.py` — `dd if=/dev/zero of=fixture bs=1 count=0 seek=1G`; assert `FileEntry.is_sparse=True`; assert manifest entry carries the flag.

### F20 — Locked / in-use file handling & Volume Shadow Copy acquisition

> ⏳ Open · 🟠 High · Effort: L · Release v0.3.0

- **Where.** `dataforge/core/scanner.py` (`scan_directory`) and
  `dataforge/core/hasher.py:19-28` open each file with a plain read handle. A
  `PermissionError`/`OSError` from a file another process holds open is caught
  and the entry is silently dropped — there is no `access_error` field on
  `FileEntry`, no count in the report, and no Volume Shadow Copy (VSS) or
  raw-volume acquisition path anywhere in the tree.
- **Why.** On a live Windows host the most forensically valuable artefacts —
  the registry hives (`SYSTEM`, `SOFTWARE`, `NTUSER.DAT`), `$MFT`,
  `pagefile.sys`, `hiberfil.sys`, an open Outlook `.pst` — are **always** locked
  by the OS or a running process. Silently skipping them yields a report that
  claims a complete scan while omitting exactly the evidence that matters. This
  is the same false-completeness failure as F8 (ADS): the tool presents a
  confident, incomplete picture. The DFIR review prompt calls out "handling
  locked files" as a mandatory capability, and no professional tool acquires a
  live Windows volume without a shadow copy or raw handle.
- **How.**
  - **Surface, don't swallow.** In the scanner/hasher, catch the open error and
    record `FileEntry.access_error` (with the errno) instead of dropping the
    entry; count and display "N files inaccessible (locked/in-use)" in reports so
    the omission is explicit.
  - **Acquire via snapshot.** Add `dataforge/core/acquire.py` with a Windows VSS
    path — create a shadow copy (`vssadmin create shadow` or WMI
    `Win32_ShadowCopy.Create`), read the locked file from the snapshot device
    (`\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopyN\...`), then release the
    copy. This ties into F5 (raw-image support): a read-only raw-volume handle
    (`CreateFile(\\.\C:, GENERIC_READ, FILE_SHARE_READ|WRITE|DELETE, ...)`) is
    the fallback for whole-volume acquisition.
  - **Linux.** Locked-file cases are rarer (advisory locks), but still catch and
    record `EACCES`/`ETXTBSY`; document that live-volume acquisition should use
    a read-only loop/`dd` image (F5), never a mounted read-write source.
  - Refuse to operate against a read-write-mounted evidence volume when
    `CaseContext.evidence_mode` (F3) is set.
  - Test: `tests/test_locked_files.py` — Windows: open a fixture with an
    exclusive lock, assert the scanner records `access_error` and does **not**
    drop the entry; Linux: `xfail`/skip the exclusive-lock case, assert the
    `EACCES` path records the flag.

### F21 — Hardlink / reflink-aware `secure_delete` and deduplication

> ⏳ Open · 🟡 Medium · Effort: S · Release v0.2.0

- **Where.** `dataforge/modules/forensics.py:912-958` (`secure_delete` —
  overwrite-in-place then unlink) and `dataforge/modules/duplicates.py`
  (`find_duplicates` groups candidates by content hash only). Neither consults
  `st_nlink`, `st_dev`, or `st_ino`.
- **Why.** This is a correctness gap distinct from the SSD/CoW caveat already
  noted under F4/S6:
  - When `st_nlink > 1`, overwriting one path's bytes destroys the data that
    **every** hardlink to that inode points at — collateral destruction of
    unrelated evidence. Conversely, a bare unlink of one link leaves the content
    fully recoverable through the others — the "destroyed" file persists.
  - On reflink/CoW filesystems (btrfs, XFS `reflink`, APFS clones) an
    overwrite-in-place writes to freshly-allocated blocks, leaving the original
    extents intact.
  - Dedup that counts a hardlink as a reclaimable duplicate over-reports the
    space it will free (deleting one link frees nothing) and may delete a link
    the examiner relied on.
  Each case produces a false chain-of-custody claim — either "I destroyed this"
  when the bytes persist, or an unlogged mutation of a second artefact.
- **How.**
  - In the F4 sanitisation seam (`modules/sanitisation.py`), `os.stat` the target
    and if `st_nlink > 1` **refuse or warn** with the count of other links, and
    record `st_dev`, `st_ino`, and `st_nlink` in the audit entry (F1) so the
    action is attributable to a specific inode, not a path.
  - In `find_duplicates`, collapse entries sharing `(st_dev, st_ino)` into one
    physical file before computing reclaimable space, so hardlinks are never
    presented as recoverable savings.
  - Test: `tests/test_hardlink_safety.py` — create a hardlink pair, assert
    `secure_delete` refuses/warns and does not silently overwrite; assert dedup
    reports zero reclaimable bytes for the pair.

---

## 3. Backend & architecture hardening (deferred detail)

F11, F12, F13 above cover the headline hardening. Three further items:

### F17 — `_run_cmd` shell-out hardening

> ⏳ Open · 🟢 Low · Effort: S

- **Where.** `dataforge/modules/forensics.py:332-339` (`_run_cmd`) wraps
  `subprocess.run(cmd, capture_output=True, text=True, timeout=10)`. Used at
  line 303 with `["last", "-f", wtmp_path, "-n", "50"]` — `wtmp_path` is
  derived from user-supplied `root_path`.
- **Why.** No injection (argv list, no `shell=True`), but if `wtmp_path`
  resolves to a FIFO the `last` invocation blocks until the 10s timeout.
- **How.**
  - Before the `subprocess.run` call, `os.stat(wtmp_path)`; refuse to invoke `last` if `not stat.S_ISREG(st.st_mode)` or if `st.st_size % 4 != 0` (utmp record is 4-byte aligned; utmpx is variable but ≥ 8 bytes — pick a sensible floor).
  - Test: `tests/test_wtmp_validation.py` — assert a named-pipe fixture is rejected with a clear error message.

### F18 — S7 system-cleanup over-classification (links to existing S7)

> 🟡 Partial · 🟠 High · Effort: S · Release v0.2.0

- **Where.** `dataforge/modules/system_cleanup.py:201-300` (S7,
  [`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md)). WS-B **fixed the live abuse path**:
  sockets/FIFOs are now skipped (line 267), System Temp entries carry a
  minimum-age guard of one day (lines 273-275), and user-supplied `--path`
  no longer inherits blanket classification — it falls under a stricter
  extension/name-only rule (lines 277-281). **What remains open:** the
  blanket-by-category rule still fires for the built-in category roots
  (`category in ("System Temp", "User Cache", "Thumbnails", "Trash", "Crash
  Reports")`, line 286), so an allow-list of provably-safe subtrees is still
  the higher-precision follow-up.
- **Why.** The original data-loss incident (point-at-my-folder deletes a live
  socket or in-use temp file) is closed. The residual is precision, not safety:
  the built-in category sweep is coarser than an allow-list would be.
- **How.** Remaining work at `system_cleanup.py`:
  - Allow-list safe subtrees (e.g., `~/.cache/mozilla/*/cache2/`) instead of
    the whole category root.
  - Extend the age/handle guards from System Temp to the other category roots.
  - Test: `tests/test_system_cleanup_safety.py` already guards the user-path
    case (`test_junk_scan_never_blanket_classifies_user_supplied_path`, WS-B);
    add an allow-list precision test when the follow-up lands.

### F19 — S4 trash-restore confinement (links to existing S4)

> 🟡 Partial · 🟠 High · Effort: S · Release v0.2.0

- **Where.** `dataforge/modules/recovery.py:205-309` (S4, **closed in WS-B**).
  `_is_safe_restore_path` (lines 205-227) now rejects non-absolute paths,
  `..` traversal, and system directories; unsafe paths are redirected to the
  confined `restore_root` fallback (line 270), and `os.makedirs(parent,
  exist_ok=True)` (line 283) only runs inside that root. **What remains open:**
  the restore action is not yet written to the F1 audit trail.
- **Why.** The path-traversal vector itself is closed (S4). The residual gap is
  chain-of-custody: per F1 every restore must emit a tamper-evident audit
  entry, which cannot land until `core/audit.py` exists.
- **How.**
  - Hook `restore_from_trash` into the F1 audit trail (`core/audit.py::log_entry`) with `op="restore"` and `{src=trash_path, dst=dest, validate_reason, case_id}`.
  - Refuse restore under EVIDENCE MODE (F3/U2).
  - Test: `tests/test_restore_audit.py` — assert restore records an audit entry; assert EVIDENCE MODE blocks restore.

---

## 4. UI / UX improvements for investigators

This section expands beyond the existing [`IMPROVEMENT_PLAN.md` §2](./IMPROVEMENT_PLAN.md)
UX review — which is structured around *general* usability — with
investigator-specific UX. Severity convention same as above.

### U1 — Case / evidence / operator context

> ⏳ Open · 🟠 High · Effort: M · Release v0.2.0

- **Where.** No concept of a "case," "evidence item," or "examiner" exists
  anywhere in `dataforge/`. Every export is just unattributed JSON.
- **Why.** Professional tools gate every operation behind a case context.
  Without it, no report can be attributed to an examiner, no two
  investigations can be kept separate, and the audit trail (F1) has no
  `case_id` to chain.
- **How.**
  - New `dataforge/core/case.py::CaseContext` dataclass: `{case_id, examiner_id, evidence_root, evidence_mode, opened_at, audit_log_tail_hash}`.
  - CLI: `fm --case <id> --examiner <id>` (or read from `~/.dataforge/case.json`); every forensic command inherits the context.
  - GUI: a sticky header widget in `DataForgeApp` showing `CASE: <id> · EXAMINER: <id> · EVIDENCE MODE: <on/off>`. Open/Case menu item to create or switch.
  - `generate_forensic_report` pulls operator/host/case_id from `CaseContext` for F2.
  - Test: `tests/test_case_context.py` — assert every report contains the case ID and examiner ID; assert CLI refuses forensic ops without `--case`.

### U2 — EVIDENCE MODE UI toggle (link to F3)

> ⏳ Open · 🔴 High · Effort: S (once F3 seam exists) · Release v0.2.0

- **Where.** Top-of-window chrome today shows theme toggle and tier; no
  EVIDENCE MODE control. `dataforge/ui/app.py::DataForgeApp.__init__`.
- **Why.** Even with F3's `FileActionService` gate, the UI must make the
  state visible and sticky, or the operator will forget they're in
  destructive mode and act.
- **How.**
  - Sticky badge in the status bar reading `EVIDENCE MODE — writes blocked` with the `danger` token colour.
  - Toggle action in a menu `Case → Toggle Evidence Mode`; emit an F1 audit entry on every toggle.
  - When evidence mode is on, every destructive button (move, copy, delete, rename, archive, secure-delete, metadata-clean) is `setEnabled(False)`; context menu removes those entries.
  - Test: `tests/test_ui_evidence_mode.py` (pytest-qt) — assert number of disabled buttons; assert toggle persists across view switches.

### U3 — Virtualised timeline view

> 🟡 Partial · 🟠 High · Effort: M · Release v0.3.0

- **Where.** `build_timeline` (`forensics.py:754-791`) returns a flat sorted
  list. The Forensics screen (`ui/views/forensics_view.py`) is **tab-driven**
  (`QTabWidget`, 11 tabs) and already renders a flat **Timeline tab**
  (`forensics_view.py:770-821`). What is missing is the *virtualisation*: the
  tab loads every event into the widget at once.
- **Why.** A flat, fully-materialised list past ~5,000 events produces
  investigator fatigue, scrolling-induced RSI, and missed events at high triage
  velocity.
- **How.**
  - New `ui/views/timeline.py::TimelineView(BaseView)` backed by a `QTreeView` with a `QAbstractItemModel` that loads pages of 1k events from DuckDB (F-engine).
  - Layout: vertical swimlane per file; time on y-axis, color-coded by MACB type (M=amber, A=green, C=blue, B=violet — paired with glyphs per U6).
  - Sticky scrubber at top with hour markers; `j`/`k` keyboard navigation, `r` jump to selection, `g` jump to start, `G` jump to end.
  - Lazy-load on scroll (Qt's `fetchMore`).
  - Test: `tests/test_timeline_view.py` — synthesise 100k events; assert memory RSS constant during scroll; assert `j`/`k` move selection.

### U4 — Inline hex view + field inspector

> 🟡 Partial · 🟠 High · Effort: M · Release v0.3.0

- **Where.** `dataforge/modules/forensics.py:798-842` returns a structured hex
  dump, and the Forensics screen now hosts an inline read-only **Hex Viewer tab**
  (`forensics_view.py:868-914`, fed by `hex_dump`). The risky OS-default-handler
  hand-off (S11) is **fixed** (commit `961cf7f`): `open_file()` gates on
  `_is_executable_file` and shows an "Open Executable?" confirm
  (`widgets.py:860-866`). **What remains missing** is the recognised-field
  *inspector* — the hex tab shows raw bytes with no decoded structure.
- **Why.** Investigators do not leave the tool to inspect bytes; a raw hex pane
  is table stakes, but the differentiator is decoding the byte under the cursor
  to a named header field.
- **How.**
  - Upgrade the Hex Viewer tab (or a new `ui/widgets/hexview.py::HexView`) to a
    16-byte grid with an offset gutter and lazy 64 KB page loads on scroll.
  - Add an inspector pane showing the magic-byte interpretation of the bytes
    under the cursor — extend `file_signatures.py::identify_file_type` with
    field-offset annotation for the top 10 file types (PNG IHDR, JPEG SOI/APP0,
    ZIP local file header, PDF header, MFT entry, registry hive cell, E01 header,
    ELF header, MZ/PE, GZIP).
  - Add an "Inspect Bytes" context-menu entry that opens the file in the Hex tab
    rather than the OS handler (the S11 executable-open confirm already covers
    the residual risk).
  - Test: `tests/test_hex_view.py` — assert PNG IHDR width/height are decoded from cursor bytes.

### U5 — "Suspicious mismatches" filter (cheap, high-value)

> ⏳ Open · 🟡 Medium · Effort: S · Release v0.2.0

- **Where.** `dataforge/modules/forensics.py:651-676` (`profile_directory_types`)
  already computes `format` and `extension`, and these are returned in `rows`.
  No view surfaces the mismatch.
- **Why.** "Filename says .jpg, magic bytes say PDF" is among the highest
  signal/effort forensic findings. Surfacing it explicitly is the strongest
  fatigue-reducing UX win available.
- **How.**
  - Add a `Mismatch Filter` toggle in the Forensics view; on toggle, filter the `profile_directory_types` rows where `entry.extension` (lowercased, dot-stripped) is not in `signature.extensions` for the detected `format`. Skip if either is unknown.
  - Add a red glyph (∅) in the row gutter for mismatches.
  - Test: `tests/test_mismatch_filter.py` — fixture with `evil.jpg` containing PNG bytes; assert it appears in the mismatch view.

### U6 — Pair every semantic colour with a glyph

> ⏳ Open · 🟡 Medium · Effort: S · Release v0.2.0

- **Where.** `dataforge/ui/theme_tokens.py` — AA-validated token table; the
  audit (`IMPROVEMENT_PLAN.md` §2.5) lists colour-only meaning as open.
- **Why.** Colour-only state fails colour-blind investigators (~8% of the
  population, ~1 in 4 of any large forensic team over a year). Pairing colour
  with an inline glyph is also the single most effective change to reduce
  investigator misreads at 14-hour-session fatigue.
- **How.**
  - Extend the token table with a `glyph` column mapping `success→✓`, `warning→⚠`, `danger→✕`, `info→ⓘ`, `modified→🖉`, `missing→⌫`, `mismatch→∅`.
  - Apply at all row-status sites in EnhancedTreeview, timeline, integrity view.
  - Test: `tests/test_token_glyphs.py` — assert every semantic state has a glyph and the pair is unique.

### U7 — Destructive preview source-correlation

> ⏳ Open · 🟡 Medium · Effort: S · Release v0.2.0

- **Where.** `dataforge/ui/views/base.py::build_preview_message`
  (`IMPROVEMENT_PLAN.md` 2c.5).
- **Why.** For an investigator, the destructive preview must show the
  *source* of the action — which step in the action builder asked for it,
  which evidence row it touches — not just the destination. Without source
  correlation, the investigator cannot audit whether a step applied to too
  broad a selection.
- **How.**
  - Extend `BatchActionRecord` with `source_step_id` and `source_evidence_id`.
  - Preview checklist renders `{step_id} → {source_path} → {dst_path}` rows; per-row opt-out checkbox.
  - Test: `tests/test_preview_source.py` — assert every preview row shows its source step and evidence ID.

### U8 — Drag-and-drop hardening on evidence views

> ⏳ Open · 🟡 Medium · Effort: S · Release v0.2.0

- **Where.** `dataforge/ui/widgets.py::EnhancedTreeview` — default Qt view
  drag-drop config is not specified.
- **Why.** An accidental drag of an evidence file onto a delete target in
  the Action Builder would mutate evidence silently.
- **How.**
  - In `EnhancedTreeview.__init__`, set `setDragDropMode(QAbstractItemView.NoDragDrop)` unconditionally *unless* EVIDENCE MODE is off AND the view is in a "move" workflow.
  - Test: `tests/test_no_drag.py` (pytest-qt) — attempt to drag a row; assert no model mutation.

### U9 — Keyboard-first timeline navigation

> ⏳ Open · 🟢 Low · Effort: S

- **Where.** New timeline view (U3).
- **Why.** Mouse-only navigation induces RSI over a forensic shift;
  keyboard-only scrub (vim-style) is the productivity convention in every
  serious investigative tool.
- **How.** `j`/`k` line, `r` to selection, `g`/`G` end, `/` search, `n`/`N`
  next/prev match, `Enter` open in HexView (U4), `Esc` exit.
  Test: see U3.

### U10 — Marketing / capability parity for `parse_os_artifacts`

> ⏳ Open · 🟡 Medium · Effort: M · Release v0.3.0

- **Where.** `dataforge/modules/forensics.py:121-329` (`parse_os_artifacts`)
  only parses Linux artefacts. README:55 markets OS artifact parsing as
  cross-platform.
- **Why.** A Windows-only customer will get an empty artefact dict and
  conclude the tool does not work. Over-claiming capability is a
  defensible-misrepresentation risk.
- **How.**
  - **Either:** Add Windows registry parsing (`python-registry`), Prefetch (`python-prefetch`), and at least an Amcache reader (`python-amcache`) — even basic versions.
  - **Or:** Update README and CLI reference to say "Linux-only; Windows support is on the roadmap" and emit a `UserWarning` from `parse_os_artifacts` when `platform.system() == "Windows"`.
  - Test: `tests/test_artifact_parity.py` — assert the warning is raised on Windows; assert Linux parsing unchanged.

### U11 — Trash recovery marketing parity

> ⏳ Open · 🟡 Medium · Effort: S · Release v0.2.0

- **Where.** `dataforge/modules/recovery.py:184-196` raises
  `TrashScanUnsupported` on Windows. README:50 markets trash recovery as
  cross-platform.
- **Why.** Customer who buys this expecting Windows Recycle Bin recovery
  has a defensible misrepresentation claim.
- **How.** Either implement Windows Recycle Bin parsing via `pywin32` (parse `$I` files in `$Recycle.Bin/<SID>/` to recover original path + deletion date — the format is documented), or scope the README claim to Linux/macOS today and add an entry to `IMPROVEMENT_PLAN.md` Phase 3.
  Test: `tests/test_windows_recycle.py` — fixture with two `$I`/`$R` pairs, assert restore works.

---

## 5. Sequencing (suggested)

This review is the input to the next revision of [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md).
The suggested ordering — by (impact × cost)^-1 — is:

| Wave | Findings | Target release | Why this order |
| --- | --- | --- | --- |
| 1 (forensic soundness) | F1, F2, F3, F4, F9, F11, F21, U1, U2 | v0.2.0 | Close the disqualifying gaps; everything else is incremental once these land |
| 2 (engine correctness) | F6, F8, F10, F13, F14, F15, F16, F17, F18, F19, F20 (detection half), U5, U6, U7, U8, U11 | v0.2.0–v0.3.0 | Make the engine actually correct before adding new surface |
| 3 (engine growth) | F5, F7, F20 (VSS/raw half), U3, U4, U9, U10 | v0.3.0 | Add raw-image, VSS/locked-file acquisition, YARA/TLsh, and timeline UX — the features that move DataForge from "manager" to "investigative tool" |

These three waves are carried in [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md)
as work-streams **WS-H** (Wave 1, v0.2.0), **WS-I** (Wave 2, v0.3.0), and **WS-J**
(Wave 3, v0.3.0). F1/F3/F6 land on the WS-F service seams (ARCH.5 audit hook,
ARCH.4 root-confinement, ARCH.6 stream carving) rather than duplicating them.

The work-stream model of [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md)
§2 (one PR per stream, alpha tag per stream close, single `develop`→`main`
PR for the release) is preserved. Each finding is one work-stream unless
explicitly grouped above.

---

## 6. Where / Why / How — explicit standard

In line with [`CONTRIBUTING.md` §8](../CONTRIBUTING.md), every finding above
answers:

- **Where** — `path:line` against current source, with a link to legacy
  audit entries where appropriate.
- **Why** — the impact if left unfixed: the risk, defect, or user cost.
  None of the above use "because the review said so."
- **How** — the fix, the seam it lands at (`FileActionService`,
  `core/audit.py`, `CaseContext`, et al.), and the test that proves it.

If a future edit to this document removes or argues against a finding, it
must record the evidence that the finding is now resolved — per
[`CONTRIBUTING.md` §8](../CONTRIBUTING.md).

---

## 7. Out of scope (explicit)

- Re-implementing in a compiled language. The current Python + PyQt5 stack is correct for the stated audience; performance headroom comes from `duckdb`, `pyahocorasick`, and native `yara-python`, not from a rewrite.
- GUI modernisation beyond forensic utility (custom webfont, primary animation framework, video walkthrough, etc.) — already rejected by [`IMPROVEMENT_PLAN.md` §"Explicitly Out of Scope"](./IMPROVEMENT_PLAN.md).
- Cloud or multi-tenant deployment model. DataForge is local-first and
  investigator-individual; this review does not assume or propose a server.
- Workflow orchestration between multiple examiner machines.
- Cross-examining the existing audits beyond their contributions to the
  provenance chain. The [`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md)
  bug-tracking work is closed; only security findings remained open at
  review time.

---

## 8. Cross-references

| Document | Section that links here |
| --- | --- |
| [`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md) | S4–S13 are **fixed in WS-B**; their architectural successors are tracked here as F4 (S6 secure_delete), F11/F1 (S12 report integrity), F12 (S5 plugin isolation), F13 (S13 parser isolation), F19 (S4 restore audit) |
| [`IMPROVEMENT_PLAN.md`](./IMPROVEMENT_PLAN.md) | §1 (cross-cutting architecture), §2.4 (interaction problems — U2, U7 here extend 2c.5), §2.5 (accessibility — U6 here), §3.3/3.4 (iconography + motion — U6 here) |
| [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) | §3–§4, §7 — carries the F1–F21 / U1–U11 work-streams from §5 above as WS-H (v0.2.0), WS-I and WS-J (v0.3.0) |
| [`EXECUTIVE_SUMMARY.md`](./EXECUTIVE_SUMMARY.md) | "Five things that matter most" — items 3 (security), 4 (UX) extended here into forensic-soundness and investigator-UX dimensions |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | §8 (where/why/why/how), §9 (security), §10 (implementation plans) |
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | Extension points: new `core/audit.py`, `core/case.py`, `core/image_io.py`, `core/acquire.py`, `core/parse_worker.py`, `core/streams.py`, `core/dt.py`, `modules/indicators.py`, `modules/sanitisation.py`; new views `ui/views/timeline.py`, new widget `ui/widgets/hexview.py` |
| [`../TECHNICAL_SOURCE_OF_TRUTH.md`](../TECHNICAL_SOURCE_OF_TRUTH.md) | `FileEntry` schema extension (F10, F14, F16); new entries for new modules to be added when work-streams land |
| [`../GUI_WORKFLOWS.md`](../GUI_WORKFLOWS.md) | Built-in views table — add Timeline view row; EVIDENCE MODE chrome row in shell description |

---

**End of review.**
This document is the forensic / security / investigator-UX tracker. It feeds
[`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) and supersedes the
"Forensic-soundness checklist" rows in
[`AUDIT_FINDINGS.md`](./AUDIT_FINDINGS.md) for items it covers (F1–F21). For
item-level commit mapping, version impact, and per-stream sequencing, see
[`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) §3–§4 and §7
(work-streams WS-H / WS-I / WS-J).