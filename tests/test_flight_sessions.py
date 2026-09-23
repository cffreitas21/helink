"""Regression tests for same-day Garmin flight imports."""

import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from helink.repositories.database_manager import SCHEMA
from helink.repositories.flight_repository import FlightRepository
from helink.services.flight_import_service import FlightImportService


def csv_file(name, content):
    return name, content.encode('utf-8')


class FlightSessionImportTests(unittest.TestCase):
    def setUp(self):
        connection = sqlite3.connect(':memory:')
        connection.row_factory = sqlite3.Row
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT INTO aircraft(id,registration,model,serial_number) "
            "VALUES('aircraft-1','CS-HAA','H125','123')"
        )
        self.connection = connection
        self.repository = FlightRepository(SimpleNamespace(connection=connection))
        self.service = FlightImportService(self.repository)

    def tearDown(self):
        self.connection.close()

    @staticmethod
    def engine(start, finish):
        name = f'2026-09-23_{start.replace(":", "")}_LPBJ_1.csv'
        return csv_file(
            name,
            'Timestamp,N1,ITT\n'
            f'2026-09-23 {start},70,700\n'
            f'2026-09-23 {finish},72,710\n',
        )

    def import_blobs(self, blobs):
        with patch(
            'helink.services.garmin_file_parser._collect_csv_blobs',
            return_value=blobs,
        ):
            return self.service.import_for_aircraft(['in-memory'], 'aircraft-1')

    def test_two_engine_recordings_on_same_day_are_separate(self):
        first = self.engine('11:00:00', '11:10:00')
        second = self.engine('14:00:00', '14:10:00')
        gps = csv_file(
            'log_260923_110000_LPBJ.csv',
            'Lcl Time,Latitude,Longitude\n'
            '2026-09-23 11:12:00,38.0,-8.0\n'
            '2026-09-23 14:12:00,39.0,-8.0\n',
        )
        cas = csv_file(
            '2026-09-23_110000_LPBJ_5.csv',
            'Timestamp,Alert Name,Level,Alert State\n'
            '2026-09-23 11:06:00,FIRST,CAUTION,SET\n'
            '2026-09-23 14:06:00,SECOND,CAUTION,SET\n',
        )
        result = self.import_blobs([first, second, gps, cas])
        self.assertEqual(result.flight_count, 2)
        flights = sorted(self.repository.find_all('aircraft-1'), key=lambda f: f.departure_time)
        self.assertEqual([f.departure_time for f in flights], ['11:00:00', '14:00:00'])
        for flight, alert_name, latitude in zip(flights, ('FIRST', 'SECOND'), (38.0, 39.0)):
            details = self.repository.find_by_id(flight.id)
            self.assertEqual(len(details.engine_data), 2)
            self.assertEqual(len(details.data_log), 1)
            self.assertEqual(details.data_log[0].latitude, latitude)
            self.assertEqual([alert.alert_name for alert in details.alerts], [alert_name])
            self.assertEqual(details.arrival_time, f'{flight.departure_time[:2]}:12:00')
            self.assertEqual(details.duration, '12 min')

        original_ids = {flight.id for flight in flights}
        repeated = self.import_blobs([first])
        self.assertEqual(repeated.flight_count, 1)
        self.assertEqual(
            {flight.id for flight in self.repository.find_all('aircraft-1')},
            original_ids,
        )

    def test_unmatched_alert_file_does_not_create_a_flight(self):
        self.import_blobs([self.engine('11:00:00', '11:10:00')])
        unrelated = csv_file(
            '2026-09-23_160000_LPBJ_5.csv',
            'Timestamp,Alert Name,Level,Alert State\n'
            '2026-09-23 16:00:00,UNRELATED,CAUTION,SET\n',
        )
        result = self.import_blobs([unrelated])
        self.assertEqual(result.flight_count, 0)
        self.assertEqual(len(result.skipped_files), 1)
        self.assertEqual(len(self.repository.find_all('aircraft-1')), 1)

    def test_preflight_gps_reading_is_not_the_arrival(self):
        engine = self.engine('11:00:00', '11:10:00')
        gps = csv_file(
            'log_260923_105900_LPBJ.csv',
            'Lcl Time,Latitude,Longitude\n'
            '2026-09-23 10:59:00,38.0,-8.0\n',
        )
        self.import_blobs([engine, gps])
        flight = self.repository.find_all('aircraft-1')[0]
        self.assertEqual(flight.arrival_time, '11:10:00')
        self.assertEqual(flight.duration, '10 min')


if __name__ == '__main__':
    unittest.main()
