# Changelog

## 0.1.0

First release.

- Terminal chart renderer: `render_figure` (matplotlib) and `render_svg` (SVG source) draw charts as unicode text (braille lines, block bars, shaded heatmaps).
- `cols` is a terminal-cell budget for every output line, including titles, legends, color keys and captions. Wide (CJK) characters count as two cells, combining marks and ANSI styling as zero. Widths too small to fit raise `ValueError`.
- Work budgets on cell and raster output bound render cost.
- Example gallery (`trendsetter_axi.gallery`, 50 charts) behind the `gallery` extra.
