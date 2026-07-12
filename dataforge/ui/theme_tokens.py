"""Design-token module — single source of truth for colour, typography, QSS generation, and palette creation.

This module replaces the two hand-written ~200-line QSS blocks (``LIGHT_STYLE``/``DARK_STYLE``) and the
``_build_palette``/``LIGHT_PALETTE``/``DARK_PALETTE`` machinery that previously lived in ``app.py`` with a
single semantic-token table plus template-driven generation.

Public API
----------
``TOKENS`` — ``{theme: {token_name: hex_value}}`` — the validated, AA-contrast-checked colour table.
``TYPE_SCALE`` — named font-size constants (caption / body / subheading / heading / display).
``FONT_FAMILY`` / ``FONT_FAMILY_MONO`` — the two font stacks used across the app.
``generate_qss(mode)`` — returns the full application stylesheet string for ``"light"`` or ``"dark"``.
``generate_palette(mode)`` — returns a ``QPalette`` for ``"light"`` or ``"dark"``.

Acceptance gates (doc 05 §8)
----------------------------
* ``generate_qss`` produces both themes from the same template — no 200-line hand-written blocks.
* No Bootstrap-era legacy hex literals (``#d9534f``, ``#5cb85c``, etc.) appear inside the QSS output.
* The two measured WCAG failures (``#5bc0de``, ``#ffc107``) are gone — replaced by the validated AA table.
* All surface/text token pairs clear ≥4.5:1 contrast for body-size text.
"""

from __future__ import annotations

import base64
from string import Template

__all__ = [
    "TOKENS",
    "TYPE_SCALE",
    "FONT_FAMILY",
    "FONT_FAMILY_MONO",
    "SEMANTIC_TOKEN_NAMES",
    "generate_qss",
    "generate_palette",
]

# ---------------------------------------------------------------------------
# Colour token table
# ---------------------------------------------------------------------------
# Every value was validated against the WCAG relative-luminance formula (doc 05 §1.2/§1.4).
# Surface/text pairs all clear ≥4.5:1. The semantic accent tokens (primary, success, warning,
# danger, info) clear ≥4.5:1 on their respective surfaces in both themes (see doc 05's table).

