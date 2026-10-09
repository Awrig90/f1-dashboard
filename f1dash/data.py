"""FastF1 boundary: disk cache plus lightweight cached session snapshots.

The hosted app deliberately does not retain a full FastF1 Session object between
Streamlit reruns. A loaded Session can be surprisingly large relative to a
512 MB host. We extract only the chart inputs we need, then release the Session.
"""
from __future__ import annotations

import ctypes
import gc
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import fastf1
import streamlit as st

from .processing import NoData, normalize, personal_bests, position_observations

CACHE_DIR = Path(os.environ.get('F1_CACHE_DIR', Path(__file__).resolve().parents[1] / '.fastf1-cache'))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))
log = logging.getLogger(__name__)

# Only keep fields that the current visualisations/exports actually use.
RESULT_COLUMNS = ('Abbreviation', 'FullName', 'DriverNumber', 'TeamName')


def current_rss_mb():
    """Best-effort current process RSS for Render diagnostics."""
    try:
        with open('/proc/self/status', 'r', encoding='utf-8') as handle:
            for line in handle:
                if line.startswith('VmRSS:'):
                    return float(line.split()[1]) / 1024.0
    except Exception:
        return None
    return None


def _release_memory(label=None):
    """Collect Python objects and, on glibc Linux, return free heap pages to OS."""
    gc.collect()
    try:
        libc = ctypes.CDLL('libc.so.6')
        trim = getattr(libc, 'malloc_trim', None)
        if trim is not None:
            trim(0)
    except Exception:
        pass
    if label:
        rss = current_rss_mb()
        if rss is not None:
            log.info('Memory after %s: %.1f MB RSS', label, rss)


@st.cache_data(ttl=3600, max_entries=6, show_spinner=False)
def schedule(year):
    try:
        result = fastf1.get_event_schedule(year, include_testing=False)
        return result.loc[result.RoundNumber.gt(0)].copy()
    except Exception as exc:
        log.exception('Schedule load failed for %s', year)
        raise NoData('The event schedule could not be loaded. Check your internet connection, '
                     'try again, or choose another season.') from exc


def _results_frame(session):
    result = pd.DataFrame(session.results)
    cols = [c for c in RESULT_COLUMNS if c in result.columns]
    return result.loc[:, cols].copy().reset_index(drop=True)


def _style_maps(session, data, results):
    """Capture FastF1 driver/team styling without retaining the Session itself."""
    styles = {'driver': {}, 'team': {}}
    try:
        import fastf1.plotting as fp
        drivers = list(dict.fromkeys(
            results.get('Abbreviation', pd.Series(dtype=object)).dropna().astype(str).tolist()
            + data.Driver.dropna().astype(str).tolist()
        ))
        teams = list(dict.fromkeys(data.Team.dropna().astype(str).tolist()))
        for driver in drivers:
            try:
                style = fp.get_driver_style(identifier=driver,
                                            style=['color', 'linestyle'],
                                            session=session)
                styles['driver'][driver] = {
                    'color': style.get('color'),
                    'linestyle': style.get('linestyle', '-')
                }
            except Exception:
                try:
                    styles['driver'][driver] = {
                        'color': fp.get_driver_color(driver, session=session),
                        'linestyle': '-'
                    }
                except Exception:
                    pass
        for team in teams:
            try:
                styles['team'][team] = fp.get_team_color(team, session=session)
            except Exception:
                pass
    except Exception:
        log.exception('Could not capture FastF1 style map; deterministic fallbacks will be used')
    return styles


