from __future__ import annotations
import os, re, shutil, sqlite3, uuid
from datetime import datetime
from pathlib import Path

SCHEMA="""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS aircraft(id TEXT PRIMARY KEY,registration TEXT UNIQUE NOT NULL,model TEXT NOT NULL,serial_number TEXT NOT NULL,flight_hours REAL NOT NULL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS flights(id TEXT PRIMARY KEY,aircraft_id TEXT NOT NULL REFERENCES aircraft(id) ON DELETE CASCADE,flight_date TEXT NOT NULL,departure_time TEXT,arrival_time TEXT,duration TEXT,origin TEXT,destination TEXT,imported_files TEXT NOT NULL DEFAULT '[]',predictive_report TEXT NOT NULL DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS engine_data(id INTEGER PRIMARY KEY AUTOINCREMENT,flight_id TEXT NOT NULL REFERENCES flights(id) ON DELETE CASCADE,seq INTEGER,timestamp TEXT,oat REAL,n1 REAL,n2 REAL,itt REAL,nr REAL,tq REAL,eng_ot REAL,fuel_press REAL,eng_op REAL,xmsn_op REAL,xmsn_ot REAL);
CREATE TABLE IF NOT EXISTS gps_data(id INTEGER PRIMARY KEY AUTOINCREMENT,flight_id TEXT NOT NULL REFERENCES flights(id) ON DELETE CASCADE,seq INTEGER,timestamp TEXT,latitude REAL,longitude REAL,alt_ind REAL,ias REAL,pitch REAL,roll REAL,heading REAL);
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY AUTOINCREMENT,flight_id TEXT NOT NULL REFERENCES flights(id) ON DELETE CASCADE,kind TEXT NOT NULL,timestamp TEXT,alert_state TEXT,alert_name TEXT,level TEXT,description TEXT,trigger_name TEXT,trigger_value TEXT,trigger_units TEXT,trigger_state TEXT,triggers_json TEXT NOT NULL DEFAULT '[]');
"""

class DatabaseManager:

    REQUIRED_TABLES={'aircraft','flights','engine_data','gps_data','alerts'}

    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.connection=sqlite3.connect(self.path); self.connection.row_factory=sqlite3.Row
        self.connection.execute('PRAGMA foreign_keys=ON'); self._migrate(); self.connection.executescript(SCHEMA)

    def _migrate(self):
        mappings={'aircraft':{'prefixo':'registration','modelo':'model','msn':'serial_number','horas_voo':'flight_hours'},'flights':{'aeronave_id':'aircraft_id','data_voo':'flight_date','hora_partida':'departure_time','hora_chegada':'arrival_time','duracao':'duration','origem':'origin','destino':'destination','ficheiros_importados':'imported_files'}}
        tables={row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        with self.connection:
            for table,columns in mappings.items():
                if table not in tables:continue
                existing={row[1] for row in self.connection.execute(f'PRAGMA table_info("{table}")')}
                for old,new in columns.items():
                    if old in existing and new not in existing:self.connection.execute(f'ALTER TABLE "{table}" RENAME COLUMN "{old}" TO "{new}"');existing.remove(old);existing.add(new)
        if 'flights' in tables:
            flight_columns = {
                row[1] for row in self.connection.execute(
                    'PRAGMA table_info("flights")'
                )
            }
            if 'arrival_time' not in flight_columns:
                with self.connection:
                    self.connection.execute(
                        'ALTER TABLE flights ADD COLUMN arrival_time TEXT'
                    )
            self._backfill_arrival_times()
            self._backfill_durations()
        if 'alerts' in tables:
            alert_columns = {
                row[1] for row in self.connection.execute(
                    'PRAGMA table_info("alerts")'
                )
            }
            if 'triggers_json' not in alert_columns:
                with self.connection:
                    self.connection.execute(
                        "ALTER TABLE alerts ADD COLUMN triggers_json TEXT NOT NULL DEFAULT '[]'"
                    )
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

    def _backfill_arrival_times(self):
        flights = self.connection.execute(
            "SELECT id FROM flights WHERE COALESCE(arrival_time, '') = ''"
        ).fetchall()
        with self.connection:
            for flight in flights:
                arrival_time = ''
                for table in ('engine_data', 'gps_data'):
                    rows = self.connection.execute(
                        f'SELECT timestamp FROM {table} '
                        'WHERE flight_id=? AND timestamp IS NOT NULL '
                        'ORDER BY seq DESC',
                        (flight['id'],),
                    ).fetchall()
                    arrival_time = next(
                        (
                            value for row in rows
                            if (value := self._clock_time(row['timestamp']))
                        ),
                        '',
                    )
                    if arrival_time:
                        break
                if arrival_time:
                    self.connection.execute(
                        'UPDATE flights SET arrival_time=? WHERE id=?',
                        (arrival_time, flight['id']),
                    )

    def _backfill_durations(self):
        flights = self.connection.execute(
            """SELECT id, departure_time, arrival_time FROM flights
               WHERE LOWER(TRIM(COALESCE(duration, ''))) IN
                     ('', 'unable to calculate')"""
        ).fetchall()
        with self.connection:
            for flight in flights:
                duration = self._duration_between(
                    flight['departure_time'], flight['arrival_time']
                )
                if duration:
                    self.connection.execute(
                        'UPDATE flights SET duration=? WHERE id=?',
                        (duration, flight['id']),
                    )

    @classmethod

    def validate(cls,path):
        resolved=Path(path).resolve(); connection=sqlite3.connect(f'file:{resolved.as_posix()}?mode=ro',uri=True)
        try: integrity=connection.execute('PRAGMA integrity_check').fetchone()[0];tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:connection.close()
        if integrity!='ok':raise ValueError('The selected SQLite database failed its integrity check.')
        if not cls.REQUIRED_TABLES.issubset(tables):raise ValueError('The selected file is not a valid HELINK database.')

    def export_to(self,destination):
        destination=Path(destination)
        if destination.resolve()==self.path.resolve():raise ValueError('Select a different destination file.')
        self.connection.commit();target=sqlite3.connect(destination)
        try:self.connection.backup(target);target.commit()
        finally:target.close()
        self.validate(destination);return destination

    def import_from(self,source):
        source=Path(source)
        if source.resolve()==self.path.resolve():raise ValueError('This database is already open.')
        self.validate(source);backup=self.path.with_name(f'helink-before-import-{datetime.now():%Y%m%d-%H%M%S}.db');temporary=self.path.with_name(f'.helink-import-{uuid.uuid4().hex}.db');replaced=False
        try:
            shutil.copy2(source,temporary);candidate=DatabaseManager(temporary);candidate.close();self.validate(temporary)
            self.connection.commit();backup_connection=sqlite3.connect(backup)
            try:self.connection.backup(backup_connection);backup_connection.commit()
            finally:backup_connection.close()
            self.connection.close();os.replace(temporary,self.path);replaced=True
            self.connection=sqlite3.connect(self.path);self.connection.row_factory=sqlite3.Row;self.connection.execute('PRAGMA foreign_keys=ON')
            return backup
        except Exception:
            if temporary.exists():temporary.unlink()
            if replaced and backup.exists():
                try:self.connection.close()
                except Exception:pass
                shutil.copy2(backup,self.path);self.connection=sqlite3.connect(self.path);self.connection.row_factory=sqlite3.Row;self.connection.execute('PRAGMA foreign_keys=ON')
            raise

    def close(self):self.connection.close()
