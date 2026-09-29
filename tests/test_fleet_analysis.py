"""Fleet trends use synthetic in-memory records; no application data is read."""

import os
import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QDate, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QFontDatabase, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton, QWidget
from matplotlib.backend_bases import MouseEvent

from helink.controllers.aircraft_controller import AircraftController
from helink.controllers.flight_controller import FlightController
from helink.controllers.navigation_controller import NavigationController
from helink.repositories.aircraft_repository import AircraftRepository
from helink.repositories.database_manager import SCHEMA
from helink.repositories.flight_repository import FlightRepository
from helink.services.aircraft_trend_summary import summarise_aircraft_trends
from helink.ui.pages.dashboard_page import DashboardPage
from helink.ui.pages.fleet_analysis_page import FleetAnalysisPage
from helink.ui.theme import STYLE


def application():
    app = QApplication.instance() or QApplication([])
    font = Path('C:/Windows/Fonts/segoeui.ttf')
    if os.name == 'nt' and font.exists():
        QFontDatabase.addApplicationFont(str(font))
    app.setStyleSheet(STYLE)
    return app


class TrendFixture:
    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)
        self.connection.executescript(SCHEMA)
        self.connection.executemany(
            'INSERT INTO aircraft(id,registration,model,serial_number) VALUES(?,?,?,?)',
            (
                ('a', 'TEST-A', 'Bell 505', '001'),
                ('b', 'TEST-B', 'Bell 505', '002'),
                ('c', 'TEST-C', 'H125', '003'),
            ),
        )
        self.connection.executemany(
            'INSERT INTO flights(id,aircraft_id,flight_date,departure_time) VALUES(?,?,?,?)',
            (
                ('a1', 'a', '2026-09-01', '08:00:00'),
                ('a2', 'a', '2026-09-01', '14:00:00'),
                ('a3', 'a', '2026-09-10', '08:00:00'),
                ('a4', 'a', '2026-09-15', '08:00:00'),
                ('b1', 'b', '2026-09-01', '08:00:00'),
                ('b2', 'b', '2026-09-10', '08:00:00'),
            ),
        )
        rows = (
            ('a1', 0, 80), ('a2', 0, 100), ('a2', 1, 100), ('a2', 2, 100),
            ('a3', 0, 105), ('a3', 1, 115), ('a4', 0, None),
            ('b1', 0, 70), ('b2', 0, 90),
        )
        self.connection.executemany(
            """INSERT INTO engine_data(
                   flight_id,seq,timestamp,eng_ot,itt,eng_op,n1,n2,nr,
                   xmsn_ot,xmsn_op,fuel_press,oat,tq)
               VALUES(?,?, '08:00:00', ?, 700, 50, 95, 100, 100, 70, 45, 15, 20, 60)""",
            rows,
        )
        self.connection.execute(
            "INSERT INTO gps_data(flight_id,seq,timestamp,latitude,longitude,ias,alt_ind)"
            " VALUES('a4',0,'08:00:00',38,-8,120,2000)"
        )
        self.database = SimpleNamespace(connection=self.connection)
        self.repository = AircraftRepository(self.database)
        self.controller = AircraftController(self.repository)


