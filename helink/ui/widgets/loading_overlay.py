from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


class LoadingOverlay(QWidget):
    """Hide stale page content while leaving application navigation available."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('pageLoadingOverlay')
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet('QWidget#pageLoadingOverlay{background:#f1f5f9}')
        layout = QVBoxLayout(self)
        layout.addStretch()
        self.message = QLabel()
        self.message.setAlignment(Qt.AlignCenter)
        self.message.setStyleSheet('color:#334155;font-size:14px')
        layout.addWidget(self.message)
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setFixedSize(240, 6)
        progress.setTextVisible(False)
        layout.addWidget(progress, 0, Qt.AlignCenter)
        layout.addStretch()
        parent.installEventFilter(self)
        self.hide()

    def show_message(self, message):
        self.message.setText(message)
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize:
            self.setGeometry(watched.rect())
        return super().eventFilter(watched, event)
