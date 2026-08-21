from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from helink.bootstrap import build_main_window
from helink.ui.theme import STYLE


def run():
    app = QApplication(sys.argv)
    app.setApplicationName('HELINK')

    icon_path = (
        Path(__file__).resolve().parent
        / 'assets'
        / 'images'
        / 'helink_icon.ico'
    )
    app.setWindowIcon(QIcon(str(icon_path)))

    app.setStyleSheet(STYLE)

    window = build_main_window()
    window.show()

    sys.exit(app.exec())
