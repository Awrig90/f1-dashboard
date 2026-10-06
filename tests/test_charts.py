import matplotlib.pyplot as plt
import pytest
from f1dash.catalog import ANALYSES
from f1dash.demo import demo_session,demo_telemetry
from f1dash.processing import normalize,csv_bytes
from f1dash.charts import generate,png_bytes

@pytest.mark.parametrize('analysis',ANALYSES,ids=lambda a:a.key)
def test_all_charts_export(analysis):
    d=normalize(demo_session().laps)
    drivers=['NOR'] if analysis.selector=='driver' else list(d.Driver.unique())
    r=generate(analysis.key,d,{'year':2024,'event':'Synthetic test','session':'Practice 1'},
               drivers=drivers,telemetry=demo_telemetry('NOR') if analysis.key=='speed' else None,
               positions=d[['Driver','LapNumber','Position']] if analysis.key=='positions' else None)
    assert r.figures and r.tables
    for fig in r.figures.values():
        assert png_bytes(fig).startswith(b'\x89PNG')
        plt.close(fig)
    for table in r.tables.values(): assert len(csv_bytes(table))>10

def test_sparse_distribution_renders_points():
    d=normalize(demo_session().laps)
    d=d.loc[d.LapNumber.isin([2,3])]
    r=generate('drivers',d,{'year':2024,'event':'Synthetic test','session':'Qualifying'})
    assert any('Fewer than five' in n for n in r.notes)
    assert r.tables['summary'].RepresentativeLaps.eq(2).all()
    for fig in r.figures.values(): plt.close(fig)
