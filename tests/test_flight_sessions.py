"""Regression tests for same-day Garmin flight imports."""

import io
import sqlite3
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from helink.repositories.database_manager import SCHEMA
from helink.repositories.flight_repository import FlightRepository
from helink.services.flight_import_service import FlightImportService


def csv_file(name, content, direct=True):
    return name, content.encode('utf-8'), direct


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

    def test_unmatched_zip_alert_file_does_not_create_a_flight(self):
        self.import_blobs([self.engine('11:00:00', '11:10:00')])
        unrelated = csv_file(
            '2026-09-23_160000_LPBJ_5.csv',
            'Timestamp,Alert Name,Level,Alert State\n'
            '2026-09-23 16:00:00,UNRELATED,CAUTION,SET\n',
            direct=False,
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

    def test_direct_exceedance_csv_creates_standalone_record(self):
        exceedance = csv_file(
            '2026-09-23_110600_LPBJ_2.csv',
            'Timestamp,Alert Name,Level,Alert State\n'
            '2026-09-23 11:06:00,NR LIMIT,WARNING,SET\n',
        )
        result = self.import_blobs([exceedance])
        self.assertEqual((result.flight_count, result.file_count), (1, 1))
        flight = self.repository.find_all('aircraft-1')[0]
        details = self.repository.find_by_id(flight.id)
        self.assertEqual(details.engine_data, ())
        self.assertEqual([alert.alert_name for alert in details.alerts], ['NR LIMIT'])

        self.import_blobs([exceedance])
        self.assertEqual(len(self.repository.find_all('aircraft-1')), 1)

    def test_direct_route_csv_creates_standalone_record(self):
        route = csv_file(
            'data_log.csv',
            'Lcl Date,Lcl Time,Latitude,Longitude\n'
            '2025-10-30,11:00:00,38.0,-8.0\n'
            '2025-10-30,11:10:00,38.1,-8.1\n',
        )
        result = self.import_blobs([route])
        self.assertEqual((result.flight_count, result.file_count), (1, 1))
        flight = self.repository.find_all('aircraft-1')[0]
        details = self.repository.find_by_id(flight.id)
        self.assertEqual(flight.flight_date, '2025-10-30')
        self.assertEqual(flight.departure_time, '11:00:00')
        self.assertEqual(len(details.data_log), 2)
        self.assertEqual(details.engine_data, ())

    def test_direct_csvs_use_time_not_just_date(self):
        early = csv_file(
            '2026-09-23_110000_LPBJ_2.csv',
            'Timestamp,Alert Name,Level,Alert State\n'
            '2026-09-23 11:00:00,EARLY,WARNING,SET\n',
        )
        late = csv_file(
            '2026-09-23_140000_LPBJ_2.csv',
            'Timestamp,Alert Name,Level,Alert State\n'
            '2026-09-23 14:00:00,LATE,WARNING,SET\n',
        )
        result = self.import_blobs([early, late])
        self.assertEqual(result.flight_count, 2)
        self.assertEqual(
            sorted(f.departure_time for f in self.repository.find_all('aircraft-1')),
            ['11:00:00', '14:00:00'],
        )

    def test_direct_exceedance_can_join_standalone_route(self):
        route = csv_file(
            'log_260923_110000_LPBJ.csv',
            'Lcl Date,Lcl Time,Latitude,Longitude\n'
            '2026-09-23,11:00:00,38.0,-8.0\n'
            '2026-09-23,11:10:00,38.1,-8.1\n',
        )
        exceedance = csv_file(
            '2026-09-23_110600_LPBJ_2.csv',
            'Timestamp,Alert Name,Level,Alert State\n'
            '2026-09-23 11:06:00,NR LIMIT,WARNING,SET\n',
        )
        result = self.import_blobs([route, exceedance])
        self.assertEqual(result.flight_count, 1)
        self.assertEqual(len(self.repository.find_all('aircraft-1')), 1)

        zipped_exceedance = (exceedance[0], exceedance[1], False)
        result = self.import_blobs([zipped_exceedance])
        self.assertEqual(result.flight_count, 0)
        self.assertEqual(len(result.skipped_files), 1)

    def test_direct_csv_can_be_added_to_standalone_flight(self):
        route = csv_file(
            'log_260923_110000_LPBJ.csv',
            'Lcl Date,Lcl Time,Latitude,Longitude\n'
            '2026-09-23,11:00:00,38.0,-8.0\n',
        )
        self.import_blobs([route])
        flight_id = self.repository.find_all('aircraft-1')[0].id
        exceedance = csv_file(
            '2026-09-23_110600_LPBJ_2.csv',
            'Timestamp,Alert Name,Level,Alert State\n'
            '2026-09-23 11:06:00,NR LIMIT,WARNING,SET\n',
        )
        with patch(
            'helink.services.garmin_file_parser._collect_csv_blobs',
            return_value=[exceedance],
        ):
            result = self.service.add_to_flight(
                ['in-memory'], flight_id, '2_Exceedance_Log'
            )
        self.assertEqual(result.flight_count, 1)
        self.assertEqual(len(self.repository.find_all('aircraft-1')), 1)
        details = self.repository.find_by_id(flight_id)
        self.assertEqual([alert.alert_name for alert in details.alerts], ['NR LIMIT'])

    def test_direct_logbook_csv_is_visible_as_cas_event(self):
        logbook = csv_file(
            '2026-09-23_110600_LPBJ_6.csv',
            'Timestamp,Alert Name,Level,Alert State\n'
            '2026-09-23 11:06:00,ROTOR LOW WARNING,WARNING,SET\n',
        )
        result = self.import_blobs([logbook])
        self.assertEqual(result.flight_count, 1)
        flight = self.repository.find_all('aircraft-1')[0]
        details = self.repository.find_by_id(flight.id)
        self.assertEqual(details.imported_files, ('6_Logbook',))
        self.assertEqual(
            [(alert.kind, alert.alert_name) for alert in details.alerts],
            [('CAS', 'ROTOR LOW WARNING')],
        )

    def test_later_csvs_enrich_the_same_standalone_record(self):
        route = csv_file(
            'log_260923_110000_LPBJ.csv',
            'Lcl Date,Lcl Time,Latitude,Longitude\n'
            '2026-09-23,11:00:00,38.0,-8.0\n'
            '2026-09-23,11:10:00,38.1,-8.1\n',
        )
        exceedance = csv_file(
            '2026-09-23_110600_LPBJ_2.csv',
            'Timestamp,Alert Name,Level,Alert State\n'
            '2026-09-23 11:06:00,NR LIMIT,WARNING,SET\n',
        )
        self.import_blobs([route])
        flight_id = self.repository.find_all('aircraft-1')[0].id
        self.import_blobs([exceedance])
        self.import_blobs([self.engine('11:00:00', '11:10:00')])
        flights = self.repository.find_all('aircraft-1')
        self.assertEqual([flight.id for flight in flights], [flight_id])
        details = self.repository.find_by_id(flight_id)
        self.assertEqual(len(details.data_log), 2)
        self.assertEqual(len(details.engine_data), 2)
        self.assertEqual([alert.alert_name for alert in details.alerts], ['NR LIMIT'])

    def test_file_picker_paths_distinguish_csv_from_zip(self):
        name = '2026-09-23_110600_LPBJ_2.csv'
        content = (
            'Timestamp,Alert Name,Level,Alert State\n'
            '2026-09-23 11:06:00,NR LIMIT,WARNING,SET\n'
        )
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, 'w') as archive:
            archive.writestr(name, content)
        actual_zipfile = zipfile.ZipFile
        with patch.object(Path, 'read_bytes', return_value=content.encode('utf-8')):
            with patch(
                'helink.services.garmin_file_parser.zipfile.ZipFile',
                side_effect=lambda _path: actual_zipfile(
                    io.BytesIO(archive_buffer.getvalue())
                ),
            ):
                direct = self.service.import_for_aircraft([name], 'aircraft-1')
                zipped = self.service.import_for_aircraft(
                    ['flight_files.zip'], 'aircraft-1'
                )

        self.assertEqual(direct.flight_count, 1)
        self.assertEqual(zipped.flight_count, 0)
        self.assertEqual(len(zipped.skipped_files), 1)
        self.assertEqual(len(self.repository.find_all('aircraft-1')), 1)


if __name__ == '__main__':
    unittest.main()