class DailyTrendQueryTests(TrendFixture, unittest.TestCase):
    def test_multiple_flights_on_a_day_use_sample_weighted_average(self):
        queries = []
        self.connection.set_trace_callback(queries.append)
        days = self.controller.daily_parameter_trends(('a', 'b'), 'eng_ot')
        self.assertEqual(len(queries), 1)
        self.assertEqual(
            [(day.aircraft_id, day.flight_date) for day in days],
            [('a', '2026-09-01'), ('b', '2026-09-01'),
             ('a', '2026-09-10'), ('b', '2026-09-10')],
        )
        self.assertEqual(days[0].average, 95)
        self.assertEqual(days[0].maximum, 100)
        self.assertEqual(days[0].flight_count, 2)
        self.assertEqual(days[0].sample_count, 4)

    def test_scope_and_inclusive_date_bounds(self):
        days = self.controller.daily_parameter_trends(
            ('a',), 'eng_ot', start_date='2026-09-10', end_date='2026-09-10',
        )
        self.assertEqual(len(days), 1)
        self.assertEqual(days[0].average, 110)
        self.assertEqual(days[0].maximum, 115)
        self.assertEqual(days[0].aircraft_id, 'a')

    def test_null_text_and_infinity_are_omitted_but_real_zero_is_valid(self):
        self.connection.executemany(
            "INSERT INTO engine_data(flight_id,seq,eng_ot) VALUES('a4',?,?)",
            ((1, 'UNK'), (2, float('inf')), (3, float('-inf'))),
        )
        days = self.controller.daily_parameter_trends(('a',), 'eng_ot')
        self.assertEqual(len(days), 2)
        self.connection.execute(
            "INSERT INTO engine_data(flight_id,seq,eng_ot) VALUES('a4',4,0)"
        )
        day = self.controller.daily_parameter_trends(('a',), 'eng_ot')[-1]
        self.assertEqual(day.average, 0)
        self.assertEqual(day.maximum, 0)
        self.assertEqual(day.sample_count, 1)

    def test_gps_parameters_use_gps_data_not_engine_rows(self):
        days = self.controller.daily_parameter_trends(('a',), 'ias')
        self.assertEqual(len(days), 1)
        self.assertEqual(days[0].flight_date, '2026-09-15')
        self.assertEqual(days[0].average, 120)
        self.assertEqual(days[0].sample_count, 1)

    def test_missing_aircraft_or_parameter_values_produce_no_points(self):
        self.assertEqual(self.controller.daily_parameter_trends(('c',), 'eng_ot'), [])
        self.assertEqual(self.controller.daily_parameter_trends(('missing',), 'eng_ot'), [])
        queries = []
        self.connection.set_trace_callback(queries.append)
        self.assertEqual(self.controller.daily_parameter_trends((), 'eng_ot'), [])
        self.assertEqual(queries, [])

    def test_invalid_parameter_or_date_is_rejected_before_database_query(self):
        queries = []
        self.connection.set_trace_callback(queries.append)
        with self.assertRaises(ValueError):
            self.controller.daily_parameter_trends(('a',), 'eng_ot); DROP TABLE flights;')
        with self.assertRaises(ValueError):
            self.controller.daily_parameter_trends(
                ('a',), 'eng_ot', start_date='2026-09-20', end_date='2026-09-01',
            )
        with self.assertRaises(ValueError):
            self.controller.daily_parameter_trends(('a',), 'eng_ot', start_date='invalid')
        self.assertEqual(queries, [])

    def test_picker_is_lightweight_and_keeps_aircraft_identity(self):
        queries = []
        self.connection.set_trace_callback(queries.append)
        aircraft = self.controller.list_for_analysis()
        self.assertEqual(len(queries), 1)
        self.assertNotIn('ALERTS', queries[0].upper())
        self.assertNotIn('ENGINE_DATA', queries[0].upper())
        self.assertEqual(aircraft[0].serial_number, '001')
        self.assertEqual([item.flight_count for item in aircraft], [4, 2, 0])

    def test_period_summary_uses_first_and_latest_daily_value_and_peak_max(self):
        days = self.controller.daily_parameter_trends(('a', 'b'), 'eng_ot')
        avg = summarise_aircraft_trends(reversed(days))
        self.assertEqual(avg['a'].first_value, 95)
        self.assertEqual(avg['a'].last_value, 110)
        self.assertEqual(avg['a'].maximum, 115)
        self.assertEqual(avg['a'].day_count, 2)
        maximum = self.controller.trend_summaries(days, 'maximum')
        self.assertEqual(maximum['a'].first_value, 100)
        self.assertEqual(maximum['a'].last_value, 115)
        with self.assertRaises(ValueError):
            summarise_aircraft_trends(days, 'invalid')

    def test_every_available_parameter_can_be_queried(self):
        from helink.ui.pages.fleet_analysis_page import PARAMETERS
        for key, *_ in PARAMETERS:
            with self.subTest(parameter=key):
                self.controller.daily_parameter_trends(('a', 'b'), key)

    def test_daily_flights_are_separate_sorted_and_loaded_in_one_query(self):
        queries = []
        self.connection.set_trace_callback(queries.append)
        flights = self.controller.parameter_flights_for_day('a', '2026-09-01', 'eng_ot')
        self.assertEqual(len(queries), 1)
        self.assertEqual([flight.flight_id for flight in flights], ['a1', 'a2'])
        self.assertEqual([flight.departure_time for flight in flights], ['08:00:00', '14:00:00'])
        self.assertEqual([flight.average for flight in flights], [80, 100])
        self.assertEqual([flight.maximum for flight in flights], [80, 100])
        self.assertEqual([flight.sample_count for flight in flights], [1, 3])
        self.assertTrue(all(flight.aircraft_id == 'a' for flight in flights))

    def test_flight_breakdown_keeps_flights_without_sensor_values(self):
        flights = self.controller.parameter_flights_for_day('a', '2026-09-15', 'eng_ot')
        self.assertEqual(len(flights), 1)
        self.assertEqual(flights[0].flight_id, 'a4')
        self.assertIsNone(flights[0].average)
        self.assertIsNone(flights[0].maximum)
        self.assertEqual(flights[0].sample_count, 0)

    def test_flight_breakdown_filters_invalid_values_but_includes_zero(self):
        self.connection.executemany(
            "INSERT INTO engine_data(flight_id,seq,eng_ot) VALUES('a1',?,?)",
            ((1, 'UNK'), (2, float('inf')), (3, float('-inf')), (4, None), (5, 0)),
        )
        flight = self.controller.parameter_flights_for_day('a', '2026-09-01', 'eng_ot')[0]
        self.assertEqual(flight.average, 40)
        self.assertEqual(flight.maximum, 80)
        self.assertEqual(flight.sample_count, 2)

    def test_flight_breakdown_uses_gps_values_for_gps_parameters(self):
        flight, = self.controller.parameter_flights_for_day('a', '2026-09-15', 'ias')
        self.assertEqual(flight.average, 120)
        self.assertEqual(flight.maximum, 120)
        self.assertEqual(flight.sample_count, 1)

    def test_daily_flight_query_rejects_invalid_date_or_parameter(self):
        queries = []
        self.connection.set_trace_callback(queries.append)
        with self.assertRaises(ValueError):
            self.controller.parameter_flights_for_day('a', 'invalid', 'eng_ot')
        with self.assertRaises(ValueError):
            self.controller.parameter_flights_for_day('a', '2026-09-01', 'invalid')
        self.assertEqual(queries, [])


