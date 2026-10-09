"""Recorded flight statistics for the Overview, without maintenance thresholds."""

from collections import Counter
from dataclasses import dataclass
from math import isfinite

from helink.models.flight.flight import Flight


@dataclass(frozen=True, slots=True)
class ParameterStatistics:
    """Average, maximum, and valid-sample count for one flight parameter."""
    average: float | None
    maximum: float | None
    samples: int


@dataclass(frozen=True, slots=True)
class EventSummary:
    """Count and availability of a relevant flight-event category."""
    count: int
    available: bool
    activated_names: tuple[tuple[str, int], ...] = ()


def recorded_statistics(records, attributes):
    """Aggregate finite values in one pass; missing values never become zero."""
    counts = dict.fromkeys(attributes, 0)
    averages = dict.fromkeys(attributes, 0.0)
    maxima = dict.fromkeys(attributes, None)
    for record in records:
        for attribute in attributes:
            raw = getattr(record, attribute, None)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if not isfinite(value):
                continue
            counts[attribute] += 1
            count = counts[attribute]
            averages[attribute] += (value - averages[attribute]) / count
            previous = maxima[attribute]
            maxima[attribute] = value if previous is None else max(previous, value)
    return {
        attribute: ParameterStatistics(
            averages[attribute] if counts[attribute] else None,
            maxima[attribute],
            counts[attribute],
        )
        for attribute in attributes
    }


def flight_parameter_statistics(flight: Flight):
    """Calculate finite engine and GPS statistics for the Overview."""
    engine = recorded_statistics(flight.engine_data, (
        'itt', 'eng_ot', 'xmsn_ot', 'oat',
        'eng_op', 'xmsn_op', 'fuel_press',
        'n1', 'n2', 'nr', 'tq',
    ))
    gps = recorded_statistics(flight.data_log, ('ias', 'alt_ind'))
    return {**engine, **gps}


def important_flight_events(flight: Flight):
    """Count activations, not SET/CLEARED pairs, and expose missing sources."""
    counts = {'exceedances': 0, 'miscmp': 0}
    exceedance_names = Counter()
    kinds = set()
    for alert in flight.alerts:
        kind = (alert.kind or '').strip().upper()
        kinds.add(kind)
        if (alert.alert_state or '').strip().upper() != 'SET':
            continue
        if kind == 'EXCEEDANCE':
            counts['exceedances'] += 1
            name = (alert.alert_name or '').strip().upper() or 'Unnamed exceedance'
            exceedance_names[name] += 1
        elif kind == 'CAS' and (
            (alert.alert_name or '').strip().upper() == 'MISCMP-P'
        ):
            counts['miscmp'] += 1
    imported = set(flight.imported_files)
    exceedance_sources = {
        '2_Exceedance_Log', '3_Exceedance_Log_CONT', '4_VNE_Dynamic',
    }
    cas_sources = {'0_CAS_Default', '5_CAS', 'Garmin Alerts'}
    return {
        'exceedances': EventSummary(
            counts['exceedances'],
            'EXCEEDANCE' in kinds or bool(imported & exceedance_sources),
            tuple(sorted(exceedance_names.items())),
        ),
        'miscmp': EventSummary(
            counts['miscmp'], 'CAS' in kinds or bool(imported & cas_sources),
        ),
    }
