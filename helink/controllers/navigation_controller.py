from __future__ import annotations

from typing import Protocol


class MainView(Protocol):
    def display_dashboard(self): ...
    def display_flight_list(self, aircraft_id): ...
    def display_flight(self, flight_id): ...


class NavigationController:
    """Owns screen navigation state only."""

    def __init__(self):
        self.view: MainView | None = None
        self.current_aircraft = None

    def attach_view(self, view: MainView):
        self.view = view

    def show_dashboard(self):
        self.current_aircraft = None
        if self.view:
            self.view.display_dashboard()

    def show_aircraft(self, aircraft_id):
        self.current_aircraft = aircraft_id
        if self.view:
            self.view.display_flight_list(aircraft_id)

    def show_flight(self, flight_id):
        if self.view:
            self.view.display_flight(flight_id)

    def back_to_aircraft(self):
        if self.current_aircraft:
            self.show_aircraft(self.current_aircraft)
        else:
            self.show_dashboard()
