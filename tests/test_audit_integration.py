"""Tests for TICK-503 — Wire AuditLog into FileActionService (F1).

Acceptance criteria:
- GIVEN FileActionService with audit_log WHEN transfer_items called THEN operation recorded
- GIVEN FileActionService with audit_log WHEN delete_items called THEN operation recorded
- GIVEN FileActionService with audit_log WHEN rename_items called THEN operation recorded
- GIVEN FileActionService with audit_log WHEN archive_items called THEN operation recorded
- GIVEN Evidence Mode active WHEN operation called THEN audit log verified first
- GIVEN audit log tampered WHEN verify called THEN raises IntegrityError
"""
import os
import sqlite3
import tempfile
import zipfile

import pytest

from dataforge.core.audit import AuditLog
from dataforge.core.case import CaseContext, clear_context
from dataforge.core.services.file_actions import AuditIntegrityError, FileActionService, IntegrityError


@pytest.fixture(autouse=True)
def _clear_case_context():
    clear_context()
    yield
    clear_context()


def _make_audit(tmpdir):
    db = os.path.join(tmpdir, "audit.db")
    log = AuditLog(db_path=db)
    return log


def test_transfer_recorded(tmp_path):
    audit_tmp = tempfile.mkdtemp()
    log = _make_audit(audit_tmp)
    ctx = CaseContext(case_id="CASE-001", operator="Alice")
    svc = FileActionService(audit_log=log, case_context=ctx)

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.txt").write_text("hello")
    (src_dir / "b.txt").write_text("world")
    dest = tmp_path / "dest"
    dest.mkdir()

    items = [str(src_dir / "a.txt"), str(src_dir / "b.txt")]
    initial = log.count()
    outcome = svc.transfer_items(items, str(dest), "copy", dry_run=False)

    assert len(outcome.successes) == 2
    assert log.count() == initial + 1
    entry = log.get_entries(limit=1)[0]
    payload = entry["payload"]
    assert payload["operation"] == "transfer"
    assert any("a.txt" in s for s in payload["sources"])
    assert any("b.txt" in s for s in payload["sources"])
    assert payload["case_id"] == "CASE-001"
    assert payload["operator"] == "Alice"
    assert "timestamp" in payload
    log.close()


def test_delete_recorded(tmp_path):
    audit_tmp = tempfile.mkdtemp()
    log = _make_audit(audit_tmp)
    svc = FileActionService(audit_log=log)

    f = tmp_path / "del.txt"
    f.write_text("to delete")
    assert log.count() == 0
    outcome = svc.delete_items([str(f)], dry_run=False, safe_mode=False)
    assert len(outcome.successes) == 1
    assert log.count() == 1
    entry = log.get_entries(limit=1)[0]
    payload = entry["payload"]
    assert payload["operation"] == "delete"
    assert any("del.txt" in s for s in payload["sources"])
    assert payload["destinations"] == []
    log.close()


def test_rename_recorded(tmp_path):
    audit_tmp = tempfile.mkdtemp()
    log = _make_audit(audit_tmp)
    svc = FileActionService(audit_log=log, case_context=CaseContext(case_id="C2", operator="Bob"))

    f = tmp_path / "old.txt"
    f.write_text("data")
    outcome = svc.rename_items([str(f)], lambda item, idx: "new.txt", dry_run=False)
    assert len(outcome.successes) == 1
    assert log.count() == 1
    payload = log.get_entries(limit=1)[0]["payload"]
    assert payload["operation"] == "rename"
    assert any("old.txt" in s for s in payload["sources"])
    assert any("new.txt" in s for s in payload["destinations"])
    assert payload["case_id"] == "C2"
    log.close()


def test_rename_with_regex_recorded(tmp_path):
    audit_tmp = tempfile.mkdtemp()
    log = _make_audit(audit_tmp)
    svc = FileActionService(audit_log=log)

    f = tmp_path / "old_1.txt"
    f.write_text("x")
    outcome = svc.rename_items_with_regex([str(f)], r"old_", "new_", dry_run=False)
    assert len(outcome.successes) == 1
    assert log.count() == 1
    assert log.get_entries(limit=1)[0]["payload"]["operation"] == "rename"
    log.close()


