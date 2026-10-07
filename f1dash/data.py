"""FastF1 boundary: disk cache, one in-process session, lazy telemetry."""
import gc
import logging
import os
from pathlib import Path
from threading import RLock

import pandas as pd
import fastf1
import streamlit as st

from .processing import NoData, normalize, personal_bests, position_observations

CACHE_DIR = Path(os.environ.get('F1_CACHE_DIR', Path(__file__).resolve().parents[1] / '.fastf1-cache'))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))
log = logging.getLogger(__name__)

# Keep exactly one loaded FastF1 Session object in this Python process. This is
# intentionally separate from Streamlit's resource cache: small hosts (notably
# 512 MB instances) cannot safely retain several full weekend sessions at once.
_SESSION_LOCK = RLock()
_CURRENT_SESSION = {
    'key': None,
    'session': None,
    'telemetry_loaded': False,
}


@st.cache_data(ttl=3600, max_entries=6, show_spinner=False)
def schedule(year):
    try:
        result = fastf1.get_event_schedule(year, include_testing=False)
        return result.loc[result.RoundNumber.gt(0)].copy()
    except Exception as exc:
        log.exception('Schedule load failed for %s', year)
        raise NoData('The event schedule could not be loaded. Check your internet connection, '
                     'try again, or choose another season.') from exc


def _load_new_session(year, round_number, name, telemetry=False):
    """Create and load one FastF1 session without retaining it globally."""
    session = fastf1.get_session(year, round_number, name)
    session.load(telemetry=telemetry, weather=False, messages=True)
    if session.laps.empty:
        raise NoData('No lap data is available. The session may not have started, may have '
                     'been cancelled, or its timing data may not yet be published.')
    return session


def _clear_derived_caches():
    """Drop small session-specific caches when the selected session changes."""
    for name in ('fastest_telemetry', 'reported_positions'):
        cached = globals().get(name)
        clear = getattr(cached, 'clear', None)
        if clear is not None:
            clear()


def clear_session_cache():
    """Drop the retained FastF1 Session and its session-specific derived caches."""
    with _SESSION_LOCK:
        _CURRENT_SESSION['session'] = None
        _CURRENT_SESSION['key'] = None
        _CURRENT_SESSION['telemetry_loaded'] = False
    _clear_derived_caches()
    gc.collect()


def session_data(year, round_number, name, telemetry=False):
    """Return the selected session while retaining at most one full Session.

    Repeated reruns for the same selected session reuse the same object. Switching
    sessions drops the previous object before the replacement is loaded. Telemetry
    is loaded lazily into that same object rather than creating a second cached
    copy of the session.
    """
    key = (int(year), int(round_number), str(name))
    with _SESSION_LOCK:
        try:
            if _CURRENT_SESSION['key'] != key or _CURRENT_SESSION['session'] is None:
                _clear_derived_caches()
                # Release the previous session before loading the replacement so
                # peak RAM is kept as low as practical on small hosted instances.
                _CURRENT_SESSION['session'] = None
                _CURRENT_SESSION['key'] = None
                _CURRENT_SESSION['telemetry_loaded'] = False
                gc.collect()

                session = _load_new_session(year, round_number, name, telemetry=False)
                _CURRENT_SESSION['session'] = session
                _CURRENT_SESSION['key'] = key

            session = _CURRENT_SESSION['session']
            if telemetry and not _CURRENT_SESSION['telemetry_loaded']:
                # FastF1 supports loading the same Session again with telemetry
                # enabled; this augments the retained object instead of caching a
                # second full Session keyed by telemetry=True.
                session.load(telemetry=True, weather=False, messages=True)
                _CURRENT_SESSION['telemetry_loaded'] = True
                if session.laps.empty:
                    raise NoData('No lap data is available. The session may not have started, may have '
                                 'been cancelled, or its timing data may not yet be published.')
            return session
        except NoData:
            clear_session_cache()
            raise
        except Exception as exc:
            clear_session_cache()
            log.exception('Session load failed: %s %s %s', year, round_number, name)
            raise NoData('Session data could not be loaded. Check your connection and try a completed '
                         'session. Some sessions have incomplete timing coverage.') from exc


