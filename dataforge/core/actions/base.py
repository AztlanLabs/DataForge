from abc import ABC, abstractmethod

class ActionContext:
    """
    Holds the state of the execution pipeline.
    """
    def __init__(self, files, logger=None, update_progress=None):
        # List of FileEntry objects
        self.files = files
        # Log of actions taken: (path, action, status)
        self.results = []
        # Support specifically for dry runs
        self.is_dry_run = False
        # External callbacks
        self._logger = logger
        self._progress = update_progress
        # Cancellation
        self.cancel_token = None
        # Shared variables (counters, etc)
        self.variables = {} 

    def log(self, path, action, status, original_path=None):
        self.results.append((path, action, status))
        if self._logger:
            self._logger(f"[{status}] {path} -> {action}")

    def progress(self, current, total, message):
        if self._progress:
            self._progress(current, total, message)
            
    def should_cancel(self):
        if self.cancel_token and self.cancel_token.is_set():
            return True
        return False

class ActionStep(ABC):
    """
    Abstract Base Class for a specific workflow step (e.g., Filter, Rename).
    """
    def __init__(self, params=None):
        self.id = id(self)
        self.params = params or {}
        
    @property
    def name(self):
        return self.__class__.__name__

    @property
    def description(self):
        return "Generic Step"

    @abstractmethod
    def execute(self, context: ActionContext):
        """
        Execute this step on the files in the context.
        Must update context.files with the remaining/modified files.
        """
        pass

    def render_ui(self, parent):
        """
        Renders the configuration UI for this step inside parent.
        Should bind widgets to update self.params.
        """
        from PyQt5.QtWidgets import QVBoxLayout, QLabel
        from PyQt5.QtCore import Qt
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("No configuration needed.", parent)
        lbl.setAlignment(Qt.AlignLeft)
        layout.addWidget(lbl)

    def get_summary(self):
        """Returns a short string summary of current config."""
        return ""

