from __future__ import annotations
from dataclasses import replace
from datetime import date

from helink.repositories import FlightRepository
from helink.repositories.aircraft_repository import AircraftRepository
from helink.services.flight_details_service import prepare_flight_details
from helink.services.preventive_maintenance_service import (
    LIMITS, assess_preventive_maintenance, aw119_limits_apply,
    screen_upper_limit_rows,
)


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
        flights = self.repository.find_summaries(
            aircraft_id, start_date=start, end_date=end, descending=descending,
        )
        if not flights:
            return flights

        aircraft_repository = AircraftRepository(self.repository.database)
        models = {}
        for item in flights:
            if item.aircraft_id not in models:
                aircraft = aircraft_repository.find_by_id(item.aircraft_id)
                models[item.aircraft_id] = aircraft.model if aircraft else ''
        applicable_ids = [
            item.id for item in flights
            if aw119_limits_apply(models[item.aircraft_id])
        ]
        statuses = screen_upper_limit_rows(
            self.repository.find_engine_limit_exceedances(applicable_ids, LIMITS),
        )
        for flight_id in self.repository.find_irregular_engine_sequences(statuses):
            if statuses[flight_id] != 'critical':
                statuses[flight_id] = 'verify_duration'
        result = []
        for flight in flights:
            model = models[flight.aircraft_id]
            if not aw119_limits_apply(model):
                status = 'not_applicable'
            elif flight.id not in statuses:
                status = (
                    'normal' if self.repository.has_limit_parameter_data(flight.id)
                    else 'unavailable'
                )
            elif statuses[flight.id] == 'verify_duration':
                rows = self.repository.find_engine_limit_rows(flight.id)
                assessment = assess_preventive_maintenance(
                    replace(flight, engine_data=rows), model,
                )
                status = (
                    'critical' if any(
                        event.severity == 'critical'
                        for event in assessment.events
                    )
                    else 'review' if assessment.events else 'normal'
                )
            else:
                status = statuses[flight.id]
            result.append(replace(flight, preventive_status=status))
        return result

    def get(self, flight_id):
        return self.repository.find_by_id(flight_id)

    def delete(self, flight_id):
        self.repository.delete(flight_id)

    def delete_many(self, flight_ids):
        self.repository.delete_many(flight_ids)
