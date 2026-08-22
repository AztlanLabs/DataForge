# Parallel Agent Work Backlog — DAG for Multiple Autonomous Agents (Hardened v2)

**Date:** 2026-08-22 · **Audit:** `docs/AUDIT_HARDENED_2026-08-22.md` · **Source docs:** `CONSOLIDATED_SPEC.md` + `reviews/{AUDIT_REPORT,FORENSIC_REVIEW,ROADMAP}` + `proposals/{PERFORMANCE,NATIVE_OS_API,INSTALL_UPGRADE}`  
**Repo:** `dataforge/` HEAD at v0.1.0 (Python 3.10+, PyQt5, Click, SQLite WAL)  
**Toolchain:** `pytest` (`requirements-dev.txt:4`), `pytest-cov`, `ruff`, `mypy` — all `validation_command` are `pytest`-based.  
**Principles enforced:** Contract-first (Wave 0) → disjoint writes per wave (no file appears twice in same wave) → sequential re-entries documented → consolidation isolates central touchpoints.

> **Wave Status — Updated 2026-08-22 18:30 UTC — Wave 0 ✅ 5/5, Wave 1 ✅ 9/9, Wave 2 🔜 3/5 DONE**
> - **Wave 0 (Contracts): 5/5 DONE — 69 tests.** Unblocks Wave 1.
> - **Wave 1 (Parallel Fixes): 9/9 DONE — 126 tests.** Unblocks Wave 2.
> - **Wave 2 (Service & Mutations): 3/5 DONE, 2 remaining — 🔜 IN PROGRESS (59 tests).** `TICK-202`, `TICK-204`, `TICK-205` verified (see Wave 2 Review). Remaining 2 tickets (`TICK-201` `file_actions.py`, `TICK-203` `system_cleanup.py`) disjoint and ready.
> - **Wave 3: 0/4 — ⏳ Pending** (needs Wave 2)
> - **Wave 4: 0/2 — ⏳ Pending** (needs Wave 3)
> - **Overall: 17/25 tickets DONE (68%) — 8 remaining.** See `docs/prompts/tickets/README.md` for per-ticket prompts.

> Read `CONSOLIDATED_SPEC.md` §2–7 for canonical definitions before picking a ticket. All `path:line` below verified at 2026-08-22.

---

## Concurrency Map (DAG) — Hardened

| Wave | Ticket ID | Domain / Module | Target Write Scope (exclusive) | Depends On | Agent Scope | Status |
|---|---|---|---|---|---|---|
| **Wave 0 — Contracts ✅ DONE** | `TICK-001` | Core / Paths & Version | `dataforge/core/paths.py [NEW FILE]`, `dataforge/__init__.py`, `dataforge/core/__init__.py` | None | Scaffolding | ✅ DONE 2026-08-22 — `tests/test_paths_contract.py` 11/11, `__version__` + XDG + legacy migration verified |
| Wave 0 | `TICK-002` | Core / Provider & Models | `dataforge/core/provider.py`, `dataforge/core/common.py` | None | Interfaces | ✅ DONE 2026-08-22 — `tests/test_provider_contract.py` 14/14, `FileEntry` `st_ino/st_dev/st_blocks` + `FileProvider` 7 methods verified |
| Wave 0 | `TICK-003` | Engine / API Contracts | `dataforge/api/__init__.py [NEW FILE]`, `dataforge/api/schema.py [NEW FILE]`, `dataforge/api/transport/__init__.py [NEW FILE]`, `dataforge/api/transport/base.py [NEW FILE]` | None | Schemas & DTOs | ✅ DONE 2026-08-22 — `tests/test_api_schema.py` 18/18, Pydantic DTOs + `Transport` `auto_discover` order verified |
| Wave 0 | `TICK-004` | Core / Persistence Contracts | `dataforge/core/config.py`, `dataforge/core/cache.py`, `dataforge/engine/__init__.py [NEW FILE]`, `dataforge/engine/migrations/README.md [NEW FILE]` | `TICK-001` | DB/Config contracts | ✅ DONE 2026-08-22 — `tests/test_migration_contracts.py` 8/8, `CONFIG_SCHEMA_VERSION=2` + adaptive workers + `CACHE_SCHEMA_VERSION` + `set_hash_many` sig verified |
| Wave 0 | `TICK-005` | Engine / Job Contract | `dataforge/engine/jobs.py [NEW FILE]`, `dataforge/engine/daemon.py [NEW FILE]` (stub) | `TICK-003` | Job model | ✅ DONE 2026-08-22 — `tests/test_jobs_contract.py` 18/18, `JobQueue` depth 8 + ULID + `is_cancelled()` + side-effect-free daemon verified |
| **Wave 1 — Parallel Fixes & Perf 🔜 IN PROGRESS (2/9 DONE)** | `TICK-101` | Core / Logger | `dataforge/core/logger.py` | `TICK-004` | Bugfix R-CORE-1 | ✅ DONE 2026-08-22 — `tests/test_logger_stdout_regression.py` 11/11, `sys.stderr` + `0o600` file verified |
| Wave 1 | `TICK-102` | Core / Scanner | `dataforge/core/scanner.py` | `TICK-002` | Perf parallel BFS | ✅ DONE 2026-08-22 — `tests/test_scanner_parallel.py` 22/22, parallel BFS + `DirEntry.stat` + `st_ino/st_dev` verified |
| Wave 1 | `TICK-103` | Core / Hasher | `dataforge/core/hasher.py` | `TICK-002` | Perf mmap + block size | ✅ DONE 2026-08-22 — `tests/test_hasher_mmap.py` 14/14, 1 MiB + `mmap` 16 MiB + `posix_fadvise` verified |
| Wave 1 | `TICK-104` | Core / Cache Impl | `dataforge/core/cache.py` *(sequential re-entry after TICK-004 — Wave 0 sig → Wave 1 impl: `set_hash_many`, `PRAGMA`s, index)* | `TICK-004` | Perf batch | ✅ DONE 2026-08-22 — `tests/test_cache_batch.py` 8/8, `executemany` + `PRAGMA synchronous=NORMAL` + `idx_hash_lookup` verified |
| Wave 1 | `TICK-105` | Operations / Primitives | `dataforge/core/operations/files.py` | `TICK-002` | Bugfix R-OPS-1/3/4/6 | ✅ DONE 2026-08-22 — `tests/test_operations_collision.py` 8/8, `O(N²)→O(N)` + prune empty + `normcase` verified |
| Wave 1 | `TICK-106` | Modules / Search | `dataforge/modules/search.py` | `TICK-003` | Perf content search | ✅ DONE 2026-08-22 — `tests/test_search_streaming.py` 22/22, `mmap` + `bytes regex` + `ThreadPool` verified |
| Wave 1 | `TICK-107` | Modules / Duplicates | `dataforge/modules/duplicates.py` | `TICK-003` | Perf pipeline + verify | ✅ DONE 2026-08-22 — `tests/test_dupes_pipeline.py` 17/17, `queue.Queue` + `xxhash` + `streaming` verified |
| Wave 1 | `TICK-108` | Modules / Integrity | `dataforge/modules/integrity.py` | `TICK-003` | Perf streaming | ✅ DONE 2026-08-22 — `tests/test_integrity_streaming.py` 14/14, `streaming` + `executemany` + `tmp+os.replace` verified |
| Wave 1 | `TICK-109` | Modules / Forensics (hash/keyword) | `dataforge/modules/forensics.py` *(first writer; second sequential writer is TICK-304 Wave 3)* | `TICK-003` | Perf + F15 | ✅ DONE 2026-08-22 — `tests/test_forensics_streaming.py` 10/10, `byte budget` + `queue` + `no double stat` verified |
| **Wave 2 — Service & Mutations 🔜 IN PROGRESS (3/5 DONE)** | `TICK-201` | Service / Batch Actions | `dataforge/core/services/file_actions.py` | `TICK-105`, `TICK-102` | Parallel mutations + R-OPS-2 | 🔜 Ready (unblocked, distinct file) |
| Wave 2 | `TICK-202` | Modules / Recovery | `dataforge/modules/recovery.py` | `TICK-102`, `TICK-103` | F6 carving (mmap + chunk) | ✅ DONE 2026-08-22 — `tests/test_recovery_parallel.py` 19/19, `mmap` + sliding-window + `ThreadPool` verified |
| Wave 2 | `TICK-203` | Modules / System Cleanup | `dataforge/modules/system_cleanup.py` | `TICK-102` | Perf + S7 follow-up | 🔜 Ready (unblocked, distinct file) |
| Wave 2 | `TICK-204` | Modules / Metadata | `dataforge/modules/metadata.py` | `TICK-003` | Consolidate vs cleaner | ✅ DONE 2026-08-22 — `tests/test_metadata_single_seam.py` 10/10, `MetadataEngine` shim + `cleaner.py` delegation verified |
| Wave 2 | `TICK-205` | Transport / UDS+Pipe | `dataforge/api/transport/uds.py [NEW FILE]`, `dataforge/api/transport/named_pipe.py [NEW FILE]` | `TICK-003`, `TICK-005` | Native IPC (N0) | ✅ DONE 2026-08-22 — `tests/test_transport_uds_pipe.py` 30/30, `UdsTransport` + `NamedPipeTransport` + `auto_discover` verified |
| **Wave 3 — Integration & Packaging ⏳ Pending** | `TICK-301` | Engine / Daemon + Client | `dataforge/engine/daemon.py` *(sequential overwrite of TICK-005 stub)*, `dataforge/client/__init__.py [NEW FILE]`, `dataforge/client/sync.py [NEW FILE]`, `dataforge/service/__main__.py [NEW FILE]` | `TICK-205`, `TICK-201` | Consolidation: job queue + auto-discover | ⏳ Pending |
| Wave 3 | `TICK-302` | Service / Lifecycle | `dataforge/service/linux/dataforge.socket [NEW FILE]`, `dataforge/service/linux/dataforge.service [NEW FILE]`, `dataforge/service/linux/com.dataforge.Engine.service [NEW FILE]`, `dataforge/service/windows/service.py [NEW FILE]`, `dataforge/service/macos/com.dataforge.engine.plist [NEW FILE]` | `TICK-301` | `systemd`/`launchd`/Service | ⏳ Pending |
| Wave 3 | `TICK-303` | Build / Packaging | `build_exe.py`, `packaging/nfpm.yaml [NEW FILE]`, `packaging/README.md [NEW FILE]` | `TICK-001` | Onefile+onedir, deb/rpm | ⏳ Pending |
| Wave 3 | `TICK-304` | Forensic / Audit & Evidence | `dataforge/core/audit.py [NEW FILE]`, `dataforge/core/case.py [NEW FILE]`, `dataforge/modules/forensics.py` *(sequential second writer after TICK-109)* | `TICK-005`, `TICK-109` | F1–F3/U2 + F9 — single seam, isolated | ⏳ Pending |
| **Wave 4 — Final Consolidation ⏳ Pending** | `TICK-401` | UI / Job Manager | `dataforge/ui/app.py`, `dataforge/ui/job_manager.py [NEW FILE]` | `TICK-301`, `TICK-304` | Replace `is_busy` + virtualize tables | ⏳ Pending |
| Wave 4 | `TICK-402` | Docs / Version Sync | `scripts/bump_version.py [NEW FILE]`, `pyproject.toml` *(sole writer this wave)* | `TICK-001`, `TICK-303` | Central version source | ⏳ Pending |

