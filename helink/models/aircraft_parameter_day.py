"""Read-only daily aircraft parameter aggregate."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AircraftParameterDay:
    """Read-only daily aggregate, not an additional database table."""

    aircraft_id: str
    flight_date: str
    average: float
    maximum: float
    flight_count: int
    sample_count: int

    @classmethod
    def from_record(cls, record):
        """Build the daily aggregate returned by an analysis query."""
        return cls(
            aircraft_id=str(record['aircraft_id']),
            flight_date=str(record['flight_date']),
            average=float(record['average']),
            maximum=float(record['maximum']),
            flight_count=int(record['flight_count']),
            sample_count=int(record['sample_count']),
        )
