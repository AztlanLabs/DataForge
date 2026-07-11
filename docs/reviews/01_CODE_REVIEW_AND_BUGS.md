# Code Review — Bugs, Errors & Correctness Findings

**Date:** 2026-07-10
**Reviewer role:** Software engineer / code auditor
**Scope:** `filemanager/` (core, modules, ui, cli), `tests/`, packaging.
**Method:** Full manual read of the source plus targeted static checks and runtime verification of the highest-value findings.

> **Status update (2026-07-10, remediation pass):** every finding below (H1, M1–M6, L1–L9) has been **fixed** in the source tree, and the test suite now runs green — **224 tests pass** (`PYTHONPATH=. pytest -q`). Each finding retains its original description for traceability and is annotated with a **✅ Fixed** note describing what changed. The stray `26.1.2` file was deleted and a `.gitignore` added.

> How to read this file: each finding has a **severity**, the **evidence** (file/line), a plain description of the **failure**, and a concrete **fix**. Findings verified by actually running code are marked ✅ **Confirmed at runtime**.

## Severity legend

| Severity | Meaning |
| --- | --- |
| 🔴 High | Broken behaviour, data-loss risk, or a false claim about the product. Fix before any release. |
| 🟠 Medium | Real defect that bites under realistic conditions (bad input, concurrency, edge case). |
| 🟡 Low | Correctness smell, hygiene, or robustness gap; low blast radius. |

---

## 🔴 HIGH severity

### H1 — The test suite does not run; docs claim "224 tests pass" ✅ Confirmed at runtime
- **Where:** `tests/test_comprehensive.py:36`
- **Evidence:**
  ```
  ImportError: cannot import name 'rename_with_regex'
  from 'filemanager.core.operations.files'
  ```
  `test_comprehensive.py` imports `rename_with_regex` (and calls it at lines 723/727/744/748), but that symbol does not exist anywhere in `filemanager/`. Only `FileActionService.rename_items_with_regex` and the low-level `rename_path` exist.
- **Impact:** `pytest` **fails at collection** for the largest test module (~1,547 lines). Only `test_integration.py` (18) + `test_contract_regressions.py` (50) + `test_new_modules.py` (9) = **77 tests actually collect**. `README.md` and `TECHNICAL_SOURCE_OF_TRUTH.md` both assert *"The full test suite (224 tests) passes."* That claim is currently false — the suite is red on a clean checkout.
- **Fix (choose one):**
  1. Re-introduce a module-level `rename_with_regex(path, pattern, repl, dry_run=...)` helper in `core/operations/files.py` (a thin wrapper over `rename_path` + `re.sub` on the basename), **or**
  2. Update the test to use the current API (`FileActionService.rename_items_with_regex`).
  Then wire the suite into CI so a red suite blocks merges (see `04_IMPROVEMENTS_AND_ROADMAP.md`).
- **✅ Fixed:** Option 1 applied — `rename_with_regex(source_path, pattern, replacement, dry_run=..., reserved_paths=...)` is restored in `core/operations/files.py` (a thin wrapper over `re.sub` on the basename → `rename_path`) and re-exported from `core/operations/__init__.py`. Three other stale tests surfaced once collection succeeded were also corrected to the current API (`rename_items_with_rules`, the `dialogs.*` browse wrapper, and the `entry_path`-aware duplicate tree). **`pytest -q` now collects and passes all 224 tests.**

---

## 🟠 MEDIUM severity

### M1 — `fm hash-calc --algo sha512` crashes ✅ Confirmed at runtime
- **Where:** `filemanager/core/hasher.py:11-12` vs `filemanager/cli.py:580` and `filemanager/modules/forensics.py:37`
- **Evidence:** the CLI advertises `--algo` choices `md5, sha1, sha256, sha512`, but `get_file_hash` only accepts `('md5','sha1','sha256')` and raises `ValueError("Unsupported hash algorithm: sha512")`. In `calculate_hashes`, that exception is caught by the generic `except Exception` and turned into an error dict **without** an `algo` key. The CLI then does `res[algo]` → `KeyError: 'sha512'` → traceback.
- **Impact:** a documented, tab-completable flag produces an unhandled crash.
- **Fix:** add `sha512` (and ideally `blake2b`) to the allow-list in `get_file_hash`/`get_hashes`, **and** make `calculate_hashes` always populate the requested algo keys (even on error) so downstream `res[algo]` is safe.
- **✅ Fixed:** `core/hasher.py` now defines `SUPPORTED_ALGORITHMS = ('md5','sha1','sha256','sha512','blake2b')` and validates against it. `forensics._hash_entry_worker` seeds every requested algo key to `""` before hashing (and catches `ValueError` alongside `OSError`), so `res[algo]` is always safe. The Settings hash-algorithm dropdown now also offers `sha512`. Verified at runtime: `fm hash-calc <file> --algo sha512` prints a 128-char digest instead of crashing.

