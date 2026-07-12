# 🔨 DataForge Development Guide

*File System Management with Steroids and Superpowers*

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
- `setup.py` installs the package and the `fm` console script.

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

### Tests

```bash
PYTHONPATH=. pytest -q
```

The nested project layout means plain `pytest -q` may not resolve `dataforge` unless the package is installed or the project root is placed on `PYTHONPATH`.

The full suite passes — 254 tests. The earlier collection failure (a stale `rename_with_regex` import) has been fixed. See [`docs/reviews/NOTES_REVIEW.md`](./reviews/NOTES_REVIEW.md) for verification details.

## Packaging and distribution

### Python package

- `setup.py` defines the package name `dataforge`
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
| `dataforge/core/scanner.py` | scan behavior, traversal, and exclusion honoring |
| `dataforge/core/config.py` | persistent settings |
| `dataforge/core/cache.py` | hash cache behavior |
| `dataforge/core/operations/files.py` | low-level rename/move/copy/delete/archive primitives |
| `dataforge/core/services/file_actions.py` | centralized batch file actions |
| `dataforge/modules/` | feature logic reusable across CLI and GUI |
| `dataforge/core/actions/` | Action Builder pipeline steps |
| `dataforge/ui/views/` | top-level desktop screens |
| `dataforge/ui/plugins/` | plugin views |
| `tests/` | behavioral and regression validation |

## Contributor rules of thumb

### Prefer shared services over ad hoc file writes

If you are implementing move/copy/delete/rename/archive behavior, check `FileActionService` and `core/operations/files.py` first. That is the intended mutation path.

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
| `tests/test_comprehensive.py` | wide feature coverage across core modules, services, media, and actions | passes (147) |
| `tests/test_integration.py` | end-to-end workflows and packaging/plugin paths | passes (18) |
| `tests/test_contract_regressions.py` | CLI and GUI-facing contract expectations | passes (50) |
| `tests/test_new_modules.py` | newer modules (hardware, forensics, recovery, metadata, etc.) | passes (9) |
| `tests/verify_scenarios.py` | scenario-style validation helpers | standalone script |

## Practical maintenance notes

- The repository mixes application source with generated build output. Be deliberate about which files are source of truth.
- The repository is under Git version control on `develop` and `main` branches. Follow [`docs/COMMIT_CONVENTION.md`](./COMMIT_CONVENTION.md) for commit messages and see [`docs/VERSIONING.md`](./VERSIONING.md) for the semver release process. A `commit-msg` hook in `.githooks/` validates every commit; install it with `git config core.hooksPath .githooks`.
- **CI is not yet wired.** Tests do not run automatically on push. Setting up CI/CD is the highest-leverage next step — see [`reviews/IMPROVEMENT_PLAN.md`](./reviews/IMPROVEMENT_PLAN.md), Phase 0.
- The plugin loader registers every discovered `BaseView` subclass in `dataforge/ui/plugins/`; plugin import failures are now logged (via `logger.error`) and skipped. Plugins are arbitrary code executed with full app privileges — only add plugins you trust (see `reviews/02`, S5).
- The stray empty `26.1.2` file has been removed and a root `.gitignore` added (the tree still needs to be put under version control).
- The current dependency story is split: `setup.py` is enough for the core package/CLI entrypoint; `requirements.txt` provisions the full GUI/media runtime, and `requirements-dev.txt` adds the build/test tooling.
- Settings are saved immediately through `ConfigManager.set()`, so UI changes often persist at the moment a control is saved rather than on app shutdown.

## Recommended onboarding order

1. Read [`../README.md`](../README.md)
2. Read [`./ARCHITECTURE.md`](./ARCHITECTURE.md)
3. Read [`./GUI_WORKFLOWS.md`](./GUI_WORKFLOWS.md) or [`./CLI_REFERENCE.md`](./CLI_REFERENCE.md), depending on your work area
4. Use [`./TECHNICAL_SOURCE_OF_TRUTH.md`](./TECHNICAL_SOURCE_OF_TRUTH.md) when you need file-by-file depth
5. Read [`./COMMIT_CONVENTION.md`](./COMMIT_CONVENTION.md) and [`./VERSIONING.md`](./VERSIONING.md) before your first commit
6. Skim [`./reviews/EXECUTIVE_SUMMARY.md`](./reviews/EXECUTIVE_SUMMARY.md) for the current bug/security/UX backlog before picking up work
