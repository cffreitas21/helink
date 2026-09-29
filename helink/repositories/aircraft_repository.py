import uuid
from sys import float_info

from helink.models.aircraft import Aircraft
from helink.models.aircraft_parameter_day import AircraftParameterDay


TREND_PARAMETER_TABLES = {
    **dict.fromkeys((
        'oat', 'n1', 'n2', 'nr', 'itt', 'tq', 'eng_ot', 'eng_op',
        'xmsn_ot', 'xmsn_op', 'fuel_press',
    ), 'engine_data'),
    **dict.fromkeys(('ias', 'alt_ind'), 'gps_data'),
}

class AircraftRepository:

    def __init__(self,database):self.database=database
    @property

    def connection(self):return self.database.connection

    def find_all(self):
        sql="""SELECT a.*,COALESCE((SELECT flight_date FROM flights f WHERE f.aircraft_id=a.id ORDER BY flight_date DESC LIMIT 1),'None') last_flight,COALESCE((SELECT COUNT(*) FROM alerts al JOIN flights f ON f.id=al.flight_id WHERE f.aircraft_id=a.id AND al.level='WARNING' AND al.trigger_state='ACTIVE'),0) active_alerts,(SELECT COUNT(*) FROM flights f WHERE f.aircraft_id=a.id) flight_count FROM aircraft a ORDER BY registration"""
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
    ):
        """Aggregate only the chosen sensor, returning one row per aircraft/day."""
        if parameter not in TREND_PARAMETER_TABLES:
            raise ValueError('The selected parameter is not available for fleet analysis.')
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

    def add(self,registration,model,serial_number):
        aircraft_id=registration.lower().replace(' ','-')
        with self.connection:self.connection.execute('INSERT INTO aircraft(id,registration,model,serial_number,flight_hours) VALUES(?,?,?,?,0)',(aircraft_id,registration.strip(),model.strip(),serial_number.strip()))
        return aircraft_id

    def delete(self,aircraft_id):
        with self.connection:self.connection.execute('DELETE FROM aircraft WHERE id=?',(aircraft_id,))
