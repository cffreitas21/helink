"""Prepare a read-only flight snapshot without involving Qt widgets."""

from dataclasses import dataclass

from helink.models.aircraft import Aircraft
from helink.models.flight.flight import Flight
from helink.services.flight_overview_summary import (
    EventSummary, ParameterStatistics, flight_parameter_statistics, important_flight_events,
)
from helink.services.flight_route_service import RouteAvailability, flight_route_availability


@dataclass(frozen=True, slots=True)
class FlightDetailsData:
    """Read-only data prepared for all tabs of a flight details page."""
    flight: Flight
    aircraft: Aircraft | None
    statistics: dict[str, ParameterStatistics]
    events: dict[str, EventSummary]
    route: RouteAvailability


def prepare_flight_details(flight, aircraft):
    """Combine a flight with aircraft, summary, events, and route status."""
    if flight is None:
        raise ValueError('The selected flight is no longer available.')
    return FlightDetailsData(
        flight, aircraft, flight_parameter_statistics(flight),
        important_flight_events(flight), flight_route_availability(flight),
    )
