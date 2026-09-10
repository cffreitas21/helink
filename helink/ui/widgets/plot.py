from __future__ import annotations

import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QAbstractScrollArea
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as Canvas
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator


class Plot(Canvas):

    point_selected=Signal(int)

    def __init__(self, height=3):
        self.fig = Figure(figsize=(7, height), tight_layout=True)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self._cursor_line = None
        self._cursor_background = None
        self.mpl_connect('pick_event', self._pick_point)
        self.mpl_connect('resize_event', self._invalidate_cursor)

    def _invalidate_cursor(self, _event=None):
        self._cursor_background = None

    def _pick_point(self,event):
        index=getattr(event.artist,'_data_index',None)
        if index is not None:self.point_selected.emit(index)

    def wheelEvent(self, event):
        scroll_area = self.parentWidget()
        while scroll_area is not None and not isinstance(
            scroll_area, QAbstractScrollArea
        ):
            scroll_area = scroll_area.parentWidget()
        if scroll_area is None:
            super().wheelEvent(event)
            return

        scrollbar = scroll_area.verticalScrollBar()
        pixel_delta = event.pixelDelta().y()
        if pixel_delta:
            distance = pixel_delta
        else:
            steps = event.angleDelta().y() / 120
            distance = steps * max(36, scrollbar.singleStep() * 3)
        scrollbar.setValue(scrollbar.value() - round(distance))
        event.accept()
    @staticmethod
    def _flight_time(value):
        seconds=max(0,int(round(value))); hours,remainder=divmod(seconds,3600); minutes,seconds=divmod(remainder,60)
        return f'{hours}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes:02d}:{seconds:02d}'
    @staticmethod
    def _clock_time(value):
        matches=re.findall(r'(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?',str(value or ''))
        if not matches:return '--:--:--'
        hour,minute,second=matches[-1]; return f'{int(hour):02d}:{minute}:{second or "00"}'
    def lines(self, series, title, ylabel='', cursor=None, show_max=False, flight_time=False, time_labels=None):
        self.ax.clear()
        for item in series:
            label,vals=item[:2]; color=item[2] if len(item)>2 else None
            if vals:
                self.ax.plot(range(len(vals)),vals,label=label,linewidth=1.4,color=color)
                if show_max:
                    maximum=max(vals); max_index=vals.index(maximum); marker=self.ax.scatter([max_index],[maximum],s=58,color=color,edgecolors='white',linewidths=1.5,zorder=5,picker=8); marker._data_index=max_index
                    annotation=self.ax.annotate(f'MAX {maximum:.1f} {ylabel}'.strip(),(max_index,maximum),xytext=(0,11),textcoords='offset points',ha='center',fontsize=8,fontweight='bold',color=color,bbox={'boxstyle':'round,pad=0.3','facecolor':'white','edgecolor':color,'alpha':.95}); annotation.set_picker(True); annotation._data_index=max_index
        self._cursor_line = None
        self._cursor_background = None
        if cursor is not None:
            self._cursor_line = self.ax.axvline(
                cursor,
                color='#475569',
                linestyle='--',
                linewidth=1.2,
                animated=True,
            )
        self.ax.set_title(title); self.ax.set_ylabel(ylabel); self.ax.grid(True,alpha=.25)
        if flight_time:
            points=max((len(item[1]) for item in series),default=1); self.ax.set_xlim(0,max(1,points-1)); self.ax.margins(y=.16); self.ax.set_xlabel('Flight Time'); self.ax.xaxis.set_major_locator(MaxNLocator(nbins=6,integer=True))
            if time_labels:self.ax.xaxis.set_major_formatter(FuncFormatter(lambda value,_:self._clock_time(time_labels[min(len(time_labels)-1,max(0,int(round(value))))])))
            else:self.ax.xaxis.set_major_formatter(FuncFormatter(lambda value,_:self._flight_time(value)))
        if len(series)>1:self.ax.legend(fontsize=8,ncol=min(3,len(series)))
        self.draw()
        if self._cursor_line is not None:
            self._cursor_background = self.copy_from_bbox(self.ax.bbox)
            self.move_cursor(cursor)

    def move_cursor(self, index):
        if self._cursor_line is None:
            return
        if self._cursor_background is None:
            self._cursor_line.set_visible(False)
            self.draw()
            self._cursor_background = self.copy_from_bbox(self.ax.bbox)
            self._cursor_line.set_visible(True)
        self.restore_region(self._cursor_background)
        self._cursor_line.set_xdata([index, index])
        self.ax.draw_artist(self._cursor_line)
        self.blit(self.ax.bbox)

    def route(self, points):
        self._cursor_line = None
        self._cursor_background = None
        self.ax.clear(); xs=[x.longitude or 0 for x in points]; ys=[x.latitude or 0 for x in points]
        if xs and ys:
            self.ax.plot(xs,ys,linewidth=1.8); self.ax.scatter([xs[0]],[ys[0]],s=45,label='Start'); self.ax.scatter([xs[-1]],[ys[-1]],s=45,label='End'); self.ax.legend()
        self.ax.set_title('GPS Route'); self.ax.set_xlabel('Longitude'); self.ax.set_ylabel('Latitude'); self.ax.grid(True,alpha=.25); self.draw()
