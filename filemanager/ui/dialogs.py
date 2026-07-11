"""
Drop-in QFileDialog replacements that always force the Qt-rendered (non-native)
dialog. Native/portal file choosers on Linux are drawn by the OS/desktop
environment and never pick up this app's light/dark theme or QSS, so a user
who selects Light mode can still get an unreadable dark-on-dark (or vice versa)
native dialog. Forcing DontUseNativeDialog makes the dialog a normal Qt widget
that inherits the QApplication-wide palette/stylesheet set in ui/app.py.
"""
from PyQt5.QtWidgets import QFileDialog

_NON_NATIVE = QFileDialog.DontUseNativeDialog


def get_existing_directory(parent=None, caption="Select Folder", directory=""):
    return QFileDialog.getExistingDirectory(
        parent, caption, directory, QFileDialog.ShowDirsOnly | _NON_NATIVE
    )


def get_open_file_name(parent=None, caption="Select File", directory="", filter=""):
    return QFileDialog.getOpenFileName(parent, caption, directory, filter, options=_NON_NATIVE)


def get_open_file_names(parent=None, caption="Select Files", directory="", filter=""):
    return QFileDialog.getOpenFileNames(parent, caption, directory, filter, options=_NON_NATIVE)


def get_save_file_name(parent=None, caption="Save File", directory="", filter=""):
    return QFileDialog.getSaveFileName(parent, caption, directory, filter, options=_NON_NATIVE)
