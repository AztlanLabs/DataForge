# Ticket TICK-504 — Fix tz-naive timestamps in non-forensic modules (F9)

> **Wave 5** | **Domain:** Core / Modules | **Depends on:** None
> **Source:** `docs/reviews/FORENSIC_REVIEW.md` F9

---

## Your Assignment

```
TICKET_ID: TICK-504
WAVE: 5
TITLE: Fix tz-naive timestamps in non-forensic modules (F9)
```

**Exclusive write files (SOLE writer for Wave 5):**
- `dataforge/modules/system_cleanup.py`
- `dataforge/modules/search.py`
- `dataforge/modules/recovery.py`
- `dataforge/modules/integrity.py`
- `dataforge/modules/performance.py`
- `dataforge/ui/views/search.py`

**Read-only references (do not edit):**
- `docs/reviews/FORENSIC_REVIEW.md`
- `docs/reviews/AUDIT_REPORT.md`

**Test target:** `tests/test_timestamp_utc.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_timestamp_utc.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/ARCHITECTURE.md` §Feature modules
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `modules/*.py` sections
- `docs/CLI_REFERENCE.md` §§ `scan/dupes/search/integrity/cleanup/recover/forensics/metadata`
- `docs/GUI_WORKFLOWS.md` Search view
- `docs/CONTRIBUTING.md` §8 (When You Change Code → Update table)

---

## Work Package YAML

```yaml
ticket_id: "TICK-504"
title: "Fix tz-naive timestamps in non-forensic modules (F9)"
type: "Bugfix"
execution_wave: 5
depends_on: []
scope:
  domain: "Core / Modules"
  exclusive_write_files:
    - "dataforge/modules/system_cleanup.py"
    - "dataforge/modules/search.py"
    - "dataforge/modules/recovery.py"
    - "dataforge/modules/integrity.py"
    - "dataforge/modules/performance.py"
    - "dataforge/ui/views/search.py"
  read_only_references:
    - "docs/reviews/FORENSIC_REVIEW.md"
    - "docs/reviews/AUDIT_REPORT.md"
architectural_context:
  existing_symbols_to_use:
    - "system_cleanup.py: datetime.now() line 232"
    - "search.py: datetime.now() line 192"
    - "recovery.py: datetime.now() line 671"
    - "integrity.py: datetime.datetime.now().isoformat() line 236"
    - "performance.py: datetime.now().isoformat() line 494"
    - "ui/views/search.py: datetime.datetime.now().strftime() line 606"
  breaking_changes: "None — all timestamps become UTC-aware"
requirements:
  summary: |
    Fix F9: tz-naive timestamps mixed with UTC.

    Forensic paths are already UTC-aware (TICK-304), but non-forensic modules
    still use tz-naive datetime.now(). This creates inconsistent timestamps
    across the application.

    Files to fix:
    1. system_cleanup.py:232 - datetime.now() → datetime.now(timezone.utc)
    2. search.py:192 - datetime.now() → datetime.now(timezone.utc)
    3. recovery.py:671 - datetime.now() → datetime.now(timezone.utc)
    4. integrity.py:236 - datetime.datetime.now().isoformat() → datetime.now(timezone.utc).isoformat()
    5. performance.py:494 - datetime.now().isoformat() → datetime.now(timezone.utc).isoformat()
    6. ui/views/search.py:606 - datetime.datetime.now().strftime() → datetime.now(timezone.utc).strftime()

    All timestamps should use datetime.now(timezone.utc) for consistency.
  source_documents:
    - "docs/reviews/FORENSIC_REVIEW.md"
  acceptance_criteria:
    - "GIVEN system_cleanup.py WHEN timestamp generated THEN UTC-aware"
    - "GIVEN search.py WHEN timestamp generated THEN UTC-aware"
    - "GIVEN recovery.py WHEN timestamp generated THEN UTC-aware"
    - "GIVEN integrity.py WHEN timestamp generated THEN UTC-aware"
    - "GIVEN performance.py WHEN timestamp generated THEN UTC-aware"
    - "GIVEN ui/views/search.py WHEN timestamp generated THEN UTC-aware"
verification:
  test_target: "tests/test_timestamp_utc.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_timestamp_utc.py -q"
```

---

## Implementation Notes

### Pattern for each file
```python
# Before:
from datetime import datetime
timestamp = datetime.now().isoformat()

# After:
from datetime import datetime, timezone
timestamp = datetime.now(timezone.utc).isoformat()
```

### For strftime patterns
```python
# Before:
datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# After:
datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
```
