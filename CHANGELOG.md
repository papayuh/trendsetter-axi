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
- Expand `summary()` source-value coverage and compact numeric formatting; see the [summary contract](README.md#what-the-text-lost-render) and [measured benchmark results](benchmarks/agent/RESULTS.md).
- Fix line/scatter summary eligibility, sample observed source pairs, expose numeric `points` and warn on hidden artists. Masked scatter rows no longer trigger clipping losses. See the [summary contract](README.md#what-the-text-lost-render).
- `render(..., ascii=True)` draws the same cells in ASCII glyphs, and `render(..., rows=N)` sets a figure's preferred height in lines (heatmaps and bar charts take more so each row or bar keeps a line).
- `benchmarks/agent`: the same 81 questions about 25 charts answered from the 80-column text, `summary()`, a PNG, mpl_ascii and plotext text, and no chart, with accuracy, tokens and latency per format. README gains a "Why" section with the integration path and those numbers.
- `benchmarks/agent/run.py`: rows are graded only when their chart hash matches `manifests/<tag>.json` (excluded rows are counted in RESULTS.md); numbers must parse as a finite number instead of having stray characters stripped, so `"1/0"` or `"10 or 11"` no longer score as 10; the default run asks every format in RESULTS.md (`ascii`, `ascii_tall` and `hybrid` included); charts missing a format are listed as incomplete instead of silently dropped; `--replicate N` repeats every call under tag `TAG#N` without reuse; `meets()` checks an accuracy threshold in integers.

## 0.1.0

First release.

- Terminal chart renderer: `render_figure` (matplotlib) and `render_svg` (SVG source) draw charts as unicode text (braille lines, block bars, shaded heatmaps).
- `cols` is a terminal-cell budget for every output line, including titles, legends, color keys and captions. Wide (CJK) characters count as two cells, combining marks and ANSI styling as zero. Widths too small to fit raise `ValueError`.
- Work budgets on cell and raster output bound render cost.
- Example gallery (`trendsetter_axi.gallery`, 50 charts) behind the `gallery` extra.