### M2 — `IntegrityMonitor.verify_snapshot` throws on a corrupt/empty snapshot
- **Where:** `filemanager/modules/integrity.py:110-114`
- **Evidence:** the snapshot read is guarded by `except OSError`, but `json.load` raises `json.JSONDecodeError` (a subclass of `ValueError`, **not** `OSError`). A truncated/hand-edited/empty `.json` snapshot therefore escapes the handler and crashes the whole verify run (and, in the GUI, surfaces as a raw error).
- **Fix:** `except (OSError, json.JSONDecodeError)` and return the existing structured error report. Same pattern should be applied to every `json.load` in the codebase that reads a user-supplied file (`forensics`, hardware export reload, etc.).
- **✅ Fixed:** `verify_snapshot` now catches `(OSError, json.JSONDecodeError)` and returns the structured `ERROR: Could not read snapshot file.` report. Verified at runtime with a truncated snapshot. (`ConfigManager.load` already guarded `JSONDecodeError`.)

### M3 — Directory scan follows symlinks → infinite recursion / scope escape
- **Where:** `filemanager/core/scanner.py:54,62,66,72`
- **Evidence:** `os.scandir` entries call `entry.is_dir()` / `entry.is_file()` with the default `follow_symlinks=True`. A symlink that points at an ancestor (`ln -s .. loop`) yields unbounded recursion → `RecursionError`/hang; a symlink pointing **outside** the chosen root silently pulls external files into search, duplicate, cleanup, and organize results.
- **Impact:** hang/DoS on hostile or merely circular trees; correctness (results include files the user never pointed at); and a safety problem when those out-of-tree paths are then moved/deleted.
- **Fix:** call `entry.is_dir(follow_symlinks=False)` / `entry.is_file(follow_symlinks=False)`; treat symlinks explicitly (skip by default, or surface them as a distinct, non-recursed entry). Add a `visited real-inode` guard for defense in depth.
- **✅ Fixed:** `scan_directory` now skips symlinks outright (`if entry.is_symlink(): continue`) and passes `follow_symlinks=False` to every `is_dir()`/`is_file()` check. Verified at runtime: a tree containing a symlink loop to its ancestor and a symlink to an out-of-tree file yields only the genuine in-tree files (no hang, no scope escape).

### M4 — Integrity hashing hardcodes MD5 and ignores the configured algorithm
- **Where:** `filemanager/modules/integrity.py:70,134` (`_hash_worker(entry_path, "md5", ...)`)
- **Evidence:** both `create_snapshot` and `verify_snapshot` pass the literal `"md5"`, even though Settings exposes a `hash_algorithm` (`md5/sha1/sha256`) that the duplicate finder honours. So a user who sets SHA-256 still gets MD5 integrity baselines, and there is no record in the snapshot of which algorithm was used.
- **Impact:** (a) inconsistent with user configuration; (b) MD5 is unsuitable for tamper-evidence (see `02_SECURITY_AND_FORENSIC_AUDIT.md`, S1); (c) snapshots aren't self-describing.
- **Fix:** read `config.get("hash_algorithm")` (default it to `sha256`), store the algorithm inside the snapshot JSON, and verify against the stored algorithm rather than a hardcoded one.
- **✅ Fixed:** `create_snapshot` now resolves the algorithm via `config.get("hash_algorithm")` (falling back to `sha256` for unknown values) and writes a **self-describing** snapshot: `{"algorithm": ..., "created_at": ..., "files": {rel: hash}}`. `verify_snapshot` reads the stored algorithm and hashes with it, with backward-compatible handling of legacy flat `{rel: hash}` (MD5) snapshots. The config default `hash_algorithm` is now `sha256` (see M6). Verified at runtime.

### M5 — Shared SQLite cache connection is used across threads without a lock
- **Where:** `filemanager/core/cache.py:18` (`check_same_thread=False`, single global `file_cache`)
- **Evidence:** one connection object is shared process-wide and marked usable from any thread. Today `find_duplicates` touches it from the main thread only, but the app runs long tasks on `BackgroundWorker(QThread)`s, and nothing prevents two concurrent workers (or a future refactor that moves `get_hash`/`set_hash` into `_hash_worker`) from writing simultaneously. SQLite with a shared connection and no serialization can raise `database is locked` / `recursive use of cursors` or interleave a `VACUUM` (in `clear()`) with in-flight cursors.
- **Fix:** guard all `CacheManager` methods with a `threading.Lock`, or open a connection per thread (or use a small connection pool), and set `PRAGMA journal_mode=WAL`.
- **✅ Fixed:** `CacheManager` now holds a `threading.Lock` and wraps every `get_hash`/`set_hash`/`clear`/`close` in `with self._lock:`, and `_init_db` sets `PRAGMA journal_mode=WAL`. The shared connection is now safe under concurrent `BackgroundWorker(QThread)` access.

