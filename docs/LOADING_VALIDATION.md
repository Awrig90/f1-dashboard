# Loading and filter validation — 9 October 2026

Changes are based on repository main `012617c035171903bf030c13eea3e3023fd171cc`, preserving the existing UI and nine analyses. No dependency upgrades or hosting changes are included.

## Defects reproduced and corrected

1. `messages=False` left every lap's deletion status unknown. Conservative validity filtering then admitted only PB-flagged laps. Timing snapshots and weekend pre-cache now load race-control messages; unknown status remains explicit rather than assumed valid.
2. Timing-only loads do not populate `LapStartDate`. Speed maps previously failed before telemetry decoding. Preserve `LapStartTime` and recover the absolute start using the maximum raw `Date - packet Time` across car and position streams, rounded to milliseconds, matching the installed FastF1 3.8.3 source. Sample dates also match FastF1's millisecond rounding. Only the chosen driver's required telemetry fields are retained.
3. Compound and inclusive lap-number controls now scope representative pace and compound usage. The quick cutoff is computed within that scope. Session-best compound deltas retain their original whole-session benchmark. Empty compound selection produces no usable laps. Selection changes hide stale exports; JSON context and PNG captions describe the scope.

## Real-source lap populations

These are previously downloaded official FastF1 data replayed through the current adapters, not synthetic demonstration data. Baseline and corrected runs used separate processes and the same cache.

| 2024 session | Source rows | Representative before | Representative after | Explicitly deleted after |
|---|---:|---:|---:|---:|
| Bahrain Practice 2 | 511 | 52 | 198 | 0 |
| Bahrain Qualifying | 267 | 81 | 83 | 2 |
| Bahrain Race | 1,129 | 129 | 988 | 20 |
| China Sprint | 378 | 67 | 353 | 3 |

All four corrected sessions have zero unknown deletion flags. Source row counts are unchanged. Detailed nested denominators and memory stages are in `evidence/loading-2026-10-09/`.

## Telemetry comparison

Reference: 2024 Bahrain qualifying, VER lap 16, **89.179 seconds**, absolute start **2024-03-01 16:59:09.798 UTC**. A separate process used native FastF1 `Session.load(telemetry=True, messages=True)`, `Lap.get_car_data`, `get_pos_data` and `get_telemetry`.

- Selective output: **345 original speed samples**. Every timestamp joins to native car data; maximum speed difference **0 km/h** and lap-start difference **0 seconds**.
- X/Y agrees with independent linear interpolation of native position samples to floating-point precision (maximum below 1e-6 source coordinate units within the native position slice).
- Native merged telemetry has **702 samples** because it merges streams and interpolates additional channels. Identical row counts are neither expected nor claimed.
- Against native merged X/Y at the 345 shared timestamps, positional separation is **2.36 source units median**, **50.58 maximum**. This is the deliberate linear-versus-native interpolation difference, not an identical-position assertion. The map remains a qualitative speed visualisation; it must not be used for precise corner positioning or lap-delta analysis.
- Negative/nonfinite speeds and telemetry gaps still follow the existing chart rules. Missing start/offset/driver data raises an explanatory error; no slower lap is silently substituted.

The offset and rounding implementation was checked against FastF1 3.8.3 `Session._calculate_t0_date`, `Session._load_telemetry`, `_api.car_data` and `_api.position_data`; deletion handling against `Session.load` and `_set_laps_deleted_from_rcm`.

## Memory measurement and limits

Linux Python 3.12.14 / FastF1 3.8.3. `resource.getrusage(RUSAGE_SELF).ru_maxrss` measures process high-water RSS; per-stage values are cumulative within that process. MiB = 1,048,576 bytes.

- Corrected adapter process, four sessions loaded sequentially, four 300 dpi distribution renders and a selective speed-map render: **263.14 MiB peak** (startup about 156.52 MiB).
- Separate full-field qualifying telemetry reference: **285.36 MiB peak**. This is a different workload, not an apples-to-apples percentage memory-saving claim.
- Old timing-only baseline: **168.46 MiB peak**, without rendering and with incorrect lap eligibility; not a valid memory-performance target.

These measurements are below the project's documented 512 MB hosting budget in this environment, but do **not** prove Render will stay below its limit. They use a warm on-disk data cache, do not run the complete Streamlit server or concurrent users, and do not measure fresh network-download peaks. The raw telemetry response still includes the full session stream. No claim of a guaranteed hosting-memory fix is made. Initial live loading encountered a Jolpica timeout and continued with timing-cache data; final reproducible checks used explicit offline mode.

## Reproduce

Install `requirements-dev.txt`, then run `python -m pytest -q` (**52 passed**). Final regression run: Streamlit 1.65.0, pandas 2.3.3, NumPy 2.5.3, Matplotlib 3.11.2; dependency files are unchanged. Upstream deprecation warnings were non-fatal. New regression checks exercise non-PB validity, deletion exclusion, missing absolute lap dates, whole-stream offset evidence, compound/range boundaries, scoped cutoff/usage/retention, empty selections and actual Streamlit controls/exports.

Set `F1_CACHE_DIR` to a cache containing the sessions above. Run each mode in a fresh process:

```bash
python scripts/validate_loading.py --mode baseline --offline --output validation
python scripts/validate_loading.py --mode snapshot --offline --output validation
python scripts/validate_loading.py --mode reference --offline --output validation
python scripts/validate_loading.py --mode compare --output validation
```

Omit `--offline` to allow missing upstream data to download. A fresh-download/Render peak measurement remains an environment-specific follow-up; do not infer it from these warm-cache figures.
