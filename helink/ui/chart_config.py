"""Chart order and colors; labels and units come from the parameter catalog."""

from helink.parameters import PARAMETERS_BY_KEY


PARAMETER_COLORS = {
    'n1': '#17becf',
    'n2': '#ff7f0e',
    'nr': '#4b5563',
    'itt': '#1f77b4',
    'eng_ot': '#2ca02c',
    'eng_op': '#d62728',
    'xmsn_ot': '#9467bd',
    'xmsn_op': '#8c564b',
    'fuel_press': '#e377c2',
    'oat': '#008080',
    'tq': '#b58900',
    'ias': '#243b80',
    'alt_ind': '#a33778',
}


def _chart_definitions(keys):
    """Combine shared parameter metadata with UI-specific chart colors."""
    return tuple(
        (key, PARAMETERS_BY_KEY[key].label, PARAMETERS_BY_KEY[key].unit,
         PARAMETER_COLORS[key])
        for key in keys
    )


TELEMETRY_PARAMETERS = _chart_definitions((
    'n1', 'n2', 'nr', 'itt', 'eng_ot', 'eng_op',
    'xmsn_ot', 'xmsn_op', 'fuel_press',
))

# Available on demand when opened from a flight's Overview.
OVERVIEW_TELEMETRY_PARAMETERS = _chart_definitions((
    'oat', 'tq', 'ias', 'alt_ind',
))
