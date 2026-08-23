# DataForge — Consolidated Specification (Authoritative)

**Date:** 2026-08-23 08:00 UTC · **Source of truth for:** `dataforge/` HEAD `b373e7e` (v0.1.0, 37/37 tickets DONE, 1213 tests) + reconciled proposals in `proposals/`  
**Replaces reading:** `APP_REFERENCE`, `ARCHITECTURE`, `CLI_REFERENCE`, `GUI_WORKFLOWS`, `TECHNICAL_SOURCE…`, `reviews/*`, `proposals/*` individually — this is the single index. Originals remain as detail supplements.  
**Verification:** Re-checked against `dataforge/{core,modules,ui,cli}.py`, `pyproject.toml`, `build_exe.py`, and `~/.dataforge/` runtime.

---

## 1. Canonical Project Definition

**One-line:** Local-first desktop (PyQt5) + CLI (`fm`) toolkit for file discovery, deduplication, organization, cleanup, integrity, recovery, and forensic triage over a shared Python core.

**Stack:** Python 3.10+, Click (CLI), PyQt5 + QSS design tokens, SQLite WAL (hash cache), `hashlib`/`xxhash`/`blake3` (future), `send2trash`, `psutil`/`python-magic`/`PyExifTool`/`mutagen`, PyInstaller (onefile + onedir bundles).

**Entrypoints:** `run_ui.py → DataForgeApp(QMainWindow)` and `fm → dataforge.cli:main` (Click group). Both delegate to `dataforge/modules/*` via `core/services/file_actions.py` where mutation is involved; read paths go via `core/scanner.py`.

**Package:** `pyproject.toml` `version = 0.1.0`, scripts `fm`, `dataforge-engine` (proposed). `setup.py` shim kept for `sdist`. Requirements split: `pyproject.toml` = CLI/core, `requirements.txt` = full GUI/media, `requirements-dev.txt` = test/build.

**Product identity:** “DataForge — File System Management with Steroids and Superpowers”, 14 views, 16 CLI groups (17 leaf commands — `integrity create`/`check` are two leaves under one group). Tagline, logo, and `~/.dataforge/` paths are canonical until `proposals/INSTALL_UPGRADE_LIFECYCLE:I0` (`core/paths.py` + XDG/AppData) lands.

---

## 2. Canonical Architecture (6 layers)

```
CLI (fm) ─┐
          ├─→ modules/*  ─┐
GUI (ui/) ┘               ├─→ services/file_actions.py → operations/files.py → OS
                          └─→ core/{scanner,hasher,cache,config,logger}
Action Builder (core/actions/*) is a second orchestration (pipeline) over the same seam.
```

| Layer | Dir | Responsibility | Current truth |
|---|---|---|---|
| **Primitives** | `core/{common,scanner,config,cache,hasher,logger,utils}` | `FileEntry`, directory walk, persistent settings, hash cache, logging | `FileEntry` dataclass; `scan_directory` is recursive `os.scandir` generator, sequential, double-`stat` defect (R-CORE-5 in proposals) |
| **Operations** | `core/operations/files.py` | Neutral `move/copy/delete/rename/collision/archive` primitives + `OperationResult` | `resolve_collision_path` is O(N²) on large batches (R-OPS-1); `makedirs` before success (R-OPS-4) |
| **Service** | `core/services/file_actions.py` | `FileActionService` — batch-aware, progress/cancel/dry-run, structured `BatchActionOutcome` | Sequential loop (no pool) — biggest throughput bottleneck; single-archive aborts leaving partial zip (R-OPS-2) |
| **Modules** | `modules/{search,duplicates,cleaner,integrity,system_cleanup,recovery,forensics,metadata,hardware,performance,device_manager,password_tools,file_signatures,usage,reporting}` | Feature logic (search, dupes, integrity, cleanup, recovery, forensics, etc.) | Several modules `list(scan_directory)` materialize full file lists → OOM on 1M files |
| **Actions** | `core/actions/{base,filters,io,modifications,media,organize}` | `ActionContext`/`ActionStep` pipeline for Action Builder (filter → io → media) | Two filter engines (`SearchQuery` vs `actions/filters`) drift — WS-F |
| **UI** | `ui/{app,views/*,widgets,theme_tokens,plugin_loader}` | Shell, 14 views, `BackgroundWorker(QThread)` + Qt signals, design tokens, plugins | Single `BackgroundWorker` + global `is_busy` blocks second job (proposals/PERFORMANCE) |

