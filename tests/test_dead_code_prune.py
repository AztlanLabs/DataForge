"""TICK-913 — Dead code prune + unused paths verification.

Verifies that:
- genuinely dead symbols (device_manager.scan_device) are gone with no import path left.
- reporting.py no longer hard-depends on pandas (imports and exports work via
  the stdlib csv fallback when pandas is unavailable).
- kept live symbols still behave as before (format_size, normalize_filename,
  categorize_extension, file_signatures.identify_file_type).
"""
from __future__ import annotations

import csv
import importlib
import inspect
import json
import sys
import tempfile


from dataforge.core.common import FileEntry
from dataforge.core.utils import (
    CATEGORY_COLORS,
    CATEGORY_EXTENSIONS,
    categorize_extension,
    check_disk_space,
    format_display_path,
    format_size,
    normalize_filename,
    parse_extensions,
    safe_zip_write,
)
from dataforge.modules import device_manager
from dataforge.modules.file_signatures import identify_file_type, get_signature, get_all_categories
from dataforge.modules.password_tools import (
    extract_password_hashes,
    generate_crackable_hash,
    run_dictionary_attack,
    analyze_password_strength,
    check_hashcat_available,
    check_john_available,
    check_zip2john_available,
    check_pdf2john_available,
    list_common_wordlists,
)
from dataforge.modules.organizer import Organizer
from dataforge.modules.reporting import ReportGenerator
from dataforge.modules.usage import analyze_size, generate_usage_report


# ------------------------------------------------------------------
# Removed symbols must be gone with no import path remaining
# ------------------------------------------------------------------

def test_device_manager_scan_device_removed():
    """scan_device had no callers anywhere in the app or tests."""
    assert not hasattr(device_manager, "scan_device")
    source = inspect.getsource(device_manager)
    assert "scan_device" not in source


def test_scan_device_no_import_path_remains():
    """No module still references the removed symbol."""
    import subprocess

    grep = subprocess.run(
        ["rg", "-n", "scan_device", "dataforge"],
        capture_output=True, text=True,
    )
    assert grep.returncode != 0, f"scan_device still referenced:\n{grep.stdout}"


# ------------------------------------------------------------------
# reporting.py: no pandas hard dependency, exports still work
# ------------------------------------------------------------------

def _sample_duplicates():
    e1 = FileEntry(path="/tmp/a.jpg", filename="a.jpg", extension=".jpg",
                   size=100, created_at=0.0, modified_at=0.0)
    e2 = FileEntry(path="/tmp/b.jpg", filename="b.jpg", extension=".jpg",
                   size=100, created_at=0.0, modified_at=0.0)
    return {"abc123": [e1, e2]}


def test_reporting_imports_without_pandas(monkeypatch):
    """Module import must succeed even when pandas is unavailable."""
    monkeypatch.setitem(sys.modules, "pandas", None)
    mod = importlib.reload(importlib.import_module("dataforge.modules.reporting"))
    assert mod.HAS_PANDAS is False
    assert mod.pd is None


def test_duplicates_to_csv_fallback_without_pandas(monkeypatch, tmp_path):
    """CSV export must work via the stdlib csv fallback."""
    monkeypatch.setitem(sys.modules, "pandas", None)
    mod = importlib.reload(importlib.import_module("dataforge.modules.reporting"))
    assert mod.HAS_PANDAS is False

    out = tmp_path / "dupes.csv"
    mod.ReportGenerator.duplicates_to_csv(_sample_duplicates(), str(out))
    with open(out, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert all(row["hash"] == "abc123" for row in rows)
    assert {"path", "size_bytes", "filename", "extension"} <= set(rows[0].keys())


def test_duplicates_to_csv_empty_creates_file(tmp_path):
    """Empty input must still produce an (empty) export file, not fail silently."""
    out = tmp_path / "empty.csv"
    ReportGenerator.duplicates_to_csv({}, str(out))
    assert out.exists()
    assert out.read_text() == ""


def test_duplicates_to_json_and_txt_work(tmp_path):
    json_out = tmp_path / "dupes.json"
    ReportGenerator.duplicates_to_json(_sample_duplicates(), str(json_out))
    data = json.loads(json_out.read_text())
    assert "abc123" in data

    txt_out = tmp_path / "dupes.txt"
    ReportGenerator.duplicates_to_txt(_sample_duplicates(), str(txt_out))
    assert "abc123" in txt_out.read_text()


# ------------------------------------------------------------------
# Kept symbols still work as before
# ------------------------------------------------------------------

def test_utils_kept_symbols_work():
    assert format_size(1024) in ("1.0 KB", "1.00 KB")
    assert format_size(0) == "0 B"
    assert categorize_extension(".jpg") == "Images"
    assert categorize_extension(".xyz") == "Other"
    assert "Documents" in CATEGORY_COLORS
    assert ".py" in CATEGORY_EXTENSIONS["Code"]
    assert parse_extensions(".jpg, png") == [".jpg", ".png"]
    assert format_display_path("/tmp/root/a.txt", root="/tmp/root") == "a.txt"
    ok, _ = check_disk_space(tempfile.gettempdir(), 1)
    assert ok is True
    renamed = normalize_filename("my file 001.txt", index=1, numeric_pattern=r"\d+",
                                 numeric_replacement="{n}", numeric_pad=2)
    assert renamed == "my file 01.txt"
    assert safe_zip_write is not None


def test_file_signatures_kept_symbols_work():
    jpeg_header = b"\xFF\xD8\xFF\xE0\x00\x10JFIF"
    assert identify_file_type(jpeg_header) == "JPEG"
    assert get_signature("PNG")["extensions"] == [".png"]
    categories = get_all_categories()
    assert "JPEG" in categories["Images"]


def test_password_tools_public_api_intact():
    assert callable(extract_password_hashes)
    assert callable(generate_crackable_hash)
    assert callable(run_dictionary_attack)
    assert callable(analyze_password_strength)
    assert callable(check_hashcat_available)
    assert callable(check_john_available)
    assert callable(check_zip2john_available)
    assert callable(check_pdf2john_available)
    assert callable(list_common_wordlists)


def test_organizer_and_usage_kept_symbols_work():
    assert callable(Organizer.organize_files)
    assert callable(Organizer.delete_files)
    assert callable(analyze_size)
    assert callable(generate_usage_report)