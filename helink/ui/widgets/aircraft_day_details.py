from datetime import date
from math import ceil

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QSizePolicy


class AircraftDayDetails(QPlainTextEdit):
    """Copyable flight breakdown that expands within the page's scroll area."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('fleetAnalysisDay')
        self.setReadOnly(True)
        self.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAccessibleName('Selected day flight statistics')
        self.document().setDocumentMargin(0)
        self.document().documentLayout().documentSizeChanged.connect(self._fit_height)
        self.reset()

    def show_message(self, text):
        self.setPlainText(text)
        self._fit_height()
        self.setTextCursor(QTextCursor(self.document()))
        self.verticalScrollBar().setValue(0)

    def _fit_height(self, *_):
        # QPlainTextDocumentLayout reports visual lines, including wrapped
        # lines, rather than a pixel height.
        lines = max(1, self.document().documentLayout().documentSize().height())
        height = max(40, ceil(lines * self.fontMetrics().lineSpacing()) + 24)
        if self.height() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_height()

    def reset(self):
        self.show_message('Click a recorded day to inspect its values.')

    @staticmethod
    def _value(value, unit):
        return '\N{EM DASH}' if value is None else f'{value:.1f} {unit}'

    def show_day(self, registration, label, unit, day, flights):
        stamp = date.fromisoformat(day.flight_date).strftime('%d/%m/%Y')
        lines = [f'{registration} \N{MIDDLE DOT} {stamp} \N{MIDDLE DOT} {label}']
        for index, flight in enumerate(flights, start=1):
            departure = flight.departure_time or '\N{EM DASH}'
            arrival = flight.arrival_time or '\N{EM DASH}'
            line = (
                f'Flight {index} \N{MIDDLE DOT} '
                f'{departure} \N{RIGHTWARDS ARROW} {arrival} \N{MIDDLE DOT} '
                f'AVG {self._value(flight.average, unit)} \N{MIDDLE DOT} '
                f'MAX {self._value(flight.maximum, unit)}'
            )
            if flight.sample_count == 0:
                line += ' \N{MIDDLE DOT} No recorded values'
            lines.append(line)
        lines.append(
            f'TOTAL \N{MIDDLE DOT} AVG {self._value(day.average, unit)} '
            f'\N{MIDDLE DOT} MAX {self._value(day.maximum, unit)}'
        )
        self.show_message('\n'.join(lines))
