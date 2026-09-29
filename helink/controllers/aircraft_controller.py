from __future__ import annotations
from datetime import date

from helink.repositories import AircraftRepository
from helink.services.aircraft_trend_summary import summarise_aircraft_trends


class AircraftController:
    """Coordinates fleet use cases exposed to the UI."""

    def __init__(self, repository: AircraftRepository, tasks=None):
        self.repository = repository
        self.tasks = tasks

    def request(self, method, *args, on_result, on_error, **kwargs):
        return self.tasks.query(
            lambda database, _progress: getattr(
                AircraftController(AircraftRepository(database)), method,
            )(*args, **kwargs),
            on_result, on_error,
            cache_key=('aircraft', method, args, kwargs),
        )

    def dashboard_data(self):
        return self.list_aircraft(), self.fleet_summaries()

    def analysis_data(self, aircraft_id, allow_comparison, parameter):
        if allow_comparison:
            aircraft = self.list_for_analysis()
        else:
            item = self.get(aircraft_id)
            aircraft = [item] if item is not None else []
        selected = [
            item.id for item in aircraft
            if not aircraft_id or item.id == aircraft_id
        ]
        return aircraft, self.daily_parameter_trends(selected, parameter)

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