def test_archive_single_recorded(tmp_path):
    audit_tmp = tempfile.mkdtemp()
    log = _make_audit(audit_tmp)
    svc = FileActionService(audit_log=log)

    f1 = tmp_path / "a.txt"
    f1.write_text("a")
    f2 = tmp_path / "b.txt"
    f2.write_text("b")
    dest = str(tmp_path / "out.zip")
    outcome = svc.archive_items([str(f1), str(f2)], mode="single", destination=dest, dry_run=False)
    assert dest in [r.result.destination_path for r in outcome.successes if r.result] or outcome.successes
    assert log.count() == 1
    payload = log.get_entries(limit=1)[0]["payload"]
    assert payload["operation"] == "archive"
    assert any("a.txt" in s for s in payload["sources"])
    assert dest in payload["destinations"] or any("out.zip" in d for d in payload["destinations"])
    log.close()


def test_archive_individual_recorded(tmp_path):
    audit_tmp = tempfile.mkdtemp()
    log = _make_audit(audit_tmp)
    svc = FileActionService(audit_log=log)

    f = tmp_path / "x.txt"
    f.write_text("x")
    outcome = svc.archive_items([str(f)], mode="individual", dry_run=False)
    assert len(outcome.successes) == 1
    assert log.count() == 1
    assert log.get_entries(limit=1)[0]["payload"]["operation"] == "archive"
    log.close()


def test_evidence_mode_verifies_audit_before_operation(tmp_path):
    """GIVEN Evidence Mode active WHEN operation called THEN audit log verified first.
    Tampered log should block or raise IntegrityError."""
    audit_tmp = tempfile.mkdtemp()
    db = os.path.join(audit_tmp, "audit.db")
    log = AuditLog(db_path=db)
    log.append("init", {"x": 1})
    log.close()

    # Tamper
    conn = sqlite3.connect(db)
    conn.execute("UPDATE audit_log SET payload_json='TAMPERED' WHERE id=1")
    conn.commit()
    conn.close()

    log2 = AuditLog(db_path=db)
    # Verify that log is tampered
    vr = log2.verify()
    assert vr["valid"] is False

    ctx = CaseContext(case_id="CASE-EV", operator="Eve", evidence_mode=True)
    svc = FileActionService(audit_log=log2, case_context=ctx)

    src = tmp_path / "evidence.txt"
    src.write_text("evidence")
    dest = tmp_path / "dest"
    dest.mkdir()

    # Operation should be blocked due to audit integrity failure.
    # Implementation raises AuditIntegrityError; accept either raise or blocked outcome.
    try:
        outcome = svc.transfer_items([str(src)], str(dest), "move", dry_run=False)
    except (AuditIntegrityError, IntegrityError) as exc:
        assert "Audit log integrity" in str(exc) or "integrity" in str(exc).lower()
        # File must not have been moved
        assert src.exists()
        log2.close()
        return
    except Exception as exc:
        # Any exception with integrity message counts
        if "integrity" in str(exc).lower() or "Audit log" in str(exc):
            assert src.exists()
            log2.close()
            return
        raise

    # If no exception, should be blocked outcome
    assert len(outcome.failures) == 1 or outcome.requested == 1
    # Check that audit failure message present or evidence mode block
    assert any("Audit log integrity" in r.message or "Evidence Mode" in r.message for r in outcome.records)
    assert src.exists()
    log2.close()


