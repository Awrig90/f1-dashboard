# F1 Session Lab

A complete local Streamlit dashboard for editorial F1 research using **FastF1 3.8.3**.
Nine analyses, session-aware controls, 300 dpi PNGs, processed CSVs and an analysis-context JSON export.
No accounts, API keys, GitHub connection or deployment required.

**Accuracy-audited update:** read `UPDATE.md` before updating an existing installation.
`docs/AUDIT.md` records the Bahrain position diagnosis, fixes, numerical checks and remaining limitations.

## Start on Windows

1. Install **64-bit Python 3.12** from https://www.python.org/downloads/ if needed. Include the Python launcher during setup.
2. Extract this ZIP to a normal folder (do not run it from inside the ZIP).
3. Double-click **run_windows.bat**. First run creates a local environment and installs dependencies.
4. The dashboard opens at **http://localhost:8501**. Keep its terminal window open. Press Ctrl+C there to stop it.

An internet connection is required for dependency installation and uncached real F1 sessions.
The first session load can take several minutes, particularly for telemetry. Subsequent loads use a local cache.
The app binds to localhost by default; it is not exposed publicly.

### macOS / Linux

With Python 3.12 installed, open a terminal in this folder and run:

```bash
bash run.sh
```

### Manual startup / existing Python environments

```bash
python -m venv .venv
# Windows:
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py
# macOS/Linux:
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

FastF1 requires Python 3.10+. This project was tested on Python 3.12; that is the recommended version.
`requirements.txt` pins FastF1 exactly and bounds the other direct dependencies.
`constraints-tested.txt` records the direct dependency versions used for validation; optionally install with
`python -m pip install -r requirements.txt -c constraints-tested.txt` on Python 3.12.

## Use

**Season → Grand Prix → Session → Visualisation → options → Generate chart**

- Seasons span 2018 through the current UTC year: FastF1's detailed timing/telemetry era. Older result-only seasons cannot support this dashboard's analyses.
- Event names and session slots come from the FastF1 schedule. Testing events are excluded. Sprint formats are not assumed to match a conventional weekend.
- Timing loads after session selection so driver/team controls can show the actual participants. Speed/position telemetry loads only when generating a track map.
- Whole-field analyses default to all eligible participants. Emptying a selection means no selection, not “all”. Single-driver features have one dropdown.
- Generate to view the chart, processed data and method notes. Changing options hides the previous output until you generate again.
- Download PNGs at 300 dpi (normally about 3600 pixels wide), each table as CSV, and the selected options/notes as JSON. CSV timing units are seconds.
- **Offline demonstration** uses explicitly labelled synthetic data. It is useful to inspect all controls without downloading a session. It is not suitable for reporting.

## Available analyses

| Analysis | Practice | Qualifying / SQ / Shootout | Race / Sprint |
|---|:---:|:---:|:---:|
| Session Fastest Laps | ✓ | ✓ | — |
| Driver Lap Times (one driver) | ✓ | ✓ | ✓ |
| Driver Lap-Time Distribution | ✓ | ✓ | ✓ |
| Team Lap-Time Distribution | ✓ | — | ✓ |
| Position Tracker | — | — | ✓ |
| Tyre Strategy | — | — | ✓ |
| Speed on Track Map (one driver) | ✓ | ✓ | ✓ |
| Practice Compound Usage and Performance | ✓ | — | — |
| Sector Performance / Theoretical Best Lap | ✓ | ✓ | — |

Team distributions are intentionally excluded from qualifying: a pooled sample of sparse, elimination-dependent attempts is a poor team-pace comparison. Driver distributions remain available with sample counts and sparse-data handling. Fastest-lap rankings and theoretical sectors target timed sessions; race analyses focus on stint development and distributions.

## Interpretation and filters

Read **docs/METHODOLOGY.md** before using a chart in an article. The essential distinctions:

- Fastest-lap and practice-compound deltas always use the **full session** fastest valid lap, even when the fastest driver is hidden.
- Session fastest laps additionally require `IsPersonalBest=True`, matching the supplied tutorial. Unknown deletion status is not silently accepted for ordinary pace laps. `IsAccurate` is additionally required for representative pace and sector calculations.
- Representative laps exclude pit in/out laps, inaccurate timing and, by default, non-green track status. The optional quick-lap filter defaults to 107% of the **individual driver's fastest retained lap on that compound**. This intentionally differs from a session-wide cutoff in some tutorials.
- Disable the quick filter for evolving conditions; a wet compound is not automatically compared to dry-compound speed. Even within one compound, conditions can change enough to make a fixed percentage inappropriate.
- Fewer than five representative laps produces individual points without a distribution box. Counts and medians are still exposed.
- Practice compound counts include completed recorded pit/slow/deleted laps and untimed outlaps with a lap-end timestamp; fastest/median metrics use separate filters.
- Qualifying fastest laps combine all phases and are **not official qualifying classification**. Elimination and track evolution matter.
- Sector sums may combine different laps, tyres and conditions. They are not a prediction of a physically achievable lap.
- No chart corrects for fuel, tyre age, track evolution, traffic, programme or weather. Practice pace is not labelled true race pace.
- Position Tracker uses the reported timing feed at each lap-count increment, not FastF1's timestamp-ranked `laps.Position`. Both values are exported. Feed lap numbering and delayed updates are retained; this is not an official FIA lap chart.

## Project structure

```text
app.py                     Streamlit flow, selectors, result persistence and downloads
f1dash/catalog.py          Session compatibility and schedule-slot parsing
f1dash/data.py             FastF1/cache boundary and on-demand telemetry
f1dash/processing.py       Independent pandas analysis functions
f1dash/charts.py           Matplotlib figures and result tables
f1dash/demo.py             Explicit synthetic fixtures
scripts/live_smoke.py      Optional real-session integration check
scripts/render_demo.py     Offline PNG export check for all nine charts
tests/                     Processing, chart/export and Streamlit runtime tests
docs/METHODOLOGY.md         Definitions, limits and source mapping
docs/VALIDATION.md          What was actually tested
```

All analysis functions return data independently of the UI. A future compound-specific multi-driver analysis can reuse the filters and styling without changing Driver Lap Times. No two-driver telemetry comparisons are implemented.

## Tests

Use the project's virtual environment:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/render_demo.py
# Optional, uses internet and downloads real timing/telemetry:
python scripts/live_smoke.py --year 2024 --round 1 --session Qualifying --telemetry
```

