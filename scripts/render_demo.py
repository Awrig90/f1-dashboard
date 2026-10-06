"""Render all nine analyses using explicit synthetic fixtures; no network calls."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import matplotlib.pyplot as plt
from f1dash.catalog import ANALYSES
from f1dash.demo import demo_session,demo_telemetry
from f1dash.processing import normalize,csv_bytes
from f1dash.charts import generate,png_bytes

out=Path('demo-exports'); out.mkdir(exist_ok=True)
d=normalize(demo_session().laps)
for analysis in ANALYSES:
    session='Race' if analysis.key in ('positions','strategy') else 'Practice 1'
    result=generate(analysis.key,d,{'year':2024,'event':'SYNTHETIC DEMONSTRATION','session':session},
                    drivers=['NOR'] if analysis.selector=='driver' else None,
                    telemetry=demo_telemetry('NOR') if analysis.key=='speed' else None,
                    positions=d[['Driver','LapNumber','Position']] if analysis.key=='positions' else None)
    for name,fig in result.figures.items():
        (out/f'SYNTHETIC-{name}.png').write_bytes(png_bytes(fig)); plt.close(fig)
    for name,table in result.tables.items():
        (out/f'SYNTHETIC-{analysis.key}-{name}.csv').write_bytes(csv_bytes(table))
    print('OK',analysis.label)
print('Exports:',out.resolve())
