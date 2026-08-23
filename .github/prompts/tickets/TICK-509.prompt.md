> **Status: ✅ COMPLETED 2026-08-23 — Wave 5 DONE, verified (see docs/PARALLEL_BACKLOG.md Wave 5 Review). This ticket is closed — do not re-run.**

# Ticket TICK-509 — Plugin loader isolation (subprocess + signing) — F12 (remainder)

> **Wave 5** | **Domain:** UI / Plugin Loader | **Depends on:** "TICK-401"
> **Source:** `docs/reviews/FORENSIC_REVIEW.md` §F12 (Plugin loader full privileges — leftover after Wave 1 S5 fix)
> **Complements:** Wave 5 master set already covers R-CORE-3/4/6, F1, F4, F9, F14, U3, U4. TICK-509 closes the **plugin isolation / signing** gap that no other Wave 5 ticket covers. S5 already addressed opt-in + world-writable + owner-writable; this ticket closes ProcessPool isolation + signature verification.

---

## Your Assignment

```
TICKET_ID: TICK-509
WAVE: 5
TITLE: Plugin loader isolation (subprocess + signing) — F12 (remainder)
```

**Exclusive write files (SOLE writer for Wave 5):**
- `dataforge/ui/plugin_loader.py`

**Read-only references (do not edit):**
- `docs/reviews/FORENSIC_REVIEW.md` §F12
- `dataforge/core/audit.py` (each plugin load result appends to `AuditLog`)
- `dataforge/core/paths.py` (default `~/.local/share/DataForge/plugins-trusted.gpg` trust anchor location)

**Test target:** `tests/test_plugin_loader_isolation.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_plugin_loader_isolation.py -q`

**Depends on:** `"TICK-401"`

---

## Relevant Documentation — Must Read Before Coding

> **This ticket’s domain is `UI / Plugin Loader` — the docs below are the authoritative sources for the files you will touch. Read them in order before editing code, and update them per `CONTRIBUTING.md §8` after editing.**

- `docs/reviews/FORENSIC_REVIEW.md` §F12 (Plugin loader full privileges; S5 opt-in + perms are done in Wave 1)
- `docs/CONSOLIDATED_SPEC.md` §7 GUI + §6 Forensic
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `ui/plugin_loader.py` section
- `docs/GUI_WORKFLOWS.md` shell/plugin section
- `docs/ARCHITECTURE.md` §GUI + plugin slots
- `docs/CONTRIBUTING.md` §8 (When You Change Code → Update table)
- `docs/CONSOLIDATED_SPEC.md` §2–7 (canonical spec)

> **How to verify you read them:** `grep -rn "PluginLoader\|plugin_loader\|HAS_PLUGINSIGN" docs/` should show every cross-reference you must keep in sync; after your change, re-run the grep and fix stale links. Never cite a review as open without `Read`ing the file at `path:line`.

---

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` (and `docs/proposals/PERFORMANCE_TICKETS.md` aliases) in parallel. Copy this prompt, replace `TICK-509` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

---

## Role

You are an autonomous coding agent working on the **DataForge** repo (`develop` branch, Python 3.10+, PyQt5, Click, SQLite WAL). Your only job is to complete **one** ticket end-to-end: code, tests, docs, verification, and a Conventional Commits push.

## Ticket Assignment

```
TICKET_ID: TICK-509   # e.g. TICK-102 or PERF-101 (alias — see alias map)
WAVE:      5        # from Concurrency Map in docs/PARALLEL_BACKLOG.md
```

If `TICK-509` starts with `PERF-`, resolve its alias first (`PERF-100→TICK-004`, `PERF-101→TICK-102`, `PERF-103→TICK-104`, etc. — see `PARALLEL_BACKLOG.md` Appendix). Never run a `PERF-*` and its `TICK-*` twin in the same wave.

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
| `Engine / API`, `Engine / Jobs`, `Engine / Daemon`, `Engine / Transport`, `Service / Lifecycle` | `docs/ARCHITECTURE.md` §Engine evolution + `docs/proposals/NATIVE_OS_API_REVIEW.md` §§2–5 + `docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md` §I0–N4 + `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `core/provider.py` |
| `UI / Shell`, `UI / Plugin Loader` | `docs/GUI_WORKFLOWS.md` full (shell, `BackgroundWorker`, `is_busy`, 14 views, tokens, plugins), `docs/ARCHITECTURE.md` §GUI + `dataforge/ui/app.py:114,186,789` + `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `ui/app.py` + `docs/DEVELOPMENT_GUIDE.md` GUI run mode |
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
git checkout -b feat/TICK-509-plugin-loader-isolation
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
PYTHONPATH=. python -m pytest tests/test_plugin_loader_isolation.py -q

# full suite before push (allow 2 world-writable plugin failures on NTFS mounts — fix with chmod 755 on ext4)
PYTHONPATH=. python -m pytest -q

# lint + type (ruff blocking, mypy advisory as in .github/workflows/ci.yml)
ruff check dataforge tests
mypy dataforge/ui/plugin_loader.py || true
pip-audit -r requirements.txt || true
```

