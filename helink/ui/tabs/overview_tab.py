from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea,
    QToolButton, QVBoxLayout, QWidget,
)

from helink.services.airport_lookup import format_airport
from helink.services.flight_overview_summary import (
    flight_parameter_statistics, important_flight_events,
)
from helink.services.flight_route_service import flight_route_availability
from helink.ui.widgets import (
    Card, ImportedFilesList, OverviewEventButton, OverviewParameterButton,
)
from helink.ui.widgets.imported_files_button import EXPECTED_FILE_TYPES


PARAMETER_GROUPS = (
    ('Temperatures', (
        ('itt', 'ITT', '\u00b0C', 1),
        ('eng_ot', 'ENG OIL TEMP', '\u00b0C', 1),
        ('xmsn_ot', 'XMSN OIL TEMP', '\u00b0C', 1),
        ('oat', 'OAT', '\u00b0C', 1),
    )),
    ('Pressures', (
        ('eng_op', 'ENG OIL PRESS', 'psi', 1),
        ('xmsn_op', 'XMSN OIL PRESS', 'psi', 1),
        ('fuel_press', 'FUEL PRESS', 'psi', 1),
    )),
    ('Engine & Flight', (
        ('n1', 'N1', '%', 1),
        ('n2', 'N2', '%', 1),
        ('nr', 'NR', '%', 1),
        ('tq', 'TORQUE', '%', 1),
        ('ias', 'IAS', 'kt', 1),
        ('alt_ind', 'ALTITUDE', 'ft', 0),
    )),
)


