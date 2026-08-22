# Ticket TICK-501 — Fix R-CORE-3/4/6: config persistence, cache null-guard, scanner error reporting

> **Wave 5** | **Domain:** Core / Infrastructure | **Depends on:** None
> **Source:** `docs/reviews/AUDIT_REPORT.md` Part 4 (R-CORE-3, R-CORE-4, R-CORE-6)

---

## Your Assignment

```
TICKET_ID: TICK-501
WAVE: 5
TITLE: Fix R-CORE-3/4/6: config persistence, cache null-guard, scanner error reporting
```

**Exclusive write files (SOLE writer for Wave 5):**
- `dataforge/core/config.py`
- `dataforge/core/cache.py`
- `dataforge/core/scanner.py`

**Read-only references (do not edit):**
- `docs/reviews/AUDIT_REPORT.md`
- `docs/reviews/FORENSIC_REVIEW.md`

**Test target:** `tests/test_core_hardening.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_core_hardening.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/ARCHITECTURE.md` §Core primitives
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `core/config.py`, `core/cache.py`, `core/scanner.py` sections
- `docs/DEVELOPMENT_GUIDE.md` (setup, `PYTHONPATH=. pytest`)
- `docs/CONTRIBUTING.md` §8 (When You Change Code → Update table)

---

## Work Package YAML

```yaml
ticket_id: "TICK-501"
title: "Fix R-CORE-3/4/6: config persistence, cache null-guard, scanner error reporting"
type: "Bugfix"
execution_wave: 5
depends_on: []
scope:
  domain: "Core / Infrastructure"
  exclusive_write_files:
    - "dataforge/core/config.py"
    - "dataforge/core/cache.py"
    - "dataforge/core/scanner.py"
  read_only_references:
    - "docs/reviews/AUDIT_REPORT.md"
    - "docs/reviews/FORENSIC_REVIEW.md"
architectural_context:
  existing_symbols_to_use:
    - "config.py: _merge_validated, DEFAULT_CONFIG"
    - "cache.py: FileHashCache, conn, _init_db"
    - "scanner.py: _scan_single_dir, scan_directory"
  breaking_changes: "None — all fixes are backward-compatible"
requirements:
  summary: |
    Fix three R-CORE findings from AUDIT_REPORT.md Part 4:

    R-CORE-3: collapsed_groups dropped on reload
    - config.py: _merge_validated() iterates only DEFAULT_CONFIG.items()
    - User-defined keys not in DEFAULT_CONFIG are silently dropped
    - Fix: Preserve unknown keys during merge (whitelist approach)

    R-CORE-4: cache.py conn=None crash if init failed
    - cache.py: self.conn initialized to None
    - If _init_db() raises sqlite3.Error, conn remains None
    - All methods (get_hash, set_hash, set_hash_many, clear) crash with AttributeError
    - Fix: Add null-guard to all methods, return None/empty on None conn

    R-CORE-6: scanner.py swallows FileNotFoundError
    - scanner.py: All OSError exceptions silently swallowed with bare continue/pass
    - No logging, no error callback, no mechanism for caller to know files were skipped
    - Fix: Add logging for OSError exceptions, optionally add error callback
  source_documents:
    - "docs/reviews/AUDIT_REPORT.md"
  acceptance_criteria:
    - "GIVEN config with custom key WHEN reloaded THEN custom key preserved"
    - "GIVEN cache init fails WHEN get_hash called THEN returns None (no crash)"
    - "GIVEN scanner encounters FileNotFoundError WHEN scanning THEN logs warning and continues"
    - "GIVEN scanner encounters PermissionError WHEN scanning THEN logs warning and continues"
verification:
  test_target: "tests/test_core_hardening.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_core_hardening.py -q"
```

---

## Implementation Notes

### R-CORE-3: Config persistence
```python
# In _merge_validated(), preserve unknown keys:
def _merge_validated(self, raw: dict) -> dict:
    merged = {}
    for key, default_val in self.DEFAULT_CONFIG.items():
        if key in raw:
            # validate and merge
            ...
        else:
            merged[key] = default_val
    # Preserve unknown keys (user-defined, plugins, etc.)
    for key in raw:
        if key not in merged:
            merged[key] = raw[key]
    return merged
```

### R-CORE-4: Cache null-guard
```python
# Add null-guard to all methods:
def get_hash(self, path: str, algo: str = "md5") -> str | None:
    if self.conn is None:
        return None
    # existing implementation...

def set_hash(self, path: str, algo: str, file_hash: str, size: int, mtime: float) -> None:
    if self.conn is None:
        return
    # existing implementation...
```

### R-CORE-6: Scanner error reporting
```python
# In _scan_single_dir(), add logging:
import logging
logger = logging.getLogger(__name__)

try:
    # scan logic
except FileNotFoundError:
    logger.warning("Path not found: %s", entry.path)
    continue
except PermissionError:
    logger.warning("Permission denied: %s", entry.path)
    continue
except OSError as e:
    logger.warning("OS error scanning %s: %s", entry.path, e)
    continue
```
