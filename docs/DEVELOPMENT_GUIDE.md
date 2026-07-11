# 🔨 DataForge Development Guide

*File System Management with Steroids and Superpowers*

## Effective Project Root

The application lives inside the repository subdirectory:

```text
FileManager/
```

That means most development commands should be run from there:

```bash
cd FileManager
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

If you skip the editable install, use `PYTHONPATH=. python -m filemanager.cli ...` instead of `fm ...`.

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

The nested project layout means plain `pytest -q` may not resolve `filemanager` unless the package is installed or the project root is placed on `PYTHONPATH`.

> [!NOTE]
> **The full suite passes — 224 tests.** The earlier collection failure (a stale `rename_with_regex` import in `tests/test_comprehensive.py`) has been fixed; see [`reviews/01_CODE_REVIEW_AND_BUGS.md`](./reviews/01_CODE_REVIEW_AND_BUGS.md) (H1). Just run `PYTHONPATH=. pytest -q`.

## Packaging and distribution

### Python package

- `setup.py` defines the package name `filemanager-utils`
- console script: `fm=filemanager.cli:main`

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
- `buildspec/release/FileManager.spec`
- `buildspec/debug/FileManager-debug.spec`

Generated artifacts land in:

- `dist/`
- `build/`

Those folders should be treated as outputs, not maintained source.

## Runtime artifacts

| Artifact | Path | Notes |
| --- | --- | --- |
| Config directory | `~/.filemanager/` | created on first run |
| Config file | `~/.filemanager/config.json` | theme, exclusions, performance settings, dashboard paths |
| Cache DB | `~/.filemanager/cache.db` | SQLite hash cache |
| Log file | `~/.filemanager/app.log` | rotating file log |

## Source map for contributors

| Path | What to change there |
| --- | --- |
| `filemanager/core/common.py` | shared file metadata types |
| `filemanager/core/scanner.py` | scan behavior, traversal, and exclusion honoring |
| `filemanager/core/config.py` | persistent settings |
| `filemanager/core/cache.py` | hash cache behavior |
| `filemanager/core/operations/files.py` | low-level rename/move/copy/delete/archive primitives |
| `filemanager/core/services/file_actions.py` | centralized batch file actions |
| `filemanager/modules/` | feature logic reusable across CLI and GUI |
| `filemanager/core/actions/` | Action Builder pipeline steps |
| `filemanager/ui/views/` | top-level desktop screens |
| `filemanager/ui/plugins/` | plugin views |
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
- **The working tree is not currently a git repository and has no CI.** There is no history, diffing, or automated test/lint gate. Putting the project under version control and running the (fixed) test suite in CI is the highest-leverage next step — see [`reviews/04_IMPROVEMENTS_AND_ROADMAP.md`](./reviews/04_IMPROVEMENTS_AND_ROADMAP.md), Phase 0.
- The plugin loader registers every discovered `BaseView` subclass in `filemanager/ui/plugins/`; plugin import failures are now logged (via `logger.error`) and skipped. Plugins are arbitrary code executed with full app privileges — only add plugins you trust (see `reviews/02`, S5).
- The stray empty `26.1.2` file has been removed and a root `.gitignore` added (the tree still needs to be put under version control).
- The current dependency story is split: `setup.py` is enough for the core package/CLI entrypoint; `requirements.txt` provisions the full GUI/media runtime, and `requirements-dev.txt` adds the build/test tooling.
- Settings are saved immediately through `ConfigManager.set()`, so UI changes often persist at the moment a control is saved rather than on app shutdown.

## Recommended onboarding order

1. Read [`../README.md`](../README.md)
2. Read [`./ARCHITECTURE.md`](./ARCHITECTURE.md)
3. Read [`./GUI_WORKFLOWS.md`](./GUI_WORKFLOWS.md) or [`./CLI_REFERENCE.md`](./CLI_REFERENCE.md), depending on your work area
4. Use [`../TECHNICAL_SOURCE_OF_TRUTH.md`](../TECHNICAL_SOURCE_OF_TRUTH.md) when you need file-by-file depth
5. Skim [`./reviews/00_EXECUTIVE_SUMMARY.md`](./reviews/00_EXECUTIVE_SUMMARY.md) for the current bug/security/UX backlog before picking up work
