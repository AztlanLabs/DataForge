# 🔨 DataForge Development Guide

*File System Management with Steroids and Superpowers*

**Last verified:** 2026-08-23 09:00 UTC *(re-verified against `pyproject.toml` / `build_exe.py` / `dataforge/` HEAD `b373e7e`; Wave 5+6 12/12 DONE, venv ext4 recommendation)*

## Effective Project Root

The application lives inside the repository subdirectory:

```text
DataForge/
```

That means most development commands should be run from there:

```bash
cd DataForge
```

## Local environment setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
```

### Why both commands matter

- `requirements.txt` contains the runtime stack (CLI + GUI/media). `requirements-dev.txt` adds build/test tooling (`pytest`, `pyinstaller`) via `-r requirements.txt`.
- `pyproject.toml` defines the package metadata and the `fm` console script; `setup.py` is a thin shim so `pip install -e .` and `python setup.py sdist` still work.

If you skip the editable install, use `PYTHONPATH=. python -m dataforge.cli ...` instead of `fm ...`.

## Run modes

### GUI

```bash
python run_ui.py
```

### CLI

```bash
fm --help
```

### Tests — Fast (per-ticket) vs Full (CI)

**Fast per-ticket (for agents, ~1-15s, no coverage):**

```bash
python scripts/run_ticket_tests.py TICK-921          # reads test_target from ticket YAML
python scripts/run_ticket_tests.py --file tests/test_dead_code_prune.py
# or manually:
QT_QPA_PLATFORM=offscreen pytest tests/test_dead_code_prune.py -q -o addopts= -p no:cov
```

Full suite is 1200+ tests and ~60s without coverage / ~260s with coverage — do NOT run it for every ticket iteration. Use the runner above.

**Full suite (only for final verification):**

```bash
QT_QPA_PLATFORM=offscreen pytest -q -o addopts= -p no:cov -n auto   # fast full, parallel (needs pytest-xdist, ~60s)
PYTHONPATH=. pytest -q --cov=dataforge --cov-report=term-missing --cov-report=xml  # CI mode with coverage (~260s, 59%)
```

The nested project layout means plain `pytest -q` may not resolve `dataforge` unless the package is installed or the project root is placed on `PYTHONPATH`. The runner sets `PYTHONPATH=.` and `QT_QPA_PLATFORM=offscreen` for you.

After TICK-912 the suite is consolidated: `tests/test_consolidated_suite.py` (44 tests) replaces 5 deprecated files (271 tests). See `scripts/tests_consolidate.py --audit` and [`docs/reviews/AUDIT_REPORT.md`](./reviews/AUDIT_REPORT.md) for verification details. Use `scripts/run_ticket_tests.py --full` to audit.

## Packaging and distribution

### Python package

- `pyproject.toml` defines the package name `dataforge`
- console script: `fm=dataforge.cli:main`

### Executable builds

Use the PyInstaller wrapper:

```bash
python build_exe.py release
python build_exe.py debug
python build_exe.py all
```

### Build profiles

| Profile | Output style | Notes |
| --- | --- | --- |
| `release` | one-file, windowed | produces the end-user desktop bundle |
| `debug` | one-dir, console, debug enabled | useful for inspecting runtime issues |

Related files:

- `build_exe.py`
- `buildspec/release/DataForge.spec`
- `buildspec/debug/DataForge-debug.spec`

Generated artifacts land in:

- `dist/`
- `build/`

Those folders should be treated as outputs, not maintained source.

## Runtime artifacts

| Artifact | Path | Notes |
| --- | --- | --- |
| Config directory | `~/.dataforge/` | created on first run |
| Config file | `~/.dataforge/config.json` | theme, exclusions, performance settings, dashboard paths |
| Cache DB | `~/.dataforge/cache.db` | SQLite hash cache |
| Log file | `~/.dataforge/app.log` | rotating file log |

## Source map for contributors

| Path | What to change there |
| --- | --- |
| `dataforge/core/common.py` | shared file metadata types |
| `dataforge/core/audit.py` | hash-chained audit log (TICK-304) |
| `dataforge/core/case.py` | CaseContext + Evidence Mode singleton (TICK-304) |
| `dataforge/core/scanner.py` | scan behavior, traversal, and exclusion honoring |
| `dataforge/core/config.py` | persistent settings |
| `dataforge/core/cache.py` | hash cache behavior |
| `dataforge/core/operations/files.py` | low-level rename/move/copy/delete/archive primitives |
| `dataforge/core/services/file_actions.py` | centralized batch file actions |
| `dataforge/modules/` | feature logic reusable across CLI and GUI |
| `dataforge/client/` | engine client with auto-discover (TICK-301) |
| `dataforge/service/` | daemon entrypoint + OS lifecycle files (TICK-301/302) |
| `dataforge/core/actions/` | Action Builder pipeline steps |
| `dataforge/ui/views/` | top-level desktop screens |
| `dataforge/ui/plugins/` | plugin views |
| `tests/` | behavioral and regression validation |

## Contributor rules of thumb

### Prefer shared services over ad hoc file writes

If you are implementing move/copy/delete/rename/archive behavior, check `FileActionService` and `dataforge/core/operations/files.py` first. That is the intended mutation path.

### Keep long-running GUI work off the main thread

For new views or view actions:

- use `app.run_workflow()` when the worker supports progress reporting
- use `app.run_background()` for other threaded work
- accept `cancel_token` and optionally `progress_callback` in worker functions

### Reuse the query/search layer

New discovery workflows should generally build on:

- `build_search_query()`
- `iter_search_files()`
- `search_files()`

### Use `BaseView` as the desktop contract

New top-level screens and plugins should inherit from `BaseView` and use its shared helpers for:

- preview confirmations
- validation
- batch-outcome summaries

## Test suite structure

| File | Focus | Status |
| --- | --- | --- |
| `tests/test_consolidated_suite.py` | consolidated parametrized suite replacing 5 deprecated files (271 tests → 44) | passes (44+1 skipped) |
| `tests/test_dead_code_prune.py` | TICK-913 dead-code prune verification | passes (10) |
| `tests/test_cursor_pointers.py` | TICK-908 cursor pointers + QPainter hardening | passes (12) |
| `tests/test_global_stability.py` | TICK-911 job lifecycle + queue depth + coalesce | passes (17) |
| `tests/test_audit_evidence_mode.py` | audit log, CaseContext, Evidence Mode gate, forensic provenance | passes (21) |
| `tests/test_daemon_client_integration.py` | daemon job queue, client auto-discover, in-process fallback | passes (21) |
| `tests/test_service_lifecycle.py` | systemd/launchd/Windows lifecycle files | passes (34) |
| `tests/test_packaging_nfpm.py` | nfpm deb/rpm packaging, postinst/prerm scripts | passes (51) |
| `tests/test_consolidated_suite.py` | (see above) consolidated | passes (44) |
| Deprecated (removed) | `test_comprehensive.py`, `test_integration.py`, `test_contract_regressions.py`, `test_new_modules.py`, `verify_scenarios.py` | removed at TICK-912 (271 tests) |

Use `python scripts/run_ticket_tests.py TICK-xxx` for per-ticket fast runs. Full suite ~1225 tests, ~60s without coverage (xdist) / ~260s with coverage.

## Practical maintenance notes

- The repository mixes application source with generated build output. Be deliberate about which files are source of truth.
- The repository is under Git version control on `develop` and `main` branches. Follow [`docs/CONTRIBUTING.md`](./CONTRIBUTING.md) for the complete development workflow — commit conventions, versioning, release process, and implementation plan format. A `commit-msg` hook in `.githooks/` validates every commit; install it with `git config core.hooksPath .githooks`.
- **CI runs on every push/PR.** `.github/workflows/ci.yml` runs pytest + coverage, ruff (blocking), mypy (advisory), and pip-audit on push/PR to `develop`/`main`. See [`reviews/ROADMAP.md`](./reviews/ROADMAP.md) WS-A.
- The plugin loader registers every discovered `BaseView` subclass in `dataforge/ui/plugins/`; plugin import failures are now logged (via `logger.error`) and skipped. Loading is **opt-in** behind `config["plugins_enabled"]` (default off) and the loader refuses plugins in group/world-writable directories or files owned by another user. Only add plugins you trust (S5, fixed in WS-B).
- The stray empty `26.1.2` file has been removed and a root `.gitignore` added.
- The current dependency story is split: `pyproject.toml` is enough for the core package/CLI entrypoint; `requirements.txt` provisions the full GUI/media runtime, and `requirements-dev.txt` adds the build/test tooling.
- Settings **autosave** on every change through `ConfigManager.set()` (no Save button) and flash a transient "Saved ✓" indicator — see `BaseView._autosave` / `_saved_indicator` in `dataforge/ui/views/settings.py` (2c.2).

## Recommended onboarding order

1. Read [`../README.md`](../README.md)
2. Read [`./ARCHITECTURE.md`](./ARCHITECTURE.md)
3. Read [`./GUI_WORKFLOWS.md`](./GUI_WORKFLOWS.md) or [`./CLI_REFERENCE.md`](./CLI_REFERENCE.md), depending on your work area
4. Use [`./TECHNICAL_SOURCE_OF_TRUTH.md`](./TECHNICAL_SOURCE_OF_TRUTH.md) when you need file-by-file depth
5. Read [`./CONTRIBUTING.md`](./CONTRIBUTING.md) for commit conventions, versioning, and implementation plan format — required before your first commit
6. Skim [`./reviews/README.md`](./reviews/README.md) for the current bug/security/UX backlog before picking up work
