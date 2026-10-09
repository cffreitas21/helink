"""Shared definition of a recorded flight parameter."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ParameterDefinition:
    """Identify a recorded parameter independently of its UI presentation."""

    key: str
    label: str
    unit: str
    source: Literal['engine', 'gps']
