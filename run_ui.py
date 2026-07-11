import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from filemanager.ui.app import FileManagerApp
from filemanager.ui.splash import SplashScreen

def main():
    # Enable High-DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    splash = SplashScreen()
    splash.show()
    app.processEvents()

    window = FileManagerApp(on_progress=splash.update_progress)
    window.show()
    splash.close()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
