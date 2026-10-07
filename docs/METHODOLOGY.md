# Audited analytical definitions — FastF1 3.8.3

This replaces the initial build's methodology. The supplied Installation, Getting Started and seven gallery PDFs were the primary references. The installed 3.8.3 source for `pick_fastest`, `pick_quicklaps`, `_check_lap_accuracy` and position calculation was also inspected. Deviations below are deliberate and must not be mistaken for exact tutorial replication.

## Shared rules

All calculations use copies of source data. Lap/sector timedeltas become explicitly named seconds columns. Driver/lap identity is `Driver` + `LapNumber`; identical duplicates are collapsed. Conflicting duplicates are flagged and excluded, rather than selecting an arbitrary first row. Missing driver identity is excluded. Unknown compounds remain UNKNOWN, not silently dropped.

**Observed lap:** positive integer LapNumber, no conflicting duplicate, not FastF1Generated. A source-observed lap is not necessarily a valid timed or clean racing lap.

**Valid timed lap:** observed; finite positive LapTime; `Deleted=False`. If Deleted is unknown, an explicit `IsPersonalBest=True` can establish eligibility for that particular lap. An explicit deletion always wins. This is a conservative source-data definition, not an independent FIA validity ruling.

**Confirmed personal best (PB):** valid timed lap and IsPersonalBest=True. This reproduces the supplied tutorials' `pick_fastest()` flag requirement. If no confirmed PB exists, no ordinary minimum is silently substituted. Ties retain source order. A driver may have multiple PB-flagged laps as their times improved; the minimum of those is used.

**Representative lap:** valid timed, IsAccurate=True, PitInTime and PitOutTime absent. By default TrackStatus must equal `1` (green only). Disabling green-only still requires IsAccurate: FastF1 itself only admits green/yellow status combinations, consistent sector sums and timing differences, and excludes certain laps following a safety car. Thus this switch does NOT enable SC/VSC or arbitrary inaccurate laps.

The optional quick filter retains LapTime ≤ 1.07 × the minimum retained lap within each driver/compound group (adjustable 1.01–1.30). This differs from tutorial `pick_quicklaps()`, which applies a strict `<` threshold to the fastest lap of whatever selection it receives. Group-specific filtering avoids comparing wet compounds against dry times, but remains a selected sample, not a race-pace model. Even a single compound can span changing weather, fuel, traffic and run plans. Disabling the quick cutoff does not disable validity/accuracy/pit filters.

`filter-retention` exports nested row counts per driver: source → unambiguous observed → valid timed → accurate non-pit → track-status eligible → quick-filter retained. These are denominators, not mutually exclusive reasons. Team analyses retain the full-session driver audit so omissions can be inspected.

## 1. Session Fastest Laps

**Fields:** Driver, Team, LapNumber, LapTime, IsPersonalBest, Deleted, FastF1Generated, Compound.

**Filter/calculation:** minimum confirmed PB for each driver. Compute session-wide minimum first; delta = driver PB minus that minimum. Apply visible-driver selection only afterward. Hidden drivers cannot change the benchmark. Export benchmark driver/time with every row.

**Tutorial:** Qualifying Results Overview; its personal-best flag requirement is now retained. Practice, qualifying, sprint qualifying/shootout are supported. All phases of qualifying are combined; this is not the official elimination-based qualifying order. IsAccurate is not additionally required for outright PB ranking, as in the tutorial. Missing PB metadata yields missing drivers or an explanatory no-data result.

## 2. Driver Lap Times

**Fields:** Driver, LapNumber, LapTime, Compound, IsAccurate, IsPersonalBest, Deleted, FastF1Generated, PitInTime, PitOutTime, TrackStatus.

**Filter/calculation:** one driver; representative-lap rules above. Scatter actual lap number against lap-time seconds, coloured by FastF1 compound colour. No interpolation across excluded laps and no multi-driver overlay. Retained lap rows and filter counts are exported.

**Tutorial:** Driver Laptimes Scatterplot. The extra explicit validity/accuracy/pit/flag filters are stricter than tutorial `pick_quicklaps()`. Slow laps are not automatically “errors”; review filter retention and disable the quick cutoff for evolving conditions. Wet/dry conditions are not normalised.

