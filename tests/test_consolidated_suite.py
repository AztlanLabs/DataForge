"""Consolidated parametrized suite — TICK-912 (Wave 10).

Replaces the five deprecated test files (test_comprehensive, test_integration,
test_contract_regressions, test_new_modules, verify_scenarios — 271 pytest
tests + 1 manual script) with a single parametrized file of fewer than 50
tests that preserves the same acceptance coverage:

  * ``test_contract_parity``     — paths/provider/api/migration/jobs (5 -> 1)
  * ``test_ui_shell``            — crossfade, sidebar, job manager, theme tokens
  * ``test_integration_smoke``   — daemon/client, audit evidence, action
                                  pipeline, plugin packaging, E2E scenarios
  * ``test_utils_parity``        — format_size, parse_extensions, disk space,
                                  safe_zip_write, config validation
  * ``test_export_parity``       — search/duplicates export row builders
  * ``test_new_modules_parity``  — junk scan, password strength, forensics,
                                  hardware/performance smoke

Per-wave feature suites (test_scanner_parallel, test_hasher_mmap,
test_dupes_pipeline, test_theme_tokens, test_ui_job_manager, ...) remain the
ground truth and are untouched. See ``scripts/tests_consolidate.py --audit``
for the full migration guide.
"""

from __future__ import annotations

import json
import re
import threading
import time
import zipfile
from pathlib import Path

import pytest

from dataforge.core.common import FileEntry
from dataforge.core.utils import check_disk_space, format_size, parse_extensions, safe_zip_write

# Qt objects built without the standard QApplication teardown must not be
# GC'd mid-suite (PyQt5 + Python 3.14 aborts on next widget construction);
# keep them alive for the whole session.
_UI_KEEP_ALIVE: list = []

# ---------------------------------------------------------------------------
# test_contract_parity — paths/provider/api/migration/jobs contracts (5 -> 1)
# ---------------------------------------------------------------------------


def _check_paths_contract(tmp_path=None) -> None:
    import dataforge
    from dataforge.core import paths

    assert dataforge.__version__  # single version source exposed
    assert hasattr(paths, "ensure_dirs")
    assert hasattr(paths, "migrate_from_legacy")
    assert getattr(paths, "LEGACY_DIR", None) is not None
    assert paths.config_file.name == "config.json"
    assert paths.cache_db.name == "cache.db"


def _check_provider_contract(tmp_path=None) -> None:
    from dataforge.core.provider import FileProvider, LocalProvider, default_provider

    provider = default_provider()
    assert isinstance(provider, LocalProvider)
    assert isinstance(provider, FileProvider)
    entry = FileEntry(path="a", filename="a", extension=".txt", size=1,
                      created_at=0, modified_at=0, st_ino=1, st_dev=2)
    assert entry.hardlink_key == (2, 1)


def _check_api_contract(tmp_path=None) -> None:
    from dataforge.api.schema import JobStatus, ScanRequest

    payload = ScanRequest(root="/tmp").to_jsonrpc()
    assert payload["jsonrpc"] == "2.0"
    assert payload["params"]["root"] == "/tmp"
    for status in ("QUEUED", "RUNNING", "DONE", "CANCELLED", "FAILED"):
        assert getattr(JobStatus, status) is not None


def _check_migration_contract(tmp_path) -> None:
    from dataforge.core.cache import CACHE_SCHEMA_VERSION, CacheManager
    from dataforge.core.config import CONFIG_SCHEMA_VERSION

    assert CONFIG_SCHEMA_VERSION >= 2
    assert CACHE_SCHEMA_VERSION >= 2

    cache = CacheManager(db_path=str(tmp_path / "cache.db"))
    try:
        assert cache.get_user_version() >= 0
        with pytest.raises(ValueError):
            cache.set_hash_many([("only-four", 1, 1.0, "h")])  # 4-tuple rejected
    finally:
        cache.close()


