from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AircraftParameterFlight:
    """Read-only sensor statistics for one flight, not a database table."""

    flight_id: str
    aircraft_id: str
    flight_date: str
    departure_time: str
    arrival_time: str
    average: float | None
    maximum: float | None
    sample_count: int

    @classmethod
    def from_record(cls, record):
        return cls(
            flight_id=str(record['flight_id']),
            aircraft_id=str(record['aircraft_id']),
            flight_date=str(record['flight_date']),
            departure_time=str(record['departure_time'] or ''),
            arrival_time=str(record['arrival_time'] or ''),
            average=None if record['average'] is None else float(record['average']),
            maximum=None if record['maximum'] is None else float(record['maximum']),
            sample_count=int(record['sample_count']),
        )
