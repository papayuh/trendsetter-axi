# trendsetter-axi

Terminal charts. trendsetter-axi renders matplotlib figures and SVG as unicode text (braille lines, block bars, shaded heatmaps) that fits a fixed number of columns. Formerly prototyped as "termchart".

## Why

More analysis now happens in a terminal, next to an agent, with no IDE or notebook open. trendsetter-axi takes the matplotlib code you already have and makes one render serve both readers: a chart the person can read where they work, and a compact account of the same figure that an agent can check.

```python
from trendsetter_axi import render

r = render(fig, cols=80, strict=True)   # your existing figure; see the strict-mode contract below
print(r.text)                           # for the person: every line fits 80 cells
context = r.summary()                   # for the agent: scales, series values from the figure's data, what was lost

lean = render(fig, cols=60, rows=12, ascii=True)
hybrid = lean.text + "\n\n" + lean.summary()  # for an agent that should also see the shape: a small ASCII chart, then the numbers
```

- Output size: `render` bounds every line with `cols`; its `rows` remains a preferred height, which heatmaps and bar charts can exceed. The opt-in [`render_compact`](#bounded-displays-and-preferences) also enforces a hard `max_rows`, titles and omissions included. `ascii=True` uses cheaper drawing glyphs; `dimensions` reports cells and lines used.
- Source summaries: eligible source observations, errorbar bounds, axis/tick identity and unsupported-artist coverage, not values reverse-engineered from terminal glyphs. Masked/non-finite line and scatter rows and hidden artists are excluded; missing counts and summary omissions remain explicit. See the [summary contract](#what-the-text-lost-render) for sampling and precision.
- Diagnostics: `r.losses` includes heatmap sampling and per-artist visibility diagnostics. Strict mode rejects material losses, not every approximation. See [loss reporting and strict mode](#what-the-text-lost-render) for painter order, materiality and known limits, and [SVG limits](#svg-limits) for bounded traversal and decoding.

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

Requires Python >=3.10, Matplotlib >=3.10.0 and NumPy >=1.23.0 (no upper
version bounds). CI tests Python 3.10, 3.12 and 3.14 with the latest compatible
dependencies, plus Python 3.10 with those exact Matplotlib/NumPy floors. Newer
Python versions need newer NumPy releases; the installer selects compatible wheels.

The project is not currently published on PyPI (`trendsetter-axi` returns 404).
Install directly from GitHub in a virtual environment:

```sh
uv venv .venv
source .venv/bin/activate
uv pip install git+https://github.com/papayuh/trendsetter-axi
```

For an editable source checkout (in an active virtual environment):

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

`render_svg(svg_text, cols=80)` does the same for SVG source. For matplotlib SVG, save with `svg.fonttype` set to `"none"` so text stays text. See [SVG limits](#svg-limits) for work and image-decode limits, clipping and unsupported effects.

`render_figure(fig, cols=80, color=False)` and `render_svg(svg_text, cols=80, color=False)` are text-only shortcuts for `render(source, cols=80, color=False).text`: the same chart, without building the report. Both functions take `color=True` for 24-bit ANSI colour. Colour never changes the cell width.

For matplotlib figures, dense black and grey data lines use the same batched dot sampler as coloured lines; short neutral rules keep their box-drawing glyphs. The batching threshold is documented in `Canvas.stroke()` in [`core.py`](src/trendsetter_axi/core.py); it applies only to strokes tagged as data, not unclassified SVG geometry.

### Bounded displays and preferences

```python
from trendsetter_axi import render_compact, render_ranking

small = render_compact(fig, cols=40, max_rows=8)  # single horizontal bar series
print(small.text)
print(small.summary())  # source values and losses, even for undisplayed rows
# Or use original records directly, without importing NumPy or Matplotlib:
small = render_ranking(["North", "South"], [-9, 3], unit="pp", cols=40, max_rows=8)
```

Rankings retain input order, show aligned exact signed values and bars on one shared magnitude scale. `top_k=N` on `render_ranking` explicitly requests stable descending ranking. The hard row budget includes wrapped title/unit/series name and the omission line. `records` retains all source rows; `omitted` counts undisplayed rows, not missing data. Long names fall back to a wrapped exact table rather than ambiguous abbreviations. If that cannot fit, `mode="explanation"` and `reason` explain the omission within the same budgets. `ascii=True` changes bars to `#`, not caller-supplied labels; this view never needs color. For other figures/SVG, the existing complete rendering is returned only if it fits; otherwise a bounded explanation reports that the chart was omitted (`omitted=None`: unknown row count). No chart is cropped.

Both bounded functions return `CompactResult`, retaining `text`, `dimensions`, `records`, `omitted`, `reason` and `mode`, and adding `losses`, `summary()` and a `report` (`RenderResult`). Only `text` is display-bounded: the summary can exceed `cols`/`max_rows` so the agent still receives source facts. `render_ranking` builds its report directly from every supplied label and exact signed value, plus title/unit/name, without importing NumPy or Matplotlib. Figure reports use the existing [figure description contract](#what-the-text-lost-render), including its sampling/rounding, summary omissions and unsupported-artist coverage. Complete-render fallbacks retain the renderer's losses, including when the chart is replaced by an explanation. Native compact bar displays and width-capacity explanations have no measured raster ink: they report source-view clipping and display omissions, not raster occlusion or heatmap sampling. SVG summaries still disclose that source values are unavailable; a width-capacity explanation cannot recover SVG shape diagnostics. Every omitted display adds a material `omitted` loss (`what="display"`, with count/reason in `detail`); this is separate from missing source values and does not remove those values from the report. `CompactResult.losses` uses the same `kind`/`what`/`detail`/`material` schema as `RenderResult.losses`.

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

`render(source, cols=80, *, color=False, strict=False, ascii=False, rows=None)` takes a figure or SVG source (`str` or `bytes`) and returns a `RenderResult` instead of a string. For text-only shortcuts with default drawing and height settings, see [Usage](#usage). `ascii=True` swaps braille, block and shade glyphs for ASCII ones in the same cells (`' - _ / \ |` for lines, `#` for bars, `. : = #` for heat levels, `o x ^ *` for series keys): coarser, and a fraction of the tokens a model spends on braille. `rows` must be `None` or a positive `int` (not `bool`); invalid values raise `ValueError`. It is the preferred height in lines, with a minimum of 8 (SVG input ignores the preference): heatmaps and bar charts take more rows so each data row or bar keeps a line, so a 20-bar `barh` at `rows=12` returns 45 lines. `cols` is the only hard output-size budget; SVG also has fixed [work and image-decode limits](#svg-limits).

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
- `series`: one dict per series: `name`, `kind` (line, errorbar, scatter, bar, barh, histogram, area, heatmap), `axes`, `key` (its glyph in the text, when there are several), `color`, `n` and key values read from the figure's own data, never from the text. Lines and scatters exclude masked and non-finite rows and count them in `missing`; their `points` field holds all eligible rows in data coordinates as an unrounded `(n, 2)` float ndarray, including points outside the axes view. All-missing lines and scatters remain listed with `n=0`, their `missing` count and empty `values` and `points`. Hidden artists (including individual bars) and hidden axes are excluded. A line lists all its points up to 16, else its first and last point and observations nearest about 10 nice x positions, in source order, plus its exact min and max; bars list every bar up to 40, else min and max; seven or more equal-width bars edge to edge retain kind `histogram` for API stability (bins, heights, peak bin), presented as `bars` with `heights:` rather than claiming counts or statistical provenance; a heatmap gives its shape, missing cells and the labelled min and max cells, the whole grid up to 36 cells, else row and column means up to 12 of each; a scatter gives its mean, Pearson r and up to 3 points far off its trend line. Line samples and scatter presentation values are rounded to a step near 1/60 of the smaller of the axis view span and the series' own span (3 significant digits on a log axis, 4 for a constant linear series); numeric line range endpoints retain 4 significant digits. Presentation values are stored as strings; `points` retains the numeric data. Line and scatter timestamps print the precision needed to tell the series' instants apart (day, minute, second or fraction of a second) in the axis timezone, appending the UTC offset only when those formats still collide across a daylight-saving fold. Scatter timestamp precision also includes the displayed mean, while numeric spans use only observations. Axis-formatted positions honour matching explicit tick labels unless two ticks share a label. Heatmap cells first take the tick label nearest their centre within half the local cell pitch, otherwise use axis formatting at the centre; Gouraud meshes use vertex positions and neighbouring vertex spacing instead. For every drawstyle, sampled `(at, ys)` pairs are rounded source observations, never interpolated across gaps or between knots. Step lines retain `drawstyle` to state their pre/post/mid convention. Errorbar containers retain their label; a visible data line stays kind `line`, otherwise the series is `errorbar`. `xerr`/`yerr` list sampled uncertainty strings (symmetric `3`, asymmetric `-1/+2`, unknown `?`), formatted to four significant digits and aligned with `at`/`ys`; missing bounds do not increase the central points' `missing`. Endpoints are converted to data coordinates before computing bounds or inferring centers. Without a data line (`fmt="none"`), centers are segment midpoints, not recoverable asymmetric source centers. One-sided limits (`lolims`, `uplims`, `xlolims`, `xuplims`) are unsupported: all bounds on each affected axis in that container are `?`, with a summary omission; line-free containers with limits are omitted because their centers are unavailable. Sparse errorbars with ambiguous duplicate perpendicular coordinates also have unknown bounds. `not_described` lists `(artist type, count)` pairs for visible unsupported artists; the summary prints a `not described:` coverage line, e.g. `2 Wedge`, without changing render losses or supported features. Pies and contours receive coverage counts, not values; annotations and axes decorations are outside this coverage audit.
- `scales`: per visible data axes (excluding colorbar axes), the title and each axis's label, kind (linear, log, date, category) and range.
- `losses`: what the renderer detects the text does not show (see [known limits](#known-limits-of-strict)), as dicts with `kind`, `what`, `detail` and `material`. Kinds: `lost_artist` (a data artist that drew nothing or lost all visible ink to text resolution), `occluded` (all its measured raster cells covered by later opaque primitives, independent of colour; non-material), `clipped_data` (points outside the axes view; matplotlib hides them too, so not material), `series_label` (a legend entry dropped or cut), `text` (a title, label or tick dropped or cut), `unsupported` (an approximated SVG effect; see [SVG limits](#svg-limits)), and for SVG `lost_series`. Heatmaps also report `heat_sampled` (non-material: original source shape, sampled text-grid size in rows × columns, and approximate source-cell count per distinct sampled source cell; repeated text cells do not count as extra source samples) and `lost_extreme` (material: an unsampled finite source min/max cell inside the view whose quantised level differs from the cell shown at its position and is absent from the sampled grid). Extreme cells include original source row/column indices, values and axis labels when available, even when empty rows are collapsed for display. Masked and non-finite cells are excluded. Min/max selection uses source values before colour normalisation; loss comparisons use quantised levels after normalisation, so an extreme is not lost if its level is shown elsewhere. Increase `cols` and/or `rows` to reduce sampling; no pooling or display-mode change is applied.
- `warnings`: notes about how the input was read, such as strokes taken for gridlines by colour. One entry counts skipped hidden artists and axes; a hidden axes counts once, not once per child artist.
- `supported_features`: what this kind of input lets the renderer know. A figure has `artist_roles`, `source_values` and `artist_losses`; SVG has shapes only, so those are false.

`summary()` is the compact form for an agent: scales, series values and losses in a few lines, far fewer tokens than the chart itself. Lines that share their x positions share one `lines at x:` row. For SVG input it says `values unavailable`: SVG carries shapes, not data, so a series is a colour and a kind with no values. The summary's `losses:` line still lists render losses only. Step lines now carry `drawstyle` (e.g. `steps-post`, right-continuous) so straight and step controls differ. Separate `summary_omissions` disclose unavailable sample support for errorbars (and midpoint-inferred centers without a data line), unsupported one-sided limits and paired bounds/sample support for filled areas; global extrema are not per-x bounds. Sample denominators and risk sets are not inferred from geometry. Counts such as line `n` count plotted points, not subjects. See `series` above for errorbar bounds and unsupported-artist coverage.

Artist text and labels are sanitised: ANSI/OSC sequences and C0/C1 controls (including DEL) are removed, except layout newlines and tabs. Renderer-generated ANSI styling remains available with `color=True`. Summary titles and axis labels join newlines with ` / ` and escape colons as `\:` so labels cannot introduce diagnostic field markers; series names remain `repr`-quoted. Text escaping is hygiene, not a guarantee that a model ignores a malicious label.

`strict=True` raises `RenderLossError` when a loss is material. Material losses include a data artist or series lost to text resolution, a cut or dropped legend entry, a heatmap extreme level lost to sampling (`lost_extreme`), and the unsupported SVG effects marked material in [SVG limits](#svg-limits). Dropped tick labels and points outside the axes view (`clipped_data`, which matplotlib hides as well) are not material, so the example above passes `strict=True`. The error's `result` holds the full `RenderResult`.

Visibility is accounted per matplotlib artist, not per colour or subplot, using measured raster cells rather than a whole-source coverage proof. Opaque fills (`alpha >= 0.95`) hide earlier strokes; later strokes remain visible, subject to the crossing limits below. Translucent fills alone keep strokes on top but cannot undo earlier opaque coverage. Source-path coincidence checks distinguish identical overplotted curves from nearby curves merged only by text resolution; checks are conservative for differently sampled non-monotone curves, so uncertain covering remains material loss. Owner accounting may reveal previously undetected losses: at 80 columns, three small bins in gallery `25_sns_hist_kde` are visible in Agg but disappear beneath the KDE at text resolution (one aggregated material loss; see `test_gallery_histogram_loss_is_newly_detected_not_source_occlusion` in [`tests/test_result.py`](tests/test_result.py)).

#### Known limits of `strict`

`strict=True` passes these, so the text can still mislead:

- Scalar-grid images and regular meshes determine opacity from artist alpha, not colormap alpha. A translucent colormap cell can therefore hide earlier ink and report non-material `occluded`.
- Intersecting neutral box-drawing arms share one painter sequence, and cap/whisker crossing exceptions can bypass intervening opaque fills. Covered ink can reappear without a material diagnostic.
- A heatmap larger than the text grid uses centre sampling (`heat_sampled`). `lost_extreme` checks min/max levels only: skipped non-extreme cells, spatial patterns and the positions of tied extrema can still be lost without a material diagnostic.
- SVG clipping approximations do not fail strict mode; see the [SVG effects table](#svg-limits).

### What a mark means

For matplotlib figures the renderer asks each artist what it is, so colour never decides it. Lines, collections, patches and images on an axes are data: a black contour, light gray bars or a big dark filled area draw like any other colour, and only a fill the colour of the page (a white bar) is left out so its edge draws. Spines and axes are the frame, the figure and axes patches are background, legends give the series keys, `ax.text` boxes are not drawn and an annotation arrow is plain ink, never a series. Gridlines are not drawn. Series keys still follow colour: two artists of one colour share a key. Artists matplotlib does not list on a figure or axes (plotnine draws its legend straight into the figure) are judged by where they sit and how they look.

SVG carries no artist information. The supported subset:

- shapes: `path` (all commands, curves and arcs flattened), `rect`, `line`, `polyline`, `polygon`, `circle`, `ellipse`, `use`, `text`/`tspan`, and base64 PNG `image`
- presentation attributes and inline `style`: fill, stroke, their opacities, `stroke-width`, `stroke-dasharray`, `font-size`, `text-anchor`, `dominant-baseline`, `display`, `visibility`, inherited through groups; `transform` with translate, scale, rotate and matrix (skew is ignored)
- clipping and effect approximations as described in [SVG limits](#svg-limits); markers and `<style>` sheets are skipped
- meaning from classes and ids: `legend` marks legend keys; plotly `gridlayer`/`minor-gridlayer` and vega `role-axis-grid` are gridlines (not drawn); plotly axis and zero-line layers and vega `role-axis` are the frame; vega `background` is background; shapes inside matplotlib text, tick and annotation groups are skipped

#### SVG limits

SVG traversal has a fixed work budget of 50,000 element visits per rendering pass, counting ID indexing, each `<use>` expansion, text descendants, paint-server scans and clip-child collection. Repeated inspections count again; a layout retry for overflowing left labels starts a new pass. The maximum nesting depth is 256 (the root is depth 0), including expanded text and effect references, so cycles stop at the depth limit. Exceeding either raises `ValueError` naming the limit; the work-budget error also gives the visited count. Root width and height, taken from `viewBox` when present or otherwise `width`/`height`, must be finite and positive, checked before canvas allocation. Embedded PNGs are limited to 16,000,000 pixels per image: dimensions are checked in the PNG header before decoding; larger images raise `ValueError`. Duplicate or noninitial PNG IHDR chunks and truncated chunks are rejected before decoding. Non-PNG base64 images and unresolved `<use>` references are skipped with `warnings`. No external resources are fetched. Group opacity multiplies into child opacity; shapes and text with effective opacity at or below 0.05 are not drawn.

A clip containing one axis-aligned rectangle in user space is honoured outside tspans; text is kept or dropped whole by its anchor.

| SVG effect | Approximation (reported as `unsupported` in losses and the text) | Material (`strict=True` raises) |
| --- | --- | --- |
| Mask | Drawn unmasked | Yes |
| Gradient | Flat first stop colour, or mid-grey when absent; unknown paint references also use this fallback | Yes |
| Pattern | Flat mid-grey | Yes |
| Filter | Drawn unfiltered | Yes |
| Clip other than one axis-aligned user-space rectangle, or any tspan-local clip | Drawn unclipped | No |

Mask, filter and unsupported clip-path references in presentation attributes or inline `style` are reported on traversed shapes, containers, text and tspans, independently of paint-channel consumption. Fill and stroke paint references in either form are resolved and reported only for enabled, geometrically applicable channels on shapes and nonempty text runs, including inherited paints, not on non-painting containers whose descendants override them. Enabled URL strokes are reported even when the renderer's filled-shape shortcut omits outline ink; disabled strokes are not. Collinear contours do not consume fill paints. Text visibility is checked per run using its effective fill and stroke opacities. Real mask, gradient, pattern and filter rendering and `<style>` sheet parsing remain unsupported.

Everything else is unknown and judged by appearance: its strokes are all kept, short segments included, except that a light gray axis-aligned stroke is taken for a gridline; a big neutral fill is taken for the page or panel; a shape the colour of the page is dropped.

`cols` is a terminal-cell budget for every output line, including titles, legends, color keys and captions. CJK characters use two cells; combining marks and ANSI styling do not add cells. Emoji modifiers, ZWJ sequences, flags and keycaps stay intact when measuring, wrapping and slicing, using `wcwidth`'s terminal widths rather than full Unicode grapheme segmentation. Color keys wrap between complete numeric ranges, using compact notation for extreme values. In `render`, `render_figure` and `render_svg`, widths too small for a single character or key entry raise `ValueError` rather than emitting an overwide line. The [bounded display path](#bounded-displays-and-preferences) translates these display-capacity failures into omission metadata; malformed-source errors still propagate.

## Extras

The core package depends on numpy, matplotlib and wcwidth. The source-only example gallery ([`examples/gallery.py`](examples/gallery.py), 50 charts, with data in `examples/data/gas.csv`) needs pandas; the charts built with other libraries need those libraries too. From a source checkout:

```
uv pip install -e '.[gallery]'
```

That installs pandas, seaborn, plotly, altair and plotnine. The gallery and its CSV are not included in the wheel; `trendsetter_axi.gallery` has been removed. In a source checkout, use `from examples.gallery import CHARTS` or run the demo below.

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

Importing `trendsetter_axi` itself now loads neither NumPy nor Matplotlib. Vector SVG rendering loads NumPy but not Matplotlib; embedded PNG decoding loads Matplotlib, as does figure rendering. The default install is unchanged. See [startup/compact measurements](benchmarks/first-three-changes.md).

## Examples

These were produced by running gallery charts through `render_figure(fig, 80, color=True)`. The screenshots use a dark terminal background with no gaps between character rows. Regenerate them and their exact plain-text versions with `python examples/readme_charts.py` (requires the `dev` extra).

Line chart (gallery id `01_mpl_line`):

![Blue braille line chart on a dark terminal: inflation-adjusted Houston gas prices from 2000 to 2026, peaking near $6 per gallon in 2008.](docs/01_mpl_line.png)

[Exact plain text](docs/01_mpl_line.txt).

Bar chart (gallery id `04_mpl_bar`):

![Blue block bar chart on a dark terminal: yearly mean Houston gas prices for 2016–2025, with exact labels and the highest bar at $3.45 per gallon in 2022.](docs/04_mpl_bar.png)

[Exact plain text](docs/04_mpl_bar.txt).

Heatmap (gallery id `10_mpl_imshow`):

![Viridis heatmap on a dark terminal: monthly inflation-adjusted gas prices for 2016–2025, with a $2.00–$5.16 per gallon color key and the brightest cells in spring and summer 2022.](docs/10_mpl_imshow.png)

[Exact plain text](docs/10_mpl_imshow.txt).

## Demo

One fixed, deterministic tour: basic charts, the same chart at 100/60/40/24 columns with measured max line width, a 100k-point render with timing, a CJK title, `render_svg`, and six gallery charts.

```
python examples/demo.py
python examples/demo.py --cols 100 --section widths --section gallery
```

Sections: `basic`, `widths`, `big`, `cjk`, `svg`, `gallery`. The `gallery` section needs pandas: `uv pip install -e '.[dev]'`. Chart text is identical run to run; only the `[timing]` line varies.

### Scatter brush prototype (not in the package)

![Standalone scatter brush prototype on synthetic account data, with a selection brush and linked statistics](docs/scatter-brush.gif)

This is a standalone interaction prototype on synthetic data, not a feature of
`trendsetter_axi`. It does not use the renderer and is not included in the installed
package. The script uses only Python's standard library.

From a source checkout, run in a POSIX terminal with mouse reporting and 24-bit
colour, at least 80 columns × 20 rows:

```sh
python examples/scatter_brush.py
```

Drag to brush; drag inside the brush to move it. Hover to inspect, click a table
row to pin an account, `z` to zoom to the brush, `b` to go back, `x` to clear,
`1`/`2`/`3` to toggle segments, and `q` to quit.

## Development

```
uv venv .venv
uv pip install -e '.[dev]' --python .venv/bin/python
.venv/bin/python -m pytest
```

The renderer regression fixtures live in `tests/test_selfchecks.py` and run with pytest (or alone with `python -m pytest tests/test_selfchecks.py`). The former `python -m trendsetter_axi.mpl --test` entry point has been removed.

Raster sampling clips each segment to the viewport first, caps samples at terminal resolution, and reduces redundant ink to occupied dots without bridging NaN gaps. See [render budgets and before/after profiling](benchmarks/README.md) for reproducible timings and work limits.

## License

MIT. See `LICENSE`.
