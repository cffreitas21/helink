from __future__ import annotations

from helink.repositories import AircraftRepository


class AircraftController:
    """Coordinates fleet use cases exposed to the UI."""

    def __init__(self, repository: AircraftRepository):
        self.repository = repository

    def list_aircraft(self):
        return self.repository.find_all()

    def engine_averages(self, aircraft_id):
        return self.repository.engine_averages(aircraft_id)

    def add(self, registration, model, serial_number):
        return self.repository.add(registration, model, serial_number)

    def delete(self, aircraft_id):
        self.repository.delete(aircraft_id)
