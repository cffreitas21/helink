from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from math import isfinite
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from helink.services.flight_telemetry_series import flight_parameter_series
from helink.services.flight_route_service import flight_route_availability
from helink.ui.telemetry_parameters import (
    OVERVIEW_TELEMETRY_PARAMETERS, TELEMETRY_PARAMETERS,
)
from helink.ui.widgets import Card, ChartFilterButton, CombinedTelemetryPlot, Plot


class TelemetryTab(QWidget):
    route_requested = Signal(object)
    CHARTS = TELEMETRY_PARAMETERS
    INSTRUMENT_ROW_COUNTS = (1, 3, 5, 7, 9, 18)
    INSTRUMENTS = (
        ('n1', 'N1', '%'),
        ('n2', 'N2', '%'),
        ('nr', 'NR', '%'),
        ('itt', 'ITT', '\N{DEGREE SIGN}C'),
        ('eng_ot', 'ENG OIL\nTEMP', '\N{DEGREE SIGN}C'),
        ('eng_op', 'ENG OIL\nPRESS', 'psi'),
        ('xmsn_ot', 'XMSN OIL\nTEMP', '\N{DEGREE SIGN}C'),
        ('xmsn_op', 'XMSN OIL\nPRESS', 'psi'),
        ('fuel_press', 'FUEL PRESS', 'psi'),
        ('oat', 'OAT', '\N{DEGREE SIGN}C'),
        ('ias', 'IAS', 'kt'),
    )

    def __init__(self):
        super().__init__()
        self.data = []
        self.flight = None
        self.plots = {}
        self.chart_cards = {}
        self._combined_mode = False
        self._reset_combined_view = True
        self._series_cache = {}
        self._time_labels = []
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(0)
        self._render_timer.timeout.connect(self._render_visible_charts)

        root = QVBoxLayout(self)
        root.setSpacing(8)

        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.prev = QPushButton('\u25c0')
        self.prev.setFixedSize(38, 36)
        self.prev.setToolTip('Previous telemetry point')
        controls.addWidget(self.prev)

        self.time = QLabel('00:00:00')
        self.time.setAlignment(Qt.AlignCenter)
        self.time.setMinimumWidth(96)
        self.time.setStyleSheet(
            'font-family:Consolas,monospace;font-size:14px;'
            'font-weight:700;color:#0f172a;background:transparent'
        )
        controls.addWidget(self.time)

        self.next = QPushButton('\u25b6')
        self.next.setFixedSize(38, 36)
        self.next.setToolTip('Next telemetry point')
        controls.addWidget(self.next)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setObjectName('telemetryTimeline')
        self.slider.setMinimumHeight(24)
        self.slider.setTracking(True)
        self.slider.setToolTip('Flight timeline')

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        rows_label = QLabel('Rows')
        rows_label.setObjectName('muted')
        self.row_count_selector = QComboBox()
        self.row_count_selector.setObjectName('telemetryRows')
        self.row_count_selector.setFixedWidth(74)
        self.row_count_selector.setAccessibleName('Number of instantaneous value rows')
        self.row_count_selector.setToolTip(
            'Keep the selected timestamp highlighted with surrounding records'
        )
        for count in self.INSTRUMENT_ROW_COUNTS:
            self.row_count_selector.addItem(str(count), count)
        self.row_count_selector.setCurrentIndex(0)
        rows_label.setBuddy(self.row_count_selector)
        toolbar.addWidget(rows_label)
        toolbar.addWidget(self.row_count_selector)
        self.view_route_button = QPushButton('View on Map')
        self.view_route_button.setObjectName('secondary')
        self.view_route_button.setFixedHeight(36)
        self.view_route_button.setEnabled(False)
        self.view_route_button.setToolTip('Open the map at the selected telemetry time')
        self.view_route_button.clicked.connect(self._request_route)
        toolbar.addWidget(self.view_route_button)
        toolbar.addStretch()
        toolbar.addLayout(controls)
        toolbar.addStretch()
        self.combine_charts_button = QPushButton('Combine Charts')
        self.combine_charts_button.setObjectName('combineChartsButton')
        self.combine_charts_button.setCheckable(True)
        self.combine_charts_button.setFixedHeight(36)
        self.combine_charts_button.setAccessibleName('Toggle combined telemetry charts')
        self.combine_charts_button.setToolTip('Combine the selected charts into one view')
        toolbar.addWidget(self.combine_charts_button)
        self.chart_filter = ChartFilterButton(self.CHARTS)
        self.chart_filter.setFixedHeight(36)
        toolbar.addWidget(self.chart_filter)
        root.addLayout(toolbar)
        root.addWidget(self.slider)

        self.instrument = QTableWidget(0, len(self.INSTRUMENTS) + 1)
        self.instrument.setObjectName('telemetryWindow')
        self.instrument.setHorizontalHeaderLabels(
            ['TIMESTAMP'] + [
                self._instrument_header(label, unit)
                for _key, label, unit in self.INSTRUMENTS
            ]
        )
        self.instrument.verticalHeader().setVisible(False)
        self.instrument.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.instrument.setSelectionMode(QAbstractItemView.NoSelection)
        self.instrument.setFocusPolicy(Qt.NoFocus)
        self.instrument.setAlternatingRowColors(False)
        header = self.instrument.horizontalHeader()
        header.setFixedHeight(58)
        header.setDefaultAlignment(Qt.AlignCenter)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.instrument.setColumnWidth(0, 92)
        for column in range(1, len(self.INSTRUMENTS) + 1):
            header.setSectionResizeMode(column, QHeaderView.Stretch)
        self.instrument.verticalHeader().setDefaultSectionSize(32)
        root.addWidget(self.instrument)
        self.row_count_selector.currentIndexChanged.connect(self._set_instrument_rows)
        self._set_instrument_rows()

        scroll = QScrollArea()
        self.chart_scroll = scroll
        scroll.viewport().installEventFilter(self)
        scroll.verticalScrollBar().valueChanged.connect(self._schedule_render)
        scroll.setWidgetResizable(True)
        charts = QWidget()
        grid = QGridLayout(charts)
        self.chart_grid = grid
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setSpacing(12)
        grid.setAlignment(Qt.AlignTop)

        for index, (key, title, unit, color) in enumerate(self.CHARTS):
            card = self._create_chart((key, title, unit, color))
            grid.addWidget(card, index // 2, index % 2)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.combined_card = Card('Combined Telemetry', charts)
        self.combined_card.setFixedHeight(640)
        self.combined_plot = CombinedTelemetryPlot()
        self.combined_plot.setMinimumHeight(560)
        self.combined_plot.setToolTip(
            'Scroll to zoom, drag to move the view, and double-click to show the full flight. '
            'Click a point or a MAX legend entry to select its timestamp.'
        )
        combined_heading = QHBoxLayout()
        combined_title = self.combined_card.layout.takeAt(0).widget()
        combined_heading.addWidget(combined_title)
        combined_heading.addStretch()
        self.combined_card.layout.addLayout(combined_heading)
        self.combined_plot.point_selected.connect(self.slider.setValue)
        self.combined_card.layout.addWidget(self.combined_plot)
        self.combined_card.hide()
        self.chart_empty_state = QWidget(charts)
        self.chart_empty_state.setObjectName('telemetryEmptyState')
        self.chart_empty_state.setMinimumHeight(180)
        empty_layout = QVBoxLayout(self.chart_empty_state)
        empty_layout.addStretch()
        empty_title = QLabel('No charts selected')
        empty_title.setObjectName('telemetryEmptyTitle')
        empty_title.setAlignment(Qt.AlignCenter)
        empty_hint = QLabel('Use Charts to choose the parameters you want to display.')
        empty_hint.setObjectName('telemetryEmptyHint')
        empty_hint.setAlignment(Qt.AlignCenter)
        empty_hint.setWordWrap(True)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_hint)
        show_all = QPushButton('Show All Charts')
        show_all.clicked.connect(
            lambda: self.chart_filter.set_selected(self.chart_cards)
        )
        empty_layout.addWidget(show_all, 0, Qt.AlignCenter)
        empty_layout.addStretch()
        self.chart_filter.selection_changed.connect(self._update_visible_charts)
        self.combine_charts_button.toggled.connect(self._set_combined_mode)
        self._update_visible_charts(self.chart_filter.selected_keys())
        scroll.setWidget(charts)
        root.addWidget(scroll, 1)

        self.slider.valueChanged.connect(self.update_cursor)
        self.prev.clicked.connect(
            lambda: self.slider.setValue(max(0, self.slider.value() - 1))
        )
        self.next.clicked.connect(
            lambda: self.slider.setValue(
                min(self.slider.maximum(), self.slider.value() + 1)
            )
        )

    @staticmethod
    def _instrument_header(label, unit):
        first, separator, second = label.partition('\n')
        return f'{first}\n{second} ({unit})' if separator else f'{label}\n({unit})'

    def _request_route(self):
        if self.data:
            self.route_requested.emit(self.data[self.slider.value()])

    def _create_chart(self, parameter):
        key, title, unit, color = parameter
        card = Card(title, self.chart_grid.parentWidget())
        plot = Plot(2.35)
        plot.setMinimumHeight(220)
        plot.series_color = color
        plot.point_selected.connect(self.slider.setValue)
        card.layout.addWidget(plot)
        card.ensurePolished()
        card.setFixedHeight(card.minimumSizeHint().height())
        self.plots[key] = (plot, title, unit)
        self.chart_cards[key] = card
        return card

    def focus_parameter(self, key):
        """Open one Overview parameter in the large combined chart."""
        parameter = next((
            item for item in (*self.CHARTS, *OVERVIEW_TELEMETRY_PARAMETERS)
            if item[0] == key
        ), None)
        if parameter is None:
            return False
        if key not in self.plots:
            self.CHARTS += (parameter,)
            self._create_chart(parameter).hide()
            self.chart_filter.add_parameter(parameter)
            self._draw_chart(key)
        self.chart_filter.set_selected((key,))
        self.combine_charts_button.setChecked(True)
        self.chart_scroll.verticalScrollBar().setValue(0)
        self.update_cursor()
        return True

    def _set_instrument_rows(self, *_):
        count = self.row_count_selector.currentData()
        if count not in self.INSTRUMENT_ROW_COUNTS:
            return
        self.instrument.setRowCount(count)
        for row in range(count):
            self.instrument.setRowHeight(row, 32)
            for column in range(self.instrument.columnCount()):
                if self.instrument.item(row, column) is None:
                    item = QTableWidgetItem('\N{EM DASH}')
                    item.setTextAlignment(Qt.AlignCenter)
                    self.instrument.setItem(row, column, item)
        self.instrument.setFixedHeight(
            self.instrument.horizontalHeader().height()
            + count * 32 + self.instrument.frameWidth() * 2
        )
        self._update_instrument_window(self.slider.value())

    def _update_visible_charts(self, selected_keys):
        selected = set(selected_keys)
        for key, card in self.chart_cards.items():
            self.chart_grid.removeWidget(card)
            card.setVisible(key in selected and not self._combined_mode)
        self.chart_grid.removeWidget(self.combined_card)
        self.combined_card.setVisible(bool(selected) and self._combined_mode)
        self.chart_grid.removeWidget(self.chart_empty_state)
        self.chart_empty_state.setVisible(not selected)
        visible = [
            key for key, *_metadata in self.CHARTS if key in selected
        ]
        if visible and self._combined_mode:
            self.chart_grid.addWidget(self.combined_card, 0, 0, 1, 2)
            self.chart_grid.activate()
            self.combined_card.layout.activate()
            self._draw_combined_chart()
        else:
            for index, key in enumerate(visible):
                self.chart_grid.addWidget(
                    self.chart_cards[key], index // 2, index % 2,
                )
        if not visible:
            self.chart_grid.addWidget(self.chart_empty_state, 0, 0, 1, 2)
        self._schedule_render()

    def _schedule_render(self, *_):
        if not self._render_timer.isActive():
            self._render_timer.start()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Resize, QEvent.Show):
            self._schedule_render()
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_render()

    def _render_visible_charts(self):
        plots = (
            [self.combined_plot] if self._combined_mode
            else [plot for plot, _title, _unit in self.plots.values()]
        )
        for plot in plots:
            if (
                plot.isVisible() and not plot.visibleRegion().isEmpty()
                and plot._cursor_background is None
            ):
                plot.draw_idle()

    def _set_combined_mode(self, enabled):
        self._combined_mode = enabled
        self.combine_charts_button.setText(
            'Separate Charts' if enabled else 'Combine Charts'
        )
        self.combine_charts_button.setToolTip(
            'Show the selected charts separately' if enabled
            else 'Combine the selected charts into one view'
        )
        self._update_visible_charts(self.chart_filter.selected_keys())

    def _draw_combined_chart(self, *, reset_view=False):
        series = []
        for key in self.chart_filter.selected_keys():
            plot, title, unit = self.plots[key]
            values = self._parameter_values(key)
            series.append((title, values, plot.series_color, unit))
        self.combined_plot.parameters(
            series, self._time_labels, self.slider.value(), render=False,
            preserve_view=not (reset_view or self._reset_combined_view),
        )
        self._reset_combined_view = False

    def load(self, flight):
        self._reset_combined_view = True
        self.flight = flight
        self.data = flight.engine_data or flight.data_log
        route = flight_route_availability(flight)
        self.view_route_button.setEnabled(route.available and bool(self.data))
        self.view_route_button.setToolTip(
            'Open the map at the selected telemetry time'
            if route.available else route.reason
        )
        self._series_cache.clear()
        self._time_labels = [point.timestamp for point in self.data]
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, len(self.data) - 1))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self._draw_charts()
        self.update_cursor()
        # A navigation overlay can still cover the canvases during load.
        # Schedule their first visible frame after the page has been revealed.
        self._schedule_render()

    def _draw_charts(self):
        for key in self.plots:
            self._draw_chart(key)
        if self._combined_mode and self.chart_filter.selected_keys():
            self._draw_combined_chart(reset_view=True)

    def _draw_chart(self, key):
        plot, title, unit = self.plots[key]
        values = self._parameter_values(key)
        plot.lines(
            [(title, values, plot.series_color)],
            '', unit, cursor=self.slider.value(), show_max=True,
            flight_time=True, time_labels=self._time_labels, render=False,
        )

    def _parameter_values(self, key):
        if key not in self._series_cache:
            self._series_cache[key] = (
                flight_parameter_series(self.flight, key, self.data)
                if self.flight is not None else []
            )
        return self._series_cache[key]

    def _update_instrument_window(self, selected_index):
        selected_background = QColor('#dbeafe')
        selected_foreground = QColor('#0f3b72')
        normal_background = QColor('#ffffff')
        normal_foreground = QColor('#111827')

        # Keep the selected sample centered in the displayed recording window.
        selected_row = (self.instrument.rowCount() - 1) // 2
        for row in range(self.instrument.rowCount()):
            offset = row - selected_row
            data_index = selected_index + offset
            point = (
                self.data[data_index]
                if 0 <= data_index < len(self.data)
                else None
            )
            values = ['\N{EM DASH}']
            if point:
                values[0] = Plot._clock_time(point.timestamp)
                for key, _label, _unit in self.INSTRUMENTS:
                    number = (
                        self._parameter_values('ias')[data_index]
                        if key == 'ias' else getattr(point, key, None)
                    )
                    values.append(
                        f'{number:.1f}' if number is not None and isfinite(number)
                        else '\N{EM DASH}'
                    )
            else:
                values.extend('\N{EM DASH}' for _item in self.INSTRUMENTS)

            highlighted = row == selected_row
            for column, value in enumerate(values):
                item = self.instrument.item(row, column)
                item.setText(value)
                item.setBackground(
                    selected_background if highlighted else normal_background
                )
                item.setForeground(
                    selected_foreground if highlighted else normal_foreground
                )
                font = QFont(item.font())
                font.setBold(highlighted)
                item.setFont(font)

    def update_cursor(self):
        index = self.slider.value()
        point = self.data[index] if self.data else None
        self.time.setText(
            Plot._clock_time(point.timestamp if point else None)
        )

        self._update_instrument_window(index)

        for plot, _title, _unit in self.plots.values():
            plot.move_cursor(index)
        if self._combined_mode:
            self.combined_plot.move_cursor(index)
