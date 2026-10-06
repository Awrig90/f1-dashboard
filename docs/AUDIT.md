# Focused correctness audit — 6 October 2026

## Conclusion

The user's concern was justified. The first release tested rendering, transformations and exports, but did not independently reconcile position history against reported timing positions. Successful rendering of real-session data was insufficient evidence of that chart's correctness.

The existing UI and module structure are retained. This update changes data selection, provenance, warnings and documented definitions; it is not a redesign.

## Priority case: Bahrain 2026 race

### Root cause and reproduced observations

FastF1 3.8.3 constructs `session.laps.Position` by sorting each lap number's aligned `Time` values and assigning ranks. The app plotted those ranks without checking their source. That is a risky assumption: the aligned per-driver lap timestamps in this session do not preserve actual position order.

In the downloaded source, Leclerc has derived position 19 on laps 51–54 and 17 at lap 55. This reproduces the late-race problem, though the user's reported endpoint of 19 differs from the fresh download's final row. No assumption is made about the exact cache/plot the user viewed. The reported timing feed gives Leclerc position **4** at lap 55, consistent with the official race result. The raw final lap-count message times are 04:13:16.022 for Verstappen and 04:13:23.225 for Leclerc. FastF1's aligned lap times are 04:12:56.278 and 04:13:23.039 respectively. Their difference is not the finishing gap; ranking these timestamps misplaces Leclerc.

There are **369 disagreements** between reported-position observations and the high-level timestamp-derived field across **1,142 observed lap-count increments**. These disagreements are not all proven errors in the derived field: the two representations also have different sampling/update semantics. The full comparison is exported in `evidence/bahrain-2026-position-audit.csv`.

FastF1's fallback session results also ranked Leclerc 17th in this download, with no official classified-position/status/lap-count metadata populated. Therefore simply “checking against session.results” would not independently validate this case. The official result was checked separately.

### Fix

Position Tracker now reads the actual TimingData Position field, joined by driver number to session identity, and captures it when NumberOfLaps increments. It never ranks elapsed timestamps, interpolates missing positions, extends a retired driver's trace, or overwrites an endpoint with a desired official result. It exports observation time, last position-update time, source name and the old derived position for inspection. The line/axis labels make the sampling definition explicit. If this source fails, the app refuses to substitute the old timestamp-derived positions.

This remains a sampled timing-feed history, **not an official FIA lap chart**. Feed updates can lag the timing line. Each driver has their own completed-lap x-coordinate, which matters for lapped traffic. This limitation is visible in the chart notes and methodology.

### VER and ANT: important lap-number distinction

The fetched feed contains:

| Driver | Completed-lap count | Reported Position at count update | Timestamp |
|---|---:|---:|---|
| VER | 2 | 6 | 02:32:32.872 |
| ANT | 2 | 8 | 02:32:33.809 |
| VER | 3 | 3 | 02:34:27.307 |
| ANT | 3 | 1 | 02:34:25.153 |
| LEC | 55 | 4 | 04:13:23.225 |

Later position updates, while the completed-lap count is still 2, put ANT first at 02:32:40.527 and VER third at 02:32:41.323. The FIA report describes a standing start after the end of lap 2. Thus the user's recollection of the post-start order is supported, but it must not be silently relabelled as the order at completion of feed lap 2. The chart keeps the source count: the first completed racing lap after that standing start is feed lap 3. No hard-coded lap-number correction has been applied.

**Remaining boundary:** a precise FIA end-of-lap classification or synchronous leader-lap snapshot would require a different source/definition. The corrected chart explicitly does not claim either. Early start-procedure transients can still look odd; its values are now traceable to the reported feed rather than inferred from unreliable aligned timestamps.

## Findings for all nine visualisations

Exact fields, filters, calculations and limitations for every analysis are in `METHODOLOGY.md`.

