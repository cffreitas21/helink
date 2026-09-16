from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
    QToolButton, QVBoxLayout, QWidget,
)


EXPECTED_FILE_TYPES = (
    '1_Engine_Data_Recording',
    'data_log',
    '2_Exceedance_Log',
    '3_Exceedance_Log_CONT',
    '4_VNE_Dynamic',
    '0_CAS_Default',
    '5_CAS',
    '6_Logbook',
    'Garmin Alerts',
)

FILE_TYPE_LABELS = {
    '1_Engine_Data_Recording': 'Engine Data',
    'data_log': 'GPS / Flight Data',
    '2_Exceedance_Log': 'Exceedance Log',
    '3_Exceedance_Log_CONT': 'Continuous Exceedance Log',
    '4_VNE_Dynamic': 'VNE Dynamic',
    '0_CAS_Default': 'CAS Default',
    '5_CAS': 'CAS Events',
    '6_Logbook': 'Logbook',
    'Garmin Alerts': 'Garmin Alerts',
}


def _ordered_file_types(imported):
    ordered = list(EXPECTED_FILE_TYPES)
    ordered.extend(sorted(imported.difference(EXPECTED_FILE_TYPES)))
    return ordered


def _file_row(file_type, loaded):
    row = QFrame()
    row.setObjectName(
        'importedFileLoaded' if loaded else 'importedFileMissing'
    )
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(10, 8, 10, 8)
    row_layout.setSpacing(10)

    marker = QLabel('\N{CHECK MARK}' if loaded else '\N{EM DASH}')
    marker.setObjectName(
        'importedFileLoadedMarker' if loaded else 'importedFileMissingMarker'
    )
    marker.setAlignment(Qt.AlignCenter)
    marker.setFixedWidth(22)
    row_layout.addWidget(marker)

    text_box = QVBoxLayout()
    text_box.setSpacing(1)
    label = QLabel(FILE_TYPE_LABELS.get(file_type, file_type))
    label.setObjectName('importedFileName')
    exact_name = QLabel(file_type)
    exact_name.setObjectName('importedFileType')
    exact_name.setTextInteractionFlags(Qt.TextSelectableByMouse)
    text_box.addWidget(label)
    text_box.addWidget(exact_name)
    row_layout.addLayout(text_box, 1)

    status = QLabel('Imported' if loaded else 'Missing')
    status.setObjectName(
        'importedFileLoadedStatus' if loaded else 'importedFileMissingStatus'
    )
    status.setAlignment(Qt.AlignCenter)
    status.setMinimumWidth(68)
    row_layout.addWidget(status)
    return row


class ImportedFilesList(QScrollArea):
    """Reusable imported/missing file coverage list."""

    def __init__(self, files=(), parent=None):
        super().__init__(parent)
        self.setObjectName('importedFilesScroll')
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.set_files(files)

    def set_files(self, files):
        imported = set(files or ())
        content = QWidget()
        content.setObjectName('importedFilesContent')
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(5)
        for file_type in _ordered_file_types(imported):
            layout.addWidget(_file_row(file_type, file_type in imported))
        layout.addStretch()

        previous = self.takeWidget()
        if previous is not None:
            previous.deleteLater()
        self.setWidget(content)


class ImportedFilesPopover(QFrame):
    """Click popover showing imported and missing flight file types."""

    def __init__(self, files, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName('importedFilesPopover')
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setFixedWidth(390)

        imported = set(files or ())
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName('importedFilesHeader')
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 13, 16, 12)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel('Imported Files')
        title.setObjectName('importedFilesTitle')
        subtitle = QLabel('File coverage for this flight')
        subtitle.setObjectName('importedFilesSubtitle')
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        count = QLabel(f'{len(imported)} / {len(EXPECTED_FILE_TYPES)}')
        count.setObjectName('importedFilesCount')
        header_layout.addWidget(count)
        root.addWidget(header)

        file_list = ImportedFilesList(imported)
        file_list.setFixedHeight(
            min(430, 62 * len(_ordered_file_types(imported)) + 18)
        )
        root.addWidget(file_list)

    def show_below(self, anchor):
        self.adjustSize()
        position = anchor.mapToGlobal(QPoint(0, anchor.height() + 6))
        screen = QGuiApplication.screenAt(position)
        if screen is not None:
            bounds = screen.availableGeometry()
            x = min(
                max(position.x(), bounds.left()),
                bounds.right() - self.width() + 1,
            )
            y = position.y()
            if y + self.height() > bounds.bottom():
                y = anchor.mapToGlobal(QPoint(0, -self.height() - 6)).y()
            position = QPoint(x, max(bounds.top(), y))
        self.move(position)
        self.show()
        self.raise_()
        self.activateWindow()


class ImportedFilesButton(QToolButton):
    """Compact file count with a preview tooltip and detailed click popover."""

    def __init__(self, files, parent=None):
        super().__init__(parent)
        self.files = tuple(dict.fromkeys(files or ()))
        self.setObjectName('fileList')
        self.setText(
            f'{len(self.files)} file'
            if len(self.files) == 1 else f'{len(self.files)} files'
        )
        self.setFixedSize(116, 36)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setToolTip(self._tooltip_text())
        self._popover = ImportedFilesPopover(self.files, self)
        self.clicked.connect(self._toggle_popover)

    def _tooltip_text(self):
        if not self.files:
            return '<b>No files imported</b><br>Click to view file coverage'
        preview = [FILE_TYPE_LABELS.get(name, name) for name in self.files[:3]]
        remaining = len(self.files) - len(preview)
        lines = '<br>'.join(preview)
        if remaining:
            lines += f'<br>+{remaining} more'
        return (
            f'<b>{len(self.files)} imported file'
            f'{"s" if len(self.files) != 1 else ""}</b><br>'
            f'{lines}<br><span style="color:#cbd5e1">Click for details</span>'
        )

    def _toggle_popover(self):
        if self._popover.isVisible():
            self._popover.hide()
        else:
            self._popover.show_below(self)