# Versioning

DataForge follows [Semantic Versioning](https://semver.org/) (SemVer) with a
`MAJOR.MINOR.PATCH` scheme and additional pre-release labels during development.

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

`0.1.0` — pre-release development. The leading `0` means the public API is
**unstable** and anything may change without a MAJOR bump. MAJOR bumps are
reserved for `1.0.0` and beyond.

## Pre-release tags

While the project is in `0.x`:

| Tag | Meaning |
| --- | --- |
| `-alpha.N` | Internal development; features incomplete |
| `-beta.N` | Feature-complete; testing and hardening in progress |
| `-rc.N` | Release candidate; final verification before a numbered release |

These are set in `setup.py` (`version=`) and in any Git tag:

```bash
git tag v0.1.0-alpha.1
```

## When to release

- **Alpha** — any push to `develop` that passes CI
- **Beta** — feature freeze; merge `develop` → `main`
- **Release candidate** — final QA pass on `main`
- **GA release** — tagged on `main` after RC is signed off

## Changelog

Every version bump is accompanied by an entry in `CHANGELOG.md` grouped by
commit type (Added / Fixed / Changed / Deprecated / Removed / Security). The
changelog is human-readable and generated from conventional commit history.
