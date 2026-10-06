"""Run with: python -m streamlit run app.py"""
from dataclasses import asdict
import json
import logging
import re
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from f1dash import catalog, processing as p
from f1dash.charts import generate, png_bytes, PLOT_LOCK
from f1dash.data import schedule, session_data, fastest_telemetry, reported_positions, roster, precache_weekend

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('f1dash')
st.set_page_config(page_title='F1 | Session Lab',page_icon='🏁',layout='wide')
st.markdown('''<style>
.block-container {padding-top:2rem;max-width:1500px;}
[data-testid="stMetric"] {background:#182332;padding:15px;border-radius:8px;}
</style>''',unsafe_allow_html=True)
st.caption('F1 / INTERNAL RESEARCH')
st.title('Session Lab')
st.write('Choose a session. Explore the laps. Export the evidence.')

def colleague_note(note: str) -> str:
    """Turn audit-oriented notes into concise colleague-facing context."""
    if 'Uses TimingData.Position' in note:
        return ("Positions come from the live timing feed at each driver's completed lap. "
                "Timing updates can occasionally arrive slightly late, so unusual starts, restarts "
                "or delayed timing updates may differ from other published lap charts.")
    if 'timestamp-derived position' in note:
        return ("FastF1 can also calculate lap positions from timing timestamps. This chart uses the "
                "live timing feed instead; both versions are kept in the exported data for checking.")
    if 'Wet running is present' in note:
        return ("Wet-weather running is included. Pace comparisons across changing conditions are not "
                "like-for-like, so use the compound and lap filters when comparing drivers or teams.")
    if 'Fewer than five representative laps' in note:
        return ("Distribution boxes are shown only when at least five representative laps remain. "
                "Drivers or teams with fewer laps are still shown as individual points.")
    if 'conflicting' in note.lower():
        return 'Some timing records conflict. The chart keeps the most defensible observations and the exported data preserves the detail for checking.'
    return note

def driver_checkbox_selector(all_drivers, labels, scope, defaults):
    """Compact whole-field selector with fast select/clear actions."""
    st.markdown('**Drivers**')
    checkbox_keys = {d: f'driver-check-{scope}-{d}' for d in all_drivers}
    default_set = set(defaults)
    for driver, key in checkbox_keys.items():
        if key not in st.session_state:
            st.session_state[key] = driver in default_set

    action_cols = st.columns([1, 1, 6])
    if action_cols[0].button('Select all', key='select-all-'+scope, use_container_width=True):
        for key in checkbox_keys.values():
            st.session_state[key] = True
    if action_cols[1].button('Select none', key='clear-all-'+scope, use_container_width=True):
        for key in checkbox_keys.values():
            st.session_state[key] = False

    columns = st.columns(4)
    selected = []
    for index, driver in enumerate(all_drivers):
        with columns[index % 4]:
            if st.checkbox(labels.get(driver, driver), key=checkbox_keys[driver]):
                selected.append(driver)
    return selected

def default_chart_text(analysis_key, context, drivers=None):
    """Human-editable defaults; axis labels remain plot-specific unless overridden."""
    title = f"{context['year']} {context['event']} · {context['session']}"
    driver = (drivers or [None])[0]
    subtitles = {
        'fastest': 'Session fastest laps',
        'laps': f'{driver} · representative lap times' if driver else 'Representative lap times',
        'drivers': 'Driver lap-time distribution',
        'teams': 'Team lap-time distribution',
        'positions': 'Position by lap',
        'strategy': 'Tyre strategy',
        'speed': f'{driver} · speed on track' if driver else 'Speed on track',
        'compounds': 'Practice compound usage',
        'sectors': 'Personal-best sectors & theoretical lap',
    }
    return {'title': title, 'subtitle': subtitles.get(analysis_key, '')}

def completed_sessions(event):
    """Sessions from the selected weekend whose scheduled UTC time has passed."""
    if event is None:
        return []
    now = pd.Timestamp.now(tz='UTC').tz_localize(None)
    names = []
    for i in range(1, 6):
        session_name = event.get(f'Session{i}')
        session_date = event.get(f'Session{i}DateUtc')
        if not isinstance(session_name, str) or not session_name.strip():
            continue
        if session_date is None or pd.isna(session_date):
            continue
        if pd.Timestamp(session_date).tz_localize(None) <= now:
            names.append(session_name)
    return list(dict.fromkeys(names))

