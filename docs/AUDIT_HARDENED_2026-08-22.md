# Hardened Audit — Documentation Index & Parallel Backlog vs. Codebase Reality

**Date:** 2026-08-22 · **Auditor role:** Principal Technical Auditor & System Code Reviewer  
**Scope:** `docs/CONSOLIDATED_SPEC.md`, `docs/PARALLEL_BACKLOG.md`, `docs/proposals/PERFORMANCE_TICKETS.md` vs `dataforge/` HEAD (v0.1.0, `pyproject.toml:8`), `dataforge/{core,modules,ui,cli}.py`  
**Toolchain verified:** `requirements-dev.txt:4` = `pytest`, `pytest-cov`; `pyproject.toml` has no `dotnet`/`npm`/`cargo` test config — all `validation_command` must be `pytest`/`python -m pytest`.

---

## 1. Audit Method

1. `find dataforge -type f | sort` + `read` every `exclusive_write_files` path.
2. `grep` every referenced symbol (`FileEntry`, `FileProvider`, `CONFIG_SCHEMA_VERSION`, `set_hash_many`, `SUPPORTED_ALGORITHMS`, `is_busy`, `BackgroundWorker`) against live definitions.
3. Cross-wave disjoint analysis: `exclusive_write_files` intersection per integer `execution_wave`.
4. Contract completeness: every Wave 1+ import must resolve to a Wave 0 file.

---

## 2. Discrepancy Report

