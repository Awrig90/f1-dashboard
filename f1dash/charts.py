"""Publication-size Matplotlib figures plus exportable analysis tables."""
from dataclasses import dataclass, field
from io import BytesIO
from threading import RLock
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
from . import processing as p
from .catalog import session_kind

PLOT_LOCK = RLock()  # Matplotlib global state is not thread safe.
COMPOUNDS = {'SOFT':'#ef4444','MEDIUM':'#edc949','HARD':'#d7dce2',
             'INTERMEDIATE':'#31aa63','WET':'#397fce','UNKNOWN':'#8b91a0'}

@dataclass
class Result:
    figures: dict = field(default_factory=dict)
    tables: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

class Styling:
    def __init__(self, session=None, style_maps=None):
        self.session = session
        self.style_maps = style_maps or {'driver': {}, 'team': {}}
    def color(self, identifier, kind='driver'):
        if kind == 'compound':
            return COMPOUNDS.get(identifier, '#8b91a0')
        if kind == 'driver':
            style = self.style_maps.get('driver', {}).get(identifier)
            if isinstance(style, dict) and style.get('color'):
                return style['color']
        if kind == 'team':
            color = self.style_maps.get('team', {}).get(identifier)
            if color:
                return color
        if self.session is not None:
            try:
                import fastf1.plotting as fp
                return getattr(fp, f'get_{kind}_color')(identifier, session=self.session)
            except (KeyError, ValueError, TypeError, AttributeError):
                pass
        # Deterministic fallback for unknown/new driver/team identities.
        return plt.get_cmap('tab20')(sum(map(ord, str(identifier))) % 20)
    def driver(self, identifier):
        style = self.style_maps.get('driver', {}).get(identifier)
        if isinstance(style, dict) and style.get('color'):
            return {'color': style['color'], 'linestyle': style.get('linestyle') or '-'}
        if self.session is not None:
            try:
                import fastf1.plotting as fp
                return fp.get_driver_style(identifier=identifier, style=['color','linestyle'], session=self.session)
            except (KeyError, ValueError, TypeError, AttributeError):
                pass
        return {'color':self.color(identifier), 'linestyle':'-'}

def new_chart(title, height=6, columns=1):
    fig, axes = plt.subplots(1, columns, figsize=(12, height), squeeze=False)
    fig.patch.set_facecolor('white')
    fig._data_source = 'Synthetic demonstration data' if 'SYNTHETIC' in title else 'FastF1'
    fig.suptitle(title, x=.075, ha='left', fontsize=15, fontweight='bold')
    for ax in axes[0]:
        ax.set_facecolor('white')
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='x', alpha=.16)
        ax.set_axisbelow(True)
    return fig, axes[0]

def finish(fig, footnote):
    fig.text(.075, .018, 'Source: ' + fig._data_source + '  •  ' + footnote, fontsize=8, color='#4c5768')
    fig.tight_layout(rect=(0,.055,1,.94))
    return fig

def apply_chart_text(fig, chart_text):
    """Apply user-facing text overrides without changing analytical content."""
    if not chart_text:
        return fig
    title = chart_text.get('title', '').strip()
    subtitle = chart_text.get('subtitle', '').strip()
    if title or subtitle:
        text = title + (('\n' + subtitle) if subtitle else '')
        if getattr(fig, '_suptitle', None) is not None:
            fig._suptitle.set_text(text)
        else:
            fig.suptitle(text, x=.075, ha='left', fontsize=15, fontweight='bold')
    axes = [ax for ax in fig.axes if ax.get_label() != '<colorbar>']
    if axes:
        if chart_text.get('x_label', '').strip():
            axes[0].set_xlabel(chart_text['x_label'].strip())
        if chart_text.get('y_label', '').strip():
            axes[0].set_ylabel(chart_text['y_label'].strip())
    return fig

def lap_label(seconds):
    return f'{int(seconds//60)}:{seconds%60:06.3f}'

