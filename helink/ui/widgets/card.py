"""Reusable framed card layout."""

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class Card(QFrame):
    """Reusable framed section with an optional heading and content layout."""
    def __init__(self, title='', parent=None):
        """Create a framed content layout with an optional heading."""
        super().__init__(parent)
        self.setObjectName('card')
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 14, 16, 14)
        self.layout.setSpacing(8)
        if title:
            label = QLabel(title)
            label.setStyleSheet('font-size:15px;font-weight:700')
            self.layout.addWidget(label)