| Ticket ID | Issue Type | Codebase Finding | Correction Applied |
|---|---|---|---|
| `TICK-001` | **Invalid Path / Shared bottleneck** — `pyproject.toml` | `pyproject.toml:8` exists with `version = 0.1.0`. Backlog made `TICK-001` (Wave 0) **and** `TICK-402` (Wave 4) both writers to `pyproject.toml`. Same file across waves is sequential but violates *single-writer consolidation* principle for version. Also `dataforge/core/paths.py` is `[NEW FILE]` not marked with marker and `dataforge/__init__.py` is empty (no `__version__`). | Removed `pyproject.toml` from `TICK-001`; `TICK-001` now only writes `dataforge/core/paths.py [NEW FILE]` + `dataforge/__init__.py` (adds `__version__` via `importlib.metadata`) + `dataforge/core/__init__.py` export. `pyproject.toml` is **sole writer** `TICK-402` Wave 4. Added `[NEW FILE]` markers. |
| `TICK-002` | **Symbol drift / Incomplete contract** — `FileProvider` | Live `dataforge/core/provider.py:4` has `FileProvider` with 3 abstract methods (`list_files`, `move`, `copy`). Backlog claimed `list_files_parallel, stat, open, hash, hash_many` (5) with `cancel_token`/`progress_callback`. Signature mismatch would break `mypy` and `LocalProvider`. | Hardened contract now lists **exact 7** methods: `list_files`, `list_files_parallel`, `stat`, `open`, `hash`, `hash_many`, `exists` — all with `cancel_token: Optional[threading.Event]` + `progress_callback` where applicable. `LocalProvider` shim updated to delegate to new `scanner`/`hasher` contracts. |
| `TICK-003` | **Invalid Path** — `dataforge/api/**` | `dataforge/api/` directory **does not exist** (`find` shows no `api/`). Both files were listed without `[NEW FILE]` marker. Also backlog implied `pydantic` DTOs but `pyproject.toml:9` and `requirements.txt` have **no** `pydantic`/`fastapi` — runtime would ImportError. | Marked both as `[NEW FILE]` and added `dataforge/api/__init__.py [NEW FILE]`, `dataforge/api/transport/__init__.py [NEW FILE]`. Added `pydantic>=2` to `requirements:` as non-breaking contract addition (Wave 0 may add dep). |
| `TICK-004` | **Missing prerequisite / Wave collision** | Backlog had `TICK-004` Wave 0 writing `dataforge/core/config.py` + `cache.py` in **parallel** with `TICK-001` which creates `paths.py` that `config.py`/`cache.py` must import. No `depends_on` → race. Also `dataforge/engine/migrations/README.md` parent `dataforge/engine/` does not exist. | Added `depends_on: ["TICK-001"]` to `TICK-004`. Added `dataforge/engine/__init__.py [NEW FILE]` creation to `TICK-005` and noted `engine/` dir creation via `engine/__init__.py`. |
| `TICK-004` cont. | **Incomplete contract** | `CONFIG_SCHEMA_VERSION` and `set_hash_many` signatures were described but not typed; `cache.py` live has no `PRAGMA user_version` read/write. Tests would not know shape of `rows: list[tuple[path,size,mtime,hash,algo]]`. | Hardened to `CONFIG_SCHEMA_VERSION: int = 2`, `MIGRATIONS: dict[int,str]` and `def set_hash_many(self, rows: list[tuple[str,int,float,str,str]]) -> None` with doc. Added `PRAGMA user_version` contract. |
| `TICK-005` | **Invalid Path / Missing dir** | `dataforge/engine/jobs.py`, `daemon.py` both `[NEW FILE]` but no `engine/__init__.py`. Also `engine/daemon.py` was listed as both Wave 0 stub **and** Wave 3 full implementation without sequential note. | Split: Wave 0 `TICK-005` creates stub `daemon.py` (`if __name__` guard) + `jobs.py` + `__init__.py`; Wave 3 `TICK-301` is **sole writer** that overwrites `daemon.py` with full implementation (sequential re-entry documented). |
| `TICK-101` | **Correct — verified** | `dataforge/core/logger.py:23` indeed `StreamHandler(sys.stdout)` — corrupts `fm --format json`. | No change. Validation kept: `fm dupes --format json \| python -m json.tool` on stderr. |
| `TICK-102` | **Verified / Symbol ok** | `dataforge/core/scanner.py:6` double-stat via `os.stat(path)` confirmed; `FileEntry` at `common.py:5` lacks `st_ino/st_dev/st_blocks`. | Hardened to note `entry.stat(follow_symlinks=False)` reuse and add `st_ino: int = 0, st_dev: int = 0, st_blocks: int = 0` with `0` default for backward compat (Wave 0 adds fields). |
| `TICK-103` | **Verified / Minor drift** | `BLOCK_SIZE = 65536` and `SUPPORTED_ALGORITHMS = ('md5','sha1','sha256','sha512','blake2b')` confirmed. No `hash_block_size` in config yet. | No path change; hardened acceptance to keep `SUPPORTED_ALGORITHMS` unchanged (no `xxhash` added to tuple — `xxhash` is internal prefilter, not public algo). |
| `TICK-104` | **Missing Work Package + Contradictory file map** | Concurrency Map row said `*split from TICK-004 by wave* → actually cache_batch.py (new)` while `exclusive_write_files` implied `cache.py`. No `### TICK-104` section existed (jumped 103→105). `tests/test_cache_batch.py` would be `[NEW FILE]` not marked. | Added complete `TICK-104` package. `exclusive_write_files: ["dataforge/core/cache.py"]` with note **sequential re-entry** after `TICK-004` Wave 0 (Wave 0 stub sig, Wave 1 impl). Added `dataforge/engine/migrations/*` note to `TICK-004` not `TICK-104`. |
| `TICK-105` | **Verified** | `resolve_collision_path:39` does `{normalize_path(path) for path in reserved_paths}` per call → caller `file_actions._run_batch_operation` rebuilds set per item → O(N²). `transfer_path:102` `makedirs` before success. `rename_path:143` `if new_name == current_name: return None` misses `normcase` case-only on Windows. | No path change; hardened to require `normcase` check and lazy `makedirs`. |
| `TICK-106` / `PERF-105` | **Symbol drift** | Live `search.py:200` uses `open(..., 'r', errors='ignore')` line loop + `os.path.getsize>10MB` check. No `python-magic` mime, no `mmap`, no pool. `search_thread_workers` config exists but unused. | Hardened to reuse `PERFORMANCE_TICKETS PERF-105` spec but ensure import is `import magic` optional (guard `try: import magic`). |
| `TICK-109` | **Redundant scan verified** | `forensics.py:486` `file_paths = []` materializes full scan; `keyword_search:351` does `f.read(10*1024*1024)` per file unbounded; `build_timeline:763` does `os.stat(entry.path)` redo. | Hardened acceptance: `grep -n "file_paths"` must absent after fix (streaming queue). |
| `TICK-201` | **Verified** | `file_actions.py:79` sequential `for index, item in enumerate...` confirmed; `archive_items:357` outside-loop `try` appends one record with `destination` as `source_path` (R-OPS-2/3). No lock on `reserved_paths`. | No path change; hardened acceptance adds `reserved_paths` lock + `dest.tmp` + `os.replace`. |
| `TICK-204` | **Already partially implemented?** | `modules/cleaner.py:5` has `MetadataCleaner` (Pillow/pypdf/Mutagen) and `modules/metadata.py` has `MetadataEngine` — two seams. Task claims keep `cleaner.py` as shim — verified not yet shim (both implement separately). Not redundant. | Corrected description: `cleaner.py` is **not** yet shim — this ticket **makes** it shim. |
| `TICK-205` | **Invalid Path / Missing dep** | `dataforge/api/transport/uds.py`, `named_pipe.py` parents do not exist; also `asyncio.start_unix_server` + `win32pipe` require `pywin32` not in `requirements.txt`. | Marked `[NEW FILE]` plus `__init__.py`; added dependency note `pywin32; sys_platform=="win32"` optional. |
| `TICK-301` | **Shared bottleneck / Sequential re-entry** | `engine/daemon.py` second writer after `TICK-005`. `dataforge/client/__init__.py` and `service/__main__.py` both `[NEW FILE]`. | Documented as **consolidation wave single-writer**: only ticket in Wave 3 may write those three files. |
| `TICK-302` | **Missing Work Package** | Listed in Concurrency Map but package body truncated to `> **Wave 3 also holds...**` — no yaml. Launch path would fail. | Added complete `TICK-302` yaml with `exclusive_write_files` listing each new service file as `[NEW FILE]`. |
| `TICK-303` | **Hallucinated build profile** | `build_exe.py:46` only has `release` (`--onefile`) and `debug` (`--onedir --debug=all`). No `onedir` production profile; backlog claimed `build_exe.py onedir` exists. Also `packaging/nfpm.yaml` parent missing. | Split `build_exe.py` edits: add `def onedir_args()` profile (distinct from `debug`). Marked `packaging/nfpm.yaml [NEW FILE]`, `packaging/README.md [NEW FILE]`. |
| `TICK-304` | **Collision — same file different wave** | Writes `modules/forensics.py` again after `TICK-109` Wave 1. Within-wave disjoint ok, but doc did not note sequential re-entry, implying parallel safety. Also `core/audit.py`, `core/case.py` both `[NEW FILE]`. | Documented as sequential re-entry (Wave 1 → Wave 3). Hardened to ensure only `TICK-304` in Wave 3 writes those three. |
| `TICK-401` / `PERF-112` | **Shared bottleneck isolation** | `dataforge/ui/app.py:186` `is_busy` + single `BackgroundWorker(QThread)` confirmed. Backlog correctly isolates to Wave 4 single-writer — valid. | Kept isolation; hardened `exclusive_write_files` to `["dataforge/ui/app.py"]` sole writer Wave 4 plus new `dataforge/ui/job_manager.py [NEW FILE]` to keep `app.py` diff small (extract). |
| `TICK-402` | **Shared bottleneck — version** | As `TICK-001` row, `pyproject.toml` second writer. Also `scripts/bump_version.py` parent `scripts/` missing. | Kept as sole writer to `pyproject.toml` Wave 4; marked `scripts/bump_version.py [NEW FILE]`, `packaging/wix/* [NEW FILE]` etc. |
| `PERF-100` | **File Collision same wave** | `PERF-100` Wave 0 writes `dataforge/core/config.py` while `TICK-004` Wave 0 also writes `config.py` — same wave collision. | **Merged into `TICK-004`** — removed standalone `PERF-100` agent. Adaptive workers (`min(32,cpu*4)`, `hash_block_size=1<<20`, `cache_batch_size=1000`) now part of `TICK-004` acceptance. `PERF-100` kept as alias note, no separate PR. |
| `PERF-101` | **Collision** | `PERF-101` Wave 1 listed `exclusive_write_files: ["dataforge/core/scanner.py", "dataforge/core/common.py"]` — `common.py` already owned by `PERF-001c` (`TICK-002`) Wave 0 contract. Second write to `common.py` in Wave 1 breaks contract-first. | Corrected to `["dataforge/core/scanner.py"]` only; `common.py` fields (`st_ino/st_dev/st_blocks`) stay Wave 0 `TICK-002/PERF-001c`. |
| `PERF-103` | **Duplicate ticket** | `PERF-103` Wave 1 `cache.py` duplicates `TICK-104` Wave 1 impl — would require two agents editing same file same wave. | Merged into `TICK-104`; `PERF-103` kept as alias, not separate agent. |
| `PERF-104` | **Wave-internal dependency violation** | Dependency listed `["PERF-101","PERF-102","PERF-103"]` but all in same Wave 1 → DAG requires deps be in earlier wave. Agent would import unmerged symbols. | Corrected to `depends_on: ["TICK-002"]` (contract only). Logical pipeline order noted as **runtime** queue order, not wave dependency. |
| `PERF-114` | **Same-file same-wave risk** | `PERF-114` Wave 3 lists `dataforge/core/hasher.py` while no other Wave 3 ticket writes hasher — sequential after `TICK-103` Wave 1 is ok, but backlog had `native/Cargo.toml` without dir `native/` existing and without `[NEW FILE]`. | Split to `dataforge/core/hasher.py` (polish) **and** `native/Cargo.toml [NEW FILE]` + `native/src/lib.rs [NEW FILE]` but documented as **same agent** (one ticket) so no intra-wave collision. Bumped to Wave 3 (not Wave 1) correctly sequenced after `TICK-103`. |
| `CONSOLIDATED_SPEC.md:13` | **Hallucination — blake3 present** | Spec says `hashlib/xxhash/blake3 (future)` — correctly marked future, but `pyproject.toml`/`requirements.txt` have no `blake3` nor `xxhash`. Not shipped. | Hardened note: `blake3`/`xxhash` are **optional** (`pip install dataforge[hash-accel]`) — `hasher.py` must fallback to `hashlib` if absent. |
| `CONSOLIDATED_SPEC.md:158` | **Hallucination — engine already exists** | Spec §6 says `extract engine/ lib` as proposed evolution — but some tables implied `engine/daemon.py` exists. | Added explicit `> Status: PROPOSAL` banner to evolution paragraph (already present but hardened). |
| `PERFORMANCE_TICKETS.md` general | **Validation command drift** | Some `completion_criteria` used `bench` script that does not exist (`scripts/bench.py` proposed only). | Hardened to `pytest <target> -q` plus `python -m py_compile` where bench not yet landed; noted bench harness is `TICK-004` dependency for perf tickets. |
| `PARALLEL_BACKLOG.md` general | **Missing `[NEW FILE]` markers** | ~18 paths missing marker per audit dimension 1 (file-system parity). | All new paths now carry ` [NEW FILE]` suffix in hardened backlog. |

