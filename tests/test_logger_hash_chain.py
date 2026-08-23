"""Tests for TICK-510 — Hash-chain app.log into AuditLog (F11 remainder).

Acceptance:
 - chain_to_audit=False (default) -> Filter NOT attached, len==1, no DB writes
 - chain_to_audit=True + is_evidence_mode True -> 10 records -> audit.append exactly 10 with event='log'
 - tampered row -> verify valid False, first_bad_id row_5/5
 - existing test_logger_stdout_regression still passes (no regression)
"""
import logging
import os
import sqlite3

import pytest

from dataforge.core import audit as audit_module
from dataforge.core.audit import AuditLog
from dataforge.core.case import CaseContext, clear_context, set_context
from dataforge.core.logger import ChainToAuditFilter, setup_logger


def _clean_logger(name):
    lg = logging.getLogger(name)
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    for f in list(lg.filters):
        try:
            lg.removeFilter(f)
        except Exception:
            pass
    lg.propagate = False
    return lg


@pytest.fixture(autouse=True)
def _clear_case():
    clear_context()
    # ensure env not blocking
    old = os.environ.get("DATAFORGE_CHAIN_APP_LOG")
    if "DATAFORGE_CHAIN_APP_LOG" in os.environ:
        del os.environ["DATAFORGE_CHAIN_APP_LOG"]
    yield
    clear_context()
    if old is not None:
        os.environ["DATAFORGE_CHAIN_APP_LOG"] = old
    elif "DATAFORGE_CHAIN_APP_LOG" in os.environ:
        del os.environ["DATAFORGE_CHAIN_APP_LOG"]


def test_default_no_filter_no_db_writes(tmp_path, monkeypatch):
    """GIVEN chain_to_audit=False WHEN setup_logger called THEN no filter, handlers==1, no DB writes."""
    calls = []
    monkeypatch.setattr(audit_module.AuditLog, "append", lambda self, *a, **k: calls.append((a, k)) or {"id": 1})

    name = "dataforge.test510.default"
    _clean_logger(name)
    lg = setup_logger(name, log_file=None, level=logging.INFO, chain_to_audit=False)
    assert not any(isinstance(f, ChainToAuditFilter) for f in lg.filters), "filter must NOT be attached when chain_to_audit=False"
    # When no log_file, only console handler
    assert len(lg.handlers) == 1
    # Emit records — should not trigger DB writes
    lg.info("hello default")
    lg.warning("warn default")
    lg.error("err default")
    assert len(calls) == 0, f"expected 0 audit calls, got {len(calls)}"
    # Cleanup
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    lg.filters.clear()


def test_chain_true_with_evidence_mode_appends_10(tmp_path):
    """GIVEN chain_to_audit=True + evidence_mode THEN 10 records -> 10 audit appends with event='log'."""
    db = str(tmp_path / "audit.db")
    audit_log = AuditLog(db_path=db)
    # Ensure evidence mode
    set_context(CaseContext(case_id="CASE-510", operator="tester", evidence_mode=True))

    name = "dataforge.test510.chain10"
    _clean_logger(name)
    lg = setup_logger(name, log_file=str(tmp_path / "app.log"), level=logging.INFO, chain_to_audit=True, audit_log=audit_log)
    # Filter should be attached now (evidence mode true, env not 0)
    assert any(isinstance(f, ChainToAuditFilter) for f in lg.filters)
    assert audit_log.count() == 0
    for i in range(10):
        lg.info(f"msg {i} chain test")
    # Also check level filtering: DEBUG should not be chained
    lg.debug("debug should not chain")
    # Need to flush
    for h in lg.handlers:
        try:
            h.flush()
        except Exception:
            pass
    assert audit_log.count() == 10, f"expected 10 entries, got {audit_log.count()}"
    entries = audit_log.get_entries(limit=10, offset=0)
    for e in entries:
        payload = e["payload"]
        # ticket says event='log' (in payload) and audit action is 'log'
        assert e["action"] == "log"
        assert payload.get("event") == "log"
        assert "level" in payload
        assert "name" in payload
        assert "msg" in payload
        assert "ts" in payload
        # Level should be INFO for our messages
        assert payload["level"] == "INFO"
    # Chain must be valid and SHA-256 extends
    vr = audit_log.verify()
    assert vr["valid"] is True
    assert vr["entries_checked"] == 10
    assert vr["first_bad_id"] is None
    # Tail hash should be 64 hex chars (SHA-256)
    tail = audit_log.tail_hash()
    assert len(tail) == 64
    assert all(c in "0123456789abcdef" for c in tail)
    audit_log.close()
    # Cleanup logger
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    lg.filters.clear()
    clear_context()


def test_chain_true_with_evidence_mode_calls_audit_via_monkeypatch(tmp_path, monkeypatch):
    """Variant using monkeypatch on AuditLog.append to count calls (acceptance style)."""
    calls = []
    orig_append = AuditLog.append

    def counting_append(self, action, payload):
        calls.append((action, payload))
        return orig_append(self, action, payload)

    monkeypatch.setattr(AuditLog, "append", counting_append)

    db = str(tmp_path / "audit2.db")
    # Patch the filter's factory to use tmp_path DB by monkeypatching AuditLog __init__
    # Instead, create audit_log instance and inject via setup_logger
    audit_log = AuditLog(db_path=db)
    set_context(CaseContext(evidence_mode=True))
    name = "dataforge.test510.monkey"
    _clean_logger(name)
    # Need to ensure filter uses our audit_log instance: pass it explicitly
    # If we rely on monkeypatch of append, any AuditLog instance will count
    lg = setup_logger(name, log_file=str(tmp_path / "app2.log"), level=logging.INFO, chain_to_audit=True, audit_log=audit_log)
    for i in range(10):
        lg.info(f"counted {i}")
    assert len(calls) == 10
    for action, payload in calls:
        assert action == "log"
        assert payload.get("event") == "log"
    audit_log.close()
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    lg.filters.clear()
    clear_context()


