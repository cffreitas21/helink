"""AW119MKII upper limits used for preventive-maintenance screening."""

from dataclasses import dataclass

from helink.parameters.engine import ENGINE_BY_KEY


@dataclass(frozen=True, slots=True)
class LimitSpec:
    """Continuous maximum and optional transient ceiling for one parameter."""

    key: str
    label: str
    unit: str
    continuous_max: float
    transient_max: float | None = None
    transient_seconds: int | None = None


def _limit(key, continuous_max, transient_max=None, transient_seconds=None):
    """Attach a configured threshold to the shared parameter metadata."""
    parameter = ENGINE_BY_KEY[key]
    return LimitSpec(
        key, parameter.label, parameter.unit,
        continuous_max, transient_max, transient_seconds,
    )


# AW119MKII G1000H NXi QRH, Limitations, Issue 1, pages 19-20.
# ENG OIL TEMP uses the separately supplied 115 C maximum, without a transient.
LIMITS = (
    _limit('n1', 100.1, 103.8, 30),
    _limit('n2', 103, 108, 10),
    _limit('nr', 103, 108, 10),
    _limit('itt', 755, 860, 5),
    _limit('eng_ot', 115),
    _limit('tq', 100, 115, 6),
)
