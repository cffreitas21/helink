from __future__ import annotations

from helink.services.flight_import_service import FlightImportService


class ImportController:
    """Coordinates file imports without exposing the service to views."""

    def __init__(self, service: FlightImportService):
        self.service = service

    def import_for_aircraft(self, paths, aircraft_id):
        return self.service.import_for_aircraft(paths, aircraft_id)

    def add_to_flight(self, paths, flight_id, file_type):
        return self.service.add_to_flight(paths, flight_id, file_type)
