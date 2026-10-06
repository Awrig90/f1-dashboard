from unittest.mock import patch
import pandas as pd
import pytest
from f1dash.data import schedule,session_data,fastest_telemetry
from f1dash.processing import NoData
from f1dash.demo import demo_session

def test_api_failure_is_explained():
    with patch('f1dash.data.fastf1.get_event_schedule',side_effect=RuntimeError('private details')):
        with pytest.raises(NoData,match='schedule could not be loaded'):
            schedule.__wrapped__(2024)

def test_session_failure_is_explained():
    with patch('f1dash.data.fastf1.get_session',side_effect=RuntimeError('raw exception')):
        with pytest.raises(NoData,match='Session data could not be loaded'):
            session_data.__wrapped__(2024,1,'Race')

def test_missing_telemetry_is_explained():
    with patch('f1dash.data.session_data',return_value=demo_session()):
        with pytest.raises(NoData,match='telemetry is unavailable'):
            fastest_telemetry.__wrapped__(2024,1,'Qualifying','NOR')
