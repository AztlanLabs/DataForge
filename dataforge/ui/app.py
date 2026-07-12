import threading
from typing import Any, Callable, Dict, Protocol, Type, TypeAlias
from functools import partial
import inspect
import os

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QCheckBox, QStackedWidget, QProgressBar,
    QStatusBar, QMessageBox, QScrollArea, QFrame, QGraphicsOpacityEffect
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QPropertyAnimation, QEasingCurve

from .views.base import BaseView
from .views.dashboard import DashboardView
from .views.search import SearchView
from .views.duplicates import DuplicatesView
from .views.settings import SettingsView
from .views.media import MediaView
from .views.system_cleanup import SystemCleanupView
from .views.performance_view import PerformanceView
from .views.recovery_view import RecoveryView
from .views.metadata_view import MetadataView
from .views.hardware_view import HardwareView
from .views.forensics_view import ForensicsView
from .views.storage_devices import StorageDevicesView
from .views.automations import AutomationsView
from .views.about import AboutView
from .plugin_loader import PluginLoader
from .theme_tokens import generate_qss, generate_palette, TYPE_SCALE
from ..core.config import config

HEADER_COLORS = {
    "light": {
        "Home": "#2563eb",                # blue
        "Find & Organize": "#d97706",     # amber
        "Clean & Optimize": "#059669",    # emerald
        "Recover & Investigate": "#7c3aed", # purple
        "System": "#db2777",              # pink
        "Plugins": "#4b5563",             # slate
    },
    "dark": {
        "Home": "#60a5fa",                # blue
        "Find & Organize": "#fbbf24",     # amber
        "Clean & Optimize": "#34d399",    # emerald
        "Recover & Investigate": "#a78bfa", # purple
        "System": "#f472b6",              # pink
        "Plugins": "#9ca3af",             # slate
    }
}

BackgroundArgs: TypeAlias = tuple[Any, ...]
BackgroundKwargs: TypeAlias = dict[str, Any]


def _humanize_callable_name(target) -> str:
    """Return a short, user-readable name for ``target``.

    Module-level functions expose ``__name__``; bound methods expose
    ``__qualname__`` (e.g. ``SearchView.start_search``). ``functools.partial``
    wraps another callable whose name we can read instead. Lambdas have
    only ``<lambda>`` for both and fall through to the generic label."""
    name = getattr(target, "__name__", None)
    if name and name != "<lambda>":
        return name.replace("_", " ")
    qualname = getattr(target, "__qualname__", None)
    if qualname:
        leaf = qualname.split(".")[-1]
        if leaf and leaf != "<lambda>":
            return leaf.replace("_", " ")
    func = getattr(target, "func", None)
    if func is not None:
        return _humanize_callable_name(func)
    return "background task"

class ProgressCallback(Protocol):
    def __call__(self, current: int, total: int, step_name: str = "") -> None: ...

class SuccessCallback(Protocol):
    def __call__(self, result: Any) -> None: ...

class ErrorCallback(Protocol):
    def __call__(self, error: Exception) -> None: ...

