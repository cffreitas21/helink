from __future__ import annotations

import csv
import io
import re
import uuid
import zipfile
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from helink.services.airport_formatter import destination_from_gps


FILE_TYPES = {
    '0_CAS_Default': ('cas_default', ['cas_default', '_0.csv']),
    '1_Engine_Data_Recording': ('engine', ['engine_data', '_1.csv']),
    '2_Exceedance_Log': ('exceedance', ['exceedance_log', '_2.csv']),
    '3_Exceedance_Log_CONT': ('exceedance', ['exceedance_log_cont', '_3.csv']),
    '4_VNE_Dynamic': ('vne', ['vne_dynamic', '_4.csv']),
    '5_CAS': ('cas', ['5_cas', '_5.csv']),
    '6_Logbook': ('logbook', ['logbook', '_6.csv']),
    'Garmin Alerts': ('cas', ['garmin alerts', '_31.csv']),
    'data_log': ('gps', ['data_log']),
}

SUPPORTED_ALERT_LEVELS = {'WARNING', 'CAUTION', 'SAFE ANN'}
ProgressCallback = Callable[[float, str], None]


@lru_cache(maxsize=1024)
def _normalized_text(value: str) -> str:
    return re.sub(r'[^a-z0-9]', '', value.lower())


def _norm(value: Any) -> str:
    return _normalized_text(str(value or ''))


class _ParsedRow(dict):
    """CSV row with a normalized column index built only once."""

    __slots__ = ('normalized',)

    def __init__(self, values):
        super().__init__(values)
        self.normalized = {_norm(key): value for key, value in values.items()}


def _num(value: Any, default=0.0) -> float:
    try:
        text = str(value).strip().replace(' ', '').replace(',', '.')
        return float(text) if text else default
    except (TypeError, ValueError):
        return default


