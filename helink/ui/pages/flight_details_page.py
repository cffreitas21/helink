from pathlib import Path
import tempfile

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from helink.ui.dialogs import PdfPreviewDialog
from helink.ui.tabs import AlertsTab, MapTab, OverviewTab, TelemetryTab


class FlightDetailsPage(QWidget):

    back_requested=Signal(); import_requested=Signal(str,str)

    def __init__(self, aircraft_controller, flight_controller, report_controller):
        super().__init__(); self.aircraft_controller=aircraft_controller; self.flight_controller=flight_controller; self.report_controller=report_controller; self.fid=None; root=QVBoxLayout(self); root.setContentsMargins(20,16,20,20)
        h=QHBoxLayout(); b=QPushButton('← Flight List'); b.setObjectName('secondary'); b.clicked.connect(self.back_requested); h.addWidget(b); self.title=QLabel(); self.title.setObjectName('title'); h.addWidget(self.title); h.addStretch(); ex=QPushButton('Export Report'); ex.clicked.connect(self.export_report); h.addWidget(ex); root.addLayout(h)
        self.info = QLabel()
        self.info.setObjectName('muted')
        root.addWidget(self.info)
        self.tabs=QTabWidget(); root.addWidget(self.tabs)
        self.overview=OverviewTab(); self.overview.import_requested.connect(lambda t:self.import_requested.emit(self.fid,t)); self.overview.event_requested.connect(self.open_event_summary); self.tabs.addTab(self.overview,'Overview')
        self.telemetry=TelemetryTab(); self.tabs.addTab(self.telemetry,'Telemetry')
        self.cas=AlertsTab('CAS'); self.tabs.addTab(self.cas,'CAS')
        self.exceed=AlertsTab('EXCEEDANCE'); self.tabs.addTab(self.exceed,'Exceedances')
        self.route=MapTab(); self.tabs.addTab(self.route,'Flight Route')
        rep=QWidget(); rl=QVBoxLayout(rep); self.report=QTextEdit(); self.report.setReadOnly(True); gen=QPushButton('Generate Maintenance Report'); gen.clicked.connect(self.make_report); rl.addWidget(gen); rl.addWidget(self.report); self.tabs.addTab(rep,'Maintenance Report')

    def load(self,fid):
        self.fid=fid; f=self.flight_controller.get(fid)
        aircraft=next((item for item in self.aircraft_controller.list_aircraft() if item.id==f.aircraft_id),None)
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
        self.overview.load(f); self.telemetry.load(f); self.exceed.load(f); self.cas.load(f); self.route.load(f); text=f.predictive_report or 'No maintenance report has been generated for this flight yet.'; self.report.setPlainText(text)

    def open_event_summary(self, event_key):
        if event_key == 'exceedances':
            self.exceed.set_filters()
            self.tabs.setCurrentWidget(self.exceed)
            return
        level = {
            'warnings': 'WARNING',
            'cautions': 'CAUTION',
            'miscmp': 'CAUTION',
        }.get(event_key, 'All')
        alert_name = 'MISCMP-P' if event_key == 'miscmp' else 'All Alerts'
        self.cas.set_filters(level, alert_name)
        self.tabs.setCurrentWidget(self.cas)

    @staticmethod
    def _report_filename(flight):
        session = (flight.departure_time or flight.id[:8]).replace(':', '')
        return f'HELINK_Maintenance_Report_{flight.flight_date}_{session}.pdf'

    def make_report(self):
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
            self.report.setPlainText(
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
        flight = self.flight_controller.get(self.fid)
        suggested = self._report_filename(flight)
        path, _ = QFileDialog.getSaveFileName(
            self,
            'Export Maintenance Report',
            suggested,
            'PDF Document (*.pdf)',
        )
        if not path:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            destination = self.report_controller.export_pdf(self.fid, path)
            self.report.setPlainText(
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
