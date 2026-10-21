# Terminal width and raster work budgets

## Reproduce

```sh
PYTHONPATH=src python benchmarks/render_budget.py --profile
PYTHONPATH=src pytest -q tests/test_cells.py tests/test_work_budget.py
```

The fixture is an 8×4-inch matplotlib figure with `sin(x)`, x=0…10,
80 terminal columns, and title `Dense sine`. Times include figure copying,
layout/draw, rasterization and serialization. Each measurement is the median
of three runs after warming caches. No Rust implementation or figure-copy
optimization was needed.

## Before / after

Measured in the same Linux worktree, Python 3.14.6, numpy 2.4.4,
matplotlib 3.11.2; other workers shared the host, so timings are indicative.

| Points | Before (ms) | After (ms) | Speedup |
| ---: | ---: | ---: | ---: |
| 1,000 | 93.9 | 75.1 | 1.25× |
| 10,000 | 244.8 | 125.4 | 1.95× |
| 100,000 | 1,865.7 | 213.6 | 8.73× |

All three outputs remain **byte-identical to their respective before output**
(1,405 characters each). SHA-256, before and after:

```text
1000   8a2be09d012a4645ba9095789b3b34097b2b79c269cb9e446dd9b038a26fff06
10000  13045d0f285f503f476171bef4a39d91d42bf9bee4ea2ce965ade53c320ba6c4
100000 79a40fda6821ca4e53a9f7cdf288798bffe23b9b3f25fe80f300cefa713c39b8
```

### 100k cProfile breakdown

Profiling adds overhead; these are cumulative times, not the wall medians above.

| Phase | Before (ms) | After (ms) |
| --- | ---: | ---: |
| Figure copy (`_copy`) | 27 | 44 |
| Layout + two figure draws (`Figure.draw`) | 116 | 203 |
| Raster sampling (`_line_dots`, includes clipping after) | 3,017 | 68 |
| Composition excluding sampler | 18 | 17 |
| Row serialization (`_serialize_rows`, part of composition) | not isolated | 1 |
| End-to-end profiled call | 3,184 | 342 |

Previously, 99,999 Python segment loops each allocated a `linspace` and
stacked samples, consuming almost all render time. Clipping, interpolation,
and occupancy reduction now run in bounded numpy batches. Serialization has
its own profiling entry point; it is not the bottleneck. Copy/layout are now
a larger fraction but do not justify a renderer-language rewrite.

## Budgets

- **Width:** every emitted line is at most `cols` terminal cells, measured
  centrally with wcwidth. ANSI SGR sequences cost zero cells. Tests use an
  independent `wcswidth` oracle at 40/80/120 columns. Titles, plot text,
  legends, side labels, key footers and clip/scaling captions share this budget.
- **Atomic keys:** wrap only between complete glyph/range entries. Huge/tiny
  values use compact 3-significant-digit notation when needed. A requested
  width unable to hold even one character or complete range raises `ValueError`.
- **Per segment:** intersect with both canvas and primitive clip rectangle
  *before* allocating interpolation samples. At most
  `max(2*cols, 4*rows)+2` samples; no dependence on offscreen coordinate magnitude.
- **Per batch:** at most 1,024 visible segments. Interpolation temporaries are
  bounded by `1024 * (max(2*cols, 4*rows)+2)` samples rather than input coordinate
  magnitude or total point count.
- **Per polyline result:** at most `8*rows*cols` occupied dots, preserving
  sampled extrema and never synthesizing an edge across a NaN gap. Input
  scanning/clipping remains O(input points), as required to detect extrema.
  The alternate staircase route uses the same clipped sampler.
- **Latency target:** on this host, warmed 80-column sine fixtures should stay
  below 250 ms for 1k/10k and 500 ms for 100k. These are profiling targets,
  not hardware-independent API guarantees. The 100k regression test compares
  byte-exact output against the executable legacy sampler and requires less
  than 75% of its elapsed time; deterministic allocation/output bounds are
  tested separately and are the primary CI work guarantees.
