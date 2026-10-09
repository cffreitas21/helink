"""Catalog of recorded flight parameters shared across the application."""

from types import MappingProxyType

from helink.parameters.definition import ParameterDefinition
from helink.parameters.engine import ENGINE_PARAMETERS
from helink.parameters.gps import GPS_PARAMETERS


PARAMETERS = ENGINE_PARAMETERS + GPS_PARAMETERS
PARAMETERS_BY_KEY = MappingProxyType({item.key: item for item in PARAMETERS})

__all__ = (
    'ParameterDefinition', 'ENGINE_PARAMETERS', 'GPS_PARAMETERS',
    'PARAMETERS', 'PARAMETERS_BY_KEY',
)
