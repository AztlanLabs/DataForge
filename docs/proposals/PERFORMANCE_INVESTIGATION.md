# DataForge Performance Investigation — Make It Ridiculously Fast

**Date:** 2026-08-22  
**Scope:** Full-app performance audit. Goal: multithread everywhere it matters + clean backend/API separation so DataForge behaves like a professional forensic tool, not a GUI script.  
> **Status: PROPOSAL — not yet implemented.** This document describes future architecture against `dataforge/` HEAD at 2026-08-22. Current truth lives in `../APP_REFERENCE.md`, `../ARCHITECTURE.md`, and `../TECHNICAL_SOURCE_OF_TRUTH.md`. Do not treat paths, service files, or APIs here as shipped.

**Method:** Source walk of every hot path (`core/scanner.py:22`, `core/hasher.py:8`, `core/cache.py:6`, `modules/duplicates.py:157`, `modules/search.py:217`, `modules/forensics.py:45`, `modules/integrity.py:70`, `modules/recovery.py:312`, `modules/system_cleanup.py:201`, `core/services/file_actions.py:79`, `ui/app.py:114`), plus threading / config / UI-worker mapping. No benchmarks on production data — estimates below are derived from code shape and should be validated with the profiling harness in §7.

---

## 0. TL;DR — Where the Speed Goes Today

| Rank | Bottleneck | Current shape | Cost on “real” data |
|------|------------|---------------|---------------------|
| **1** | **Single-threaded filesystem walk** — `scan_directory()` | Recursive `os.scandir` generator, yields one `FileEntry` at a time. No parallelism, no batching. | Walk of 500k files on SSD: ~25-60s. On HDD/NAS: minutes. Every feature (search, dupes, integrity, forensics, cleanup, dashboard) pays it. |
| **2** | **Hashing** — `get_file_hash()` + callers | 64 KiB blocks, Python loop, `ThreadPool(4)` only for the integer files that survive size grouping. Single SQLite connection serializes every cache write with `commit()` → `fsync`. | Dupes on 100k candidates: 10-20× slower than disk can deliver. Large files (1GB+) hash at ~120 MB/s instead of ~500-800 MB/s. |
| **3** | **Content search** — `SearchQuery._check_content()` + `search_files()` | Opens each file sequentially, reads line-by-line in Python, 10 MB cap, no threads. `keyword_search()` *does* have a thread pool, but Search view does not use it. | `search --content` on 50k files: minutes, mostly Python I/O. |
| **4** | **Batch mutations** — `FileActionService._run_batch_operation()` | Strictly sequential loop, one `shutil.move/copy`/ `send2trash` at a time. | Move/copy/delete of 10k files: linear, UI frozen on worker thread, no I/O overlap. |
| **5** | **Cache + integrity + forensics fan-out** | Collect-all-then-hash, materialize full `list(scan_directory(...))`, store `file_paths: list[str]` in RAM. | 1M-file ingest: OOM risk, double `os.stat`, double memory. |
| **6** | **UI concurrency** | Single `BackgroundWorker(QThread)` + global `is_busy` guard. Second action is dropped with “Busy” message. No queue, no cancellation propagation to ThreadPool children beyond token check. | UX feels single-tasking; can’t scan + preview + hash. |

**Headline fix:** Parallel walk + pipeline (producer → queue → consumer pool) + batched cache writes + larger blocks + parallel mutations + an API service. Each alone is 2-5×; together 10-50× on large corpora.

---

## 1. Current Hot-Path Inventory (with receipts)

### 1.1 Scanner — `core/scanner.py:22`

```python
# current
def scan_directory(root_path, recursive=True, max_depth=-1, cancel_token=None):
    with os.scandir(root_path) as it:
        for entry in it:
            if entry.is_symlink(): continue
            if entry.is_file(follow_symlinks=False):
                yield build_file_entry(entry.path)  # build_file_entry does os.stat(path) again
            elif entry.is_dir(...):
                yield from scan_directory(entry.path, ...)  # recursive generator
```

