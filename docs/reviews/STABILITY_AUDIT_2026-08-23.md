# DataForge Functionality Recovery Audit

Date: 2026-08-23 (refined 2026-08-23 12:30 UTC — verified against source)
Repository: `develop` at `fc24e83`
Scope: GUI, core operations, modules, job engine, API/transports, CLI,
packaging, tests, and external-tool integration.

This is an audit and recovery specification. No production code was changed as
part of this document. Findings marked **reproduced** were observed in the
current environment or test run. Findings marked **source-confirmed** are
deterministic from the implementation. Findings marked **coverage gap** need a
runtime or integration test before release.

## Executive Verdict

The application is not currently releasable as a general-purpose file and
forensics tool. The reported crashes have a confirmed Qt-threading cause, but
fixing that alone will not restore all functionality. Several actions can also
silently report success, lose failure records, mutate files after cancellation,
bypass evidence-mode protection, or fail because package/service contracts do
not match their callers.

The recovery must be staged:

1. Make the GUI and job lifecycle safe before exercising destructive actions.
2. Make every operation return one explicit result contract with accurate
   success, failure, cancellation, and output-file state.
3. Make preview and execute operate on the same immutable input snapshot.
4. Make destructive operations atomic, confined to intended paths, centrally
   protected by evidence mode, and auditable.
5. Verify every visible action on a real temporary fixture, not only through
   static tests or mocked callbacks.

## Current Evidence

The following commands were run from the repository root with the system
Python 3.14.7 because `.venv/bin/python` does not contain the development tools.

| Check | Current result | Meaning |
|---|---:|---|
| `python -m pytest --collect-only -q -p no:cacheprovider` | 1185 collected | The suite is broad, but collection alone does not prove GUI/runtime behavior. |
| `QT_QPA_PLATFORM=offscreen python -m pytest -q -p no:cacheprovider --maxfail=5` | 854 passed, 5 failed, 4 skipped before stop | The run stopped after 5 failures at 177 seconds; it was not green. |
| `python -m ruff check dataforge tests` | Passed | Formatting/lint rules do not catch the runtime contracts below. |
| `python -m mypy dataforge` | 214 errors | Type checking is advisory and currently cannot protect operation boundaries. |
| `.venv/bin/python -m pytest` | `No module named pytest` | The documented project venv is incomplete for verification. |
| `exiftool` executable | Missing | The Python `PyExifTool` package is not the native ExifTool binary required by metadata code. |

Current test failures observed:

- `tests/test_comprehensive.py::TestPluginLoader::test_loader_returns_list`
  because the plugin directory is mode `0777` on the current filesystem and is
  correctly rejected by `plugin_loader.py:482-506`.
- `tests/test_plugin_loader_isolation.py::test_inline_returns_same_as_before`
  for the same permission condition.
- `tests/test_contract_regressions.py::test_reduce_motion_zeroes_animation_duration`
  and `test_toggle_sidebar_group_animates_container_height` because fixtures
  construct `DataForgeApp` without `QMainWindow.__init__()` while
  `app.py:449-453` now uses Qt-backed attribute access.
- `tests/test_contract_regressions.py::test_switch_view_fades_in_new_view`
  because the test expects another animation while the app already has one
  from startup.

These failures must be fixed or explicitly reclassified before a green build
can be trusted. The plugin tests must run on a native filesystem with secure
permissions, or use a controlled fixture; weakening the production permission
check is not an acceptable fix.

## P0: Process Stability And Job Lifecycle

### P0.1 Progress updates mutate Qt widgets from a worker

**Status: source-confirmed and runtime-probed.**

`DataForgeApp.post_progress()` and `post_status()` only recognize the obsolete
`BackgroundWorker` class:

- `dataforge/ui/app.py:884-896`
- active worker class: `dataforge/ui/job_manager.py:66-78`

`ManagedWorker.run()` invokes the original callback inline:

- `dataforge/ui/job_manager.py:128-140`

For GUI workflows, that callback is `app.post_progress`, which falls through
to `update_progress()` and updates `QProgressBar` and `QLabel` from the worker
thread:

- `dataforge/ui/app.py:854-865`
- `dataforge/ui/app.py:393-394`

The same progress event is then emitted through `progress_signal`, producing a
second UI update. A runtime probe observed two `update_progress()` calls for a
single worker event, one from the worker and one from the GUI path.

This explains the reported `QWidget::repaint: Recursive repaint detected` and
is the most likely direct cause of the SIGSEGV. It affects every
`run_workflow(..., progress=True)` action, including PDF operations, metadata,
entropy, scans, cleanup, duplicates, recovery, and image conversion.

**Required fix:** pass a worker-only event sink that emits immutable progress
events; deliver them through a real GUI-affine `QObject` slot; never invoke an
application method that touches widgets inline from a worker. Coalesce noisy
updates to a bounded rate and discard updates after terminal/cancelled state.

### P0.2 Completion delivery lacks an explicit affinity contract

The first version of this audit stated that every plain Python callback
connection necessarily runs on the worker. That is too broad for this PyQt5
path. The current PyQt proxy behavior generally delivered these connections on
the GUI thread when they were made by the GUI thread, and a runtime probe
observed `_internal_on_result`, `_internal_on_error`, `_on_progress`, and
`on_success` on the GUI thread.

