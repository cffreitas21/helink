from __future__ import annotations
from datetime import date

from helink.repositories import FlightRepository
from helink.repositories.aircraft_repository import AircraftRepository
from helink.services.flight_details_service import prepare_flight_details


class FlightController:
    """Coordinates flight queries and lifecycle operations."""

    def __init__(self, repository: FlightRepository, tasks=None):
        self.repository = repository
        self.tasks = tasks

    def request(self, method, *args, on_result, on_error, **kwargs):
        return self.tasks.query(
            lambda database, _progress: getattr(
                FlightController(FlightRepository(database)), method,
            )(*args, **kwargs),
            on_result, on_error,
            cache_key=('flight', method, args, kwargs),
        )

    def details_data(self, flight_id):
        flight = self.get(flight_id)
        if flight is None:
            raise ValueError('The selected flight is no longer available.')
        aircraft = AircraftRepository(self.repository.database).find_by_id(flight.aircraft_id)
        return prepare_flight_details(flight, aircraft)

    def list_page_data(self, aircraft_id, **kwargs):
        aircraft = AircraftRepository(self.repository.database).find_by_id(aircraft_id)
        return aircraft, self.list_flights(aircraft_id, **kwargs)

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
