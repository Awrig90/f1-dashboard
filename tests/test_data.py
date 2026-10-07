from unittest.mock import MagicMock, patch
import pandas as pd
import pytest
from f1dash.data import schedule, session_data, fastest_telemetry, precache_weekend, clear_session_cache
from f1dash.processing import NoData
from f1dash.demo import demo_session


def setup_function():
    clear_session_cache()


def teardown_function():
    clear_session_cache()


def test_api_failure_is_explained():
    schedule.clear()
    with patch('f1dash.data.fastf1.get_event_schedule',side_effect=RuntimeError('private details')):
        with pytest.raises(NoData,match='schedule could not be loaded'):
            schedule.__wrapped__(2024)


def test_session_failure_is_explained():
    with patch('f1dash.data.fastf1.get_session',side_effect=RuntimeError('raw exception')):
        with pytest.raises(NoData,match='Session data could not be loaded'):
            session_data(2024,1,'Race')


def test_same_session_is_reused_and_switch_releases_previous():
    first = demo_session('Race')
    second = demo_session('Qualifying')
    with patch('f1dash.data._load_new_session',side_effect=[first, second]) as load:
        assert session_data(2026,1,'Race') is first
        assert session_data(2026,1,'Race') is first
        assert session_data(2026,1,'Qualifying') is second
    assert load.call_count == 2


def test_missing_telemetry_is_explained():
    with patch('f1dash.data.session_data',return_value=demo_session()):
        with pytest.raises(NoData,match='telemetry is unavailable'):
            fastest_telemetry.__wrapped__(2024,1,'Qualifying','NOR')


def test_precache_weekend_is_disk_only_and_sequential():
    a = demo_session('Practice 1')
    b = demo_session('Qualifying')
    with patch('f1dash.data._load_new_session',side_effect=[a,b]) as load:
        report = precache_weekend(2026,1,['Practice 1','Qualifying'])
    assert [x['status'] for x in report] == ['cached','cached']
    assert load.call_count == 2
    load.assert_any_call(2026,1,'Practice 1',telemetry=False)
    load.assert_any_call(2026,1,'Qualifying',telemetry=False)
