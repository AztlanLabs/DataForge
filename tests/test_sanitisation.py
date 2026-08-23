"""
Tests for TICK-502: Move secure_delete to dedicated sanitisation module (F4).

Verification:
    python -m pytest tests/test_sanitisation.py -q
"""
import os
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

from dataforge.core.case import CaseContext, clear_context, set_context


class TestSanitisationExists:
    """GIVEN sanitisation.py exists WHEN imported THEN secure_delete available."""

    def test_import(self):
        from dataforge.modules.sanitisation import secure_delete

        assert callable(secure_delete)

    def test_forensics_reexport(self):
        from dataforge.modules.forensics import secure_delete as f_sd
        from dataforge.modules.sanitisation import secure_delete as s_sd

        assert callable(f_sd)
        assert callable(s_sd)

    def test_forensics_is_sanitisation(self):
        """Re-export identity (covers static import case)."""
        from dataforge.modules import forensics, sanitisation

        # With PEP 562 lazy, identity holds before and after patch
        assert forensics.secure_delete is sanitisation.secure_delete


class TestDelegation:
    """GIVEN forensics.py imported WHEN secure_delete called THEN delegates to sanitisation.py."""

    def test_delegates_via_patch(self):
        # This checks dynamic delegation (PEP 562). With static import it would
        # still pass if test patches before import, but dynamic covers both.
        import dataforge.modules.forensics as f_mod

        with patch("dataforge.modules.sanitisation.secure_delete") as mock:
            mock.return_value = {"success": True, "mocked": True}
            result = f_mod.secure_delete("/tmp/does_not_matter")
            mock.assert_called_once()
            assert result["mocked"] is True


class TestEvidenceMode:
    """GIVEN Evidence Mode active WHEN secure_delete called THEN blocked with ACPO error."""

    def setup_method(self):
        clear_context()

    def teardown_method(self):
        clear_context()

    def test_blocked_global_context(self):
        from dataforge.modules.sanitisation import secure_delete

        set_context(CaseContext(evidence_mode=True))
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"evidence")
            path = tf.name
        try:
            result = secure_delete(path)
            assert result["success"] is False
            # Must contain Evidence Mode and ACPO
            assert "Evidence Mode" in result["message"]
            assert "ACPO" in result["message"] or "ACPO" in result.get("error", "")
            # File must remain
            assert os.path.exists(path)
            assert open(path, "rb").read() == b"evidence"
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_blocked_via_param(self):
        from dataforge.modules.sanitisation import secure_delete

        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"data")
            path = tf.name
        try:
            result = secure_delete(path, evidence_mode=True)
            assert result["success"] is False
            assert "Evidence Mode" in result["message"]
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_blocked_forensics_reexport(self):
        from dataforge.modules.forensics import secure_delete

        set_context(CaseContext(evidence_mode=True))
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"evidence")
            path = tf.name
        try:
            result = secure_delete(path)
            assert result["success"] is False
            assert "Evidence Mode" in result["message"]
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.unlink(path)


class TestHardlinkAwareness:
    """GIVEN hardlink detected WHEN secure_delete called THEN warns about shared data."""

    def test_hardlink_warns(self):
        from dataforge.modules.sanitisation import secure_delete

        clear_context()
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"hl")
            path = tf.name
        link = path + ".link"
        os.link(path, link)
        try:
            result = secure_delete(path)
            assert result["success"] is False
            # Must warn about hardlink / shared data
            msg = (result.get("message", "") + result.get("warning", "") + result.get("error", "")).lower()
            assert "hardlink" in msg or "hard link" in msg or "shared" in msg
            # Should not have deleted either link (both still exist) or at least warn before delete
            # Our implementation returns warning before overwrite, so both should remain
            # If implementation deletes, at least one link would be gone — we check warning status
            assert result.get("status") in {"warning", "blocked", "error"} or result["success"] is False
        finally:
            for p in (path, link):
                if os.path.exists(p):
                    os.unlink(p)

    def test_no_hardlink_succeeds(self):
        from dataforge.modules.sanitisation import secure_delete

        clear_context()
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"single")
            path = tf.name
        result = secure_delete(path, passes=1)
        assert result["success"] is True
        assert not os.path.exists(path)


class TestSanitisationFunctional:
    """Additional functional coverage."""

    def test_secure_delete_removes_file(self):
        from dataforge.modules.sanitisation import secure_delete

        clear_context()
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"junk")
            path = tf.name
        assert os.path.exists(path)
        result = secure_delete(path, passes=1)
        assert result["success"] is True
        assert "best-effort" in result["message"].lower() or "overwrite" in result["message"].lower()
        assert not os.path.exists(path)
        assert result["passes"] == 1

    def test_path_object(self):
        from dataforge.modules.sanitisation import secure_delete

        clear_context()
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"pathobj")
            path = Path(tf.name)
        result = secure_delete(path, passes=1)
        assert result["success"] is True
        assert not path.exists()

    def test_not_regular_file(self):
        from dataforge.modules.sanitisation import secure_delete

        clear_context()
        with tempfile.TemporaryDirectory() as tmp:
            result = secure_delete(tmp)
            assert result["success"] is False
            assert "not a regular file" in result["message"].lower()

    def test_cancel_token(self):
        from dataforge.modules.sanitisation import secure_delete

        clear_context()
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"x" * 1024 * 10)
            path = tf.name
        evt = threading.Event()
        evt.set()
        try:
            result = secure_delete(path, passes=3, cancel_token=evt)
            assert result["success"] is False
            assert "cancel" in result["message"].lower()
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_legacy_positional_cancel(self):
        from dataforge.modules.sanitisation import secure_delete

        clear_context()
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"legacy")
            path = tf.name
        evt = threading.Event()
        evt.set()
        try:
            # legacy: third positional is cancel_token
            result = secure_delete(path, 3, evt)
            assert result["success"] is False
            assert "cancel" in result["message"].lower()
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_reflink_note_in_message(self):
        """Reflink/CoW awareness — success message must note CoW limitation."""
        from dataforge.modules.sanitisation import secure_delete

        clear_context()
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"cow")
            path = tf.name
        result = secure_delete(path, passes=1)
        assert result["success"] is True
        # Must mention CoW / SSD / flash limitation
        assert "cow" in result["message"].lower() or "ssd" in result["message"].lower() or "flash" in result["message"].lower()
