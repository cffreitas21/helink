"""Shared validation for recorded positions and offline route availability."""

from dataclasses import dataclass
from pathlib import Path

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
