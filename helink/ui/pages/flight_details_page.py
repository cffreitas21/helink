from pathlib import Path
import tempfile

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QProgressDialog, QPushButton, QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from helink.ui.dialogs import PdfPreviewDialog
from helink.services.flight_route_service import nearest_route_point_index
from helink.services.flight_report_builder import flight_report_html
from helink.ui.tabs import (
    EventsTab, FlightRouteTab, OverviewTab, PreventiveMaintenanceTab,
    TelemetryTab,
)


class FlightDetailsPage(QWidget):

    back_requested=Signal(); import_requested=Signal(str,str)

    def __init__(self, aircraft_controller, flight_controller, report_controller):
        super().__init__(); self.aircraft_controller=aircraft_controller; self.flight_controller=flight_controller; self.report_controller=report_controller; self.fid=None; root=QVBoxLayout(self); root.setContentsMargins(20,16,20,20)
        self._flight = None
        self._aircraft = None
        self._prepared = None
        self.tasks = None
        self._loaded_tabs = set()
        self._route_follows_telemetry = False
        h=QHBoxLayout(); b=QPushButton('← Flight List'); b.setObjectName('secondary'); b.clicked.connect(self.back_requested); h.addWidget(b); self.title=QLabel(); self.title.setObjectName('title'); h.addWidget(self.title); h.addStretch(); root.addLayout(h)
        self.info = QLabel()
        self.info.setObjectName('muted')
        root.addWidget(self.info)
        self.tabs=QTabWidget(); root.addWidget(self.tabs)
        self.overview=OverviewTab(); self.overview.import_requested.connect(lambda t:self.import_requested.emit(self.fid,t)); self.overview.event_requested.connect(self.open_event_summary); self.tabs.addTab(self.overview,'Overview')
        self.telemetry=TelemetryTab(); self.tabs.addTab(self.telemetry,'Telemetry')
        self.telemetry.route_requested.connect(self.open_route_at_telemetry)
        self.telemetry.slider.valueChanged.connect(self._telemetry_position_changed)
        self.overview.parameter_requested.connect(self.open_parameter_chart)
        self.preventive=PreventiveMaintenanceTab()
        self.tabs.addTab(self.preventive, 'Preventive Maintenance')
        self.preventive.point_requested.connect(self.open_preventive_point)
        self.cas=EventsTab('CAS'); self.tabs.addTab(self.cas,'CAS')
        self.exceed=EventsTab('EXCEEDANCE'); self.tabs.addTab(self.exceed,'Exceedances')
        self.route=FlightRouteTab(); self.tabs.addTab(self.route,'Flight Route')
        self.overview.route_requested.connect(self.open_full_route)
        self.report_tab = QWidget()
        report_layout = QVBoxLayout(self.report_tab)
        report_layout.setContentsMargins(14, 14, 14, 14)
        report_layout.setSpacing(12)
        report_toolbar = QFrame()
        report_toolbar.setObjectName('flightReportToolbar')
        toolbar_layout = QHBoxLayout(report_toolbar)
        toolbar_layout.setContentsMargins(16, 13, 16, 13)
        toolbar_layout.setSpacing(16)
        introduction = QVBoxLayout()
        introduction.setSpacing(3)
        report_title = QLabel('Flight Report')
        report_title.setObjectName('flightReportTitle')
        report_hint = QLabel(
            'Review the report below. Open the PDF preview to save a copy.'
        )
        report_hint.setObjectName('flightReportHint')
        report_hint.setWordWrap(True)
        introduction.addWidget(report_title)
        introduction.addWidget(report_hint)
        toolbar_layout.addLayout(introduction, 1)
        preview_button = QPushButton('Preview PDF')
        preview_button.setObjectName('flightReportPreview')
        preview_button.setToolTip('Open a PDF preview with the option to save it')
        preview_button.clicked.connect(self.make_report)
        toolbar_layout.addWidget(preview_button, 0, Qt.AlignVCenter)
        self.report = QTextBrowser()
        self.report.setObjectName('flightReportDocument')
        self.report.setReadOnly(True)
        self.report.setOpenExternalLinks(False)
        report_layout.addWidget(report_toolbar)
        report_layout.addWidget(self.report, 1)
        self.tabs.addTab(self.report_tab, 'Flight Report')
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
        self._aircraft = aircraft
        # Rendering can be reused only while the database snapshot is unchanged.
        self._loaded_tabs.clear()
        self._route_follows_telemetry = False
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
        tab = self.tabs.widget(index)
        self._ensure_tab_loaded(tab)
        if tab is self.route and self._route_follows_telemetry:
            self._focus_route_at_selected_telemetry()

    def _ensure_tab_loaded(self, tab):
        if self._flight is None or tab is None or tab in self._loaded_tabs:
            return
        if tab in (self.cas, self.exceed):
            tab.tasks = self.tasks
        if tab is self.report_tab:
            self._render_report()
        elif tab is self.overview and self._prepared is not None:
            tab.load(
                self._flight, statistics=self._prepared.statistics,
                events=self._prepared.events, route=self._prepared.route,
            )
        elif tab is self.preventive:
            tab.load(self._flight, self._aircraft)
        else:
            tab.load(self._flight)
        self._loaded_tabs.add(tab)

    def _render_report(self):
        self.report.setHtml(flight_report_html(self._flight, self._aircraft))
        # PDF generation can update this before the tab has been opened.
        self._loaded_tabs.add(self.report_tab)

    def open_parameter_chart(self, parameter_key):
        self._ensure_tab_loaded(self.telemetry)
        if self.telemetry.focus_parameter(parameter_key):
            self.tabs.setCurrentWidget(self.telemetry)

    def open_preventive_point(self, sample_index):
        self._ensure_tab_loaded(self.telemetry)
        self.telemetry.slider.setValue(sample_index)
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
        self._route_follows_telemetry = True
        self.route.focus_point(point_index)

    def _telemetry_position_changed(self, _index):
        if self._route_follows_telemetry and self.tabs.currentWidget() is self.route:
            self._focus_route_at_selected_telemetry()

    def _focus_route_at_selected_telemetry(self):
        if self._flight is None or not self.telemetry.data:
            return
        sample = self.telemetry.data[self.telemetry.slider.value()]
        point_index = nearest_route_point_index(self._flight, sample)
        if point_index is not None:
            self.route.focus_point(point_index)

    def open_full_route(self):
        self._route_follows_telemetry = False
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
        return f'HELINK_Flight_Report_{flight.flight_date}_{session}.pdf'

    def make_report(self):
        if self.fid is None:
            return
        if self.tasks is not None:
            handle = tempfile.NamedTemporaryFile(
                prefix='helink_report_', suffix='.pdf', delete=False,
            )
            path = Path(handle.name)
            handle.close()
            return self._preview_background(path)
        flight = self._flight
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
            self._render_report()
        except Exception as error:
            QMessageBox.critical(self, 'Report error', str(error))
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return
        finally:
            QApplication.restoreOverrideCursor()

        preview = None
        try:
            preview = PdfPreviewDialog(temporary_path, suggested, self)
            preview.exec()
        except Exception as error:
            QMessageBox.critical(self, 'Report preview error', str(error))
        finally:
            if preview is not None:
                preview.release()
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _preview_background(self, destination):
        flight_id = self.fid
        suggested = self._report_filename(self._flight)
        progress = QProgressDialog('Preparing flight report PDF...', '', 0, 0, self)
        progress.setCancelButton(None)
        progress.setWindowTitle('Flight Report')
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.show()

        def cleanup():
            try:
                Path(destination).unlink(missing_ok=True)
            except OSError:
                pass

        def received(result):
            progress.close()
            path, _text = result
            if getattr(self.window(), '_closing', False) or self.fid != flight_id:
                cleanup()
                return
            self._render_report()
            dialog = None
            try:
                dialog = PdfPreviewDialog(path, suggested, self)
                dialog.exec()
            except Exception as error:
                QMessageBox.critical(self, 'Report preview error', str(error))
            finally:
                if dialog is not None:
                    dialog.release()
                cleanup()

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
