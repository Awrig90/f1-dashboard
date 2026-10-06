"""Clearly labelled synthetic fixtures for offline inspection and deterministic tests."""
from types import SimpleNamespace
import numpy as np
import pandas as pd

def demo_session(name='Practice 1'):
    rows = []
    drivers = [('NOR','McLaren'),('PIA','McLaren'),('VER','Red Bull Racing'),
               ('RUS','Mercedes'),('LEC','Ferrari'),('HAM','Ferrari')]
    for i,(driver,team) in enumerate(drivers):
        for lap in range(1,25):
            compound = 'MEDIUM' if lap<=12 else 'SOFT'
            seconds = 89+i*.22 + (lap%6)*.14 + (0.7 if compound=='MEDIUM' else 0)
            pit = lap in (1,12,13)
            if pit: seconds+=16
            rows.append(dict(Driver=driver,Team=team,LapNumber=lap,LapTime=pd.Timedelta(seconds=seconds),
                             Sector1Time=pd.Timedelta(seconds=seconds*.31),
                             Sector2Time=pd.Timedelta(seconds=seconds*.40),
                             Sector3Time=pd.Timedelta(seconds=seconds*.29),
                             Compound=compound,Stint=1 if lap<=12 else 2,
                             Position=((i+(1 if 8<=lap<=12 else 0))%6)+1,
                             Time=pd.Timedelta(seconds=lap*110), IsPersonalBest=True,
                             IsAccurate=True,Deleted=(i==0 and lap==18),FastF1Generated=False,
                             PitInTime=pd.Timedelta(seconds=lap*90) if lap==12 else pd.NaT,
                             PitOutTime=pd.Timedelta(seconds=lap*90) if lap in (1,13) else pd.NaT,
                             TrackStatus='4' if lap==7 else '1'))
    results = pd.DataFrame([dict(Abbreviation=d,FullName={'NOR':'Lando Norris','PIA':'Oscar Piastri',
                'VER':'Max Verstappen','RUS':'George Russell','LEC':'Charles Leclerc','HAM':'Lewis Hamilton'}[d],
                TeamName=t) for d,t in drivers])
    return SimpleNamespace(laps=pd.DataFrame(rows),results=results,name=name)

def demo_telemetry(driver):
    t=np.linspace(0,2*np.pi,400)
    tel=pd.DataFrame({'X':1000*np.cos(t)*(1+.15*np.sin(3*t)),
                      'Y':650*np.sin(t),'Speed':210+80*np.sin(2*t),
                      'Time':pd.to_timedelta(np.linspace(0,90,400),unit='s'),
                      'Driver':driver,'LapNumber':24})
    return tel,90.,24
