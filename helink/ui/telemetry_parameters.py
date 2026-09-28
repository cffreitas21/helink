"""Shared presentation metadata for recorded telemetry parameters."""

TELEMETRY_PARAMETERS = (
    ('n1', 'N1', '%', '#17becf'),
    ('n2', 'N2', '%', '#ff7f0e'),
    ('nr', 'NR', '%', '#4b5563'),
    ('itt', 'ITT', '\N{DEGREE SIGN}C', '#1f77b4'),
    ('eng_ot', 'ENG OIL TEMP', '\N{DEGREE SIGN}C', '#2ca02c'),
    ('eng_op', 'ENG OIL PRESS', 'psi', '#d62728'),
    ('xmsn_ot', 'XMSN OIL TEMP', '\N{DEGREE SIGN}C', '#9467bd'),
    ('xmsn_op', 'XMSN OIL PRESS', 'psi', '#8c564b'),
    ('fuel_press', 'FUEL PRESS', 'psi', '#e377c2'),
)

# Available on demand when opened from a flight's Overview.
OVERVIEW_TELEMETRY_PARAMETERS = (
    ('oat', 'OAT', '\N{DEGREE SIGN}C', '#008080'),
    ('tq', 'TORQUE', '%', '#b58900'),
    ('ias', 'IAS', 'kt', '#243b80'),
    ('alt_ind', 'ALTITUDE', 'ft', '#a33778'),
)
