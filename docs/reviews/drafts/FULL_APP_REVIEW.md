# Full Application Review — DataForge — DRAFT

> **Status: DRAFT — sections 3+ pending.** Only §0 Findings Index + §1 Core + §2 Operations/Service are complete (R-CORE-1..9, R-OPS-1..7). Remaining sections (modules, UI, packaging, tests) are unwritten. Treat open findings as verified for their sections only; do not treat the doc as a whole-app sign-off. Located in `reviews/drafts/` until complete.

**Date:** 2026-08-22
**Scope:** Entire `dataforge/` package (core, operations, services, actions, modules, CLI, UI) reviewed section by section for bugs, correctness issues, security issues, and performance problems.
**Method:** Fresh line-level source review, informed by (but not limited to) the existing audit trail:

- [`AUDIT_REPORT.md`](../AUDIT_REPORT.md) — S1–S13 (reported fixed), H1/M1–M6/L1–L9 (fixed)
- [`FORENSIC_REVIEW.md`](../FORENSIC_REVIEW.md) — F1–F21 / U1–U11 (known open architectural backlog)
- [`ROADMAP.md`](../ROADMAP.md) — ARCH.1–ARCH.6 (WS-F open)
- [`AUDIT_REPORT.md`](../AUDIT_REPORT.md), [`README.md`](../README.md), [`ROADMAP.md`](../ROADMAP.md)

**Goal of this document:** find issues **not already covered** by the trackers above, verify that "fixed" claims hold in the current source, and record every finding immediately per section so nothing is lost.

**Finding ID convention:** `R-<section>-<n>` (e.g., `R-CORE-1`). Severity: 🔴 High (data loss/crash/security), 🟠 Medium (real defect under realistic conditions), 🟡 Low (hygiene/robustness), 🔵 Info (observation/no action required). Status: ⏳ Open / ✅ Verified-fixed (prior claim re-verified).

---

## 0. Findings Index

| ID | Severity | Section | Title | Status |
| --- | --- | --- | --- | --- |
| R-CORE-1 | 🟠 High | Core / CLI | Logger writes to stdout → corrupts every JSON/JSONL CLI output; documented `\| jq` workflow fails | ⏳ Open (verified) |
| R-CORE-2 | 🟠 Medium | Core / Scanner | Config validation misses list item types → non-string `excluded_extensions` / unhashable `excluded_folders` crash **every** scan | ⏳ Open (verified) |
| R-CORE-3 | 🟡 Low | Core / Config | Runtime-only config keys (`collapsed_groups`) silently dropped on reload → sidebar collapse state never persists across restarts | ⏳ Open (verified by code trace) |
| R-CORE-4 | 🟡 Low | Core / Cache | If SQLite init fails, `conn=None`; `get_hash` raises `AttributeError` (uncaught) inside worker threads | ⏳ Open |
| R-CORE-5 | 🟡 Low | Core / Cache | One commit (fsync) per cached hash → large duplicate scans are I/O-bound; batching possible | ⏳ Open |
| R-CORE-6 | 🟡 Low | Core / Scanner | Nonexistent/unreadable root yields silent "no results" — indistinguishable from an empty tree | ⏳ Open |
| R-CORE-7 | 🟡 Low | Core / Logger | `setup_logger` crashes (`makedirs("")`) if called with a bare filename lacking a directory component | ⏳ Open |
| R-CORE-8 | 🔵 Info | Core / Hasher | `get_hashes()` does not validate algorithms (unlike `get_file_hash`) — arbitrary strings raise `AttributeError` | ⏳ Open |
| R-CORE-9 | 🔵 Info | Core | Known issues re-confirmed in current source: `created_at`=st_ctime mislabel (F14), naive timestamps (F9), dead `LocalProvider` (ARCH.3), `find_duplicates` stores sha256 in `entry.md5` field | Known/tracked |
| R-OPS-1 | 🟡 Medium | Operations / Service | Collision resolution is O(N²): shared `reserved_paths` re-normalized per item → multi-thousand-item batches waste seconds of CPU | ⏳ Open |
| R-OPS-2 | 🟠 Medium | Service / Archive | Single-mode archive aborts entirely on one bad file; partial `.zip` left on disk; remaining items get no records; Cancel also leaves partial zip | ⏳ Open |
| R-OPS-3 | 🟡 Low | Service / Archive | `archive_items` overwrites an existing destination zip without collision resolution (inconsistent with move/copy/rename rules) | ⏳ Open |
| R-OPS-4 | 🟡 Low | Operations / Transfer | `os.makedirs(destination_dir)` runs before the first successful transfer — failed transfers leave empty directories behind | ⏳ Open |
| R-OPS-5 | 🔵 Info | Operations / Delete | Permanent delete (`safe_mode=False`) uses `os.remove`, which cannot remove directories — folder deletion in permanent mode always fails with an error record (arguably safe, but undocumented) | ⏳ Open |
| R-OPS-6 | 🔵 Info | Operations / Rename | Case-only renames (`FOO.txt`→`foo.txt`) on case-insensitive filesystems become `foo_1.txt` because `resolve_collision_path` sees the target as existing | ⏳ Open |
| R-OPS-7 | 🔵 Info | Service | Regex errors from `rename_items_with_regex` (`re.compile`) propagate out of the service uncaught — callers must pre-validate (checked per-caller in Sections 7–9) | ⏳ Open |

