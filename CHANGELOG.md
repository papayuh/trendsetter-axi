# Changelog

## Unreleased

- Add experimental `from_figure(fig)` chart records and `query(record, operation, *args)` with evidence, interpolation conventions and explicit unavailable results. Records retain source arrays, paired bands, bar bases/tops, segments, heat grids and author declarations. Queries cover values, widths, source-row predicates, crossings, attached-record counts, claims, exact diffs and geometry-only facts; `python -m trendsetter_axi.queries` queries saved JSON without importing NumPy or matplotlib. Existing rendering and summary text are unchanged. See [experimental records](README.md#experimental-chart-records-and-queries) for scope and follow-ups.

- Replace the unavailable PyPI install with a GitHub install and retain the editable source route. Refresh the README overview of source summaries and loss diagnostics; benchmark numbers remain labelled with measured commit `9288d2b`.
- Ship the scatter brush in the package: `interact(fig)` and `python -m trendsetter_axi.interact record.json` add exact scatter/line/bar hover and scatter box-select with live linked statistics and marginals. `render_styled(fig)` prints the same styled terminal drawing without interaction. POSIX terminal handling uses only the standard library and restores modes on quit, errors, Ctrl-C and termination. Unsupported figures fall back to a static chart; unsupported saved records show a data overview. Existing `render`, summaries and public chart records stay unchanged. Replace the standalone demo with an actual matplotlib figure and re-record the README GIF plus a static screenshot from the packaged feature.

- Remove the documented `trendsetter_axi.gallery` module from the installed package: all 50 charts and their CSV now live in `examples/gallery.py` and `examples/data/gas.csv` in the source checkout. Use `from examples.gallery import CHARTS` there, or `python examples/demo.py --section gallery`; the `gallery` extra still installs the optional chart libraries. Move the Matplotlib self-checks to `tests/test_selfchecks.py` and remove `python -m trendsetter_axi.mpl --test`; run them with `python -m pytest tests/test_selfchecks.py`. Rendering APIs are unchanged.

- Require Matplotlib >=3.10.0 and NumPy >=1.23.0, verified together on Python 3.10. Test latest dependencies on Python 3.10, 3.12 and 3.14, plus the dependency floors and a clean, non-editable wheel install with figure/SVG rendering and the renderer regression fixtures. Python classifiers now match the CI matrix; see [installation requirements](README.md#install).

- Preserve source summaries and loss reports in `CompactResult`, including bounded explanations; document `render_figure` and `render_svg` as text-only shortcuts. See [bounded displays](README.md#bounded-displays-and-preferences) for report scope and omission diagnostics.

- Fix opaque-fill painter order and colour-dependent artist-loss verdicts; see the [loss contract](README.md#what-the-text-lost-render) for occlusion reporting, newly detected gallery losses and remaining limits.

- Batch dense neutral data lines to avoid per-segment rendering overhead; see [usage](README.md#usage) for scope and compatibility.
- Add heatmap sampling diagnostics without changing rendered text; see the [loss contract](README.md#what-the-text-lost-render) for `heat_sampled`, `lost_extreme` and mitigation.
- Validate `render(rows=...)` as `None` or a positive integer excluding booleans; the height remains preferred (minimum 8), not a hard cap.
- Keep emoji skin-tone modifiers, variation selectors, keycaps and tag sequences with their base when measuring, wrapping and slicing terminal cells.
- Sanitise artist text and scale labels by removing terminal escape sequences and control characters while preserving layout newlines/tabs and renderer-generated ANSI colour. Summary titles/axis labels flatten newlines and escape colons; series names remain quoted. This is text hygiene, not protection against model prompt injection.

- Expand summaries to describe errorbar bounds and disclose unsupported artists; see the [summary contract](README.md#what-the-text-lost-render) for coverage and limitations.
- Replace statistical claims in compact touching-bar summaries with neutral wording; compatibility details are in the [summary contract](README.md#what-the-text-lost-render).
- Fix `summary()` identity and precision for heatmaps, small numeric series, timestamps, scatter means and explicit tick labels; see the [summary contract](README.md#what-the-text-lost-render).
- Bound SVG traversal and PNG decoding, validate root sizes, report unsupported effects and skipped resources, and propagate group opacity. See [SVG limits](README.md#svg-limits) for budgets, approximations and strict-mode materiality.

- Defer format-specific imports: package import, native rankings and scalar responses load neither NumPy nor Matplotlib; vector SVG does not load Matplotlib. Default dependencies are unchanged.
- Opt-in `render_ranking` and `render_compact` enforce hard row and cell budgets, with exact signed values, wrapped table fallback and structured display omissions; legacy `render(rows=...)` remains a preference.
- `present` resolves explicit/session/saved/automatic display preferences against a caller-supplied surface, bypasses rendering for scalars and requires a confirmed user-visible callback for images. The harness owns persistence and delivery.
- Step lines record drawstyle. Add `summary_omissions` separately from render losses; see the [summary contract](README.md#what-the-text-lost-render).
- Documentation: strict mode, `rows`, summary rounding and the benchmark threshold now state exactly what is checked and measured.
- `render(source, cols=80, *, color=False, strict=False)` returns a `RenderResult`: `text`, `dimensions`, `series`, `scales`, `warnings`, `losses` and `supported_features`. `render_figure` and `render_svg` still return the same string.
- Report render losses and support `strict=True`; see the [loss contract](README.md#what-the-text-lost-render) for loss kinds and materiality.
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
