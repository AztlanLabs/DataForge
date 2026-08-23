> **Status: ✅ COMPLETED 2026-08-23 — Wave 5 DONE, verified (see docs/PARALLEL_BACKLOG.md Wave 5 Review). This ticket is closed — do not re-run.**

# Ticket TICK-511 — Parser ProcessPool isolation — F13

> **Wave 5** | **Domain:** Engine / Parsers | **Depends on:** "TICK-301"
> **Source:** `docs/reviews/FORENSIC_REVIEW.md` §F13 (Parsers in-process, no isolation — a malicious or buggy parser exception can crash the whole app; a parser that segfaults a C extension takes down DataForge)
> **Complements:** Wave 5 master set already covers R-CORE-3/4/6, F1, F4, F9, F14, U3, U4. TICK-511 closes the **parser isolation** gap that no other Wave 5 ticket covers. Lives in a NEW module that any parser (registry-style) can register to.

---

## Your Assignment

```
TICKET_ID: TICK-511
WAVE: 5
TITLE: Parser ProcessPool isolation — F13
```

**Exclusive write files (SOLE writer for Wave 5):**
- `dataforge/engine/parsers.py [NEW FILE]`

**Read-only references (do not edit):**
- `docs/reviews/FORENSIC_REVIEW.md` §F13
- `dataforge/engine/jobs.py` (Engine uses `ThreadPoolExecutor` already; this ticket adds a complementary `ProcessPoolExecutor`)
- `dataforge/modules/forensics.py:127` `parse_os_artifacts` (this is one of the parsers that should opt-in to the pool)

**Test target:** `tests/test_parser_pool_isolation.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_parser_pool_isolation.py -q`

**Depends on:** `"TICK-301"`

---

## Relevant Documentation — Must Read Before Coding

> **This ticket’s domain is `Engine / Parsers` — the docs below are the authoritative sources for the files you will touch. Read them in order before editing code, and update them per `CONTRIBUTING.md §8` after editing.**

- `docs/reviews/FORENSIC_REVIEW.md` §F13 (Parsers in-process, no isolation)
- `docs/proposals/PERFORMANCE_INVESTIGATION.md` §1.13 (pool sizing)
- `docs/CONSOLIDATED_SPEC.md` §3 Engine + §6 Forensic
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `engine/jobs.py`, `engine/daemon.py` sections + new `engine/parsers.py` subsection
- `docs/ARCHITECTURE.md` §Engine evolution
- `docs/CONTRIBUTING.md` §8 (When You Change Code → Update table)
- `docs/CONSOLIDATED_SPEC.md` §2–7 (canonical spec)

> **How to verify you read them:** `grep -rn "ProcessPoolExecutor\|parse_os_artifacts\|parser_pool" docs/` should show every cross-reference you must keep in sync; after your change, re-run the grep and fix stale links. Never cite a review as open without `Read`ing the file at `path:line`.

---

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` (and `docs/proposals/PERFORMANCE_TICKETS.md` aliases) in parallel. Copy this prompt, replace `TICK-511` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

---

## Role

You are an autonomous coding agent working on the **DataForge** repo (`develop` branch, Python 3.10+, PyQt5, Click, SQLite WAL). Your only job is to complete **one** ticket end-to-end: code, tests, docs, verification, and a Conventional Commits push.

## Ticket Assignment

```
TICKET_ID: TICK-511   # e.g. TICK-102 or PERF-101 (alias — see alias map)
WAVE:      5        # from Concurrency Map in docs/PARALLEL_BACKLOG.md
```

If `TICK-511` starts with `PERF-`, resolve its alias first (`PERF-100→TICK-004`, `PERF-101→TICK-102`, `PERF-103→TICK-104`, etc. — see `PARALLEL_BACKLOG.md` Appendix). Never run a `PERF-*` and its `TICK-*` twin in the same wave.

## Required Reading (in order, before touching code)

1. `docs/CONSOLIDATED_SPEC.md` §2–7 — canonical layers, seams, and domain models (your ticket's `scope` assumes this).
2. `docs/PARALLEL_BACKLOG.md` — Concurrency Map (your wave + `depends_on`) + **How to Work a Ticket — Sequential and Parallel Execution Guide** (§ after the map). For perf-only tickets also read `docs/proposals/PERFORMANCE_TICKETS.md` alias map.
3. `docs/CONTRIBUTING.md` §3, §8, §10 — Conventional Commits (`type(scope): description` ≤72 chars, `commit-msg` hook), docs sync table, and parallel-vs-sequential rules. Also `docs/AUDIT_HARDENED_2026-08-22.md` for why the backlog is hardened.
4. Your ticket's **Work Package YAML** in `docs/PARALLEL_BACKLOG.md` — `exclusive_write_files`, `read_only_references`, `architectural_context`, `requirements.acceptance_criteria`, `verification`.
5. The files listed in `read_only_references` and `architectural_context.existing_symbols_to_use` (e.g. `dataforge/core/common.py:5`, `dataforge/core/scanner.py:22`, `dataforge/ui/app.py:114`).

### 6. Domain-Relevant Documentation (read the row for your ticket's `scope`)

| Ticket scope | Must also read |
|---|---|
| `Core / Infrastructure`, `Core / Provider`, `Core / Persistence`, `Core / Cache`, `Core / Logger`, `Core / Scanner`, `Core / Hasher`, `Core / Operations` | `docs/ARCHITECTURE.md` §Core primitives + `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `core/common.py`, `core/scanner.py`, `core/config.py`, `core/cache.py` sections + `docs/DEVELOPMENT_GUIDE.md` (setup, `PYTHONPATH=. pytest`) |
| `Core / Operations`, `Service / Batch` | `docs/ARCHITECTURE.md` §Operations + §Service (`FileActionService`), `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `operations/files.py`, `services/file_actions.py`, `docs/CLI_REFERENCE.md` (verify `fm` still delegates to service) |
| `Modules / Search`, `Modules / Duplicates`, `Modules / Integrity`, `Modules / Forensics`, `Modules / Recovery`, `Modules / System Cleanup`, `Modules / Metadata` | `docs/ARCHITECTURE.md` §Feature modules + `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `modules/*.py` + `docs/CLI_REFERENCE.md` §§ `scan/dupes/search/integrity/cleanup/recover/forensics/metadata` + `docs/GUI_WORKFLOWS.md` view for that module (e.g. Search, Duplicate Finder, Forensics) |
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
git checkout -b feat/TICK-511-parser-processpool-isolation
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
PYTHONPATH=. python -m pytest tests/test_parser_pool_isolation.py -q

