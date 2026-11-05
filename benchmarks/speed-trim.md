# Matplotlib rendering: remove discarded work

## Summary

- Run geometry-only preliminary layout instead of drawing every artist into a discarded Canvas. The shortening retry also only lays out geometry.
- Clone the artist graph with matplotlib's pickle protocol rather than Python's recursive deepcopy. Keep the existing plotnine-aware deepcopy fallback for local functions and custom objects that reject serialization.
- Preserve the baseline's pre-copy tick materialization: otherwise each disposable clone constructs the initial Tick artists again in `prepare`.
- No new dependencies, public API/import-surface changes, cross-call result caches, renderer rewrite, or feature removal.

## Before / after medians

Base: current main `4376145` (includes painter-order changes). Head: `fm/ts-speed-trim`.
Python 3.10.22, matplotlib 3.10.9, numpy 2.2.6, wcwidth 0.9.3; Agg backend.

The first measurement, before editing current main, gave cold figure **367.5 ms**, warm structured **84.1 ms**, and warm text **106.5 ms**. The dense-line budget gave **64.0 / 68.1 / 109.4 ms** for 1k / 10k / 100k points. These were remeasured rather than reusing the older `1956a78` numbers.

Final `startup_routes.py`: **15 samples per variant**, alternating before/after order, fresh Python with warm OS/font caches. Interpreter launch is excluded; warm routes also exclude imports and fixture construction. No other task-local test/benchmark jobs ran during this comparison. Shared-host load varied, so compare paired-run medians, not the initial run against the final run.

| Route | Before (ms) | After (ms) | Reduction |
| --- | ---: | ---: | ---: |
| Cold figure | 480.8 | 367.0 | 23.7% |
| Warm structured | 135.8 | 100.0 | 26.4% |
| Warm text shortcut | 82.6 | 66.0 | 20.1% |
| Warm compact | 19.4 | 10.2 | 47.2% |
| Warm compact ASCII | 17.6 | 9.3 | 47.0% |
| Import control | 19.6 | 19.2 | unchanged path |
| SVG control | 95.2 | 91.7 | unchanged path |
| PNG control | 27.1 | 26.4 | unchanged path |

Cold figure ranges were 358.9–542.5 ms before and 331.2–502.4 ms after; warm structured ranges were 84.5–148.5 and 67.5–112.6 ms. These are observations, not timing assertions in CI.

Final `render_budget.py` medians (three warm samples, sequential baseline/head processes):

| Line points | Before (ms) | After (ms) |
| --- | ---: | ---: |
| 1,000 | 102.3 | 77.0 |
| 10,000 | 99.6 | 83.0 |
| 100,000 | 160.7 | 139.7 |

All three output SHA-256 values remained identical.

## Profile evidence and stopping point

Final 100k-point `cProfile` runs:

| Named work | Before | After |
| --- | ---: | ---: |
| Total calls | 362,734 | 175,114 |
| `Figure.draw` calls | 2 | 1 |
| `Axes.draw` calls | 2 | 1 |
| `Text.get_window_extent` calls | 298 | 245 |
| `Axis._update_ticks` calls | 71 | 62 |
| `copy.deepcopy` calls | 25,141 | 0 |
| `_copy` cumulative | 45 ms | 18 ms |
| Total profiled render | 239 ms | 190 ms |

An intermediate profile exposed 17 initial Tick constructions under `prepare/findobj`; pre-copy materialization removes that repeated construction, matching the original copy route's behavior.

The remaining layout-engine executions are intentional: measure the initial geometry, then reflow the tuned ticks/padding, unless snapping freezes the axes. Removing the final reflow would change output. Matplotlib's tight layout still takes about 80 ms under profiling, and the unchanged Canvas render takes 58 ms on the dense line. Stop here rather than change matplotlib layout, rasterization, or features.

## Byte identity and source preservation

- **496/496 renders:** all 50 gallery charts plus every example chart, columns 60 and 80, color off/on, ASCII off/on, including both compact height budgets. Compare exact UTF-8 text bytes and complete `RenderResult`/compact losses at base and head.
- Use the same exported SVG inputs for both versions. Plotly generates random SVG IDs that appear verbatim in loss captions; generating separate SVGs would compare different inputs.
- Entire baseline/head matrix files have the same SHA-256: `25e2da3e119471a357070c4f7435f885ed73189ece786ab99c7809738cc0cbf7`.
- **1,762 tests passed**, including the existing source-figure preservation tests. Added source-PNG byte preservation, managed/unmanaged figures, independent category counters/artists, deepcopy compatibility, and mutation-between-calls coverage.
- The work-budget regression is red on base: ordinary layout draws data twice; shortening draws it three times. Both draw it exactly once at head. No machine-dependent timing test was added.

## Reproduce

With the development/gallery dependencies and SVG exporters available:

```sh
mkdir -p .scratch/speed-base
git archive 4376145 src | tar -x -C .scratch/speed-base
PYTHONPATH=.scratch/speed-base/src .venv/bin/python benchmarks/render_budget.py --profile
PYTHONPATH=src .venv/bin/python benchmarks/render_budget.py --profile
.venv/bin/python benchmarks/startup_routes.py \
  --baseline-source .scratch/speed-base/src --source src --samples 15 \
  --output .scratch/speed-final-interleaved.json
PYTHONPATH=.scratch/speed-base/src .venv/bin/python benchmarks/render_identity.py \
  --svg-dir .scratch/identity-svg --output .scratch/base-identity.json
PYTHONPATH=src .venv/bin/python benchmarks/render_identity.py \
  --svg-dir .scratch/identity-svg --output .scratch/head-identity.json
.venv/bin/python benchmarks/render_identity.py \
  --compare .scratch/base-identity.json .scratch/head-identity.json
PYTHONPATH=src .venv/bin/python -m pytest -q
```
