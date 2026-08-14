from __future__ import annotations

from html import escape
from statistics import mean

from helink.models.flight import AlertTrigger, Flight


FILE_TYPES = (
    '1_Engine_Data_Recording',
    'data_log',
    '2_Exceedance_Log',
    '3_Exceedance_Log_CONT',
    '4_VNE_Dynamic',
    '0_CAS_Default',
    '5_CAS',
    '6_Logbook',
    'Garmin Alerts',
)


def _values(items, attribute):
    return [
        float(value)
        for item in items
        if (value := getattr(item, attribute)) is not None
    ]


def _stat(values, unit, decimals=1):
    if not values:
        return 'NO DATA', 'NO DATA'
    return (
        f'{mean(values):.{decimals}f} {unit}',
        f'{max(values):.{decimals}f} {unit}',
    )


def _alert_triggers(alert):
    if alert.triggers:
        return alert.triggers
    if alert.trigger_name:
        return (
            AlertTrigger(
                alert.trigger_name,
                alert.trigger_value or '',
                alert.trigger_units or '',
                alert.trigger_state or '',
            ),
        )
    return ()


def technical_report(flight: Flight) -> str:
    engine = flight.engine_data
    gps = flight.data_log
    alerts = flight.alerts
    exceedances = [alert for alert in alerts if alert.kind == 'EXCEEDANCE']

    parameters = (
        ('ITT', *_stat(_values(engine, 'itt'), 'deg C')),
        ('Torque', *_stat(_values(engine, 'tq'), '%')),
        ('ENG Oil Temperature', *_stat(_values(engine, 'eng_ot'), 'deg C')),
        ('XMSN Oil Temperature', *_stat(_values(engine, 'xmsn_ot'), 'deg C')),
        ('Altitude', *_stat(_values(gps, 'alt_ind'), 'ft', 0)),
        ('IAS', *_stat(_values(gps, 'ias'), 'kt')),
    )

    first_time = (
        engine[0].timestamp if engine
        else (gps[0].timestamp if gps else None)
    )
    last_time = (
        engine[-1].timestamp if engine
        else (gps[-1].timestamp if gps else None)
    )
    valid_gps = [
        point for point in gps
        if point.latitude is not None and point.longitude is not None
        and 35 <= point.latitude <= 45 and -11 <= point.longitude <= 5
    ]

    warning_count = sum(alert.level == 'WARNING' for alert in alerts)
    caution_count = sum(alert.level == 'CAUTION' for alert in alerts)

    lines = [
        'HELINK',
        'HELICOPTER ANALYSIS AND PREVENTIVE MAINTENANCE SYSTEM',
        '',
        'MAINTENANCE REPORT',
        '=' * 72,
        '',
        'FLIGHT OVERVIEW',
        '-' * 72,
        f'Flight date:       {flight.flight_date or "N/A"}',
        f'Departure:         {flight.departure_time or "N/A"}',
        f'Duration:          {flight.duration or "N/A"}',
        f'Origin:            {flight.origin or "N/A"}',
        f'Destination:       {flight.destination or "N/A"}',
        '',
        'KEY FLIGHT PARAMETERS',
        '-' * 72,
        f'{"Parameter":<30} {"AVG":>18} {"MAXIMUM":>18}',
    ]
    for label, average, maximum in parameters:
        lines.append(f'{label:<30} {average:>18} {maximum:>18}')

    lines += [
        '',
        'DATA COVERAGE',
        '-' * 72,
        f'Engine samples:    {len(engine):,}',
        f'GPS points:        {len(gps):,}',
        f'Recording window:  {first_time or "N/A"} to {last_time or "N/A"}',
        '',
        'FLIGHT EVENTS',
        '-' * 72,
        f'Total events:      {len(alerts)}',
        f'Exceedances:       {len(exceedances)}',
        f'Warnings:          {warning_count}',
        f'Cautions:          {caution_count}',
        '',
        'ROUTE SUMMARY',
        '-' * 72,
        f'Valid route points: {len(valid_gps):,}',
    ]
    if valid_gps:
        start, end = valid_gps[0], valid_gps[-1]
        lines += [
            f'Start position:    {start.latitude:.5f}, {start.longitude:.5f}',
            f'End position:      {end.latitude:.5f}, {end.longitude:.5f}',
        ]
    else:
        lines.append('Route:             No valid GPS route is available.')

    imported = set(flight.imported_files)
    lines += ['', 'IMPORTED FILES', '-' * 72]
    for file_type in FILE_TYPES:
        lines.append(
            f'[{"LOADED" if file_type in imported else "MISSING":7}] {file_type}'
        )

    lines += ['', 'EXCEEDANCES', '=' * 72]
    if not exceedances:
        lines.append('No exceedances were recorded for this flight.')
    for index, alert in enumerate(exceedances, 1):
        lines += [
            '',
            f'Exceedance {index}',
            f'  Timestamp:    {alert.timestamp or "N/A"}',
            f'  State:        {alert.alert_state or "N/A"}',
            f'  Level:        {alert.level or "N/A"}',
            f'  Alert:        {alert.alert_name or "N/A"}',
            f'  Description:  {alert.description or "N/A"}',
            '  Triggers:',
        ]
        triggers = _alert_triggers(alert)
        if not triggers:
            lines.append('    - No trigger details available')
        for trigger in triggers:
            measurement = ' '.join(
                value for value in (trigger.value, trigger.units) if value
            ) or 'N/A'
            lines.append(
                f'    - {trigger.name or "Unnamed trigger"}: '
                f'{measurement} | State: {trigger.state or "N/A"}'
            )

    lines += [
        '',
        'MAINTENANCE NOTE',
        '=' * 72,
        'Confirm all trends and exceedances against the approved maintenance '
        'manual, operating limitations, and aircraft history. This report '
        'supports technical assessment and does not replace certified '
        'maintenance documentation.',
    ]
    return '\n'.join(lines)