# full suite before push (allow 2 world-writable plugin failures on NTFS mounts — fix with chmod 755 on ext4)
PYTHONPATH=. python -m pytest -q

# lint + type (ruff blocking, mypy advisory as in .github/workflows/ci.yml)
ruff check dataforge tests
mypy dataforge/engine/parsers.py || true
pip-audit -r requirements.txt || true
```

Each `requirements.acceptance_criteria` line is a `GIVEN/WHEN/THEN` you must demonstrate — run the exact command from `verification.validation_command`. Gate: every `P0` perf change must keep result count identical to sequential baseline on a 100k-file fixture (see `PERFORMANCE_INVESTIGATION.md §7`).

### 4. Commit

```bash
git add <your exclusive_write_files> tests/test_*.py  # never git add -A outside your list
git commit -m "feat(engine): parser ProcessPool isolation (F13)"
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
git push -u origin feat/TICK-511-parser-processpool-isolation
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

**Start now:** Replace `TICK-511` with your assigned ticket, locate its Work Package in `docs/PARALLEL_BACKLOG.md`, and execute steps 1–5 above. For perf aliases, resolve the alias first and work under the `TICK-*` exclusive list.


---

## Work Package YAML for TICK-511 (from `docs/PARALLEL_BACKLOG.md`)

```yaml
ticket_id: "TICK-511"
title: "Parser ProcessPool isolation — F13"
type: "Feature"
execution_wave: 5
depends_on: ["TICK-301"]
scope:
  domain: "Engine / Parsers"
  exclusive_write_files:
    - "dataforge/engine/parsers.py [NEW FILE]"
  read_only_references:
    - "docs/reviews/FORENSIC_REVIEW.md"
    - "dataforge/engine/jobs.py"
    - "dataforge/modules/forensics.py"
architectural_context:
  existing_symbols_to_use:
    - "JobQueue (dataforge/engine/jobs.py:1)  [ThreadPool + ProcessPool already imported]"
    - "Job + cancel_token (dataforge/engine/jobs.py:1)"
    - "parse_os_artifacts (dataforge/modules/forensics.py:127)  [example opt-in caller]"
  breaking_changes: "None — additive: new module, no changes to existing call sites (Wave 6 ticket can opt-in call sites)."
requirements:
  summary: "Close F13 by introducing `dataforge/engine/parsers.py` with `ParserPool` — a `concurrent.futures.ProcessPoolExecutor(min(2, cpu_count()-1))` (lazy-initialised in `__init__`) plus a `register(name, fn)` registry for parser functions (each function is `@pickle`-able and takes `(path: str, cancel_token: threading.Event) -> ParseResult`) and a `run(name, path, cancel_token=None)` entry point. On `ProcessPoolExecutor`, worker crashes (segfault/timeout) are reported as `ParseResult(success=False, message='worker died')` rather than propagating into the main thread — `concurrent.futures` cancels the future on `BrokenProcessPool` and the public API surface returns the failure result instead. Default `pool_size=min(2, cpu_count()-1)` leaves cores for the rest of DataForge; CLI flag `--parser-pool-size N` overrides (env `DATAFORGE_PARSER_POOL_SIZE`). No existing call sites are modified in this ticket — opt-in happens in a follow-up Wave 6 ticket (`TICK-601-parser-opt-in`) so this ticket stays purely additive."
  source_documents:
    - "docs/reviews/FORENSIC_REVIEW.md#index--all-findings-status-at-2026-07-12"
    - "docs/proposals/PERFORMANCE_INVESTIGATION.md"
  acceptance_criteria:
    - "GIVEN ParserPool() with default settings WHEN inspect.getmembers(ParserPool) THEN `executor is None` until first call (lazy init)"
    - "GIVEN a `register('evil', lambda p, t: 1/0)` lambda WHEN `run('evil', '/tmp/x', cancel_token)` is called AND the lambda raises ZeroDivisionError in a worker THEN the future is reported as `ParseResult(success=False, message='ZeroDivisionError')`; main thread is NOT killed"
    - "GIVEN `pool_size=1` and 2 simultaneous `run(...)` calls THEN they serialise on the single worker (proven via wall-time + tagged-print order)"
    - "GIVEN cancel_token.is_set() before run WHEN run('parse', path, cancel_token) is called THEN the worker bails out early and returns `ParseResult(success=False, message='cancelled')` within 1 second"
    - "GIVEN the import succeeds on POSIX AND Windows (no platform-specific code required) WHEN `import dataforge.engine.parsers` is performed THEN no ImportError on either"
    - "GIVEN no call sites modified (intentional) WHEN the existing test suite runs THEN no regression (Lazy init means no extra processes are spawned unless used)"
verification:
  test_target: "tests/test_parser_pool_isolation.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_parser_pool_isolation.py -q"
```
