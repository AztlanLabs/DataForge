# DataForge Development Workflow

> **Audience:** Human developers and AI assistants working on this repo.
> Feed this file as global context before any implementation task.

---

## Quick Reference Card

| Rule | Value |
| --- | --- |
| Commit format | `type(scope): description` — [Conventional Commits](https://www.conventionalcommits.org/) |
| Tabs vs spaces | Follow existing file convention — do not mix |
| Test command | `PYTHONPATH=. pytest -q` (254+ pass required) |
| Before push | Tests must pass; commit message must match convention |
| Default branch | `develop` — all feature work merges here |
| Stable branch | `main` — tagged releases only; PR from `develop` required |
| Version source | `setup.py` `version=` — single source of truth |
| Hook enforcement | `git config core.hooksPath .githooks` |
| Changelog | Keep a Changelog format in `CHANGELOG.md` |

---

## 1. Branching Model

```
main     ●────────────●────── v0.1.0-beta.1     ●────── v0.1.0
          \          /                           /
develop    ●─●─●─●─●●─●─●─●─●─●─●  (alpha tags)
```

| Branch | Purpose | Version tags allowed |
| --- | --- | --- |
| `develop` | Integration branch. All feature/fix branches merge here. | `vX.Y.Z-alpha.N` only |
| `main` | Stable channel. Only accepts merges from `develop` via PR. | `vX.Y.Z-beta.N` · `vX.Y.Z-rc.N` · `vX.Y.Z` |

### Feature branches (short-lived)

Branch off `develop`, merge back via PR or direct push (solo project):

```
git checkout -b feat/my-feature develop
# ... commits ...
git checkout develop && git merge feat/my-feature
```

---

## 2. Commit Convention

### Format

```
<type>(<scope>): <short description>

[optional body]

[optional footer with BREAKING CHANGE]
```

### Types

| Type | When to use | Version bump |
| --- | --- | --- |
| `feat` | New feature or capability | MINOR |
| `fix` | Bug fix | PATCH |
| `docs` | Documentation only | — |
| `refactor` | Code change, no bug fix or feature | — |
| `test` | Adding or updating tests | — |
| `chore` | Build, tooling, CI, repo maintenance | — |
| `style` | Formatting, whitespace, linting (no logic) | — |
| `perf` | Performance improvement | — |
| `revert` | Revert a previous commit | — |

### Scopes

| Scope | Covers |
| --- | --- |
| `core` | Scanner, config, cache, hasher, logger, operations, services |
| `cli` | Click command surface (`fm ...`) |
| `ui` | GUI shell, views, widgets, theme, plugins |
| `modules` | Feature modules (search, duplicates, forensics, hardware, etc.) |
| `actions` | Action Builder pipeline engine |
| `design` | Theme tokens, QSS, palette, type scale, visual design |
| `build` | setup.py, build_exe.py, PyInstaller specs, requirements |
| `docs` | Everything under docs/ and root README |
| `tests` | Test suite |
| `repo` | .gitignore, CI config, git hooks, repo structure |

Omit scope for cross-cutting changes: `docs: update all cross-references`

### Short description rules

- Imperative mood: `add` not `added`, `fix` not `fixes`
- No trailing period
- 72 characters max
- Backtick-quote symbols: `` `theme_tokens.py` ``

### BREAKING CHANGES

Append `!` or add `BREAKING CHANGE:` footer:

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

### Enforcement

A `commit-msg` hook in `.githooks/` validates every message:

```bash
git config core.hooksPath .githooks
```

---

## 3. Versioning

DataForge follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH[-PRE]`.

| Component | Trigger | Example |
| --- | --- | --- |
| MAJOR | `feat!` / `fix!` (breaking change) | `1.0.0` |
| MINOR | `feat` (new feature) | `0.2.0` |
| PATCH | `fix` (bug fix) | `0.1.1` |

`docs`, `style`, `refactor`, `test`, `chore`, `perf` do not bump version on their own.

**Current version:** `0.1.0` — pre-release development on `develop`. Leading `0`
means the public API is unstable — anything may change without a MAJOR bump.

### Version lifecycle

| Stage | Branch | `setup.py` version | Git tag |
| --- | --- | --- | --- |
| Development | `develop` | `0.1.0` or `0.1.0.dev` | No tag |
| Alpha checkpoint | `develop` | `0.1.0-alpha.N` | `v0.1.0-alpha.N` |
| Beta (feature freeze) | `main` | `0.1.0-beta.N` | `v0.1.0-beta.N` |
| Release candidate | `main` | `0.1.0-rc.N` | `v0.1.0-rc.N` |
| GA release | `main` | `0.1.0` | `v0.1.0` |

**Branch-version matrix:**

| What | `develop` | `main` |
| --- | --- | --- |
| Works-in-progress | `0.X.Y.dev` | N/A |
| Feature-incomplete | `v0.X.Y-alpha.N` | N/A |
| Feature-complete | N/A | `v0.X.Y-beta.N` |
| QA freeze | N/A | `v0.X.Y-rc.N` |
| Public release | N/A | `v0.X.Y` |

`setup.py version=` is the single authority. Read it programmatically:

```bash
python setup.py --version
```

### Tagging an alpha on develop

```bash
git checkout develop
PYTHONPATH=. pytest -q          # must be green
git tag v0.1.0-alpha.1
git push origin develop --tags
```

### Tagging a beta/RC/GA on main

```bash
git checkout main
git merge develop --no-ff
# bump version in setup.py
git add setup.py && git commit -m "chore(release): bump to 0.1.0-beta.1"
git tag v0.1.0-beta.1
git push origin main --tags
```

---

## 4. Release Process

### When to PR from develop → main

| # | Gate | Status (2026-07-11) |
| --- | --- | --- |
| G1 | Test suite green (254+) | ✅ |
| G2 | No HIGH-severity open bugs | ✅ |
| G3 | No HIGH-severity open security findings | ❌ — S2 (XSS in forensic report) |
| G4 | CI wired (tests run automatically) | ❌ — no CI yet |
| G5 | Docs accurate against current sources | ✅ |
| G6 | MEDIUM security (S4, S7) fixed | ❌ |
| G7 | No regression in primary workflows | ✅ |
| G8 | PR reviewed (solo project: self-review) | ✅ |

### Recommended first-PR path to v0.1.0-beta.1

1. Fix S2 (HTML-escape forensic report — 2-line fix + test)
2. Wire GitHub Actions CI (pytest on push)
3. Fix S4 (trash-restore path traversal)
4. Fix S7 (System Cleanup safe-guards)
5. Merge `develop` → `main`, tag `v0.1.0-beta.1`

### Release checklist (for any main-branch release)

- [ ] `PYTHONPATH=. pytest -q` — 254+ tests, 0 failures
- [ ] `setup.py version=` matches intended tag
- [ ] `CHANGELOG.md` entry under new version heading
- [ ] `docs/` cross-references verified (no broken links)
- [ ] `python setup.py sdist` succeeds
- [ ] `python build_exe.py release` succeeds
- [ ] Smoke: `fm dupes --help`, `fm search --help`, GUI launches
- [ ] Tag pushed with `--tags`

### After a release

```bash
git checkout develop && git merge main && git push origin develop
# bump setup.py to next pre-release, e.g. 0.1.1.dev
```

---

## 5. Implementation Plan Guidance

When creating an implementation plan — whether you are an AI assistant or a
human developer — structure the plan so each task maps cleanly to commits that
follow this document's conventions.

### Plan structure

For each implementation task in the plan, specify:

1. **What** — the change being made
2. **Files touched** — which source files are affected
3. **Commit type + scope** — the conventional commit that will carry this change
4. **Version impact** — whether this triggers a version bump (and which component)
5. **Test impact** — what test file needs updating or what new test is needed

### Example: a feature implementation plan

```
## Task: Add disk-health trend tracking to Performance view

Files touched: dataforge/modules/performance.py,
               dataforge/ui/views/performance_view.py,
               tests/test_new_modules.py

Commits:
  1. feat(modules): add SMART attribute history collector
     → bumps MINOR (0.1.0 → 0.2.0)
  2. feat(ui): add trend-chart widget to Performance view
     → no separate bump (same feature)
  3. test: add history-collector unit tests
     → no bump

Verification:
  - pytest tests/test_new_modules.py -k smart
  - manual: open Performance view, verify chart renders with live data
```

### Example: a bug-fix plan

```
## Task: Fix symlink recursion in scanner

Files touched: dataforge/core/scanner.py, tests/test_comprehensive.py

Commits:
  1. fix(core): prevent symlink recursion with follow_symlinks=False
     → bumps PATCH (0.1.0 → 0.1.1)
  2. test: add symlink-loop regression guard
     → no bump

Verification:
  - create symlink loop in /tmp, run fm scan /tmp --recursive
  - pytest tests/test_comprehensive.py -k symlink
```

### Example: a refactor plan

```
## Task: Consolidate two metadata-cleaning implementations

Files touched: dataforge/modules/cleaner.py,
               dataforge/modules/metadata.py,
               dataforge/ui/views/tools.py,
               dataforge/ui/plugins/cleaner_plugin.py,
               tests/test_comprehensive.py

Commits:
  1. refactor(modules): unify metadata cleaning into MetadataEngine
     → no version bump (refactor)
  2. refactor(ui): update Tools and CleanerPlugin to use unified engine
     → no version bump
  3. test: update metadata tests for unified API
     → no bump

Verification:
  - pytest tests/test_comprehensive.py -k metadata
  - manual: scan+clean metadata in both Tools tab and CleanerPlugin
```

### Rules for plans

1. **One commit per logical change.** If a task touches 5 files for the same
   reason, it's one commit. If it does two unrelated things, it's two commits.
2. **Commits that belong to the same feature should be sequential.** Don't
   interleave feature-A commits with feature-B commits in your plan.
3. **Test commits come after their implementation commit** unless adding tests
   first (TDD), in which case `test:` commits come first with known failures.
4. **Multi-scope changes omit scope** (e.g. `docs:` not `docs(readme):` when
   updating 6 doc files across the tree).
5. **Breaking changes must be explicit.** If your plan removes an API, changes a
   CLI flag, or alters a public contract, use `!` in the commit type and add a
   `BREAKING CHANGE:` footer.
6. **Version impact is cumulative across commits pushed together.** If you push
   3 `feat:` commits, the version bumps MINOR once, not three times.

### Plan checklist

Before executing any implementation plan, verify:

- [ ] Each commit maps to a valid `type(scope)` combination from §2
- [ ] Breaking changes are marked with `!` and have a footer
- [ ] `feat` commits correctly predict MINOR bump; `fix` commits predict PATCH
- [ ] Test verification steps are concrete (exact pytest invocation)
- [ ] No commit crosses 72 characters in the subject line
- [ ] The sequence of commits tells a coherent story in `git log --oneline`

---

## 6. Working with AI Assistants

When using an AI coding assistant (Claude, Copilot, etc.), include this file
as global context at the start of the session.

### AI prompt template

```
You are working on the DataForge repo at /path/to/DataForge.
Read docs/CONTRIBUTING.md for the full development workflow —
commit conventions, versioning rules, release process, and
implementation plan format. Follow that document's conventions
for all commits you create.

Your task: [describe the task here]
```

### What the AI should produce

When asked to implement a feature or fix, the AI should:

1. First produce an **implementation plan** following §5 format
2. Map every planned change to a conventional commit
3. State the version impact of the work
4. Execute commits that match the plan
5. Verify with `PYTHONPATH=. pytest -q` before declaring done

### What the AI should NOT do

- Create commits with messages like "update code", "fix bug", "WIP"
- Skip the test run before pushing
- Commit directly to `main` — all work targets `develop`
- Generate changelog entries manually (derive from commit log)
- Add comments to code unless the implementation plan calls for it

---

## Related Documents

- [`README.md`](../README.md) — project overview, quick start, feature index
- [`docs/ARCHITECTURE.md`](./ARCHITECTURE.md) — layered design, key abstractions
- [`docs/DEVELOPMENT_GUIDE.md`](./DEVELOPMENT_GUIDE.md) — setup, testing, packaging
- [`docs/reviews/EXECUTIVE_SUMMARY.md`](./reviews/EXECUTIVE_SUMMARY.md) — current audit status and backlog
- [`docs/reviews/AUDIT_FINDINGS.md`](./reviews/AUDIT_FINDINGS.md) — bug and security tracker
- [`docs/reviews/IMPROVEMENT_PLAN.md`](./reviews/IMPROVEMENT_PLAN.md) — UX roadmap and phased plan
