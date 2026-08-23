# Ticket TICK-701 — R-CORE-2/5: config item validation + cache batch commit

> **Wave 7** | **Domain:** Core / Config+Cache | **Depends on:** None
> **Source:** `docs/reviews/AUDIT_REPORT.md` Part 4 (R-CORE-2, R-CORE-5)

---

## Your Assignment

```
TICKET_ID: TICK-701
WAVE: 7
TITLE: R-CORE-2/5: config item validation + cache batch commit
```

**Exclusive write files (SOLE writer for Wave 7):**
- `dataforge/core/config.py`
- `dataforge/core/cache.py`

**Read-only references (do not edit):**
- `docs/reviews/AUDIT_REPORT.md`
- `dataforge/core/scanner.py`
- `dataforge/modules/duplicates.py`

**Test target:** `tests/test_core_item_validation.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_core_item_validation.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/ARCHITECTURE.md` §Core primitives
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `core/config.py`, `core/cache.py` sections
- `docs/DEVELOPMENT_GUIDE.md` (setup, `PYTHONPATH=. pytest`)
- `docs/CONTRIBUTING.md` §8 (When You Change Code → Update table)

---

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` (and `docs/proposals/PERFORMANCE_TICKETS.md` aliases) in parallel. Copy this prompt, replace `TICK-508` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

---

## Role

You are an autonomous coding agent working on the **DataForge** repo (`develop` branch, Python 3.10+, PyQt5, Click, SQLite WAL). Your only job is to complete **one** ticket end-to-end: code, tests, docs, verification, and a Conventional Commits push.

## Ticket Assignment

```
TICKET_ID: TICK-508   # e.g. TICK-102 or PERF-101 (alias — see alias map)
WAVE:      5        # from Concurrency Map in docs/PARALLEL_BACKLOG.md
```

If `TICK-508` starts with `PERF-`, resolve its alias first (`PERF-100→TICK-004`, `PERF-101→TICK-102`, `PERF-103→TICK-104`, etc. — see `PARALLEL_BACKLOG.md` Appendix). Never run a `PERF-*` and its `TICK-*` twin in the same wave.

## Required Reading (in order, before touching code)

1. `docs/CONSOLIDATED_SPEC.md` §2–7 — canonical layers, seams, and domain models (your ticket's `scope` assumes this).
2. `docs/PARALLEL_BACKLOG.md` — Concurrency Map (your wave + `depends_on`) + **How to Work a Ticket — Sequential and Parallel Execution Guide** (§ after the map). For perf-only tickets also read `docs/proposals/PERFORMANCE_TICKETS.md` alias map.
3. `docs/CONTRIBUTING.md` §3, §8, §10 — Conventional Commits (`type(scope): description` ≤72 chars, `commit-msg` hook), docs sync table, and parallel-vs-sequential rules. Also `docs/AUDIT_HARDENED_2026-08-22.md` for why the backlog is hardened.
4. Your ticket's **Work Package YAML** in `docs/PARALLEL_BACKLOG.md` — `exclusive_write_files`, `read_only_references`, `architectural_context`, `requirements.acceptance_criteria`, `verification`.
5. The files listed in `read_only_references` and `architectural_context.existing_symbols_to_use` (e.g. `dataforge/core/common.py:5`, `dataforge/core/scanner.py:22`, `dataforge/ui/app.py:114`).

### 6. Domain-Relevant Documentation (read the row for your ticket's `scope`)

| Ticket scope | Must also read |
|---|---|
| `Core / Infrastructure`, `Core / Provider`, `Core / Persistence`, `Core / Cache`, `Core / Logger`, `Core / Scanner`, `Core / Hasher`, `Core / Operations`, `Forensic / Engine` | `docs/ARCHITECTURE.md` §Core primitives + `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `core/common.py`, `core/scanner.py`, `core/config.py`, `core/cache.py` sections + `docs/DEVELOPMENT_GUIDE.md` (setup, `PYTHONPATH=. pytest`) |
| `Core / Operations`, `Service / Batch` | `docs/ARCHITECTURE.md` §Operations + §Service (`FileActionService`), `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `operations/files.py`, `services/file_actions.py`, `docs/CLI_REFERENCE.md` (verify `fm` still delegates to service) |
| `Modules / Search`, `Modules / Duplicates`, `Modules / Integrity`, `Modules / Forensics`, `Modules / Recovery`, `Modules / System Cleanup`, `Modules / Metadata`, `Modules / Indicators` | `docs/ARCHITECTURE.md` §Feature modules + `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `modules/*.py` + `docs/CLI_REFERENCE.md` §§ `scan/dupes/search/integrity/cleanup/recover/forensics/metadata` + `docs/GUI_WORKFLOWS.md` view for that module (e.g. Search, Duplicate Finder, Forensics) |
| `Engine / API`, `Engine / Jobs`, `Engine / Daemon`, `Engine / Transport`, `Service / Lifecycle`, `Engine / Parsers` | `docs/ARCHITECTURE.md` §Engine evolution + `docs/proposals/NATIVE_OS_API_REVIEW.md` §§2–5 + `docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md` §I0–N4 + `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `core/provider.py` |
| `UI / Shell` | `docs/GUI_WORKFLOWS.md` full (shell, `BackgroundWorker`, `is_busy`, 14 views, tokens), `docs/ARCHITECTURE.md` §GUI + `dataforge/ui/app.py:114,186,789` + `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `ui/app.py` + `docs/DEVELOPMENT_GUIDE.md` GUI run mode |
| `Build / Packaging`, `Build / Release` | `docs/DEVELOPMENT_GUIDE.md` §Packaging + `docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md` + `docs/ARCHITECTURE.md` §Persistence, `pyproject.toml`, `build_exe.py`, `packaging/README.md` |

