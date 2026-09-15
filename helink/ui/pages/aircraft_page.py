from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QLabel,
    QMenu, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QToolButton, QVBoxLayout, QWidget,
)

from helink.services.airport_formatter import format_airport


class AircraftPage(QWidget):
    flight_selected = Signal(str)
    import_requested = Signal(str)
    back_requested = Signal()

    def __init__(self, aircraft_controller, flight_controller):
        super().__init__()
        self.aircraft_controller = aircraft_controller
        self.flight_controller = flight_controller
        self.aid = None
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(12)

        heading = QHBoxLayout()
        back = QPushButton('\u2190 Fleet')
        back.setObjectName('secondary')
        back.clicked.connect(self.back_requested)
        heading.addWidget(back)
        self.title = QLabel()
        self.title.setObjectName('title')
        heading.addWidget(self.title)
        heading.addStretch()
        import_button = QPushButton('\u21e7 Import Files')
        import_button.clicked.connect(lambda: self.import_requested.emit(self.aid))
        heading.addWidget(import_button)
        root.addLayout(heading)

        self.info = QLabel()
        self.info.setObjectName('muted')
        root.addWidget(self.info)

        toolbar = QHBoxLayout()
        self.flight_count = QLabel()
        self.flight_count.setObjectName('listSummary')
        toolbar.addWidget(self.flight_count)
        toolbar.addStretch()
        self.delete_btn = QPushButton('Delete Selected')
        self.delete_btn.setObjectName('danger')
        self.delete_btn.clicked.connect(self.delete_selected)
        toolbar.addWidget(self.delete_btn)
        root.addLayout(toolbar)

        self.table = QTableWidget(0, 8)
        self.table.setObjectName('flightTable')
        self.table.setHorizontalHeaderLabels([
            '', 'FLIGHT DATE', 'DEPARTURE', 'ARRIVAL', 'DURATION',
            'ORIGIN', 'IMPORTED FILES', 'ACTIONS',
        ])
        header = self.table.horizontalHeader()
        for column in range(7):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
        header.setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 46)
        self.table.setColumnWidth(1, 145)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 230)
        self.table.setColumnWidth(6, 145)
        header.setMinimumSectionSize(42)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(62)
        self.table.doubleClicked.connect(self.open_current)
        root.addWidget(self.table)

    def load(self, aircraft_id):
        self.aid = aircraft_id
        aircraft = next(
            item for item in self.aircraft_controller.list_aircraft() if item.id == aircraft_id
        )
        self.title.setText(aircraft.registration)
        self.info.setText(
            f'{aircraft.model} \u00b7 SN {aircraft.serial_number} '
        )
        rows = sorted(
            self.flight_controller.list_flights(aircraft_id),
            key=lambda flight: (str(flight.flight_date), str(flight.departure_time)),
        )
        count = len(rows)
        self.flight_count.setText(
            f'{count} imported flight' if count == 1
            else f'{count} imported flights  \u00b7  oldest first'
        )
        self.delete_btn.setEnabled(bool(rows))
        self.table.setRowCount(count)

        for row, flight in enumerate(rows):
            checkbox = QCheckBox()
            checkbox.setProperty('fid', flight.id)
            checkbox_box = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_box)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.addWidget(checkbox)
            self.table.setCellWidget(row, 0, checkbox_box)

            values = (
                flight.flight_date,
                flight.departure_time,
                flight.arrival_time or '\N{EM DASH}',
                flight.duration,
                format_airport(flight.origin),
            )
            for column, value in enumerate(values, 1):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(
                    Qt.AlignLeft | Qt.AlignVCenter
                    if column == 1 else Qt.AlignCenter
                )
                if column == 1:
                    item.setData(Qt.UserRole, flight.id)
                self.table.setItem(row, column, item)

            self.table.setCellWidget(
                row, 6, self._files_button(flight.imported_files)
            )

            actions = QWidget()
            actions.setObjectName('tableActions')
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(8, 8, 8, 8)
            action_layout.setSpacing(8)
            open_button = QPushButton('Open')
            open_button.setObjectName('tableAction')
            open_button.setFixedSize(82, 36)
            open_button.clicked.connect(
                lambda _, flight_id=flight.id:
                self.flight_selected.emit(flight_id)
            )
            delete_button = QPushButton('Delete')
            delete_button.setObjectName('tableDelete')
            delete_button.setFixedSize(82, 36)
            delete_button.clicked.connect(
                lambda _, flight_id=flight.id: self.delete_one(flight_id)
            )
            action_layout.addWidget(open_button)
            action_layout.addWidget(delete_button)
            action_layout.addStretch()
            self.table.setCellWidget(row, 7, actions)

    def _files_button(self, files):
        names = list(files or [])
        button = QToolButton()
        button.setObjectName('fileList')
        button.setText(
            f'{len(names)} file' if len(names) == 1 else f'{len(names)} files'
        )
        button.setFixedSize(116, 36)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(
            '<b>Imported files</b><br>'
            + ('<br>'.join(names) if names else 'No files recorded')
        )
        menu = QMenu(button)
        heading = menu.addAction('IMPORTED FILES')
        heading.setEnabled(False)
        menu.addSeparator()
        if names:
            for name in names:
                menu.addAction(f'  {name}')
        else:
            empty = menu.addAction('No files recorded')
            empty.setEnabled(False)
        button.setMenu(menu)
        button.setPopupMode(QToolButton.InstantPopup)
        return button

    def selected_ids(self):
        selected = []
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            checkbox = widget.findChild(QCheckBox) if widget else None
            if checkbox and checkbox.isChecked():
                selected.append(checkbox.property('fid'))
        return selected

    def delete_one(self, flight_id):
        if QMessageBox.question(
            self,
            'Delete flight',
            'Permanently delete this flight and all associated data?',
        ) == QMessageBox.Yes:
            self.flight_controller.delete(flight_id)
            self.load(self.aid)

    def delete_selected(self):
        flight_ids = self.selected_ids()
        if flight_ids and QMessageBox.question(
            self,
            'Delete flights',
            f'Delete {len(flight_ids)} selected flight(s)?',
        ) == QMessageBox.Yes:
            self.flight_controller.delete_many(flight_ids)
            self.load(self.aid)

    def open_current(self):
        row = self.table.currentRow()
        if row >= 0:
            self.flight_selected.emit(
                self.table.item(row, 1).data(Qt.UserRole)
            )
