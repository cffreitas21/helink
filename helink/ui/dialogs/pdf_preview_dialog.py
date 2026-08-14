from pathlib import Path
import shutil

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QVBoxLayout,
)


class PdfPreviewDialog(QDialog):
    def __init__(self, pdf_path, suggested_name, parent=None):
        super().__init__(parent)
        self.pdf_path = Path(pdf_path)
        self.suggested_name = suggested_name
        self.setWindowTitle('Maintenance Report ? PDF Preview')
        self.resize(980, 760)
        self.setMinimumSize(760, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(10)

        toolbar = QHBoxLayout()
        title = QLabel('Maintenance Report Preview')
        title.setObjectName('title')
        toolbar.addWidget(title)
        toolbar.addStretch()

        zoom_out = QPushButton('?')
        zoom_out.setObjectName('secondary')
        zoom_out.setFixedSize(38, 34)
        zoom_out.setToolTip('Zoom out')
        zoom_out.clicked.connect(lambda: self._zoom(0.85))
        toolbar.addWidget(zoom_out)

        fit = QPushButton('Fit Width')
        fit.setObjectName('secondary')
        fit.clicked.connect(
            lambda: self.viewer.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        )
        toolbar.addWidget(fit)

        zoom_in = QPushButton('+')
        zoom_in.setObjectName('secondary')
        zoom_in.setFixedSize(38, 34)
        zoom_in.setToolTip('Zoom in')
        zoom_in.clicked.connect(lambda: self._zoom(1.15))
        toolbar.addWidget(zoom_in)
        root.addLayout(toolbar)

        self.pdf_data = QByteArray(self.pdf_path.read_bytes())
        self.pdf_buffer = QBuffer(self)
        self.pdf_buffer.setData(self.pdf_data)
        self.pdf_buffer.open(QIODevice.ReadOnly)
        self.document = QPdfDocument(self)
        error = self.document.load(self.pdf_buffer)
        if error is not None and error != QPdfDocument.Error.None_:
            raise RuntimeError('The PDF preview could not be loaded.')

        self.viewer = QPdfView(self)
        self.viewer.setDocument(self.document)
        self.viewer.setPageMode(QPdfView.PageMode.MultiPage)
        self.viewer.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        root.addWidget(self.viewer, 1)

        footer = QHBoxLayout()
        pages = QLabel(
            f'{self.document.pageCount()} page' +
            ('s' if self.document.pageCount() != 1 else '')
        )
        pages.setObjectName('muted')
        footer.addWidget(pages)
        footer.addStretch()
        close = QPushButton('Close')
        close.setObjectName('secondary')
        close.clicked.connect(self.reject)
        footer.addWidget(close)
        save = QPushButton('Save PDF')
        save.clicked.connect(self.save_pdf)
        footer.addWidget(save)
        root.addLayout(footer)

    def _zoom(self, factor):
        self.viewer.setZoomMode(QPdfView.ZoomMode.Custom)
        self.viewer.setZoomFactor(
            max(0.25, min(4.0, self.viewer.zoomFactor() * factor))
        )

    def save_pdf(self):
        destination, _ = QFileDialog.getSaveFileName(
            self,
            'Save Maintenance Report',
            self.suggested_name,
            'PDF Document (*.pdf)',
        )
        if not destination:
            return
        destination = Path(destination)
        if destination.suffix.lower() != '.pdf':
            destination = destination.with_suffix('.pdf')
        try:
            shutil.copy2(self.pdf_path, destination)
        except Exception as error:
            QMessageBox.critical(self, 'Save error', str(error))
            return
        QMessageBox.information(
            self,
            'Report saved',
            f'PDF report saved successfully to:\n{destination}',
        )

    def release(self):
        self.viewer.setDocument(None)
        self.document.close()
        self.pdf_buffer.close()
