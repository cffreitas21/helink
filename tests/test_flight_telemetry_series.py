"""Timestamp alignment tests using synthetic engine and GPS records."""

import unittest
from dataclasses import replace
from math import isnan

from helink.models.flight.engine_data import EngineData
from helink.models.flight.flight import Flight
from helink.models.flight.gps_data import GPSData
from helink.services.flight_telemetry_series import flight_parameter_series


class FlightTelemetrySeriesTests(unittest.TestCase):
    def setUp(self):
        self.engine = tuple(
            EngineData(id=index, flight_id='test',
                       timestamp=f'2026-09-28 11:00:{index:02d}', itt=600 + index)
            for index in range(3)
        )
        self.flight = Flight(
            id='test', aircraft_id='test', flight_date='2026-09-28',
            engine_data=self.engine,
            data_log=(GPSData(id=1, flight_id='test', timestamp='11:00:01',
                              ias=105, alt_ind=1200),),
        )

    def test_engine_values_keep_their_recorded_order(self):
        self.assertEqual(
            flight_parameter_series(self.flight, 'itt', self.engine), [600, 601, 602],
        )

    def test_gps_values_match_clock_seconds_and_missing_seconds_remain_gaps(self):
        values = flight_parameter_series(self.flight, 'ias', self.engine)
        self.assertTrue(isnan(values[0]))
        self.assertEqual(values[1], 105)
        self.assertTrue(isnan(values[2]))

    def test_zero_is_valid_and_invalid_values_do_not_create_zero_samples(self):
        gps = (
            replace(self.flight.data_log[0], ias=0),
            GPSData(id=2, flight_id='test', timestamp='11:00:02', ias=float('inf')),
        )
        flight = replace(self.flight, data_log=gps)
        values = flight_parameter_series(flight, 'ias', self.engine)
        self.assertEqual(values[1], 0)
        self.assertTrue(isnan(values[2]))

    def test_missing_and_invalid_timestamps_are_not_associated_to_a_sample(self):
        for timestamp in (None, 'unknown', '25:00:01', '11:90:01', '11:00:91'):
            with self.subTest(timestamp=timestamp):
                gps = replace(self.flight.data_log[0], timestamp=timestamp)
                flight = replace(self.flight, data_log=(gps,))
                self.assertTrue(all(isnan(value) for value in
                    flight_parameter_series(flight, 'ias', self.engine)))

    def test_full_date_and_fractional_seconds_match_the_same_recorded_second(self):
        gps = replace(self.flight.data_log[0], timestamp='2026-09-28T11:00:01.250')
        flight = replace(self.flight, data_log=(gps,))
        self.assertEqual(flight_parameter_series(flight, 'ias', self.engine)[1], 105)

    def test_gps_only_flight_uses_its_own_recorded_timeline(self):
        flight = replace(self.flight, engine_data=())
        self.assertEqual(
            flight_parameter_series(flight, 'ias', flight.data_log), [105],
        )
        self.assertTrue(isnan(
            flight_parameter_series(flight, 'itt', flight.data_log)[0]
        ))


if __name__ == '__main__':
    unittest.main()
