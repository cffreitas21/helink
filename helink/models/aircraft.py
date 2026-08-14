from __future__ import annotations

from dataclasses import dataclass
from typing import Any



@dataclass(frozen=True, slots=True)
class Aircraft:
    id: str
    registration: str
    model: str
    serial_number: str
    flight_hours: float = 0.0
    created_at: str | None = None
    last_flight: str = 'None'
    active_alerts: int = 0
    flight_count: int = 0

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> 'Aircraft':
        return cls(
            id=str(record['id']),
            registration=str(record['registration']),
            model=str(record['model']),
            serial_number=str(record['serial_number']),
            flight_hours=float(record.get('flight_hours') or 0),
            created_at=record.get('created_at'),
            last_flight=str(record.get('last_flight') or 'None'),
            active_alerts=int(record.get('active_alerts') or 0),
            flight_count=int(record.get('flight_count') or 0),
        )
