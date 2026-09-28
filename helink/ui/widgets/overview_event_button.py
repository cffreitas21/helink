from PySide6.QtWidgets import QToolButton


class OverviewEventButton(QToolButton):
    """Clickable overview card whose wrapped content determines its height."""

    def sizeHint(self):
        layout = self.layout()
        if layout is not None:
            return layout.sizeHint().expandedTo(self.minimumSize())
        return super().sizeHint()

    def minimumSizeHint(self):
        layout = self.layout()
        if layout is not None:
            return layout.minimumSize().expandedTo(self.minimumSize())
        return super().minimumSizeHint()

    def heightForWidth(self, width):
        layout = self.layout()
        if layout is not None and layout.hasHeightForWidth():
            return max(self.minimumHeight(), layout.totalHeightForWidth(width))
        return self.sizeHint().height()
