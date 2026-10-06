"""Data correctness assertions, not merely successful rendering."""
import numpy as np
import pandas as pd
import pytest
from f1dash import processing as p
from f1dash.demo import demo_session
from f1dash.charts import generate

def data():
    return p.normalize(demo_session().laps)

def test_fastest_requires_personal_best_flag():
    d=data()
    d.loc[0, ['LapTimeSeconds','IsPersonalBest']]=[1,False]
    assert p.fastest(d).LapTimeSeconds.min()>80

def test_unknown_deleted_does_not_become_known_valid():
    d=data()
    d.loc[0,['Deleted','IsPersonalBest']]=[pd.NA,False]
    assert 0 not in p.valid_laps(d).index

def test_untimed_completed_outlaps_count_for_usage_not_pace():
    d=data()
    d.loc[0,'LapTimeSeconds']=np.nan
    table=p.compound_usage(d,['NOR'])
    assert table.LapsCompleted.sum()==24
    assert table.ValidLaps.sum()==22

def test_conflicting_duplicates_are_not_arbitrarily_selected():
    raw=demo_session().laps
    bad=raw.iloc[[2]].copy()
    bad['LapTime']=pd.Timedelta(seconds=1)
    d=p.normalize(pd.concat([raw,bad],ignore_index=True))
    assert d.DuplicateLapConflict.sum()==2
    assert len(p.observed_laps(d))==len(raw)-1
    assert p.fastest(d).LapTimeSeconds.min()>80

def test_identical_duplicates_do_not_double_count():
    raw=demo_session().laps
    d=p.normalize(pd.concat([raw,raw.iloc[[2]]],ignore_index=True))
    assert len(d)==len(raw)
    assert not d.DuplicateLapConflict.any()

def test_sector_source_laps_reproduce_sector_values():
    d=data(); table=p.sector_performance(d)
    for row in table.itertuples():
        for i in (1,2,3):
            source=d[(d.Driver==row.Driver)&(d.LapNumber==getattr(row,f'Sector{i}SourceLap'))].iloc[0]
            assert source[f'Sector{i}TimeSeconds']==getattr(row,f'Sector{i}TimeSeconds')

def test_sector_sum_must_be_consistent_even_if_accuracy_flag_is_wrong():
    d=data(); d['Sector1TimeSeconds']=1
    with pytest.raises(p.NoData):p.sector_performance(d)

def test_unknown_stints_do_not_merge_separated_runs():
    d=data().query("Driver=='NOR'").copy()
    d['Stint']=np.nan;d['Compound']='SOFT'
    d=d[d.LapNumber!=10]
    table=p.stint_table(d)
    assert table.StartLap.tolist()==[1,11]
    assert table.RecordedLaps.tolist()==[9,14]

def test_position_source_is_feed_not_time_or_result_rank():
    raw=[('00:00:01',{'Lines':{'16':{'Position':'4'},'3':{'Position':'3'}}}),
         ('00:01:10',{'Lines':{'16':{'NumberOfLaps':1}}}),
         ('00:01:15',{'Lines':{'3':{'NumberOfLaps':1}}}),
         ('00:02:00',{'Lines':{'3':{'Position':'1','NumberOfLaps':2}}})]
    out=p.position_observations(raw,{'16':'LEC','3':'VER','12':'ANT','44':'HAM'})
    assert out.query("Driver=='LEC'").Position.tolist()==[4]
    assert out.query("Driver=='VER'").Position.tolist()==[3,1]
    assert out.query("Driver=='LEC'").LapNumber.max()==1  # no DNF extrapolation

def test_position_missing_lap_not_invented_and_missing_position_not_backfilled():
    raw=[('00:01:00',{'Lines':{'3':{'NumberOfLaps':1}}}),
         ('00:03:00',{'Lines':{'3':{'NumberOfLaps':3,'Position':'1'}}})]
    out=p.position_observations(raw,{'3':'VER'})
    assert out.LapNumber.tolist()==[1,3]
    assert pd.isna(out.iloc[0].Position)

def test_positions_fail_closed_without_feed():
    with pytest.raises(p.NoData):generate('positions',data(),{'year':2024,'event':'Test','session':'Race'})

def test_retention_stages_are_nested():
    table=p.retention_table(data()).drop(columns='Driver')
    assert (np.diff(table.to_numpy(),axis=1)<=0).all()
