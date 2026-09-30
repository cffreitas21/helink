from colorsys import hls_to_rgb
from datetime import date

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLayout,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from helink.ui.telemetry_parameters import (
    OVERVIEW_TELEMETRY_PARAMETERS, TELEMETRY_PARAMETERS,
)
from helink.ui.widgets.aircraft_selection_button import AircraftSelectionButton
from helink.ui.widgets.aircraft_day_details import AircraftDayDetails
from helink.ui.widgets.aircraft_trend_plot import AircraftTrendPlot
from helink.ui.widgets.card import Card
from helink.ui.widgets.flight_date_filter_button import FlightDateFilterButton


PARAMETERS = TELEMETRY_PARAMETERS + OVERVIEW_TELEMETRY_PARAMETERS
AIRCRAFT_COLORS = (
    '#2563eb', '#c2410c', '#15803d', '#9333ea', '#be123c',
    '#0891b2', '#a16207', '#475569', '#4f46e5', '#0f766e',
)


def _aircraft_color(index):
    if index < len(AIRCRAFT_COLORS):
        return AIRCRAFT_COLORS[index]
    red, green, blue = hls_to_rgb((index * 0.61803398875) % 1, 0.38, 0.68)
    return f'#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}'


class FleetAnalysisPage(QWidget):
    """Single-aircraft trends and like-for-like fleet parameter comparisons."""

    back_requested = Signal()
    flights_requested = Signal(str)
    loading_changed = Signal(bool, str)

    def __init__(self, aircraft_controller):
        super().__init__()
        self.aircraft_controller = aircraft_controller
        self.aircraft = []
        self.days = []
        self.colors = {}
        self._loading = False
        self._allow_comparison = True
        self._fixed_aircraft_id = None
        self._row_by_aircraft = {}
        self._day_flight_cache = {}
        self._query_token = 0
        self._query_task = None
        self._day_token = 0
        self._day_task = None
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setObjectName('fleetAnalysisScroll')
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content = QWidget()
        root = QVBoxLayout(self.content)
        root.setSizeConstraint(QLayout.SetMinimumSize)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(12)
        heading = QHBoxLayout()
        self.back_button = QPushButton('\N{LEFTWARDS ARROW} Fleet')
        self.back_button.setObjectName('secondary')
        self.back_button.clicked.connect(self.back_requested)
        heading.addWidget(self.back_button)
        self.title = QLabel('Fleet Analysis')
        self.title.setObjectName('title')
        heading.addWidget(self.title)
        heading.addStretch()
        self.view_flights = QPushButton('View Flights')
        self.view_flights.clicked.connect(self._open_flights)
        heading.addWidget(self.view_flights)
        root.addLayout(heading)
        self.context = QLabel()
        self.context.setObjectName('muted')
        self.context.setTextFormat(Qt.PlainText)
        self.context.setWordWrap(True)
        root.addWidget(self.context)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.aircraft_selector = AircraftSelectionButton()
        self.aircraft_selector.selection_changed.connect(self._reload)
        toolbar.addWidget(self.aircraft_selector)
        toolbar.addWidget(QLabel('Parameter'))
        self.parameter = QComboBox()
        self.parameter.setObjectName('fleetAnalysisFilter')
        self.parameter.setAccessibleName('Select sensor for daily analysis')
        for key, label, unit, _ in PARAMETERS:
            self.parameter.addItem(f'{label} ({unit})', key)
        self.parameter.setCurrentIndex(self.parameter.findData('itt'))
        self.parameter.setMinimumWidth(220)
        self.parameter.currentIndexChanged.connect(self._reload)
        toolbar.addWidget(self.parameter, 1)
        self.statistic = QComboBox()
        self.statistic.setObjectName('fleetAnalysisFilter')
        self.statistic.setAccessibleName('Choose daily statistic')
        for label, key in (
            ('Daily AVG', 'average'), ('Daily MAX', 'maximum'), ('AVG and MAX', 'both'),
        ):
            self.statistic.addItem(label, key)
        self.statistic.setMinimumWidth(160)
        self.statistic.currentIndexChanged.connect(self._render)
        toolbar.addWidget(self.statistic)
        self.date_filter = FlightDateFilterButton()
        self.date_filter.range_changed.connect(self._reload)
        toolbar.addWidget(self.date_filter)
        minimum_label = QLabel('Min. duration')
        self.minimum_minutes = QSpinBox()
        self.minimum_minutes.setObjectName('fleetMinimumDuration')
        self.minimum_minutes.setAccessibleName('Minimum flight duration in minutes')
        self.minimum_minutes.setToolTip(
            'Exclude shorter flights from the chart and daily totals. '
            '0 min includes all flights. Flights without a calculable duration '
            'are excluded when a minimum is set.'
        )
        self.minimum_minutes.setRange(0, 1440)
        self.minimum_minutes.setSingleStep(1)
        self.minimum_minutes.setSuffix(' min')
        self.minimum_minutes.setFixedWidth(108)
        self.minimum_minutes.setKeyboardTracking(False)
        self.minimum_minutes.setAccelerated(True)
        self.minimum_minutes.valueChanged.connect(self._reload)
        minimum_label.setBuddy(self.minimum_minutes)
        toolbar.addWidget(minimum_label)
        toolbar.addWidget(self.minimum_minutes)
        root.addLayout(toolbar)

        chart = Card()
        chart_heading = QHBoxLayout()
        self.chart_title = QLabel('Daily Parameter Evolution')
        self.chart_title.setObjectName('fleetAnalysisTitle')
        chart_heading.addWidget(self.chart_title)
        chart_heading.addStretch()
        self.coverage = QLabel()
        self.coverage.setObjectName('muted')
        chart_heading.addWidget(self.coverage)
        chart.layout.addLayout(chart_heading)
        self.plot = AircraftTrendPlot()
        self.plot.day_selected.connect(self._show_day)
        chart.layout.addWidget(self.plot)
        self.day_details = AircraftDayDetails()
        chart.layout.addWidget(self.day_details)
        root.addWidget(chart)

        summary = Card()
        self.comparison_title = QLabel('Period Comparison')
        self.comparison_title.setStyleSheet('font-size:15px;font-weight:700')
        summary.layout.addWidget(self.comparison_title)
        self.comparison = QTableWidget(0, 5)
        self.comparison.setObjectName('fleetComparisonTable')
        self.comparison.verticalHeader().hide()
        self.comparison.verticalHeader().setDefaultSectionSize(40)
        self.comparison.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.comparison.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.comparison.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.comparison.setSelectionMode(QAbstractItemView.SingleSelection)
        self.comparison.setAlternatingRowColors(True)
        self.comparison.setShowGrid(False)
        self.comparison.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        summary.layout.addWidget(self.comparison)
        root.addWidget(summary)
        root.addStretch()
        self.scroll.setWidget(self.content)
        page_layout.addWidget(self.scroll)
        self._page_scroll_targets = (
            self.plot, self.day_details.viewport(), self.comparison.viewport(),
        )
        for widget in self._page_scroll_targets:
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        # Nested canvases and item views otherwise consume the wheel, even
        # when their own scrollbars are disabled.
        if event.type() == QEvent.Wheel and watched in self._page_scroll_targets:
            QApplication.sendEvent(self.scroll.viewport(), event)
            return True
        return super().eventFilter(watched, event)

    def load(self, aircraft_id=None, *, allow_comparison=True, prepared=None):
        if not allow_comparison and not aircraft_id:
            raise ValueError('An aircraft is required for individual analysis.')
        self._loading = True
        self._query_token += 1
        self._day_token += 1
        for task in (self._query_task, self._day_task):
            if task is not None:
                task.cancel()
        try:
            self._allow_comparison = allow_comparison
            self._fixed_aircraft_id = aircraft_id if not allow_comparison else None
            self.title.setText('Fleet Analysis' if allow_comparison else 'Aircraft Analysis')
            self.back_button.setText(
                '\N{LEFTWARDS ARROW} Fleet' if allow_comparison
                else '\N{LEFTWARDS ARROW} Flights'
            )
            self.comparison_title.setText(
                'Period Comparison' if allow_comparison else 'Period Summary'
            )
            self.aircraft_selector.hidePopup()
            self.aircraft_selector.setVisible(allow_comparison)
            self.aircraft_selector.setEnabled(allow_comparison)
            if prepared is not None:
                self.aircraft = prepared[0]
            elif allow_comparison:
                self.aircraft = self.aircraft_controller.list_for_analysis()
            else:
                aircraft = self.aircraft_controller.get(aircraft_id)
                self.aircraft = [aircraft] if aircraft is not None else []
            self.colors = {
                item.id: _aircraft_color(index)
                for index, item in enumerate(self.aircraft)
            }
            selected = [
                item.id for item in self.aircraft
                if not aircraft_id or item.id == aircraft_id
            ]
            self.date_filter.reset(emit=False)
            self.aircraft_selector.set_aircraft(self.aircraft, selected, self.colors)
        finally:
            self._loading = False
        self._reload(preloaded_days=prepared[1] if prepared is not None else None)
        self.scroll.verticalScrollBar().setValue(0)

    def _selected_aircraft_ids(self):
        # Individual analysis is pinned to its aircraft, independently of
        # the (hidden) comparison selector.
        if not self._allow_comparison:
            return tuple(
                item.id for item in self.aircraft
                if item.id == self._fixed_aircraft_id
            )
        return self.aircraft_selector.selected_ids()

    def cancel_pending(self):
        self._query_token += 1
        self._day_token += 1
        for task in (self._query_task, self._day_task):
            if task is not None:
                task.cancel()

    def _selected_aircraft(self):
        selected = set(self._selected_aircraft_ids())
        return [item for item in self.aircraft if item.id in selected]

    def _parameter_metadata(self):
        return next(
            item for item in PARAMETERS if item[0] == self.parameter.currentData()
        )

    def _reload(self, *_, preloaded_days=None):
        if self._loading:
            return
        self._day_flight_cache.clear()
        self._day_token += 1
        if self._day_task is not None:
            self._day_task.cancel()
        start, end = self.date_filter.date_range
        minimum = self.minimum_minutes.value()
        if preloaded_days is not None:
            self.days = preloaded_days
            self.date_filter.set_available_dates(day.flight_date for day in self.days)
            self._render()
            return
        if self.aircraft_controller.tasks is not None:
            self._query_token += 1
            token = self._query_token
            if self._query_task is not None:
                self._query_task.cancel()
            self.loading_changed.emit(True, 'Loading parameter trends...')

            def received(days):
                if token != self._query_token:
                    return
                self.days = days
                if start is None:
                    self.date_filter.set_available_dates(day.flight_date for day in days)
                self._render()
                self.loading_changed.emit(False, '')

            def failed(error):
                if token == self._query_token:
                    self.loading_changed.emit(False, '')
                    QMessageBox.warning(self, self.title.text(), str(error))

            self._query_task = self.aircraft_controller.request(
                'daily_parameter_trends', self._selected_aircraft_ids(),
                self.parameter.currentData(), start_date=start, end_date=end,
                minimum_minutes=minimum,
                on_result=received, on_error=failed,
            )
            return
        try:
            self.days = self.aircraft_controller.daily_parameter_trends(
                self._selected_aircraft_ids(),
                self.parameter.currentData(), start_date=start, end_date=end,
                minimum_minutes=minimum,
            )
        except Exception as error:
            self.days = []
            QMessageBox.warning(
                self, self.title.text(), f'The recorded values could not be loaded:\n{error}',
            )
        if start is None:
            self.date_filter.set_available_dates(day.flight_date for day in self.days)
        self._render()

    def _render(self, *_):
        if self._loading:
            return
        selected = self._selected_aircraft()
        _, label, unit, _color = self._parameter_metadata()
        statistic = self.statistic.currentData()
        self.chart_title.setText(f'{label} - Daily Evolution')
        day_count = len({day.flight_date for day in self.days})
        coverage = (
            f'{len(selected)} aircraft \N{MIDDLE DOT} '
            f'{day_count} recorded {"day" if day_count == 1 else "days"}'
        )
        if self.minimum_minutes.value():
            coverage += (
                f' \N{MIDDLE DOT} minimum {self.minimum_minutes.value()} min'
            )
        self.coverage.setText(coverage)
        self.view_flights.setVisible(self._allow_comparison and len(selected) == 1)
        if len(selected) == 1:
            item = selected[0]
            self.context.setText(
                f'Fleet Management / {item.registration} \N{MIDDLE DOT} '
                f'{item.model} \N{MIDDLE DOT} SN {item.serial_number}'
            )
        elif self._allow_comparison:
            self.context.setText(
                'Fleet Management / Compare aircraft using the same parameter, dates and units.'
            )
        else:
            self.context.setText('Fleet Management / Aircraft unavailable')
        self.plot.show_trends(
            self.days, selected, self.colors, label, unit, statistic,
            empty_message=(
                'No recorded values match this parameter, date range and '
                'minimum flight duration.'
                if self.minimum_minutes.value() else None
            ),
        )
        self.day_details.reset()
        summary_field = 'maximum' if statistic == 'maximum' else 'average'
        caption = 'MAX' if summary_field == 'maximum' else 'AVG'
        summaries = self.aircraft_controller.trend_summaries(self.days, summary_field)
        self.comparison.setHorizontalHeaderLabels((
            'AIRCRAFT', 'RECORDED DAYS', f'FIRST {caption}\n({unit})',
            f'LATEST {caption}\n({unit})', f'PEAK MAX\n({unit})',
        ))
        self._row_by_aircraft = {}
        self.comparison.setRowCount(len(selected))
        for row, item in enumerate(selected):
            self._row_by_aircraft[item.id] = row
            result = summaries.get(item.id)
            texts = (
                item.registration,
                str(result.day_count) if result else '0',
                f'{result.first_value:.1f}' if result else '\N{EM DASH}',
                f'{result.last_value:.1f}' if result else '\N{EM DASH}',
                f'{result.maximum:.1f}' if result else '\N{EM DASH}',
            )
            for column, text in enumerate(texts):
                cell = QTableWidgetItem(text)
                cell.setTextAlignment(Qt.AlignCenter)
                cell.setData(Qt.UserRole, item.id)
                if column == 0:
                    chip = QPixmap(10, 10)
                    chip.fill(QColor(self.colors[item.id]))
                    cell.setData(Qt.DecorationRole, chip)
                    cell.setToolTip(f'{item.model} - SN {item.serial_number}')
                elif not result:
                    cell.setToolTip('No valid values for this parameter in the selected period.')
                elif column in (2, 3):
                    stamp = result.first_date if column == 2 else result.last_date
                    cell.setToolTip(date.fromisoformat(stamp).strftime('%d/%m/%Y'))
                self.comparison.setItem(row, column, cell)
        self.comparison.setFixedHeight(
            self.comparison.horizontalHeader().sizeHint().height()
            + max(1, len(selected)) * 40 + 4
        )

    def _show_day(self, day):
        if day.aircraft_id not in self._selected_aircraft_ids():
            return
        parameter, label, unit, _color = self._parameter_metadata()
        minimum = self.minimum_minutes.value()
        cache_key = (day.aircraft_id, day.flight_date, parameter, minimum)
        if self.aircraft_controller.tasks is not None and cache_key not in self._day_flight_cache:
            self._day_token += 1
            token = self._day_token
            if self._day_task is not None:
                self._day_task.cancel()
            self.day_details.show_message('Loading flight statistics...')

            def received(flights):
                if token == self._day_token:
                    self._day_flight_cache[cache_key] = flights
                    self._show_day(day)

            def failed(error):
                if token == self._day_token:
                    self.day_details.show_message('The flight statistics could not be loaded.')
                    QMessageBox.warning(self, self.title.text(), str(error))

            self._day_task = self.aircraft_controller.request(
                'parameter_flights_for_day', day.aircraft_id, day.flight_date, parameter,
                minimum_minutes=minimum,
                on_result=received, on_error=failed,
            )
            return
        try:
            if cache_key not in self._day_flight_cache:
                self._day_flight_cache[cache_key] = (
                    self.aircraft_controller.parameter_flights_for_day(
                        day.aircraft_id, day.flight_date, parameter,
                        minimum_minutes=minimum,
                    )
                )
        except Exception as error:
            self.day_details.show_message('The flight values for this day could not be loaded.')
            QMessageBox.warning(
                self, self.title.text(), f'The flight values could not be loaded:\n{error}',
            )
            return
        aircraft = next(item for item in self.aircraft if item.id == day.aircraft_id)
        self.day_details.show_day(
            aircraft.registration, label, unit, day, self._day_flight_cache[cache_key],
        )
        row = self._row_by_aircraft.get(day.aircraft_id)
        if row is not None:
            self.comparison.selectRow(row)

    def _open_flights(self):
        selected = self._selected_aircraft_ids()
        if len(selected) == 1:
            self.flights_requested.emit(selected[0])