However, the implementation relies on that implicit behavior:

- `dataforge/ui/job_manager.py:506-522` (actual block extends to 522 including `finished_signal`; `506-520` covers the three callback connections)

It does not provide a durable contract if connection context, object lifetime,
or callback registration changes. Completion callbacks open dialogs, rebuild
trees, and submit follow-up jobs. They must be delivered by explicit
GUI-affine `@pyqtSlot` methods or `post_to_main()` dispatch, with thread-affinity
assertions in tests. Do not describe the current behavior as guaranteed merely
because it happens under the current PyQt version.

### P0.3 Managed workers are deleted before native thread termination

`ManagedWorker` emits its custom `finished_signal` in `run()` before the QThread
has returned:

- `dataforge/ui/job_manager.py:284-285`

The connected cleanup removes the worker and calls `deleteLater()` immediately:

- `dataforge/ui/job_manager.py:522`
- `dataforge/ui/job_manager.py:654-660`

A delayed-return probe reproduced `QThread: Destroyed while thread is still
running`. Cleanup must be connected to the native `QThread.finished` signal,
not a signal emitted from inside `run()`.

`JobManager.shutdown()` only shuts down the registry executor and does not wait
for `ManagedWorker` threads:

- `dataforge/ui/job_manager.py:674-677`

`DataForgeApp` has no reliable `closeEvent()` shutdown barrier. Closing the GUI
while a job is active can leave native threads alive during Qt teardown.

**Required fix:** stop accepting work, request cancellation, wait for every
active worker/executor, then destroy the manager. Add a subprocess test that
fails on `QThread: Destroyed while thread is still running`, SIGABRT, SIGSEGV,
or recursive repaint warnings.

### P0.4 JobManager does not enforce `max_workers`

`JobManager` creates `JobQueue(max_workers=...)` but submits with
`execute=False`, then immediately starts one QThread per job:

- `dataforge/ui/job_manager.py:315-319`
- `dataforge/ui/job_manager.py:400-428`
- `dataforge/ui/job_manager.py:524-528`

The configured queue depth is therefore a registry count, not an execution
bound. A burst can start an unbounded number of QThreads, while individual
operations can create additional pools of up to 32 threads. This creates
oversubscription, memory pressure, and unstable cancellation behavior.

**Required fix:** use one bounded execution substrate. Preferred: make
`JobQueue` the actual executor and bridge its future completion to the GUI.
Do not combine an unused executor with one QThread per job.

### P0.5 Cancellation races can execute work after cancellation

`JobQueue.cancel()` marks a queued job cancelled, but `ManagedWorker.run()` does
not return when it starts with an already-cancelled job:

- `dataforge/engine/jobs.py:436-450`
- `dataforge/ui/job_manager.py:102-120`
- target invocation: `dataforge/ui/job_manager.py:142`

A non-cooperative target can therefore run and mutate files after cancellation.
File primitives also do not accept or check cancellation:

- `dataforge/core/operations/files.py:126-233`

Cancellation of parallel file actions cancels futures but exits a
`ThreadPoolExecutor` context that waits for running mutations:

- `dataforge/core/services/file_actions.py:308-355`

The UI can report cancellation before all in-flight mutations are accounted
for. Renamer rollback only sees recorded successes and can leave a partial
rename:

- `dataforge/modules/renamer.py:90-106`

**Required fix:** define cancellation as cooperative and precise: queued jobs
must never invoke their target; running operations must check between units;
terminal delivery waits until all in-flight mutations are recorded; the result
must state `cancelled`, `completed`, and `failed` counts.

### P0.6 Parallel file-action exceptions are dropped

In `_run_batch_parallel()`, a future is removed before its index is looked up:

- `dataforge/core/services/file_actions.py:315-342`

The later `futures.get(fut, -1)` cannot find the removed future. Exceptions can
therefore produce no failure record, and the final list filters the missing
record:

- `dataforge/core/services/file_actions.py:353-355`

Failed moves, copies, deletes, and renames can disappear from both the UI and
audit log.

**Required fix:** retain the future-to-index mapping until the exception is
recorded; always return one record per requested item, including failures and
cancelled items.

### P0.7 Evidence mode is bypassable

Evidence mode is enforced in `JobManager` by substring matching the submitted
target name:

- `dataforge/ui/job_manager.py:393-399,662-668`

Wrapped workers such as action pipelines, duplicate actions, metadata writes,
and PDF workers can call mutation code without a matching destructive keyword.
Metadata operations do not enforce evidence mode:

- `dataforge/ui/app.py:378-391`
- `dataforge/modules/metadata.py:222-329`

The file-action service checks a case context, but the UI mode does not
reliably establish that context:

- `dataforge/core/services/file_actions.py:147-154`
- `dataforge/core/case.py:67-88`

**Required fix:** enforce evidence mode at the mutation boundary, not by
target-name inspection. Every delete, move, rename, archive, metadata write,
strip, secure-delete, and pipeline mutation must receive a read-only policy or
case context and return a blocked result. Add direct and wrapped-operation
tests.

### P0.8 File-type profiling fails on larger directories

`FileEntry` exposes `filename`, not `name`:

- `dataforge/core/common.py:63-72`

`profile_directory_types()` accesses `entry.name`:

