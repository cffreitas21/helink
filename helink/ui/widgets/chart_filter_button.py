"""Multi-select popover for telemetry chart visibility."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton,
    QToolButton, QVBoxLayout, QWidget, QWidgetAction,
)


class _ChartCheckBox(QCheckBox):
    """Make the full chart-filter option respond to clicks."""
    def hitButton(self, position):
        """Use the complete option rectangle as the checkbox hit area."""
        # Treat the entire menu row as a checkbox target, including whitespace.
        # Otherwise an ignored click can propagate to QMenu and close it.
        return self.rect().contains(position)


class ChartFilterButton(QToolButton):
    """Persistent checkbox menu for choosing visible telemetry charts."""

    selection_changed = Signal(object)

    def __init__(self, parameters, parent=None):
        """Build a popup of checkable telemetry parameters."""
        super().__init__(parent)
        self.parameters = tuple(parameters)
        self.checkboxes = {}
        self.setObjectName('chartFilterButton')
        self.setPopupMode(QToolButton.InstantPopup)
        self.setAccessibleName('Choose visible telemetry charts')
        self.setToolTip('Choose which telemetry charts to display')

        menu = QMenu(self)
        content = QWidget()
        content.setObjectName('chartFilterContent')
        content.setMinimumWidth(235)
        layout = QVBoxLayout(content)
        self.content_layout = layout
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)
        heading = QLabel('Visible Charts')
        heading.setObjectName('chartFilterTitle')
        layout.addWidget(heading)
        actions = QHBoxLayout()
        self.select_all = QPushButton('Select All')
        self.clear_all = QPushButton('Clear All')
        for button in (self.select_all, self.clear_all):
            button.setObjectName('chartFilterBulk')
            actions.addWidget(button)
        layout.addLayout(actions)
        divider = QFrame()
        divider.setObjectName('chartFilterDivider')
        divider.setFrameShape(QFrame.HLine)
        layout.addWidget(divider)
        for key, title, *_metadata in self.parameters:
            checkbox = _ChartCheckBox(title)
            checkbox.setChecked(True)
            checkbox.toggled.connect(self._emit_selection)
            self.checkboxes[key] = checkbox
            layout.addWidget(checkbox)
        action = QWidgetAction(menu)
        action.setDefaultWidget(content)
        menu.addAction(action)
        self.setMenu(menu)
        self.select_all.clicked.connect(
            lambda: self.set_selected(self.checkboxes)
        )
        self.clear_all.clicked.connect(lambda: self.set_selected(()))
        self._update_caption()

    def selected_keys(self):
        """Return parameter keys currently enabled in the chart picker."""
        return tuple(
            key for key, checkbox in self.checkboxes.items()
            if checkbox.isChecked()
        )

    def add_parameter(self, parameter):
        """Offer an Overview-only parameter without selecting other charts."""
        key, title, *_metadata = parameter
        if key in self.checkboxes:
            return
        checkbox = _ChartCheckBox(title)
        checkbox.toggled.connect(self._emit_selection)
        self.checkboxes[key] = checkbox
        self.parameters += (parameter,)
        self.content_layout.addWidget(checkbox)
        self._update_caption()

    def set_selected(self, keys):
        """Select exactly the provided chart parameter keys."""
        selected = set(keys)
        for key, checkbox in self.checkboxes.items():
            blocked = checkbox.blockSignals(True)
            try:
                checkbox.setChecked(key in selected)
            finally:
                checkbox.blockSignals(blocked)
        self._emit_selection()

    def _update_caption(self):
        """Summarize how many chart channels are currently selected."""
        self.setText(f'Charts ({len(self.selected_keys())}/{len(self.checkboxes)})')

    def _emit_selection(self, *_):
        """Notify the telemetry tab when the chosen channels change."""
        self._update_caption()
        self.selection_changed.emit(self.selected_keys())
