# Validation record

## Accuracy audit update (supersedes the original correctness claims)

The focused review adds data-value assertions and frozen real-source regressions. **43 tests pass**, including all 20 supplied Spanish qualifying fastest-lap times/deltas and the Bahrain reported-position sequence. See `AUDIT.md`, `METHODOLOGY.md` and `evidence/audit-validation.json` for exact checks and limitations. The original test results below establish the initial runtime baseline; they did not independently validate race-position semantics.

Validated 6 October 2026 on Linux / Python 3.12 with FastF1 3.8.3, Streamlit 1.65.0,
pandas 2.2.3, NumPy 2.3.5 and Matplotlib 3.10.8.

## Automated suite

**29 tests passed.**

Coverage includes full-session benchmark preservation when the fastest driver is hidden; invalid/generated lap exclusion;
pit/flag/quick-filter behaviour; wet versus dry compound groups; empty selections; missing sectors; compound usage when
no valid pace exists; missing laps in strategy; numeric CSV exports; dynamic weekend formats; all nine PNG/table exports;
sparse distributions; and human-readable schedule, session and telemetry errors.

Streamlit AppTest exercised the actual application runtime with deterministic data boundaries: select sessions/analyses,
generate each of the nine visualisations, check table/download availability, change selectors and verify stale outputs
are hidden. It also tested offline mode after a schedule-loading failure.

The installed Matplotlib emitted a non-fatal pending-deprecation warning for its `vert` boxplot argument. The argument is
retained for compatibility with the project's supported Matplotlib range; it does not change the plotted results.

## Live integration checks

Real FastF1 data was downloaded and used. These were not synthetic substitutes.

| Session | Analyses generated | Selected evidence |
|---|---|---|
| 2024 Bahrain Practice 2 | Fastest laps, single-driver lap times, driver/team distributions, compounds, sectors | 20 fastest-lap rows; 198 representative laps across 20 drivers / 10 teams; 28 driver/compound rows; 20 sector rows |
| 2024 Bahrain Qualifying | Fastest laps, single-driver lap times, driver distributions, speed map, sectors | 20 fastest-lap rows; 83 representative laps; a real 695-sample speed/position telemetry map; 20 sector rows |
| 2024 Bahrain Race | Single-driver lap times, driver/team distributions, positions, strategy | 988 representative laps; 1,129 position observations; 63 driver/stint/compound groups |
| 2024 Chinese Sprint | Single-driver lap times, driver/team distributions, positions, strategy | 353 representative laps; 378 position observations; 21 driver/stint/compound groups |

The packaged `scripts/live_smoke.py` was additionally run through the actual caching/data adapter for Bahrain Qualifying,
including on-demand telemetry. All five offered qualifying analyses passed.

Exported fastest-lap, tyre-strategy, sector and speed-map PNGs were visually inspected for readable labels, legends,
units and layout. A local Streamlit process started successfully and returned HTTP 200 / `ok` from its health endpoint.

FastF1 reported an Ergast results-source warning for the qualifying session but loaded all 20 drivers and the timing and
telemetry successfully from its other sources. The app uses the available session results plus lap roster.

## Limits of validation

- Native Windows/macOS execution was not available; launchers are supplied but testing ran on Linux. Python 3.12 is recommended.
- No guarantee is made that every historical/current session has complete upstream data. Wet/missing/sparse/invalid data
  edge cases were covered by deterministic tests; the live sessions above are representative samples, not exhaustive coverage.
- The UI was exercised with Streamlit AppTest and a live server health check, not a manual cross-browser visual audit.
- No deployment or GitHub integration was performed.
