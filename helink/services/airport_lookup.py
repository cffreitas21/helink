"""Resolve ICAO names and infer destinations from offline GPS coordinates."""

from __future__ import annotations

import json
from math import asin, cos, isfinite, radians, sin, sqrt
from pathlib import Path


ICAO_DICTIONARY_FILE = (
    Path(__file__).resolve().parents[1]
    / 'assets'
    / 'icao_dictionary.json'
)


def _load_icao_dictionary() -> dict[str, dict]:
    """Load offline airfield names and coordinates distributed with HELINK."""
    try:
        with ICAO_DICTIONARY_FILE.open(encoding='utf-8') as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError, TypeError):
        return {}

    result = {}
    for code, record in data.items():
        normalized = str(code).strip().upper()
        if isinstance(record, str):
            record = {'name': record, 'gps': None}
        if normalized and isinstance(record, dict) and record.get('name'):
            result[normalized] = record
    return result


ICAO_DICTIONARY = _load_icao_dictionary()


def format_airport(code: str | None) -> str:
    """Return an ICAO code with its offline location name when known."""
    normalized = str(code or '').strip().upper()
    if not normalized or normalized == '-':
        return '\N{EM DASH}'
    record = ICAO_DICTIONARY.get(normalized)
    name = record['name'] if record else None
    return f'{normalized} - {name}' if name else normalized


def nearest_airport(latitude, longitude, max_distance_km=5.0) -> str:
    """Return the nearest ICAO code inside the search radius, or ``''``.

    The default margin is strictly less than 5 km: about 2.7 nautical miles
    (3.1 statute miles). Distances use the haversine great-circle formula.
    """
    try:
        latitude, longitude = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return ''
    if (not isfinite(latitude) or not isfinite(longitude)
            or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
            or (latitude == 0 and longitude == 0)):
        return ''

    closest_code = ''
    closest_distance = max_distance_km
    for code, record in ICAO_DICTIONARY.items():
        gps = record.get('gps')
        if not isinstance(gps, list) or len(gps) != 2:
            continue
        try:
            airfield_lat, airfield_lon = map(float, gps)
        except (TypeError, ValueError):
            continue
        delta_lat = radians(airfield_lat - latitude)
        delta_lon = radians(airfield_lon - longitude)
        arc = (sin(delta_lat / 2) ** 2
               + cos(radians(latitude)) * cos(radians(airfield_lat))
               * sin(delta_lon / 2) ** 2)
        # 12,742 km is Earth's approximate diameter; the result is in km.
        distance = 12742 * asin(min(1.0, sqrt(max(0.0, arc))))
        if distance < closest_distance:
            closest_code, closest_distance = code, distance
    return closest_code


def destination_from_gps(points) -> str:
    """Infer the destination from the last valid recorded GPS coordinate.

    Match it to the nearest aerodrome within the default 5 km margin
    (approximately 2.7 nautical miles, or 3.1 statute miles). Return an empty
    code when no aerodrome falls inside that radius; earlier route points are
    not used as a fallback.
    """
    for point in reversed(points):
        latitude = (point.get('latitude') if isinstance(point, dict)
                    else getattr(point, 'latitude', None))
        longitude = (point.get('longitude') if isinstance(point, dict)
                     else getattr(point, 'longitude', None))
        try:
            lat, lon = float(latitude), float(longitude)
        except (TypeError, ValueError):
            continue
        if isfinite(lat) and isfinite(lon) and -90 <= lat <= 90 \
                and -180 <= lon <= 180 and (lat != 0 or lon != 0):
            return nearest_airport(lat, lon)
    return ''
