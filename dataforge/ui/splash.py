"""
Startup splash screen shown while DataForgeApp constructs its views.

Progress is real, not simulated: DataForgeApp.__init__ accepts an
on_progress(current, total, message) callback and invokes it once per view
as it's constructed, so the bar and "what's loading" text track actual work.
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QApplication
from PyQt5.QtCore import Qt

from ..core.config import config


class SplashScreen(QWidget):
    WIDTH = 420
    HEIGHT = 200

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._center_on_screen()

        is_dark = config.get("theme", "cosmo") == "darkly"
        bg, fg, muted, accent, border = (
            ("#121214", "#e2e8f0", "#a1a1aa", "#6366f1", "#27272a") if is_dark
            else ("#ffffff", "#1f2937", "#6b7280", "#3b82f6", "#e5e7eb")
        )
        self.setStyleSheet(f"""
            QWidget#splashRoot {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 10px;
            }}
            QLabel#splashTitle {{
                color: {fg};
                font-size: 20px;
                font-weight: bold;
            }}
            QLabel#splashStatus {{
                color: {muted};
                font-size: 12px;
            }}
            QLabel#splashPct {{
                color: {accent};
                font-size: 12px;
                font-weight: bold;
            }}
            QProgressBar {{
                background-color: {"#1f1f23" if is_dark else "#f3f4f6"};
                border: none;
                border-radius: 5px;
                height: 10px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {accent};
                border-radius: 5px;
            }}
        """)
        self.setObjectName("splashRoot")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 24)
        layout.setSpacing(10)
        layout.addStretch()

        title = QLabel("DataForge", self)
        title.setObjectName("splashTitle")
        layout.addWidget(title)

        subtitle = QLabel("Starting up...", self)
        subtitle.setObjectName("splashStatus")
        layout.addWidget(subtitle)

        layout.addStretch()

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        status_row = QVBoxLayout()
        status_row.setSpacing(2)
        self.status_lbl = QLabel("Initializing...", self)
        self.status_lbl.setObjectName("splashStatus")
        status_row.addWidget(self.status_lbl)

        self.pct_lbl = QLabel("0%", self)
        self.pct_lbl.setObjectName("splashPct")
        self.pct_lbl.setAlignment(Qt.AlignRight)
        status_row.addWidget(self.pct_lbl)

        layout.addLayout(status_row)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.WIDTH) // 2
        y = geo.y() + (geo.height() - self.HEIGHT) // 2
        self.move(x, y)

    def update_progress(self, current, total, message=""):
        pct = int((current / total) * 100) if total else 0
        pct = max(0, min(100, pct))
        self.progress_bar.setValue(pct)
        self.pct_lbl.setText(f"{pct}%")
        if message:
            self.status_lbl.setText(message)
        # __init__ runs synchronously on the main thread, so nothing repaints
        # between steps unless we pump the event loop ourselves here.
        QApplication.processEvents()
