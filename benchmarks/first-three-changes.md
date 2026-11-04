# First three changes: validation and handoff

Starting main: `7fbc29d9173b2ce22a15ea1989b5e260f0d1bd35`.
Branch: `fm/ts-handoff-c123`.

## Scope

- Deferred format-specific imports, keeping existing functions, exceptions, return types and figure-copy behavior. No dependency split.
- Opt-in `render_ranking` / `render_compact`: hard cell/row budgets including headings, units, series identity and omission notices. Exact signed values, shared magnitude scale, input order unless top-k explicitly requests ranking, wrapped exact-table fallback, structured omissions and bounded explanations. Figure tick-label lookup happens on a copy, too.
- Thin `present` adapter: explicit > session > saved > automatic, intersected with surface rows/color and an explicitly supplied user-visible image route. Scalar bypass, one-shot text overrides, no TERM inference, globals or persistence side effects. The harness owns saving/reset/scope and image delivery; this is not an installed Claude Code or Pi extension.
- Small supported summary patch: step drawstyles and separate omissions for unrepresented errorbar endpoints/filled-area paired bounds and sample support. The current sampling contract is in the [README](../README.md#what-the-text-lost-render). No inferred denominators, risk sets or generic polygon interval extraction; `losses` and strict-mode materiality are unchanged.
- Review fixes: show complete ranking/table blocks without reserving an unnecessary omission notice. Reject ranking conversion when legends, side titles, category-axis labels, child axes, extra visible figure artists, unsupported text, missing widths or formatter semantics would lose identity/context. Conversion accepts only the standard numeric x formatter, no labelled minor ticks and no y formatter offset. Use the complete-render/bounded-explanation fallback instead. Translate only typed insufficient-display-capacity errors into bounded omissions, including `present` fallback; direct ranking validation and malformed-source errors still raise.

Inspected the eligibility branch at `fabf6221423c57f9952777f6f67bd13e3aa7fb71` before implementation. Per Firstmate's scope decision, this delivery fixes step-summary sampling only. Hidden axes/artists, gap accounting, masked scatter/clipping and missing counts belong to the separate [T1 task / PR #10](https://github.com/papayuh/trendsetter-axi/pull/10), not this delivery. These are historical delivery boundaries, not current limitations; see the [README](../README.md#what-the-text-lost-render) for current eligibility behavior.

## Exact checks and results

The commands/results below are historical **pre-review-fix evidence**, recorded for the original implementation (starting review HEAD `4e46d1523f3a9cbde8f20cc9414f20b4df136b2a`), not fresh validation of the review-fixed code. Existing development environment for those checks: Python 3.14.7, dev extra available.

```sh
.venv/bin/python -m pytest -q
# Baseline: 159 passed in 24.62s
# Final:    295 passed in 26.03s

.venv/bin/python -m pytest -q tests/test_compact.py tests/test_display.py tests/test_handoff_fixtures.py tests/test_import_routes.py
# 136 passed in 5.43s (also included in final full run)

git diff --check
# clean

PYTHONPATH=.scratch/src .venv/bin/python tests/route_probe.py > .scratch/before-public-outputs.json
PYTHONPATH=src .venv/bin/python tests/route_probe.py > .scratch/after-public-outputs.json
cmp .scratch/before-public-outputs.json .scratch/after-public-outputs.json
# identical: 42 public-output/strict-mode cases, fresh subprocesses

.scratch/core-after/bin/python tests/route_probe.py > .scratch/core-public-outputs.json
cmp .scratch/before-public-outputs.json .scratch/core-public-outputs.json
# identical: all 42 cases in the core-only wheel install

.scratch/core-after/bin/python benchmarks/core_smoke.py
# core-only smoke: import, ranking, SVG, strict figure, scalar pass; pandas blocked
```

The suite retains `test_render_figure_leaves_figure_unchanged`. Fresh-process `sys.modules` tests prove: import, native rankings and scalar answers load neither NumPy nor Matplotlib; vector SVG loads NumPy but not Matplotlib; figures load their normal dependencies. Eager versus lazy public outputs also match in fresh interpreters.

Targeted fixtures cover unequal calibration support/Wilson whiskers, masked versus zero-filled cohorts, exchanged forecast widths, straight versus post-step ECDFs, moved survival censor marks and duplicated subjects. Direct record calculations establish the exact answers; the renderer does not fabricate interval endpoints or risk counts. Compact tests cover every line's display cells and total rows, mixed signs, ties/zeros, CJK/combining labels, ASCII/color-off, small windows, exact tables, top-k omissions, source geometry and existing Tick state. Preference tests cover scalar/image sentinels, one text fallback, explicit/session/saved precedence, false/auto resets, caller-owned scope isolation, concurrent independent actual text renders and local redraws without saving overrides.

## Review-fix focused verification

### Initial review fixes (`72f3517`)

Linux review worktree, `/usr/bin/python`: Python **3.14.6**, pytest **9.1.1**, Matplotlib **3.11.2**, NumPy **2.4.4**, wcwidth **0.8.2**. The checkout has no `.venv`; the available interpreter supplies the test dependencies. No packages or host settings were changed.

Before fixes, executable reproductions confirmed the relabelled legend became an anonymous ranking; the one-column `東` SVG and three-column heatmap color key raised capacity `ValueError`s; both long pre/post-step summaries reported `20=67` instead of their respective values `100` and `0`.

After all fixes:

```sh
PYTHONPATH=src MPLBACKEND=Agg python -m pytest -q tests/test_compact.py tests/test_display.py tests/test_handoff_fixtures.py tests/test_cells.py tests/test_import_routes.py tests/test_render.py::test_render_figure_leaves_figure_unchanged
# 232 passed in 13.88s
```

Executable regressions cover axes/figure legend labels and titles, both side titles, category-axis labels, inset/subfigure context, figure-level text/artists, complete-render and bounded `present` fallbacks, narrow figure/SVG/bytes/color-key capacity, and malformed-source error propagation. Step tests cover the reported 18-point fixture, pre/post/mid conventions, both directions, short and long lines, unsorted/repeated x and the legacy straight-line control. Source-immutability and lazy-import regressions remain passing in this focused check.

The full suite, lint, core-only installation checks and later delivery gates belong to the outer pipeline; they were not rerun in this review-fix phase. No timing/size benchmarks or live-host checks were rerun.

### Complete-display and eligibility follow-up (starting `72f3517`)

Executable pre-fix reproductions confirmed that two complete rows at 8×2 were replaced with an explanation; a multiline title and NaN width raised ranking-validation errors; and a percent-formatted figure silently became a unitless raw-value ranking.

The same available review interpreter was used. After the fixes:

```sh
PYTHONPATH=src MPLBACKEND=Agg python -m pytest -q tests/test_compact.py tests/test_display.py tests/test_import_routes.py tests/test_render.py::test_render_figure_leaves_figure_unchanged
# 233 passed in 14.71s
```

The first focused run had 231 passes and two failed new assertions requiring the NaN category label in legacy output. Those assertions exceeded the approved legacy fallback contract: the existing renderer omits that tick. The regression now checks exact legacy output and unchanged source NaN instead; no T1 renderer behavior was changed.

Regressions exercise complete ranking/table/wrapped-table blocks, headings, ASCII, top-k selecting all records, genuinely required omission notices, narrow figure conversion and `present`. Eligibility regressions cover multiline/control-character category labels, titles, units and series names, missing widths, percent/currency/custom scalar formatters, both axes' labelled minor ticks and y offsets. Both complete-render and bounded-explanation routes are exercised directly and through `present`; direct ranking validation, malformed-source errors, source immutability and lazy-import checks remain passing.

Historical benchmark provenance, the initial chart captures and niche example below are unchanged. No full suite, lint, core-only installation, benchmark, live-host or Glyph checks were run in this follow-up review phase.

### Overflow-safe ranking geometry (starting `6e90882`)

Pre-fix executable reproductions with signed integer minima in NumPy int8, int16, int32 and int64 produced bar lengths `[0, 12]`, versus `[12, 6]` for equivalent Python integers. Both absolute-value operations overflowed on the fixed-width minimum.

Ranking geometry now promotes integral operands to Python integers before computing magnitudes. Original stored values, exact signed strings, input order and explicit top-k ordering are unchanged; native rankings still import neither NumPy nor Matplotlib.

```sh
PYTHONPATH=src MPLBACKEND=Agg python -m pytest -q tests/test_compact.py tests/test_import_routes.py
# 250 passed in 10.21s
```

Regressions compare the reported int8 `[-128, 64]` case and the corresponding int16/int32/int64 minima with Python-integer controls, treating numeric overflow as an error. They assert full/half shared-scale bars, original exact values and types, input/top-k order, ASCII/Unicode output, cell/row budgets and matching table/explanation fallbacks. Fresh-process checks cover native integer rankings without NumPy/Matplotlib imports.

No full suite, lint, benchmarks, installation checks or live-host/Glyph checks were run in this review phase. All prior scope decisions, chart captures, niche evidence and pre-review benchmark provenance remain unchanged.

## Before/after: ten-team ranking

These preserved chart captures and byte/row counts are pre-review-fix evidence, not new captures of the review-fixed code.

Exact commands (UTF-8 byte counts exclude the final saved-file newline):

```sh
.venv/bin/python examples/compact_demo.py --output-dir .scratch
```

60 columns: legacy `rows=18` produces **26 rows, 59 cells, 2,422 bytes** locally (not the older experiment's 28 rows). Compact `max_rows=11` produces **11 rows, 35 cells, 436 bytes**; its ASCII bars use **316 bytes**. All ten source values remain visible.

Before, 60 columns:

```text
                                  Team change
                     ┌────────────────────────────────────┐
     Retail servicing│ █████████████████████████████████  │
                    -9 ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀  │
       Direct lending│  -8 ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇  │
                     │     ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀  │
                     │        ▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆  │
      Partner channel│     -7 ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀  │
                     │            ▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆  │
    Branch operations│         -6 ██████████████████████  │
                     │                ▅▅▅▅▅▅▅▅▅▅▅▅▅▅▅▅▅▅  │
  Digital acquisition│             -5 ██████████████████  │
                     │                   ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄  │
    Wholesale lending│                -4 ███████████████  │
                     │                       ▄▄▄▄▄▄▄▄▄▄▄  │
  Application support│                    -3 ███████████  │
                     │                          ▃▃▃▃▃▃▃▃  │
   Field underwriting│                       -2 ████████  │
                     │                              ▃▃▃▃  │
   Central processing│                           -1 ████  │
                     │                                    │
   Portfolio services│                                   0│
                     │                                    │
                     └────────────────────────────────────┘
                                     -5                0
                                       pp
```

After, 60 columns:

```text
Team change [pp]
Retail servicing    -9 ████████████
Direct lending      -8 ███████████
Partner channel     -7 █████████
Branch operations   -6 ████████
Digital acquisition -5 ███████
Wholesale lending   -4 █████
Application support -3 ████
Field underwriting  -2 ███
Central processing  -1 █
Portfolio services   0
```

40×8: legacy remains **26 rows, 39 cells, 1,458 bytes** despite `rows=8`. Compact is **8 rows, 35 cells, 326 bytes**: six teams and a four-row omission notice.

Before, 40×8:

```text
                        Team change
                     ┌────────────────┐
     Retail servicing│██████████████  │
                   -9│▀▀▀▀▀▀▀▀▀▀▀▀▀▀  │
       Direct lending-8 ▇▇▇▇▇▇▇▇▇▇▇▇  │
                     │  ▀▀▀▀▀▀▀▀▀▀▀▀  │
                     │   ▆▆▆▆▆▆▆▆▆▆▆  │
      Partner channel│-7 ▀▀▀▀▀▀▀▀▀▀▀  │
                     │     ▆▆▆▆▆▆▆▆▆  │
    Branch operations│  -6 █████████  │
                     │      ▅▅▅▅▅▅▅▅  │
  Digital acquisition│   -5 ████████  │
                     │        ▄▄▄▄▄▄  │
    Wholesale lending│     -4 ██████  │
                     │         ▄▄▄▄▄  │
  Application support│      -3 █████  │
                     │           ▃▃▃  │
   Field underwriting│        -2 ███  │
                     │            ▃▃  │
   Central processing│         -1 ██  │
                     │                │
   Portfolio services│               0│
                     │                │
                     └────────────────┘
                           -5      0
                             pp
```

After, 40×8:

```text
Team change [pp]
Retail servicing    -9 ████████████
Direct lending      -8 ███████████
Partner channel     -7 █████████
Branch operations   -6 ████████
Digital acquisition -5 ███████
Wholesale lending   -4 █████
4 omitted
```

## Niche failure / repair

```sh
PYTHONPATH=.scratch/src .venv/bin/python examples/semantics_demo.py > .scratch/niche-before.txt
PYTHONPATH=src .venv/bin/python examples/semantics_demo.py > .scratch/niche-after.txt
```

Before: `drawing changed True summary changed False`. After: `drawing changed True summary changed True`. The same ECDF knots now say `steps-post` only for the right-continuous drawing:

```text
lines at x: 100 160 1000
  'A' ● steps-post: 50 95 100
  'B' × steps-post: 50 90 100
```

At 300 ms the source counts give A=95/100, B=90/100. Straight segments through those knots do not give the same interior values. The forecast control still cannot yield exact paired crossings from an area silhouette: both variants now explicitly state that paired bounds/sample support are unavailable in the summary. The source half-width arrays establish W6 versus W2. This is an honest repair of missing semantics, not a claim of general statistical fidelity.

## Timing and size

All timing, output-size and installed-size numbers in this section and `first-three-changes.json` are **pre-review-fix evidence** for the original implementation, not measurements of the review-fixed code. They have not been rerun after the eligibility, capacity-error and step-sampling corrections.

Linux, CPython **3.14.7** (GCC 13.3.0), Axi **0.1.0**, NumPy **2.5.4**, Matplotlib **3.11.2**, wcwidth **0.9.3**. Complete dependency versions and byte accounting are in `first-three-changes.json`.

Seven fresh processes per route/variant, one warm-up per variant, interleaved with alternating order. Interpreter launch excluded. **Cold Python, warm OS/font caches**: not a disk-cache-cold claim. `warm-*` initializes fonts and routes, then times one repeated operation; fixture construction/import excluded. Figure routes retain copying. Output is monochrome. PNG measures encoding only, not user-visible delivery.

| Route | Before median [min, max] ms | After median [min, max] ms | Output bytes before → after |
| --- | ---: | ---: | ---: |
| Package import | 219.36 [203.93, 261.49] | 11.39 [11.27, 14.62] | 0 → 0 |
| Import + first vector SVG | 223.43 [217.60, 293.02] | 97.18 [75.34, 124.25] | 444 → 444 |
| Import + first figure/structured render | 504.40 [343.00, 516.29] | 500.70 [366.80, 516.46] | 2,422 → 2,422 |
| Warm structured figure | 101.40 [69.24, 105.16] | 71.76 [70.46, 123.15] | 2,422 → 2,422 |
| Warm text-only figure | 97.31 [67.97, 168.56] | 90.64 [70.42, 108.25] | 2,422 → 2,422 |
| Warm PNG encoding | 50.88 [34.80, 53.45] | 46.51 [34.87, 53.91] | 20,835 → 20,835 |
| Warm compact figure | — | 10.98 [7.65, 11.93] | — → 436 |
| Warm compact figure, ASCII bars | — | 7.79 [7.58, 12.20] | — → 316 |

A separate seven-process repeat measured cold import **213.49 [209.68, 217.55] → 11.23 [10.96, 17.10] ms**. The cold-import improvement repeats; overlapping warm/figure ranges are not evidence of a general figure speedup. Unchanged legacy routes have identical output bytes/content; compact is intentionally a different presentation.

Installed size is separate from output bytes and timings. Two core-only wheel installs, same 13 distribution versions, RECORD-owned files excluding interpreter/venv files and unrecorded caches:

- Axi: **329,217 → 348,010 installed bytes** (+18,793, including code/docs/install metadata).
- Entire core environment's distributions: **139,821,439 → 139,840,226 bytes**. Small dependency metadata-path differences also affect the total.
- Package source/data excluding `__pycache__`: **301,881 → 315,887 bytes**.
- Default runtime requirements remain Matplotlib, NumPy, wcwidth. No Glyph, plotext, trial packages or optional-dependency split added.

Reproduction (baseline snapshot is ordinary archived files, not a second Git worktree):

```sh
mkdir -p .scratch
git archive 7fbc29d9173b2ce22a15ea1989b5e260f0d1bd35 src pyproject.toml README.md LICENSE | tar -x -C .scratch
uv build --directory .scratch --wheel --out-dir baseline-wheel
uv build --wheel --out-dir .scratch/after-wheel
uv venv --python .venv/bin/python .scratch/core-before
uv venv --python .venv/bin/python .scratch/core-after
uv pip install --python .scratch/core-before/bin/python .scratch/baseline-wheel/*.whl numpy==2.5.4 matplotlib==3.11.2 wcwidth==0.9.3
uv pip install --python .scratch/core-after/bin/python .scratch/after-wheel/*.whl numpy==2.5.4 matplotlib==3.11.2 wcwidth==0.9.3
.scratch/core-after/bin/python benchmarks/startup_routes.py --baseline-source .scratch/core-before/lib/python3.14/site-packages --source .scratch/core-after/lib/python3.14/site-packages --samples 7 --output .scratch/final-timings.json
.scratch/core-after/bin/python benchmarks/startup_routes.py --baseline-source .scratch/core-before/lib/python3.14/site-packages --source .scratch/core-after/lib/python3.14/site-packages --samples 7 --routes import --output .scratch/repeat-import.json
.scratch/core-before/bin/python benchmarks/installed_size.py > .scratch/core-before-installed-bytes.json
.scratch/core-after/bin/python benchmarks/installed_size.py > .scratch/core-after-installed-bytes.json
```

## Saved terminal outputs / live verification

- `.scratch/ranking-before-60.txt`
- `.scratch/ranking-after-60.txt`
- `.scratch/ranking-before-40x8.txt`
- `.scratch/ranking-after-40x8.txt`
- `.scratch/ranking-after-60-ascii.txt`
- `.scratch/ranking-after-40x8-ascii.txt`
- `.scratch/niche-before.txt`
- `.scratch/niche-after.txt`

The resulting charts were printed through the Linux command-output channel and saved as plain text, not merely mounted in a headless UI. Still **unverified in a human's live terminal**: Linux terminal glyph/font behavior, actual Claude Code user-visible image plugin/client delivery, Pi human-facing image delivery versus model-facing content, cross-session saved harness settings, and the Windows text fallback. Callback/snapshot tests establish the adapter contract, not those integrations or human-visible latency. Firstmate approved leaving both live Linux terminal verification and Windows text fallback unverified for this delivery: Firstmate shows Linux output to the captain; the Windows check is follow-up. No broad preference or performance claim is warranted yet.

Firstmate approved moving the pinned Glyph comparison to the follow-up agent-trial task. No Glyph comparison has run and no Glyph/trial dependencies are added. That task owns the separate environment and pinned Glyph `ccb45c7` / `plotext==5.3.2` baseline.

Other follow-up, deliberately out of scope: multi-harness agent trial (steps 3–5), randomized/blind held-out head-to-heads, new chart families, generic figure auditing, the separate [T1 eligibility task](https://github.com/papayuh/trendsetter-axi/pull/10), and an optional-dependency split only if measured install size becomes an obstacle.
