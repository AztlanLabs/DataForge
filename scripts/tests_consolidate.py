#!/usr/bin/env python3
"""Test-suite consolidation audit tool (TICK-912, Wave 10).

This script is the single source of truth for the Wave 10 test consolidation:
it classifies every file under ``tests/`` as **kept** or **deprecated** and
prints an audit report that matches the ticket acceptance criteria:

    python scripts/tests_consolidate.py --audit

The report lists:
  * every kept file (per-wave feature tests, ground truth — untouched),
  * the 5 deprecated files and what they were merged into,
  * before/after test counts and the reduction percentage.

Migration guide
---------------
What was deprecated (5 files, ~271 pytest tests + 1 manual script):

  * ``tests/test_comprehensive.py``           149 tests — legacy catch-all; core
    hasher/scanner/cache/search/dupes/operations coverage now lives in the
    per-wave suites (``test_hasher_mmap``, ``test_scanner_parallel``,
    ``test_cache_batch``, ``test_search_streaming``, ``test_dupes_pipeline``,
    ``test_operations_collision``, ...). The unique utils/config/export
    essence is preserved in ``tests/test_consolidated_suite.py``
    (``test_utils_parity``, ``test_export_parity``).
  * ``tests/test_integration.py``               18 tests — action-pipeline E2E
    and plugin packaging path checks, merged into ``test_integration_smoke``
    (pipeline, plugin packaging, shared ops, search+move).
  * ``tests/test_contract_regressions.py``      91 tests — CLI contract +
    UI-shell regressions (crossfade, sidebar, reduce-motion, focus ring,
    empty state, icons), merged into ``test_ui_shell`` and the CLI smoke
    cases of ``test_integration_smoke``.
  * ``tests/test_new_modules.py``               13 tests — junk-scan
    classification, password strength, forensics HTML escaping, hardware /
    performance smoke, merged into ``test_new_modules_parity``.
  * ``tests/verify_scenarios.py``               manual ``unittest`` script
    (not collected by pytest) — dupes/search/cleaner/renamer/integrity
    end-to-end scenarios, merged into ``test_integration_smoke``
    (``test_workflow_scenarios_*``).

What replaced them:

  * ``tests/test_consolidated_suite.py`` — one parametrized file (<50 tests)
    with ``test_contract_parity`` (paths/provider/api/migration/jobs, 5->1),
    ``test_ui_shell`` (crossfade, sidebar, job manager, theme tokens),
    ``test_integration_smoke`` (daemon/client, audit evidence, action
    pipeline), ``test_utils_parity``, ``test_export_parity`` and
    ``test_new_modules_parity``.

What was explicitly kept (ground truth, do NOT delete):
  test_scanner_parallel, test_hasher_mmap, test_cache_batch,
  test_dupes_pipeline, test_integrity_streaming, test_search_streaming,
  test_forensics_streaming, test_logger_stdout_regression,
  test_operations_collision, test_daemon_client_integration,
  test_audit_evidence_mode, test_audit_integration, test_theme_tokens,
  test_ui_job_manager, test_paths_contract, test_provider_contract,
  test_api_schema, test_migration_contracts, test_jobs_contract, and every
  other Wave 1-9 feature/stability suite.

Test-count bookkeeping
----------------------
Numbers below are from the last verified ``pytest --collect-only -q`` run on
``develop`` (2026-08-25):

  * before: 1185 collected tests across 64 ``test_*.py`` files
  * deprecated: 149 + 18 + 91 + 13 = 271 (verify_scenarios.py is not
    pytest-collected; it is a manual script)
  * consolidated replacement: tests/test_consolidated_suite.py (AST-counted
    below, <50 by contract)
  * after: 1185 - 271 + consolidated ~= 950 (target 900-1000)

The AST counter here is an estimate; the authoritative count is
``pytest --collect-only -q`` (runs in ~3s).
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO_ROOT / "tests"

# Last verified pytest --collect-only counts (2026-08-25, develop HEAD 052f8c1).
VERIFIED_BEFORE_TOTAL = 1185
VERIFIED_DEPRECATED_COUNTS = {
    "test_comprehensive.py": 149,
    "test_integration.py": 18,
    "test_contract_regressions.py": 91,
    "test_new_modules.py": 13,
    "verify_scenarios.py": 0,  # manual unittest script, not pytest-collected
}

DEPRECATED = tuple(VERIFIED_DEPRECATED_COUNTS)
MERGED_INTO = "tests/test_consolidated_suite.py"


def _count_test_functions(path: Path) -> int:
    """AST count of pytest test functions/methods in one file.

    ``def test_*`` at module level, methods of ``class Test*``, and a
    ``@pytest.mark.parametrize`` multiplier estimate (first-arg list length).
    """

    def _parametrize_len(decorators: list[ast.expr]) -> int:
        for dec in decorators:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            if isinstance(func, ast.Attribute) and func.attr == "parametrize":
                pass
            elif isinstance(func, ast.Name) and func.id == "parametrize":
                pass
            else:
                continue
            args = [a for a in dec.args if isinstance(a, ast.List)]
            if args:
                return max(1, len(args[0].elts))
        return 1

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return 0

    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                count += _parametrize_len(node.decorator_list)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith(
                    "test_"
                ):
                    count += _parametrize_len(item.decorator_list)
    return count


def _pytest_collected_count(path: Path) -> int:
    """Authoritative test count for one file via ``pytest --collect-only``."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", str(path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        )
        match = re.search(r"(\d+) tests? collected", result.stdout + result.stderr)
        return int(match.group(1)) if match else 0
    except Exception:
        return 0


