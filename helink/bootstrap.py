from __future__ import annotations

from pathlib import Path

from helink.controllers import (
    AircraftController,
    DatabaseController,
    FlightController,
    ImportController,
    NavigationController,
    ReportController,
)
from helink.repositories import AircraftRepository, DatabaseManager, FlightRepository
from helink.services.database_transfer_service import DatabaseTransferService
from helink.services.flight_import_service import FlightImportService
from helink.services.report_service import ReportService
from helink.ui.main_window import MainWindow
from helink.controllers.task_controller import TaskController


def build_main_window(database_path: Path | None = None) -> MainWindow:
    """Create the object graph and inject each dependency into the UI."""

    resolved_path = database_path or Path.home() / '.helink' / 'helink.db'

    database = DatabaseManager(resolved_path)

    aircraft_repository = AircraftRepository(database)
    flight_repository = FlightRepository(database)
    tasks = TaskController(database)

    return MainWindow(
        aircraft_controller=AircraftController(aircraft_repository, tasks),
        flight_controller=FlightController(flight_repository, tasks),
        import_controller=ImportController(
            FlightImportService(flight_repository), tasks,
        ),
        report_controller=ReportController(ReportService(flight_repository), tasks),
        database_controller=DatabaseController(
            DatabaseTransferService(database), database, tasks,
        ),
        navigation_controller=NavigationController(),
        tasks=tasks,
    )
