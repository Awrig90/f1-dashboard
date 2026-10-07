"""Opt-in live integration check. Exits nonzero if an offered analysis fails."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import matplotlib.pyplot as plt
from f1dash.catalog import available
from f1dash.data import session_snapshot, fastest_telemetry, reported_positions, roster, schedule
from f1dash.processing import csv_bytes
from f1dash.charts import generate, png_bytes

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--year',type=int,default=2024)
parser.add_argument('--round',type=int,default=1)
parser.add_argument('--session',default='Qualifying',help='Full session name, e.g. "Practice 2"')
parser.add_argument('--telemetry',action='store_true',help='Also download and check speed map telemetry')
parser.add_argument('--output',type=Path,default=Path('live-exports'))
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)

snapshot=session_snapshot(args.year,args.round,args.session)
d=snapshot['data']
events=schedule(args.year)
event_row=events.loc[events.RoundNumber.eq(args.round)].iloc[0]
context={'year':args.year,'event':event_row.EventName,'session':args.session}
all_drivers,_=roster(snapshot['results'],d)
report={}
for analysis in available(args.session):
    if analysis.key=='speed' and not args.telemetry:
        report[analysis.key]={'skipped':'Use --telemetry to download telemetry.'}; continue
    try:
        drivers=[all_drivers[0]] if analysis.selector=='driver' else all_drivers
        telemetry=fastest_telemetry(args.year,args.round,args.session,drivers[0]) if analysis.key=='speed' else None
        positions=reported_positions(args.year,args.round,args.session) if analysis.key=='positions' else None
        result=generate(analysis.key,d,context,drivers=drivers,telemetry=telemetry,positions=positions,
                        styles=snapshot.get('styles'))
        for name,fig in result.figures.items():
            (args.output/f'{name}.png').write_bytes(png_bytes(fig)); plt.close(fig)
        for name,table in result.tables.items():
            (args.output/f'{analysis.key}-{name}.csv').write_bytes(csv_bytes(table))
        report[analysis.key]={'rows':{name:len(table) for name,table in result.tables.items()}}
        print('PASS',analysis.label)
    except Exception as exc:
        report[analysis.key]={'error':str(exc)}
        print('FAIL',analysis.label,str(exc),file=sys.stderr)
(args.output/'report.json').write_text(json.dumps({'context':context,'results':report},indent=2),encoding='utf-8')
sys.exit(1 if any('error' in result for result in report.values()) else 0)