- `dataforge/modules/forensics.py:916-917`

The UI always enables progress for this action:

- `dataforge/ui/views/forensics_view.py:909-922`

This raises `AttributeError` once the path reaches the profiling branch. Add a
25-, 100-, and 1000-file functional test.

### P0.9 Unknown progress totals violate the API schema

The provider contract documents `-1` for an unknown total and emits it:
- `dataforge/core/provider.py:23-24` (doc) + `provider.py:145-146` (`LocalProvider.list_files` emits `-1`)

`JobEvent.total` rejects values below zero:

- `dataforge/api/schema.py:190-197`

The daemon emits `progress_callback(len(entries), -1, ...)`:

- `dataforge/engine/daemon.py:375-376`

`JobQueue._progress()` constructs the event without converting the sentinel:

- `dataforge/engine/jobs.py:184-200`

Long scans can therefore fail when progress is emitted. Standardize unknown
total on `None` or a schema-approved sentinel and test a scan over 100 files.

### P0.10 Job state has multiple unsynchronized owners

`ManagedWorker.run()` mutates `Job.status`, `results`, `error`, and `events`
directly:

- `dataforge/ui/job_manager.py:98-211`

The manager's signal handlers mutate the same job under `JobQueue._lock`:

- `dataforge/ui/job_manager.py:430-500`

The worker-side mutations do not use that lock. This can produce duplicate or
out-of-order status/result events and inconsistent `is_busy` observations.
Choose one state owner, serialize every transition, and deliver one terminal
event only after execution and cleanup are complete.

## P1: User-Visible Operation Failures

### P1.1 Common result contract is missing

The code mixes lists, strings, ad-hoc dictionaries, `OperationResult`, and
`BatchActionOutcome`. Cancellation may be a string, an exception, or a nested
dictionary. A worker returning `{"success": False}` is still marked `DONE` by
the job layer:

- `dataforge/ui/job_manager.py:180-209`
- `dataforge/engine/jobs.py:296-329`

This lets the UI display job success when the operation failed.

Define one result shape for all user-facing operations:

```text
OperationReport {
  operation, requested, completed, failed, skipped,
  cancelled, success, errors[], outputs[], warnings[],
  dry_run, input_snapshot, output_snapshot
}
```

`JobStatus.DONE` should mean the operation completed without unhandled
exceptions; `report.success` should mean the requested action succeeded.
Handlers must render the report rather than infer success from job status.

### P1.2 Generic callback contract is inconsistent

`BaseView.restore_tree_selection()` calls `on_select(None)`:

- `dataforge/ui/views/base.py:478-483`

Callbacks such as `MediaView.on_img_select`, `SearchView.on_preview_select`,
and `ToolsView.on_cleaner_preview` accept no argument. These errors are then
swallowed by `DataForgeApp.run_background()`:

- callback definitions: `dataforge/ui/views/media.py:975-979`,
  `search.py:401-411`, `tools.py:797-806`
- swallowed callback exceptions: `dataforge/ui/app.py:993-1005`

Use one callback signature, do not swallow handler failures, and show a
diagnostic status while keeping the original operation result intact.

### P1.3 Preview and execute are not bound to one input snapshot

Several workflows re-read mutable UI state after preview confirmation:

- PDF merge paths/page order: `dataforge/ui/views/media.py:871-899`
- batch renamer rules: `dataforge/ui/views/tools.py:649-685,1040-1065`
- folder sync source/destination: `tools.py:687-730,1121-1193`
- action-builder steps: `dataforge/ui/views/action_builder.py:382-435`

The user can confirm one set of files or rules and execute another set. Create
an immutable preview object containing normalized paths, options, rules,
collision policy, and a fingerprint. Execution must reject a stale snapshot.

### P1.4 PDF Merge/Split/Compress are not reliable

References: `dataforge/core/media_ops.py` and
`dataforge/ui/views/media.py`.

| ID | Finding | Reference |
|---|---|---|
| M1 | Missing `pypdf` raises from merge rather than returning a report. | `media_ops.py:89-92` |
| M2 | Merge writes an empty/junk output if no input contributes pages. | `media_ops.py:198-205` |
| M3 | A file is counted as merged even when every page addition failed. | `media_ops.py:159-167` |
| M4 | Split records output paths before successful writes and retains failed paths. | `media_ops.py:265-296` |
| M5 | Split error dictionaries do not have the normal report shape. | `media_ops.py:224-260` |
| M6 | Compress `quality` only selects a fabricated dry-run ratio; it does not affect the real path. | `media_ops.py:305-325` |
| M7 | The writer-level `compress_content_streams` check is dead; pypdf compresses page content streams. | `media_ops.py:377-380` |
| M8 | Final replacement failure can still produce a success-shaped compression report. | `media_ops.py:398-410` |
| M9 | PDF conversion writes final outputs directly and can leave partial page sets. | `media_ops.py:514-619` |
| M10 | Selected PDF path expression has operator-precedence behavior that can discard a valid path. | `media.py:683-701` |
| M11 | Merge execute rereads tree paths instead of using previewed paths. | `media.py:871-899` |

Required behavior: validate every input, write to a unique same-directory
temporary output, fsync/close, atomically replace only after success, never
create an output with zero successful inputs, and report exact counts and
existing output paths. Compression must either implement quality semantics or
label the operation as lossless rewrite and remove the misleading ratio.

