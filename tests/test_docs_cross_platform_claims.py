"""TICK-512 — Docs cross-platform claim fix for --parse-artifacts + trash (U10 + U11).

Acceptance:
- CLI_REFERENCE recover+forensics sections no longer match trash.*system|System trash
- README trash recovery line contains Linux/macOS only
- about.py trash row shows Linux/macOS only and tooltip contains TrashScanUnsupported
- Windows-rendered about card shows Windows: ✗ (TrashScanUnsupported, pywin32 path planned)
- CLI tests still pass (no regression)
"""

import re
from pathlib import Path


def _read_cli_reference_sections():
    text = Path("docs/CLI_REFERENCE.md").read_text(encoding="utf-8")
    # Split by top-level headings ## `
    # Find recover and forensics sections
    sections = {}
    # Use regex to extract sections starting with ## `fm recover` and ## `fm forensics`
    # Split on "\n## "
    parts = re.split(r"\n## ", text)
    for part in parts:
        low = part.lower()
        if low.startswith("`fm recover`"):
            sections["recover"] = part
        elif low.startswith("`fm forensics`"):
            sections["forensics"] = part
    return sections


def test_cli_reference_no_system_trash_overclaim():
    """Recover + forensics sections must not contain trash.*system or System trash."""
    sections = _read_cli_reference_sections()
    assert "recover" in sections, "recover section not found"
    assert "forensics" in sections, "forensics section not found"
    pattern = re.compile(r"trash.*system|System trash", re.IGNORECASE)
    for name, sec in sections.items():
        match = pattern.search(sec)
        assert not match, f"{name} section still over-claims: {match.group(0)!r} in {sec[:200]!r}"
    # Replacement matrix must be present
    combined = sections["recover"] + sections["forensics"]
    assert "TrashScanUnsupported" in combined, "platform matrix missing TrashScanUnsupported"
    assert "recovery.py:208" in combined or "recovery.py:184" in combined
    assert "Linux" in combined and "macOS" in combined and "Windows" in combined
    # Forensics platform note
    assert "forensics.py:602" in sections["forensics"]


def test_cli_reference_recover_platform_matrix():
    """Recover section must contain the platform matrix with ✓/✗."""
    sections = _read_cli_reference_sections()
    recover = sections["recover"]
    # Check for matrix rows
    assert "Linux" in recover and "✓" in recover
    assert "macOS" in recover and "✓" in recover
    assert "Windows" in recover and "✗" in recover
    assert "TrashScanUnsupported" in recover
    assert "pywin32" in recover


def test_readme_trash_recovery_contains_platform():
    """README trash recovery bullet must contain Linux/macOS only."""
    text = Path("README.md").read_text(encoding="utf-8")
    # Find all lines containing trash recovery; at least one (the feature bullet) must have the gate
    found_lines = [line for line in text.splitlines() if re.search(r"trash recovery", line, re.IGNORECASE)]
    assert found_lines, "README missing 'trash recovery' line"
    assert any("Linux/macOS only" in line for line in found_lines), (
        f"no trash recovery line contains platform gate: {found_lines!r}"
    )
    # Ensure the feature bullet specifically has it (starts with - **Trash recovery)
    bullet = [line for line in found_lines if line.strip().startswith("- **Trash recovery")]
    if bullet:
        assert "Linux/macOS only" in bullet[0], f"feature bullet missing gate: {bullet[0]!r}"
    # Also check OS artifact parsing
    found2 = [line for line in text.splitlines() if re.search(r"os artifact parsing", line, re.IGNORECASE)]
    assert found2, "README missing 'OS artifact parsing' line"
    assert any("Linux/macOS only" in line for line in found2), (
        f"no artifact parsing line contains platform gate: {found2!r}"
    )