> **Rule:** Before editing, `grep -rn` the doc for your file name to find every cross-reference; after editing, update the doc row per `CONTRIBUTING.md §8` “When You Change Code → Update”. Never cite a review as still open without re-verifying the doc’s claim against the current file at `path:line`.

Do not cite a review as still open without re-verifying against the current file at `path:line`.

## File Ownership — The Only Rule for Parallel Safety

- **Write only** to `exclusive_write_files` in your ticket. You may *read* any `read_only_references` but must not `git add` anything outside your exclusive list.
- New files carry ` [NEW FILE]` — `mkdir -p` the parent first. Existing files already exist on `develop` at your wave's start.
- Central touchpoints (`dataforge/ui/app.py`, `pyproject.toml`, `dataforge/engine/daemon.py`, `dataforge/modules/forensics.py`, `dataforge/core/cache.py`) are **single-writer per wave** by design. If two tickets list the same file, they are in *different waves* → they run **sequentially**, not in parallel. Your wave’s disjoint guarantee means no two tickets in the *same wave* share a file — verify with `grep` before pushing.
- Append-only `CHANGELOG.md` under `## [Unreleased]` and `.sdlc/progress.md` are safe for concurrent appends; everything else is exclusive.

## Workflow

### 1. Branch

```bash
git checkout develop && git pull origin develop
git checkout -b feat/TICK-508-forensic-engine-image-streams-indicators
# examples: feat/TICK-102-parallel-scanner, fix/TICK-101-logger-stderr, perf/PERF-102-mmap-hasher
git config core.hooksPath .githooks
git config core.fileMode false   # ignore NTFS 0777→0755 mode noise on /run/media
```

Wave gate: do not start this ticket until every `depends_on` ticket in earlier waves has merged to `develop` (e.g. `TICK-004` waits for `TICK-001`, `TICK-102` waits for `TICK-002`). Within the same wave, all tickets may start concurrently.

### 2. Implement

- Edit only `exclusive_write_files`. Keep the public API described in `architectural_context.existing_symbols_to_use` — additive changes only unless `breaking_changes` says otherwise.
- If you discover you need a file outside your exclusive list, **stop** — file a new ticket or request reassignment. Do not “fix” it opportunistically.
- New tests go to `verification.test_target` (`tests/test_*.py [NEW FILE]`). Follow `tests/test_comprehensive.py` style: `tmp_path` fixture, `monkeypatch`, `cancel_token` (`threading.Event`) checks, `dry_run` no-FS-change assertions.

