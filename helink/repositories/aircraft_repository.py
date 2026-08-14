import uuid
from helink.models.aircraft import Aircraft

class AircraftRepository:
    def __init__(self,database):self.database=database
    @property
    def connection(self):return self.database.connection

    def find_all(self):
        sql="""SELECT a.*,COALESCE((SELECT flight_date FROM flights f WHERE f.aircraft_id=a.id ORDER BY flight_date DESC LIMIT 1),'None') last_flight,COALESCE((SELECT COUNT(*) FROM alerts al JOIN flights f ON f.id=al.flight_id WHERE f.aircraft_id=a.id AND al.level='WARNING' AND al.trigger_state='ACTIVE'),0) active_alerts,(SELECT COUNT(*) FROM flights f WHERE f.aircraft_id=a.id) flight_count FROM aircraft a ORDER BY registration"""
        return [Aircraft.from_record(dict(row)) for row in self.connection.execute(sql)]

    def engine_averages(self,aircraft_id):
        row=self.connection.execute("""SELECT AVG(flight_itt) avg_itt,AVG(flight_eng_ot) avg_eng_ot,AVG(flight_xmsn_ot) avg_xmsn_ot FROM(SELECT AVG(e.itt) flight_itt,AVG(e.eng_ot) flight_eng_ot,AVG(e.xmsn_ot) flight_xmsn_ot FROM flights f JOIN engine_data e ON e.flight_id=f.id WHERE f.aircraft_id=? GROUP BY f.id HAVING MAX(ABS(e.itt))+MAX(ABS(e.eng_ot))+MAX(ABS(e.xmsn_ot))>0) per_flight""",(aircraft_id,)).fetchone()
        return dict(row)

    def add(self,registration,model,serial_number):
        aircraft_id=registration.lower().replace(' ','-')
        with self.connection:self.connection.execute('INSERT INTO aircraft(id,registration,model,serial_number,flight_hours) VALUES(?,?,?,?,0)',(aircraft_id,registration.strip(),model.strip(),serial_number.strip()))
        return aircraft_id

    def delete(self,aircraft_id):
        with self.connection:self.connection.execute('DELETE FROM aircraft WHERE id=?',(aircraft_id,))