def test_about_py_contains_platform_gating():
    """about.py file must contain platform-gated strings and TrashScanUnsupported."""
    text = Path("dataforge/ui/views/about.py").read_text(encoding="utf-8")
    assert "Linux/macOS only" in text, "about.py missing Linux/macOS only"
    assert "TrashScanUnsupported" in text, "about.py missing TrashScanUnsupported"
    assert "raise TrashScanUnsupported" in text, "about.py tooltip must quote raise TrashScanUnsupported"
    assert "recovery.py:208" in text or "recovery.py:184" in text
    assert "Windows: ✗ (TrashScanUnsupported, pywin32 path planned)" in text


def test_about_view_trash_row_and_tooltip():
    """About card trash row shows Linux/macOS only and tooltip contains TrashScanUnsupported."""
    import os

    # Ensure offscreen platform for CI
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication, QWidget

    from dataforge.ui.views.about import AboutView

    app = QApplication.instance()
    if not app:
        app = QApplication([])

    parent = QWidget()
    view = AboutView(parent)

    # Find all labels and check for File Recovery title
    all_text = []
    for child in view.findChildren(QWidget):
        try:
            txt = child.text() if hasattr(child, "text") else ""
            if txt:
                all_text.append(txt)
            tip = child.toolTip()
            if tip:
                all_text.append(tip)
        except Exception:
            pass
        # Also check window title via objectName? For CollapsibleCard, title is in a label
        # So we also collect via findChildren for QLabel
    from PyQt5.QtWidgets import QLabel

    for lbl in view.findChildren(QLabel):
        try:
            all_text.append(lbl.text())
            if lbl.toolTip():
                all_text.append(lbl.toolTip())
        except Exception:
            pass

    combined = "\n".join(all_text)
    assert "File Recovery" in combined, "About view missing File Recovery card"
    assert "Linux/macOS only" in combined, "About view trash row missing platform gate"
    # Tooltip check
    has_tooltip = any("TrashScanUnsupported" in t for t in all_text)
    assert has_tooltip, f"About view tooltip missing TrashScanUnsupported, got: {all_text[:5]}"
    # Check that at least one tooltip contains raise
    has_raise = any("raise TrashScanUnsupported" in t for t in all_text)
    assert has_raise, "Tooltip must quote 'raise TrashScanUnsupported'"

    parent.deleteLater()


def test_about_view_windows_rendered():
    """Windows-rendered about card shows Windows: ✗ (TrashScanUnsupported, pywin32 path planned)."""
    import os
    from unittest.mock import patch

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication, QWidget, QLabel

    from dataforge.ui.views.about import AboutView

    app = QApplication.instance()
    if not app:
        app = QApplication([])

    with patch("platform.system", return_value="Windows"):
        parent = QWidget()
        view = AboutView(parent)
        texts = []
        for lbl in view.findChildren(QLabel):
            try:
                texts.append(lbl.text())
                if lbl.toolTip():
                    texts.append(lbl.toolTip())
            except Exception:
                pass
        for child in view.findChildren(QWidget):
            try:
                tip = child.toolTip()
                if tip:
                    texts.append(tip)
            except Exception:
                pass
        combined = "\n".join(texts)
        # The description or tooltip should contain the Windows line even when mocked to Windows
        assert "Windows: ✗ (TrashScanUnsupported, pywin32 path planned)" in combined, (
            f"Windows rendering missing expected string, combined: {combined[:500]!r}"
        )
        parent.deleteLater()


def test_gui_workflows_about_card_matrix():
    """GUI_WORKFLOWS about-card must contain platform matrix."""
    text = Path("docs/GUI_WORKFLOWS.md").read_text(encoding="utf-8")
    assert "About & Help" in text, "GUI_WORKFLOWS missing About & Help section"
    assert "TrashScanUnsupported" in text, "GUI_WORKFLOWS missing TrashScanUnsupported"
    assert "recovery.py:208" in text
    assert "Linux" in text and "macOS" in text and "Windows" in text
    assert "Linux/macOS only" in text or "Platform support" in text