**Proposed evolution (proposals/):** Extract `engine/` lib, parallel BFS scanner + batched cache + mmap hashing, pipelined `engine/daemon.py` with UDS/Named Pipes + D-Bus/XPC/COM + HTTP gateway, `FileProvider` ABC for Local/Ssh/S3/Image backends, `core/paths.py` for XDG/AppData, versioned `CONFIG_SCHEMA` + `PRAGMA user_version`.

---

## 3. Canonical Domain Models

### FileEntry (`core/common.py:6`)
```py
@dataclass class FileEntry:
  path: str; filename: str; extension: str; size: int
  created_at: float; modified_at: float; is_dir: bool = False
  md5/sha1/sha256: Optional[str]
  st_ino/st_dev/st_blocks: int = 0  # TICK-002 landed — hardlink/sparse awareness
  hardlink_key -> (st_dev, st_ino)  # equal pairs are hardlinked
```

### Config (`core/config.py:16` → proposed `core/paths.py` + `CONFIG_SCHEMA_VERSION`)
- File: `~/.dataforge/config.json` today → `$XDG_CONFIG_HOME/dataforge/config.json` / `~/Library/Application Support/DataForge/config.json` / `%AppData%\DataForge\config.json` after I0.
- Keys (17): `theme`, `safe_mode`, `excluded_extensions/.folders`, `max_thread_workers=4` (→ `min(32, cpu*4)` proposed), `search_thread_workers=4`, `hash_algorithm=sha256`, `log_level`, `size_unit`, `path_display_mode`, `dashboard_paths`, `settings_ui_tier`, `duplicate_default_keep_strategy`, `plugins_enabled`, `ui_reduce_motion`, (proposed `hash_block_size=1MiB`, `cache_batch_size=1000`, `_schema_version`).
- Validation: `config.py:73` validates types/ranges/enums, drops unknown keys — but misses list-item types (R-CORE-2).

### Cache (`core/cache.py:6`)
- `~/.dataforge/cache.db` SQLite WAL, single `file_hashes(path PK, size, mtime, hash, algo)` + `threading.Lock` per method. Proposed: composite index `(algo,size,mtime)`, `PRAGMA synchronous=NORMAL`, `set_hash_many` batch, `user_version` migrations.

### OperationResult / BatchActionOutcome (`operations/files.py`, `services/file_actions.py`)
- `OperationResult(action, source_path, destination_path, success, message, dry_run)` and `BatchActionRecord`/`Outcome` with per-item status. Single-arch-mode zip is the outlier (R-OPS-2/3).

### ActionContext / ActionStep (`core/actions/base.py`)
- `ActionContext(files, dry_run, cancel_token, progress_callback, variables)` + `ActionStep.execute(ctx)` chain. Shared by Action Builder; filters vs. search duplication is WS-F tech debt.

---

## 4. Feature Catalog (current truth)

### CLI — `fm` (16 groups, 17 leaves, `cli.py:57`)
| Group | Leaf(es) | Notes |
|---|---|---|
| `scan` | scan | List files via `scan_directory` |
| `dupes` | dupes | Size-group → hash → group |
| `search` | search | `SearchQuery` (name/ext/size/date/content) |
| `organize`, `rename`, `clean`, `usage` | each 1 | Move/copy with collision, regex rename, empty-dir prune, size rollup |
| `integrity` | `create`, `check` | Snapshot `{algorithm, created_at, files:{rel:hash}}`, legacy flat MD5 still readable |
| `cleanup` | cleanup | Junk categories (System Temp … Crash Reports) + `browser` artifacts (future) |
| `performance` | performance | CPU/RAM/disk health via `psutil` |
| `recover` | recover | Trash scan + carving (header/footer + PhotoRec `testdisk` hook) |
| `metadata` | metadata | Read/edit/strip via `Pillow`/`pypdf`/`mutagen`/`ExifTool` |
| `hardware` | hardware | Diagnostics + recommendations |
| `forensics` | forensics | Artifacts, keyword search, signature `profile_directory_types` |
| `devices`, `hash-calc` | devices, hash-calc | Mount/type/used/total; single hash |

