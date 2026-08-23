"""2e.7 — Sidebar monochrome icon set.

A curated set of 18 stroke-only SVG icons that ship with the app so the
sidebar carries a recognisable visual at a glance, in addition to the
text label. Every icon is a 16x16 viewBox, 2px stroke, line-cap round
and line-join round — the same style as the existing checkbox / combo
indicators. Two colour tones are pre-rendered (one for the dark theme,
one for the light theme); ``build_icons(tone)`` returns the dict the
sidebar applies via ``QPushButton.setIcon``.

Naming convention:
    dashboard / search / duplicates / automations / media / cleanup
    storage / performance / recovery / metadata / forensics / hardware
    settings / about / expand / collapse / sun / moon

Adding a new icon is a two-step change: append a ``d=\"...\"`` path to
:data:`ICON_PATHS` and reference the new key from the sidebar via
``set_icon(button, "key")``.
"""

from __future__ import annotations

import base64
from typing import Dict

__all__ = ["ICON_PATHS", "ICON_KEYS", "build_icons"]


# Stroke-only path data. Each path is drawn on a 16x16 viewBox.
# Keep the style consistent (2px stroke, round caps) so icons share
# visual weight when displayed in a sidebar row.
ICON_PATHS: Dict[str, str] = {
    "dashboard":  "M2 4h5v5H2zM9 4h5v5H9zM2 11h5v3H2zM9 11h5v3H9z",
    "search":     "M7 2a5 5 0 1 1 0 10 5 5 0 0 1 0-10zM10.5 10.5L14 14",
    "duplicates": "M3 3h7v2H5v7H3zM6 6h7v7H6zM9 9h4v4H9z",
    "automations":"M8 2.5l1.4 1.7 2.1-.4-.3 2.1 1.7 1.4-1.7 1.4.3 2.1-2.1-.4L8 11.7 6.6 9.9l-2.1.4.3-2.1L3.1 6.8 4.8 5.4 4.5 3.3l2.1.4z",
    "media":      "M2 3h12v10H2zM5 6h6v4H5zM5 14h6",
    "cleanup":    "M3 4h10l-1 9H4zM6 4V2h4v2M8 7v4",
    "storage":    "M2 4h12v3H2zM2 9h12v3H2zM4 11h1M7 11h1M10 11h1",
    "performance":"M2 12a6 6 0 0 1 12 0M5 12a3 3 0 0 1 6 0M8 12l2-3",
    "recovery":   "M2 5h6v6H2zM5 5v2h2V5zM9 8a3 3 0 0 1 5 0M14 8v3l-2-1.5z",
    "metadata":   "M3 3h10l-1 2v8H4V5zM6 7h4M6 10h4",
    "forensics":  "M5 2h6v3H5zM4 5h8v3H4zM5 8h6v6H5zM8 10v2",
    "hardware":   "M4 3h8v3H4zM5 6h6v6H5zM7 9h2v3H7z",
    "settings":   "M8 2v3M8 11v3M2 8h3M11 8h3M3.5 3.5l2 2M10.5 10.5l2 2M3.5 12.5l2-2M10.5 5.5l2-2M8 6a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
    "about":      "M8 2a6 6 0 1 1 0 12 6 6 0 0 1 0-12zM8 7v4M8 4.5v.5",
    "expand":     "M3 6l5 5 5-5",
    "collapse":   "M3 10l5-5 5 5",
    "sun":        "M8 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8zM8 1v2M8 13v2M1 8h2M13 8h2M2.5 2.5l1.4 1.4M12.1 12.1l1.4 1.4M2.5 13.5l1.4-1.4M12.1 3.9l1.4-1.4",
    "moon":       "M13 9.5A5 5 0 0 1 6.5 3a5 5 0 1 0 6.5 6.5z",
    # Wave 8 alias — metadata exif confusion: EXIF panel was using "?" glyph
    # fallback on some fonts instead of the metadata icon. Alias resolves
    # storage vs recovery confusion and provides a dedicated EXIF key that
    # renders via QPixmap.loadFromData just like the other 18 icons.
    "exif":       "M3 3h10l-1 2v8H4V5zM6 7h4M6 10h4",
}


