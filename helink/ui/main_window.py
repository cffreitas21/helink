from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import *

from helink.ui.dialogs import AboutDialog, AddAircraftDialog
from helink.ui.pages import AircraftPage, DashboardPage, FlightPage
from helink.ui.widgets import Sidebar


class MainWindow(QMainWindow):
    def __init__(
        self,
        aircraft_controller,
        flight_controller,
        import_controller,
        report_controller,
        database_controller,
        navigation_controller,
    ):
        super().__init__()
        self.aircraft_controller = aircraft_controller
        self.flight_controller = flight_controller
        self.import_controller = import_controller
        self.report_controller = report_controller
        self.database_controller = database_controller
        self.navigation_controller = navigation_controller
        self.navigation_controller.attach_view(self)

        self.setWindowTitle('HELINK - Helicopter Flight Analysis & Maintenance')
        self.resize(1450, 900)
        self.setup_menu_bar()

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.dashboard_requested.connect(
            self.navigation_controller.show_dashboard
        )
        self.sidebar.import_requested.connect(self.import_global)
        root.addWidget(self.sidebar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        body_layout.addWidget(self.stack)
        root.addWidget(body, 1)

        self.dashboard = DashboardPage(self.aircraft_controller)
        self.aircraft = AircraftPage(
            self.aircraft_controller, self.flight_controller
        )
        self.flight = FlightPage(
            self.flight_controller, self.report_controller
        )
        for page in (self.dashboard, self.aircraft, self.flight):
            self.stack.addWidget(page)

        self.dashboard.aircraft_selected.connect(
            self.navigation_controller.show_aircraft
        )
        self.dashboard.add_requested.connect(self.add_aircraft)
        self.aircraft.back_requested.connect(
            self.navigation_controller.show_dashboard
        )
        self.aircraft.flight_selected.connect(
            self.navigation_controller.show_flight
        )
        self.aircraft.import_requested.connect(self.import_for_aircraft)
        self.flight.back_requested.connect(
            self.navigation_controller.back_to_aircraft
        )
        self.flight.import_requested.connect(self.import_for_flight)
        self.navigation_controller.show_dashboard()

    def setup_menu_bar(self):
        self.file_menu = self.menuBar().addMenu('File')
        self.settings_action = self.file_menu.addAction('Settings')
        self.file_menu.addSeparator()
        import_action = self.file_menu.addAction('Import Database')
        import_action.triggered.connect(self.import_database)
        export_action = self.file_menu.addAction('Export Database')
        export_action.triggered.connect(self.export_database)
        self.file_menu.addSeparator()
        exit_action = self.file_menu.addAction('Exit')
        exit_action.triggered.connect(self.close)

        about_action = self.menuBar().addAction('About')
        about_action.triggered.connect(self.show_about)

    def show_about(self):
        AboutDialog(self).exec()

    def display_dashboard(self):
        self.dashboard.refresh()
        self.stack.setCurrentWidget(self.dashboard)

    def display_aircraft(self, aircraft_id):
        self.aircraft.load(aircraft_id)
        self.stack.setCurrentWidget(self.aircraft)

    def display_flight(self, flight_id):
        self.flight.load(flight_id)
        self.stack.setCurrentWidget(self.flight)

    def add_aircraft(self):
        dialog = AddAircraftDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            aircraft_id = self.aircraft_controller.add(
                dialog.prefix.text(),
                dialog.model.text(),
                dialog.serial_number.text() or 'Unknown',
            )
            self.navigation_controller.show_dashboard()
        except Exception as error:
            QMessageBox.critical(self, 'Error', str(error))

    def import_global(self):
        aircraft = self.aircraft_controller.list_aircraft()
        if not aircraft:
            QMessageBox.information(
                self, 'No aircraft', 'Register an aircraft first.'
            )
            return
        registrations = [item.registration for item in aircraft]
        selected, accepted = QInputDialog.getItem(
            self,
            'Select aircraft',
            'Destination aircraft:',
            registrations,
            0,
            False,
        )
        if not accepted:
            return
        selected_aircraft = next(
            item for item in aircraft if item.registration == selected
        )
        self.import_for_aircraft(selected_aircraft.id)

    def import_for_aircraft(self, aircraft_id):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            'Load Garmin G1000H Data',
            '',
            'Garmin (*.zip *.csv);;ZIP (*.zip);;CSV (*.csv)',
        )
        if not files:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            count = self.import_controller.import_for_aircraft(files, aircraft_id)
            QMessageBox.information(
                self,
                'Import complete',
                f'{count} flight(s) imported into the SQLite database.',
            )
            self.navigation_controller.show_aircraft(aircraft_id)
        except Exception as error:
            QMessageBox.critical(
                self, 'Import error', f'The files could not be processed:\n{error}'
            )
        finally:
            QApplication.restoreOverrideCursor()

    def import_for_flight(self, flight_id, file_type):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            f'Add {file_type} to flight',
            '',
            'CSV (*.csv);;ZIP (*.zip)',
        )
        if not files:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.import_controller.add_to_flight(files, flight_id, file_type)
            self.navigation_controller.show_flight(flight_id)
            QMessageBox.information(
                self, 'Import complete', f'{file_type} added to the flight.'
            )
        except Exception as error:
            QMessageBox.critical(self, 'Import error', str(error))
        finally:
            QApplication.restoreOverrideCursor()

    def export_database(self):
        suggested = str(Path.home() / 'helink-export.db')
        filename, _ = QFileDialog.getSaveFileName(
            self, 'Export Database', suggested, 'SQLite Database (*.db)'
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.lower() != '.db':
            destination = destination.with_suffix('.db')
        try:
            self.database_controller.export(destination)
            QMessageBox.information(
                self,
                'Export complete',
                f'Database exported successfully to:\n{destination}',
            )
        except Exception as error:
            QMessageBox.critical(self, 'Export error', str(error))

    def import_database(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, 'Import Database', '', 'SQLite Database (*.db);;All Files (*)'
        )
        if not filename:
            return
        source = Path(filename)
        try:
            self.database_controller.validate(source)
        except Exception as error:
            QMessageBox.critical(self, 'Invalid database', str(error))
            return
        answer = QMessageBox.question(
            self,
            'Import Database',
            'Importing this database will replace the current aircraft and flight data.\n\n'
            'A backup of the current database will be created automatically. Continue?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            backup = self.database_controller.import_(source)
            self.navigation_controller.show_dashboard()
            QMessageBox.information(
                self,
                'Import complete',
                f'Database imported successfully.\n\n'
                f'Previous database backup:\n{backup}',
            )
        except Exception as error:
            QMessageBox.critical(self, 'Import error', str(error))
        finally:
            QApplication.restoreOverrideCursor()

    def closeEvent(self, event):
        self.database_controller.close()
        super().closeEvent(event)