TOKENS: dict[str, dict[str, str]] = {
    "light": {
        # --- Surfaces ---
        "window_bg":          "#f3f4f6",
        "surface":            "#f7f7f8",
        "surface_elevated":   "#ffffff",
        "surface_hover":      "#f9fafb",
        "surface_pressed":    "#f3f4f6",
        "surface_selected":   "#eff6ff",

        # --- Text ---
        "text":               "#1f2937",
        "text_button":        "#374151",
        "text_muted":         "#4b5563",
        "text_hover":         "#111827",
        "text_selected":      "#1d4ed8",
        "text_mono":          "#4b5563",

        # --- Borders ---
        "border":             "#e5e7eb",
        "border_strong":      "#d1d5db",
        "border_hover":       "#9ca3af",
        "border_item":        "#f3f4f6",
        "border_scrollbar":   "#f1f5f9",
        "handle_scrollbar":   "#cbd5e1",
        "handle_scrollbar_hover": "#94a3b8",

        # --- Accents ---
        "primary":            "#2563eb",
        "accent_focus":       "#3b82f6",

        # --- Semantic (validated AA — doc 05 §1.4) ---
        "danger":             "#dc2626",
        "danger_bg":          "#ef4444",
        "danger_hover":       "#dc2626",
        "success":            "#047857",
        "warning":            "#b45309",
        "info":               "#0369a1",

        # --- Tooltip ---
        "tooltip_base":       "#ffffff",

        # --- Text on semantic-coloured buttons ---
        "text_on_semantic":   "#ffffff",

        # --- Checkbox / spinbox / combo indicators ---
        "indicator_border":   "#d1d5db",
        "indicator_bg":       "#ffffff",
        "indicator_accent":   "#3b82f6",
        "indicator_btn_bg":   "#ffffff",
        "indicator_arrow":    "#374151",
        "indicator_disabled": "#f3f4f6",

        # --- Palette (QPalette values) ---
        "pal_window":          "#f3f4f6",
        "pal_window_text":     "#1f2937",
        "pal_base":            "#ffffff",
        "pal_alt_base":        "#f9fafb",
        "pal_text":             "#1f2937",
        "pal_button":         "#ffffff",
        "pal_button_text":    "#374151",
        "pal_highlight":      "#3b82f6",
        "pal_highlighted_text": "#ffffff",
        "pal_tooltip_base":   "#ffffff",
        "pal_tooltip_text":   "#1f2937",
    },
    "dark": {
        # --- Surfaces ---
        "window_bg":          "#1c1c20",
        "surface":            "#1c1c20",
        "surface_elevated":   "#26262c",
        "surface_hover":      "#242429",
        "surface_pressed":    "#3f3f46",
        "surface_selected":   "#2e2a47",

        # --- Text ---
        "text":               "#e2e8f0",
        "text_button":        "#e2e8f0",
        "text_muted":         "#a1a1aa",
        "text_hover":         "#ffffff",
        "text_selected":      "#a5b4fc",
        "text_mono":          "#fbbf24",

        # --- Borders ---
        "border":             "#27272a",
        "border_strong":      "#3f3f46",
        "border_hover":       "#52525b",
        "border_item":        "#242429",
        "border_scrollbar":   "#18181b",
        "handle_scrollbar":   "#3f3f46",
        "handle_scrollbar_hover": "#52525b",

        # --- Accents ---
        "primary":            "#818cf8",
        "accent_focus":       "#6366f1",

        # --- Semantic ---
        "danger":             "#f87171",
        "danger_bg":          "#ef4444",
        "danger_hover":       "#dc2626",
        "success":            "#34d399",
        "warning":            "#fbbf24",
        "info":               "#38bdf8",

        # --- Tooltip ---
        "tooltip_base":       "#26262c",

        # --- Text on semantic-coloured buttons ---
        "text_on_semantic":   "#1c1c20",

        # --- Checkbox / spinbox / combo indicators ---
        "indicator_border":   "#3f3f46",
        "indicator_bg":       "#242429",
        "indicator_accent":   "#6366f1",
        "indicator_btn_bg":   "#1f1f23",
        "indicator_arrow":    "#e2e8f0",
        "indicator_disabled": "#1c1c20",

        # --- Palette (QPalette values) ---
        "pal_window":          "#1c1c20",
        "pal_window_text":     "#e2e8f0",
        "pal_base":            "#26262c",
        "pal_alt_base":        "#242429",
        "pal_text":             "#e2e8f0",
        "pal_button":          "#1f1f23",
        "pal_button_text":     "#e2e8f0",
        "pal_highlight":      "#6366f1",
        "pal_highlighted_text": "#ffffff",
        "pal_tooltip_base":    "#26262c",
        "pal_tooltip_text":    "#e2e8f0",
    },
}

# Semantic token names that per-widget dynamic-property rules reference (doc 05 §1.4 / Phase 2b.2).
# These are the "public" tokens — the rest drive QSS internals.
SEMANTIC_TOKEN_NAMES = frozenset({
    "primary", "success", "warning", "danger", "info",
})

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------
# doc 05 §2: 4–5 named sizes with a fixed weight pairing.
# All existing ``font-size: Npx`` literals map onto one of these five (10→caption, 11→caption,
# 12→body, 13→body, 14→subheading, 15→subheading, 16→heading, 18→heading, 20→display).

TYPE_SCALE: dict[str, int] = {
    "caption": 11,
    "body": 13,
    "subheading": 15,
    "heading": 18,
    "display": 24,
}

FONT_FAMILY = '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
FONT_FAMILY_MONO = '"Courier New", Consolas, monospace'

