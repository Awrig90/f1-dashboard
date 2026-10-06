"""Frozen real-source extracts. No API/network access required for these checks."""
import json
from pathlib import Path
import pandas as pd
import numpy as np
from f1dash import processing as p

FIXTURES=Path(__file__).parent/'fixtures'

def test_all_twenty_spanish_qualifying_times_match_supplied_tutorial():
    raw=pd.read_csv(FIXTURES/'spain2021-qualifying.csv')
    out=p.fastest(p.normalize(raw))
    expected=[('HAM',76.741),('VER',76.777),('BOT',76.873),('LEC',77.510),
              ('OCO',77.580),('SAI',77.620),('RIC',77.622),('PER',77.669),
              ('NOR',77.696),('ALO',77.966),('STR',77.974),('GAS',77.982),
              ('VET',78.079),('GIO',78.356),('RUS',78.445),('TSU',78.556),
              ('RAI',78.917),('MSC',79.117),('LAT',79.219),('MAZ',79.807)]
    assert out.Driver.tolist()==[d for d,t in expected]
    assert np.allclose(out.LapTimeSeconds,[t for d,t in expected],atol=1e-9)
    assert np.allclose(out.DeltaSeconds,[t-76.741 for d,t in expected],atol=1e-9)

def test_real_bahrain_feed_leclerc_finishes_fourth():
    fixture=json.loads((FIXTURES/'bahrain2026-position-feed.json').read_text())
    out=p.position_observations(fixture['messages'],fixture['driver_map'])
    lec=out.query("Driver=='LEC'")
    assert lec.iloc[-1].LapNumber==55
    assert lec.iloc[-1].Position==4
    # Preserve observed numbering. Do not make lap 2 match a wished-for answer.
    assert out.query("Driver=='VER' and LapNumber==2").Position.item()==6
    assert out.query("Driver=='ANT' and LapNumber==2").Position.item()==8
    assert out.query("Driver=='VER' and LapNumber==3").Position.item()==3
    assert out.query("Driver=='ANT' and LapNumber==3").Position.item()==1
