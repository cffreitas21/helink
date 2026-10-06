"""Upper-limit screening of every imported AW119 engine sample.

This is a review aid, not an aircraft limitation or airworthiness determination.
No flight phase is inferred; a phase-specific QRH allowance may differ.
"""

from dataclasses import dataclass
from math import isfinite
import re


@dataclass(frozen=True, slots=True)
class LimitSpec:
    key: str
    label: str
    unit: str
    continuous_max: float
    transient_max: float | None = None
    transient_seconds: int | None = None


# AW119MKII G1000H NXi QRH, Limitations, Issue 1, pages 19-20.
# ENG OIL TEMP uses the separately supplied 115 C maximum, without a transient.
LIMITS = (
    LimitSpec('n1', 'N1', '%', 100.1, 103.8, 30),
    LimitSpec('n2', 'N2', '%', 103, 108, 10),
    LimitSpec('nr', 'NR', '%', 103, 108, 10),
    LimitSpec('itt', 'ITT', '\N{DEGREE SIGN}C', 755, 860, 5),
    LimitSpec('eng_ot', 'ENG OIL TEMP', '\N{DEGREE SIGN}C', 115),
    LimitSpec('tq', 'TORQUE', '%', 100, 115, 6),
)

MAX_CONTIGUOUS_GAP_SECONDS = 2


@dataclass(frozen=True, slots=True)
class LimitEvent:
    parameter: str
    severity: str
    finding: str
    observed: float
    limit: str
    start_index: int
    end_index: int
    timestamp: str
    duration_seconds: int | None


@dataclass(frozen=True, slots=True)
class ParameterAssessment:
    spec: LimitSpec
    samples: int
    observed_max: float | None
    severity: str
    findings: int


@dataclass(frozen=True, slots=True)
class MaintenanceAssessment:
    applicable: bool
    message: str
    assessed_samples: int
    parameters: tuple[ParameterAssessment, ...]
    events: tuple[LimitEvent, ...]


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _clock_seconds(timestamp):
    matches = re.findall(
        r'(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?', str(timestamp or ''),
    )
    if not matches:
        return None
    hour, minute, second = (int(part or 0) for part in matches[-1])
    if hour >= 24 or minute >= 60 or second >= 60:
        return None
    return hour * 3600 + minute * 60 + second


def _elapsed_seconds(rows):
    """Unwrap an overnight recording without treating clock reversals as time."""
    elapsed = []
    previous_clock = None
    previous_elapsed = None
    day_offset = 0
    for row in rows:
        clock = _clock_seconds(getattr(row, 'timestamp', None))
        if clock is None:
            elapsed.append(None)
            continue
        if previous_clock is not None and previous_clock - clock > 12 * 3600:
            day_offset += 24 * 3600
        instant = clock + day_offset
        elapsed.append(
            instant if previous_elapsed is None or instant >= previous_elapsed
            else None
        )
        previous_clock = clock
        if elapsed[-1] is not None:
            previous_elapsed = instant
    return elapsed


def aw119_limits_apply(model):
    normalized = re.sub(r'[^a-z0-9]', '', str(model or '').casefold())
    return any(name in normalized for name in ('aw119', 'a119', 'koala'))


def _category(value, spec):
    # Lower limits are intentionally outside this first screening pass.
    if spec.transient_max is None:
        return 'above_maximum' if value > spec.continuous_max else None
    if value > spec.transient_max:
        return 'above_transient'
    if value > spec.continuous_max:
        return 'transient'
    return None


def _limit_text(spec, category):
    if category == 'above_maximum':
        return f'Maximum {spec.continuous_max:g} {spec.unit}'
    if category == 'above_transient':
        return f'Transient ceiling {spec.transient_max:g} {spec.unit}'
    return (
        f'Continuous maximum {spec.continuous_max:g} {spec.unit}; '
        f'transient up to {spec.transient_max:g} {spec.unit} '
        f'for {spec.transient_seconds} s'
    )


def _event(spec, category, start, end, values, elapsed, rows):
    duration = (
        round(elapsed[end] - elapsed[start])
        if end > start and elapsed[start] is not None and elapsed[end] is not None
        else None
    )
    if category == 'transient':
        exceeded = duration is not None and duration > spec.transient_seconds
        severity = 'critical' if exceeded else 'advisory'
        finding = (
            'Transient duration exceeded' if exceeded
            else 'Above continuous - duration unknown' if duration is None
            else 'Above continuous'
        )
    else:
        severity = 'critical'
        finding = (
            'Above maximum' if category == 'above_maximum'
            else 'Above transient ceiling'
        )
    observed = max(values)
    return LimitEvent(
        spec.key, severity, finding, observed, _limit_text(spec, category),
        start, end, str(rows[start].timestamp or ''), duration,
    )


def _assess_parameter(spec, rows, window, elapsed):
    observed = []
    events = []
    category = None
    start = previous = None
    values = []

    def finish():
        nonlocal category, start, previous, values
        if category is not None:
            events.append(
                _event(spec, category, start, previous, values, elapsed, rows)
            )
        category, start, previous, values = None, None, None, []

    for index in window:
        value = _number(getattr(rows[index], spec.key, None))
        if value is not None:
            observed.append(value)
        current = _category(value, spec) if value is not None else None
        contiguous = (
            previous is not None
            and index == previous + 1
            and elapsed[previous] is not None
            and elapsed[index] is not None
            and 0 <= elapsed[index] - elapsed[previous] <= MAX_CONTIGUOUS_GAP_SECONDS
        )
        if current != category or category is not None and not contiguous:
            finish()
        if current is not None:
            if category is None:
                category, start = current, index
            previous = index
            values.append(value)
    finish()
    severity = (
        'critical' if any(event.severity == 'critical' for event in events)
        else 'advisory' if events else 'normal' if observed else 'unavailable'
    )
    return ParameterAssessment(
        spec, len(observed), max(observed) if observed else None,
        severity, len(events),
    ), events


def assess_preventive_maintenance(flight, aircraft_model):
    """Screen AW119 upper limits across the whole imported engine recording."""
    if not aw119_limits_apply(aircraft_model):
        return MaintenanceAssessment(
            False,
            'The AW119MKII limits are not applied to '
            f'{aircraft_model or "an unidentified aircraft model"}.',
            0,
            tuple(ParameterAssessment(spec, 0, None, 'unavailable', 0)
                  for spec in LIMITS),
            (),
        )
    rows = tuple(flight.engine_data or ())
    elapsed = _elapsed_seconds(rows)
    if not rows:
        message = (
            'No engine data was imported for this flight. The limits cannot '
            'be assessed.'
        )
    else:
        message = (
            'All imported engine samples are assessed against the selected '
            'upper limits. No flight-phase classification or GPS filtering '
            'is applied.'
        )
    parameters = []
    events = []
    for spec in LIMITS:
        assessment, findings = _assess_parameter(
            spec, rows, range(len(rows)), elapsed,
        )
        parameters.append(assessment)
        events.extend(findings)
    events.sort(key=lambda event: (event.start_index, event.parameter))
    return MaintenanceAssessment(
        True, message, len(rows), tuple(parameters), tuple(events),
    )
