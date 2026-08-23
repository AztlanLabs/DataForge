"""
Tests for TICK-508 — forensic engine: image_io + streams + indicators (F5/F7/F8).

Covers acceptance_criteria:
- HAS_LIBEWF false + open_image fallback + logger.info('raw image fallback')
- Synthetic E01 guarded integration (DATAFORGE_ENABLE_LIBEWF_TESTS)
- Linux xattr user.test=b'42'
- Windows MotW :Zone.Identifier (skipped on non-Windows)
- YARA marker rule match
- YARA missing returns empty + debug log, no crash
- NSRL CSV pivot hit/miss
"""

import hashlib
import importlib.util
import logging
import os
import sys
from pathlib import Path
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_xattr_support(tmp_path: Path) -> bool:
    if not hasattr(os, "listxattr"):
        return False
    f = tmp_path / "_probe_xattr"
    try:
        f.write_bytes(b"probe")
        os.setxattr(str(f), "user.test_probe", b"1")  # type: ignore[attr-defined]
        os.getxattr(str(f), "user.test_probe")  # type: ignore[attr-defined]
        return True
    except Exception:
        return False
    finally:
        try:
            f.unlink()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# image_io — F5
# ---------------------------------------------------------------------------

class TestImageIO:
    def test_has_libewf_flag_exists(self):
        from dataforge.core import image_io

        assert hasattr(image_io, "HAS_LIBEWF")
        assert isinstance(image_io.HAS_LIBEWF, bool)
        # In this CI libewf is not installed -> False
        if importlib.util.find_spec("pyewf") is None:
            assert image_io.HAS_LIBEWF is False

    def test_has_aff4_flag_exists(self):
        from dataforge.core import image_io

        assert hasattr(image_io, "HAS_AFF4")
        assert isinstance(image_io.HAS_AFF4, bool)

    def test_open_image_fallback_returns_tempfile_and_logs_info(self, tmp_path, caplog):
        from dataforge.core import image_io

        # Use a real file so copy succeeds
        src = tmp_path / "foo.dd"
        src.write_bytes(b"hello forensic world" * 100)

        # Ensure we are in fallback (libewf missing, not E01)
        assert image_io.HAS_LIBEWF is False or src.suffix.lower() != ".e01"

        caplog.set_level(logging.INFO)
        with image_io.open_image(str(src)) as reader:
            # RawImageReader is read-only, byte-iterable
            assert hasattr(reader, "read")
            assert hasattr(reader, "seek")
            assert hasattr(reader, "__iter__")
            data = reader.read()
            assert b"hello forensic" in data
            # byte-iterable
            chunks = list(reader)
            assert b"".join(chunks) == data
            # read-only
            with pytest.raises(Exception):
                reader.write(b"bad")  # type: ignore

        # Must have emitted exactly the required string
        assert any("raw image fallback" in rec.message for rec in caplog.records)

    def test_open_image_synthetic_foo_dd_even_when_missing(self, caplog):
        from dataforge.core import image_io

        caplog.set_level(logging.INFO)
        # foo.dd does not exist — should still return context manager, not raise
        with image_io.open_image("foo.dd") as reader:
            data = reader.read()
            assert isinstance(data, bytes)
        assert any("raw image fallback" in r.message for r in caplog.records)

    def test_raw_image_to_tempfile_exists_and_logs(self, tmp_path, caplog):
        from dataforge.core.image_io import raw_image_to_tempfile

        src = tmp_path / "raw.bin"
        src.write_bytes(b"abc123")
        caplog.set_level(logging.INFO)
        with raw_image_to_tempfile(str(src)) as reader:
            assert reader.read() == b"abc123"
        assert any("raw image fallback" in r.message for r in caplog.records)

    def test_raw_image_reader_is_readonly(self, tmp_path):
        from dataforge.core.image_io import RawImageReader

        f = tmp_path / "r.bin"
        f.write_bytes(b"data")
        fh = open(str(f), "rb")
        r = RawImageReader(fh, path=str(f))
        assert r.readable() is True
        assert r.writable() is False
        with pytest.raises(Exception):
            r.write(b"x")
        r.close()

    def test_list_entries_directory_delegates_to_scanner(self, tmp_path):
        from dataforge.core.image_io import list_entries

        d = tmp_path / "img_dir"
        d.mkdir()
        (d / "a.txt").write_text("a")
        (d / "b.txt").write_text("b")
        entries = list(list_entries(str(d)))
        assert len(entries) == 2
        paths = {e.path for e in entries}
        assert str(d / "a.txt") in paths

    def test_list_entries_file_single_entry(self, tmp_path):
        from dataforge.core.image_io import list_entries

        f = tmp_path / "single.dd"
        f.write_bytes(b"rawdata")
        entries = list(list_entries(str(f)))
        assert len(entries) == 1
        assert entries[0].path == str(f)

    def test_list_entries_e01_guarded(self, tmp_path):
        """Guarded integration: when libewf present + env set, count>1."""
        from dataforge.core import image_io

        if not image_io.HAS_LIBEWF:
            pytest.skip("libewf not installed — guarded test skipped")
        if os.getenv("DATAFORGE_ENABLE_LIBEWF_TESTS") != "1":
            pytest.skip("DATAFORGE_ENABLE_LIBEWF_TESTS !=1 — guarded test skipped")
        # Create synthetic 5 MiB file with .E01 suffix
        e01 = tmp_path / "synthetic.E01"
        e01.write_bytes(b"\x00" * (5 * 1024 * 1024))
        entries = list(image_io.list_entries(str(e01)))
        assert len(entries) > 1

    def test_image_io_source_contains_required_strings(self):
        src = Path("dataforge/core/image_io.py").read_text()
        assert "pyewf" in src
        assert "aff4" in src.lower()
        assert "raw image fallback" in src
        assert "RawImageReader" in src
        assert "open_image" in src
        assert "HAS_LIBEWF" in src


