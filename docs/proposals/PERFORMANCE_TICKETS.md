# Performance Tickets — From Investigation to Parallel Execution (Hardened v2)

**Source:** `PERFORMANCE_INVESTIGATION.md` §1 (11 hot paths) + §4 (P0–P3) + §5 exact edits  
**Date:** 2026-08-22 · **Audit:** `../AUDIT_HARDENED_2026-08-22.md` · **Scope:** Performance-only  
**Principles:** Contract-first Wave 0 → disjoint writes per wave → aliases merge into `../PARALLEL_BACKLOG.md` (hardened) — **pick one set per run, never run twins same wave**.

> Each ticket below is 1 agent = 1 PR = 1 merge. Two tickets in the same wave never touch the same file. All `exclusive_write_files` that do not yet exist carry ` [NEW FILE]`.

---

## Map: Investigation → Ticket (Hardened)

| # in doc | Bottleneck (§1) | Fix (§4) | Ticket | Wave | Exclusive file(s) | Merges Into |
|---|---|---|---|---|---|---|
| §5 | Config `max_thread_workers=4` tiny | §5 adaptive `min(32,cpu*4)` | `PERF-100` *(alias)* | 0 | `dataforge/core/config.py` (now part of `TICK-004`) | `TICK-004` — **no separate agent** |
| 1.1 + common | Scanner sequential + double `stat` + FileEntry inode | P0-1 Parallel BFS + `DirEntry.stat` | `PERF-001c` | 0 | `dataforge/core/common.py`, `dataforge/core/provider.py` | `TICK-002` |
| 1.1 | Scanner sequential | P0-1 Parallel BFS | `PERF-101` | 1 | `dataforge/core/scanner.py` | `TICK-102` |
| 1.2 | Hasher 64 KiB, pool 4 | P0-2 1 MiB + `mmap` + `xxhash` prefilter | `PERF-102` | 1 | `dataforge/core/hasher.py` | `TICK-103` |
| 1.3 | Cache 1 fsync/file | P0-2 `executemany` + `PRAGMA`+index | `PERF-103` *(alias)* | 1 | `dataforge/core/cache.py` (impl) | `TICK-104` — **no separate agent** |
| 1.10b | `operations/files.py` O(N²) + `makedirs` before success | P0-4 | `PERF-111` | 1 | `dataforge/core/operations/files.py` | `TICK-105` |
| 1.4–1.6 | Dupes phases block + OOM `list()` | P0-3 Pipelined streaming | `PERF-104` | 1 | `dataforge/modules/duplicates.py` | `TICK-107` |
| 1.5 | Search content sequential | P1-5 `mmap`+pool+shared engine | `PERF-105` | 1 | `dataforge/modules/search.py` | `TICK-106` |
| 1.6 | Integrity `list(scan)` OOM | P0-3 Streaming | `PERF-106` | 1 | `dataforge/modules/integrity.py` | `TICK-108` |
| 1.7 | Forensics fan-out + 10 MB/read + double `stat` | P0-3 + P1-5 shared + F15 | `PERF-107` | 1 | `dataforge/modules/forensics.py` *(first writer; second is TICK-304 Wave 3)* | `TICK-109` |
| 1.8 | Recovery sector-aligned + RAM hog | P2-10 `mmap` chunks | `PERF-108` | 2 | `dataforge/modules/recovery.py` | `TICK-202` |
| 1.9 | Cleanup O(N²) walks + extra `stat` | P2 dedupe walks | `PERF-109` | 2 | `dataforge/modules/system_cleanup.py` | `TICK-203` |
| 1.10 | Batch `FileActionService` sequential | P0-4 ThreadPool | `PERF-110` | 2 | `dataforge/core/services/file_actions.py` | `TICK-201` |
| 1.11 | UI single `BackgroundWorker` + `is_busy` | P1-6 JobManager + virtualization | `PERF-112` | 3 | `dataforge/ui/app.py`, `dataforge/ui/job_manager.py [NEW FILE]` | `TICK-401` |
| — | Index instead of re-scan | P1-7 FTS | `PERF-113` | 3 | `dataforge/engine/index.py [NEW FILE]` | follow-on after `TICK-303` |
| P3 | Polish (`blake3`, `io_uring`, adaptive) | P3 | `PERF-114` | 3 | `dataforge/core/hasher.py` *(sequential after PERF-102)* + `native/Cargo.toml [NEW FILE]` + `native/src/lib.rs [NEW FILE]` | polish follow-on |

