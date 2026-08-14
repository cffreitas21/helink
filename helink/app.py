from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from helink.bootstrap import build_main_window
from helink.ui.theme import STYLE


def run():
    app = QApplication(sys.argv)
    app.setApplicationName('HELINK')
    app.setStyleSheet(STYLE)
    window = build_main_window()
    window.show()
    sys.exit(app.exec())
