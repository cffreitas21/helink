import json,uuid
from helink.models.flight import Flight

class FlightRepository:

    def __init__(self,database):self.database=database
    @property

    def connection(self):return self.database.connection

    def find_all(self,aircraft_id=None):
        query='SELECT * FROM flights';params=[]
        if aircraft_id:query+=' WHERE aircraft_id=?';params=[aircraft_id]
        query+=' ORDER BY flight_date DESC,departure_time DESC';result=[]
        for row in self.connection.execute(query,params):
            record=dict(row);record['imported_files']=json.loads(record['imported_files']);result.append(Flight.from_record(record))
        return result

    def find_by_id(self,flight_id):
        row=self.connection.execute('SELECT * FROM flights WHERE id=?',(flight_id,)).fetchone()
        if not row:return None
        record=dict(row);record['imported_files']=json.loads(record['imported_files'])
        record['engine_data']=[dict(x) for x in self.connection.execute('SELECT * FROM engine_data WHERE flight_id=? ORDER BY seq',(flight_id,))]
        record['data_log']=[dict(x) for x in self.connection.execute('SELECT * FROM gps_data WHERE flight_id=? ORDER BY seq',(flight_id,))]
        record['alerts']=[]
        for row in self.connection.execute(
            """SELECT * FROM alerts
               WHERE flight_id=?
                 AND UPPER(COALESCE(level,'')) IN ('WARNING','CAUTION','SAFE ANN')
               ORDER BY timestamp""",
            (flight_id,),
        ):
            alert=dict(row);alert['triggers']=json.loads(alert.get('triggers_json') or '[]');record['alerts'].append(alert)
        return Flight.from_record(record)

    def save(self,flight):
        existing=self.connection.execute('SELECT id FROM flights WHERE aircraft_id=? AND flight_date=?',(flight['aircraft_id'],flight['flight_date'])).fetchone()
        flight_id=existing['id'] if existing else flight.get('id') or str(uuid.uuid4())
        if existing:
            old=self.find_by_id(flight_id)
            if not flight.get('engine_data'):flight['engine_data']=[self._engine_parser(item) for item in old.engine_data]
            if not flight.get('data_log'):flight['data_log']=[self._gps_parser(item) for item in old.data_log]
            old_ex=[a for a in old.alerts if a.kind=='EXCEEDANCE'];old_cas=[a for a in old.alerts if a.kind=='CAS']
            if not flight.get('exceedances'):flight['exceedances']=[self._alert_parser(a) for a in old_ex]
            if not flight.get('cas_messages'):flight['cas_messages']=[self._alert_parser(a) for a in old_cas]
            flight['imported_files']=sorted(set(old.imported_files+tuple(flight.get('imported_files',[]))))
        with self.connection:
            self.connection.execute("""INSERT OR REPLACE INTO flights(id,aircraft_id,flight_date,departure_time,duration,origin,destination,imported_files,predictive_report) VALUES(?,?,?,?,?,?,?,?,COALESCE((SELECT predictive_report FROM flights WHERE id=?),''))""",(flight_id,flight['aircraft_id'],flight['flight_date'],flight.get('departure_time',''),flight.get('duration',''),flight.get('origin',''),flight.get('destination',''),json.dumps(flight.get('imported_files',[])),flight_id))
            for table in ('engine_data','gps_data','alerts'):self.connection.execute(f'DELETE FROM {table} WHERE flight_id=?',(flight_id,))
            for seq,item in enumerate(flight.get('engine_data',[])):
                self.connection.execute('INSERT INTO engine_data(flight_id,seq,timestamp,oat,n1,n2,itt,nr,tq,eng_ot,fuel_press,eng_op,xmsn_op,xmsn_ot) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(flight_id,seq,item.get('timestamp'),item.get('OAT'),item.get('N1'),item.get('N2'),item.get('ITT'),item.get('NR'),item.get('TQ'),item.get('ENG_OT'),item.get('FUEL_PRESS'),item.get('ENG_OP'),item.get('XMSN_OP'),item.get('XMSN_OT')))
            for seq,item in enumerate(flight.get('data_log',[])):
                self.connection.execute('INSERT INTO gps_data(flight_id,seq,timestamp,latitude,longitude,alt_ind,ias,pitch,roll,heading) VALUES(?,?,?,?,?,?,?,?,?,?)',(flight_id,seq,item.get('timestamp'),item.get('latitude'),item.get('longitude'),item.get('altInd'),item.get('ias'),item.get('pitch'),item.get('roll'),item.get('heading')))
            for collection in ('exceedances','cas_messages'):
                for alert in flight.get(collection,[]):
                    level = str(alert.get('level') or '').strip().upper()
                    if level not in ('WARNING', 'CAUTION', 'SAFE ANN'):
                        continue
                    self.connection.execute('INSERT INTO alerts(flight_id,kind,timestamp,alert_state,alert_name,level,description,trigger_name,trigger_value,trigger_units,trigger_state,triggers_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(flight_id,'EXCEEDANCE' if collection=='exceedances' else 'CAS',alert.get('timestamp'),alert.get('alertState'),alert.get('alertName'),level,alert.get('description'),alert.get('triggerName'),str(alert.get('triggerValue','')),alert.get('triggerUnits'),alert.get('triggerState'),json.dumps(alert.get('triggers',[]))))
        return flight_id
    @staticmethod

    def _engine_parser(x):return {'timestamp':x.timestamp,'OAT':x.oat,'N1':x.n1,'N2':x.n2,'ITT':x.itt,'NR':x.nr,'TQ':x.tq,'ENG_OT':x.eng_ot,'FUEL_PRESS':x.fuel_press,'ENG_OP':x.eng_op,'XMSN_OP':x.xmsn_op,'XMSN_OT':x.xmsn_ot}
    @staticmethod

    def _gps_parser(x):return {'timestamp':x.timestamp,'latitude':x.latitude,'longitude':x.longitude,'altInd':x.alt_ind,'ias':x.ias,'pitch':x.pitch,'roll':x.roll,'heading':x.heading}
    @staticmethod

    def _alert_parser(a):return {'timestamp':a.timestamp,'alertState':a.alert_state,'alertName':a.alert_name,'level':a.level,'description':a.description,'triggerName':a.trigger_name,'triggerValue':a.trigger_value,'triggerUnits':a.trigger_units,'triggerState':a.trigger_state,'triggers':[{'name':t.name,'value':t.value,'units':t.units,'state':t.state} for t in a.triggers]}

    def delete(self,flight_id):
        with self.connection:self.connection.execute('DELETE FROM flights WHERE id=?',(flight_id,))

    def delete_many(self,flight_ids):
        with self.connection:self.connection.executemany('DELETE FROM flights WHERE id=?',[(x,) for x in flight_ids])

    def save_report(self,flight_id,text):
        with self.connection:self.connection.execute('UPDATE flights SET predictive_report=? WHERE id=?',(text,flight_id))
