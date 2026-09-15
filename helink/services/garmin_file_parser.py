from __future__ import annotations
import csv, io, re, zipfile, uuid
from datetime import datetime
from pathlib import Path
from typing import Any

FILE_TYPES = {
    '0_CAS_Default': ('cas_default', ['cas_default','_0.csv']),
    '1_Engine_Data_Recording': ('engine', ['engine_data','_1.csv']),
    '2_Exceedance_Log': ('exceedance', ['exceedance_log','_2.csv']),
    '3_Exceedance_Log_CONT': ('exceedance', ['exceedance_log_cont','_3.csv']),
    '4_VNE_Dynamic': ('vne', ['vne_dynamic','_4.csv']),
    '5_CAS': ('cas', ['5_cas','_5.csv']),
    '6_Logbook': ('logbook', ['logbook','_6.csv']),
    'Garmin Alerts': ('cas', ['garmin alerts','_31.csv']),
    'data_log': ('gps', ['data_log','log_']),
}

def _norm(s: Any) -> str:
    return re.sub(r'[^a-z0-9]', '', str(s or '').lower())

def _num(v: Any, default=0.0) -> float:
    try:
        t=str(v).strip().replace(' ','').replace(',','.')
        return float(t) if t else default
    except Exception:return default

def _read(data: bytes) -> tuple[list[dict], list[str]]:
    text=data.decode('utf-8-sig',errors='replace')
    lines=[x for x in text.splitlines() if x.strip()]
    if not lines:return [],[]
    # Some Garmin exports wrap the complete CSV row in quotes and escape every
    # inner quote twice. Unwrap those rows before asking csv.reader to split them.
    first_row = next(csv.reader([lines[0]]), [])
    wrapped_row = (
        len(first_row) == 1
        and lines[0].startswith('"')
        and lines[0].endswith('"')
        and '""' in lines[0]
    )
    if wrapped_row:
        lines = [
            line[1:-1].replace('""', '"')
            if line.startswith('"') and line.endswith('"')
            else line
            for line in lines
        ]
    header_idx=0
    for i,line in enumerate(lines[:40]):
        low=line.lower()
        if any(k in low for k in ('timestamp','lcl date','lcltime','lcl time','alert name')):
            header_idx=i; break
    sample='\n'.join(lines[header_idx:header_idx+8])
    try:dialect=csv.Sniffer().sniff(sample,delimiters=',;\t')
    except Exception:dialect=csv.excel
    reader=csv.reader(
        io.StringIO('\n'.join(lines[header_idx:])),
        delimiter=getattr(dialect, 'delimiter', ','),
        quotechar='"',
        doublequote=True,
        skipinitialspace=True,
    )
    raw=list(reader)
    if not raw:return [],[]
    headers=[]; seen={}
    for i,h in enumerate(raw[0]):
        h=str(h).strip().strip('"\'').lstrip('#').strip() or f'unnamed_{i}'
        if h in seen: seen[h]+=1; h=f'{h}_{seen[h]}'
        else:seen[h]=0
        headers.append(h)
    maximum_columns = max((len(values) for values in raw), default=len(headers))
    trigger_fields = (
        'Trigger Name', 'Trigger Value', 'Trigger Units', 'Trigger State',
    )
    for offset in range(maximum_columns - len(headers)):
        group = offset // len(trigger_fields) + 1
        field = trigger_fields[offset % len(trigger_fields)]
        headers.append(f'{field}_{group}')

    rows=[]
    for vals in raw[1:]:
        if not vals or (vals and str(vals[0]).strip().startswith('#')):continue
        vals=list(vals)+['']*max(0,len(headers)-len(vals))
        row={headers[i]:str(vals[i]).strip().strip('"\'') for i in range(len(headers))}
        if any(v!='' for v in row.values()):rows.append(row)
    return rows,headers

def _get(row:dict,*aliases,default=''):
    index={_norm(k):v for k,v in row.items()}
    for a in aliases:
        n=_norm(a)
        if n in index:return index[n]
    for a in aliases:
        n=_norm(a)
        if len(n)>1:
            for k,v in index.items():
                if n in k or k in n:return v
    return default

def _detect(name:str, forced:str|None=None):
    if forced:
        return forced, FILE_TYPES.get(forced,('gps',[]))[0]
    low=name.lower().replace('\\','/')
    # order matters: CONT before normal exceedance
    for label in ('3_Exceedance_Log_CONT','1_Engine_Data_Recording','2_Exceedance_Log','4_VNE_Dynamic','0_CAS_Default','5_CAS','6_Logbook','Garmin Alerts','data_log'):
        kind,needles=FILE_TYPES[label]
        if any(n in low for n in needles):return label,kind
    return 'data_log','gps'