## 3. Driver Lap-Time Distribution

**Fields/filter:** same lap fields and representative rules as analysis 2; all session participants can be selected.

**Calculation:** per-driver count, arithmetic median, and minimum of retained lap times. Order by retained-lap median. Boxes show quartiles, median and 1.5-IQR whiskers; all retained observations remain visible as points. Fewer than five samples produces points only, not an estimated distribution box. A one-lap median is mathematically defined but not evidence of sustained pace.

**Tutorial:** Driver Laptimes Distribution Visualization. No restriction to top-ten finishers. Boxplots replace violin density estimation to avoid overinterpreting sparse samples. This pools compounds/conditions; medians must not be interpreted as controlled performance rankings. DNFs contribute only their observed eligible laps; no completed race is inferred. Missing/filtered-out participants are reported by the UI.

## 4. Team Lap-Time Distribution

**Fields:** analysis 3 fields plus Team.

**Calculation:** same distribution statistics, grouped by Team. Pool all retained driver laps; drivers with more retained laps receive more weight. Team selection is applied to the display, not to quick-filter benchmarks. No equal-driver averaging or tyre/fuel correction.

**Tutorial:** Team Pace Comparison. Tutorial's pooled session-wide quick cutoff is replaced by the shared group-specific filter. Practice labels say lap-time distribution, never true race pace. Qualifying is excluded because sparse, elimination-dependent pooled team samples are especially misleading. Wet-session cautions are shown beside the chart.

## 5. Position Tracker

**Fields:** original FastF1 timing API `TimingData` messages: Lines keyed by driver number, Position, NumberOfLaps, message timestamp. Session results provide only driver-number-to-abbreviation identity. `session.laps.Position` is retained as `FastF1DerivedPosition` for comparison, NOT used to plot the line.

**Calculation:** process messages in source order. Maintain each driver's most recently reported Position. At a positive integer NumberOfLaps increment, capture that position, the message timestamp and last position-update timestamp. Apply same-message Position updates before recording the lap. Driver selection never reranks positions. Missing counts are not invented, missing positions are not backfilled, and a lap-counter reset refuses to generate an unsafe history. No extrapolation after the last reported lap. Pit/deleted/SC/wet laps are not filtered out of race history.

**Tutorial:** Position Changes During a Race plots `laps.Position` directly. In 3.8.3 that high-level field ranks aligned lap-end Time values; those timestamps are demonstrably unsuitable for the priority Bahrain case. An isolated private `_api.fetch_page(..., 'timing_data')` adapter is therefore used, with FastF1 pinned to 3.8.3. If it fails, the application explains the failure instead of silently reverting to a known-risk timestamp ranking.

**Limits:** these are reported positions at each driver's own lap-count update, NOT simultaneous field snapshots, official FIA lap-chart positions, or steward-adjusted classification. Feed position updates may be delayed; exported timestamps reveal that limitation. Lapped cars have their own completed-lap x-coordinate. Delayed starts/formation laps preserve the feed's numbering, rather than manually shifting it to match a recollection. Straight line segments connect available successive lap samples only; they do not locate an overtake within a lap. A missing lap creates a gap. Last observed DNF position is not final classification. See AUDIT.md for the early Bahrain sequence.

## 6. Tyre Strategy

**Fields:** Driver, LapNumber, Stint, Compound, FastF1Generated; no timed-lap/pace filters.

**Calculation:** observed lap slots form bars at their actual lap numbers. Group each continuous stint/compound sequence into a Segment. Preserve missing lap slots visually and export StartLap, EndLap, RecordedLaps, MissingLapsWithinSpan. For unknown Stint=-1, a missing lap also breaks the segment; a later return to the same compound is not merged across intervening compounds. The label is a count of observed lap records, not an inferred duration. Known same-stint gaps remain visible and counted as missing within the span.

**Tutorial:** Tyre Strategies During a Race groups Driver/Stint/Compound and counts laps, then draws cumulative lengths. This app retains true lap positions so gaps are not shifted away. Generated DNF placeholder laps are excluded; an actual completed but untimed lap remains. Missing tyre updates, red-flag tyre changes and unknown stint IDs limit what can be inferred. No tyre-set identity, tyre inventory or freshness is invented.