with st.sidebar:
    st.subheader('Session workspace')
    demo = st.toggle('Offline demonstration',value=False,
                     help='Synthetic data for testing the interface. Never use for reporting.')
    if st.button('Refresh session data',help='Clear in-memory caches and refresh on the next load.'):
        st.cache_data.clear()
        st.session_state.pop('output',None)
    st.caption('FastF1 3.8.3 · Charts export at 300 dpi')
    st.caption('First loads may take several minutes. Later loads use a local disk cache.')

columns = st.columns([1,2,1.5])
year = columns[0].selectbox('Season',catalog.seasons(),key='year')
if demo:
    st.warning('OFFLINE DEMONSTRATION — synthetic laps and track shape; not real F1 results.')
    event_name = columns[1].selectbox('Grand Prix',['Demonstration Grand Prix'])
    round_number = 1
    session_names = ['Practice 1','Practice 2','Qualifying','Sprint Qualifying','Sprint','Race']
    event = None
else:
    try:
        with st.spinner('Loading event schedule…'):
            events = schedule(year)
        if events.empty:
            st.info('No Grand Prix schedule is available for this season.'); st.stop()
    except p.NoData as exc:
        st.info(str(exc)); st.caption('You can inspect all features using Offline demonstration in the sidebar.'); st.stop()
    rounds = [int(x) for x in events.RoundNumber]
    names = dict(zip(rounds,events.EventName))
    # Scope downstream widget state by upstream identity.
    round_number = columns[1].selectbox('Grand Prix',rounds,format_func=names.get,key=f'event-{year}')
    event = events.loc[events.RoundNumber.eq(round_number)].iloc[0]
    event_name = event.EventName
    session_names = catalog.event_sessions(event)
if not session_names:
    st.info('No sessions are listed for this event.'); st.stop()
name = columns[2].selectbox('Session',session_names,key=f'session-{year}-{round_number}-{demo}')

if not demo:
    with st.sidebar.expander('Cache management', expanded=False):
        st.caption('Optional: download the completed sessions from the selected Grand Prix once, so switching between them later is faster.')
        cacheable = completed_sessions(event)
        if cacheable:
            st.caption('Completed sessions: ' + ', '.join(cacheable))
            if st.button('Pre-cache selected weekend', use_container_width=True, key=f'precache-{year}-{round_number}'):
                with st.spinner('Caching completed sessions for this weekend…'):
                    report = precache_weekend(year, round_number, cacheable)
                successes = [x['session'] for x in report if x['status'] == 'cached']
                failures = [x for x in report if x['status'] != 'cached']
                if successes:
                    st.success('Cached: ' + ', '.join(successes))
                if failures:
                    st.warning('Could not cache: ' + ', '.join(x['session'] for x in failures))
        else:
            st.caption('No completed sessions are available to pre-cache yet.')

analyses = catalog.available(name)
if not analyses:
    st.info('This session format has no supported analysis yet.'); st.stop()
analysis_key = st.selectbox('Visualisation',[a.key for a in analyses],
                           format_func={a.key:a.label for a in analyses}.get,
                           key=f'analysis-{name}-{demo}')
analysis = next(a for a in analyses if a.key==analysis_key)
if event is not None:
    if not bool(event.get('F1ApiSupport',True)):
        st.info('Detailed FastF1 timing is not supported for this event. Please choose another Grand Prix.'); st.stop()
    slot = next((i for i in range(1,6) if event.get(f'Session{i}')==name),None)
    date = event.get(f'Session{slot}DateUtc')
    if date is not None and pd.notna(date) and pd.Timestamp(date).tz_localize(None) > pd.Timestamp.now(tz='UTC').tz_localize(None):
        st.info('This session is scheduled in the future. Choose a completed session to generate charts.'); st.stop()
