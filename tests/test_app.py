"""Streamlit's real runtime, with deterministic data boundaries (no network required)."""
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from f1dash.demo import demo_session,demo_telemetry
from f1dash.processing import NoData

APP = str(Path(__file__).resolve().parents[1]/'app.py')
EVENTS=pd.DataFrame([{'RoundNumber':1,'EventName':'Test Grand Prix','F1ApiSupport':True,
                     'Session1':'Practice 1','Session2':'Sprint Shootout','Session3':'Sprint',
                     'Session4':'Qualifying','Session5':'Race'}])

def selector(app,label):
    return next(w for w in app.selectbox if w.label==label)

def button(app,label):
    return next(w for w in app.button if w.label==label)

def test_workflow_all_analyses_and_stale_results():
    with patch('f1dash.data.schedule',return_value=EVENTS), \
         patch('f1dash.data.session_data',return_value=demo_session()), \
         patch('f1dash.data.reported_positions',return_value=demo_session().laps[['Driver','LapNumber','Position']]), \
         patch('f1dash.data.fastest_telemetry',return_value=demo_telemetry('NOR')):
        at=AppTest.from_file(APP,default_timeout=30).run()
        assert not at.exception
        for name,keys in [('Practice 1',['fastest','laps','drivers','teams','speed','compounds','sectors']),
                          ('Race',['positions','strategy'])]:
            selector(at,'Session').set_value(name).run()
            for key in keys:
                selector(at,'Visualisation').set_value(key).run()
                button(at,'Generate chart').click().run()
                assert not at.exception, at.exception
                assert not at.error, [e.value for e in at.error]
                assert len(at.get('imgs'))>0 or 'output' in at.session_state
                assert at.session_state.output['tables']
                assert len(at.get('download_button'))>=3
        selector(at,'Session').set_value('Qualifying').run()
        assert len(at.get('download_button'))==0
        assert 'Position Tracker' not in selector(at,'Visualisation').options

def test_schedule_failure_human_readable():
    with patch('f1dash.data.schedule',side_effect=NoData('Schedule unavailable')):
        at=AppTest.from_file(APP).run()
        assert not at.exception
        assert any('Schedule unavailable' in x.value for x in at.info)
        at.toggle[0].set_value(True).run()
        assert not at.exception
        button(at,'Generate chart').click().run()
        assert at.session_state.output['metadata']['synthetic'] is True
