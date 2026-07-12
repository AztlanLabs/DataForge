"""
Tests for the design-token module (ui/theme_tokens.py).

Guards the acceptance gates from doc 05 §8 / doc 06 §2b:
  - generate_qss produces both themes from one template (no hand-written blocks).
  - No Bootstrap-era legacy hex literals appear in the generated QSS.
  - Every text/surface token pair clears WCAG AA (≥4.5:1 for body-size text).
  - The two previously-failing pairs (#5bc0de, #ffc107) are gone.
  - Typography constants exist and cover the 5 named sizes.
  - generate_palette returns a QPalette for both modes.
"""

import unittest
import re

from dataforge.ui.theme_tokens import (
    TOKENS,
    TYPE_SCALE,
    FONT_FAMILY,
    FONT_FAMILY_MONO,
    SEMANTIC_TOKEN_NAMES,
    generate_qss,
    generate_palette,
)


# ---------------------------------------------------------------------------
# WCAG contrast helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Parse '#rrggbb' to (r, g, b) ints."""
    h = hex_str.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG 2.1 relative luminance formula."""
    def _channel(v: int) -> float:
        s = v / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def _contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """Compute the WCAG contrast ratio between two '#rrggbb' colours."""
    l1 = _relative_luminance(_hex_to_rgb(fg_hex))
    l2 = _relative_luminance(_hex_to_rgb(bg_hex))
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# Bootstrap-era legacy hex literals that must never appear in generated QSS.
# (doc 05 §1.1 / §8 acceptance gate)
LEGACY_HEX_LITERALS = [
    "#d9534f", "#5cb85c", "#5bc0de",     # Bootstrap-era (settings/tools)
    "#ffc107", "#dc3545", "#17a2b8",     # Older Bootstrap (search/duplicates)
    "#0275d8", "#f0ad4e", "#28a745",     # Older Bootstrap continued
]


class TestTokenTable(unittest.TestCase):
    """The token table itself is well-formed."""

    def test_both_themes_defined(self):
        self.assertIn("light", TOKENS)
        self.assertIn("dark", TOKENS)

    def test_themes_share_same_token_names(self):
        light_keys = set(TOKENS["light"].keys())
        dark_keys = set(TOKENS["dark"].keys())
        self.assertEqual(light_keys, dark_keys,
                         "Both themes must use identical token names (only values differ).")

    def test_all_values_are_hex(self):
        for mode, tokens in TOKENS.items():
            for name, value in tokens.items():
                self.assertTrue(
                    re.match(r'^#[0-9a-fA-F]{6}$', value),
                    f"Token '{name}' in '{mode}' is not a valid #rrggbb hex: {value!r}",
                )

    def test_semantic_tokens_present(self):
        for mode in ("light", "dark"):
            for name in SEMANTIC_TOKEN_NAMES:
                self.assertIn(name, TOKENS[mode],
                              f"Semantic token '{name}' missing from {mode} theme.")

    def test_no_legacy_hex_in_token_table(self):
        for mode, tokens in TOKENS.items():
            for name, value in tokens.items():
                for legacy in LEGACY_HEX_LITERALS:
                    self.assertNotEqual(
                        value.lower(), legacy.lower(),
                        f"Token '{name}' in '{mode}' uses legacy hex {legacy}.",
                    )


class TestTypographyConstants(unittest.TestCase):
    """Type scale (doc 05 §2 / §8 acceptance gate)."""

    def test_five_named_sizes(self):
        expected = {"caption", "body", "subheading", "heading", "display"}
        self.assertEqual(set(TYPE_SCALE.keys()), expected)

    def test_size_values_increase_monotonically(self):
        sizes = list(TYPE_SCALE.values())
        self.assertEqual(sizes, sorted(sizes),
                         "Type-scale values must increase monotonically.")

    def test_body_is_13(self):
        self.assertEqual(TYPE_SCALE["body"], 13)

    def test_font_families_defined(self):
        self.assertIsInstance(FONT_FAMILY, str)
        self.assertIsInstance(FONT_FAMILY_MONO, str)
        self.assertIn("Segoe UI", FONT_FAMILY)
        self.assertIn("Courier New", FONT_FAMILY_MONO)


class TestQSSGeneration(unittest.TestCase):
    """generate_qss produces correct, non-regresssing stylesheets."""

    def test_returns_non_empty_string_for_both_modes(self):
        for mode in ("light", "dark"):
            qss = generate_qss(mode)
            self.assertIsInstance(qss, str)
            self.assertGreater(len(qss), 1000,
                               f"QSS for {mode} suspiciously short ({len(qss)} chars).")

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            generate_qss("invalid")
        with self.assertRaises(ValueError):
            generate_palette("invalid")

    def test_no_legacy_hex_in_generated_qss(self):
        """doc 05 §8: grep for legacy literals returns zero hits."""
        for mode in ("light", "dark"):
            qss = generate_qss(mode).lower()
            for legacy in LEGACY_HEX_LITERALS:
                self.assertNotIn(
                    legacy.lower(), qss,
                    f"Legacy hex {legacy} found in generated {mode} QSS.",
                )

    def test_no_outline_zero_suppression(self):
        """doc 05 §5/§8: outline: 0 must not appear."""
        for mode in ("light", "dark"):
            qss = generate_qss(mode)
            self.assertNotIn("outline: 0", qss,
                             f"outline:0 suppression found in {mode} QSS.")

    def test_combo_dropdown_arrow_rules_exist(self):
        """doc 05 §3/§8: QComboBox::down-arrow rules must exist."""
        for mode in ("light", "dark"):
            qss = generate_qss(mode)
            self.assertIn("QComboBox::drop-down", qss)
            self.assertIn("QComboBox::down-arrow", qss)

    def test_checkbox_checkmark_svg_present(self):
        """doc 05 §3/§8: checkbox indicator:checked must have an SVG image."""
        for mode in ("light", "dark"):
            qss = generate_qss(mode)
            self.assertIn("QCheckBox::indicator:checked", qss)
            self.assertIn("data:image/svg+xml;base64", qss)

    def test_font_sizes_from_type_scale(self):
        """Body, subheading, and caption sizes must come from TYPE_SCALE."""
        for mode in ("light", "dark"):
            qss = generate_qss(mode)
            self.assertIn(f"font-size: {TYPE_SCALE['body']}px", qss)
            self.assertIn(f"font-size: {TYPE_SCALE['subheading']}px", qss)
            self.assertIn(f"font-size: {TYPE_SCALE['caption']}px", qss)

    def test_surface_brightness_fix_applied(self):
        """doc 05 §1.3/§8: light surface is #f7f7f8 (not #ffffff); dark base is #1c1c20, elevated #26262c."""
        light = generate_qss("light")
        self.assertIn("#f7f7f8", light, "Light surface #f7f7f8 missing.")
        dark = generate_qss("dark")
        self.assertIn("#1c1c20", dark, "Dark base #1c1c20 missing.")
        self.assertIn("#26262c", dark, "Dark elevated #26262c missing.")

    def test_prior_wcag_failures_gone(self):
        """The two measured WCAG failures (#5bc0de, #ffc107) must not appear."""
        for mode in ("light", "dark"):
            qss = generate_qss(mode).lower()
            self.assertNotIn("#5bc0de", qss)
            self.assertNotIn("#ffc107", qss)

    def test_both_themes_use_same_qss_structure(self):
        """The QSS template is shared — only token values differ. Strip hex
        values and base64 data URLs (which embed theme-specific colours) and
        verify the remainder is identical for both themes."""
        light = generate_qss("light")
        dark = generate_qss("dark")
        hex_pattern = re.compile(r'#[0-9a-fA-F]{6}')
        b64_pattern = re.compile(r'base64,[A-Za-z0-9+/=]+')
        light_structure = b64_pattern.sub("base64,XXX", hex_pattern.sub("#XXXXXX", light))
        dark_structure = b64_pattern.sub("base64,XXX", hex_pattern.sub("#XXXXXX", dark))
        self.assertEqual(
            light_structure, dark_structure,
            "Both themes must share the same QSS structure (only hex/base64 values differ).",
        )


