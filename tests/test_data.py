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

    base.load.assert_called_once_with(telemetry=False, weather=False, messages=True)
    assert set(snap) == {'data', 'results', 'styles', 'api_path', 'unknown_deleted_laps'}
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
    a.load.assert_called_once_with(telemetry=False, weather=False, messages=True)
    b.load.assert_called_once_with(telemetry=False, weather=False, messages=True)



def test_timing_only_snapshot_requires_messages_for_non_pb_validity():
    from f1dash.processing import valid_laps
    base = demo_session('Race')
    base.laps['Deleted'] = pd.NA
    base.laps['IsPersonalBest'] = False
    base.api_path = '/static/test/'
    def load(**kwargs):
        if kwargs.get('messages'):
            base.laps['Deleted'] = False
            base.laps.loc[0, 'Deleted'] = True
    base.load = load
    with patch('f1dash.data.fastf1.get_session', return_value=base), \
         patch('f1dash.data._style_maps', return_value={}):
        snap = session_snapshot.__wrapped__(2024, 1, 'Race')
    assert snap['unknown_deleted_laps'] == 0
    assert len(valid_laps(snap['data'])) == len(base.laps) - 1


def test_telemetry_recovers_absolute_start_without_full_session():
    raw = demo_session().laps.iloc[[1]].copy()
    raw['DriverNumber'] = '4'
    raw['LapStartTime'] = pd.Timedelta(seconds=10)
    raw['LapTime'] = pd.Timedelta(seconds=2)
    data = normalize(raw)
    assert data.LapStartDate.isna().all()
    zero = pd.Timestamp('2024-01-01')
    dates = zero + pd.to_timedelta([9, 10, 11, 12, 13], unit='s')
    car = pd.DataFrame({'Date': dates, 'Speed': [100, 200, 210, 220, 100]})
    pos = pd.DataFrame({'Date': dates, 'X': [0, 1, 2, 3, 4], 'Y': [4, 3, 2, 1, 0]})
    car.attrs['t0_date'] = zero - pd.Timedelta(milliseconds=50)
    pos.attrs['t0_date'] = zero  # later offset across BOTH streams wins
    snap = {'data': data, 'results': pd.DataFrame(), 'api_path': '/test/'}
    with patch('f1dash.data.session_snapshot', return_value=snap), \
         patch('f1dash.data._decode_driver_car', return_value=car), \
         patch('f1dash.data._decode_driver_position', return_value=pos):
        tel, seconds, lap = fastest_telemetry.__wrapped__(2024, 1, 'Qualifying', 'NOR')
    assert seconds == 2 and lap == 2
    assert tel.Speed.tolist() == [200, 210, 220]
    assert tel.Time.dt.total_seconds().tolist() == [0, 1, 2]


@pytest.mark.parametrize('stream', ['car_data', 'position'])
def test_raw_stream_offset_includes_later_other_driver_packet(stream):
    import base64, json, zlib
    from f1dash.data import _decode_driver_stream
    def record(clock, utc, driver, speed):
        fields = {'Channels': {'0': 10000, '2': speed, '3': 7, '4': 100, '5': 0}} if stream == 'car_data' else {'X': speed, 'Y': 2, 'Z': 0}
        entry = {'Utc': utc, 'Cars': {driver: fields}} if stream == 'car_data' else {'Timestamp': utc, 'Entries': {driver: fields}}
        payload = {'Entries' if stream == 'car_data' else 'Position': [entry]}
        compressor = zlib.compressobj(wbits=-15)
        zipped = compressor.compress(json.dumps(payload).encode()) + compressor.flush()
        return clock + json.dumps(base64.b64encode(zipped).decode())
    records = [record('00:00:01.000', '2024-01-01T00:00:01.000400Z', '4', 200),
               record('00:00:02.000', '2024-01-01T00:00:02.100Z', '1', 300)]
    with patch('fastf1._api.fetch_page', return_value=records):
        out = _decode_driver_stream('/test/', '4', stream)
    assert len(out) == 1
    assert out.Date.iloc[0] == pd.Timestamp('2024-01-01T00:00:01.000')
    assert out.attrs['t0_date'] == pd.Timestamp('2024-01-01T00:00:00.100')
    assert out.iloc[0]['Speed' if stream == 'car_data' else 'X'] == 200
