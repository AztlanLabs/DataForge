# Contributing to DataForge

> **Audience:** Human developers and AI assistants working on this repo.

---

## Quick Reference

| Rule | Value |
| --- | --- |
| License | GPL-3.0 |
| Commit format | `type(scope): description` — [Conventional Commits](https://www.conventionalcommits.org/) |
| Test command | `PYTHONPATH=. pytest -q` |
| Before push | All tests pass; commit message matches convention |
| Default branch | `develop` — all feature work merges here |
| Stable branch | `main` — tagged releases only |
| Version source | `pyproject.toml` `[project] version` field |
| Hook setup | `git config core.hooksPath .githooks` |
| Changelog | [Keep a Changelog](https://keepachangelog.com/) format in `CHANGELOG.md` |

---

## 1. Getting Started

### Prerequisites

- Python 3.10+
- Git

### Setup

```bash
git clone https://github.com/AztlanLabs/DataForge.git
cd DataForge
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
git config core.hooksPath .githooks
pre-commit install
```

### Verify

```bash
PYTHONPATH=. pytest -q           # all tests must pass
fm --help                        # CLI works
python run_ui.py                 # GUI launches
```

### Project Layout

```
DataForge/
├── dataforge/
│   ├── cli.py                   # Click CLI (fm command)
│   ├── core/                    # Scanner, config, cache, hasher, operations, services
│   │   ├── actions/             # Action Builder pipeline engine
│   │   ├── operations/          # Low-level file mutation primitives
│   │   └── services/            # FileActionService (central batch operations)
│   ├── modules/                 # Feature logic (search, duplicates, forensics, etc.)
│   └── ui/                      # PyQt5 desktop app
│       ├── app.py               # Main window, threading, navigation
│       ├── views/               # Built-in screens (14 views)
│       ├── plugins/             # Plugin views
│       ├── widgets.py           # Shared widgets
│       └── theme_tokens.py      # Design tokens (colours, type scale, QSS)
├── tests/                       # pytest test suite
├── docs/                        # Documentation
├── .githooks/                   # Commit-msg hook
├── pyproject.toml               # Package metadata + version, tool config (ruff/black/mypy/coverage)
├── setup.py                     # Thin `setup()` shim (metadata lives in pyproject.toml)
├── requirements.txt             # Runtime dependencies
├── requirements-dev.txt         # Dev dependencies (pytest, pyinstaller)
├── build_exe.py                 # PyInstaller build script
├── run_ui.py                    # GUI entry point
└── CHANGELOG.md                 # Version history
```

---

## 2. Branching Model

```
main     ●────────────●────── v0.1.0-beta.1     ●────── v0.1.0
          \          /                           /
develop    ●─●─●─●─●●─●─●─●─●─●─●  (alpha tags)
              \         \
feature       ●─●─●     ●─●─●
```

| Branch | Purpose | Tags allowed |
| --- | --- | --- |
| `develop` | Integration branch. All feature/fix branches merge here. | `vX.Y.Z-alpha.N` |
| `main` | Stable channel. Only accepts merges from `develop`. | `vX.Y.Z-beta.N`, `vX.Y.Z-rc.N`, `vX.Y.Z` |
| Feature branches | Branch off `develop`, merge back via PR or direct push. | None |

### Workflow

```bash
git checkout -b feat/my-feature develop
# ... work ...
git checkout develop && git merge feat/my-feature
```

---

## 3. Commit Convention

All commits are validated by the `commit-msg` hook in `.githooks/`. Messages that don't match are rejected.

### Format

```
type(scope): short description

[optional body]

[optional footer]
```

### Types

| Type | Version bump | When to use |
| --- | --- | --- |
| `feat` | MINOR | New feature or capability |
| `fix` | PATCH | Bug fix |
| `docs` | — | Documentation only |
| `refactor` | — | Code change that neither fixes a bug nor adds a feature |
| `test` | — | Adding or updating tests |
| `chore` | — | Build, tooling, CI, repo maintenance |
| `style` | — | Formatting, whitespace, linting (no logic change) |
| `perf` | — | Performance improvement |
| `revert` | — | Revert a previous commit |

### Scopes

| Scope | Covers |
| --- | --- |
| `core` | Scanner, config, cache, hasher, logger, operations, services |
| `cli` | Click command surface (`fm ...`) |
| `ui` | GUI shell, views, widgets, theme, plugins |
| `modules` | Feature modules (search, duplicates, forensics, hardware, etc.) |
| `actions` | Action Builder pipeline engine |
| `design` | Theme tokens, QSS, palette, type scale, visual design |
| `build` | pyproject.toml, setup.py, build_exe.py, PyInstaller specs, requirements |
| `docs` | Everything under docs/ and root README |
| `tests` | Test suite |
| `repo` | .gitignore, CI config, git hooks, repo structure |

Omit scope for cross-cutting changes: `docs: update all cross-references`

### Rules

- Imperative mood: `add` not `added`, `fix` not `fixes`
- No trailing period
- 72 characters max (enforced by hook)
- Backtick-quote symbols: `` `theme_tokens.py` ``

### Breaking Changes

Append `!` to the type or add `BREAKING CHANGE:` footer:

```
feat(cli)!: remove deprecated --legacy flag

BREAKING CHANGE: The --legacy flag is removed. Use --format instead.
```

### Examples

```
feat(design): add AA-validated design-token system
fix(core): prevent symlink recursion in scanner
docs: restructure review documentation into consolidated files
refactor(ui): migrate QSS to token-driven generation
test(design): add 30 regression guards for colour tokens
chore(repo): add commitlint git hook
```

---

## 4. Code Style

### General

- Follow the existing style of the file you're editing
- Use 4-space indentation (Python), 2-space for YAML/JSON
- No trailing whitespace
- UTF-8 encoding everywhere
- Maximum line length: 120 characters (soft limit)

### Python

- Type hints on public functions
- Docstrings on public classes and functions (Google style)
- Use `pathlib.Path` over `os.path` for new code
- Prefer f-strings over `.format()` or `%` formatting
- Use `logging` module, never `print()` for errors

### PyQt5 / GUI

- All views inherit from `BaseView`
- Long-running work goes through `app.run_workflow()` or `app.run_background()`
- Never block the Qt main thread
- Use design tokens from `theme_tokens.py` — no hardcoded hex colours
- Follow the preview → confirm → execute pattern for destructive operations

### File Mutations

- All file mutations go through `FileActionService` or `dataforge/core/operations/files.py`
- Never call `shutil.move`, `shutil.copy2`, or `os.remove` directly from views or modules
- Always support `dry_run` parameter

---

## 5. Testing

### Running Tests

```bash
PYTHONPATH=. pytest -q                    # all tests
PYTHONPATH=. pytest tests/test_comprehensive.py -v   # one file, verbose
PYTHONPATH=. pytest -k "symlink" -v       # filter by keyword
```

### Test Structure

| File | Focus |
| --- | --- |
| `tests/test_comprehensive.py` | Core modules, services, operations, actions |
| `tests/test_integration.py` | End-to-end workflows, plugin packaging |
| `tests/test_contract_regressions.py` | CLI and GUI contract stability |
| `tests/test_new_modules.py` | Newer modules (hardware, forensics, recovery, metadata) |
| `tests/test_theme_tokens.py` | Design token regression guards |
| `tests/verify_scenarios.py` | Scenario-style validation (standalone script) |

### Writing Tests

- Test files: `tests/test_*.py`
- Test classes: `Test<Feature>` (e.g., `TestSearchQuery`)
- Test functions: `test_<behavior>` (e.g., `test_search_by_extension`)
- Use `tmp_path` fixture for temporary files
- Use `monkeypatch` for mocking, not `unittest.mock` where possible
- Every bug fix must include a regression test
- Every new feature must include tests for its public API

### What to Test

- Public API of every module
- Edge cases: empty input, missing files, permission errors, symlinks
- Cancellation: pass a `threading.Event` as `cancel_token`, set it, verify early exit
- Dry-run: verify no filesystem changes when `dry_run=True`
- Error paths: invalid input, missing files, corrupt data

---

## 6. Versioning

DataForge follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH[-PRE]`.

| Component | Trigger | Example |
| --- | --- | --- |
| MAJOR | Breaking change (`feat!` / `fix!`) | `1.0.0` |
| MINOR | New feature (`feat`) | `0.2.0` |
| PATCH | Bug fix (`fix`) | `0.1.1` |

`docs`, `style`, `refactor`, `test`, `chore`, `perf` do not bump version.

**Current version:** `0.1.0` (pre-release). Leading `0` means the public API is unstable.

### Version Lifecycle

| Stage | Branch | `pyproject.toml` version | Git tag |
| --- | --- | --- | --- |
| Development | `develop` | `0.1.0` or `0.1.0.dev` | — |
| Alpha | `develop` | `0.1.0-alpha.N` | `v0.1.0-alpha.N` |
| Beta | `main` | `0.1.0-beta.N` | `v0.1.0-beta.N` |
| RC | `main` | `0.1.0-rc.N` | `v0.1.0-rc.N` |
| GA | `main` | `0.1.0` | `v0.1.0` |

### Read Version

```bash
python setup.py --version
```

### Tag a Release

```bash
# Alpha on develop
git checkout develop
PYTHONPATH=. pytest -q
git tag v0.1.0-alpha.1
git push origin develop --tags

# Beta/RC/GA on main
git checkout main
git merge develop --no-ff
# bump version in pyproject.toml
git add pyproject.toml && git commit -m "chore(release): bump to 0.1.0-beta.1"
git tag v0.1.0-beta.1
git push origin main --tags
```

---

## 7. Release Process

### Before Merging `develop` → `main`

- [ ] `PYTHONPATH=. pytest -q` — all tests pass
- [ ] `pyproject.toml` `[project] version` matches intended tag
- [ ] `CHANGELOG.md` updated (move [Unreleased] entries under new version heading)
- [ ] `docs/` cross-references verified (no broken links)
- [ ] `python setup.py sdist` succeeds
- [ ] `python build_exe.py release` succeeds
- [ ] Smoke test: `fm dupes --help`, `fm search --help`, GUI launches
- [ ] No HIGH-severity open security findings

### After a Release

```bash
git checkout develop && git merge main && git push origin develop
# bump pyproject.toml to next pre-release, e.g. 0.1.1.dev
```

---

## 8. Documentation

Every code change must update the docs that reference it. Code and docs stay in lockstep.

### Where / Why / How — the standard for every documented issue

Any finding, task, or work-item in the docs (reviews, plans, source-of-truth) must
answer three questions. A row that skips one is not done:

| Question | Means | Example |
| --- | --- | --- |
| **Where** | Exact location — `path:line`, component, or doc section | `dataforge/modules/forensics.py:581-625` |
| **Why** | The impact if left unfixed — the risk, defect, or user cost | Stored XSS in examiner context; disqualifying for court use |
| **How** | The concrete fix, the seam it lands at, and the test that proves it | `html.escape()` every interpolated value + `<script>`-filename regression test |

Never justify work with "the review says so." State the impact. This standard
applies to `docs/reviews/`, `docs/TECHNICAL_SOURCE_OF_TRUTH.md`, and any new plan.
Before citing a finding as still open, **verify it against the current code** and
record the evidence — do not assume an older review is still accurate.

### When You Change Code

| Changed | Update |
| --- | --- |
| `dataforge/cli.py` | `docs/CLI_REFERENCE.md`, `README.md` |
| `dataforge/core/` | `docs/ARCHITECTURE.md`, `docs/TECHNICAL_SOURCE_OF_TRUTH.md` |
| `dataforge/modules/` | `docs/ARCHITECTURE.md`, `docs/TECHNICAL_SOURCE_OF_TRUTH.md`, `docs/CLI_REFERENCE.md` |
| `dataforge/ui/app.py` | `docs/ARCHITECTURE.md`, `docs/GUI_WORKFLOWS.md`, `docs/TECHNICAL_SOURCE_OF_TRUTH.md` |
| `dataforge/ui/views/` | `docs/GUI_WORKFLOWS.md`, `docs/TECHNICAL_SOURCE_OF_TRUTH.md` |
| `dataforge/ui/widgets.py` | `docs/GUI_WORKFLOWS.md`, `docs/TECHNICAL_SOURCE_OF_TRUTH.md` |
| `dataforge/ui/plugins/` | `docs/ARCHITECTURE.md`, `docs/GUI_WORKFLOWS.md` |
| `dataforge/ui/theme_tokens.py` | `docs/ARCHITECTURE.md` |
| `dataforge/core/actions/` | `docs/ARCHITECTURE.md`, `docs/TECHNICAL_SOURCE_OF_TRUTH.md`, `docs/GUI_WORKFLOWS.md` |
| `tests/` | `docs/DEVELOPMENT_GUIDE.md`, `README.md` (test count) |
| `pyproject.toml`, `setup.py`, `build_exe.py`, `requirements*.txt` | `docs/DEVELOPMENT_GUIDE.md`, `README.md` |
| Any user-facing change | `CHANGELOG.md` |

### When You Change Docs

| Changed | Update |
| --- | --- |
| Add/rename/delete `docs/` file | `README.md`, `docs/DEVELOPMENT_GUIDE.md`, all files linking to it |
| `README.md` | Verify claims match `docs/CLI_REFERENCE.md`, `docs/DEVELOPMENT_GUIDE.md`, `pyproject.toml` |
| `docs/CONTRIBUTING.md` | `.githooks/commit-msg` (if format rules change) |
| Test count changes | `README.md`, `docs/DEVELOPMENT_GUIDE.md`, this file (Quick Reference) |

### Verify Before Push

```bash
# Search for old names across all docs
grep -rn "old-name" docs/ README.md

# Verify relative links resolve
ls docs/path/to/linked-file.md
```

---

## 9. Security

### Reporting

If you find a security vulnerability, **do not open a public issue**. Email the maintainers or file a private security advisory on GitHub.

### Current Status

Security findings are tracked in [`docs/reviews/AUDIT_FINDINGS.md`](./reviews/AUDIT_FINDINGS.md).
The point-security backlog **S1–S13 is complete** — all closed across WS-A/WS-B
(trash-restore confinement, plugin-loader hardening, cleanup safeguards, `0600`
report/credential permissions, `defusedxml`, config validation, executable-open
confirm, decompression-bomb caps).

The open work is now **forensic-soundness architecture**, tracked as F1–F4 in
[`docs/reviews/FORENSIC_SECURITY_REVIEW.md`](./reviews/FORENSIC_SECURITY_REVIEW.md):

- **F1** — no chain-of-custody / tamper-evident audit log
- **F2** — no acquisition provenance (operator, host, source-image hash) in reports
- **F3** — no read-only "Evidence Mode"; destructive ops one click from evidence
- **F4** — `secure_delete` placement and hardlink/reflink-awareness (with F21)

These are the gating items for any forensic-product claim and are sequenced in
[`docs/reviews/IMPLEMENTATION_PLAN.md`](./reviews/IMPLEMENTATION_PLAN.md) as WS-H → WS-J.

### Guidelines

- Never log secrets, passwords, or API keys
- Use `html.escape()` on all user-controlled data in HTML output
- Validate and sanitize file paths before use in `shutil.move`, `os.makedirs`, etc.
- Prefer `send2trash` over `os.remove` for user-facing delete operations
- Write sensitive files with `0o600` permissions
- Use `defusedxml` for XML parsing (adopted in `forensics.py`; S9 closed)

---

## 10. Implementation Plans

For non-trivial changes, write a plan before coding. Structure each task as:

1. **What** — the change
2. **Files touched** — affected source files
3. **Commit** — `type(scope): description`
4. **Version impact** — MINOR / PATCH / none
5. **Test** — which test file to update or create

### Example

```
Task: Fix symlink recursion in scanner

Files: dataforge/core/scanner.py, tests/test_comprehensive.py

Commits:
  1. fix(core): prevent symlink recursion with follow_symlinks=False
     → PATCH (0.1.0 → 0.1.1)
  2. test: add symlink-loop regression guard
     → no bump

Verify:
  - pytest tests/test_comprehensive.py -k symlink
  - create symlink loop in /tmp, run fm scan /tmp --recursive
```

### Rules

- **Commit as soon as a logical task is complete** — do not batch several tasks
  into one commit, and never leave finished work uncommitted. A completed task is
  the commit boundary.
- **Close a work-stream by tagging** — when a plan's work-stream is finished and
  `PYTHONPATH=. pytest -q` is green, cut its `vX.Y.Z-alpha.N` tag on `develop`
  before starting the next stream (see `docs/reviews/IMPLEMENTATION_PLAN.md` §2.2).
- One commit per logical change
- Sequential commits for the same feature (don't interleave)
- Test commits after implementation (unless TDD)
- Multi-scope changes omit scope: `docs:` not `docs(readme):`
- Breaking changes: use `!` and add `BREAKING CHANGE:` footer
- Version impact is cumulative (3 `feat:` commits = one MINOR bump)

---

## 11. AI Assistants

When using an AI coding assistant, include this file as context:

```
You are working on the DataForge repo.
Read docs/CONTRIBUTING.md for the development workflow.
Follow that document's conventions for all commits.

Your task: [describe the task]
```

### AI Workflow

1. Produce an implementation plan (§10)
2. Map every change to a conventional commit
3. State the version impact
4. Identify docs to update (§8)
5. Execute commits matching the plan
6. Verify with `PYTHONPATH=. pytest -q`

### AI Must Not

- Create commits with messages like "update code", "fix bug", "WIP"
- Skip the test run before pushing
- Commit directly to `main`
- Add comments unless the plan calls for it
- Modify code without updating the docs that reference it

---

## 12. Related Documents

| Document | Purpose |
| --- | --- |
| [`README.md`](../README.md) | Project overview, quick start, feature index |
| [`CHANGELOG.md`](../CHANGELOG.md) | Version history and release notes |
| [`docs/ARCHITECTURE.md`](./ARCHITECTURE.md) | Layered design, key abstractions |
| [`docs/DEVELOPMENT_GUIDE.md`](./DEVELOPMENT_GUIDE.md) | Setup, testing, packaging |
| [`docs/CLI_REFERENCE.md`](./CLI_REFERENCE.md) | Complete CLI command reference |
| [`docs/GUI_WORKFLOWS.md`](./GUI_WORKFLOWS.md) | Desktop app workflows |
| [`docs/TECHNICAL_SOURCE_OF_TRUTH.md`](./TECHNICAL_SOURCE_OF_TRUTH.md) | File-by-file source map |
| [`docs/reviews/EXECUTIVE_SUMMARY.md`](./reviews/EXECUTIVE_SUMMARY.md) | Audit status and backlog |
| [`docs/reviews/AUDIT_FINDINGS.md`](./reviews/AUDIT_FINDINGS.md) | Bug and security tracker |
| [`docs/reviews/IMPROVEMENT_PLAN.md`](./reviews/IMPROVEMENT_PLAN.md) | UX roadmap and phased plan |
| [`docs/reviews/IMPLEMENTATION_PLAN.md`](./reviews/IMPLEMENTATION_PLAN.md) | Sequenced execution plan and `v0.2.0` release roadmap |
| [`docs/reviews/FORENSIC_SECURITY_REVIEW.md`](./reviews/FORENSIC_SECURITY_REVIEW.md) | Forensic-soundness, security, and investigator-UX architectural review (F1–F21, U1–U11) |
