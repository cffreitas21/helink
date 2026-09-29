from PySide6.QtCore import QCoreApplication, QDate, QEvent, QPoint, Signal
from PySide6.QtGui import QActionEvent
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFormLayout, QHBoxLayout, QLabel, QMenu,
    QPushButton, QVBoxLayout, QWidget, QWidgetAction,
)


class FlightDateFilterButton(QComboBox):
    """Date or inclusive date-range filter applied explicitly from a popup."""

    range_changed = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('flightDateFilter')
        self.addItem('Dates: All')
        self.setMinimumWidth(160)
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.setAccessibleName('Filter flights by date')
        self._active_range = (None, None)
        self._available_dates = (QDate.currentDate(), QDate.currentDate())
        menu = QMenu(self)
        self._popup_menu = menu
        menu.aboutToHide.connect(super().hidePopup)
        content = QWidget()
        content.setObjectName('flightDateFilterContent')
        content.setMinimumWidth(285)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        heading = QLabel('Filter by Date')
        heading.setObjectName('flightDateFilterTitle')
        layout.addWidget(heading)
        self.mode = QComboBox()
        self.mode.addItems(('All Dates', 'Single Date', 'Date Range'))
        self.mode.setAccessibleName('Date filter type')
        layout.addWidget(self.mode)
        fields = QFormLayout()
        fields.setHorizontalSpacing(10)
        fields.setVerticalSpacing(8)
        self.start_label, self.end_label = QLabel('From'), QLabel('To')
        self.start_edit = QDateEdit(QDate.currentDate())
        self.end_edit = QDateEdit(QDate.currentDate())
        for field, name in (
            (self.start_edit, 'Flight date or interval start'),
            (self.end_edit, 'Interval end date'),
        ):
            field.setCalendarPopup(True)
            field.setDisplayFormat('dd/MM/yyyy')
            field.setAccessibleName(name)
            field.dateChanged.connect(self._validate)
        fields.addRow(self.start_label, self.start_edit)
        fields.addRow(self.end_label, self.end_edit)
        self.start_label.setBuddy(self.start_edit)
        self.end_label.setBuddy(self.end_edit)
        layout.addLayout(fields)
        self.error = QLabel('The end date must be on or after the start date.')
        self.error.setObjectName('flightDateFilterError')
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        self.clear_button = QPushButton('Clear')
        self.clear_button.setObjectName('secondary')
        self.apply_button = QPushButton('Apply')
        actions.addWidget(self.clear_button)
        actions.addStretch()
        actions.addWidget(self.apply_button)
        layout.addLayout(actions)
        action = QWidgetAction(menu)
        action.setDefaultWidget(content)
        menu.addAction(action)
        self._action = action
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.clear_button.clicked.connect(self.reset)
        self.apply_button.clicked.connect(self.apply)
        self._mode_changed()
        self._update_caption()

    def showPopup(self):
        """Use the same dropdown control as sorting, with date fields inside."""
        self._popup_menu.popup(self.mapToGlobal(QPoint(0, self.height())))

    def hidePopup(self):
        self._popup_menu.hide()
        super().hidePopup()

    def menu(self):
        return self._popup_menu

    def text(self):
        return self.currentText()

    @property
    def date_range(self):
        return self._active_range

    def set_available_dates(self, dates):
        parsed = [
            value for text in dates
            if (value := QDate.fromString(str(text), 'yyyy-MM-dd')).isValid()
        ]
        if parsed:
            self._available_dates = (min(parsed), max(parsed))

    def _mode_changed(self, *_):
        mode = self.mode.currentIndex()
        self.start_label.setText('Date' if mode == 1 else 'From')
        self.start_label.setVisible(mode != 0)
        self.start_edit.setVisible(mode != 0)
        self.end_label.setVisible(mode == 2)
        self.end_edit.setVisible(mode == 2)
        if self._active_range == (None, None):
            earliest, latest = self._available_dates
            self.start_edit.setDate(latest if mode == 1 else earliest)
            self.end_edit.setDate(latest)
        self._validate()

    def _validate(self, *_):
        invalid = (
            self.mode.currentIndex() == 2
            and self.start_edit.date() > self.end_edit.date()
        )
        self.error.setVisible(invalid)
        self.apply_button.setEnabled(not invalid)
        # QMenu caches widget-action heights. Invalidate that cache when fields
        # or validation feedback become visible, then resize the popup.
        if self.menu() is not None:
            QCoreApplication.sendEvent(
                self.menu(), QActionEvent(QEvent.ActionChanged, self._action),
            )
            self.menu().adjustSize()

    def apply(self):
        self.start_edit.interpretText()
        self.end_edit.interpretText()
        self._validate()
        if not self.apply_button.isEnabled():
            return
        mode = self.mode.currentIndex()
        start = self.start_edit.date().toString('yyyy-MM-dd') if mode else None
        end = self.end_edit.date().toString('yyyy-MM-dd') if mode == 2 else start
        self._active_range = (start, end)
        self._update_caption()
        self.menu().hide()
        self.range_changed.emit(start, end)

    def reset(self, *_args, emit=True):
        self._active_range = (None, None)
        self.mode.setCurrentIndex(0)
        self._mode_changed()
        self._update_caption()
        self.menu().hide()
        if emit:
            self.range_changed.emit(None, None)

    def _update_caption(self):
        start, end = self._active_range
        if start is None:
            text = 'Dates: All'
            tooltip = 'Show all flights or filter by a date or date range'
        elif start == end:
            text = 'Date: ' + QDate.fromString(start, 'yyyy-MM-dd').toString('dd/MM/yyyy')
            tooltip = 'Flights on ' + text.removeprefix('Date: ')
        else:
            start_text = QDate.fromString(start, 'yyyy-MM-dd').toString('dd/MM/yyyy')
            end_text = QDate.fromString(end, 'yyyy-MM-dd').toString('dd/MM/yyyy')
            text = f'Dates: {start_text} - {end_text}'
            tooltip = f'Flights from {start_text} to {end_text}, including both dates'
        self.setItemText(0, text)
        self.setToolTip(tooltip)
        self.setProperty('filterActive', start is not None)
        self.style().unpolish(self)
        self.style().polish(self)
