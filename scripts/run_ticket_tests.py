#!/usr/bin/env python3
"""
Fast ticket-specific test runner — avoids running the full 1200+ test suite.

Usage:
  python scripts/run_ticket_tests.py TICK-921
  python scripts/run_ticket_tests.py --ticket TICK-921 --no-cov
  python scripts/run_ticket_tests.py --file tests/test_dead_code_prune.py
  python scripts/run_ticket_tests.py --ticket TICK-921 --with-cov

Why this exists:
  Full suite `pytest -q --cov=dataforge` takes ~260s and 59% coverage is
  not needed per-ticket. Agents should validate only the files they touched.

  This runner:
  - Reads the ticket's `test_target` / `validation_command` from
    docs/prompts/tickets/TICK-xxx.prompt.md (or docs/resolved/res_TICK-xxx)
  - Falls back to exclusive_write_files -> test mapping
  - Runs ONLY those tests with QT_QPA_PLATFORM=offscreen and --no-cov by default
  - Prints timing and exit code

Examples:
  # Exactly what the ticket says (fast):
  python scripts/run_ticket_tests.py TICK-921
  # -> QT_QPA_PLATFORM=offscreen pytest tests/test_dead_code_prune.py -q --no-cov

  # Full suite (slow, only for final verification):
  python scripts/run_ticket_tests.py --full
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TICKETS_DIR = REPO_ROOT / "docs" / "prompts" / "tickets"
RESOLVED_DIR = REPO_ROOT / "docs" / "resolved"


def find_ticket_file(ticket_id: str) -> pathlib.Path | None:
    # Normalize: TICK-921 or 921
    if not ticket_id.startswith("TICK-"):
        ticket_id = f"TICK-{ticket_id}"
    for d in (TICKETS_DIR, RESOLVED_DIR):
        for p in d.glob(f"{ticket_id}.prompt.md"):
            return p
        for p in d.glob(f"res_{ticket_id}.prompt.md"):
            return p
        for p in d.glob(f"*{ticket_id}*.prompt.md"):
            return p
    return None


def parse_test_target(ticket_path: pathlib.Path) -> list[str]:
    text = ticket_path.read_text(encoding="utf-8", errors="ignore")
    targets: list[str] = []
    # 1) Work Package YAML test_target: "tests/test_xxx.py [NEW FILE]"
    for m in re.finditer(r"test_target:\s*\"?([^\"\n]+)\"?", text):
        raw = m.group(1).strip()
        for part in re.split(r"[,\s]+", raw):
            part = part.strip().strip('"').strip("'")
            part = re.sub(r"\[.*?\]", "", part).strip()
            if part.endswith(".py"):
                if not part.startswith("tests/") and part.startswith("test_"):
                    part = f"tests/{part}"
                if part.startswith("tests/") and part not in targets:
                    targets.append(part)
    # 2) Validation: `python -m pytest tests/... -q`  (Validation field in Metadata table)
    for m in re.finditer(r"Validation\s*\|\s*`([^`]+)`", text):
        cmd = m.group(1)
        for token in cmd.split():
            if token.startswith("tests/") and ".py" in token:
                token = token.split(":")[0].split()[0].strip("`")
                # token may be tests/test_xxx.py -q -> clean
                token = re.sub(r"[^a-zA-Z0-9_/.-]", "", token.split(".py")[0] + ".py") if ".py" in token else token
                # simpler: extract tests/test_*.py via regex
                for found in re.findall(r"tests/test_[a-zA-Z0-9_]+\.py", cmd):
                    if found not in targets:
                        targets.append(found)
    # 3) validation_command: "python -m pytest tests/... -q"
    for m in re.finditer(r"validation_command:\s*\"([^\"]+)\"", text):
        cmd = m.group(1)
        for found in re.findall(r"tests/test_[a-zA-Z0-9_]+\.py", cmd):
            if found not in targets:
                targets.append(found)
    # 4) Files to create / Files to modify patterns like `tests/test_*.py`
    for m in re.finditer(r"Files to (?:create|modify).*?\|\s*`([^`]+)`", text, re.DOTALL):
        block = m.group(0)
        for found in re.findall(r"tests/test_[a-zA-Z0-9_]+\.py", block):
            if found not in targets:
                targets.append(found)
    # 5) Generic fallback: any tests/test_*.py mentioned
    for found in re.findall(r"tests/test_[a-zA-Z0-9_]+\.py", text):
        if found not in targets:
            # Only add if near Validation or Test file sections to avoid noise
            targets.append(found)
            if len(targets) > 5:
                break
    # Deduplicate, keep order
    seen = set()
    uniq = []
    for t in targets:
        if t not in seen:
            seen.add(t)
            # Normalize
            t = t.strip()
            if t.endswith(".py") and t.startswith("tests/"):
                uniq.append(t)
    # If still empty, try to infer from exclusive_write_files -> test file via ticket id
    # e.g. TICK-921 -> tests/test_metadata_capabilities.py is hinted in Validation
    if not uniq:
        # Look for Validation line again more broadly
        for line in text.splitlines():
            if "pytest" in line and "tests/test_" in line:
                for found in re.findall(r"tests/test_[a-zA-Z0-9_]+\.py", line):
                    if found not in uniq:
                        uniq.append(found)
    return uniq


def run_pytest(test_files: list[str], with_cov: bool = False, extra_args: list[str] | None = None) -> int:
    import shutil

    env = dict(**__import__("os").environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = f"{REPO_ROOT}:{env.get('PYTHONPATH','')}".strip(":")
    # Prefer system pytest (often in PATH) over venv python -m pytest which may not have pytest
    pytest_bin = shutil.which("pytest") or shutil.which("pytest3")
    if pytest_bin:
        cmd = [pytest_bin, "-q"]
    else:
        cmd = [sys.executable, "-m", "pytest", "-q"]
    # Coverage is opt-in (slow). Default is no coverage for speed.
    # CI uses --cov explicitly; agents should NOT use it per-ticket.
    if with_cov:
        cmd.extend(["--cov=dataforge", "--cov-report=term-missing"])
    else:
        # Ensure no coverage even if pyproject addopts enables it (it doesn't by default)
        # Use -p no:cov to disable plugin if installed, but don't require --no-cov flag
        # (which may not exist if pytest-cov not installed)
        cmd.extend(["-o", "addopts=", "-p", "no:cov"])
    if extra_args:
        cmd.extend(extra_args)
    cmd.extend(test_files)
    print(f"$ {' '.join(cmd)}  (QT_QPA_PLATFORM=offscreen PYTHONPATH={REPO_ROOT})")
    start = time.monotonic()
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    elapsed = time.monotonic() - start
    print(f"[{elapsed:.1f}s] exit={result.returncode}  {' '.join(test_files) if test_files else '(no files)'}  (use --with-cov for coverage, --full for all)")
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast ticket test runner")
    parser.add_argument("ticket", nargs="?", help="TICK id e.g. TICK-921 or 921")
    parser.add_argument("--ticket", dest="ticket_opt", help="TICK id")
    parser.add_argument("--file", dest="file_opt", help="Test file e.g. tests/test_dead_code_prune.py")
    parser.add_argument("--with-cov", action="store_true", help="Enable coverage (slow)")
    parser.add_argument("--no-cov", action="store_true", help="Disable coverage (default fast)")
    parser.add_argument("--full", action="store_true", help="Run full suite (slow, 260s)")
    parser.add_argument("--collect-only", action="store_true", help="Only collect, don't run")
    parser.add_argument("--extra", nargs=argparse.REMAINDER, help="Extra pytest args after --")
    args = parser.parse_args()

    ticket_id = args.ticket or args.ticket_opt

    if args.full:
        # Full suite but without coverage for speed unless requested
        test_files: list[str] = []
        with_cov = args.with_cov
        extra = []
        if args.collect_only:
            extra.append("--collect-only")
        if args.extra:
            extra.extend(args.extra)
        return run_pytest(test_files, with_cov=with_cov, extra_args=extra)

    test_files: list[str] = []
    if args.file_opt:
        test_files = [args.file_opt]
    elif ticket_id:
        ticket_path = find_ticket_file(ticket_id)
        if not ticket_path:
            print(f"Ticket {ticket_id} not found in {TICKETS_DIR} or {RESOLVED_DIR}", file=sys.stderr)
            print(f"Try: ls {TICKETS_DIR}/TICK-*.prompt.md", file=sys.stderr)
            return 2
        print(f"Ticket: {ticket_path}")
        test_files = parse_test_target(ticket_path)
        if not test_files:
            # Fallback: look for exclusive_write_files -> map to test file via ticket id
            # e.g. TICK-921 -> tests/test_dead_code_prune.py is not obvious, so just warn
            print(f"No test_target found in {ticket_path}, running nothing", file=sys.stderr)
            print("Check the ticket's Work Package YAML test_target field", file=sys.stderr)
            return 2
        print(f"Targets: {test_files}")
        # Filter to existing files for helpful message, but still try to run (pytest will error if missing)
        existing = [f for f in test_files if (REPO_ROOT / f).exists()]
        missing = [f for f in test_files if not (REPO_ROOT / f).exists()]
        if missing:
            print(f"Note: {missing} do not exist yet (NEW FILE) — create them first", file=sys.stderr)
        # Only run existing files by default
        if existing:
            test_files = existing
    else:
        parser.print_help()
        print("\nExamples:")
        print("  python scripts/run_ticket_tests.py TICK-921")
        print("  python scripts/run_ticket_tests.py --file tests/test_dead_code_prune.py")
        print("  python scripts/run_ticket_tests.py --full --no-cov  # fast full without cov")
        return 2

    with_cov = args.with_cov
    if args.no_cov:
        with_cov = False
    # Default fast = no cov
    if not args.with_cov and not args.no_cov:
        with_cov = False

    extra = []
    if args.collect_only:
        extra.append("--collect-only")
    if args.extra:
        # argparse REMAINDER includes '--' itself
        extra.extend([a for a in args.extra if a != "--"])

    return run_pytest(test_files, with_cov=with_cov, extra_args=extra)


if __name__ == "__main__":
    raise SystemExit(main())
