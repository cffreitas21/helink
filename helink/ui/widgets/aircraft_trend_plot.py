from datetime import date

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QToolTip
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backend_bases import MouseButton
from matplotlib.dates import AutoDateLocator, DateFormatter, date2num
from matplotlib.figure import Figure


class AircraftTrendPlot(FigureCanvasQTAgg):
    """Real calendar dates, shared physical scale, and clickable daily values."""

    day_selected = Signal(object)
    CHART_HEIGHT = 380

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(10, 4), layout='constrained', facecolor='white')
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setFixedHeight(self.CHART_HEIGHT)
        self.series = []
        self._annotation = None
        self._unit = ''
        self._registrations = {}
        self.mpl_connect('button_press_event', self._on_click)
        self.mpl_connect('motion_notify_event', self._on_hover)

    def show_trends(
        self, days, aircraft, colors, label, unit, statistic='average',
    ):
        QToolTip.hideText()
        self.ax.clear()
        for legend in list(self.fig.legends):
            legend.remove()
        self.series = []
        self._annotation = None
        self._unit = unit
        self._registrations = {item.id: item.registration for item in aircraft}
        by_aircraft = {}
        for day in days:
            by_aircraft.setdefault(day.aircraft_id, []).append(day)
        fields = ('average', 'maximum') if statistic == 'both' else (statistic,)
        handles = []
        for item in aircraft:
            recorded = sorted(
                by_aircraft.get(item.id, ()), key=lambda day: day.flight_date,
            )
            if not recorded:
                continue
            dates = date2num([date.fromisoformat(day.flight_date) for day in recorded])
            for field in fields:
                caption = 'AVG' if field == 'average' else 'MAX'
                values = np.array([getattr(day, field) for day in recorded])
                line, = self.ax.plot(
                    dates, values,
                    label=f'{item.registration} - {caption}',
                    color=colors[item.id],
                    linestyle='-' if field == 'average' else '--',
                    marker='o' if field == 'average' else '^',
                    linewidth=2, markersize=5,
                )
                handles.append(line)
                self.series.append((line, recorded, dates, values))
        legend_rows = (len(handles) + 2) // 3
        # Add space for extra legend rows instead of reducing the plot area.
        self.setFixedHeight(self.CHART_HEIGHT + max(0, legend_rows - 1) * 24)
        if not handles:
            self.ax.set_axis_off()
            message = (
                'No recorded values for this parameter in the selected dates.'
                if aircraft else 'Select an aircraft to view its parameter evolution.'
            )
            self.ax.text(
                0.5, 0.5, message, transform=self.ax.transAxes,
                ha='center', va='center', fontsize=12, color='#64748b', wrap=True,
            )
        else:
            self.ax.set_axis_on()
            self.ax.set_facecolor('#f8fafc')
            self.ax.set_xlabel('Flight Date', fontsize=10, color='#334155')
            self.ax.set_ylabel(f'{label} ({unit})', fontsize=10, color='#334155')
            locator = AutoDateLocator(minticks=3, maxticks=7, interval_multiples=False)
            self.ax.xaxis.set_major_locator(locator)
            self.ax.xaxis.set_major_formatter(DateFormatter('%d/%m/%Y'))
            self.ax.tick_params(axis='both', labelsize=9, colors='#475569')
            self.ax.grid(axis='y', color='#cbd5e1', linewidth=0.8, alpha=0.7)
            self.ax.spines[['top', 'right']].set_visible(False)
            for side in ('bottom', 'left'):
                self.ax.spines[side].set_color('#cbd5e1')
            self.ax.margins(x=0.06, y=0.15)
            all_dates = [value for _, _, dates, _ in self.series for value in dates]
            if min(all_dates) == max(all_dates):
                self.ax.set_xlim(all_dates[0] - 1, all_dates[0] + 1)
                self.ax.set_xticks([all_dates[0]])
            self.fig.legend(
                handles=handles, loc='outside upper center',
                ncol=min(3, len(handles)), fontsize=10, frameon=False,
            )
        self.draw_idle()

    def _nearest_point(self, event):
        if event.inaxes is not self.ax or event.x is None or event.y is None:
            return None
        closest = None
        best_distance = float('inf')
        for line, recorded, dates, values in self.series:
            positions = self.ax.transData.transform(np.column_stack((dates, values)))
            distances = np.sum((positions - (event.x, event.y)) ** 2, axis=1)
            index = int(np.argmin(distances))
            if distances[index] < best_distance:
                best_distance = float(distances[index])
                closest = line, recorded[index], dates[index], values[index]
        return (closest, best_distance) if closest is not None else None

    def day_text(self, day):
        registration = self._registrations[day.aircraft_id]
        stamp = date.fromisoformat(day.flight_date).strftime('%d/%m/%Y')
        flights = 'flight' if day.flight_count == 1 else 'flights'
        return (
            f'{registration} - {stamp}\n'
            f'AVG {day.average:.1f} {self._unit}   '
            f'MAX {day.maximum:.1f} {self._unit}\n'
            f'{day.flight_count} {flights}'
        )

    def _on_hover(self, event):
        nearest = self._nearest_point(event)
        if nearest is not None and nearest[1] <= 14 ** 2:
            QToolTip.showText(QCursor.pos(), self.day_text(nearest[0][1]), self)
        else:
            QToolTip.hideText()

    def _on_click(self, event):
        if event.button != MouseButton.LEFT:
            return
        nearest = self._nearest_point(event)
        if nearest is None:
            return
        line, day, x, y = nearest[0]
        if self._annotation is not None:
            self._annotation.remove()
        right_half = x > sum(self.ax.get_xlim()) / 2
        self._annotation = self.ax.annotate(
            self.day_text(day), xy=(x, y),
            xytext=(-12 if right_half else 12, -16),
            textcoords='offset points',
            ha='right' if right_half else 'left', va='top',
            fontsize=9, color='#1e293b',
            bbox=dict(boxstyle='round,pad=0.6', facecolor='white',
                      edgecolor=line.get_color(), alpha=0.97),
            arrowprops=dict(arrowstyle='->', color=line.get_color()),
        )
        self._annotation.set_in_layout(False)
        self.day_selected.emit(day)
        self.draw_idle()