### P1.5 Image conversion has preview side effects and collision risk

`convert_image()` creates the destination directory before checking dry run:

- `dataforge/core/media_ops.py:742-778`

Same-format conversion can resolve output to the source and then replace it:

- `media_ops.py:742-765,843-869`

The image action step checks `context.should_cancel()` but does not forward
`cancel_token`, `progress_callback`, or per-file dry-run granularity to
`convert_image` (per-iteration check exists; forwarded token/progress do not):

- `dataforge/core/actions/media.py:14-34`

Batch outputs with the same basename can overwrite one another:

- `dataforge/ui/views/media.py:1003-1029`
- `dataforge/core/media_ops.py:742-764,843-869`

The UI exposes "Preserve EXIF" but the PNG branch does not preserve it:

- `media.py:265-267`
- `media_ops.py:787-810`

Preview must be side-effect-free. Same-file replacement must require explicit
overwrite confirmation. Output names must be collision-checked before work.

### P1.6 Metadata writes are incomplete and the error message is misleading

Without native ExifTool, `write_metadata()` dispatches image writes to
`_write_pillow()`:

- `dataforge/modules/metadata.py:222-261`

The Pillow fallback only attempts JPEG with optional `piexif`:

- `metadata.py:572-617`

PNG text chunks and PNG eXIf can be written with Pillow, but no `PngInfo` path
exists. The message "Pillow write not supported" describes an implementation
gap, not a general Pillow limitation.

`_has_exiftool()` is cached forever and invokes a hardcoded `exiftool` name:

- `metadata.py:46-61`

`PyExifTool` in `requirements.txt` is only a Python wrapper; it does not install
the native executable. PDF metadata has no fallback writer even though pypdf
can add metadata.

Required behavior:

- implement supported PNG text/eXIf writes or accurately mark them read-only;
- add an explicit capability report for each format and field type;
- use `shutil.which()` plus a configured executable path and a rescan path;
- keep writes atomic and preserve file permissions/timestamps where required;
- refresh displayed metadata after a successful strip/write;
- make selective removal honest: never fall back from GPS-only to strip-all;
- test with and without the native executable.

Metadata UI stale-state references:

- `dataforge/ui/views/metadata_view.py:651-666,760-784`

### P1.7 Search, duplicates, and file actions have destructive-action gaps

- Search can retain old `current_results` while a new search is running:
  `dataforge/ui/views/search.py:413-485`.
- Search accepts invalid paths and contradictory ranges without validation:
  `search.py:413-466`.
- Duplicate "Select Extras" does not verify content before destructive actions:
  `dataforge/ui/views/duplicates.py:396-437`.
- Duplicate tree path maps can remain stale across rebuilds:
  `duplicates.py:648-674`.
- Bulk actions advertise plural selection while `EnhancedTreeview` does not
  configure extended selection: `dataforge/ui/widgets.py:452-465`.
- Generic tree context menus can bypass view-specific preview/confirmation and
  can operate on report rows or device paths:
  `widgets.py:887-954`.
- Cache keys use path, size, mtime, and algorithm; replacement content with
  unchanged metadata can reuse a stale hash: `dataforge/core/cache.py:182-208`.
- Parallel file-action failures are lost as described in P0.6.
- Rename input must remain a basename. `rename_path()` currently joins an
  arbitrary `new_name`, allowing separators or `..` to escape the source
  directory: `dataforge/core/operations/files.py:205-233`.
- Archive operations use predictable `destination + ".tmp"` paths and can
  conflict or follow a pre-existing symlink:
  `dataforge/core/services/file_actions.py:794-867`.

Required behavior: clear stale state at operation start, use explicit path
resolvers per view, enable extended selection only where supported, verify
duplicate content before every destructive duplicate action, confine rename
names to validated basenames, use unique secure temp files, and retain one
outcome record per requested item.

### P1.8 Cleanup is partially disconnected from its controls

- "Include browser artifacts" is persisted but not passed to the junk scan:
  `dataforge/ui/views/system_cleanup.py:111-115,436-487`.
- Common `.tmp` and `.log` files are excluded by the default scanner, while
  cleanup claims to find them: `dataforge/core/config.py:97-102`,
  `dataforge/core/scanner.py:204-206`,
  `dataforge/modules/system_cleanup.py:338-347`.
- Junk scan error handler does not surface the worker error via the
  expected `show_workflow_error` path and leaves stale results visible:
  `dataforge/ui/views/system_cleanup.py:477-503` (connected via `run_workflow`
  kwargs at `477-487`, so positional order is not the bug — the handler
  `489-503` clears no stale state and does not delegate to the shared error
  display).
- Browser/junk categories can overlap and double-count savings:
  `system_cleanup.py:533-549` and module `system_cleanup.py:365-411`.
- Browser artifact scanning exists, but there is no corresponding browser
  cleanup action: `dataforge/ui/views/system_cleanup.py:755-805`.

Required behavior: each checkbox must change the worker request; scan results
must be deduplicated by canonical path; cleanup must preview exactly what will
be deleted; unsupported browser cleanup must be visibly unavailable.

### P1.9 Recovery actions have incorrect options and cancellation display

