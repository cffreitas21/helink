"""Recorded parameter series aligned to the selected flight timeline."""

import re
from math import isfinite

from helink.parameters import GPS_PARAMETERS as GPS_DEFINITIONS

GPS_PARAMETER_KEYS = frozenset(item.key for item in GPS_DEFINITIONS)


def _clock_key(timestamp):
    """Normalize a recorded clock to an hour-minute-second lookup key."""
    matches = re.findall(
        r'(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?', str(timestamp or ''),
    )
    if not matches:
        return None
    hour, minute, second = matches[-1]
    parts = int(hour), int(minute), int(second or 0)
    return parts if parts[0] < 24 and parts[1] < 60 and parts[2] < 60 else None


def _recorded_value(record, key):
    """Return a finite sensor value or NaN for missing measurements."""
    try:
        value = float(getattr(record, key, None))
    except (TypeError, ValueError):
        return float('nan')
    return value if isfinite(value) else float('nan')


def flight_parameter_series(flight, key, timeline):
    """Match actual recorded seconds; do not interpolate or invent missing data."""
    records = flight.data_log if key in GPS_PARAMETER_KEYS else flight.engine_data
    if timeline is records:
        return [_recorded_value(record, key) for record in records]
    by_time = {}
    for record in records:
        clock = _clock_key(record.timestamp)
        value = _recorded_value(record, key)
        if clock is not None and isfinite(value):
            by_time[clock] = value
    return [
        by_time.get(_clock_key(record.timestamp), float('nan'))
        for record in timeline
    ]