### M6 — Duplicate detection deletes based on hash equality alone (default MD5), no byte compare
- **Where:** `filemanager/modules/duplicates.py:136,213` + `core/config.py` (`hash_algorithm: "md5"`)
- **Evidence:** files are grouped purely by digest; the GUI/CLI then offer to move/delete all-but-one. With MD5 (the default) a deliberate collision, or even a fluke on adversarial input, marks two *different* files as duplicates → the wrong file can be deleted.
- **Fix:** default to SHA-256, and for the *delete* path add a final `filecmp`/byte-for-byte confirmation for each group before removal (cheap relative to hashing, and eliminates the collision-driven data-loss class entirely).
- **✅ Fixed:** the config default `hash_algorithm` is now `sha256`, and `select_duplicate_records(..., verify_content=True)` byte-compares each non-keeper against its group's keeper (`filecmp.cmp(shallow=False)`) before it can be acted on — a digest collision (or a file changed since scanning) is logged and *kept*, never removed. The GUI one-click keep-and-act flow (`run_keep_action`) passes `verify_content=True`.

---

## 🟡 LOW severity

### L1 — Bare `except:` clauses swallow everything and silently coerce bad input to 0
- **Where:** `filemanager/core/actions/filters.py:59,61,100,142,144,162`; `core/actions/media.py:12`
- **Evidence:** e.g. `try: min_b = int(...) \n except: min_b = 0`. A bare `except` also catches `KeyboardInterrupt`/`SystemExit`, and turning an invalid size/date/dimension into `0` silently changes filter semantics (a typo'd "min size" becomes "no minimum") with no user feedback.
- **Fix:** catch `(ValueError, TypeError)`, and either surface a validation error or keep the previous value; never bare-`except`.
- **✅ Fixed:** the numeric-coercion sites in `core/actions/filters.py` (`SizeFilter`, `DateFilter`, `ImagePropFilter`) and `core/actions/media.py` (`ConvertImageStep`) now catch `(ValueError, TypeError)`; the image-open guard catches `(OSError, ValueError)`. No bare `except:` remains in these paths.

### L2 — `print()` used for error reporting instead of the logger
- **Where:** `filemanager/core/media_ops.py:68`; `filemanager/ui/plugin_loader.py:52`
- **Evidence:** PDF-merge read errors and plugin-load failures go to stdout via `print`, bypassing the app's logging/log-level config and invisible in the packaged GUI.
- **Fix:** use `logger.error(...)`; PDF merge failures should also propagate into the returned report's `failed_paths` (they already are) and be surfaced in the UI.
- **✅ Fixed:** both sites now use `logger.error(...)` (`media_ops.merge_pdfs` and `ui/plugin_loader.py`). PDF-merge failures continue to be reported via the report's `failed_paths`.

### L3 — `convert_image` has a no-op `except Exception as e: raise e`
- **Where:** `filemanager/core/media_ops.py:144-145`
- **Evidence:** the handler re-raises unchanged, adding a stack frame and obscuring the origin while providing zero value.
- **Fix:** delete the try/except (let it propagate) or convert to a logged, typed error return consistent with the rest of the module's `_report` pattern.
- **✅ Fixed:** `convert_image` now catches `(OSError, ValueError)`, logs the error, and re-`raise`s (bare `raise`, no extra frame) instead of the no-op `raise e`.

### L4 — ExifTool availability probe runs a subprocess at import time
- **Where:** `filemanager/modules/metadata.py:60` (`HAS_EXIFTOOL = _exiftool_available()`)
- **Evidence:** importing the metadata module shells out to `exiftool -ver`. Because views are constructed at startup, this adds a subprocess launch to every GUI/CLI cold start and makes import success depend on an external binary's behaviour.
- **Fix:** make the probe lazy (`functools.lru_cache` on first real use), not a module-level side effect.
- **✅ Fixed:** the module-level `HAS_EXIFTOOL = _exiftool_available()` is gone; the probe is now `@lru_cache(maxsize=1) def _has_exiftool()`, called on first real use. All former `HAS_EXIFTOOL` references were updated to `_has_exiftool()`. Importing `modules/metadata.py` no longer shells out to `exiftool`.

### L5 — `render_template_name` uses naive string replacement
- **Where:** `filemanager/core/operations/files.py:162-178`
- **Evidence:** it `str.replace`s `{name}`, `{counter}`, etc. If an original filename literally contains one of those tokens it gets rewritten; and the "append extension if missing" heuristic (`"." not in new_name`) drops the extension for any template output that happens to contain a dot.
- **Fix:** use `str.format`/`string.Template` with explicit fields, and reattach the original extension deterministically instead of sniffing for a `.`.
- **✅ Fixed:** `render_template_name` now renders via `string.Formatter().vformat` over an explicit field map (`name/ext/date/size/counter`), with a `__missing__` that leaves unknown `{tokens}` untouched, and reattaches the original extension deterministically whenever the template lacks `{ext}` (no more `"." not in new_name` sniffing).

### L6 — Packaging drift: dev deps in `requirements.txt`, unpinned versions, setup/requirements divergence
- **Where:** `requirements.txt`, `setup.py`
- **Evidence:** `requirements.txt` mixes runtime (`PyQt5`, `Pillow`, `psutil`) with dev/build tooling (`pytest`, `pyinstaller`) and pins only a few packages. `setup.py`'s `install_requires` is a different, smaller set. There is no lockfile.
- **Fix:** split `requirements.txt` (runtime) from `requirements-dev.txt` (pytest, pyinstaller, linters); pin/upper-bound the security-relevant libs (`Pillow`, `pypdf`, `pymupdf`); consider `pyproject.toml` with extras (`.[gui]`, `.[dev]`).
- **✅ Partially fixed:** `requirements.txt` is now runtime-only, and a new `requirements-dev.txt` (`-r requirements.txt` + `pytest`, `pyinstaller`) holds the build/test tooling. Broader pinning and a `pyproject.toml` migration remain open (roadmap).

### L7 — Stray empty file committed at repo root
- **Where:** `./26.1.2` (0 bytes)
- **Evidence:** looks like the accidental artefact of a shell mistake (e.g. `pip install pkg==26.1.2` redirected to a file, or `> 26.1.2`).
- **Fix:** delete it and add an entry to a `.gitignore` (the repo also has no `.gitignore` at root and is not currently a git repo — see roadmap).
- **✅ Fixed:** the stray `26.1.2` file was deleted and a root `.gitignore` was added (covers `__pycache__/`, `.venv/`, `.pytest_cache/`, `build/`, `dist/`, logs, etc.). Putting the tree under version control remains a roadmap item.

### L8 — Windows Recycle Bin recovery is a silent no-op
- **Where:** `filemanager/modules/recovery.py:182-188` (`_scan_windows_trash` returns `[]`)
- **Evidence:** on Windows, "Scan Trash" always reports zero items; the limitation is only logged at INFO, so the GUI shows an empty, apparently-successful result.
- **Fix:** surface the "unsupported on this platform / install pywin32" state to the user instead of an empty success, or implement via `$Recycle.Bin` `$I` record parsing.
- **✅ Fixed:** `_scan_windows_trash` now raises a typed `TrashScanUnsupported` (logged at WARNING) instead of returning `[]`. The CLI `fm recover --trash` catches it and prints an explicit "Trash scan unavailable" message; the GUI surfaces it through `run_workflow`'s error dialog. (Actual `$Recycle.Bin` `$I` parsing remains future work.)

### L9 — `_run_john_dictionary` always reports success
- **Where:** `filemanager/modules/password_tools.py:382-388` (`"success": True` unconditionally)
- **Evidence:** unlike the hashcat path (which keys success off the return code), the john path hardcodes `success: True` regardless of whether anything cracked or john errored.
- **Fix:** derive `success` from `outcome["returncode"]` and whether `cracked` is non-empty.
- **✅ Fixed:** `_run_john_dictionary` now returns `"success": outcome["returncode"] == 0 and bool(cracked.strip())`, mirroring the hashcat path.

---

## Cross-cutting quality observations

- **Two parallel filter engines.** `modules/search.py` (`SearchQuery`) and `core/actions/filters.py` are independent implementations of the same size/date/name filtering. They can (and over time will) diverge in edge-case semantics. Consolidate the Action Builder filters onto `SearchQuery`.
- **Two metadata-cleaning implementations.** `modules/cleaner.py::MetadataCleaner.remove_metadata` (returns `bool`, re-encodes JPEG at quality 100) and `modules/metadata.py::MetadataEngine.remove_metadata` (returns a dict, exiftool-backed). The CLI uses the latter; the Action Builder/plugin use the former. Pick one source of truth.
- **`LocalProvider`/`FileProvider` in `core/provider.py` is dead code** (confirmed by the TSOT itself). Either adopt it as the IO seam (useful for testing and future remote backends) or remove it.
- **Error surfacing is inconsistent** — some modules return `{"error": ...}` dicts, some raise, some `print`. A single result/error convention would make the UI and CLI handling uniform.

## Suggested fix order

1. **H1** (unbreak the test suite) — nothing else can be trusted until the suite is green and in CI.
2. **M3 / M1 / M2** (crashes & scope-escape on realistic input).
3. **M4 / M6 / M5** (integrity correctness, dedup safety, cache concurrency).
4. **L-series** hygiene, ideally alongside the linter adoption in the roadmap.