def _read(
    data: bytes,
    row_progress: Callable[[float], None] | None = None,
) -> tuple[list[dict], list[str]]:
    text = data.decode('utf-8-sig', errors='replace')
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return [], []

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

    header_index = 0
    for index, line in enumerate(lines[:40]):
        lowered = line.lower()
        if any(
            marker in lowered
            for marker in (
                'timestamp', 'lcl date', 'lcltime', 'lcl time', 'alert name',
            )
        ):
            header_index = index
            break

    sample = '\n'.join(lines[header_index:header_index + 8])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(
        io.StringIO('\n'.join(lines[header_index:])),
        delimiter=getattr(dialect, 'delimiter', ','),
        quotechar='"',
        doublequote=True,
        skipinitialspace=True,
    )
    raw_rows = list(reader)
    if not raw_rows:
        return [], []
    if row_progress:
        row_progress(0.08)

    headers = []
    seen = {}
    for index, header in enumerate(raw_rows[0]):
        header = (
            str(header).strip().strip('"\'').lstrip('#').strip()
            or f'unnamed_{index}'
        )
        if header in seen:
            seen[header] += 1
            header = f'{header}_{seen[header]}'
        else:
            seen[header] = 0
        headers.append(header)

    maximum_columns = max(
        (len(values) for values in raw_rows), default=len(headers)
    )
    trigger_fields = (
        'Trigger Name', 'Trigger Value', 'Trigger Units', 'Trigger State',
    )
    for offset in range(maximum_columns - len(headers)):
        group = offset // len(trigger_fields) + 1
        field = trigger_fields[offset % len(trigger_fields)]
        headers.append(f'{field}_{group}')

    rows = []
    data_rows = raw_rows[1:]
    report_every = max(500, len(data_rows) // 50)
    for index, values in enumerate(data_rows, 1):
        if not values or str(values[0]).strip().startswith('#'):
            continue
        values = list(values) + [''] * max(0, len(headers) - len(values))
        mapped = {
            headers[column]: str(values[column]).strip().strip('"\'')
            for column in range(len(headers))
        }
        if any(mapped.values()):
            rows.append(_ParsedRow(mapped))
        if row_progress and (index % report_every == 0 or index == len(data_rows)):
            row_progress(0.08 + 0.92 * index / max(1, len(data_rows)))
    return rows, headers


def _get(row: dict, *aliases, default=''):
    index = (
        row.normalized
        if isinstance(row, _ParsedRow)
        else {_norm(key): value for key, value in row.items()}
    )
    normalized_aliases = tuple(_norm(alias) for alias in aliases)
    for alias in normalized_aliases:
        if alias in index:
            return index[alias]
    for alias in normalized_aliases:
        if len(alias) > 1:
            for key, value in index.items():
                if alias in key or key in alias:
                    return value
    return default


def _detect(name: str, forced: str | None = None):
    if forced:
        return (forced, FILE_TYPES[forced][0]) if forced in FILE_TYPES else (None, None)
    lowered = name.replace('\\', '/').rsplit('/', 1)[-1].lower()
    order = (
        '3_Exceedance_Log_CONT', '1_Engine_Data_Recording',
        '2_Exceedance_Log', '4_VNE_Dynamic', '0_CAS_Default',
        '5_CAS', '6_Logbook', 'Garmin Alerts', 'data_log',
    )
    for label in order:
        kind, needles = FILE_TYPES[label]
        if any(needle in lowered for needle in needles):
            return label, kind
    if re.fullmatch(r'log_\d{6,8}_\d{6}_[a-z0-9]{3,4}\.csv', lowered):
        return 'data_log', 'gps'
    return None, None


def _format_issue(kind, headers, rows):
    """Reject files whose contents do not match their declared category."""
    if not rows:
        return 'No readable data records were found.'
    names = {_norm(header) for header in headers}

    def has(*aliases):
        return any(alias in names for alias in aliases)

    if kind == 'gps':
        if not (has('latitude', 'lat') and has('longitude', 'lon', 'lng')
                and has('lcltime', 'timestamp', 'time')):
            return 'Required GPS coordinate or time columns are missing.'
    elif kind == 'engine':
        if not has('timestamp', 'lcltime', 'time') or not any(
            name.startswith(('n1', 'n2', 'itt', 'engot', 'xmsnot'))
            for name in names
        ):
            return 'The file does not contain recognizable engine data.'
    elif kind in ('cas', 'cas_default', 'exceedance', 'vne', 'logbook'):
        if not has('timestamp', 'lcltime', 'time') or not has('alertname'):
            return 'Required alert or flight-record columns are missing.'
    return ''


def _stamp(name: str):
    upper = name.upper()
    match = re.search(
        r'(20\d{2})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})_([A-Z0-9]{3,4})',
        upper,
    )
    if match:
        return (
            f'{match[1]}-{match[2]}-{match[3]}',
            f'{match[4]}:{match[5]}:{match[6]}',
            match[7],
        )
    match = re.search(
        r'LOG_(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})_([A-Z0-9]{3,4})',
        upper,
    )
    if match:
        return (
            f'20{match[1]}-{match[2]}-{match[3]}',
            f'{match[4]}:{match[5]}:{match[6]}',
            match[7],
        )
    now = datetime.now()
    return now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S'), '-'


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


def _duration(rows: list[dict]):
    if len(rows) < 2:
        return None

    def seconds(row):
        value = _get(row, 'Timestamp', 'Lcl Time', 'LclTime', 'Time')
        match = re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?', str(value))
        if not match:
            return None
        return int(match[1]) * 3600 + int(match[2]) * 60 + int(match[3] or 0)

    start, end = seconds(rows[0]), seconds(rows[-1])
    if start is None or end is None:
        return None
    difference = end - start
    if difference < 0:
        difference += 86400
    minutes = max(1, round(difference / 60))
    if minutes < 60:
        return f'{minutes} min'
    hours, remaining = divmod(minutes, 60)
    return f'{hours}h {remaining}m' if remaining else f'{hours}h'


SESSION_MARGIN = timedelta(minutes=20)


def _moment(value, flight_date):
    text = str(value or '').strip()
    iso = re.search(r'(20\d{2}-\d{2}-\d{2})[ T](\d{1,2}:\d{2}(?::\d{2})?)', text)
    if iso:
        try:
            return datetime.fromisoformat(f'{iso[1]}T{iso[2]}')
        except ValueError:
            return None
    day_first = re.search(r'(\d{2})/(\d{2})/(20\d{2})[ T](\d{1,2}:\d{2}(?::\d{2})?)', text)
    if day_first:
        try:
            return datetime.fromisoformat(
                f'{day_first[3]}-{day_first[2]}-{day_first[1]}T{day_first[4]}'
            )
        except ValueError:
            return None
    clock = _clock_time(text)
    if not clock:
        return None
    try:
        return datetime.fromisoformat(f'{flight_date}T{clock}')
    except ValueError:
        return None


def _row_moment(row, flight_date):
    value = _get(row, 'Timestamp', 'Lcl Time', 'Time')
    row_date = _get(row, 'Lcl Date', 'Date')
    return _moment(value, str(row_date).strip() or flight_date)


def _file_window(rows, flight_date, fallback_time):
    times = (
        _row_moment(row, flight_date)
        for row in rows
    )
    first = next((value for value in times if value is not None), None)
    last = next(
        (value for row in reversed(rows)
         if (value := _row_moment(row, flight_date)) is not None),
        None,
    )
    start = first or _moment(fallback_time, flight_date)
    end = last or start
    if start and end and end < start:
        end += timedelta(days=1)
    return start, end


def _session_from_record(record):
    date = record['flight_date']
    starts = [value for candidate in (
        record.get('engine_start'), record.get('gps_start'),
        record.get('departure_time'),
    ) if (value := _moment(candidate, date)) is not None]
    start = min(starts) if starts else _moment('00:00:00', date)
    ends = [value for candidate in (
        record.get('engine_end'), record.get('gps_end'),
        record.get('arrival_time'),
    ) if (value := _moment(candidate, date)) is not None]
    end = max(ends) if ends else start
    if end < start:
        end += timedelta(days=1)
    return {
        'id': record['id'], 'aircraft_id': record['aircraft_id'],
        'flight_date': date, 'departure_time': record.get('departure_time') or '',
        'origin': record.get('origin') or '', 'start': start, 'end': end,
        'batch_engine': False,
        'has_engine': bool(record.get('has_engine', record.get('engine_start'))),
    }


def _nearest_session(moment, sessions):
    if moment is None:
        return None
    best = None
    best_score = None
    for session in sessions:
        if moment < session['start']:
            distance = session['start'] - moment
        elif moment > session['end']:
            distance = moment - session['end']
        else:
            distance = timedelta(0)
        if distance > SESSION_MARGIN:
            continue
        score = (distance, abs(moment - session['start']))
        if best_score is None or score < best_score:
            best, best_score = session, score
    return best


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


def _alert(row: dict, level=None):
    name = _get(
        row, 'Alert Name', 'AlertName', 'Alert', 'Message', default='Alert'
    )
    raw_level = _get(row, 'Level', 'Severity', default=level or '')
    normalized_level = str(raw_level or '').strip().upper()
    if normalized_level not in SUPPORTED_ALERT_LEVELS:
        if 'WARN' in normalized_level:
            normalized_level = 'WARNING'
        elif 'CAUT' in normalized_level:
            normalized_level = 'CAUTION'
        elif 'SAFE' in normalized_level:
            normalized_level = 'SAFE ANN'
        elif level in SUPPORTED_ALERT_LEVELS:
            normalized_level = level
        else:
            return None
    return {
        'timestamp': _get(
            row, 'Timestamp', 'Lcl Time', 'Time', default='00:00:00'
        ),
        'alertState': _get(
            row, 'Alert State', 'AlertState', 'State', default='SET'
        ),
        'alertName': name,
        'level': normalized_level,
        'description': _get(
            row,
            'Description',
            'Desc',
            default='Alert recorded by the Garmin system.',
        ),
        'triggerName': _get(
            row, 'Trigger Name', 'TriggerName', 'Trigger', default=''
        ),
        'triggerValue': _get(
            row, 'Trigger Value', 'TriggerValue', 'Value', default=''
        ),
        'triggerUnits': _get(
            row, 'Trigger Units', 'TriggerUnits', 'Units', default=''
        ),
        'triggerState': _get(
            row, 'Trigger State', 'TriggerState', default='ACTIVE'
        ),
        'triggers': _triggers(row),
    }


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


def _collect_csv_blobs(paths, progress: ProgressCallback | None, skipped, forced_type):
    blobs = []
    total = max(1, len(paths))
    for index, raw_path in enumerate(paths, 1):
        path = Path(raw_path)
        if progress:
            progress(5 * (index - 1) / total, f'Checking {path.name}...')
        if path.suffix.lower() == '.zip':
            try:
                with zipfile.ZipFile(path) as archive:
                    names = [name for name in archive.namelist()
                             if not name.endswith('/')]
                    if not names:
                        skipped.append((path.name, 'The archive contains no files.'))
                    archive_blobs = []
                    for name in names:
                        if not name.lower().endswith('.csv'):
                            skipped.append((name, 'Unsupported file format.'))
                            continue
                        if not forced_type and _detect(name)[0] is None:
                            skipped.append((name, 'File type not recognized.'))
                            continue
                        archive_blobs.append((name, archive.read(name), False))
                    blobs.extend(archive_blobs)
            except zipfile.BadZipFile:
                skipped.append((path.name, 'The archive could not be opened.'))
        elif path.suffix.lower() == '.csv':
            if not forced_type and _detect(path.name)[0] is None:
                skipped.append((path.name, 'File type not recognized.'))
            else:
                blobs.append((path.name, path.read_bytes(), True))
        else:
            skipped.append((path.name, 'Unsupported file format.'))
    return blobs


def parse_files(
    paths: list[str],
    aircraft_id: str,
    forced_type: str | None = None,
    progress: ProgressCallback | None = None,
    skipped_files: list[tuple[str, str]] | None = None,
    accepted_files: list[str] | None = None,
    existing_sessions: list[dict] | None = None,
    target_flight: dict | None = None,
):
    skipped = skipped_files if skipped_files is not None else []
    blobs = _collect_csv_blobs(paths, progress, skipped, forced_type)
    if not blobs:
        if skipped:
            if progress:
                progress(70, 'File review complete.')
            return []
        raise ValueError('No supported flight data files were found.')

    prepared = []
    total_files = len(blobs)
    for file_index, blob in enumerate(blobs):
        name, data = blob[:2]
        direct_csv = blob[2] if len(blob) > 2 else True
        file_start = 5 + 40 * file_index / total_files
        file_span = 40 / total_files
        message = f'Reading {name} ({file_index + 1}/{total_files})'
        if progress:
            progress(file_start, message)

        detected_label, _ = _detect(name)
        if forced_type and detected_label and detected_label != forced_type:
            skipped.append((name, 'File type does not match the selected category.'))
            continue
        label, kind = _detect(name, forced_type)
        if label is None:
            skipped.append((name, 'File type not recognized.'))
            continue
        try:
            rows, headers = _read(
                data,
                (
                    lambda fraction, start=file_start, span=file_span, text=message:
                    progress(start + span * fraction, text)
                ) if progress else None,
            )
        except (csv.Error, UnicodeError, ValueError):
            skipped.append((name, 'The CSV file could not be read.'))
            continue
        issue = _format_issue(kind, headers, rows)
        if issue:
            skipped.append((name, issue))
            continue

        date, time, origin = _stamp(name)
        start, end = _file_window(rows, date, time)
        if start is not None:
            date, time = start.date().isoformat(), start.strftime('%H:%M:%S')
        prepared.append({
            'name': name, 'label': label, 'kind': kind, 'rows': rows,
            'date': date, 'time': time, 'origin': origin,
            'start': start, 'end': end, 'direct_csv': direct_csv,
        })
        if accepted_files is not None:
            accepted_files.append(name)

    blobs.clear()
    if not prepared:
        if progress:
            progress(70, 'File review complete.')
        return []

    sessions = [
        _session_from_record(record) for record in (existing_sessions or ())
    ]
    target = _session_from_record(target_flight) if target_flight else None
    if target is not None:
        sessions = [target]
    else:
        for file in prepared:
            if file['kind'] != 'engine':
                continue
            start = file['start'] or _moment(file['time'], file['date'])
            end = file['end'] or start
            matching = next(
                (
                    session for session in sessions
                    if session['flight_date'] == file['date']
                    and (
                        abs(session['start'] - start) <= timedelta(seconds=90)
                        if session['has_engine']
                        else _nearest_session(start, [session]) is not None
                    )
                ),
                None,
            )
            if matching is None:
                matching = {
                    'id': str(uuid.uuid4()), 'aircraft_id': aircraft_id,
                    'flight_date': file['date'],
                    'departure_time': _clock_time(start) or file['time'],
                    'origin': file['origin'], 'start': start, 'end': end,
                    'batch_engine': True, 'has_engine': True,
                }
                sessions.append(matching)
            else:
                if not matching['has_engine']:
                    matching['departure_time'] = _clock_time(start)
                    matching['origin'] = file['origin'] or matching['origin']
                if matching['batch_engine']:
                    matching['start'] = min(matching['start'], start)
                    matching['end'] = max(matching['end'], end)
                else:
                    matching['start'] = min(matching['start'], start)
                    matching['end'] = max(matching['end'], end)
                matching['batch_engine'] = True
                matching['has_engine'] = True
            file['session'] = matching

    groups = {}
    orphan_sessions = {}

    def group_for(session):
        key = session['id']
        if key not in groups:
            groups[key] = {
                'id': key,
                'aircraft_id': aircraft_id,
                'flight_date': session['flight_date'],
                'departure_time': session['departure_time'],
                'arrival_time': '',
                'duration': 'Unable to calculate',
                'origin': session['origin'],
                'destination': '',
                'imported_files': [],
                '_source_files': [],
                '_direct_csv': False,
                'engine_data': [],
                'data_log': [],
                'exceedances': [],
                'cas_messages': [],
                'auxiliary_data': {},
                '_exceedance_keys': set(),
                '_cas_keys': set(),
            }
        return groups[key]

    for file_index, file in enumerate(prepared):
        name, label, kind, rows = (
            file['name'], file['label'], file['kind'], file['rows']
        )
        message = f'Assigning {name} to flight ({file_index + 1}/{len(prepared)})'
        if progress:
            progress(45 + 25 * file_index / len(prepared), message)

        if target is not None:
            assignments = [(target, rows)]
        elif kind == 'engine':
            assignments = [(file['session'], rows)]
        else:
            by_session = {}
            candidates = [
                session for session in sessions
                if file['start'] is not None
                and abs((session['start'].date() - file['start'].date()).days) <= 1
                and (file['direct_csv'] or session['has_engine'])
            ]
            unmatched = []
            for row in rows:
                moment = _row_moment(row, file['date']) or file['start']
                if (moment is not None and file['start'] is not None
                        and moment < file['start'] - timedelta(hours=12)):
                    moment += timedelta(days=1)
                session = _nearest_session(moment, candidates)
                if session is not None:
                    by_session.setdefault(session['id'], (session, []))[1].append(row)
                else:
                    unmatched.append(row)
            assignments = list(by_session.values())
            if file['direct_csv'] and unmatched:
                start, end = _file_window(unmatched, file['date'], file['time'])
                standalone = {
                    'id': str(uuid.uuid4()), 'aircraft_id': aircraft_id,
                    'flight_date': start.date().isoformat(),
                    'departure_time': start.strftime('%H:%M:%S'),
                    'origin': file['origin'], 'start': start, 'end': end,
                    'batch_engine': False, 'has_engine': False,
                }
                sessions.append(standalone)
                assignments.append((standalone, unmatched))
            elif not assignments:
                orphan = orphan_sessions.get(file['date'])
                if orphan is None:
                    orphan = {
                        'id': str(uuid.uuid4()), 'aircraft_id': aircraft_id,
                        'flight_date': file['date'],
                        'departure_time': file['time'],
                        'origin': file['origin'],
                    }
                    orphan_sessions[file['date']] = orphan
                assignments = [(orphan, rows)]

        for session, assigned_rows in assignments:
            group = group_for(session)
            if name not in group['_source_files']:
                group['_source_files'].append(name)
            group['_direct_csv'] |= file['direct_csv']
            if label not in group['imported_files']:
                group['imported_files'].append(label)

            report_every = max(500, len(assigned_rows) // 30)
            for row_index, row in enumerate(assigned_rows, 1):
                if kind == 'engine':
                    group['engine_data'].append({
                        'timestamp': _get(
                            row, 'Timestamp', 'Lcl Time', 'Time',
                            default='00:00:00',
                        ),
                        'OAT': _num(_get(row, 'OAT')),
                        'N1': _num(_get(row, 'N1', 'Ng')),
                        'N2': _num(_get(row, 'N2')),
                        'ITT': _num(_get(row, 'ITT', 'E1 ITT')),
                        'NR': _num(_get(row, 'NR')),
                        'TQ': _num(_get(row, 'TQ', 'Torque')),
                        'ENG_OT': _num(_get(row, 'ENG OT', 'Eng Oil Temp', 'Oil Temp')),
                        'FUEL_PRESS': _num(_get(row, 'Fuel Press')),
                        'ENG_OP': _num(_get(row, 'ENG OP', 'Eng Oil Press', 'Oil Press')),
                        'XMSN_OP': _num(_get(row, 'XMSN OP', 'MGB Oil Press')),
                        'XMSN_OT': _num(_get(row, 'XMSN OT', 'MGB Oil Temp')),
                    })
                elif kind == 'gps':
                    time_value = _get(row, 'Lcl Time', 'Time', 'Timestamp')
                    if time_value:
                        group['data_log'].append({
                            'timestamp': time_value,
                            'latitude': _num(_get(row, 'Latitude', 'Lat')),
                            'longitude': _num(_get(row, 'Longitude', 'Lon', 'Lng')),
                            'altInd': _num(
                                _get(row, 'AltInd', 'Alt MSL', 'Altitude')
                            ),
                            'ias': _num(_get(row, 'IAS', 'GndSpd')),
                            'pitch': _num(_get(row, 'Pitch')),
                            'roll': _num(_get(row, 'Roll')),
                            'heading': _num(_get(row, 'Heading', 'HDG', 'TRK')),
                        })
                elif kind in ('exceedance', 'vne'):
                    alert = (
                        _vne_alert(row) if kind == 'vne'
                        else _alert(row, 'WARNING')
                    )
                    key = (alert['timestamp'], alert['alertName'])
                    if key not in group['_exceedance_keys']:
                        group['_exceedance_keys'].add(key)
                        group['exceedances'].append(alert)
                elif kind in ('cas', 'cas_default', 'logbook'):
                    alert = _alert(
                        row, 'CAUTION' if kind == 'cas' else None
                    )
                    if alert is not None:
                        key = (
                            alert['timestamp'], alert['alertName'],
                            alert['alertState'],
                        )
                        if key not in group['_cas_keys']:
                            group['_cas_keys'].add(key)
                            group['cas_messages'].append(alert)
                else:
                    group['auxiliary_data'].setdefault(label, []).append(row)

                if progress and (
                    row_index % report_every == 0
                    or row_index == len(assigned_rows)
                ):
                    progress(
                        45 + 25 * (
                            file_index + row_index / max(1, len(assigned_rows))
                        ) / len(prepared),
                        message,
                    )

    flights = list(groups.values())
    for flight in flights:
        for collection in ('engine_data', 'data_log'):
            flight[collection].sort(
                key=lambda item: _moment(
                    item.get('timestamp'), flight['flight_date']
                ) or datetime.min
            )
        if flight['data_log']:
            flight['destination'] = destination_from_gps(flight['data_log'])
        flight.pop('_exceedance_keys', None)
        flight.pop('_cas_keys', None)
        moments = [
            moment for collection in ('engine_data', 'data_log')
            for item in flight[collection]
            if (moment := _moment(
                item.get('timestamp'), flight['flight_date']
            )) is not None
        ]
        if moments:
            flight['arrival_time'] = _clock_time(max(moments))
        flight['duration'] = (
            _duration_between(
                flight.get('departure_time'), flight.get('arrival_time')
            ) or 'Unable to calculate'
        )

    if progress:
        progress(70, 'Flight sessions identified.')
    return sorted(
        flights,
        key=lambda flight: (flight['flight_date'], flight['departure_time']),
    )
