# Ticket TICK-505 — Fix ingest_disk_image list materialisation (F14)

> **Wave 6** | **Domain:** Modules / Forensics | **Depends on:** "TICK-502", "TICK-304"
> **Source:** `docs/reviews/FORENSIC_REVIEW.md` F14
> **Note:** Moved from Wave 5 → Wave 6 on 2026-08-23 to resolve same-wave `dataforge/modules/forensics.py` collision with TICK-502 (both exclusive writers in Wave 5). TICK-502 remains sole Wave 5 writer to `forensics.py`; TICK-505 is sole Wave 6 writer (sequential re-entry, hardened disjoint guarantee).

---

## Your Assignment

```
TICKET_ID: TICK-505
WAVE: 6
TITLE: Fix ingest_disk_image list materialisation (F14)
```

**Exclusive write files (SOLE writer for Wave 6 — sequential re-entry after TICK-502 Wave 5):**
- `dataforge/modules/forensics.py`

**Read-only references (do not edit):**
- `docs/reviews/FORENSIC_REVIEW.md`
- `docs/reviews/AUDIT_REPORT.md`

**Test target:** `tests/test_forensics_streaming.py` (extend existing)
**Validation:** `python -m pytest tests/test_forensics_streaming.py -q`

**Depends on:** "TICK-502", "TICK-304" *(Wave 6 gate: TICK-502 Wave 5 must merge first due to `forensics.py` sequential re-entry)*

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
ticket_id: "TICK-505"
title: "Fix ingest_disk_image list materialisation (F14)"
type: "Bugfix"
execution_wave: 6
depends_on: ["TICK-502", "TICK-304"]  # Wave 6 — sequential after TICK-502 Wave 5 (forensics.py re-entry)
scope:
  domain: "Modules / Forensics"
  exclusive_write_files:
    - "dataforge/modules/forensics.py"
  read_only_references:
    - "docs/reviews/FORENSIC_REVIEW.md"
    - "docs/reviews/AUDIT_REPORT.md"
architectural_context:
  existing_symbols_to_use:
    - "forensics.py: ingest_disk_image (lines 551-697)"
    - "forensics.py: stream_entries, queued_paths"
  breaking_changes: "None — streaming behavior preserved"
requirements:
  summary: |
    Fix F14: ingest_disk_image materialises full path list despite streaming queue.

    Current behavior (lines 632-635 comment):
    "In a true pipeline each stage would consume from queue incrementally;
    here we drain once and reuse the list."

    The code appends every path to stream_entries (line 629), then drains
    the queue into queued_paths (lines 636-643), and uses one of these lists
    for both hash and keyword stages.

    Fix: Make each stage consume directly from the queue incrementally:
    1. Hash stage: consume from queue, hash, yield results
    2. Artifact stage: consume from queue, parse artifacts, yield results
    3. Keyword stage: consume from queue, search keywords, yield results

    This eliminates the list materialisation and reduces memory usage.
  source_documents:
    - "docs/reviews/FORENSIC_REVIEW.md"
  acceptance_criteria:
    - "GIVEN ingest_disk_image called WHEN processing THEN no full list materialised"
    - "GIVEN ingest_disk_image called WHEN processing THEN memory usage O(batch) not O(files)"
    - "GIVEN ingest_disk_image called WHEN processing THEN streaming behavior preserved"
verification:
  test_target: "tests/test_forensics_streaming.py"
  validation_command: "python -m pytest tests/test_forensics_streaming.py -q"
```

---

## Implementation Notes

### Streaming pipeline
```python
def ingest_disk_image(image_path: str, ...) -> dict:
    """Ingest disk image with streaming pipeline."""

    # Create queue for streaming
    entry_queue = queue.Queue(maxsize=1000)

    # Producer thread: scan image and put entries in queue
    def producer():
        for entry in scan_directory(image_path):
            entry_queue.put(entry)
        entry_queue.put(None)  # Sentinel

    # Start producer
    producer_thread = threading.Thread(target=producer)
    producer_thread.start()

    # Consumer stages: each reads from queue
    results = {
        "hashes": [],
        "artifacts": [],
        "keywords": [],
    }

    # Hash stage
    while True:
        entry = entry_queue.get()
        if entry is None:
            break
        hash_result = calculate_hashes(entry)
        results["hashes"].append(hash_result)

    # Note: For multiple stages, we need to either:
    # 1. Use multiple queues (pipeline pattern)
    # 2. Or process all stages per entry (simpler)

    # Option 2: Process all stages per entry
    while True:
        entry = entry_queue.get()
        if entry is None:
            break

        # Hash
        hash_result = calculate_hashes(entry)
        results["hashes"].append(hash_result)

        # Artifacts
        artifact_result = parse_artifacts(entry)
        results["artifacts"].append(artifact_result)

        # Keywords
        keyword_result = search_keywords(entry)
        results["keywords"].append(keyword_result)

    producer_thread.join()
    return results
```