**Disjoint guarantee (hardened):** No two tickets in the **same wave** list the same `exclusive_write_files` path. Central touchpoints (`dataforge/ui/app.py`, `pyproject.toml`, `dataforge/engine/daemon.py`, `dataforge/modules/forensics.py`, `dataforge/core/cache.py`) appear in **different waves** sequentially and are documented as re-entries. Wave 0 contracts land before any Wave 1 impl that imports them (`TICK-004` now depends on `TICK-001`).

*Alias:* `docs/proposals/PERFORMANCE_TICKETS.md` `PERF-*` tickets are **aliases** to `TICK-*` below — `PERF-100→TICK-004`, `PERF-101→TICK-102`, `PERF-102→TICK-103`, `PERF-103→TICK-104`, `PERF-104→TICK-107`, etc. Pick one set per run; never run twins same wave.

---

## Wave 0 Review — Completed 2026-08-22 (5/5 DONE, 69 tests)

> **Reviewer:** Principal Technical Auditor · **Method:** `Read` each `exclusive_write_files` + `Read` `tests/test_*` + `PYTHONPATH=. pytest` + manual `python -c` import checks against `CONSOLIDATED_SPEC.md` §2–7 and hardened audit `docs/AUDIT_HARDENED_2026-08-22.md`. All 5 Wave 0 contracts are **file-parity clean, symbol-accurate, and disjoint per wave**.

| Ticket | Implementation | Verification | Finding | Status |
|---|---|---|---|---|
| `TICK-001` | `dataforge/core/paths.py [NEW]` PlatformDirs + `_FallbackDirs` (XDG `~/.config`/`~/.cache`/`~/.local/state`/`/tmp`/`Logs`, macOS `~/Library`, Windows `AppData`), `LEGACY_DIR=~/.dataforge`, `migrate_from_legacy()` copies `config.json`/`cache.db`/`app.log` to `backup.<ts>`, `ensure_dirs()`, `dataforge/__init__.py` `__version__` via `importlib.metadata` → `pyproject.toml` fallback (`0.1.0` matches), `core/__init__.py` re-exports | `pytest tests/test_paths_contract.py` 11/11 ✅ · `python -c 'import dataforge; print(__version__)'` `0.1.0` · `paths.config_file==~/.config/DataForge/config.json` (XDG) | Adaptive `DATAFORGE_SKIP_LEGACY_MIGRATION` env, no `pyproject.toml` write (correct per hardened `TICK-001` — `pyproject` sole writer is `TICK-402` Wave 4). No hallucination. | ✅ DONE |
| `TICK-002` | `dataforge/core/common.py` adds `st_ino:int=0, st_dev:int=0, st_blocks:int=0` + `hardlink_key` property; `provider.py` expands to 7 methods `list_files` (+`cancel_token`/`progress_callback`), `list_files_parallel` (shim), `stat`, `open`, `hash`, `hash_many`, `exists` + `move`/`copy` abstract, `LocalProvider` implements all via `scanner`/`hasher`/`os.stat`/`shutil`, `default_provider()` | `pytest tests/test_provider_contract.py` 14/14 ✅ · `mypy provider.py` clean (advisory) · `isinstance(LocalProvider(),FileProvider)` · `FileEntry(st_ino=123,st_dev=456).hardlink_key==(456,123)` | No redundant work (Wave 0 contract only — no parallel walk yet, that is `TICK-102`). `exists`/`hash_many` default shim added correctly (previous 3-method ABC → 7-method, backward compat). | ✅ DONE |
| `TICK-003` | `dataforge/api/schema.py [NEW]` Pydantic `ApiRequest.to_jsonrpc()` + `ScanRequest`/`SearchRequest`/`DupesRequest`/`HashRequest`/`IntegrityRequest` + `JobStatus`/`JobEvent`/`JobEventType` with `field_validator` for `root`, `algo`; `transport/base.py [NEW]` `Transport` ABC `send`/`recv`/`subscribe`/`auto_discover` + `_discover_endpoints()` order `DATAFORGE_ENGINE_SOCK` → `XDG_RUNTIME_DIR` → `~/Library` → `\\.\pipe` → `http://127.0.0.1:8765` + `_probe_first_existing()` | `pytest tests/test_api_schema.py` 18/18 ✅ · `ScanRequest(root='/tmp').to_jsonrpc()=={'jsonrpc':'2.0',...}` · `Transport` subclass requires 4 methods · no circular import `core→api` | Correctly adds `pydantic` to `requirements` scope (new dep isolated to `api/`). `api/__init__.py` + `transport/__init__.py` added per hardened file parity. No hallucination (previously missing `api/` dir). | ✅ DONE |
| `TICK-004` | `config.py` adds `CONFIG_SCHEMA_VERSION=2`, `MIGRATIONS={1:_migrate_v1_to_v2}`, adaptive `_default_max_thread_workers()=min(32,cpu*4)`, `hash_block_size=1<<20`, `cache_batch_size=1000`, `_schema_version` handling + backup `config.json.bak.v1`; `cache.py` adds `CACHE_SCHEMA_VERSION=2`, `MIGRATIONS_DIR`, `get_user_version()`, `get_pending_migrations()`/`pending_migrations`, `set_hash_many(rows: list[tuple[str,int,float,str,str]])` shape validation (Wave 0 stub, impl is `TICK-104`) + `PRAGMA user_version` read | `pytest tests/test_migration_contracts.py` 8/8 ✅ · `config.CONFIG_SCHEMA_VERSION==2` · `cache.CACHE_SCHEMA_VERSION==2` · `set_hash_many` validates 5-tuple shape · `test_config_adaptive_workers_12_core` mocked `cpu_count=12` → 32 workers | `depends_on: ["TICK-001"]` correctly added (needs `paths.py`). `cache.py` `set_hash_many` is **stub** per contract (returns `None` after validation) — impl deferred to `TICK-104` Wave 1, so no redundant work. | ✅ DONE |
| `TICK-005` | `engine/jobs.py [NEW]` `Job` (ULID 26-char, `provider`/`params`/`cancel_token`/`progress_callback`/`status`→`JobStatus.QUEUED`→`RUNNING`→`DONE`/`CANCELLED`/`FAILED`, `is_cancelled()`, `to_dict()`/`json_safe()`), `JobQueue` depth 8 `ThreadPoolExecutor` + `_run_job`/`submit`/`get`/`cancel`/`list_jobs`/`subscribe`, `EngineDaemon` stub `daemon.py [NEW]` side-effect-free `Daemon` wrapping `JobQueue` (`is_running` false on import) | `pytest tests/test_jobs_contract.py` 18/18 ✅ · `JobQueue().submit(dummy)` → `DONE` · `job.is_cancelled()` after `cancel_token.set()` · `job.json_safe()` JSON dumps · `from dataforge.engine.daemon import Daemon` no server start | `engine/__init__.py` + `migrations/README.md` added per hardened parity. Stub correctly defers real `asyncio`+`ProcessPool` loop to `TICK-301` Wave 3 (sequential re-entry). | ✅ DONE |

**Wave 0 gate:** 5/5 contracts landed, `69 passed` (`11+14+18+8+18`), no file appears twice in Wave 0 (disjoint), `depends_on` satisfied (`TICK-004→001`, `TICK-005→003`), `git diff --name-only origin/develop` shows only `exclusive_write_files` + tests. **Wave 1 is now unblocked — 9 agents may start in parallel on distinct files.**

---

## Wave 1 Review — Completed 2026-08-22 17:15 UTC (9/9 DONE)

> **Reviewer:** Principal Technical Auditor · **Method:** `Read` each `exclusive_write_files` + `Read` `tests/test_*` + `PYTHONPATH=. pytest` + `git log --oneline --grep=TICK-10` + `ls -l dataforge/...` file-time checks. Wave 1 now has **9/9 merged tickets — 126 tests, 9/9 `validation_command` green, file parity clean, 9 disjoint files, no collision**.

