# trendsetter-axi

Terminal charts. trendsetter-axi renders matplotlib figures and SVG as unicode text (braille lines, block bars, shaded heatmaps) that fits a fixed number of columns. Formerly prototyped as "termchart".

## Why

More analysis now happens in a terminal, next to an agent, with no IDE or notebook open. trendsetter-axi takes the matplotlib code you already have and makes one render serve both readers: a chart the person can read where they work, and a compact account of the same figure that an agent can check.

```python
from trendsetter_axi import render

r = render(fig, cols=80, strict=True)   # your existing figure; raises RenderLossError if the text would misrepresent it
print(r.text)                           # for the person: every line fits 80 cells
context = r.summary()                   # for the agent: scales, series values from the figure's data, what was lost
```

- Output budget: `cols` bounds every line, titles and keys included; `r.dimensions` reports the width and height used.
- Diagnostics: `r.losses` lists everything the text does not show, and `strict=True` turns a material loss into an error instead of a misleading chart.

What it saves, measured on 81 questions about 25 charts with `claude-sonnet-5-5` ([benchmark](benchmarks/agent/README.md)): the summary answered 86% at a median 94 tokens per chart; a 640×480 PNG answered 99% at 408; the 80-column text answered 81% at 639. The token saving comes from `summary()`, not from the text chart, and when the model can take images the PNG is the more accurate input.

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

### What the text lost: `render`

`render(source, cols=80, *, color=False, strict=False)` takes a figure or SVG source (`str` or `bytes`) and returns a `RenderResult` instead of a string. Its `text` is exactly what `render_figure` / `render_svg` return.

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
x: x, linear, 0.8..5.2
y: y, linear, 0..6
line 'demand' n=5 x=1..5 y=2..7 1=2 2=4 3=3 4=5 5=7
losses: clipped_data Line2D 'demand': 1 of 5 points outside the axes view
```

Fields:

- `text`: the chart.
- `dimensions`: `cols` (the budget), `width` (widest line) and `height` (lines), in terminal cells.
- `series`: one dict per series: `name`, `kind` (line, scatter, bar, barh, area, heatmap), `axes`, `key` (its glyph in the text, when there are several), `color`, `n` and key values read from the figure's own data, never from the text. A line lists all its points up to 8, else first, last, min and max; bars list every bar up to 12, else min and max; a heatmap gives its shape, missing cells and the labelled min and max cells.
- `scales`: per axes, the title and each axis's label, kind (linear, log, date, category) and range.
- `losses`: everything the text does not show, as dicts with `kind`, `what`, `detail` and `material`. Kinds: `lost_artist` (a data artist that drew nothing or ended with no visible cell, such as a line hidden under another), `clipped_data` (points outside the axes view; matplotlib hides them too, so not material), `series_label` (a legend entry dropped or cut), `text` (a title, label or tick dropped or cut), `unsupported` (an SVG clip drawn unclipped), and for SVG `lost_series`.
- `warnings`: notes about how the input was read, such as strokes taken for gridlines by colour.
- `supported_features`: what this kind of input lets the renderer know. A figure has `artist_roles`, `source_values` and `artist_losses`; SVG has shapes only, so those are false.

`summary()` is the compact form for an agent: scales, series values and losses in a few lines, far fewer tokens than the chart itself. For SVG input it says `values unavailable`: SVG carries shapes, not data, so a series is a colour and a kind with no values.

`strict=True` raises `RenderLossError` when a loss is material, that is when the text would misrepresent the chart: a lost data artist or series, or a cut legend entry. Dropped tick labels and points outside the axes view (`clipped_data`, which matplotlib hides as well) are not material, so the example above passes `strict=True`. The error's `result` holds the full `RenderResult`.

Lost artists are found by series colour: an artist that shares its colour with one that drew counts as drawn.

### What a mark means

For matplotlib figures the renderer asks each artist what it is, so colour never decides it. Lines, collections, patches and images on an axes are data: a black contour, light gray bars or a big dark filled area draw like any other colour, and only a fill the colour of the page (a white bar) is left out so its edge draws. Spines and axes are the frame, the figure and axes patches are background, legends give the series keys, `ax.text` boxes are not drawn and an annotation arrow is plain ink, never a series. Gridlines are not drawn. Series keys still follow colour: two artists of one colour share a key. Artists matplotlib does not list on a figure or axes (plotnine draws its legend straight into the figure) are judged by where they sit and how they look.

SVG carries no artist information. The supported subset:

- shapes: `path` (all commands, curves and arcs flattened), `rect`, `line`, `polyline`, `polygon`, `circle`, `ellipse`, `use`, `text`/`tspan`, and base64 PNG `image`
- presentation attributes and inline `style`: fill, stroke, their opacities, `stroke-width`, `stroke-dasharray`, `font-size`, `text-anchor`, `dominant-baseline`, `display`, `visibility`, inherited through groups; `transform` with translate, scale, rotate and matrix (skew is ignored)
- `clip-path` as described above; gradients, patterns, masks, markers, filters and `<style>` sheets are skipped
- meaning from classes and ids: `legend` marks legend keys; plotly `gridlayer`/`minor-gridlayer` and vega `role-axis-grid` are gridlines (not drawn); plotly axis and zero-line layers and vega `role-axis` are the frame; vega `background` is background; shapes inside matplotlib text, tick and annotation groups are skipped

Everything else is unknown and judged by appearance: its strokes are all kept, short segments included, except that a light gray axis-aligned stroke is taken for a gridline; a big neutral fill is taken for the page or panel; a shape the colour of the page is dropped.

`cols` is a terminal-cell budget for every output line, including titles, legends, color keys and captions. CJK characters use two cells; combining marks and ANSI styling do not add cells. Color keys wrap between complete numeric ranges, using compact notation for extreme values. Widths too small for a single character or key entry raise `ValueError` rather than emitting an overwide line.

## Extras

The core package depends on numpy, matplotlib and wcwidth. The example gallery (`trendsetter_axi.gallery`, 50 charts) needs pandas; the charts built with other libraries need those libraries too:

```
uv pip install -e '.[gallery]'
```

That installs pandas, seaborn, plotly, altair and plotnine.

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
