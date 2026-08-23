# TICK-918 — Forensics: file-type profiling, progress sentinel, timeline atime, integrity contract

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-918 |
| Wave | 11 — Critical Stability (P0) |
| Priority | P0 — Crash + correctness |
| Depends on | TICK-915 |
| Files to modify | `dataforge/modules/forensics.py`, `dataforge/api/schema.py` |
| Files to create | `tests/test_forensics_contract.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P0.8, P0.9, P1.10 |
| Validation | `python -m pytest tests/test_forensics_contract.py -q` |

## Context

**P0.8 — Profiling crash:** `profile_directory_types()` at `forensics.py:916-917` calls `progress_callback(total, total, f"Classifying: {entry.name}")`. `FileEntry` at `common.py:63-72` exposes `filename`, not `name`. This raises `AttributeError` once the 25th file is reached (the callback fires every 25 files).

**P0.9 — Progress sentinel:** `JobEvent.total` at `schema.py:194` requires `ge=0`. The daemon at `daemon.py:376` emits `progress_callback(len(entries), -1, ...)`. `JobQueue._progress()` at `jobs.py:184-200` constructs the event without converting. Pydantic raises `ValidationError`.

**P1.10 — Timeline atime:** The UI offers mtime/atime/ctime selection (`forensics_view.py:1171-1178`). The module at `forensics.py:1019-1035` assigns `modified_at` for all three. `FileEntry` has no `atime` field.

**P1.10 — Integrity snapshot:** The UI at `forensics_view.py:1733-1801` passes directories directly to `snapshot_file_state()`. The function at `forensics.py:1192-1223` hashes the directory path itself instead of recursing.

**P1.10 — Verify only first hash:** `verify_file_state()` at `forensics.py:1236-1262` checks only the first configured hash algorithm, not all recorded hashes.

**P1.10 — Artifact path escape:** Artifact parser at `forensics.py:199-209` resolves absolute home paths from a mounted `/etc/passwd` against the host filesystem, not the evidence root.

## Objectives

1. Fix profiling to use `entry.filename`.
2. Fix progress sentinel to accept unknown totals.
3. Add `atime` to `FileEntry` and use it in timeline.
4. Fix integrity snapshot to recurse directories.
5. Fix verify to check all configured hashes.
6. Constrain artifact paths to evidence root.

## Implementation Guide

### Step 1: Fix profiling

At `forensics.py:917`, change `entry.name` to `entry.filename`.

### Step 2: Fix progress sentinel

In `schema.py`, change `total` field:

```python
total: Optional[int] = Field(default=None, ge=0)
```

This already allows `None`. The fix is in the daemon: convert `-1` to `None`:

```python
# daemon.py:376
progress_callback(len(entries), None, f"Scanned {len(entries)} files")
```

And in `jobs.py:_progress()`:

```python
safe_total = total if total is not None and total >= 0 else None
```

### Step 3: Add atime to FileEntry

In `common.py`, add `atime: float = 0.0` to `FileEntry`. In `scanner.py`, populate it from `stat_result.st_atime`. In `forensics.py:1019-1035`, use `entry.atime` for atime column.

### Step 4: Fix integrity snapshot

In `forensics.py:snapshot_file_state()`, if path is a directory, enumerate files first:

```python
if os.path.isdir(path):
    files = [os.path.join(path, f) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
else:
    files = [path]
```

### Step 5: Fix verify to check all hashes

In `verify_file_state()`, iterate all recorded hash algorithms:

```python
for algo, expected_hash in snapshot.get("hashes", {}).items():
    actual_hash = get_file_hash(path, algo)
    if actual_hash != expected_hash:
        return {"verified": False, "algorithm": algo, "expected": expected_hash, "actual": actual_hash}
```

### Step 6: Constrain artifact paths

In artifact parsing, resolve paths under the evidence root:

```python
evidence_root = os.path.abspath(root)
for history_path in parsed_paths:
    full_path = os.path.join(evidence_root, history_path.lstrip("/"))
    if not full_path.startswith(evidence_root):
        continue  # Skip paths that escape evidence root
```

## Unit Tests

Create `tests/test_forensics_contract.py`:

| Test function | What it asserts |
|---|---|
| `test_profile_directory_types_25_files` | Create 25 temp files. Call `profile_directory_types()`. Assert completes without error. Assert `total == 25`. |
| `test_profile_directory_types_100_files` | Create 100 temp files. Assert completes. Assert `by_format` has entries. |
| `test_profile_directory_types_empty_dir` | Empty directory. Assert returns `{"total": 0, ...}`. |
| `test_progress_negative_total_becomes_none` | Construct `JobEvent` with `total=-1` via the safe path. Assert `total is None`. |
| `test_progress_zero_total_preserved` | Construct `JobEvent` with `total=0`. Assert `total == 0`. |
| `test_timeline_atime_differs_from_mtime` | Create file, modify it, read back. Assert `atime` and `mtime` values differ (or at least `atime` is populated). |
| `test_integrity_snapshot_recurses_directory` | Create dir with 3 files. Call `snapshot_file_state()`. Assert snapshot contains 3 file entries. |
| `test_verify_checks_all_hashes` | Create snapshot with md5 and sha256. Verify. Assert both are checked (mock `get_file_hash` and verify called for each). |
| `test_verify_detects_tamper` | Create snapshot. Modify file. Assert `verified: False`. |
| `test_artifact_path_confined_to_evidence_root` | Parse artifacts with `/etc/passwd` referencing `/home/user/.bash_history`. Assert paths are resolved under evidence root, not host root. |

## Edge Cases

- Profile directory with 0 files (empty result).
- Profile directory with 10,000 files (progress fires correctly, no crash).
- FileEntry with no atime (graceful fallback to 0).
- Integrity snapshot on a symlink (skip or follow based on policy).
- Artifact parser with no evidence root (use CWD or reject).

## Validation Checklist

- [ ] `python -m pytest tests/test_forensics_contract.py -q` passes
- [ ] `ruff check dataforge/modules/forensics.py dataforge/api/schema.py` passes
- [ ] `entry.name` replaced with `entry.filename` in profiling
- [ ] `JobEvent` accepts `total=None`
- [ ] Daemon emits `None` for unknown total, not `-1`
- [ ] `FileEntry` has `atime` field
- [ ] `snapshot_file_state` recurses directories
- [ ] `verify_file_state` checks all hash algorithms

## Definition of Done

All 10 unit tests pass. Profiling works on large directories. Progress sentinel is fixed. Timeline shows correct atime. Integrity snapshots recurse. Verification checks all hashes. Artifact paths are confined.

## File References

### Files to modify
- `dataforge/modules/forensics.py`
- `dataforge/api/schema.py`
### Test files to create/modify
- `tests/test_*.py` (see Unit Tests section above)

### Audit documentation
- `docs/reviews/STABILITY_AUDIT_2026-08-23.md` — source of all findings
- `docs/PARALLEL_BACKLOG.md` — ticket definitions and wave DAG
- `docs/prompts/tickets/README.md` — ticket index

### Related tickets
- Depends on: TICK-915
- Blocks: see wave DAG in `docs/PARALLEL_BACKLOG.md`

### Test file
- `tests/test_forensics_contract.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-918-forensics-profiling-progress-atime
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
git commit -m "fix(<scope>): <description> (TICK-918)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-918.

### Step 6: Push to remote
```bash
git push origin fix/TICK-918-forensics-profiling-progress-atime
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff fix/TICK-918-forensics-profiling-progress-atime -m "Merge fix/TICK-918 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-918-forensics-profiling-progress-atime
git push origin --delete fix/TICK-918-forensics-profiling-progress-atime
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-918 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-918.prompt.md`) after merge.