| Ticket | Implementation | Verification | Finding | Status |
|---|---|---|---|---|
| `TICK-101` | `dataforge/core/logger.py` routes console handler to `sys.stderr` (was `sys.stdout` → `R-CORE-1` JSON corruption), keeps `RotatingFileHandler`, ensures `0o600` on `log_file` creation via `os.open(...,0o600)` + `os.chmod(...,0o600)`; change is isolated to `setup_logger` (`ch = StreamHandler(sys.stderr)`) | `pytest tests/test_logger_stdout_regression.py` 11/11 ✅ · `PYTHONPATH=. pytest tests/test_logger_stdout_regression.py tests/test_hasher_mmap.py -q` 25/25 (11+14) · manual `fm dupes --format json | jq` no `INFO` on stdout | Correct fix for `R-CORE-1`: `StreamHandler(sys.stdout)` → `sys.stderr` per hardened audit; no file parity issue (existing file, no new file). Disjoint in Wave 1 (only writer to `logger.py`). | ✅ DONE 2026-08-22 — merged `fix/TICK-101-logger-stderr` (`8771a2a` → `c57be1e`) |
| `TICK-102` | `dataforge/core/scanner.py` now parallel BFS work-queue `os.scandir` via `ThreadPoolExecutor(min(32,cpu*4))`, `entry.stat(follow_symlinks=False)` (no `build_file_entry` double-stat), populates `st_ino/st_dev/st_blocks`, batch `queue.Queue` 1k, keeps `excluded_folders/extensions` + `cancel_token`; `FileEntry` `st_ino` fields from `TICK-002` used | `pytest tests/test_scanner_parallel.py` 22/22 ✅ · `perf(core): parallel BFS scanner with DirEntry.stat reuse` (`17f52ff` → `4514ec1` merge) · `stat` syscall halved, `hardlink_key` verified | Correct per `TICK-102`/`PERF-101`: double-stat fixed, sequential `yield from` replaced. Disjoint (only writer to `scanner.py` in Wave 1). | ✅ DONE 2026-08-22 — merged `feat/TICK-102-parallel-scanner` |
| `TICK-103` | `dataforge/core/hasher.py` now 1 MiB config-driven (`_DEFAULT_BLOCK_SIZE=1<<20`, `_get_block_size()` reads `config.hash_block_size` with `1024–16MiB` validation, fallback `1<<20`), `MMAP_THRESHOLD=16MiB`, `mmap.mmap` + `posix_fadvise(WILLNEED)`/`madvise(WILLNEED)` for large files, `cancel_token` per chunk, `get_hashes` single-pass for many algos, keeps `SUPPORTED_ALGORITHMS` unchanged (`md5` default) | `pytest tests/test_hasher_mmap.py` 14/14 ✅ · `perf(core): switch hasher to 1 MiB mmap blocks` (`5cd786d` → `c58154f` merge) · `BLOCK_SIZE` now dynamic via `_get_block_size()` | Correct per `TICK-103` spec: `BLOCK_SIZE 64KiB→1MiB`, `mmap` path, no `xxhash` added to `SUPPORTED_ALGORITHMS` (prefilter is internal, not public). Disjoint (only writer to `hasher.py` in Wave 1; polish `PERF-114` Wave 3 is sequential). | ✅ DONE 2026-08-22 — merged `feat/TICK-103-mmap-hasher` |
| `TICK-104` | `dataforge/core/cache.py` now implements `set_hash_many(rows)` via `executemany` + single `commit` (batch `cache_batch_size`), `PRAGMA synchronous=NORMAL`/`cache_size=-64000`, `CREATE INDEX IF NOT EXISTS idx_hash_lookup ON file_hashes(algo,size,mtime)`, keeps `threading.Lock` single connection | `pytest tests/test_cache_batch.py` 8/8 ✅ · `perf(core): batch cache writes + WAL pragmas + composite index` (`cb77bd8` → `40ee06f` merge) · `EXPLAIN QUERY PLAN` uses `idx_hash_lookup`, 100k `executemany` 1 fsync | Correct per `TICK-104`/`PERF-103`: `commit()` per file → `executemany` batch, `WAL` stays, no `database is locked` under `ThreadPool(4)`. Sequential re-entry `cache.py` W0 sig → W1 impl (disjoint per wave). | ✅ DONE 2026-08-22 — merged `feat/TICK-104-batch-cache-writes` |
| `TICK-105` | `dataforge/core/operations/files.py` now pre-normalizes `reserved_paths` once per batch (was `O(N²)` `set` rebuild per call), lazy `os.makedirs` only on first success (clean empty on total failure), `normcase(candidate)!=normcase(current_path)` for case-only rename, `resolve_collision_path` thread-safe | `pytest tests/test_operations_collision.py` 8/8 ✅ · `fix(core): collision O(N), prune empty dest, case-only rename` (`accf9ca` → `d901feb` merge) · `normalize_path` count `O(N)` profiled | Correct per `TICK-105`/`PERF-111` `R-OPS-1/3/4/6`: `O(N²)` fixed, empty-dest pruned, `FOO.txt→foo.txt` not `foo_1.txt` on case-insensitive FS. Disjoint (only writer to `operations/files.py` in Wave 1). | ✅ DONE 2026-08-22 — merged `fix/TICK-105-collision-prune-case-rename` |
| `TICK-106` | `dataforge/modules/search.py` now `mmap` + `bytes` `re` on `mmap.ACCESS_READ`, `python-magic` `mime` binary skip (unless `--force-binary`), `ThreadPool(search_thread_workers)` `min(32,cpu*2)`, 1 MiB sliding window + 10 MB cap, shared with `forensics.keyword_search` via engine helper, no `open(...).readlines()` | `pytest tests/test_search_streaming.py` 22/22 ✅ · `perf(modules): parallel mmap search shared with forensics` (`1c53474` → `0288e77` merge, also `4788447` batch) · `EXPLAIN` + `ThreadPool` verified | Correct per `TICK-106`/`PERF-105`: `f.read(10MB)` + line loop → `mmap` + `bytes regex` + pool, binary-aware, 1 MiB window. Disjoint (only writer to `search.py` in Wave 1). | ✅ DONE 2026-08-22 — merged `feat/TICK-106-search-mmap-parallel` |
| `TICK-107` | `dataforge/modules/duplicates.py` now `queue.Queue[FileEntry]` pipeline: `scan_directory` → producer thread(s) → `queue` → `streaming size-map` → `xxhash64(first 4KiB)` prefilter (fallback to `hashlib`) → `ThreadPool(min(32,cpu*4))` `sha256` only on collisions, `verify_content=True` `filecmp.cmp` byte-compare, `order_duplicate_records` double-sort fixed, `hardlink_key` dedup | `pytest tests/test_dupes_pipeline.py` 17/17 ✅ · `feat(modules): pipeline dupes streaming size-map fast-hash verify` (`653016e` → `e77f879` merge) · `list(scan_directory)` absent, `RSS O(batch)` | Correct per `TICK-107`/`PERF-104`: `list()` OOM → `queue` streaming, `xxhash→sha256` two-phase, `verify_content` closed. Disjoint (only writer to `duplicates.py`). | ✅ DONE 2026-08-22 — merged `feat/TICK-107-pipeline-dupes` |
| `TICK-108` | `dataforge/modules/integrity.py` now streaming `scan_directory` → `queue.Queue` → `ThreadPool(min(32,cpu*4))` `get_file_hash` → `executemany` `set_hash_many` + `PRAGMA`, atomic `snapshot.json` via `tmp` + `os.replace`, keeps legacy flat `md5` readable, `cancel_token` per hash | `pytest tests/test_integrity_streaming.py` 14/14 ✅ · `perf(modules): stream integrity snapshots via queue and atomic write` (`d3033b2` → `4788447` merge) · `RSS O(batch)`, `tmp→replace` atomic | Correct per `TICK-108`/`PERF-106`: `list(scan_directory)` `~300MB` for 1M files → `queue` streaming. Disjoint (only writer to `integrity.py`). | ✅ DONE 2026-08-22 — merged `feat/TICK-108-stream-integrity` |
| `TICK-109` | `dataforge/modules/forensics.py` now `calculate_hashes` reuses `hasher.py` `mmap` path, `keyword_search` global byte budget `10MB×workers → bounded queue` (was `f.read(10MB)` per file unbounded), `ingest_disk_image` streaming `queue` to `hash+artifacts+keyword` (no `file_paths: list`), `build_timeline` reuses `FileEntry` `st_mtime` (no `os.stat` redo) | `pytest tests/test_forensics_streaming.py` 10/10 ✅ · `perf(modules): forensics streaming engine with byte budget` (`93b2fad` → `7cb454c` merge) · `RSS <100MB` for 4 workers, `grep -n file_paths` absent | Correct per `TICK-109`/`PERF-107`: `f.read(10MB)` unbounded → bounded `queue`, `file_paths` list removed, `os.stat` redo removed. Disjoint in Wave 1 (only writer to `forensics.py` in Wave 1; second writer is `TICK-304` Wave 3). | ✅ DONE 2026-08-22 — merged `feat/TICK-109-forensics-streaming` |

**Wave 1 gate:** 9/9 DONE (126 tests: `11+22+14+8+8+22+17+14+10`), 9/9 `validation_command` green, file parity clean, 9 disjoint files, no collision. **Wave 1 is now fully green — Wave 2 is unblocked (all Wave 2 `depends_on` satisfied: `TICK-102`/`103`/`105`/`003`/`005` are DONE) and can start with 5 parallel agents on distinct files. Wave 1 → Wave 2 handoff verified via `git diff --name-only` (only `exclusive_write_files` + tests changed).**

---

## Wave 2 Review — Partial 2026-08-22 18:30 UTC (3/5 DONE, 2 remaining)

> **Reviewer:** Principal Technical Auditor · **Method:** `Read` each `exclusive_write_files` + `Read` `tests/test_*` + `PYTHONPATH=. pytest` + `git log --oneline --grep=TICK-20` + `ls -l dataforge/...` file-time checks. Wave 2 now has 3 merged tickets (`TICK-202`, `TICK-204`, `TICK-205` — 59 tests) and 2 still open (`TICK-201`, `TICK-203`). All remaining are **disjoint, unblocked (Wave 1 green), and ready for parallel execution**.

| Ticket | Implementation | Verification | Finding | Status |
|---|---|---|---|---|
| `TICK-201` | `dataforge/core/services/file_actions.py` still at `Jul 11 23:20` (sequential `for index, item in enumerate...`, no `ThreadPool`, no lock on `reserved_paths`, `archive_items` single-mode `try` outside loop) — **not yet implemented** | No `tests/test_file_actions_parallel.py` | **Open, ready** — depends on `TICK-105`/`102` (DONE), distinct file | 🔜 Ready |
| `TICK-202` | `dataforge/modules/recovery.py` now `mmap` image, 64 MiB sliding windows with `overlap=max(header+footer)`, `ThreadPoolExecutor(min(32,cpu*4))` parallel signature scan, per-worker temp then `os.replace` atomic move, `_get_max_workers()` adaptive, `_carve_one`/`_scan_window` helpers | `pytest tests/test_recovery_parallel.py` 19/19 ✅ · `feat(modules): parallel carving mmap sliding-window chunked workers` (`f3968c7` → `327d14c` merge) · `mmap` + sliding window + `ThreadPool` verified | Correct per `TICK-202`/`PERF-108`: sector-alignment miss fixed (sliding window), `days→hours` on 500 GB, no partial on cancel. Disjoint (only writer to `recovery.py` in Wave 2). | ✅ DONE 2026-08-22 — merged `feat/TICK-202-parallel-carving` |
| `TICK-203` | `dataforge/modules/system_cleanup.py` still at `Jul 12 00:30` (still per-pattern `os.walk`, `_is_socket_or_fifo` extra `stat`) — **not yet implemented** | No `tests/test_system_cleanup_walks.py` | **Open, ready** — depends on `TICK-102` (DONE), distinct file | 🔜 Ready |
| `TICK-204` | `dataforge/modules/metadata.py` now `MetadataEngine` is single source (`exiftool→Pillow→pypdf→mutagen` tiered); `dataforge/modules/cleaner.py` `MetadataCleaner` is thin shim delegating `remove_metadata` to `MetadataEngine`; `cleaner.py:4` `from .metadata import MetadataEngine` | `pytest tests/test_metadata_single_seam.py` 10/10 ✅ · `refactor(modules): consolidate metadata cleaning to MetadataEngine shim` (`6be098a` → `2eee4e0` merge) · `grep MetadataCleaner` shows only shim | Correct per `TICK-204`: `cleaner.py` is now shim (was separate impl), return type unified to `dict`. Disjoint (only writer to `metadata.py` in Wave 2). | ✅ DONE 2026-08-22 — merged `feat/TICK-204-metadata-engine-consolidation` |
| `TICK-205` | `dataforge/api/transport/uds.py [NEW]` `UdsTransport` `asyncio.start_unix_server` + `SO_PEERCRED` check + `0o700` socket + length-prefixed `msgpack` framing; `dataforge/api/transport/named_pipe.py [NEW]` `NamedPipeTransport` `win32pipe`/`Proactor` + SDDL + `auto_discover` order `$DATAFORGE_ENGINE_SOCK→XDG→~/Library→\\.\pipe→http://127.0.0.1:8765` | `pytest tests/test_transport_uds_pipe.py` 30/30 ✅ · `feat(engine): implement UDS and Named Pipe transports for native IPC` (`7a2e652` → `d9e1ed4` merge) · `auto_discover` order verified, `0o700` perms check | Correct per `TICK-205`/`PERF-110`: UDS primary local, Named Pipe Windows, `msgpack` framing, `SO_PEERCRED`/`LOCAL_PEERCRED` auth. Disjoint (only writer to `uds.py`+`named_pipe.py` in Wave 2). | ✅ DONE 2026-08-22 — merged `feat/TICK-205-uds-named-pipe-transport` |

