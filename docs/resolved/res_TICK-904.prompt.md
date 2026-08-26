# Ticket TICK-904 — Duplicate finder SIGSEGV hashing

> **Wave 9** | **Domain:** Modules / Duplicates | **Depends on:** None
> **Source:** user report `Duplicate finder when run scan crashes 2026-08-22 21:56:00,233 Scanned 493 files. Analyzing potential duplicates... Hashing 33 new files... fish: Job 1 terminated by signal SIGSEGV` + `dataforge/modules/duplicates.py:223 find_duplicates` + `dataforge/core/hasher.py:1`

---

## Your Assignment

```
TICKET_ID: TICK-904
WAVE: 9
TITLE: Duplicate finder SIGSEGV hashing
```

**Exclusive write files (SOLE writer for Wave 9):**
- `dataforge/modules/duplicates.py`
- `dataforge/core/hasher.py`

**Read-only references (do not edit):**
- `dataforge/core/cache.py`
- `dataforge/core/scanner.py`
- `dataforge/core/common.py`
- `dataforge/ui/job_manager.py`
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

**Test target:** `tests/test_duplicates_stability.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_duplicates_stability.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` Duplicate Finder section
- `docs/ARCHITECTURE.md` §Duplicates / §Hasher / §Cache
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `modules/duplicates.py`, `core/hasher.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-904"
title: "Duplicate finder SIGSEGV hashing"
type: "Bugfix"
execution_wave: 9
depends_on: []
scope:
  domain: "Modules / Duplicates"
  exclusive_write_files:
    - "dataforge/modules/duplicates.py"
    - "dataforge/core/hasher.py"
  read_only_references:
    - "dataforge/core/cache.py"
    - "dataforge/core/scanner.py"
    - "dataforge/core/common.py"
    - "dataforge/ui/job_manager.py"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
architectural_context:
  existing_symbols_to_use:
    - "duplicates.py: find_duplicates, _fast_hash, _hash_worker, _get_max_workers, find_duplicates progress_callback cancel_token"
    - "hasher.py: get_file_hash, get_hashes, _get_block_size, mmap, posix_fadvise, cancel_token"
    - "cache.py: file_cache.get_hash/set_hash/set_hash_many (read-only here)"
    - "scanner.py: scan_directory generator queue BFS"
    - "job_manager.py: ManagedWorker cancel_token injection"
  breaking_changes: "None — hardening, no API break"
requirements:
  summary: |
    Duplicate finder crashes deterministically after scanning 493 files and hashing 33 new files: SIGSEGV.

    Suspects:

    * duplicates.py find_duplicates uses unbounded ThreadPoolExecutor(max_workers=min(32,cpu*4)) for two stages (fast_hash + full hash) while also holding a queue.Queue entry_queue and dicts size_map/sparse_size_map that are mutated without lock. But that is main-thread only, so not race. However _hash_worker calls get_file_hash which in hasher.py uses mmap.mmap + posix_fadvise and reads 1 MiB blocks via config hash_block_size. hasher.py get_file_hash does `mmap.mmap(f.fileno(), ...)` without handling zero-length or short files, and without closing mmap on cancel. If file is truncated/deleted between scan and hash (race), mmap may SIGSEGV (MAP_SHARED vs file size mismatch). Also hasher does not check cancel_token before mmap, so if job cancelled mid-hash, the QThread is terminated while mmap still mapped → SIGSEGV in C.

    * duplicates.py _fast_hash reads first 4KiB without try for permission, and uses filecmp.cmp fallback which does blocking IO on main thread.

    * duplicates.py cache batch: `pending_rows` is flushed via file_cache.set_hash_many inside ThreadPool as_completed loop. file_cache.set_hash_many uses sqlite3 executemany with check_same_thread=False but single connection + RLock. However _flush_batch_locked is not used there; direct executemany while another thread's get_hash holds lock can cause sqlite3 SIGSEGV (SQLite not fully thread-safe with single connection + busy_timeout? The lock is RLock but executemany releases GIL and may still corrupt if connection is used from multiple threads concurrently via ThreadPool callbacks that also call get_hash for cache probe stage). The log "Hashing 33 new files..." suggests crash during that stage (full hash + batch insert).

    * hasher.py uses `Image.MAX_IMAGE_PIXELS` style global but not related. More relevant: `open(path, 'rb') as f: mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)` — if file size is 0, mmap fails with OSError but not caught, bubble causes worker thread exception not normalized to cancelled dict, then JobManager treats as error_signal -> maybe not crash. But SIGSEGV suggests C-level fault, not Python exception.

    * Scanner provides FileEntry.size from DirEntry.stat at scan time; if file grows/shrinks before hash, hasher reads stale size vs actual file size, causing mmap length mismatch? Should re-stat before mmap.

    Fix:

    * hasher.py: harden get_file_hash/get_hashes: before mmap, do `os.path.getsize` + `os.stat` to verify file still exists and is regular file (`S_ISREG`). If size 0, return hash of empty via hashlib directly (no mmap). For size > MMAP_THRESHOLD (16MiB), mmap with `length=0` only if size>0, wrap in try/except OSError -> fallback to buffered read. Ensure mmap closed via `with mmap.mmap(...) as mm` context manager (Python 3.8+ supports) or try/finally mm.close(). Check cancel_token before mmap and per 1MiB chunk; if set, close mmap and raise InterruptedError. Use `os.posix_fadvise` only if available and fd valid. Avoid `file.read` + `mmap` double open.

    * duplicates.py: harden _fast_hash to open with try, read 4096 buffered, not rely on mmap, and handle OSError -> return None (skip). Make _hash_worker call get_file_hash inside try/except and return None on error, not propagate.

    * duplicates.py find_duplicates: serialize cache access: do not call file_cache.get_hash inside ThreadPool submission loop concurrently with set_hash_many flush from same pool. Instead, do cache probe sequentially before ThreadPool, or protect with same RLock but ensure no concurrent readers during bulk insert. Simplest: before Stage 3, collect `files_to_hash` via sequential cache_probe loop (already sequential), then Stage 3 only hashes not-cached files and batches results into pending_rows but flush only after ThreadPool completes (deferred flush), or flush inside lock but not during get_hash. Change to: accumulate pending_rows in main thread after each future.result, then after loop, single set_hash_many call. Remove per-batch flush inside pool.

    * Add cancel_token checks before each queue drain and before each ThreadPool submit, and ensure executor.shutdown(cancel_futures=True) on cancel.

    * Ensure filecmp.cmp verify_content path is only run when verify_content=True and handle OSError gracefully.

    * hasher.py: add `try: import xxhash` fast path already, but ensure fallback blake2b not called on SIGSEGV.

    Keep streaming size_map via queue.Queue and sparse handling intact.

  source_documents:
    - "docs/GUI_WORKFLOWS.md"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
    - "dataforge/modules/duplicates.py:223"
    - "dataforge/core/hasher.py:1"
  acceptance_criteria:
    - "GIVEN 500-file fixture with 33 uncached duplicates WHEN find_duplicates called via run_workflow THEN no SIGSEGV, returns dict and logs 'Hashing N new files...' without crash, verified via PYTHONPATH=. pytest -q (no segfault)"
    - "GIVEN find_duplicates with cancel_token set after 10 hashes WHEN running THEN raises InterruptedError or returns cancelled flag quickly, no SIGSEGV, no lingering threads"
    - "GIVEN hasher get_file_hash on 0-byte file WHEN called THEN returns hash of empty (not mmap attempt) and does not SIGSEGV"
    - "GIVEN file deleted between scan and hash WHEN hashed THEN _fast_hash returns None and find_duplicates skips without crash"
    - "GIVEN 4 concurrent ThreadPool workers hashing + cache batch WHEN run 3 times THEN no sqlite3 'database is locked' and no SIGSEGV, file_cache consistent"
verification:
  test_target: "tests/test_duplicates_stability.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_duplicates_stability.py -q"
```