def _load_snapshot(year, round_number, name):
    """Load FastF1 once, copy lean chart inputs, then release the full Session."""
    session = None
    try:
        rss = current_rss_mb()
        if rss is not None:
            log.info('Memory before FastF1 load: %.1f MB RSS', rss)
        session = fastf1.get_session(year, round_number, name)
        # Race-control messages populate Deleted and correct IsPersonalBest.
        # Telemetry/weather remain off; speed and position use on-demand paths.
        session.load(telemetry=False, weather=False, messages=True)
        if session.laps.empty:
            raise NoData('No lap data is available. The session may not have started, may have '
                         'been cancelled, or its timing data may not yet be published.')
        data = normalize(session.laps)
        results = _results_frame(session)
        styles = _style_maps(session, data, results)
        api_path = str(session.api_path)
        return {'data': data, 'results': results, 'styles': styles, 'api_path': api_path,
                'unknown_deleted_laps': int(data.Deleted.isna().sum())}
    finally:
        session = None
        _release_memory('releasing full FastF1 session')


@st.cache_data(ttl=3600, max_entries=1, show_spinner=False)
def session_snapshot(year, round_number, name):
    """Small, serialisable representation of one selected session.

    Only one snapshot is kept because session switching should not grow the
    Streamlit data cache indefinitely on a small hosted instance.
    """
    try:
        return _load_snapshot(year, round_number, name)
    except NoData:
        raise
    except Exception as exc:
        log.exception('Session load failed: %s %s %s', year, round_number, name)
        raise NoData('Session data could not be loaded. Check your connection and try a completed '
                     'session. Some sessions have incomplete timing coverage.') from exc


def _naive_utc(value):
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return pd.NaT
    if ts.tzinfo is not None:
        ts = ts.tz_convert('UTC').tz_localize(None)
    return ts


def _decode_driver_stream(api_path, driver_number, stream, start=None, end=None, pad_seconds=1.0):
    """Scan official packets, retaining one driver's required channels only.

    The maximum Date - packet Time across both streams is FastF1 3.8.3's
    session-zero offset. Scan the whole stream so a late low-latency packet is
    not missed. No full-field telemetry frames are materialised. fetch_page
    still downloads the full compressed stream; loading peak is not bounded.
    """
    from fastf1 import _api
    from fastf1.utils import to_datetime, to_timedelta
    is_car = stream == 'car_data'
    columns = ['Date', 'Speed'] if is_car else ['Date', 'X', 'Y']
    required = ('0', '2', '3', '4', '5') if is_car else ('X', 'Y', 'Z')
    rows, offset, failures = [], None, 0
    response = None
    try:
        response = _api.fetch_page(api_path, stream)
        if not response:
            raise NoData('Telemetry stream is unavailable for this session.')
        for record in response:
            try:
                packet_time = pd.Timedelta(to_timedelta(record[:12]))
                packet = _api.parse(record[12:], zipped=True)
                for entry in packet.get('Entries' if is_car else 'Position', []):
                    date = pd.Timestamp(to_datetime(entry['Utc' if is_car else 'Timestamp']))
                    if pd.isna(date) or pd.isna(packet_time):
                        continue
                    entries = entry.get('Cars' if is_car else 'Entries', {})
                    channels = [v.get('Channels', {}) if is_car else v for v in entries.values()]
                    if any(all(k in value for k in required) for value in channels):
                        candidate = date - packet_time
                        offset = candidate if offset is None else max(offset, candidate)
                    selected = entries.get(str(driver_number), {})
                    selected = selected.get('Channels', {}) if is_car else selected
                    if not all(k in selected for k in required):
                        continue
                    if start is not None and date < start - pd.Timedelta(seconds=pad_seconds):
                        continue
                    if end is not None and date > end + pd.Timedelta(seconds=pad_seconds):
                        continue
                    values = [selected['2']] if is_car else [selected['X'], selected['Y']]
                    rows.append((date, *values))
            except (ValueError, TypeError, KeyError, AttributeError):
                failures += 1
        if failures:
            log.warning('%s: skipped %s malformed telemetry packets', stream, failures)
    finally:
        response = None
        _release_memory('decoding selected-driver ' + stream)
    out = pd.DataFrame(rows, columns=columns)
    for col in columns[1:]:
        out[col] = pd.to_numeric(out[col], errors='coerce')
    # Match Session._load_telemetry: offset uses raw dates, samples use ms dates.
    out['Date'] = pd.to_datetime(out['Date']).dt.round('ms')
    out = out.dropna().drop_duplicates('Date').sort_values('Date')
    if out.empty:
        raise NoData('Telemetry is unavailable for the selected driver.')
    out.attrs['t0_date'] = offset
    return out


