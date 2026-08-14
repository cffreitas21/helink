from __future__ import annotations

from helink.services.report_service import ReportService


class ReportController:
    """Coordinates maintenance report generation and export."""

    def __init__(self, service: ReportService):
        self.service = service

    def generate(self, flight_id):
        return self.service.generate(flight_id)

    def export_pdf(self, flight_id, destination):
        return self.service.export_pdf(flight_id, destination)