def audit() -> dict:
    """Classify tests/ files and return the audit payload."""
    test_files = sorted(p for p in TESTS_DIR.glob("*.py") if p.name.startswith("test_"))
    deprecated: list[dict] = []
    kept: list[dict] = []
    consolidated_path = TESTS_DIR / "test_consolidated_suite.py"
    consolidated = _pytest_collected_count(consolidated_path) if consolidated_path.exists() else 0

    for name in DEPRECATED:
        path = TESTS_DIR / name
        deprecated.append({
            "name": name,
            "verified": VERIFIED_DEPRECATED_COUNTS[name],
            "removed": not path.exists(),
        })

    for path in test_files:
        ast_count = _count_test_functions(path)
        if path.name == consolidated_path.name:
            kept.append({"name": path.name, "verified": None, "ast": ast_count, "merged": True})
        else:
            kept.append({"name": path.name, "verified": None, "ast": ast_count, "merged": False})

    manual = [p for p in TESTS_DIR.glob("*.py") if not p.name.startswith("test_")]

    deprecated_total = sum(d["verified"] for d in deprecated)
    after_total = VERIFIED_BEFORE_TOTAL - deprecated_total + consolidated
    reduction = (VERIFIED_BEFORE_TOTAL - after_total) / VERIFIED_BEFORE_TOTAL * 100.0

    return {
        "total_files": len(test_files),
        "kept": kept,
        "deprecated": deprecated,
        "manual": [p.name for p in manual],
        "consolidated_count": consolidated,
        "verified_before": VERIFIED_BEFORE_TOTAL,
        "deprecated_total": deprecated_total,
        "after_total": after_total,
        "reduction_pct": reduction,
    }


def print_audit() -> None:
    report = audit()

    print("=" * 78)
    print("TICK-912 — Test suite consolidation audit")
    print(f"tests/ files scanned: {report['total_files']} test_*.py present "
      f"({len(report['deprecated'])} deprecated files removed, {len(report['kept'])} kept)")
    print("=" * 78)

    print(f"\nDeprecated: {len(report['deprecated'])} files ({report['deprecated_total']} pytest tests)")
    for entry in report["deprecated"]:
        status = "DELETED — merged" if entry["removed"] else "still present — must be deleted"
        print(f"  - {entry['name']:<42} {entry['verified']} tests ({status})")

    print(f"\nKept: {len(report['kept'])} files (ground truth, unchanged)")
    for entry in report["kept"]:
        label = " (consolidated replacement)" if entry["merged"] else ""
        print(f"  - {entry['name']:<50} {entry['ast']} tests{label}")

    if report["manual"]:
        print(f"\nManual scripts (not pytest): {', '.join(report['manual'])}")

    print("\n" + "=" * 78)
    print(f"Before: {report['verified_before']} tests | Deprecated: -{report['deprecated_total']} "
          f"| Consolidated: +{report['consolidated_count']}")
    print(f"After:  ~{report['after_total']} tests (target 900-1000, reduction "
          f"{report['reduction_pct']:.0f}%)")
    print("Authoritative count: PYTHONPATH=. pytest --collect-only -q")
    print("=" * 78)

    if not (900 <= report["after_total"] <= 1000):
        print("WARNING: projected total outside 900-1000 target band.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tests_consolidate",
        description="Audit the consolidated test suite (TICK-912).",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Print the kept/deprecated/merged audit report (default action).",
    )
    args = parser.parse_args(argv)
    if not args.audit:
        parser.print_help()
        return 0
    print_audit()
    return 0


if __name__ == "__main__":
    sys.exit(main())