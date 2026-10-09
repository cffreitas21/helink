"""Names, units, and sources of recorded engine parameters."""

from types import MappingProxyType

from helink.parameters.definition import ParameterDefinition


ENGINE_PARAMETERS = (
    ParameterDefinition('n1', 'N1', '%', 'engine'),
    ParameterDefinition('n2', 'N2', '%', 'engine'),
    ParameterDefinition('nr', 'NR', '%', 'engine'),
    ParameterDefinition('itt', 'ITT', '\N{DEGREE SIGN}C', 'engine'),
    ParameterDefinition('eng_ot', 'ENG OIL TEMP', '\N{DEGREE SIGN}C', 'engine'),
    ParameterDefinition('eng_op', 'ENG OIL PRESS', 'psi', 'engine'),
    ParameterDefinition('xmsn_ot', 'XMSN OIL TEMP', '\N{DEGREE SIGN}C', 'engine'),
    ParameterDefinition('xmsn_op', 'XMSN OIL PRESS', 'psi', 'engine'),
    ParameterDefinition('fuel_press', 'FUEL PRESS', 'psi', 'engine'),
    ParameterDefinition('oat', 'OAT', '\N{DEGREE SIGN}C', 'engine'),
    ParameterDefinition('tq', 'TORQUE', '%', 'engine'),
)

ENGINE_BY_KEY = MappingProxyType({item.key: item for item in ENGINE_PARAMETERS})
