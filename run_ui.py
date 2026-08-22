import os
# Suppress benign Wayland warning: QWindow::requestActivate() is not supported
# on Wayland by design (activation is compositor-controlled). The app shows
# correctly without it; we just silence the warning category.
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.wayland.warning=false")

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from dataforge.ui.app import DataForgeApp
from dataforge.ui.splash import SplashScreen

def main():
    # Enable High-DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    splash = SplashScreen()
    splash.show()
    app.processEvents()

    window = DataForgeApp(on_progress=splash.update_progress)
    window.show()
    splash.close()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