def technical_report_html(flight: Flight) -> str:
    report = escape(technical_report(flight))
    return f'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {{ size: A4; margin: 14mm; }}
body {{
    font-family: "Segoe UI", Arial, sans-serif;
    color: #172033;
    background: #ffffff;
    font-size: 9.5pt;
}}
.header {{
    background: #0b1830;
    color: #ffffff;
    padding: 24px 26px;
    border-radius: 8px;
}}
.brand {{
    font-size: 27pt;
    font-weight: 800;
    letter-spacing: 1.5px;
}}
.subtitle {{
    color: #c5d5e8;
    font-size: 9pt;
    margin-top: 2px;
}}
.title {{
    font-size: 17pt;
    font-weight: 700;
    margin-top: 17px;
}}
.meta {{
    width: 100%;
    margin: 14px 0;
    border-collapse: separate;
    border-spacing: 7px;
}}
.meta td {{
    background: #f0f4f8;
    border: 1px solid #cbd7e4;
    border-radius: 6px;
    padding: 9px 12px;
}}
.meta-label {{
    color: #64748b;
    font-size: 7pt;
    font-weight: 700;
    text-transform: uppercase;
}}
.meta-value {{
    color: #0d213d;
    font-size: 11pt;
    font-weight: 700;
    margin-top: 3px;
}}
.report {{
    background: #ffffff;
    border: 1px solid #c7d3e1;
    border-top: 4px solid #2d6eb5;
    border-radius: 6px;
    padding: 17px 19px;
}}
pre {{
    font-family: "Consolas", "Courier New", monospace;
    font-size: 8.2pt;
    line-height: 1.48;
    white-space: pre-wrap;
    color: #26364a;
    margin: 0;
}}
.note {{
    background: #edf4fb;
    border-left: 4px solid #2d6eb5;
    color: #405269;
    padding: 10px 12px;
    margin-top: 13px;
    font-size: 8pt;
}}
.footer {{
    border-top: 1px solid #ccd7e4;
    color: #718096;
    text-align: center;
    margin-top: 16px;
    padding-top: 7px;
    font-size: 8pt;
}}
</style>
</head>
<body>
<div class="header">
  <div class="brand">HELINK</div>
  <div class="subtitle">Helicopter Analysis and Preventive Maintenance System</div>
  <div class="title">Preventive Maintenance Report</div>
</div>
<table class="meta"><tr>
  <td><div class="meta-label">Flight Date</div><div class="meta-value">{escape(flight.flight_date or "N/A")}</div></td>
  <td><div class="meta-label">Departure</div><div class="meta-value">{escape(flight.departure_time or "N/A")}</div></td>
  <td><div class="meta-label">Duration</div><div class="meta-value">{escape(flight.duration or "N/A")}</div></td>
  <td><div class="meta-label">Origin</div><div class="meta-value">{escape(flight.origin or "N/A")}</div></td>
</tr></table>
<div class="report"><pre>{report}</pre></div>
<div class="note"><b>Important:</b> This report supports technical assessment and does not replace approved or certified maintenance documentation.</div>
<div class="footer">HELINK &middot; 2026 &middot; v1.0</div>
</body>
</html>'''
