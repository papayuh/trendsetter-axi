# Changelog

## Unreleased

- `render(source, cols=80, *, color=False, strict=False)` returns a `RenderResult`: `text`, `dimensions`, `series`, `scales`, `warnings`, `losses` and `supported_features`. `render_figure` and `render_svg` still return the same string.
- Losses count data artists that drew nothing or ended with no visible cell, data points outside the axes view, cut legend entries and dropped or cut text.
- `strict=True` raises `RenderLossError` on a material loss: a lost data artist or series, or a cut legend entry. Points outside the axes view are reported but not material, since matplotlib hides them too.
- `summary()` maps reference lines and shading drawn in axes or blended coordinates (`axhline`, `axvline`) back to data values.
- `RenderResult.summary()`: compact scales, series values and losses read from the figure's data; SVG input says values are unavailable.
- `color=True` on `render_figure` and `render_svg` adds 24-bit ANSI colour.
- `summary()` carries enough to answer from: every point of a line up to 16 (else first, last, ~10 evenly spaced points and the exact extremes) with one shared x row for lines that share x, every bar up to 40, histograms as bins and counts, small heatmaps in full and larger ones as row and column means, scatter mean, r and outliers. Numbers round to ~1/60 of the axis span; linear axes no longer print their view range. On the agent benchmark: 98% (dev) and 95% (held-out) at a median 102 and 114 tokens, from 86% and 90%.
- `render(..., ascii=True)` draws the same cells in ASCII glyphs, and `render(..., rows=N)` sets a figure's height in lines.
- `benchmarks/agent`: the same 81 questions about 25 charts answered from the 80-column text, `summary()`, a PNG, mpl_ascii and plotext text, and no chart, with accuracy, tokens and latency per format. README gains a "Why" section with the integration path and those numbers.

## 0.1.0

First release.

- Terminal chart renderer: `render_figure` (matplotlib) and `render_svg` (SVG source) draw charts as unicode text (braille lines, block bars, shaded heatmaps).
- `cols` is a terminal-cell budget for every output line, including titles, legends, color keys and captions. Wide (CJK) characters count as two cells, combining marks and ANSI styling as zero. Widths too small to fit raise `ValueError`.
- Work budgets on cell and raster output bound render cost.
- Example gallery (`trendsetter_axi.gallery`, 50 charts) behind the `gallery` extra.
