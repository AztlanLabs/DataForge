"""Tests for TICK-507 — HexView widget (U4)."""
import os
import struct
import time
import tempfile

import pytest

# Force offscreen platform before QApplication creation (needed for headless CI)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QColor

from dataforge.ui.widgets import HexView

# Ensure single QApplication for all tests
@pytest.fixture(scope="module")
def app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # Do not quit — other tests may need it

@pytest.fixture
def hexview(app):
    w = HexView()
    # Not shown — offscreen is fine
    yield w
    w.close()
    w.deleteLater()

def test_hexview_created_displays_hex_dump_correctly(hexview):
    data = b"Hello World\x00\xff\x01\x02" + b"A"*16 + b"B"*16
    hexview.set_data(data, offset=0)
    # Check hex_display plain text
    text = hexview.hex_display.toPlainText()
    assert text != ""
    lines = text.split("\n")
    # First line offset 00000000
    assert lines[0].startswith("00000000")
    # Contains hex for 'H' (0x48) and 'e' (0x65)
    assert "48 65 6c 6c 6f" in lines[0].lower()
    # Contains ascii Hello
    assert "Hello" in text
    # Offset increments by 16 bytes per row
    if len(data) > 16:
        assert lines[1].startswith("00000010")  # 16 decimal = 0x10
    # get_hex_lines helper should match display
    helper_lines = hexview.get_hex_lines()
    assert helper_lines[0] == lines[0]
    # Size label updated
    assert f"{len(data)}" in hexview.size_label.text()
    assert "0x00000000" in hexview.offset_label.text()

def test_hexview_with_offset_displays_correct_offset(hexview):
    data = b"ABCD" * 4
    hexview.set_data(data, offset=0x1000)
    text = hexview.hex_display.toPlainText()
    lines = text.split("\n")
    assert lines[0].startswith("00001000")
    # Next row if exists should be 0x1010
    if len(data) > 16:
        assert "00001010" in text

def test_hexview_selection_highlights_both_columns(hexview):
    data = b"0123456789ABCDEF" * 2  # 32 bytes, 2 rows
    hexview.set_data(data, offset=0)
    # Select byte 0
    hexview.select_byte(0)
    assert hexview.get_selected_byte() == 0
    # Extra selections should be 2 (hex + ascii)
    selections = hexview.hex_display.extraSelections()
    # In some cases only hex+ascii (2), for first row both should be present
    assert len(selections) == 2, f"expected 2 extra selections, got {len(selections)}"
    # Verify highlight color yellow
    for sel in selections:
        assert sel.format.background().color().name() == QColor("#ffeb3b").name()
    # Select byte in second row, col 5
    hexview.select_byte(21)
    assert hexview.get_selected_byte() == 21
    selections2 = hexview.hex_display.extraSelections()
    assert len(selections2) >= 1
    # Label should update to show selected offset
    assert "0x00000015" in hexview.lbl_selected.text() or "21" in hexview.lbl_selected.text()

def test_selection_updates_field_inspector(hexview):
    data = b"\x00\x01\x02\x03\x04\x05"
    hexview.set_data(data, offset=0)
    # No selection -> file overview
    assert hexview.field_inspector.topLevelItemCount() >= 1
    hexview.select_byte(1)
    # Inspector should now show Byte field with value 0x01
    items = [hexview.field_inspector.topLevelItem(i).text(0) for i in range(hexview.field_inspector.topLevelItemCount())]
    assert "Byte" in items
    # Find Byte item value
    for i in range(hexview.field_inspector.topLevelItemCount()):
        it = hexview.field_inspector.topLevelItem(i)
        if it.text(0) == "Byte":
            assert "0x01" in it.text(1).lower()
            break
    else:
        pytest.fail("Byte inspector item not found")

def test_field_inspector_shows_structured_interpretation_mbr(hexview):
    # Build fake MBR: 512 bytes, boot signature 55 AA, one partition entry
    data = bytearray(512)
    data[510] = 0x55
    data[511] = 0xAA
    # Partition 1 at 446: status 0x80, type 0x07 (NTFS), LBA 2048, sectors 100000
    data[446] = 0x80
    data[450] = 0x07
    struct.pack_into("<I", data, 454, 2048)
    struct.pack_into("<I", data, 458, 100000)
    hexview.set_data(bytes(data), offset=0)
    hexview.select_byte(0)
    # Inspector at offset 0 should contain MBR Signature
    texts = []
    for i in range(hexview.field_inspector.topLevelItemCount()):
        item = hexview.field_inspector.topLevelItem(i)
        texts.append((item.text(0), item.text(1), item.text(2)))
    # Check MBR signature present
    assert any("MBR Signature" in t[0] for t in texts), f"No MBR Signature in {texts}"
    # Check Partition entry
    assert any("Partition 1" in t[0] for t in texts), f"No Partition 1 in {texts}"

def test_field_inspector_shows_elf(hexview):
    # Build ELF header minimal
    data = bytearray(64)
    data[0:4] = b"\x7fELF"
    data[4] = 2  # 64-bit
    data[5] = 1  # LE
    data[16:18] = (2).to_bytes(2, "little")  # ET_EXEC
    data[18:20] = (62).to_bytes(2, "little")  # x86-64
    hexview.set_data(bytes(data), offset=0)
    hexview.select_byte(0)
    texts = [(hexview.field_inspector.topLevelItem(i).text(0), hexview.field_inspector.topLevelItem(i).text(1)) for i in range(hexview.field_inspector.topLevelItemCount())]
    assert any("ELF Magic" in t[0] for t in texts)
    assert any("ELF Class" in t[0] for t in texts)