try:
    with st.spinner('Loading session timing and participants…'):
        if demo:
            from f1dash.demo import demo_session
            session = demo_session(name)
        else:
            session = session_data(year,round_number,name)
    data = p.normalize(session.laps)
except p.NoData as exc:
    st.info(str(exc)); st.stop()
all_drivers, labels = roster(session,data)
all_teams = sorted(data.Team.dropna().unique().tolist())
if not all_drivers:
    st.info('No participants have been reported for this session.'); st.stop()

scope = f'{year}-{round_number}-{name}-{analysis_key}-{demo}'
drivers = None; teams = None
if analysis.selector == 'driver':
    driver = st.selectbox('Driver',all_drivers,format_func=labels.get,key='driver-'+scope)
    drivers = [driver]
elif analysis.selector == 'teams':
    teams = st.multiselect('Teams',all_teams,default=all_teams,key='teams-'+scope)
else:
    # Whole-field analyses start with everyone selected; users can rapidly narrow the field.
    defaults = all_drivers
    drivers = driver_checkbox_selector(all_drivers, labels, scope, defaults)

options = p.FilterOptions()
if analysis.filtering:
    with st.expander('Representative-lap filters',expanded=False):
        c1,c2,c3 = st.columns([1,1,1])
        quick = c1.checkbox('Remove unusually slow laps',value=True,key='quick-'+scope)
        threshold = c2.slider('Maximum % of driver/compound best',101,130,107,1,disabled=not quick,key='threshold-'+scope)
        green = c3.checkbox('Green-track laps only',value=True,key='green-'+scope)
        st.caption('Pit laps, deleted laps, generated laps and inaccurate timing are excluded. '
                   'Turning off green-only permits yellow-flag laps that pass FastF1 accuracy checks, not SC/VSC laps. '
                   'Disable the slow-lap cutoff when conditions change substantially, including within one compound.')
        options = p.FilterOptions(quick,threshold/100,green)

if analysis_key=='teams' and catalog.session_kind(name)=='practice':
    st.info('Practice lap-time distribution: these laps do not establish true race pace or fuel-corrected performance.')
if analysis_key=='sectors':
    st.caption('Personal-best sectors may come from different laps and conditions. Theoretical time is an illustration, not a prediction.')

context = {'year':year,'event':('SYNTHETIC · '+event_name) if demo else event_name,'session':name}

text_defaults = default_chart_text(analysis_key, context, drivers)
text_scope = scope + ('-' + drivers[0] if analysis.selector == 'driver' and drivers else '')
text_keys = {
    'title': 'chart-title-' + text_scope,
    'subtitle': 'chart-subtitle-' + text_scope,
    'x_label': 'chart-x-' + text_scope,
    'y_label': 'chart-y-' + text_scope,
}
for key, default in [('title', text_defaults['title']), ('subtitle', text_defaults['subtitle']), ('x_label', ''), ('y_label', '')]:
    st.session_state.setdefault(text_keys[key], default)

with st.expander('Chart text', expanded=False):
    reset_col, _ = st.columns([1, 5])
    if reset_col.button('Reset defaults', key='reset-text-' + text_scope, use_container_width=True):
        st.session_state[text_keys['title']] = text_defaults['title']
        st.session_state[text_keys['subtitle']] = text_defaults['subtitle']
        st.session_state[text_keys['x_label']] = ''
        st.session_state[text_keys['y_label']] = ''
        st.rerun()
    chart_title = st.text_input('Title', key=text_keys['title'])
    chart_subtitle = st.text_input('Subtitle', key=text_keys['subtitle'])
    with st.expander('Advanced axis labels', expanded=False):
        st.caption('Leave an axis label blank to keep the chart-specific automatic label.')
        x_label = st.text_input('X-axis label', key=text_keys['x_label'])
        y_label = st.text_input('Y-axis label', key=text_keys['y_label'])

chart_text = {
    'title': chart_title.strip(),
    'subtitle': chart_subtitle.strip(),
    'x_label': x_label.strip(),
    'y_label': y_label.strip(),
}
signature = json.dumps([demo,context,analysis_key,drivers,teams,asdict(options),chart_text],sort_keys=True)
can_generate = (drivers is None or len(drivers)>0) and (teams is None or len(teams)>0)
if not can_generate:
    st.info('Select at least one '+('team' if analysis.selector=='teams' else 'driver')+'.')