## 7. Speed on Track Map

**Fields:** PB selection fields from analysis 1 plus `DriverNumber` and `LapStartDate`; FastF1 3.8.3 raw car-data `Date`/`Speed` samples and raw position-data `Date`/`X`/`Y` samples for the selected driver and lap window.

**Calculation:** select one driver's fastest confirmed PB; do not silently choose a slower lap if its telemetry fails. To avoid materialising full-field telemetry on small hosted instances, decode only that driver's compressed car/position stream around the lap. Preserve original car-data speed samples and linearly interpolate X/Y by timestamp between the surrounding official position samples. Colour each adjacent X/Y segment by mean endpoint speed (km/h). Equal axis aspect. Require at least three finite speed/position samples and two usable continuous segments. Invalid/nonfinite/negative speed samples form gaps; intervals ≤0 or >2 seconds are not connected. The two-second rule is a conservative display-gap threshold, not a claim about FastF1's sampling frequency.

**Tutorial:** Speed Visualization on Track Map, with the same fastest-PB and segment-colouring concept. The hosted low-memory path does not call `Lap.get_telemetry()` and therefore does not add FastF1's extra merged channels such as driver-ahead/distance; they are irrelevant to this chart. X/Y interpolation is explicitly timestamp-based and limited to the selected lap. No geographic positioning/corner attribution, two-driver comparison, or lap-delta inference.

## 8. Practice Compound Usage and Performance

**Fields:** Driver, Compound, LapNumber, Time, LapTime plus shared validity/representative fields.

**Calculation:** count observed completed lap rows with a lap-end Time or positive LapTime. This includes untimed completed outlaps, pit/slow/deleted laps. A generated partial/DNF row does not count. For each driver/compound export count, valid timed count, representative count, minimum known-valid timed LapTime, representative median and delta to the whole-session confirmed PB on any compound. No benchmark means blank delta, not zero. No valid pace for a used compound means blank timing cells, not omission of its usage.

**Tutorial basis:** tyre grouping plus lap-time aggregation; no supplied dedicated example. Compound names are normalised but unknown values remain visible. Usage and performance use different denominators intentionally. Mixed conditions and fuel loads are unknown; compound fastest laps are not a controlled tyre comparison. A negative compound delta would signal disagreement between validity/PB metadata, not a newly redefined session benchmark.

## 9. Sector Performance / Theoretical Best Lap

**Fields:** Driver, LapNumber, Compound, Sector1Time/2Time/3Time, LapTime, IsAccurate, Deleted, IsPersonalBest, FastF1Generated, PitInTime, PitOutTime.

**Filter/calculation:** source sector laps must be valid timed, accurate, non-pit, have three finite positive sectors and sum to LapTime within 3 ms. For each driver take each eligible sector minimum independently and sum them. Export every sector's source lap/compound. Actual fastest uses confirmed PB selection, not necessarily the same set of eligible sector laps. Potential = actual PB minus theoretical. Values below -3 ms or missing actual PB are marked inconsistent/unavailable; sub-3ms rounding negatives are clamped to zero. Missing sectors never become zero.

**Display:** order by theoretical time; stacked sector loss is against the minimum selected-driver sector, not the full-session lap benchmark. A one-driver selection has zero relative sector losses but still exports absolute sectors. A second panel compares theoretical and actual lap times.

**Limits/tutorial:** no supplied dedicated sector tutorial. These are best ELIGIBLE complete-lap sectors, not unrestricted sector records that include pit/partial/deleted laps. Sector minima may come from different tyres, runs or conditions; the sum is not a physically achievable prediction. Source-lap provenance makes the definition inspectable.

## Reference URLs

The supplied PDFs correspond to https://docs.fastf1.dev/getting_started/installation.html, https://docs.fastf1.dev/getting_started/basics.html and the gallery examples under https://docs.fastf1.dev/gen_modules/examples_gallery/ . Exact PDF-to-feature mapping is retained in AUDIT.md. Installed FastF1 3.8.3 source was used to verify version-specific behaviour rather than assuming current online documentation is identical.
