> **Status: ✅ COMPLETED 2026-08-23 — Wave 5 DONE, verified (see docs/PARALLEL_BACKLOG.md Wave 5 Review). This ticket is closed — do not re-run.**

# Ticket TICK-502 — Move secure_delete to dedicated sanitisation module (F4)

> **Wave 5** | **Domain:** Modules / Sanitisation | **Depends on:** "TICK-304"
> **Source:** `docs/reviews/FORENSIC_REVIEW.md` F4

---

## Your Assignment

```
TICKET_ID: TICK-502
WAVE: 5
TITLE: Move secure_delete to dedicated sanitisation module (F4)
```

**Exclusive write files (SOLE writer for Wave 5):**
- `dataforge/modules/sanitisation.py [NEW FILE]`
- `dataforge/modules/forensics.py`

**Read-only references (do not edit):**
- `docs/reviews/FORENSIC_REVIEW.md`
- `docs/reviews/AUDIT_REPORT.md`

**Test target:** `tests/test_sanitisation.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_sanitisation.py -q`

**Depends on:** "TICK-304"

---

## Relevant Documentation — Must Read Before Coding

- `docs/ARCHITECTURE.md` §Feature modules
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `modules/forensics.py` section
- `docs/CLI_REFERENCE.md` §§ `forensics`
- `docs/GUI_WORKFLOWS.md` Forensics view
- `docs/CONTRIBUTING.md` §8 (When You Change Code → Update table)

---

## Work Package YAML

```yaml
ticket_id: "TICK-502"
title: "Move secure_delete to dedicated sanitisation module (F4)"
type: "Refactor"
execution_wave: 5
depends_on: ["TICK-304"]
scope:
  domain: "Modules / Sanitisation"
  exclusive_write_files:
    - "dataforge/modules/sanitisation.py [NEW FILE]"
    - "dataforge/modules/forensics.py"
  read_only_references:
    - "docs/reviews/FORENSIC_REVIEW.md"
    - "docs/reviews/AUDIT_REPORT.md"
architectural_context:
  existing_symbols_to_use:
    - "forensics.py: secure_delete (lines 1098-1159)"
    - "forensics.py: Evidence Mode gate (line 1116)"
  breaking_changes: "None — forensics.py re-exports secure_delete for backward compat"
requirements:
  summary: |
    Move secure_delete() from forensics.py to a dedicated sanitisation.py module.

    F4 Issue: A destroy primitive (secure_delete) sitting beside carving/timeline
    in the forensic module is a procurement flag. It should be in a separate module.

    Implementation:
    1. Create dataforge/modules/sanitisation.py
    2. Move secure_delete() function to sanitisation.py
    3. Keep backward-compatible re-export in forensics.py
    4. Preserve Evidence Mode gate (F3)
    5. Add hardlink/reflink awareness (F21)
  source_documents:
    - "docs/reviews/FORENSIC_REVIEW.md"
  acceptance_criteria:
    - "GIVEN sanitisation.py exists WHEN imported THEN secure_delete available"
    - "GIVEN forensics.py imported WHEN secure_delete called THEN delegates to sanitisation.py"
    - "GIVEN Evidence Mode active WHEN secure_delete called THEN blocked with ACPO error"
    - "GIVEN hardlink detected WHEN secure_delete called THEN warns about shared data"
verification:
  test_target: "tests/test_sanitisation.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_sanitisation.py -q"
```

---

## Implementation Notes

### Module structure
```python
# dataforge/modules/sanitisation.py
"""Secure file sanitisation module.

Moved from forensics.py to separate destroy primitives from forensic analysis.
"""

import os
from pathlib import Path

def secure_delete(path: Path, passes: int = 3, evidence_mode: bool = False) -> dict:
    """Securely delete a file by overwriting before removal.

    Args:
        path: File to delete
        passes: Number of overwrite passes (default 3)
        evidence_mode: If True, block destructive operations (ACPO §1)

    Returns:
        dict with status, path, passes, method
    """
    if evidence_mode:
        return {
            "status": "blocked",
            "path": str(path),
            "error": "Secure delete blocked in Evidence Mode (ACPO §1)",
        }

    # Check for hardlinks
    try:
        stat = path.stat()
        if stat.st_nlink > 1:
            return {
                "status": "warning",
                "path": str(path),
                "warning": f"File has {stat.st_nlink} hardlinks - data may persist",
            }
    except OSError:
        pass

    # Implementation...
```

### Backward-compatible re-export
```python
# In forensics.py, add at end:
from .sanitisation import secure_delete  # noqa: F401 — backward compat
```
