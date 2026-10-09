"""Fleet use cases and background query entry points."""

from __future__ import annotations
from datetime import date

from helink.repositories import AircraftRepository
from helink.services.aircraft_trend_summary import summarise_aircraft_trends


class AircraftController:
    """Coordinates fleet use cases exposed to the UI."""

    def __init__(self, repository: AircraftRepository, tasks=None):
        """Bind aircraft storage and an optional background task runner."""
        self.repository = repository
        self.tasks = tasks

    def request(self, method, *args, on_result, on_error, **kwargs):
        """Run a fleet query off the UI thread and cache its result."""
        return self.tasks.query(
            lambda database, _progress: getattr(
                AircraftController(AircraftRepository(database)), method,
            )(*args, **kwargs),
            on_result, on_error,
            cache_key=('aircraft', method, args, kwargs),
        )

    def fleet_data(self):
        """Load aircraft and their parameter summaries as one complete view."""
        return self.list_aircraft(), self.fleet_summaries()

    def analysis_data(self, aircraft_id, allow_comparison, parameter, minimum_minutes=0):
        """Return aircraft choices and daily values for the analysis screen."""
        if allow_comparison:
            aircraft = self.list_for_analysis()
        else:
            item = self.get(aircraft_id)
            aircraft = [item] if item is not None else []
        selected = [
            item.id for item in aircraft
            if not aircraft_id or item.id == aircraft_id
        ]
        return aircraft, self.daily_parameter_trends(
            selected, parameter, minimum_minutes=minimum_minutes,
        )

    def list_aircraft(self):
        """Return all registered aircraft."""
        return self.repository.find_all()

    def get(self, aircraft_id):
        """Return one aircraft by its identifier, if it exists."""
        return self.repository.find_by_id(aircraft_id)


    def fleet_summaries(self):
        """Return aggregated parameter readings for the fleet list."""
        return self.repository.fleet_summaries()

    def list_for_analysis(self):
        """Return aircraft eligible for comparison in trend analysis."""
        return self.repository.find_for_analysis()

    def daily_parameter_trends(
        self, aircraft_ids, parameter, *, start_date=None, end_date=None,
        minimum_minutes=0,
    ):
        """Return per-day parameter trends within the validated date range."""
        start = date.fromisoformat(str(start_date)).isoformat() if start_date else None
        end = date.fromisoformat(str(end_date)).isoformat() if end_date else None
        if start and end and start > end:
            raise ValueError('The start date must not be after the end date.')
        if isinstance(aircraft_ids, str):
            aircraft_ids = (aircraft_ids,)
        return self.repository.daily_parameter_trends(
            aircraft_ids, parameter, start_date=start, end_date=end,
            minimum_minutes=minimum_minutes,
        )

    def trend_summaries(self, days, statistic='average'):
        """Summarise the requested statistic across daily trend records."""
        return summarise_aircraft_trends(days, statistic)

    def parameter_flights_for_day(
        self, aircraft_id, flight_date, parameter, *, minimum_minutes=0,
    ):
        """Return individual flight readings behind one daily trend point."""
        day = date.fromisoformat(str(flight_date)).isoformat()
        return self.repository.parameter_flights_for_day(
            aircraft_id, day, parameter, minimum_minutes=minimum_minutes,
        )

    def add(self, registration, model, serial_number):
        """Create an aircraft with its registration and identity details."""
        return self.repository.add(registration, model, serial_number)

    def delete(self, aircraft_id):
        """Delete the selected aircraft through the repository."""
        self.repository.delete(aircraft_id)