**Merge rule:** `PERF-100` and `PERF-103` are aliases merged into `PARALLEL_BACKLOG` Wave 0/1 contracts — **do not assign separate agents** for them. Remaining `PERF-*` are 1:1 aliases to `TICK-*` (same file, same acceptance); pick either ID when assigning but never both.

---

## Concurrency Map — Performance Only (Hardened)

| Wave | Ticket | Target Write Scope | Depends On | Agent | Notes |
|---|---|---|---|---|---|
| **Wave 0 — Contract** | `PERF-001c` | `dataforge/core/common.py` (`st_ino/st_dev/st_blocks`) + `dataforge/core/provider.py` (extend ABC) | None | Interface | `TICK-002` alias; `config.py` adaptive workers are `TICK-004` (no PERF-100 agent) |
| **Wave 1 — Independent hot paths (all parallel, depend only on Wave 0)** | `PERF-101` | `dataforge/core/scanner.py` | `PERF-001c` | Scanner | Only scanner — `common.py` stays Wave 0 |
| Wave 1 | `PERF-102` | `dataforge/core/hasher.py` | `PERF-001c` | Hasher |  |
| Wave 1 | `PERF-111` | `dataforge/core/operations/files.py` | `PERF-001c` | Ops |  |
| Wave 1 | `PERF-104` | `dataforge/modules/duplicates.py` | `PERF-001c` | Dupes | Was `["PERF-101",...]` — corrected to Wave 0 only for DAG (runtime queue order inside wave) |
| Wave 1 | `PERF-105` | `dataforge/modules/search.py` | `PERF-001c` | Search | Was `PERF-101` — corrected |
| Wave 1 | `PERF-106` | `dataforge/modules/integrity.py` | `PERF-001c` | Integrity | Was `PERF-101` — corrected |
| Wave 1 | `PERF-107` | `dataforge/modules/forensics.py` | `PERF-001c` | Forensics | Was `PERF-101` — corrected |
| **Wave 2 — Need Wave 1 outputs** | `PERF-108` | `dataforge/modules/recovery.py` | `PERF-101`, `PERF-102` | Recovery |  |
| Wave 2 | `PERF-109` | `dataforge/modules/system_cleanup.py` | `PERF-101` | Cleanup |  |
| Wave 2 | `PERF-110` | `dataforge/core/services/file_actions.py` | `PERF-111` | Batch | Was `PERF-111, PERF-101` — simplified to direct `PERF-111` |
| **Wave 3 — Consolidation** | `PERF-112` | `dataforge/ui/app.py` + `job_manager.py [NEW FILE]` | `PERF-110` | UI queue |  |
| Wave 3 | `PERF-113` | `dataforge/engine/index.py [NEW FILE]` | `PERF-101`, `PERF-105` | Index | New file, no collision with 112 |
| Wave 3 | `PERF-114` | `native/Cargo.toml [NEW FILE]` + `native/src/lib.rs [NEW FILE]` (+ optional `hasher.py` polish) | `PERF-102` | Polish | Same agent writes both native files + optional hasher polish (sequential after Wave 1) |

**Disjoint guarantee (hardened):** No two Wave 1 tickets share a file — `cache.py` batch is `TICK-104` (not a separate PERF-103 agent), `common.py` is Wave 0 only, `hasher.py` appears Wave 1 (`PERF-102`) and polish Wave 3 (`PERF-114`) sequentially.

---

## Work Packages (performance-only, Hardened)

