from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from f1dash.data import schedule, session_snapshot, fastest_telemetry, precache_weekend
from f1dash.processing import NoData, normalize
from f1dash.demo import demo_session


def test_api_failure_is_explained():
    schedule.clear()
    with patch('f1dash.data.fastf1.get_event_schedule', side_effect=RuntimeError('private details')):
        with pytest.raises(NoData, match='schedule could not be loaded'):
            schedule.__wrapped__(2024)


def test_session_failure_is_explained():
    session_snapshot.clear()
    with patch('f1dash.data.fastf1.get_session', side_effect=RuntimeError('raw exception')):
        with pytest.raises(NoData, match='Session data could not be loaded'):
            session_snapshot.__wrapped__(2024, 1, 'Race')


def test_snapshot_keeps_lean_data_not_full_session():
    base = demo_session('Race')
    base.laps['DriverNumber'] = base.laps['Driver'].map(
        {'NOR': '4', 'PIA': '81', 'VER': '1', 'RUS': '63', 'LEC': '16', 'HAM': '44'})
    base.laps['LapStartDate'] = pd.Timestamp('2026-01-01') + base.laps['Time'] - base.laps['LapTime']
    base.results['DriverNumber'] = base.results['Abbreviation'].map(
        {'NOR': '4', 'PIA': '81', 'VER': '1', 'RUS': '63', 'LEC': '16', 'HAM': '44'})
    base.api_path = '/static/test/'
    base.load = MagicMock()

    with patch('f1dash.data.fastf1.get_session', return_value=base), \
         patch('f1dash.data._style_maps', return_value={'driver': {}, 'team': {}}):
        snap = session_snapshot.__wrapped__(2026, 1, 'Race')

    base.load.assert_called_once_with(telemetry=False, weather=False, messages=False)
    assert set(snap) == {'data', 'results', 'styles', 'api_path'}
    assert 'LapTimeSeconds' in snap['data']
    assert 'LapStartDate' in snap['data']
    assert snap['api_path'] == '/static/test/'
    # The snapshot deliberately contains no Session object.
    assert all(not hasattr(value, 'load') for value in snap.values())


def test_fastest_telemetry_uses_selected_driver_only():
    raw = demo_session('Qualifying').laps.copy()
    raw['DriverNumber'] = raw['Driver'].map(
        {'NOR': '4', 'PIA': '81', 'VER': '1', 'RUS': '63', 'LEC': '16', 'HAM': '44'})
    raw['LapStartDate'] = pd.Timestamp('2026-01-01') + raw['Time'] - raw['LapTime']
    data = normalize(raw)
    results = pd.DataFrame({'Abbreviation': ['NOR'], 'DriverNumber': ['4']})
    snap = {'data': data, 'results': results, 'styles': {}, 'api_path': '/static/test/'}
    best = data.loc[data.Driver.eq('NOR') & data.IsPersonalBest.fillna(False)].sort_values('LapTimeSeconds').iloc[0]
    start = pd.Timestamp(best.LapStartDate)
    car = pd.DataFrame({
        'Date': start + pd.to_timedelta([0.0, 0.5, 1.0, 1.5], unit='s'),
        'Speed': [200, 210, 220, 230],
    })
    pos = pd.DataFrame({
        'Date': start + pd.to_timedelta([0.0, 0.75, 1.5], unit='s'),
        'X': [0.0, 10.0, 20.0],
        'Y': [0.0, 5.0, 10.0],
    })
    with patch('f1dash.data.session_snapshot', return_value=snap), \
         patch('f1dash.data._decode_driver_car', return_value=car) as car_decode, \
         patch('f1dash.data._decode_driver_position', return_value=pos) as pos_decode:
        tel, seconds, lap = fastest_telemetry.__wrapped__(2026, 1, 'Qualifying', 'NOR')
    assert len(tel) >= 3
    assert {'X', 'Y', 'Speed', 'Time'}.issubset(tel.columns)
    assert np.isfinite(tel[['X', 'Y', 'Speed']].to_numpy()).all()
    assert seconds > 0 and lap > 0
    assert car_decode.call_args.args[1] == '4'
    assert pos_decode.call_args.args[1] == '4'


def test_precache_weekend_is_disk_only_and_sequential():
    a = demo_session('Practice 1')
    b = demo_session('Qualifying')
    for item in (a, b):
        item.load = MagicMock()
    with patch('f1dash.data.fastf1.get_session', side_effect=[a, b]) as get_session:
        report = precache_weekend(2026, 1, ['Practice 1', 'Qualifying'])
    assert [x['status'] for x in report] == ['cached', 'cached']
    assert get_session.call_count == 2
    a.load.assert_called_once_with(telemetry=False, weather=False, messages=False)
    b.load.assert_called_once_with(telemetry=False, weather=False, messages=False)
