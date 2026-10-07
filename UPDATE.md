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

The first hosted-performance build retained several loaded FastF1 sessions and proved too memory-hungry
for a 512 MB Render instance. This revision uses a strict low-memory model:

- at most **one full FastF1 Session** is deliberately retained in process memory;
- repeated reruns for the same selected session reuse that object;
- switching session releases the previous object before loading the replacement;
- **Pre-cache selected weekend** is now disk-only: sessions are loaded sequentially, telemetry disabled, and discarded after their FastF1 cache files are warmed;
- telemetry is loaded lazily into the currently selected session instead of creating a separate telemetry-keyed Session cache entry;
- telemetry and reported-position data caches are tightly bounded;
- charts still render once at 300 dpi and are immediately available through **Download PNG**;
- **Refresh session data** clears Streamlit data caches and the retained FastF1 session.

These changes do not alter analytical definitions or chart calculations.