**Wave 2 gate:** 3/5 DONE (`TICK-202`, `TICK-204`, `TICK-205` — 59 tests: `19+10+30`), 2/9 remaining (`TICK-201` `file_actions.py`, `TICK-203` `system_cleanup.py`) are **all unblocked** (their `depends_on` are Wave 1 DONE) and **file-disjoint** (2 different files). They can run **in parallel on 2 agents** without collision. Wave 3 `TICK-301` needs `TICK-205` (DONE) + `TICK-201` (open) → **Wave 3 partially unblocked** but `TICK-301` needs `TICK-201` — finish Wave 2 remaining 2 first.

---

## How to Work a Ticket — Sequential and Parallel Execution Guide

> **Required reading before picking a ticket:** `docs/CONSOLIDATED_SPEC.md` §2–7 + `docs/CONTRIBUTING.md` §2–10. Every ticket below is one agent = one branch = one commit = one PR.

### 1. One ticket, one branch, one commit

```bash
git checkout develop && git pull origin develop
git checkout -b feat/TICK-102-parallel-scanner   # or perf/PERF-101-…
# — work only inside exclusive_write_files —
PYTHONPATH=. python -m pytest tests/test_scanner_parallel.py -q   # per-ticket target
PYTHONPATH=. python -m pytest -q                                   # full suite before push
git add <exclusive_write_files> tests/test_*.py
git commit -m "feat(core): parallel BFS scanner with DirEntry.stat reuse"  # Conventional Commits, ≤72 chars
```

- **Branch name:** `feat/<TICK-ID>-kebab-summary` or `fix/<TICK-ID>-…` / `perf/<TICK-ID>-…` matching `type(scope)` in ticket.
- **Commit scope:** `core`, `modules`, `ui`, `build`, `docs`, `tests`, `repo` per `CONTRIBUTING.md:148`. Omit scope for cross-cutting `docs:`.
- **One logical change per commit** (`CONTRIBUTING.md:453`). Do not batch two tickets into one commit; do not leave finished work uncommitted.

### 2. File ownership — the only rule for parallel safety

- `exclusive_write_files` is the **sole writer** contract for this wave. An agent may *read* any `read_only_references` but must **not** `git add` a file outside its exclusive list. If two tickets need the same file, they are in **different waves** (sequential re-entry, e.g. `cache.py` W0→W1) — not same wave.
- New files carry ` [NEW FILE]` — create the parent dir (`mkdir -p`) before writing.
- Central touchpoints (`dataforge/ui/app.py`, `pyproject.toml`, `dataforge/engine/daemon.py`, `dataforge/modules/forensics.py`) are **single-writer per wave** by design. Do not edit them outside their wave.
- Append-only files (`CHANGELOG.md` under `[Unreleased]`, `progress.md` if using `.sdlc/`) are safe for concurrent appends; everything else is exclusive.

### 3. Sequential execution (default, any repo size)

Execute waves in DAG order. A wave starts only after **all** `depends_on` tickets in earlier waves have merged to `develop`:

```
Wave 0 (contracts) → Wave 1 (parallel fixes, 9 agents but still after W0) → Wave 2 → Wave 3 → Wave 4
```

Inside a wave with dependencies, respect the ticket’s `depends_on` list (e.g. `TICK-004` depends on `TICK-001` — land `TICK-001` first even though both are Wave 0).

Verification per ticket (Definition of Done, per `CONTRIBUTING.md:458` and `.github/workflows/sdlc-*`):

1. Code written inside `exclusive_write_files` + new test `tests/test_*.py [NEW FILE]`.
2. `PYTHONPATH=. python -m pytest tests/test_<ticket>.py -q` passes.
3. `PYTHONPATH=. python -m pytest -q` passes (allow 2 world-writable plugin failures on NTFS mounts — fix with `chmod 755` on ext4).
4. `ruff check dataforge tests` and `mypy <changed file>` clean (mypy advisory).
5. `validation_command` from ticket’s `verification` block passes.

### 4. Parallel execution (when to use, how to stay safe)

| Scenario | Recommendation |
|---|---|
| Small project, one dev | Sequential — simpler, no rebase. |
| Large project, many features, CI green | **Parallel within a wave** — all tickets in same wave have disjoint write sets and can run concurrently. |
| Time-critical delivery | Parallel within wave + sequential across waves (waves are the gate). |
| Two tickets touch same file | **Sequential** — do not run in parallel; they are deliberately in different waves. |

**Parallel within a wave — how:**

1. **One branch per ticket** off the same `develop` base. No branch shares an `exclusive_write_files` path with another branch in the same wave.
2. **No cross-file edits.** If you discover you need a file outside your exclusive list, stop — open a new ticket or reassign to the owning ticket’s wave.
3. **Rebase, never merge** while wave is in flight: `git fetch origin && git rebase origin/develop` before push to keep history linear.
4. **CI is the gate:** `.github/workflows/ci.yml` (pytest+coverage, ruff blocking, mypy advisory, pip-audit) runs on push/PR to `develop`/`main`. Do not start next wave until CI is green on `develop` after previous wave merges.
5. **Handoffs:** If using `.sdlc/` workspace (see `.github/workflows/sdlc-parallel.workflow.md` Phase 1–4), agents write handoff files and `progress.md`/`activeContext.md` (append-only) — concurrent appends are safe per shared-memory skill.

**Example — Wave 1 parallel (9 agents):**

```bash
# Terminal A
git checkout -b feat/TICK-101-logger-stderr
# edits only dataforge/core/logger.py

# Terminal B (concurrent)
git checkout -b feat/TICK-102-parallel-scanner
# edits only dataforge/core/scanner.py

# Terminal C (concurrent)
git checkout -b feat/TICK-105-collision
# edits only dataforge/core/operations/files.py
# ... all push to origin, CI runs in parallel, merge to develop in any order — no conflict
```

**When to switch to sequential:** If CI reports a conflict on `dataforge/core/cache.py` (or any central file), two agents edited same file → they were in different waves. Stop parallel, finish the earlier wave’s PR, merge, then start the later wave.

### 5. Pushing per `CONTRIBUTING.md` & `DEVELOPMENT_GUIDE.md`

```bash
git config core.hooksPath .githooks   # one-time (CONTRIBUTING.md:18)
# — ensure commit-msg hook enforces type(scope): description ≤72 chars —
PYTHONPATH=. python -m pytest -q      # must be green (CONTRIBUTING.md:14)
git push -u origin feat/TICK-102-parallel-scanner
# PR: base develop, title same as commit, checklist from CONTRIBUTING.md §7
# Alternatives: direct push to develop allowed for docs/chore if CI green and branch is develop
```

- Default branch is `develop` (feature work), `main` is stable releases only (`CONTRIBUTING.md:15`).
- Tag releases only on `develop`→`main` merges per `CONTRIBUTING.md §6`.
- Every code change updates the docs that reference it (`CONTRIBUTING.md §8` table — e.g. `dataforge/core/` → `ARCHITECTURE.md` + `TECHNICAL_SOURCE_OF_TRUTH.md`).

---

## Work Packages (Hardened)

### TICK-001 — Contract: platformdirs paths + single version source
```yaml
ticket_id: "TICK-001"
title: "Define canonical paths (platformdirs) and single version source"
type: "Contract"
execution_wave: 0
depends_on: []
scope:
  domain: "Core / Infrastructure"
  exclusive_write_files:
    - "dataforge/core/paths.py [NEW FILE]"
    - "dataforge/__init__.py"
    - "dataforge/core/__init__.py"
  read_only_references:
    - "docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md"
    - "dataforge/core/config.py"
    - "dataforge/core/cache.py"
architectural_context:
  existing_symbols_to_use:
    - "ConfigManager.DEFAULT_CONFIG (dataforge/core/config.py:16)"
    - "CacheManager (dataforge/core/cache.py:6)"
  breaking_changes: "None — new file; legacy ~/.dataforge migrated via shim"
requirements:
  summary: "Introduce PlatformDirs-based paths.py as single source for config/cache/state/logs/runtime (XDG on Linux, Application Support/Caches on macOS, AppData/LocalAppData on Windows) with legacy ~/.dataforge migration shim; expose __version__ from importlib.metadata fallback to pyproject.toml:8 version = 0.1.0. Do NOT edit pyproject.toml here (sole writer is TICK-402 Wave 4)."
  source_documents:
    - "docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md"
    - "docs/CONSOLIDATED_SPEC.md"
  acceptance_criteria:
    - "GIVEN legacy ~/.dataforge/config.json exists and new location empty WHEN paths is imported THEN legacy is copied to new location with ~/.dataforge.backup.<ts> and migrated_from_legacy logged"
    - "GIVEN import dataforge; dataforge.__version__ WHEN no install THEN falls back to pyproject.toml version without error"
    - "GIVEN paths.config_file WHEN called on Linux/macOS/Windows THEN returns XDG/AppSupport/AppData path (mocked via env in tests)"
verification:
  test_target: "tests/test_paths_contract.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_paths_contract.py -q"
```

### TICK-002 — Contract: FileProvider ABC + FileEntry extension
```yaml
ticket_id: "TICK-002"
title: "Expand FileProvider ABC and FileEntry for hardlink/sparse/inode awareness"
type: "Contract"
execution_wave: 0
depends_on: []
scope:
  domain: "Core / Provider"
  exclusive_write_files:
    - "dataforge/core/provider.py"
    - "dataforge/core/common.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
    - "docs/proposals/NATIVE_OS_API_REVIEW.md"
architectural_context:
  existing_symbols_to_use:
    - "FileEntry dataclass (dataforge/core/common.py:5)"
    - "FileProvider ABC + LocalProvider (dataforge/core/provider.py:4)"
  breaking_changes: "Additive — new fields default to 0, new ABC methods optional with default shim so existing LocalProvider still instantiable"
requirements:
  summary: "Extend FileProvider with 7 methods: list_files, list_files_parallel, stat, open, hash, hash_many, exists (all cancel_token: Optional[threading.Event] and progress_callback where applicable) and add st_ino: int=0, st_dev: int=0, st_blocks: int=0 to FileEntry. Keep LocalProvider as thin shim over new scanner/hasher contracts."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.1"
    - "docs/proposals/NATIVE_OS_API_REVIEW.md#3.3"
  acceptance_criteria:
    - "GIVEN isinstance(LocalProvider(), FileProvider) WHEN checking ABC THEN all 7 methods are abstract and implementable without TypeError"
    - "GIVEN a FileEntry with st_ino/st_dev WHEN compared THEN hardlink-equal entries share same pair and downstream dedup can group them"
    - "GIVEN no provider selection WHEN scan_directory is called THEN defaults to LocalProvider (no behavior change yet)"
verification:
  test_target: "tests/test_provider_contract.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_provider_contract.py -q && mypy dataforge/core/provider.py"
```

