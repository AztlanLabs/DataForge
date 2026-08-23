# Ticket TICK-912 — Test suite consolidation + deprecated prune

> **Wave 10** | **Domain:** Tests / Quality | **Depends on:** Wave 9 (901-908)
> **Source:** user report `Create a ticket where reduce the number of unit tests, and deprecated tests, also merge tests so instead of multiple tests that does the same now have less with more robust tests.` + `tests/` 57 files, `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

---

## Your Assignment

```
TICKET_ID: TICK-912
WAVE: 10
TITLE: Test suite consolidation + deprecated prune
```

**Exclusive write files (SOLE writer for Wave 10):**
- `tests/test_comprehensive.py`
- `tests/test_integration.py`
- `tests/test_contract_regressions.py`
- `tests/test_new_modules.py`
- `tests/verify_scenarios.py`
- `scripts/tests_consolidate.py [NEW FILE]`

**Read-only references (do not edit):**
- `tests/test_scanner_parallel.py`
- `tests/test_hasher_mmap.py`
- `tests/test_cache_batch.py`
- `tests/test_ui_job_manager.py`
- `pyproject.toml`
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`

**Test target:** `tests/test_consolidated_suite.py [NEW FILE]`
**Validation:** `python -m pytest tests/test_consolidated_suite.py -q`

**Depends on:** ["TICK-901", "TICK-902", "TICK-903", "TICK-904", "TICK-905", "TICK-906", "TICK-907", "TICK-908"]

---

## Relevant Documentation — Must Read Before Coding

- `docs/CONTRIBUTING.md` §Testing
- `docs/TECHNICAL_SOURCE_OF_TRUTH.md`
- `tests/` existing suite

---

## Work Package YAML

```yaml
ticket_id: "TICK-912"
title: "Test suite consolidation + deprecated prune"
type: "Refactor"
execution_wave: 10
depends_on: ["TICK-901", "TICK-902", "TICK-903", "TICK-904", "TICK-905", "TICK-906", "TICK-907", "TICK-908"]
scope:
  domain: "Tests / Quality"
  exclusive_write_files:
    - "tests/test_comprehensive.py"
    - "tests/test_integration.py"
    - "tests/test_contract_regressions.py"
    - "tests/test_new_modules.py"
    - "tests/verify_scenarios.py"
    - "scripts/tests_consolidate.py [NEW FILE]"
  read_only_references:
    - "tests/test_scanner_parallel.py"
    - "tests/test_hasher_mmap.py"
    - "tests/test_cache_batch.py"
    - "tests/test_ui_job_manager.py"
    - "pyproject.toml"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
architectural_context:
  existing_symbols_to_use:
    - "tests/test_comprehensive.py: 223 tests? legacy comprehensive"
    - "tests/test_integration.py: integration"
    - "tests/test_contract_regressions.py: 412? crossfade/instant sidebar"
    - "tests/test_new_modules.py: new modules"
    - "verify_scenarios.py: manual scenarios"
    - "pytest: parametrize, fixtures, tmp_path"
  breaking_changes: "None — test-only, no prod code change"
requirements:
  summary: |
    Test suite has grown to 57 files, 1406 tests, with much duplication and deprecated scenarios:

    * test_comprehensive.py, test_integration.py, test_contract_regressions.py, test_new_modules.py overlap heavily with per-wave tests (test_scanner_parallel, test_hasher_mmap, test_dupes_pipeline, etc.). Example: contract_regressions checks crossfade/instant sidebar already covered by test_ui_job_manager + newer stability tests.
    * verify_scenarios.py is manual script, not pytest.
    * Many Wave 0-3 contract tests (test_paths_contract, test_provider_contract, test_api_schema, test_migration_contracts, test_jobs_contract) are now redundant after impl; keep as smoke but merge.
    * 1406 tests take >90s, CI slow.

    Goal: reduce number of tests, remove deprecated, merge overlapping into fewer more robust tests with parametrization.

    Tasks:

    * Audit all 57 tests: classify kept, deprecated (remove), merged. Produce report `scripts/tests_consolidate.py` that prints audit (like `python scripts/tests_consolidate.py --audit` lists kept/removed/merged counts). Keep per-wave feature tests (test_scanner_parallel, test_hasher_mmap, test_dupes_pipeline, test_integrity_streaming, test_search_streaming, test_forensics_streaming, test_logger_stdout, test_operations_collision, etc.) as ground truth — do NOT delete those. Target deprecated: test_comprehensive, test_integration, test_contract_regressions (412 tests!), test_new_modules, verify_scenarios. Those 5 files account for ~800 tests overlapping.

    * Create `tests/test_consolidated_suite.py [NEW FILE]` that merges the kept essence of deprecated tests into parametrized suites:
      - One parametrized `test_contract_parity` covering paths/provider/api/migration/jobs contracts (5→1 file).
      - One `test_ui_shell` covering crossfade, sidebar, job manager, theme tokens.
      - One `test_integration_smoke` covering daemon/client + audit evidence integration.

      The consolidated file must have <50 tests but cover same acceptance as deprecated 800.

    * Deprecate (delete or gut) the 5 target files: either delete them or replace with `pytest.skip("consolidated into test_consolidated_suite")` shim to keep import path but not run. Preferred: delete file contents and keep file with skip, or delete file entirely and let git track removal — choose delete (rm) and document in script. Ensure `pytest -q` total count drops from 1406 to ~900-1000 but coverage not lost.

    * Update pyproject.toml test config if needed (addopts -q).

    * Provide migration guide in script docstring.

    This is SOLE writer to those 5 test files + new script for Wave 10; no other Wave 10 ticket touches tests (TICK-911 touches engine, TICK-913 touches dead code). Disjoint guarantee satisfied.

  source_documents:
    - "docs/CONTRIBUTING.md"
    - "docs/TECHNICAL_SOURCE_OF_TRUTH.md"
    - "tests/test_comprehensive.py:1"
    - "tests/test_contract_regressions.py:1"
  acceptance_criteria:
    - "GIVEN audit via scripts/tests_consolidate.py --audit WHEN run THEN report lists 57 files, marks 5 deprecated (comprehensive, integration, contract_regressions, new_modules, verify_scenarios) as deprecated, and shows merged count"
    - "GIVEN deprecated files removed/replaced WHEN pytest tests/test_consolidated_suite.py -q THEN passes with <50 tests covering same contracts"
    - "GIVEN full suite pytest -q WHEN run THEN total tests 900-1000 (down from 1406) and passes, no deprecated file still runs 400+ tests"
    - "GIVEN kept per-wave tests (scanner_parallel, hasher_mmap, dupes_pipeline, etc.) WHEN run THEN still pass unchanged"
verification:
  test_target: "tests/test_consolidated_suite.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_consolidated_suite.py -q"
```

