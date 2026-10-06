import numpy as np
import pandas as pd
import pytest
from f1dash import processing as p
from f1dash.catalog import available,event_sessions,seasons
from f1dash.demo import demo_session

@pytest.fixture
def laps():
    return p.normalize(demo_session().laps)

def test_hidden_fastest_remains_benchmark(laps):
    whole = p.fastest(laps)
    winner = whole.iloc[0]
    other = whole.Driver.iloc[-1]
    filtered = p.fastest(laps,[other]).iloc[0]
    assert filtered.BenchmarkDriver == winner.Driver
    assert filtered.DeltaSeconds == pytest.approx(filtered.LapTimeSeconds-winner.LapTimeSeconds)
    assert filtered.DeltaSeconds > 0

def test_invalid_fastest_cannot_win(laps):
    laps.loc[0,['LapTimeSeconds','Deleted']] = [1,True]
    laps.loc[1,['LapTimeSeconds','FastF1Generated']] = [2,True]
    assert p.fastest(laps).LapTimeSeconds.min() > 80

def test_representative_excludes_pits_flags_and_invalid(laps):
    q = p.representative(laps)
    assert q.PitInTime.isna().all() and q.PitOutTime.isna().all()
    assert q.TrackStatus.eq('1').all()
    assert not q.Deleted.any()
    assert not q.LapNumber.isin([1,7,12,13]).any()
    assert 7 in p.representative(laps,p.FilterOptions(green_only=False)).LapNumber.values

def test_quick_laps_per_driver_and_compound(laps):
    wet = laps.loc[(laps.Driver=='NOR') & laps.LapNumber.isin([2,3])].copy()
    wet['Compound'] = 'WET'; wet['LapTimeSeconds'] = [140,145]
    q = pd.concat([laps,wet],ignore_index=True)
    assert len(p.representative(q).query("Compound=='WET'"))==2

def test_quick_cutoff_can_be_disabled(laps):
    laps.loc[2,'LapTimeSeconds'] = 160
    assert not (p.representative(laps).LapTimeSeconds==160).any()
    assert (p.representative(laps,p.FilterOptions(quick=False)).LapTimeSeconds==160).any()

def test_counts_distinguish_pace_and_usage(laps):
    table = p.compound_usage(laps)
    nor = table[table.Driver=='NOR']
    assert nor.LapsCompleted.sum()==24
    assert nor.ValidLaps.sum()==23
    assert nor.RepresentativeLaps.sum()<23
    subset=p.compound_usage(laps,['HAM'])
    assert subset.BenchmarkSeconds.iloc[0]==p.fastest(laps).BenchmarkSeconds.iloc[0]

def test_sectors_sum_personal_bests_not_session_mix(laps):
    table=p.sector_performance(laps,['NOR','VER'])
    assert np.allclose(table.TheoreticalSeconds,table[[f'Sector{i}TimeSeconds' for i in (1,2,3)]].sum(axis=1))
    assert table.PotentialSeconds.ge(-.003).all()
    assert set(table.Driver)=={'NOR','VER'}

def test_missing_sectors_graceful(laps):
    laps['Sector2TimeSeconds']=np.nan
    with pytest.raises(p.NoData): p.sector_performance(laps)

def test_missing_laps_do_not_shift_stints(laps):
    laps=laps.loc[~laps.LapNumber.eq(5)]
    table=p.stint_table(laps,['NOR'])
    assert table.StartLap.tolist()==[1,13]
    assert table.RecordedLaps.tolist()==[11,12]

def test_empty_selection_not_all(laps):
    with pytest.raises(p.NoData): p.fastest(laps,[])

def test_empty_session():
    with pytest.raises(p.NoData): p.fastest(p.normalize(pd.DataFrame()))

def test_export_numeric_timedelta(laps):
    text=p.csv_bytes(laps).decode('utf-8-sig')
    assert 'LapTime_seconds' in text
    assert '0 days' not in text

def test_formats_and_compatibility():
    event={'Session1':'Practice 1','Session2':'Sprint Shootout','Session3':'Sprint',
           'Session4':'Qualifying','Session5':'Race','Session1Date':'ignore'}
    assert event_sessions(event)==['Practice 1','Sprint Shootout','Sprint','Qualifying','Race']
    for name in ('Practice 1','Qualifying','Sprint Qualifying','Sprint Shootout'):
        keys={a.key for a in available(name)}
        assert 'fastest' in keys and 'sectors' in keys
        assert 'positions' not in keys and 'strategy' not in keys
    assert 'compounds' in {a.key for a in available('Practice 3')}
    for name in ('Race','Sprint'):
        keys={a.key for a in available(name)}
        assert {'positions','strategy','laps','drivers','teams','speed'}<=keys
        assert 'fastest' not in keys
    assert available('Unknown')==[]
    assert min(seasons())==2018 and len(seasons())>1

def test_compound_usage_survives_no_valid_laps(laps):
    laps['Deleted']=True
    table=p.compound_usage(laps)
    assert table.LapsCompleted.sum()==len(laps)
    assert table.ValidLaps.eq(0).all()
    assert table.FastestSeconds.isna().all()