- PhotoRec ignores selected file-type checkboxes:
  `dataforge/ui/views/recovery_view.py:476-481,544-576`.
- CLI lowercases recovery types while the carving implementation expects keys
  such as `JPEG`: `dataforge/cli.py:400-402`,
  `dataforge/modules/recovery.py:387-390`.
- Restore and carving handlers can display completion after cancellation:
  `recovery_view.py:437-457,510-542`.
- Generic Trash rows can resolve the original file path rather than the trash
  object without an explicit path resolver:
  `recovery_view.py:174-187`, `dataforge/ui/widgets.py:1031-1068`.
- Cancellation can leave already committed carved files despite the intended
  no-partial-files behavior: `recovery.py:453-478,565-601`.
- Carving submits all windows and can copy up to 64 MiB per worker:
  `recovery.py:405-406,480-486,559-584`.

Required behavior: normalize type identifiers once, pass the same filter to
every recovery backend, never target Trash rows through a generic path guess,
report cancellation distinctly, and make output commit/rollback semantics
explicit.

### P1.10 Forensics contains correctness and evidence-boundary bugs

- Hash verification can use basename matching instead of the selected row's
  path: `dataforge/ui/views/forensics_view.py:2062-2091`.
- Timeline `atime` is populated with mtime because `FileEntry` has no atime:
  `forensics_view.py:1171-1178`,
  `dataforge/modules/forensics.py:1019-1035`.
- Directory integrity snapshot UI passes directories directly to a file hash
  routine instead of recursively enumerating them:
  `forensics_view.py:1733-1801`,
  `dataforge/modules/forensics.py:1192-1223`.
- UI snapshot and `IntegrityMonitor` implement incompatible integrity contracts:
  `forensics_view.py:1792-1795`,
  `dataforge/modules/integrity.py:210-225,371-399`.
- Forensic ingestion is directory-oriented, creates output before validation,
  writes manifests directly, and lacks consistent cancellation results:
  `dataforge/modules/forensics.py:588-722`.
- Artifact parser can resolve absolute home paths against the host instead of
  the supplied evidence root: `forensics.py:199-209`.
- `verify_file_state()` checks only the first configured hash and does not
  compare all recorded attributes: `forensics.py:1236-1262`.

Required behavior: define one evidence snapshot format, resolve every artifact
path under the evidence root, distinguish mounted directories from raw images,
use atomic output, verify the selected absolute path, and preserve atime/mtime/
ctime independently.

### P1.11 Action Builder hides step failures

Step exceptions are logged and execution continues:

- `dataforge/ui/views/action_builder.py:424-435`

The completion handler then reports "Pipeline Completed":

- `action_builder.py:440-455`

`DeleteStep` also clears `context.files` regardless of dry-run or deletion
result:

- `dataforge/core/actions/io.py:73-82`

The worker receives live mutable step objects from the view:

- `action_builder.py:382-435`

Required behavior: clone/serialize the pipeline before submission; stop or
continue only according to an explicit policy; report failed steps as failure;
never clear inputs merely because a step was attempted; make dry-run output
match execution output.

### P1.12 Folder Sync and renaming can diverge after preview

Folder Sync compares modification times rather than content and does not lock
or fingerprint source/destination between Analyze and Sync Now:

- `dataforge/ui/views/tools.py:687-730,1121-1193`

The renamer materializes all scan entries and can leave a producer thread when
the consumer abandons the generator:

- `dataforge/modules/renamer.py:18-75`

Required behavior: use a declared comparison policy, capture a preview
fingerprint, reject stale input, and close producer resources in all paths.

### P1.13 Optional dependency handling is inconsistent

The package comments treat GUI/media dependencies as optional, but imports can
fail before graceful feature messages are shown:

- `dataforge/ui/views/about.py:10` imports `psutil` unconditionally.
- `dataforge/core/actions/media.py:6` imports Pillow unconditionally.
- `dataforge/modules/cleaner.py:1-6` imports Pillow while the CLI imports the
  cleaner module at startup: `dataforge/cli.py:8-12`.

`pyproject.toml` omits packages present in `requirements.txt`, including
Pillow, PyQt5, pypdf, PyMuPDF, pandas, msgpack, and `platformdirs`:

- `pyproject.toml:9-24`
- `requirements.txt:6-26`
- IPC imports msgpack: `dataforge/api/transport/uds.py:24-25`,
  `named_pipe.py:26-29`.

