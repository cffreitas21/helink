from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class StateBadge(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        normalized = str(state or '').strip().upper()
        object_name = {
            'SET': 'stateSet',
            'CLEARED': 'stateCleared',
        }.get(normalized, 'stateNeutral')
        self.setObjectName('stateCell')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setAlignment(Qt.AlignCenter)
        badge = QLabel(normalized or 'N/A')
        badge.setObjectName(object_name)
        badge.setAlignment(Qt.AlignCenter)
        badge.setMinimumWidth(86)
        badge.setFixedHeight(30)
        layout.addWidget(badge)
