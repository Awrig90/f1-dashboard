"""Pure pandas transformations. Times exported in seconds; source laps are never mutated."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

class NoData(ValueError):
    """Expected unavailable/insufficient data, safe to explain to a user."""

@dataclass(frozen=True)
class FilterOptions:
    quick: bool = True
    threshold: float = 1.07
    green_only: bool = True

TIME_COLUMNS = ('LapTime', 'Sector1Time', 'Sector2Time', 'Sector3Time')
LAP_SOURCE_COLUMNS = (
    'Driver', 'DriverNumber', 'Team', 'Compound', 'LapNumber', 'Stint', 'Position',
    'LapTime', 'Sector1Time', 'Sector2Time', 'Sector3Time', 'LapStartDate',
    'PitInTime', 'PitOutTime', 'Time', 'IsPersonalBest', 'Deleted',
    'FastF1Generated', 'IsAccurate', 'TrackStatus'
)

def normalize(laps):
    # Convert FastF1's extended Laps frame to a plain, deliberately narrow
    # DataFrame. Retaining every FastF1 column needlessly increases RAM on the
    # hosted dashboard and can preserve metadata references to the source.
    source = pd.DataFrame(laps)
    keep = [col for col in LAP_SOURCE_COLUMNS if col in source.columns]
    d = source.loc[:, keep].copy().reset_index(drop=True)
    for col in TIME_COLUMNS:
        d[col + 'Seconds'] = (pd.to_timedelta(d[col], errors='coerce').dt.total_seconds()
                                  if col in d else np.nan)
    defaults = {'Driver': None, 'DriverNumber': None, 'Team': 'Unknown', 'Compound': 'UNKNOWN',
                'LapNumber': np.nan, 'Stint': np.nan, 'Position': np.nan,
                'LapStartDate': pd.NaT, 'PitInTime': pd.NaT, 'PitOutTime': pd.NaT,
                'Time': pd.NaT, 'IsPersonalBest': False,
                'Deleted': pd.NA, 'FastF1Generated': False, 'IsAccurate': False,
                'TrackStatus': ''}
    for col, value in defaults.items():
        if col not in d:
            d[col] = value
    for col in ('Deleted', 'IsPersonalBest', 'FastF1Generated', 'IsAccurate'):
        d[col] = d[col].astype('boolean')
    for col in ('Compound', 'Team'):
        d[col] = d[col].fillna(defaults[col]).replace('', defaults[col])
    d['Compound'] = d.Compound.astype(str).str.strip().str.upper().replace('', 'UNKNOWN')
    d = d.dropna(subset=['Driver']).drop_duplicates().reset_index(drop=True)
    d['DuplicateLapConflict'] = d.duplicated(['Driver', 'LapNumber'], keep=False)
    return d

def observed_laps(d):
    """No arbitrary first-row selection when two different records claim one lap."""
    return d.loc[~d.DuplicateLapConflict & d.LapNumber.gt(0)
                 & d.LapNumber.mod(1).eq(0)
                 & ~d.FastF1Generated.fillna(False).astype(bool)].copy()

def valid_laps(d):
    # Valid recorded lap is not synonymous with IsAccurate (a stricter timing check).
    q = observed_laps(d)
    # Unknown deletion status is not evidence of sporting validity. A PB flag
    # provides positive evidence for that individual lap, unless explicitly deleted.
    known_valid = q.Deleted.eq(False).fillna(False) | (
        q.Deleted.isna() & q.IsPersonalBest.fillna(False).astype(bool))
    return q.loc[(q.LapTimeSeconds > 0) & np.isfinite(q.LapTimeSeconds)
                 & known_valid].copy()

def personal_bests(d):
    """Match tutorial pick_fastest(): only laps flagged as personal best qualify."""
    q = valid_laps(d)
    return q.loc[q.IsPersonalBest.fillna(False).astype(bool)].copy()

def representative(d, options=FilterOptions()):
    q = valid_laps(d)
    q = q.loc[q.IsAccurate.fillna(False).astype(bool)
              & q.PitInTime.isna() & q.PitOutTime.isna()].copy()
    if options.green_only:
        q = q.loc[q.TrackStatus.astype(str).eq('1')].copy()
    if options.quick and not q.empty:
        best = q.groupby(['Driver', 'Compound']).LapTimeSeconds.transform('min')
        q = q.loc[q.LapTimeSeconds <= best * options.threshold].copy()
    return q

def selected(d, drivers=None, teams=None):
    if drivers is not None:
        d = d.loc[d.Driver.isin(drivers)]
    if teams is not None:
        d = d.loc[d.Team.isin(teams)]
    return d.copy()

def require(d, message='No usable laps remain. Try another session or relax the lap filters.'):
    if d.empty:
        raise NoData(message)
    return d

def fastest(d, drivers=None):
    v = require(personal_bests(d), 'No confirmed personal-best laps are available. Timing or validity metadata may be incomplete.')
    benchmark = v.loc[v.LapTimeSeconds.idxmin()]
    out = v.sort_values('LapTimeSeconds', kind='stable').drop_duplicates('Driver').copy()
    out['DeltaSeconds'] = out.LapTimeSeconds - benchmark.LapTimeSeconds
    out['BenchmarkDriver'] = benchmark.Driver
    out['BenchmarkSeconds'] = benchmark.LapTimeSeconds
    return require(selected(out, drivers), 'The selected drivers have no valid timed laps.')

def summary(q, group='Driver'):
    return q.groupby(group).agg(RepresentativeLaps=('LapTimeSeconds', 'size'),
                               MedianSeconds=('LapTimeSeconds', 'median'),
                               FastestSeconds=('LapTimeSeconds', 'min')).reset_index().sort_values('MedianSeconds')

def compound_usage(d, drivers=None, options=FilterOptions()):
    # Count completed, recorded laps (including pit/slow/deleted laps), not synthetic rows.
    completed = observed_laps(d)
    # A completed outlap can have a lap-end timestamp but no measured LapTime.
    completed = completed.loc[completed.Time.notna() | completed.LapTimeSeconds.gt(0)]
    counts = completed.groupby(['Driver', 'Compound']).agg(LapsCompleted=('LapNumber', 'nunique'))
    v = valid_laps(d)
    pb = personal_bests(d)
    best = pb.loc[pb.LapTimeSeconds.idxmin()] if not pb.empty else None
    pace = v.groupby(['Driver', 'Compound']).agg(ValidLaps=('LapTimeSeconds', 'size'),
                                              FastestSeconds=('LapTimeSeconds', 'min'))
    rep = representative(d, options).groupby(['Driver', 'Compound']).agg(
        RepresentativeLaps=('LapTimeSeconds', 'size'), MedianSeconds=('LapTimeSeconds', 'median'))
    out = counts.join(pace, how='outer').join(rep, how='outer').reset_index()
    for c in ['LapsCompleted', 'ValidLaps', 'RepresentativeLaps']:
        out[c] = out[c].fillna(0).astype(int)
    out['DeltaToSessionBestSeconds'] = out.FastestSeconds - (best.LapTimeSeconds if best is not None else np.nan)
    out['BenchmarkDriver'] = best.Driver if best is not None else None
    out['BenchmarkSeconds'] = best.LapTimeSeconds if best is not None else np.nan
    return require(selected(out, drivers))

def sector_performance(d, drivers=None):
    v = valid_laps(d)
    actual = personal_bests(d).groupby('Driver').LapTimeSeconds.min().rename('ActualFastestSeconds')
    cols = [f'Sector{i}TimeSeconds' for i in (1,2,3)]
    # Consistent complete, accurate, non-pit laps: avoids invented theoretical times.
    eligible = v.loc[v.IsAccurate.fillna(False).astype(bool) & v.PitInTime.isna()
                     & v.PitOutTime.isna() & v[cols].gt(0).all(axis=1)
                     & np.isfinite(v[cols]).all(axis=1)
                     & (v[cols].sum(axis=1)-v.LapTimeSeconds).abs().le(.0030001)]
    out = eligible.groupby('Driver')[cols].min()
    for i, col in enumerate(cols, 1):
        source = eligible.sort_values([col, 'LapNumber'], kind='stable').drop_duplicates('Driver').set_index('Driver')
        out[f'Sector{i}SourceLap'] = source.LapNumber
        out[f'Sector{i}Compound'] = source.Compound
    out['TheoreticalSeconds'] = out[cols].sum(axis=1)
    out = out.join(actual).reset_index()
    actual_sources = personal_bests(d).sort_values('LapTimeSeconds', kind='stable').drop_duplicates('Driver').set_index('Driver')
    out['ActualFastestSourceLap'] = out.Driver.map(actual_sources.LapNumber)
    out['EligibleSectorLaps'] = out.Driver.map(eligible.groupby('Driver').size())
    out['PotentialSeconds'] = out.ActualFastestSeconds - out.TheoreticalSeconds
    # An actual fastest lap may lack consistent sectors. Never claim negative potential.
    out['TimingConsistent'] = out.PotentialSeconds.ge(-0.003)
    out.loc[~out.TimingConsistent, 'PotentialSeconds'] = np.nan
    out.loc[out.TimingConsistent, 'PotentialSeconds'] = out.loc[out.TimingConsistent, 'PotentialSeconds'].clip(lower=0)
    return require(selected(out, drivers).sort_values('TheoreticalSeconds'),
                   'No selected driver has complete, accurate sector timing on a valid non-pit lap.')

def stint_table(d, drivers=None):
    q = require(selected(observed_laps(d), drivers)).sort_values(['Driver', 'LapNumber']).copy()
    q['Stint'] = q.Stint.fillna(-1)
    # Repeated unknown stint IDs and compound changes must not merge disjoint runs.
    boundary = q.Driver.ne(q.Driver.shift()) | q.Stint.ne(q.Stint.shift()) | q.Compound.ne(q.Compound.shift())
    boundary |= q.Stint.eq(-1) & q.LapNumber.diff().ne(1)
    q['Segment'] = boundary.cumsum()
    out = q.groupby(['Driver', 'Stint', 'Compound', 'Segment'], dropna=False, sort=False).agg(
        StartLap=('LapNumber','min'), EndLap=('LapNumber','max'),
        RecordedLaps=('LapNumber','nunique')).reset_index()
    out['MissingLapsWithinSpan'] = out.EndLap-out.StartLap+1-out.RecordedLaps
    return require(out)

def retention_table(d, options=FilterOptions()):
    """Auditable denominators; stages are nested, not overlapping reasons."""
    stages = [('SourceRows', d), ('UnambiguousObservedLaps', observed_laps(d)),
              ('ValidTimedLaps', valid_laps(d)),
              ('AccurateNonPitLaps', representative(d, FilterOptions(False, options.threshold, False))),
              ('BeforeQuickCutoff', representative(d, FilterOptions(False, options.threshold, options.green_only))),
              ('RepresentativeLaps', representative(d, options))]
    out = pd.DataFrame(index=sorted(d.Driver.unique()))
    for name, rows in stages:
        out[name] = rows.groupby('Driver').size()
    return out.fillna(0).astype(int).rename_axis('Driver').reset_index()

def position_observations(raw, driver_map):
    """Reported timing position at each driver lap-count increment, NOT a time rank.

    Retain the actual message timestamp and timestamp of last position update.
    Never extrapolate retired drivers or backfill missing lap counts/positions.
    """
    state, rows = {}, []
    for timestamp, packet in raw:
        time = pd.to_timedelta(timestamp)
        for number, update in packet.get('Lines', {}).items():
            if str(number) not in driver_map or not isinstance(update, dict):
                continue
            entry = state.setdefault(str(number), {'laps': 0, 'position': np.nan, 'position_time': pd.NaT})
            if 'Position' in update:
                entry['position'] = pd.to_numeric(update['Position'], errors='coerce')
                entry['position_time'] = time
            count = pd.to_numeric(update.get('NumberOfLaps'), errors='coerce')
            if pd.notna(count) and count > entry['laps'] and float(count).is_integer():
                entry['laps'] = count
                rows.append({'Driver': driver_map[str(number)], 'DriverNumber': str(number),
                             'LapNumber': int(count), 'Position': entry['position'],
                             'ObservationTime': time, 'PositionUpdateTime': entry['position_time'],
                             'PositionSource': 'TimingData.Position at NumberOfLaps increment'})
            elif pd.notna(count) and count < entry['laps']:
                # A counter reset makes previously emitted lap identities ambiguous.
                raise NoData('The timing feed resets lap numbering. Position history cannot be safely assembled for this session.')
    out = pd.DataFrame(rows)
    require(out, 'No reported lap-count/position observations are available.')
    out.loc[~out.Position.between(1, len(driver_map)) | out.Position.mod(1).ne(0), 'Position'] = np.nan
    return out

def csv_bytes(df):
    out = df.copy()
    for col in out:
        if pd.api.types.is_timedelta64_dtype(out[col]):
            out[col] = out[col].dt.total_seconds()
            out = out.rename(columns={col: col + '_seconds'})
    return out.to_csv(index=False, float_format='%.6f').encode('utf-8-sig')
