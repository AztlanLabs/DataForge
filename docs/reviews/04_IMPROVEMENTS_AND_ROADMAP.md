# Improvements, Enhancements & Roadmap

**Date:** 2026-07-10
**Scope:** engineering practices, architecture, features to implement, and a phased plan.
**Companion docs:** `01_CODE_REVIEW_AND_BUGS.md`, `02_SECURITY_AND_FORENSIC_AUDIT.md`, `03_UIUX_REVIEW.md`.

This file is about *where the project should go next*, not individual bugs (those are in doc 01). Items are grouped by theme and tagged with rough effort (**S**=hours, **M**=days, **L**=week+) and impact.

---

## 1. Engineering foundation (do this before adding features)

### 1.1 Repository & process
- **Put the code under version control.** The working tree is **not a git repository** (confirmed) — there is history nowhere, no diffs, no blame, no CI. This is the single highest-leverage change. `git init`, commit, push, protect the main branch. *(Effort S, impact 🔴 huge.)*
- **Add a `.gitignore`** covering `build/`, `dist/`, `__pycache__/`, `.venv/`, `.pytest_cache/`, `~/.filemanager/`, and stray files (there's an empty `26.1.2` at root — delete it). *(S)*
- **Stand up CI** (GitHub Actions) that runs `pytest`, a linter, and a type check on every push. The `.github/` folder is full of agent/workflow markdown but there is **no actual test/lint CI workflow**. *(M)*
- **Unbreak the test suite first** — see doc 01 / H1. CI on a red suite is pointless. *(S)*

### 1.2 Quality tooling
- **Linting/formatting:** adopt `ruff` (fast, catches the bare-`except`, unused imports, `print`-vs-log issues automatically) + `black` for formatting. *(S to add, M to clean up.)*
- **Type checking:** the code already uses type hints in places (`file_actions.py`, `app.py`). Add `mypy`/`pyright` in non-strict mode and tighten over time. *(M)*
- **Pre-commit hooks** to run the above locally. *(S)*
- **Coverage reporting** so the (large) test suite's real coverage is visible; today the biggest test file doesn't even import. *(S)*

### 1.3 Dependency & packaging hygiene
- **Split requirements:** `requirements.txt` (runtime) vs `requirements-dev.txt` (pytest, pyinstaller, ruff, mypy). Reconcile with `setup.py`/move to `pyproject.toml` with extras (`.[gui]`, `.[dev]`). *(S)*
- **Pin/upper-bound security-relevant libs** (`Pillow`, `pypdf`, `pymupdf`, `PyQt5`) and add `pip-audit`/Dependabot for CVE alerts. *(S)*
- **Refresh the stale `debug` PyInstaller bundle** (README notes it still embeds the pre-migration Tkinter/ttkbootstrap code) or delete generated `build/`/`dist/` from the tree entirely and build in CI. *(S)*

---

## 2. Architecture improvements

### 2.1 Collapse the duplicated logic the TSOT already flags
- **Two filter engines:** `modules/search.py` (`SearchQuery`) vs `core/actions/filters.py`. Make the Action Builder filters thin wrappers over `SearchQuery` so semantics can't drift. *(M)*
- **Two metadata cleaners:** `modules/cleaner.py::MetadataCleaner` vs `modules/metadata.py::MetadataEngine`. Choose the exiftool-backed engine as the single source of truth; have the Action Builder step and plugin call it. *(M)*
- **Three rename orchestrations** (module regex / pipeline template / tools "parts") all delegate to `FileActionService` — good — but the *entry points* should share one options object to reduce surface. *(M)*
- **Adopt or delete `LocalProvider`.** It's dead infrastructure. If you want testable IO and a path to remote/cloud backends, route `scanner`/`operations` through the `FileProvider` seam; otherwise remove it to cut confusion. *(M)*

### 2.2 Make the seams enforce the security controls
Because mutation is centralised in `FileActionService` and discovery in `scanner`, the fixes in doc 02 can be enforced *once*:
- Add **root-confinement** and **symlink policy** in the scanner (fixes M3/S3 for every consumer).
- Add an **audit log** hook in `FileActionService` (every delete/move/rename appended to a tamper-evident log) — valuable for both trust and the forensic story. *(M)*
- Add a **byte-compare gate** before destructive dedup in one place. *(S)*

### 2.3 Concurrency & performance
- **Cache thread-safety** (doc 01/M5): lock or per-thread connections + WAL. *(S)*
- **Stream carving instead of buffering whole files** — `carve_files_from_image` reads up to a signature's `max_size` into RAM per hit (`recovery.py:334`); cap and stream. *(M)*
- **Progress for the scan phase** of duplicate/cleanup is indeterminate; a two-pass count or a rolling estimate would improve perceived performance. *(S)*

---

## 3. Testing gaps to close

Beyond unbreaking the suite (H1), add tests for the classes of bug found in this review — these are exactly the regressions most likely to recur:

- **Hash algorithm matrix** incl. `sha512`/unsupported → asserts no crash, correct error shape (guards M1).
- **Corrupt/empty integrity snapshot** → structured error, no exception (guards M2).
- **Symlink loop & out-of-tree symlink** in `scan_directory` → bounded, confined (guards M3/S3).
- **Malicious `.trashinfo`** with absolute/`..` `Path=` → restore is confined (guards S4).
- **Forensic HTML report with `<script>` in filename/username** → output is escaped (guards S2).
- **System cleanup never flags a user-supplied ordinary folder as blanket junk** (guards S7).
- **Config with out-of-range/unknown keys** → clamped/ignored (guards S10).
- Cross-platform stubs so `recovery`/`system_cleanup`/`performance` (which branch on `platform.system()`) are exercised for each OS via monkeypatch.

Add a **GUI smoke test** (pytest-qt) that constructs each view and mounts/unmounts it — cheap protection against import/rename breakage like H1.

---

## 4. Feature enhancements (user-visible)

Ordered by value-to-effort. See doc 03 for the UX framing.

### High value
- **Surface `fm devices` in the GUI** as a "Storage & Devices" view (capability exists, no UI). *(S)*
- **Task-first Dashboard launcher** — top-5 jobs as deep-linked buttons. *(M)*
- **Unified "review changes" checklist** for every batch/destructive op (scrollable, per-row opt-out, space-reclaimed total). *(M)*
- **Scheduled/rule-based cleanup & integrity checks** — "verify this folder weekly, alert on change"; leverages existing integrity + cleanup engines. *(L)*
- **Saved searches & saved automations** (persist a `SearchQuery`/pipeline and re-run). *(M)*

### Medium value
- **Duplicate finder: preview & smart-select** (thumbnails for images, keep-newest/keep-in-folder rules, protected paths). *(M)*
- **Search: content preview & regex tester** inline. *(M)*
- **Metadata: batch "remove location from all photos in folder"** one-click privacy action. *(S)*
- **Export/report polish:** hashed, timestamped, permission-restricted reports (ties to forensic soundness). *(S/M)*
- **Undo for the last batch operation** where safe (moves/renames are reversible from the log). *(M)*
- **CLI ↔ GUI parity map** so every capability is reachable from both. *(S doc, M code.)*

### Nice to have
- **Internationalisation** scaffolding (Qt `tr()`), since labels are being reworked anyway.
- **Plugin marketplace/manifest** with an explicit trust prompt (also closes S5).
- **Dashboard trends** (storage over time) using the persistent cache DB.

---

## 5. Observability & support

- **Structured logging** with rotation under `~/.filemanager/` (there's a logger; add rotation + a "copy diagnostics" button in About).
- **Opt-in crash reporting** (local file the user can attach), never automatic upload.
- **A `fm doctor` command** that checks optional external tools (exiftool, hashcat, john, photorec, magic) and prints install hints — the app already probes these ad hoc.

---

## 6. Phased plan

### Phase 0 — Stabilize (1 sprint) 🔴
`git init` + `.gitignore` + delete stray files · unbreak test suite (H1) · CI running pytest · fix the crash-class bugs (M1, M2, M3) · escape the forensic report (S2) · lock the cache (M5).

### Phase 1 — Trust & safety (1–2 sprints) 🟠
SHA-256 default + integrity algo stored (S1/M4) · dedup byte-compare (M6) · symlink confinement in scanner (S3) · trash-restore confinement (S4) · cleanup allow-listing (S7) · secret hygiene (S8) · config validation (S10) · add the regression tests in §3.

### Phase 2 — Coherence (2–3 sprints)
UX quick wins from doc 03 §8 (path picker, settings persistence, merge Automations, surface devices, dedupe dark-mode, rich help, renames) · consolidate the two filter engines and two metadata cleaners · design-token + icon layer.

### Phase 3 — Grow (ongoing)
Task-first dashboard · scheduled cleanup/integrity · saved searches/automations · undo · reporting polish · i18n · plugin trust model.

---

## 7. Definition of done for "healthy project"

- [ ] Under git with protected main and CI (pytest + ruff + mypy) green.
- [ ] `pytest` collects and passes **all** tests; coverage tracked.
- [ ] No crash on documented flags; hostile input handled (symlinks, corrupt snapshots, malicious trash/reports).
- [ ] SHA-256 is the default; integrity snapshots are self-describing; destructive dedup is collision-safe.
- [ ] One consistent settings-persistence model and one product name.
- [ ] Every CLI capability has a GUI path (or a documented reason it doesn't).
- [ ] README and `TECHNICAL_SOURCE_OF_TRUTH.md` match reality (see the updates shipped alongside this review).
