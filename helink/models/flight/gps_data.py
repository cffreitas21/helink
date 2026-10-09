"""Recorded GPS and flight-data sample entity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any



def _number(value):
    """Convert a present GPS measurement to float without inventing zero."""
    return None if value is None else float(value)


@dataclass(frozen=True, slots=True)
class GPSData:
    """One timestamped position and flight-data sample."""
    id: int
    flight_id: str
    seq: int | None = None
    timestamp: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    alt_ind: float | None = None
    ias: float | None = None
    pitch: float | None = None
    roll: float | None = None
    heading: float | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> 'GPSData':
        """Convert a database row into typed GPS measurements."""
        return cls(
            id=int(record['id']),
            flight_id=str(record['flight_id']),
            seq=None if record.get('seq') is None else int(record['seq']),
            timestamp=record.get('timestamp'),
            latitude=_number(record.get('latitude')),
            longitude=_number(record.get('longitude')),
            alt_ind=_number(record.get('alt_ind')),
            ias=_number(record.get('ias')),
            pitch=_number(record.get('pitch')),
            roll=_number(record.get('roll')),
            heading=_number(record.get('heading')),
        )
