from PySide6.QtCore import QPoint, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton,
    QSpinBox, QVBoxLayout, QWidget, QWidgetAction,
)


class FlightDurationFilter(QComboBox):
    """A compact minimum-flight-time filter with quick choices and minute input."""

    minimum_changed = Signal(int)
    PRESETS = (0, 5, 10, 15, 20, 30)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('fleetDurationFilter')
        self.setAccessibleName('Filter by minimum flight duration')
        self.setMinimumWidth(160)
        self.addItem('Flights: All')

        self._popup_menu = QMenu(self)
        self._popup_menu.aboutToHide.connect(super().hidePopup)
        content = QWidget()
        content.setObjectName('flightDurationFilterContent')
        content.setMinimumWidth(302)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        title = QLabel('Minimum flight time')
        title.setObjectName('flightDurationFilterTitle')
        layout.addWidget(title)
        explanation = QLabel('Ignore flights shorter than the selected time.')
        explanation.setObjectName('muted')
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        presets = QGridLayout()
        presets.setSpacing(6)
        self.preset_buttons = {}
        for index, minutes in enumerate(self.PRESETS):
            button = QPushButton('All flights' if minutes == 0 else f'{minutes} min')
            button.setObjectName('durationPreset')
            button.setAccessibleName(
                'Include all flights' if minutes == 0
                else f'Minimum flight duration {minutes} minutes'
            )
            button.clicked.connect(
                lambda _checked=False, value=minutes: self._choose_preset(value)
            )
            presets.addWidget(button, index // 3, index % 3)
            self.preset_buttons[minutes] = button
        layout.addLayout(presets)

        custom = QHBoxLayout()
        custom_label = QLabel('Custom (min)')
        self.minimum_minutes = QSpinBox()
        self.minimum_minutes.setObjectName('fleetMinimumDuration')
        self.minimum_minutes.setAccessibleName('Custom minimum flight duration in minutes')
        self.minimum_minutes.setToolTip(
            'Use the arrows or type a number of minutes. '
            '0 includes all flights; unknown durations are excluded when a minimum is set.'
        )
        self.minimum_minutes.setRange(0, 1440)
        self.minimum_minutes.setSingleStep(1)
        self.minimum_minutes.setSuffix(' min')
        self.minimum_minutes.setValue(20)
        self.minimum_minutes.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.minimum_minutes.setMinimumWidth(80)
        self.minimum_minutes.setKeyboardTracking(False)
        self.minimum_minutes.setAccelerated(True)
        self.minimum_minutes.valueChanged.connect(self._value_changed)
        custom_label.setBuddy(self.minimum_minutes)
        self.decrease_button = QPushButton('\N{MINUS SIGN}')
        self.decrease_button.setObjectName('durationStepButton')
        self.decrease_button.setAccessibleName('Decrease minimum flight duration by one minute')
        self.decrease_button.setToolTip('Decrease by 1 minute')
        self.decrease_button.setFixedSize(34, 34)
        self.decrease_button.clicked.connect(self.minimum_minutes.stepDown)
        self.increase_button = QPushButton('+')
        self.increase_button.setObjectName('durationStepButton')
        self.increase_button.setAccessibleName('Increase minimum flight duration by one minute')
        self.increase_button.setToolTip('Increase by 1 minute')
        self.increase_button.setFixedSize(34, 34)
        self.increase_button.clicked.connect(self.minimum_minutes.stepUp)
        custom.addWidget(custom_label)
        custom.addStretch()
        custom.addWidget(self.decrease_button)
        custom.addWidget(self.minimum_minutes)
        custom.addWidget(self.increase_button)
        layout.addLayout(custom)

        action = QWidgetAction(self._popup_menu)
        action.setDefaultWidget(content)
        self._popup_menu.addAction(action)
        self._update_caption()

    def showPopup(self):
        self._popup_menu.popup(self.mapToGlobal(QPoint(0, self.height())))

    def hidePopup(self):
        self._popup_menu.hide()
        super().hidePopup()

    def _choose_preset(self, minutes):
        self.minimum_minutes.setValue(minutes)
        self._popup_menu.hide()

    def _value_changed(self, minutes):
        self._update_caption()
        self.minimum_changed.emit(minutes)

    def _update_caption(self):
        minutes = self.minimum_minutes.value()
        self.setItemText(0, 'Flights: All' if minutes == 0 else f'Flights: {minutes}+ min')
        self.setToolTip(
            'Include flights of any duration'
            if minutes == 0
            else f'Include only flights lasting at least {minutes} minutes'
        )
        self.setProperty('filterActive', minutes > 0)
        self.style().unpolish(self)
        self.style().polish(self)
        for value, button in self.preset_buttons.items():
            button.setProperty('selected', value == minutes)
            button.style().unpolish(button)
            button.style().polish(button)
        self.decrease_button.setEnabled(minutes > self.minimum_minutes.minimum())
        self.increase_button.setEnabled(minutes < self.minimum_minutes.maximum())