def _stamp(name:str):
    upper=name.upper()
    m=re.search(r'(20\d{2})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})_([A-Z0-9]{3,4})',upper)
    if m:return f'{m[1]}-{m[2]}-{m[3]}',f'{m[4]}:{m[5]}:{m[6]}',m[7]
    m=re.search(r'LOG_(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})_([A-Z0-9]{3,4})',upper)
    if m:return f'20{m[1]}-{m[2]}-{m[3]}',f'{m[4]}:{m[5]}:{m[6]}',m[7]
    return datetime.now().strftime('%Y-%m-%d'),datetime.now().strftime('%H:%M:%S'),'-'

def _clock_time(value):
    matches = re.findall(
        r'(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?',
        str(value or ''),
    )
    if not matches:
        return ''
    hour, minute, second = matches[-1]
    return f'{int(hour):02d}:{minute}:{second or "00"}'


def _duration_between(departure_time, arrival_time):
    departure = _clock_time(departure_time)
    arrival = _clock_time(arrival_time)
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


def _duration(rows:list[dict]):
    if len(rows)<2:return None
    def ts(r):return _get(r,'Timestamp','Lcl Time','LclTime','Time')
    def sec(v):
        m=re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?',str(v))
        return int(m[1])*3600+int(m[2])*60+int(m[3] or 0) if m else None
    a,b=sec(ts(rows[0])),sec(ts(rows[-1]))
    if a is None or b is None:return None
    diff=b-a
    if diff<0:diff+=86400
    mins=max(1,round(diff/60)); return f'{mins//60}h {mins%60}m' if mins>=60 and mins%60 else (f'{mins//60}h' if mins>=60 else f'{mins} min')

def _triggers(row: dict) -> list[dict]:
    triggers = []
    for key, name in row.items():
        match = re.fullmatch(r'Trigger Name(?:_(\d+))?', key, re.IGNORECASE)
        if not match or not str(name).strip():
            continue
        suffix = f'_{match[1]}' if match[1] else ''
        value = str(row.get(f'Trigger Value{suffix}', '')).strip()
        if value.upper() == 'UNK':
            continue
        triggers.append({
            'name': str(name).strip(),
            'value': value,
            'units': str(row.get(f'Trigger Units{suffix}', '')).strip(),
            'state': str(row.get(f'Trigger State{suffix}', '')).strip(),
        })
    return triggers


SUPPORTED_ALERT_LEVELS = {'WARNING', 'CAUTION', 'SAFE ANN'}


def _alert(r: dict, level=None):
    name = _get(r, 'Alert Name', 'AlertName', 'Alert', 'Message', default='Alert')
    raw_level = _get(r, 'Level', 'Severity', default=level or '')
    lvl = str(raw_level or '').strip().upper()
    if lvl not in SUPPORTED_ALERT_LEVELS:
        if 'WARN' in lvl:
            lvl = 'WARNING'
        elif 'CAUT' in lvl:
            lvl = 'CAUTION'
        elif 'SAFE' in lvl:
            lvl = 'SAFE ANN'
        elif level in SUPPORTED_ALERT_LEVELS:
            lvl = level
        else:
            return None
    return {'timestamp':_get(r,'Timestamp','Lcl Time','Time',default='00:00:00'),
      'alertState':_get(r,'Alert State','AlertState','State',default='SET'),
      'alertName':name,'level':lvl,
      'description':_get(r,'Description','Desc',default='Alert recorded by the Garmin system.'),
      'triggerName':_get(r,'Trigger Name','TriggerName','Trigger',default=''),
      'triggerValue':_get(r,'Trigger Value','TriggerValue','Value',default=''),
      'triggerUnits':_get(r,'Trigger Units','TriggerUnits','Units',default=''),
      'triggerState':_get(r,'Trigger State','TriggerState',default='ACTIVE'),
      'triggers':_triggers(r)}

def _vne_alert(row: dict) -> dict:
    alert = _alert(row, 'WARNING')
    for key, name in row.items():
        if not _norm(key).startswith('triggername'):
            continue
        if 'ias' not in _norm(name):
            continue
        suffix = key[len('Trigger Name'):]
        alert['triggerName'] = str(name).strip()
        alert['triggerValue'] = row.get(f'Trigger Value{suffix}', '')
        alert['triggerUnits'] = row.get(f'Trigger Units{suffix}', 'kts')
        alert['triggerState'] = row.get(f'Trigger State{suffix}', 'ACTIVE')
        break
    return alert


