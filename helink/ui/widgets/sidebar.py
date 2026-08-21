from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout
from pathlib import Path



class Sidebar(QFrame):
    """Main navigation component for the HELINK application."""

    dashboard_requested = Signal()
    import_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('sidebar')
        self.setFixedWidth(235)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 22, 16, 18)

        tagline = QLabel('Helicopter Flight Analysis & Maintenance')
        tagline.setWordWrap(True)
        tagline.setStyleSheet('color:#94a3b8')
        layout.addWidget(tagline)
        layout.addSpacing(25)

        self.dashboard_button = QPushButton('Fleet Overview')
        self.dashboard_button.setObjectName('nav')
        self.dashboard_button.clicked.connect(self.dashboard_requested)
        layout.addWidget(self.dashboard_button)

        self.import_button = QPushButton('Import Files')
        self.import_button.setObjectName('nav')
        self.import_button.clicked.connect(self.import_requested)
        layout.addWidget(self.import_button)

        self.sidebar_image = QLabel()
        self.sidebar_image.setAlignment(Qt.AlignCenter)
        self.sidebar_image.setFixedSize(203, 130)


        logo_path = (
                        Path(__file__).resolve().parents[2]
                        / 'assets'
                        / 'images'
                        / 'helink_logo.png'
            
                    )
        logo_pixmap = QPixmap(str(logo_path))

        self.sidebar_image.setPixmap(logo_pixmap.scaled(
                    self.sidebar_image.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                ))

        layout.addStretch()
        layout.addWidget(self.sidebar_image)
        layout.addStretch()

        footer = QLabel('\nHELINK - 2026')
        footer.setStyleSheet(
            'color:#aebdd0;font-size:11px;background:transparent'
        )
        layout.addWidget(footer)
