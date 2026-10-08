from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, QTimer, Qt, Signal
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

from helink.services.airport_lookup import format_airport
from helink.ui.widgets import (
    FlightDateFilter, FlightSelectionButton, ImportedFilesButton, SelectAllHeader,
)


class FlightListPage(QWidget):
    flight_selected = Signal(str)
    import_requested = Signal(str)
    back_requested = Signal()
    analysis_requested = Signal(str)
    loading_changed = Signal(bool, str)

    def __init__(self, aircraft_controller, flight_controller):
        super().__init__()
        self.aircraft_controller = aircraft_controller
        self.flight_controller = flight_controller
        self.aid = None
        self.row_checkboxes = []
        self._selection_syncing = False
        self._total_count = 0
        self._query_token = 0
        self._query_task = None
        self._render_token = 0
        self._render_pending = False
        self._rendered_rows = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(12)

        heading = QHBoxLayout()
        left_actions = QHBoxLayout()
        back = QPushButton('← Fleet')
        back.setObjectName('secondary')
        back.clicked.connect(self.back_requested)
        left_actions.addWidget(back)

        self.title = QLabel()
        self.title.setObjectName('title')
        left_actions.addWidget(self.title)
        left_actions.addStretch()
        heading.addLayout(left_actions, 1)

        self.analysis_button = QPushButton('Aircraft Analysis')
        self.analysis_button.setObjectName('analysisNavigation')
        self.analysis_button.setToolTip('View parameter evolution for this aircraft')
        self.analysis_button.setEnabled(False)
        self.analysis_button.clicked.connect(
            lambda: self.analysis_requested.emit(self.aid)
        )
        heading.addWidget(self.analysis_button, 0, Qt.AlignCenter)

        right_actions = QHBoxLayout()
        right_actions.addStretch()
        import_button = QPushButton('Import Files')
        import_button.clicked.connect(
            lambda: self.import_requested.emit(self.aid)
        )
        right_actions.addWidget(import_button)
        heading.addLayout(right_actions, 1)
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
        self.date_filter = FlightDateFilter()
        self.date_filter.range_changed.connect(self._reload_rows)
        toolbar.addWidget(self.date_filter)
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
        self.filter_message = QLabel()
        self.filter_message.setObjectName('muted')
        self.filter_message.setAlignment(Qt.AlignCenter)
        self.filter_message.hide()
        root.addWidget(self.filter_message)

        self.table = QTableWidget(0, 10)
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
            'ROUTE', 'EVENTS', 'PREVENTIVE\nMAINTENANCE',
            'IMPORTED FILES', 'ACTIONS',
        ])

        header = self.table.horizontalHeader()
        for column in range(10):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
        header.setFixedHeight(49)
        self.table.setColumnWidth(0, 44)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 92)
        self.table.setColumnWidth(3, 92)
        self.table.setColumnWidth(4, 145)
        self.table.setColumnWidth(5, 125)
        self.table.setColumnWidth(6, 130)
        self.table.setColumnWidth(7, 160)
        self.table.setColumnWidth(8, 125)
        self.table.setColumnWidth(9, 110)
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

    def load(self, aircraft_id, prepared=None):
        self._query_token += 1
        if self._query_task is not None:
            self._query_task.cancel()
        changing_aircraft = aircraft_id != self.aid
        if changing_aircraft:
            self.date_filter.reset(emit=False)
        self.aid = aircraft_id
        aircraft = (
            self.aircraft_controller.get(aircraft_id)
            if prepared is None else prepared[0]
        )
        self.analysis_button.setEnabled(aircraft is not None)
        if aircraft is None:
            self.title.setText('Aircraft unavailable')
            self.info.clear()
            self._total_count = 0
            self._render_rows([])
            return
        self._total_count = aircraft.flight_count
        self.title.setText(aircraft.registration)
        self.info.setText(
            f'{aircraft.model} · SN {aircraft.serial_number} '
        )

        if prepared is None:
            rows = self._reload_rows(initialize_dates=changing_aircraft)
        else:
            rows = prepared[1]
            self._render_rows(rows)
        if changing_aircraft and (
            prepared is not None or self.flight_controller.tasks is None
        ):
            self.date_filter.set_available_dates(flight.flight_date for flight in rows)

    def cancel_pending(self):
        self._query_token += 1
        if self._query_task is not None:
            self._query_task.cancel()
        self._render_token += 1
        if self._render_pending:
            self._rendered_rows = None
        self._render_pending = False

    def _reload_rows(self, *_, initialize_dates=False):
        if self.aid is None:
            return []
        start, end = self.date_filter.date_range
        if self.flight_controller.tasks is not None:
            self._query_token += 1
            token = self._query_token
            if self._query_task is not None:
                self._query_task.cancel()
            self.loading_changed.emit(True, 'Loading flights...')

            def received(rows):
                if token != self._query_token:
                    return
                if initialize_dates:
                    self.date_filter.set_available_dates(flight.flight_date for flight in rows)
                self._render_rows(rows)
                if not self._render_pending:
                    self.loading_changed.emit(False, '')

            def failed(error):
                if token == self._query_token:
                    self.loading_changed.emit(False, '')
                    QMessageBox.warning(self, 'Unable to load flights', str(error))

            self._query_task = self.flight_controller.request(
                'list_flights', self.aid, start_date=start, end_date=end,
                descending=self.sort_order.currentData() == 'descending',
                on_result=received, on_error=failed,
            )
            return []
        rows = self.flight_controller.list_flights(
            self.aid, start_date=start, end_date=end,
            descending=self.sort_order.currentData() == 'descending',
        )
        self._render_rows(rows)
        return rows

    def _render_rows(self, rows):
        if rows is self._rendered_rows and not self._render_pending:
            return
        self._render_token += 1
        self._render_pending = False
        count = len(rows)
        filtered = self.date_filter.date_range != (None, None)
        if filtered:
            self.flight_count.setText(f'{count} of {self._total_count} flights')
        else:
            self.flight_count.setText(
                f'{count} imported flight' if count == 1
                else f'{count} imported flights'
            )
        self.filter_message.setText(
            'No flights match the selected dates.' if filtered
            else 'No flights have been imported for this aircraft.'
        )
        self.filter_message.setVisible(count == 0)
        if self.flight_controller.tasks is not None and count > 40:
            self._render_rows_in_batches(rows)
            return
        self.table.setUpdatesEnabled(False)
        try:
            self._populate_rows(rows)
        finally:
            self.table.setUpdatesEnabled(True)
        self._rendered_rows = rows

    def _render_rows_in_batches(self, rows):
        token = self._render_token
        self._render_pending = True
        self.row_checkboxes.clear()
        self.table.clearContents()
        self.table.setRowCount(0)
        self.selection_header.set_check_enabled(False)
        self._sync_selection_ui()

        def batch(start=0):
            if token != self._render_token:
                return
            end = min(len(rows), start + 24)
            self.table.setUpdatesEnabled(False)
            try:
                self.table.setRowCount(end)
                self._populate_rows(
                    rows[start:end], start=start, reset=False, finish=False,
                )
            finally:
                self.table.setUpdatesEnabled(True)
            if start == 0:
                # The first visible rows are ready; finish the rest without
                # covering the usable list with a full-page loading overlay.
                self.loading_changed.emit(False, '')
            if end < len(rows):
                QTimer.singleShot(0, lambda: batch(end))
            else:
                self._render_pending = False
                self._rendered_rows = rows
                self.selection_header.set_check_enabled(bool(rows))
                self._sync_selection_ui()

        QTimer.singleShot(0, batch)

    def _populate_rows(self, rows, *, start=0, reset=True, finish=True):
        if reset:
            self.row_checkboxes.clear()
            self.table.clearContents()
            self.table.setRowCount(len(rows))

        for row, flight in enumerate(rows, start):
            # Items underneath cell widgets keep the selection background continuous.
            for column in (0, 6, 7, 8, 9):
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

            event_cell = QWidget()
            event_cell.setObjectName('flightEventCell')
            event_layout = QVBoxLayout(event_cell)
            event_layout.setContentsMargins(4, 4, 4, 4)
            event_layout.setSpacing(2)
            event_layout.setAlignment(Qt.AlignCenter)
            for count, label, object_name in (
                (flight.exceedance_count, 'Exceedances', 'flightExceedanceBadge'),
                (flight.miscmp_count, 'MISCMP-P', 'flightMiscmpBadge'),
            ):
                if not count:
                    continue
                badge = QLabel(f'{label} {count}')
                badge.setObjectName(object_name)
                badge.setAlignment(Qt.AlignCenter)
                badge.setMinimumWidth(112)
                badge.setFixedHeight(24)
                badge.setToolTip(
                    f'{count} recorded {label} SET '
                    f'{"activation" if count == 1 else "activations"}.'
                )
                event_layout.addWidget(badge)
            if event_layout.count() == 0:
                none = QLabel('\N{EM DASH}')
                none.setObjectName('muted')
                none.setAlignment(Qt.AlignCenter)
                none.setToolTip('No recorded exceedance or MISCMP-P SET activations.')
                event_layout.addWidget(none)
            self.table.setCellWidget(row, 6, event_cell)

            preventive_cell = QWidget()
            preventive_cell.setObjectName('flightPreventiveCell')
            preventive_layout = QHBoxLayout(preventive_cell)
            preventive_layout.setContentsMargins(5, 5, 5, 5)
            preventive_layout.setAlignment(Qt.AlignCenter)
            status_text, badge_name, explanation = {
                'critical': (
                    'Limit finding', 'flightPmCritical',
                    'A preventive-maintenance upper limit or permitted '
                    'transient duration was exceeded.',
                ),
                'review': (
                    'Transient review', 'flightPmReview',
                    'A continuous upper limit was exceeded; review the '
                    'recorded transient in Preventive Maintenance.',
                ),
                'normal': (
                    'No finding', 'flightPmNormal',
                    'No upper-limit departures were identified in the '
                    'recorded engine samples.',
                ),
                'unavailable': (
                    'No PM data', 'flightPmUnavailable',
                    'No supported engine-limit measurements are available '
                    'for preventive-maintenance assessment.',
                ),
                'not_applicable': (
                    'Not applicable', 'flightPmUnavailable',
                    'AW119MKII limits are not applied to this aircraft model.',
                ),
            }.get(
                flight.preventive_status,
                ('Unavailable', 'flightPmUnavailable',
                 'Preventive-maintenance assessment is unavailable.'),
            )
            preventive_badge = QLabel(status_text)
            preventive_badge.setObjectName(badge_name)
            preventive_badge.setAlignment(Qt.AlignCenter)
            preventive_badge.setToolTip(explanation)
            preventive_badge.setMinimumWidth(132)
            preventive_badge.setFixedHeight(27)
            preventive_layout.addWidget(preventive_badge)
            self.table.setCellWidget(row, 7, preventive_cell)

            files_cell = QWidget()
            files_cell.setObjectName('flightCell')
            files_layout = QHBoxLayout(files_cell)
            files_layout.setContentsMargins(4, 6, 4, 6)
            files_layout.addWidget(
                self._files_button(flight.imported_files),
                0,
                Qt.AlignCenter,
            )
            self.table.setCellWidget(row, 8, files_cell)

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

            action_layout.addStretch()
            action_layout.addWidget(open_button)
            action_layout.addStretch()
            self.table.setCellWidget(row, 9, actions)

        if finish:
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
            self._reload_rows()

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

        for column in (0, 6, 7, 8, 9):
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
