from __future__ import annotations

from helink.services.report_service import ReportService
from helink.repositories.flight_repository import FlightRepository
from helink.repositories.aircraft_repository import AircraftRepository


class ReportController:
    """Coordinates maintenance report generation and export."""

    def __init__(self, service: ReportService, tasks=None):
        self.service = service
        self.tasks = tasks

    def request_export(self, flight_id, destination, on_result, on_error):
        def export(database, _progress):
            repository = FlightRepository(database)
            path = ReportService(
                repository, AircraftRepository(database),
            ).export_pdf(flight_id, destination)
            return path, repository.find_metadata_by_id(flight_id).predictive_report
        return self.tasks.write(
            export,
            on_result, on_error,
        )

    def generate(self, flight_id):
        return self.service.generate(flight_id)

    def export_pdf(self, flight_id, destination):
        return self.service.export_pdf(flight_id, destination)