<!-- Rows are appended as each section is completed. -->

---

## Section 1 — Core primitives (`dataforge/core/`)

*Files: `common.py`, `scanner.py`, `config.py`, `cache.py`, `hasher.py`, `logger.py`, `utils.py`, `provider.py`*

**Review status:** ✅ Complete

### Findings

#### R-CORE-1 — 🟠 Log lines corrupt machine-readable CLI output *(verified)*
- **Where:** `dataforge/core/logger.py:23` (console `StreamHandler(sys.stdout)`) + `dataforge/core/config.py:69` (INFO log at import/load time) + every module that logs during command execution (`duplicates.py:159,180,204,238` …).
- **Affects:** All `fm` commands with `--format json/jsonl` or JSON error output; README.md:142 documents exactly this workflow (`fm dupes --format jsonl | jq '.path' | xargs rm`).
- **Evidence:** Reproduced on current source:
  ```
  $ PYTHONPATH=. python -m dataforge.cli dupes /tmp/x --format json 2>/dev/null | python -c 'import json,sys; json.load(sys.stdin)'
  json.decoder.JSONDecodeError: Extra data: line 1 column 5
  ```
  stdout contains `2026-08-22 ... - dataforge - INFO - Starting duplicate scan ...` interleaved before/around the JSON payload.
- **Why:** Every scripting/integration consumer of the CLI breaks; piped output can even be *silently wrong* for consumers that ignore parse errors (e.g. `xargs rm` receiving garbage lines).
- **How:** Send the console handler to `sys.stderr` (keep file handler as-is), or disable the stream handler when a Click context is in JSON mode. Add a regression test asserting `json.loads(stdout)` succeeds for `dupes/search --format json`.

#### R-CORE-2 — 🟠 Incomplete config validation bricks all scans *(verified)*
- **Where:** `dataforge/core/config.py:107-108` — `_validate_one` checks only `isinstance(val, list)` for `excluded_extensions` / `excluded_folders` / `dashboard_paths`, never item types. Consumed at `dataforge/core/scanner.py:35-39,61-67`.
- **Evidence:** With `config.json` containing `"excluded_extensions": [123]`:
  ```
  TypeError: tuple for endswith must only contain str, not int
  ```
  With `"excluded_folders": [{"a": 1}]`:
  ```
  TypeError: cannot use 'dict' as a set element (unhashable type: 'dict')
  ```
  Both raise from *every* `scan_directory` call → search/duplicates/organize/dashboard all fail. This is a gap in the S10 fix ("validate config types"): container validated, items not.
- **Why:** `~/.dataforge/config.json` is user-editable and written by multiple code paths; one bad value turns the whole app into "scan returns nothing/crashes" with only a raw traceback to explain.
- **How:** Validate items: all members must be `str` (and non-empty); drop or coerce invalid items with a warning. Extend `test_config_merge_validates_and_clamps_bad_values`.