All return plain text; several support `--format json/jsonl` but logger on `stdout` corrupts it (R-CORE-1).

### GUI — `ui/app.py:114` (14 views, task-oriented sidebar)
Home: Dashboard · Find & Organize: Search, Duplicate Finder, Media Tools, Metadata & EXIF, Automations (Action Builder + Tools) · Clean & Optimize: Clean Up Space, Storage & Devices, Performance · Recover & Investigate: File Recovery, Forensics · System: Hardware Info, Settings, About & Help + `plugins/MetadataCleanerPlugin`.

Threading: `run_workflow`/`run_background` → single `BackgroundWorker(QThread)` → Qt signals (`progress/status/result/error`). `cancel_token` (`threading.Event`) checked per item; ThreadPool children only check at task boundaries.

---

## 5. Cross-Cutting Rules (reconciled)

- **Mutation seam:** All move/copy/delete/rename/archive **must** go via `FileActionService` (except dedicated writers: `recovery` carve, `metadata` strip, `integrity` snapshot — documented as separate). New destructive work adds to `operations/files.py` first, then exposes via service.
- **Read seam:** New discovery via `build_search_query` → `iter_search_files` → `search_files` (not ad-hoc `os.walk`).
- **Background:** Views never block Qt main; accept `cancel_token` + `progress_callback` where practical; use `run_workflow(progress=True)` for progress.
- **Plugins:** Under `ui/plugins/`, opt-in via `plugins_enabled`, owner/world-writable rejected (`plugin_loader.py:40`), `isolation='inline'` (default) or `isolation='subprocess'` via `ProcessPoolExecutor` + `Queue` (+ `subprocess.run` fallback) and `require_signed` verifies `plugin.sig` against `plugins-trusted.gpg` / `plugins-trusted.sha256` with `AuditLog` provenance (F12 remainder — `plugin_loader.py:13` `PluginLoader`).
- **Tokens/Theming:** All colour via `ui/theme_tokens.py` (46 tokens/theme, WCAG AA, `focus_ring`), QSS via `generate_qss`/`generate_palette`. No ad-hoc hex in `ui/**/*.py` (guarded by tests).

---

## 6. Identified Conflicts & Decisions

| Conflict | Sources | Resolution |
|---|---|---|
| 16 vs 17 commands | `README:73` 16 vs `ARCH diagram` 17 vs `cli.py` | **16 groups, 17 leaves** (integrity is 2). Docs now say “16 groups (17 leaf)” consistently. |
| Paths `~/.dataforge` vs XDG/AppData | `core/*.py` hardcode `~/.dataforge` vs `proposals/INSTALL_UPGRADE_LIFECYCLE` XDG | **Current truth stays `~/.dataforge`**; migration gated on `proposals:I0` (`core/paths.py` + `_schema_version` + `user_version`). Audit docs updated to call out the gate. |
| HTTP API vs native | `proposals/PERFORMANCE §3` (FastAPI primary) vs `proposals/NATIVE_OS_API §2–3` (UDS/Named Pipes + D-Bus/XPC/COM + HTTP remote) | **Native hybrid wins.** `PERFORMANCE §3` marked superseded; canonical is `NATIVE_OS_API §3` (UDS/pipe primary local, D-Bus/XPC/COM discoverable, HTTP remote). New `PERFORMANCE` forward-links. |
| Fixed vs open for S4/S7 | `ARCHITECTURE:214` said S4/S7 open while `reviews/AUDIT_REPORT:Part 2` says fixed in WS-B | **Fixed in WS-B** is correct (`recovery.py:205`, `system_cleanup.py:267`). Updated stale paragraphs and bumped `Last verified` to 2026-08-22. |
| Test counts 254/255 vs 301 | `NOTES_REVIEW`/`IMPLEMENTATION_PLAN` historical 254/255 vs `README` 301 | Historical counts preserved as audit record; live `README`/`AUDIT_REPORT` use 301. |
| Overlap of 5 docs repeating file map/layers/views/CLI | `APP_REFERENCE` + `ARCHITECTURE` + `TECHNICAL_SOURCE…` + `GUI_WORKFLOWS` + `README` | **Canonicals:** file map → `TECHNICAL_SOURCE`, layers → `ARCHITECTURE`, CLI flags → `CLI_REFERENCE`, GUI → `GUI_WORKFLOWS`, user-facing → `APP_REFERENCE`. Others link. `docs/README.md` index now states tiers. |
| 7 files in `reviews/` with no index | `reviews/` before `README.md` | Added `docs/reviews/README.md` index; merged 7→4 concise files (next section) + `DOCUMENTATION_AUDIT_2026-08-22` as trace. |

