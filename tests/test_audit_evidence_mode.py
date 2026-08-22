"""
Tests for TICK-304: Hash-chained audit log, CaseContext, and Evidence Mode gate.

Acceptance criteria:
- GIVEN audit log with 10k entries WHEN one byte is tampered THEN
  audit.verify() fails and forensic command refuses to run
- GIVEN CaseContext.evidence_mode=True WHEN FileActionService.transfer/delete
  is called THEN returns success=False and leaves FS unchanged
- GIVEN generate_forensic_report WHEN run THEN report contains
  {operator, host, source_sha256, case_id, audit_tail_hash, tool_version}
  and report_generated is UTC ISO-8601
"""
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime

from dataforge.core.audit import AuditLog
from dataforge.core.case import (
    CaseContext,
    clear_context,
    get_context,
    is_evidence_mode,
    set_context,
)
from dataforge.core.services.file_actions import FileActionService
from dataforge.modules.forensics import generate_forensic_report, secure_delete


class TestAuditLog(unittest.TestCase):
    """Hash-chained audit log tests."""

    def test_append_and_verify_chain(self):
        """GIVEN empty audit log WHEN entries appended THEN chain verifies."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "audit.db")
            log = AuditLog(db_path=db)
            try:
                for i in range(100):
                    log.append("test_action", {"index": i})
                result = log.verify()
                self.assertTrue(result["valid"])
                self.assertEqual(result["entries_checked"], 100)
                self.assertIsNone(result["first_bad_id"])
            finally:
                log.close()

    def test_verify_fails_on_tamper(self):
        """GIVEN audit log with entries WHEN one byte is tampered THEN verify() fails."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "audit.db")
            log = AuditLog(db_path=db)
            try:
                for i in range(10):
                    log.append("test_action", {"index": i})
                log.close()

                # Tamper with entry 5
                conn = sqlite3.connect(db)
                conn.execute(
                    "UPDATE audit_log SET payload_json = 'TAMPERED' WHERE id = 5"
                )
                conn.commit()
                conn.close()

                log2 = AuditLog(db_path=db)
                result = log2.verify()
                self.assertFalse(result["valid"])
                self.assertEqual(result["first_bad_id"], 5)
                log2.close()
            finally:
                pass

    def test_verify_10k_entries(self):
        """GIVEN audit log with 10k entries WHEN verified THEN chain is valid."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "audit.db")
            log = AuditLog(db_path=db)
            try:
                for i in range(10_000):
                    log.append("bulk_action", {"seq": i})
                result = log.verify()
                self.assertTrue(result["valid"])
                self.assertEqual(result["entries_checked"], 10_000)
            finally:
                log.close()

    def test_tail_hash(self):
        """GIVEN audit log WHEN entries appended THEN tail_hash changes."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "audit.db")
            log = AuditLog(db_path=db)
            try:
                h0 = log.tail_hash()
                log.append("action", {"x": 1})
                h1 = log.tail_hash()
                self.assertNotEqual(h0, h1)
                log.append("action", {"x": 2})
                h2 = log.tail_hash()
                self.assertNotEqual(h1, h2)
            finally:
                log.close()

    def test_count(self):
        """GIVEN audit log WHEN entries appended THEN count matches."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "audit.db")
            log = AuditLog(db_path=db)
            try:
                self.assertEqual(log.count(), 0)
                for i in range(5):
                    log.append("action", {"i": i})
                self.assertEqual(log.count(), 5)
            finally:
                log.close()

    def test_get_entries(self):
        """GIVEN audit log WHEN get_entries called THEN returns recent entries."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "audit.db")
            log = AuditLog(db_path=db)
            try:
                for i in range(5):
                    log.append("action", {"i": i})
                entries = log.get_entries(limit=3)
                self.assertEqual(len(entries), 3)
                # Most recent first
                self.assertEqual(entries[0]["payload"]["i"], 4)
            finally:
                log.close()

    def test_file_permissions_0o600(self):
        """GIVEN new audit log WHEN created THEN file is 0o600."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "audit.db")
            log = AuditLog(db_path=db)
            try:
                mode = os.stat(db).st_mode & 0o777
                self.assertEqual(mode, 0o600)
            finally:
                log.close()

    def test_genesis_hash(self):
        """GIVEN empty audit log WHEN tail_hash called THEN returns genesis."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "audit.db")
            log = AuditLog(db_path=db)
            try:
                self.assertEqual(log.tail_hash(), AuditLog.GENESIS_HASH)
            finally:
                log.close()


