from __future__ import annotations

from helink.repositories import FlightRepository


class FlightController:
    """Coordinates flight queries and lifecycle operations."""

    def __init__(self, repository: FlightRepository):
        self.repository = repository

    def list_flights(self, aircraft_id=None):
        return self.repository.find_all(aircraft_id)

    def get(self, flight_id):
        return self.repository.find_by_id(flight_id)

    def delete(self, flight_id):
        self.repository.delete(flight_id)

    def delete_many(self, flight_ids):
        self.repository.delete_many(flight_ids)
