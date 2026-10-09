"""Overview parameter tile that opens its telemetry chart."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSizePolicy

from helink.ui.widgets.overview_event_button import OverviewEventButton


class OverviewParameterButton(OverviewEventButton):
    """Layout-sized parameter card that requests a focused telemetry view."""

    parameter_selected = Signal(str)

    def __init__(self, key, label, parent=None):
        """Create a clickable parameter tile identified by ``key``."""
        super().__init__(parent)
        self.setObjectName('overviewParameter')
        self.setCursor(Qt.PointingHandCursor)
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setAccessibleName(f'Open {label} in Telemetry')
        self.clicked.connect(lambda: self.parameter_selected.emit(key))