### TICK-003 — Contract: Engine API schemas (Pydantic DTOs)
```yaml
ticket_id: "TICK-003"
title: "Define engine API schemas (Scan/Search/Dupes/Hash/Integrity) and transport ABC"
type: "Contract"
execution_wave: 0
depends_on: []
scope:
  domain: "Engine / API"
  exclusive_write_files:
    - "dataforge/api/__init__.py [NEW FILE]"
    - "dataforge/api/schema.py [NEW FILE]"
    - "dataforge/api/transport/__init__.py [NEW FILE]"
    - "dataforge/api/transport/base.py [NEW FILE]"
  read_only_references:
    - "docs/proposals/NATIVE_OS_API_REVIEW.md"
    - "dataforge/modules/search.py"
    - "dataforge/modules/duplicates.py"
architectural_context:
  existing_symbols_to_use:
    - "SearchQuery (dataforge/modules/search.py:123)"
    - "FileEntry (dataforge/core/common.py:5)"
  breaking_changes: "New dependency pydantic>=2 (add to requirements.txt) — isolated to api/ import, core/ remains dependency-free"
requirements:
  summary: "Add Pydantic ScanRequest/SearchRequest/DupesRequest/HashRequest/IntegrityRequest + JobStatus/JobEvent and Transport ABC (send/recv/subscribe, auto_discover). These are the sole types Wave 1 modules and Wave 2 transports may import; no circular import with core/*."
  source_documents:
    - "docs/proposals/NATIVE_OS_API_REVIEW.md#3.1"
    - "docs/CONSOLIDATED_SPEC.md"
  acceptance_criteria:
    - "GIVEN from dataforge.api.schema import ScanRequest WHEN ScanRequest(root='/tmp', recursive=True) THEN validates and serializes to JSON-RPC 2.0 payload"
    - "GIVEN Transport ABC WHEN subclassed THEN send/recv/subscribe are required (pytest checks abstract)"
    - "GIVEN schemas WHEN imported by Wave 1 modules THEN no circular import with core/*"
verification:
  test_target: "tests/test_api_schema.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_api_schema.py -q"
```

### TICK-004 — Contract: DB/config versioning + adaptive workers (merged PERF-100)
```yaml
ticket_id: "TICK-004"
title: "Add CONFIG_SCHEMA_VERSION, cache PRAGMA user_version, set_hash_many sig, and adaptive worker defaults"
type: "Contract"
execution_wave: 0
depends_on: ["TICK-001"]
scope:
  domain: "Core / Persistence"
  exclusive_write_files:
    - "dataforge/core/config.py"
    - "dataforge/core/cache.py"
    - "dataforge/engine/__init__.py [NEW FILE]"
    - "dataforge/engine/migrations/README.md [NEW FILE]"
  read_only_references:
    - "docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md"
    - "dataforge/core/paths.py [NEW FILE]"  # from TICK-001
architectural_context:
  existing_symbols_to_use:
    - "ConfigManager.DEFAULT_CONFIG, _validate_one (dataforge/core/config.py:16,89)"
    - "CacheManager._init_db, get_hash, set_hash (dataforge/core/cache.py:20,41,51)"
    - "paths.config_file, paths.cache_db (from TICK-001)"
  breaking_changes: "None — new keys get defaults; existing config.json auto-migrated with .bak"
requirements:
  summary: "Add CONFIG_SCHEMA_VERSION: int = 2 + MIGRATIONS dict + _schema_version top-level key (backups on write), adaptive defaults max_thread_workers=min(32,(cpu_count or 4)*4), search_thread_workers=min(32,(cpu_count or 4)*2), hash_block_size=1<<20, cache_batch_size=1000, plus PRAGMA user_version + def set_hash_many(self, rows: list[tuple[str,int,float,str,str]]) signature + migrations/*.sql convention. No heavy impl yet — constants, signatures, empty migration dir; Wave 1 (TICK-104) fills impl."
  source_documents:
    - "docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md"
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#5"
  acceptance_criteria:
    - "GIVEN config.json with no _schema_version WHEN loaded THEN treated as v1 and migrated to current (1→2) with config.json.bak.v1 and new keys filled"
    - "GIVEN 12-core host WHEN config.get('max_thread_workers') THEN == 32 (adaptive) not 4"
    - "GIVEN cache.db with user_version=1 WHEN opened THEN pending *.sql are enumerated (not yet applied)"
    - "GIVEN set_hash_many(rows) WHEN called with [(path,size,mtime,hash,algo)] THEN validates tuple shape without commit (stub)"
verification:
  test_target: "tests/test_migration_contracts.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_migration_contracts.py -q"
```

### TICK-005 — Contract: Job model
```yaml
ticket_id: "TICK-005"
title: "Define Job model (id, provider, params, cancel_token, progress_callback, results)"
type: "Contract"
execution_wave: 0
depends_on: ["TICK-003"]
scope:
  domain: "Engine / Jobs"
  exclusive_write_files:
    - "dataforge/engine/jobs.py [NEW FILE]"
    - "dataforge/engine/daemon.py [NEW FILE]"  # stub only; full overwrite is TICK-301 Wave 3
  read_only_references:
    - "docs/proposals/NATIVE_OS_API_REVIEW.md"
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#3.3"
    - "dataforge/api/schema.py [NEW FILE]"
architectural_context:
  existing_symbols_to_use:
    - "JobStatus / JobEvent (from TICK-003 schema)"
    - "FileProvider ABC (from TICK-002)"
  breaking_changes: "None — stub daemon importable without side effects (no server start on import)"
requirements:
  summary: "Add Job dataclass + JobQueue stub (queue depth 8, cancel_token: threading.Event, progress_callback → event stream, append-only jobs table hook for future F1). Daemon is a stub that can be imported without starting; real loop is TICK-301."
  source_documents:
    - "docs/proposals/NATIVE_OS_API_REVIEW.md#3.3"
  acceptance_criteria:
    - "GIVEN JobQueue().submit(scan_fn, params) WHEN queried THEN JobStatus is queued → running → done/cancelled/failed"
    - "GIVEN a Job WHEN cancel_token.set() THEN is_cancelled() is True"
    - "GIVEN Job WHEN serialized THEN job_id is ULID-like and JSON-safe"
verification:
  test_target: "tests/test_jobs_contract.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_jobs_contract.py -q"
```

### TICK-101 — Fix: logger stdout corrupts JSON
```yaml
ticket_id: "TICK-101"
title: "Route console logger to stderr so CLI JSON stays clean"
type: "Bugfix"
execution_wave: 1
depends_on: ["TICK-004"]
scope:
  domain: "Core / Logger"
  exclusive_write_files:
    - "dataforge/core/logger.py"
  read_only_references:
    - "docs/reviews/AUDIT_REPORT.md"
    - "dataforge/cli.py"
architectural_context:
  existing_symbols_to_use:
    - "setup_logger(name, log_file, level) (dataforge/core/logger.py:6)"
    - "logger global (dataforge/core/logger.py:40)"
  breaking_changes: "None — stderr vs stdout, file handler unchanged"
requirements:
  summary: "Change StreamHandler(sys.stdout) to sys.stderr (keep file handler at 0o600), or gate stream handler off when Click context is --format json/jsonl. Fixes R-CORE-1 where fm dupes --format json | jq hits JSONDecodeError from INFO Starting duplicate scan on stdout."
  source_documents:
    - "docs/reviews/AUDIT_REPORT.md"
  acceptance_criteria:
    - "GIVEN PYTHONPATH=. python -m dataforge.cli dupes /tmp/x --format json WHEN piped THEN json.load(sys.stdin) succeeds with no log lines on stdout"
    - "GIVEN same command WHEN 2>/dev/null is NOT used THEN log lines appear on stderr"
    - "GIVEN verify_snapshot truncated JSON WHEN run THEN ERROR: Could not read snapshot file. is still reported (on stderr, not swallowed)"
verification:
  test_target: "tests/test_logger_stdout_regression.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_logger_stdout_regression.py -q"
```

### TICK-102 — Perf: parallel BFS scanner + DirEntry.stat reuse
```yaml
ticket_id: "TICK-102"
title: "Replace recursive yield-from walk with parallel BFS + DirEntry.stat reuse + inode fields"
type: "Feature"
execution_wave: 1
depends_on: ["TICK-002"]
scope:
  domain: "Core / Scanner"
  exclusive_write_files:
    - "dataforge/core/scanner.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.1"
    - "dataforge/core/common.py"  # for st_ino/st_dev/st_blocks added in TICK-002
architectural_context:
  existing_symbols_to_use:
    - "FileEntry (dataforge/core/common.py:5) with st_ino/st_dev/st_blocks (from TICK-002)"
    - "scan_directory(root_path, recursive, max_depth, cancel_token) generator signature"
  breaking_changes: "None — same generator signature; internal parallelization is transparent"
requirements:
  summary: "BFS work-queue of dirs via ThreadPoolExecutor(min(32, cpu*4)) calling os.scandir; build FileEntry from entry.stat(follow_symlinks=False) (no build_file_entry double-stat); populate st_ino/st_dev/st_blocks; batch emission (1k) via queue.Queue; keep excluded_folders/extensions honoring and cancel_token. Fixes double-stat + sequential walk (rank #1 bottleneck)."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN 500k-file fixture WHEN scan_directory runs THEN wall time is 3-5x faster than HEAD and stat syscall count is halved (no double-stat)"
    - "GIVEN a dir with hardlinks WHEN scanned THEN two FileEntrys share (st_dev,st_ino) and downstream dedup can group them"
    - "GIVEN cancel_token.set() mid-walk WHEN checked THEN walk stops promptly and yields no further entries"
verification:
  test_target: "tests/test_scanner_parallel.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_scanner_parallel.py -q"
```

### TICK-103 — Perf: mmap hashing + 1 MiB blocks
```yaml
ticket_id: "TICK-103"
title: "Switch hasher to 1 MiB blocks + mmap for large files"
type: "Feature"
execution_wave: 1
depends_on: ["TICK-002"]
scope:
  domain: "Core / Hasher"
  exclusive_write_files:
    - "dataforge/core/hasher.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.2"
    - "dataforge/core/config.py"  # hash_block_size added in TICK-004
architectural_context:
  existing_symbols_to_use:
    - "SUPPORTED_ALGORITHMS = ('md5','sha1','sha256','sha512','blake2b') (dataforge/core/hasher.py:6)"
    - "get_file_hash(filepath, algo, cancel_token), get_hashes(filepath, algos)"
  breaking_changes: "None — same API; BLOCK_SIZE becomes config-driven 1<<20"
requirements:
  summary: "Raise BLOCK_SIZE to 1<<20 (read from config hash_block_size), use mmap.mmap for files >16 MiB with posix_fadvise(WILLNEED)/madvise, keep hashlib API and SUPPORTED_ALGORITHMS + cancel_token checks per chunk. xxhash/blake3 remain optional prefilter (not added to SUPPORTED_ALGORITHMS). Keep get_hashes() single-pass for many algos."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN a 1 GiB file WHEN hashed THEN throughput is ≥ 400 MB/s on SSD (vs ~120 MB/s at 64 KiB) and cancel_token aborts mid-file"
    - "GIVEN get_file_hash(path, algo='sha256') WHEN algo is unsupported THEN raises ValueError"
    - "GIVEN get_hashes WHEN called with ['md5','sha256'] THEN single read, two digests match separate get_file_hash calls"
verification:
  test_target: "tests/test_hasher_mmap.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_hasher_mmap.py -q"
```

