from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from helink.services.airport_formatter import format_airport
from helink.ui.widgets import (
    FlightSelectionButton, ImportedFilesButton, SelectAllHeader,
)


class FlightListPage(QWidget):
    flight_selected = Signal(str)
    import_requested = Signal(str)
    back_requested = Signal()

    def __init__(self, aircraft_controller, flight_controller):
        super().__init__()
        self.aircraft_controller = aircraft_controller
        self.flight_controller = flight_controller
        self.aid = None
        self.row_checkboxes = []
        self._selection_syncing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(12)

        heading = QHBoxLayout()
        back = QPushButton('← Fleet')
        back.setObjectName('secondary')
        back.clicked.connect(self.back_requested)
        heading.addWidget(back)

        self.title = QLabel()
        self.title.setObjectName('title')
        heading.addWidget(self.title)
        heading.addStretch()

        import_button = QPushButton('Import Files')
        import_button.clicked.connect(
            lambda: self.import_requested.emit(self.aid)
        )
        heading.addWidget(import_button)
        root.addLayout(heading)

        self.info = QLabel()
        self.info.setObjectName('muted')
        root.addWidget(self.info)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.flight_count = QLabel()
        self.flight_count.setObjectName('listSummary')
        toolbar.addWidget(self.flight_count)

        self.sort_order = QComboBox()
        self.sort_order.setObjectName('flightSort')
        self.sort_order.addItem('Oldest first', 'ascending')
        self.sort_order.addItem('Most recent first', 'descending')
        self.sort_order.setCurrentIndex(1)
        self.sort_order.setMinimumWidth(160)
        self.sort_order.setToolTip('Change the flight list order')
        self.sort_order.currentIndexChanged.connect(
            self._sort_order_changed
        )
        toolbar.addWidget(self.sort_order)
        toolbar.addStretch()

        self.selection_count = QLabel()
        self.selection_count.setObjectName('selectionCount')
        self.selection_count.setMinimumWidth(105)
        self.selection_count.hide()
        toolbar.addWidget(self.selection_count)

        self.delete_btn = QPushButton('Delete Selected')
        self.delete_btn.setObjectName('danger')
        self.delete_btn.setEnabled(False)
        self.delete_btn.hide()
        self.delete_btn.clicked.connect(self.delete_selected)
        toolbar.addWidget(self.delete_btn)
        root.addLayout(toolbar)

        self.table = QTableWidget(0, 8)
        self.table.setObjectName('flightTable')

        self.selection_header = SelectAllHeader(
            Qt.Horizontal, self.table
        )
        self.selection_header.toggle_all_requested.connect(
            self._toggle_all
        )
        self.table.setHorizontalHeader(self.selection_header)
        self.table.setHorizontalHeaderLabels([
            '', 'FLIGHT DATE', 'DEPARTURE', 'ARRIVAL', 'DURATION',
            'ROUTE', 'IMPORTED FILES', 'ACTIONS',
        ])

        header = self.table.horizontalHeader()
        for column in range(7):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
        header.setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 54)
        self.table.setColumnWidth(1, 145)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 160)
        self.table.setColumnWidth(6, 145)
        header.setMinimumSectionSize(42)
        header.setDefaultAlignment(Qt.AlignCenter)

        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(64)
        self.table.doubleClicked.connect(self.open_current)
        root.addWidget(self.table)

    def load(self, aircraft_id):
        self.aid = aircraft_id
        aircraft = next(
            item for item in self.aircraft_controller.list_aircraft()
            if item.id == aircraft_id
        )
        self.title.setText(aircraft.registration)
        self.info.setText(
            f'{aircraft.model} · SN {aircraft.serial_number} '
        )

        descending = self.sort_order.currentData() == 'descending'
        rows = sorted(
            self.flight_controller.list_flights(aircraft_id),
            key=lambda flight: (
                str(flight.flight_date), str(flight.departure_time)
            ),
            reverse=descending,
        )
        count = len(rows)
        self.flight_count.setText(
            f'{count} imported flight' if count == 1
            else f'{count} imported flights'
        )

        self.row_checkboxes.clear()
        self.table.clearContents()
        self.table.setRowCount(count)

        for row, flight in enumerate(rows):
            # Items underneath cell widgets keep the selection background continuous.
            for column in (0, 6, 7):
                self.table.setItem(row, column, QTableWidgetItem())
            checkbox = FlightSelectionButton()
            checkbox.setProperty('fid', flight.id)
            checkbox.setProperty('row', row)
            checkbox.setToolTip('Select this flight')
            checkbox.setAccessibleName('Select flight')

            checkbox_box = QWidget()
            checkbox_box.setObjectName('selectionCell')
            checkbox_layout = QHBoxLayout(checkbox_box)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.addWidget(checkbox)
            self.table.setCellWidget(row, 0, checkbox_box)
            self.row_checkboxes.append(checkbox)
            checkbox.toggled.connect(
                lambda checked, current_row=row, button=checkbox:
                self._set_row_selected(current_row, button, checked)
            )

            values = (
                flight.flight_date,
                flight.departure_time,
                flight.arrival_time or '—',
                flight.duration,
                self._route_label(flight),
            )
            for column, value in enumerate(values, 1):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                if column == 5:
                    item.setToolTip(
                        f'Origin: {format_airport(flight.origin)}\n'
                        f'Destination: {format_airport(flight.destination)}'
                    )
                if column == 1:
                    item.setData(Qt.UserRole, flight.id)
                self.table.setItem(row, column, item)

            files_cell = QWidget()
            files_cell.setObjectName('flightCell')
            files_layout = QHBoxLayout(files_cell)
            files_layout.setContentsMargins(6, 6, 6, 6)
            files_layout.addWidget(
                self._files_button(flight.imported_files),
                0,
                Qt.AlignCenter,
            )
            self.table.setCellWidget(row, 6, files_cell)

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

            action_layout.addStretch()
            action_layout.addWidget(open_button)
            action_layout.addWidget(delete_button)
            action_layout.addStretch()
            self.table.setCellWidget(row, 7, actions)

        self.selection_header.set_check_enabled(bool(rows))
        self._sync_selection_ui()

    @staticmethod
    def _route_label(flight):
        def code(value):
            normalized = str(value or '').strip().upper()
            return normalized if normalized and normalized != '-' else '\N{EM DASH}'

        return f'{code(flight.origin)}  \N{RIGHTWARDS ARROW}  {code(flight.destination)}'

    @staticmethod
    def _files_button(files):
        return ImportedFilesButton(files)

    def _sort_order_changed(self):
        if self.aid is not None:
            self.load(self.aid)

    def _toggle_all(self, checked):
        self._selection_syncing = True
        try:
            for row, checkbox in enumerate(self.row_checkboxes):
                checkbox.setChecked(checked)
                self._set_checkbox_appearance(checkbox, checked)
                self._set_row_visual(row, checked)
        finally:
            self._selection_syncing = False
        self._sync_selection_ui()

    def _set_row_selected(self, row, checkbox, selected):
        self._set_checkbox_appearance(checkbox, selected)
        self._set_row_visual(row, selected)
        if not self._selection_syncing:
            self._sync_selection_ui()

    @staticmethod
    def _set_checkbox_appearance(checkbox, selected):
        checkbox.setAccessibleName(
            'Deselect flight' if selected else 'Select flight'
        )

    def _set_row_visual(self, row, selected):
        action = (
            QItemSelectionModel.Select if selected
            else QItemSelectionModel.Deselect
        )
        self.table.selectionModel().select(
            self.table.model().index(row, 0),
            action | QItemSelectionModel.Rows,
        )

        for column in (0, 6, 7):
            widget = self.table.cellWidget(row, column)
            if widget is None:
                continue
            widget.setProperty('rowSelected', selected)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def _sync_selection_ui(self):
        selected_count = sum(
            checkbox.isChecked() for checkbox in self.row_checkboxes
        )
        total = len(self.row_checkboxes)

        if total and selected_count == total:
            state = Qt.Checked
        elif selected_count:
            state = Qt.PartiallyChecked
        else:
            state = Qt.Unchecked
        self.selection_header.set_check_state(state)

        if selected_count:
            suffix = 'flight' if selected_count == 1 else 'flights'
            self.selection_count.setText(
                f'{selected_count} {suffix} selected'
            )
            self.selection_count.setProperty('active', True)
            self.delete_btn.setText(f'Delete Selected ({selected_count})')
        else:
            self.selection_count.clear()
            self.selection_count.setProperty('active', False)
            self.delete_btn.setText('Delete Selected')

        self.selection_count.style().unpolish(self.selection_count)
        self.selection_count.style().polish(self.selection_count)
        self.selection_count.setVisible(selected_count > 0)
        self.delete_btn.setEnabled(selected_count > 0)
        self.delete_btn.setVisible(selected_count > 0)

    def selected_ids(self):
        return [
            checkbox.property('fid')
            for checkbox in self.row_checkboxes
            if checkbox.isChecked()
        ]

    def delete_one(self, flight_id):
        answer = QMessageBox.warning(
            self,
            'Delete flight',
            """Permanently delete this flight and all associated data?

This action cannot be undone.""",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer == QMessageBox.Yes:
            self.flight_controller.delete(flight_id)
            self.load(self.aid)

    def delete_selected(self):
        flight_ids = self.selected_ids()
        if not flight_ids:
            return

        count = len(flight_ids)
        noun = 'flight' if count == 1 else 'flights'
        message = (
            f'Permanently delete {count} selected {noun} and all '
            f"""associated data?

This action cannot be undone."""
        )
        answer = QMessageBox.warning(
            self,
            'Delete selected flights',
            message,
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer == QMessageBox.Yes:
            self.flight_controller.delete_many(flight_ids)
            self.load(self.aid)

    def open_current(self):
        row = self.table.currentRow()
        if row >= 0:
            self.flight_selected.emit(
                self.table.item(row, 1).data(Qt.UserRole)
            )