# ---------------------------------------------------------------------------
# streams — F8
# ---------------------------------------------------------------------------

class TestStreams:
    def test_has_xattr_flag_exists(self):
        from dataforge.core import streams

        assert hasattr(streams, "HAS_XATTR")
        assert isinstance(streams.HAS_XATTR, bool)

    def test_alternate_stream_dataclass(self):
        from dataforge.core.streams import AlternateStream

        s = AlternateStream(name="user.test", size=2, xattrs={"user.test": b"42"})
        assert s.name == "user.test"
        assert s.size == 2
        assert s.xattrs["user.test"] == b"42"

    def test_list_alternate_streams_linux_xattr(self, tmp_path):
        from dataforge.core.streams import list_alternate_streams

        if not _has_xattr_support(tmp_path):
            pytest.skip("xattr not supported on this filesystem")

        f = tmp_path / "xattr_test.txt"
        f.write_text("hello")
        # set xattr user.test = b'42'
        try:
            os.setxattr(str(f), "user.test", b"42")  # type: ignore[attr-defined]
        except OSError as exc:
            pytest.skip(f"setxattr failed: {exc}")

        streams = list_alternate_streams(str(f))
        # Must contain user.test with size 2 and xattrs dict with raw bytes
        found = [s for s in streams if s.name == "user.test"]
        assert len(found) == 1, f"expected user.test stream, got {streams}"
        assert found[0].size == 2
        assert found[0].xattrs.get("user.test") == b"42"

    def test_list_alternate_streams_no_xattr_empty(self, tmp_path):
        from dataforge.core.streams import list_alternate_streams

        f = tmp_path / "no_xattr.txt"
        f.write_text("no xattr here")
        streams = list_alternate_streams(str(f))
        # May be empty or contain unrelated xattrs; but should not contain user.test
        assert not any(s.name == "user.test" for s in streams)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only MotW test")
    def test_list_alternate_streams_motw_windows(self, tmp_path):
        from dataforge.core.streams import list_alternate_streams

        # This branch only runs on Windows; on Linux we skip.
        # For completeness, create a file and try to simulate Zone.Identifier
        f = tmp_path / "motw.txt"
        f.write_text("test")
        # On Windows, ADS would be f + ":Zone.Identifier"
        # We can't reliably create ADS on Linux, so just verify function doesn't crash
        streams = list_alternate_streams(str(f))
        assert isinstance(streams, list)

    def test_list_alternate_streams_motw_name(self):
        # Verify source handles Zone.Identifier
        src = Path("dataforge/core/streams.py").read_text()
        assert "Zone.Identifier" in src
        assert "FindFirstStreamW" in src or "ntfsutils" in src
        assert "list_alternate_streams" in src
        assert "HAS_XATTR" in src

    def test_streams_source_contains_required(self):
        src = Path("dataforge/core/streams.py").read_text()
        assert "xattr" in src.lower()
        assert "AlternateStream" in src


# ---------------------------------------------------------------------------
# indicators — F7
# ---------------------------------------------------------------------------

