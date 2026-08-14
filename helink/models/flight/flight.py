from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from helink.models.flight.alert import Alert
from helink.models.flight.engine_data import EngineData
from helink.models.flight.gps_data import GPSData


@dataclass(frozen=True, slots=True)
class Flight:
    id: str
    aircraft_id: str
    flight_date: str
    departure_time: str = ''
    duration: str = ''
    origin: str = ''
    destination: str = ''
    imported_files: tuple[str, ...] = field(default_factory=tuple)
    predictive_report: str = ''
    created_at: str | None = None
    engine_data: tuple[EngineData, ...] = field(default_factory=tuple)
    data_log: tuple[GPSData, ...] = field(default_factory=tuple)
    alerts: tuple[Alert, ...] = field(default_factory=tuple)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> 'Flight':
        return cls(
            id=str(record['id']),
            aircraft_id=str(record['aircraft_id']),
            flight_date=str(record['flight_date']),
            departure_time=str(record.get('departure_time') or ''),
            duration=str(record.get('duration') or ''),
            origin=str(record.get('origin') or ''),
            destination=str(record.get('destination') or ''),
            imported_files=tuple(record.get('imported_files') or ()),
            predictive_report=str(record.get('predictive_report') or ''),
            created_at=record.get('created_at'),
            engine_data=tuple(
                item if isinstance(item, EngineData) else EngineData.from_record(item)
                for item in record.get('engine_data') or ()
            ),
            data_log=tuple(
                item if isinstance(item, GPSData) else GPSData.from_record(item)
                for item in record.get('data_log') or ()
            ),
            alerts=tuple(
                item if isinstance(item, Alert) else Alert.from_record(item)
                for item in record.get('alerts') or ()
            ),
        )