#### R-CORE-3 — 🟡 `collapsed_groups` never survives restart
- **Where:** `dataforge/core/config.py:77` (`_merge_validated` iterates `DEFAULT_CONFIG` only, dropping unknown keys) vs `dataforge/ui/app.py:545` (`config.set("collapsed_groups", ...)`, persisted to disk but discarded on next `load()`).
- **Affects:** Sidebar group expand/collapse persistence (documented as a feature in GUI_WORKFLOWS/TSOT §app.py `build_navigation_sidebar`).
- **Why:** The UI writes state that is silently thrown away at next launch — settings appear not to stick.
- **How:** Either add `collapsed_groups` (validated `list[str]`) to `DEFAULT_CONFIG`/`_validate_one`, or have `_merge_validated` keep unknown-but-typed keys under an allow-list of runtime keys.

#### R-CORE-4 — 🟡 `CacheManager` crashes with `AttributeError` if DB init failed
- **Where:** `dataforge/core/cache.py:38-49` — on `sqlite3.Error` during `_init_db`, `self.conn` stays `None`; `get_hash` (line 43) then raises uncaught `AttributeError`; `set_hash` catches only `sqlite3.Error`.
- **Affects:** Any environment where `~/.dataforge/cache.db` cannot be created/opened (full disk, read-only home, corrupted path): duplicate scanning threads die instead of degrading to "no cache".
- **How:** Guard methods with `if self.conn is None: return None`; log once.

#### R-CORE-5 — 🟡 Per-file commit in hash cache (performance)
- **Where:** `dataforge/core/cache.py:51-60` — `set_hash` runs `INSERT OR REPLACE` + `commit()` per file; callers invoke it once per hashed file (`duplicates.py:231`).
- **Affects:** Large scans (10k+ new files) pay one fsync per file; on HDDs this dominates scan time. WAL mitigates concurrency, not fsync cost.
- **How:** Batch inserts (queue + flush every N=200 or on completion via `executemany`), or set `PRAGMA synchronous=NORMAL` (safe in WAL).

#### R-CORE-6 — 🟡 Silent empty result for nonexistent root
- **Where:** `dataforge/core/scanner.py:47-50,80-82` — `os.scandir` raising `FileNotFoundError` is swallowed by the broad `except OSError`; caller sees zero entries.
- **Affects:** Search/duplicates UI shows "no results" instead of "path does not exist"; CLI likewise exits 0 with empty output.
- **How:** Let `FileNotFoundError`/`NotADirectoryError` propagate (or yield an error record); keep swallowing `PermissionError`.

#### R-CORE-7 — 🟡 `setup_logger` with bare filename crashes
- **Where:** `dataforge/core/logger.py:30` — `os.makedirs(os.path.dirname(log_file))` → `makedirs("")` raises `FileNotFoundError` when `log_file="app.log"`. Only default path is used today, so latent.
- **How:** `d = os.path.dirname(log_file); if d: os.makedirs(d, exist_ok=True)`.

#### R-CORE-8 — 🔵 `get_hashes` lacks algorithm validation
- **Where:** `dataforge/core/hasher.py:32-34` — unlike `get_file_hash` (line 13), no allow-list check; `getattr(hashlib, "md5 ")` etc. raise `AttributeError`. Latent (single caller passes constants).
- **How:** Reuse `SUPPORTED_ALGORITHMS` validation.

#### R-CORE-9 — 🔵 Prior findings re-confirmed present in current source
- `FileEntry.created_at = stat.st_ctime` mislabel (`common.py:17`, `scanner.py:17`) — tracked as F14.
- Naive local timestamps in `created_dt`/`modified_dt` (`common.py:22-27`) — tracked as F9.
- `provider.py` dead abstraction — tracked as ARCH.3.
- `duplicates.py:197` stores any algorithm's digest into `entry.md5` (cosmetic field misuse, acknowledged in comment).
- Scanner symlink policy (S3/M3) and WAL+lock cache (M5) verified fixed as claimed.

---

## Section 2 — Operations layer & service (`operations/files.py`, `services/file_actions.py`)

**Review status:** ✅ Complete

### Findings

