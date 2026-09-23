from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout


class FleetParameterCard(QFrame):
    """Readable two-column AVG/MAX telemetry card for fleet summaries."""

    def __init__(self, title, average, maximum, unit, parent=None):
        super().__init__(parent)
        self.setObjectName('fleetParameterCard')
        self.setFixedSize(181, 86)

        root = QVBoxLayout(self)
        root.setContentsMargins(5, 8, 5, 9)
        root.setSpacing(5)

        heading = QHBoxLayout()
        heading.setSpacing(2)
        title_label = QLabel(title.upper())
        title_label.setObjectName('fleetParameterTitle')
        title_label.setToolTip(f'{title} ({unit})')
        heading.addWidget(title_label)
        heading.addStretch()
        unit_label = QLabel(unit)
        unit_label.setObjectName('fleetParameterUnit')
        unit_label.setToolTip(f'{title} ({unit})')
        heading.addWidget(unit_label)
        root.addLayout(heading)

        statistics = QGridLayout()
        statistics.setContentsMargins(0, 0, 0, 0)
        statistics.setHorizontalSpacing(14)
        statistics.setVerticalSpacing(1)
        statistics.setColumnStretch(0, 1)
        statistics.setColumnStretch(1, 1)

        for column, (caption_text, value) in enumerate(
            (('AVG', average), ('MAX', maximum))
        ):
            caption = QLabel(caption_text)
            caption.setObjectName('fleetParameterStatistic')
            caption.setAlignment(Qt.AlignCenter)
            statistics.addWidget(caption, 0, column)

            value_text = '\N{EM DASH}' if value is None else f'{value:.1f}'
            value_label = QLabel(value_text)
            value_label.setObjectName('fleetParameterValue')
            value_label.setAlignment(Qt.AlignCenter)
            if value is not None:
                value_label.setToolTip(
                    f'{caption_text}: {value:.1f} {unit}'
                )
            statistics.addWidget(value_label, 1, column)

        root.addLayout(statistics)