| Visualisation | Audit result and change |
|---|---|
| Session Fastest Laps | Session benchmark-before-filter logic was correct. PB selection differed from supplied `pick_fastest()`: now requires IsPersonalBest. Unknown validity is no longer silently accepted. All 20 2021 Spanish qualifying fastest times and deltas match the supplied tutorial. |
| Driver Lap Times | Coordinates and compound grouping were correct. Added retention evidence, clarified IsAccurate/flag filtering and missing-data rules. Kept single-driver scope. No claim that the quick filter identifies true representative race pace. |
| Driver Distribution | Median/min/count arithmetic was correct. Sparse-sample handling retained. Added visible mixed-wet caution and filter counts; pooled conditions remain an explicit limitation. |
| Team Distribution | Grouped medians/counts were correct. Pooled team samples weight drivers by lap count; this is now explicit. Practice wording retained. Wet caution and per-driver retention expose selection bias. |
| Position Tracker | Material source-selection error: timestamp ranking is not reliable race-position history. Switched to reported position snapshots with timestamps, before/after audit and no silent fallback. Early Bahrain lap-number caveat remains explicit. |
| Tyre Strategy | Counts and actual-lap placement were correct for complete known stints. Fixed disjoint unknown-stint/compound groups being merged. Added missing-lap counts within spans. Generated DNF rows excluded, no retirement extrapolation. |
| Speed Map | Segment-colour arithmetic was correct. PB selection now follows tutorial semantics. Invalid/nonfinite samples and gaps are no longer bridged into fictitious track segments. Source telemetry exported unchanged apart from numeric sanitisation and driver/lap metadata. |
| Practice Compounds | Material count error: positive LapTime requirement omitted completed untimed laps/outlaps. Now counts observed completions with Time or positive LapTime. Pace definitions remain separate. Bahrain 2024 FP2 usage changes from 430 to 511 recorded completed laps; representative pace remains 198 laps. |
| Sector/Theoretical | Sector minimum/sum arithmetic was correct under the stated restricted eligibility rule. Added independent 3-ms sector-sum check, finite-value checks and source lap/compound provenance. Actual fastest now uses PB semantics; misleading negative potential is suppressed, tiny rounding negatives clamped. |

Cross-cutting correction: conflicting driver/lap duplicate records are excluded with a warning, not arbitrarily reduced to one row. Missing deletion status is distinguished from False. No default quick-filter redesign was attempted; its driver/compound threshold is documented as a deliberate deviation from tutorial session-wide filtering.

## Validation evidence

- 43 automated tests, including frozen real-source regression fixtures and the actual Streamlit application flow. See VALIDATION.md.
- All 20 fastest times/deltas in the supplied Spanish qualifying tutorial reproduced from a freshly loaded 2021 session. HAM 76.741; VER 76.777 (+0.036); BOT 76.873 (+0.132); LEC 77.510 (+0.769).
- 102 driver/session PB minima compared with FastF1 `pick_fastest()` across Bahrain 2026 Race and the existing 2024 Bahrain FP2/Qualifying/Race and Chinese Sprint data; all matched.
- All applicable non-telemetry analyses regenerated on those sessions, except the revised position source was live-data-validated on the priority Bahrain case rather than redownloaded for the older races. A real 2024 qualifying speed map was regenerated.
- For Bahrain 2026, 1,145 source lap rows → 1,142 observed non-generated laps → 1,011 valid timed laps → 757 accurate non-pit laps → 658 green-track laps → 643 after the quick cutoff. Per-driver counts are included, rather than hidden behind one pooled total.
- Regression fixtures preserve the raw reported-position updates for LEC/VER/ANT and the source fields for all Spanish qualifying laps. Tests check Leclerc's 4th-place finish and preserve the actual early-lap numbering rather than asserting a fabricated correction.

Evidence files are small extracts/aggregates, not full telemetry caches. Their provenance is the FastF1 timing service downloaded during this review. Official results corroborate the finish; they do not validate every intermediate feed sample.

## Sources

- Supplied FastF1 3.8.3 PDFs: Installation; Getting Started with the Basics; Qualifying Results Overview; Driver Laptimes Scatterplot; Driver Laptimes Distribution Visualization; Team Pace Comparison; Position Changes During a Race; Tyre Strategies During a Race; Speed Visualization on Track Map.
- Installed FastF1 3.8.3 `core.py`: lap position construction, pick_fastest, pick_quicklaps, _check_lap_accuracy. Installed `_api.py`: TimingData message structure and timing stream semantics.
- [Official Formula 1 Bahrain 2026 race result](https://www.formula1.com/en/results/2026/races/1308/bahrain/race-result): Leclerc fourth.
- [FIA Bahrain race report](https://api.fia.com/news/f1-verstappen-wins-dramatic-bahrain-grand-prix-malaysia-ahead-antonelli-and-hamilton): standing start after lap 2, Mercedes one-two ahead of Verstappen; finishing order.

## What is not claimed

Passing tests does not make every upstream lap reliable. The audit has not independently checked every historical session or every intermediate position against an official lap chart. Wet/traffic/fuel/tyre-age effects remain uncontrolled. No final classification is injected into a history, and no inferred performance is presented as fuel-corrected car pace. Native Windows execution was not available; preserve the working local launcher when updating.
