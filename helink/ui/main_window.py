from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import *

from helink.ui.dialogs import (
    AboutDialog, AddAircraftDialog, ImportSummaryDialog,
)
from helink.ui.pages import DashboardPage, FlightListPage, FlightDetailsPage, FleetAnalysisPage
from helink.ui.widgets import Sidebar
from helink.ui.widgets.imported_files_button import FILE_TYPE_LABELS
from helink.ui.widgets.loading_overlay import LoadingOverlay


class MainWindow(QMainWindow):
    def __init__(
        self,
        flight_controller,
        import_controller,
        aircraft_controller,
        report_controller,
        database_controller,
        navigation_controller,
        tasks=None,
    ):
        super().__init__()
        self.aircraft_controller = aircraft_controller
        self.flight_controller = flight_controller
        self.import_controller = import_controller
        self.report_controller = report_controller
        self.database_controller = database_controller
        self.navigation_controller = navigation_controller
        self.navigation_controller.attach_view(self)
        self.tasks = tasks
        self._navigation_token = 0
        self._navigation_task = None
        self._closing = False
        if tasks is not None:
            tasks.setParent(self)
            tasks.idle.connect(self._finish_close)

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
        self.loading_overlay = LoadingOverlay(self.stack)
        root.addWidget(body, 1)

        self.dashboard = DashboardPage(self.aircraft_controller)
        self.fleet_analysis = FleetAnalysisPage(self.aircraft_controller)
        self.flight_list = FlightListPage(
            self.aircraft_controller, self.flight_controller
        )
        self.flight_details = FlightDetailsPage(
            self.aircraft_controller,
            self.flight_controller,
            self.report_controller,
        )
        self.flight_details.tasks = tasks
        for page in (self.flight_list, self.fleet_analysis):
            page.loading_changed.connect(
                lambda busy, message, current=page: self._page_loading(current, busy, message)
            )
        for page in (self.dashboard, self.fleet_analysis, self.flight_list, self.flight_details):
            self.stack.addWidget(page)

        self.dashboard.aircraft_selected.connect(
            self.navigation_controller.show_aircraft
        )
        self.dashboard.analysis_requested.connect(
            self.navigation_controller.show_fleet_analysis
        )
        self.fleet_analysis.back_requested.connect(
            self.navigation_controller.back_from_analysis
        )
        self.fleet_analysis.flights_requested.connect(
            self.navigation_controller.show_aircraft
        )
        self.dashboard.add_requested.connect(self.add_aircraft)
        self.flight_list.back_requested.connect(
            self.navigation_controller.show_dashboard
        )
        self.flight_list.flight_selected.connect(
            self.navigation_controller.show_flight
        )
        self.flight_list.analysis_requested.connect(
            self.navigation_controller.show_aircraft_analysis
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
        if self.tasks is not None:
            return self._request_page(
                self.dashboard, self.aircraft_controller, 'dashboard_data', (),
                self.dashboard.refresh, 'Loading fleet...',
            )
        self.dashboard.refresh()
        self.stack.setCurrentWidget(self.dashboard)

    def display_flight_list(self, aircraft_id):
        if self.tasks is not None:
            start, end = (
                self.flight_list.date_filter.date_range
                if aircraft_id == self.flight_list.aid else (None, None)
            )
            return self._request_page(
                self.flight_list, self.flight_controller, 'list_page_data', (aircraft_id,),
                lambda data: self.flight_list.load(aircraft_id, prepared=data),
                'Loading flights...', start_date=start, end_date=end,
                descending=self.flight_list.sort_order.currentData() == 'descending',
            )
        self.flight_list.load(aircraft_id)
        self.stack.setCurrentWidget(self.flight_list)

    def display_flight(self, flight_id):
        if self.tasks is not None:
            return self._request_page(
                self.flight_details, self.flight_controller, 'details_data', (flight_id,),
                lambda data: self.flight_details.load(flight_id, prepared=data),
                'Loading flight...',
            )
        self.flight_details.load(flight_id)
        self.stack.setCurrentWidget(self.flight_details)

    def display_fleet_analysis(self, aircraft_id=None, *, allow_comparison=True):
        if self.tasks is not None:
            return self._request_page(
                self.fleet_analysis, self.aircraft_controller, 'analysis_data',
                (
                    aircraft_id, allow_comparison,
                    self.fleet_analysis.parameter.currentData(),
                    self.fleet_analysis.minimum_minutes.value(),
                ),
                lambda data: self.fleet_analysis.load(
                    aircraft_id, allow_comparison=allow_comparison, prepared=data,
                ),
                'Loading parameter trends...',
            )
        self.fleet_analysis.load(aircraft_id, allow_comparison=allow_comparison)
        self.stack.setCurrentWidget(self.fleet_analysis)

    def _request_page(self, page, controller, method, args, apply, message, **kwargs):
        previous = self.stack.currentWidget()
        if previous is not None and hasattr(previous, 'cancel_pending'):
            previous.cancel_pending()
        self._navigation_token += 1
        token = self._navigation_token
        if self._navigation_task is not None:
            self._navigation_task.cancel()
        self.stack.setCurrentWidget(page)
        self.loading_overlay.show_message(message)

        def current():
            return token == self._navigation_token and not self._closing

        def received(data):
            if not current():
                return
            try:
                apply(data)
            except Exception as error:
                failed(error)
                return
            if not getattr(page, '_render_pending', False):
                self.loading_overlay.hide()

        def failed(error):
            if current():
                self.loading_overlay.hide()
                QMessageBox.warning(self, 'Unable to load data', str(error))

        self._navigation_task = controller.request(
            method, *args, on_result=received, on_error=failed, **kwargs,
        )

    def _page_loading(self, page, busy, message):
        if self.stack.currentWidget() is page and not self._closing:
            if busy:
                self.loading_overlay.show_message(message)
            else:
                self.loading_overlay.hide()

    def _finish_close(self):
        if self._closing:
            self.close()

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
        if self.tasks is None:
            QApplication.processEvents()

        def update(value, message):
            dialog.setLabelText(message)
            dialog.setValue(max(0, min(100, round(value))))
            if self.tasks is None:
                QApplication.processEvents()
                if dialog.wasCanceled():
                    raise InterruptedError('Import cancelled by the user.')

        return dialog, update

    def _run_import(self, method, args, on_success):
        dialog, progress = self._import_progress()

        def received(result):
            dialog.close()
            if self._closing:
                return
            if result.file_count:
                on_success()
            ImportSummaryDialog(result, self).exec()

        def failed(error):
            dialog.close()
            if not self._closing:
                QMessageBox.critical(
                    self, 'Import error', f'The files could not be processed:\n{error}',
                )

        handle = self.import_controller.request(
            method, *args, on_result=received, on_error=failed, on_progress=progress,
        )
        dialog.canceled.connect(handle.cancel)
        handle.cancelled.connect(
            lambda: self.statusBar().showMessage('Import cancelled.', 4000)
        )
        handle.finished.connect(dialog.close)
        handle.finished.connect(dialog.deleteLater)

    def import_for_aircraft(self, aircraft_id):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            'Select Flight Data Files',
            '',
            'Flight Data (*.zip *.csv);;ZIP Archives (*.zip);;CSV Files (*.csv)',
        )
        if not files:
            return

        if self.tasks is not None:
            return self._run_import(
                'import_for_aircraft', (files, aircraft_id),
                lambda: self.navigation_controller.show_aircraft(aircraft_id),
            )
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

        if self.tasks is not None:
            return self._run_import(
                'add_to_flight', (files, flight_id, file_type),
                lambda: self.navigation_controller.show_flight(flight_id),
            )
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
        if self.tasks is not None:
            dialog = self._transfer_progress('Exporting database...')

            def received(path):
                dialog.close()
                if not self._closing:
                    QMessageBox.information(
                        self, 'Export complete', f'Database exported successfully to:\n{path}',
                    )

            def failed(error):
                dialog.close()
                if not self._closing:
                    QMessageBox.critical(self, 'Export error', str(error))

            handle = self.database_controller.request_export(destination, received, failed)
            handle.finished.connect(dialog.close)
            handle.finished.connect(dialog.deleteLater)
            return
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
        if self.tasks is not None and self.tasks.busy:
            QMessageBox.information(
                self, 'Operation in progress',
                'Wait for the current operation to finish before replacing the database.',
            )
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, 'Import Database', '', 'SQLite Database (*.db);;All Files (*)'
        )
        if not filename:
            return
        source = Path(filename)
        if self.tasks is not None:
            return self._import_database_background(source)
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

    def _transfer_progress(self, message):
        dialog = QProgressDialog(message, '', 0, 0, self)
        dialog.setWindowTitle('Database Transfer')
        dialog.setCancelButton(None)
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.show()
        return dialog

    def _import_database_background(self, source):
        dialog = self._transfer_progress('Checking database...')

        def failed(error):
            dialog.close()
            if not self._closing:
                QMessageBox.critical(self, 'Import error', str(error))

        def validated(_result):
            dialog.close()
            if self._closing:
                return
            answer = QMessageBox.question(
                self, 'Import Database',
                'Importing this database will replace the current aircraft and flight data.\n\n'
                'A backup of the current database will be created automatically. Continue?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            importing = self._transfer_progress('Importing database...')

            def received(backup):
                importing.close()
                if not self._closing:
                    self.navigation_controller.show_dashboard()
                    QMessageBox.information(
                        self, 'Import complete',
                        f'Database imported successfully.\n\nPrevious database backup:\n{backup}',
                    )

            def import_failed(error):
                importing.close()
                if not self._closing:
                    QMessageBox.critical(self, 'Import error', str(error))

            task = self.database_controller.request_import(source, received, import_failed)
            task.finished.connect(importing.close)
            task.finished.connect(importing.deleteLater)

        task = self.database_controller.request_validate(source, validated, failed)
        task.finished.connect(dialog.close)
        task.finished.connect(dialog.deleteLater)

    def closeEvent(self, event):
        self._closing = True
        self.flight_list.cancel_pending()
        self.fleet_analysis.cancel_pending()
        self.flight_details.cancel_pending()
        if self.tasks is not None and self.tasks.busy:
            self.tasks.cancel_all()
            self.statusBar().showMessage('Finishing pending operations...')
            event.ignore()
            return
        self.database_controller.close()
        super().closeEvent(event)