If using the batch launcher, replace `python` above with `.venv\Scripts\python` on Windows, or `.venv/bin/python` on macOS/Linux.

## Cache and troubleshooting

- The default cache is `.fastf1-cache/` inside the project. Set environment variable `F1_CACHE_DIR` to use another writable folder.
- **Refresh session data** clears Streamlit's in-memory caches. FastF1's disk cache remains intact, so this is not a forced full redownload. For suspected stale/corrupt upstream data, stop the app, rename or delete `.fastf1-cache`, then restart.
- Future, cancelled, unsupported and incomplete sessions get explanatory messages. Recently completed sessions may take time to become available. This is a historical research dashboard, not live timing.
- If the schedule fails, check internet/proxy access, choose a different year, or use offline demonstration. The app never silently substitutes synthetic data for real results.
- Missing telemetry can affect a specific driver/lap while timing charts still work. The map does not silently switch to a slower lap.
- Terminal logs contain technical details; the UI avoids raw tracebacks. Upstream API/coverage issues cannot be repaired by the dashboard.
- If installation fails, rerun the launcher after fixing the displayed error. It retries incomplete dependency installation. If Python itself is wrong, delete only `.venv` and recreate it with Python 3.12.
- If port 8501 is busy, add `--server.port 8502` to the manual Streamlit command.

## Later GitHub / Streamlit use

This is a normal source project with requirements and `.gitignore`. It contains no credentials, virtual environment, caches or deployment integration. You can upload it to your own repository later. If you later host it, set the entrypoint to `app.py` and override the local-only server address as your host requires. Review access control and persistent-cache handling for your hosting setup; nothing has been deployed.

The supplied FastF1 PDF examples were the primary technical references. They are mapped in docs/METHODOLOGY.md, not bundled into this distributable. FastF1 and upstream F1 data remain subject to their respective terms; this project does not grant data republication rights.


## Chart text customisation

Open **Chart text** before generating a visualisation to edit the title and subtitle.
Advanced axis-label overrides are also available; leaving an axis label blank keeps the
analysis-specific automatic label. PNG exports use the text currently selected in the UI.

## Optional weekend pre-caching

The app keeps **only one full FastF1 Session object in process memory at a time**. Loading an entire
weekend into RAM is deliberately avoided because a 512 MB host can exceed its memory limit quickly.
**Cache management** in the sidebar can still pre-cache all completed sessions from the selected Grand
Prix to FastF1's disk cache. Those sessions are loaded one at a time with telemetry disabled and then
discarded, so later session loads can reuse downloaded files without retaining the whole weekend in RAM.
Telemetry remains lazy and is loaded into the currently selected session only when a telemetry-based
visualisation needs it.

## Hosted-performance behaviour

Repeated Streamlit reruns for the same selected session reuse one retained FastF1 Session object. When
the user switches session, the previous object is released before the replacement is loaded and garbage
collection is requested. Small processed-data caches are also tightly bounded. Chart generation renders
the PNG once at 300 dpi; those same bytes are used for the on-screen preview and the immediate **Download
PNG** control. **Refresh session data** clears Streamlit data caches and the retained FastF1 session.

On hosts with ephemeral filesystems, FastF1's disk cache can still disappear after a service restart or
spin-down. A persistent disk and an always-on service are hosting concerns rather than application
requirements.

For lap-time distribution charts, a box-and-whisker summary is shown only when at least five
representative laps remain for that driver/team. Smaller samples are shown as individual points
without a distribution box.
