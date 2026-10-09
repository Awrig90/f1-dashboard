"""Opt-in real-data validation and Linux process peak RSS measurement.

Run each mode in a fresh process against the same F1_CACHE_DIR:
  python scripts/validate_loading.py --mode baseline --offline --output validation
  python scripts/validate_loading.py --mode snapshot --offline --output validation
  python scripts/validate_loading.py --mode reference --offline --output validation
  python scripts/validate_loading.py --mode compare --output validation
Offline uses previously downloaded official FastF1 data, never demo fixtures.
"""
import argparse
import json
from pathlib import Path
import platform
import resource
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fastf1
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from f1dash.data import _load_snapshot, fastest_telemetry, current_rss_mb, _release_memory
from f1dash.processing import normalize, retention_table
from f1dash.charts import generate, png_bytes


def peak():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 ** 2 if sys.platform == 'darwin' else 1024)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['baseline', 'snapshot', 'reference', 'compare'], required=True)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('validation'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.offline_mode(args.offline)
    report = {'mode': args.mode, 'source': 'cached official data' if args.offline else 'FastF1 network/cache',
              'python': platform.python_version(), 'fastf1': fastf1.__version__, 'platform': platform.platform(),
              'baseline_rss_mib': current_rss_mb(), 'stages': {}}
    if args.mode in ('baseline', 'snapshot'):
        for year, rnd, name in [(2024, 1, 'Practice 2'), (2024, 1, 'Qualifying'), (2024, 1, 'Race'), (2024, 5, 'Sprint')]:
            if args.mode == 'baseline':
                session = fastf1.get_session(year, rnd, name)
                session.load(telemetry=False, weather=False, messages=False)
                d = normalize(session.laps)
                del session
            else:
                snapshot = _load_snapshot(year, rnd, name)
                d = snapshot['data']
            key = f'{year}-{rnd}-{name}'
            retention = retention_table(d)
            report['stages'][key] = {'rows': len(d), 'unknown_deleted': int(d.Deleted.isna().sum()),
                'deleted': int(d.Deleted.fillna(False).sum()), 'lap_start_dates': int(d.LapStartDate.notna().sum()),
                'retention': retention.sum(numeric_only=True).to_dict(), 'peak_rss_mib': peak(), 'rss_mib': current_rss_mb()}
            retention.to_csv(args.output / f'{args.mode}-{key}-retention.csv', index=False)
            if args.mode == 'snapshot':
                result = generate('drivers', d, {'year': year, 'event': 'Bahrain' if rnd == 1 else 'China', 'session': name})
                for fig in result.figures.values():
                    png_bytes(fig, dpi=300)
                    plt.close(fig)
                del result
                _release_memory()
                report['stages'][key]['after_render_peak_rss_mib'] = peak()
            print(key, report['stages'][key], flush=True)
        if args.mode == 'snapshot':
            telemetry, seconds, lap = fastest_telemetry(2024, 1, 'Qualifying', 'VER')
            telemetry.to_csv(args.output / 'selective-telemetry.csv', index=False)
            report['telemetry'] = {'samples': len(telemetry), 'lap': lap, 'seconds': seconds, 'peak_rss_mib': peak()}
            result = generate('speed', d, {'year': 2024, 'event': 'Bahrain', 'session': 'Qualifying'}, drivers=['VER'], telemetry=(telemetry, seconds, lap))
            for key, fig in result.figures.items():
                (args.output / f'{key}.png').write_bytes(png_bytes(fig, dpi=300))
                plt.close(fig)
            report['telemetry']['after_render_peak_rss_mib'] = peak()
    elif args.mode == 'reference':
        session = fastf1.get_session(2024, 1, 'Qualifying')
        session.load(telemetry=True, weather=False, messages=True)
        lap = session.laps.pick_drivers('VER').pick_fastest()
        lap.get_car_data().to_csv(args.output / 'reference-car.csv', index=False)
        lap.get_pos_data().to_csv(args.output / 'reference-position.csv', index=False)
        lap.get_telemetry().to_csv(args.output / 'reference-telemetry.csv', index=False)
        report['telemetry'] = {'lap': int(lap.LapNumber), 'seconds': lap.LapTime.total_seconds(),
            'start': str(lap.LapStartDate), 't0_date': str(session.t0_date), 'peak_rss_mib': peak()}
    else:
        report['source'] = 'comparison of saved real-data outputs'
        lean = pd.read_csv(args.output / 'selective-telemetry.csv', parse_dates=['Date'])
        car = pd.read_csv(args.output / 'reference-car.csv', parse_dates=['Date'])
        pos = pd.read_csv(args.output / 'reference-position.csv', parse_dates=['Date'])
        full = pd.read_csv(args.output / 'reference-telemetry.csv', parse_dates=['Date'])
        ref_report = json.loads((args.output / 'reference.json').read_text())['telemetry']
        lean_report = json.loads((args.output / 'snapshot.json').read_text())['telemetry']
        assert ref_report['lap'] == lean_report['lap'] and ref_report['seconds'] == lean_report['seconds']
        joined = lean.merge(car[['Date', 'Speed']], on='Date', suffixes=('_lean', '_reference'), validate='one_to_one')
        assert len(joined) == len(lean)
        speed_error = (joined.Speed_lean - joined.Speed_reference).abs().max()
        assert speed_error == 0
        start = pd.Timestamp(ref_report['start'])
        clock_error = ((lean.Date - pd.to_timedelta(lean.Time)) - start).dt.total_seconds().abs().max()
        assert clock_error <= 0.001
        # Compare independent linear interpolation of native position samples.
        inside = lean.Date.between(pos.Date.min(), pos.Date.max())
        assert int(inside.sum()) >= len(lean) - 2
        coordinate_errors = {}
        for axis in ('X', 'Y'):
            target = lean.loc[inside, 'Date'].astype('int64')
            expected = np.interp(target, pos.Date.astype('int64'), pos[axis])
            error = float(np.max(np.abs(lean.loc[inside, axis] - expected)))
            coordinate_errors[axis] = error
            assert error < 1e-6
        # Native get_telemetry merges/interpolates more channels and timestamps;
        # do not claim equal row counts or identical cubic-vs-linear positions.
        overlap = lean.merge(full[['Date', 'X', 'Y']], on='Date', suffixes=('_lean', '_native'))
        distances = np.hypot(overlap.X_lean - overlap.X_native, overlap.Y_lean - overlap.Y_native)
        report['comparison'] = {'samples': len(lean), 'native_merged_samples': len(full),
            'speed_max_error_kmh': float(speed_error), 'start_max_error_seconds': float(clock_error),
            'linear_position_compared_samples': int(inside.sum()),
            'linear_position_max_errors_source_units': coordinate_errors,
            'native_position_overlap': len(overlap), 'native_position_distance_median_source_units': float(np.median(distances)),
            'native_position_distance_max_source_units': float(np.max(distances))}
    report['peak_rss_mib'] = peak()
    (args.output / f'{args.mode}.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
