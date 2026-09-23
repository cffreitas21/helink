from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from helink.services.garmin_file_parser import parse_files


ProgressCallback = Callable[[float, str], None]


@dataclass(frozen=True)
class ImportResult:
    flight_count: int
    file_count: int
    skipped_files: tuple[tuple[str, str], ...]


class FlightImportService:
    def __init__(self, flights):
        self.flights = flights

    def import_for_aircraft(
        self, paths, aircraft_id, progress: ProgressCallback | None = None
    ):
        skipped = []
        parsed = parse_files(
            paths, aircraft_id, progress=progress,
            skipped_files=skipped,
            existing_sessions=self.flights.list_engine_sessions(aircraft_id),
        )
        eligible, file_count = self._only_flights_with_engine_data(
            parsed, skipped,
            lambda flight: self.flights.has_engine_data(flight['id']),
        )
        self._save(eligible, progress)
        return ImportResult(len(eligible), file_count, tuple(skipped))

    def add_to_flight(
        self,
        paths,
        flight_id,
        file_type,
        progress: ProgressCallback | None = None,
    ):
        existing = self.flights.find_metadata_by_id(flight_id)
        if existing is None:
            raise ValueError('The selected flight no longer exists.')

        skipped = []
        parsed = parse_files(
            paths, existing.aircraft_id, file_type, progress=progress,
            skipped_files=skipped,
            target_flight={
                'id': existing.id,
                'aircraft_id': existing.aircraft_id,
                'flight_date': existing.flight_date,
                'departure_time': existing.departure_time,
                'arrival_time': existing.arrival_time,
                'origin': existing.origin,
            },
        )
        for flight in parsed:
            flight['flight_date'] = existing.flight_date
            flight['departure_time'] = existing.departure_time
            flight['origin'] = existing.origin
            if not flight['data_log']:
                flight['destination'] = existing.destination

        has_engine_data = self.flights.has_engine_data(flight_id)
        eligible, file_count = self._only_flights_with_engine_data(
            parsed, skipped, lambda flight: has_engine_data,
        )
        self._save(eligible, progress)
        return ImportResult(len(eligible), file_count, tuple(skipped))

    @staticmethod
    def _only_flights_with_engine_data(flights, skipped, has_existing_engine):
        eligible = []
        accepted_names = set()
        for flight in flights:
            source_files = flight.pop('_source_files', [])
            if flight['engine_data'] or has_existing_engine(flight):
                eligible.append(flight)
                accepted_names.update(source_files)
            else:
                reason = (
                    'Flight not imported: no engine data recording is '
                    f'available for {flight["flight_date"]}.'
                )
                skipped.extend((name, reason) for name in source_files)
        return eligible, len(accepted_names)

    def _save(self, flights, progress):
        def write_progress(completed, total, message):
            if progress:
                fraction = completed / max(1, total)
                progress(70 + 29 * fraction, message)

        if flights:
            self.flights.save_many(flights, write_progress)
        if progress:
            progress(100, 'File import complete.')