### PERF-001c — Contract: FileEntry inode fields + FileProvider ABC (alias TICK-002)
```yaml
ticket_id: "PERF-001c"
title: "Expand FileEntry with st_ino/st_dev/st_blocks and FileProvider ABC to 7 methods"
type: "Contract"
execution_wave: 0
depends_on: []
scope:
  domain: "Core / Provider"
  exclusive_write_files:
    - "dataforge/core/common.py"
    - "dataforge/core/provider.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.1"
architectural_context:
  existing_symbols_to_use:
    - "FileEntry dataclass (dataforge/core/common.py:5)"
    - "FileProvider ABC + LocalProvider (dataforge/core/provider.py:4)"
  breaking_changes: "Additive — new fields default 0, new ABC methods have shim defaults"
requirements:
  summary: "Add st_ino: int=0, st_dev: int=0, st_blocks: int=0 to FileEntry; expand FileProvider to list_files, list_files_parallel, stat, open, hash, hash_many, exists with cancel_token/progress_callback."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN FileEntry with st_ino/st_dev WHEN compared THEN hardlink-equal entries share same pair"
    - "GIVEN LocalProvider() WHEN isinstance check THEN all 7 methods implementable"
    - "GIVEN scan_directory without provider WHEN called THEN defaults to LocalProvider"
verification:
  test_target: "tests/test_provider_contract.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_provider_contract.py -q"
```

### PERF-101 — Parallel scanner + DirEntry.stat reuse (alias TICK-102)
```yaml
ticket_id: "PERF-101"
title: "Replace recursive scanner with parallel BFS + DirEntry.stat + batch queue"
type: "Feature"
execution_wave: 1
depends_on: ["PERF-001c"]
scope:
  domain: "Core / Scanner"
  exclusive_write_files:
    - "dataforge/core/scanner.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.1"
    - "dataforge/core/common.py"  # st_* fields from PERF-001c
architectural_context:
  existing_symbols_to_use:
    - "FileEntry with st_ino/st_dev/st_blocks (from PERF-001c)"
    - "scan_directory(root_path, recursive, max_depth, cancel_token) generator"
  breaking_changes: "None — same signature"
requirements:
  summary: "BFS work-queue with ThreadPoolExecutor(min(32,cpu*4)) over os.scandir; build FileEntry from entry.stat(follow_symlinks=False) (no double-stat); batch emit via queue.Queue; keep excluded_folders/extensions, max_depth, cancel_token. Alias to TICK-102."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN 500k files WHEN scanning THEN 3-5× faster and syscall count halved vs HEAD"
    - "GIVEN hardlinks WHEN scanned THEN entries share (st_dev,st_ino)"
    - "GIVEN cancel_token.set() mid-walk THEN stops promptly"
verification:
  test_target: "tests/test_scanner_parallel.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_scanner_parallel.py -q"
```

### PERF-102 — mmap hasher + 1 MiB blocks + xxhash prefilter (alias TICK-103)
```yaml
ticket_id: "PERF-102"
title: "Switch hasher to 1 MiB blocks + mmap for large files + xxhash fast prefilter"
type: "Feature"
execution_wave: 1
depends_on: ["PERF-001c"]
scope:
  domain: "Core / Hasher"
  exclusive_write_files:
    - "dataforge/core/hasher.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.2"
architectural_context:
  existing_symbols_to_use:
    - "SUPPORTED_ALGORITHMS, BLOCK_SIZE, get_file_hash, get_hashes (dataforge/core/hasher.py)"
  breaking_changes: "None — same API"
requirements:
  summary: "BLOCK_SIZE=1<<20 (from config hash_block_size via TICK-004), mmap for files >16 MiB + posix_fadvise(WILLNEED), keep SUPPORTED_ALGORITHMS and cancel_token per chunk, add xxhash64(first 4KiB) helper for dupes prefilter (fallback to hashlib if xxhash absent). Alias to TICK-103."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN 1 GiB file WHEN hashed THEN ≥400 MB/s on SSD and cancel aborts mid-file"
    - "GIVEN get_hashes(['md5','sha256']) WHEN called THEN single read, both digests match separate get_file_hash"
    - "GIVEN xxhash available WHEN dupes prefilter THEN first-4KiB hash via xxhash"
verification:
  test_target: "tests/test_hasher_mmap.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_hasher_mmap.py -q"
```

