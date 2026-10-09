"""Flight-local review of recorded AW119MKII engine-limit departures."""

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from helink.services.preventive_maintenance_service import (
    LIMITS, assess_preventive_maintenance,
)
from helink.ui.widgets import Card


def _value(value):
    """Format a recorded numeric value or a missing-data marker."""
    return '\N{EM DASH}' if value is None else f'{value:g}'


def _time_label(timestamp):
    """Display the local flight clock time from an event timestamp."""
    matches = re.findall(
        r'(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?', str(timestamp or ''),
    )
    if not matches:
        return str(timestamp or '\N{EM DASH}')
    hour, minute, second = matches[-1]
    return f'{int(hour):02d}:{minute}:{second or "00"}'


class PreventiveMaintenanceTab(QWidget):
    """Present AW119 upper-limit assessments and their telemetry links."""
    point_requested = Signal(int)

    def __init__(self):
        """Build AW119 limit cards and the filterable observation table."""
        super().__init__()
        self.assessment = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)

        profile = Card()
        title = QLabel('Engine and Rotor Limitations')
        title.setObjectName('preventiveTitle')
        profile.layout.addWidget(title)
        self.intro = QLabel(
            'Maximum and Transient '
            'Limits \N{MIDDLE DOT} According to the AW119MKII Rotorcraft Flight Manual'
        )
        self.intro.setObjectName('muted')
        self.intro.setWordWrap(True)
    
        profile.layout.addWidget(self.intro)
        self.scope = QLabel()
        self.scope.setObjectName('preventiveScope')
        self.scope.setTextFormat(Qt.PlainText)
        self.scope.setWordWrap(True)
        self.scope.hide()
        profile.layout.addWidget(self.scope)
        layout.addWidget(profile)

        parameter_grid = QGridLayout()
        parameter_grid.setSpacing(10)
        self.cards = {}
        for index, spec in enumerate(LIMITS):
            card = Card(spec.label)
            card.setMinimumWidth(245)
            continuous = (
                f'Maximum: {spec.continuous_max:g} {spec.unit}'
                if spec.transient_max is None else
                f'Continuous maximum: {spec.continuous_max:g} {spec.unit}'
            )
            normal = QLabel(continuous)
            normal.setObjectName('preventiveDetail')
            card.layout.addWidget(normal)
            transient = QLabel(
                'Related CAS: ENG OIL HOT'
                if spec.key == 'eng_ot' else
                f'Transient: up to {spec.transient_max:g} {spec.unit}'
                f' / {spec.transient_seconds} s'
            )
            transient.setObjectName('preventiveDetail')
            card.layout.addWidget(transient)
            observed = QLabel('Recorded maximum: \N{EM DASH}')
            observed.setObjectName('preventiveObserved')
            card.layout.addWidget(observed)
            status = QLabel('NO DATA')
            status.setObjectName('preventiveUnavailable')
            card.layout.addWidget(status)
            parameter_grid.addWidget(card, index // 3, index % 3)
            self.cards[spec.key] = (observed, status)
        for column in range(3):
            parameter_grid.setColumnStretch(column, 1)
        layout.addLayout(parameter_grid)

        findings = Card('Recorded limit observations')
        filters = QHBoxLayout()
        filters.addStretch()
        self.parameter_filter = QComboBox()
        self.parameter_filter.setObjectName('fleetAnalysisFilter')
        self.parameter_filter.setAccessibleName('Filter maintenance observations by parameter')
        self.parameter_filter.addItem('All parameters', None)
        for spec in LIMITS:
            self.parameter_filter.addItem(spec.label, spec.key)
        filters.addWidget(self.parameter_filter)
        findings.layout.addLayout(filters)
        self.empty = QLabel()
        self.empty.setObjectName('muted')
        self.empty.setWordWrap(True)
        findings.layout.addWidget(self.empty)
        self.table = QTableWidget(0, 7)
        self.table.setObjectName('preventiveTable')
        self.table.setHorizontalHeaderLabels((
            'TIME', 'PARAMETER', 'FINDING', 'OBSERVED', 'LIMIT', 'DURATION',
            'ACTION',
        ))
        self.table.horizontalHeaderItem(5).setToolTip(
            'Estimated from consecutive timestamps, treating each value as '
            'lasting until the next sample. Without a closing sample, the '
            'first-to-last over-limit span is shown.'
        )
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setMinimumSectionSize(64)
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents,
        )
        self.table.horizontalHeader().setFixedHeight(44)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        for column in range(6):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
                if column != 4 else QHeaderView.Stretch
            )
        self.table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.Fixed,
        )
        self.table.setColumnWidth(6, 158)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setFixedHeight(310)
        findings.layout.addWidget(self.table)
        layout.addWidget(findings)
        layout.addStretch()
        self.scroll.setWidget(content)
        root.addWidget(self.scroll)
        self.parameter_filter.currentIndexChanged.connect(self._render_events)

    @staticmethod
    def _set_status(label, text, state):
        """Update a parameter badge and reapply its severity style."""
        label.setText(text)
        label.setObjectName('preventive' + state)
        label.style().unpolish(label)
        label.style().polish(label)

    def load(self, flight, aircraft=None):
        """Assess the flight and render parameter and occurrence summaries."""
        model = getattr(aircraft, 'model', '') if aircraft else ''
        self.assessment = assess_preventive_maintenance(flight, model)
        result = self.assessment
        self.scope.setText(result.message)
        self.scope.setObjectName(
            'preventiveScope' if result.applicable else 'preventiveScopeWarning'
        )
        self.scope.style().unpolish(self.scope)
        self.scope.style().polish(self.scope)
        self.scope.setVisible(not result.applicable or not result.assessed_samples)
        for parameter in result.parameters:
            observed, status = self.cards[parameter.spec.key]
            observed.setText(
                f'Recorded maximum: {_value(parameter.observed_max)} '
                f'{parameter.spec.unit}'
                if parameter.samples else 'Recorded maximum: \N{EM DASH}'
            )
            state = parameter.severity
            caption = {
                'normal': (
                    'WITHIN MAXIMUM'
                    if parameter.spec.transient_max is None else
                    'WITHIN CONTINUOUS MAXIMUM'
                ),
                'advisory': f'REVIEW - {parameter.findings} finding(s)',
                'critical': f'LIMIT FINDING - {parameter.findings}',
                'unavailable': (
                    'NOT APPLICABLE' if not result.applicable else 'NO DATA'
                ),
            }[state]
            self._set_status(status, caption, state.capitalize())
        self.parameter_filter.setCurrentIndex(0)
        self._render_events()
        self.scroll.verticalScrollBar().setValue(0)

    def _render_events(self, *_):
        """Render filtered limit observations with telemetry jump actions."""
        if self.assessment is None:
            return
        key = self.parameter_filter.currentData()
        visible_events = tuple(
            event for event in self.assessment.events
            if key is None or event.parameter == key
        )
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(visible_events))
        for row, event in enumerate(visible_events):
            spec = next(spec for spec in LIMITS if spec.key == event.parameter)
            values = (
                _time_label(event.timestamp),
                spec.label,
                event.finding,
                f'{event.observed:g} {spec.unit}',
                event.limit.replace('; ', '\n', 1),
                (
                    (
                        f'{event.duration_seconds} s+'
                        if event.duration_is_open else
                        f'{event.duration_seconds} s'
                    )
                    if event.duration_seconds is not None else '\N{EM DASH}'
                ),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(
                    Qt.AlignVCenter | (
                        Qt.AlignCenter if column in (0, 3, 5) else Qt.AlignLeft
                    )
                )
                if column == 2:
                    critical = event.severity == 'critical'
                    item.setForeground(QColor('#991b1b' if critical else '#92400e'))
                    item.setBackground(QColor('#fee2e2' if critical else '#fef3c7'))
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row, column, item)
            action_cell = QWidget()
            action_cell.setObjectName('tableActions')
            action_layout = QHBoxLayout(action_cell)
            action_layout.setContentsMargins(6, 4, 6, 4)
            button = QPushButton('See Telemetry')
            button.setObjectName('tableAction')
            button.setFixedHeight(40)
            button.setAccessibleName(
                f'See {spec.label} at {_time_label(event.timestamp)} '
                'in Telemetry'
            )
            button.clicked.connect(
                lambda _checked=False, index=event.start_index:
                self.point_requested.emit(index)
            )
            action_layout.addWidget(button)
            self.table.setCellWidget(row, 6, action_cell)
        self.table.setUpdatesEnabled(True)
        has_rows = bool(visible_events)
        self.table.setVisible(has_rows)
        if not has_rows:
            self.empty.setText(
                'No observations match this filter.'
                if self.assessment.events else
                'No engine samples are available for assessment.'
                if not self.assessment.assessed_samples else
                'No supported upper-limit parameters were recorded.'
                if not any(
                    parameter.samples for parameter in self.assessment.parameters
                ) else
                'No upper-limit departures were found in the '
                'assessed samples. Parameters without data remain unassessed.'
            )
        self.empty.setVisible(not has_rows)

