# TICK-930 — Packaging: fix platform maps, spec files, asset references, build verification

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-930 |
| Wave | 13 — Platform, API, CLI, Packaging (P1) |
| Priority | P1 — Build broken |
| Depends on | Wave 12 |
| Files to modify | `build_exe.py`, `buildspec/release/DataForge.spec`, `buildspec/debug/DataForge-debug.spec`, `packaging/wix/Product.wxs`, `packaging/nfpm.yaml` |
| Files to create | `tests/test_packaging_build.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P1.19 |
| Validation | `python -m pytest tests/test_packaging_build.py -q` |

## Context

**P1.19 — macOS platform mismatch:** `detect_platform()` at `build_exe.py:25-46` returns `"macos"`. Hidden-import/exclude dicts at `build_exe.py:65-72,119-125` use `"darwin"`. macOS builds get no platform-specific imports.

**P1.19 — Hardcoded paths:** Release spec at `buildspec/release/DataForge.spec:4-10` contains `/mnt/pharos/...` paths that don't exist on CI.

**P1.19 — Stale debug spec:** Debug spec at `buildspec/debug/DataForge-debug.spec:4-15` references old Tkinter/ttkbootstrap stack.

**P1.19 — WiX wrong executable:** `packaging/wix/Product.wxs:23-29,62-68` expects executable the build script doesn't create.

**P1.19 — Missing asset:** `packaging/nfpm.yaml:37-42` references PNG asset. Only SVG exists.

## Objectives

1. Fix macOS platform mapping.
2. Remove hardcoded paths from specs.
3. Update debug spec to PyQt5.
4. Fix WiX executable reference.
5. Fix nfpm asset reference.
6. Add build smoke test.

## Implementation Guide

### Step 1: Fix platform mapping

```python
PLATFORM_MAP = {
    "linux": "linux",
    "darwin": "macos",  # detect_platform returns "macos"
    "win32": "windows",
}

def get_platform_excludes(platform):
    key = PLATFORM_MAP.get(platform, platform)
    return _PLATFORM_EXCLUDES.get(key, [])
```

Or change `detect_platform()` to return `"darwin"` on macOS.

### Step 2: Remove hardcoded paths

Replace `/mnt/pharos/...` with relative paths or environment variables in spec files.

### Step 3: Update debug spec

Replace Tkinter/ttkbootstrap imports with PyQt5 imports.

### Step 4: Fix WiX reference

Update `Product.wxs` to reference the correct executable name from `build_exe.py`.

### Step 5: Fix nfpm asset

Change PNG reference to SVG, or add the missing PNG.

### Step 6: Build smoke test

```python
def test_build_references_exist():
    """Verify all files referenced by packaging configs exist."""
    # Check nfpm assets
    # Check WiX source files
    # Check spec file paths
```

## Unit Tests

Create `tests/test_packaging_build.py`:

| Test function | What it asserts |
|---|---|
| `test_macos_platform_maps_correctly` | Call `detect_platform()` on macOS. Assert platform-specific imports resolve. |
| `test_release_spec_no_hardcoded_paths` | Read release spec. Assert no `/mnt/` paths. |
| `test_debug_spec_references_pyqt5` | Read debug spec. Assert PyQt5 imports (not Tkinter). |
| `test_wix_executable_matches_build` | Read WiX. Assert executable name matches `build_exe.py` output. |
| `test_nfpm_asset_exists` | Read nfpm.yaml. Assert referenced assets exist on disk. |
| `test_build_exe_has_onedir_profile` | Assert onedir profile exists and returns valid args. |
| `test_platform_excludes_are_valid` | For each platform, assert excluded modules are real module names. |

## Edge Cases

- Build on unknown platform (fallback to defaults).
- Spec file with Windows paths on Linux (should handle).
- Missing PyInstaller (clear error).

## Validation Checklist

- [ ] `python -m pytest tests/test_packaging_build.py -q` passes
- [ ] `ruff check build_exe.py` passes
- [ ] No `/mnt/` in spec files
- [ ] macOS platform maps correctly
- [ ] WiX references correct executable
- [ ] nfpm assets exist

## Definition of Done

All 7 unit tests pass. Platform maps work. Specs are clean. Assets exist. Build references are valid.

## File References

### Files to modify
- `build_exe.py`
- `buildspec/release/DataForge.spec`
- `buildspec/debug/DataForge-debug.spec`
- `packaging/wix/Product.wxs`
- `packaging/nfpm.yaml`
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
- `tests/test_packaging_build.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-930-packaging-platform-maps-specs
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
git commit -m "fix(<scope>): <description> (TICK-930)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-930.

### Step 6: Push to remote
```bash
git push origin fix/TICK-930-packaging-platform-maps-specs
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff fix/TICK-930-packaging-platform-maps-specs -m "Merge fix/TICK-930 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-930-packaging-platform-maps-specs
git push origin --delete fix/TICK-930-packaging-platform-maps-specs
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-930 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-930.prompt.md`) after merge.