### PERF-111 — Primitives: O(N²) + makedirs before success + case-only (alias TICK-105)
```yaml
ticket_id: "PERF-111"
title: "Fix operations primitives for perf + correctness"
type: "Bugfix"
execution_wave: 1
depends_on: ["PERF-001c"]
scope:
  domain: "Core / Operations"
  exclusive_write_files:
    - "dataforge/core/operations/files.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.10"
    - "docs/reviews/AUDIT_REPORT.md"
architectural_context:
  existing_symbols_to_use:
    - "normalize_path, resolve_collision_path, transfer_path (dataforge/core/operations/files.py)"
  breaking_changes: "None"
requirements:
  summary: "Pre-normalize reserved_paths once per batch, lazy makedirs only on first success, normcase check for case-only rename. Alias to TICK-105."
  source_documents:
    - "docs/reviews/AUDIT_REPORT.md"
  acceptance_criteria:
    - "GIVEN 5k move WHEN profiled THEN normalize_path O(N) not O(N²)"
    - "GIVEN all transfers fail THEN no empty dest dir left"
    - "GIVEN FOO.txt→foo.txt on case-insensitive FS THEN foo.txt not foo_1.txt"
verification:
  test_target: "tests/test_operations_collision.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_operations_collision.py -q"
```

### PERF-104 — Pipelined duplicates (streaming, no list) (alias TICK-107)
```yaml
ticket_id: "PERF-104"
title: "Pipeline dupes: size-map streaming → xxhash → sha256 only on collisions + verify"
type: "Feature"
execution_wave: 1
depends_on: ["PERF-001c"]
scope:
  domain: "Modules / Duplicates"
  exclusive_write_files:
    - "dataforge/modules/duplicates.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.4"
architectural_context:
  existing_symbols_to_use:
    - "find_duplicates, build_duplicate_records (dataforge/modules/duplicates.py)"
  breaking_changes: "None"
requirements:
  summary: "Don't list(scan_directory); scanner → queue → streaming size-map → xxhash64(4KiB) prefilter → full sha256 only on same-xxhash+size collisions via ThreadPool(min(32,cpu*4)); verify_content byte-compare; fix double sort. Alias to TICK-107."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN 100k files WHEN find_duplicates THEN peak RSS O(batch) not O(n) and list(scan) absent from code"
    - "GIVEN same-size+same-xxhash but different sha256 WHEN grouped THEN not duplicates"
    - "GIVEN hardlink (st_dev,st_ino) equal WHEN grouped THEN counted once"
verification:
  test_target: "tests/test_dupes_pipeline.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_dupes_pipeline.py -q"
```

### PERF-105 — Parallel content search via mmap (alias TICK-106)
```yaml
ticket_id: "PERF-105"
title: "Make search content path parallel, mmap-based, shared with forensics"
type: "Feature"
execution_wave: 1
depends_on: ["PERF-001c"]
scope:
  domain: "Modules / Search"
  exclusive_write_files:
    - "dataforge/modules/search.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.5"
architectural_context:
  existing_symbols_to_use:
    - "SearchQuery, iter_search_files (dataforge/modules/search.py)"
  breaking_changes: "None"
requirements:
  summary: "Unify search_files and forensics.keyword_search: mmap + bytes regex, magic mime binary skip unless --force-binary, ThreadPool(search_thread_workers), 1 MiB sliding window (10 MB cap), no open().readlines(). Alias to TICK-106."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN 50k files WHEN --content search THEN minutes→seconds and RSS <200 MB"
    - "GIVEN binary file WHEN without --force-binary THEN skipped"
    - "GIVEN --error-format json with invalid glob+regex WHEN run THEN stderr JSON exit 2"
verification:
  test_target: "tests/test_search_streaming.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_search_streaming.py -q"
```

### PERF-106 — Streaming integrity (no materialize) (alias TICK-108)
```yaml
ticket_id: "PERF-106"
title: "Stream integrity create/verify atomically"
type: "Feature"
execution_wave: 1
depends_on: ["PERF-001c"]
scope:
  domain: "Modules / Integrity"
  exclusive_write_files:
    - "dataforge/modules/integrity.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.6"
architectural_context:
  existing_symbols_to_use:
    - "IntegrityMonitor.create_snapshot, verify_snapshot"
  breaking_changes: "None"
requirements:
  summary: "Replace list(scan_directory) with streaming scan → queue → ThreadPool hash → executemany cache → tmp+os.replace atomic snapshot.json. Alias to TICK-108."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN 1M files WHEN create_snapshot THEN RSS O(batch) and snapshot tmp→replace is atomic"
    - "GIVEN legacy flat MD5 WHEN verify THEN still readable"
    - "GIVEN cancel mid-verify THEN returns cancelled promptly"
verification:
  test_target: "tests/test_integrity_streaming.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_integrity_streaming.py -q"
```