def test_tamper_detection_row_5(tmp_path):
    """GIVEN tampered row 5 WHEN verify THEN valid False, first_bad_id 5 / row_5."""
    db = str(tmp_path / "audit_tamper.db")
    audit_log = AuditLog(db_path=db)
    set_context(CaseContext(evidence_mode=True))
    name = "dataforge.test510.tamper"
    _clean_logger(name)
    lg = setup_logger(name, log_file=str(tmp_path / "app_tamper.log"), level=logging.INFO, chain_to_audit=True, audit_log=audit_log)
    for i in range(10):
        lg.info(f"tamper msg {i}")
    assert audit_log.count() == 10
    # Verify clean before tamper
    vr = audit_log.verify()
    assert vr["valid"] is True
    audit_log.close()
    # Tamper: 1 char changed in row 5 payload_json
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT payload_json FROM audit_log WHERE id=5").fetchone()
    assert row is not None
    tampered = row[0][:-1] + ("X" if row[0][-1] != "X" else "Y")
    conn.execute("UPDATE audit_log SET payload_json=? WHERE id=5", (tampered,))
    conn.commit()
    conn.close()
    # Reopen and verify
    audit2 = AuditLog(db_path=db)
    vr2 = audit2.verify()
    assert vr2["valid"] is False
    # Acceptance says 'row_5' string; actual audit returns int 5. Accept either containing 5.
    first = vr2["first_bad_id"]
    assert first == 5 or first == "row_5" or str(first) == "5" or str(first) == "row_5", f"expected first_bad_id 5/row_5 got {first!r}"
    audit2.close()
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    lg.filters.clear()
    clear_context()


def test_env_var_disables_chaining(tmp_path):
    """DATAFORGE_CHAIN_APP_LOG=0 disables chaining even when chain_to_audit True + evidence mode."""
    db = str(tmp_path / "audit_env.db")
    audit_log = AuditLog(db_path=db)
    set_context(CaseContext(evidence_mode=True))
    os.environ["DATAFORGE_CHAIN_APP_LOG"] = "0"
    name = "dataforge.test510.env"
    _clean_logger(name)
    lg = setup_logger(name, log_file=str(tmp_path / "app_env.log"), level=logging.INFO, chain_to_audit=True, audit_log=audit_log)
    # Filter may still be added at setup but should be inactive due to env check in filter.filter
    # Or if setup checks env, filter not added — either way count must stay 0
    for i in range(5):
        lg.info(f"env disabled {i}")
    assert audit_log.count() == 0
    audit_log.close()
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    lg.filters.clear()
    del os.environ["DATAFORGE_CHAIN_APP_LOG"]
    clear_context()


def test_evidence_mode_off_no_chaining(tmp_path):
    """When evidence_mode False, even chain_to_audit True must not chain."""
    db = str(tmp_path / "audit_no_ev.db")
    audit_log = AuditLog(db_path=db)
    # No evidence mode (default)
    clear_context()
    name = "dataforge.test510.noev"
    _clean_logger(name)
    lg = setup_logger(name, log_file=str(tmp_path / "app_noev.log"), level=logging.INFO, chain_to_audit=True, audit_log=audit_log)
    for i in range(5):
        lg.info(f"no ev {i}")
    assert audit_log.count() == 0
    audit_log.close()
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    lg.filters.clear()


def test_below_info_not_chained(tmp_path):
    """DEBUG records (<INFO) must not be forwarded even when chaining enabled."""
    db = str(tmp_path / "audit_debug.db")
    audit_log = AuditLog(db_path=db)
    set_context(CaseContext(evidence_mode=True))
    name = "dataforge.test510.debug"
    _clean_logger(name)
    lg = setup_logger(name, log_file=str(tmp_path / "app_debug.log"), level=logging.DEBUG, chain_to_audit=True, audit_log=audit_log)
    lg.debug("debug msg")
    lg.info("info msg")
    assert audit_log.count() == 1
    entry = audit_log.get_entries(limit=1)[0]
    assert entry["payload"]["msg"] == "info msg"
    audit_log.close()
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    lg.filters.clear()
    clear_context()


def test_sanity_tmp_chained_verify(tmp_path):
    """Sanity: setup_logger(chain_to_audit=True) in tmp_path, 10 records, verify valid."""
    db = str(tmp_path / "audit_sanity.db")
    audit_log = AuditLog(db_path=db)
    set_context(CaseContext(evidence_mode=True))
    name = "dataforge.test510.sanity"
    _clean_logger(name)
    lg = setup_logger(name, log_file=str(tmp_path / "sanity.log"), level=logging.INFO, chain_to_audit=True, audit_log=audit_log)
    for i in range(10):
        lg.info(f"sanity {i}")
    vr = audit_log.verify()
    assert vr == {"valid": True, "entries_checked": 10, "first_bad_id": None}
    audit_log.close()
    for h in list(lg.handlers):
        try:
            h.close()
        except Exception:
            pass
    lg.handlers.clear()
    lg.filters.clear()
    clear_context()


def test_chain_filter_class_exists():
    """Filter is a logging.Filter subclass with correct name."""
    import logging

    f = ChainToAuditFilter()
    assert isinstance(f, logging.Filter)
    # Ensure logger integration works without audit DB
    lg = logging.getLogger("dataforge.test510.filter_exists")
    _clean_logger("dataforge.test510.filter_exists")
    lg.addFilter(f)
    assert any(isinstance(x, ChainToAuditFilter) for x in lg.filters)
    lg.removeFilter(f)
