# TICK-929 — Service: fix entrypoint arguments, transport security, pipe SDDL

## Metadata

| Field | Value |
|---|---|
| Ticket | TICK-929 |
| Wave | 13 — Platform, API, CLI, Packaging (P1) |
| Priority | P1 — Service won't start |
| Depends on | Wave 12 |
| Files to modify | `dataforge/service/__main__.py`, `dataforge/service/linux/dataforge.service`, `dataforge/api/transport/uds.py`, `dataforge/api/transport/named_pipe.py` |
| Files to create | `tests/test_service_transport_contract.py` |
| Audit reference | `docs/reviews/STABILITY_AUDIT_2026-08-23.md` P1.14, P1.18 |
| Validation | `python -m pytest tests/test_service_transport_contract.py -q` |

## Context

**P1.14 — Service won't start:** Source service at `dataforge.service:21` passes `--dbus`. Parser at `__main__.py:102-136` has no `--dbus` option. Service exits with argument error.

**P1.14 — Packaged unit mismatch:** Packaged unit at `packaging/systemd/dataforge.service:7-20` launches GUI bundle with `--engine`. `run_ui.py:18-39` only starts GUI.

**P1.18 — UDS iterator unreachable:** UDS iterator at `uds.py:200-207` has unreachable terminal check because same-job condition returns first.

**P1.18 — Pipe SDDL not applied:** `named_pipe.py:36-38` declares SDDL but `CreateNamedPipe()` at `named_pipe.py:321-334` receives `None` security attributes.

**P1.18 — Pipe stop incomplete:** `NamedPipeServer.stop()` at `named_pipe.py:289-319` only flips a flag. Does not cancel blocked accept/read.

**P1.18 — Client skips HTTP:** `_auto_discover_transport()` at `client/__init__.py:208-264` returns `None` after checking only UDS and pipes.

## Objectives

1. Fix service argument parser to accept all used flags.
2. Align source and packaged systemd units.
3. Fix UDS/pipe iterator condition order.
4. Apply SDDL to named pipe.
5. Fix pipe stop to cancel blocked operations.
6. Add HTTP to client auto-discover.

## Implementation Guide

### Step 1: Fix service parser

Add `--dbus` to parser (or remove from service unit):

```python
parser.add_argument("--dbus", action="store_true", help="Enable D-Bus transport (Linux)")
```

### Step 2: Align units

Source unit should use same entrypoint as packaged. If packaged uses `dataforge-engine`, source should too.

### Step 3: Fix UDS iterator

Reorder conditions: check terminal state before same-job:

```python
async def __anext__(self):
    if self._last_event and self._last_event.status in TERMINAL_STATES:
        raise StopAsyncIteration
    if same_job_check:
        ...
```

### Step 4: Apply SDDL

```python
security_attributes = SECURITY_ATTRIBUTES()
security_attributes.Sddl = SDDL
# Pass to CreateNamedPipe
```

### Step 5: Fix pipe stop

```python
async def stop(self):
    self._running = False
    if self._server:
        self._server.close()
        await self._server.wait_closed()
```

### Step 6: Add HTTP to auto-discover

```python
async def _auto_discover_transport(self):
    # Try UDS first
    # Try named pipes
    # Try HTTP
    try:
        transport = HttpGateway()
        if await transport.probe():
            return transport
    except Exception:
        pass
    return None
```

## Unit Tests

Create `tests/test_service_transport_contract.py`:

| Test function | What it asserts |
|---|---|
| `test_service_parser_accepts_dbus` | Parse `["--dbus"]`. Assert no error. Assert `args.dbus is True`. |
| `test_service_parser_accepts_socket` | Parse `["--socket", "/tmp/test.sock"]`. Assert no error. |
| `test_service_parser_accepts_pipe` | Parse `["--pipe", "test"]`. Assert no error. |
| `test_service_parser_rejects_unknown` | Parse `["--unknown"]`. Assert SystemExit. |
| `test_uds_iterator_terminal_check` | Create iterator. Append terminal event. Assert next raises StopAsyncIteration. |
| `test_pipe_sddl_applied` | Create server. Assert security attributes set (mock CreateNamedPipe). |
| `test_pipe_stop_cancels_blocked` | Start server. Stop. Assert returns within timeout. |
| `test_client_discovers_http` | Mock HTTP probe succeeding. Assert auto_discover returns HTTP transport. |

## Edge Cases

- Service with no arguments (use defaults).
- UDS socket path doesn't exist (create or error).
- Pipe name already in use (error or wait).
- HTTP probe timeout (skip, try next).

## Validation Checklist

- [ ] `python -m pytest tests/test_service_transport_contract.py -q` passes
- [ ] `ruff check` on all 4 files passes
- [ ] `--dbus` accepted by parser
- [ ] Source and packaged units aligned
- [ ] UDS iterator terminal check works
- [ ] Pipe SDDL applied
- [ ] Client discovers HTTP

## Definition of Done

All 8 unit tests pass. Service starts with its arguments. Transports work correctly. Client discovers all transports.

## File References

### Files to modify
- `dataforge/service/__main__.py`
- `dataforge/service/linux/dataforge.service`
- `dataforge/api/transport/uds.py`
- `dataforge/api/transport/named_pipe.py`
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
- `tests/test_service_transport_contract.py`

## Git Workflow

Follow this exact workflow for every ticket. Base branch is `dev`.

### Step 1: Sync dev first
```bash
git checkout dev
git pull origin dev
```

### Step 2: Branch from dev
```bash
git checkout -b fix/TICK-929-service-arguments-transport
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
git commit -m "fix(<scope>): <description> (TICK-929)"
```
Use Conventional Commits format. Max 72 chars. Reference TICK-929.

### Step 6: Push to remote
```bash
git push origin fix/TICK-929-service-arguments-transport
```

### Step 7: Merge to dev
```bash
git checkout dev
git pull origin dev
git merge --no-ff fix/TICK-929-service-arguments-transport -m "Merge fix/TICK-929 into dev"
git push origin dev
```

### Step 8: Clean up
```bash
git branch -d fix/TICK-929-service-arguments-transport
git push origin --delete fix/TICK-929-service-arguments-transport
```

### Step 9: Reset to dev
```bash
git checkout dev
git pull origin dev
```

### Step 10: Update backlog
Mark TICK-929 as DONE in `docs/PARALLEL_BACKLOG.md` with:
- Date
- Test count (e.g., `10/10`)
- Commit hash
- Brief verification summary

Delete this prompt file (`docs/prompts/tickets/TICK-929.prompt.md`) after merge.
