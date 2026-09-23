from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Iterable

from helink.models.flight import Flight


WriteProgress = Callable[[int, int, str], None]


class FlightRepository:
    """Persists flights and telemetry using atomic batch operations."""

    BATCH_SIZE = 5_000

    def __init__(self, database):
        self.database = database

    @property
    def connection(self):
        return self.database.connection

    def find_all(self, aircraft_id=None):
        query = 'SELECT * FROM flights'
        params = []
        if aircraft_id:
            query += ' WHERE aircraft_id=?'
            params = [aircraft_id]
        query += ' ORDER BY flight_date DESC, departure_time DESC'
        result = []
        for row in self.connection.execute(query, params):
            record = dict(row)
            record['imported_files'] = json.loads(record['imported_files'])
            result.append(Flight.from_record(record))
        return result

    def find_metadata_by_id(self, flight_id):
        """Load only flight metadata, avoiding large telemetry collections."""
        row = self.connection.execute(
            'SELECT * FROM flights WHERE id=?', (flight_id,)
        ).fetchone()
        if not row:
            return None
        record = dict(row)
        record['imported_files'] = json.loads(record['imported_files'])
        return Flight.from_record(record)

    def has_engine_data(self, flight_id):
        return self.connection.execute(
            'SELECT 1 FROM engine_data WHERE flight_id=? LIMIT 1',
            (flight_id,),
        ).fetchone() is not None

    def has_engine_data_for_aircraft_date(self, aircraft_id, flight_date):
        return self.connection.execute(
            'SELECT 1 FROM flights f JOIN engine_data e ON e.flight_id=f.id '
            'WHERE f.aircraft_id=? AND f.flight_date=? LIMIT 1',
            (aircraft_id, flight_date),
        ).fetchone() is not None

    def list_engine_sessions(self, aircraft_id):
        """Return existing flight windows for matching supplementary files."""
        rows = self.connection.execute(
            """SELECT f.id, f.aircraft_id, f.flight_date, f.departure_time,
                      f.arrival_time, f.origin,
                      (SELECT e.timestamp FROM engine_data e
                       WHERE e.flight_id=f.id ORDER BY e.seq LIMIT 1)
                          AS engine_start,
                      (SELECT e.timestamp FROM engine_data e
                       WHERE e.flight_id=f.id ORDER BY e.seq DESC LIMIT 1)
                          AS engine_end
               FROM flights f
               WHERE f.aircraft_id=?
                 AND EXISTS(SELECT 1 FROM engine_data e WHERE e.flight_id=f.id)""",
            (aircraft_id,),
        )
        return [dict(row) for row in rows]

    def find_by_id(self, flight_id):
        row = self.connection.execute(
            'SELECT * FROM flights WHERE id=?', (flight_id,)
        ).fetchone()
        if not row:
            return None
        record = dict(row)
        record['imported_files'] = json.loads(record['imported_files'])
        record['engine_data'] = [
            dict(item) for item in self.connection.execute(
                'SELECT * FROM engine_data WHERE flight_id=? ORDER BY seq',
                (flight_id,),
            )
        ]
        record['data_log'] = [
            dict(item) for item in self.connection.execute(
                'SELECT * FROM gps_data WHERE flight_id=? ORDER BY seq',
                (flight_id,),
            )
        ]
        record['alerts'] = []
        for alert_row in self.connection.execute(
            """SELECT * FROM alerts
               WHERE flight_id=?
                 AND UPPER(COALESCE(level,'')) IN
                     ('WARNING','CAUTION','SAFE ANN')
               ORDER BY timestamp""",
            (flight_id,),
        ):
            alert = dict(alert_row)
            alert['triggers'] = json.loads(
                alert.get('triggers_json') or '[]'
            )
            record['alerts'].append(alert)
        return Flight.from_record(record)

    def save(self, flight):
        return self.save_many([flight])[0]

    def save_many(
        self,
        flights: Iterable[dict],
        progress: WriteProgress | None = None,
    ) -> list[str]:
        """Save several flights in one transaction and report write progress."""
        flights = list(flights)
        total = max(
            1,
            len(flights) + sum(
                len(flight.get('engine_data', ()))
                + len(flight.get('data_log', ()))
                + len(flight.get('exceedances', ()))
                + len(flight.get('cas_messages', ()))
                for flight in flights
            ),
        )
        completed = 0
        saved_ids = []

        def report(increment=0, message='Saving flight data...'):
            nonlocal completed
            completed += increment
            if progress:
                progress(min(completed, total), total, message)

        if progress:
            progress(0, total, 'Preparing flight records...')

        # Exceptions from progress (including cancellation) roll back all writes.
        with self.connection:
            for index, flight in enumerate(flights, 1):
                message = f'Saving flight {index} of {len(flights)}...'
                flight_id = self._save_flight(flight, report, message)
                saved_ids.append(flight_id)
                report(1, message)

        if progress:
            progress(total, total, 'Finalizing flight records...')
        return saved_ids

    def _save_flight(self, flight, report, message):
        existing = self.connection.execute(
            """SELECT id, arrival_time, duration, destination, imported_files,
                      predictive_report
               FROM flights
               WHERE id=? AND aircraft_id=?""",
            (flight['id'], flight['aircraft_id']),
        ).fetchone()
        flight_id = existing['id'] if existing else flight.get('id') or str(uuid.uuid4())

        old_files = []
        if existing:
            try:
                old_files = json.loads(existing['imported_files'] or '[]')
            except (TypeError, json.JSONDecodeError):
                old_files = []
        imported_files = sorted(
            set(old_files).union(flight.get('imported_files', ()))
        )

        arrival_time = self._latest_arrival_time(
            flight.get('departure_time'),
            flight.get('arrival_time'),
            self._derive_arrival_time(flight),
            existing['arrival_time'] if existing else '',
        )
        duration = (
            self._duration_between(flight.get('departure_time'), arrival_time)
            or flight.get('duration', '')
            or (existing['duration'] if existing else '')
        )

        destination = flight.get('destination', '')
        if existing and not flight.get('data_log'):
            destination = existing['destination'] or destination

        values = (
            flight['aircraft_id'],
            flight['flight_date'],
            flight.get('departure_time', ''),
            arrival_time,
            duration,
            flight.get('origin', ''),
            destination,
            json.dumps(imported_files),
        )
        if existing:
            self.connection.execute(
                """UPDATE flights
                   SET aircraft_id=?, flight_date=?, departure_time=?,
                       arrival_time=?, duration=?, origin=?, destination=?,
                       imported_files=?
                   WHERE id=?""",
                (*values, flight_id),
            )
        else:
            self.connection.execute(
                """INSERT INTO flights(
                       id, aircraft_id, flight_date, departure_time,
                       arrival_time, duration, origin, destination,
                       imported_files, predictive_report
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    flight_id,
                    *values,
                    flight.get('predictive_report', ''),
                ),
            )

        engine_data = flight.get('engine_data', ())
        if engine_data:
            self.connection.execute(
                'DELETE FROM engine_data WHERE flight_id=?', (flight_id,)
            )
            rows = (
                (
                    flight_id, seq, item.get('timestamp'), item.get('OAT'),
                    item.get('N1'), item.get('N2'), item.get('ITT'),
                    item.get('NR'), item.get('TQ'), item.get('ENG_OT'),
                    item.get('FUEL_PRESS'), item.get('ENG_OP'),
                    item.get('XMSN_OP'), item.get('XMSN_OT'),
                )
                for seq, item in enumerate(engine_data)
            )
            self._executemany_batched(
                """INSERT INTO engine_data(
                       flight_id,seq,timestamp,oat,n1,n2,itt,nr,tq,eng_ot,
                       fuel_press,eng_op,xmsn_op,xmsn_ot
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows, len(engine_data), report, message,
            )

        data_log = flight.get('data_log', ())
        if data_log:
            self.connection.execute(
                'DELETE FROM gps_data WHERE flight_id=?', (flight_id,)
            )
            rows = (
                (
                    flight_id, seq, item.get('timestamp'),
                    item.get('latitude'), item.get('longitude'),
                    item.get('altInd'), item.get('ias'), item.get('pitch'),
                    item.get('roll'), item.get('heading'),
                )
                for seq, item in enumerate(data_log)
            )
            self._executemany_batched(
                """INSERT INTO gps_data(
                       flight_id,seq,timestamp,latitude,longitude,alt_ind,
                       ias,pitch,roll,heading
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                rows, len(data_log), report, message,
            )

        for collection, kind in (
            ('exceedances', 'EXCEEDANCE'), ('cas_messages', 'CAS')
        ):
            alerts = [
                alert for alert in flight.get(collection, ())
                if str(alert.get('level') or '').strip().upper()
                in ('WARNING', 'CAUTION', 'SAFE ANN')
            ]
            if not alerts:
                continue
            self.connection.execute(
                'DELETE FROM alerts WHERE flight_id=? AND kind=?',
                (flight_id, kind),
            )
            rows = (
                (
                    flight_id, kind, alert.get('timestamp'),
                    alert.get('alertState'), alert.get('alertName'),
                    str(alert.get('level') or '').strip().upper(),
                    alert.get('description'), alert.get('triggerName'),
                    str(alert.get('triggerValue', '')),
                    alert.get('triggerUnits'), alert.get('triggerState'),
                    json.dumps(alert.get('triggers', ())),
                )
                for alert in alerts
            )
            self._executemany_batched(
                """INSERT INTO alerts(
                       flight_id,kind,timestamp,alert_state,alert_name,level,
                       description,trigger_name,trigger_value,trigger_units,
                       trigger_state,triggers_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows, len(alerts), report, message,
            )
        return flight_id

    def _executemany_batched(
        self, sql, rows, row_count, report, message
    ):
        iterator = iter(rows)
        written = 0
        while written < row_count:
            batch = []
            for _ in range(min(self.BATCH_SIZE, row_count - written)):
                try:
                    batch.append(next(iterator))
                except StopIteration:
                    break
            if not batch:
                break
            self.connection.executemany(sql, batch)
            written += len(batch)
            report(len(batch), message)

    @staticmethod
    def _clock_time(value):
        matches = re.findall(
            r'(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?',
            str(value or ''),
        )
        if not matches:
            return ''
        hour, minute, second = matches[-1]
        return f'{int(hour):02d}:{minute}:{second or "00"}'

    @classmethod
    def _duration_between(cls, departure_time, arrival_time):
        departure = cls._clock_time(departure_time)
        arrival = cls._clock_time(arrival_time)
        if not departure or not arrival:
            return ''

        def seconds(value):
            hour, minute, second = map(int, value.split(':'))
            return hour * 3600 + minute * 60 + second

        difference = seconds(arrival) - seconds(departure)
        if difference < 0:
            difference += 86400
        minutes = max(1, round(difference / 60))
        if minutes < 60:
            return f'{minutes} min'
        hours, remaining = divmod(minutes, 60)
        return f'{hours}h {remaining}m' if remaining else f'{hours}h'

    @classmethod
    def _latest_arrival_time(cls, departure_time, *candidates):
        departure = cls._clock_time(departure_time)
        valid = [value for item in candidates if (value := cls._clock_time(item))]
        if not valid:
            return ''
        if not departure:
            return valid[0]

        def seconds(value):
            hour, minute, second = map(int, value.split(':'))
            return hour * 3600 + minute * 60 + second

        start = seconds(departure)

        def elapsed(value):
            difference = (seconds(value) - start) % 86400
            # A reading shortly before engine start is not a next-day arrival.
            return difference if difference <= 12 * 3600 else -1

        latest = max(valid, key=elapsed)
        return latest if elapsed(latest) >= 0 else ''

    @classmethod
    def _derive_arrival_time(cls, flight):
        for collection in ('engine_data', 'data_log'):
            for item in reversed(flight.get(collection, ())):
                timestamp = (
                    item.get('timestamp') if isinstance(item, dict)
                    else getattr(item, 'timestamp', None)
                )
                if arrival_time := cls._clock_time(timestamp):
                    return arrival_time
        return ''

    def delete(self, flight_id):
        with self.connection:
            self.connection.execute(
                'DELETE FROM flights WHERE id=?', (flight_id,)
            )

    def delete_many(self, flight_ids):
        with self.connection:
            self.connection.executemany(
                'DELETE FROM flights WHERE id=?',
                [(flight_id,) for flight_id in flight_ids],
            )

    def save_report(self, flight_id, text):
        with self.connection:
            self.connection.execute(
                'UPDATE flights SET predictive_report=? WHERE id=?',
                (text, flight_id),
            )
