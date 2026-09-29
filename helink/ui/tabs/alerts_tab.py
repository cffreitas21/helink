import re

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHeaderView, QHBoxLayout, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from helink.ui.widgets import StateBadge, TriggerButton


class AlertsTab(QWidget):
    jump_requested = Signal(str)

    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.all = []
        self.tasks = None
        self._render_token = 0
        self._render_pending = False
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render_next_batch)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(80)
        self._search_timer.timeout.connect(self.apply)
        root = QVBoxLayout(self)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Filter by name, description or trigger')
        self.alert_filter = QComboBox()
        self.alert_filter.addItem('All Alerts')
        self.alert_filter.setMinimumWidth(190)
        self.level = QComboBox()
        self.level.addItems([
            'All', 'WARNING', 'CAUTION', 'SAFE ANN',
        ])
        filters.addWidget(self.search, 1)
        filters.addWidget(self.alert_filter)
        filters.addWidget(self.level)
        root.addLayout(filters)
        self.summary = QLabel()
        self.summary.setObjectName('muted')
        root.addWidget(self.summary)

        self.show_description = kind != 'CAS'
        headers = ['TIME', 'STATE', 'LEVEL', 'ALERT']
        if self.show_description:
            headers.append('DESCRIPTION')
        headers.append('TRIGGERS')
        self.trigger_column = len(headers) - 1
        self.table = QTableWidget(0, len(headers))
        self.table.setObjectName('alertsTable')
        self.table.setHorizontalHeaderLabels(headers)
        header = self.table.horizontalHeader()
        header.setFixedHeight(44)
        header.setMinimumSectionSize(72)
        header.setStretchLastSection(False)
        for column in range(len(headers)):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setMinimumSectionSize(56)
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        root.addWidget(self.table, 1)
        self.search.textChanged.connect(self._search_changed)
        self.alert_filter.currentTextChanged.connect(self.apply)
        self.level.currentTextChanged.connect(self.apply)

    def _search_changed(self, *_):
        if self.tasks is None:
            self.apply()
        else:
            self._search_timer.start()

    def cancel_pending(self):
        self._search_timer.stop()
        self._render_timer.stop()
        self._render_token += 1
        was_pending = self._render_pending
        self._render_pending = False
        return was_pending

    def _schedule_row_resize(self, *_):
        QTimer.singleShot(0, self._fit_table_to_contents)

    def _fit_table_to_contents(self):
        self.table.resizeColumnsToContents()
        header = self.table.horizontalHeader()
        for column in range(self.table.columnCount()):
            required_width = max(
                header.sectionSizeHint(column),
                self.table.columnWidth(column),
            )
            for row in range(self.table.rowCount()):
                item = self.table.item(row, column)
                if item is not None:
                    font = item.font()
                    if font.pointSizeF() <= 0:
                        font = self.table.font()
                    text_width = QFontMetrics(font).horizontalAdvance(
                        item.text()
                    )
                    required_width = max(required_width, text_width + 28)
                widget = self.table.cellWidget(row, column)
                if widget is not None:
                    widget_padding = (
                        40 if column == self.trigger_column else 18
                    )
                    required_width = max(
                        required_width,
                        widget.sizeHint().width() + widget_padding,
                    )
            self.table.setColumnWidth(column, required_width)

        self.table.resizeRowsToContents()
        for row in range(self.table.rowCount()):
            required_height = 56
            for column in range(self.table.columnCount()):
                widget = self.table.cellWidget(row, column)
                if widget is not None:
                    required_height = max(
                        required_height, widget.sizeHint().height() + 12
                    )
            self.table.setRowHeight(row, required_height)

    def set_filters(self, level='All', alert_name='All Alerts'):
        # Overview navigation must not retain a previous search or level filter.
        controls = (self.search, self.level, self.alert_filter)
        previous = [control.blockSignals(True) for control in controls]
        try:
            self.search.clear()
            self.level.setCurrentText(
                level if self.level.findText(level) >= 0 else 'All'
            )
            index = next((
                index for index in range(self.alert_filter.count())
                if self.alert_filter.itemText(index).strip().casefold()
                == alert_name.strip().casefold()
            ), -1)
            if index < 0:
                # Keep the requested scope even if it currently has zero events.
                self.alert_filter.addItem(alert_name)
                index = self.alert_filter.count() - 1
            self.alert_filter.setCurrentIndex(index)
        finally:
            for control, blocked in zip(controls, previous):
                control.blockSignals(blocked)
        self.apply()

    @staticmethod
    def _valid_triggers(alert):
        return TriggerButton.valid_triggers(alert)

    @classmethod
    def _trigger_text(cls, alert):
        return ' '.join(
            f'{trigger.name} {trigger.value} {trigger.units} {trigger.state}'
            for trigger in cls._valid_triggers(alert)
        )

    @staticmethod
    def _display_time(timestamp):
        value = str(timestamp or '')
        match = re.search(
            r'(\d{1,2}:\d{2}:\d{2})(?!.*\d{1,2}:\d{2}:\d{2})', value
        )
        return match.group(1) if match else value

    def load(self, flight):
        self.all = [
            alert for alert in flight.alerts if alert.kind == self.kind
        ]
        self.alert_filter.blockSignals(True)
        self.alert_filter.clear()
        self.alert_filter.addItem('All Alerts')
        for name in sorted({
            alert.alert_name for alert in self.all if alert.alert_name
        }):
            self.alert_filter.addItem(name)
        self.alert_filter.blockSignals(False)
        self.apply()

    def apply(self):
        self.cancel_pending()
        query = self.search.text().lower()
        selected_alert = self.alert_filter.currentText()
        level = self.level.currentText()
        rows = [
            alert for alert in self.all
            if (
                selected_alert == 'All Alerts'
                or alert.alert_name == selected_alert
            )
            and (level == 'All' or alert.level == level)
            and (
                not query
                or query in (
                    f'{alert.alert_name or ""} {alert.description or ""} '
                    f'{self._trigger_text(alert)}'
                ).lower()
            )
        ]
        trigger_count = sum(len(self._valid_triggers(alert)) for alert in rows)
        type_count = len({alert.alert_name for alert in rows})
        self.summary.setText(
            f'{len(rows)} EVENTS   \u00b7   {type_count} ALERT '
            f'{"TYPE" if type_count == 1 else "TYPES"}   \u00b7   '
            f'{trigger_count} VALID TRIGGERS'
        )
        self.table.clearContents()
        self.table.setRowCount(len(rows))
        if self.tasks is not None and len(rows) > 80:
            self._render_rows = rows
            self._render_offset = 0
            self._render_pending = True
            self._render_next_batch()
        else:
            self._populate_rows(rows)
            self._finish_render()

    def _render_next_batch(self):
        if not self._render_pending:
            return
        end = min(len(self._render_rows), self._render_offset + 24)
        self._populate_rows(
            self._render_rows[self._render_offset:end], start=self._render_offset,
        )
        self._render_offset = end
        if end < len(self._render_rows):
            self._render_timer.start(0)
        else:
            self._render_pending = False
            self._finish_render()

    def _populate_rows(self, rows, *, start=0):
        for row, alert in enumerate(rows):
            row += start
            values = [
                (0, self._display_time(alert.timestamp)),
                (2, alert.level),
                (3, alert.alert_name),
            ]
            if self.show_description:
                values.append((4, alert.description))
            for column, value in values:
                item = QTableWidgetItem(str(value or ''))
                item.setTextAlignment(
                    Qt.AlignCenter if column in (0, 2)
                    else Qt.AlignLeft | Qt.AlignVCenter
                )
                self.table.setItem(row, column, item)
            self.table.setCellWidget(
                row, 1, self._state_badge(alert.alert_state)
            )
            self.table.setCellWidget(
                row, self.trigger_column, self._triggers_button(alert)
            )
    def _finish_render(self):
        self._fit_table_to_contents()
        self.table.scrollToTop()

    @staticmethod
    def _state_badge(state):
        return StateBadge(state)

    def _triggers_button(self, alert):
        return TriggerButton(alert)
