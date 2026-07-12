# Versioning

DataForge follows [Semantic Versioning](https://semver.org/) with a
`MAJOR.MINOR.PATCH` scheme and pre-release labels. The branch determines
which labels are legal and what a version number means.

## Version number

```
MAJOR . MINOR . PATCH [-PRE]
  0   .   1   .   0   -alpha.1
```

| Component | When to bump | Commit type that triggers |
| --- | --- | --- |
| **MAJOR** | Incompatible API changes or breaking CLI/GUI contract changes | `feat!`, `fix!` etc. |
| **MINOR** | Backward-compatible new features or deprecations | `feat` |
| **PATCH** | Backward-compatible bug fixes | `fix` |

`docs`, `style`, `refactor`, `test`, `chore`, `perf` commits that don't change
the feature surface do not bump any version number on their own.

## Current version

`0.1.0` *(pre-release development on `develop` branch)*

The leading `0` means the public API is **unstable** — anything may change
without a MAJOR bump. MAJOR bumps are reserved for `1.0.0` and beyond.

## Version lifecycle by branch

### `develop` branch (pre-release)

Only **alpha** tags are legal on `develop`. These mark integration checkpoints
where `pytest` is green.

| Label | `setup.py` version | Git tag | Frequency |
| --- | --- | --- | --- |
| Development | `0.1.0.dev` (or bare `0.1.0`) | No tag | Every commit |
| Alpha checkpoint | `0.1.0-alpha.1` | `v0.1.0-alpha.1` | At coherent milestones |

Alpha tags happen on `develop` before any merge to `main`. Example sequence:

```
develop:  0.1.0.dev → 0.1.0-alpha.1 → 0.1.0-alpha.2 → (PR to main)
```

### `main` branch (stable channel)

After a PR from `develop` lands on `main`, bump to beta. Beta, RC, and final
GA tags are only created on `main`.

| Label | Meaning | Git tag | Trigger |
| --- | --- | --- | --- |
| Beta | Feature-complete; testing and hardening in progress | `v0.1.0-beta.1` | `develop` PR lands on `main`; hard gates passed |
| Release candidate | Final verification; bugfix-only | `v0.1.0-rc.1` | QA pass on beta; all MEDIUM+ security fixed |
| GA release | Production-ready | `v0.1.0` | RC signed off; 72+ hours with no regression |

Example sequence:

```
main:  v0.1.0-beta.1 → v0.1.0-beta.2 → v0.1.0-rc.1 → v0.1.0
```

## Branch-version matrix

| What | `develop` | `main` |
| --- | --- | --- |
| Works-in-progress commits | `0.1.0.dev` | N/A |
| Feature-incomplete snapshot | `v0.1.0-alpha.N` | N/A |
| Feature-complete, needs hardening | N/A | `v0.1.0-beta.N` |
| Freeze for QA | N/A | `v0.1.0-rc.N` |
| Public release | N/A | `v0.1.0` |

## Version source of truth

The single authoritative version string is `version=` in
[`setup.py`](../setup.py). All tags, `CHANGELOG.md` headings, and CI
consistency checks derive from it.

To read the current version programmatically:

```bash
python setup.py --version
# 0.1.0
```

## Changelog

Every version bump is accompanied by an entry in `CHANGELOG.md` grouped by
commit type (Added / Fixed / Changed / Deprecated / Removed / Security). The
changelog is human-readable and follows [Keep a
Changelog](https://keepachangelog.com/).

## Related documents

- [`RELEASE_PROCESS.md`](./RELEASE_PROCESS.md) — when to PR to `main`, release
  checklist, gate criteria, current readiness assessment
- [`COMMIT_CONVENTION.md`](./COMMIT_CONVENTION.md) — commit message format that
  drives version bumps
