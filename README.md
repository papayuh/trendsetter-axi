# trendsetter-axi

Terminal charts. trendsetter-axi renders matplotlib figures and SVG as unicode text (braille lines, block bars, shaded heatmaps) that fits a fixed number of columns. Formerly prototyped as "termchart".

## Install

PyPI publication is not done yet, so install from source for now:

```
git clone https://github.com/papayuh/trendsetter-axi
cd trendsetter-axi
uv pip install -e .
```

Once published this will be `uv pip install trendsetter-axi`.

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

### What a mark means

For matplotlib figures the renderer asks each artist what it is, so colour never decides it. Lines, collections, patches and images on an axes are data: a black contour, light gray bars or a big dark filled area draw like any other colour. Spines and axes are the frame, the figure and axes patches are background, legends give the series keys, `ax.text` boxes are not drawn and an annotation arrow is plain ink, never a series. Gridlines are not drawn. Series keys still follow colour: two artists of one colour share a key. Artists matplotlib does not list on a figure or axes (plotnine draws its legend straight into the figure) are judged by where they sit and how they look.

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