def _decode_driver_car(api_path, driver_number, start=None, end=None, pad_seconds=1.0):
    return _decode_driver_stream(api_path, driver_number, 'car_data', start, end, pad_seconds)


def _decode_driver_position(api_path, driver_number, start=None, end=None, pad_seconds=1.0):
    return _decode_driver_stream(api_path, driver_number, 'position', start, end, pad_seconds)


@st.cache_data(ttl=3600, max_entries=1, show_spinner=False)
def fastest_telemetry(year, round_number, name, driver):
    """Low-memory fastest-lap speed map inputs.

    Instead of Session.load(telemetry=True), which materialises telemetry for the
    full field, parse only the selected driver's car/position samples around the
    selected lap and interpolate positions onto the car-data timestamps.
    """
    snapshot = session_snapshot(year, round_number, name)
    d = personal_bests(snapshot['data'])
    d = d.loc[d.Driver.eq(driver)]
    if d.empty:
        raise NoData('This driver has no valid timed lap in the selected session.')
    best = d.sort_values('LapTimeSeconds').iloc[0]
    start = _naive_utc(best.get('LapStartDate'))
    seconds = float(best.LapTimeSeconds)
    if not np.isfinite(seconds) or seconds <= 0:
        raise NoData('The fastest lap has no usable lap duration for telemetry slicing.')
    relative_start = pd.to_timedelta(best.get('LapStartTime'), errors='coerce')
    if pd.isna(start) and pd.isna(relative_start):
        raise NoData('The fastest lap has no usable start timing for telemetry slicing.')
    end = start + pd.Timedelta(seconds=seconds) if pd.notna(start) else None
    driver_number = best.get('DriverNumber')
    if pd.isna(driver_number) or str(driver_number).strip() in ('', 'nan', 'None'):
        results = snapshot['results']
        if {'Abbreviation', 'DriverNumber'}.issubset(results.columns):
            matches = results.loc[results.Abbreviation.eq(driver), 'DriverNumber'].dropna()
            if not matches.empty:
                driver_number = matches.iloc[0]
    if pd.isna(driver_number) or str(driver_number).strip() in ('', 'nan', 'None'):
        raise NoData('The selected driver’s timing number is unavailable for telemetry lookup.')

    try:
        car = _decode_driver_car(snapshot['api_path'], driver_number, start if pd.notna(start) else None, end)
        pos = _decode_driver_position(snapshot['api_path'], driver_number, start if pd.notna(start) else None, end)
        if pd.isna(start):
            offsets = [frame.attrs.get('t0_date') for frame in (car, pos)]
            offsets = [value for value in offsets if value is not None and pd.notna(value)]
            if not offsets:
                raise NoData('Telemetry has no usable session timestamp offset.')
            start = max(offsets).round('ms') + relative_start
            end = start + pd.Timedelta(seconds=seconds)
        # Keep only original car samples from the timed lap itself. Position is
        # interpolated by timestamp between the surrounding official samples.
        car = car.loc[car.Date.between(start, end)].copy()
        pos = pos.loc[pos.Date.between(start - pd.Timedelta(seconds=1),
                                       end + pd.Timedelta(seconds=1))].copy()
        if len(car) < 3 or len(pos) < 3:
            raise NoData('There are too few telemetry samples to draw this lap.')
        target = car.Date.astype('int64').to_numpy(dtype=np.int64)
        ptime = pos.Date.astype('int64').to_numpy(dtype=np.int64)
        inside = (target >= ptime.min()) & (target <= ptime.max())
        car = car.loc[inside].copy()
        target = target[inside]
        if len(target) < 3:
            raise NoData('There are too few overlapping car/position samples to draw this lap.')
        tel = pd.DataFrame({
            'Date': car.Date.to_numpy(),
            'Time': (car.Date - start).to_numpy(),
            'Speed': pd.to_numeric(car.Speed, errors='coerce').to_numpy(dtype=float),
            'X': np.interp(target, ptime, pd.to_numeric(pos.X, errors='coerce').to_numpy(dtype=float)),
            'Y': np.interp(target, ptime, pd.to_numeric(pos.Y, errors='coerce').to_numpy(dtype=float)),
        })
        tel.loc[tel.Speed.lt(0), 'Speed'] = np.nan
        tel['Driver'] = driver
        tel['LapNumber'] = int(best.LapNumber)
        if len(tel.dropna(subset=['X', 'Y', 'Speed'])) < 3:
            raise NoData('There are too few valid telemetry samples to draw this lap.')
        return tel, seconds, int(best.LapNumber)
    except NoData:
        raise
    except Exception as exc:
        log.exception('Telemetry unavailable for %s', driver)
        raise NoData('Speed/position telemetry is unavailable for this driver’s fastest valid lap. '
                     'Try another driver or session. Timing charts can still be used.') from exc
    finally:
        _release_memory('building selected-driver telemetry')


