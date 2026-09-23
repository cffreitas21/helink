import uuid
from helink.models.aircraft import Aircraft

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

    def add(self,registration,model,serial_number):
        aircraft_id=registration.lower().replace(' ','-')
        with self.connection:self.connection.execute('INSERT INTO aircraft(id,registration,model,serial_number,flight_hours) VALUES(?,?,?,?,0)',(aircraft_id,registration.strip(),model.strip(),serial_number.strip()))
        return aircraft_id

    def delete(self,aircraft_id):
        with self.connection:self.connection.execute('DELETE FROM aircraft WHERE id=?',(aircraft_id,))