### TICK-104 — Perf: batched cache (executemany + PRAGMA + index)
```yaml
ticket_id: "TICK-104"
title: "Batch cache writes + WAL pragmas + composite index (impl for TICK-004 contract)"
type: "Feature"
execution_wave: 1
depends_on: ["TICK-004"]
scope:
  domain: "Core / Cache"
  exclusive_write_files:
    - "dataforge/core/cache.py"  # sequential re-entry: Wave 0 sig → Wave 1 impl
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.3"
    - "dataforge/core/config.py"  # cache_batch_size from TICK-004
architectural_context:
  existing_symbols_to_use:
    - "CacheManager.get_hash / set_hash (dataforge/core/cache.py:41,51)"
    - "threading.Lock serialization (dataforge/core/cache.py:17)"
  breaking_changes: "None — new method set_hash_many is additive; PRAGMAs are idempotent"
requirements:
  summary: "Implement set_hash_many(rows) via executemany + single commit (batch 1k = cache_batch_size), add PRAGMA synchronous=NORMAL, cache_size=-64000, and CREATE INDEX IF NOT EXISTS idx_hash_lookup ON file_hashes(algo,size,mtime). Keep single-connection+Lock for get_hash; concurrent ThreadPool 4 hashing must not hit 'database is locked'. This is the impl companion to TICK-004 contract (sequential same file, not same wave)."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN 100k set_hash_many WHEN flushed THEN 1 transaction not 100k fsyncs and WAL stays enabled (PRAGMA journal_mode=WAL)"
    - "GIVEN lookup by (path,size,mtime,algo) WHEN queried THEN uses index (EXPLAIN QUERY PLAN shows idx_hash_lookup)"
    - "GIVEN concurrent ThreadPool 4 hashing WHEN contending THEN no 'database is locked' and results match serial"
verification:
  test_target: "tests/test_cache_batch.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_cache_batch.py -q"
```

### TICK-105 — Fix: O(N²) collision + empty-dir + case-only rename
```yaml
ticket_id: "TICK-105"
title: "Fix collision O(N²), prune empty-dest, and case-only rename on case-insensitive FS"
type: "Bugfix"
execution_wave: 1
depends_on: ["TICK-002"]
scope:
  domain: "Core / Operations"
  exclusive_write_files:
    - "dataforge/core/operations/files.py"
  read_only_references:
    - "docs/reviews/AUDIT_REPORT.md"
    - "dataforge/core/operations/__init__.py"
architectural_context:
  existing_symbols_to_use:
    - "normalize_path, resolve_collision_path, transfer_path, rename_path (dataforge/core/operations/files.py:23,34,74,132)"
    - "OperationResult dataclass (dataforge/core/operations/files.py:13)"
  breaking_changes: "None — same signatures; internal pre-normalize + normcase"
requirements:
  summary: "Pre-normalize reserved_paths once per batch (lock-protected), lazily makedirs only on first success (and clean empty on total failure), and compare normcase(candidate) != normcase(current_path) for case-only renames. Addresses R-OPS-1/3/4/6."
  source_documents:
    - "docs/reviews/AUDIT_REPORT.md"
  acceptance_criteria:
    - "GIVEN 5k-item move WHEN resolve_collision_path is called THEN normalize_path count is O(N) not O(N²) (profiled via monkeypatch counter)"
    - "GIVEN all transfers fail WHEN transfer_path was called THEN no empty destination dir remains"
    - "GIVEN FOO.txt → foo.txt on case-insensitive FS WHEN renamed THEN result is foo.txt not foo_1.txt"
verification:
  test_target: "tests/test_operations_collision.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_operations_collision.py -q"
```

### TICK-106 — Perf: streaming content search via pool + mmap
```yaml
ticket_id: "TICK-106"
title: "Make search content path parallel, mmap-based, and shared with forensics"
type: "Feature"
execution_wave: 1
depends_on: ["TICK-003"]
scope:
  domain: "Modules / Search"
  exclusive_write_files:
    - "dataforge/modules/search.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.5"
    - "dataforge/api/schema.py [NEW FILE]"
architectural_context:
  existing_symbols_to_use:
    - "SearchQuery.set_content, matches, _check_content (dataforge/modules/search.py:123,166,200)"
    - "iter_search_files, search_files (dataforge/modules/search.py:217,251)"
    - "search_thread_workers config key (dataforge/core/config.py:22)"
  breaking_changes: "None — same query API; binary handling becomes opt-in --force-binary"
requirements:
  summary: "Unify search_files and forensics.keyword_search into one engine-shared path: mmap + bytes regex, binary-aware skip via python-magic (optional try-import), ThreadPool(search_thread_workers) (default min(32,cpu*2)), 1 MiB sliding window for regex, 10 MB cap, no open(...).readlines()."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN 50k-file corpus WHEN search --content runs THEN wall time is minutes→seconds and peak RSS stays < 200 MB (streaming)"
    - "GIVEN --error-format json with invalid --name-glob+--name-regex WHEN run THEN stderr JSON error and exit 2"
    - "GIVEN binary files WHEN content search without --force-binary THEN skipped unless mime is text"
verification:
  test_target: "tests/test_search_streaming.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_search_streaming.py -q"
```

### TICK-107 — Perf: pipelined dupes (streaming, verify)
```yaml
ticket_id: "TICK-107"
title: "Pipeline dupes: streaming size-map → fast-hash → full-hash with verify"
type: "Feature"
execution_wave: 1
depends_on: ["TICK-003"]
scope:
  domain: "Modules / Duplicates"
  exclusive_write_files:
    - "dataforge/modules/duplicates.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.4"
    - "dataforge/core/cache.py"  # set_hash_many from TICK-104
architectural_context:
  existing_symbols_to_use:
    - "find_duplicates, build_duplicate_records, order_duplicate_records (dataforge/modules/duplicates.py:17,30,157)"
    - "file_cache.get_hash/set_hash (dataforge/core/cache.py)"
  breaking_changes: "None — same return Dict[hash, List[FileEntry]]; streaming is internal"
requirements:
  summary: "No list(scan_directory); scanner thread(s) → queue.Queue[FileEntry] → streaming size-map → xxhash64(first 4KiB) prefilter → full sha256 only on collisions, via ThreadPool(min(32,cpu*4)); verify_content=True byte-compare on close hashes; emit queue of BatchActionRecord. Depends only on TICK-003 contract for wave-disjointness; logical scanner/hasher reuse is runtime queue order, not wave dependency."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
    - "docs/reviews/AUDIT_REPORT.md"
  acceptance_criteria:
    - "GIVEN 100k-file fixture WHEN find_duplicates runs THEN peak RSS is O(batch) not O(n) and list(scan) is gone from code (grep fails)"
    - "GIVEN two files same size + same xxhash but different sha256 WHEN grouped THEN not presented as duplicates (verify_content path)"
    - "GIVEN (st_dev,st_ino) equal WHEN grouped THEN counted once (no hardlink double-hash)"
verification:
  test_target: "tests/test_dupes_pipeline.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_dupes_pipeline.py -q"
```

### TICK-108 — Perf: streaming integrity snapshots
```yaml
ticket_id: "TICK-108"
title: "Stream integrity create/verify instead of materializing file lists"
type: "Feature"
execution_wave: 1
depends_on: ["TICK-003"]
scope:
  domain: "Modules / Integrity"
  exclusive_write_files:
    - "dataforge/modules/integrity.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.6"
architectural_context:
  existing_symbols_to_use:
    - "IntegrityMonitor.create_snapshot, verify_snapshot (dataforge/modules/integrity.py:72,137)"
    - "SUPPORTED_ALGORITHMS, get_file_hash (dataforge/core/hasher.py:6)"
  breaking_changes: "None — same snapshot JSON shape; atomic write via tmp+os.replace"
requirements:
  summary: "Replace list(scan_directory(...)) with streaming scan → queue → ThreadPool(min(32,cpu*4)) hash → executemany cache write; atomic snapshot.json write via tmp+os.replace. Keep legacy flat MD5 readable."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN 1M-file tree WHEN create_snapshot runs THEN peak RSS is O(batch) and snapshot is written atomically (no partial on cancel)"
    - "GIVEN legacy flat MD5 snapshot WHEN verify_snapshot runs THEN still readable (fallback to md5)"
    - "GIVEN cancel_token mid-verify WHEN set THEN returns promptly with cancelled flag"
verification:
  test_target: "tests/test_integrity_streaming.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_integrity_streaming.py -q"
```

### TICK-109 — Forensics hash/keyword: share engine path + F15 budget
```yaml
ticket_id: "TICK-109"
title: "Make forensics calc_hashes/keyword_search share streaming engine + byte budget"
type: "Feature"
execution_wave: 1
depends_on: ["TICK-003"]
scope:
  domain: "Modules / Forensics"
  exclusive_write_files:
    - "dataforge/modules/forensics.py"  # first writer; second is TICK-304 Wave 3
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.7"
    - "docs/reviews/FORENSIC_REVIEW.md"
architectural_context:
  existing_symbols_to_use:
    - "calculate_hashes, keyword_search, ingest_disk_image (dataforge/modules/forensics.py:45,369,431)"
    - "search_thread_workers config"
  breaking_changes: "None — same return shapes; streaming is internal"
requirements:
  summary: "Have calculate_hashes reuse TICK-103 mmap path; make keyword_search call the shared search engine with a global byte budget (10 MB × workers → bounded queue) instead of f.read(10MB) per file unbounded; ingest_disk_image streams queue to hash+artifacts+keyword without file_paths list; build_timeline reuses FileEntry timestamps (no os.stat redo)."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
    - "docs/reviews/FORENSIC_REVIEW.md"
  acceptance_criteria:
    - "GIVEN 4 workers × 10 MB WHEN keyword_search runs THEN peak RSS stays < 100 MB (budgeted streaming)"
    - "GIVEN ingest_disk_image WHEN grep -n file_paths on file THEN no file_paths list remains — streaming queue feeds stages"
    - "GIVEN build_timeline WHEN run THEN no second os.stat (reuses FileEntry timestamps)"
verification:
  test_target: "tests/test_forensics_streaming.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_forensics_streaming.py -q"
```