---

## 7. Functional Spec Matrix (inventory)

### Shipped & green (723 tests)
- Scanner symlink-safe, cache WAL+lock, integrity `sha256` self-describing snapshots, XSS fixed (`html.escape`), config validation + autosave “Saved ✓”, sidebar always-visible + task-oriented groups + Automations merge, WS-E Motion/Empty/Error/A11y polish (animations gated by `ui_reduce_motion`, `focus_ring`, `EmptyState`, `friendly_error_message`, `accessibleName`+`⚠` glyph, 18 SVG icons). Parallel scanner/hasher/cache, streaming modules, parallel batch ops, UDS/Named Pipe transports, daemon+client integration, systemd/launchd/Windows lifecycle, nfpm packaging, hash-chained audit log, CaseContext, Evidence Mode, UTC provenance.

### Open — correctness/performance (from `reviews/AUDIT_REPORT:Part 4` + `proposals/PERFORMANCE`)
- **R-CORE-2** (config list items) remains. R-CORE-1 fixed (TICK-101), R-OPS-1/3/4 fixed (TICK-105), R-OPS-2 fixed (TICK-201). Then R-CORE-3…8.

### Open — forensic / investigator UX (from `reviews/FORENSIC_REVIEW`)
- **Narrow the forensic gap:** F1 (hash-chained `core/audit.py` + `FileActionService` hook), F2 (provenance: operator/host/image-hash/case ID), F3/U2 (Evidence Mode read-only gate + `CaseContext`), F9 (UTC ISO-8601) — **all fixed in TICK-304 (Wave 3)**. Remaining: F4/F21 (`secure_delete` out of `forensics.py` + hardlink-aware), F13 (parser isolation). Rest: F5 raw image, F6 carving, F7 YARA/SSDEEP/NSRL, F8 ADS/xattrs, F14 streaming + `FileEntry` MACB, F15 budget, F16 sparse, F20 VSS, U3–U9 UX (virtualised timeline, hex inspector, mismatch filter, etc.), U10/U11 cross-platform marketing.

### Open — proposals that become the v0.2–v0.3 engine
- **I0** `core/paths.py` (platformdirs) + `CONFIG_SCHEMA_VERSION` + `PRAGMA user_version` + `__version__` + legacy `~/.dataforge` migration — **DONE (TICK-001, Wave 0)**.
- **N0–N4** UDS/Named Pipes + D-Bus/XPC/COM + `engine/daemon.py` + `FileProvider` expansion + parallel scanner/batched cache/mmap + HTTP gateway for remote + native FS/Rust helper + packaging (`deb/rpm/msi/dmg`) — **N0 done (TICK-205), daemon done (TICK-301), lifecycle done (TICK-302), packaging done (TICK-303)**. Remaining: HTTP gateway, native FS/Rust helper. See `proposals/` trio for line-level seams.

---

## 8. How to read the docs after this

| You are… | Start here |
|---|---|
| New user | `README` → `APP_REFERENCE` |
| New contributor | `DEVELOPMENT_GUIDE` → `ARCHITECTURE` → `TECHNICAL_SOURCE…` |
| CLI user | `CLI_REFERENCE` |
| GUI user | `GUI_WORKFLOWS` |
| Building what’s next | `reviews/ROADMAP.md` → `CONSOLIDATED_SPEC §7` → `proposals/README.md` |
| Auditing | `reviews/AUDIT_REPORT.md` → `reviews/FORENSIC_REVIEW.md` |

Freshness: current-truth docs carry `Last verified: 2026-08-22` (re-checked, no code change since 2026-07-12). Proposals carry `Status: PROPOSAL`. History (`reviews/`) is frozen; audit that produced this file is `DOCUMENTATION_AUDIT_2026-08-22.md`.
