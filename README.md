# trendsetter-axi

Terminal charts. trendsetter-axi renders matplotlib figures and SVG as unicode text (braille lines, block bars, shaded heatmaps) that fits a fixed number of columns. Formerly prototyped as "termchart".

## Why

More analysis now happens in a terminal, next to an agent, with no IDE or notebook open. trendsetter-axi takes the matplotlib code you already have and makes one render serve both readers: a chart the person can read where they work, and a compact account of the same figure that an agent can check.

```python
from trendsetter_axi import render

r = render(fig, cols=80, strict=True)   # your existing figure; raises RenderLossError if a series left no visible cell or a legend entry was cut
print(r.text)                           # for the person: every line fits 80 cells
context = r.summary()                   # for the agent: scales, series values from the figure's data, what was lost

lean = render(fig, cols=60, rows=12, ascii=True)
hybrid = lean.text + "\n\n" + lean.summary()  # for an agent that should also see the shape: a small ASCII chart, then the numbers
```

- Output size: `render` bounds every line with `cols`; its `rows` remains a preferred height, which heatmaps and bar charts can exceed. The opt-in [`render_compact`](#bounded-displays-and-preferences) also enforces a hard `max_rows`, titles and omissions included. `ascii=True` uses cheaper drawing glyphs; `dimensions` reports cells and lines used.
- Diagnostics: `r.losses` lists what the renderer detects the text does not show, and `strict=True` raises when a data artist or series left no visible cell or a legend entry was cut or dropped. It does not catch everything: see [known limits of `strict`](#known-limits-of-strict).

What it saves, measured with `claude-sonnet-5-5` on 81 questions about 25 charts, and on 39 questions about 12 held-out charts that were not used for tuning ([benchmark](benchmarks/agent/README.md)):

| what the model gets | accuracy, dev / held-out | tokens per chart (median), dev / held-out |
| --- | ---: | ---: |
| `summary()` | 98% (79/81) / 95% (37/39) | 102 / 114 |
| hybrid: 60×12 ASCII chart + `summary()` | 96% (78/81) / 100% (39/39) | 316 / 326 |
| 640×480 PNG | 99% (80/81) / 100% (39/39) | 408 / 408 |
| `render(fig, 80, ascii=True).text` | 79% (64/81) / 90% (35/39) | 422 / 421 |
| `render(fig, 80).text`, the terminal chart | 81% (66/81) / 90% (35/39) | 639 / 701 |

This is a single-model pilot measured at commit 9288d2b: one run per format, no repeats, no baseline that hands the model the data directly. Later changes to `summary()` are not re-measured until the next benchmark run.

The token saving comes from `summary()` and the hybrid, not from the terminal chart: that one is for the person. When the model can take images, the PNG is as accurate as the hybrid for about a quarter more input tokens.

Other ways to get a matplotlib figure into a terminal, checked in the same benchmark: [mpl_ascii](https://github.com/chriscave/mpl_ascii) 1.0.1 is a matplotlib backend (`plt.show()`, or `savefig("x.txt")`) whose width follows the figure size at 12 characters per inch, and [plotext](https://github.com/piccolomo/plotext) 6.1.0 converts a figure's lines, scatter points and bar rectangles with `plotext.matplotlib(fig)`. On the same questions their text scored 78% and 73%, against 81%. Neither drew the three heatmaps; mpl_ascii raised on the log-scale chart and plotext drew it on a linear axis. Neither has a data summary or reports what it dropped.

## Install

```
uv pip install trendsetter-axi
```

From source:

```
git clone https://github.com/papayuh/trendsetter-axi
cd trendsetter-axi
uv pip install -e .
```

## Usage

```python
import matplotlib.pyplot as plt
from trendsetter_axi import render_figure

fig, ax = plt.subplots()
ax.plot([1, 2, 3, 4, 5], [2, 4, 3, 5, 7])
ax.set(title="Example", xlabel="x", ylabel="y")

print(render_figure(fig, cols=80))
```

`render_svg(svg_text, cols=80)` does the same for SVG source. For matplotlib SVG, save with `svg.fonttype` set to `"none"` so text stays text. A `clip-path` that is one axis-aligned rectangle is honoured; any other clip is drawn unclipped and the output ends with an `unsupported: ...` line saying so.

Both functions take `color=True` for 24-bit ANSI colour. Colour never changes the cell width.

### Bounded displays and preferences

```python
from trendsetter_axi import render_compact, render_ranking

small = render_compact(fig, cols=40, max_rows=8)  # single horizontal bar series
print(small.text)
# Or use original records directly, without importing NumPy or Matplotlib:
small = render_ranking(["North", "South"], [-9, 3], unit="pp", cols=40, max_rows=8)
```

Rankings retain input order, show aligned exact signed values and bars on one shared magnitude scale. `top_k=N` on `render_ranking` explicitly requests stable descending ranking. The hard row budget includes wrapped title/unit/series name and the omission line. `records` retains all source rows; `omitted` counts undisplayed rows, not missing data. Long names fall back to a wrapped exact table rather than ambiguous abbreviations. If that cannot fit, `mode="explanation"` and `reason` explain the omission within the same budgets. `ascii=True` changes bars to `#`, not caller-supplied labels; this view never needs color. For other figures/SVG, the existing complete rendering is returned only if it fits; otherwise a bounded explanation reports that the chart was omitted (`omitted=None`: unknown row count). No chart is cropped.

`render_compact` converts only a single zero-based horizontal bar series on one visible linear axes, without other data marks or extra figure context. Conversion requires a standard numeric x formatter, no y formatter offset and unlabelled minor ticks. Legends, side titles, category-axis labels, child axes, custom x formatters, missing widths or control characters in labels/headings use the complete-render/bounded-explanation fallback instead. It does not flatten multi-series/stacked charts into a ranking. Run `python examples/compact_demo.py` for the ten-team before/after and saved plain-text outputs in `.scratch/`.

```python
from trendsetter_axi import DisplayPreferences, Scalar, Surface, present

surface = Surface(cols=60, rows=11)  # unknown/text-only host: no image route
saved = DisplayPreferences(mode="image", ascii=True)  # loaded by your harness
answer = present(fig, surface=surface, saved=saved,
                 explicit=DisplayPreferences(mode="text", color=False))
print(answer.text)
number = present(Scalar(95, "%"), surface=surface, saved=saved)  # no rendering or encoding
```

The thin adapter resolves each field **explicit request → session override → saved default → automatic**, then caps rows and color to `Surface`. Preferences are only `mode` (`auto/image/text`), `rows`, `color`, `ascii`. No globals, environment inference, disk writes or implicit persistence: the harness supplies immutable snapshots and owns saving/reset at the user's chosen user/project/session scope. One-turn overrides do not change the next call. To redraw, call again with the same source and new explicit settings.

For images, pass `Surface(image_route=send_visible_figure)` only when the host has an installed **user-visible** route. That callback receives the original figure exactly once and owns encoding/delivery; the text renderer is not called. Neither inherited `TERM` nor the model's ability to read PNGs establishes this capability. Withhold the route for pipes/transcripts. An image preference without it falls back once to bounded text and exposes `fallback_reason`. In Pi keep model-facing tool content separate from the human-facing tool renderer; in Claude Code confirm a visible image plugin/client route. This library does not install either harness integration or persist harness settings.

Short guide: use a line or difference from a meaningful reference for evolution/crossings; use an age-by-cohort grid for follow-up; compute an exact threshold from source values and answer directly. A requested picture still wins over this guide.

### What the text lost: `render`

`render(source, cols=80, *, color=False, strict=False, ascii=False, rows=None)` takes a figure or SVG source (`str` or `bytes`) and returns a `RenderResult` instead of a string. Its `text` is exactly what `render_figure` / `render_svg` return. `ascii=True` swaps braille, block and shade glyphs for ASCII ones in the same cells (`' - _ / \ |` for lines, `#` for bars, `. : = #` for heat levels, `o x ^ *` for series keys): coarser, and a fraction of the tokens a model spends on braille. `rows` is the preferred height in lines (at least 8; SVG input ignores it): heatmaps and bar charts take more rows so each data row or bar keeps a line, so a 20-bar `barh` at `rows=12` returns 45 lines. `cols` is the only hard budget.

```python
from trendsetter_axi import render

fig, ax = plt.subplots()
ax.plot([1, 2, 3, 4, 5], [2, 4, 3, 5, 7], label="demand")
ax.set(title="Example", xlabel="x", ylabel="y")
ax.set_ylim(0, 6)   # hides the last point, as matplotlib does: reported in losses, not material

r = render(fig, cols=80)
print(r.summary())
```

```
title: Example
x: x
y: y
lines at x: 1 2 3 4 5
  'demand': 2 4 3 5 7
losses: clipped_data Line2D 'demand': 1 of 5 points outside the axes view
```

Fields:

- `text`: the chart.
- `dimensions`: `cols` (the budget), `width` (widest line) and `height` (lines), in terminal cells.
- `series`: one dict per series: `name`, `kind` (line, errorbar, scatter, bar, barh, histogram, area, heatmap), `axes`, `key` (its glyph in the text, when there are several), `color`, `n` and key values read from the figure's own data, never from the text. Lines and scatters exclude masked and non-finite rows and count them in `missing`; their `points` field holds all eligible rows in data coordinates as an unrounded `(n, 2)` float ndarray, including points outside the axes view. All-missing lines and scatters remain listed with `n=0`, their `missing` count and empty `values` and `points`. Hidden artists (including individual bars) and hidden axes are excluded. A line lists all its points up to 16, else its first and last point and observations nearest about 10 nice x positions, in source order, plus its exact min and max; bars list every bar up to 40, else min and max; seven or more equal-width bars edge to edge retain kind `histogram` for API stability (bins, heights, peak bin), presented as `bars` with `heights:` rather than claiming counts or statistical provenance; a heatmap gives its shape, missing cells and the labelled min and max cells, the whole grid up to 36 cells, else row and column means up to 12 of each; a scatter gives its mean, Pearson r and up to 3 points far off its trend line. Presentation values other than errorbar bounds are rounded to a step near 1/60 of the smaller of the axis view span and the series' own span (4 significant digits for a constant series, 3 on a log axis) and stored as strings; `points` retains the numeric data. Timestamps print the precision needed to tell the series' instants apart (day, minute, second or fraction of a second) in the axis timezone, appending the UTC offset only when those formats still collide across a daylight-saving fold. Scatter precision also includes the displayed mean. Explicit tick labels name positions unless two ticks share a label; heatmap cells take the tick label nearest their centre only within half a cell, whatever the data units. For every drawstyle, sampled `(at, ys)` pairs are rounded source observations, never interpolated across gaps or between knots. Step lines retain `drawstyle` to state their pre/post/mid convention. Errorbar containers retain their label; a visible data line stays kind `line`, otherwise the series is `errorbar`. `xerr`/`yerr` list sampled uncertainty strings (symmetric `3`, asymmetric `-1/+2`, unknown `?`), formatted to four significant digits and aligned with `at`/`ys`; missing bounds do not increase the central points' `missing`. Endpoints are converted to data coordinates before computing bounds or inferring centers. Without a data line (`fmt="none"`), centers are segment midpoints, not recoverable asymmetric source centers. One-sided limits (`lolims`, `uplims`, `xlolims`, `xuplims`) are unsupported: all bounds on each affected axis in that container are `?`, with a summary omission; line-free containers with limits are omitted because their centers are unavailable. Sparse errorbars with ambiguous duplicate perpendicular coordinates also have unknown bounds. `not_described` lists `(artist type, count)` pairs for visible unsupported artists; the summary prints a `not described:` coverage line, e.g. `2 Wedge`, without changing render losses or supported features. Pies and contours receive coverage counts, not values; annotations and axes decorations are outside this coverage audit.
- `scales`: per visible data axes (excluding colorbar axes), the title and each axis's label, kind (linear, log, date, category) and range.
- `losses`: what the renderer detects the text does not show (see [known limits](#known-limits-of-strict)), as dicts with `kind`, `what`, `detail` and `material`. Kinds: `lost_artist` (a data artist that drew nothing or ended with no visible cell, such as a line hidden under another), `clipped_data` (points outside the axes view; matplotlib hides them too, so not material), `series_label` (a legend entry dropped or cut), `text` (a title, label or tick dropped or cut), `unsupported` (an SVG clip drawn unclipped), and for SVG `lost_series`.
- `warnings`: notes about how the input was read, such as strokes taken for gridlines by colour. One entry counts skipped hidden artists and axes; a hidden axes counts once, not once per child artist.
- `supported_features`: what this kind of input lets the renderer know. A figure has `artist_roles`, `source_values` and `artist_losses`; SVG has shapes only, so those are false.

`summary()` is the compact form for an agent: scales, series values and losses in a few lines, far fewer tokens than the chart itself. Lines that share their x positions share one `lines at x:` row. For SVG input it says `values unavailable`: SVG carries shapes, not data, so a series is a colour and a kind with no values. The summary's `losses:` line still lists render losses only. Step lines now carry `drawstyle` (e.g. `steps-post`, right-continuous) so straight and step controls differ. Separate `summary_omissions` disclose unavailable sample support for errorbars (and midpoint-inferred centers without a data line), unsupported one-sided limits and paired bounds/sample support for filled areas; global extrema are not per-x bounds. Sample denominators and risk sets are not inferred from geometry. Counts such as line `n` count plotted points, not subjects. See `series` above for errorbar bounds and unsupported-artist coverage.

`strict=True` raises `RenderLossError` when a loss is material. Two checks make a loss material: a data artist or series that left no visible cell, or a legend entry that was cut or dropped. Dropped tick labels and points outside the axes view (`clipped_data`, which matplotlib hides as well) are not material, so the example above passes `strict=True`. The error's `result` holds the full `RenderResult`.

#### Known limits of `strict`

`strict=True` passes these, so the text can still mislead:

- Lost artists are found by series colour: same-colour series that fully overlap count as drawn (T9).
- A line under an opaque fill at a higher zorder still shows through the fill in the text (T9).
- A heatmap larger than the text grid is sampled, and a cell the sampling skips is lost without a diagnostic (T4).
- SVG masks, gradients and non-rectangular clips are approximated: a non-rectangular clip is reported as `unsupported`, masks and gradients are not reported (T5).

### What a mark means

For matplotlib figures the renderer asks each artist what it is, so colour never decides it. Lines, collections, patches and images on an axes are data: a black contour, light gray bars or a big dark filled area draw like any other colour, and only a fill the colour of the page (a white bar) is left out so its edge draws. Spines and axes are the frame, the figure and axes patches are background, legends give the series keys, `ax.text` boxes are not drawn and an annotation arrow is plain ink, never a series. Gridlines are not drawn. Series keys still follow colour: two artists of one colour share a key. Artists matplotlib does not list on a figure or axes (plotnine draws its legend straight into the figure) are judged by where they sit and how they look.

SVG carries no artist information. The supported subset:

- shapes: `path` (all commands, curves and arcs flattened), `rect`, `line`, `polyline`, `polygon`, `circle`, `ellipse`, `use`, `text`/`tspan`, and base64 PNG `image`
- presentation attributes and inline `style`: fill, stroke, their opacities, `stroke-width`, `stroke-dasharray`, `font-size`, `text-anchor`, `dominant-baseline`, `display`, `visibility`, inherited through groups; `transform` with translate, scale, rotate and matrix (skew is ignored)
- `clip-path` as described above; gradients, patterns, masks, markers, filters and `<style>` sheets are skipped
- meaning from classes and ids: `legend` marks legend keys; plotly `gridlayer`/`minor-gridlayer` and vega `role-axis-grid` are gridlines (not drawn); plotly axis and zero-line layers and vega `role-axis` are the frame; vega `background` is background; shapes inside matplotlib text, tick and annotation groups are skipped

Everything else is unknown and judged by appearance: its strokes are all kept, short segments included, except that a light gray axis-aligned stroke is taken for a gridline; a big neutral fill is taken for the page or panel; a shape the colour of the page is dropped.

`cols` is a terminal-cell budget for every output line, including titles, legends, color keys and captions. CJK characters use two cells; combining marks and ANSI styling do not add cells. Color keys wrap between complete numeric ranges, using compact notation for extreme values. In `render`, `render_figure` and `render_svg`, widths too small for a single character or key entry raise `ValueError` rather than emitting an overwide line. The [bounded display path](#bounded-displays-and-preferences) translates these display-capacity failures into omission metadata; malformed-source errors still propagate.

## Extras

The core package depends on numpy, matplotlib and wcwidth. The example gallery (`trendsetter_axi.gallery`, 50 charts) needs pandas; the charts built with other libraries need those libraries too:

```
uv pip install -e '.[gallery]'
```

That installs pandas, seaborn, plotly, altair and plotnine.

Polars is optional and its columns can be passed directly to Matplotlib, without converting through pandas:

```python
import polars as pl  # install separately if needed
from matplotlib.figure import Figure
from trendsetter_axi import render_figure

frame = pl.DataFrame({"week": [1, 2, 3], "units": [10, 14, 12]})
ax = Figure().subplots()
ax.plot(frame["week"], frame["units"])
print(render_figure(ax.figure, cols=60))
```

Importing `trendsetter_axi` itself now loads neither NumPy nor Matplotlib. SVG rendering loads NumPy but not Matplotlib; figure rendering loads its normal plotting dependencies. The default install is unchanged. See [startup/compact measurements](benchmarks/first-three-changes.md).

## Examples

These were produced by running gallery charts through `render_figure(fig, 80)`.

Line chart (gallery id `01_mpl_line`):

```
                       Houston Gas Price (inflation-adjusted)
        ┌───────────────────────────────────────────────────────────────────┐
    6.0 │                     ⡇                                             │
        │                     ⣿      ⡄                                      │
    5.5 │                    ⢀⢿     ⢸⡇ ⡇                                    │
        │                    ⢸⢸     ⢸⣧ ⡇                                    │
        │                    ⢸⢸     ⢸⣿⢰⢻⡇⡄                     ⡇            │
    5.0 │              ⢰     ⢸⢸     ⢸⢿⢸⢸⣧⣿⡆                    ⡇            │
        │              ⢸ ⣤ ⢸ ⢸⢸     ⢸⠘⣼⢸⢸⡿⣷⢰⢿                  ⣇            │
        │              ⢸ ⣿ ⢸⣤⡏ ⡇    ⢸ ⣿⠸⢸⡇⢹⢸⢸                 ⢠⣿            │
    4.5 │              ⢸ ⣿ ⡞⣿⠇ ⡇    ⡞ ⠙ ⢸ ⢸⣾⠈⡆                ⢸⣿            │
        │              ⢸⣇⠏⡇⡇⣿  ⡇  ⢠ ⡇     ⠘⠇ ⡇                ⢸⢸            │
    4.0 │              ⡸⣿ ⡇⡇⠛  ⡇ ⢀⣿⢰⡇        ⡇                ⢸⢸            │
        │              ⡇⣿ ⡇⡇   ⡇⢰⣼⡿⣿         ⡇                ⢸⢸        ⣠⡦  │
        │             ⢠⡇⣿ ⣇⡇   ⡇⢸⡿⠃⠁         ⢇       ⢰       ⢀⢸⢸ ⣠⡆     ⣿⡇  │
    3.5 │             ⢸⡇⡟ ⣿⡇   ⡇⡟⡇           ⢸⢸⡄     ⢸⣇⢀⡀    ⣸⡏⢸⡇⣿⡇⢀    ⣿⠇  │
        │           ⢸⢰⡸   ⠻⠇   ⡇⡇            ⢸⡜⡇    ⡆⡜⢻⢸⣇   ⣰⠟⠁ ⣿⡿⢣⣸⡄   ⡟   │
        │  ⡀ ⣄      ⡸⣿⡇        ⡇⡇            ⢸⡇⡇   ⡄⣇⡇⢸⢸⢿   ⡟   ⣿⠃⢸⡇⢱   ⡇   │
    3.0 │  ⢿ ⣿   ⢠⢀ ⡇⠘⡇        ⡇⡇            ⢸⡇⡇ ⡆⣄⣧⢿⠇⢸⢸⠘⣄  ⡇   ⢹ ⢸⡇⢸⢀⣀ ⡇   │
        │  ⠘⣆⣿   ⢸⣸⣴⠃          ⣿⠃            ⢸ ⢻⢰⣷⡟⢸   ⡿ ⢹  ⡇     ⠸⠃⠘⡞⠛⡇⡇   │
    2.5 │   ⠹⢿⡆⢰⣰⡎⣿⣿           ⣿             ⠘ ⢸⢸⠈⠁    ⠃  ⡇⢠⠃          ⢳⡇   │
        │    ⠈⡇⡎⠉⠃ ⠉           ⢿                ⣿         ⣿⣾           ⠸    │
        │     ⢸⡇                                ⡟         ⣿⠙                │
    2.0 │     ⢸⡇                                ⠁         ⠃                 │
        │     ⠈                                                             │
        └───────────────────────────────────────────────────────────────────┘
        2000      2004     2008      2012     2016      2020     2024     2028
                                        Date
y: Price (today's $/gal)
```

Bar chart (gallery id `04_mpl_bar`):

```
                             Yearly Mean Houston Gas Price
        ┌─────────────────────────────────────────────────────────────────────┐
    3.5 │                                          3.45                       │
        │                                          ▆▆▆▆▆                      │
        │                                          █████                      │
        │                                          █████  3.01                │
    3.0 │                                          █████ █████  2.83          │
        │                                    2.62  █████ █████  ▇▇▇▇▇  2.61   │
        │                                   ▄▄▄▄▄  █████ █████  █████ ▄▄▄▄▄   │
    2.5 │               ▂2.42   2.29        █████  █████ █████  █████ █████   │
        │         2.12  █████  ▄▄▄▄▄        █████  █████ █████  █████ █████   │
        │         ▃▃▃▃▃ █████  █████        █████  █████ █████  █████ █████   │
    2.0 │   1.87  █████ █████  █████  1.82  █████  █████ █████  █████ █████   │
        │  ▆▆▆▆▆  █████ █████  █████  ▄▄▄▄▄ █████  █████ █████  █████ █████   │
        │  █████  █████ █████  █████  █████ █████  █████ █████  █████ █████   │
    1.5 │  █████  █████ █████  █████  █████ █████  █████ █████  █████ █████   │
        │  █████  █████ █████  █████  █████ █████  █████ █████  █████ █████   │
        │  █████  █████ █████  █████  █████ █████  █████ █████  █████ █████   │
    1.0 │  █████  █████ █████  █████  █████ █████  █████ █████  █████ █████   │
        │  █████  █████ █████  █████  █████ █████  █████ █████  █████ █████   │
        │  █████  █████ █████  █████  █████ █████  █████ █████  █████ █████   │
    0.5 │  █████  █████ █████  █████  █████ █████  █████ █████  █████ █████   │
        │  █████  █████ █████  █████  █████ █████  █████ █████  █████ █████   │
        │  █████  █████ █████  █████  █████ █████  █████ █████  █████ █████   │
        │  █████  █████ █████  █████  █████ █████  █████ █████  █████ █████   │
    0.0 └─────────────────────────────────────────────────────────────────────┘
            2016  2017   2018   2019  2020   2021  2022   2023  2024   2025
                                         Year
y: Mean price ($/gal)
```

Heatmap (gallery id `10_mpl_imshow`):

```
                           Mean Gas Price by Year and Month
  2016 ░░░░░ ░░░░░ ░░░░░ ░░░░░ ░░░░░ ▒▒▒▒▒ ░░░░░ ░░░░░ ░░░░░ ░░░░░ ░░░░░ ░░░░░
  2017 ▒▒▒▒▒ ░░░░░ ░░░░░ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ░░░░░ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒
  2018 ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▓▓▓▓▓ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ░░░░░
  2019 ░░░░░ ░░░░░ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒
  2020 ▒▒▒▒▒ ░░░░░ ░░░░░ ░░░░░ ░░░░░ ░░░░░ ░░░░░ ░░░░░ ░░░░░ ░░░░░ ░░░░░ ░░░░░
  2021 ░░░░░ ░░░░░ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒
  2022 ▒▒▒▒▒ ▓▓▓▓▓ █████ ▓▓▓▓▓ █████ █████ █████ ▓▓▓▓▓ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒
  2023 ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▓▓▓▓▓ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ░░░░░
  2024 ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ░░░░░ ░░░░░
  2025 ░░░░░ ░░░░░ ░░░░░ ▒▒▒▒▒ ░░░░░ ░░░░░ ░░░░░ ░░░░░ ░░░░░ ░░░░░ ░░░░░ ░░░░░
         Jan   Feb   Mar   Apr   May   Jun   Jul   Aug   Sep   Oct   Nov   Dec
$/gal (today's)  ░ 2.00-2.79  ▒ 2.79-3.58  ▓ 3.58-4.37  █ 4.37-5.16
```

## Demo

One fixed, deterministic tour: basic charts, the same chart at 100/60/40/24 columns with measured max line width, a 100k-point render with timing, a CJK title, `render_svg`, and six gallery charts.

```
python examples/demo.py
python examples/demo.py --cols 100 --section widths --section gallery
```

Sections: `basic`, `widths`, `big`, `cjk`, `svg`, `gallery`. The `gallery` section needs pandas: `uv pip install -e '.[dev]'`. Chart text is identical run to run; only the `[timing]` line varies.

## Development

```
uv venv .venv
uv pip install -e '.[dev]' --python .venv/bin/python
.venv/bin/python -m pytest
```

`python -m trendsetter_axi.mpl --test` runs the extra self-checks bundled with the matplotlib renderer; pytest runs them too.

Raster sampling clips each segment to the viewport first, caps samples at terminal resolution, and reduces redundant ink to occupied dots without bridging NaN gaps. See [render budgets and before/after profiling](benchmarks/README.md) for reproducible timings and work limits.

## License

MIT. See `LICENSE`.