Each `requirements.acceptance_criteria` line is a `GIVEN/WHEN/THEN` you must demonstrate — run the exact command from `verification.validation_command`. Gate: every `P0` perf change must keep result count identical to sequential baseline on a 100k-file fixture (see `PERFORMANCE_INVESTIGATION.md §7`).

### 4. Commit

```bash
git add <your exclusive_write_files> tests/test_*.py  # never git add -A outside your list
git commit -m "feat(ui): plugin loader subprocess isolation + signature checks"
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
git push -u origin feat/TICK-509-plugin-loader-isolation
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

**Start now:** Replace `TICK-509` with your assigned ticket, locate its Work Package in `docs/PARALLEL_BACKLOG.md`, and execute steps 1–5 above. For perf aliases, resolve the alias first and work under the `TICK-*` exclusive list.


---

## Work Package YAML for TICK-509 (from `docs/PARALLEL_BACKLOG.md`)

```yaml
ticket_id: "TICK-509"
title: "Plugin loader isolation (subprocess + signing) — F12 (remainder)"
type: "Feature"
execution_wave: 5
depends_on: ["TICK-401"]
scope:
  domain: "UI / Plugin Loader"
  exclusive_write_files:
    - "dataforge/ui/plugin_loader.py"
  read_only_references:
    - "docs/reviews/FORENSIC_REVIEW.md"
    - "dataforge/core/audit.py"
    - "dataforge/core/paths.py"
architectural_context:
  existing_symbols_to_use:
    - "PluginLoader (dataforge/ui/plugin_loader.py:13)  [+28 S5: opt-in + world/owner-writable checks]"
    - "load_plugins (dataforge/ui/plugin_loader.py:35) [currently `enabled` flag-gated]"
    - "AuditLog.append (dataforge/core/audit.py:60)  [forensic_event sink]"
  breaking_changes: "Additive — new optional `isolation='subprocess' | 'inline'` default `inline`; new `require_signed: bool` opt (default `False`) for backwards compat"
requirements:
  summary: "Close F12 (remainder) by adding two independent isolation knobs to `PluginLoader`: (1) `isolation='subprocess'` runs each plugin's import + entrypoints in `multiprocessing.Process` (or `subprocess.run(['python', '-c', ...])` for the dynamic-import case) under a `concurrent.futures.ProcessPoolExecutor(max_workers=min(2, cpu_count()-1))` and discards the worker on timeout/crash; the result (list of plugin instances) is returned via `multiprocessing.Queue`. (2) `require_signed=True` verifies a detached signature file `plugin.sig` next to each `plugin.py` against a configurable trust anchor (default location `~/.local/share/DataForge/plugins-trusted.gpg` if `python-gnupg` is installed, else a plain SHA-256 fingerprint whitelist at `~/.local/share/DataForge/plugins-trusted.sha256`). Each successful load (or refuse) appends an entry to `AuditLog` via `AuditLog.append({event: 'plugin_load', path, sha256, signed: bool, isolation: str})` so the chain captures plugin provenance."
  source_documents:
    - "docs/reviews/FORENSIC_REVIEW.md#summary--the-5-disqualifiers"
    - "docs/reviews/FORENSIC_REVIEW.md#index--all-findings-status-at-2026-07-12"
  acceptance_criteria:
    - "GIVEN PluginLoader(enabled=True, isolation='subprocess') and a malicious plugin that raises ZeroDivisionError at import WHEN load_plugins is called THEN it does NOT propagate the exception into the main UI thread (worker is killed by timeout); result `[]` is returned; AuditLog entry `event='plugin_load_failed' path=...` is appended"
    - "GIVEN PluginLoader(enabled=True, require_signed=True, trust_anchor=sha256_whitelist) and a signed plugin WITH valid sig WHEN load_plugins is called THEN the plugin is loaded and AuditLog entry `event='plugin_load_signed' sha256=...` is appended"
    - "GIVEN PluginLoader(enabled=True, require_signed=True) and a plugin WITHOUT .sig file WHEN load_plugins is called THEN the plugin is REJECTED with a `PluginSignatureMissingError`; AuditLog `event='plugin_load_unsigned_refused'`"
    - "GIVEN require_signed=False (default for backwards-compat) WHEN load_plugins is called THEN behaviour is unchanged: opt-in + world/owner-writable checks still apply (S5 coverage preserved)"
    - "GIVEN an existing plugin (e.g. MetadataCleanerPlugin) loaded under isolation='inline' WHEN load_plugins is called THEN it returns the same list as before — no regression"
verification:
  test_target: "tests/test_plugin_loader_isolation.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_plugin_loader_isolation.py -q"
```