### PERF-107 — Forensics streaming + byte budget + no double stat (alias TICK-109)
```yaml
ticket_id: "PERF-107"
title: "Make forensics hash/keyword/timeline share streaming engine"
type: "Feature"
execution_wave: 1
depends_on: ["PERF-001c"]
scope:
  domain: "Modules / Forensics"
  exclusive_write_files:
    - "dataforge/modules/forensics.py"  # first writer
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.7"
architectural_context:
  existing_symbols_to_use:
    - "calculate_hashes, keyword_search, build_timeline"
  breaking_changes: "None — first writer; second is TICK-304 Wave 3"
requirements:
  summary: "Reuse mmap hasher; keyword_search with global byte budget; ingest_disk_image streams queue to hash+artifacts+keyword (no file_paths list); build_timeline reuses FileEntry timestamps. Alias to TICK-109."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN 4 workers WHEN keyword_search THEN RSS <100 MB"
    - "GIVEN ingest WHEN run THEN no file_paths list in code"
    - "GIVEN timeline WHEN run THEN no second os.stat per file"
verification:
  test_target: "tests/test_forensics_streaming.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_forensics_streaming.py -q"
```

### PERF-108 — Parallel carving via mmap chunks (alias TICK-202)
```yaml
ticket_id: "PERF-108"
title: "Parallelize carving: mmap image, sliding-window scan, chunked workers"
type: "Feature"
execution_wave: 2
depends_on: ["PERF-101", "PERF-102"]
scope:
  domain: "Modules / Recovery"
  exclusive_write_files:
    - "dataforge/modules/recovery.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.8"
    - "docs/reviews/FORENSIC_REVIEW.md"
architectural_context:
  existing_symbols_to_use:
    - "carve_files_from_image (dataforge/modules/recovery.py:312)"
  breaking_changes: "None — fixes F6 sector-alignment"
requirements:
  summary: "mmap image, 64 MiB windows with overlap=max(header+footer), parallel signature scan, per-worker temp then atomic move. Alias to TICK-202."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN header at non-%512 offset WHEN carved THEN found"
    - "GIVEN 500 GB image WHEN carved THEN days→hours with same carved count as single-thread"
    - "GIVEN cancel WHEN set THEN no partial carved file left"
verification:
  test_target: "tests/test_recovery_parallel.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_recovery_parallel.py -q"
```

### PERF-109 — Cleanup dedup walks (alias TICK-203)
```yaml
ticket_id: "PERF-109"
title: "Dedupe cleanup walks and reuse parallel scanner"
type: "Feature"
execution_wave: 2
depends_on: ["PERF-101"]
scope:
  domain: "Modules / System Cleanup"
  exclusive_write_files:
    - "dataforge/modules/system_cleanup.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.9"
architectural_context:
  existing_symbols_to_use:
    - "scan_junk_files, scan_browser_artifacts"
  breaking_changes: "None"
requirements:
  summary: "One scan_directory per category (max_depth=5) reused, not per-pattern os.walk; socket/FIFO via DirEntry without extra stat; keep /tmp 1-day guard and non-blanket user path. Alias to TICK-203."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN cleanup scan WHEN counted THEN os.walk calls O(categories) not O(categories×patterns)"
    - "GIVEN /tmp file <1 day WHEN scanned THEN not junk"
    - "GIVEN socket/FIFO WHEN scanned THEN never junk"
verification:
  test_target: "tests/test_system_cleanup_walks.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_system_cleanup_walks.py -q"
```

