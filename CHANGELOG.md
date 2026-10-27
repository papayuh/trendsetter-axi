# Changelog

## Unreleased

- Defer format-specific imports: package import, native rankings and scalar responses load neither NumPy nor Matplotlib; vector SVG does not load Matplotlib. Default dependencies are unchanged.
- Opt-in `render_ranking` and `render_compact` enforce hard row and cell budgets, with exact signed values, wrapped table fallback and structured display omissions; legacy `render(rows=...)` remains a preference.
- `present` resolves explicit/session/saved/automatic display preferences against a caller-supplied surface, bypasses rendering for scalars and requires a confirmed user-visible callback for images. The harness owns persistence and delivery.
- Step lines record drawstyle. Separate `summary_omissions` disclose unrepresented errorbar endpoints, filled-area paired bounds and sample support without changing render losses or strict-mode materiality.
- Documentation: strict mode, `rows`, summary rounding and the benchmark threshold now state exactly what is checked and measured.
- `render(source, cols=80, *, color=False, strict=False)` returns a `RenderResult`: `text`, `dimensions`, `series`, `scales`, `warnings`, `losses` and `supported_features`. `render_figure` and `render_svg` still return the same string.
- Losses count data artists that drew nothing or ended with no visible cell, data points outside the axes view, cut legend entries and dropped or cut text.
- `strict=True` raises `RenderLossError` on a material loss: a lost data artist or series, or a cut legend entry. Points outside the axes view are reported but not material, since matplotlib hides them too.
- `summary()` maps reference lines and shading drawn in axes or blended coordinates (`axhline`, `axvline`) back to data values.
- `RenderResult.summary()`: compact scales, series values and losses read from the figure's data; SVG input says values are unavailable.
- `color=True` on `render_figure` and `render_svg` adds 24-bit ANSI colour.
- `summary()` carries enough to answer from: every point of a line up to 16 (else first, last, ~10 evenly spaced points and the exact extremes) with one shared x row for lines that share x, every bar up to 40, histograms as bins and counts, small heatmaps in full and larger ones as row and column means, scatter mean, r and outliers. Numbers round to ~1/60 of the axis span; linear axes no longer print their view range. On the agent benchmark: 98% (dev) and 95% (held-out) at a median 102 and 114 tokens, from 86% and 90%.
- Line and scatter `series` exclude masked and non-finite rows from counts, means and samples and count them in `missing`; sampled lines of every drawstyle quote observed source pairs, never interpolated values. Hidden artists and hidden axes are skipped and counted in one warning. Lines and scatters gain `points`, their eligible rows as an `(n, 2)` float array. The clipping check ignores masked scatter points.
- `render(..., ascii=True)` draws the same cells in ASCII glyphs, and `render(..., rows=N)` sets a figure's preferred height in lines (heatmaps and bar charts take more so each row or bar keeps a line).
- `benchmarks/agent`: the same 81 questions about 25 charts answered from the 80-column text, `summary()`, a PNG, mpl_ascii and plotext text, and no chart, with accuracy, tokens and latency per format. README gains a "Why" section with the integration path and those numbers.

## 0.1.0

First release.

- Terminal chart renderer: `render_figure` (matplotlib) and `render_svg` (SVG source) draw charts as unicode text (braille lines, block bars, shaded heatmaps).
- `cols` is a terminal-cell budget for every output line, including titles, legends, color keys and captions. Wide (CJK) characters count as two cells, combining marks and ANSI styling as zero. Widths too small to fit raise `ValueError`.
- Work budgets on cell and raster output bound render cost.
- Example gallery (`trendsetter_axi.gallery`, 50 charts) behind the `gallery` extra.
