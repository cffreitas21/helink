from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from helink.ui.dialogs import DeleteAircraftDialog
from helink.ui.widgets import Card


class DashboardPage(QWidget):
    aircraft_selected=Signal(str); add_requested=Signal()
    def __init__(self, aircraft_controller):
        super().__init__(); self.aircraft_controller=aircraft_controller; root=QVBoxLayout(self); root.setContentsMargins(24,20,24,24); root.setSpacing(14)
        h=QHBoxLayout(); t=QLabel('Fleet Management'); t.setObjectName('title'); h.addWidget(t); h.addStretch(); b=QPushButton('＋ Add Aircraft'); b.clicked.connect(self.add_requested); h.addWidget(b); delete=QPushButton('Delete Aircraft'); delete.setObjectName('danger'); delete.clicked.connect(self.choose_aircraft_to_delete); h.addWidget(delete); root.addLayout(h)
        sc=QScrollArea(); sc.setWidgetResizable(True); sc.setFrameShape(QFrame.NoFrame); self.box=QWidget(); self.list=QVBoxLayout(self.box); self.list.setContentsMargins(0,4,0,4); self.list.setSpacing(10); sc.setWidget(self.box); root.addWidget(sc)
    def refresh(self):
        ac=self.aircraft_controller.list_aircraft()
        while self.list.count():
            item=self.list.takeAt(0); w=item.widget(); w and w.deleteLater()
        if not ac:
            empty=Card(); empty.layout.setContentsMargins(28,32,28,32); msg=QLabel('There are no helicopters in the fleet yet'); msg.setAlignment(Qt.AlignCenter); msg.setStyleSheet('font-size:17px;font-weight:700'); empty.layout.addWidget(msg)
            hint=QLabel('Add the first aircraft to start importing and analysing flights.'); hint.setObjectName('muted'); hint.setAlignment(Qt.AlignCenter); empty.layout.addWidget(hint); self.list.addWidget(empty)
        for a in ac:
            averages=self.aircraft_controller.engine_averages(a.id)
            row=QFrame(); row.setObjectName('aircraftRow'); lay=QHBoxLayout(row); lay.setContentsMargins(18,16,18,16); lay.setSpacing(14)
            icon=QFrame(); icon.setObjectName('aircraftIcon'); icon.setFixedSize(54,54); il=QVBoxLayout(icon); il.setContentsMargins(0,0,0,0); glyph=QLabel('✈'); glyph.setAlignment(Qt.AlignCenter); glyph.setStyleSheet('font-size:23px;color:#2563eb;background:transparent'); il.addWidget(glyph); lay.addWidget(icon)
            identity=QVBoxLayout(); identity.setSpacing(3); title=QLabel(a.registration); title.setStyleSheet('font-size:18px;font-weight:800;color:#0f172a'); identity.addWidget(title); model=QLabel(a.model); model.setObjectName('muted'); identity.addWidget(model); serial_number=QLabel(f"SN {a.serial_number}"); serial_number.setObjectName('muted'); identity.addWidget(serial_number); lay.addLayout(identity,2)
            stats=((str(a.flight_count),'IMPORTED FLIGHTS'),(self._temperature(averages['avg_itt']),'AVG ITT'),(self._temperature(averages['avg_eng_ot']),'AVG ENG OIL TEMP'),(self._temperature(averages['avg_xmsn_ot']),'AVG XMSN OIL TEMP'))
            for value,label in stats:
                box=QFrame(); box.setObjectName('statBox'); box.setMinimumWidth(125); stat=QVBoxLayout(box); stat.setContentsMargins(12,9,12,9); stat.setSpacing(2); sv=QLabel(value); sv.setObjectName('statValue'); stat.addWidget(sv); sl=QLabel(label); sl.setObjectName('statLabel'); stat.addWidget(sl); lay.addWidget(box,1)
            b=QPushButton('View Flights  →'); b.setMinimumSize(140,54); b.clicked.connect(lambda _,aid=a.id:self.aircraft_selected.emit(aid)); lay.addWidget(b); self.list.addWidget(row)
        self.list.addStretch()

    @staticmethod
    def _temperature(value):
        return f'{value:.1f} °C' if value is not None else '—'

    def choose_aircraft_to_delete(self):
        aircraft = self.aircraft_controller.list_aircraft()
        if not aircraft:
            QMessageBox.information(
                self, 'No aircraft', 'There are no aircraft to delete.'
            )
            return

        dialog = DeleteAircraftDialog(aircraft, self)
        if dialog.exec() != QDialog.Accepted:
            return

        selected = dialog.selected_aircraft
        self.aircraft_controller.delete(selected.id)
        self.refresh()
        QMessageBox.information(
            self,
            'Aircraft deleted',
            f'Aircraft {selected.registration} and its associated data '
            'have been deleted.',
        )