# ---------------------------------------------------------------------------
# SVG glyph helpers (moved from app.py)
# ---------------------------------------------------------------------------

def _stroke_svg_b64(path_d: str, stroke: str) -> str:
    """Embed a stroke-only SVG path as a base64 data URL for QSS ``image:``."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        f'<path d="{path_d}" stroke="{stroke}" stroke-width="2" fill="none" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )
    return base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _fill_svg_b64(path_d: str, fill: str) -> str:
    """Embed a fill-only SVG path as a base64 data URL for QSS ``image:``."""
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="{path_d}" fill="{fill}"/></svg>'
    return base64.b64encode(svg.encode("utf-8")).decode("ascii")


# ---------------------------------------------------------------------------
# QSS template
# ---------------------------------------------------------------------------
# One template produces both themes — only the token values differ.
# Uses ``string.Template`` ($token) so literal CSS braces ``{ }`` don't need escaping.

_QSS_TEMPLATE = Template("""
QMainWindow {
    background-color: $window_bg;
}
QWidget {
    font-family: $font_family;
    font-size: ${font_body}px;
    color: $text;
}
QFrame#navFrame {
    background-color: $surface;
    border-right: 1px solid $border;
}
QFrame#navFrame QPushButton {
    background-color: transparent;
    color: $text_muted;
    border: none;
    border-left: 3px solid transparent;
    padding: 12px 16px;
    border-radius: 0px;
    text-align: left;
    font-weight: 500;
}
QFrame#navFrame QPushButton:hover {
    background-color: $surface_hover;
    color: $text_hover;
}
QFrame#navFrame QPushButton:checked {
    background-color: $surface_selected;
    color: $primary;
    border-left: 3px solid $primary;
    font-weight: 600;
}
QFrame#navFrame QPushButton[compact="true"] {
    text-align: center;
    padding: 12px 0px;
}
QPushButton {
    background-color: $surface_elevated;
    color: $text_button;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
    text-align: center;
}
QPushButton:hover {
    background-color: $surface_hover;
    border-color: $border_hover;
}
QPushButton:pressed {
    background-color: $surface_pressed;
}
QPushButton#stopBtn {
    background-color: $danger_bg;
    color: #ffffff;
    font-weight: bold;
    border: none;
}
QPushButton#stopBtn:hover {
    background-color: $danger_hover;
}
/* --- Semantic-variant buttons (per-widget setProperty("variant", ...)) --- */
/* Drives the 2b.2 migration: replaces per-widget setStyleSheet("#hex; color:#hex") */
QPushButton[variant="danger"] {
    background-color: $danger;
    color: $text_on_semantic;
    border: none;
}
QPushButton[variant="danger"]:hover {
    background-color: $danger_hover;
}
QPushButton[variant="success"] {
    background-color: $success;
    color: $text_on_semantic;
    border: none;
}
QPushButton[variant="warning"] {
    background-color: $warning;
    color: $text_on_semantic;
    border: none;
}
QPushButton[variant="info"] {
    background-color: $info;
    color: $text_on_semantic;
    border: none;
}
QPushButton[variant="primary"] {
    background-color: $primary;
    color: $text_on_semantic;
    border: none;
}
QGroupBox {
    font-weight: 600;
    font-size: ${font_subheading}px;
    border: 1px solid $border;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    background-color: $surface;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: $text_muted;
}
QLineEdit, QSpinBox, QComboBox {
    background-color: $surface_elevated;
    color: $text;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 6px 10px;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: $accent_focus;
    background-color: $surface_elevated;
}
QTreeWidget, QTreeView, QListWidget, QTextEdit {
    background-color: $surface;
    color: $text;
    border: 1px solid $border;
    border-radius: 8px;
}
QTreeView::item {
    padding: 6px;
    border-bottom: 1px solid $border_item;
}
QTreeView::item:hover {
    background-color: $surface_hover;
}
QTreeView::item:selected {
    background-color: $surface_selected;
    color: $text_selected;
}
QHeaderView::section {
    background-color: $surface_hover;
    color: $text_muted;
    padding: 8px;
    border: none;
    border-bottom: 1px solid $border;
    font-weight: 600;
}
QTabBar::tab {
    background-color: $surface_pressed;
    color: $text_muted;
    padding: 10px 16px;
    border: 1px solid $border;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background-color: $surface;
    color: $primary;
    border-bottom: 2px solid $primary;
    font-weight: 600;
}
QProgressBar {
    border: 1px solid $border;
    border-radius: 6px;
    text-align: center;
    background-color: $surface_pressed;
    font-weight: bold;
}
QProgressBar::chunk {
    background-color: $accent_focus;
    border-radius: 5px;
}
QLabel#dashboardFileSize {
    color: $text_mono;
    font-family: $font_family_mono;
}
QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    border: none;
    background: $border_scrollbar;
    width: 10px;
    margin: 0px 0px 0px 0px;
}
QScrollBar::handle:vertical {
    background: $handle_scrollbar;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: $handle_scrollbar_hover;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    border: none;
    background: $border_scrollbar;
    height: 10px;
    margin: 0px 0px 0px 0px;
}
QScrollBar::handle:horizontal {
    background: $handle_scrollbar;
    min-width: 20px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover {
    background: $handle_scrollbar_hover;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QTabWidget::pane {
    border: 1px solid $border;
    background-color: $surface;
    border-radius: 6px;
}
QTabWidget > QWidget {
    background-color: $surface;
}
QLabel#mutedLabel {
    color: $text_muted;
}
QLabel[class="muted"] {
    color: $text_muted;
}
/* --- Semantic-coloured labels (category headers in Action Builder etc.) --- */
QLabel[variant="primary"] {
    color: $primary;
    font-weight: bold;
}
QLabel[variant="success"] {
    color: $success;
    font-weight: bold;
}
QLabel[variant="warning"] {
    color: $warning;
    font-weight: bold;
}
QLabel[variant="danger"] {
    color: $danger;
    font-weight: bold;
}
QLabel[variant="info"] {
    color: $info;
    font-weight: bold;
}
QFrame#navFrame QPushButton#groupHeader {
    background-color: transparent;
    border: none;
    font-weight: bold;
    font-size: ${font_caption}px;
    text-align: left;
    padding: 16px 16px 4px 16px;
    border-left: none;
    text-transform: uppercase;
}
QFrame#navFrame QPushButton#groupHeader:hover {
    background-color: transparent;
}
QFrame#navFrame QPushButton#groupHeader:checked {
    background-color: transparent;
    border-left: none;
}
""")

# ---------------------------------------------------------------------------
# Checkbox / spinbox / combo indicator sub-template
# ---------------------------------------------------------------------------

_INDICATOR_TEMPLATE = Template("""
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid $indicator_border;
    border-radius: 3px;
    background-color: $indicator_bg;
}
QCheckBox::indicator:hover {
    border-color: $indicator_accent;
}
QCheckBox::indicator:checked {
    background-color: $indicator_accent;
    border-color: $indicator_accent;
    image: url(data:image/svg+xml;base64,$check_svg_b64);
}
QCheckBox::indicator:disabled {
    background-color: $indicator_disabled;
    border-color: $indicator_border;
}
QSpinBox::up-button, QSpinBox::down-button {
    background-color: $indicator_btn_bg;
    border: 1px solid $indicator_border;
    width: 16px;
}
QSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    border-top-right-radius: 6px;
}
QSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    border-bottom-right-radius: 6px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background-color: $indicator_accent;
}
QSpinBox::up-arrow {
    width: 8px;
    height: 8px;
    image: url(data:image/svg+xml;base64,$up_arrow_svg_b64);
}
QSpinBox::down-arrow {
    width: 8px;
    height: 8px;
    image: url(data:image/svg+xml;base64,$down_arrow_svg_b64);
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid $indicator_border;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background-color: transparent;
}
QComboBox::drop-down:hover {
    border-left-color: $indicator_accent;
}
QComboBox::down-arrow {
    width: 10px;
    height: 10px;
    image: url(data:image/svg+xml;base64,$down_arrow_svg_b64);
}
""")

# ---------------------------------------------------------------------------
# QSS generation
# ---------------------------------------------------------------------------

def _build_indicator_qss(tokens: dict[str, str]) -> str:
    """Build the checkbox/spinbox/combo indicator rules from tokens + inline-SVG glyphs."""
    check_svg = _stroke_svg_b64("M3 8.5l3 3 7-7", "#ffffff")
    up_arrow_svg = _fill_svg_b64("M4 10l4-5 4 5z", tokens["indicator_arrow"])
    down_arrow_svg = _fill_svg_b64("M4 6l4 5 4-5z", tokens["indicator_arrow"])
    return _INDICATOR_TEMPLATE.substitute(
        check_svg_b64=check_svg,
        up_arrow_svg_b64=up_arrow_svg,
        down_arrow_svg_b64=down_arrow_svg,
        **tokens,
    )


def generate_qss(mode: str = "light") -> str:
    """Return the full application stylesheet for ``"light"`` or ``"dark"``.

    The stylesheet is built from :data:`TOKENS` plus :data:`TYPE_SCALE` via a shared
    template — no hand-written per-theme blocks. The output includes the checkbox/
    spinbox/combobox indicator rules appended at the end (same technique as the prior
    ``_build_checkbox_spinbox_style`` in ``app.py``).
    """
    if mode not in TOKENS:
        raise ValueError(f"Unknown theme mode {mode!r}; expected one of {list(TOKENS)}")
    tokens = dict(TOKENS[mode])
    tokens["font_family"] = FONT_FAMILY
    tokens["font_family_mono"] = FONT_FAMILY_MONO
    tokens["font_body"] = str(TYPE_SCALE["body"])
    tokens["font_subheading"] = str(TYPE_SCALE["subheading"])
    tokens["font_caption"] = str(TYPE_SCALE["caption"])
    qss = _QSS_TEMPLATE.substitute(tokens)
    qss += _build_indicator_qss(tokens)
    return qss


# ---------------------------------------------------------------------------
# Palette generation
# ---------------------------------------------------------------------------

def generate_palette(mode: str = "light"):
    """Return a ``QPalette`` for ``"light"`` or ``"dark"``.

    The palette values come from the ``pal_*`` entries in :data:`TOKENS`. This replaces
    the ``_build_palette`` / ``LIGHT_PALETTE`` / ``DARK_PALETTE`` static blocks that were
    in ``app.py``.
    """
    from PyQt5.QtGui import QPalette, QColor

    if mode not in TOKENS:
        raise ValueError(f"Unknown theme mode {mode!r}; expected one of {list(TOKENS)}")
    t = TOKENS[mode]
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(t["pal_window"]))
    palette.setColor(QPalette.WindowText, QColor(t["pal_window_text"]))
    palette.setColor(QPalette.Base, QColor(t["pal_base"]))
    palette.setColor(QPalette.AlternateBase, QColor(t["pal_alt_base"]))
    palette.setColor(QPalette.ToolTipBase, QColor(t["pal_tooltip_base"]))
    palette.setColor(QPalette.ToolTipText, QColor(t["pal_tooltip_text"]))
    palette.setColor(QPalette.Text, QColor(t["pal_text"]))
    palette.setColor(QPalette.Button, QColor(t["pal_button"]))
    palette.setColor(QPalette.ButtonText, QColor(t["pal_button_text"]))
    palette.setColor(QPalette.Highlight, QColor(t["pal_highlight"]))
    palette.setColor(QPalette.HighlightedText, QColor(t["pal_highlighted_text"]))
    palette.setColor(QPalette.Link, QColor(t["pal_highlight"]))
    return palette