Problems:
- **Double `stat`.** `DirEntry` already caches `stat` after `is_file()`/`is_dir()` on most platforms, but `build_file_entry` at `core/scanner.py:6` calls `os.stat(path)` unconditionally. That’s 2× syscalls per file. Fix: `entry.stat(follow_symlinks=False)`.
- **Purely sequential.** No parallel descent. Directory tree walk is the only thing that touches the filesystem first — everything downstream blocks on it.
- **Recursive `yield from`.** Python recursion depth + generator delegation adds overhead. Deep trees risk `RecursionError`. No `os.scandir` batching.
- **Exclusion check is string `in` set per entry** — cheap, but `excl_exts` is a `tuple` and `endswith(tuple)` per file adds a Python call. Use pre-lowered set + `os.path.splitext` reuse.
- **No inode/device deduplication.** Hardlinks counted twice; later dedup treats them as separate files then hashes both.
- **No `st_blocks` / sparse awareness.** Large sparse files report `st_size` but hashing reads zeros.

### 1.2 Hasher — `core/hasher.py:8`

```python
BLOCK_SIZE = 65536
hasher.update(f.read(BLOCK_SIZE))  # loop in Python
```

- 64 KiB is small. Modern SSDs like 256 KiB-1 MiB. Each iteration is a Python call + GIL dance. Switch to 1 MiB and `mmap` for files > 16 MiB.
- `hashlib` releases the GIL per `update`, so threads help, but 4 workers is tiny on 12-core host (`os.cpu_count():12`). Default `max_thread_workers=4` at `core/config.py:21` throttles both hashing and integrity.
- No fast pre-filter: dupes could `xxhash64` first 4 KiB in one read, then full `sha256` only on collisions. Would cut hashing volume 70-90%.
- `get_hashes()` reads once for many digests — good, but not used by dupes/integrity (they call `get_file_hash` per file).

### 1.3 Cache — `core/cache.py:6`

```python
self.conn = sqlite3.connect(db_path, check_same_thread=False)
self._lock = threading.Lock()
# get_hash: with lock: SELECT ... WHERE path=? AND size=? AND mtime=? AND algo=?
# set_hash: with lock: INSERT OR REPLACE ...; commit()
```

- Single connection + global lock = serialization. Every `get` and `set` takes the lock. Hash pool of 4 workers contends on one mutex.
- `commit()` per `set_hash` → `fsync` per file. 100k files = 100k fsyncs. Should `executemany` in one transaction and `commit` every N or at end.
- No index on `(algo, size, mtime)` — lookup is PK on `path`, so query with 4 predicates does a PK lookup then filter, but `size/mtime/algo` aren’t indexed for reverse lookups. Add composite index.
- No `PRAGMA synchronous=NORMAL` / `temp_store=MEMORY` / `cache_size`. Default is safe but slow.
- No TTL/eviction — cache grows unbounded.

### 1.4 Duplicates — `modules/duplicates.py:157`

- Phase 1: single-threaded size-group scan (blocks on scanner).
- Phase 2: sequential cache probe loop (`file_cache.get_hash` per entry, each taking lock).
- Phase 3: `ThreadPool(4)` for uncached files only; cached files already grouped. Good, but pool too small, and `file_cache.set_hash` inside loop still serializes.
- Double sort in `order_duplicate_records` when `sort_key` set: first by path, then by key — wasteful.

### 1.5 Search — `modules/search.py:217`

- `iter_search_files` yields from `scan_directory` sequentially, then `query.matches` per file.
- `SearchQuery._check_content` at line 200: `os.path.getsize` + `open(..., 'r', errors='ignore')` line loop + `pattern.search(line)` per line. No `mmap`, no `re` prefilter, no binary skip, sequential only.
- `search_thread_workers` exists in config but search view doesn’t use it. `forensics.keyword_search` *does* use a pool — inconsistency.

### 1.6 Integrity — `modules/integrity.py:70`

- `list(scan_directory(...))` materializes all `FileEntry`s in RAM before hashing. 1M files → ~300 MB of Python objects.
- Hashing pool 4 workers, same issues as dupes.

### 1.7 Forensics — `modules/forensics.py:45`, `431`

- `calculate_hashes` pools correctly but image ingest at `ingest_disk_image` first collects `file_paths = []` via full scan (RAM + double scan for artifacts + keyword search reusing same list).
- `keyword_search` at line 369 *does* use `search_thread_workers` pool and 10 MiB cap — better than search module, but still reads entire file into `content = f.read(10MB)` per file (10 MB × 4 workers = 40 MB resident) with no streaming.
- Timeline `build_timeline` does `os.stat(entry.path)` *again* after `FileEntry` already has `stat` data — double syscall × file count.
- Entropy / stego / hex are single-threaded or per-file loops.