@st.cache_data(ttl=3600, max_entries=1, show_spinner=False)
def reported_positions(year, round_number, name):
    snapshot = session_snapshot(year, round_number, name)
    raw = None
    try:
        # Deliberately isolated private API dependency, pinned to FastF1 3.8.3.
        from fastf1 import _api
        raw = _api.fetch_page(snapshot['api_path'], 'timing_data')
        if not raw:
            raise NoData('The reported position feed is unavailable. No timestamp-derived substitute will be plotted.')
        roster_rows = snapshot['results']
        if not {'DriverNumber', 'Abbreviation'}.issubset(roster_rows.columns):
            raise NoData('Driver-number mapping is unavailable for the reported position feed.')
        mapping = dict(zip(roster_rows.DriverNumber.astype(str), roster_rows.Abbreviation))
        out = position_observations(raw, mapping)
        original = snapshot['data'][['Driver', 'LapNumber', 'Position']].rename(
            columns={'Position': 'FastF1DerivedPosition'})
        original = original.drop_duplicates(['Driver', 'LapNumber'], keep=False)
        return out.merge(original, on=['Driver', 'LapNumber'], how='left', validate='one_to_one')
    except NoData:
        raise
    except Exception as exc:
        log.exception('Reported position feed unavailable')
        raise NoData('Reported race positions could not be loaded. No timestamp-derived substitute will be plotted; try refreshing or another session.') from exc
    finally:
        raw = None
        _release_memory('reported position feed')


def roster(results, d):
    result = pd.DataFrame(results)
    ordered = result.Abbreviation.dropna().tolist() if 'Abbreviation' in result else []
    ordered = list(dict.fromkeys([x for x in ordered if x] + d.Driver.dropna().tolist()))
    labels = {x: x for x in ordered}
    if {'Abbreviation', 'FullName'}.issubset(result):
        for _, row in result.iterrows():
            if row.Abbreviation in labels and pd.notna(row.FullName):
                labels[row.Abbreviation] = f'{row.FullName} ({row.Abbreviation})'
    return ordered, labels


def precache_weekend(year, round_number, session_names):
    """Warm FastF1's disk cache one timing-only session at a time."""
    # Do not populate session_snapshot here: this control is for the on-disk
    # FastF1 cache and should not increase Streamlit's retained memory.
    session_snapshot.clear()
    fastest_telemetry.clear()
    reported_positions.clear()
    report = []
    for session_name in session_names:
        session = None
        try:
            session = fastf1.get_session(year, round_number, session_name)
            session.load(telemetry=False, weather=False, messages=True)
            if session.laps.empty:
                raise NoData('No lap data is available.')
            report.append({'session': session_name, 'status': 'cached'})
        except Exception as exc:
            log.exception('Weekend pre-cache failed: %s %s %s', year, round_number, session_name)
            report.append({'session': session_name, 'status': 'failed', 'error': str(exc)})
        finally:
            session = None
            _release_memory(f'pre-caching {session_name}')
    return report

