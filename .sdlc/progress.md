
## TICK-001 handoff (2026-08-22) — canonical paths + version source [agent: TICK-001]

Status: COMPLETE, committed, NOT yet pushed (no GitHub credentials in sandbox).

Recovery anchors (tags survive branch resets/overrides):
- tag `tick-001/clean`  = 013be78 single-ticket commit directly on origin/develop (ffaae80). PUSH THIS.
- tag `tick-001/shared-head` = fe10db4 same patch on shared-checkout HEAD (carries TICK-002 fd4fc5d + TICK-005 b9cec46 as ancestors).

Push command once credentials exist:
  git push -u origin tick-001/clean:refs/heads/feat/TICK-001-canonical-paths-version
PR: base develop <- feat/TICK-001-canonical-paths-version. Patch-id of the
9-ticket-files diff is identical between both tags (verified).

If any agent overwrites/reverts these files, restore exactly:
  git checkout tick-001/clean -- dataforge/core/paths.py dataforge/__init__.py dataforge/core/__init__.py tests/test_paths_contract.py CHANGELOG.md README.md docs/ARCHITECTURE.md docs/DEVELOPMENT_GUIDE.md docs/TECHNICAL_SOURCE_OF_TRUTH.md
or cherry-pick: git cherry-pick tick-001/clean

Files owned by TICK-001 (do not edit in other tickets):
  dataforge/core/paths.py [NEW], dataforge/__init__.py,
  dataforge/core/__init__.py, tests/test_paths_contract.py [NEW]
Docs synced per CONTRIBUTING §8: ARCHITECTURE.md, TECHNICAL_SOURCE_OF_TRUTH.md,
DEVELOPMENT_GUIDE.md (301→314), README.md (301→314), CHANGELOG.md.
Verification: PYTHONPATH=. pytest tests/test_paths_contract.py -q => 13 passed;
ruff clean; full suite green except 2 pre-existing NTFS world-writable plugin
failures (plugin_loader.py:83 S_IWOTH guard; reproduce on pure develop).