### TICK-201 — Service: parallel batch mutations + zip abort fix
```yaml
ticket_id: "TICK-201"
title: "Parallelize FileActionService + fix single-mode zip abort/partial"
type: "Bugfix"
execution_wave: 2
depends_on: ["TICK-105", "TICK-102"]
scope:
  domain: "Service / Batch"
  exclusive_write_files:
    - "dataforge/core/services/file_actions.py"
  read_only_references:
    - "docs/reviews/AUDIT_REPORT.md"
    - "dataforge/core/operations/files.py"
architectural_context:
  existing_symbols_to_use:
    - "FileActionService._run_batch_operation, transfer_items, archive_items (dataforge/core/services/file_actions.py:79,131,321)"
    - "OperationResult, BatchActionRecord, BatchActionOutcome"
  breaking_changes: "None — same BatchActionOutcome shape; internal ThreadPool is additive"
requirements:
  summary: "Add ThreadPool(min(16,cpu*2)) to transfer_items/delete_items/rename_items/archive_items(individual), lock reserved_paths, progress via atomic counter. Fix R-OPS-2: move try/except inside loop for per-item records, write to dest.tmp then os.replace, delete partial on cancel/failure, correct source_path on failure record. Keep archive single as single writer but hash/compress per file then write sequentially."
  source_documents:
    - "docs/reviews/AUDIT_REPORT.md"
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.10"
  acceptance_criteria:
    - "GIVEN single-mode zip with 1 bad file WHEN archive_items runs THEN other items still get records, partial .zip is removed, and failure record has correct source_path"
    - "GIVEN 10k-file move WHEN run THEN wall time tracks storage bandwidth not Python loop, and reserved_paths is thread-safe"
    - "GIVEN cancel_token mid-batch WHEN set THEN returns cancelled with partial records and no orphan zip"
verification:
  test_target: "tests/test_file_actions_parallel.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_file_actions_parallel.py -q"
```

### TICK-202 — Recovery: parallel carving via mmap chunks
```yaml
ticket_id: "TICK-202"
title: "Parallelize carving: mmap image, sliding-window scan, chunked workers"
type: "Feature"
execution_wave: 2
depends_on: ["TICK-102", "TICK-103"]
scope:
  domain: "Modules / Recovery"
  exclusive_write_files:
    - "dataforge/modules/recovery.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.8"
    - "docs/reviews/FORENSIC_REVIEW.md"
architectural_context:
  existing_symbols_to_use:
    - "carve_files_from_image, scan_trash, restore_from_trash (dataforge/modules/recovery.py:50,230,312)"
    - "SIGNATURES, identify_file_type (dataforge/modules/file_signatures.py)"
  breaking_changes: "None — same return dict with carved list; sliding window fixes sector-alignment miss"
requirements:
  summary: "mmap the image, scan 64 MiB windows with overlap = max(header+footer), run signature check in parallel chunks, write carved files to per-worker temp then atomic move. Fixes F6 sector-alignment miss and adds ~8× on large images."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
    - "docs/reviews/FORENSIC_REVIEW.md"
  acceptance_criteria:
    - "GIVEN a 500 GB image WHEN carved THEN wall time is days→hours and carved count matches single-thread baseline"
    - "GIVEN a header at byte offset not %512 WHEN scanning THEN still found (sliding window)"
    - "GIVEN cancel_token WHEN set THEN workers stop and no partial carved file is left"
verification:
  test_target: "tests/test_recovery_parallel.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_recovery_parallel.py -q"
```

### TICK-203 — System cleanup: dedupe walks + reuse scanner
```yaml
ticket_id: "TICK-203"
title: "Dedupe cleanup walks and reuse parallel scanner"
type: "Feature"
execution_wave: 2
depends_on: ["TICK-102"]
scope:
  domain: "Modules / System Cleanup"
  exclusive_write_files:
    - "dataforge/modules/system_cleanup.py"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.9"
architectural_context:
  existing_symbols_to_use:
    - "scan_junk_files, scan_browser_artifacts (dataforge/modules/system_cleanup.py:201,303)"
    - "_is_socket_or_fifo, _is_under_system_temp"
  breaking_changes: "None"
requirements:
  summary: "One scan_directory per category with max_depth=5 reuse instead of per-pattern os.walk; use DirEntry socket/FIFO check without extra stat; keep 1-day /tmp guard and user-supplied path non-blanket rule (S7)."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN browser artifact scan WHEN run THEN os.walk call count is O(categories) not O(categories×patterns)"
    - "GIVEN /tmp file <1 day old WHEN scanned THEN not classified as junk"
    - "GIVEN socket/FIFO WHEN scanned THEN never classified as junk"
verification:
  test_target: "tests/test_system_cleanup_walks.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_system_cleanup_walks.py -q"
```

### TICK-204 — Metadata: single cleaning seam
```yaml
ticket_id: "TICK-204"
title: "Consolidate metadata cleaning to MetadataEngine (keep cleaner.py as shim)"
type: "Refactor"
execution_wave: 2
depends_on: ["TICK-003"]
scope:
  domain: "Modules / Metadata"
  exclusive_write_files:
    - "dataforge/modules/metadata.py"
  read_only_references:
    - "docs/reviews/ROADMAP.md"
    - "dataforge/modules/cleaner.py"
architectural_context:
  existing_symbols_to_use:
    - "MetadataEngine.remove_metadata, read_metadata, write_metadata (dataforge/modules/metadata.py)"
    - "MetadataCleaner (dataforge/modules/cleaner.py) — will become shim"
  breaking_changes: "None — cleaner.py shim preserves import path; return type unified to dict"
requirements:
  summary: "Make MetadataEngine.remove_metadata the single source (exiftool→Pillow→pypdf→mutagen); cleaner.py::MetadataCleaner becomes a thin shim delegating to MetadataEngine. Addresses ARCH.2 (WS-F)."
  source_documents:
    - "docs/reviews/ROADMAP.md"
  acceptance_criteria:
    - "GIVEN cleaner.MetadataCleaner.remove_metadata(path) WHEN called THEN delegates to MetadataEngine and return type is dict (not bool)"
    - "GIVEN metadata.py shim missing WHEN imported THEN no circular import"
    - "GIVEN image+PDF fixtures WHEN stripped THEN payload is identical via either entry point"
verification:
  test_target: "tests/test_metadata_single_seam.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_metadata_single_seam.py -q"
```

### TICK-205 — Transport: UDS + Named Pipes (native primary local)
```yaml
ticket_id: "TICK-205"
title: "Implement UDS (Linux/macOS) + Named Pipes (Windows) transports"
type: "Feature"
execution_wave: 2
depends_on: ["TICK-003", "TICK-005"]
scope:
  domain: "Engine / Transport"
  exclusive_write_files:
    - "dataforge/api/transport/uds.py [NEW FILE]"
    - "dataforge/api/transport/named_pipe.py [NEW FILE]"
  read_only_references:
    - "docs/proposals/NATIVE_OS_API_REVIEW.md"
    - "dataforge/api/transport/base.py [NEW FILE]"
    - "dataforge/api/schema.py [NEW FILE]"
architectural_context:
  existing_symbols_to_use:
    - "Transport ABC send/recv/subscribe, auto_discover (from TICK-003)"
    - "Job, JobQueue (from TICK-005)"
  breaking_changes: "New optional dep pywin32 on Windows (sys_platform=='win32'); POSIX has no new dep"
requirements:
  summary: "Length-prefixed MessagePack JSON-RPC 2.0 over asyncio.start_unix_server (UDS, 0700, SO_PEERCRED check) and win32pipe/Proactor (Named Pipe, SDDL D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;AU)). auto_discover order: $DATAFORGE_ENGINE_SOCK → $XDG_RUNTIME_DIR/...sock → ~/Library/Application Support/...sock → \\.\pipe\… → http://127.0.0.1:8765 fallback."
  source_documents:
    - "docs/proposals/NATIVE_OS_API_REVIEW.md"
  acceptance_criteria:
    - "GIVEN no explicit env WHEN DataForge.connect() runs THEN auto_discover tries UDS→pipe→HTTP in order and connects to first available"
    - "GIVEN UDS at $XDG_RUNTIME_DIR/dataforge/engine.sock WHEN perms are 0777 THEN connection is rejected (expects 0700)"
    - "GIVEN a scan request WHEN sent over UDS and over Named Pipe THEN same JobEvent stream (progress/result) is observed"
verification:
  test_target: "tests/test_transport_uds_pipe.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_transport_uds_pipe.py -q"
```

### TICK-301 — Integration: daemon + auto-discovering client
```yaml
ticket_id: "TICK-301"
title: "Wire daemon job queue + client auto-discover (consolidation)"
type: "Integration"
execution_wave: 3
depends_on: ["TICK-205", "TICK-201"]
scope:
  domain: "Engine / Daemon"
  exclusive_write_files:
    - "dataforge/engine/daemon.py"  # sequential overwrite of Wave 0 stub
    - "dataforge/client/__init__.py [NEW FILE]"
    - "dataforge/client/sync.py [NEW FILE]"
    - "dataforge/service/__main__.py [NEW FILE]"
  read_only_references:
    - "docs/proposals/NATIVE_OS_API_REVIEW.md"
    - "dataforge/engine/jobs.py [NEW FILE]"
    - "dataforge/api/schema.py [NEW FILE]"
architectural_context:
  existing_symbols_to_use:
    - "JobQueue, Job (from TICK-005)"
    - "Transport.auto_discover (from TICK-003/TICK-205)"
    - "FileActionService (dataforge/core/services/file_actions.py)"
  breaking_changes: "None — daemon import still side-effect free; in_process fallback preserved"
requirements:
  summary: "Single-writer consolidation: JobQueue (asyncio + ThreadPool + ProcessPool for hash), daemon.py main loop, client/DataForge.connect() that wraps Transport.auto_discover and exposes scan/search/dupes/hash → Job with events() async iter. service/__main__.py entrypoint for dataforge-engine. Only ticket in this wave may write these four files."
  source_documents:
    - "docs/proposals/NATIVE_OS_API_REVIEW.md"
  acceptance_criteria:
    - "GIVEN daemon not running WHEN DataForge.connect(in_process=True) THEN falls back to in-process engine (no socket needed) and scan still works"
    - "GIVEN daemon running WHEN DataForge.connect() called THEN discovers UDS/pipe and job.events() streams progress → result"
    - "GIVEN two concurrent scan jobs WHEN queued THEN both run (no global is_busy drop) and each is cancellable independently"
verification:
  test_target: "tests/test_daemon_client_integration.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_daemon_client_integration.py -q"
```

