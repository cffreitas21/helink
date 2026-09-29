"""Headless chart interaction tests with synthetic telemetry."""

import os
import unittest
from dataclasses import replace
from math import isnan
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QFontDatabase, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox
from matplotlib.backend_bases import MouseButton, MouseEvent

from helink.models.flight.engine_data import EngineData
from helink.models.flight.flight import Flight
from helink.models.flight.gps_data import GPSData
from helink.ui.tabs.telemetry_tab import TelemetryTab
from helink.ui.theme import STYLE
from helink.ui.telemetry_parameters import (
    OVERVIEW_TELEMETRY_PARAMETERS, TELEMETRY_PARAMETERS,
)
from helink.ui.widgets import ChartFilterButton, Plot
from helink.ui.widgets.combined_chart_toolbar import CombinedChartToolbar
from helink.ui.widgets.combined_telemetry_plot import CombinedTelemetryPlot


def application():
    app = QApplication.instance() or QApplication([])
    font = Path('C:/Windows/Fonts/segoeui.ttf')
    if os.name == 'nt' and font.exists():
        QFontDatabase.addApplicationFont(str(font))
    app.setStyleSheet(STYLE)
    return app


def click_canvas(plot, x, y, button=MouseButton.LEFT):
    event = MouseEvent('button_press_event', plot, x, y, button=button)
    plot.callbacks.process('button_press_event', event)


def click_time(plot, index, height_fraction=0.06, button=MouseButton.LEFT):
    bottom, top = plot.ax.get_ylim()
    x, y = plot.ax.transData.transform(
        (index, bottom + (top - bottom) * height_fraction)
    )
    click_canvas(plot, x, y, button)


def drag_canvas(plot, start, end, button=MouseButton.LEFT):
    for name, position in (
        ('button_press_event', start),
        ('motion_notify_event', end),
        ('button_release_event', end),
    ):
        options = {'buttons': {button}} if name == 'motion_notify_event' else {'button': button}
        event = MouseEvent(name, plot, *position, **options)
        plot.callbacks.process(name, event)


def wheel_canvas(plot, delta):
    box = plot.ax.bbox
    local = QPointF(
        (box.x0 + box.x1) / 2 / plot.device_pixel_ratio,
        plot.height() - (box.y0 + box.y1) / 2 / plot.device_pixel_ratio,
    )
    event = QWheelEvent(
        local, QPointF(plot.mapToGlobal(local.toPoint())), QPoint(), QPoint(0, delta),
        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False,
    )
    QApplication.sendEvent(plot, event)


class CombinedNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.plot = CombinedTelemetryPlot()
        self.plot.resize(1000, 560)
        self.toolbar = CombinedChartToolbar(self.plot)
        self.plot.show()
        self.series = (
            ('N1', [90 + i * 0.05 for i in range(50)], '#2563eb', '%'),
            ('ITT', [600 + i * 2 for i in range(50)], '#d97706', '\u00b0C'),
            ('FUEL PRESS', [25 + i * 0.1 for i in range(50)], '#9333ea', 'psi'),
        )
        self.timestamps = tuple(f'11:00:{i:02d}' for i in range(50))
        self.plot.parameters(self.series, self.timestamps, cursor=20)
        self.app.processEvents()
        self.received = []
        self.plot.point_selected.connect(self.received.append)

    def tearDown(self):
        self.toolbar.clear_mode()
        self.toolbar.close()
        self.toolbar.deleteLater()
        self.plot.close()
        self.plot.deleteLater()
        self.app.processEvents()

    def assert_shared_timeline(self):
        expected = self.plot.ax.get_xlim()
        for axis in self.plot.unit_axes.values():
            self.assertEqual(axis.get_xlim(), expected)

    def test_zoom_buttons_change_all_scales_and_reset_restores_entire_flight(self):
        original_x = self.plot.ax.get_xlim()
        original_y = {unit: axis.get_ylim() for unit, axis in self.plot.unit_axes.items()}
        self.toolbar.zoom_in_action.trigger()
        self.assertLess(self.plot.ax.get_xlim()[1] - self.plot.ax.get_xlim()[0], 49)
        for unit, axis in self.plot.unit_axes.items():
            bottom, top = axis.get_ylim()
            old_bottom, old_top = original_y[unit]
            self.assertLess(top - bottom, old_top - old_bottom)
        self.assert_shared_timeline()
        self.toolbar.zoom_out_action.trigger()
        self.assertAlmostEqual(self.plot.ax.get_xlim()[0], original_x[0])
        self.assertAlmostEqual(self.plot.ax.get_xlim()[1], original_x[1])
        self.toolbar.pan_action.trigger()
        self.toolbar.home()
        self.assertFalse(self.toolbar.mode)
        self.assertEqual(self.plot.ax.get_xlim(), original_x)
        self.assertEqual(
            {unit: axis.get_ylim() for unit, axis in self.plot.unit_axes.items()}, original_y,
        )
        self.assertEqual(self.plot._cursor_line.get_xdata(), [20, 20])

    def test_wheel_zooms_without_selecting_another_timestamp(self):
        wheel_canvas(self.plot, 120)
        zoomed = self.plot.ax.get_xlim()
        self.assertAlmostEqual(zoomed[1] - zoomed[0], 49 * 0.8)
        self.assertEqual(self.received, [])
        self.assertEqual(self.plot._cursor_line.get_xdata(), [20, 20])
        wheel_canvas(self.plot, -120)
        self.assertAlmostEqual(self.plot.ax.get_xlim()[1] - self.plot.ax.get_xlim()[0], 49)
        self.assert_shared_timeline()

    def test_pan_moves_all_scales_without_changing_selected_timestamp(self):
        self.plot.zoom_view(0.25)
        self.plot.draw()
        before_x = self.plot.ax.get_xlim()
        before_y = {unit: axis.get_ylim() for unit, axis in self.plot.unit_axes.items()}
        self.toolbar.pan_action.trigger()
        box = self.plot.ax.bbox
        drag_canvas(
            self.plot, (box.x0 + box.width * 0.5, box.y0 + box.height * 0.5),
            (box.x0 + box.width * 0.35, box.y0 + box.height * 0.4),
        )
        self.assertGreater(self.plot.ax.get_xlim()[0], before_x[0])
        self.assertAlmostEqual(
            self.plot.ax.get_xlim()[1] - self.plot.ax.get_xlim()[0], before_x[1] - before_x[0],
        )
        self.assertTrue(all(
            axis.get_ylim() != before_y[unit] for unit, axis in self.plot.unit_axes.items()
        ))
        self.assert_shared_timeline()
        self.assertEqual(self.received, [])
        self.toolbar.pan_action.trigger()
        click_time(self.plot, 22)
        self.assertEqual(self.received, [22])

    def test_zoom_rectangle_and_right_drag_zoom_out_keep_shared_scales(self):
        self.toolbar.zoom_action.trigger()
        box = self.plot.ax.bbox
        start = (box.x0 + box.width * 0.25, box.y0 + box.height * 0.25)
        end = (box.x0 + box.width * 0.75, box.y0 + box.height * 0.75)
        drag_canvas(self.plot, start, end)
        self.assertAlmostEqual(self.plot.ax.get_xlim()[1] - self.plot.ax.get_xlim()[0], 24.5, delta=0.1)
        self.assert_shared_timeline()
        drag_canvas(self.plot, start, end, MouseButton.RIGHT)
        self.assertAlmostEqual(self.plot.ax.get_xlim()[1] - self.plot.ax.get_xlim()[0], 49, delta=0.3)
        self.assert_shared_timeline()
        self.assertEqual(self.received, [])

    def test_navigation_is_bounded_and_axes_labels_remain_visible(self):
        for _ in range(20):
            self.plot.zoom_view(0.1)
        self.assertAlmostEqual(self.plot.ax.get_xlim()[1] - self.plot.ax.get_xlim()[0], 1)
        self.plot.ax.set_xlim(-500, -490)
        self.plot.limit_view()
        self.assertGreaterEqual(self.plot.ax.get_xlim()[0], 0)
        self.plot.ax.set_xlim(500, 510)
        self.plot.limit_view()
        self.assertLessEqual(self.plot.ax.get_xlim()[1], 49)
        self.plot.reset_view()
        self.plot.zoom_view(0.5)
        self.plot.draw()
        renderer = self.plot.get_renderer()
        for axis in self.plot.unit_axes.values():
            bounds = axis.yaxis.label.get_window_extent(renderer)
            self.assertGreaterEqual(bounds.x0, 0)
            self.assertLessEqual(bounds.x1, self.plot.fig.bbox.width)
            self.assertTrue(axis.yaxis.get_ticklabels())
        self.assertEqual(self.plot.ax.xaxis.get_major_formatter()(20, 0), '11:00:20')

    def test_selection_recenters_time_without_losing_zoom_or_rebuilding_data(self):
        self.plot.zoom_view(0.2)
        width = self.plot.ax.get_xlim()[1] - self.plot.ax.get_xlim()[0]
        lines = dict(self.plot.parameter_lines)
        self.plot.move_cursor(49)
        self.assertLessEqual(self.plot.ax.get_xlim()[0], 49)
        self.assertGreaterEqual(self.plot.ax.get_xlim()[1], 49)
        self.assertAlmostEqual(self.plot.ax.get_xlim()[1] - self.plot.ax.get_xlim()[0], width)
        self.assertEqual(self.plot.parameter_lines, lines)
        self.assertEqual(self.plot._cursor_line.get_xdata(), [49, 49])

    def test_filter_rebuild_can_preserve_view_but_new_recording_resets_it(self):
        self.plot.zoom_view(0.4)
        previous = self.plot.ax.get_xlim()
        self.plot.parameters(self.series[1:], self.timestamps, cursor=20, preserve_view=True)
        self.assertEqual(self.plot.ax.get_xlim(), previous)
        self.plot.parameters(self.series, self.timestamps, cursor=20)
        self.assertEqual(self.plot.ax.get_xlim(), (0, 49))

    def test_empty_or_single_sample_never_produces_invalid_zoom_limits(self):
        for values in ([], [42]):
            self.plot.parameters([('ITT', values, '#d97706', '\u00b0C')])
            limits = self.plot.ax.get_xlim()
            self.plot.zoom_view(0.1)
            self.plot.zoom_view(10)
            self.assertEqual(self.plot.ax.get_xlim(), limits)


class PlotInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.plot = Plot(2.35)
        self.plot.resize(600, 220)
        self.plot.show()
        self.plot.lines(
            [('ITT', [610, 620, 650, 630, 640], '#1f77b4')],
            '', '\u00b0C', cursor=0, show_max=True, flight_time=True,
        )
        self.app.processEvents()
        self.received = []
        self.plot.point_selected.connect(self.received.append)

    def tearDown(self):
        self.plot.close()
        self.plot.deleteLater()
        self.app.processEvents()

    def test_click_anywhere_selects_nearest_timestamp_not_nearest_curve(self):
        click_time(self.plot, 3.6)
        self.assertEqual(self.received, [4])
        click_time(self.plot, 1.2, height_fraction=0.8)
        self.assertEqual(self.received, [4, 1])

    def test_maximum_marker_selects_once(self):
        x, y = self.plot.ax.transData.transform((2, 650))
        click_canvas(self.plot, x, y)
        self.assertEqual(self.received, [2])

    def test_maximum_label_selects_its_sample_not_position_under_label(self):
        label = self.plot._selection_artists[-1]
        bounds = label.get_window_extent(self.plot.get_renderer())
        click_canvas(
            self.plot, (bounds.x0 + bounds.x1) / 2, (bounds.y0 + bounds.y1) / 2,
        )
        self.assertEqual(self.received, [2])

    def test_right_click_and_canvas_margins_do_not_select(self):
        click_time(self.plot, 3, button=MouseButton.RIGHT)
        click_canvas(self.plot, -5, -5)
        self.assertEqual(self.received, [])

    def test_empty_and_single_point_recordings_are_safe(self):
        self.plot.lines([('ITT', [], '#1f77b4')], '', cursor=0, flight_time=True)
        click_time(self.plot, 0.5)
        self.assertEqual(self.received, [])
        self.plot.lines(
            [('ITT', [42], '#1f77b4')], '', cursor=0, show_max=True,
            flight_time=True,
        )
        click_time(self.plot, 0.6)
        self.assertEqual(self.received, [0])

    def test_compact_margins_increase_graph_area_without_changing_canvas_size(self):
        canvas_size = self.plot.size()
        self.plot.fig.set_layout_engine('tight', pad=1.08)
        self.plot.draw()
        old = self.plot.ax.bbox.frozen()
        self.plot.fig.set_layout_engine('tight', pad=0.3)
        self.plot.draw()
        new = self.plot.ax.bbox
        self.assertGreater(new.width, old.width)
        self.assertGreater(new.height, old.height)
        self.assertEqual(self.plot.size(), canvas_size)

    def test_cached_cursor_moves_without_redrawing_entire_chart(self):
        with patch.object(self.plot, 'draw', wraps=self.plot.draw) as draw:
            self.plot.move_cursor(3)
            self.plot.move_cursor(4)
        draw.assert_not_called()
        self.assertEqual(list(self.plot._cursor_line.get_xdata()), [4, 4])

    def test_redraw_and_resize_keep_current_cursor_and_refresh_background(self):
        self.plot.move_cursor(3)
        self.plot.resize(650, 240)
        self.app.processEvents()
        self.plot.draw()
        self.assertIsNotNone(self.plot._cursor_background)
        self.assertEqual(list(self.plot._cursor_line.get_xdata()), [3, 3])
        with patch.object(self.plot, 'draw', wraps=self.plot.draw) as draw:
            self.plot.move_cursor(4)
        draw.assert_not_called()

    def test_maximum_labels_at_both_ends_remain_inside_canvas(self):
        for values in ([700, 620, 650, 630, 640], [610, 620, 650, 630, 700]):
            with self.subTest(values=values):
                self.plot.lines(
                    [('ITT', values, '#1f77b4')], '', '\u00b0C',
                    cursor=0, show_max=True, flight_time=True,
                )
                label = self.plot._selection_artists[-1]
                bounds = label.get_window_extent(self.plot.get_renderer())
                self.assertGreaterEqual(bounds.x0, 0)
                self.assertLessEqual(bounds.x1, self.plot.fig.bbox.width)
                self.assertLessEqual(bounds.y1, self.plot.fig.bbox.height)


class ChartFilterButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.button = ChartFilterButton(TelemetryTab.CHARTS)
        self.button.show()
        self.app.processEvents()
        self.received = []
        self.button.selection_changed.connect(self.received.append)

    def tearDown(self):
        self.button.menu().hide()
        self.button.close()
        self.button.deleteLater()
        self.app.processEvents()

    def test_checkboxes_default_to_all_selected_in_chart_order(self):
        self.assertEqual(
            self.button.selected_keys(), tuple(key for key, *_ in TelemetryTab.CHARTS),
        )
        self.assertEqual(self.button.text(), 'Charts (9/9)')

    def test_menu_stays_open_for_multiple_checkbox_changes(self):
        self.button.menu().popup(
            self.button.mapToGlobal(QPoint(0, self.button.height()))
        )
        self.app.processEvents()
        for key in ('n1', 'n2'):
            QTest.mouseClick(self.button.checkboxes[key], Qt.LeftButton)
            self.assertTrue(self.button.menu().isVisible())
            self.assertNotIn(key, self.button.selected_keys())
        self.assertEqual(self.button.text(), 'Charts (7/9)')
        self.assertEqual(len(self.received), 2)

    def test_bulk_selection_emits_once_and_preserves_menu(self):
        self.button.menu().popup(
            self.button.mapToGlobal(QPoint(0, self.button.height()))
        )
        self.app.processEvents()
        QTest.mouseClick(self.button.clear_all, Qt.LeftButton)
        self.assertEqual(self.received, [()])
        self.assertEqual(self.button.text(), 'Charts (0/9)')
        self.assertTrue(self.button.menu().isVisible())
        QTest.mouseClick(self.button.select_all, Qt.LeftButton)
        self.assertEqual(len(self.received), 2)
        self.assertEqual(len(self.button.selected_keys()), 9)
        self.assertTrue(self.button.menu().isVisible())

    def test_filter_menu_contains_only_parameter_checkboxes(self):
        content = self.button.menu().actions()[0].defaultWidget()
        self.assertEqual(
            tuple(checkbox.text() for checkbox in content.findChildren(QCheckBox)),
            tuple(title for _key, title, *_rest in TelemetryTab.CHARTS),
        )


class TelemetrySynchronizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.tab = TelemetryTab()
        self.tab.resize(1180, 950)
        self.tab.show()
        engine = tuple(
            EngineData(
                id=index, flight_id='test', timestamp=f'2026-09-28 11:00:{index:02d}',
                oat=22,
                **{
                    key: 60 + index + number
                    for number, (key, *_rest) in enumerate(self.tab.CHARTS)
                },
            )
            for index in range(12)
        )
        self.tab.load(Flight(id='test', aircraft_id='test', flight_date='',
                             engine_data=engine))
        self.app.processEvents()

    def tearDown(self):
        self.tab.close()
        self.tab.deleteLater()
        self.app.processEvents()

    def assert_synchronized(self, selected):
        self.assertEqual(self.tab.slider.value(), selected)
        self.assertEqual(self.tab.time.text(), f'11:00:{selected:02d}')
        selected_row = (self.tab.instrument.rowCount() - 1) // 2
        self.assertEqual(self.tab.instrument.item(selected_row, 0).text(),
                         f'11:00:{selected:02d}')
        for plot, _title, _unit in self.tab.plots.values():
            self.assertEqual(list(plot._cursor_line.get_xdata()), [selected, selected])
        if self.tab._combined_mode and self.tab.combined_plot._cursor_line is not None:
            self.assertEqual(
                list(self.tab.combined_plot._cursor_line.get_xdata()), [selected, selected],
            )

    def test_default_row_count_is_one_and_user_preference_survives_reload(self):
        self.assertEqual(self.tab.row_count_selector.currentData(), 1)
        self.assertEqual(self.tab.instrument.rowCount(), 1)
        self.tab.row_count_selector.setCurrentIndex(
            self.tab.row_count_selector.findData(7)
        )
        self.tab.load(self.tab.flight)
        self.assertEqual(self.tab.instrument.rowCount(), 7)

    def test_focus_parameter_opens_only_one_large_chart_and_keeps_timestamp(self):
        self.tab.slider.setValue(6)
        for key, title, _unit, _color in TELEMETRY_PARAMETERS:
            with self.subTest(parameter=key):
                self.assertTrue(self.tab.focus_parameter(key))
                self.app.processEvents()
                self.assertEqual(self.tab.chart_filter.selected_keys(), (key,))
                self.assertTrue(self.tab.combine_charts_button.isChecked())
                self.assertFalse(self.tab.combined_card.isHidden())
                self.assertEqual(set(self.tab.combined_plot.parameter_lines), {title})
                self.assertEqual(len(self.tab.combined_plot.legend.get_texts()), 1)
                self.assert_synchronized(6)

    def test_extra_engine_parameters_are_available_on_demand_and_reload_correctly(self):
        flight = replace(
            self.tab.flight,
            engine_data=tuple(
                replace(point, tq=30 + index)
                for index, point in enumerate(self.tab.data)
            ),
        )
        self.tab.load(flight)
        self.assertEqual(len(self.tab.plots), 9)
        for key, title, expected in (('oat', 'OAT', 22), ('tq', 'TORQUE', 30)):
            with self.subTest(parameter=key):
                self.assertTrue(self.tab.focus_parameter(key))
                self.assertEqual(self.tab.chart_filter.selected_keys(), (key,))
                self.assertEqual(
                    self.tab.combined_plot.parameter_lines[title].get_ydata()[0], expected,
                )
        self.assertEqual(len(self.tab.plots), 11)
        self.tab.load(replace(flight, engine_data=()))
        self.assertEqual(self.tab.combined_plot._point_count, 0)
        self.assertIn('NO DATA', self.tab.combined_plot.legend.get_texts()[0].get_text())

    def test_gps_parameters_match_timestamps_and_leave_unrecorded_seconds_empty(self):
        gps = tuple(
            GPSData(id=index, flight_id='test', timestamp=f'11:00:{index:02d}',
                    ias=100 + index, alt_ind=1000 + index)
            for index in (3, 7)
        )
        self.tab.load(replace(self.tab.flight, data_log=gps))
        for key, title, expected in (('ias', 'IAS', 103), ('alt_ind', 'ALTITUDE', 1003)):
            with self.subTest(parameter=key):
                self.assertTrue(self.tab.focus_parameter(key))
                line = self.tab.combined_plot.parameter_lines[title]
                values = line.get_ydata()
                self.assertEqual(len(values), 12)
                self.assertEqual(values[3], expected)
                self.assertTrue(isnan(values[0]))
                self.assertTrue(isnan(values[4]))
                click_time(self.tab.combined_plot, 7)
                self.assert_synchronized(7)

    def test_gps_only_flight_supports_focused_chart_and_clock_without_engine_values(self):
        gps = tuple(
            GPSData(id=index, flight_id='test', timestamp=f'11:00:{index:02d}',
                    ias=100 + index)
            for index in range(3)
        )
        self.tab.load(replace(self.tab.flight, engine_data=(), data_log=gps))
        self.assertTrue(self.tab.focus_parameter('ias'))
        self.tab.slider.setValue(2)
        self.assertEqual(self.tab.time.text(), '11:00:02')
        self.assertEqual(self.tab.instrument.item(0, 0).text(), '11:00:02')
        self.assertEqual(self.tab.instrument.item(0, 1).text(), '\N{EM DASH}')
        self.assertEqual(
            list(self.tab.combined_plot.parameter_lines['IAS'].get_ydata()),
            [100, 101, 102],
        )

    def test_missing_parameter_has_no_fake_maximum_and_invalid_key_is_ignored(self):
        self.assertTrue(self.tab.focus_parameter('ias'))
        self.assertIn('NO DATA', self.tab.combined_plot.legend.get_texts()[0].get_text())
        self.assertFalse(self.tab.focus_parameter('unknown'))
        self.assertEqual(self.tab.chart_filter.selected_keys(), ('ias',))

    def test_extra_chart_colors_are_unique_and_do_not_change_default_class_parameters(self):
        parameters = (*TELEMETRY_PARAMETERS, *OVERVIEW_TELEMETRY_PARAMETERS)
        self.assertEqual(len({color for *_metadata, color in parameters}), len(parameters))
        self.tab.focus_parameter('oat')
        self.assertEqual(len(TelemetryTab.CHARTS), 9)
        self.assertEqual(len(self.tab.CHARTS), 10)

    def test_controls_share_toolbar_between_rows_and_charts_above_slider(self):
        rows = self.tab.row_count_selector.geometry()
        charts = self.tab.chart_filter.geometry()
        previous = self.tab.prev.geometry()
        time = self.tab.time.geometry()
        following = self.tab.next.geometry()
        self.assertLess(rows.right(), previous.left())
        self.assertLess(previous.right(), time.left())
        self.assertLess(time.right(), following.left())
        self.assertLess(following.right(), charts.left())
        self.assertEqual(previous.center().y(), charts.center().y())
        self.assertLess(previous.bottom(), self.tab.slider.y())

    def test_arrow_buttons_keep_timeline_synchronized(self):
        self.tab.slider.setValue(5)
        self.tab.prev.click()
        self.assert_synchronized(4)
        self.tab.next.click()
        self.assert_synchronized(5)

    def test_combine_button_is_outside_filter_and_immediately_to_its_left(self):
        button = self.tab.combine_charts_button
        self.assertIs(button.parentWidget(), self.tab)
        self.assertIsNot(button.parentWidget(), self.tab.chart_filter.menu())
        self.assertLess(self.tab.next.geometry().right(), button.geometry().left())
        self.assertLess(button.geometry().right(), self.tab.chart_filter.geometry().left())
        self.assertEqual(
            button.geometry().center().y(), self.tab.chart_filter.geometry().center().y(),
        )
        self.assertLess(button.geometry().bottom(), self.tab.slider.y())

    def test_external_combine_button_toggles_views_without_resetting_filters_or_time(self):
        self.tab.chart_filter.set_selected(('itt', 'fuel_press'))
        self.tab.slider.setValue(6)
        button = self.tab.combine_charts_button
        self.assertEqual(button.text(), 'Combine Charts')
        QTest.mouseClick(button, Qt.LeftButton)
        self.app.processEvents()
        self.assertTrue(button.isChecked())
        self.assertTrue(self.tab._combined_mode)
        self.assertEqual(button.text(), 'Separate Charts')
        self.assertFalse(self.tab.combined_card.isHidden())
        self.assertEqual(self.tab.chart_filter.selected_keys(), ('itt', 'fuel_press'))
        self.assert_synchronized(6)
        self.tab.chart_filter.set_selected(('itt',))
        self.assertTrue(button.isChecked())
        QTest.mouseClick(button, Qt.LeftButton)
        self.app.processEvents()
        self.assertFalse(button.isChecked())
        self.assertFalse(self.tab._combined_mode)
        self.assertEqual(button.text(), 'Combine Charts')
        self.assertEqual(self.tab.chart_filter.selected_keys(), ('itt',))
        self.assertTrue(self.tab.combined_card.isHidden())
        self.assertFalse(self.tab.chart_cards['itt'].isHidden())
        self.assert_synchronized(6)

    def test_every_chart_click_synchronizes_all_charts_slider_and_instruments(self):
        for number, (key, (plot, _title, _unit)) in enumerate(self.tab.plots.items()):
            with self.subTest(chart=key):
                selected = (number + 2) % 12
                click_time(plot, selected)
                self.assert_synchronized(selected)

    def test_maximum_label_synchronizes_all_charts(self):
        plot, _title, _unit = self.tab.plots['itt']
        annotation = plot._selection_artists[-1]
        bounds = annotation.get_window_extent(plot.get_renderer())
        click_canvas(plot, (bounds.x0 + bounds.x1) / 2, (bounds.y0 + bounds.y1) / 2)
        self.assert_synchronized(11)

    def test_slider_selection_keeps_card_dimensions_and_chart_colors(self):
        cards = {key: plot.parentWidget().size()
                 for key, (plot, *_rest) in self.tab.plots.items()}
        self.tab.slider.setValue(7)
        self.assert_synchronized(7)
        for key, _title, _unit, color in self.tab.CHARTS:
            plot = self.tab.plots[key][0]
            self.assertEqual(plot.parentWidget().size(), cards[key])
            self.assertEqual(plot.parentWidget().layout.contentsMargins().left(), 16)
            self.assertEqual(plot.minimumHeight(), 220)
            self.assertEqual(plot.ax.lines[0].get_color(), color)

    def test_all_row_counts_keep_selected_timestamp_highlighted_and_centered(self):
        self.tab.slider.setValue(5)
        for count in self.tab.INSTRUMENT_ROW_COUNTS:
            with self.subTest(count=count):
                self.tab.row_count_selector.setCurrentIndex(
                    self.tab.row_count_selector.findData(count)
                )
                self.assertEqual(self.tab.instrument.rowCount(), count)
                self.assert_synchronized(5)
                selected_row = (count - 1) // 2
                for row in range(count):
                    item = self.tab.instrument.item(row, 0)
                    sample_index = 5 + row - selected_row
                    expected = (
                        f'11:00:{sample_index:02d}'
                        if 0 <= sample_index < len(self.tab.data)
                        else '\N{EM DASH}'
                    )
                    self.assertEqual(item.text(), expected)
                    self.assertEqual(
                        item.background().color().name(),
                        '#dbeafe' if row == selected_row else '#ffffff',
                    )
                    self.assertEqual(item.font().bold(), row == selected_row)
                self.assertEqual(
                    self.tab.instrument.height(),
                    58 + count * 32 + self.tab.instrument.frameWidth() * 2,
                )

    def test_row_window_uses_placeholders_at_recording_boundaries(self):
        largest_count = max(self.tab.INSTRUMENT_ROW_COUNTS)
        selected_row = (largest_count - 1) // 2
        self.tab.row_count_selector.setCurrentIndex(
            self.tab.row_count_selector.findData(largest_count)
        )
        self.tab.slider.setValue(0)
        for row in range(selected_row):
            self.assertEqual(self.tab.instrument.item(row, 0).text(), '\N{EM DASH}')
        self.assertEqual(self.tab.instrument.item(selected_row, 0).text(), '11:00:00')
        self.tab.slider.setValue(11)
        self.assertEqual(self.tab.instrument.item(selected_row, 0).text(), '11:00:11')
        for row in range(selected_row + 1, largest_count):
            self.assertEqual(self.tab.instrument.item(row, 0).text(), '\N{EM DASH}')
        self.tab.row_count_selector.setCurrentIndex(
            self.tab.row_count_selector.findData(1)
        )
        self.assertEqual(self.tab.instrument.item(0, 0).text(), '11:00:11')

    def test_filtered_charts_reflow_in_original_order_and_keep_card_height(self):
        heights = {key: card.height() for key, card in self.tab.chart_cards.items()}
        self.tab.chart_filter.set_selected(('fuel_press', 'itt', 'nr'))
        self.app.processEvents()
        expected = ('nr', 'itt', 'fuel_press')
        for index, key in enumerate(expected):
            self.assertIs(
                self.tab.chart_grid.itemAtPosition(index // 2, index % 2).widget(),
                self.tab.chart_cards[key],
            )
            self.assertFalse(self.tab.chart_cards[key].isHidden())
            self.assertEqual(self.tab.chart_cards[key].height(), heights[key])
        for key in ('n1', 'n2', 'eng_ot', 'eng_op', 'xmsn_ot', 'xmsn_op'):
            self.assertTrue(self.tab.chart_cards[key].isHidden())
        self.assertTrue(self.tab.chart_empty_state.isHidden())
        self.assertEqual(self.tab.chart_filter.text(), 'Charts (3/9)')

    def test_filtering_does_not_rebuild_plot_data_or_reset_selection(self):
        self.tab.slider.setValue(6)
        plots = {key: plot for key, (plot, *_rest) in self.tab.plots.items()}
        with patch.object(self.tab, '_draw_charts', wraps=self.tab._draw_charts) as draw:
            self.tab.chart_filter.set_selected(('itt', 'eng_ot'))
            self.tab.row_count_selector.setCurrentIndex(
                self.tab.row_count_selector.findData(7)
            )
        draw.assert_not_called()
        self.assert_synchronized(6)
        for key, (plot, *_rest) in self.tab.plots.items():
            self.assertIs(plot, plots[key])
        click_time(self.tab.plots['itt'][0], 8)
        self.assert_synchronized(8)
        self.tab.chart_filter.set_selected(self.tab.chart_cards)
        self.app.processEvents()
        self.assert_synchronized(8)

    def test_clear_all_has_empty_state_and_select_all_restores_charts(self):
        self.tab.chart_filter.set_selected(())
        self.app.processEvents()
        self.assertFalse(self.tab.chart_empty_state.isHidden())
        self.assertTrue(all(card.isHidden() for card in self.tab.chart_cards.values()))
        self.tab.chart_filter.select_all.click()
        self.app.processEvents()
        self.assertTrue(self.tab.chart_empty_state.isHidden())
        self.assertTrue(all(not card.isHidden() for card in self.tab.chart_cards.values()))
        self.assertEqual(self.tab.chart_filter.text(), 'Charts (9/9)')

    def test_empty_flight_and_reload_preserve_display_preferences(self):
        self.tab.row_count_selector.setCurrentIndex(
            self.tab.row_count_selector.findData(3)
        )
        self.tab.chart_filter.set_selected(('n1', 'itt'))
        self.tab.load(Flight(id='empty', aircraft_id='test', flight_date=''))
        self.assertEqual(self.tab.instrument.rowCount(), 3)
        self.assertTrue(all(
            self.tab.instrument.item(row, column).text() == '\N{EM DASH}'
            for row in range(3) for column in range(self.tab.instrument.columnCount())
        ))
        self.assertEqual(self.tab.chart_filter.selected_keys(), ('n1', 'itt'))
        self.assertFalse(self.tab.chart_cards['itt'].isHidden())
        self.assertTrue(self.tab.chart_cards['fuel_press'].isHidden())

    def test_combined_view_has_all_colors_legend_and_separate_unit_scales(self):
        self.tab.combine_charts_button.setChecked(True)
        self.app.processEvents()
        self.assertFalse(self.tab.combined_card.isHidden())
        self.assertTrue(all(card.isHidden() for card in self.tab.chart_cards.values()))
        self.assertIs(self.tab.chart_grid.itemAtPosition(0, 0).widget(),
                      self.tab.combined_card)
        plot = self.tab.combined_plot
        self.assertEqual(set(plot.unit_axes), {'%', '\u00b0C', 'psi'})
        self.assertEqual(len(plot.fig.axes), 3)
        self.assertEqual(len(plot.legend.get_texts()), 9)
        for _key, title, unit, color in self.tab.CHARTS:
            self.assertEqual(plot.parameter_lines[title].get_color(), color)
            self.assertIs(plot.parameter_lines[title].axes, plot.unit_axes[unit])

    def test_every_parameter_has_a_unique_color_in_both_views(self):
        colors = [color.lower() for _key, _title, _unit, color in self.tab.CHARTS]
        self.assertEqual(len(colors), len(set(colors)))
        self.tab.combine_charts_button.setChecked(True)
        self.app.processEvents()
        for key, title, _unit, color in self.tab.CHARTS:
            with self.subTest(parameter=key):
                self.assertEqual(self.tab.plots[key][0].ax.lines[0].get_color(), color)
                self.assertEqual(
                    self.tab.combined_plot.parameter_lines[title].get_color(), color,
                )

    def test_combined_chart_is_taller_without_resizing_individual_cards(self):
        heights = {key: card.height() for key, card in self.tab.chart_cards.items()}
        self.tab.combine_charts_button.setChecked(True)
        for _ in range(3):
            self.app.processEvents()
        self.assertEqual(self.tab.combined_card.height(), 640)
        self.assertGreaterEqual(self.tab.combined_plot.height(), 560)
        self.assertGreater(self.tab.combined_plot.ax.bbox.height, 400)
        self.tab.combine_charts_button.setChecked(False)
        self.app.processEvents()
        self.assertEqual(
            {key: card.height() for key, card in self.tab.chart_cards.items()}, heights,
        )

    def test_combined_area_click_synchronizes_slider_all_charts_and_table(self):
        self.tab.combine_charts_button.setChecked(True)
        self.app.processEvents()
        click_time(self.tab.combined_plot, 4.6)
        self.assert_synchronized(5)
        self.tab.slider.setValue(8)
        self.assert_synchronized(8)

    def test_combined_legend_is_larger_at_the_top_without_overlapping_chart(self):
        self.tab.combine_charts_button.setChecked(True)
        for _ in range(3):
            self.app.processEvents()
        plot = self.tab.combined_plot
        plot.draw()
        self.assertTrue(all(
            text.get_fontsize() == 10 for text in plot.legend.get_texts()
        ))
        bounds = plot.legend.get_window_extent(plot.get_renderer())
        self.assertGreaterEqual(bounds.x0, 0)
        self.assertLessEqual(bounds.x1, plot.fig.bbox.width)
        self.assertLessEqual(bounds.y1, plot.fig.bbox.height)
        self.assertLess(plot.fig.bbox.height - bounds.y1, 5)
        self.assertGreater(bounds.y0, plot.ax.bbox.y1)

    def test_combined_maximum_legend_entry_selects_exact_timestamp(self):
        self.tab.combine_charts_button.setChecked(True)
        self.app.processEvents()
        plot = self.tab.combined_plot
        text = plot.legend.get_texts()[3]
        bounds = text.get_window_extent(plot.get_renderer())
        click_canvas(plot, (bounds.x0 + bounds.x1) / 2, (bounds.y0 + bounds.y1) / 2)
        self.assert_synchronized(11)

    def test_combined_filter_and_return_to_individual_cards_preserve_selection(self):
        self.tab.slider.setValue(6)
        self.tab.combine_charts_button.setChecked(True)
        self.tab.chart_filter.set_selected(('itt', 'fuel_press'))
        self.app.processEvents()
        self.assertEqual(
            set(self.tab.combined_plot.parameter_lines), {'ITT', 'FUEL PRESS'},
        )
        self.assertEqual(set(self.tab.combined_plot.unit_axes), {'\u00b0C', 'psi'})
        self.assert_synchronized(6)
        self.tab.combine_charts_button.setChecked(False)
        self.app.processEvents()
        self.assertTrue(self.tab.combined_card.isHidden())
        self.assertFalse(self.tab.chart_cards['itt'].isHidden())
        self.assertFalse(self.tab.chart_cards['fuel_press'].isHidden())
        self.assertTrue(self.tab.chart_cards['n1'].isHidden())
        self.assert_synchronized(6)

    def test_combined_empty_flight_and_clear_all_do_not_create_fake_samples(self):
        self.tab.combine_charts_button.setChecked(True)
        self.tab.load(Flight(id='empty', aircraft_id='test', flight_date=''))
        self.assertEqual(self.tab.combined_plot._point_count, 0)
        self.assertEqual(len(self.tab.combined_plot.legend.get_texts()), 9)
        self.assertTrue(all('NO DATA' in text.get_text()
                            for text in self.tab.combined_plot.legend.get_texts()))
        self.tab.chart_filter.set_selected(())
        self.assertTrue(self.tab.combined_card.isHidden())
        self.assertFalse(self.tab.chart_empty_state.isHidden())

    def test_combined_navigation_keeps_slider_table_and_maximum_click_synchronized(self):
        self.tab.combine_charts_button.setChecked(True)
        self.app.processEvents()
        plot = self.tab.combined_plot
        self.tab.combined_toolbar.zoom_in_action.trigger()
        self.assert_synchronized(0)
        self.tab.combined_toolbar.pan_action.trigger()
        click_time(plot, 4)
        self.assert_synchronized(0)
        self.tab.combined_toolbar.pan_action.trigger()
        plot.draw()
        text = plot.legend.get_texts()[3]
        bounds = text.get_window_extent(plot.get_renderer())
        click_canvas(plot, (bounds.x0 + bounds.x1) / 2, (bounds.y0 + bounds.y1) / 2)
        self.assert_synchronized(11)
        self.assertLessEqual(plot.ax.get_xlim()[0], 11)
        self.assertGreaterEqual(plot.ax.get_xlim()[1], 11)
        self.tab.combined_toolbar.home()
        self.assert_synchronized(11)
        self.assertEqual(plot.ax.get_xlim(), (0, 11))

    def test_zoom_is_only_combined_and_new_flight_restores_original_view(self):
        self.tab.combine_charts_button.setChecked(True)
        self.app.processEvents()
        original = {key: plot.ax.get_xlim() for key, (plot, *_rest) in self.tab.plots.items()}
        wheel_canvas(self.tab.combined_plot, 120)
        zoomed = self.tab.combined_plot.ax.get_xlim()
        self.tab.chart_filter.set_selected(('itt', 'fuel_press'))
        self.assertEqual(self.tab.combined_plot.ax.get_xlim(), zoomed)
        self.tab.combine_charts_button.setChecked(False)
        self.assertEqual(
            {key: plot.ax.get_xlim() for key, (plot, *_rest) in self.tab.plots.items()}, original,
        )
        self.tab.combine_charts_button.setChecked(True)
        self.assertEqual(self.tab.combined_plot.ax.get_xlim(), zoomed)
        self.tab.combined_toolbar.pan_action.trigger()
        self.tab.load(self.tab.flight)
        self.assertFalse(self.tab.combined_toolbar.mode)
        self.assertEqual(self.tab.combined_plot.ax.get_xlim(), (0, 11))

    def test_new_flight_in_separate_mode_does_not_inherit_previous_combined_zoom(self):
        self.tab.combine_charts_button.setChecked(True)
        self.app.processEvents()
        self.tab.combined_plot.zoom_view(0.2)
        self.tab.combine_charts_button.setChecked(False)
        self.tab.load(replace(self.tab.flight, id='another-flight'))
        self.tab.combine_charts_button.setChecked(True)
        self.assertEqual(self.tab.combined_plot.ax.get_xlim(), (0, 11))


if __name__ == '__main__':
    unittest.main()
