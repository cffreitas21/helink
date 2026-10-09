"""Names, units, and sources of recorded GPS/flight parameters."""

from helink.parameters.definition import ParameterDefinition


GPS_PARAMETERS = (
    ParameterDefinition('ias', 'IAS', 'kt', 'gps'),
    ParameterDefinition('alt_ind', 'ALTITUDE', 'ft', 'gps'),
)
