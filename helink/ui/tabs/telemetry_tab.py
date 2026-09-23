from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
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

from helink.ui.telemetry_parameters import TELEMETRY_PARAMETERS
from helink.ui.widgets import Card, Plot


class TelemetryTab(QWidget):
    CHARTS = TELEMETRY_PARAMETERS
    INSTRUMENTS = (
        ('n1', 'N1', '%'),
        ('n2', 'N2', '%'),
        ('nr', 'NR', '%'),
        ('itt', 'ITT', '\N{DEGREE SIGN}C'),
        ('eng_ot', 'ENG OIL TEMP', '\N{DEGREE SIGN}C'),
        ('eng_op', 'ENG OIL PRESS', 'psi'),
        ('xmsn_ot', 'XMSN OIL TEMP', '\N{DEGREE SIGN}C'),
        ('xmsn_op', 'XMSN OIL PRESS', 'psi'),
        ('fuel_press', 'FUEL PRESS', 'psi'),
        ('oat', 'OAT', '\N{DEGREE SIGN}C'),
    )

    def __init__(self):
        super().__init__()
        self.data = []
        self.plots = {}

        root = QVBoxLayout(self)
        root.setSpacing(8)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        controls.addStretch()

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
        controls.addStretch()
        root.addLayout(controls)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setTracking(True)
        self.slider.setToolTip('Flight timeline')
        root.addWidget(self.slider)

        self.instrument = QTableWidget(5, len(self.INSTRUMENTS) + 1)
        self.instrument.setObjectName('telemetryWindow')
        self.instrument.setHorizontalHeaderLabels(
            ['TIMESTAMP'] + [
                f'{label}\n({unit})'
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
        self.instrument.setFixedHeight(58 + (5 * 32) + 2)
        for row in range(5):
            for column in range(len(self.INSTRUMENTS) + 1):
                item = QTableWidgetItem('\N{EM DASH}')
                item.setTextAlignment(Qt.AlignCenter)
                self.instrument.setItem(row, column, item)
        root.addWidget(self.instrument)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        charts = QWidget()
        grid = QGridLayout(charts)
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setSpacing(12)

        for index, (key, title, unit, color) in enumerate(self.CHARTS):
            card = Card(title)
            plot = Plot(2.35)
            plot.setMinimumHeight(220)
            plot.series_color = color
            plot.point_selected.connect(self.slider.setValue)
            card.layout.addWidget(plot)
            self.plots[key] = (plot, title, unit)
            grid.addWidget(card, index // 2, index % 2)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
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

    def load(self, flight):
        self.data = flight.engine_data
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, len(self.data) - 1))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self._draw_charts()
        self.update_cursor()

    def _draw_charts(self):
        time_labels = [point.timestamp for point in self.data]
        for key, (plot, title, unit) in self.plots.items():
            values = [getattr(point, key) or 0 for point in self.data]
            plot.lines(
                [(title, values, plot.series_color)],
                '',
                unit,
                cursor=self.slider.value(),
                show_max=True,
                flight_time=True,
                time_labels=time_labels,
            )

    def _update_instrument_window(self, selected_index):
        selected_background = QColor('#dbeafe')
        selected_foreground = QColor('#0f3b72')
        normal_background = QColor('#ffffff')
        normal_foreground = QColor('#111827')

        for row, offset in enumerate(range(-2, 3)):
            data_index = selected_index + offset
            point = (
                self.data[data_index]
                if 0 <= data_index < len(self.data)
                else None
            )
            values = ['\N{EM DASH}']
            if point:
                values[0] = Plot._clock_time(point.timestamp)
                values.extend(
                    f'{(getattr(point, key) or 0):.1f}'
                    for key, _label, _unit in self.INSTRUMENTS
                )
            else:
                values.extend('\N{EM DASH}' for _item in self.INSTRUMENTS)

            highlighted = row == 2
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