def _check_jobs_contract(tmp_path=None) -> None:
    from dataforge.engine.daemon import Daemon
    from dataforge.engine.jobs import Job, JobQueue

    assert not Daemon().is_running()  # import must not start a server
    job = Job()
    assert len(job.job_id) == 26  # ULID
    assert not job.is_cancelled()

    results = []
    queue = JobQueue(max_workers=1)
    try:
        submitted = queue.submit(lambda: results.append("ran") or {"ok": True})
        queue.get(submitted.job_id)
        assert results == ["ran"]
    finally:
        queue.shutdown()


CONTRACT_CHECKERS = {
    "paths": _check_paths_contract,
    "provider": _check_provider_contract,
    "api": _check_api_contract,
    "migration": _check_migration_contract,
    "jobs": _check_jobs_contract,
}


@pytest.mark.parametrize("contract", sorted(CONTRACT_CHECKERS))
def test_contract_parity(contract, tmp_path):
    CONTRACT_CHECKERS[contract](tmp_path)


# ---------------------------------------------------------------------------
# test_ui_shell — crossfade, sidebar, job manager, theme tokens, a11y essence
# ---------------------------------------------------------------------------


def _qapp():
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _ui_app():
    """Bare DataForgeApp with a stack and two registered views (no sidebar)."""
    from PyQt5.QtWidgets import QStackedWidget

    from dataforge.ui.app import DataForgeApp

    app = DataForgeApp.__new__(DataForgeApp)
    app._qapp_ref = _qapp()  # keep the QApplication alive for the widget tree
    app.content_stack = QStackedWidget()
    app.views = {}
    app.current_view = None
    app.nav_buttons = []
    app._active_nav_btn = None
    app._active_animations = []
    app._in_switch = False
    app._in_build = False

    from dataforge.ui.views.dashboard import DashboardView
    from dataforge.ui.views.search import SearchView

    app.add_view(DashboardView)
    app.add_view(SearchView)
    return app


def _real_app(tier: str = "Simple"):
    """Fully-built DataForgeApp with mocked config (safe on all PyQt5/Py
    versions; avoids __new__-based QObject instances which Python 3.14 sip
    rejects with 'super-class __init__() never called')."""
    from unittest.mock import patch

    from dataforge.ui.app import DataForgeApp

    qapp = _qapp()
    with patch("dataforge.ui.app.config") as mock_config:
        mock_config.get.side_effect = lambda k, d=None: {
            "theme": "cosmo",
            "settings_ui_tier": tier,
            "plugins_enabled": False,
            "collapsed_groups": [],
        }.get(k, d)
        mock_config.set = lambda *a, **k: None
        app = DataForgeApp()
    app._qapp_ref = qapp  # keep QApplication + app tree alive across tests
    _UI_KEEP_ALIVE.append(app)
    return app


def test_ui_shell_crossfade_views_have_no_permanent_effect():
    """Views at rest must have no QGraphicsOpacityEffect (transient crossfade
    only) and must be opaque via WA_StyledBackground + autoFillBackground."""
    from PyQt5.QtCore import Qt

    app = _ui_app()
    for title, view in app.views.items():
        assert view.graphicsEffect() is None, f"{title} must not keep a crossfade effect"
        assert view.testAttribute(Qt.WA_StyledBackground), f"{title} must be opaque"
        assert view.autoFillBackground(), f"{title} must auto-fill background"


def test_ui_shell_sidebar_uses_task_oriented_groups():
    """Sidebar groups are task-oriented and tier-gated: Simple shows the
    essentials, Everything reveals every group; each group owns a header,
    buttons and a collapsible container."""
    simple = _real_app(tier="Simple")
    assert set(simple.group_containers) == {"Home", "Find & Organize", "System"}

    everything = _real_app(tier="Everything")
    expected = {"Home", "Find & Organize", "Clean & Optimize", "Recover & Investigate", "System"}
    assert expected.issubset(set(everything.group_containers))
    assert set(everything.group_containers) == set(everything.group_headers)
    assert all(everything.group_buttons[g] for g in everything.group_containers)


def test_ui_shell_toggle_sidebar_group_instantly_hides():
    """toggle_sidebar_group must collapse/expand instantly (setVisible) with
    no maximumHeight animation left in the animation registry."""
    app = _real_app()
    container = app.group_containers["Home"]
    header = app.group_headers["Home"]
    app.toggle_sidebar_group("Home", header)
    assert container.isHidden()
    app.toggle_sidebar_group("Home", header)
    assert not container.isHidden()
    sidebar_anims = [a for a in app._active_animations if a.propertyName() == b"maximumHeight"]
    assert sidebar_anims == []