class FleetAnalysisPageTests(TrendFixture, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        super().setUp()
        self.page = FleetAnalysisPage(self.controller)
        self.addCleanup(self.page.deleteLater)
        self.addCleanup(self.page.close)
        self.page.resize(1200, 850)
        self.page.show()
        self.page.load('a')
        self.page.parameter.setCurrentIndex(self.page.parameter.findData('eng_ot'))
        self.app.processEvents()

    def test_single_aircraft_default_preserves_units_dates_and_identity(self):
        self.assertEqual(self.page.aircraft_selector.selected_ids(), ('a',))
        self.assertEqual(len(self.page.plot.series), 1)
        self.assertEqual(self.page.comparison.rowCount(), 1)
        self.assertEqual(self.page.comparison.item(0, 2).text(), '95.0')
        self.assertEqual(self.page.comparison.item(0, 4).text(), '115.0')
        self.assertIn('SN 001', self.page.context.text())
        self.assertIn('\u00b0C', self.page.plot.ax.get_ylabel())
        _, _, dates, _ = self.page.plot.series[0]
        self.assertEqual(dates[1] - dates[0], 9)

    def test_initial_single_aircraft_analysis_fits_without_vertical_scrolling(self):
        for _ in range(3):
            self.app.processEvents()
        self.assertEqual(self.page.scroll.verticalScrollBar().maximum(), 0)
        self.assertFalse(self.page.scroll.verticalScrollBar().isVisible())
        self.assertFalse(self.page.scroll.horizontalScrollBar().isVisible())
        self.assertEqual(self.page.plot.height(), self.page.plot.CHART_HEIGHT)
        self.assertLessEqual(self.page.plot.height(), 400)
        self.assertEqual(self.page.comparison.verticalScrollBar().maximum(), 0)

    def test_page_scrollbars_appear_only_when_needed_in_both_analysis_modes(self):
        for allow_comparison in (True, False):
            with self.subTest(allow_comparison=allow_comparison):
                self.page.load('a', allow_comparison=allow_comparison)
                self.page.resize(1200, 850)
                for _ in range(3):
                    self.app.processEvents()
                self.assertEqual(
                    self.page.scroll.verticalScrollBarPolicy(), Qt.ScrollBarAsNeeded,
                )
                self.assertEqual(
                    self.page.scroll.horizontalScrollBarPolicy(), Qt.ScrollBarAsNeeded,
                )
                scrollbar = self.page.scroll.verticalScrollBar()
                self.assertEqual(scrollbar.maximum(), 0)
                self.assertFalse(scrollbar.isVisible())
                original_height = self.page.plot.height()
                self.page.resize(1200, 550)
                for _ in range(3):
                    self.app.processEvents()
                self.assertGreater(scrollbar.maximum(), 0)
                self.assertTrue(scrollbar.isVisible())
                self.assertEqual(self.page.plot.height(), original_height)
                self.page.resize(1200, 850)
                for _ in range(3):
                    self.app.processEvents()
                self.assertEqual(scrollbar.maximum(), 0)
                self.assertFalse(scrollbar.isVisible())
                self.assertEqual(self.page.plot.height(), original_height)

    def test_individual_mode_loads_only_its_aircraft_without_a_comparison_selector(self):
        with patch.object(self.controller, 'list_for_analysis') as fleet_query:
            self.page.load('b', allow_comparison=False)
        fleet_query.assert_not_called()
        self.assertEqual([item.id for item in self.page.aircraft], ['b'])
        self.assertEqual(set(self.page.aircraft_selector.checkboxes), {'b'})
        self.assertTrue(self.page.aircraft_selector.isHidden())
        self.assertFalse(self.page.aircraft_selector.isEnabled())
        self.assertTrue(self.page.view_flights.isHidden())
        self.assertEqual(self.page.title.text(), 'Aircraft Analysis')
        self.assertEqual(self.page.back_button.text(), '\N{LEFTWARDS ARROW} Flights')
        self.assertEqual(self.page.comparison_title.text(), 'Period Summary')
        self.assertIn('TEST-B', self.page.context.text())
        self.assertEqual(self.page.comparison.rowCount(), 1)
        self.assertEqual(self.page.comparison.item(0, 0).text(), 'TEST-B')
        self.assertTrue(all(day.aircraft_id == 'b' for day in self.page.days))

    def test_individual_mode_remains_pinned_when_selection_and_filters_change(self):
        self.page.load('b', allow_comparison=False)
        with patch.object(
            self.controller, 'daily_parameter_trends',
            wraps=self.controller.daily_parameter_trends,
        ) as query:
            self.page.aircraft_selector.set_selected(('a', 'c'))
            self.page.parameter.setCurrentIndex(self.page.parameter.findData('itt'))
            self.page.statistic.setCurrentIndex(self.page.statistic.findData('both'))
            self.page.date_filter.mode.setCurrentIndex(1)
            self.page.date_filter.start_edit.setDate(QDate(2026, 9, 10))
            self.page.date_filter.apply()
        self.assertTrue(query.call_args_list)
        self.assertTrue(all(call.args[0] == ('b',) for call in query.call_args_list))
        self.assertEqual(self.page._selected_aircraft_ids(), ('b',))
        self.assertEqual(len(self.page.days), 1)
        self.assertEqual(self.page.days[0].aircraft_id, 'b')
        self.assertEqual(self.page.days[0].flight_date, '2026-09-10')
        self.assertEqual(len(self.page.plot.series), 2)

    def test_individual_day_details_still_show_each_flight_and_daily_totals(self):
        self.page.load('a', allow_comparison=False)
        self.page._show_day(self.page.days[0])
        lines = self.page.day_details.toPlainText().splitlines()
        self.assertEqual(len(lines), 4)
        self.assertIn('Flight 1', lines[1])
        self.assertIn('Flight 2', lines[2])
        self.assertIn('TOTAL', lines[3])
        self.assertIn('AVG 95.0', lines[3])
        self.assertIn('MAX 100.0', lines[3])
        foreign_day = self.controller.daily_parameter_trends(('b',), 'eng_ot')[0]
        with patch.object(self.controller, 'parameter_flights_for_day') as query:
            self.page._show_day(foreign_day)
        query.assert_not_called()
        self.assertEqual(self.page.day_details.toPlainText().splitlines(), lines)

    def test_missing_or_empty_individual_aircraft_never_falls_back_to_the_fleet(self):
        self.page.load('c', allow_comparison=False)
        self.assertEqual(self.page._selected_aircraft_ids(), ('c',))
        self.assertEqual(self.page.days, [])
        self.assertEqual(self.page.comparison.rowCount(), 1)
        self.assertEqual(self.page.plot.series, [])
        self.page.load('missing', allow_comparison=False)
        self.assertEqual(self.page._selected_aircraft_ids(), ())
        self.assertEqual(self.page.days, [])
        self.assertEqual(self.page.comparison.rowCount(), 0)
        self.assertIn('Aircraft unavailable', self.page.context.text())
        with self.assertRaises(ValueError):
            self.page.load(allow_comparison=False)

    def test_reopening_from_fleet_restores_full_comparison_on_the_same_page(self):
        self.page.load('b', allow_comparison=False)
        self.page.date_filter.mode.setCurrentIndex(1)
        self.page.date_filter.start_edit.setDate(QDate(2026, 9, 10))
        self.page.date_filter.apply()
        self.page.load()
        self.assertFalse(self.page.aircraft_selector.isHidden())
        self.assertTrue(self.page.aircraft_selector.isEnabled())
        self.assertEqual(self.page.title.text(), 'Fleet Analysis')
        self.assertEqual(self.page.back_button.text(), '\N{LEFTWARDS ARROW} Fleet')
        self.assertEqual(self.page.comparison_title.text(), 'Period Comparison')
        self.assertEqual(self.page.aircraft_selector.selected_ids(), ('a', 'b', 'c'))
        self.assertEqual(self.page.date_filter.date_range, (None, None))
        self.assertEqual(self.page.comparison.rowCount(), 3)
        self.page.aircraft_selector.set_selected(('a', 'b'))
        self.assertEqual({day.aircraft_id for day in self.page.days}, {'a', 'b'})

    def test_comparison_uses_stable_colors_and_does_not_invent_missing_values(self):
        self.page.aircraft_selector.set_selected(('a', 'b', 'c'))
        self.app.processEvents()
        self.assertEqual(len(self.page.plot.series), 2)
        self.assertEqual(self.page.comparison.rowCount(), 3)
        colors = [line.get_color() for line, *_ in self.page.plot.series]
        self.assertEqual(len(set(colors)), 2)
        color_b = colors[1]
        self.assertEqual(self.page.comparison.item(2, 2).text(), '\u2014')
        self.page.aircraft_selector.set_selected(('b',))
        self.assertEqual(self.page.plot.series[0][0].get_color(), color_b)

    def test_max_or_both_changes_display_without_requerying_telemetry(self):
        self.page.aircraft_selector.set_selected(('a', 'b'))
        with patch.object(self.controller, 'daily_parameter_trends') as query:
            self.page.statistic.setCurrentIndex(self.page.statistic.findData('maximum'))
            self.assertEqual(self.page.comparison.item(0, 2).text(), '100.0')
            self.assertIn('LATEST MAX', self.page.comparison.horizontalHeaderItem(3).text())
            self.page.statistic.setCurrentIndex(self.page.statistic.findData('both'))
        query.assert_not_called()
        self.assertEqual(len(self.page.plot.series), 4)
        self.assertEqual(
            {line.get_linestyle() for line, *_ in self.page.plot.series}, {'-', '--'},
        )

    def test_date_filter_applies_to_every_selected_aircraft(self):
        self.page.aircraft_selector.set_selected(('a', 'b'))
        button = self.page.date_filter
        button.mode.setCurrentIndex(1)
        button.start_edit.setDate(QDate(2026, 9, 1))
        button.apply()
        self.app.processEvents()
        self.assertEqual(len(self.page.days), 2)
        self.assertTrue(all(day.flight_date == '2026-09-01' for day in self.page.days))
        self.assertEqual(self.page.comparison.item(0, 2).text(), '95.0')
        self.assertEqual(self.page.comparison.item(0, 3).text(), '95.0')
        self.assertEqual(self.page.comparison.item(0, 4).text(), '100.0')
        button.reset()
        self.assertEqual(len(self.page.days), 4)

    def test_empty_selection_or_period_shows_a_clear_empty_state(self):
        self.page.aircraft_selector.set_selected(())
        self.app.processEvents()
        self.assertEqual(self.page.days, [])
        self.assertEqual(self.page.plot.series, [])
        self.assertFalse(self.page.view_flights.isVisible())
        self.assertIn('Select an aircraft', self.page.plot.ax.texts[0].get_text())
        self.page.aircraft_selector.set_selected(('c',))
        self.app.processEvents()
        self.assertEqual(self.page.plot.series, [])
        self.assertIn('No recorded values', self.page.plot.ax.texts[0].get_text())

    def test_comparison_omits_change_columns_in_every_statistic_mode(self):
        for statistic in ('average', 'maximum', 'both'):
            with self.subTest(statistic=statistic):
                self.page.statistic.setCurrentIndex(self.page.statistic.findData(statistic))
                self.assertEqual(self.page.comparison.columnCount(), 5)
                headers = [
                    self.page.comparison.horizontalHeaderItem(column).text()
                    for column in range(self.page.comparison.columnCount())
                ]
                self.assertTrue(all('CHANGE' not in header for header in headers))
                self.assertIn('PEAK MAX', headers[4])
                self.assertEqual(self.page.comparison.item(0, 4).text(), '115.0')

    def test_all_fleet_entry_and_single_aircraft_reload_reset_comparison_and_dates(self):
        self.page.load()
        self.assertEqual(self.page.aircraft_selector.selected_ids(), ('a', 'b', 'c'))
        self.page.date_filter.mode.setCurrentIndex(1)
        self.page.date_filter.apply()
        self.page.load('b')
        self.assertEqual(self.page.aircraft_selector.selected_ids(), ('b',))
        self.assertEqual(self.page.date_filter.date_range, (None, None))

    def test_clicking_a_recorded_point_inspects_correct_aircraft_day_and_values(self):
        self.page.aircraft_selector.set_selected(('a', 'b'))
        self.page.plot.draw()
        _, days, dates, values = self.page.plot.series[1]
        x, y = self.page.plot.ax.transData.transform((dates[1], values[1]))
        event = MouseEvent('button_press_event', self.page.plot, x, y, button=1)
        received = []
        self.page.plot.day_selected.connect(received.append)
        self.page.plot._on_click(event)
        self.assertEqual(received, [days[1]])
        self.assertIn('TEST-B', self.page.day_details.toPlainText())
        self.assertIn('10/09/2026', self.page.day_details.toPlainText())
        self.assertIn('AVG 90.0', self.page.day_details.toPlainText())
        self.assertEqual(self.page.comparison.currentRow(), 1)

    def test_flight_and_fleet_navigation_actions_still_work(self):
        flights, back = [], []
        self.page.flights_requested.connect(flights.append)
        self.page.back_requested.connect(lambda: back.append(True))
        self.page.view_flights.click()
        self.assertEqual(flights, ['a'])
        button = next(
            button for button in self.page.findChildren(QPushButton)
            if button.text().endswith('Fleet')
        )
        button.click()
        self.assertEqual(back, [True])

    def test_daily_information_can_be_selected_and_copied(self):
        label = self.page.day_details
        flags = label.textInteractionFlags()
        self.assertTrue(flags & Qt.TextSelectableByMouse)
        self.assertTrue(flags & Qt.TextSelectableByKeyboard)
        self.assertTrue(label.isReadOnly())
        self.page._show_day(self.page.days[0])
        label.setFocus()
        label.selectAll()
        self.assertEqual(
            label.textCursor().selectedText().replace('\u2029', '\n'), label.toPlainText(),
        )
        # The offscreen clipboard is isolated from the user's system clipboard.
        if self.app.platformName() == 'offscreen':
            clipboard = self.app.clipboard()
            original = clipboard.text()
            try:
                QTest.keyClick(label, Qt.Key_C, Qt.ControlModifier)
                self.assertEqual(clipboard.text(), label.toPlainText())
            finally:
                clipboard.setText(original)

    def test_selected_day_lists_each_flight_then_sample_weighted_total(self):
        self.connection.execute(
            "UPDATE flights SET arrival_time='09:00:00' WHERE id='a1'"
        )
        self.connection.execute(
            "UPDATE flights SET arrival_time='15:00:00' WHERE id='a2'"
        )
        self.page._show_day(self.page.days[0])
        lines = self.page.day_details.toPlainText().splitlines()
        self.assertEqual(len(lines), 4)
        self.assertIn('TEST-A', lines[0])
        self.assertIn('ENG OIL TEMP', lines[0])
        self.assertIn('Flight 1', lines[1])
        self.assertIn('08:00:00 \u2192 09:00:00', lines[1])
        self.assertIn('AVG 80.0 \u00b0C', lines[1])
        self.assertIn('MAX 80.0 \u00b0C', lines[1])
        self.assertIn('Flight 2', lines[2])
        self.assertIn('14:00:00 \u2192 15:00:00', lines[2])
        self.assertIn('AVG 100.0 \u00b0C', lines[2])
        self.assertTrue(lines[-1].startswith('TOTAL'))
        self.assertIn('AVG 95.0 \u00b0C', lines[-1])
        self.assertIn('MAX 100.0 \u00b0C', lines[-1])

    def test_flights_without_selected_sensor_are_visible_but_do_not_change_totals(self):
        self.connection.execute(
            "INSERT INTO flights(id,aircraft_id,flight_date,departure_time)"
            " VALUES('no-sensor','a','2026-09-01','16:00:00')"
        )
        self.page._show_day(self.page.days[0])
        lines = self.page.day_details.toPlainText().splitlines()
        self.assertEqual(len(lines), 5)
        self.assertIn('Flight 3', lines[3])
        self.assertIn('AVG \u2014', lines[3])
        self.assertIn('MAX \u2014', lines[3])
        self.assertIn('No recorded values', lines[3])
        self.assertIn('AVG 95.0', lines[-1])

    def test_repeated_day_clicks_reuse_breakdown_and_sensor_change_invalidates_cache(self):
        with patch.object(
            self.controller, 'parameter_flights_for_day',
            wraps=self.controller.parameter_flights_for_day,
        ) as query:
            self.page._show_day(self.page.days[0])
            self.page._show_day(self.page.days[0])
            self.assertEqual(query.call_count, 1)
            self.page.parameter.setCurrentIndex(self.page.parameter.findData('eng_op'))
            self.page._show_day(self.page.days[0])
            self.assertEqual(query.call_count, 2)
        self.assertIn('ENG OIL PRESS', self.page.day_details.toPlainText())
        self.assertIn('AVG 50.0 psi', self.page.day_details.toPlainText())
        self.assertNotIn('95.0', self.page.day_details.toPlainText())

    def test_many_flights_expand_content_and_scroll_the_page_without_shrinking_chart(self):
        original_height = self.page.plot.height()
        original_window_height = self.page.height()
        self.connection.executemany(
            "INSERT INTO flights(id,aircraft_id,flight_date,departure_time)"
            " VALUES(?,'a','2026-09-01','16:00:00')",
            ((f'extra-{index}',) for index in range(35)),
        )
        self.page._show_day(self.page.days[0])
        for _ in range(3):
            self.app.processEvents()
        self.assertEqual(len(self.page.day_details.toPlainText().splitlines()), 39)
        self.assertGreater(self.page.day_details.height(), 180)
        self.assertEqual(self.page.day_details.verticalScrollBar().maximum(), 0)
        self.assertGreater(self.page.scroll.verticalScrollBar().maximum(), 0)
        self.assertTrue(self.page.scroll.verticalScrollBar().isVisible())
        self.assertTrue(self.page.day_details.toPlainText().splitlines()[-1].startswith('TOTAL'))
        self.assertEqual(self.page.plot.height(), original_height)
        self.assertEqual(self.page.height(), original_window_height)

    def test_selection_and_day_details_do_not_reduce_chart_height(self):
        original_height = self.page.plot.height()
        original_range = self.page.scroll.verticalScrollBar().maximum()
        self.page.aircraft_selector.set_selected(('a', 'b', 'c'))
        self.page._show_day(self.page.days[0])
        for _ in range(3):
            self.app.processEvents()
        self.assertEqual(self.page.plot.height(), original_height)
        self.assertGreater(self.page.scroll.verticalScrollBar().maximum(), original_range)
        self.assertEqual(self.page.comparison.verticalScrollBar().maximum(), 0)
        self.assertTrue(self.page.content.isAncestorOf(self.page.view_flights))

    def test_many_aircraft_and_legend_rows_add_height_instead_of_compressing_plot(self):
        self.page.plot.draw()
        original_height = self.page.plot.height()
        original_axes_height = self.page.plot.ax.bbox.height
        for index in range(6):
            aircraft_id = f'extra-aircraft-{index}'
            flight_id = f'extra-flight-{index}'
            self.connection.execute(
                'INSERT INTO aircraft(id,registration,model,serial_number) VALUES(?,?,?,?)',
                (aircraft_id, f'TEST-{index}', 'Bell 505', str(index)),
            )
            self.connection.execute(
                "INSERT INTO flights(id,aircraft_id,flight_date,departure_time)"
                " VALUES(?,?,'2026-09-01','08:00:00')", (flight_id, aircraft_id),
            )
            self.connection.execute(
                "INSERT INTO engine_data(flight_id,seq,eng_ot) VALUES(?,0,?)",
                (flight_id, 80 + index),
            )
        self.page.load()
        self.page.statistic.setCurrentIndex(self.page.statistic.findData('both'))
        for _ in range(3):
            self.app.processEvents()
        self.page.plot.draw()
        self.assertEqual(self.page.comparison.rowCount(), 9)
        self.assertGreater(self.page.comparison.height(), 9 * 40)
        self.assertEqual(self.page.comparison.verticalScrollBar().maximum(), 0)
        self.assertGreater(self.page.plot.height(), original_height)
        self.assertGreaterEqual(self.page.plot.ax.bbox.height, original_axes_height - 2)
        self.assertGreater(self.page.scroll.verticalScrollBar().maximum(), 0)

    def test_mouse_wheel_over_chart_scrolls_the_whole_page(self):
        self.page.resize(1200, 550)
        for _ in range(3):
            self.app.processEvents()
        scrollbar = self.page.scroll.verticalScrollBar()
        scrollbar.setValue(0)
        original_size = self.page.plot.size()
        position = QPoint(100, 100)
        event = QWheelEvent(
            QPointF(position), QPointF(self.page.plot.mapToGlobal(position)),
            QPoint(0, 0), QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
            Qt.NoScrollPhase, False,
        )
        self.app.sendEvent(self.page.plot, event)
        self.app.processEvents()
        self.assertGreater(scrollbar.value(), 0)
        self.assertEqual(self.page.plot.size(), original_size)

    def test_mouse_wheel_over_details_and_table_scrolls_the_page_not_the_widgets(self):
        self.page.resize(1200, 550)
        self.page.load()
        self.page._show_day(self.page.days[0])
        for _ in range(3):
            self.app.processEvents()
        scrollbar = self.page.scroll.verticalScrollBar()
        for widget in (self.page.day_details, self.page.comparison):
            with self.subTest(widget=type(widget).__name__):
                scrollbar.setValue(scrollbar.maximum())
                initial = scrollbar.value()
                position = QPoint(10, 10)
                event = QWheelEvent(
                    QPointF(position), QPointF(widget.viewport().mapToGlobal(position)),
                    QPoint(0, 0), QPoint(0, 120), Qt.NoButton, Qt.NoModifier,
                    Qt.NoScrollPhase, False,
                )
                self.app.sendEvent(widget.viewport(), event)
                self.app.processEvents()
                self.assertLess(scrollbar.value(), initial)
                self.assertEqual(widget.verticalScrollBar().maximum(), 0)

    def test_wrapped_day_details_expand_without_an_internal_scrollbar(self):
        from helink.ui.widgets.aircraft_day_details import AircraftDayDetails

        details = AircraftDayDetails()
        self.addCleanup(details.deleteLater)
        self.addCleanup(details.close)
        details.resize(700, 40)
        text = 'Flight details ' * 30 + '\nTOTAL'
        details.show_message(text)
        details.show()
        for _ in range(3):
            self.app.processEvents()
        original_height = details.height()
        details.resize(280, original_height)
        for _ in range(3):
            self.app.processEvents()
        self.assertGreater(details.height(), original_height)
        self.assertEqual(details.verticalScrollBar().maximum(), 0)
        self.assertEqual(details.toPlainText(), text)

    def test_aircraft_checkboxes_stay_open_for_multiple_selections(self):
        selector = self.page.aircraft_selector
        selector.showPopup()
        self.app.processEvents()
        QTest.mouseClick(selector.checkboxes['b'], Qt.LeftButton)
        self.app.processEvents()
        self.assertEqual(selector.selected_ids(), ('a', 'b'))
        self.assertTrue(selector._menu.isVisible())
        selector.hidePopup()

    def test_header_units_and_filters_are_not_clipped(self):
        self.page.load()
        self.app.processEvents()
        toolbar_controls = (
            self.page.aircraft_selector, self.page.parameter,
            self.page.statistic, self.page.date_filter,
        )
        self.assertEqual(len({widget.height() for widget in toolbar_controls}), 1)
        self.assertEqual(len({widget.y() for widget in toolbar_controls}), 1)
        self.assertGreaterEqual(
            self.page.comparison.horizontalHeader().height(),
            self.page.comparison.fontMetrics().height() * 2,
        )
        for widget in toolbar_controls:
            self.assertLess(widget.geometry().right(), self.page.width())


class FleetAnalysisNavigationTests(TrendFixture, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def test_dashboard_exposes_whole_fleet_and_individual_aircraft_analysis(self):
        page = DashboardPage(self.controller)
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.close)
        page.refresh()
        requested = []
        page.analysis_requested.connect(requested.append)
        button = next(
            widget for widget in page.findChildren(QPushButton)
            if widget.text() == 'Fleet Analysis'
        )
        button.click()
        self.assertEqual(requested, [''])
        page.findChildren(QToolButton, 'fleetRegistration')[0].click()
        self.assertEqual(requested, ['', 'a'])

    def test_navigation_keeps_analysis_separate_from_flight_list(self):
        view = Mock()
        navigation = NavigationController()
        navigation.attach_view(view)
        navigation.show_fleet_analysis('a')
        view.display_fleet_analysis.assert_called_once_with('a')
        view.display_flight_list.assert_not_called()
        navigation.show_aircraft('b')
        view.display_flight_list.assert_called_once_with('b')
        navigation.back_to_aircraft()
        self.assertEqual(view.display_flight_list.call_count, 2)

    def test_individual_analysis_navigation_returns_to_flights_but_fleet_returns_to_dashboard(self):
        view = Mock()
        navigation = NavigationController()
        navigation.attach_view(view)
        navigation.show_aircraft_analysis('b')
        view.display_fleet_analysis.assert_called_once_with('b', allow_comparison=False)
        self.assertEqual(navigation.current_aircraft, 'b')
        navigation.back_from_analysis()
        view.display_flight_list.assert_called_once_with('b')
        view.display_dashboard.assert_not_called()
        navigation.show_fleet_analysis('a')
        navigation.back_from_analysis()
        view.display_dashboard.assert_called_once_with()
        self.assertIsNone(navigation.current_aircraft)
        view.reset_mock()
        navigation.show_aircraft_analysis(None)
        view.display_fleet_analysis.assert_not_called()

    def test_main_window_connects_new_page_without_changing_flight_navigation(self):
        from helink.ui.main_window import MainWindow

        class FlightDetailsStub(QWidget):
            back_requested = Signal()
            import_requested = Signal(str, str)

            def __init__(self, *_controllers):
                super().__init__()

        navigation = NavigationController()
        with patch('helink.ui.main_window.FlightDetailsPage', FlightDetailsStub):
            window = MainWindow(
                flight_controller=FlightController(FlightRepository(self.database)),
                aircraft_controller=self.controller,
                import_controller=Mock(), report_controller=Mock(),
                database_controller=Mock(), navigation_controller=navigation,
            )
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        registration = window.dashboard.findChildren(QToolButton, 'fleetRegistration')[0]
        registration.click()
        self.assertIs(window.stack.currentWidget(), window.fleet_analysis)
        self.assertEqual(window.fleet_analysis.aircraft_selector.selected_ids(), ('a',))
        window.fleet_analysis.view_flights.click()
        self.assertIs(window.stack.currentWidget(), window.flight_list)
        self.assertEqual(window.flight_list.aid, 'a')
        existing_analysis = window.fleet_analysis
        existing_page_count = window.stack.count()
        window.flight_list.date_filter.mode.setCurrentIndex(1)
        window.flight_list.date_filter.start_edit.setDate(QDate(2026, 9, 1))
        window.flight_list.date_filter.apply()
        window.flight_list.analysis_button.click()
        self.assertIs(window.stack.currentWidget(), existing_analysis)
        self.assertEqual(window.stack.count(), existing_page_count)
        self.assertTrue(existing_analysis.aircraft_selector.isHidden())
        self.assertEqual(existing_analysis._selected_aircraft_ids(), ('a',))
        existing_analysis.back_button.click()
        self.assertIs(window.stack.currentWidget(), window.flight_list)
        self.assertEqual(window.flight_list.aid, 'a')
        self.assertEqual(
            window.flight_list.date_filter.date_range, ('2026-09-01', '2026-09-01'),
        )
        navigation.show_aircraft('b')
        window.flight_list.analysis_button.click()
        self.assertIs(window.stack.currentWidget(), existing_analysis)
        self.assertEqual(existing_analysis._selected_aircraft_ids(), ('b',))
        existing_analysis.back_button.click()
        self.assertIs(window.stack.currentWidget(), window.flight_list)
        self.assertEqual(window.flight_list.aid, 'b')
        navigation.show_fleet_analysis()
        self.assertIs(window.stack.currentWidget(), existing_analysis)
        self.assertFalse(existing_analysis.aircraft_selector.isHidden())
        self.assertEqual(existing_analysis._selected_aircraft_ids(), ('a', 'b', 'c'))
        existing_analysis.back_button.click()
        self.assertIs(window.stack.currentWidget(), window.dashboard)


if __name__ == '__main__':
    unittest.main()