class BackgroundTarget(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


class BackgroundWorker(QThread):
    progress_signal = pyqtSignal(int, int, str)
    status_signal = pyqtSignal(str)
    result_signal = pyqtSignal(object)
    error_signal = pyqtSignal(Exception)

    def __init__(self, target, args=(), kwargs=(), cancel_event=None):
        super().__init__()
        self.target = target
        self.args = args
        self.kwargs = kwargs
        self.cancel_event = cancel_event

    def run(self):
        try:
            sig = inspect.signature(self.target)
            kwargs_copy = dict(self.kwargs)
            
            if 'cancel_token' in sig.parameters and self.cancel_event:
                kwargs_copy['cancel_token'] = self.cancel_event
                
            if 'progress_callback' in sig.parameters:
                def progress_callback(current, total, step_name=""):
                    self.progress_signal.emit(current, total, step_name)
                kwargs_copy['progress_callback'] = progress_callback
                
            result = self.target(*self.args, **kwargs_copy)
            self.result_signal.emit(result)
        except Exception as e:
            self.error_signal.emit(e)


# Stylesheets + palettes — generated from the semantic token table (ui/theme_tokens.py).
# The two ~200-line hand-written QSS blocks and the _build_palette machinery they
# replaced are gone; one template + one token dict drives both themes now (doc 05 §1.4).
LIGHT_STYLE = generate_qss("light")
DARK_STYLE = generate_qss("dark")
LIGHT_PALETTE = generate_palette("light")
DARK_PALETTE = generate_palette("dark")


class DataForgeApp(QMainWindow):
    post_signal = pyqtSignal(object, tuple, dict)

    # The sidebar used to hide groups above the user's current Experience
    # Level (Simple → no System Maintenance/Advanced Analysis; Standard → no
    # Advanced Analysis; Everything → everything). That created a
    # discoverability cliff: a user on Simple could not see that Forensics
    # Lab existed. The rail now shows every group and the tier only filters
    # in-view complexity, so the navigation is stable while advanced
    # controls stay hidden behind "More options" expanders per view.
    TIER_RANK = {"Simple": 0, "Standard": 1, "Everything": 2}

    # 2e.1 motion constants — every animated transition reads its duration
    # from here so a single call (2e.3's reduce-motion setting) can shorten
    # or skip them all in one place.
    SIDEBAR_ANIM_MS = 180
    VIEW_ANIM_MS = 160
    ANIM_EASING = QEasingCurve.OutCubic

    def __init__(self, on_progress: Callable[[int, int, str], None] | None = None):
        super().__init__()
        self.setWindowTitle("DataForge")
        self.resize(1100, 750)
        # Several views pack many controls into one row; below ~900px wide
        # the sidebar (230px) leaves too little content width and buttons/
        # labels start getting clipped.
        self.setMinimumSize(900, 600)

        # Threading/Cancellation
        self.cancel_event = threading.Event()
        self.current_worker = None
        self.is_busy = False

        # Signals
        self.post_signal.connect(self._handle_posted_event)

        # Central Layout Setup
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        self.main_layout = QHBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Navigation Panel
        self.nav_frame = QFrame(central_widget)
        self.nav_frame.setObjectName("navFrame")
        self.nav_frame.setFixedWidth(230)
        self.nav_layout = QVBoxLayout(self.nav_frame)
        self.nav_layout.setContentsMargins(10, 10, 10, 10)

        # Navigation Header (Title only)
        self.nav_header = QHBoxLayout()
        self.nav_title_lbl = QLabel("DataForge", self.nav_frame)
        self.nav_title_lbl.setStyleSheet(f"font-weight: bold; font-size: {TYPE_SCALE['heading']}px; padding-left: 16px;")
        self.nav_header.addWidget(self.nav_title_lbl)
        self.nav_layout.addLayout(self.nav_header)

        # Theme Toggle row: an icon label + the Dark Mode checkbox.
        # The icon swaps between a sun (light) and a moon (dark) so the
        # toggle is recognizable at a glance, not just a colored box.
        self.theme_row = QWidget(self.nav_frame)
        theme_row_layout = QHBoxLayout(self.theme_row)
        theme_row_layout.setContentsMargins(16, 5, 0, 0)
        theme_row_layout.setSpacing(8)
        self.theme_icon_lbl = QLabel("☀", self.theme_row)
        self.theme_icon_lbl.setStyleSheet(f"font-size: {TYPE_SCALE['heading']}px;")
        theme_row_layout.addWidget(self.theme_icon_lbl)
        self.theme_chk = QCheckBox("Dark Mode", self.theme_row)
        self.theme_chk.stateChanged.connect(self.toggle_theme)
        theme_row_layout.addWidget(self.theme_chk)
        theme_row_layout.addStretch()
        self.nav_layout.addWidget(self.theme_row)

        # Separator line
        sep = QFrame(self.nav_frame)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        self.nav_layout.addWidget(sep)

        # Scrollable area for Navigation Buttons
        self.nav_scroll = QScrollArea(self.nav_frame)
        self.nav_scroll.setWidgetResizable(True)
        self.nav_scroll.setFrameShape(QFrame.NoFrame)
        self.nav_btn_widget = QWidget()
        self.nav_btn_layout = QVBoxLayout(self.nav_btn_widget)
        self.nav_btn_layout.setContentsMargins(0, 0, 0, 0)
        self.nav_btn_layout.setAlignment(Qt.AlignTop)
        self.nav_scroll.setWidget(self.nav_btn_widget)
        self.nav_layout.addWidget(self.nav_scroll)

        # Content Area Stack
        self.content_stack = QStackedWidget(central_widget)
        
        # Add side navigation and content stack to central layout
        self.main_layout.addWidget(self.nav_frame)
        self.main_layout.addWidget(self.content_stack, 1)

        # Status Bar Setup
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel("Ready", self)
        self.status_bar.addWidget(self.status_label, 1)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setVisible(False)
        self.status_bar.addWidget(self.progress_bar, 2)

        self.spinner_chars = "\u280B\u2819\u2839\u2838\u283C\u2834\u2826\u2827\u2807\u280F"
        self.spinner_idx = 0
        self.spinner_label = QLabel("  ", self)
        self.spinner_label.setStyleSheet(f"font-family: Consolas; font-size: {TYPE_SCALE['subheading']}px;")
        self.status_bar.addPermanentWidget(self.spinner_label)

        self.cancel_btn = QPushButton("STOP", self)
        self.cancel_btn.setObjectName("stopBtn")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_action)
        self.status_bar.addPermanentWidget(self.cancel_btn)

        # Spinner Animation Timer
        self.spinner_timer = QTimer(self)
        self.spinner_timer.timeout.connect(self._animate_spinner)

        # Sidebar navigation buttons state
        self.nav_buttons = []
        self.group_headers = {}
        self.group_buttons = {}
        self.group_containers = {}
        # Hold active QPropertyAnimation objects so they don't get GC'd
        # mid-flight — Qt deletes the animation when its Python wrapper
        # is collected, which used to freeze the animation at the start
        # value and leave the sidebar half-collapsed (2e.1).
        self._active_animations: list[QPropertyAnimation] = []
        self.views: Dict[str, BaseView] = {}
        self.current_view = None

        # Load configuration theme
        current_theme = config.get("theme", "cosmo")
        is_dark = current_theme == "darkly"
        self.theme_chk.setChecked(is_dark)
        self.apply_theme(is_dark)
        self._update_theme_icon(is_dark)

        # Initialize Base Views. Progress here is real (not simulated): each
        # step corresponds to an actual view being constructed, so a caller
        # showing a splash screen (see ui/splash.py) can track true startup
        # progress instead of faking a bar animation.
        view_classes = [
            (DashboardView, "Dashboard"),
            (SearchView, "Search"),
            (DuplicatesView, "Duplicate Finder"),
            (AutomationsView, "Automations"),
            (MediaView, "Media Tools"),
            (SystemCleanupView, "Clean Up Space"),
            (PerformanceView, "Performance"),
            (RecoveryView, "File Recovery"),
            (MetadataView, "Metadata & EXIF"),
            (HardwareView, "Hardware Info"),
            (ForensicsView, "Forensics"),
            (StorageDevicesView, "Storage & Devices"),
            (SettingsView, "Settings"),
            (AboutView, "About & Help"),
        ]
        total_steps = len(view_classes) + 2  # + plugin loading + finalize

        def report(step, message):
            if on_progress:
                on_progress(step, total_steps, message)

        for i, (view_cls, label) in enumerate(view_classes, start=1):
            report(i, f"Loading {label}...")
            self.add_view(view_cls)

        # Load Plugins
        report(len(view_classes) + 1, "Loading plugins...")
        plugin_dir = os.path.join(os.path.dirname(__file__), 'plugins')
        plugins_enabled = config.get("plugins_enabled", False)
        loader = PluginLoader(plugin_dir, enabled=plugins_enabled)
        for plugin_cls in loader.load_plugins():
            self.add_view(plugin_cls)

        # Build Sidebar and switch to Dashboard
        report(len(view_classes) + 2, "Finishing up...")
        self.build_navigation_sidebar()
        self.switch_view("Dashboard")

    def update_status(self, message: str):
        self.status_label.setText(message)

    def cancel_action(self):
        """Signal the running thread to stop."""
        if self.is_busy:
            self.cancel_event.set()
            self.update_status("Cancelling...")

    def _animate_spinner(self):
        if self.is_busy:
            char = self.spinner_chars[self.spinner_idx % len(self.spinner_chars)]
            self.spinner_label.setText(char)
            self.spinner_idx += 1
        else:
            self.spinner_label.setText("  ")

    def add_view(self, view_cls: Type[BaseView]):
        view_instance = view_cls(self.content_stack, app=self)
        title = view_instance.get_title()
        # 2e.1 view crossfade — every view gets an opacity effect so
        # ``switch_view`` can fade it in from 0→1. Setting the effect after
        # the view is parented ensures PyQt5 picks it up before the
        # first paint; opacity is left at 1.0 so the very first view
        # (Dashboard) renders normally until ``switch_view`` overrides it.
        view_instance.setGraphicsEffect(QGraphicsOpacityEffect(view_instance))
        view_instance.graphicsEffect().setOpacity(1.0)

        self.content_stack.addWidget(view_instance)
        self.views[title] = view_instance

    def build_navigation_sidebar(self):
        self.nav_buttons = []
        self.group_headers = {}
        self.group_buttons = {}
        self.group_containers = {}

        # Group definitions — task-oriented sidebar (IMPROVEMENT_PLAN §2.2).
        # The labels are stable across the rename in 2d.3 and the view merge
        # in 2d.2/2d.4; the build-time list is the contract every commit
        # updates in lockstep with the registered view titles.
        groups = {
            "Home": ["Dashboard"],
            "Find & Organize": [
                "Search",
                "Duplicate Finder",
                "Media Tools",
                "Metadata & EXIF",
                "Automations",
            ],
            "Clean & Optimize": [
                "Clean Up Space",
                "Storage & Devices",
                "Performance",
            ],
            "Recover & Investigate": [
                "File Recovery",
                "Forensics",
            ],
            "System": [
                "Hardware Info",
                "Settings",
                "About & Help",
            ],
        }

        # Collect unregistered/plugin views
        all_titles = list(self.views.keys())
        registered = []
        for g_list in groups.values():
            registered.extend(g_list)
        unregistered = [t for t in all_titles if t not in registered]

        if unregistered:
            groups["Plugins"] = unregistered

        # Apply Detail level gating from Settings before rendering.
        # The tier is kept as a hint for in-view expanders but the sidebar
        # itself is no longer filtered by it; every group is rendered.
        tier_name = config.get("settings_ui_tier", "Simple")
        tier_rank = self.TIER_RANK.get(tier_name, 0)
        self._current_tier_rank = tier_rank

        # Clear layout first (if re-building)
        while self.nav_btn_layout.count():
            item = self.nav_btn_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Load collapsed state
        collapsed_groups = config.get("collapsed_groups", [])
        is_dark = self.theme_chk.isChecked()
        theme_key = "dark" if is_dark else "light"

        # Populate grouped layout
        for group_name, titles in groups.items():
            available = [t for t in titles if t in self.views]
            if not available:
                continue

            # Collapse state
            is_collapsed = (group_name in collapsed_groups)
            arrow = "▶ " if is_collapsed else "▼ "

            # Group Header Button
            header_btn = QPushButton(f"{arrow}{group_name.upper()}", self.nav_btn_widget)
            header_btn.setObjectName("groupHeader")
            color = HEADER_COLORS[theme_key].get(group_name, "#6b7280")
            header_btn.setStyleSheet(f"color: {color};")

            header_btn.setCheckable(False)
            header_btn.clicked.connect(
                lambda checked, g=group_name, b=header_btn: self.toggle_sidebar_group(g, b)
            )

            self.nav_btn_layout.addWidget(header_btn)
            self.group_headers[group_name] = header_btn
            self.group_buttons[group_name] = []

            # Per-group container (2e.1) — the buttons live inside a
            # dedicated QWidget so we can animate its ``maximumHeight``
            # for the collapse/expand transition. A flat layout of all
            # buttons cannot be height-animated as a unit.
            group_container = QWidget(self.nav_btn_widget)
            group_container.setObjectName("navGroup")
            container_layout = QVBoxLayout(group_container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(0)
            self.group_containers[group_name] = group_container

            for title in available:
                btn = QPushButton(title, group_container)
                btn.setCheckable(True)
                btn.clicked.connect(lambda checked, t=title: self.switch_view(t))
                container_layout.addWidget(btn)
                self.nav_buttons.append((btn, title))
                self.group_buttons[group_name].append(btn)

            if is_collapsed:
                group_container.setMaximumHeight(0)
                group_container.setVisible(False)
            else:
                group_container.setMaximumHeight(16777215)
                group_container.setVisible(True)

            self.nav_btn_layout.addWidget(group_container)

    def toggle_sidebar_group(self, group_name, header_button):
        collapsed_groups = config.get("collapsed_groups", [])
        if group_name in collapsed_groups:
            collapsed_groups.remove(group_name)
            is_collapsed = False
        else:
            collapsed_groups.append(group_name)
            is_collapsed = True

        config.set("collapsed_groups", collapsed_groups)

        # Update text/arrow
        is_dark = self.theme_chk.isChecked()
        theme_key = "dark" if is_dark else "light"
        color = HEADER_COLORS[theme_key].get(group_name, "#6b7280")
        header_button.setText(f"{'▶' if is_collapsed else '▼'}  {group_name.upper()}")
        header_button.setStyleSheet(f"color: {color};")

        container = self.group_containers.get(group_name)
        if container is not None:
            if is_collapsed:
                container.setVisible(True)
                self._animate_max_height(container, container.maximumHeight(), 0, restore_to=None)
            else:
                target = max(container.sizeHint().height(), container.minimumSizeHint().height())
                if target <= 0:
                    # sizeHint not yet realised — give the layout a turn
                    container.adjustSize()
                    target = max(container.sizeHint().height(), container.minimumSizeHint().height())
                self._animate_max_height(
                    container,
                    container.maximumHeight(),
                    target,
                    restore_to=16777215,
                )

    def _animate_max_height(self, widget, start, end, restore_to=None):
        """Run a ``maximumHeight`` animation on *widget*.

        ``restore_to`` is the value the constraint snaps back to once the
        animation finishes; pass ``None`` to leave the animated value in
        place. The animation object is kept alive in
        :attr:`_active_animations` so PyQt5 does not garbage-collect it
        mid-flight."""
        anim = QPropertyAnimation(widget, b"maximumHeight")
        anim.setDuration(self.SIDEBAR_ANIM_MS)
        anim.setEasingCurve(self.ANIM_EASING)
        anim.setStartValue(start)
        anim.setEndValue(end)
        if restore_to is not None:
            anim.finished.connect(lambda w=widget, v=restore_to: w.setMaximumHeight(v))
        self._active_animations.append(anim)
        anim.finished.connect(lambda a=anim: self._drop_finished_animation(a))
        anim.start()

    def _drop_finished_animation(self, anim):
        try:
            self._active_animations.remove(anim)
        except ValueError:
            pass

    def update_sidebar_header_colors(self):
        is_dark = self.theme_chk.isChecked()
        theme_key = "dark" if is_dark else "light"
        for group_name, header_btn in self.group_headers.items():
            color = HEADER_COLORS[theme_key].get(group_name, "#6b7280")
            header_btn.setStyleSheet(f"color: {color};")

    def update_sidebar_experience(self):
        """Rebuild the sidebar and notify the current view of the new tier
        so its in-view complexity (e.g. advanced expanders) can update."""
        self.build_navigation_sidebar()
        if self.current_view and hasattr(self.current_view, "apply_tier"):
            tier_name = config.get("settings_ui_tier", "Simple")
            self.current_view.apply_tier(tier_name)

    def switch_view(self, title):
        if self.current_view:
            self.current_view.unmount()

        view = self.views.get(title)
        if view:
            same_view = (view is self.current_view)
            self.content_stack.setCurrentWidget(view)
            view.mount()
            self.current_view = view
            self.setWindowTitle(f"DataForge - {title}")

            # 2e.1 view crossfade — start the new view at opacity 0 and
            # animate to 1. The first switch at startup is also faded in
            # so the dashboard reveal is consistent with the rest of the
            # app. ``switch_view`` is the only call that mutates the
            # effect's opacity.
            if not same_view:
                effect = view.graphicsEffect()
                if isinstance(effect, QGraphicsOpacityEffect):
                    self._animate_opacity(effect, 0.0, 1.0)

            # Highlight active nav button
            for btn, btn_title in self.nav_buttons:
                if btn_title == title:
                    btn.setChecked(True)
                    self._active_nav_btn = btn
                else:
                    btn.setChecked(False)

    def _animate_opacity(self, effect, start, end):
        """Fade a ``QGraphicsOpacityEffect`` from *start* to *end*."""
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(self.VIEW_ANIM_MS)
        anim.setEasingCurve(self.ANIM_EASING)
        anim.setStartValue(start)
        anim.setEndValue(end)
        self._active_animations.append(anim)
        anim.finished.connect(lambda a=anim: self._drop_finished_animation(a))
        anim.start()



    def reset_status(self):
        self.update_status("Ready")
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        self.cancel_btn.setVisible(False)
        self.spinner_label.setText("  ")

    def start_progress(self, message: str = "Working..."):
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.update_status(message)

    def update_progress(self, current: int, total: int, step_name: str = ""):
        self.progress_bar.setVisible(True)
        if total > 0:
            pct = int((current / total) * 100)
            self.progress_bar.setValue(pct)
            txt = f"{step_name}: {current}/{total} ({pct}%)"
        else:
            self.progress_bar.setValue(0)
            txt = f"{step_name}: {current}..."
        self.update_status(txt)

    def set_task_name(self, name: str):
        """Override the name shown in the status bar for the running task.

        Most callers should pass ``task_name=`` to ``run_workflow`` instead.
        This helper exists for places that spawn a task inside another
        workflow and need to relabel what the user sees."""
        if name:
            self._current_task_name = name
            self.update_status(f"Running: {name}…")

    def post_to_main(self, callback: Callable[..., Any], *args: Any, **kwargs: Any):
        self.post_signal.emit(callback, args, kwargs)

    def _handle_posted_event(self, callback, args, kwargs):
        if callback:
            callback(*args, **kwargs)

    def post_progress(self, current: int, total: int, step_name: str = ""):
        curr_thread = QThread.currentThread()
        if isinstance(curr_thread, BackgroundWorker):
            curr_thread.progress_signal.emit(current, total, step_name)
        else:
            self.update_progress(current, total, step_name)

    def post_status(self, message: str):
        curr_thread = QThread.currentThread()
        if isinstance(curr_thread, BackgroundWorker):
            curr_thread.status_signal.emit(message)
        else:
            self.update_status(message)

    def show_error_dialog(self, title: str, message: str):
        QMessageBox.critical(self, title, message)

    def show_warning_dialog(self, title: str, message: str):
        QMessageBox.warning(self, title, message)

    def show_info_dialog(self, title: str, message: str):
        QMessageBox.information(self, title, message)

    def show_workflow_error(self, error: Exception | str, title: str = "Operation Failed"):
        message = str(error)
        self.update_status(f"Error: {message}")
        self.show_error_dialog(title, message)

    def make_progress_callback(self) -> ProgressCallback:
        return self.post_progress

    def run_workflow(
        self,
        target: BackgroundTarget,
        on_success: SuccessCallback | None = None,
        *args,
        on_error: ErrorCallback | None = None,
        progress: bool = False,
        error_title: str = "Operation Failed",
        task_name: str | None = None,
    ) -> None:
        kwargs = {}
        signature = inspect.signature(target)
        if progress and "progress_callback" in signature.parameters:
            kwargs["progress_callback"] = self.make_progress_callback()
        error_handler = on_error or partial(self.show_workflow_error, title=error_title)
        self.run_background(
            target, on_success, *args,
            on_error=error_handler,
            show_progress=progress,
            task_name=task_name,
            **kwargs,
        )

    def run_background(
        self,
        target: BackgroundTarget,
        callback: SuccessCallback | None,
        *args: Any,
        on_error: ErrorCallback | None = None,
        show_progress: bool = False,
        task_name: str | None = None,
        **extra_kwargs: Any,
    ) -> None:
        """
        Run a target function in a background thread.
        Automatically starts spinner and handles cancellation.
        """
        if self.is_busy:
            current = getattr(self, "_current_task_name", None) or "another task"
            self.update_status(
                f"Busy: '{current}' is still running — please wait for it to finish."
            )
            return

        self.reset_status()
        self._current_task_name = task_name or _humanize_callable_name(target)
        self.update_status(f"Running: {self._current_task_name}…")

        self.is_busy = True
        self.cancel_event.clear()
        self.spinner_timer.start(100)
        self.cancel_btn.setVisible(True)
        if show_progress:
            self.start_progress()

        # Create Background worker thread
        self.current_worker = BackgroundWorker(target, args, extra_kwargs, self.cancel_event)
        
        # Connect signals
        self.current_worker.progress_signal.connect(self.update_progress)
        self.current_worker.status_signal.connect(self.update_status)
        
        if callback:
            self.current_worker.result_signal.connect(callback)
            
        if on_error:
            self.current_worker.error_signal.connect(on_error)
        else:
            self.current_worker.error_signal.connect(lambda e: self.update_status(f"Error: {e}"))
            
        # Clean up slot
        self.current_worker.finished.connect(self._on_worker_finished)
        
        self.current_worker.start()

    def _on_worker_finished(self):
        self.is_busy = False
        self.spinner_timer.stop()
        self.spinner_label.setText("  ")
        self.cancel_btn.setVisible(False)
        self.progress_bar.setVisible(False)
        self.current_worker = None
        self._current_task_name = None

    def run_in_thread(
        self,
        target: BackgroundTarget,
        callback: SuccessCallback | None,
        *args: Any,
        _error_callback: ErrorCallback | None = None,
        **extra_kwargs: Any,
    ) -> None:
        self.run_background(target, callback, *args, on_error=_error_callback, **extra_kwargs)

    def toggle_theme(self):
        is_dark = self.theme_chk.isChecked()
        self.apply_theme(is_dark)
        config.set("theme", "darkly" if is_dark else "cosmo")
        self.update_sidebar_header_colors()
        self._update_theme_icon(is_dark)

    def _update_theme_icon(self, is_dark: bool):
        if hasattr(self, "theme_icon_lbl"):
            self.theme_icon_lbl.setText("🌙" if is_dark else "☀")

    def apply_theme(self, is_dark: bool):
        """
        Applies style/palette at the QApplication level (not just this window)
        so dialogs (QFileDialog, QMessageBox, tooltips, popups) — which are
        separate top-level windows — pick up the same theme instead of
        falling back to the platform's default look.

        Updating the QApplication-wide stylesheet is what makes Qt re-polish
        every widget; doing it while updates are frozen (and showing the
        busy cursor) keeps the change snappy and avoids the visible
        "re-flow" flicker that previously made the toggle feel slow.
        """
        qapp = QApplication.instance()
        qapp.setOverrideCursor(Qt.WaitCursor)
        # Freeze repaints across the application so the repolish pass
        # applies in a single composite pass when we unfreeze below.
        for w in qapp.topLevelWidgets():
            w.setUpdatesEnabled(False)
        try:
            qapp.setStyle("Fusion")
            qapp.setPalette(DARK_PALETTE if is_dark else LIGHT_PALETTE)
            qapp.setStyleSheet(DARK_STYLE if is_dark else LIGHT_STYLE)
        finally:
            for w in qapp.topLevelWidgets():
                w.setUpdatesEnabled(True)
            qapp.restoreOverrideCursor()
            for w in qapp.topLevelWidgets():
                w.update()

    def show_current_help(self):
        if self.current_view:
            self.current_view.show_help()
        else:
            QMessageBox.information(self, "Help", "Select a view to see help.")
