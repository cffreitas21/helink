"""Size-aware button for important Overview flight events."""

from PySide6.QtWidgets import QToolButton


class OverviewEventButton(QToolButton):
    """Clickable event badge in the flight summary."""

    def sizeHint(self):
        """Suggest a card size that accommodates its wrapped caption."""
        layout = self.layout()
        if layout is not None:
            return layout.sizeHint().expandedTo(self.minimumSize())
        return super().sizeHint()

    def minimumSizeHint(self):
        """Return the smallest usable size for the event card."""
        layout = self.layout()
        if layout is not None:
            return layout.minimumSize().expandedTo(self.minimumSize())
        return super().minimumSizeHint()

    def heightForWidth(self, width):
        """Calculate the card height needed for the available width."""
        layout = self.layout()
        if layout is not None and layout.hasHeightForWidth():
            return max(self.minimumHeight(), layout.totalHeightForWidth(width))
        return self.sizeHint().height()
