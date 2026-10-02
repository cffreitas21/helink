from pathlib import Path
import tempfile

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QProgressDialog, QPushButton, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from helink.ui.dialogs import PdfPreviewDialog
from helink.services.flight_route_service import nearest_route_point_index
from helink.ui.tabs import AlertsTab, MapTab, OverviewTab, TelemetryTab


class FlightDetailsPage(QWidget):

    back_requested=Signal(); import_requested=Signal(str,str)

    def __init__(self, aircraft_controller, flight_controller, report_controller):
        super().__init__(); self.aircraft_controller=aircraft_controller; self.flight_controller=flight_controller; self.report_controller=report_controller; self.fid=None; root=QVBoxLayout(self); root.setContentsMargins(20,16,20,20)
        self._flight = None
        self._prepared = None
        self.tasks = None
        self._loaded_tabs = set()
        h=QHBoxLayout(); b=QPushButton('← Flight List'); b.setObjectName('secondary'); b.clicked.connect(self.back_requested); h.addWidget(b); self.title=QLabel(); self.title.setObjectName('title'); h.addWidget(self.title); h.addStretch(); ex=QPushButton('Export Report'); ex.clicked.connect(self.export_report); h.addWidget(ex); root.addLayout(h)
        self.info = QLabel()
        self.info.setObjectName('muted')
        root.addWidget(self.info)
        self.tabs=QTabWidget(); root.addWidget(self.tabs)
        self.overview=OverviewTab(); self.overview.import_requested.connect(lambda t:self.import_requested.emit(self.fid,t)); self.overview.event_requested.connect(self.open_event_summary); self.tabs.addTab(self.overview,'Overview')
        self.telemetry=TelemetryTab(); self.tabs.addTab(self.telemetry,'Telemetry')
        self.telemetry.route_requested.connect(self.open_route_at_telemetry)
        self.overview.parameter_requested.connect(self.open_parameter_chart)
        self.cas=AlertsTab('CAS'); self.tabs.addTab(self.cas,'CAS')
        self.exceed=AlertsTab('EXCEEDANCE'); self.tabs.addTab(self.exceed,'Exceedances')
        self.route=MapTab(); self.tabs.addTab(self.route,'Flight Route')
        self.overview.route_requested.connect(self.open_full_route)
        self.report_tab=QWidget(); rl=QVBoxLayout(self.report_tab); self.report=QTextEdit(); self.report.setReadOnly(True); gen=QPushButton('Generate Maintenance Report'); gen.clicked.connect(self.make_report); rl.addWidget(gen); rl.addWidget(self.report); self.tabs.addTab(self.report_tab,'Maintenance Report')
        self.tabs.currentChanged.connect(self._load_selected_tab)

    def load(self, fid, prepared=None):
        if fid == self.fid and prepared is not None and prepared is self._prepared:
            self._ensure_tab_loaded(self.tabs.currentWidget())
            return
        switching_flight = self.fid is not None and fid != self.fid
        self.cancel_pending()
        self._prepared = prepared
        if prepared is None:
            f = self.flight_controller.get(fid)
            aircraft = self.aircraft_controller.get(f.aircraft_id)
        else:
            f, aircraft = prepared.flight, prepared.aircraft
        self.fid = fid
        self._flight = f
        # Rendering can be reused only while the database snapshot is unchanged.
        self._loaded_tabs.clear()
        registration=aircraft.registration if aircraft else f.aircraft_id
        departure = f.departure_time or '\N{EM DASH}'
        arrival = f.arrival_time or '\N{EM DASH}'
        duration = f.duration or '\N{EM DASH}'
        self.title.setText(
            f'{registration}  \N{MIDDLE DOT}  {f.flight_date}  '
            f'\N{MIDDLE DOT}  {departure} \N{RIGHTWARDS ARROW} {arrival}  '
            f'\N{MIDDLE DOT}  {duration}'
        )
        self.info.setText(
            f'{aircraft.model} \N{MIDDLE DOT} SN {aircraft.serial_number}'
            if aircraft else ''
        )
        self._ensure_tab_loaded(self.overview)
        if switching_flight:
            self.tabs.setCurrentWidget(self.overview)
        else:
            self._ensure_tab_loaded(self.tabs.currentWidget())

    def cancel_pending(self):
        for tab in (self.cas, self.exceed):
            if tab.cancel_pending():
                self._loaded_tabs.discard(tab)

    def _load_selected_tab(self, index):
        self._ensure_tab_loaded(self.tabs.widget(index))

    def _ensure_tab_loaded(self, tab):
        if self._flight is None or tab is None or tab in self._loaded_tabs:
            return
        if tab in (self.cas, self.exceed):
            tab.tasks = self.tasks
        if tab is self.report_tab:
            self._set_report_text(
                self._flight.predictive_report
                or 'No maintenance report has been generated for this flight yet.'
            )
        elif tab is self.overview and self._prepared is not None:
            tab.load(
                self._flight, statistics=self._prepared.statistics,
                events=self._prepared.events, route=self._prepared.route,
            )
        else:
            tab.load(self._flight)
        self._loaded_tabs.add(tab)

    def _set_report_text(self, text):
        self.report.setPlainText(text)
        # Export can update the report before its tab has ever been opened.
        # Do not replace that new text with the opening snapshot afterwards.
        self._loaded_tabs.add(self.report_tab)

    def open_parameter_chart(self, parameter_key):
        self._ensure_tab_loaded(self.telemetry)
        if self.telemetry.focus_parameter(parameter_key):
            self.tabs.setCurrentWidget(self.telemetry)

    def open_route_at_telemetry(self, sample):
        if self._flight is None:
            return
        point_index = nearest_route_point_index(self._flight, sample)
        if point_index is None:
            QMessageBox.information(
                self, 'Route position unavailable',
                'No GPS position with a usable timestamp matches this telemetry point.',
            )
            return
        self._ensure_tab_loaded(self.route)
        self.tabs.setCurrentWidget(self.route)
        self.route.focus_point(point_index)

    def open_full_route(self):
        self._ensure_tab_loaded(self.route)
        self.tabs.setCurrentWidget(self.route)
        self.route.show_full_route()

    def open_event_summary(self, event_key):
        if event_key == 'exceedances':
            self._ensure_tab_loaded(self.exceed)
            self.exceed.set_filters()
            self.tabs.setCurrentWidget(self.exceed)
            return
        level = {
            'warnings': 'WARNING',
            'cautions': 'CAUTION',
            'miscmp': 'All',
        }.get(event_key, 'All')
        alert_name = 'MISCMP-P' if event_key == 'miscmp' else 'All Alerts'
        self._ensure_tab_loaded(self.cas)
        self.cas.set_filters(level, alert_name)
        self.tabs.setCurrentWidget(self.cas)

    @staticmethod
    def _report_filename(flight):
        session = (flight.departure_time or flight.id[:8]).replace(':', '')
        return f'HELINK_Maintenance_Report_{flight.flight_date}_{session}.pdf'

    def make_report(self):
        if self.tasks is not None:
            handle = tempfile.NamedTemporaryFile(
                prefix='helink_report_', suffix='.pdf', delete=False,
            )
            path = Path(handle.name)
            handle.close()
            return self._export_background(path, preview=True)
        flight = self.flight_controller.get(self.fid)
        suggested = self._report_filename(flight)
        temporary_path = None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            handle = tempfile.NamedTemporaryFile(
                prefix='helink_report_', suffix='.pdf', delete=False
            )
            temporary_path = Path(handle.name)
            handle.close()
            self.report_controller.export_pdf(self.fid, temporary_path)
            self._set_report_text(
                self.flight_controller.get(self.fid).predictive_report
            )
        except Exception as error:
            QMessageBox.critical(self, 'Report error', str(error))
            return
        finally:
            QApplication.restoreOverrideCursor()

        preview = PdfPreviewDialog(temporary_path, suggested, self)
        try:
            preview.exec()
        finally:
            preview.release()
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    def export_report(self):
        flight = self._flight if self.tasks is not None else self.flight_controller.get(self.fid)
        suggested = self._report_filename(flight)
        path, _ = QFileDialog.getSaveFileName(
            self,
            'Export Maintenance Report',
            suggested,
            'PDF Document (*.pdf)',
        )
        if not path:
            return
        if self.tasks is not None:
            return self._export_background(path)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            destination = self.report_controller.export_pdf(self.fid, path)
            self._set_report_text(
                self.flight_controller.get(self.fid).predictive_report
            )
            QMessageBox.information(
                self,
                'Export complete',
                f'PDF report exported successfully to:\n{destination}',
            )
        except Exception as error:
            QMessageBox.critical(self, 'Export error', str(error))
        finally:
            QApplication.restoreOverrideCursor()

    def _export_background(self, destination, *, preview=False):
        flight_id = self.fid
        suggested = self._report_filename(self._flight)
        progress = QProgressDialog('Preparing maintenance report...', '', 0, 0, self)
        progress.setCancelButton(None)
        progress.setWindowTitle('Maintenance Report')
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.show()

        def cleanup():
            if preview:
                try:
                    Path(destination).unlink(missing_ok=True)
                except OSError:
                    pass

        def received(result):
            progress.close()
            path, text = result
            if getattr(self.window(), '_closing', False):
                cleanup()
                return
            if self.fid == flight_id:
                self._set_report_text(text)
            if preview:
                dialog = PdfPreviewDialog(path, suggested, self)
                try:
                    dialog.exec()
                finally:
                    dialog.release()
                    cleanup()
            else:
                QMessageBox.information(
                    self, 'Export complete', f'PDF report exported successfully to:\n{path}',
                )

        def failed(error):
            progress.close()
            cleanup()
            if not getattr(self.window(), '_closing', False):
                QMessageBox.critical(self, 'Report error', str(error))

        task = self.report_controller.request_export(
            flight_id, destination, received, failed,
        )
        task.cancelled.connect(cleanup)
        task.finished.connect(progress.close)
        task.finished.connect(progress.deleteLater)
