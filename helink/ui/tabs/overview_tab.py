from statistics import mean

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QScrollArea, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget,
)

from helink.ui.widgets import Card


class OverviewTab(QWidget):
    import_requested = Signal(str)
    event_requested = Signal(str)

    FILE_TYPES = [
        '1_Engine_Data_Recording', 'data_log', '2_Exceedance_Log',
        '3_Exceedance_Log_CONT', '4_VNE_Dynamic', '0_CAS_Default',
        '5_CAS', '6_Logbook', 'Garmin Alerts',
    ]

    def __init__(self):
        super().__init__()
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 4, 0)
        self.content_layout.setSpacing(12)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        summary = Card('Flight Summary')
        summary_grid = QGridLayout()
        summary_grid.setHorizontalSpacing(28)
        summary_grid.setVerticalSpacing(10)
        self.summary_values = {}
        summary_fields = (
            ('date', 'Flight Date'),
            ('departure', 'Departure'),
            ('duration', 'Duration'),
            ('origin', 'Origin'),
        )
        for index, (key, label) in enumerate(summary_fields):
            box = QVBoxLayout()
            caption = QLabel(label.upper())
            caption.setObjectName('overviewCaption')
            value = QLabel('\u2014')
            value.setObjectName('overviewValue')
            self.summary_values[key] = value
            box.addWidget(caption)
            box.addWidget(value)
            summary_grid.addLayout(box, 0, index)
        summary.layout.addLayout(summary_grid)
        self.content_layout.addWidget(summary)

        metrics_card = Card('Key Flight Parameters')
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(10)
        self.metric_values = {}
        parameter_specs = (
            ('itt', 'ITT', '\u00b0C', 1),
            ('torque', 'Torque', '%', 1),
            ('ias', 'IAS', 'kt', 1),
            ('eng_temp', 'ENG Oil Temperature', '\u00b0C', 1),
            ('xmsn_temp', 'XMSN Oil Temperature', '\u00b0C', 1),
            ('altitude', 'Altitude', 'ft', 0),
        )
        for index, (key, label, unit, decimals) in enumerate(parameter_specs):
            metric = QFrame()
            metric.setObjectName('overviewParameter')
            layout = QVBoxLayout(metric)
            layout.setContentsMargins(13, 10, 13, 11)
            layout.setSpacing(7)
            title = QLabel(label.upper())
            title.setObjectName('overviewParameterTitle')
            layout.addWidget(title)

            values_row = QHBoxLayout()
            values_row.setSpacing(12)
            for statistic, caption_text in (
                ('avg', 'AVG'),
                ('max', 'MAXIMUM'),
            ):
                value_box = QVBoxLayout()
                value_box.setSpacing(2)
                value = QLabel('\u2014')
                value.setObjectName('overviewMetricValue')
                caption = QLabel(caption_text)
                caption.setObjectName('overviewMetricLabel')
                value_box.addWidget(value)
                value_box.addWidget(caption)
                values_row.addLayout(value_box, 1)
                self.metric_values[f'{key}_{statistic}'] = value
            layout.addLayout(values_row)
            metrics_grid.addWidget(metric, index // 3, index % 3)
        metrics_card.layout.addLayout(metrics_grid)
        self.content_layout.addWidget(metrics_card)

        lower = QHBoxLayout()
        lower.setSpacing(12)
        coverage = Card('Data Coverage')
        self.coverage = QLabel()
        self.coverage.setObjectName('overviewBody')
        self.coverage.setWordWrap(True)
        coverage.layout.addWidget(self.coverage)
        lower.addWidget(coverage, 1)

        alert_card = Card('Flight Events')
        event_grid = QGridLayout()
        event_grid.setSpacing(8)
        event_grid.setColumnStretch(0, 1)
        event_grid.setColumnStretch(1, 1)
        self.event_values = {}
        self.event_badges = {}
        event_specs = (
            ('total', 'TOTAL', 'eventTotal'),
            ('exceedances', 'EXCEEDANCES', 'eventExceedance'),
            ('warnings', 'WARNINGS', 'eventWarning'),
            ('cautions', 'CAUTIONS', 'eventCaution'),
            ('miscmp', 'MISCMP-P EVENTS', 'eventMiscmp'),
        )
        for index, (key, label, object_name) in enumerate(event_specs):
            badge = QToolButton()
            badge.setObjectName(object_name)
            badge.setText('')
            badge.setCursor(Qt.PointingHandCursor)
            badge.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            badge.setMinimumHeight(66)
            badge.setToolTip(f'Open {label.title()} details')
            badge.clicked.connect(
                lambda _, event_key=key: self.event_requested.emit(event_key)
            )
            badge_layout = QVBoxLayout(badge)
            badge_layout.setContentsMargins(9, 7, 9, 7)
            badge_layout.setSpacing(1)
            value = QLabel('0')
            value.setObjectName('eventValue')
            caption = QLabel(label)
            caption.setObjectName('eventLabel')
            badge_layout.addWidget(value)
            badge_layout.addWidget(caption)
            value.setAlignment(Qt.AlignCenter)
            caption.setAlignment(Qt.AlignCenter)
            self.event_values[key] = value
            self.event_badges[key] = badge
            if key == 'miscmp':
                event_grid.addWidget(badge, 2, 0, 1, 2)
            else:
                event_grid.addWidget(badge, index // 2, index % 2)
        self.event_badges['miscmp'].setVisible(False)
        alert_card.layout.addLayout(event_grid)
        lower.addWidget(alert_card, 1)
        self.content_layout.addLayout(lower)

        route = Card('Route Summary')
        self.route_summary = QLabel()
        self.route_summary.setObjectName('overviewBody')
        self.route_summary.setWordWrap(True)
        route.layout.addWidget(self.route_summary)
        self.content_layout.addWidget(route)
        self.content_layout.addStretch()

        files_panel = Card('Imported Files')
        files_panel.setObjectName('filesPanel')
        files_panel.setFixedWidth(310)
        self.file_count = QLabel()
        self.file_count.setObjectName('muted')
        files_panel.layout.addWidget(self.file_count)
        self.files = QListWidget()
        self.files.setObjectName('overviewFiles')
        files_panel.layout.addWidget(self.files, 1)
        root.addWidget(files_panel)

    @staticmethod
    def _values(items, attribute):
        return [
            float(value)
            for item in items
            if (value := getattr(item, attribute)) is not None
        ]

    @staticmethod
    def _display(values, unit, average=False, decimals=1):
        if not values:
            return '\u2014'
        value = mean(values) if average else max(values)
        return f'{value:.{decimals}f} {unit}'

    def load(self, flight):
        engine = flight.engine_data
        gps = flight.data_log
        alerts = flight.alerts

        self.summary_values['date'].setText(flight.flight_date or '\u2014')
        self.summary_values['departure'].setText(
            flight.departure_time or '\u2014'
        )
        self.summary_values['duration'].setText(flight.duration or '\u2014')
        self.summary_values['origin'].setText(flight.origin or '\u2014')

        itt = self._values(engine, 'itt')
        torque = self._values(engine, 'tq')
        eng_temp = self._values(engine, 'eng_ot')
        xmsn_temp = self._values(engine, 'xmsn_ot')
        altitude = self._values(gps, 'alt_ind')
        ias = self._values(gps, 'ias')
        metric_text = {}
        for key, values, unit, decimals in (
            ('itt', itt, '\u00b0C', 1),
            ('torque', torque, '%', 1),
            ('ias', ias, 'kt', 1),
            ('eng_temp', eng_temp, '\u00b0C', 1),
            ('xmsn_temp', xmsn_temp, '\u00b0C', 1),
            ('altitude', altitude, 'ft', 0),
        ):
            metric_text[f'{key}_avg'] = self._display(
                values, unit, average=True, decimals=decimals
            )
            metric_text[f'{key}_max'] = self._display(
                values, unit, decimals=decimals
            )
        if not ias:
            metric_text['ias_avg'] = 'NO DATA'
            metric_text['ias_max'] = 'NO DATA'
        for key, value in metric_text.items():
            self.metric_values[key].setText(value)

        first_time = (
            engine[0].timestamp if engine else
            (gps[0].timestamp if gps else None)
        )
        last_time = (
            engine[-1].timestamp if engine else
            (gps[-1].timestamp if gps else None)
        )
        self.coverage.setText(
            f'<b>{len(engine):,}</b> engine samples<br>'
            f'<b>{len(gps):,}</b> GPS points<br>'
            f'Recording window: <b>{first_time or "\u2014"}</b> to '
            f'<b>{last_time or "\u2014"}</b>'
        )

        exceedances = sum(alert.kind == 'EXCEEDANCE' for alert in alerts)
        warnings = sum(alert.level == 'WARNING' for alert in alerts)
        cautions = sum(alert.level == 'CAUTION' for alert in alerts)
        miscmp = sum(
            (alert.alert_name or '').upper() == 'MISCMP-P'
            and alert.level == 'CAUTION'
            and (alert.alert_state or '').upper() == 'SET'
            for alert in alerts
        )
        event_counts = {
            'total': len(alerts),
            'exceedances': exceedances,
            'warnings': warnings,
            'cautions': cautions,
            'miscmp': miscmp,
        }
        for key, count in event_counts.items():
            self.event_values[key].setText(str(count))
        self.event_badges['miscmp'].setVisible(miscmp > 0)

        valid_gps = [
            point for point in gps
            if point.latitude is not None and point.longitude is not None
            and 35 <= point.latitude <= 45 and -11 <= point.longitude <= 5
        ]
        if valid_gps:
            start, end = valid_gps[0], valid_gps[-1]
            self.route_summary.setText(
                f'<b>{len(valid_gps):,}</b> valid route points  \u00b7  '
                f'Start: <b>{start.latitude:.5f}, {start.longitude:.5f}</b>  '
                f'\u00b7  End: <b>{end.latitude:.5f}, {end.longitude:.5f}</b>'
            )
        else:
            self.route_summary.setText('No valid GPS route is available.')

        imported = set(flight.imported_files)
        count = len(imported)
        self.file_count.setText(
            f'{count} of {len(self.FILE_TYPES)} file types imported'
        )
        self.files.clear()
        for name in self.FILE_TYPES:
            loaded = name in imported
            item = QListWidgetItem(
                f'\u2713  {name}' if loaded else f'\u2014  {name}'
            )
            item.setData(Qt.UserRole, loaded)
            item.setForeground(QColor('#15803d' if loaded else '#64748b'))
            item.setToolTip(
                'Imported for this flight' if loaded
                else 'Not imported for this flight'
            )
            self.files.addItem(item)