### 3. Verify (Definition of Done per `CONTRIBUTING.md:458` + CI)

```bash
# per-ticket target
PYTHONPATH=. python -m pytest tests/test_forensic_engine_modules.py -q

# full suite before push (allow 2 world-writable plugin failures on NTFS mounts — fix with chmod 755 on ext4)
PYTHONPATH=. python -m pytest -q

# lint + type (ruff blocking, mypy advisory as in .github/workflows/ci.yml)
ruff check dataforge tests
mypy dataforge/core/image_io.py dataforge/core/streams.py dataforge/modules/indicators.py || true
pip-audit -r requirements.txt || true
```

Each `requirements.acceptance_criteria` line is a `GIVEN/WHEN/THEN` you must demonstrate — run the exact command from `verification.validation_command`. Gate: every `P0` perf change must keep result count identical to sequential baseline on a 100k-file fixture (see `PERFORMANCE_INVESTIGATION.md §7`).

### 4. Commit

```bash
git add <your exclusive_write_files> tests/test_*.py  # never git add -A outside your list
git commit -m "feat(Forensic): image_io + streams + indicators modules (F5/F7/F8)"
# type: feat|fix|docs|refactor|test|chore|style|perf  scope: core|cli|ui|modules|actions|build|docs|tests|repo
# ≤72 chars, no trailing period, backtick-quote symbols (`theme_tokens.py`)
# examples:
#   feat(core): parallel BFS scanner with DirEntry.stat reuse
#   fix(core): route logger console handler to stderr for JSON
#   perf(core): switch hasher to 1 MiB mmap blocks
```

One logical change per commit. Do not batch two tickets. Do not leave finished work uncommitted. Update `docs/` per `CONTRIBUTING.md §8` table if your change touches Arch layers.

### 5. Push & PR

```bash
git fetch origin && git rebase origin/develop   # linear history, no merge commits
git push -u origin feat/TICK-508-forensic-engine-image-streams-indicators
# PR: base develop, title = commit title, body = ticket ID + acceptance checklist, CI must be green
```

Direct push to `develop` is allowed for `docs`/`chore` if CI green and you are on `develop`; otherwise use PR. Never push to `main` (`CONTRIBUTING.md:11 AI Must Not`). Tagging `vX.Y.Z-alpha.N` on `develop` happens only after a work-stream is fully green (see `CONTRIBUTING.md:459`).

## Parallel vs Sequential — When to Choose

| Scenario | Use |
|---|---|
| One dev / small scope | Sequential — waves `0→4` in order, no rebase needed |
| Many tickets, CI green | **Parallel within a wave** — all tickets in same wave have disjoint files, so N agents can run concurrently on N branches (e.g. Wave 1: 9 agents on 9 different files) |
| Two tickets list same file | **Sequential** — they are deliberately in different waves (e.g. `cache.py` W0→W1, `forensics.py` W1→W3, `daemon.py` W0→W3) |
| Time-critical | Parallel within wave + sequential across waves (waves are the gate) |

**Parallel safety checklist before `git push`:**
- [ ] `git diff --name-only origin/develop` shows only files in my `exclusive_write_files` (+ my test file)
- [ ] No file appears in two open PRs from the same wave (check `PARALLEL_BACKLOG.md` Concurrency Map)
- [ ] Rebased onto latest `origin/develop` so `depends_on` tickets are already merged
- [ ] `PYTHONPATH=. python -m pytest -q` green; `ruff check` green

## Failure & Handoff

- If blocked (missing `depends_on` not yet merged), document the blocker in your PR and wait — do not edit the dependency’s file.
- If using `.sdlc/` workspace (see `.github/workflows/sdlc-parallel.workflow.md`), append progress to `progress.md`/`activeContext.md` (append-only, safe for concurrent writes) and write a handoff file for the next wave.

## Completion Checklist (paste into PR)

- [ ] Read `CONSOLIDATED_SPEC.md` + ticket YAML + `read_only_references`
- [ ] Wrote only to `exclusive_write_files` (plus test file)
- [ ] `verification.validation_command` passes
- [ ] `PYTHONPATH=. python -m pytest -q` passes (or documented NTFS caveat)
- [ ] `ruff check` + `mypy` clean
- [ ] Commit follows Conventional Commits and `CONTRIBUTING.md` docs sync table
- [ ] Rebased on `origin/develop`, no file collision with other open PRs in same wave