#### R-OPS-1 — 🟡 Collision resolution is O(N²) (performance)
- **Where:** `dataforge/core/operations/files.py:39` — `resolve_collision_path` rebuilds `normalized_reserved_paths = {normalize_path(p) for p in reserved_paths}` on **every call**; `FileActionService.transfer_items` / `rename_items` pass one shared, growing `reserved_paths` set (`file_actions.py:143,196`) and call the resolver once per item.
- **Affects:** Large batch moves/copies/renames. A 5,000-item move performs ~12.5M `normalize_path` calls (each doing `expanduser` + `abspath` + `normpath`) — seconds of pure CPU inside a worker thread that otherwise does I/O.
- **How:** Pre-normalize once per batch: have callers pass an already-normalized set plus a small wrapper that adds normalized candidates, or cache normalization in the service loop.

#### R-OPS-2 — 🟠 Single-archive mode aborts wholesale and leaves partial zip
- **Where:** `dataforge/core/services/file_actions.py:357-383` — the entire item loop runs inside one `try:` around `zipfile.ZipFile(destination, "w")`. Any exception from `safe_zip_write` (unreadable source, file vanishing mid-batch, disk full) breaks out of the whole loop:
  - items before the failure are already written to the zip but only they get success records;
  - remaining items get **no records at all** (silently missing from outcome);
  - the partial `.zip` remains on disk;
  - the single failure record mislabels `source_path=destination`.
  The cancel path (lines 366-367) likewise returns early and leaves the partial zip.
- **Affects:** GUI Search/Duplicates "Zip selected" flows and any CLI/service caller; users see "1 failed" while half their selection was silently unprocessed.
- **How:** Move try/except *inside* the loop for per-item error records; write to `destination + tmp suffix` then `os.replace` atomically on success; delete partial output on cancel/failure.

#### R-OPS-3 — 🟡 Archive destinations never collision-check
- **Where:** `file_actions.py:364` (`zipfile.ZipFile(destination, "w")` truncates any existing file) and `file_actions.py:390-400` (individual mode derives `<name>.zip`, overwriting without check).
- **Affects:** Inconsistent with the app's own collision-safe move/copy/rename rules (docs: "collision handling" is a selling point); a pre-existing zip with the same name is destroyed (permanent data loss of that archive).
- **How:** Route the destination through `resolve_collision_path` (or refuse to overwrite after confirm).

#### R-OPS-4 — 🟡 Failed transfers leave empty directories
- **Where:** `dataforge/core/operations/files.py:102` — `os.makedirs(destination_dir, exist_ok=True)` executes before the first item succeeds; if every subsequent `shutil.move/copy2` fails (e.g., source vanished), the freshly created destination tree persists.
- **Affects:** Folder-sync and organize flows can litter empty target folders.
- **How:** Create lazily per successful transfer, or clean up created-but-empty dirs on failure.

#### R-OPS-5 — 🔵 Permanent delete cannot remove directories
- **Where:** `files.py:124-125` — unsafe-mode delete uses `os.remove`, which raises `IsADirectoryError` for folders. Result surfaces as an ERROR record rather than documented behavior.
- **Why it matters:** Silent-ish capability mismatch — safe mode trashes directories fine, permanent mode cannot. Undocumented anywhere.
- **How:** Document it, or use `shutil.rmtree` behind an explicit double-confirm for directories.

#### R-OPS-6 — 🔵 Case-only rename degrades to `_1` suffix
- **Where:** `files.py:45` — `os.path.exists(candidate)` is True on case-insensitive filesystems even when the existing file *is* the source; combined with line 49's string comparison against `current_path`, `FOO.txt → foo.txt` resolves to `foo_1.txt`.
- **Affects:** Windows/macOS case-normalization renames.
- **How:** Compare `os.path.normcase(candidate) != os.path.normcase(current_path)` in the exists-check.

#### R-OPS-7 — 🔵 Regex compilation errors escape the service
- **Where:** `file_actions.py:232` — `re.compile(pattern)` raises `re.error` before any record exists; contract tests show views pre-validate via `BaseView.validate_regex_pattern`. CLI path checked in Section 7.
- **How:** Wrap into a failed `BatchActionOutcome` or document the raising contract.

#### Verified-fixed claims re-checked in this section
- S6-related: no trash fallback remains in `delete_path`/archive paths ✅ (matches AUDIT_FINDINGS).
- Dry-run default (`dry_run: bool = True`) enforced consistently across all mutators ✅.
- Preview/execute outcomes carry structured `OperationResult`/`BatchActionRecord` ✅.