### 1.8 Recovery carving — `modules/recovery.py:312`

- Reads `512+16` bytes per block, checks magic at sector boundary only (misses unaligned headers — `FORENSIC_REVIEW.md: F6`), then `f.read(max_size)` whole file in RAM. Single-threaded, no `mmap`, no parallel signature scan. On 500 GB image → days.

### 1.9 System cleanup — `modules/system_cleanup.py:201`

- Loops categories sequentially, each `scan_directory(..., max_depth=5)`. `_is_socket_or_fifo` does `os.stat` per file again. Browser artifact scan does nested `os.walk` per pattern → O(n²) walks.

### 1.10 Batch file ops — `core/services/file_actions.py:79`

```python
for index, item in enumerate(items, start=1):
    record = operation(item, source_path, index)  # shutil.move/copy, send2trash, zip
    if progress_callback: progress_callback(index, total, ...)
```

- Sequential, no pool. I/O bound — parallelism would help on SSD and across devices. `transfer_path` also does `os.makedirs` + `resolve_collision_path` (which does `os.path.exists` loop) per file, sequentially.

### 1.11 UI worker — `ui/app.py:114`

- One `BackgroundWorker(QThread)` at a time, `is_busy` global guard drops second job. No queue, no executor, no progress multiplexing. `cancel_token` is a `threading.Event` passed to worker, but `ThreadPoolExecutor` children check it only at task start/end — mid-hash cancellation waits until block completes.

---

## 2. What “Ridiculously Fast + Accurate” Means Here

- **Fast:** 1M-file scan in < 10s on NVMe, dupes on 100k files in < 30s, content search 50k files in < 15s, batch move 10k files at storage bandwidth, not Python loop speed.
- **Accurate:** No double-stat skew, mtime/size/algo-qualified cache hits only, `xxhash → sha256` two-phase without collision risk, inode-aware dedup, sparse-aware hashing, deterministic sort, correct cancellation.
- **Professional:** Non-blocking UI, queueable jobs, persistent index, resumable scans, API-consumable backend so CLI / GUI / headless / remote all use same engine.

---

## 3. Architecture — Separate App and Backend, Make the Backend an API

> **Note:** §3’s FastAPI/HTTP sketch is superseded by [`NATIVE_OS_API_REVIEW.md`](./NATIVE_OS_API_REVIEW.md) §2–3, which keeps the app↔engine split but replaces HTTP-as-primary with UDS/Named Pipes + D-Bus/XPC/COM (HTTP stays as remote gateway). Read that next.

### 3.1 Proposed layering

```
┌──────────────┐   ┌──────────────┐   ┌─────────────────────┐
│  DataForge   │   │   fm CLI     │   │  Headless / CI /    │
│  Desktop GUI │   │              │   │  Remote client      │
│  (PyQt5)     │   │              │   │                     │
└──────┬───────┘   └──────┬───────┘   └──────────┬──────────┘
       │                  │                      │
       └──────────────────┼──────────────────────┘
                          │  HTTP / WebSocket / gRPC
                          ▼
               ┌──────────────────────┐
               │  DataForge Engine API │  FastAPI + Uvicorn (or gRPC)
               │  /scan  /search  /dupes  /hash  /integrity
               │  /cleanup /recovery /forensics /jobs/{id}
               │  Auth: token / local-only mode
               └──────────┬───────────┘
                          │
               ┌──────────▼───────────┐
               │   Core Engine lib     │  dataforge/core + dataforge/engine
               │  Scanner (parallel)   │  Hasher (mmap+pool)  Cache (batched)
               │  Search index (Tantivy/SQLite FTS)  Job queue
               └──────────┬───────────┘
                          │
            ┌─────────────┼─────────────┐
            │             │             │
       LocalProvider  SshProvider  S3Provider  (FileProvider ABC)
```

**Why:** Today `provider.py:4` defines `FileProvider` but nothing uses it. Promoting it to the engine boundary lets the same scan/hash/search run on local FS, mounted image, SSH host, or S3 — and lets the API be local (Unix socket) or remote.

### 3.2 Engine API sketch (FastAPI)

Keep it tiny, then grow. All long jobs are async and pollable.