---

**Start now:** Replace `TICK-508` with your assigned ticket, locate its Work Package in `docs/PARALLEL_BACKLOG.md`, and execute steps 1–5 above. For perf aliases, resolve the alias first and work under the `TICK-*` exclusive list.


---

---

## Work Package YAML

```yaml
ticket_id: "TICK-701"
title: "R-CORE-2/5: config item validation + cache batch commit"
type: "Bugfix"
execution_wave: 7
depends_on: []
scope:
  domain: "Core / Config+Cache"
  exclusive_write_files:
    - "dataforge/core/config.py"
    - "dataforge/core/cache.py"
  read_only_references:
    - "docs/reviews/AUDIT_REPORT.md"
    - "dataforge/core/scanner.py"
    - "dataforge/modules/duplicates.py"
architectural_context:
  existing_symbols_to_use:
    - "config.py: _validate_one, DEFAULT_CONFIG"
    - "config.py: _merge_validated"
    - "cache.py: FileHashCache, set_hash, set_hash_many"
  breaking_changes: "None — validation tightens, batch path is additive"
requirements:
  summary: |
    Fix R-CORE-2: config.py: _validate_one for excluded_extensions/folders currently returns isinstance(val,list) without checking items. A list containing int/None/dict then reaches scanner.py:220 where set() or endswith() crashes. Tighten _validate_one to check every item is a non-empty str (strip, check len>0, check not containing path separators except for extensions). Invalid items are dropped with logger.warning and the key is replaced by default if all items invalid.

    Fix R-CORE-5: cache.py: set_hash() does per-file execute+commit (fsync) → I/O bound on large scans (1 fsync/file). TICK-104 added set_hash_many(executemany+commit) and duplicates.py/integrity.py now use it, but direct set_hash callers (e.g., hasher.py, search.py) still pay per-file cost. Add a write-behind batch buffer: set_hash() appends to an in-memory list and flushes via set_hash_many when batch >= cache_batch_size (from config) or on explicit flush() / close(). Preserve explicit set_hash_many and file_cache.flush() API. Ensure thread-safety via existing self._lock and handle conn is None guard from TICK-501.
  source_documents:
    - "docs/reviews/AUDIT_REPORT.md"
  acceptance_criteria:
    - "GIVEN config.json contains excluded_extensions=['.log', 123, null] WHEN ConfigManager load THEN only ['.log'] remains, warning logged, no crash on next scan_directory"
    - "GIVEN config.json contains excluded_folders=['node_modules', 123] WHEN load THEN only ['node_modules'] remains"
    - "GIVEN 1000 files with set_hash called in tight loop WHEN batch_size=500 THEN at most 3 commits observed (spy on conn.commit count)"
    - "GIVEN cache init fails (conn is None) WHEN set_hash called THEN no crash, returns None (null-guard preserved)"
verification:
  test_target: "tests/test_core_item_validation.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_core_item_validation.py -q"
```

---

## Implementation Notes

### R-CORE-2: Config item validation
```python
# In _validate_one, for excluded_* keys:
if key in ("excluded_extensions", "excluded_folders", "dashboard_paths"):
    if not isinstance(val, list):
        return False
    # NEW: check every item is non-empty str
    cleaned = []
    for item in val:
        if not isinstance(item, str) or not item.strip():
            logger.warning("Config %s: dropping invalid item %r", key, item)
            continue
        cleaned.append(item.strip())
    # mutate to cleaned list for merge
    # if all invalid, treat as invalid
    return len(cleaned) > 0 or len(val) == 0
```

### R-CORE-5: Cache batch commit
```python
# In CacheManager:
def set_hash(self, path, size, mtime, file_hash, algo="md5"):
    if self.conn is None:
        return None
    with self._lock:
        self._batch_buffer.append((path, size, mtime, file_hash, algo))
        if len(self._batch_buffer) >= self._batch_size:
            self._flush_batch_locked()  # calls set_hash_many
```
