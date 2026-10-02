from math import isfinite

from PySide6.QtCore import Qt
from matplotlib.backend_bases import MouseButton, MouseEvent
from matplotlib.ticker import FuncFormatter, MaxNLocator

from helink.ui.widgets.plot import Plot


class CombinedTelemetryPlot(Plot):
    """Shared timeline with physical scales kept separate by measurement unit."""

    def __init__(self):
        super().__init__(4.2)
        self.unit_axes = {}
        self.parameter_lines = {}
        self.legend = None
        self._full_xlim = (0, 1)
        self._full_ylims = {}
        self._pressed_at = None
        self._pan_start = None
        self._dragged = False
        self.mpl_connect('scroll_event', self._scroll_zoom)
        self.mpl_connect('motion_notify_event', self._drag_view)
        self.mpl_connect('button_release_event', self._release_view)

    def parameters(self, series, time_labels=(), cursor=0, *, render=True, preserve_view=False):
        self._pressed_at = None
        self._pan_start = None
        self._dragged = False
        self.setCursor(Qt.ArrowCursor)
        previous_x = self.ax.get_xlim() if preserve_view and self._point_count else None
        previous_y = (
            {unit: axis.get_ylim() for unit, axis in self.unit_axes.items()}
            if previous_x is not None else {}
        )
        self._cursor_line = None
        self._cursor_background = None
        self._selection_artists = []
        self._point_count = max((len(values) for _, values, _, _ in series), default=0)
        self.fig.clear()
        self.ax = self.fig.add_subplot(111)
        self.unit_axes = {}
        self.parameter_lines = {}
        self.legend = None
        handles, captions, maximum_indices = [], [], []
        units = list(dict.fromkeys(unit for _, _, _, unit in series))
        for index, unit in enumerate(units):
            axis = self.ax if index == 0 else self.ax.twinx()
            if index > 1:
                axis.spines['right'].set_position(('outward', 58 * (index - 1)))
            axis.set_ylabel(unit, labelpad=3)
            axis.tick_params(axis='both', labelsize=9, pad=2)
            axis.margins(y=0.12)
            self.unit_axes[unit] = axis
        self._selection_axes = tuple(self.unit_axes.values()) or (self.ax,)
        for title, values, color, unit in series:
            axis = self.unit_axes[unit]
            line, = axis.plot(range(len(values)), values, color=color, linewidth=1.5)
            self.parameter_lines[title] = line
            handles.append(line)
            maximum_record = max((
                (index, float(value)) for index, value in enumerate(values)
                if value is not None and isfinite(float(value))
            ), key=lambda item: item[1], default=None)
            if maximum_record is not None:
                maximum_index, maximum = maximum_record
                marker = axis.scatter(
                    [maximum_index], [maximum], s=42, color=color,
                    edgecolors='white', linewidths=1.2, zorder=5, picker=8,
                )
                marker._data_index = maximum_index
                self._selection_artists.append(marker)
                captions.append(f'{title} ({unit})  MAX {maximum:.1f}')
                maximum_indices.append(maximum_index)
            else:
                captions.append(f'{title} ({unit})  NO DATA')
                maximum_indices.append(None)
        self.ax.set_xlim(0, max(1, self._point_count - 1))
        self.ax.set_xlabel('Flight Time', labelpad=2)
        self.ax.xaxis.set_major_locator(MaxNLocator(nbins=8, integer=True))
        if time_labels:
            self.ax.xaxis.set_major_formatter(FuncFormatter(
                lambda value, _: self._clock_time(
                    time_labels[min(len(time_labels) - 1, max(0, round(value)))]
                )
            ))
        else:
            self.ax.xaxis.set_major_formatter(FuncFormatter(
                lambda value, _: self._flight_time(value)
            ))
        self.ax.grid(True, alpha=0.22)
        legend_rows = (len(captions) + 2) // 3
        self.fig.set_layout_engine(
            'tight', pad=0.3, rect=(0, 0, 1, 1 - (0.035 * legend_rows + 0.025)),
        )
        if handles:
            self.legend = self.fig.legend(
                handles, captions, loc='upper center', bbox_to_anchor=(0.5, 1.0),
                ncol=min(3, len(handles)), fontsize=10, frameon=True,
                edgecolor='#cbd5e1', columnspacing=1.2,
                borderaxespad=0.2, borderpad=0.3, labelspacing=0.3,
            )
            self.legend.set_in_layout(False)
            for text, index in zip(self.legend.get_texts(), maximum_indices):
                if index is not None:
                    text._data_index = index
                    text.set_picker(True)
                    self._selection_artists.append(text)
        self._cursor_line = self.ax.axvline(
            cursor, color='#475569', linestyle='--', linewidth=1.2, animated=True,
        )
        self._full_xlim = self.ax.get_xlim()
        self._full_ylims = {unit: axis.get_ylim() for unit, axis in self.unit_axes.items()}
        for axis in self._selection_axes:
            axis.callbacks.connect('xlim_changed', self._invalidate_cursor)
            axis.callbacks.connect('ylim_changed', self._invalidate_cursor)
        if previous_x is not None:
            self.ax.set_xlim(previous_x)
            for unit, axis in self.unit_axes.items():
                if unit in previous_y:
                    axis.set_ylim(previous_y[unit])
            self.limit_view()
        if render:
            self.draw()
        else:
            self.draw_idle()

    @staticmethod
    def _bounded_interval(limits, bounds, minimum):
        left, right = sorted(limits)
        lower, upper = bounds
        if not all(isfinite(value) for value in (left, right)):
            return bounds
        width = min(upper - lower, max(minimum, right - left))
        center = (left + right) / 2
        start = min(upper - width, max(lower, center - width / 2))
        return start, start + width

    def limit_view(self):
        """Keep navigation inside the flight and the original physical scales."""
        self.ax.set_xlim(self._bounded_interval(self.ax.get_xlim(), self._full_xlim, 1))
        for unit, axis in self.unit_axes.items():
            bounds = self._full_ylims[unit]
            axis.set_ylim(self._bounded_interval(
                axis.get_ylim(), bounds, (bounds[1] - bounds[0]) * 1e-6,
            ))
        self._invalidate_cursor()
        self.draw_idle()

    def reset_view(self):
        self.ax.set_xlim(self._full_xlim)
        for unit, axis in self.unit_axes.items():
            axis.set_ylim(self._full_ylims[unit])
        self._invalidate_cursor()
        self.draw_idle()

    def zoom_view(self, factor, *, x_fraction=None, y_fraction=0.5):
        if self._point_count < 2 or not isfinite(factor) or factor <= 0:
            return
        left, right = self.ax.get_xlim()
        if x_fraction is None:
            selected = self._cursor_line.get_xdata()[0]
            x_fraction = (selected - left) / (right - left) if left <= selected <= right else 0.5
        x_fraction = min(1, max(0, x_fraction))
        y_fraction = min(1, max(0, y_fraction))
        anchor = left + (right - left) * x_fraction
        width = (right - left) * factor
        self.ax.set_xlim(anchor - width * x_fraction, anchor + width * (1 - x_fraction))
        for axis in self.unit_axes.values():
            bottom, top = axis.get_ylim()
            anchor = bottom + (top - bottom) * y_fraction
            height = (top - bottom) * factor
            axis.set_ylim(anchor - height * y_fraction, anchor + height * (1 - y_fraction))
        self.limit_view()

    def _scroll_zoom(self, event):
        if not event.step or event.inaxes not in self._selection_axes:
            return
        box = self.ax.bbox
        self.zoom_view(
            1.25 ** (-max(-4, min(4, event.step))),
            x_fraction=(event.x - box.x0) / box.width,
            y_fraction=(event.y - box.y0) / box.height,
        )

    def wheelEvent(self, event):
        x, y = self.mouseEventCoords(event)
        if self._point_count > 1 and self.ax.bbox.contains(x, y):
            steps = event.angleDelta().y() / 120 or event.pixelDelta().y() / 120
            if steps:
                mouse = MouseEvent('scroll_event', self, x, y, step=steps, guiEvent=event)
                self.callbacks.process('scroll_event', mouse)
                event.accept()
                return
        super().wheelEvent(event)

    def _select_point(self, event):
        # Delay selection until release: the same left button can start a pan.
        if event.button != MouseButton.LEFT:
            return
        if event.dblclick:
            self._pressed_at = None
            self._pan_start = None
            self._dragged = False
            if event.inaxes in self._selection_axes:
                self.reset_view()
            return
        self._pressed_at = (event.x, event.y)
        self._dragged = False
        self._pan_start = (
            (
                self.ax.get_xlim(),
                {unit: axis.get_ylim() for unit, axis in self.unit_axes.items()},
            )
            if self._point_count > 1 and event.inaxes in self._selection_axes
            else None
        )

    def _drag_view(self, event):
        if self._pressed_at is None:
            self.setCursor(Qt.ArrowCursor)
            return
        dx = event.x - self._pressed_at[0]
        dy = event.y - self._pressed_at[1]
        if not self._dragged and dx * dx + dy * dy < 25:
            return
        self._dragged = True
        if self._pan_start is None:
            return
        self.setCursor(Qt.ClosedHandCursor)
        box = self.ax.bbox
        if not box.width or not box.height:
            return
        (left, right), y_limits = self._pan_start
        x_shift = dx * (right - left) / box.width
        self.ax.set_xlim(left - x_shift, right - x_shift)
        for unit, axis in self.unit_axes.items():
            bottom, top = y_limits[unit]
            y_shift = dy * (top - bottom) / box.height
            axis.set_ylim(bottom - y_shift, top - y_shift)
        self.limit_view()

    def _release_view(self, event):
        if event.button != MouseButton.LEFT or self._pressed_at is None:
            return
        pressed_at = self._pressed_at
        dragged = self._dragged
        self._pressed_at = None
        self._pan_start = None
        self._dragged = False
        self.setCursor(Qt.ArrowCursor)
        if (
            not dragged
            and (event.x - pressed_at[0]) ** 2 + (event.y - pressed_at[1]) ** 2 < 25
        ):
            super()._select_point(event)

    def move_cursor(self, index):
        left, right = self.ax.get_xlim()
        if self._point_count and not left <= index <= right:
            width = right - left
            self.ax.set_xlim(self._bounded_interval(
                (index - width / 2, index + width / 2), self._full_xlim, 1,
            ))
        super().move_cursor(index)
