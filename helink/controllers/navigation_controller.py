"""Navigation state and the main-window display contract."""

from __future__ import annotations

from typing import Protocol


class MainView(Protocol):
    """Navigation operations required from the main window."""

    def display_fleet(self):
        """Display the fleet page."""
        ...

    def display_flight_list(self, aircraft_id):
        """Display the flights belonging to one aircraft."""
        ...

    def display_flight(self, flight_id):
        """Display one flight's details."""
        ...

    def display_fleet_analysis(self, aircraft_id=None, *, allow_comparison=True):
        """Display fleet or single-aircraft trend analysis."""
        ...


class NavigationController:
    """Owns screen navigation state only."""

    def __init__(self):
        """Initialize the current aircraft and navigation origin."""
        self.view: MainView | None = None
        self.current_aircraft = None
        self._analysis_from_flights = False

    def attach_view(self, view: MainView):
        """Attach the window that performs screen changes."""
        self.view = view

    def show_fleet(self):
        """Return to the fleet and clear aircraft-specific navigation state."""
        self.current_aircraft = None
        self._analysis_from_flights = False
        if self.view:
            self.view.display_fleet()

    def show_aircraft(self, aircraft_id):
        """Open the flight list for the selected aircraft."""
        self.current_aircraft = aircraft_id
        self._analysis_from_flights = False
        if self.view:
            self.view.display_flight_list(aircraft_id)

    def show_flight(self, flight_id):
        """Open the details page for the selected flight."""
        if self.view:
            self.view.display_flight(flight_id)

    def show_fleet_analysis(self, aircraft_id=None):
        """Open comparison-capable fleet analysis."""
        self.current_aircraft = aircraft_id or None
        self._analysis_from_flights = False
        if self.view:
            self.view.display_fleet_analysis(aircraft_id or None)

    def show_aircraft_analysis(self, aircraft_id):
        """Open analysis restricted to one aircraft."""
        if not aircraft_id:
            return
        self.current_aircraft = aircraft_id
        self._analysis_from_flights = True
        if self.view:
            self.view.display_fleet_analysis(aircraft_id, allow_comparison=False)

    def back_from_analysis(self):
        """Return to the fleet or flight list that opened analysis."""
        if self._analysis_from_flights:
            self.back_to_aircraft()
        else:
            self.show_fleet()

    def back_to_aircraft(self):
        """Return to the selected aircraft, or the fleet if none is selected."""
        if self.current_aircraft:
            self.show_aircraft(self.current_aircraft)
        else:
            self.show_fleet()
