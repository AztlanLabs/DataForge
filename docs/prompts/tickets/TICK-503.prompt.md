> **Status: ✅ COMPLETED 2026-08-23 — Wave 5 DONE, verified (see docs/PARALLEL_BACKLOG.md Wave 5 Review). This ticket is closed — do not re-run.**

# Ticket TICK-503 — Wire AuditLog into FileActionService (F1)

> **Wave 5** | **Domain:** Service / Audit | **Depends on:** "TICK-304"
> **Source:** `docs/reviews/FORENSIC_REVIEW.md` F1

---

## Your Assignment

```
TICKET_ID: TICK-503
WAVE: 5
TITLE: Wire AuditLog into FileActionService (F1)
```

**Exclusive write files (SOLE writer for Wave 5):**
- `dataforge/core/services/file_actions.py`

**Read-only references (do not edit):**
- `dataforge/core/audit.py`
- `dataforge/core/case.py`
- `docs/reviews/FORENSIC_REVIEW.md`

**Test target:** `tests/test_audit_integration.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_audit_integration.py -q`

**Depends on:** "TICK-304"

---

## Relevant Documentation — Must Read Before Coding

- `docs/ARCHITECTURE.md` §Operations + §Service (`FileActionService`)
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `services/file_actions.py`, `core/audit.py`
- `docs/CLI_REFERENCE.md` (verify `fm` still delegates to service)
- `docs/CONTRIBUTING.md` §8 (When You Change Code → Update table)

---

## Work Package YAML

```yaml
ticket_id: "TICK-503"
title: "Wire AuditLog into FileActionService (F1)"
type: "Feature"
execution_wave: 5
depends_on: ["TICK-304"]
scope:
  domain: "Service / Audit"
  exclusive_write_files:
    - "dataforge/core/services/file_actions.py"
  read_only_references:
    - "dataforge/core/audit.py"
    - "dataforge/core/case.py"
    - "docs/reviews/FORENSIC_REVIEW.md"
architectural_context:
  existing_symbols_to_use:
    - "audit.py: AuditLog, append, verify"
    - "case.py: CaseContext, evidence_mode"
    - "file_actions.py: FileActionService, transfer_items, delete_items, rename_items, archive_items"
  breaking_changes: "None — audit_log parameter is optional"
requirements:
  summary: |
    Wire AuditLog into FileActionService so all file operations are recorded
    in the hash-chained audit log.

    F1 Issue: AuditLog infrastructure exists (TICK-304) but is not wired into
    FileActionService. No file operation actually writes to the audit log.

    Implementation:
    1. Add optional audit_log parameter to FileActionService.__init__()
    2. Add optional case_context parameter to FileActionService.__init__()
    3. Record each operation in audit_log.append() with:
       - operation type (transfer/delete/rename/archive)
       - source path(s)
       - destination path(s)
       - timestamp (UTC)
       - result (success/failure)
       - case_id from case_context
    4. In Evidence Mode, verify audit log integrity before operations
  source_documents:
    - "docs/reviews/FORENSIC_REVIEW.md"
  acceptance_criteria:
    - "GIVEN FileActionService with audit_log WHEN transfer_items called THEN operation recorded"
    - "GIVEN FileActionService with audit_log WHEN delete_items called THEN operation recorded"
    - "GIVEN FileActionService with audit_log WHEN rename_items called THEN operation recorded"
    - "GIVEN FileActionService with audit_log WHEN archive_items called THEN operation recorded"
    - "GIVEN Evidence Mode active WHEN operation called THEN audit log verified first"
    - "GIVEN audit log tampered WHEN verify called THEN raises IntegrityError"
verification:
  test_target: "tests/test_audit_integration.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_audit_integration.py -q"
```

---

## Implementation Notes

### Constructor changes
```python
class FileActionService:
    def __init__(
        self,
        provider: FileProvider | None = None,
        audit_log: AuditLog | None = None,
        case_context: CaseContext | None = None,
    ):
        self.provider = provider or default_provider()
        self.audit_log = audit_log
        self.case_context = case_context
```

### Recording operations
```python
def _record_operation(
    self,
    operation: str,
    sources: list[str],
    destinations: list[str],
    result: str,
    error: str | None = None,
) -> None:
    """Record operation in audit log if available."""
    if self.audit_log is None:
        return

    entry = {
        "operation": operation,
        "sources": sources,
        "destinations": destinations,
        "result": result,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if self.case_context:
        entry["case_id"] = self.case_context.case_id
        entry["operator"] = self.case_context.operator

    self.audit_log.append(json.dumps(entry))
```

### Evidence Mode gate
```python
def transfer_items(self, items, destination, dry_run=False):
    # Verify audit log integrity in Evidence Mode
    if self.case_context and self.case_context.evidence_mode:
        if self.audit_log and not self.audit_log.verify():
            return [{"status": "blocked", "error": "Audit log integrity check failed"}]

    # Existing implementation...
```