```python
# dataforge/api/main.py
from fastapi import FastAPI, BackgroundTasks
app = FastAPI(title="DataForge Engine", version="0.2.0")

@app.post("/jobs/scan")
def scan(req: ScanRequest):          # → {job_id}
@app.post("/jobs/search")
def search(req: SearchRequest):      # name/ext/size/date/content, streaming results
@app.post("/jobs/dupes")
def dupes(req: DupesRequest):        # size_group → fast_hash → full_hash pipeline
@app.post("/jobs/hash")
def hash_files(req: HashRequest):    # paths + algos, batched, cached
@app.get("/jobs/{job_id}")           # status + progress
@app.get("/jobs/{job_id}/events")    # WebSocket / SSE for progress_callback
@app.get("/jobs/{job_id}/results")   # paginated, JSONL streaming
@app.delete("/jobs/{job_id}")        # cancel via token
@app.post("/batch/move")             # parallel transfer service
```

GUI and CLI become thin clients: GUI subscribes to `events` WebSocket, CLI does `POST /jobs/search` then `GET /results?format=jsonl`.

**Alternative backends:** `FileProvider` implementations share the same `ScanRequest`:
- `LocalProvider` — `os.scandir` + `stat` via `DirEntry.stat()`, `mmap` hashing.
- `SshProvider` — `sftp.listdir` / `stat`, streaming hash over SSH.
- `S3Provider` — `list_objects_v2` pagination, `ETag`/`HeadObject` for size/mtime, `GetObject` range for hashing.
- `ImageProvider` — `pytsk3` / `dissect` over raw/E01/AFF4 (fixes `F5` — currently requires mounted dir, `forensics.py:475`).

### 3.3 Job system

- Replace single `BackgroundWorker` with an **engine-side job queue** (`ThreadPoolExecutor` + `asyncio` or `arq`/`celery` for remote). Each job has `cancel_token: threading.Event` + `progress_callback` that pushes to SSE/WebSocket.
- GUI keeps one `QThread` that tails the event stream, not one that runs the work. Multiple jobs can run; `is_busy` becomes per-job, not global.
- Every job writes to an append-only `jobs` table (SQLite or Postgres for remote) so it’s resumable and auditable (`F1`).

---

## 4. Concrete Multithread / Performance Fixes (prioritized)

### P0 — Must do for 10× (1-2 weeks)

1. **Parallel scanner + DirEntry stat reuse**
   - Replace recursive `yield from scan_directory` with a work-queue BFS: `collections.deque` of dirs, `ThreadPoolExecutor(max_workers = min(32, os.cpu_count()*4))` that `os.scandir`’s each dir and enqueues subdirs. Collect `FileEntry` via `entry.stat(follow_symlinks=False)` — no `build_file_entry` double-stat.
   - Emit in batches (e.g., 1k entries) to a `queue.Queue` for downstream consumers. Add `st_ino`/`st_dev` to `FileEntry` (`core/common.py:6`) for hardlink dedup.
   - Validate with `fio` on 500k files: expect 3-5× over current sequential walk.

2. **Batch cache transactions + larger hash blocks + mmap**
   - `core/cache.py:6`: add `PRAGMA synchronous=NORMAL`, `cache_size=-64000`, composite index `CREATE INDEX IF NOT EXISTS idx_hash_lookup ON file_hashes(algo, size, mtime)`. Replace per-file `commit()` with `executemany` per batch (1k) + single `commit()`. Use per-thread connections or `queue` writer thread.
   - `core/hasher.py:3`: `BLOCK_SIZE = 1<<20` (1 MiB), `mmap.mmap` path for files > 16 MiB, `os.posix_fadvise(..., WILLNEED)` on Linux. Hash still via `hashlib`, just fewer Python iterations. For dupes pre-filter, add `xxhash` (pure-Python fallback) first-4KiB hash via `get_file_hash(..., algo='xxhash')` if lib present.

3. **Pipeline dupes / search / integrity (producer → consumers)**
   - Don’t `list(scan_directory(...))`. Instead: scanner thread(s) → `queue.Queue[FileEntry]` → hasher pool drains it. For dupes: size-map can be updated streaming, then second stage hashes only `len>1` groups. Memory goes from O(n) to O(batch).
   - Apply same to `integrity.create_snapshot` / `verify_snapshot` and `forensics.calculate_hashes`: stream `FileEntry`, hash in pool, `executemany` cache writes.

