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
