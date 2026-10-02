"""Responsiveness checks using disposable databases, never application data."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import sqlite3
import tempfile
from threading import Event, get_ident
from time import monotonic, sleep
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from helink.bootstrap import build_main_window
from helink.controllers.task_controller import TaskController
from helink.controllers.flight_controller import FlightController
from helink.repositories.database_manager import DatabaseManager
from helink.repositories.flight_repository import FlightRepository


class BackgroundTasksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='helink-async-tests-')
        self.path = Path(self.temp.name) / 'test.db'
        self.database = DatabaseManager(self.path)
        with self.database.connection:
            self.database.connection.execute(
                "INSERT INTO aircraft(id,registration,model,serial_number)"
                " VALUES('a','TEST-A','Bell 505','001')"
            )
            self.database.connection.execute(
                "INSERT INTO flights(id,aircraft_id,flight_date,departure_time,arrival_time)"
                " VALUES('f','a','2026-09-01','08:00:00','08:00:02')"
            )
            self.database.connection.executemany(
                "INSERT INTO engine_data(flight_id,seq,timestamp,itt,eng_ot)"
                " VALUES('f',?,?,?,?)",
                ((i, f'08:00:{i:02d}', 600 + i, 80 + i) for i in range(3)),
            )
        self.tasks = TaskController(self.database)
        self.errors = []
        self.addCleanup(self.cleanup)

    def wait_until(self, condition, timeout=5000):
        deadline = monotonic() + timeout / 1000
        while not condition() and monotonic() < deadline:
            QTest.qWait(5)
        self.assertTrue(condition(), 'Background operation did not finish in time.')

    def cleanup(self):
        self.tasks.cancel_all()
        self.wait_until(lambda: not self.tasks.busy)
        self.tasks.pool.waitForDone(5000)
        self.database.close()
        self.tasks.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_queries_use_worker_owned_connections_and_callbacks_use_ui_thread(self):
        main_thread = get_ident()
        received = []

        def read(database, _progress):
            return get_ident(), database.connection.execute(
                'SELECT COUNT(*) FROM engine_data'
            ).fetchone()[0]

        self.tasks.query(
            read, lambda data: received.append((get_ident(), data)), self.errors.append,
        )
        self.wait_until(lambda: not self.tasks.busy)
        self.assertEqual(self.errors, [])
        callback_thread, (worker_thread, count) = received[0]
        self.assertEqual(callback_thread, main_thread)
        self.assertNotEqual(worker_thread, main_thread)
        self.assertEqual(count, 3)

    def test_event_loop_keeps_running_during_slow_background_work(self):
        ticks, received = [], []
        timer = QTimer()
        timer.setInterval(5)
        timer.timeout.connect(lambda: ticks.append(monotonic()))
        timer.start()
        self.addCleanup(timer.stop)

        def read(database, _progress):
            sleep(0.12)
            return database.connection.execute('SELECT COUNT(*) FROM flights').fetchone()[0]

        started = monotonic()
        self.tasks.query(read, received.append, self.errors.append)
        self.assertLess(monotonic() - started, 0.05)
        self.wait_until(lambda: not self.tasks.busy)
        self.assertGreaterEqual(len(ticks), 5)
        self.assertEqual(received, [1])

    def test_cache_reuses_results_and_invalidates_on_main_connection_writes(self):
        calls, received = [], []

        def read(database, _progress):
            calls.append(True)
            return database.connection.execute(
                "SELECT registration FROM aircraft WHERE id='a'"
            ).fetchone()[0]

        for _ in range(2):
            self.tasks.query(read, received.append, self.errors.append, cache_key=('identity', 'a'))
            self.wait_until(lambda: not self.tasks.busy)
        self.assertEqual(len(calls), 1)
        with self.database.connection:
            self.database.connection.execute(
                "UPDATE aircraft SET registration='TEST-B' WHERE id='a'"
            )
        self.tasks.query(read, received.append, self.errors.append, cache_key=('identity', 'a'))
        self.wait_until(lambda: not self.tasks.busy)
        self.assertEqual(len(calls), 2)
        self.assertEqual(received, ['TEST-A', 'TEST-A', 'TEST-B'])

    def test_cache_detects_external_connection_commits(self):
        received = []
        read = lambda database, _progress: database.connection.execute(
            "SELECT registration FROM aircraft WHERE id='a'"
        ).fetchone()[0]
        self.tasks.query(read, received.append, self.errors.append, cache_key='identity')
        self.wait_until(lambda: not self.tasks.busy)
        with sqlite3.connect(self.path) as external:
            external.execute("UPDATE aircraft SET registration='TEST-C' WHERE id='a'")
        external.close()
        self.tasks.query(read, received.append, self.errors.append, cache_key='identity')
        self.wait_until(lambda: not self.tasks.busy)
        self.assertEqual(received, ['TEST-A', 'TEST-C'])

    def test_cancelling_a_write_rolls_back_the_transaction(self):
        started, cancelled, results = Event(), [], []

        def write(database, progress):
            with database.connection:
                database.connection.execute(
                    "UPDATE aircraft SET registration='NOT-COMMITTED' WHERE id='a'"
                )
                started.set()
                while True:
                    progress(10, 'Writing...')
                    sleep(0.005)

        handle = self.tasks.write(write, results.append, self.errors.append)
        handle.cancelled.connect(lambda: cancelled.append(True))
        self.wait_until(started.is_set)
        handle.cancel()
        self.wait_until(lambda: not self.tasks.busy)
        self.assertEqual(results, [])
        self.assertEqual(self.errors, [])
        self.assertEqual(cancelled, [True])
        value = self.database.connection.execute(
            "SELECT registration FROM aircraft WHERE id='a'"
        ).fetchone()[0]
        self.assertEqual(value, 'TEST-A')

    def test_query_connections_are_read_only_and_errors_are_delivered(self):
        self.tasks.query(
            lambda database, _progress: database.connection.execute('DELETE FROM aircraft'),
            lambda _: self.fail('A read task was allowed to write.'), self.errors.append,
        )
        self.wait_until(lambda: not self.tasks.busy)
        self.assertEqual(len(self.errors), 1)
        self.assertIn('readonly', str(self.errors[0]).lower())

    def test_cache_has_a_fixed_entry_limit(self):
        for index in range(36):
            self.tasks.query(
                lambda _database, _progress, value=index: value,
                lambda _: None, self.errors.append, cache_key=('small', index),
            )
        self.wait_until(lambda: not self.tasks.busy)
        self.assertLessEqual(len(self.tasks._cache), self.tasks.MAX_CACHE_ENTRIES)
        self.assertEqual(self.errors, [])

    def test_full_flight_cache_retains_only_two_snapshots(self):
        for index in range(5):
            self.tasks.query(
                lambda _database, _progress, value=index: SimpleNamespace(flight=value),
                lambda _: None, self.errors.append, cache_key=('details', index),
            )
            self.wait_until(lambda: not self.tasks.busy)
        self.assertEqual(list(self.tasks._cache), [('details', 3), ('details', 4)])

    def database_controller(self):
        from helink.controllers.database_controller import DatabaseController
        from helink.services.database_transfer_service import DatabaseTransferService
        return DatabaseController(
            DatabaseTransferService(self.database), self.database, self.tasks,
        )

    def test_database_export_in_worker_is_valid_and_preserves_source(self):
        destination = Path(self.temp.name) / 'export.db'
        results = []
        self.database_controller().request_export(destination, results.append, self.errors.append)
        self.wait_until(lambda: not self.tasks.busy)
        self.assertEqual(self.errors, [])
        self.assertEqual(results, [destination])
        DatabaseManager.validate(destination)
        with sqlite3.connect(destination) as exported:
            self.assertEqual(exported.execute('SELECT COUNT(*) FROM engine_data').fetchone()[0], 3)
        exported.close()
        self.assertEqual(self.database.connection.execute('SELECT COUNT(*) FROM flights').fetchone()[0], 1)

    def test_cancelled_export_does_not_overwrite_an_existing_destination(self):
        from helink.services.database_transfer_service import DatabaseTransferService
        destination = Path(self.temp.name) / 'keep.db'
        self.database.export_to(destination)
        original = destination.read_bytes()

        def cancelled(_value, _message):
            raise InterruptedError('Cancelled before replacing the destination.')

        with self.assertRaises(InterruptedError):
            DatabaseTransferService.export_session(self.database, destination, cancelled)
        self.assertEqual(destination.read_bytes(), original)
        self.assertEqual(list(Path(self.temp.name).glob('.helink-export-*')), [])

    def test_database_import_reopens_ui_connection_and_preserves_backup(self):
        source = Path(self.temp.name) / 'replacement.db'
        candidate = DatabaseManager(source)
        with candidate.connection:
            candidate.connection.execute(
                "INSERT INTO aircraft(id,registration,model,serial_number)"
                " VALUES('new','TEST-NEW','H125','002')"
            )
        candidate.close()
        results = []
        self.database_controller().request_import(source, results.append, self.errors.append)
        self.wait_until(lambda: not self.tasks.busy)
        self.assertEqual(self.errors, [])
        self.assertEqual(
            self.database.connection.execute('SELECT registration FROM aircraft').fetchone()[0],
            'TEST-NEW',
        )
        self.assertTrue(results[0].exists())
        with sqlite3.connect(results[0]) as backup:
            self.assertEqual(backup.execute('SELECT registration FROM aircraft').fetchone()[0], 'TEST-A')
        backup.close()
        self.assertEqual(self.tasks._cache, {})

    def test_invalid_database_import_restores_a_usable_connection(self):
        source = Path(self.temp.name) / 'invalid.db'
        with sqlite3.connect(source) as invalid:
            invalid.execute('CREATE TABLE unrelated(id INTEGER)')
        invalid.close()
        results = []
        self.database_controller().request_import(source, results.append, self.errors.append)
        self.wait_until(lambda: not self.tasks.busy)
        self.assertEqual(results, [])
        self.assertEqual(len(self.errors), 1)
        self.assertEqual(self.database.connection.execute('SELECT COUNT(*) FROM flights').fetchone()[0], 1)

    def test_csv_import_uses_background_parser_and_reports_completion(self):
        from helink.controllers.import_controller import ImportController
        from helink.services.flight_import_service import FlightImportService
        blob = (
            '2026-09-23_110000_LPBJ_1.csv',
            b'Timestamp,N1,ITT\n2026-09-23 11:00:00,70,700\n2026-09-23 11:01:00,72,710\n',
            True,
        )
        controller = ImportController(
            FlightImportService(FlightRepository(self.database)), self.tasks,
        )
        results, progress = [], []
        with patch('helink.services.garmin_file_parser._collect_csv_blobs', return_value=[blob]):
            controller.request(
                'import_for_aircraft', ['in-memory'], 'a', on_result=results.append,
                on_error=self.errors.append, on_progress=lambda value, _message: progress.append(value),
            )
            self.wait_until(lambda: not self.tasks.busy)
        self.assertEqual(self.errors, [])
        self.assertEqual(results[0].flight_count, 1)
        self.assertIn(100, progress)
        self.assertEqual(self.database.connection.execute('SELECT COUNT(*) FROM flights').fetchone()[0], 2)

    def test_large_alert_table_batches_rows_and_filter_discards_pending_rows(self):
        from helink.models.flight.alert import Alert
        from helink.ui.tabs.alerts_tab import AlertsTab
        tab = AlertsTab('CAS')
        tab.tasks = self.tasks
        tab.resize(1100, 700)
        tab.show()
        self.addCleanup(tab.close)
        alerts = tuple(
            Alert(
                id=index, flight_id='f', kind='CAS', timestamp='08:00:01',
                alert_name='MISCMP-P' if index % 2 else 'OTHER',
                alert_state='SET' if index % 2 else 'CLEARED', level='CAUTION',
            ) for index in range(211)
        )
        tab.load(SimpleNamespace(alerts=alerts))
        self.assertTrue(tab._render_pending)
        tab.set_filters(alert_name='MISCMP-P')
        self.wait_until(lambda: not tab._render_pending)
        self.assertEqual(tab.table.rowCount(), 105)
        self.assertTrue(all(
            tab.table.item(row, 3).text() == 'MISCMP-P' for row in range(105)
        ))
        self.assertTrue(all(
            tab.table.rowHeight(row) >= tab.table.cellWidget(row, 1).sizeHint().height() + 12
            for row in range(105)
        ))
        tab.search.setText('unmatched')
        self.wait_until(lambda: tab.table.rowCount() == 0)

    def test_telemetry_draws_after_navigation_overlay_and_after_scrolling(self):
        window = self.window()
        window.navigation_controller.show_flight('f')
        self.wait_until(lambda: not window.tasks.busy)
        telemetry = window.flight_details.telemetry
        window.flight_details.tabs.setCurrentWidget(telemetry)
        first = telemetry.plots['n1'][0]
        self.wait_until(lambda: first._cursor_background is not None)
        window.navigation_controller.show_aircraft('a')
        self.wait_until(lambda: not window.tasks.busy)
        # Force a fresh snapshot while the Telemetry tab stays selected.
        with self.database.connection:
            self.database.connection.execute(
                "UPDATE engine_data SET itt=800 WHERE flight_id='f'"
            )
        window.navigation_controller.show_flight('f')
        self.wait_until(lambda: not window.tasks.busy)
        self.wait_until(lambda: first._cursor_background is not None)
        self.assertFalse(window.loading_overlay.isVisible())
        self.assertEqual(list(telemetry.plots['itt'][0].ax.lines[0].get_ydata()), [800, 800, 800])
        scrollbar = telemetry.chart_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        last = telemetry.plots['fuel_press'][0]
        self.wait_until(lambda: last._cursor_background is not None)
        telemetry.slider.setValue(2)
        self.assertEqual(first._cursor_line.get_xdata(), [2, 2])
        self.assertEqual(last._cursor_line.get_xdata(), [2, 2])

    def test_closing_window_cancels_work_before_closing_database(self):
        window = self.window()
        started = Event()

        def read(_database, progress):
            started.set()
            while True:
                progress(10, 'Reading...')
                sleep(0.005)

        window.tasks.query(read, lambda _: None, self.errors.append)
        self.wait_until(started.is_set)
        window.close()
        self.wait_until(lambda: not window.tasks.busy and not window.isVisible())
        self.assertEqual(self.errors, [])
        with self.assertRaises(sqlite3.ProgrammingError):
            window.tasks.database.connection.execute('SELECT 1')

    def window(self):
        route = QWidget()
        route.load = Mock()
        with patch('helink.ui.pages.flight_details_page.MapTab', return_value=route):
            window = build_main_window(self.path)
        window.show()
        self.wait_until(lambda: not window.tasks.busy)

        def close():
            window.close()
            self.wait_until(lambda: not window.tasks.busy)
            self.app.processEvents()
            window.deleteLater()
            self.app.processEvents()
        self.addCleanup(close)
        return window

    def test_real_async_navigation_keeps_overview_data_and_reuses_cached_snapshot(self):
        window = self.window()
        window.navigation_controller.show_flight('f')
        self.wait_until(lambda: not window.tasks.busy)
        self.assertIs(window.stack.currentWidget(), window.flight_details)
        self.assertFalse(window.loading_overlay.isVisible())
        self.assertEqual(window.flight_details.overview.metric_values['itt_avg'].text(), '601.0')
        prepared = window.flight_details._prepared
        window.navigation_controller.show_aircraft('a')
        self.wait_until(lambda: not window.tasks.busy)
        self.assertEqual(window.flight_list.table.rowCount(), 1)
        window.navigation_controller.show_flight('f')
        self.wait_until(lambda: not window.tasks.busy)
        self.assertIs(window.flight_details._prepared, prepared)

    def test_old_navigation_results_cannot_replace_a_newly_selected_page(self):
        window = self.window()
        original = FlightController.details_data

        def delayed(controller, flight_id):
            sleep(0.08)
            return original(controller, flight_id)

        with patch.object(FlightController, 'details_data', delayed):
            window.navigation_controller.show_flight('f')
            window.navigation_controller.show_aircraft('a')
            self.wait_until(lambda: not window.tasks.busy)
        self.assertIs(window.stack.currentWidget(), window.flight_list)
        self.assertEqual(window.flight_list.aid, 'a')
        self.assertFalse(window.loading_overlay.isVisible())

    def test_large_flight_lists_are_built_in_batches_without_losing_rows(self):
        with self.database.connection:
            self.database.connection.executemany(
                "INSERT INTO flights(id,aircraft_id,flight_date,departure_time)"
                " VALUES(?,'a','2026-09-02','09:00:00')",
                ((f'extra-{i}',) for i in range(120)),
            )
        window = self.window()
        window.navigation_controller.show_aircraft('a')
        self.wait_until(
            lambda: not window.tasks.busy and not window.flight_list._render_pending,
        )
        self.assertEqual(window.flight_list.table.rowCount(), 121)
        self.assertEqual(len(window.flight_list.row_checkboxes), 121)
        self.assertFalse(window.loading_overlay.isVisible())
        self.assertTrue(all(
            window.flight_list.table.item(row, 1) is not None for row in range(121)
        ))

    def test_fleet_and_individual_analysis_run_asynchronously_without_changing_scope(self):
        window = self.window()
        window.navigation_controller.show_aircraft_analysis('a')
        self.wait_until(lambda: not window.tasks.busy)
        page = window.fleet_analysis
        self.assertEqual(page._selected_aircraft_ids(), ('a',))
        self.assertTrue(page.aircraft_selector.isHidden())
        page.minimum_minutes.setValue(0)
        self.wait_until(lambda: not window.tasks.busy)
        page.parameter.setCurrentIndex(page.parameter.findData('eng_ot'))
        self.wait_until(lambda: not window.tasks.busy)
        self.assertEqual(page.days[0].average, 81)
        page._show_day(page.days[0])
        self.wait_until(lambda: not window.tasks.busy)
        self.assertIn('AVG 81.0', page.day_details.toPlainText())
        window.navigation_controller.show_fleet_analysis()
        self.wait_until(lambda: not window.tasks.busy)
        self.assertFalse(page.aircraft_selector.isHidden())

    def test_minimum_flight_duration_is_applied_in_background_and_survives_navigation(self):
        with self.database.connection:
            self.database.connection.execute(
                "UPDATE flights SET duration='2 min' WHERE id='f'"
            )
            self.database.connection.execute(
                "INSERT INTO flights(id,aircraft_id,flight_date,departure_time,"
                "arrival_time,duration) VALUES('long','a','2026-09-02',"
                "'09:00:00','09:15:00','15 min')"
            )
            self.database.connection.execute(
                "INSERT INTO engine_data(flight_id,seq,timestamp,itt) "
                "VALUES('long',0,'09:00:00',850)"
            )
        window = self.window()
        window.navigation_controller.show_aircraft_analysis('a')
        self.wait_until(lambda: not window.tasks.busy)
        page = window.fleet_analysis
        self.assertEqual(page.minimum_minutes.value(), 20)
        self.assertEqual(page.days, [])
        page.minimum_minutes.setValue(10)
        self.wait_until(lambda: not window.tasks.busy)
        self.assertEqual([day.flight_date for day in page.days], ['2026-09-02'])
        self.assertEqual(page.days[0].average, 850)
        page._show_day(page.days[0])
        self.wait_until(lambda: not window.tasks.busy)
        self.assertIn('09:00:00', page.day_details.toPlainText())
        window.navigation_controller.show_dashboard()
        self.wait_until(lambda: not window.tasks.busy)
        window.navigation_controller.show_aircraft_analysis('a')
        self.wait_until(lambda: not window.tasks.busy)
        self.assertEqual(page.minimum_minutes.value(), 10)
        self.assertEqual([day.flight_date for day in page.days], ['2026-09-02'])
        page.minimum_minutes.setValue(0)
        self.wait_until(lambda: not window.tasks.busy)
        self.assertEqual(len(page.days), 2)

    def test_pdf_export_in_worker_returns_file_and_updated_report_text(self):
        from helink.controllers.report_controller import ReportController
        from helink.services.report_service import ReportService
        results = []
        destination = Path(self.temp.name) / 'report.pdf'
        controller = ReportController(
            ReportService(FlightRepository(self.database)), self.tasks,
        )
        controller.request_export('f', destination, results.append, self.errors.append)
        self.wait_until(lambda: not self.tasks.busy, timeout=10000)
        self.assertEqual(self.errors, [])
        self.assertTrue(destination.exists())
        self.assertGreater(destination.stat().st_size, 100)
        self.assertEqual(destination.read_bytes()[:4], b'%PDF')
        self.assertTrue(results[0][1])


if __name__ == '__main__':
    unittest.main()