def parse_files(paths:list[str], aircraft_id:str, forced_type:str|None=None):
    blobs=[]
    for p in paths:
        path=Path(p)
        if path.suffix.lower()=='.zip':
            with zipfile.ZipFile(path) as z:
                blobs.extend((n,z.read(n)) for n in z.namelist() if n.lower().endswith('.csv'))
        elif path.suffix.lower()=='.csv':blobs.append((path.name,path.read_bytes()))
    if not blobs:raise ValueError('No CSV files found.')
    groups={}
    for name,data in blobs:
        date,time,loc=_stamp(name); key=date # React merges the Garmin files of the same day
        g=groups.setdefault(key,{'id':str(uuid.uuid4()),'aircraft_id':aircraft_id,'flight_date':date,'departure_time':time,'arrival_time':'','duration':'Unable to calculate','origin':loc,'destination':'','imported_files':[],'engine_data':[],'data_log':[],'exceedances':[],'cas_messages':[],'auxiliary_data':{}})
        label,kind=_detect(name,forced_type)
        if label not in g['imported_files']:g['imported_files'].append(label)
        rows,headers=_read(data)
        d=_duration(rows)
        if d and (g['duration']=='Unable to calculate' or kind in ('gps','engine')):g['duration']=d
        if kind=='engine':
            for r in rows:
                g['engine_data'].append({'timestamp':_get(r,'Timestamp','Lcl Time','Time',default='00:00:00'),
                 'OAT':_num(_get(r,'OAT')),'N1':_num(_get(r,'N1','Ng')),'N2':_num(_get(r,'N2')),
                 'ITT':_num(_get(r,'ITT','E1 ITT')),'NR':_num(_get(r,'NR')),'TQ':_num(_get(r,'TQ','Torque')),
                 'ENG_OT':_num(_get(r,'ENG OT','Eng Oil Temp','Oil Temp')),'FUEL_PRESS':_num(_get(r,'Fuel Press')),
                 'ENG_OP':_num(_get(r,'ENG OP','Eng Oil Press','Oil Press')),'XMSN_OP':_num(_get(r,'XMSN OP','MGB Oil Press')),
                 'XMSN_OT':_num(_get(r,'XMSN OT','MGB Oil Temp'))})
        elif kind=='gps':
            for r in rows:
                datev=_get(r,'Lcl Date','Date'); timev=_get(r,'Lcl Time','Time','Timestamp')
                if not timev:continue
                g['data_log'].append({'timestamp':timev,'latitude':_num(_get(r,'Latitude','Lat')),
                 'longitude':_num(_get(r,'Longitude','Lon','Lng')),'altInd':_num(_get(r,'AltInd','Alt MSL','Altitude')),
                 'ias':_num(_get(r,'IAS','GndSpd')),'pitch':_num(_get(r,'Pitch')),'roll':_num(_get(r,'Roll')),
                 'heading':_num(_get(r,'Heading','HDG','TRK'))})
        elif kind in ('exceedance', 'vne'):
            for r in rows:
                alert = _vne_alert(r) if kind == 'vne' else _alert(r, 'WARNING')
                if not any(
                    item['timestamp'] == alert['timestamp']
                    and item['alertName'] == alert['alertName']
                    for item in g['exceedances']
                ):
                    g['exceedances'].append(alert)
        elif kind in ('cas','cas_default'):
            for r in rows:
                a = _alert(r, 'CAUTION' if kind == 'cas' else None)
                if a is None:
                    continue
                if not any(
                    item['timestamp'] == a['timestamp']
                    and item['alertName'] == a['alertName']
                    and item['alertState'] == a['alertState']
                    for item in g['cas_messages']
                ):
                    g['cas_messages'].append(a)
        else:
            g['auxiliary_data'][label]=rows
    for flight in groups.values():
        for collection in ('engine_data', 'data_log'):
            for item in reversed(flight[collection]):
                if arrival_time := _clock_time(item.get('timestamp')):
                    flight['arrival_time'] = arrival_time
                    break
            if flight['arrival_time']:
                break
        if str(flight.get('duration') or '').strip().lower() in (
            '', 'unable to calculate'
        ):
            flight['duration'] = _duration_between(
                flight.get('departure_time'), flight.get('arrival_time')
            ) or flight['duration']
    return list(groups.values())
