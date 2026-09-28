from __future__ import annotations

import re
from math import floor, isfinite

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QAbstractScrollArea
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as Canvas
from matplotlib.backend_bases import MouseButton
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator


class Plot(Canvas):

    point_selected=Signal(int)

    def __init__(self, height=3):
        self.fig = Figure(figsize=(7, height))
        self.fig.set_layout_engine('tight', pad=0.3)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self._cursor_line = None
        self._cursor_background = None
        self._point_count = 0
        self._selection_artists = []
        self._selection_axes = (self.ax,)
        self.mpl_connect('button_press_event', self._select_point)
        self.mpl_connect('resize_event', self._invalidate_cursor)
        self.mpl_connect('draw_event', self._cache_cursor_background)

    def _invalidate_cursor(self, _event=None):
        self._cursor_background = None

    def _cache_cursor_background(self, _event):
        if self._cursor_line is not None:
            # Animated cursors are excluded from the regular draw. Cache only
            # the static graph, then paint the cursor into the current frame.
            self._cursor_background = self.copy_from_bbox(self.ax.bbox)
            self.ax.draw_artist(self._cursor_line)

    def _select_point(self, event):
        if event.button != MouseButton.LEFT or not self._point_count:
            return
        # A MAX label can be offset from its timestamp. It must still select
        # its exact sample, rather than the position underneath the label.
        for artist in reversed(self._selection_artists):
            if artist.contains(event)[0]:
                self.point_selected.emit(artist._data_index)
                return
        if event.inaxes not in self._selection_axes or event.xdata is None:
            return
        if not isfinite(event.xdata):
            return
        index = min(self._point_count - 1, max(0, floor(event.xdata + 0.5)))
        self.point_selected.emit(index)

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
        self._selection_axes = (self.ax,)
        self._point_count = max((len(item[1]) for item in series), default=0)
        self._selection_artists = []
        self._cursor_line = None
        self._cursor_background = None
        self.ax.clear()
        for item in series:
            label,vals=item[:2]; color=item[2] if len(item)>2 else None
            if vals:
                self.ax.plot(range(len(vals)),vals,label=label,linewidth=1.4,color=color)
                if show_max:
                    maximum_record = max((
                        (index, float(value)) for index, value in enumerate(vals)
                        if value is not None and isfinite(float(value))
                    ), key=lambda item: item[1], default=None)
                    if maximum_record is None:
                        continue
                    max_index, maximum = maximum_record
                    marker=self.ax.scatter([max_index],[maximum],s=58,color=color,edgecolors='white',linewidths=1.5,zorder=5,picker=8); marker._data_index=max_index
                    if max_index <= (len(vals) - 1) * 0.15:
                        alignment, offset = 'left', 6
                    elif max_index >= (len(vals) - 1) * 0.85:
                        alignment, offset = 'right', -6
                    else:
                        alignment, offset = 'center', 0
                    annotation=self.ax.annotate(f'MAX {maximum:.1f} {ylabel}'.strip(),(max_index,maximum),xytext=(offset,8),textcoords='offset points',ha=alignment,fontsize=8,fontweight='bold',color=color,bbox={'boxstyle':'round,pad=0.3','facecolor':'white','edgecolor':color,'alpha':.95}); annotation.set_picker(True); annotation._data_index=max_index
                    annotation.set_in_layout(False)
                    self._selection_artists.extend((marker, annotation))
        if cursor is not None:
            self._cursor_line = self.ax.axvline(
                cursor,
                color='#475569',
                linestyle='--',
                linewidth=1.2,
                animated=True,
            )
        self.ax.set_title(title); self.ax.set_ylabel(ylabel, labelpad=2); self.ax.grid(True,alpha=.25)
        self.ax.tick_params(axis='both', labelsize=9, pad=2)
        if flight_time:
            points=max((len(item[1]) for item in series),default=1); self.ax.set_xlim(0,max(1,points-1)); self.ax.margins(y=.16); self.ax.set_xlabel('Flight Time', labelpad=2); self.ax.xaxis.set_major_locator(MaxNLocator(nbins=6,integer=True))
            if time_labels:self.ax.xaxis.set_major_formatter(FuncFormatter(lambda value,_:self._clock_time(time_labels[min(len(time_labels)-1,max(0,int(round(value))))])))
            else:self.ax.xaxis.set_major_formatter(FuncFormatter(lambda value,_:self._flight_time(value)))
        if len(series)>1:self.ax.legend(fontsize=8,ncol=min(3,len(series)))
        self.draw()

    def move_cursor(self, index):
        if self._cursor_line is None:
            return
        self._cursor_line.set_xdata([index, index])
        if self._cursor_background is None:
            self.draw()
            return
        self.restore_region(self._cursor_background)
        self.ax.draw_artist(self._cursor_line)
        self.blit(self.ax.bbox)

    def route(self, points):
        self._point_count = 0
        self._selection_artists = []
        self._cursor_line = None
        self._cursor_background = None
        self.ax.clear(); xs=[x.longitude or 0 for x in points]; ys=[x.latitude or 0 for x in points]
        if xs and ys:
            self.ax.plot(xs,ys,linewidth=1.8); self.ax.scatter([xs[0]],[ys[0]],s=45,label='Start'); self.ax.scatter([xs[-1]],[ys[-1]],s=45,label='End'); self.ax.legend()
        self.ax.set_title('GPS Route'); self.ax.set_xlabel('Longitude'); self.ax.set_ylabel('Latitude'); self.ax.grid(True,alpha=.25); self.draw()
