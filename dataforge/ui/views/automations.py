"""
Automations GUI view.

Single sidebar entry that groups the two multi-step workflow builders
under one "Automations" heading with sub-tabs. Previously, the
sidebar exposed "Tools & Workflows" (Integrity Monitor, Metadata
Cleaner, Batch Renamer, Folder Sync) and "Action Builder" as
sibling entries, which sounded duplicate and forced users to choose
between two destinations they had to mentally combine.

Layout: an outer QTabWidget with two tabs:

  - "Action Builder" — embeds the existing ``ActionBuilderView``
  - "Tools" — embeds the existing ``ToolsView`` (its own inner
    notebook with the four Tools sub-tabs)

Two-level tabs is intentional: the 1:1 mapping to the existing
view classes means no internal logic is duplicated, and the inner
notebook inside the "Tools" tab is the one users have been using
for the four sub-tools. Future work in WS-F/WS-H can flatten this
into a single-level notebook without changing the sidebar contract.
"""
from PyQt5.QtWidgets import QVBoxLayout, QTabWidget

from .base import BaseView
from .action_builder import ActionBuilderView
from .tools import ToolsView


class AutomationsView(BaseView):
    def get_title(self):
        return "Automations"

    def __init__(self, master, app=None):
        super().__init__(master, app)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.notebook = QTabWidget(self)
        layout.addWidget(self.notebook, 1)

        self.action_builder = ActionBuilderView(self.notebook, app=app)
        self.notebook.addTab(self.action_builder, "Action Builder")

        self.tools = ToolsView(self.notebook, app=app)
        self.notebook.addTab(self.tools, "Tools")


__all__ = ["AutomationsView"]