### PERF-110 — Parallel batch mutations (alias TICK-201)
```yaml
ticket_id: "PERF-110"
title: "Parallelize FileActionService transfers"
type: "Feature"
execution_wave: 2
depends_on: ["PERF-111"]
scope:
  domain: "Service / Batch"
  exclusive_write_files:
    - "dataforge/core/services/file_actions.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.10"
architectural_context:
  existing_symbols_to_use:
    - "FileActionService._run_batch_operation, transfer_items"
  breaking_changes: "None"
requirements:
  summary: "ThreadPool(min(16,cpu*2)) for transfer/delete/rename/individual-zip with lock-protected reserved_paths and thread-safe resolve_collision_path; archive single stays single writer but per-file hash/compress then sequential write; progress via atomic counter. Alias to TICK-201."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN 10k-file move WHEN run THEN tracks storage bandwidth not Python loop, reserved_paths thread-safe"
    - "GIVEN single-mode zip with 1 bad file WHEN run THEN others still get records, no partial orphan"
    - "GIVEN cancel mid-batch THEN returns cancelled with partial records"
verification:
  test_target: "tests/test_file_actions_parallel.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_file_actions_parallel.py -q"
```

### PERF-112 — UI job queue + virtualization (alias TICK-401)
```yaml
ticket_id: "PERF-112"
title: "Replace is_busy with JobManager + virtualized tables"
type: "Integration"
execution_wave: 3
depends_on: ["PERF-110"]
scope:
  domain: "UI / Shell"
  exclusive_write_files:
    - "dataforge/ui/app.py"
    - "dataforge/ui/job_manager.py [NEW FILE]"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.11"
architectural_context:
  existing_symbols_to_use:
    - "DataForgeApp.is_busy, BackgroundWorker(QThread) (dataforge/ui/app.py:114,186)"
  breaking_changes: "None — same progress_callback shape"
requirements:
  summary: "JobManager {job_id→Job} queue depth 8 per-job cancel, QTreeView+QAbstractItemModel for Search/Dupes (no 500k QTreeWidgetItem), job.events→progress_signal bridge. Sole writer to ui/app.py this wave. Alias to TICK-401."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN two run_workflow WHEN second issued THEN not dropped 'Busy' — queued"
    - "GIVEN 500k rows WHEN rendered THEN RSS <500 MB and scroll smooth"
    - "GIVEN Evidence Mode WHEN destructive clicked THEN disabled + 'EVIDENCE MODE — writes blocked'"
verification:
  test_target: "tests/test_ui_job_manager.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_ui_job_manager.py -q"
```

### PERF-113 — Index instead of re-scan (FTS)
```yaml
ticket_id: "PERF-113"
title: "Add engine index (SQLite FTS5/Tantivy) for sub-second search"
type: "Feature"
execution_wave: 3
depends_on: ["PERF-101", "PERF-105"]
scope:
  domain: "Engine / Index"
  exclusive_write_files:
    - "dataforge/engine/index.py [NEW FILE]"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#4-P1-7"
architectural_context:
  existing_symbols_to_use:
    - "scan_directory, FileEntry"
    - "SearchQuery"
  breaking_changes: "None — new file; search falls back to walk if index absent"
requirements:
  summary: "On first scan index path/filename/ext/size/mtime/magic; later search becomes SELECT not walk; incremental via watchdog/inotify. New file, no conflict with other Wave 3 tickets (112 writes app.py, 114 writes hasher/native)."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN first scan WHEN done THEN SELECT 'pdf' returns <100 ms vs walk"
    - "GIVEN file changed WHEN watched THEN index invalidates that dir"
    - "GIVEN 1M index WHEN searched THEN result count == walk count"
verification:
  test_target: "tests/test_engine_index.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_engine_index.py -q"
```

### PERF-114 — Polish: blake3/xxhash + io_uring + adaptive workers
```yaml
ticket_id: "PERF-114"
title: "Polish: blake3/xxhash, io_uring, adaptive pool, send2trash batching"
type: "Feature"
execution_wave: 3
depends_on: ["PERF-102"]
scope:
  domain: "Engine / Native"
  exclusive_write_files:
    - "native/Cargo.toml [NEW FILE]"
    - "native/src/lib.rs [NEW FILE]"
    - "dataforge/core/hasher.py"  # polish pass — sequential after PERF-102 Wave 1
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#P3"
architectural_context:
  existing_symbols_to_use:
    - "get_file_hash, SUPPORTED_ALGORITHMS (dataforge/core/hasher.py)"
  breaking_changes: "None — optional blake3 binding with hashlib fallback"
requirements:
  summary: "Optional blake3 binding (keep sha256 for forensic chain), io_uring for carving fallback to mmap, adaptive max_thread_workers=min(32,cpu*4) auto-tune via iowait, gio trash parallel. Same agent writes native crate + optional hasher polish (sequential after Wave 1, no intra-wave collision)."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN blake3 available WHEN hashing THEN 3-5× vs sha256 and forensic chain still sha256"
    - "GIVEN HDD with iowait>30% WHEN scanning THEN workers auto-tune down (no thrash via lsblk ROTA)"
    - "GIVEN blake3 absent WHEN hashing THEN fallback to hashlib still passes"
verification:
  test_target: "tests/test_hasher_blake3.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_hasher_blake3.py -q"
```

