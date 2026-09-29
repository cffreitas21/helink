from __future__ import annotations
from datetime import date

from helink.repositories import FlightRepository


class FlightController:
    """Coordinates flight queries and lifecycle operations."""

    def __init__(self, repository: FlightRepository):
        self.repository = repository

    def list_flights(
        self, aircraft_id=None, *, start_date=None, end_date=None, descending=True,
    ):
        start = date.fromisoformat(str(start_date)).isoformat() if start_date else None
        end = date.fromisoformat(str(end_date)).isoformat() if end_date else None
        if start and end and start > end:
            raise ValueError('The start date must not be after the end date.')
        return self.repository.find_summaries(
            aircraft_id, start_date=start, end_date=end, descending=descending,
        )

    def get(self, flight_id):
        return self.repository.find_by_id(flight_id)

    def delete(self, flight_id):
        self.repository.delete(flight_id)

    def delete_many(self, flight_ids):
        self.repository.delete_many(flight_ids)