### TICK-302 — Service lifecycle (systemd / launchd / Windows Service)
```yaml
ticket_id: "TICK-302"
title: "Install service lifecycle files (systemd user service + socket, launchd plist, Windows Service)"
type: "Integration"
execution_wave: 3
depends_on: ["TICK-301"]
scope:
  domain: "Service / Lifecycle"
  exclusive_write_files:
    - "dataforge/service/linux/dataforge.socket [NEW FILE]"
    - "dataforge/service/linux/dataforge.service [NEW FILE]"
    - "dataforge/service/linux/com.dataforge.Engine.service [NEW FILE]"
    - "dataforge/service/windows/service.py [NEW FILE]"
    - "dataforge/service/windows/install.py [NEW FILE]"
    - "dataforge/service/macos/com.dataforge.engine.plist [NEW FILE]"
  read_only_references:
    - "docs/proposals/NATIVE_OS_API_REVIEW.md#3.2"
    - "docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md"
    - "dataforge/service/__main__.py [NEW FILE]"
architectural_context:
  existing_symbols_to_use:
    - "dataforge-engine entrypoint (from TICK-301)"
    - "paths.runtime_dir (from TICK-001)"
  breaking_changes: "None — files are installed to user locations on demand; no system modification on import"
requirements:
  summary: "Ship systemd user socket+service (ListenStream=%t/dataforge/engine.sock, SocketMode=0700, ExecStart=%h/.local/bin/dataforge-engine), D-Bus service file for busctl, launchd plist for macOS, and pywin32 ServiceFramework for Windows SCM (NT SERVICE\\DataForge, Named Pipe SDDL). Enables systemctl --user status / sc query / launchctl list checks."
  source_documents:
    - "docs/proposals/NATIVE_OS_API_REVIEW.md"
  acceptance_criteria:
    - "GIVEN Linux WHEN systemd-analyze verify dataforge.service THEN no error and ListenStream is %t/dataforge/engine.sock with 0700"
    - "GIVEN Windows WHEN python -m dataforge.service.windows.install --help THEN prints sc create usage and SDDL D:(A;;GA;;;BA)"
    - "GIVEN macOS WHEN plutil -lint com.dataforge.engine.plist THEN exits 0"
verification:
  test_target: "tests/test_service_lifecycle.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_service_lifecycle.py -q"
```

### TICK-303 — Build: onefile+onedir + packaging
```yaml
ticket_id: "TICK-303"
title: "Produce onefile (portable) + onedir (package) + nfpm deb/rpm"
type: "Feature"
execution_wave: 3
depends_on: ["TICK-001"]
scope:
  domain: "Build / Packaging"
  exclusive_write_files:
    - "build_exe.py"
    - "packaging/nfpm.yaml [NEW FILE]"
    - "packaging/README.md [NEW FILE]"
  read_only_references:
    - "docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md"
    - "dataforge/core/paths.py [NEW FILE]"
architectural_context:
  existing_symbols_to_use:
    - "build_common_args, release_args, debug_args (build_exe.py:28,46,53)"
  breaking_changes: "None — new onedir_args() profile added alongside existing release/debug; CLI gains onedir choice"
requirements:
  summary: "Keep build_exe.py release (--onefile dist/release/DataForge) and add onedir profile (--onedir dist/onedir/DataForge/) for nfpm deb/rpm at /opt/dataforge/ + systemd --user units + .desktop. Do not yet touch wix/ (Windows) or dmg/ (macOS) — those are post-TICK-303 add-ons."
  source_documents:
    - "docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md"
  acceptance_criteria:
    - "GIVEN python build_exe.py release WHEN run THEN dist/release/DataForge exists and DataForge --help prints version"
    - "GIVEN python build_exe.py onedir WHEN run THEN dist/onedir/DataForge/DataForge exists and startup is < 1s (no unpack)"
    - "GIVEN nfpm pkg --packager deb WHEN run THEN dataforge_0.2.0_amd64.deb contains /opt/dataforge/DataForge + dataforge.socket/service"
verification:
  test_target: "tests/test_packaging_nfpm.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_packaging_nfpm.py -q"
```

### TICK-304 — Forensic: audit log + Evidence Mode + provenance
```yaml
ticket_id: "TICK-304"
title: "Add hash-chained audit log, CaseContext, and Evidence Mode gate (F1–F3/U2 + F9)"
type: "Feature"
execution_wave: 3
depends_on: ["TICK-005", "TICK-109"]
scope:
  domain: "Forensic / Soundness"
  exclusive_write_files:
    - "dataforge/core/audit.py [NEW FILE]"
    - "dataforge/core/case.py [NEW FILE]"
    - "dataforge/modules/forensics.py"  # sequential second writer after TICK-109
  read_only_references:
    - "docs/reviews/FORENSIC_REVIEW.md"
    - "docs/reviews/AUDIT_REPORT.md"
architectural_context:
  existing_symbols_to_use:
    - "FileActionService (dataforge/core/services/file_actions.py:67)"
    - "generate_forensic_report (dataforge/modules/forensics.py:550)"
    - "Job table hook (from TICK-005)"
  breaking_changes: "None — new modules; forensics.py second write is additive (provenance, UTC fix)"
requirements:
  summary: "Append-only 0o600 job DB (WAL, hash(prev||canonical_json) chain), CaseContext (case/operator/host/image-hash), FileActionService Evidence Mode gate (--evidence-mode returns success=False with no FS change), and UTC ISO-8601 everywhere (generate_forensic_report:563 fixed to timezone.utc). Seals F1/F2/F3/U2/F9/F11 in one seam to avoid scattered writes."
  source_documents:
    - "docs/reviews/FORENSIC_REVIEW.md"
    - "docs/reviews/AUDIT_REPORT.md"
  acceptance_criteria:
    - "GIVEN audit log with 10k entries WHEN one byte is tampered THEN audit.verify() fails and forensic command refuses to run"
    - "GIVEN CaseContext.evidence_mode=True WHEN FileActionService.transfer/delete is called THEN returns success=False and leaves FS unchanged"
    - "GIVEN generate_forensic_report WHEN run THEN report contains {operator, host, source_sha256, case_id, audit_tail_hash, tool_version} and report_generated is UTC ISO-8601"
verification:
  test_target: "tests/test_audit_evidence_mode.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_audit_evidence_mode.py -q"
```

### TICK-401 — Integration: UI job manager + virtualized tables
```yaml
ticket_id: "TICK-401"
title: "Replace single BackgroundWorker is_busy with JobManager + virtualized views"
type: "Integration"
execution_wave: 4
depends_on: ["TICK-301", "TICK-304"]
scope:
  domain: "UI / Shell"
  exclusive_write_files:
    - "dataforge/ui/app.py"
    - "dataforge/ui/job_manager.py [NEW FILE]"
  read_only_references:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md#1.11"
    - "dataforge/client/__init__.py [NEW FILE]"
    - "dataforge/engine/jobs.py [NEW FILE]"
architectural_context:
  existing_symbols_to_use:
    - "DataForgeApp, BackgroundWorker(QThread), is_busy, run_background (dataforge/ui/app.py:114,186,789)"
    - "Job, JobQueue, JobStatus"
  breaking_changes: "None — JobManager keeps same progress_callback shape; QTreeView virtualization is opt-in per view"
requirements:
  summary: "Single-writer UI consolidation: JobManager {job_id→Job} (queue depth 8, per-job cancel), QTreeView + QAbstractItemModel virtualization for Search/Dupes (no 500k QTreeWidgetItem), job.events → progress_signal bridge. Extract JobManager to job_manager.py to keep app.py diff reviewable; only ticket in Wave 4 may write app.py."
  source_documents:
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
    - "docs/reviews/ROADMAP.md"
  acceptance_criteria:
    - "GIVEN two run_workflow calls WHEN second is issued THEN not dropped with 'Busy' — queued and both progress streams update"
    - "GIVEN 500k-row result WHEN rendered THEN peak RSS stays < 500 MB and scroll is smooth (no 500k item allocation)"
    - "GIVEN Evidence Mode on WHEN destructive button is clicked THEN button is setEnabled(False) and status shows 'EVIDENCE MODE — writes blocked'"
verification:
  test_target: "tests/test_ui_job_manager.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_ui_job_manager.py -q"
```

### TICK-402 — Integration: version sync (sole writer to pyproject)
```yaml
ticket_id: "TICK-402"
title: "Centralize version bump (pyproject → __init__ → Info.plist/wxs)"
type: "Integration"
execution_wave: 4
depends_on: ["TICK-001", "TICK-303"]
scope:
  domain: "Build / Release"
  exclusive_write_files:
    - "scripts/bump_version.py [NEW FILE]"
    - "pyproject.toml"  # sole writer this wave (TICK-001 no longer writes pyproject)
  read_only_references:
    - "docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md"
    - "dataforge/__init__.py"
architectural_context:
  existing_symbols_to_use:
    - "__version__ via importlib.metadata (dataforge/__init__.py) from TICK-001"
    - "pyproject.toml:8 version = 0.1.0"
  breaking_changes: "None — version bump is idempotent and checks via --check"
requirements:
  summary: "Sole-writer consolidation for version: scripts/bump_version.py syncs pyproject.toml:version → dataforge/__init__.__version__ → wix/Product.wxs + Info.plist. No other ticket in this wave may write pyproject.toml."
  source_documents:
    - "docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md"
  acceptance_criteria:
    - "GIVEN python scripts/bump_version.py 0.2.0 WHEN run THEN pyproject.toml, dataforge/__init__.py, and wix/Product.wxs all report 0.2.0"
    - "GIVEN fm --version and dataforge-engine --version WHEN run THEN print same string"
    - "GIVEN version bump WHEN python -m build runs THEN version in dist/*.whl matches"
verification:
  test_target: "tests/test_version_sync.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_version_sync.py -q && python scripts/bump_version.py --check"
```

---

## Appendix — Performance alias map (do not run twins same wave)

| PERF alias | Hardened to | Wave | Exclusive file (hardened) |
|---|---|---|---|
| `PERF-100` | merged into `TICK-004` | 0 | `config.py` adaptive workers — no separate agent |
| `PERF-001c` | `TICK-002` | 0 | `common.py`+`provider.py` |
| `PERF-101` | `TICK-102` | 1 | `scanner.py` |
| `PERF-102` | `TICK-103` | 1 | `hasher.py` |
| `PERF-103` | merged into `TICK-104` | 1 | `cache.py` |
| `PERF-104` | `TICK-107` | 1 | `duplicates.py` |
| `PERF-105` | `TICK-106` | 1 | `search.py` |
| `PERF-106` | `TICK-108` | 1 | `integrity.py` |
| `PERF-107` | `TICK-109` | 1 | `forensics.py` |
| `PERF-108` | `TICK-202` | 2 | `recovery.py` |
| `PERF-109` | `TICK-203` | 2 | `system_cleanup.py` |
| `PERF-110` | `TICK-201` | 2 | `file_actions.py` |
| `PERF-111` | `TICK-105` | 1 | `operations/files.py` |
| `PERF-112` | `TICK-401` | 4 | `ui/app.py` |
| `PERF-113` | deferred — `engine/index.py [NEW FILE]` at `TICK-303` post follow-on | 3+ | `engine/index.py` |
| `PERF-114` | polish — `hasher.py`+`native/` at follow-on after `TICK-103` | 3+ | `hasher.py`, `native/Cargo.toml` |

