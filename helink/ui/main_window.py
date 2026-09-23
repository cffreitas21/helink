from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import *

from helink.ui.dialogs import (
    AboutDialog, AddAircraftDialog, ImportSummaryDialog,
)
from helink.ui.pages import DashboardPage, FlightListPage, FlightDetailsPage
from helink.ui.widgets import Sidebar
from helink.ui.widgets.imported_files_button import FILE_TYPE_LABELS


class MainWindow(QMainWindow):
    def __init__(
        self,
        flight_controller,
        import_controller,
        aircraft_controller,
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
        self.flight_list = FlightListPage(
            self.aircraft_controller, self.flight_controller
        )
        self.flight_details = FlightDetailsPage(
            self.aircraft_controller,
            self.flight_controller,
            self.report_controller,
        )
        for page in (self.dashboard, self.flight_list, self.flight_details):
            self.stack.addWidget(page)

        self.dashboard.aircraft_selected.connect(
            self.navigation_controller.show_aircraft
        )
        self.dashboard.add_requested.connect(self.add_aircraft)
        self.flight_list.back_requested.connect(
            self.navigation_controller.show_dashboard
        )
        self.flight_list.flight_selected.connect(
            self.navigation_controller.show_flight
        )
        self.flight_list.import_requested.connect(self.import_for_aircraft)
        self.flight_details.back_requested.connect(
            self.navigation_controller.back_to_aircraft
        )
        self.flight_details.import_requested.connect(self.import_for_flight)
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

    def display_flight_list(self, aircraft_id):
        self.flight_list.load(aircraft_id)
        self.stack.setCurrentWidget(self.flight_list)

    def display_flight(self, flight_id):
        self.flight_details.load(flight_id)
        self.stack.setCurrentWidget(self.flight_details)

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

    def _import_progress(self):
        dialog = QProgressDialog(
            'Preparing flight data import...', 'Cancel Import', 0, 100, self
        )
        dialog.setWindowTitle('Importing Flight Data')
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setMinimumWidth(440)
        dialog.setValue(0)
        dialog.show()
        QApplication.processEvents()

        def update(value, message):
            dialog.setLabelText(message)
            dialog.setValue(max(0, min(100, round(value))))
            QApplication.processEvents()
            if dialog.wasCanceled():
                raise InterruptedError('Import cancelled by the user.')

        return dialog, update

    def import_for_aircraft(self, aircraft_id):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            'Select Flight Data Files',
            '',
            'Flight Data (*.zip *.csv);;ZIP Archives (*.zip);;CSV Files (*.csv)',
        )
        if not files:
            return

        dialog, progress = self._import_progress()
        result = None
        try:
            result = self.import_controller.import_for_aircraft(
                files, aircraft_id, progress
            )
            if result.file_count:
                self.navigation_controller.show_aircraft(aircraft_id)
        except InterruptedError:
            self.statusBar().showMessage('Import cancelled.', 4000)
        except Exception as error:
            QMessageBox.critical(
                self,
                'Import error',
                f'The files could not be processed:\n{error}',
            )
        finally:
            dialog.close()
            dialog.deleteLater()
        if result is not None:
            ImportSummaryDialog(result, self).exec()

    def import_for_flight(self, flight_id, file_type):
        display_type = FILE_TYPE_LABELS.get(file_type, 'Flight Data')
        files, _ = QFileDialog.getOpenFileNames(
            self,
            f'Select {display_type} Files',
            '',
            'CSV (*.csv);;ZIP (*.zip)',
        )
        if not files:
            return

        dialog, progress = self._import_progress()
        result = None
        try:
            result = self.import_controller.add_to_flight(
                files, flight_id, file_type, progress
            )
            if result.file_count:
                self.navigation_controller.show_flight(flight_id)
        except InterruptedError:
            self.statusBar().showMessage('Import cancelled.', 4000)
        except Exception as error:
            QMessageBox.critical(
                self, 'Import error',
                f'The selected files could not be processed:\n{error}',
            )
        finally:
            dialog.close()
            dialog.deleteLater()
        if result is not None:
            ImportSummaryDialog(result, self).exec()

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