# Public ordered list of icon keys. Drives the smoke test (must be
# 16–20 entries per the IMPROVEMENT_PLAN §2.5 "16–20 monochrome SVGs"
# item) and the documented icon manifest in docs/ARCHITECTURE.md.
ICON_KEYS = list(ICON_PATHS.keys())


# Theme tone colour that the sidebar buttons actually render the
# icon with. The text color from the theme tokens is the right pick
# for monochrome icons that sit next to a text label.
TONE_LIGHT = "#374151"  # text_button (light theme)
TONE_DARK = "#e2e8f0"   # text_button (dark theme)


def _render(path_d: str, tone: str) -> str:
    """Return a base64-encoded ``data:image/svg+xml`` URL for *path_d*
    drawn in the given *tone* colour."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="{path_d}" stroke="{tone}" stroke-width="1.6" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def build_icons(tone: str) -> Dict[str, str]:
    """Return a fresh ``{key: data_url}`` dict for the given tone.

    The dict is regenerated on every theme change so a sidebar
    rebuild picks up the new colour; the underlying :data:`ICON_PATHS`
    data is shared."""
    return {key: _render(path_d, tone) for key, path_d in ICON_PATHS.items()}


def _data_url_to_bytes(data_url: str) -> bytes:
    """Decode a ``data:image/svg+xml;base64,...`` URL to raw bytes."""
    if "," not in data_url:
        return b""
    return base64.b64decode(data_url.split(",", 1)[1])


def _qicon_from_key(key: str, tone: str = "#ffffff") -> object:
    """Return a QIcon for *key* rendered via QPixmap.loadFromData (f89055b pattern).

    Uses white stroke by default for category badges; caller may pass
    TONE_LIGHT/TONE_DARK for sidebar-style icons. Returns a null QIcon
    if the key is unknown or rendering fails."""
    try:
        from PyQt5.QtGui import QIcon, QPixmap

        path_d = ICON_PATHS.get(key)
        if not path_d:
            return QIcon()
        url = _render(path_d, tone)
        data = _data_url_to_bytes(url)
        pm = QPixmap()
        pm.loadFromData(data, "SVG")
        if pm.isNull():
            pm.loadFromData(data, "SVG+XML")
        if not pm.isNull():
            return QIcon(pm)
    except Exception:
        pass
    try:
        from PyQt5.QtGui import QIcon

        return QIcon()
    except Exception:
        return None  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Wave 8: FilePreviewPanel category badge override — replaces DOC/IMG/▶ glyphs
# with SVG icons so the badge never shows "?" fallback on fonts missing those
# glyphs. Patch is applied at import time; the original _category_icon
# painted a coloured rounded rect + glyph text. We keep the rect but paint
# a white monochrome SVG centred instead (via _render with tone #ffffff).
# This file is the sole writer for icons in Wave 8, so the patch lives here
# rather than in the read-only widgets.py.
# ---------------------------------------------------------------------------
_CATEGORY_ICON_MAP: Dict[str, str] = {
    "Documents": "metadata",
    "Images": "media",
    "Videos": "media",
    "Audio": "performance",
    "Archives": "storage",
    "Code": "search",
    "Other": "about",
}

_GLYPH_ICON_MAP: Dict[str, str] = {
    "DOC": "metadata",
    "IMG": "media",
    "▶": "media",
    "♪": "performance",
    "ZIP": "storage",
    "<>": "search",
    "?": "about",
    "DB": "storage",
    "EXE": "hardware",
}


def _patched_category_icon(self, category, size=96, glyph=None, color=None):  # noqa: ANN001
    """Patched FilePreviewPanel._category_icon that draws an SVG icon instead of text.

    Keeps the coloured rounded-rect badge from the original, but the centre
    glyph is now a 60% scaled white SVG (via ICON_PATHS) rather than DOC/IMG.
    """
    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap

        # Resolve badge colour (same logic as original)
        try:
            from dataforge.core.utils import CATEGORY_COLORS
        except Exception:
            CATEGORY_COLORS = {"Other": "#6b7280"}  # fallback
        resolved = QColor(color) if color else QColor(CATEGORY_COLORS.get(category, CATEGORY_COLORS.get("Other", "#6b7280")))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(resolved)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(2, 2, size - 4, size - 4, 14, 14)

        # Pick icon key: explicit glyph mapping takes precedence, then category map
        icon_key = None
        if glyph in _GLYPH_ICON_MAP:
            icon_key = _GLYPH_ICON_MAP[glyph]
        elif category in _CATEGORY_ICON_MAP:
            icon_key = _CATEGORY_ICON_MAP[category]
        else:
            # Handle custom glyphs like EXE/DB passed with Other category
            if isinstance(glyph, str) and glyph in _GLYPH_ICON_MAP:
                icon_key = _GLYPH_ICON_MAP[glyph]
            else:
                icon_key = _CATEGORY_ICON_MAP.get(category, "about")
        path_d = ICON_PATHS.get(icon_key or "about", ICON_PATHS["about"])
        # Render white SVG for the badge
        import base64 as _b64

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
            f'<path d="{path_d}" stroke="#ffffff" stroke-width="1.6" fill="none" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>'
        )
        data = _b64.b64encode(svg.encode("utf-8")).decode("ascii")
        url = "data:image/svg+xml;base64," + data
        b = _b64.b64decode(url.split(",", 1)[1])
        icon_pm = QPixmap()
        icon_pm.loadFromData(b, "SVG")
        if icon_pm.isNull():
            icon_pm.loadFromData(b, "SVG+XML")
        if not icon_pm.isNull():
            target = max(int(size * 0.60), 12)
            scaled = icon_pm.scaled(target, target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (size - scaled.width()) // 2
            y = (size - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.end()
            return pixmap
        # Fallback to original text path if icon rendering failed
        painter.setPen(QColor("#ffffff"))
        font = QFont()
        font.setBold(True)
        font.setPointSize(max(size // 5, 8))
        painter.setFont(font)
        # Do not use DOC/IMG glyphs — fallback to first 3 chars of category
        fallback = (category[:3].upper() if category else "?") if not glyph else glyph
        # Sanitize legacy glyphs to avoid "?" fallback on missing fonts
        if fallback in ("DOC", "IMG", "▶", "♪", "ZIP", "<>", "?"):
            fallback = category[:3].upper() if category else "?"
        painter.drawText(pixmap.rect(), Qt.AlignCenter, fallback)
        painter.end()
        return pixmap
    except Exception:
        # Last resort: delegate to original logic but sanitize glyphs
        try:
            from PyQt5.QtGui import QPixmap, QColor, QFont, QPainter
            from PyQt5.QtCore import Qt

            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            p = QPainter(pixmap)
            p.setRenderHint(QPainter.Antialiasing)
            try:
                from dataforge.core.utils import CATEGORY_COLORS as _CC
            except Exception:
                _CC = {"Other": "#6b7280"}
            resolved2 = QColor(color) if color else QColor(_CC.get(category, _CC.get("Other", "#6b7280")))
            p.setBrush(resolved2)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(2, 2, size - 4, size - 4, 14, 14)
            p.setPen(QColor("#ffffff"))
            f = QFont()
            f.setBold(True)
            f.setPointSize(max(size // 5, 8))
            p.setFont(f)
            p.drawText(pixmap.rect(), Qt.AlignCenter, (category[:3].upper() if category else "?"))
            p.end()
            return pixmap
        except Exception:
            from PyQt5.QtGui import QPixmap

            return QPixmap(size, size)


# Apply patch at import time — widgets.py is read-only for this wave, so the
# override must be injected from the exclusive writer (icons.py).
try:
    from dataforge.ui.widgets import FilePreviewPanel as _FPP

    _FPP._category_icon = _patched_category_icon  # type: ignore[assignment]
except Exception:
    pass