---

## Implementation Notes

```python
# scripts/tests_consolidate.py — audit tool
# python scripts/tests_consolidate.py --audit
# should print:
# Kept: 52 files (scanner_parallel, hasher_mmap, ...)
# Deprecated: 5 files (comprehensive, integration, contract_regressions, new_modules, verify_scenarios) → merged into test_consolidated_suite
# Total before: 1406, after: ~950, reduction: 32%

# tests/test_consolidated_suite.py — merged parametrized
import pytest
@pytest.mark.parametrize("contract,fn", [
    ("paths", check_paths), ("provider", check_provider), ...
])
def test_contract_parity(contract, fn): fn()

def test_ui_shell_crossfade(...): ...
def test_integration_smoke_daemon(...): ...

# For deprecated files: either delete or leave skip stub
# tests/test_comprehensive.py:
import pytest; pytest.skip("consolidated into test_consolidated_suite", allow_module_level=True)
```

# Prompt: Parallel Ticket Agent — DataForge Hardened Backlog

> **Generic prompt for AI agents working on `docs/PARALLEL_BACKLOG.md` in parallel. Copy this prompt, replace `TICK-912` with the ticket you own, and run. One ticket = one branch = one commit = one PR. Do not touch files outside your ticket's `exclusive_write_files`.**

## Role

You are an autonomous coding agent on `develop` (Python 3.10+, PyQt5, Click, SQLite WAL). Complete **one** ticket end-to-end.

## Ticket Assignment

```
TICKET_ID: TICK-912
WAVE: 10
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
git checkout -b refactor/TICK-912-test-consolidation
PYTHONPATH=. python -m pytest tests/test_consolidated_suite.py -q
PYTHONPATH=. python -m pytest -q
ruff check dataforge tests
git add tests/test_comprehensive.py tests/test_integration.py tests/test_contract_regressions.py tests/test_new_modules.py tests/verify_scenarios.py scripts/tests_consolidate.py tests/test_consolidated_suite.py
git commit -m "refactor(tests): consolidate deprecated suite into parametrized"
git push -u origin refactor/TICK-912-test-consolidation
```

## Work Package YAML for TICK-912

```yaml
ticket_id: "TICK-912"
title: "Test suite consolidation + deprecated prune"
type: "Refactor"
execution_wave: 10
depends_on: ["TICK-901", "TICK-902", "TICK-903", "TICK-904", "TICK-905", "TICK-906", "TICK-907", "TICK-908"]
scope:
  domain: "Tests / Quality"
  exclusive_write_files:
    - "tests/test_comprehensive.py"
    - "tests/test_integration.py"
    - "tests/test_contract_regressions.py"
    - "tests/test_new_modules.py"
    - "tests/verify_scenarios.py"
    - "scripts/tests_consolidate.py [NEW FILE]"
  read_only_references:
    - "tests/test_scanner_parallel.py"
architectural_context:
  existing_symbols_to_use:
    - "tests/test_comprehensive.py"
  breaking_changes: "None"
requirements:
  summary: "Reduce deprecated tests, merge into robust parametrized"
  source_documents:
    - "docs/CONTRIBUTING.md"
  acceptance_criteria:
    - "GIVEN audit THEN deprecated 5 files merged"
verification:
  test_target: "tests/test_consolidated_suite.py [NEW FILE]"
  validation_command: "python -m pytest tests/test_consolidated_suite.py -q"
```