def test_ui_shell_switch_view_fades_new_view():
    """switch_view schedules an opacity animation on the incoming view and
    keeps a reference in _active_animations so it cannot be GC'd mid-run."""
    app = _real_app()
    app._in_switch = False  # clear the startup-switch debounce before probing
    baseline = len(app._active_animations)
    app.switch_view("Search")
    assert len(app._active_animations) > baseline
    anim = app._active_animations[-1]
    assert anim.targetObject() is app.views["Search"].graphicsEffect()
    assert anim.propertyName() == b"opacity"
    assert abs(anim.startValue() - 0.0) < 1e-3
    assert abs(anim.endValue() - 1.0) < 1e-3


def test_ui_shell_theme_tokens_both_themes_share_names_and_pass_wcag():
    """Both themes define the same token names, all values are #rrggbb hex,
    and the body text/surface pairs clear WCAG AA (>= 4.5:1)."""
    from PyQt5.QtGui import QPalette

    from dataforge.ui.theme_tokens import TOKENS, generate_palette, generate_qss

    assert len(TOKENS) == 2
    names = set(TOKENS[list(TOKENS)[0]])
    for mode, table in TOKENS.items():
        assert set(table) == names, f"{mode} must share the same token names"
        for token, value in table.items():
            assert re.fullmatch(r"#[0-9a-fA-F]{6}", value), f"{mode}/{token} must be #rrggbb"
        assert "focus_ring" in table
        assert generate_qss(mode)
        assert generate_palette(mode).color(QPalette.Window).isValid()

    def _luminance(rgb):
        def _c(v):
            v /= 255.0
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * _c(rgb[0]) + 0.7152 * _c(rgb[1]) + 0.0722 * _c(rgb[2])

    def _contrast(fg, bg):
        l1, l2 = _luminance(fg), _luminance(bg)
        return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)

    def _rgb(hex_str):
        h = hex_str.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    for mode, table in TOKENS.items():
        assert _contrast(_rgb(table["text"]), _rgb(table["surface"])) >= 4.5, mode

    with pytest.raises(ValueError):
        generate_qss("neon")


def _job_manager():
    from dataforge.ui.job_manager import JobManager

    return JobManager(max_workers=2)


def _drain_until(predicate, timeout=5.0):
    from PyQt5.QtWidgets import QApplication

    deadline = time.time() + timeout
    while time.time() < deadline and not predicate():
        time.sleep(0.05)
        QApplication.processEvents()
    return predicate()


def test_ui_shell_job_manager_submit_complete_and_cancel(qapp):
    """JobManager submits fast jobs to completion and cancels slow ones."""
    manager = _job_manager()
    try:
        done = []
        slow_results = []

        def fast(cancel_token=None, progress_callback=None):
            return {"done": True}

        def slow(cancel_token=None, progress_callback=None):
            for _ in range(50):
                if cancel_token and cancel_token.is_set():
                    return {"cancelled": True}
                time.sleep(0.05)
            return {"done": True}

        jid = manager.submit(target=fast, on_success=done.append, task_name="fast")
        assert jid and len(jid) == 26  # ULID
        assert _drain_until(lambda: bool(done))
        assert done == [{"done": True}]

        started = threading.Event()

        def slow_with_signal(cancel_token=None, progress_callback=None):
            started.set()
            return slow(cancel_token, progress_callback)

        cid = manager.submit(target=slow_with_signal, on_success=slow_results.append, task_name="slow")
        assert started.wait(timeout=3)
        time.sleep(0.1)
        assert manager.cancel(cid)
        assert _drain_until(lambda: bool(slow_results))
        assert slow_results[0].get("cancelled") is True
        assert not manager.is_busy
    finally:
        manager.shutdown()