---

## How to run (Hardened)

- **Wave 0:** land `PERF-001c` (alias `TICK-002`) + `TICK-004` (includes `PERF-100` adaptive workers) + `TICK-001/003/005` (3 days) — unblocks everything. No two Wave 0 tickets share a file.
- **Wave 1:** 7 agents in parallel on `PERF-101/102/111/104/105/106/107` (no file overlap; `cache.py` impl is `TICK-104` not `PERF-103` separate). Each PR must keep `python -m pytest` result count == baseline.
- **Wave 2:** `108/109/110` (`PERF-108/109/110`) after Wave 1 merges.
- **Wave 3:** `112/113/114` (`PERF-112/113/114`) consolidation (single-writer `ui/app.py` via `PERF-112`).
- **Rule:** Do not run `PERF-100` separate from `TICK-004` nor `PERF-103` separate from `TICK-104` — they are the same file.

All IDs merge 1:1 into `../PARALLEL_BACKLOG.md` hardened `TICK-*` — pick either set when assigning; do not run both a `PERF-*` and its `TICK-*` twin in the same wave (they write the same file).

---

## How to Work Performance Tickets — Sequential and Parallel Guide

> **Pick one ID set per execution:** either `PERF-*` *or* hardened `TICK-*` twins — never both. This file’s `PERF-*` are performance-only aliases; full gates live in `../PARALLEL_BACKLOG.md`. Read `../../CONTRIBUTING.md` §10 and `.github/workflows/sdlc-parallel.workflow.md` before starting.

### One ticket, one branch

```bash
git checkout develop && git pull origin develop
git checkout -b perf/PERF-102-mmap-hasher
# — edit only exclusive_write_files for this ticket —
PYTHONPATH=. python -m pytest tests/test_hasher_mmap.py -q
PYTHONPATH=. python -m pytest -q   # full suite before push
git add dataforge/core/hasher.py tests/test_hasher_mmap.py
git commit -m "perf(core): switch hasher to 1 MiB mmap blocks"
```

### File ownership (parallel safety)

- `PERF-100` and `PERF-103` are **aliases only** — no separate branch. `PERF-100`’s adaptive workers live in `TICK-004` (`config.py`), `PERF-103`’s batch cache lives in `TICK-104` (`cache.py`). Creating a branch for them would collide same-wave on `config.py`/`cache.py`.
- All other `PERF-*` have disjoint `exclusive_write_files` **within the same wave** (Wave 1: `scanner.py`, `hasher.py`, `operations/files.py`, `duplicates.py`, `search.py`, `integrity.py`, `forensics.py` are seven different files — 7 agents can run concurrently).
- New files carry ` [NEW FILE]` — create parent dir first.

### Sequential vs parallel

- **Sequential (default):** Wave 0 contracts (`PERF-001c`) → Wave 1 (7 perf tickets in parallel is safe, but still after Wave 0) → Wave 2 → Wave 3. Respect `depends_on` (Wave 0 contracts before Wave 1 consumers).
- **Parallel within a wave:** All Wave 1 `PERF-*` can run concurrently because their exclusive files are disjoint. Rebase before push (`git rebase origin/develop`), keep CI gate `.github/workflows/ci.yml` green before next wave. If two agents need same file (`hasher.py` in Wave 1 `PERF-102` vs polish `PERF-114` Wave 3), they are **different waves → sequential**.

See `../PARALLEL_BACKLOG.md#how-to-work-a-ticket--sequential-and-parallel-execution-guide` for the full wave DAG, verification checklist, and `.sdlc/` handoff rules.
