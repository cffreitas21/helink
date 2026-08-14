from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QPushButton, QVBoxLayout


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('About HELINK')
        self.setFixedSize(520, 390)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(10)

        product = QLabel('HELINK')
        product.setAlignment(Qt.AlignCenter)
        product.setStyleSheet(
            'font-size:24px;font-weight:800;color:#0f172a'
        )
        layout.addWidget(product)

        description = QLabel(
            'Helicopter Analysis and Preventive Maintenance System'
        )
        description.setAlignment(Qt.AlignCenter)
        description.setWordWrap(True)
        description.setObjectName('muted')
        layout.addWidget(description)

        version = QLabel('2026  \u00b7  v1.0')
        version.setAlignment(Qt.AlignCenter)
        version.setObjectName('muted')
        layout.addWidget(version)
        layout.addSpacing(12)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet('color:#cbd5e1')
        layout.addWidget(separator)
        layout.addSpacing(8)

        map_heading = QLabel('Offline map attribution')
        map_heading.setAlignment(Qt.AlignCenter)
        map_heading.setStyleSheet('font-weight:700;color:#334155')
        layout.addWidget(map_heading)

        attribution = QLabel(
            'Map data from '
            '<a style="color:#2563eb;" href="https://www.openstreetmap.org/copyright">'
            'OpenStreetMap contributors</a><br>'
            'Licensed under the Open Database License (ODbL)<br>'
            'Map rendering powered by '
            '<a style="color:#2563eb;" href="https://protomaps.com">Protomaps</a><br>'
            'Map interface powered by '
            '<a style="color:#2563eb;" href="https://leafletjs.com">Leaflet</a>'
        )
        attribution.setTextFormat(Qt.RichText)
        attribution.setTextInteractionFlags(Qt.TextBrowserInteraction)
        attribution.setOpenExternalLinks(True)
        attribution.setAlignment(Qt.AlignCenter)
        attribution.setWordWrap(True)
        attribution.setObjectName('muted')
        layout.addWidget(attribution)
        layout.addStretch()

        close_button = QPushButton('Close')
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
