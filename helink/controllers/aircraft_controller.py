from __future__ import annotations
from datetime import date

from helink.repositories import AircraftRepository
from helink.services.aircraft_trend_summary import summarise_aircraft_trends


class AircraftController:
    """Coordinates fleet use cases exposed to the UI."""

    def __init__(self, repository: AircraftRepository):
        self.repository = repository

    def list_aircraft(self):
        return self.repository.find_all()

    def get(self, aircraft_id):
        return self.repository.find_by_id(aircraft_id)


    def fleet_summaries(self):
        return self.repository.fleet_summaries()

    def list_for_analysis(self):
        return self.repository.find_for_analysis()

    def daily_parameter_trends(
        self, aircraft_ids, parameter, *, start_date=None, end_date=None,
    ):
        start = date.fromisoformat(str(start_date)).isoformat() if start_date else None
        end = date.fromisoformat(str(end_date)).isoformat() if end_date else None
        if start and end and start > end:
            raise ValueError('The start date must not be after the end date.')
        if isinstance(aircraft_ids, str):
            aircraft_ids = (aircraft_ids,)
        return self.repository.daily_parameter_trends(
            aircraft_ids, parameter, start_date=start, end_date=end,
        )

    def trend_summaries(self, days, statistic='average'):
        return summarise_aircraft_trends(days, statistic)

    def parameter_flights_for_day(self, aircraft_id, flight_date, parameter):
        day = date.fromisoformat(str(flight_date)).isoformat()
        return self.repository.parameter_flights_for_day(aircraft_id, day, parameter)

    def add(self, registration, model, serial_number):
        return self.repository.add(registration, model, serial_number)

    def delete(self, aircraft_id):
        self.repository.delete(aircraft_id)
