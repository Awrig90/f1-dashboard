"""FastF1 boundary: disk cache, bounded Streamlit caches, lazy telemetry."""
import logging
import os
from pathlib import Path
import pandas as pd
import fastf1
import streamlit as st
from .processing import NoData, normalize, personal_bests, position_observations

CACHE_DIR = Path(os.environ.get('F1_CACHE_DIR', Path(__file__).resolve().parents[1] / '.fastf1-cache'))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))
log = logging.getLogger(__name__)

@st.cache_data(ttl=3600, max_entries=12, show_spinner=False)
def schedule(year):
    try:
        result = fastf1.get_event_schedule(year, include_testing=False)
        return result.loc[result.RoundNumber.gt(0)].copy()
    except Exception as exc:
        log.exception('Schedule load failed for %s', year)
        raise NoData('The event schedule could not be loaded. Check your internet connection, '
                     'try again, or choose another season.') from exc

@st.cache_data(ttl=3600, max_entries=4, show_spinner=False)
def session_data(year, round_number, name, telemetry=False):
    # cache_data returns isolated copies; no mutable Session shared between users.
    try:
        session = fastf1.get_session(year, round_number, name)
        session.load(telemetry=telemetry, weather=False, messages=True)
        if session.laps.empty:
            raise NoData('No lap data is available. The session may not have started, may have '
                         'been cancelled, or its timing data may not yet be published.')
        return session
    except NoData:
        raise
    except Exception as exc:
        log.exception('Session load failed: %s %s %s', year, round_number, name)
        raise NoData('Session data could not be loaded. Check your connection and try a completed '
                     'session. Some sessions have incomplete timing coverage.') from exc

@st.cache_data(ttl=3600, max_entries=8, show_spinner=False)
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

@st.cache_data(ttl=3600, max_entries=8, show_spinner=False)
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
    """Warm FastF1's persistent disk cache for completed sessions in one weekend.

    Telemetry is deliberately excluded: timing/lap data are the common path and
    telemetry is much larger. A telemetry plot will fetch/cache it on demand.
    This function bypasses Streamlit's in-memory Session cache on purpose.
    """
    report = []
    for name in session_names:
        try:
            session = fastf1.get_session(year, round_number, name)
            session.load(telemetry=False, weather=False, messages=False)
            report.append({'session': name, 'status': 'cached'})
        except Exception as exc:
            log.exception('Weekend pre-cache failed: %s %s %s', year, round_number, name)
            report.append({'session': name, 'status': 'failed', 'error': str(exc)})
    return report
