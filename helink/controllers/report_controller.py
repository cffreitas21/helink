"""Coordinate flight-report PDF exports."""

from __future__ import annotations

from helink.services.report_service import ReportService
from helink.repositories.flight_repository import FlightRepository
from helink.repositories.aircraft_repository import AircraftRepository


class ReportController:
    """Coordinates maintenance report generation and export."""

    def __init__(self, service: ReportService, tasks=None):
        """Bind PDF generation and optional background task handling."""
        self.service = service
        self.tasks = tasks

    def request_export(self, flight_id, destination, on_result, on_error):
        """Export a flight PDF in a background database task."""
        def export(database, _progress):
            """Resolve worker-owned repositories and export the PDF."""
            repository = FlightRepository(database)
            return ReportService(
                repository, AircraftRepository(database),
            ).export_pdf(flight_id, destination)
        return self.tasks.query(
            export,
            on_result, on_error,
        )

    def export_pdf(self, flight_id, destination):
        """Generate and save the PDF report for one flight."""
        return self.service.export_pdf(flight_id, destination)
