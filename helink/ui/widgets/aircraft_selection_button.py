from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QMenu, QPushButton,
    QScrollArea, QStyle, QStyleOptionButton, QVBoxLayout, QWidget, QWidgetAction,
)


class _AircraftCheckBox(QCheckBox):
    def hitButton(self, position):
        return self.rect().contains(position)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isChecked():
            return
        # A styled indicator supplies the visible square but not a native tick.
        option = QStyleOptionButton()
        self.initStyleOption(option)
        rect = self.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, self)
        tick = QPainterPath()
        tick.moveTo(rect.left() + 4, rect.center().y())
        tick.lineTo(rect.left() + 8, rect.bottom() - 5)
        tick.lineTo(rect.right() - 4, rect.top() + 5)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(Qt.white, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(tick)


class AircraftSelectionButton(QComboBox):
    """Dropdown with persistent checkboxes for fleet comparisons."""

    selection_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('fleetAnalysisFilter')
        self.addItem('Aircraft (0)')
        self.setMinimumWidth(175)
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.setAccessibleName('Choose aircraft to compare')
        self.setToolTip('Select one aircraft for its evolution, or several to compare')
        self.checkboxes = {}
        self._menu = QMenu(self)
        self._menu.aboutToHide.connect(super().hidePopup)

    def showPopup(self):
        self._menu.popup(self.mapToGlobal(QPoint(0, self.height())))

    def hidePopup(self):
        self._menu.hide()
        super().hidePopup()

    def set_aircraft(self, aircraft, selected_ids, colors):
        self._menu.clear()
        self.checkboxes = {}
        content = QWidget()
        content.setObjectName('aircraftSelectionContent')
        content.setMinimumWidth(285)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 10)
        heading = QLabel('Compare Aircraft')
        heading.setObjectName('chartFilterTitle')
        layout.addWidget(heading)
        actions = QHBoxLayout()
        for text, choose_all in (('Select All', True), ('Clear All', False)):
            button = QPushButton(text)
            button.setObjectName('chartFilterBulk')
            button.clicked.connect(
                lambda _, all_=choose_all:
                self.set_selected(self.checkboxes if all_ else ())
            )
            actions.addWidget(button)
        layout.addLayout(actions)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(min(260, max(40, len(aircraft) * 34 + 8)))
        rows = QWidget()
        rows.setObjectName('aircraftSelectionContent')
        row_layout = QVBoxLayout(rows)
        row_layout.setContentsMargins(2, 2, 6, 2)
        row_layout.setSpacing(4)
        selected = set(selected_ids)
        for item in aircraft:
            row = QHBoxLayout()
            chip = QLabel()
            chip.setFixedSize(10, 10)
            chip.setStyleSheet(
                f'background:{colors[item.id]};border:none;border-radius:3px'
            )
            row.addWidget(chip)
            checkbox = _AircraftCheckBox(item.registration)
            checkbox.setToolTip(f'{item.model} - SN {item.serial_number}')
            checkbox.setChecked(item.id in selected)
            checkbox.toggled.connect(self._emit_selection)
            self.checkboxes[item.id] = checkbox
            row.addWidget(checkbox, 1)
            row_layout.addLayout(row)
        if not aircraft:
            row_layout.addWidget(QLabel('No aircraft available'))
        row_layout.addStretch()
        scroll.setWidget(rows)
        layout.addWidget(scroll)
        action = QWidgetAction(self._menu)
        action.setDefaultWidget(content)
        self._menu.addAction(action)
        self._update_caption()

    def selected_ids(self):
        return tuple(
            aircraft_id for aircraft_id, checkbox in self.checkboxes.items()
            if checkbox.isChecked()
        )

    def set_selected(self, aircraft_ids):
        selected = set(aircraft_ids)
        for aircraft_id, checkbox in self.checkboxes.items():
            blocked = checkbox.blockSignals(True)
            try:
                checkbox.setChecked(aircraft_id in selected)
            finally:
                checkbox.blockSignals(blocked)
        self._emit_selection()

    def _update_caption(self):
        ids = self.selected_ids()
        text = self.checkboxes[ids[0]].text() if len(ids) == 1 else f'Aircraft ({len(ids)})'
        self.setItemText(0, text)

    def _emit_selection(self, *_):
        self._update_caption()
        self.selection_changed.emit(self.selected_ids())
