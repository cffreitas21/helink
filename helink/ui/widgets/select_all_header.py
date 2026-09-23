from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QAbstractButton, QHeaderView


def _draw_selection_box(
    painter: QPainter,
    rect: QRect,
    state,
    enabled=True,
    hovered=False,
):
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)

    border = QColor('#2563eb') if hovered else QColor('#64748b')
    background = QColor('#ffffff')
    if not enabled:
        border = QColor('#aebed2')
        background = QColor('#e2e8f0')
    elif state in (Qt.Checked, Qt.PartiallyChecked):
        border = QColor('#1d4ed8')
        background = QColor('#2563eb')

    painter.setPen(QPen(border, 2))
    painter.setBrush(background)
    painter.drawRoundedRect(rect, 4, 4)

    if state == Qt.Checked:
        painter.setPen(QPen(QColor('#ffffff'), 2.2))
        painter.drawLine(
            rect.left() + 5,
            rect.center().y(),
            rect.left() + 8,
            rect.bottom() - 5,
        )
        painter.drawLine(
            rect.left() + 8,
            rect.bottom() - 5,
            rect.right() - 4,
            rect.top() + 5,
        )
    elif state == Qt.PartiallyChecked:
        painter.setPen(QPen(QColor('#ffffff'), 2.4))
        painter.drawLine(
            rect.left() + 5,
            rect.center().y(),
            rect.right() - 5,
            rect.center().y(),
        )

    painter.restore()


class FlightSelectionButton(QAbstractButton):
    """Compact, consistently rendered checkbox for a flight row."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('flightSelector')
        self.setCheckable(True)
        self.setFixedSize(25, 25)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName('Select flight')

    def sizeHint(self):
        return QSize(25, 25)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        state = Qt.Checked if self.isChecked() else Qt.Unchecked
        _draw_selection_box(
            painter,
            self.rect().adjusted(2, 2, -2, -2),
            state,
            self.isEnabled(),
            self.underMouse(),
        )


class SelectAllHeader(QHeaderView):
    """Header with a three-state checkbox in its first section."""

    toggle_all_requested = Signal(bool)

    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self._check_state = Qt.Unchecked
        self._check_enabled = False
        self.setSectionsClickable(True)
        self.setToolTip('Select or clear every flight')

    def set_check_state(self, state):
        if self._check_state == state:
            return
        self._check_state = state
        self.updateSection(0)

    def set_check_enabled(self, enabled):
        if self._check_enabled == enabled:
            return
        self._check_enabled = enabled
        self.updateSection(0)

    def paintSection(self, painter: QPainter, rect: QRect, logical_index: int):
        super().paintSection(painter, rect, logical_index)
        if logical_index != 0:
            return

        painter.save()
        painter.fillRect(rect.adjusted(1, 1, -1, -1), QColor('#dbeafe'))
        painter.restore()

        size = 21
        checkbox_rect = QRect(
            rect.center().x() - size // 2,
            rect.center().y() - size // 2,
            size,
            size,
        )
        _draw_selection_box(
            painter,
            checkbox_rect,
            self._check_state,
            self._check_enabled,
        )

    def mouseReleaseEvent(self, event: QMouseEvent):
        logical_index = self.logicalIndexAt(event.position().toPoint())
        if logical_index == 0 and self._check_enabled:
            self.toggle_all_requested.emit(
                self._check_state != Qt.Checked
            )
            event.accept()
            return
        super().mouseReleaseEvent(event)
