"""Summarize daily aircraft sensor trends for the analysis page."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AircraftTrendSummary:
    """First, latest, and peak daily values for an aircraft trend."""
    day_count: int
    first_date: str
    last_date: str
    first_value: float
    last_value: float
    maximum: float


def summarise_aircraft_trends(days, statistic='average'):
    """Summarise first/latest recorded days, without filling missing days."""
    if statistic not in ('average', 'maximum'):
        raise ValueError('Select AVG or MAX for the trend summary.')
    by_aircraft = {}
    for day in days:
        by_aircraft.setdefault(day.aircraft_id, []).append(day)
    summaries = {}
    for aircraft_id, recorded_days in by_aircraft.items():
        ordered = sorted(recorded_days, key=lambda day: day.flight_date)
        first, last = ordered[0], ordered[-1]
        first_value = getattr(first, statistic)
        last_value = getattr(last, statistic)
        summaries[aircraft_id] = AircraftTrendSummary(
            day_count=len(ordered),
            first_date=first.flight_date,
            last_date=last.flight_date,
            first_value=first_value,
            last_value=last_value,
            maximum=max(day.maximum for day in ordered),
        )
    return summaries