4. **Parallel batch mutations**
   - `core/services/file_actions.py:79`: add `ThreadPoolExecutor(max_workers = min(16, os.cpu_count()*2))` for `transfer_items` / `delete_items` / `rename_items` / `archive_items` (individual mode). Keep `reserved_paths` protected by a lock, and `resolve_collision_path` thread-safe. For `archive single` mode, still single writer (zip isn’t thread-safe) but hashing/compression can be done per file then written sequentially. Progress via atomic counter.

### P1 — High leverage (2-4 weeks)

5. **Content search parallelism + ripgrep-style skip**
   - `modules/search.py:200`: make `_check_content` use `mmap` + `re` on bytes, skip files with `magic` mime `binary` unless forced, and run it in `ThreadPool(search_thread_workers)`. Unify `search_files` and `forensics.keyword_search` into one engine `Engine.search(paths, query, workers, batch)` so GUI and CLI share the fast path.
   - Add `max_bytes` streaming: read 1 MiB sliding window for regex, not whole file via `open(...).readlines()`.

6. **UI job queue + streaming results**
   - `ui/app.py:789`: replace `is_busy` global with `JobManager { job_id → BackgroundWorker | EngineJob }`, queue depth 8, cancel per job. GUI tables become virtualized (`QTreeView` + `QAbstractItemModel`) so 500k rows don’t allocate 500k `QTreeWidgetItem`s. Results stream via `results` pagination (1k rows) rather than `list(...)` upfront.

7. **Index instead of re-scan**
   - Add `dataforge/engine/index.py` backed by `SQLite FTS5` or `Tantivy` (Rust): on first scan, index `path, filename, ext, size, mtime, magic_type`. Subsequent `search` becomes `SELECT ... WHERE ...` not a walk. Incremental: `watchdog` or `inotify` invalidates changed dirs. Dashboard and cleanup then query the index.

### P2 — Professional-grade (4-8 weeks, unlocks API + remote)

8. **Engine as importable lib + FastAPI service**
   - Extract `dataforge/engine` from `dataforge/core+modules` so `dataforge/api` imports it without Qt. CLI can run `--local` (in-process) or `--engine http://host:8000`. GUI defaults to local Unix socket (`~/.dataforge/engine.sock`) then falls back to in-process if service not running.

9. **Provider-pluggable backends**
   - Finish `core/provider.py:4`: add `stat(path)`, `open(path, 'rb')`, `hash(path, algo)` to `FileProvider`. `LocalProvider` uses `DirEntry.stat()` + `mmap`. `S3Provider` uses `boto3` range GETs. Scanner becomes `provider.list_files_parallel(root)` and hashing becomes `provider.hash_many(paths)`.

10. **Recovery + forensics throughput**
    - `recovery.carve_files_from_image`: `mmap` the image, run signature scan in parallel chunks (e.g., 64 MiB windows with overlap = max header+footer), write carved files to per-worker temp then move. Fixes sector-alignment miss and adds ~8× on large images.
    - `forensics.build_timeline` / `profile_directory_types`: avoid `os.stat` redo, reuse `FileEntry.stat` fields.

### P3 — Polish (nice to have)

- `blake3` crate via `blake3` Python binding for hashing 3-5× faster than `sha256` while still cryptographically strong; keep `sha256` for forensic chain.
- `io_uring` on Linux 5.19+ for carving (fallback to `mmap`).
- Adaptive `max_thread_workers`: `min(32, cpu_count*4)` default, auto-tune from I/O wait (`psutil.disk_io_counters`).
- `send2trash` batching + `gio trash` parallel on Linux.

---

## 5. Config + Cache + Hasher — Exact Edits

**`core/config.py:16`** — change defaults and allow API-owned overrides:
```python
DEFAULT_CONFIG = {
    "max_thread_workers": min(32, (os.cpu_count() or 4) * 4),
    "search_thread_workers": min(32, (os.cpu_count() or 4) * 2),
    "hash_block_size": 1<<20,  # 1 MiB, was implicit 64 KiB
    "cache_batch_size": 1000,
    ...
}
```

**`core/cache.py:6`** — batched writer:
```python
# inside CacheManager
def set_hash_many(self, rows: list[tuple]):  # (path,size,mtime,hash,algo)
    with self._lock:
        self.conn.executemany(
            "INSERT OR REPLACE INTO file_hashes(path,size,mtime,hash,algo) VALUES (?,?,?,?,?)", rows
        )
        self.conn.commit()
```