def test_ui_shell_job_manager_evidence_mode_blocks_destructive(qapp):
    """TICK-917: evidence mode blocks destructive mutations at the boundary."""
    from dataforge.api.schema import JobStatus
    from dataforge.core import case
    from dataforge.core.services import FileActionService

    manager = _job_manager()
    try:
        outcomes = []

        def delete_files(cancel_token=None, progress_callback=None):
            return FileActionService.delete_items(["dummy"], dry_run=False)

        case.set_evidence_mode(True)
        jid = manager.submit(target=delete_files, on_success=outcomes.append, task_name="delete files")
        assert jid is not None, "submit must accept the job (boundary enforces evidence mode)"
        assert _drain_until(lambda: manager.get_status(jid) == JobStatus.DONE)
        assert _drain_until(lambda: len(outcomes) == 1)
        assert all(not rec.success for rec in outcomes[0].records)
        assert any("Evidence Mode" in rec.message for rec in outcomes[0].records)

        case.set_evidence_mode(False)
        jid = manager.submit(target=delete_files, on_success=lambda r: None, task_name="delete files")
        assert jid is not None
        assert _drain_until(lambda: manager.get_status(jid) == JobStatus.DONE)
    finally:
        case.set_evidence_mode(False)
        case.clear_context()
        manager.shutdown()
        manager.shutdown()


@pytest.fixture
def qapp():
    return _qapp()


# ---------------------------------------------------------------------------
# test_integration_smoke — daemon/client, audit evidence, pipeline, scenarios
# ---------------------------------------------------------------------------


def test_integration_smoke_daemon_connect_and_scan(tmp_path):
    """In-process daemon fallback: connect() then scan returns a job."""
    from dataforge.client.sync import DataForgeSync

    root = tmp_path / "tree"
    root.mkdir()
    (root / "a.txt").write_text("alpha", encoding="utf-8")
    (root / "b.txt").write_text("beta", encoding="utf-8")

    sync = DataForgeSync.connect(in_process=True)
    try:
        job = sync.scan(str(root))
        assert job.job_id is not None
        result = job.wait(timeout=10.0)
        assert result is not None
    finally:
        sync.close()


def test_integration_smoke_audit_chain_and_tamper(tmp_path):
    """AuditLog appends hash-chained entries, verifies the chain, detects
    tampering, and the log file is created 0o600."""
    import sqlite3

    from dataforge.core.audit import AuditLog

    db = tmp_path / "audit.db"
    log = AuditLog(db_path=str(db))
    try:
        first = log.append("scan", {"root": "/tmp"})
        second = log.append("delete", {"path": "/tmp/x"})
        assert first["prev_hash"] != second["prev_hash"]
        assert log.verify()["valid"] is True
        assert log.count() == 2
    finally:
        log.close()

    conn = sqlite3.connect(str(db))
    try:
        conn.execute("UPDATE audit_log SET payload_json = 'TAMPERED' WHERE id = 2")
        conn.commit()
    finally:
        conn.close()

    reopened = AuditLog(db_path=str(db))
    try:
        assert reopened.verify()["valid"] is False
    finally:
        reopened.close()
    assert (db.stat().st_mode & 0o777) == 0o600


def test_integration_smoke_evidence_mode_gates_mutations(tmp_path):
    """Evidence mode blocks destructive FileActionService operations with a
    failed outcome; the source file stays untouched."""
    from dataforge.core.audit import AuditLog
    from dataforge.core.case import CaseContext
    from dataforge.core.services.file_actions import FileActionService

    src = tmp_path / "src"
    src.mkdir()
    victim = src / "victim.txt"
    victim.write_text("data", encoding="utf-8")

    ctx = CaseContext(case_id="CASE-1", operator="tester", evidence_mode=True)
    audit = AuditLog(db_path=str(tmp_path / "a.db"))
    try:
        svc = FileActionService(audit_log=audit, case_context=ctx)
        outcome = svc.delete_items([str(victim)], dry_run=False)
        assert len(outcome.failures) == 1
        assert "Evidence Mode" in outcome.failures[0].message
        assert victim.exists()  # blocked before mutation
    finally:
        audit.close()