@st.cache_data(ttl=3600, max_entries=2, show_spinner=False)
def fastest_telemetry(year, round_number, name, driver):
    session = session_data(year, round_number, name, telemetry=True)
    try:
        d = personal_bests(normalize(session.laps))
        d = d.loc[d.Driver.eq(driver)]
        if d.empty:
            raise NoData('This driver has no valid timed lap in the selected session.')
        best = d.sort_values('LapTimeSeconds').iloc[0]
        lap = session.laps.loc[(session.laps.Driver == driver)
                               & (session.laps.LapNumber == best.LapNumber)].iloc[0]
        tel = pd.DataFrame(lap.get_telemetry()).copy()
        if not {'X', 'Y', 'Speed'}.issubset(tel.columns):
            raise NoData('Position or speed telemetry is missing for this lap.')
        # Keep bad samples as gaps: dropping them would connect across missing data.
        import numpy as np
        for col in ['X', 'Y', 'Speed']:
            tel[col] = pd.to_numeric(tel[col], errors='coerce').replace([np.inf, -np.inf], np.nan)
        tel.loc[tel.Speed.lt(0), 'Speed'] = np.nan
        if len(tel.dropna(subset=['X', 'Y', 'Speed'])) < 3:
            raise NoData('There are too few telemetry samples to draw this lap.')
        tel['Driver'] = driver
        tel['LapNumber'] = best.LapNumber
        return tel, float(best.LapTimeSeconds), int(best.LapNumber)
    except NoData:
        raise
    except Exception as exc:
        log.exception('Telemetry unavailable for %s', driver)
        raise NoData('Speed/position telemetry is unavailable for this driver’s fastest valid lap. '
                     'Try another driver or session. Timing charts can still be used.') from exc


@st.cache_data(ttl=3600, max_entries=2, show_spinner=False)
def reported_positions(year, round_number, name):
    session = session_data(year, round_number, name)
    try:
        # Deliberately isolated private API dependency, pinned to FastF1 3.8.3.
        # The high-level laps.Position is derived from aligned timestamps and
        # demonstrably incorrect for some delayed-start sessions.
        from fastf1 import _api
        raw = _api.fetch_page(session.api_path, 'timing_data')
        if not raw:
            raise NoData('The reported position feed is unavailable. No timestamp-derived substitute will be plotted.')
        roster_rows = pd.DataFrame(session.results)
        mapping = dict(zip(roster_rows.DriverNumber.astype(str), roster_rows.Abbreviation))
        out = position_observations(raw, mapping)
        original = pd.DataFrame(session.laps)[['Driver', 'LapNumber', 'Position']].rename(columns={'Position':'FastF1DerivedPosition'})
        original = original.drop_duplicates(['Driver', 'LapNumber'], keep=False)
        return out.merge(original, on=['Driver','LapNumber'], how='left', validate='one_to_one')
    except NoData:
        raise
    except Exception as exc:
        log.exception('Reported position feed unavailable')
        raise NoData('Reported race positions could not be loaded. No timestamp-derived substitute will be plotted; try refreshing or another session.') from exc


def roster(session, d):
    result = pd.DataFrame(session.results)
    ordered = result.Abbreviation.dropna().tolist() if 'Abbreviation' in result else []
    ordered = list(dict.fromkeys([x for x in ordered if x] + d.Driver.dropna().tolist()))
    labels = {x: x for x in ordered}
    if {'Abbreviation','FullName'}.issubset(result):
        for _, row in result.iterrows():
            if row.Abbreviation in labels and pd.notna(row.FullName):
                labels[row.Abbreviation] = f'{row.FullName} ({row.Abbreviation})'
    return ordered, labels


def precache_weekend(year, round_number, session_names):
    """Warm FastF1's disk cache without retaining weekend sessions in RAM.

    The currently retained in-process session is released first. Each completed
    session is then loaded one at a time with telemetry disabled and immediately
    discarded. This keeps peak memory close to one FastF1 Session while making
    later selected-session loads cheaper because the source files are on disk.
    """
    clear_session_cache()
    report = []
    for name in session_names:
        session = None
        try:
            session = _load_new_session(year, round_number, name, telemetry=False)
            report.append({'session': name, 'status': 'cached'})
        except Exception as exc:
            log.exception('Weekend pre-cache failed: %s %s %s', year, round_number, name)
            report.append({'session': name, 'status': 'failed', 'error': str(exc)})
        finally:
            session = None
            gc.collect()
    return report
