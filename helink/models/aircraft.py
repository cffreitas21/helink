from __future__ import annotations

from dataclasses import dataclass
from typing import Any



@dataclass(frozen=True, slots=True)
class Aircraft:
    id: str
    registration: str
    model: str
    serial_number: str
    created_at: str | None = None
    flight_count: int = 0

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> 'Aircraft':
        return cls(
            id=str(record['id']),
            registration=str(record['registration']),
            model=str(record['model']),
            serial_number=str(record['serial_number']),
            created_at=record.get('created_at'),
            flight_count=int(record.get('flight_count') or 0),
        )