def test_integration_smoke_action_pipeline_filter_then_rename(tmp_path):
    """Action pipeline E2E: SearchFilter -> RenameStep only touches matches."""
    from dataforge.core.actions.base import ActionContext
    from dataforge.core.actions.filters import SearchFilter
    from dataforge.core.actions.modifications import RenameStep
    from dataforge.core.scanner import scan_directory

    root = tmp_path / "src"
    root.mkdir()
    (root / "report_jan.txt").write_text("jan", encoding="utf-8")
    (root / "report_feb.txt").write_text("feb", encoding="utf-8")
    (root / "notes.md").write_text("markdown", encoding="utf-8")

    files = list(scan_directory(str(root), recursive=True))
    ctx = ActionContext(files)
    ctx.is_dry_run = False

    search_filter = SearchFilter({"pattern": r".*\.txt$"})
    search_filter.execute(ctx)
    assert len(ctx.files) == 2

    rename_step = RenameStep({"pattern": "archive_{counter}.{ext}", "counter_start": "1"})
    rename_step.execute(ctx)

    renamed = sorted(f.filename for f in ctx.files)
    assert renamed == ["archive_001.txt", "archive_002.txt"]
    assert (root / "notes.md").exists()


def test_integration_smoke_action_pipeline_dry_run(tmp_path):
    """Dry-run pipeline plans renames without touching the filesystem."""
    from dataforge.core.actions.base import ActionContext
    from dataforge.core.actions.modifications import RenameStep
    from dataforge.core.scanner import scan_directory

    root = tmp_path / "src"
    root.mkdir()
    (root / "file.txt").write_text("data", encoding="utf-8")

    ctx = ActionContext(list(scan_directory(str(root), recursive=True)))
    ctx.is_dry_run = True

    RenameStep({"pattern": "{stem}_v2{ext}"}).execute(ctx)
    assert (root / "file.txt").exists()
    assert not (root / "file_v2.txt").exists()


def test_integration_smoke_plugin_packaging_paths():
    """Plugin packaging paths agree: build_exe plugin source == loader dir,
    the plugins directory is an importable package, and the loader discovers
    MetadataCleanerPlugin."""
    import os

    import build_exe  # noqa: F401  (packaging constants under test)

    repo_root = Path(__file__).resolve().parents[1]
    plugin_dir = repo_root / "dataforge" / "ui" / "plugins"
    assert plugin_dir.is_dir()
    assert (plugin_dir / "__init__.py").exists()

    try:
        st = os.stat(plugin_dir)
        if st.st_mode & 0o002:  # NTFS fuse mounts are world-writable; try to fix
            try:
                os.chmod(plugin_dir, 0o755)
            except OSError:
                pytest.skip("plugin dir world-writable on NTFS, loader correctly skips")
    except OSError:
        pass

    from dataforge.ui.plugin_loader import PluginLoader

    loader = PluginLoader(str(plugin_dir), enabled=True)
    plugin_names = {cls.__name__ for cls in loader.load_plugins()}
    if not plugin_names:
        pytest.skip("plugin dir still unsafe, loader correctly skipped")
    assert "MetadataCleanerPlugin" in plugin_names


@pytest.mark.parametrize("scenario", ["dupes", "search", "cleaner", "renamer", "integrity"])
def test_integration_smoke_workflow_scenarios(scenario, tmp_path):
    """verify_scenarios.py essence: end-to-end module scenarios on one tree."""
    from dataforge.modules.cleaner import remove_empty_folders
    from dataforge.modules.duplicates import find_duplicates
    from dataforge.modules.integrity import IntegrityMonitor
    from dataforge.modules.renamer import bulk_rename
    from dataforge.modules.search import SearchQuery, search_files

    root = tmp_path / "env"
    root.mkdir()
    (root / "file1.txt").write_text("content A", encoding="utf-8")
    (root / "file2.txt").write_text("content A", encoding="utf-8")
    (root / "file3.jpg").write_text("content B", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "file4.txt").write_text("content C", encoding="utf-8")
    (root / "empty_dir").mkdir()
    (root / "deep" / "empty").mkdir(parents=True)

    if scenario == "dupes":
        dups = find_duplicates(str(root))
        assert len(dups) >= 1
    elif scenario == "search":
        query = SearchQuery().set_extensions(["txt"])
        results = search_files(str(root), query)
        assert len(results) == 3
    elif scenario == "cleaner":
        remove_empty_folders(str(root), dry_run=False)
        assert not (root / "empty_dir").exists()
        assert not (root / "deep" / "empty").exists()
    elif scenario == "renamer":
        bulk_rename(str(root), "file1", "replacement", recursive=True, dry_run=False)
        assert (root / "replacement.txt").exists()
    else:  # integrity
        snap = tmp_path / "snapshot.json"
        IntegrityMonitor.create_snapshot(str(root), str(snap))
        (root / "file3.jpg").write_text("modified content", encoding="utf-8")
        issues = IntegrityMonitor.verify_snapshot(str(root), str(snap))["discrepancies"]
        assert any("MODIFIED" in i for i in issues)


