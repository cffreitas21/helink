from __future__ import annotations

import json
from pathlib import Path


ICAO_DICTIONARY_FILE = (
    Path(__file__).resolve().parents[1]
    / 'assets'
    / 'icao_dictionary.json'
)


def _load_icao_dictionary() -> dict[str, str]:
    """Load the offline ICAO dictionary distributed with HELINK."""
    try:
        with ICAO_DICTIONARY_FILE.open(encoding='utf-8') as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError, TypeError):
        return {}

    return {
        str(code).strip().upper(): str(name).strip()
        for code, name in data.items()
        if str(code).strip() and str(name).strip()
    }


ICAO_DICTIONARY = _load_icao_dictionary()


def format_airport(code: str | None) -> str:
    """Return an ICAO code with its offline location name when known."""
    normalized = str(code or '').strip().upper()
    if not normalized or normalized == '-':
        return '\N{EM DASH}'
    name = ICAO_DICTIONARY.get(normalized)
    return f'{normalized} - {name}' if name else normalized