if st.button('Generate chart',type='primary',disabled=not can_generate):
    st.session_state.pop('output',None)
    try:
        with st.spinner('Generating chart…'):
            telemetry = None
            positions = None
            if analysis_key == 'positions':
                positions = data[['Driver','LapNumber','Position']].copy() if demo else reported_positions(year, round_number, name)
            if analysis_key=='speed':
                if demo:
                    from f1dash.demo import demo_telemetry
                    telemetry = demo_telemetry(drivers[0])
                else:
                    telemetry = fastest_telemetry(year,round_number,name,drivers[0])
            with PLOT_LOCK:
                result = generate(analysis_key,data,context,drivers,teams,options,
                                  session=None if demo else session,telemetry=telemetry,positions=positions,
                                  chart_text=chart_text)
                try:
                    figures = {key:png_bytes(fig) for key,fig in result.figures.items()}
                finally:
                    for fig in result.figures.values(): plt.close(fig)
            reported = set()
            for table in result.tables.values():
                if 'Driver' in table: reported.update(table.Driver.dropna())
            missing = sorted(set(drivers or []) - reported)
            if missing: result.notes.append('No usable observations for this analysis: '+', '.join(missing))
            if demo:
                result.notes.insert(0,'SYNTHETIC DEMONSTRATION — not real session data.')
            st.session_state.output = dict(signature=signature,figures=figures,tables=result.tables,notes=result.notes,
                                          metadata={'context':context,'analysis':analysis_key,'drivers':drivers,'teams':teams,
                                                    'filters':asdict(options),'chart_text':chart_text,'synthetic':demo,'fastf1':'3.8.3',
                                                    'generated_at_utc':pd.Timestamp.now(tz='UTC').isoformat(),
                                                    'notes':result.notes})
    except p.NoData as exc:
        st.info(str(exc))
    except Exception:
        log.exception('Chart generation failed')
        with PLOT_LOCK: plt.close('all')
        st.error('This analysis could not be generated from the available data. Try another driver/session '
                 'or refresh the session. Technical details are in the terminal running this app.')
output = st.session_state.get('output')
if output and output['signature']==signature:
    st.divider()
    chart_tab,data_tab,method_tab = st.tabs(['Chart','Processed data','Method & context'])
    slug = re.sub(r'[^a-zA-Z0-9_-]+','-',f'{year}-{event_name}-{name}-{analysis_key}').strip('-')
    if demo: slug='SYNTHETIC-'+slug
    with chart_tab:
        shown_notes = set()
        for note in output['notes']:
            if any(word in note for word in ('Wet running', 'timestamp-derived', 'conflicting', 'TimingData.Position', 'Fewer than five representative laps')):
                if analysis_key == 'positions' and 'timestamp-derived' in note:
                    continue
                friendly = colleague_note(note)
                if friendly not in shown_notes:
                    st.info(friendly)
                    shown_notes.add(friendly)
        for key,png in output['figures'].items():
            st.image(png,use_container_width=True)
            st.download_button('Download PNG · 300 dpi',png,f'{slug}-{key}.png','image/png',key='png-'+key)
    with data_tab:
        for key,table in output['tables'].items():
            st.subheader(key.replace('-',' ').title())
            st.dataframe(table,hide_index=True,use_container_width=True)
            st.download_button('Download CSV',p.csv_bytes(table),f'{slug}-{key}.csv','text/csv',key='csv-'+key)
    with method_tab:
        st.caption('Plain-English notes on how this chart was produced. Detailed audit information remains in the downloadable analysis context.')
        seen = set()
        for note in output['notes']:
            friendly = colleague_note(note)
            if friendly not in seen:
                st.write(friendly)
                seen.add(friendly)
        st.download_button('Download analysis context',json.dumps(output['metadata'],indent=2),f'{slug}-context.json','application/json')
elif output:
    st.caption('Your selection has changed. Generate a new chart to update the result.')
else:
    st.caption('Set your options, then select Generate chart. Exports appear with the result.')