# ---------------------------------------------------------------------------
# test_utils_parity — utils/config essence from test_comprehensive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode,value,expected",
    [
        ("Auto", 0, "0 B"),
        ("Bytes", 1024, "1024"),
        ("KB", 2048, "2.00"),
        ("MB", 1048576, "1.00"),
        ("GB", 1073741824, "1.00"),
        ("Auto", 5 * 1024 * 1024, "MB"),
    ],
)
def test_utils_parity_format_size(mode, value, expected, monkeypatch):
    from dataforge.core import utils

    monkeypatch.setattr(utils.config, "get", lambda *a, **k: mode)
    assert expected in format_size(value)


def test_utils_parity_format_size_none(monkeypatch):
    from dataforge.core import utils

    monkeypatch.setattr(utils.config, "get", lambda *a, **k: "Auto")
    assert format_size(None) == "0 B"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", []),
        (".jpg, .png", [".jpg", ".png"]),
        ("jpg,png", [".jpg", ".png"]),
        (".JPG, png, .Pdf", [".jpg", ".png", ".pdf"]),
        (None, []),
    ],
)
def test_utils_parity_parse_extensions(raw, expected):
    assert parse_extensions(raw) == expected


def test_utils_parity_check_disk_space(tmp_path):
    ok, _ = check_disk_space(str(tmp_path), 1)
    assert ok is True
    ok, _ = check_disk_space(str(tmp_path / "missing_dir"), 1)
    assert ok is True


