"""Explicit analytical compatibility; event sessions themselves come from FastF1."""
from dataclasses import dataclass
from datetime import datetime, timezone
import re

@dataclass(frozen=True)
class Analysis:
    key: str
    label: str
    kinds: tuple[str, ...]
    selector: str = 'drivers'
    filtering: bool = False

ALL = ('practice', 'qualifying', 'race')
TIMED = ('practice', 'qualifying')
ANALYSES = (
    Analysis('fastest', 'Session Fastest Laps', TIMED),
    Analysis('laps', 'Driver Lap Times', ALL, 'driver', True),
    Analysis('drivers', 'Driver Lap-Time Distribution', ALL, 'drivers', True),
    Analysis('teams', 'Team Lap-Time Distribution', ('practice', 'race'), 'teams', True),
    Analysis('positions', 'Position Tracker', ('race',)),
    Analysis('strategy', 'Tyre Strategy', ('race',)),
    Analysis('speed', 'Speed on Track Map', ALL, 'driver'),
    Analysis('compounds', 'Practice Compound Usage and Performance', ('practice',), 'drivers', True),
    Analysis('sectors', 'Sector Performance / Theoretical Best Lap', TIMED),
)

def session_kind(name: str) -> str:
    if name in ('Race', 'Sprint'):
        return 'race'
    if name.startswith('Practice'):
        return 'practice'
    if name in ('Qualifying', 'Sprint Qualifying', 'Sprint Shootout'):
        return 'qualifying'
    return 'unknown'

def available(name):
    return [a for a in ANALYSES if session_kind(name) in a.kinds]

def event_sessions(event):
    """Read every numbered session slot, without assuming a weekend format."""
    keys = sorted((k for k in event.keys() if re.fullmatch(r'Session\d+', str(k))),
                  key=lambda k: int(k[7:]))
    return list(dict.fromkeys(event[k] for k in keys
                             if isinstance(event[k], str) and event[k].strip()))

def seasons():
    # Detailed timing and telemetry required here are supported from 2018.
    return list(range(datetime.now(timezone.utc).year, 2017, -1))
