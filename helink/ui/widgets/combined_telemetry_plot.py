from math import isfinite

from matplotlib.ticker import FuncFormatter, MaxNLocator

from helink.ui.widgets.plot import Plot


class CombinedTelemetryPlot(Plot):
    """Shared timeline with physical scales kept separate by measurement unit."""

    def __init__(self):
        super().__init__(4.2)
        self.unit_axes = {}
        self.parameter_lines = {}
        self.legend = None

    def parameters(self, series, time_labels=(), cursor=0):
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
        self.draw()
