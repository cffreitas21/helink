from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from helink.models.flight.alert_trigger import AlertTrigger



@dataclass(frozen=True, slots=True)
class Alert:
    id: int
    flight_id: str
    kind: str
    timestamp: str | None = None
    alert_state: str | None = None
    alert_name: str | None = None
    level: str | None = None
    description: str | None = None
    trigger_name: str | None = None
    trigger_value: str | None = None
    trigger_units: str | None = None
    trigger_state: str | None = None
    triggers: tuple[AlertTrigger, ...] = ()

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> 'Alert':
        return cls(
            id=int(record['id']),
            flight_id=str(record['flight_id']),
            kind=str(record.get('kind') or ''),
            timestamp=record.get('timestamp'),
            alert_state=record.get('alert_state'),
            alert_name=record.get('alert_name'),
            level=record.get('level'),
            description=record.get('description'),
            trigger_name=record.get('trigger_name'),
            trigger_value=record.get('trigger_value'),
            trigger_units=record.get('trigger_units'),
            trigger_state=record.get('trigger_state'),
            triggers=tuple(AlertTrigger.from_record(item) for item in record.get('triggers', [])),
        )