---

## Implementation Notes

```python
# hasher.py — harden mmap path
def get_file_hash(filepath, algo='md5', cancel_token=None):
    if cancel_token and cancel_token.is_set(): raise InterruptedError("cancelled")
    try:
        st = os.stat(filepath)
        if not stat.S_ISREG(st.st_mode): raise OSError("not regular file")
        size = st.st_size
        if size == 0:
            h = hashlib.new(algo); return h.hexdigest()
        if size > 16*1024*1024:
            with open(filepath, 'rb') as f:
                if cancel_token and cancel_token.is_set(): raise InterruptedError
                try:
                    with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                        # chunked hash with cancel checks
                        ...
                except OSError:
                    # fallback to buffered read
                    f.seek(0); while chunk := f.read(1<<20): ...
    except OSError as e:
        logger.debug(f"hash OSError {filepath}: {e}"); return None

# duplicates.py — defer batch flush
pending_rows = []
with ThreadPoolExecutor(...) as ex:
    futures = {ex.submit(_hash_worker, e.path, ...): e for e in files_to_hash}
    for fut in as_completed(futures):
        if cancel_token and cancel_token.is_set(): ex.shutdown(cancel_futures=True); raise InterruptedError
        _path, h = fut.result()
        if h:
            hash_map[h].append(entry)
            pending_rows.append((...))
# single flush after pool
if pending_rows:
    file_cache.set_hash_many(pending_rows)
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-904` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-904
WAVE: 9
```

## Required Reading (in order)

1. `docs/CONSOLIDATED_SPEC.md` §2–7
2. `docs/PARALLEL_BACKLOG.md` Concurrency Map + How to Work a Ticket
3. `docs/CONTRIBUTING.md` §3, §8, §10
4. Your Work Package YAML above
5. `read_only_references` files

## File Ownership

- Write only to `exclusive_write_files`. New files carry ` [NEW FILE]`.
- Central touchpoints are single-writer per wave.

## Workflow

```bash
git checkout develop && git pull origin develop
git checkout -b fix/TICK-904-duplicates-sigsegv
PYTHONPATH=. python -m pytest tests/test_duplicates_stability.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add dataforge/modules/duplicates.py dataforge/core/hasher.py tests/test_duplicates_stability.py
git commit -m "fix(modules): duplicate finder SIGSEGV hashing hardening"
git push -u origin fix/TICK-904-duplicates-sigsegv
```

## Work Package YAML for TICK-904

```yaml
ticket_id: "TICK-904"
title: "Duplicate finder SIGSEGV hashing"
type: "Bugfix"
execution_wave: 9
depends_on: []
scope:
  domain: "Modules / Duplicates"
  exclusive_write_files:
    - "dataforge/modules/duplicates.py"
    - "dataforge/core/hasher.py"
  read_only_references:
    - "dataforge/core/cache.py"
architectural_context:
  existing_symbols_to_use:
    - "duplicates.py: find_duplicates"
  breaking_changes: "None"
requirements:
  summary: "Fix duplicate finder SIGSEGV at Hashing 33"
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN 500 files THEN no SIGSEGV"
verification:
  test_target: "tests/test_duplicates_stability.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_duplicates_stability.py -q"
```
