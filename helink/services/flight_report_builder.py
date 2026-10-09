"""Flight-specific maintenance report content and printable presentation."""

from __future__ import annotations

from datetime import datetime
from html import escape

from helink.models.aircraft import Aircraft
from helink.models.flight import AlertTrigger, Flight
from helink.services.airport_lookup import format_airport
from helink.services.flight_overview_summary import flight_parameter_statistics
from helink.services.flight_route_service import flight_route_availability
from helink.services.preventive_maintenance_service import (
    assess_preventive_maintenance,
)


PARAMETERS = (
    ('n1', 'N1', '%'), ('n2', 'N2', '%'), ('nr', 'NR', '%'),
    ('itt', 'ITT', '°C'), ('eng_ot', 'ENG OIL TEMP', '°C'),
    ('eng_op', 'ENG OIL PRESS', 'psi'),
    ('xmsn_ot', 'XMSN OIL TEMP', '°C'),
    ('xmsn_op', 'XMSN OIL PRESS', 'psi'),
    ('fuel_press', 'FUEL PRESS', 'psi'), ('tq', 'TORQUE', '%'),
    ('oat', 'OAT', '°C'), ('ias', 'IAS', 'kt'),
    ('alt_ind', 'ALTITUDE', 'ft'),
)


def _plain(value):
    return str(value) if value not in (None, '') else 'N/A'


def _html(value):
    return escape(_plain(value))


def _number(value, decimals=1):
    return '—' if value is None else f'{value:,.{decimals}f}'


def _measurement(value, unit, decimals=1):
    return '—' if value is None else f'{_number(value, decimals)} {unit}'


def _triggers(alert):
    valid = tuple(
        item for item in alert.triggers
        if str(item.value or '').strip().upper() != 'UNK'
    )
    if valid:
        return valid
    legacy = str(alert.trigger_value or '').strip()
    if alert.trigger_name and legacy.upper() != 'UNK':
        return (
            AlertTrigger(
                alert.trigger_name, legacy,
                alert.trigger_units or '', alert.trigger_state or '',
            ),
        )
    return ()


def _report_data(flight, aircraft):
    recording = flight.engine_data or flight.data_log
    return {
        'statistics': flight_parameter_statistics(flight),
        'assessment': assess_preventive_maintenance(
            flight, aircraft.model if aircraft else '',
        ),
        'exceedances': tuple(
            alert for alert in flight.alerts
            if (alert.kind or '').strip().upper() == 'EXCEEDANCE'
        ),
        'miscmp': tuple(
            alert for alert in flight.alerts
            if (alert.kind or '').strip().upper() == 'CAS'
            and (alert.alert_name or '').strip().upper() == 'MISCMP-P'
            and (alert.alert_state or '').strip().upper() == 'SET'
        ),
        'route': flight_route_availability(flight),
        'first': recording[0].timestamp if recording else None,
        'last': recording[-1].timestamp if recording else None,
    }


def _status(parameter):
    return {
        'normal': 'No upper-limit finding',
        'advisory': f'Transient review ({parameter.findings})',
        'critical': f'Limit finding ({parameter.findings})',
        'unavailable': 'No data',
    }[parameter.severity]


def _trigger_text(alert):
    parts = []
    for trigger in _triggers(alert):
        measurement = ' '.join(
            part for part in (_plain(trigger.value), trigger.units) if part
        )
        state = f' [{trigger.state}]' if trigger.state else ''
        parts.append(f'{_plain(trigger.name)}: {measurement}{state}')
    return '; '.join(parts) or 'No trigger details recorded'


def _table_cell(value, fixed):
    opening = (
        '<td class="fixed" bgcolor="#e9eef3">' if fixed
        else '<td bgcolor="#ffffff">'
    )
    return f'{opening}{_html(value)}</td>'


def _table(headers, rows, widths=None, *, fixed_columns=()):
    heading = ''.join(
        f'<th width="{widths[index] if widths else ""}">{_html(label)}</th>'
        for index, label in enumerate(headers)
    )
    body = ''.join(
        '<tr>' + ''.join(
            _table_cell(value, index in fixed_columns)
            for index, value in enumerate(row)
        ) + '</tr>'
        for row in rows
    )
    return (
        '<table class="data" width="100%" cellspacing="0" cellpadding="5">'
        f'<tr>{heading}</tr>{body}</table>'
    )


