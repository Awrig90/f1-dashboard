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


## Hosted performance update

This package also includes a responsiveness pass for low-CPU hosting:

- loaded FastF1 Session objects now use Streamlit's resource cache instead of being serialized/copied via `st.cache_data` on each rerun;
- **Pre-cache selected weekend** now warms the in-process loaded-session cache as well as FastF1's disk cache;
- charts render once at 300 dpi and the same PNG bytes are used for display and download;
- 300 dpi PNGs are generated with the chart and are immediately available via **Download PNG**;
- **Refresh session data** clears both data and resource caches.

These changes do not alter analytical definitions or chart calculations. Telemetry remains lazy. Resource-cached Session objects are treated as read-only.
