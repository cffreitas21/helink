"""One trigger condition attached to a recorded alert."""

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True,slots=True)
class AlertTrigger:
    """One recorded condition associated with a CAS or exceedance alert."""
    name:str
    value:str=''
    units:str=''
    state:str=''
    @classmethod
    def from_record(cls,record:dict[str,Any]):
        """Convert a stored trigger mapping into an immutable entity."""
        return cls(str(record.get('name') or ''),str(record.get('value') or ''),str(record.get('units') or ''),str(record.get('state') or ''))