def _facts(items):
    rows = [
        (items[index][0], items[index][1],
         items[index + 1][0] if index + 1 < len(items) else '',
         items[index + 1][1] if index + 1 < len(items) else '')
        for index in range(0, len(items), 2)
    ]
    return _table(
        ('FIELD', 'VALUE', 'FIELD', 'VALUE'), rows,
        ('18%', '32%', '18%', '32%'), fixed_columns=(0, 2),
    )


def _section(number, title, content, *, new_page=False):
    break_before = '<p style="page-break-before: always;"></p>' if new_page else ''
    return break_before + f'<h2>{number:02d} &nbsp; {_html(title)}</h2>{content}'


def _event_table(alerts):
    if not alerts:
        return '<p class="empty">No records available for this flight.</p>'
    return _table(
        ('TIME', 'STATE', 'LEVEL', 'EVENT', 'TRIGGERS / VALUES'),
        [
            (_plain(item.timestamp), _plain(item.alert_state),
             _plain(item.level), _plain(item.alert_name), _trigger_text(item))
            for item in alerts
        ],
        ('17%', '10%', '11%', '20%', '42%'),
    )


def flight_report_html(
    flight: Flight, aircraft: Aircraft | None = None,
    *, generated_at: datetime | None = None,
) -> str:
    """Manual-inspired, application-branded HTML for preview and A4 PDF."""
    data = _report_data(flight, aircraft)
    assessment = data['assessment']
    generated = (generated_at or datetime.now().astimezone()).strftime(
        '%Y-%m-%d %H:%M'
    )
    identity = _facts((
        ('Registration', aircraft.registration if aircraft else 'N/A'),
        ('Model', aircraft.model if aircraft else 'N/A'),
        ('Serial number', aircraft.serial_number if aircraft else 'N/A'),
        ('Flight reference', flight.id),
    ))
    summary = _facts((
        ('Flight date', flight.flight_date), ('Duration', flight.duration),
        ('Departure', flight.departure_time), ('Arrival', flight.arrival_time),
        ('Origin', format_airport(flight.origin) if flight.origin else 'N/A'),
        ('Destination',
         format_airport(flight.destination) if flight.destination else 'N/A'),
        ('Route', 'Available' if data['route'].available else 'Unavailable'),
        ('Recorded period',
         f'{_plain(data["first"])} to {_plain(data["last"])}'),
    ))
    parameter_rows = []
    for key, label, unit in PARAMETERS:
        stat = data['statistics'][key]
        digits = 0 if key == 'alt_ind' else 1
        parameter_rows.append((
            label,
            _measurement(stat.average, unit, digits),
            _measurement(stat.maximum, unit, digits),
        ))
    parameters = _table(
        ('PARAMETER', 'AVG', 'MAX'),
        parameter_rows, ('46%', '27%', '27%'),
        fixed_columns=(0,),
    )
    if assessment.applicable:
        preventive_rows = []
        for item in assessment.parameters:
            spec = item.spec
            transient = (
                f'{spec.transient_max:g} {spec.unit} / {spec.transient_seconds} s'
                if spec.transient_max is not None else '—'
            )
            observed = (
                f'{item.observed_max:g} {spec.unit}'
                if item.observed_max is not None else '—'
            )
            preventive_rows.append((
                spec.label, f'{spec.continuous_max:g} {spec.unit}',
                transient, observed, _status(item),
            ))
        preventive = (
            (
                f'<p class="notice">{_html(assessment.message)}</p>'
                if not assessment.assessed_samples else ''
            )
            + _table(
                ('PARAMETER', 'CONTINUOUS MAX', 'TRANSIENT LIMIT',
                 'RECORDED MAX', 'ASSESSMENT'),
                preventive_rows, ('17%', '20%', '22%', '18%', '23%'),
                fixed_columns=(0, 1, 2),
            )
        )
        if assessment.events:
            events = []
            for event in assessment.events:
                spec = next(
                    item.spec for item in assessment.parameters
                    if item.spec.key == event.parameter
                )
                events.append((
                    _plain(event.timestamp), spec.label, event.finding,
                    f'{event.observed:g} {spec.unit}',
                    f'{event.duration_seconds} s'
                    if event.duration_seconds is not None else 'Unknown',
                    event.limit,
                ))
            preventive += '<h3>Recorded limit observations</h3>' + _table(
                ('TIME', 'PARAMETER', 'FINDING', 'OBSERVED', 'DURATION', 'LIMIT'),
                events, ('15%', '13%', '22%', '13%', '11%', '26%'),
            )
        else:
            if not assessment.assessed_samples:
                message = 'No engine samples are available for assessment.'
            elif not any(item.samples for item in assessment.parameters):
                message = 'No supported upper-limit parameters were recorded.'
            else:
                message = (
                    'No upper-limit departures were identified in the '
                    'assessed samples.'
                )
            preventive += f'<p class="empty">{_html(message)}</p>'
    else:
        preventive = (
            f'<p class="notice">{_html(assessment.message)}</p>'
            '<p>No AW119 limit assessment has been made for this aircraft.</p>'
        )
    exceedance_count = len(data['exceedances'])
    recorded_events = (
        f'<h3>Exceedances — {exceedance_count} '
        f'{"record" if exceedance_count == 1 else "records"}</h3>'
        + _event_table(data['exceedances'])
        + f'<h3>MISCMP-P — {len(data["miscmp"])} activations</h3>'
        + _event_table(data['miscmp'])
    )
    sections = ''.join((
        _section(1, 'Flight Summary', summary),
        _section(2, 'Flight Parameters', parameters),
        _section(3, 'Preventive Maintenance', preventive, new_page=True),
        _section(4, 'Recorded Events', recorded_events),
    ))
    return f'''<!doctype html>
<html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 14mm; }}
body {{ font-family: Arial, "Segoe UI", sans-serif; color: #20242a;
        background: white; font-size: 9pt; }}
h1 {{ font-size: 18pt; margin: 12px 0 3px; text-align: center; }}
h2 {{ font-size: 11pt; margin: 18px 0 8px; padding-bottom: 5px;
      border-bottom: 2px solid #162b44; }}
h3 {{ font-size: 9pt; margin: 12px 0 5px; }}
p {{ margin: 5px 0 8px; }}
table {{ border-collapse: collapse; }}
table.data th {{ font-size: 7.7pt; font-weight: bold; text-align: left;
                 background: #e9eef3; border: 1px solid #b8c2cd;
                 padding: 6px; }}
table.data td {{ border: 1px solid #c8d0d9; padding: 5px 6px;
                 vertical-align: top; background: #ffffff; }}
table.data td.fixed {{ background: #e9eef3; color: #23364a; }}
.masthead td {{ border: 0; padding: 0 0 5px; font-size: 9pt; }}
.rule {{ border-bottom: 3px solid #162b44; margin: 2px 0 11px; }}
.subtitle {{ text-align: center; color: #56616d; font-size: 8.5pt; }}
.identity {{ margin-top: 13px; }}
.intro {{ color: #4b5563; }}
.empty {{ color: #546273; font-style: italic; padding: 7px 0; }}
.notice {{ border: 1px solid #a77e28; background: #fff7e8; padding: 8px; }}
.note {{ border-top: 1px solid #7b8793; margin-top: 17px; padding-top: 8px;
         font-size: 8pt; }}
.footer {{ border-top: 1px solid #7b8793; margin-top: 18px; padding-top: 5px;
           font-size: 7.5pt; color: #4b5563; }}
</style></head><body>
<table class="masthead" width="100%"><tr>
<td width="54%"><span style="font-size:15pt;font-weight:bold;">HELINK</span><br>
<span style="font-size:10pt;">Helicopter Analysis and Preventive Maintenance System</span></td>
<td width="46%" align="right"><span style="font-size:15pt;font-weight:bold;">FLIGHT REPORT</span><br>
Generated {_html(generated)}</td></tr></table>
<div class="rule"></div>
<h1>FLIGHT REPORT</h1>
<div class="identity">{identity}</div>
{sections}
<div class="note"><b>TECHNICAL NOTE:</b> This report is an analysis aid, not an
approved maintenance record or a release-to-service decision. Confirm findings
against applicable approved documentation, operating context and aircraft
history. </div>
<div class="footer">HELINK &nbsp;|&nbsp; Report Flight ID {_html(flight.id)}
&nbsp;|&nbsp; Generated {_html(generated)}</div>
</body></html>'''