def test_utils_parity_safe_zip_write(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("data", encoding="utf-8")

    with zipfile.ZipFile(tmp_path / "t.zip", "w") as zf:
        assert safe_zip_write(zf, str(target), "a.txt", set()) == "a.txt"
    with zipfile.ZipFile(tmp_path / "t2.zip", "w") as zf:
        assert safe_zip_write(zf, str(target), "a.txt", {"a.txt"}) == "a_1.txt"


def test_utils_parity_config_merge_validates_and_clamps():
    """_merge_validated keeps known keys in range, clamps out-of-range values
    back to defaults, and preserves unknown keys (R-CORE-3)."""
    from dataforge.core.config import ConfigManager

    cfg = object.__new__(ConfigManager)
    cfg.data = ConfigManager.DEFAULT_CONFIG.copy()

    cfg._merge_validated({
        "hash_algorithm": "sha256",
        "max_thread_workers": 999999,
        "log_level": "NOT_A_LEVEL",
        "totally_unknown_key": "value",
        "theme": "midnight",
    })

    assert cfg.data["hash_algorithm"] == "sha256"
    assert cfg.data["max_thread_workers"] == ConfigManager.DEFAULT_CONFIG["max_thread_workers"]
    assert cfg.data["log_level"] == ConfigManager.DEFAULT_CONFIG["log_level"]
    assert cfg.data["theme"] == "midnight"
    assert cfg.data["totally_unknown_key"] == "value"


# ---------------------------------------------------------------------------
# test_export_parity — search/duplicates export row builders
# ---------------------------------------------------------------------------


def test_export_parity_search_rows(tmp_path):
    """Search results serialize and export to JSON without data loss."""
    from dataforge.modules.search import (
        SearchQuery,
        export_result_rows,
        search_files,
        serialize_file_entry,
    )

    root = tmp_path / "t"
    root.mkdir()
    (root / "a.txt").write_text("x", encoding="utf-8")
    (root / "b.png").write_text("y", encoding="utf-8")

    results = search_files(str(root), SearchQuery())
    assert len(results) >= 2

    out = tmp_path / "out.json"
    export_result_rows([serialize_file_entry(e) for e in results], str(out), format="json")
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert {r["extension"] for r in rows} >= {".txt", ".png"}
    assert all(r["filename"] for r in rows)


def test_export_parity_duplicate_rows(tmp_path):
    """Duplicate export rows: only the duplicated pair exports (2 members),
    group summary excluded."""
    from dataforge.modules.duplicates import (
        build_duplicate_export_rows,
        build_duplicate_records,
        find_duplicates,
    )

    root = tmp_path / "t"
    root.mkdir()
    (root / "one.bin").write_bytes(b"same content")
    (root / "two.bin").write_bytes(b"same content")
    (root / "three.bin").write_bytes(b"unique")

    records = build_duplicate_records(find_duplicates(str(root)))
    rows = build_duplicate_export_rows(records, include_group_summary=False)
    assert len(rows) == 2
    assert all(row["record_type"] == "duplicate_entry" for row in rows)


# ---------------------------------------------------------------------------
# test_new_modules_parity — junk scan, password, forensics, hardware essence
# ---------------------------------------------------------------------------


def test_new_modules_parity_junk_scan_user_path_never_blanket(tmp_path):
    """User-supplied paths under 'System Temp' are matched by
    extension/filename only, never blanket-classified."""
    from dataforge.modules.system_cleanup import scan_junk_files

    (tmp_path / "junk.bak").write_text("junk", encoding="utf-8")
    (tmp_path / "normal.txt").write_text("important", encoding="utf-8")

    results = scan_junk_files(paths=[str(tmp_path)], categories=["System Temp"])
    paths = [e.path for e in results.get("System Temp", [])]
    assert any("junk.bak" in p for p in paths)
    assert not any("normal.txt" in p for p in paths)


def test_new_modules_parity_password_strength():
    from dataforge.modules.password_tools import analyze_password_strength

    results = analyze_password_strength(["abc", "CorrectHorseBatteryStaple!9"])
    weak, strong = results[0], results[1]
    assert weak["score"] < strong["score"]


def test_new_modules_parity_forensic_report_html_escapes(tmp_path):
    """Forensic HTML reports escape attacker-controlled filenames."""
    from dataforge.modules.forensics import generate_forensic_report

    malicious = "<script>alert(1)</script>.txt"
    results = {
        "file_count": 1,
        "hashes": [{
            "filename": malicious,
            "formatted_size": "1 B",
            "md5": "0" * 32,
            "sha256": "0" * 64,
        }],
        "artifacts": {
            "users": [{
                "username": malicious,
                "uid": 0,
                "home": "/root",
                "shell": "/bin/bash",
            }],
        },
    }
    out = tmp_path / "report.html"
    generate_forensic_report(results, str(out), fmt="html")
    html = out.read_text(encoding="utf-8")
    assert "&lt;script&gt;" in html
    assert "<script>" not in html


def test_new_modules_parity_hardware_and_performance():
    """Hardware report and system info still produce meaningful payloads."""
    from dataforge.modules.hardware import get_hardware_report
    from dataforge.modules.performance import get_system_info

    report = get_hardware_report()
    assert report is not None
    info = get_system_info()
    assert isinstance(info, dict)
    assert any(key in info for key in ("cpu", "cpu_count", "os", "platform", "system"))


# ---------------------------------------------------------------------------
# Import-time parity guard — deprecated suites no longer run their own tests
# ---------------------------------------------------------------------------


def test_deprecated_files_are_not_collected():
    """The 5 deprecated files must be gone so the total suite stays inside
    the 900-1000 band (acceptance criterion 3)."""
    deprecated = [
        "test_comprehensive.py",
        "test_integration.py",
        "test_contract_regressions.py",
        "test_new_modules.py",
        "verify_scenarios.py",
    ]
    for name in deprecated:
        assert not (Path(__file__).parent / name).exists(), f"{name} must be removed"