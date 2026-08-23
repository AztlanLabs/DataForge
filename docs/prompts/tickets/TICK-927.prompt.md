# TICK-927 — Dependencies: optional imports, acquire cleanup, VSS, package extras

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-927 |
| Wave | 13 — Platform, API, CLI, Packaging (P1) |
| Priority | P1 — Install broken |
| Depends on | Wave 12 |
| Files to modify | `dataforge/core/acquire.py`, `pyproject.toml`, `requirements.txt` |
| Files to create | `tests/test_dependency_contract.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P1.13, P1.20 |
| Validation | `python -m pytest tests/test_dependency_contract.py -q` |

## Context

**P1.13 — CLI import fails without Pillow:** `cli.py:8-12` imports `modules.cleaner` at startup. `cleaner.py:1-6` imports Pillow unconditionally. `pip install .` without `requirements.txt` fails even for `fm --help`.

**P1.13 — Missing pyproject deps:** `pyproject.toml:9-24` omits Pillow, PyQt5, pypdf, PyMuPDF, pandas, msgpack, platformdirs. These are in `requirements.txt` but not declared as extras.

**P1.20 — Acquire temp leak:** `acquire_file()` at `acquire.py:233-249,294-307` has cleanup closures that capture `tmp_path`, then the outer function sets `tmp_path` to `None`. When the returned file closes, `os.unlink(None)` fails silently and the temp copy remains.

**P1.20 — VSS returns None:** The Windows VSS branch at `acquire.py:159-182` only lists shadow copies and returns `None`. It does not acquire a usable file.

## Objectives

1. Make CLI importable without GUI/media dependencies.
2. Define pyproject extras for optional dependency groups.
3. Fix acquire temp cleanup.
4. Mark VSS as explicitly unsupported.
5. Add msgpack and platformdirs to pyproject.

## Implementation Guide

### Step 1: Lazy imports

Note: This step edits `dataforge/cli.py` and `dataforge/modules/cleaner.py`. Those files are NOT listed in this ticket's exclusive_write_files. Either expand the file list or defer these lazy-import changes to a follow-up. Coordinate with the backlog owner.

In `cli.py`, move cleaner import inside the command function:

```python
# Before (top level):
from dataforge.modules.cleaner import MetadataCleaner

# Inside the command:
def clean_cmd(...):
    from dataforge.modules.cleaner import MetadataCleaner
    ...
```

In `cleaner.py`, move Pillow import inside functions:

```python
def remove_metadata(path, ...):
    from PIL import Image  # Lazy import
    ...
```

### Step 2: Define extras in pyproject.toml

```toml
[project.optional-dependencies]
gui = ["PyQt5>=5.15.0"]
media = ["Pillow>=10.0.0", "pypdf>=6.14.2", "pymupdf>=1.28.0", "opencv-python-headless>=5.0.0.93", "pandas>=2.2.3"]
forensics = ["psutil>=5.9.0", "python-magic>=0.4.27", "PyExifTool>=0.5.0", "mutagen>=1.47.0"]
dev = ["pytest", "pytest-cov", "pytest-asyncio", "ruff", "mypy", "pre-commit", "pip-audit", "pyinstaller"]
# Note: msgpack and platformdirs are needed by core (transport/paths) — add to main dependencies, not just extras
# all is NOT a self-reference like ["dataforge[cli,gui,media,forensics]"] — enumerate explicitly if needed
```

### Step 3: Fix acquire temp cleanup

```python
# Fix: capture tmp_path by value (default arg), not by reference
def acquire_file(path, ...):
    tmp_path = None
    try:
        if needs_sudo:
            tmp_path = _copy_with_sudo(path)
            actual_path = tmp_path
        else:
            actual_path = path

        f = open(actual_path, "rb")
        orig_close = f.close

        # Capture by value via default arg — otherwise outer tmp_path=None nulls the closure
        def _close_and_cleanup(_tmp=tmp_path, _orig=orig_close):
            try:
                _orig()
            finally:
                if _tmp and os.path.exists(_tmp):
                    try:
                        os.unlink(_tmp)
                    except OSError:
                        pass

        f.close = _close_and_cleanup
        return f
    except:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise
```

### Step 4: Mark VSS unsupported

The live function is `_try_windows_acquire` (not `_acquire_vss`). It currently returns `None` on all paths. Make the contract explicit:

```python
def _try_windows_acquire(path):
    """Windows VSS/acquire is not yet implemented."""
    # Return None so caller falls back to direct open, but log clearly
    import logging
    logging.getLogger(__name__).debug("VSS not supported on this platform: %s", path)
    return None
```

Note: The audit says "mark as unsupported instead of returning None" — but returning None IS the fallback. The fix is to ensure callers distinguish "unsupported" from "file not found" via logging or a dedicated return value. Do not raise — caller at acquire.py:392 expects None fallback.

## Unit Tests

Create `tests/test_dependency_contract.py`:

| Test function | What it asserts |
|---|---|
| `test_cli_importable_without_pillow` | Mock Pillow unavailable. Import cli. Assert no ImportError. |
| `test_cleaner_importable_without_pillow` | Mock Pillow unavailable. Import cleaner. Assert no ImportError. |
| `test_pyproject_has_extras` | Parse pyproject.toml. Assert `gui`, `media`, `forensics`, `dev` extras exist. |
| `test_pyproject_has_msgpack` | Assert msgpack in dependencies or extras. |
| `test_pyproject_has_platformdirs` | Assert platformdirs in dependencies or extras. |
| `test_acquire_temp_cleaned_on_close` | Acquire sudo-backed file. Close handle. Assert temp file removed. |
| `test_acquire_temp_cleaned_on_exception` | Force acquire to fail. Assert temp file removed. |
| `test_vss_returns_none` | Call VSS acquire. Assert returns None (not raises). |

## Edge Cases

- Import with all optional deps missing (CLI still works).
- Acquire file that doesn't exist (error before temp creation).
- Acquire on platform without sudo (direct open).
- pyproject.toml parse error (clear message).

## Validation Checklist

- [ ] `python -m pytest tests/test_dependency_contract.py -q` passes
- [ ] `ruff check dataforge/core/acquire.py` passes
- [ ] `fm --help` works without Pillow installed
- [ ] pyproject.toml has extras sections
- [ ] Acquire temp files cleaned up
- [ ] VSS returns None (not raises)

## Definition of Done

All 8 unit tests pass. CLI works without Pillow. Extras defined. Acquire cleanup works. VSS is honest.

## File References

### Files to modify
- `dataforge/core/acquire.py`
- `pyproject.toml`
- `requirements.txt`
### Test files to create/modify
- `tests/test_*.py` (see Unit Tests section above)

### Audit documentation
- `docs/reviews/STABILITY_AUDIT_2026-08-23.md` — source of all findings
- `docs/PARALLEL_BACKLOG.md` — ticket definitions and wave DAG
- `docs/prompts/tickets/README.md` — ticket index

### Related tickets
- Depends on: Wave 12 (TICK-919-926)
- Blocks: see wave DAG in `docs/PARALLEL_BACKLOG.md`

### Test file
- `tests/test_dependency_contract.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b feat/TICK-927-dependencies-optional-imports-extras
```

### Step 3: Implement changes
Edit the files listed above. Run tests frequently:
```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_*.py -q
ruff check <modified files>
```

### Step 4: Verify changes
```bash
git status
git diff
git diff --stat
```
Confirm all intended files are tracked. No untracked changes to unrelated files.

### Step 5: Commit
```bash
git add <modified files>
git commit -m "feat(<scope>): <description> (TICK-927)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-927.

### Step 6: Push to remote
```bash
git push origin feat/TICK-927-dependencies-optional-imports-extras
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff feat/TICK-927-dependencies-optional-imports-extras -m "Merge feat/TICK-927 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d feat/TICK-927-dependencies-optional-imports-extras
git push origin --delete feat/TICK-927-dependencies-optional-imports-extras
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-927 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-927.prompt.md`) after merge.
