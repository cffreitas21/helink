"""Fleet cards, ordering controls, and aircraft actions."""

from __future__ import annotations

from math import isfinite

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

from helink.ui.dialogs import DeleteAircraftDialog
from helink.ui.telemetry_parameters import TELEMETRY_PARAMETERS
from helink.ui.widgets import Card, FleetParameterCard


FLEET_PARAMETER_KEYS = {
    'itt', 'eng_ot', 'eng_op', 'xmsn_ot', 'xmsn_op', 'fuel_press',
}


class FleetPage(QWidget):
    """Display aircraft cards, fleet parameter summaries, and sorting tools."""
    aircraft_selected = Signal(str)
    analysis_requested = Signal(str)
    add_requested = Signal()

    def __init__(self, aircraft_controller):
        """Build fleet controls and connect aircraft-related actions."""
        super().__init__()
        self.aircraft_controller = aircraft_controller
        self._rendered_data = None
        self._aircraft = ()
        self._summaries = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(14)

        heading = QHBoxLayout()
        left_actions = QHBoxLayout()
        title = QLabel('Fleet Management')
        title.setObjectName('title')
        left_actions.addWidget(title)
        left_actions.addStretch()
        heading.addLayout(left_actions, 1)
        analysis_button = QPushButton('Fleet Analysis')
        analysis_button.setObjectName('analysisNavigation')
        analysis_button.clicked.connect(lambda: self.analysis_requested.emit(''))
        heading.addWidget(analysis_button, 0, Qt.AlignCenter)
        right_actions = QHBoxLayout()
        right_actions.addStretch()
        add_button = QPushButton('\N{FULLWIDTH PLUS SIGN} Add Aircraft')
        add_button.clicked.connect(self.add_requested)
        right_actions.addWidget(add_button)
        delete_button = QPushButton('Delete Aircraft')
        delete_button.setObjectName('danger')
        delete_button.clicked.connect(self.choose_aircraft_to_delete)
        right_actions.addWidget(delete_button)
        heading.addLayout(right_actions, 1)
        root.addLayout(heading)

        sorting = QHBoxLayout()
        sorting.setSpacing(10)
        sort_label = QLabel('Sort by')
        sort_label.setObjectName('muted')
        sorting.addWidget(sort_label)
        self.sort_by = QComboBox()
        self.sort_by.setObjectName('fleetSort')
        self.sort_by.setAccessibleName('Sort aircraft by')
        self.sort_by.setMinimumWidth(220)
        self.sort_by.addItem('Tail number', 'registration')
        for key, label, _unit, _color in TELEMETRY_PARAMETERS:
            if key in FLEET_PARAMETER_KEYS:
                self.sort_by.addItem(f'{label} - AVG', f'avg_{key}')
                self.sort_by.addItem(f'{label} - MAX', f'max_{key}')
        sorting.addWidget(self.sort_by)
        self.sort_order = QComboBox()
        self.sort_order.setObjectName('fleetSort')
        self.sort_order.setAccessibleName('Aircraft sort direction')
        self.sort_order.setMinimumWidth(140)
        self.sort_order.addItem('A to Z', 'ascending')
        self.sort_order.addItem('Z to A', 'descending')
        sorting.addWidget(self.sort_order)
        sorting.addStretch()
        root.addLayout(sorting)
        self.sort_by.currentIndexChanged.connect(self._sort_field_changed)
        self.sort_order.currentIndexChanged.connect(self._render_list)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.container = QWidget()
        self.list = QVBoxLayout(self.container)
        self.list.setContentsMargins(0, 4, 0, 4)
        self.list.setSpacing(12)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll)

    def refresh(self, prepared=None):
        """Reload aircraft and summaries, optionally using prepared results."""
        if prepared is not None and prepared is self._rendered_data:
            return
        if prepared is None:
            aircraft = self.aircraft_controller.list_aircraft()
            summaries = self.aircraft_controller.fleet_summaries()
        else:
            aircraft, summaries = prepared
        self._rendered_data = prepared
        self._aircraft = tuple(aircraft)
        self._summaries = summaries
        self._render_list()

    def _sort_field_changed(self, *_):
        """Adjust available sort directions when the chosen metric changes."""
        numeric = self.sort_by.currentData() != 'registration'
        blocked = self.sort_order.blockSignals(True)
        self.sort_order.setItemText(0, 'Lowest first' if numeric else 'A to Z')
        self.sort_order.setItemText(1, 'Highest first' if numeric else 'Z to A')
        self.sort_order.setCurrentIndex(1 if numeric else 0)
        self.sort_order.blockSignals(blocked)
        self._render_list()

    def _ordered_aircraft(self):
        """Sort aircraft using the current tail-number or parameter criterion."""
        field = self.sort_by.currentData()
        descending = self.sort_order.currentData() == 'descending'
        identity = lambda item: (item.registration.casefold(), item.id)
        if field == 'registration':
            return sorted(self._aircraft, key=identity, reverse=descending)

        measured = []
        missing = []
        for item in self._aircraft:
            value = self._summaries.get(item.id, {}).get(field)
            try:
                number = float(value)
            except (TypeError, ValueError):
                number = None
            if number is None or not isfinite(number):
                missing.append(item)
            else:
                measured.append((item, number))
        measured.sort(key=lambda pair: (
            -pair[1] if descending else pair[1], *identity(pair[0]),
        ))
        return (
            [item for item, _number in measured]
            + sorted(missing, key=identity)
        )

    def _render_list(self, *_):
        """Rebuild the visible fleet cards in the selected order."""
        self._clear_list()

        if not self._aircraft:
            self._add_empty_state()
        else:
            for item in self._ordered_aircraft():
                self.list.addWidget(
                    self._aircraft_card(item, self._summaries.get(item.id, {}))
                )
        self.list.addStretch()
        self.scroll.verticalScrollBar().setValue(0)

    def _clear_list(self):
        """Remove the current fleet cards before a redraw."""
        while self.list.count():
            item = self.list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def _add_empty_state(self):
        """Show guidance when the fleet has no registered aircraft."""
        empty = Card()
        empty.layout.setContentsMargins(28, 32, 28, 32)
        message = QLabel('There are no helicopters in the fleet yet')
        message.setAlignment(Qt.AlignCenter)
        message.setStyleSheet('font-size:17px;font-weight:700')
        empty.layout.addWidget(message)
        hint = QLabel(
            'Add the first aircraft to start importing and analysing flights.'
        )
        hint.setObjectName('muted')
        hint.setAlignment(Qt.AlignCenter)
        empty.layout.addWidget(hint)
        self.list.addWidget(empty)

    def _aircraft_card(self, aircraft, summary):
        """Build one aircraft row with identity, metrics, and actions."""
        card = QFrame()
        card.setObjectName('aircraftRow')
        root = QHBoxLayout(card)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        icon = QFrame()
        icon.setObjectName('aircraftIcon')
        icon.setFixedSize(44, 44)
        icon_layout = QVBoxLayout(icon)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        glyph = QLabel('\N{AIRPLANE}')
        glyph.setAlignment(Qt.AlignCenter)
        glyph.setStyleSheet(
            'font-size:19px;color:#2563eb;background:transparent'
        )
        icon_layout.addWidget(glyph)
        root.addWidget(icon, 0, Qt.AlignVCenter)

        identity_panel = QWidget()
        identity_panel.setObjectName('fleetIdentity')
        identity_panel.setMinimumWidth(150)
        identity_panel.setMaximumWidth(180)
        identity_panel.setMinimumHeight(68)
        identity_panel.setStyleSheet('background:transparent')
        identity = QVBoxLayout(identity_panel)
        identity.setContentsMargins(0, 0, 0, 0)
        identity.setSpacing(2)
        registration = QToolButton()
        registration.setText(aircraft.registration)
        registration.setObjectName('fleetRegistration')
        registration.setCursor(Qt.PointingHandCursor)
        registration.setAccessibleName(f'View parameter trends for {aircraft.registration}')
        registration.setToolTip('Open daily parameter evolution and compare aircraft')
        registration.clicked.connect(
            lambda _, aircraft_id=aircraft.id:
            self.analysis_requested.emit(aircraft_id)
        )
        identity.addWidget(registration)
        details = QLabel(aircraft.model)
        details.setObjectName('fleetModel')
        details.setWordWrap(True)
        details.setTextFormat(Qt.PlainText)
        details.setToolTip(aircraft.model)
        identity.addWidget(details)
        serial = QLabel(f'SN {aircraft.serial_number}')
        serial.setObjectName('fleetSerial')
        serial.setWordWrap(True)
        serial.setTextFormat(Qt.PlainText)
        serial.setToolTip(f'Serial Number {aircraft.serial_number}')
        metadata = QHBoxLayout()
        metadata.setSpacing(8)
        metadata.addWidget(serial)
        metadata.addStretch()
        flight_count = QLabel(
            f'{aircraft.flight_count} imported flight'
            if aircraft.flight_count == 1
            else f'{aircraft.flight_count} imported flights'
        )
        flight_count.setObjectName('fleetFlightCount')
        metadata.addWidget(flight_count)
        identity.addLayout(metadata)
        root.addWidget(identity_panel, 0, Qt.AlignVCenter)

        metrics = QHBoxLayout()
        metrics.setSpacing(4)
        for key, label, unit, _color in TELEMETRY_PARAMETERS:
            if key not in FLEET_PARAMETER_KEYS:
                continue
            metrics.addWidget(
                FleetParameterCard(
                    label,
                    summary.get(f'avg_{key}'),
                    summary.get(f'max_{key}'),
                    unit,
                )
            )
        root.addLayout(metrics)
        root.addStretch()

        open_button = QPushButton('View Flights  \N{RIGHTWARDS ARROW}')
        open_button.setFixedSize(138, 68)
        open_button.clicked.connect(
            lambda _, aircraft_id=aircraft.id:
            self.aircraft_selected.emit(aircraft_id)
        )
        root.addWidget(open_button, 0, Qt.AlignVCenter)
        return card
    def choose_aircraft_to_delete(self):
        """Open the aircraft-selection and deletion confirmation dialog."""
        aircraft = self.aircraft_controller.list_aircraft()
        if not aircraft:
            QMessageBox.information(
                self, 'No aircraft', 'There are no aircraft to delete.'
            )
            return

        dialog = DeleteAircraftDialog(aircraft, self)
        if dialog.exec() != QDialog.Accepted:
            return

        selected = dialog.selected_aircraft
        self.aircraft_controller.delete(selected.id)
        self.refresh()
        QMessageBox.information(
            self,
            'Aircraft deleted',
            f'Aircraft {selected.registration} and its associated data '
            'have been deleted.',
        )
