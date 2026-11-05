# Experimental record/query validation

Historical evidence for the initial implementation at `929cda4`, before the
review fixes in `ec2976f` and `d6d364e`; not validation of those revisions.
Baseline: `d83ce5e` (main at dispatch). No benchmark fixtures or rendering/summary
code paths were replaced. Current behavior and deferred work belong to the
[experimental API contract](../README.md#experimental-chart-records-and-queries).

## Oracles

`tests/test_record.py` checks the figures' own input arrays, not chart text:

- Forecast bounds: first source week with width >= 24 is **6 / 2**.
- ECDF at 300: step-post **95 / 90**; straight control
  **95.83333333333333 / 91.66666666666667**. Outside the knots is unavailable.
- Kaplan-Meier: unavailable without subject records (duplicated subjects can
  draw identical curves); attached records give **1 / 3 / 2**.
- Hidden/masked/NaN eligibility, missing runs, source order, duplicate identity,
  bar bases/tops, multi-vertex segments, heat missing versus zero, step bounds,
  log-scale interpolation, claims, diffs, declaration-only intent and CLI imports.

## Local suite and packaging

Pre-review local suite: **1818 passed**, 34 existing/dependency warnings (Python
3.10.22, matplotlib 3.10.9, NumPy 2.2.6), with `BROWSER_PATH` set for Plotly exports.
`uv build --wheel` succeeds; an isolated interpreter loading that wheel verifies
the public lazy API and saved-record queries without NumPy/matplotlib imports.
No dependency declarations changed.

## Gallery byte identity

The existing `benchmarks/render_identity.py` matrix was run against archived
baseline source and the initial implementation. A scratch copy of its driver added
`summary=result.summary()` to each output entry; the benchmark itself and all
fixtures remained unchanged. SVG exports were shared across both runs, as the
existing driver requires, to avoid random SVG IDs in diagnostic captions.

All **512** matrix entries compare equal, including **all 50 gallery charts** at
60/80 columns, plain/colour and braille/ASCII, plus the driver's demos, step-line
controls, compact ranking and draw-dependent artists. Comparison includes UTF-8
chart text, summary text and loss reports. SHA-256 of the sorted JSON mapping
`{case: field_text}` (`ensure_ascii=False`) is identical on both sides:

- Chart text: `665e83c1f7982d9025b12e125187d2fb65e7ce2dc43510ff5f12d67277d300e2`
- Summary: `79583d466c3cd8ee88a78aff5e7481431445550da23768cf5048f4c6192c3039`

To reproduce, archive baseline `src` under `.scratch/record-base`, copy the driver
under `.scratch` with that extra output field (and its fixture import root set to
`Path.cwd()`), then run it with `PYTHONPATH=.scratch/record-base/src` and
`PYTHONPATH=src`, the same `--svg-dir`, and separate `--output` files. Its
`--compare before.json after.json` compares complete entries, including summaries.
The gallery extra, Kaleido, vl-convert and a local Chrome executable are needed;
set `BROWSER_PATH` for Kaleido when Chrome is outside its search path.

## Import boundary

On Python 3.10.22, alternating fresh interpreters pinned to one CPU (40 measured
samples per version after warmup), package-import medians were **49.406 ms
baseline / 49.380 ms current**. This is a local shared-host observation, not a
performance guarantee. Both versions load neither NumPy nor matplotlib. Record
and query modules are still deferred at package import; saved-record queries
load only stdlib modules beyond the package's existing lightweight imports.
Isolated-interpreter tests enforce that boundary and repeated calls through the
public `query` entry.

These results do not update the agent benchmark's model-accuracy claims.
