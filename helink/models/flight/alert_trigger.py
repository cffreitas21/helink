from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True,slots=True)
class AlertTrigger:
    name:str
    value:str=''
    units:str=''
    state:str=''
    @classmethod
    def from_record(cls,record:dict[str,Any]):
        return cls(str(record.get('name') or ''),str(record.get('value') or ''),str(record.get('units') or ''),str(record.get('state') or ''))
