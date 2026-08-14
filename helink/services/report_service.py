from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter

from helink.services.maintenance_report_builder import (
    technical_report,
    technical_report_html,
)


class ReportService:
    def __init__(self, flights):
        self.flights = flights

    def generate(self, flight_id):
        report = technical_report(self.flights.find_by_id(flight_id))
        self.flights.save_report(flight_id, report)
        return report

    def export_pdf(self, flight_id, destination):
        destination = Path(destination)
        if destination.suffix.lower() != '.pdf':
            destination = destination.with_suffix('.pdf')
        flight = self.flights.find_by_id(flight_id)
        report = technical_report(flight)
        self.flights.save_report(flight_id, report)

        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(str(destination))
        printer.setPageSize(QPageSize(QPageSize.A4))
        printer.setPageMargins(
            QMarginsF(14, 14, 14, 14),
            QPageLayout.Millimeter,
        )
        document = QTextDocument()
        document.setDocumentMargin(0)
        document.setHtml(technical_report_html(flight))
        document.print_(printer)
        if not destination.exists() or destination.stat().st_size == 0:
            raise RuntimeError('The PDF report could not be created.')
        return destination
