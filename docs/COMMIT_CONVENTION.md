# Commit Convention

DataForge uses [Conventional Commits](https://www.conventionalcommits.org/) for all
git commit messages. This keeps history machine-readable, enables automated
changelog generation, and makes `git log --oneline` scannable.

## Format

```
<type>(<scope>): <short description>

[optional body]
```

## Types

| Type | When to use |
| --- | --- |
| `feat` | A new feature or capability (bumps MINOR version) |
| `fix` | A bug fix (bumps PATCH version) |
| `docs` | Documentation only changes |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or updating tests |
| `chore` | Build process, tooling, CI, or repo maintenance |
| `style` | Formatting, whitespace, linting (no logic change) |
| `perf` | Performance improvement |
| `revert` | Revert a previous commit |

### BREAKING CHANGES

Append `!` after the type/scope, or add `BREAKING CHANGE:` in the footer:

```
feat(api)!: remove deprecated search endpoint

BREAKING CHANGE: The /v1/search endpoint has been removed.
Use /v2/query with the --name-glob flag instead.
```

## Scopes

| Scope | Area |
| --- | --- |
| `core` | Scanner, config, cache, hasher, logger, operations, services |
| `cli` | Click command surface (`fm ...`) |
| `ui` | GUI shell, views, widgets, theme, plugins |
| `modules` | Feature modules (search, duplicates, forensics, hardware, etc.) |
| `actions` | Action Builder pipeline engine |
| `design` | Theme tokens, QSS, palette, type scale, visual design |
| `build` | setup.py, build_exe.py, PyInstaller specs, requirements |
| `docs` | All documentation under docs/ and root README |
| `tests` | Test suite |
| `repo` | .gitignore, CI config, git hooks, repo structure |

Omit the scope if the change spans multiple areas:

```
docs: update all cross-references after review restructure
```

## Short description rules

- Imperative mood: `add` not `added`, `fix` not `fixes`
- No trailing period
- 72 characters max
- Use backtick-quoting for symbols: `` `theme_tokens.py` ``

## Examples

```
feat(design): add AA-validated design-token system
fix(core): prevent symlink recursion in scanner
docs: restructure review documentation into consolidated files
refactor(ui): migrate QSS to token-driven generation
test(design): add 30 regression guards for colour tokens
chore(repo): add commitlint git hook
perf(core): parallelize hash computation across worker threads
```

## Enforcement

A `commit-msg` Git hook in `.githooks/` validates every commit message against
this convention. Install the hooks once:

```bash
git config core.hooksPath .githooks
```
