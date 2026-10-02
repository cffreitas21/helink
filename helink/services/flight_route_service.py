"""Shared validation for recorded positions and offline route availability."""

from dataclasses import dataclass
from pathlib import Path
import re

from helink.models.flight.flight import Flight


OFFLINE_MAP_ASSETS = (
    'leaflet.css', 'leaflet.js', 'protomaps-leaflet.js', 'portugal_z12.pmtiles',
)


@dataclass(frozen=True, slots=True)
class RouteAvailability:
    available: bool
    reason: str


def route_coordinates(record):
    """Use the same geographic coverage for Overview and the map renderer."""
    try:
        latitude = float(record.latitude)
        longitude = float(record.longitude)
    except (AttributeError, TypeError, ValueError):
        return None
    if not (35 <= latitude <= 45 and -11 <= longitude <= 5):
        return None
    return latitude, longitude


def _clock_seconds(value):
    matches = re.findall(
        r'(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?', str(value or ''),
    )
    if not matches:
        return None
    hour, minute, second = (int(part or 0) for part in matches[-1])
    if hour >= 24 or minute >= 60 or second >= 60:
        return None
    return hour * 3600 + minute * 60 + second


def nearest_route_point_index(flight: Flight, sample):
    """Return the nearest valid GPS point in the map's filtered point list."""
    sample_time = _clock_seconds(getattr(sample, 'timestamp', None))
    nearest_index = None
    nearest_distance = None
    valid_index = 0
    for record in flight.data_log:
        if route_coordinates(record) is None:
            continue
        if record is sample:
            return valid_index
        record_time = _clock_seconds(record.timestamp)
        if sample_time is not None and record_time is not None:
            difference = abs(record_time - sample_time)
            distance = min(difference, 86400 - difference)
            if nearest_distance is None or distance < nearest_distance:
                nearest_index = valid_index
                nearest_distance = distance
        valid_index += 1
    return nearest_index


def offline_map_assets_available():
    directory = Path(__file__).resolve().parents[1] / 'assets' / 'map'
    return all((directory / name).is_file() for name in OFFLINE_MAP_ASSETS)


def flight_route_availability(flight: Flight):
    if not flight.data_log:
        return RouteAvailability(
            False, 'No GPS data was imported for this flight.',
        )
    if not any(route_coordinates(record) is not None for record in flight.data_log):
        return RouteAvailability(
            False, 'No valid GPS coordinates are available in the offline map area.',
        )
    if not offline_map_assets_available():
        return RouteAvailability(
            False, 'Offline map resources are missing from the application installation.',
        )
    return RouteAvailability(
        True, 'Recorded GPS positions are available for viewing in Flight Route.',
    )