def test_field_inspector_shows_pe(hexview):
    data = bytearray(256)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 60, 0x80)  # e_lfanew
    data[0x80:0x84] = b"PE\x00\x00"
    struct.pack_into("<H", data, 0x84, 0x8664)  # machine AMD64
    struct.pack_into("<H", data, 0x86, 3)  # num sections
    hexview.set_data(bytes(data), offset=0)
    hexview.select_byte(0)
    texts = [(hexview.field_inspector.topLevelItem(i).text(0), hexview.field_inspector.topLevelItem(i).text(1)) for i in range(hexview.field_inspector.topLevelItemCount())]
    assert any("DOS Magic" in t[0] for t in texts)
    assert any("e_lfanew" in t[0] for t in texts)
    assert any("PE Signature" in t[0] for t in texts)

def test_large_file_remains_responsive(hexview):
    # 2 MiB file — should not render all bytes, only MAX_DISPLAY_BYTES
    large = b"A" * (2 * 1024 * 1024)  # 2 MB
    start = time.monotonic()
    hexview.set_data(large, offset=0)
    elapsed = time.monotonic() - start
    # Should be fast (<0.5s ideally, allow 1s for CI)
    assert elapsed < 1.0, f"Large file display took {elapsed:.2f}s, should be <1s"
    text = hexview.hex_display.toPlainText()
    lines = text.split("\n")
    # Display should be truncated, not full 2MB /16 = 131k lines
    assert len(lines) < 5000, f"Expected truncated display, got {len(lines)} lines"
    assert "truncated" in text.lower()
    # Inspector should still work
    hexview.select_byte(0)
    assert hexview.get_selected_byte() == 0
    # Selecting beyond displayed window should clear highlight but still set selection?
    # Our implementation clears highlight if beyond max but keeps selected_byte
    hexview.select_byte(100000)  # beyond 64KiB
    # Should still set selected byte but extraSelections empty (since not displayed)
    assert hexview.get_selected_byte() == 100000
    # Extra selections empty because not in view window
    assert len(hexview.hex_display.extraSelections()) == 0

def test_hexview_empty_data(hexview):
    hexview.set_data(b"", offset=0)
    # Should show no crash, maybe placeholder in inspector
    assert hexview.field_inspector.topLevelItemCount() >= 1
    # Selecting invalid should clear
    hexview.select_byte(5)
    assert hexview.get_selected_byte() == -1

def test_hexview_ascii_column(hexview):
    # Check that non-printable becomes '.'
    data = b"\x00\x01\x20\x41\xff"  # NUL, SOH, space, 'A', 0xff
    hexview.set_data(data, offset=0)
    text = hexview.hex_display.toPlainText()
    # ASCII column is after "|...|"
    # Space (0x20) should be ' ', 'A' should be 'A', others '.' => " ..A."
    # Our data 5 bytes: chunk ".. A."? Actually space is printable (32) so kept as ' ', so => ".. A." where first two are '.' then ' ' then 'A' then '.'
    assert "|.. A.|" in text or ".. A." in text

def test_hexview_offset_display_and_navigation(hexview):
    data = b"X"*100
    hexview.set_data(data, offset=0x1234)
    assert "0x00001234" in hexview.offset_label.text()
    hexview.select_byte(10)
    # After selection, offset_label should show selected absolute offset
    assert "0x0000123e" in hexview.offset_label.text().lower()  # 0x1234 +10 =0x123e
    # Spin should be synced
    assert hexview.spin_offset.value() == 10
    # Test set_offset changes base
    hexview.set_offset(0x2000)
    assert "0x00002000" in hexview.offset_label.text() or hexview.get_offset() == 0x2000
    # Display should update to new offset
    text = hexview.hex_display.toPlainText()
    assert "00002000" in text

def test_hexview_load_file_roundtrip(hexview):
    # Create temp file and load via load_file
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(b"HELLOFILE" * 10)
        fname = tf.name
    try:
        hexview.load_file(fname, max_bytes=20, offset=0)
        assert len(hexview.get_data()) == 20
        assert b"HELLO" in hexview.get_data()
        text = hexview.hex_display.toPlainText()
        assert "48 45 4c 4c 4f" in text.lower()  # HELLO hex
    finally:
        os.unlink(fname)

def test_hexview_bytes_per_row(hexview):
    data = b"0"*32
    hexview.set_data(data, offset=0)
    hexview.set_bytes_per_row(8)
    assert hexview.get_bytes_per_row() == 8
    lines = hexview.get_hex_lines()
    # With 32 bytes and 8 per row, should be 4 rows
    assert len(lines) == 4
    # Each line hex area padded but should contain 8 bytes
    assert lines[0].count("30") == 8  # '0' is 0x30

def test_hexview_wide_data_does_not_crash(hexview):
    # Edge: single byte
    hexview.set_data(b"\x42", offset=0)
    assert "42" in hexview.hex_display.toPlainText().lower()
    hexview.select_byte(0)
    assert hexview.field_inspector.topLevelItemCount() > 0
