from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)


class ImportSummaryDialog(QDialog):
    """Show the final import outcome, including every excluded file."""

    def __init__(self, result, parent=None):
        super().__init__(parent)
        skipped = result.skipped_files
        title = (
            'No files imported' if not result.file_count else
            'Import completed with exceptions' if skipped else
            'Import complete'
        )
        self.setWindowTitle(title)
        self.setMinimumWidth(690 if skipped else 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        heading = QLabel(title)
        heading.setStyleSheet('font-size:19px;font-weight:750;color:#0f172a')
        layout.addWidget(heading)

        imported = result.file_count
        if imported:
            files_label = 'file' if imported == 1 else 'files'
            flights_label = 'flight' if result.flight_count == 1 else 'flights'
            summary = QLabel(
                f'{imported} {files_label} imported successfully for '
                f'{result.flight_count} {flights_label}.'
            )
        else:
            summary = QLabel('No files were imported.')
        summary.setWordWrap(True)
        layout.addWidget(summary)

        if skipped:
            skipped_count = len(skipped)
            detail = QLabel(
                (f'{skipped_count} file was not imported. '
                 if skipped_count == 1 else
                 f'{skipped_count} files were not imported. ')
                + 'Review the reason for each file below.'
            )
            detail.setWordWrap(True)
            detail.setObjectName('muted')
            layout.addWidget(detail)

            table = QTableWidget(len(skipped), 2)
            table.setHorizontalHeaderLabels(['FILE', 'REASON'])
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionMode(QAbstractItemView.NoSelection)
            table.setWordWrap(True)
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(44)
            table.horizontalHeader().setSectionResizeMode(
                QHeaderView.Stretch
            )
            for row, (name, reason) in enumerate(skipped):
                for column, value in enumerate((name, reason)):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                    table.setItem(row, column, item)
            table.resizeRowsToContents()
            table.setMinimumHeight(min(360, 55 + 44 * len(skipped)))
            layout.addWidget(table)

        close = QPushButton('Close')
        close.clicked.connect(self.accept)
        layout.addWidget(close, 0, Qt.AlignRight)