class OverviewTab(QWidget):
    import_requested = Signal(str)
    event_requested = Signal(str)
    route_requested = Signal()
    parameter_requested = Signal(str)

    def __init__(self):
        super().__init__()
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content.setObjectName('overviewContent')
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 4, 0)
        self.content_layout.setSpacing(12)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        summary = Card('Flight Summary')
        summary.layout.setContentsMargins(14, 10, 14, 10)
        summary.layout.setSpacing(7)
        self.summary_values = {}
        timing = QGridLayout()
        timing.setHorizontalSpacing(16)
        timing.setVerticalSpacing(2)
        for column, (key, label) in enumerate((
            ('date', 'FLIGHT DATE'), ('departure', 'DEPARTURE'),
            ('arrival', 'ARRIVAL'), ('duration', 'DURATION'),
        )):
            caption = QLabel(label)
            caption.setObjectName('overviewCaption')
            value = QLabel('\u2014')
            value.setObjectName('overviewValue')
            value.setWordWrap(True)
            timing.addWidget(caption, 0, column)
            timing.addWidget(value, 1, column)
            timing.setColumnStretch(column, 1)
            self.summary_values[key] = value
        for column, (key, label, span) in enumerate((
            ('origin', 'ORIGIN', 1), ('destination', 'DESTINATION', 1),
        )):
            caption = QLabel(label)
            caption.setObjectName('overviewCaption')
            caption.setContentsMargins(0, 5, 0, 0)
            value = QLabel('\u2014')
            value.setObjectName('overviewRouteValue')
            value.setTextFormat(Qt.PlainText)
            value.setWordWrap(True)
            timing.addWidget(caption, 2, column, 1, span)
            timing.addWidget(value, 3, column, 1, span)
            self.summary_values[key] = value
        self.view_route_button = QToolButton()
        self.view_route_button.setObjectName('overviewViewRoute')
        self.view_route_button.setText('Route Unavailable')
        self.view_route_button.setCursor(Qt.PointingHandCursor)
        self.view_route_button.setEnabled(False)
        self.view_route_button.clicked.connect(lambda: self.route_requested.emit())
        timing.addWidget(
            self.view_route_button, 2, 2, 2, 1, Qt.AlignLeft | Qt.AlignVCenter,
        )
        event_column = QVBoxLayout()
        event_column.setContentsMargins(0, 4, 0, 0)
        event_column.setSpacing(4)
        event_column.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.event_badges = {}
        for key, title, object_name in (
            ('exceedances', 'Exceedances', 'overviewExceedances'),
            ('miscmp', 'MISCMP-P', 'overviewMiscmp'),
        ):
            badge = OverviewEventButton()
            badge.setObjectName(object_name)
            badge.setCursor(Qt.PointingHandCursor)
            badge.setFixedSize(132, 25)
            badge.hide()
            badge.clicked.connect(
                lambda _, event_key=key: self.event_requested.emit(event_key)
            )
            self.event_badges[key] = badge
            event_column.addWidget(badge, 0, Qt.AlignLeft)
        self.event_placeholder = QLabel('\u2014')
        self.event_placeholder.setObjectName('overviewEventEmpty')
        self.event_placeholder.setToolTip(
            'No recorded exceedance or MISCMP-P SET activations.'
        )
        event_column.addWidget(self.event_placeholder, 0, Qt.AlignLeft)
        timing.addLayout(event_column, 2, 3, 2, 1, Qt.AlignLeft | Qt.AlignTop)
        summary.layout.addLayout(timing)
        self.content_layout.addWidget(summary)

        dashboard = Card('Flight Parameter Dashboard')
        dashboard.layout.setContentsMargins(14, 12, 14, 12)
        dashboard.layout.setSpacing(8)
        self.metric_values = {}
        self.metric_tiles = {}
        self.metric_groups = []
        for group_title, specs in PARAMETER_GROUPS:
            heading = QLabel(group_title.upper())
            heading.setObjectName('overviewSectionTitle')
            dashboard.layout.addWidget(heading)
            grid = QGridLayout()
            grid.setSpacing(8)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            tiles = []
            for index, (key, label, unit, _) in enumerate(specs):
                tile = self._parameter_tile(key, label, unit)
                tiles.append(tile)
                grid.addWidget(tile, index // 2, index % 2)
            self.metric_groups.append({
                'grid': grid, 'tiles': tiles, 'columns': 2,
                'limit': 4 if group_title == 'Temperatures' else 3,
            })
            dashboard.layout.addLayout(grid)
        self.content_layout.addWidget(dashboard)

        self.content_layout.addStretch()
        content.installEventFilter(self)

        files_panel = Card('Imported Files')
        files_panel.setObjectName('filesPanel')
        files_panel.setFixedWidth(285)
        files_panel.layout.setContentsMargins(12, 12, 12, 12)
        self.file_count = QLabel()
        self.file_count.setObjectName('importedFilesCount')
        files_panel.layout.addWidget(self.file_count)
        self.files = ImportedFilesList(show_status=False)
        files_panel.layout.addWidget(self.files, 1)
        root.addWidget(files_panel)

    def _parameter_tile(self, key, label, unit):
        metric = OverviewParameterButton(key, label)
        metric.parameter_selected.connect(self.parameter_requested)
        layout = QVBoxLayout(metric)
        layout.setContentsMargins(11, 8, 11, 9)
        layout.setSpacing(6)
        heading = QHBoxLayout()
        heading.setSpacing(6)
        title = QLabel(label)
        title.setObjectName('overviewParameterTitle')
        title.setWordWrap(True)
        units = QLabel(f'({unit})')
        units.setObjectName('overviewUnit')
        heading.addWidget(title, 1)
        heading.addWidget(units)
        layout.addLayout(heading)
        values = QGridLayout()
        values.setHorizontalSpacing(16)
        values.setVerticalSpacing(1)
        for column, statistic in enumerate(('avg', 'max')):
            caption = QLabel(statistic.upper())
            caption.setObjectName('overviewMetricLabel')
            value = QLabel('\u2014')
            value.setObjectName('overviewMetricValue')
            value.setTextFormat(Qt.PlainText)
            values.addWidget(caption, 0, column)
            values.addWidget(value, 1, column)
            values.setColumnStretch(column, 1)
            self.metric_values[f'{key}_{statistic}'] = value
        layout.addLayout(values)
        for child in metric.findChildren(QLabel):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.metric_tiles[key] = metric
        return metric

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize:
            available = max(0, event.size().width() - 34)
            columns = 4 if available >= 740 else (
                3 if available >= 560 else (2 if available >= 340 else 1)
            )
            for group in self.metric_groups:
                count = min(columns, group['limit'])
                if group['limit'] == 4 and count == 3:
                    count = 2
                if count == group['columns']:
                    continue
                grid = group['grid']
                for tile in group['tiles']:
                    grid.removeWidget(tile)
                for column in range(group['limit']):
                    grid.setColumnStretch(column, 1 if column < count else 0)
                for index, tile in enumerate(group['tiles']):
                    grid.addWidget(tile, index // count, index % count)
                group['columns'] = count
        return super().eventFilter(watched, event)

    def load(self, flight, *, statistics=None, events=None, route=None):
        for key, text in (
            ('date', flight.flight_date), ('departure', flight.departure_time),
            ('arrival', flight.arrival_time), ('duration', flight.duration),
            ('origin', format_airport(flight.origin)),
            ('destination', format_airport(flight.destination)),
        ):
            self.summary_values[key].setText(text or '\u2014')

        if statistics is None:
            statistics = flight_parameter_statistics(flight)
        for _, specs in PARAMETER_GROUPS:
            for key, label, unit, decimals in specs:
                summary = statistics[key]
                tooltip = f'Open {label} in Telemetry.\n' + (
                    f'{summary.samples:,} valid recorded samples. '
                    'AVG is the arithmetic mean; MAX is the highest recorded value.'
                    if summary.samples else 'No recorded values for this parameter.'
                )
                self.metric_tiles[key].setToolTip(tooltip)
                for name, number in (
                    ('avg', summary.average), ('max', summary.maximum),
                ):
                    value = self.metric_values[f'{key}_{name}']
                    value.setText(
                        '\u2014' if number is None else f'{number:,.{decimals}f}'
                    )
                    value.setAccessibleName(f'{label} {name.upper()} ({unit})')
                    value.setToolTip(tooltip)

        event_count = 0
        for key, summary in (
            important_flight_events(flight) if events is None else events
        ).items():
            badge = self.event_badges[key]
            title = 'Exceedances' if key == 'exceedances' else 'MISCMP-P'
            badge.setText(f'{title} {summary.count}')
            badge.setVisible(summary.count > 0)
            badge.setEnabled(summary.available)
            event_count += summary.count
            badge.setAccessibleName(
                f'{title}: {summary.count} SET '
                f'{"activation" if summary.count == 1 else "activations"}. Open history.'
            )
            details = '\n'.join(
                f'{name} ({count})' if count > 1 else name
                for name, count in summary.activated_names
            )
            badge.setToolTip(
                f'Open {title} event history. '
                f'{summary.count} SET '
                f'{"activation" if summary.count == 1 else "activations"}.'
                + (f'\n{details}' if details else '')
            )
        self.event_placeholder.setVisible(event_count == 0)

        if route is None:
            route = flight_route_availability(flight)
        self.view_route_button.setText(
            'View Route' if route.available else 'Route Unavailable'
        )
        self.view_route_button.setEnabled(route.available)
        self.view_route_button.setToolTip(
            'Open the recorded flight on map'
            if route.available else route.reason
        )

        imported = set(flight.imported_files)
        self.file_count.setText(
            f'{len(imported)} / {len(EXPECTED_FILE_TYPES)}'
        )
        self.file_count.setToolTip(
            f'{len(imported)} of {len(EXPECTED_FILE_TYPES)} file types imported'
        )
        self.files.set_files(imported)
