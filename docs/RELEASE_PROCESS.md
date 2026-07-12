# Release Process

How DataForge moves from development on `develop` to tagged releases on
`main`. This is a lightweight git-flow variant — two long-lived branches and
tagged releases. No release branches unless the final QA warrants one.

## Branching model

```
main     ●────────────●────── v0.1.0-beta.1     ●────── v0.1.0
          \          /                           /
develop    ●─●─●─●─●●─●─●─●─●─●─●  (alpha tags)
```

| Branch | Purpose | Version tag scheme |
| --- | --- | --- |
| `develop` | Integration branch. All feature/refactor branches merge here. | `v0.1.0-alpha.N` (pre-release snapshots only) |
| `main` | Stable channel. Only accepts merges from `develop` via PR. | `v0.1.0-beta.N` · `v0.1.0-rc.N` · `v0.1.0` (final) |

## Release cadence

### On `develop` — alpha snapshots

Tag an alpha whenever `develop` reaches a coherent checkpoint and all
tests pass:

```bash
git checkout develop
PYTHONPATH=. pytest -q          # must be green (254+ tests)
git tag v0.1.0-alpha.1
git push origin develop --tags
```

Commits on `develop` update `setup.py` `version=` as follows:

| Pre-release stage | `setup.py` version | Git tag | Branch |
| --- | --- | --- | --- |
| Pre-alpha dev | `0.1.0.dev` (or just `0.1.0`) | No tag | `develop` |
| Alpha checkpoint | `0.1.0-alpha.1` | `v0.1.0-alpha.1` | `develop` |
| Beta on main | `0.1.0-beta.1` | `v0.1.0-beta.1` | `main` |
| Release candidate | `0.1.0-rc.1` | `v0.1.0-rc.1` | `main` |
| General availability | `0.1.0` | `v0.1.0` | `main` |

### On `main` — betas, RCs, GA

After a PR from `develop` → `main` lands, bump the pre-release label on
`main`, tag, and push:

```bash
git checkout main
git merge develop --no-ff
# Bump version in setup.py: 0.1.0-alpha.N → 0.1.0-beta.1
git add setup.py && git commit -m "chore(release): bump to 0.1.0-beta.1"
git tag v0.1.0-beta.1
git push origin main --tags
```

## When to create a PR from develop → main

A PR to `main` is appropriate when `develop` meets these gate criteria:

### Hard gates (blocker)

| # | Gate | Status (2026-07-11) |
| --- | --- | --- |
| G1 | Test suite green (254+) | ✅ |
| G2 | No known HIGH-severity open bugs | ✅ (all 15 correctness bugs fixed) |
| G3 | No known HIGH-severity open security findings | ❌ — S2 (XSS in forensic HTML report) open |
| G4 | CI wired — tests run automatically on push | ❌ — no CI yet |
| G5 | `README.md`, architecture docs, CLI ref accurate against current sources | ✅ |

### Soft gates (recommended)

| # | Gate | Status |
| --- | --- | --- |
| G6 | MEDIUM security findings (S4, S7) fixed | ❌ — trash-restore traversal, cleanup over-classification |
| G7 | No known regression in primary workflows (dupes, search, clean) | ✅ |
| G8 | PR reviewed by at least one other contributor | ❌ (solo project currently) |

### First PR recommendation

The **first** PR from `develop` → `main` should deliver `v0.1.0-beta.1` after
these minimum tasks:

1. **Fix S2** (HTML-escape forensic report — 2-line fix, test)
2. **Wire CI** (GitHub Actions: pytest, lint if available)
3. **Fix S4** (trash-restore path traversal)
4. **Fix S7** (System Cleanup safe-guards)

After those, merge `develop` → `main`, tag `v0.1.0-beta.1`, and continue
iteration. Between beta and final `v0.1.0`, fix the remaining MEDIUM items
(S5, S6, S8) and the LOW hardening items (S9–S13).

## Release checklist

Before tagging any release on `main`:

- [ ] `PYTHONPATH=. pytest -q` — 254+ tests, 0 failures
- [ ] `setup.py version=` matches the intended tag
- [ ] `CHANGELOG.md` entry written under the new version heading
- [ ] `docs/` cross-references verified (no broken links to deleted files)
- [ ] `python setup.py sdist` produces a valid source distribution
- [ ] `python build_exe.py release` produces a working desktop bundle
- [ ] Smoke-test: `fm dupes --help`, `fm search --help`, GUI launches
- [ ] Tag created and pushed with `--tags`

## After a release

1. Merge `main` back into `develop` so `develop` stays in sync:
   ```bash
   git checkout develop
   git merge main
   git push origin develop
   ```
2. Bump `setup.py` to the next pre-release version:
   ```bash
   # After v0.1.0 → set to 0.1.1.dev
   # After v0.1.0-beta.1 → set to 0.1.0-beta.2.dev
   ```
3. Update `CHANGELOG.md` with an `[Unreleased]` section for the new version.

## Changelog

`CHANGELOG.md` lives at the repository root and follows [Keep a
Changelog](https://keepachangelog.com/) conventions. Each entry is grouped
under Added / Fixed / Changed / Deprecated / Removed / Security.

Generate from the commit log between tags:

```bash
git log v0.1.0-alpha.1..v0.1.0-beta.1 --oneline --no-merges
```

## Version source of truth

The single authoritative version string is `version=` in
[`setup.py`](../setup.py). All tags and `CHANGELOG.md` headings derive from
it. A CI check verifies that the tag, `setup.py`, and `CHANGELOG.md` top
heading all agree.
