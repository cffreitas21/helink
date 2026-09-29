from __future__ import annotations

from helink.services.flight_import_service import FlightImportService
from helink.repositories.flight_repository import FlightRepository


class ImportController:
    """Coordinates Garmin imports without exposing services to views."""

    def __init__(self, service: FlightImportService, tasks=None):
        self.service = service
        self.tasks = tasks

    def request(self, method, *args, on_result, on_error, on_progress):
        return self.tasks.write(
            lambda database, progress: getattr(
                FlightImportService(FlightRepository(database)), method,
            )(*args, progress=progress),
            on_result, on_error, on_progress=on_progress,
        )

    def import_for_aircraft(
        self, paths, aircraft_id, progress=None
    ):
        return self.service.import_for_aircraft(
            paths, aircraft_id, progress
        )

    def add_to_flight(
        self, paths, flight_id, file_type, progress=None
    ):
        return self.service.add_to_flight(
            paths, flight_id, file_type, progress
        )
