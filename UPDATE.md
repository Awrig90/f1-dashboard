# Installing the accuracy-audited update

Stop the running app (Ctrl+C in its terminal). Back up your existing project folder.

Copy `app.py`, the complete `f1dash/` folder, `scripts/`, `tests/`, `docs/`, `README.md` and this file from the updated ZIP into your existing project, replacing the old copies.

**Keep your working `run_windows.bat`, `.venv` and `.fastf1-cache` unchanged.** In particular, keep any Anaconda/Python-path adjustment you made to your launcher. No dependency change is required.

Restart with your existing launcher. Restarting clears the old in-memory Streamlit cache. Existing downloaded FastF1 data can remain; the revised position analysis reads the original reported-position feed separately. Regenerate old exports: downloaded PNG/CSV files cannot update themselves.

## What changed

- Reported timing positions replace timestamp-derived positions; no silent fallback or hand-edited driver results.
- Session fastest/telemetry/actual-fastest sector references use confirmed personal-best flags.
- Untimed completed laps count towards compound usage.
- Unknown deletion status and conflicting duplicate lap records are no longer silently accepted.
- Disjoint unknown stints are not combined into one apparent stint.
- Sector source laps/compounds and lap-filter retention counts are exported.
- Wet-session cautions appear beside the chart; the track-status filter explanation is corrected.
- Speed traces no longer connect across invalid samples or time gaps longer than two seconds.

The main selectors, nine analyses, tabs, downloads and module architecture are retained.

See `docs/AUDIT.md` and `docs/METHODOLOGY.md` for the findings and exact definitions.


## Hosted performance / memory update

Two earlier hosted-performance attempts retained full FastF1 Session objects and proved too memory-hungry
for a 512 MB Render instance. This revision removes that retention entirely:

- selected sessions are loaded only long enough to extract a narrow, plain-Pandas analysis snapshot;
- the full FastF1 Session is then released before any chart is generated;
- only one lightweight snapshot is kept in Streamlit's data cache;
- **Pre-cache selected weekend** remains disk-only and disables telemetry, weather and race-control-message loading;
- Position Tracker reads the reported timing feed without loading another full Session;
- Speed on Track Map decodes only the chosen driver's car/position samples around the fastest lap rather than loading full-field telemetry;
- 300 dpi PNG generation and the immediate **Download PNG** workflow are unchanged;
- Linux deployments request a best-effort heap trim after large data operations and log current RSS around the expensive stages.

The core lap/sector/strategy calculations are unchanged. The speed-map data path is intentionally different
for memory reasons and is documented in `docs/METHODOLOGY.md`.
