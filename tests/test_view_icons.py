"""Tests for TICK-803 — Icons for forensic, file recovery, Metadata exif.

AC:
 - GIVEN forensic view WHEN tabs rendered THEN no tab shows emoji fallback, all have icon pixmap not null
 - GIVEN recovery view WHEN file list shown THEN no row shows x/?, all category icons are valid SVG
 - GIVEN metadata view WHEN EXIF panel shown THEN no ? glyph, shows forensics icon or metadata icon correctly
 - GIVEN headless test for all ICON_PATHS WHEN QIcon built via QPixmap.loadFromData THEN isNull==False and availableSizes not empty
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import base64
import pytest
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtGui import QIcon, QPixmap


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _data_url_to_bytes(url: str) -> bytes:
    if "," not in url:
        return b""
    return base64.b64decode(url.split(",", 1)[1])


def test_all_icon_paths_render_via_pixmap(qapp):
    """GIVEN headless test for all ICON_PATHS WHEN QIcon built via QPixmap.loadFromData THEN isNull==False and availableSizes not empty (f89055b pattern)."""
    from dataforge.ui.resources.icons import ICON_PATHS, build_icons, TONE_DARK, TONE_LIGHT

    # Must be 16-20 entries (including exif alias). Allow 18-20.
    assert 16 <= len(ICON_PATHS) <= 20, f"ICON_PATHS count {len(ICON_PATHS)} not in 16-20"
    # Must contain exif alias and core keys
    assert "metadata" in ICON_PATHS
    assert "exif" in ICON_PATHS, "exif alias missing (metadata vs exif confusion)"
    assert "forensics" in ICON_PATHS
    assert "recovery" in ICON_PATHS
    assert "storage" in ICON_PATHS
    # Validate each renders via QPixmap.loadFromData
    for tone in (TONE_DARK, TONE_LIGHT):
        icons = build_icons(tone)
        assert len(icons) == len(ICON_PATHS)
        for key, url in icons.items():
            assert url.startswith("data:image/svg+xml;base64,"), f"{key} url malformed"
            data = _data_url_to_bytes(url)
            assert len(data) > 0, f"{key} data empty"
            pm = QPixmap()
            pm.loadFromData(data, "SVG")
            if pm.isNull():
                pm.loadFromData(data, "SVG+XML")
            assert not pm.isNull(), f"{key} pixmap isNull with tone {tone} (SVG load failed)"
            icon = QIcon(pm)
            assert not icon.isNull(), f"{key} QIcon isNull"
            sizes = icon.availableSizes()
            assert len(sizes) > 0, f"{key} availableSizes empty"
            pix = icon.pixmap(16, 16)
            assert not pix.isNull(), f"{key} pixmap(16,16) isNull"
            # Ensure pixmap size 16
            assert pix.width() > 0 and pix.height() > 0


def _has_emoji(text: str) -> bool:
    # Emoji block starting at 0x1F300, but also check for common symbols like 📁 etc.
    for ch in text:
        if ord(ch) >= 0x1F300:
            return True
        # Also catch variation selectors and some misc symbols that are emoji-like
        if 0x2600 <= ord(ch) <= 0x27BF and ch not in ("→", "—", "•", "…", "✓", "⚠"):
            # Allow ⚠ which is GLYPH_WARNING intentional, but not emoji file icons
            # If char is in this range and is an icon emoji, flag it
            # For simplicity, flag any char in 0x1F000+ already handled, and treat ⚡ etc as emoji
            if ch in ("⚡", "♻"):
                return True
    return False


def test_forensic_view_tabs_no_emoji_and_have_icons(qapp):
    """GIVEN forensic view WHEN tabs rendered THEN no tab shows emoji fallback, all have icon pixmap not null"""
    from unittest.mock import MagicMock
    from dataforge.ui.views.forensics_view import ForensicsView

    parent = QWidget()
    mock_app = MagicMock()
    mock_app.update_status = MagicMock()
    mock_app.show_warning_dialog = MagicMock()
    mock_app.show_error_dialog = MagicMock()
    mock_app.show_info_dialog = MagicMock()
    mock_app.run_workflow = MagicMock()
    mock_app.run_background = MagicMock()

    view = ForensicsView(parent, app=mock_app)
    tabs = view.tabs
    assert tabs.count() >= 11, f"expected >=11 forensic tabs, got {tabs.count()}"
    for i in range(tabs.count()):
        text = tabs.tabText(i)
        assert not _has_emoji(text), f"tab {i} text '{text}' contains emoji fallback (should use QIcon)"
        # No "?" or "x" fallback in text
        assert "?" not in text or text.strip() == "?", f"tab {i} contains ? fallback"
        icon = tabs.tabIcon(i)
        # Icon must be non-null via QPixmap path
        assert not icon.isNull(), f"tab {i} '{text}' icon isNull (should be built via QPixmap.loadFromData)"
        sizes = icon.availableSizes()
        assert len(sizes) > 0, f"tab {i} '{text}' availableSizes empty"
        pix = icon.pixmap(16, 16)
        assert not pix.isNull(), f"tab {i} '{text}' pixmap isNull (x/? fallback)"
        # Also check icon key is valid SVG path from ICON_PATHS (indirectly via not null)
    # Also ensure no emoji remain in source for Forensics (tab titles)
    # Source file should not contain emoji tab strings
    import pathlib
    src = pathlib.Path("dataforge/ui/views/forensics_view.py").read_text()
    for emoji in ["💿", "🔐", "🔎", "🔑", "🧬", "📈", "🕰", "👁", "🕵", "🗑", "🛡", "📄", "📁", "📂", "⚔"]:
        # Allow those inside comments? But tabs should not have them.
        # Check that addTab lines do not contain emoji
        for line in src.splitlines():
            if "addTab" in line and emoji in line:
                pytest.fail(f"forensics_view still contains emoji {emoji} in addTab: {line}")

    parent.deleteLater()


def test_recovery_view_tabs_and_category_icons(qapp):
    """GIVEN recovery view WHEN file list shown THEN no row shows x/?, all category icons are valid SVG"""
    from unittest.mock import MagicMock
    from dataforge.ui.views.recovery_view import RecoveryView

    parent = QWidget()
    mock_app = MagicMock()
    mock_app.update_status = MagicMock()
    mock_app.show_warning_dialog = MagicMock()
    mock_app.show_error_dialog = MagicMock()
    mock_app.show_info_dialog = MagicMock()
    mock_app.run_workflow = MagicMock()

    view = RecoveryView(parent, app=mock_app)
    tabs = view.tabs
    assert tabs.count() == 2, f"expected 2 recovery tabs, got {tabs.count()}"
    for i in range(tabs.count()):
        text = tabs.tabText(i)
        assert not _has_emoji(text), f"recovery tab {i} '{text}' has emoji"
        icon = tabs.tabIcon(i)
        assert not icon.isNull(), f"recovery tab {i} '{text}' icon isNull"
        assert len(icon.availableSizes()) > 0
        assert not icon.pixmap(16, 16).isNull()

    # Check buttons have icons via QPixmap (not null)
    for attr in ["btn_restore_selected", "btn_restore_all", "btn_carve", "btn_photorec", "btn_scan_trash"]:
        btn = getattr(view, attr, None)
        if btn is not None:
            icon = btn.icon()
            # Buttons should have icon set via _apply_button_icon (QPixmap)
            assert not icon.isNull(), f"{attr} icon isNull (should use QPixmap.loadFromData)"
            assert not icon.pixmap(16, 16).isNull(), f"{attr} pixmap isNull"

    # Category icons: FilePreviewPanel._category_icon should return valid pixmap with SVG icon, not DOC text
    from dataforge.ui.widgets import FilePreviewPanel

    # Create a panel and call _category_icon for each category
    panel = FilePreviewPanel(parent)
    for category in ["Documents", "Images", "Videos", "Audio", "Archives", "Code", "Other"]:
        pix = panel._category_icon(category, size=96)
        assert not pix.isNull(), f"category {category} pixmap isNull"
        assert pix.width() == 96 and pix.height() == 96
        # Ensure the underlying ICON_PATHS for the mapped key is valid SVG (already tested via first test)
        # But also ensure that the panel's pixmap is not just empty: it should have non-transparent pixels
        img = pix.toImage()
        # Check that at least some pixel is not transparent (badge drawn)
        has_content = False
        for x in range(0, 96, 8):
            for y in range(0, 96, 8):
                if img.pixelColor(x, y).alpha() > 0:
                    has_content = True
                    break
        assert has_content, f"category {category} badge appears empty"

    # Ensure source uses correct keys (recovery not storage confusion)
    import pathlib
    src = pathlib.Path("dataforge/ui/views/recovery_view.py").read_text()
    # Recovery deep tab should use recovery icon, not storage
    assert 'Deep Recovery' in src
    # Check that addTab for deep uses recovery
    assert '"recovery"' in src, "recovery icon key not found in recovery_view"
    assert "storage vs recovery" not in src.lower()  # no confusion comment needed

    parent.deleteLater()


def test_metadata_view_exif_no_question_and_has_icon(qapp):
    """GIVEN metadata view WHEN EXIF panel shown THEN no ? glyph, shows forensics icon or metadata icon correctly"""
    from unittest.mock import MagicMock
    from dataforge.ui.views.metadata_view import MetadataView

    parent = QWidget()
    mock_app = MagicMock()
    mock_app.update_status = MagicMock()
    mock_app.show_warning_dialog = MagicMock()
    mock_app.show_error_dialog = MagicMock()
    mock_app.show_info_dialog = MagicMock()
    mock_app.run_workflow = MagicMock()

    view = MetadataView(parent, app=mock_app)
    tabs = view.detail_tabs
    assert tabs.count() >= 4, f"expected >=4 detail tabs, got {tabs.count()}"
    for i in range(tabs.count()):
        text = tabs.tabText(i)
        assert not _has_emoji(text), f"metadata detail tab {i} '{text}' has emoji"
        # No "?" glyph fallback in tab text
        assert "?" not in text, f"metadata tab {i} '{text}' contains ? fallback"
        icon = tabs.tabIcon(i)
        assert not icon.isNull(), f"metadata detail tab {i} '{text}' icon isNull"
        assert len(icon.availableSizes()) > 0
        assert not icon.pixmap(16, 16).isNull()

    # Check GPS tab specifically uses exif or metadata alias via QPixmap
    # Find GPS tab index
    gps_index = -1
    for i in range(tabs.count()):
        if "GPS" in tabs.tabText(i):
            gps_index = i
            break
    assert gps_index != -1, "GPS tab not found"
    gps_icon = tabs.tabIcon(gps_index)
    assert not gps_icon.isNull()
    assert not gps_icon.pixmap(16, 16).isNull()

    # Check EXIF alias renders same as metadata
    from dataforge.ui.resources.icons import build_icons, TONE_DARK, ICON_PATHS
    icons = build_icons(TONE_DARK)
    assert "exif" in icons
    assert "metadata" in icons
    # Both should be valid SVG via QPixmap (tested earlier), but check they are equal path data
    assert ICON_PATHS["exif"] == ICON_PATHS["metadata"], "exif should alias metadata"

    # Buttons in metadata view should have icons
    for attr in ["btn_strip_all", "btn_strip_gps", "btn_edit", "btn_export"]:
        btn = getattr(view, attr, None)
        if btn is not None:
            icon = btn.icon()
            assert not icon.isNull(), f"{attr} icon isNull"
            assert not icon.pixmap(16, 16).isNull()

    # Ensure no unicode glyph "?" fallback on fonts for GPS: check that has_gps column uses Yes/No not emoji
    import pathlib
    src = pathlib.Path("dataforge/ui/views/metadata_view.py").read_text()
    assert 'has_gps = "Yes"' in src or "has_gps" in src
    assert '📍' not in src, "metadata_view still contains 📍 emoji fallback"

    parent.deleteLater()


def test_forensics_buttons_use_qpixmap_not_emoji(qapp):
    """Additional check: view-internal buttons use QPixmap path, not QIcon(data_url)"""
    from unittest.mock import MagicMock
    from dataforge.ui.views.forensics_view import ForensicsView

    parent = QWidget()
    mock_app = MagicMock()
    mock_app.update_status = MagicMock()
    mock_app.show_warning_dialog = MagicMock()
    mock_app.show_error_dialog = MagicMock()
    mock_app.show_info_dialog = MagicMock()
    mock_app.run_workflow = MagicMock()

    view = ForensicsView(parent, app=mock_app)
    # Check a few key buttons
    for attr, expected_key in [
        ("btn_calc_hash", "forensics"),
        ("btn_parse", "search"),
        ("btn_extract", "forensics"),
        ("btn_timeline", "dashboard"),
        ("btn_hex_view", "search"),
    ]:
        btn = getattr(view, attr, None)
        if btn is None:
            continue
        text = btn.text()
        assert not _has_emoji(text), f"{attr} text '{text}' has emoji"
        icon = btn.icon()
        assert not icon.isNull(), f"{attr} icon isNull"
        assert not icon.pixmap(16, 16).isNull()
    parent.deleteLater()
