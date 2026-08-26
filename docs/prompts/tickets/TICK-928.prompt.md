# TICK-928 — Daemon API: implement or remove advertised fields, HTTP auth, event subscription

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-928 |
| Wave | 13 — Platform, API, CLI, Packaging (P1) |
| Priority | P1 — API contract mismatch |
| Depends on | Wave 12 |
| Files to modify | `dataforge/engine/daemon.py`, `dataforge/api/transport/http_gateway.py` |
| Files to create | `tests/test_daemon_api_contract.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P1.15, P1.16, P1.17 |
| Validation | `python -m pytest tests/test_daemon_api_contract.py -q` |

## Context

**P1.15 — Silently ignored fields:**
- Search `sort_key`, `reverse`, `limit`: `schema.py:65-83` defines them; `daemon.py:399-417` ignores them.
- Duplicate `hash_algorithm`, `verify_content`: `schema.py:93-100`; `daemon.py:452-457` ignores.
- Integrity `algorithm`: read but unused at `daemon.py:546-564`.
- Scan `provider`: schema field at `schema.py:50-55`; no provider dispatch at `daemon.py:346-383`.

**P1.16 — Event subscription is snapshot:** `JobQueue.subscribe()` at `jobs.py:459-467` returns `iter(list(job.events))`, not a live stream. UDS/pipe servers never publish events.

**P1.17 — No HTTP auth:** `http_gateway.py:11-15` says remote exposure requires a token. No token is accepted or checked anywhere. Non-loopback binding exposes all operations without authentication.

## Objectives

1. Implement or remove each advertised API field.
2. Enforce HTTP authentication for non-loopback binding.
3. Define event subscription behavior.

## Implementation Guide

### Step 1: Implement search fields

In `_handle_search()`:

```python
sort_key = params.get("sort_key", "name")
reverse = params.get("reverse", False)
limit = params.get("limit")
# Apply to search results
results = sorted(results, key=lambda r: r.get(sort_key, ""), reverse=reverse)
if limit:
    results = results[:limit]
```

### Step 2: Implement duplicate fields

```python
hash_algorithm = params.get("hash_algorithm", "sha256")
verify_content = params.get("verify_content", False)
result = find_duplicates(root, ..., hash_algorithm=hash_algorithm, verify_content=verify_content)
```

### Step 3: Implement integrity algorithm

```python
algorithm = params.get("algorithm", "sha256")
result = verify_snapshot(snapshot_path, hash_algorithm=algorithm)
```

### Step 4: HTTP authentication

```python
class HttpGateway:
    def __init__(self, host="127.0.0.1", port=8443, auth_token=None):
        if host not in ("127.0.0.1", "localhost", "::1") and not auth_token:
            raise ValueError("Non-loopback binding requires auth_token")
        self._auth_token = auth_token
    
    def _check_auth(self, request):
        if self._auth_token:
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            if token != self._auth_token:
                raise HTTPException(status_code=401, detail="Unauthorized")
```

### Step 5: Event subscription

Define as snapshot (current behavior) and document it:

```python
def subscribe(self, job_id: str):
    """Returns a snapshot of events at call time. Not a live stream."""
    job = self.get(job_id)
    if job is None:
        return iter([])
    return iter(list(job.events))
```

## Unit Tests

Create `tests/test_daemon_api_contract.py`:

| Test function | What it asserts |
|---|---|
| `test_search_sort_key_applied` | Search with sort_key="size". Assert results sorted by size. |
| `test_search_limit_applied` | Search with limit=5. Assert <= 5 results. |
| `test_search_reverse_applied` | Search with reverse=True. Assert descending order. |
| `test_duplicate_hash_algorithm_passed` | Request with hash_algorithm="md5". Assert md5 used. |
| `test_duplicate_verify_content_passed` | Request with verify_content=True. Assert verification done. |
| `test_integrity_algorithm_applied` | Request with algorithm="sha256". Assert sha256 used. |
| `test_http_non_loopback_requires_token` | Bind to 0.0.0.0 without token. Assert raises ValueError. |
| `test_http_non_loopback_with_token_succeeds` | Bind to 0.0.0.0 with token. Assert no error. |
| `test_http_auth_rejects_invalid_token` | Request with wrong token. Assert 401. |
| `test_http_auth_accepts_valid_token` | Request with correct token. Assert 200. |
| `test_event_subscription_returns_list` | Subscribe to job. Assert returns iterable. |

## Edge Cases

- Search with all fields None (use defaults).
- HTTP on IPv6 loopback (::1).
- Subscribe to non-existent job (empty iterator).
- Auth token is empty string (should reject).

## Validation Checklist

- [ ] `python -m pytest tests/test_daemon_api_contract.py -q` passes
- [ ] `ruff check dataforge/engine/daemon.py dataforge/api/transport/http_gateway.py` passes
- [ ] Search sort/limit/reverse work
- [ ] Duplicate algorithm/verify work
- [ ] HTTP non-loopback requires token
- [ ] Event subscription documented

## Definition of Done

All 11 unit tests pass. API fields work or are removed. HTTP auth enforced. Events documented.

## File References

### Files to modify
- `dataforge/engine/daemon.py`
- `dataforge/api/transport/http_gateway.py`
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
- `tests/test_daemon_api_contract.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `develop`.

### Step 1: Sync dev first
```bash
git checkout develop
git pull origin develop
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-928-daemon-api-fields-http-auth
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
git commit -m "fix(<scope>): <description> (TICK-928)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-928.

### Step 6: Push to remote
```bash
git push origin fix/TICK-928-daemon-api-fields-http-auth
```

### Step 7: Merge to dev
```bash
git checkout develop
git pull origin develop
git merge --no-ff fix/TICK-928-daemon-api-fields-http-auth -m "Merge fix/TICK-928 into develop"
git push origin develop
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-928-daemon-api-fields-http-auth
git push origin --delete fix/TICK-928-daemon-api-fields-http-auth
```

### Step 9: Reset to dev
```bash
git checkout develop
git pull origin develop
```

### Step 10: Update backlog
Mark TICK-928 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-928.prompt.md`) after merge.