class TestCaseContext(unittest.TestCase):
    """CaseContext and Evidence Mode tests."""

    def setUp(self):
        clear_context()

    def tearDown(self):
        clear_context()

    def test_case_context_defaults(self):
        """GIVEN CaseContext WHEN created with defaults THEN evidence_mode is False."""
        ctx = CaseContext()
        self.assertFalse(ctx.evidence_mode)
        self.assertEqual(ctx.case_id, "")
        self.assertEqual(ctx.operator, "")

    def test_case_context_evidence_mode(self):
        """GIVEN CaseContext.evidence_mode=True WHEN checked THEN is True."""
        ctx = CaseContext(case_id="C1", operator="OP", evidence_mode=True)
        self.assertTrue(ctx.evidence_mode)

    def test_set_get_clear_context(self):
        """GIVEN global context WHEN set/get/clear THEN works correctly."""
        self.assertIsNone(get_context())
        ctx = CaseContext(case_id="C1", evidence_mode=True)
        set_context(ctx)
        self.assertIsNotNone(get_context())
        self.assertTrue(get_context().evidence_mode)
        clear_context()
        self.assertIsNone(get_context())

    def test_is_evidence_mode_convenience(self):
        """GIVEN global context with evidence_mode=True WHEN is_evidence_mode THEN True."""
        self.assertFalse(is_evidence_mode())
        set_context(CaseContext(evidence_mode=True))
        self.assertTrue(is_evidence_mode())
        clear_context()
        self.assertFalse(is_evidence_mode())

    def test_case_context_to_dict_roundtrip(self):
        """GIVEN CaseContext WHEN to_dict/from_dict THEN roundtrips."""
        ctx = CaseContext(
            case_id="CASE-2026-0001",
            operator="Agent Smith",
            host="evidence-box",
            source_sha256="abc123",
            evidence_mode=True,
        )
        d = ctx.to_dict()
        ctx2 = CaseContext.from_dict(d)
        self.assertEqual(ctx.case_id, ctx2.case_id)
        self.assertEqual(ctx.operator, ctx2.operator)
        self.assertEqual(ctx.host, ctx2.host)
        self.assertEqual(ctx.source_sha256, ctx2.source_sha256)
        self.assertEqual(ctx.evidence_mode, ctx2.evidence_mode)