---

## 3. Concurrency Hardening Summary

- **Wave 0 (Contracts) — 5 agents, disjoint:** `paths.py`+`__init__.py` (TICK-001) | `provider.py`+`common.py` (TICK-002) | `api/schema.py`+`transport/base.py` (TICK-003) | `config.py`+`cache.py`+`migrations/README` (TICK-004, now depends on TICK-001) | `engine/jobs.py`+`daemon stub`+`engine/__init__.py` (TICK-005). No file appears twice in Wave 0.

- **Wave 1 (Parallel fixes, all depend only on Wave 0) — 9 agents, disjoint:** `logger.py` (101) | `scanner.py` (102) | `hasher.py` (103) | `cache.py` impl (104, sequential after 004) | `operations/files.py` (105) | `search.py` (106) | `duplicates.py` (107) | `integrity.py` (108) | `forensics.py` hash/keyword (109). `cache.py` appears in Wave 0 (sig) and Wave 1 (impl) — documented sequential re-entry, **not** same wave.

- **Wave 2 — 5 agents, disjoint:** `file_actions.py` (201) | `recovery.py` (202) | `system_cleanup.py` (203) | `metadata.py` (204) | `transport/uds.py`+`named_pipe.py` (205).

- **Wave 3 — 4 agents, disjoint, consolidation of central files:** `daemon.py`+`client/__init__.py`+`service/__main__.py` (301, sole writer to daemon) | `service/linux/*,windows/*,macos/*` (302) | `build_exe.py`+`packaging/nfpm.yaml` (303) | `audit.py`+`case.py`+`forensics.py` (304, sequential second write to forensics after 109).

- **Wave 4 — 2 agents, disjoint:** `ui/app.py`+`ui/job_manager.py` (401, sole writer to `app.py`) | `scripts/bump_version.py`+`pyproject.toml` (402, sole writer to `pyproject.toml`).

- **Performance tickets:** `PERF-100` and `PERF-103` merged into `TICK-004`/`TICK-104`; remaining `PERF-*` are aliases to `TICK-*` — pick one set per run, never run both twins same wave.

---

## 4. Execution Completeness Fixes

- Every `acceptance_criteria` rewritten to deterministic `GIVEN/WHEN/THEN` with observable file or exit-code.
- Every `test_target` is `tests/test_*.py` (new files marked `[NEW FILE]`) and `validation_command` is `python -m pytest <test> -q` or `pytest <test> -q` — matching `requirements-dev.txt:4` (`pytest`).
- Added `architectural_context.existing_symbols_to_use` + `breaking_changes` to each package (required schema).

---

*Hardened backlog follows in `docs/PARALLEL_BACKLOG.md` (v2) and `docs/proposals/PERFORMANCE_TICKETS.md` (v2). This file is the audit trail.*