def generate(key, d, context, drivers=None, teams=None, options=p.FilterOptions(),
             session=None, telemetry=None, positions=None, chart_text=None, styles=None):
    """context requires year, event, session; filters never modify benchmark population."""
    title = f"{context['year']} {context['event']} · {context['session']}"
    style = Styling(session, styles)
    r = Result()
    conflicts = int(d.DuplicateLapConflict.sum())
    if conflicts:
        r.notes.append(f'{conflicts} conflicting driver/lap records were excluded rather than choosing an arbitrary row.')
    if key == 'fastest':
        table = p.fastest(d, drivers)
        first = table.iloc[0]
        fig, (ax,) = new_chart(title+'\nSession fastest laps', max(5, len(table)*.32+2))
        ys = np.arange(len(table))
        ax.barh(ys, table.DeltaSeconds, color=[style.color(x) for x in table.Driver])
        for y, row in zip(ys, table.itertuples()):
            ax.annotate(f'+{row.DeltaSeconds:.3f}  |  {lap_label(row.LapTimeSeconds)}',
                        (row.DeltaSeconds,y), xytext=(6,0), textcoords='offset points', va='center', fontsize=9)
        ax.set_yticks(ys, table.Driver); ax.invert_yaxis()
        ax.set_xlim(0, max(.5,table.DeltaSeconds.max())*1.4+.3)
        ax.set_xlabel(f'Delta to session best: {first.BenchmarkDriver} {lap_label(first.BenchmarkSeconds)} (s)')
        r.figures['fastest-laps'] = finish(fig, 'All session phases combined; benchmark includes hidden drivers.')
        r.tables['fastest-laps'] = table[['Driver','Team','LapNumber','Compound','LapTimeSeconds','DeltaSeconds','BenchmarkDriver','BenchmarkSeconds','IsPersonalBest','Deleted','IsAccurate']]
        r.notes.append('This ranks fastest recorded valid laps across the session, not official qualifying classification. Track evolution and run plans affect comparisons.')
    elif key in ('laps','drivers','teams'):
        q = p.require(p.selected(p.representative(d, options), drivers, teams))
        r.tables['representative-laps'] = q
        if key == 'laps':
            if q.Driver.nunique() != 1:
                raise p.NoData('Choose exactly one driver for Driver Lap Times.')
            fig, (ax,) = new_chart(title+f'\n{q.Driver.iloc[0]} · representative lap times')
            for compound, group in q.groupby('Compound'):
                ax.scatter(group.LapNumber, group.LapTimeSeconds, label=compound,
                           color=style.color(compound,'compound'), edgecolors='#354052', linewidths=.5, s=45)
            ax.set(xlabel='Lap number', ylabel='Lap time (s)'); ax.legend(title='Compound')
        else:
            group_col = 'Team' if key == 'teams' else 'Driver'
            metrics = p.summary(q, group_col)
            r.tables['summary'] = metrics
            r.tables['summary-by-compound'] = q.groupby([group_col, 'Compound']).agg(
                RepresentativeLaps=('LapTimeSeconds','size'), MedianSeconds=('LapTimeSeconds','median'),
                FastestSeconds=('LapTimeSeconds','min')).reset_index()
            fig, (ax,) = new_chart(title+'\n'+('Team' if key == 'teams' else 'Driver')+' lap-time distribution', max(5,len(metrics)*.4+2))
            sparse = []
            for i, row in enumerate(metrics.itertuples(index=False)):
                group = getattr(row, group_col)
                values = q.loc[q[group_col].eq(group),'LapTimeSeconds'].to_numpy()
                color = style.color(group,'team' if key == 'teams' else 'driver')
                if len(values) >= 5:
                    bp = ax.boxplot([values], positions=[i], vert=False, widths=.5,
                                    patch_artist=True, showfliers=False, manage_ticks=False)
                    bp['boxes'][0].set(facecolor=color, alpha=.4)
                    for line in bp['medians']: line.set(color='#111827')
                else:
                    sparse.append(str(group))
                # Deterministic jitter; every representative lap is visible.
                ax.scatter(values, i+np.linspace(-.12,.12,len(values)), s=15, color=color, edgecolor='#555', linewidths=.25)
            ax.set_yticks(range(len(metrics)), [f'{x}  (n={n})' for x,n in zip(metrics[group_col], metrics.RepresentativeLaps)])
            ax.invert_yaxis(); ax.set_xlabel('Representative lap time (s)')
            if sparse:
                r.notes.append('Fewer than five representative laps: '+', '.join(sparse)+'. Individual observations are shown without a distribution box.')
            r.notes.append('Ordered by median of retained laps. Compounds, conditions, run plans, fuel and traffic are not controlled. Pooled team laps weight drivers by their retained lap counts.')
        r.figures[key] = finish(fig, filter_caption(options))
    elif key == 'positions':
        if positions is None:
            raise p.NoData('Reported race positions are unavailable. Timestamp-derived positions are not used as a fallback.')
        q = p.require(p.selected(positions, drivers).dropna(subset=['LapNumber','Position']))
        q = p.require(q.loc[q.Position.ge(1)])
        fig, (ax,) = new_chart(title+'\nPosition by lap')
        for driver, group in q.groupby('Driver', sort=False):
            group = group.sort_values('LapNumber')
            # NaNs at missing lap numbers avoid drawing fictitious continuous coverage.
            line = group.set_index('LapNumber').Position.reindex(range(int(group.LapNumber.min()),int(group.LapNumber.max())+1))
            ax.plot(line.index,line.values,label=driver,linewidth=1.8,**style.driver(driver))
        maximum = int(q.Position.max())
        ax.set_yticks(range(1,maximum+1)); ax.set_ylim(maximum+.5,.5)
        ax.set(xlabel='Completed lap number (timing feed)',ylabel='Reported position at lap-count update')
        ax.legend(bbox_to_anchor=(1.01,1),loc='upper left',fontsize=8,ncol=2 if q.Driver.nunique()>12 else 1)
        r.figures[key] = finish(fig,'Reported at each driver’s lap-count update; not a synchronous field snapshot or final classification.')
        r.tables[key] = q
        r.notes.append('Uses TimingData.Position at each driver’s NumberOfLaps increment, not ranks of lap timestamps. Feed updates can lag the timing line. Formation/delayed starts retain feed lap numbering. Missing observations remain gaps; DNFs stop at their last reported lap. Do not interpret this as a synchronous leaderboard or FIA lap chart.')
        if 'FastF1DerivedPosition' in q:
            differences = q.Position.ne(q.FastF1DerivedPosition) & q.FastF1DerivedPosition.notna()
            r.notes.append(f'{int(differences.sum())} displayed observations differ from FastF1’s timestamp-derived position. Both values are exported for audit; no final-result position has been forced onto the history.')
    elif key == 'strategy':
        table = p.stint_table(d, drivers)
        order = [x for x in (drivers if drivers is not None else d.Driver.unique()) if x in set(table.Driver)]
        fig, (ax,) = new_chart(title+'\nTyre strategy',max(5,len(order)*.34+2))
        # Draw recorded lap slots at their real positions; missing laps remain gaps.
        q = p.selected(p.observed_laps(d),drivers)
        for i, driver in enumerate(order):
            g = q.loc[q.Driver.eq(driver)].sort_values('LapNumber')
            for row in g.itertuples():
                ax.barh(i,1,left=row.LapNumber-.5,color=style.color(row.Compound,'compound'),height=.7)
            for row in table.loc[table.Driver.eq(driver)].itertuples():
                ax.vlines(row.StartLap-.5,i-.35,i+.35,color='#303846',linewidth=1)
                if row.RecordedLaps>=3:
                    ax.text((row.StartLap+row.EndLap)/2,i,str(row.RecordedLaps),ha='center',va='center',fontsize=8,color='#111827')
        ax.set_yticks(range(len(order)),order); ax.invert_yaxis(); ax.set_xlabel('Lap number')
        compound_legend(ax,q.Compound.unique(),style)
        r.figures[key] = finish(fig,'Labels: recorded laps per stint. Gaps indicate missing observations.')
        r.tables['stints'] = table
    elif key == 'compounds':
        table = p.compound_usage(d,drivers,options)
        usage = table.pivot(index='Driver',columns='Compound',values='LapsCompleted').fillna(0)
        fig, (ax,) = new_chart(title+'\nPractice compound usage',max(5,len(usage)*.33+2))
        left = np.zeros(len(usage))
        for compound in usage.columns:
            values = usage[compound].to_numpy()
            ax.barh(usage.index,values,left=left,color=style.color(compound,'compound'),label=compound,edgecolor='#fff',linewidth=.4)
            for i,n in enumerate(values):
                if n>=2: ax.text(left[i]+n/2,i,str(int(n)),ha='center',va='center',fontsize=8)
            left += values
        ax.invert_yaxis(); ax.set_xlabel('Completed recorded laps (includes pit and slow laps)')
        compound_legend(ax,usage.columns,style)
        r.figures[key] = finish(fig,'Completed recorded laps include untimed outlaps; pace metrics use separate filters.\n' + scope_caption(options))
        r.tables['compound-performance'] = table.sort_values(['Driver','FastestSeconds'])
        r.notes.append('Usage includes recorded lap completions even when LapTime is missing. FastestSeconds uses known-valid timed laps; MedianSeconds uses representative laps. Deltas reference the full-session confirmed personal best, across all compounds. Unknown deletion status is not silently accepted.')
    elif key == 'sectors':
        table = p.sector_performance(d,drivers)
        cols = [f'Sector{i}TimeSeconds' for i in (1,2,3)]
        fig, axes = new_chart(title+'\nPersonal-best sectors & theoretical lap',max(5,len(table)*.36+2),2)
        ax, bx = axes; y = np.arange(len(table)); left = np.zeros(len(table))
        # Relative sector losses use the selected drivers' individual sector minima.
        for col,color,label in zip(cols,['#3274A1','#e6a23c','#59a98c'],['Sector 1','Sector 2','Sector 3']):
            loss = table[col]-table[col].min()
            ax.barh(y,loss,left=left,label=label,color=color); left+=loss.to_numpy()
            table[label.replace(' ','')+'LossSeconds'] = loss
        ax.set_yticks(y,table.Driver); ax.invert_yaxis()
        ax.set_xlabel('Sector losses vs best selected sector (s)'); ax.legend(fontsize=8)
        bx.scatter(table.TheoreticalSeconds,y,label='Theoretical',marker='D',color='#3274a1',zorder=3)
        bx.scatter(table.ActualFastestSeconds,y,label='Actual fastest',marker='o',color='#e65555',zorder=3)
        bx.hlines(y,table.TheoreticalSeconds,table.ActualFastestSeconds,color='#89919e')
        bx.set_yticks(y,table.Driver); bx.invert_yaxis(); bx.set_xlabel('Lap time (s)'); bx.legend(fontsize=8)
        r.figures[key] = finish(fig,'Sectors can come from different laps and conditions; theoretical time is not a prediction.')
        r.tables['sector-performance'] = table
        r.notes.append('Sorted by theoretical time. Sector-loss references use the selected drivers; actual fastest laps are reported separately. Only complete, accurate, valid non-pit laps supply personal-best sectors.')
        if not table.TimingConsistent.all():
            r.notes.append('Some fastest laps have inconsistent/incomplete sector coverage. PotentialSeconds is blank where it would misleadingly be negative.')
    elif key == 'speed':
        if telemetry is None:
            raise p.NoData('Speed and position telemetry is unavailable for this lap.')
        tel, seconds, lap = telemetry
        driver = drivers[0]
        fig,(ax,) = new_chart(title+f'\n{driver} · lap {lap} · {lap_label(seconds)} · speed',7)
        tel = tel.copy()
        points = tel[['X','Y']].to_numpy().reshape(-1,1,2)
        segments = np.concatenate([points[:-1],points[1:]],axis=1)
        speeds = tel.Speed.to_numpy()
        usable = np.isfinite(segments).all(axis=(1,2)) & np.isfinite(speeds[:-1]) & np.isfinite(speeds[1:])
        if 'Time' in tel:
            gaps = pd.to_timedelta(tel.Time).diff().dt.total_seconds().to_numpy()[1:]
            usable &= (gaps > 0) & (gaps <= 2)
        if usable.sum() < 2:
            plt.close(fig)
            raise p.NoData('Telemetry has too few continuous valid samples to draw a reliable map.')
        segment_speeds = ((speeds[:-1]+speeds[1:])/2)[usable]
        lc = LineCollection(segments[usable],cmap='plasma',norm=plt.Normalize(segment_speeds.min(),segment_speeds.max()),linewidth=4)
        lc.set_array(segment_speeds)
        ax.add_collection(LineCollection(segments[usable],color='#d1d5db',linewidth=7,zorder=0))
        ax.add_collection(lc); ax.autoscale(); ax.set_aspect('equal'); ax.axis('off')
        fig.colorbar(lc,ax=ax,orientation='horizontal',pad=.04,shrink=.7,label='Speed (km/h)')
        r.figures[key] = finish(fig,'Fastest valid lap for the selected driver; sampled/interpolated telemetry.')
        r.tables['telemetry'] = tel
    else:
        raise ValueError(f'Unknown analysis: {key}')
    if key in ('laps','drivers','teams','compounds'):
        r.tables['filter-retention'] = p.selected(p.retention_table(d, options), drivers)
        r.notes.append(filter_caption(options)+'. Accurate, non-deleted, non-generated, non-pit laps only for representative pace.')
        if {'INTERMEDIATE','WET'} & set(d.Compound):
            r.notes.append('Wet running is present. Pooled distributions/medians mix conditions and are not a like-for-like pace ranking; inspect compound-specific samples and filter-retention counts. A driver/compound quick cutoff can still remove early wet laps as a track dries.')
    for fig in r.figures.values():
        apply_chart_text(fig, chart_text)
    return r

def filter_caption(options):
    speed = f'≤ {options.threshold*100:.0f}% of driver/compound best' if options.quick else 'No quick-lap cutoff'
    flags = 'green track only' if options.green_only else 'green/yellow laps passing FastF1 accuracy checks'
    return speed+'; '+flags+'\n'+scope_caption(options)

def scope_caption(options):
    scope = 'All compounds' if options.compounds is None else 'Compounds: ' + ', '.join(options.compounds)
    laps = f'lap range {options.lap_min or 1}–{options.lap_max or "end"} (inclusive)'
    return scope+'; '+laps

def compound_legend(ax, compounds, style):
    ax.legend(handles=[Patch(facecolor=style.color(c,'compound'),edgecolor='#777',label=c) for c in compounds],
              bbox_to_anchor=(1.01,1),loc='upper left',fontsize=8)

def png_bytes(fig, dpi=300):
    """Render a figure to PNG bytes at the requested resolution.

    The dashboard renders its downloadable chart output at 300 dpi.
    """
    output = BytesIO()
    fig.savefig(output,format='png',dpi=dpi,facecolor='white')
    return output.getvalue()

