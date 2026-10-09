"""SQL persistence and trend aggregation for aircraft records."""

from sys import float_info

from helink.models.aircraft import Aircraft
from helink.models.aircraft_parameter_day import AircraftParameterDay
from helink.models.aircraft_parameter_flight import AircraftParameterFlight


TREND_PARAMETER_TABLES = {
    **dict.fromkeys((
        'oat', 'n1', 'n2', 'nr', 'itt', 'tq', 'eng_ot', 'eng_op',
        'xmsn_ot', 'xmsn_op', 'fuel_press',
    ), 'engine_data'),
    **dict.fromkeys(('ias', 'alt_ind'), 'gps_data'),
}

# The displayed flight duration is already rounded to whole minutes. Use that
# value first so a flight shown as "10 min" passes a 10-minute filter. Older
# records without a duration fall back to their departure/arrival clock times.
# An unmeasurable duration does not pass an active minimum.
_MINIMUM_DURATION_CONDITION = """
f.id IN (
    SELECT eligible.id FROM flights AS eligible
    WHERE COALESCE(
        CASE
            WHEN LOWER(TRIM(eligible.duration)) GLOB '[0-9]* min'
                THEN CAST(TRIM(eligible.duration) AS INTEGER)
            WHEN LOWER(TRIM(eligible.duration)) GLOB '[0-9]*h*'
                THEN CAST(eligible.duration AS INTEGER) * 60
                     + CASE
                           WHEN INSTR(LOWER(eligible.duration), 'm') > 0
                           THEN CAST(SUBSTR(
                               eligible.duration,
                               INSTR(LOWER(eligible.duration), 'h') + 1
                           ) AS INTEGER)
                           ELSE 0
                       END
        END,
        CASE
            WHEN TIME(eligible.departure_time) IS NOT NULL
             AND TIME(eligible.arrival_time) IS NOT NULL
            THEN MAX(1, ROUND((
                (
                    CAST(STRFTIME('%s', '2000-01-01 ' || eligible.arrival_time)
                        AS INTEGER)
                    - CAST(STRFTIME('%s', '2000-01-01 ' || eligible.departure_time)
                        AS INTEGER)
                    + 86400
                ) % 86400
            ) / 60.0))
        END
    ) >= ?
)
"""


def _validate_minimum_duration(minimum_minutes):
    """Require a non-negative whole-minute threshold for trend queries."""
    if (
        isinstance(minimum_minutes, bool)
        or not isinstance(minimum_minutes, int)
        or minimum_minutes < 0
    ):
        raise ValueError(
            'Minimum flight duration must be a non-negative number of minutes.'
        )