def test_audit_tampered_verify_raises_integrity_error(tmp_path):
    """GIVEN audit log tampered WHEN verify called via FileActionService THEN raises IntegrityError."""
    audit_tmp = tempfile.mkdtemp()
    db = os.path.join(audit_tmp, "audit.db")
    log = AuditLog(db_path=db)
    for i in range(5):
        log.append("test", {"i": i})
    log.close()

    # Tamper entry 3
    conn = sqlite3.connect(db)
    conn.execute("UPDATE audit_log SET entry_hash='BAD' WHERE id=3")
    conn.commit()
    conn.close()

    log2 = AuditLog(db_path=db)
    vr = log2.verify()
    assert vr["valid"] is False
    assert vr["first_bad_id"] == 3

    # Now via FileActionService in evidence mode, verify should raise
    ctx = CaseContext(evidence_mode=True)
    svc = FileActionService(audit_log=log2, case_context=ctx)
    # Directly test _verify_audit raises
    with pytest.raises((AuditIntegrityError, IntegrityError)):
        svc._verify_audit()

    # Also test that operation raises
    f = tmp_path / "t.txt"
    f.write_text("t")
    with pytest.raises((AuditIntegrityError, IntegrityError)):
        svc.delete_items([str(f)], dry_run=False, safe_mode=False)

    log2.close()


def test_without_audit_log_still_works(tmp_path):
    """GIVEN FileActionService without audit_log WHEN called THEN no error."""
    svc = FileActionService()  # no audit
    src = tmp_path / "a.txt"
    src.write_text("a")
    dest = tmp_path / "dest"
    dest.mkdir()
    outcome = svc.transfer_items([str(src)], str(dest), "copy", dry_run=True)
    assert len(outcome.successes) == 1

    # Also via class method (legacy)
    outcome2 = FileActionService.transfer_items([str(src)], str(dest), "copy", dry_run=True)
    assert len(outcome2.successes) == 1


def test_class_method_legacy_still_works(tmp_path):
    """Legacy class-method calls must still work without audit."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.txt").write_text("hi")
    dest = tmp_path / "dest"
    dest.mkdir()
    # Call as class method (no instance)
    outcome = FileActionService.transfer_items([str(src / "f.txt")], str(dest), "move", dry_run=True)
    assert outcome.requested == 1

    outcome2 = FileActionService.delete_items([str(src / "f.txt")], dry_run=True)
    assert outcome2.requested == 1

    outcome3 = FileActionService.rename_items_with_regex([str(src / "f.txt")], r"f", "g", dry_run=True)
    assert outcome3.requested == 1


def test_constructor_accepts_optional_params():
    log = AuditLog(db_path=os.path.join(tempfile.mkdtemp(), "audit.db"))
    ctx = CaseContext(case_id="C", operator="O")
    svc = FileActionService(audit_log=log, case_context=ctx)
    assert svc.audit_log is log
    assert svc.case_context is ctx
    assert svc.provider is not None

    # provider optional
    svc2 = FileActionService(audit_log=log)
    assert svc2.case_context is None

    svc3 = FileActionService()
    assert svc3.audit_log is None
    log.close()


def test_dry_run_still_recorded(tmp_path):
    audit_tmp = tempfile.mkdtemp()
    log = _make_audit(audit_tmp)
    svc = FileActionService(audit_log=log)

    f = tmp_path / "a.txt"
    f.write_text("a")
    outcome = svc.delete_items([str(f)], dry_run=True)
    assert len(outcome.successes) == 1
    # dry_run should still be recorded
    assert log.count() == 1
    payload = log.get_entries(limit=1)[0]["payload"]
    assert payload["dry_run"] is True
    log.close()


def test_evidence_mode_blocks_without_audit_tamper(tmp_path):
    """Evidence mode without audit should still block destructive ops."""
    from dataforge.core.case import set_context

    ctx = CaseContext(evidence_mode=True)
    set_context(ctx)
    try:
        f = tmp_path / "e.txt"
        f.write_text("evidence")
        outcome = FileActionService.delete_items([str(f)], dry_run=False, safe_mode=False)
        assert len(outcome.failures) == 1
        assert "Evidence Mode" in outcome.failures[0].message
        assert f.exists()

        # With instance audit_log also blocked
        audit_tmp = tempfile.mkdtemp()
        log = _make_audit(audit_tmp)
        svc = FileActionService(audit_log=log, case_context=ctx)
        f2 = tmp_path / "e2.txt"
        f2.write_text("evidence2")
        outcome2 = svc.transfer_items([str(f2)], str(tmp_path / "dest"), "move", dry_run=False)
        assert len(outcome2.failures) == 1
        log.close()
    finally:
        clear_context()
