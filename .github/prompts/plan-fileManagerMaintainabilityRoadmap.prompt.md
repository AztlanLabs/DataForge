## Plan: Maintainability and Capability Roadmap

Stabilize the codebase first, then centralize duplicated behavior behind a shared layer, and only then expand capabilities. That sequence matters because the current friction comes from broken contracts and parallel implementations, not from lack of features alone.

### Recommended direction

1. Fix the broken public contracts first.
2. Align plugin discovery and packaging so extensibility actually works.
3. Introduce a neutral shared service/operation layer.
4. Refactor CLI, GUI views, widgets, and action steps to call that layer.
5. Add new capabilities on the stable base.

### Why this is the right order

1. Right now some parts are simply inconsistent:
   - filemanager/cli.py
   - filemanager/modules/cleaner.py
   - tests/verify_scenarios.py
2. Some features are implemented multiple times:
   - move/copy/delete
   - rename
   - search/filter building
   - metadata cleaning
3. That duplication is what makes changes expensive and risky.
4. If you add more capabilities before removing that duplication, every new feature will spread across even more files.

### Phases

1. Stabilize current broken contracts.
2. Fix plugin discovery and plugin packaging.
3. Introduce a shared service/operation layer.
4. Refactor duplicate behavior to use the shared layer.
5. Add capabilities on the stable base.

### Step-by-step

1. Align the cleaner API between filemanager/cli.py, filemanager/modules/cleaner.py, and tests/verify_scenarios.py.
   Depends on: none
   Goal: make the CLI/test contract real again.
   Recommendation: split responsibilities internally if needed, but keep compatibility imports until the repo is stable.

2. Fix the SearchQuery data-model mismatch in filemanager/modules/search.py.
   Depends on: none
   Goal: use FileEntry.size and FileEntry.modified_at directly instead of entry.stat().
   This should happen immediately because it affects trust in search filtering.

3. Add smoke and integration tests for the actual public behavior.
   Depends on: steps 1-2
   Goal: lock down CLI imports, cleaner behavior, plugin loading, search filters, and a few end-to-end workflows.
   Without this, refactoring will be guesswork.

4. Fix plugin discovery so filemanager/ui/plugins/cleaner_plugin.py actually loads.
   Depends on: none
   Goal: align filemanager/ui/app.py, filemanager/ui/plugin_loader.py, build_exe.py, and FileManager.spec to the same plugin directory.
   Recommendation: standardize on filemanager/ui/plugins/cleaner_plugin.py and make loader/build paths match that reality.

5. Introduce a neutral shared layer for business operations.
   Depends on: steps 1-4
   Goal: create one place for:
   - search
   - move
   - copy
   - delete
   - rename
   - metadata clean
   - duplicate scan
   Recommendation: put it under a neutral area like core/services or core/operations, not inside the GUI action-step system.

6. Consolidate move/copy/delete through the shared layer.
   Depends on: step 5
   Update these paths:
   - filemanager/modules/organizer.py
   - filemanager/core/actions/io.py
   - filemanager/ui/widgets.py
   - filemanager/ui/views/search.py
   Outcome: one collision strategy, one logging model, one safe-delete policy.

7. Consolidate rename behavior through the shared layer.
   Depends on: step 5
   Update these paths:
   - filemanager/modules/renamer.py
   - filemanager/core/actions/modifications.py
   - filemanager/ui/views/search.py
   - filemanager/ui/views/tools.py
   Outcome: preserve both rename modes:
   - regex mode
   - placeholder/template mode

8. Consolidate search/filter construction.
   Depends on: steps 2 and 5
   Update these paths:
   - filemanager/modules/search.py
   - filemanager/core/actions/filters.py
   - filemanager/ui/views/search.py
   - filemanager/ui/views/tools.py
   - filemanager/ui/plugins/cleaner_plugin.py
   Outcome: one search-building path, instead of separate view-local and action-local logic.

9. Remove filesystem mutation from shared UI widgets.
   Depends on: steps 5-8
   Main target: filemanager/ui/widgets.py
   Outcome: widgets become presentation-only, and views/app services handle real operations.

10. Clean up duplicated or overridden GUI shell logic.
    Depends on: steps 4-9
    Main target: filemanager/ui/app.py
    Outcome: remove duplicate definitions like update_progress and _stop_busy, and make progress/cancel behavior easier to reason about.

11. Standardize shared helpers and config usage.
    Depends on: steps 5-10
    Main targets:
    - filemanager/modules/usage.py
    - filemanager/core/utils.py
    - filemanager/core/config.py
    Outcome: fewer hidden inconsistencies like duplicate format_size logic and duplicate config keys.

12. Update the documentation after refactor.
    Depends on: all previous steps
    Main target: TECHNICAL_SOURCE_OF_TRUTH.md
    Outcome: the documentation stays authoritative after the architecture changes.

13. Add new capabilities only after the shared layer is in place.
    Depends on: steps 5-12
    Best candidates:
    - more plugins
    - saved workflows
    - undo/rollback for batch actions
    - richer reports
    - remote/cloud providers
    - better media workflows

### Your requested next tasks

1. Align the cleaner API between filemanager/cli.py, filemanager/modules/cleaner.py, and tests/verify_scenarios.py.
2. Fix plugin discovery so filemanager/ui/plugins/cleaner_plugin.py can actually load.
3. Consolidate duplicate business logic across modules, views, widgets, and action steps.

### Priority order for actual execution

1. Cleaner API alignment
2. SearchQuery fix
3. Plugin discovery fix
4. Shared service/operation layer
5. Move/copy/delete consolidation
6. Rename consolidation
7. Search/filter consolidation
8. Widget cleanup
9. App shell cleanup
10. Capability expansion

### Files that matter most

- filemanager/cli.py
- filemanager/modules/cleaner.py
- tests/verify_scenarios.py
- filemanager/modules/search.py
- filemanager/modules/organizer.py
- filemanager/modules/renamer.py
- filemanager/core/actions/io.py
- filemanager/core/actions/modifications.py
- filemanager/core/actions/filters.py
- filemanager/ui/app.py
- filemanager/ui/plugin_loader.py
- filemanager/ui/widgets.py
- filemanager/ui/views/search.py
- filemanager/ui/views/tools.py
- filemanager/ui/views/action_builder.py
- filemanager/ui/plugins/cleaner_plugin.py
- build_exe.py
- FileManager.spec
- TECHNICAL_SOURCE_OF_TRUTH.md

### Verification

1. CLI commands import and run without missing-symbol failures.
2. Search size/date filters work correctly on controlled test files.
3. The cleaner plugin appears in the GUI navigation and loads successfully.
4. Equivalent workflows across CLI, Search view, and Action Builder behave the same where they are supposed to.
5. Regression coverage exists for collision handling, dry-run, safe-mode delete, cancellation, and progress callbacks.
6. Packaged builds include the correct plugin directory.

### Decisions

- Recommended plugin layout: keep GUI view plugins under filemanager/ui/plugins/cleaner_plugin.py and align loader/build paths to that.
- Recommended cleaner strategy: split responsibilities internally if needed, but preserve a compatibility surface first so the repo stops breaking.
- Recommended consolidation strategy: use a neutral shared layer instead of making the CLI depend directly on GUI action-step classes.