class AircraftRepository:
    """Read and write aircraft records and fleet-analysis aggregates."""

    def __init__(self,database):
        """Use the connection managed by ``database``."""
        self.database=database
    @property

    def connection(self):
        """Return the database connection owned by the manager."""
        return self.database.connection

    def find_all(self):
        """List aircraft with their current number of imported flights."""
        sql="""SELECT a.*,(SELECT COUNT(*) FROM flights f WHERE f.aircraft_id=a.id) flight_count FROM aircraft a ORDER BY registration"""
        return [Aircraft.from_record(dict(row)) for row in self.connection.execute(sql)]


    def fleet_summaries(self):
        """Return AVG/MAX telemetry metrics for every aircraft in one query."""
        rows = self.connection.execute(
            """
            WITH telemetry AS (
                SELECT
                    f.aircraft_id,
                    AVG(e.itt) AS avg_itt,
                    MAX(e.itt) AS max_itt,
                    AVG(e.eng_ot) AS avg_eng_ot,
                    MAX(e.eng_ot) AS max_eng_ot,
                    AVG(e.eng_op) AS avg_eng_op,
                    MAX(e.eng_op) AS max_eng_op,
                    AVG(e.xmsn_ot) AS avg_xmsn_ot,
                    MAX(e.xmsn_ot) AS max_xmsn_ot,
                    AVG(e.xmsn_op) AS avg_xmsn_op,
                    MAX(e.xmsn_op) AS max_xmsn_op,
                    AVG(e.fuel_press) AS avg_fuel_press,
                    MAX(e.fuel_press) AS max_fuel_press
                FROM flights f
                JOIN engine_data e ON e.flight_id = f.id
                GROUP BY f.aircraft_id
            )
            SELECT a.id AS aircraft_id, t.*
            FROM aircraft a
            LEFT JOIN telemetry t ON t.aircraft_id = a.id
            """
        ).fetchall()
        return {row['aircraft_id']: dict(row) for row in rows}

    def find_by_id(self, aircraft_id):
        """Fetch one aircraft without scanning fleet alerts or telemetry."""
        row = self.connection.execute(
            """SELECT a.*, (SELECT COUNT(*) FROM flights f
                           WHERE f.aircraft_id=a.id) AS flight_count
               FROM aircraft a WHERE a.id=?""",
            (aircraft_id,),
        ).fetchone()
        return Aircraft.from_record(dict(row)) if row else None

    def find_for_analysis(self):
        """Load the aircraft picker without querying alerts or telemetry."""
        rows = self.connection.execute(
            """SELECT a.*, COUNT(f.id) AS flight_count
               FROM aircraft a LEFT JOIN flights f ON f.aircraft_id=a.id
               GROUP BY a.id ORDER BY a.registration"""
        )
        return [Aircraft.from_record(dict(row)) for row in rows]

    def daily_parameter_trends(
        self, aircraft_ids, parameter, *, start_date=None, end_date=None,
        minimum_minutes=0,
    ):
        """Aggregate only the chosen sensor, returning one row per aircraft/day."""
        if parameter not in TREND_PARAMETER_TABLES:
            raise ValueError('The selected parameter is not available for fleet analysis.')
        _validate_minimum_duration(minimum_minutes)
        aircraft_ids = tuple(dict.fromkeys(aircraft_ids))
        if not aircraft_ids:
            return []
        table = TREND_PARAMETER_TABLES[parameter]
        placeholders = ','.join('?' for _ in aircraft_ids)
        # Table and column identifiers come exclusively from the whitelist.
        # Values and date bounds are always bound parameters.
        conditions = [
            f'f.aircraft_id IN ({placeholders})',
            "date(f.flight_date) IS NOT NULL",
            f"typeof(d.{parameter}) IN ('real', 'integer')",
            f'd.{parameter} BETWEEN ? AND ?',
        ]
        values = [*aircraft_ids, -float_info.max, float_info.max]
        if start_date:
            conditions.append('f.flight_date >= ?')
            values.append(start_date)
        if end_date:
            conditions.append('f.flight_date <= ?')
            values.append(end_date)
        if minimum_minutes:
            conditions.append(_MINIMUM_DURATION_CONDITION)
            values.append(minimum_minutes)
        rows = self.connection.execute(
            f"""SELECT f.aircraft_id, f.flight_date,
                       AVG(d.{parameter}) AS average,
                       MAX(d.{parameter}) AS maximum,
                       COUNT(DISTINCT f.id) AS flight_count,
                       COUNT(*) AS sample_count
                FROM flights f JOIN {table} d ON d.flight_id=f.id
                WHERE {' AND '.join(conditions)}
                GROUP BY f.aircraft_id, f.flight_date
                ORDER BY f.flight_date, f.aircraft_id""",
            values,
        )
        return [AircraftParameterDay.from_record(dict(row)) for row in rows]

    def parameter_flights_for_day(
        self, aircraft_id, flight_date, parameter, *, minimum_minutes=0,
    ):
        """Return every flight of a day, including those missing this sensor."""
        if parameter not in TREND_PARAMETER_TABLES:
            raise ValueError('The selected parameter is not available for fleet analysis.')
        _validate_minimum_duration(minimum_minutes)
        table = TREND_PARAMETER_TABLES[parameter]
        duration_clause = (
            f' AND {_MINIMUM_DURATION_CONDITION}' if minimum_minutes else ''
        )
        values = [-float_info.max, float_info.max, aircraft_id, flight_date]
        if minimum_minutes:
            values.append(minimum_minutes)
        rows = self.connection.execute(
            f"""SELECT f.id AS flight_id, f.aircraft_id, f.flight_date,
                       f.departure_time, f.arrival_time,
                       AVG(d.{parameter}) AS average,
                       MAX(d.{parameter}) AS maximum,
                       COUNT(d.{parameter}) AS sample_count
                FROM flights f
                LEFT JOIN {table} d ON d.flight_id=f.id
                    AND typeof(d.{parameter}) IN ('real', 'integer')
                    AND d.{parameter} BETWEEN ? AND ?
                WHERE f.aircraft_id=? AND f.flight_date=?
                      {duration_clause}
                GROUP BY f.id
                ORDER BY CASE WHEN COALESCE(f.departure_time, '')='' THEN 1 ELSE 0 END,
                         f.departure_time, f.id""",
            values,
        )
        return [AircraftParameterFlight.from_record(dict(row)) for row in rows]

    def add(self,registration,model,serial_number):
        """Insert an aircraft and return its registration-derived identifier."""
        aircraft_id=registration.lower().replace(' ','-')
        with self.connection:self.connection.execute('INSERT INTO aircraft(id,registration,model,serial_number) VALUES(?,?,?,?)',(aircraft_id,registration.strip(),model.strip(),serial_number.strip()))
        return aircraft_id

    def delete(self,aircraft_id):
        """Delete an aircraft and its dependent flights via foreign-key cascade."""
        with self.connection:self.connection.execute('DELETE FROM aircraft WHERE id=?',(aircraft_id,))
