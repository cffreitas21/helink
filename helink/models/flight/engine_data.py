"""Recorded engine-parameter sample entity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any



def _number(value):
    """Convert a present database measurement to float without inventing zero."""
    return None if value is None else float(value)


@dataclass(frozen=True, slots=True)
class EngineData:
    """One timestamped engine sample; missing measurements remain ``None``."""
    id: int
    flight_id: str
    seq: int | None = None
    timestamp: str | None = None
    n1: float | None = None
    n2: float | None = None
    nr: float | None = None
    itt: float | None = None
    tq: float | None = None
    eng_ot: float | None = None
    fuel_press: float | None = None
    eng_op: float | None = None
    xmsn_op: float | None = None
    xmsn_ot: float | None = None
    oat: float | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> 'EngineData':
        """Convert a database row into typed engine measurements."""
        return cls(
            id=int(record['id']),
            flight_id=str(record['flight_id']),
            seq=None if record.get('seq') is None else int(record['seq']),
            timestamp=record.get('timestamp'),
            n1=_number(record.get('n1')),
            n2=_number(record.get('n2')),
            nr=_number(record.get('nr')),
            itt=_number(record.get('itt')),
            tq=_number(record.get('tq')),
            eng_ot=_number(record.get('eng_ot')),
            fuel_press=_number(record.get('fuel_press')),
            eng_op=_number(record.get('eng_op')),
            xmsn_op=_number(record.get('xmsn_op')),
            xmsn_ot=_number(record.get('xmsn_ot')),
            oat=_number(record.get('oat')),
        )
