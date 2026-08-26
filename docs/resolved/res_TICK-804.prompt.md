# Ticket TICK-804 — Settings Performance DB Cache info + size

> **Wave 8** | **Domain:** UI / Settings+Cache | **Depends on:** None
> **Source:** `docs/GUI_WORKFLOWS.md` Settings, `dataforge/core/cache.py`

---

## Your Assignment

```
TICKET_ID: TICK-804
WAVE: 8
TITLE: Settings Performance DB Cache info + size
```

**Exclusive write files (SOLE writer for Wave 8):**
- `dataforge/ui/views/settings.py`
- `dataforge/core/cache.py`
- `dataforge/modules/performance.py`

**Read-only references (do not edit):**
- `dataforge/core/paths.py`
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

**Test target:** `tests/test_cache_info.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_cache_info.py -q`

**Depends on:** None

---

## Relevant Documentation — Must Read Before Coding

- `docs/GUI_WORKFLOWS.md` Settings Performance section
- `docs/ARCHITECTURE.md` §Core
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md` `core/cache.py`

---

## Work Package YAML

```yaml
ticket_id: "TICK-804"
title: "Settings Performance DB Cache info + size"
type: "Feature"
execution_wave: 8
depends_on: []
scope:
  domain: "UI / Settings+Cache"
  exclusive_write_files:
    - "dataforge/ui/views/settings.py"
    - "dataforge/core/cache.py"
    - "dataforge/modules/performance.py"
  read_only_references:
    - "dataforge/core/paths.py"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
architectural_context:
  existing_symbols_to_use:
    - "cache.py: FileHashCache, get_stats, clear, file_cache"
    - "settings.py: row_cache, btn_clear_cache"
    - "performance.py: get_live_resource_snapshot"
  breaking_changes: "None — additive cache stats API, UI adds labels"
requirements:
  summary: |
    Settings → Performance → DB Cache currently only has Clear Cache DB button (register_tiered Everything) with no info. User wants to see size, info, useful stats, not only delete.

    Add to cache.py: get_stats() -> {path, size_bytes, formatted_size, entry_count (SELECT count(*)), page_count/freelist via PRAGMA, last_vacuum, hit_rate if tracked}. Use os.path.getsize(cache_db) and PRAGMA.

    Add to settings.py: row_cache now shows cache size label, entry count, last modified, and a Refresh button that calls cache.get_stats() via run_workflow (not blocking UI). Keep Clear button but add confirmation with size. Also add row for cache_batch_size and hash_block_size display.

    Add to performance.py: include cache stats in get_live_resource_snapshot (optional) for Performance view.
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
  acceptance_criteria:
    - "GIVEN Settings Performance tab WHEN opened THEN shows cache size (e.g., '2.4 MB'), entry count (e.g., '1234 entries'), path, and last modified"
    - "GIVEN cache with 100 entries WHEN get_stats called THEN entry_count == 100 and size_bytes > 0"
    - "GIVEN Clear Cache clicked WHEN confirmed THEN cache cleared and stats refresh to 0 entries"
    - "GIVEN no cache file WHEN stats called THEN size 0 and entry_count 0, no crash"
verification:
  test_target: "tests/test_cache_info.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_cache_info.py -q"
```

---

## Implementation Notes

```python
# cache.py: add get_stats()
def get_stats(self):
    try:
        size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
        with self._lock:
            c = self.conn.execute("SELECT count(*) FROM file_hashes")
            count = c.fetchone()[0]
            # PRAGMA page_count etc.
    except Exception: ...

# settings.py: add labels + refresh
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-804` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-804
WAVE: 8
```

## Required Reading (in order)

1. `docs/CONSOLIDATED_SPEC.md` §2–7
2. `docs/PARALLEL_BACKLOG.md` Concurrency Map + How to Work a Ticket
3. `docs/CONTRIBUTING.md` §3, §8, §10
4. Your Work Package YAML above
5. `read_only_references` files

## File Ownership

- Write only to `exclusive_write_files`. New files carry ` [NEW FILE]`.
- Central touchpoints are single-writer per wave.

## Workflow

```bash
git checkout develop && git pull origin develop
git checkout -b feat/TICK-804-cache-info
PYTHONPATH=. python -m pytest tests/test_cache_info.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add <exclusive> tests/test_*.py
git commit -m "feat(ui): cache info size + stats in Performance"
git push -u origin feat/TICK-804-cache-info
```

## Work Package YAML for TICK-804

```yaml
ticket_id: "TICK-804"
title: "Settings Performance DB Cache info + size"
type: "Feature"
execution_wave: 8
depends_on: []
scope:
  domain: "UI / Settings+Cache"
  exclusive_write_files:
    - "dataforge/ui/views/settings.py"
    - "dataforge/core/cache.py"
    - "dataforge/modules/performance.py"
  read_only_references:
    - "dataforge/core/paths.py"
architectural_context:
  existing_symbols_to_use:
    - "cache.py: FileHashCache"
  breaking_changes: "None"
requirements:
  summary: "Add cache info"
  source_documents:
    - "docs/GUI_WORKFLOWS.md"
  acceptance_criteria:
    - "GIVEN Settings Performance WHEN opened THEN shows cache size"
verification:
  test_target: "tests/test_cache_info.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_cache_info.py -q"
```