**`core/hasher.py:8`** — mmap path:
```python
def get_file_hash(path, algo='sha256', cancel_token=None):
    if os.path.getsize(path) > 16<<20:
        with open(path, 'rb') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                # chunked update still, but zero-copy, or single update for small files
```

---

## 6. Accuracy — Don’t Trade Correctness for Speed

- **Two-phase hashing for dupes:** `xxhash64(first 4 KiB) → size group → sha256(full)` keeps accuracy at `sha256` level, skips full read on most non-dupes.
- **Inode deduplication:** group by `(st_dev, st_ino)` before hashing so hardlinks aren’t hashed twice and aren’t presented as “duplicates” of themselves.
- **Sparse handling:** check `st_blocks * 512 < st_size` → hash via `mmap` still reads zeros, but log a `sparse: true` flag so caller can decide to sample.
- **Cache key stays `(path, size, mtime, algo)`** — never `path` alone. Invalidate on `mtime` change.
- **Content search:** binary-aware — `python-magic` quick `mime` before reading; if `text/*` skip is needed, still use bytes regex to avoid decode cost.

---

## 7. How to Prove It — Profiling Harness

Add `scripts/bench.py` (not committed as prod code):

```bash
PYTHONPATH=. .venv/bin/python scripts/bench.py --root ~/corpus --runs 3 \
  --profile scan --profile dupes --profile search-content --profile integrity
```

Each profile:
- `cProfile` + `py-spy` for Python hotspots,
- `iostat`/`pidstat` for disk wait,
- asserts: peak RSS, wall time, result count matches sequential baseline.

Gate: every P0 change must keep result count identical to current single-threaded run on a 100k-file fixture.

---

## 8. Minimal Roadmap (ship order)

| Phase | Ships | Effort | Expected gain |
|-------|-------|--------|---------------|
| **A. Parallel walk + DirEntry stat + batched cache + 1 MiB blocks** | `core/scanner.py`, `core/cache.py`, `core/hasher.py`, `FileEntry` inode fields | S (1 week) | 3-5× scan, 2-3× hash |
| **B. Pipeline dupes/search/integrity + parallel mutations** | `modules/duplicates.py`, `modules/search.py`, `modules/integrity.py`, `core/services/file_actions.py` | M (1-2 weeks) | 5-10× search/content, constant memory |
| **C. UI job queue + virtualized tables** | `ui/app.py`, `ui/views/*` | M (1-2 weeks) | No more “Busy” drops, 500k rows smooth |
| **D. Engine lib + FastAPI + Provider ABC** | `dataforge/engine`, `dataforge/api`, `core/provider.py` | L (2-3 weeks) | Local API, then remote/SSH/S3 backends |
| **E. Index (FTS) + incremental watch + carving parallel** | `engine/index.py`, `modules/recovery.py` | L (2-3 weeks) | Sub-second search after first index |

Phases A+B alone make the app feel “ridiculous fast” on typical 100k-1M file homes. D+E make it a real professional service.

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Thread oversubscription on HDD (thrashing) | Auto-tune workers down when `iowait > 30%`, or single-walk + parallel-hash (not parallel walk) on rotational media (detect via `lsblk --output ROTA`). |
| SQLite contention with many writers | One writer thread + queue; readers use `BEGIN IMMEDIATE` + `WAL`. |
| S3/SSH latency | Batch `stat` via `list_objects_v2` pagination; hash with range GETs and local cache. |
| API auth for forensic chain-of-custody (`F1`) | Local socket is `0700` + `0600` job DB; remote mode adds token + audit log (see `FORENSIC_REVIEW.md: F1`). |
| GIL for `re` on content search | Use `bytes` regex + `mmap` (releases GIL on large buffers) or `hyperscan` binding if needed. |

---

## 10. What to Do Next (today)

1. Land Phase A on a branch, add `scripts/bench.py`, run on a 200k-file fixture and record baseline vs. parallel walk numbers in this doc’s §7.
2. Decide transport: `FastAPI + SSE` is enough for local; add `gRPC` only if you need bidirectional streaming to remote workers.
3. Promote `FileProvider` to engine boundary — one PR that makes `scan_directory` call `provider.list_files_parallel` so backends are swappable before the API lands.

Want me to start Phase A (parallel scanner + batched cache) or scaffold the `dataforge/engine` + `dataforge/api` skeleton first?