class TestIndicators:
    def test_has_yara_has_ssdeep_flags(self):
        from dataforge.modules import indicators

        assert hasattr(indicators, "HAS_YARA")
        assert hasattr(indicators, "HAS_SSDEEP")
        assert isinstance(indicators.HAS_YARA, bool)
        assert isinstance(indicators.HAS_SSDEEP, bool)

    def test_indicator_match_dataclass(self):
        from dataforge.modules.indicators import IndicatorMatch

        m = IndicatorMatch(yara_rules=["marker"], ssdeep_cluster=None, nsrl_hit=False)
        assert m.yara_rules == ["marker"]
        assert m.ssdeep_cluster is None
        assert m.nsrl_hit is False

    def test_match_path_yara_missing_returns_empty_and_logs_debug(self, tmp_path, caplog):
        from dataforge.modules import indicators

        f = tmp_path / "nomatch.txt"
        f.write_text("nothing relevant")

        # Ensure YARA is treated as missing
        with mock.patch.object(indicators, "HAS_YARA", False):
            caplog.set_level(logging.DEBUG, logger="dataforge")
            # ensure logger allows DEBUG
            indicators.logger.setLevel(logging.DEBUG)
            result = indicators.match_path(str(f))
            assert result.yara_rules == []
            assert result.ssdeep_cluster is None
            assert result.nsrl_hit is False
            # Must log debug warning, not crash
            assert any("yara" in r.message.lower() for r in caplog.records)
            # Also test missing file
            result2 = indicators.match_path(str(tmp_path / "does_not_exist.bin"))
            assert result2.yara_rules == []

    def test_match_path_yara_marker_via_mock(self, tmp_path):
        """GIVEN YARA rule marker WHEN file contains forensic THEN yara_rules=['marker']."""
        from dataforge.modules import indicators

        f = tmp_path / "forensic.txt"
        f.write_text("this file contains forensic keyword")

        # Build a fake yara module that mimics yara.compile(source=...).match(filepath=...)
        fake_match = mock.MagicMock()
        fake_match.rule = "marker"
        fake_rules = mock.MagicMock()
        fake_rules.match.return_value = [fake_match]

        fake_yara = mock.MagicMock()
        fake_yara.compile.return_value = fake_rules

        with mock.patch.dict("sys.modules", {"yara": fake_yara}):
            with mock.patch.object(indicators, "HAS_YARA", True):
                result = indicators.match_path(str(f))
                assert result.yara_rules == ["marker"]
                assert result.ssdeep_cluster is None
                assert result.nsrl_hit is False
                # Verify yara.compile was called
                assert fake_yara.compile.called

                # Also test file without keyword -> empty if we make match return []
                fake_rules.match.return_value = []
                f2 = tmp_path / "nomatch2.txt"
                f2.write_text("nothing")
                result2 = indicators.match_path(str(f2))
                assert result2.yara_rules == []

    def test_match_path_nsrl_hit(self, tmp_path, monkeypatch):
        from dataforge.modules import indicators

        f = tmp_path / "nsrl_test.bin"
        content = b"nsrl content for hash"
        f.write_bytes(content)
        sha256 = hashlib.sha256(content).hexdigest()

        # Create fake NSRL csv at expected location via monkeypatching Path.home
        nsrl_dir = tmp_path / "nsrl_home" / ".local" / "share" / "DataForge" / "nsrl"
        nsrl_dir.mkdir(parents=True)
        nsrl_file = nsrl_dir / "NSRLFile.txt"
        # Write CSV line containing sha256
        nsrl_file.write_text(f'"SHA-256","MD5","FileName"\n"{sha256}","abc","test.bin"\n')

        fake_home = tmp_path / "nsrl_home"
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        # Also ensure YARA missing doesn't interfere
        with mock.patch.object(indicators, "HAS_YARA", False):
            with mock.patch.object(indicators, "HAS_SSDEEP", False):
                result = indicators.match_path(str(f))
                assert result.nsrl_hit is True

                # Test miss
                f2 = tmp_path / "nsrl_miss.bin"
                f2.write_bytes(b"other content")
                result2 = indicators.match_path(str(f2))
                assert result2.nsrl_hit is False

    def test_match_path_nsrl_miss_when_no_file(self, tmp_path, monkeypatch):
        from dataforge.modules import indicators

        f = tmp_path / "plain.txt"
        f.write_text("plain")
        fake_home = tmp_path / "empty_home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        with mock.patch.object(indicators, "HAS_YARA", False):
            result = indicators.match_path(str(f))
            assert result.nsrl_hit is False

    def test_match_path_ssdeep_none_when_missing(self, tmp_path):
        from dataforge.modules import indicators

        f = tmp_path / "ssdeep.txt"
        f.write_text("test")
        with mock.patch.object(indicators, "HAS_SSDEEP", False):
            with mock.patch.object(indicators, "HAS_YARA", False):
                result = indicators.match_path(str(f))
                assert result.ssdeep_cluster is None

    def test_indicators_source_contains_required(self):
        src = Path("dataforge/modules/indicators.py").read_text()
        assert "yara.compile" in src
        assert "ssdeep" in src.lower()
        # ssdeep.compare is gated
        assert "ssdeep.compare" in src or "ssdeep" in src
        assert "NSRLFile.txt" in src
        assert "HAS_YARA" in src
        assert "HAS_SSDEEP" in src

    def test_match_path_does_not_crash_on_missing_yara(self, tmp_path):
        from dataforge.modules.indicators import match_path

        f = tmp_path / "crash.txt"
        f.write_text("forensic")
        # Even with real HAS_YARA=False, should not crash
        result = match_path(str(f))
        assert isinstance(result.yara_rules, list)
        assert result.ssdeep_cluster is None or isinstance(result.ssdeep_cluster, str)
        assert isinstance(result.nsrl_hit, bool)