class TestEvidenceModeGate(unittest.TestCase):
    """Evidence Mode blocks destructive operations."""

    def setUp(self):
        clear_context()

    def tearDown(self):
        clear_context()

    def test_secure_delete_blocked_in_evidence_mode(self):
        """GIVEN evidence_mode=True WHEN secure_delete called THEN returns success=False."""
        set_context(CaseContext(evidence_mode=True))
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"evidence")
            path = f.name
        try:
            result = secure_delete(path)
            self.assertFalse(result["success"])
            self.assertIn("Evidence Mode", result["message"])
            # File must remain unchanged
            self.assertTrue(os.path.exists(path))
            with open(path, "rb") as f:
                self.assertEqual(f.read(), b"evidence")
        finally:
            os.unlink(path)

    def test_transfer_blocked_in_evidence_mode(self):
        """GIVEN evidence_mode=True WHEN FileActionService.transfer called dry_run=False THEN returns success=False."""
        set_context(CaseContext(evidence_mode=True))
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "evidence.txt")
            with open(src, "w") as f:
                f.write("evidence")
            dst = os.path.join(tmp, "dest")
            os.makedirs(dst)

            outcome = FileActionService.transfer_items(
                [src], dst, "move", dry_run=False
            )
            self.assertEqual(len(outcome.failures), 1)
            self.assertIn("Evidence Mode", outcome.failures[0].message)
            # Source must still exist
            self.assertTrue(os.path.exists(src))

    def test_delete_blocked_in_evidence_mode(self):
        """GIVEN evidence_mode=True WHEN FileActionService.delete called dry_run=False THEN returns success=False."""
        set_context(CaseContext(evidence_mode=True))
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"evidence")
            path = f.name
        try:
            outcome = FileActionService.delete_items([path], dry_run=False)
            self.assertEqual(len(outcome.failures), 1)
            self.assertIn("Evidence Mode", outcome.failures[0].message)
            # File must remain unchanged
            self.assertTrue(os.path.exists(path))
        finally:
            os.unlink(path)

    def test_dry_run_allowed_in_evidence_mode(self):
        """GIVEN evidence_mode=True WHEN dry_run=True THEN operations proceed (preview only)."""
        set_context(CaseContext(evidence_mode=True))
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"evidence")
            path = f.name
        try:
            outcome = FileActionService.delete_items([path], dry_run=True)
            # dry_run should succeed (preview, no FS change)
            self.assertEqual(len(outcome.successes), 1)
            self.assertTrue(os.path.exists(path))
        finally:
            os.unlink(path)

    def test_no_gate_without_context(self):
        """GIVEN no CaseContext WHEN secure_delete called THEN proceeds normally."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"junk")
            path = f.name
        result = secure_delete(path, passes=1)
        self.assertTrue(result["success"])
        self.assertFalse(os.path.exists(path))


class TestForensicReportProvenance(unittest.TestCase):
    """Forensic report contains provenance fields and UTC timestamp."""

    def test_report_contains_provenance_fields(self):
        """GIVEN generate_forensic_report with CaseContext WHEN run THEN report has provenance."""
        ctx = CaseContext(
            case_id="CASE-2026-0001",
            operator="Agent Smith",
            host="evidence-box",
            source_sha256="abc123def456",
        )
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "audit.db")
            audit = AuditLog(db_path=db)
            audit.append("test", {"x": 1})

            out_path = os.path.join(tmp, "report.json")
            generate_forensic_report(
                {"file_count": 42}, out_path,
                case_context=ctx, audit_log=audit,
            )

            with open(out_path) as f:
                report = json.load(f)

            self.assertEqual(report["case_id"], "CASE-2026-0001")
            self.assertEqual(report["operator"], "Agent Smith")
            self.assertEqual(report["host"], "evidence-box")
            self.assertEqual(report["source_sha256"], "abc123def456")
            self.assertIn("audit_tail_hash", report)
            self.assertEqual(report["tool_version"], "0.2.0")
            audit.close()

    def test_report_generated_is_utc_iso8601(self):
        """GIVEN generate_forensic_report WHEN run THEN report_generated is UTC ISO-8601."""
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "report.json")
            generate_forensic_report({"file_count": 1}, out_path)

            with open(out_path) as f:
                report = json.load(f)

            ts = report["report_generated"]
            # Must contain timezone info (UTC offset)
            self.assertIn("+00:00", ts)
            # Parse to verify valid ISO-8601
            dt = datetime.fromisoformat(ts)
            self.assertIsNotNone(dt.tzinfo)

    def test_report_html_contains_provenance(self):
        """GIVEN generate_forensic_report fmt=html with CaseContext WHEN run THEN HTML has provenance."""
        ctx = CaseContext(
            case_id="CASE-2026-0002",
            operator="Analyst",
            host="lab-station",
            source_sha256="hash123",
        )
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "report.html")
            generate_forensic_report(
                {"file_count": 5}, out_path,
                fmt="html", case_context=ctx,
            )
            with open(out_path) as f:
                html = f.read()
            self.assertIn("CASE-2026-0002", html)
            self.assertIn("Analyst", html)
            self.assertIn("hash123", html)


if __name__ == "__main__":
    unittest.main()
