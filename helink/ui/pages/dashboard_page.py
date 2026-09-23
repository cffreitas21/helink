from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from helink.ui.dialogs import DeleteAircraftDialog
from helink.ui.telemetry_parameters import TELEMETRY_PARAMETERS
from helink.ui.widgets import Card, FleetParameterCard


FLEET_PARAMETER_KEYS = {
    'itt', 'eng_ot', 'eng_op', 'xmsn_ot', 'xmsn_op', 'fuel_press',
}


class DashboardPage(QWidget):
    aircraft_selected = Signal(str)
    add_requested = Signal()

    def __init__(self, aircraft_controller):
        super().__init__()
        self.aircraft_controller = aircraft_controller

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(14)

        heading = QHBoxLayout()
        title = QLabel('Fleet Management')
        title.setObjectName('title')
        heading.addWidget(title)
        heading.addStretch()
        add_button = QPushButton('\N{FULLWIDTH PLUS SIGN} Add Aircraft')
        add_button.clicked.connect(self.add_requested)
        heading.addWidget(add_button)
        delete_button = QPushButton('Delete Aircraft')
        delete_button.setObjectName('danger')
        delete_button.clicked.connect(self.choose_aircraft_to_delete)
        heading.addWidget(delete_button)
        root.addLayout(heading)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.container = QWidget()
        self.list = QVBoxLayout(self.container)
        self.list.setContentsMargins(0, 4, 0, 4)
        self.list.setSpacing(12)
        scroll.setWidget(self.container)
        root.addWidget(scroll)

    def refresh(self):
        aircraft = self.aircraft_controller.list_aircraft()
        summaries = self.aircraft_controller.fleet_summaries()
        self._clear_list()

        if not aircraft:
            self._add_empty_state()
        else:
            for item in aircraft:
                self.list.addWidget(
                    self._aircraft_card(item, summaries.get(item.id, {}))
                )
        self.list.addStretch()

    def _clear_list(self):
        while self.list.count():
            item = self.list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_empty_state(self):
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
        card = QFrame()
        card.setObjectName('aircraftRow')
        root = QVBoxLayout(card)
        root.setContentsMargins(16, 13, 16, 15)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)

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
        header.addWidget(icon)

        identity = QVBoxLayout()
        identity.setSpacing(2)
        registration = QLabel(aircraft.registration)
        registration.setObjectName('fleetRegistration')
        identity.addWidget(registration)
        details = QLabel(f'{aircraft.model}  \N{MIDDLE DOT}  SN {aircraft.serial_number}')
        details.setObjectName('fleetModel')
        details.setToolTip(
            f'{aircraft.model} · Serial Number {aircraft.serial_number}'
        )
        identity.addWidget(details)
        flight_count = QLabel(
            f'{aircraft.flight_count} imported flight'
            if aircraft.flight_count == 1
            else f'{aircraft.flight_count} imported flights'
        )
        flight_count.setObjectName('fleetFlightCount')
        identity.addWidget(flight_count)
        header.addLayout(identity)
        header.addStretch()

        open_button = QPushButton('View Flights  \N{RIGHTWARDS ARROW}')
        open_button.setFixedSize(138, 44)
        open_button.clicked.connect(
            lambda _, aircraft_id=aircraft.id:
            self.aircraft_selected.emit(aircraft_id)
        )
        header.addWidget(open_button)
        root.addLayout(header)

        metrics = QHBoxLayout()
        metrics.setSpacing(6)
        metrics.addStretch()
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
        metrics.addStretch()
        root.addLayout(metrics)
        return card
    def choose_aircraft_to_delete(self):
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