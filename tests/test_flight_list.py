"""Flight-list performance and date filtering checks with an in-memory DB."""

import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QDate, QPoint, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QMessageBox, QPushButton

from helink.controllers.aircraft_controller import AircraftController
from helink.controllers.flight_controller import FlightController
from helink.repositories.aircraft_repository import AircraftRepository
from helink.repositories.database_manager import SCHEMA
from helink.repositories.flight_repository import FlightRepository
from helink.ui.pages.dashboard_page import DashboardPage
from helink.ui.pages.flight_list_page import FlightListPage
from helink.ui.theme import STYLE
from helink.ui.widgets import FlightDateFilterButton, ImportedFilesButton


def application():
    app = QApplication.instance() or QApplication([])
    font = Path('C:/Windows/Fonts/segoeui.ttf')
    if os.name == 'nt' and font.exists():
        QFontDatabase.addApplicationFont(str(font))
    app.setStyleSheet(STYLE)
    return app


class FlightDatabaseFixture:
    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)
        self.connection.executescript(SCHEMA)
        self.connection.executemany(
            'INSERT INTO aircraft(id,registration,model,serial_number) VALUES(?,?,?,?)',
            (('a', 'TEST-A', 'Bell 505', '001'), ('b', 'TEST-B', 'H125', '002')),
        )
        flights = (
            ('f1', 'a', '2026-09-01', '11:00:00'),
            ('f2', 'a', '2026-09-10', '08:00:00'),
            ('f3', 'a', '2026-09-10', '14:00:00'),
            ('f4', 'a', '2026-09-30', '09:00:00'),
            ('f5', 'b', '2026-09-10', '07:00:00'),
        )
        self.connection.executemany(
            """INSERT INTO flights(id,aircraft_id,flight_date,departure_time,
                       arrival_time,duration,origin,destination,imported_files,predictive_report)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            ((*flight, '15:00:00', '10 min', 'LPBJ', 'LPPT',
              '["1_Engine_Data_Recording","data_log"]', 'Report text ' * 1000)
             for flight in flights),
        )
        self.connection.execute(
            "INSERT INTO engine_data(flight_id,seq,timestamp,itt) "
            "VALUES('f1',0,'11:00:00',700)"
        )
        database = SimpleNamespace(connection=self.connection)
        self.flight_repository = FlightRepository(database)
        self.aircraft_repository = AircraftRepository(database)
        self.flight_controller = FlightController(self.flight_repository)
        self.aircraft_controller = AircraftController(self.aircraft_repository)

    def add_sample_events(self):
        self.connection.executemany(
            'INSERT INTO alerts(flight_id,kind,alert_state,alert_name,level) '
            'VALUES(?,?,?,?,?)',
            (
                ('f3', 'EXCEEDANCE', 'SET', 'ENG OIL TEMP', 'WARNING'),
                ('f3', 'EXCEEDANCE', 'CLEARED', 'ENG OIL TEMP', 'WARNING'),
                ('f3', 'EXCEEDANCE', 'SET', 'ITT', 'CAUTION'),
                ('f3', 'CAS', 'SET', 'MISCMP-P', 'CAUTION'),
                ('f3', 'CAS', 'SET', 'OTHER', 'WARNING'),
                ('f2', 'CAS', 'SET', 'MISCMP-P', 'CAUTION'),
                ('f2', 'CAS', 'CLEARED', 'MISCMP-P', 'CAUTION'),
                ('f1', 'EXCEEDANCE', 'SET', 'VNE', 'INFO'),
                ('f5', 'EXCEEDANCE', 'SET', 'TQ', 'WARNING'),
            ),
        )


class FlightSummaryQueryTests(FlightDatabaseFixture, unittest.TestCase):
    def test_event_counts_match_set_activations_in_one_summary_query(self):
        self.add_sample_events()
        queries = []
        self.connection.set_trace_callback(queries.append)
        flights = self.flight_controller.list_flights('a')
        self.assertEqual(len(queries), 1)
        counts = {
            flight.id: (flight.exceedance_count, flight.miscmp_count)
            for flight in flights
        }
        self.assertEqual(
            counts, {'f4': (0, 0), 'f3': (2, 1), 'f2': (0, 1), 'f1': (0, 0)},
        )
        self.assertNotIn('ENGINE_DATA', queries[0].upper())
        self.assertNotIn('TRIGGERS_JSON', queries[0].upper())
        filtered = self.flight_controller.list_flights(
            'a', start_date='2026-09-10', end_date='2026-09-10',
        )
        self.assertEqual([flight.id for flight in filtered], ['f3', 'f2'])
        self.assertEqual(
            [(flight.exceedance_count, flight.miscmp_count) for flight in
             self.flight_controller.list_flights('b')],
            [(1, 0)],
        )

    def test_summaries_do_not_load_reports_or_telemetry_and_use_one_query(self):
        queries = []
        self.connection.set_trace_callback(queries.append)
        flights = self.flight_controller.list_flights('a')
        self.assertEqual(len(queries), 1)
        self.assertTrue(all(not flight.predictive_report for flight in flights))
        self.assertTrue(all(not flight.engine_data for flight in flights))
        self.assertEqual(flights[0].imported_files, ('1_Engine_Data_Recording', 'data_log'))
        self.assertNotIn('PREDICTIVE_REPORT', queries[0].upper())
        self.assertNotIn('ENGINE_DATA', queries[0].upper())

    def test_single_date_keeps_separate_flights_on_the_same_day(self):
        flights = self.flight_controller.list_flights(
            'a', start_date='2026-09-10', end_date='2026-09-10',
        )
        self.assertEqual([flight.id for flight in flights], ['f3', 'f2'])

    def test_range_includes_both_boundary_dates(self):
        flights = self.flight_controller.list_flights(
            'a', start_date='2026-09-01', end_date='2026-09-10',
        )
        self.assertEqual([flight.id for flight in flights], ['f3', 'f2', 'f1'])

    def test_sorting_is_by_date_then_departure_and_scoped_to_aircraft(self):
        self.assertEqual(
            [f.id for f in self.flight_controller.list_flights('a')],
            ['f4', 'f3', 'f2', 'f1'],
        )
        self.assertEqual(
            [f.id for f in self.flight_controller.list_flights('a', descending=False)],
            ['f1', 'f2', 'f3', 'f4'],
        )
        self.assertEqual(
            [f.id for f in self.flight_controller.list_flights('b')], ['f5'],
        )

    def test_invalid_or_reversed_dates_are_rejected_before_querying(self):
        queries = []
        self.connection.set_trace_callback(queries.append)
        for start, end in (
            ('2026-09-30', '2026-09-01'),
            ('2026-02-30', None),
            ("2026-09-10' OR 1=1", None),
        ):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                self.flight_controller.list_flights('a', start_date=start, end_date=end)
        self.assertEqual(queries, [])

    def test_aircraft_lookup_does_not_scan_alerts_or_the_whole_fleet(self):
        queries = []
        self.connection.set_trace_callback(queries.append)
        aircraft = self.aircraft_controller.get('a')
        self.assertEqual(aircraft.registration, 'TEST-A')
        self.assertEqual(aircraft.flight_count, 4)
        self.assertEqual(len(queries), 1)
        self.assertNotIn('ALERTS', queries[0].upper())
        self.assertIsNone(self.aircraft_controller.get('missing'))

    def test_full_flight_details_still_include_report_and_telemetry(self):
        flight = self.flight_controller.get('f1')
        self.assertTrue(flight.predictive_report)
        self.assertEqual(flight.engine_data[0].itt, 700)


class FlightDateFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        self.button = FlightDateFilterButton()
        self.addCleanup(self.button.deleteLater)
        self.addCleanup(self.button.close)
        self.received = []
        self.button.range_changed.connect(
            lambda start, end: self.received.append((start, end))
        )
        self.button.set_available_dates(('2026-09-01', '2026-09-30', 'unknown'))

    def test_all_dates_are_default_and_single_date_uses_latest_imported_date(self):
        self.assertEqual(self.button.date_range, (None, None))
        self.assertEqual(self.button.text(), 'Dates: All')
        self.button.mode.setCurrentIndex(1)
        self.assertEqual(self.button.start_edit.date(), QDate(2026, 9, 30))
        self.button.start_edit.setDate(QDate(2026, 9, 10))
        self.assertEqual(self.received, [])
        self.button.apply_button.click()
        self.assertEqual(self.received, [('2026-09-10', '2026-09-10')])
        self.assertIn('10/09/2026', self.button.text())

    def test_range_defaults_to_recorded_dates_and_clear_restores_all(self):
        self.button.mode.setCurrentIndex(2)
        self.assertEqual(self.button.start_edit.date(), QDate(2026, 9, 1))
        self.assertEqual(self.button.end_edit.date(), QDate(2026, 9, 30))
        self.button.apply_button.click()
        self.assertEqual(self.button.date_range, ('2026-09-01', '2026-09-30'))
        self.button.clear_button.click()
        self.assertEqual(self.button.date_range, (None, None))
        self.assertEqual(self.button.text(), 'Dates: All')
        self.assertEqual(self.received[-1], (None, None))

    def test_reversed_interval_disables_apply_and_shows_error(self):
        self.button.mode.setCurrentIndex(2)
        self.button.start_edit.setDate(QDate(2026, 10, 1))
        self.assertFalse(self.button.apply_button.isEnabled())
        self.assertFalse(self.button.error.isHidden())
        self.button.apply()
        self.assertEqual(self.received, [])
        self.button.end_edit.setDate(QDate(2026, 10, 1))
        self.assertTrue(self.button.apply_button.isEnabled())
        self.assertTrue(self.button.error.isHidden())

    def test_reset_without_emitting_is_available_for_aircraft_navigation(self):
        self.button.mode.setCurrentIndex(1)
        self.button.apply()
        self.received.clear()
        self.button.reset(emit=False)
        self.assertEqual(self.received, [])
        self.assertEqual(self.button.date_range, (None, None))

    def test_date_fields_have_a_valid_point_size_for_native_windows_controls(self):
        self.button.show()
        self.app.processEvents()
        for field in (self.button.start_edit, self.button.end_edit):
            field.ensurePolished()
            self.assertGreater(field.font().pointSizeF(), 0)
            self.assertTrue(field.calendarPopup())

    @unittest.skipUnless(os.name == 'nt', 'Requires the native Windows Qt style')
    def test_native_windows_date_filter_starts_without_font_size_warning(self):
        script = """
from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QStyleFactory, QVBoxLayout, QWidget
from helink.ui.theme import STYLE
from helink.ui.widgets.flight_date_filter_button import FlightDateFilterButton

app = QApplication([])
style = next((name for name in QStyleFactory.keys()
              if name.lower() in ('windows11', 'windowsvista')), 'Windows')
app.setStyle(style)
app.setStyleSheet(STYLE)
messages = []
def capture(kind, context, message):
    if 'QFont::setPointSize' in message:
        messages.append(message)
previous = qInstallMessageHandler(capture)
page = QWidget()
layout = QVBoxLayout(page)
layout.addWidget(FlightDateFilterButton())
page.show()
app.processEvents()
page.close()
qInstallMessageHandler(previous)
assert not messages, messages
"""
        result = subprocess.run(
            [sys.executable, '-c', script], capture_output=True, text=True,
            timeout=20, env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dropdown_opens_by_mouse_or_keyboard_and_closes_without_applying(self):
        self.button.show()
        self.app.processEvents()
        QTest.mouseClick(self.button, Qt.LeftButton)
        self.app.processEvents()
        self.assertTrue(self.button.menu().isVisible())
        QTest.keyClick(self.button.menu(), Qt.Key_Escape)
        self.app.processEvents()
        self.assertFalse(self.button.menu().isVisible())
        self.button.setFocus()
        QTest.keyClick(self.button, Qt.Key_F4)
        self.app.processEvents()
        self.assertTrue(self.button.menu().isVisible())
        self.button.hidePopup()
        self.assertFalse(self.button.menu().isVisible())
        self.assertEqual(self.received, [])

    def test_popup_grows_for_range_fields_and_validation_message_without_clipping(self):
        self.button.show()
        menu = self.button.menu()
        self.addCleanup(menu.hide)
        menu.popup(self.button.mapToGlobal(QPoint(0, self.button.height())))
        self.app.processEvents()
        original_height = menu.height()
        self.button.mode.setCurrentIndex(2)
        for _ in range(3):
            self.app.processEvents()
        self.assertGreater(menu.height(), original_height)
        content = menu.actions()[0].defaultWidget()
        self.assertGreaterEqual(content.height(), content.minimumSizeHint().height())
        range_height = menu.height()
        self.button.start_edit.setDate(QDate(2026, 10, 1))
        for _ in range(3):
            self.app.processEvents()
        self.assertGreater(menu.height(), range_height)
        self.assertGreaterEqual(content.height(), content.minimumSizeHint().height())


class FlightListPageTests(FlightDatabaseFixture, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def setUp(self):
        super().setUp()
        self.page = FlightListPage(self.aircraft_controller, self.flight_controller)
        self.addCleanup(self.page.deleteLater)
        self.addCleanup(self.page.close)
        self.page.resize(1280, 800)
        self.page.show()
        self.page.load('a')
        self.app.processEvents()

    def row_ids(self):
        return [
            self.page.table.item(row, 1).data(Qt.UserRole)
            for row in range(self.page.table.rowCount())
        ]

    def single_date(self, date=QDate(2026, 9, 10)):
        button = self.page.date_filter
        button.mode.setCurrentIndex(1)
        button.start_edit.setDate(date)
        button.apply_button.click()
        self.app.processEvents()

    def test_opening_list_loads_no_eager_file_popovers_or_fleet_query(self):
        self.assertEqual(self.row_ids(), ['f4', 'f3', 'f2', 'f1'])
        files_buttons = self.page.findChildren(ImportedFilesButton)
        self.assertEqual(len(files_buttons), 4)
        self.assertTrue(all(button._popover is None for button in files_buttons))
        with patch.object(self.aircraft_controller, 'list_aircraft') as fleet_query:
            self.page.load('a')
        fleet_query.assert_not_called()

    def test_events_column_shows_counts_and_highlights_with_selected_row(self):
        self.add_sample_events()
        self.page._reload_rows()
        self.assertEqual(self.page.table.columnCount(), 9)
        self.assertEqual(self.page.table.horizontalHeaderItem(6).text(), 'EVENTS')
        mixed = self.page.table.cellWidget(1, 6)
        badges = mixed.findChildren(QLabel)
        self.assertEqual(
            [(badge.objectName(), badge.text()) for badge in badges],
            [('flightExceedanceBadge', 'Exceedances 2'),
             ('flightMiscmpBadge', 'MISCMP-P 1')],
        )
        self.assertEqual(
            self.page.table.cellWidget(2, 6).findChildren(QLabel)[0].text(),
            'MISCMP-P 1',
        )
        self.assertEqual(
            self.page.table.cellWidget(0, 6).findChildren(QLabel)[0].text(),
            '\N{EM DASH}',
        )
        self.page.row_checkboxes[1].setChecked(True)
        self.assertTrue(mixed.property('rowSelected'))
        self.page.row_checkboxes[1].setChecked(False)
        self.assertFalse(mixed.property('rowSelected'))
        self.single_date()
        self.assertEqual(self.row_ids(), ['f3', 'f2'])
        self.assertEqual(
            self.page.table.cellWidget(0, 6).findChildren(QLabel)[0].text(),
            'Exceedances 2',
        )

    def test_analysis_navigation_buttons_are_centered_and_blue_styled(self):
        button = self.page.analysis_button
        self.assertEqual(button.objectName(), 'analysisNavigation')
        self.assertLess(abs(button.geometry().center().x() - self.page.width() / 2), 12)
        dashboard = DashboardPage(self.aircraft_controller)
        self.addCleanup(dashboard.deleteLater)
        self.addCleanup(dashboard.close)
        dashboard.resize(1280, 800)
        dashboard.show()
        self.app.processEvents()
        fleet_button = next(
            item for item in dashboard.findChildren(QPushButton)
            if item.text() == 'Fleet Analysis'
        )
        self.assertEqual(fleet_button.objectName(), 'analysisNavigation')
        self.assertLess(
            abs(fleet_button.geometry().center().x() - dashboard.width() / 2), 12,
        )
        self.assertIn('QPushButton#analysisNavigation{background:#eff6ff', STYLE)

    def test_analysis_button_emits_only_the_current_aircraft_and_is_disabled_if_missing(self):
        requested = []
        self.page.analysis_requested.connect(requested.append)
        self.assertEqual(self.page.analysis_button.text(), 'Aircraft Analysis')
        self.assertTrue(self.page.analysis_button.isEnabled())
        self.page.analysis_button.click()
        self.assertEqual(requested, ['a'])
        self.page.load('b')
        self.page.analysis_button.click()
        self.assertEqual(requested, ['a', 'b'])
        self.page.load('missing')
        self.assertFalse(self.page.analysis_button.isEnabled())
        self.page.analysis_button.click()
        self.assertEqual(requested, ['a', 'b'])

    def test_filter_keeps_route_arrival_and_files_for_each_matching_flight(self):
        self.single_date()
        self.assertEqual(self.row_ids(), ['f3', 'f2'])
        self.assertEqual(self.page.flight_count.text(), '2 of 4 flights')
        self.assertEqual(self.page.table.item(0, 3).text(), '15:00:00')
        self.assertEqual(self.page.table.item(0, 5).text(), 'LPBJ  \u2192  LPPT')
        self.page.date_filter.clear_button.click()
        self.assertEqual(self.page.table.rowCount(), 4)
        self.assertEqual(self.page.flight_count.text(), '4 imported flights')

    def test_date_filter_matches_sort_control_height_alignment_and_font(self):
        sort, dates = self.page.sort_order, self.page.date_filter
        self.assertIsInstance(dates, QComboBox)
        for mode in (0, 1, 2):
            with self.subTest(mode=mode):
                dates.mode.setCurrentIndex(mode)
                dates.apply()
                for _ in range(3):
                    self.app.processEvents()
                self.assertEqual(dates.height(), sort.height())
                self.assertEqual(dates.y(), sort.y())
                self.assertEqual(dates.minimumWidth(), sort.minimumWidth())
                self.assertEqual(dates.font(), sort.font())
                self.assertGreaterEqual(dates.width(), dates.sizeHint().width())

    def test_order_changes_preserve_filter_without_refetching_aircraft(self):
        self.single_date()
        with patch.object(self.aircraft_controller, 'get') as aircraft_query:
            self.page.sort_order.setCurrentIndex(0)
        aircraft_query.assert_not_called()
        self.assertEqual(self.row_ids(), ['f2', 'f3'])
        self.assertEqual(
            self.page.date_filter.date_range, ('2026-09-10', '2026-09-10'),
        )

    def test_select_all_and_delete_apply_only_to_visible_filtered_flights(self):
        self.single_date()
        self.page._toggle_all(True)
        self.assertEqual(set(self.page.selected_ids()), {'f2', 'f3'})
        self.assertFalse(self.page.delete_btn.isHidden())
        with patch(
            'helink.ui.pages.flight_list_page.QMessageBox.warning',
            return_value=QMessageBox.Yes,
        ):
            self.page.delete_selected()
        self.assertEqual(self.page.table.rowCount(), 0)
        self.assertEqual(
            [f.id for f in self.flight_controller.list_flights('a')], ['f4', 'f1'],
        )
        self.assertEqual(self.page.flight_count.text(), '0 of 2 flights')
        self.assertFalse(self.page.filter_message.isHidden())
        self.assertTrue(self.page.delete_btn.isHidden())

    def test_applying_filter_clears_hidden_selections(self):
        self.page._toggle_all(True)
        self.single_date()
        self.assertEqual(self.page.selected_ids(), [])
        self.assertTrue(self.page.delete_btn.isHidden())
        self.assertTrue(self.page.selection_count.isHidden())

    def test_empty_result_disables_select_all_and_explains_the_filter(self):
        self.single_date(QDate(2025, 1, 1))
        self.assertEqual(self.page.table.rowCount(), 0)
        self.assertFalse(self.page.selection_header._check_enabled)
        self.assertEqual(self.page.filter_message.text(), 'No flights match the selected dates.')

    def test_switching_aircraft_resets_dates_but_keeps_sort_preference(self):
        self.single_date()
        self.page.sort_order.setCurrentIndex(0)
        self.page.load('b')
        self.assertEqual(self.page.date_filter.date_range, (None, None))
        self.assertEqual(self.page.sort_order.currentData(), 'ascending')
        self.assertEqual(self.row_ids(), ['f5'])

    def test_open_action_still_uses_the_flight_id_after_filtering(self):
        self.single_date()
        received = []
        self.page.flight_selected.connect(received.append)
        self.page.table.setCurrentCell(0, 1)
        self.page.open_current()
        self.assertEqual(received, ['f3'])

    def test_each_flight_has_only_open_action_and_bulk_delete_remains_available(self):
        for row in range(self.page.table.rowCount()):
            actions = self.page.table.cellWidget(row, 8)
            self.assertEqual(
                [button.text() for button in actions.findChildren(QPushButton)],
                ['Open'],
            )
        self.page.row_checkboxes[0].setChecked(True)
        self.assertTrue(self.page.delete_btn.isVisible())

    def test_table_repaints_are_restored_even_if_population_fails(self):
        with patch.object(self.page, '_populate_rows', side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):
                self.page._reload_rows()
        self.assertTrue(self.page.table.updatesEnabled())


class ImportedFilesLazyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application()

    def test_popover_is_created_only_on_first_click_and_reused(self):
        button = ImportedFilesButton(('data_log',))
        self.addCleanup(button.deleteLater)
        self.addCleanup(button.close)
        button.show()
        self.app.processEvents()
        self.assertIsNone(button._popover)
        self.assertIn('GPS / Flight Data', button.toolTip())
        QTest.mouseClick(button, Qt.LeftButton)
        self.assertIsNotNone(button._popover)
        popover = button._popover
        self.assertTrue(popover.isVisible())
        button._toggle_popover()
        self.assertFalse(popover.isVisible())
        button._toggle_popover()
        self.assertIs(button._popover, popover)
        popover.hide()


if __name__ == '__main__':
    unittest.main()
