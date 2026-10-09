from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter

from helink.services.flight_report_builder import flight_report_html


class ReportService:
    def __init__(self, flights, aircraft):
        self.flights = flights
        self.aircraft = aircraft

    def _records(self, flight_id):
        flight = self.flights.find_by_id(flight_id)
        if flight is None:
            raise ValueError('The selected flight is no longer available.')
        return flight, self.aircraft.find_by_id(flight.aircraft_id)

    def export_pdf(self, flight_id, destination):
        destination = Path(destination)
        if destination.suffix.lower() != '.pdf':
            destination = destination.with_suffix('.pdf')
        flight, aircraft = self._records(flight_id)
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
        document.setHtml(flight_report_html(flight, aircraft))
        document.print_(printer)
        if not destination.exists() or destination.stat().st_size == 0:
            raise RuntimeError('The PDF report could not be created.')
        return destination