Note: `pyproject.toml:29-31` documents this omission as intentional
("only back the desktop GUI ... Install from requirements.txt for full
GUI/media support"). It is still a problem because `pip install .` alone
leaves the CLI and several modules broken -- the fix is to make the intent
real via `optional-dependencies` and lazy imports, not to merely document
the gap.

Required behavior: define install extras such as `cli`, `gui`, `media`,
`forensics`, and `dev`; lazy-import optional features; make `pip install .`
and the documented full install both testable from clean environments.

## P1: Service, API, CLI, And Packaging Contracts

### P1.14 Linux service cannot start with its configured arguments

The source service passes `--dbus`:

- `dataforge/service/linux/dataforge.service:19-25`

The service parser accepts no `--dbus` option:

- `dataforge/service/__main__.py:102-149`

The packaged systemd unit also invokes a GUI bundle with `--engine` while
`run_ui.py` only starts the GUI:

- `packaging/systemd/dataforge.service:7-20`
- `run_ui.py:18-39`

Required behavior: choose one daemon entry point, make source and packaged
units use the same supported flags, and add an actual service startup test.

### P1.15 Daemon/API request fields are silently ignored

The schemas advertise fields that dispatchers do not apply:

- Search sort/reverse/limit: `dataforge/api/schema.py:65-83`,
  `dataforge/engine/daemon.py:399-417`.
- Duplicate algorithm/content verification:
  `schema.py:93-100`, `daemon.py:452-457`.
- Integrity algorithm: `daemon.py:546-564`.
- Scan provider: `schema.py:50-55`, `daemon.py:346-383`.

The API must either implement each field or remove it from the public schema;
silently ignoring a user request is not acceptable.

### P1.16 Job event subscription is only a snapshot

`JobQueue.subscribe()` returns `iter(list(job.events))`, not a live stream:

- `dataforge/engine/jobs.py:459-467`

UDS and named-pipe servers do not publish job events and have unreachable
terminal checks due to condition order:

- `dataforge/api/transport/uds.py:200-207,279-292`
- `dataforge/api/transport/named_pipe.py:252-258,344-370`

The client polls status and emits a synthetic terminal event:

- `dataforge/client/__init__.py:63-100`

Define whether subscriptions are snapshots or streams. For a stream, implement
bounded event queues, disconnect handling, terminal delivery, and backpressure.

### P1.17 HTTP gateway has no token enforcement

The module documentation says remote exposure requires a token, but the gateway
does not accept or validate one:

- `dataforge/api/transport/http_gateway.py:11-15,170-198,213-280`

Binding outside loopback can expose filesystem operations without
authentication. Refuse non-loopback binding without an explicit authenticated
configuration and test both cases.

### P1.18 CLI and transport discovery contracts are incomplete

Automatic HTTP discovery is documented but `_auto_discover_transport()` returns
`None` after checking only local UDS and named pipes:

- `dataforge/client/__init__.py:208-264`

The CLI recovery type normalization mismatch is documented in P1.9. CLI startup
also depends on Pillow through the cleaner import, despite the package metadata
claiming GUI-only dependencies are excluded.

### P1.19 Packaging is not build-verified

- macOS detection returns `macos` while build maps use `darwin`:
  `build_exe.py:25-46,65-72,119-125`.
- Release spec contains hardcoded `/mnt/pharos/...` paths:
  `buildspec/release/DataForge.spec:4-10`.
- Debug spec references the old ttkbootstrap/Tk stack (via
  `ttkbootstrap`/`PIL.ImageTk`, not literal `tkinter`):
  `buildspec/debug/DataForge-debug.spec:4-15`.
- WiX expects an executable the build script does not create:
  `packaging/wix/Product.wxs:23-29,62-68`.
- Linux packaging references an absent PNG asset:
  `packaging/nfpm.yaml:37-42`.
- Packaging tests are structural and do not build/install artifacts.

Required behavior: build on each supported platform, install into a clean
environment, start the installed GUI/daemon, and test the packaged service.

### P1.20 Core acquisition, provider, and shutdown contracts are incomplete

- `acquire_file()` cleanup closures capture a temporary path and then reset the
  captured variable, so closing a sudo-backed file can fail to unlink its
  temporary copy: `dataforge/core/acquire.py:233-249,294-307`.
- The Windows VSS branch only lists shadow copies and returns `None`; it does
  not acquire a usable file: `acquire.py:159-182`.
- `JobQueue._invoke_worker()` retries a target under multiple calling
  conventions after any `TypeError`: `dataforge/engine/jobs.py:223-263`.
  A target that mutates state and then raises an internal `TypeError` can run
  more than once. Inspect the signature once and invoke one convention.
- `JobQueue.shutdown()` only delegates to the executor and does not
  transition pending jobs to `CANCELLED`, nor clear completed future
  references: `dataforge/engine/jobs.py:469-470` (note: `375-423` is
  `submit()`, not `shutdown()`).
- `FileActionService` stores a provider but still uses local `os`/`shutil`
  operations, so alternate providers cannot perform file actions:
  `dataforge/core/services/file_actions.py:126-143`.

Required behavior: clean every temporary acquisition artifact, explicitly mark
unsupported VSS instead of pretending it works, invoke each target exactly
once, close futures and terminalize pending jobs, and route all provider-aware
operations through the selected provider.

## P2: Responsiveness, State, And Observability

These are not the first crash blockers, but they make the application appear
broken on real data:

- Dashboard scan has no cancellation/progress and invokes view-owned behavior
  from a worker: `dataforge/ui/views/dashboard.py:218-274`.
- Hash-folder and entropy-folder enumeration can block the GUI:
  `dataforge/ui/views/forensics_view.py:1984-2011,1074-1089`.
- Single hash verification, single entropy, hex dump, steganography, password
  extraction, and several exports run synchronously in the UI.
- Cache clear can run SQLite `VACUUM` on the GUI thread:
  `dataforge/ui/views/settings.py:538-566` triggers
  `dataforge/core/cache.py:269` (`VACUUM`) synchronously.
- Invalid metadata and cleanup paths can become successful empty operations:
  `metadata_view.py:352-403`, `system_cleanup.py:448-450`.
- Scanner converts missing/unreadable roots into empty successful results:
  `dataforge/core/scanner.py:408-417` (note: `332-352` is the `_log_scan_error`
  helper, not the conversion site).
- Forensic/search/report output writes are not consistently atomic:
  `dataforge/modules/forensics.py:691-715,767-774`,
  `dataforge/modules/search.py:219-243`,
  `dataforge/modules/reporting.py:20-46`.
- Startup management is read-only while documentation implies editing:
  `dataforge/ui/views/performance_view.py:251-285,551-571`.
- NVMe SMART base-device derivation is incorrect:
  `dataforge/modules/performance.py:418-423`.
- Automation names can collide after sanitization and malformed JSON is silently
  skipped: `dataforge/ui/views/automations.py:31-55,130-159,401-477`.

Move heavy work off the GUI, validate inputs before job submission, clear stale
results at operation start, use atomic report writers, and surface malformed
configuration instead of silently ignoring it.

## Complete User-Facing Functionality Matrix

The following matrix is the minimum recovery scope. A row is not complete until
its worker, preview, execute path, cancellation, error result, output state,
and GUI thread affinity are tested.

| Area | User-facing actions | Main recovery requirements |
|---|---|---|
| Dashboard | Refresh, comprehensive scan | cancellable scan, correct counts, no worker UI access, empty/error distinction |
| Search | filesystem/content search, sort/filter, export, move/copy/delete, rename, zip | validate filters, clear stale results, secure preview, complete action records, archive output accuracy |
| Duplicates | scan, verify, select extras, keep/delete/move, export | configurable hash, content verification for every destructive path, stale-map cleanup, plural selection |
| PDF media | add/reorder/expand, merge, split, compress, convert | immutable preview, exact reports, atomic outputs, real compression semantics, dependency messaging |
| Images | add, preview, convert, resize/rotate/quality/EXIF | no preview side effects, collision policy, same-file protection, metadata capability accuracy |
| Metadata | scan, inspect, write, strip, GPS-only strip, export | format capability matrix, native-tool detection, atomic write, refreshed display, cancellation |
| Cleanup | junk scan, browser scan, preview, clean | checkbox wiring, dedupe, path validation, secure destructive policy, cancellation |
| Recovery | Trash scan/restore, carve, PhotoRec | correct target path, type filters, output rollback policy, cancellation display, external-tool status |
| Forensics | ingestion, hashes, verification, artifacts, file types, entropy, timeline, hex, stego, integrity | evidence-root confinement, correct timestamps, bounded memory, one snapshot contract, no GUI blocking |
| Performance/hardware | overview, process list/kill, startup, disk health, hardware, storage | optional tools, correct device paths, nonblocking UI, explicit unsupported state |
| Tools | integrity, metadata cleaner, renamer, sync | immutable preview, step failure policy, atomic outputs, rollback, cancellation |
| Action Builder | filters, actions, preview, execute, automation serialization | cloned pipeline, per-step reports, evidence policy, stable serialization, no swallowed errors |
| Automations | save/load/duplicate/delete/run | collision-safe names, schema validation, visible malformed-file errors, snapshot before execution |
| CLI/API | scan, search, duplicates, hashes, integrity, transports | schema fields implemented, live events defined, clean install, authentication, terminal states |
| Packaging/services | GUI, CLI, Linux daemon, Windows service, macOS launcher | clean build/install/start tests and aligned entrypoint arguments |

## Recovery Architecture

### 1. One execution model

Select one bounded executor. The recommended model is:

- `JobQueue` owns execution and enforces `max_workers` and queue depth.
- Each job receives a cancellation token and immutable parameters.
- Worker code emits only serializable progress/result/error data.
- The GUI bridge owns callback registration and delivery.
- No worker receives a widget, view, `QPixmap`, `QImage`, `QPainter`, or tree.

If QThreads are retained instead, use a worker `QObject` moved to a QThread,
connect native `finished` for cleanup, retain strong references through
termination, and wait during application shutdown. Do not retain the current
custom-finished-before-return lifecycle.

### 2. Explicit GUI dispatch

Create a GUI-affine dispatcher with decorated slots for progress, success,
error, and terminal cleanup. Store user callbacks in a per-job record and invoke
them only from those slots. `post_to_main()` must use that dispatcher rather
than relying on receiverless lambda behavior or `QTimer.singleShot()` from a
thread without an event loop.

### 3. Immutable job and preview snapshots

Before submission, capture:

- normalized input paths and file identities;
- selected pages, filters, rules, options, and output paths;
- evidence/read-only policy;
- a generation ID and preview fingerprint.

Reject stale execute requests when source files, options, or destination policy
changed after preview.

### 4. Unified operation reports

Every operation must return the same serializable report fields. A report must
never claim an output exists unless it exists and passed validation. A cancelled
operation must state what completed before cancellation. An operation with any
failure must expose each failed input.

### 5. Mutation boundary and output safety

All mutations must pass through a central policy that checks evidence mode,
path confinement, collision policy, and cancellation. Write outputs to unique
same-directory temporary files, flush and close them, validate them, then use
atomic replacement. Clean temporary files in `finally` blocks.

### 6. Optional capability model

Capabilities must be detected lazily and exposed to the UI/API as structured
data:

```text
capability, available, executable_or_package, supported_formats, message
```

The UI must disable unsupported actions or show an actionable error before
starting a job. Python wrappers and native executables must be distinguished.

## Prioritized Implementation Plan

### Phase 0: Stop crashes and data corruption

1. Fix progress callback delivery and remove duplicate inline invocation.
2. Add explicit GUI-affine result/error/progress dispatch.
3. Fix worker cleanup to wait for native termination.
4. Add `DataForgeApp.closeEvent()` shutdown barrier.
5. Enforce actual worker limits.
6. Prevent cancelled queued jobs from invoking targets.
7. Remove the image worker tree access at `media.py:1105`.
8. Stop swallowing completion callback failures.

Exit gate: repeated GUI subprocess smoke tests with progress-heavy PDF,
metadata, entropy, scan, and image jobs produce no Qt warnings, aborts, or
segfaults; every callback thread assertion passes.

### Phase 1: Restore operation correctness and safety

1. Introduce the common operation report.
2. Repair parallel failure indexing and cancellation accounting.
3. Move evidence enforcement to mutation primitives.
4. Fix PDF media reports, path selection, preview snapshots, and atomic output.
5. Fix image dry-run side effects, same-file protection, and collisions.
6. Fix metadata capability/write/refresh behavior.
7. Repair search, duplicate, cleanup, recovery, forensics, renamer, sync, and
   Action Builder issues listed in P1.

Exit gate: every matrix row passes a real temporary-fixture workflow with
success, invalid input, missing dependency, partial failure, cancellation, and
repeat-run cases.

### Phase 2: Restore platform and integration functionality

1. Align `pyproject.toml`, requirements, optional extras, and CLI imports.
2. Fix daemon/service entrypoint arguments and test a real Linux service.
3. Implement or remove every advertised API field.
4. Define live event subscription behavior.
5. Enforce HTTP authentication and secure named-pipe configuration.
6. Build/install/test Linux, Windows, and macOS artifacts on native runners.

Exit gate: clean-install CLI, GUI, daemon, and packaged-service smoke tests
pass on each supported platform or the platform is explicitly unsupported.

### Phase 3: Responsiveness and maintainability

1. Move remaining heavy synchronous work off the GUI thread.
2. Make report/config writes atomic and errors visible.
3. Correct documentation and test counts from the current source of truth.
4. Make mypy actionable by fixing boundary types and reducing ignored errors.
5. Add runtime diagnostics for job IDs, generation IDs, thread IDs, and output
   paths without logging sensitive file content.

## Required Regression Tests

### GUI and jobs

- Progress, result, error, dialog, and tree callbacks run on the GUI thread.
- One UI progress update is delivered per logical event after coalescing.
- Five jobs with `max_workers=1` never run more than one target concurrently.
- A cancelled queued job has zero target invocations.
- A cancelled running job has exactly one terminal callback and no late progress.
- A completion callback that submits another job cannot hide the new job's UI.
- Shutdown waits for active workers and leaves no running QThread.
- A target that raises an internal `TypeError` is invoked exactly once.
- Shutdown terminalizes queued jobs and releases completed future references.
- Worker functions contain no Qt widget access.

### Operations

- Parallel move/copy/delete/rename failure produces one failure record per item.
- Cancellation reports completed, failed, and unstarted items accurately.
- Evidence mode blocks direct and wrapped mutations.
- PDF merge with zero valid inputs creates no output.
- PDF split lists only files that exist and validate.
- Compression reports actual output state and does not fabricate quality claims.
- Image preview creates no directory or file and detects output collisions.
- PNG metadata round-trips through the declared supported field model.
- Metadata strip/write refreshes every visible panel.
- Search, duplicate, cleanup, recovery, and Action Builder preview selections
  remain identical at execute time.
- File-type profiling passes at 25, 100, and 1000 files.
- Forensics stays confined to the selected evidence root and preserves atime.
- Sudo-backed acquisition removes temporary copies when handles close.
- Unsupported Windows VSS is reported as unsupported, not as an empty result.
- Provider-backed file actions use the selected provider rather than local-only
  filesystem calls.

### Packaging and integration

- Clean `pip install .` runs `fm --help` without GUI-only packages.
- Full extras install starts `run_ui.py` in offscreen mode and shuts down cleanly.
- Native ExifTool present/absent capability tests pass.
- Linux service starts with its installed unit and accepts a UDS request.
- API request fields change behavior or are rejected explicitly.
- HTTP non-loopback binding requires valid authentication.
- Native packaging builds produce artifacts whose referenced files exist.

## Definition Of Restored Functionality

The app can be considered functional only when all of the following are true:

- no reported SIGSEGV, recursive repaint, or QThread-destruction warning under
  stress and shutdown;
- no UI mutation occurs from worker code;
- every submitted job reaches one terminal state;
- every requested input has an outcome record;
- cancellation never silently permits unreported mutations;
- previews describe the exact operation that will execute;
- destructive operations are centrally blocked by evidence mode;
- output paths and success messages match files actually on disk;
- missing dependencies produce actionable, feature-specific messages;
- all user-facing matrix rows pass real workflow tests;
- clean installation and supported platform service/package smoke tests pass;
- documentation, schemas, CLI, daemon, and implementation describe the same
  behavior.
