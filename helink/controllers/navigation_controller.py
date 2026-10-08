from __future__ import annotations

from typing import Protocol


class MainView(Protocol):
    def display_fleet(self): ...
    def display_flight_list(self, aircraft_id): ...
    def display_flight(self, flight_id): ...
    def display_fleet_analysis(self, aircraft_id=None, *, allow_comparison=True): ...


class NavigationController:
    """Owns screen navigation state only."""

    def __init__(self):
        self.view: MainView | None = None
        self.current_aircraft = None
        self._analysis_from_flights = False

    def attach_view(self, view: MainView):
        self.view = view

    def show_fleet(self):
        self.current_aircraft = None
        self._analysis_from_flights = False
        if self.view:
            self.view.display_fleet()

    def show_aircraft(self, aircraft_id):
        self.current_aircraft = aircraft_id
        self._analysis_from_flights = False
        if self.view:
            self.view.display_flight_list(aircraft_id)

    def show_flight(self, flight_id):
        if self.view:
            self.view.display_flight(flight_id)

    def show_fleet_analysis(self, aircraft_id=None):
        self.current_aircraft = aircraft_id or None
        self._analysis_from_flights = False
        if self.view:
            self.view.display_fleet_analysis(aircraft_id or None)

    def show_aircraft_analysis(self, aircraft_id):
        if not aircraft_id:
            return
        self.current_aircraft = aircraft_id
        self._analysis_from_flights = True
        if self.view:
            self.view.display_fleet_analysis(aircraft_id, allow_comparison=False)

    def back_from_analysis(self):
        if self._analysis_from_flights:
            self.back_to_aircraft()
        else:
            self.show_fleet()

    def back_to_aircraft(self):
        if self.current_aircraft:
            self.show_aircraft(self.current_aircraft)
        else:
            self.show_fleet()