class TestWCAGContrast(unittest.TestCase):
    """Every text/surface token pair must clear WCAG AA (≥4.5:1 for body text)."""

    # Text tokens that render on the main content surface.
    TEXT_TOKENS = ["text", "text_button", "text_muted", "text_selected"]

    # Text tokens that render on elevated/button surfaces.
    TEXT_ON_ELEVATED = ["text", "text_button"]

    # Text tokens that render on the selected/tinted surface.
    TEXT_ON_SELECTED = ["text_selected"]

    def _assert_min_contrast(self, text_hex, surface_hex, min_ratio, context):
        actual = _contrast_ratio(text_hex, surface_hex)
        self.assertGreaterEqual(
            actual, min_ratio,
            f"Contrast {actual:.2f}:1 < {min_ratio}:1 for {context} "
            f"(text {text_hex} on {surface_hex}).",
        )

    def test_light_text_on_surface(self):
        t = TOKENS["light"]
        for name in self.TEXT_TOKENS:
            self._assert_min_contrast(
                t[name], t["surface"], 4.5, f"light/{name} on surface")

    def test_light_text_on_elevated(self):
        t = TOKENS["light"]
        for name in self.TEXT_ON_ELEVATED:
            self._assert_min_contrast(
                t[name], t["surface_elevated"], 4.5, f"light/{name} on surface_elevated")

    def test_light_text_on_selected(self):
        t = TOKENS["light"]
        for name in self.TEXT_ON_SELECTED:
            self._assert_min_contrast(
                t[name], t["surface_selected"], 4.5, f"light/{name} on surface_selected")

    def test_dark_text_on_surface(self):
        t = TOKENS["dark"]
        for name in self.TEXT_TOKENS:
            self._assert_min_contrast(
                t[name], t["surface"], 4.5, f"dark/{name} on surface")

    def test_dark_text_on_elevated(self):
        t = TOKENS["dark"]
        for name in self.TEXT_ON_ELEVATED:
            self._assert_min_contrast(
                t[name], t["surface_elevated"], 4.5, f"dark/{name} on surface_elevated")

    def test_dark_text_on_selected(self):
        t = TOKENS["dark"]
        for name in self.TEXT_ON_SELECTED:
            self._assert_min_contrast(
                t[name], t["surface_selected"], 4.5, f"dark/{name} on surface_selected")

    def test_light_muted_text_on_surface(self):
        """text_muted must pass AA on the main surface (commonly borderline)."""
        t = TOKENS["light"]
        ratio = _contrast_ratio(t["text_muted"], t["surface"])
        self.assertGreaterEqual(ratio, 4.5,
                                f"Light text_muted on surface: {ratio:.2f}:1")

    def test_dark_muted_text_on_surface(self):
        t = TOKENS["dark"]
        ratio = _contrast_ratio(t["text_muted"], t["surface"])
        self.assertGreaterEqual(ratio, 4.5,
                                f"Dark text_muted on surface: {ratio:.2f}:1")

    def test_stop_btn_text_contrast(self):
        """stopBtn text is always white on danger_bg — verify it's ≥3:1 (large UI)."""
        for mode in ("light", "dark"):
            t = TOKENS[mode]
            ratio = _contrast_ratio("#ffffff", t["danger_bg"])
            self.assertGreaterEqual(ratio, 3.0,
                                    f"stopBtn white-on-danger in {mode}: {ratio:.2f}:1")


class TestPaletteGeneration(unittest.TestCase):
    """generate_palette returns a usable QPalette."""

    def test_returns_palette_for_both_modes(self):
        try:
            from PyQt5.QtGui import QPalette
        except ImportError:
            self.skipTest("PyQt5 not available")
        for mode in ("light", "dark"):
            pal = generate_palette(mode)
            self.assertIsInstance(pal, QPalette)
            # Verify a colour was actually set (not the default).
            self.assertIsNotNone(pal.color(QPalette.Window))

    def test_palette_window_matches_token(self):
        try:
            from PyQt5.QtGui import QPalette, QColor
        except ImportError:
            self.skipTest("PyQt5 not available")
        for mode in ("light", "dark"):
            t = TOKENS[mode]
            pal = generate_palette(mode)
            win_color = pal.color(QPalette.Window)
            expected = QColor(t["pal_window"])
            self.assertEqual(win_color.name(), expected.name(),
                             f"{mode} palette Window colour mismatch.")


if __name__ == "__main__":
    unittest.main()