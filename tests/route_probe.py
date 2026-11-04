"""Deterministic public-output probe, also run against a git-archive baseline."""
import json
import sys

if '--eager' in sys.argv:
    from trendsetter_axi import core, mpl, svg
import trendsetter_axi as axi

SVG = '<svg width="200" height="100"><path d="M10 80 L80 20 L180 60" fill="none" stroke="blue"/></svg>'
results = []
for source in (SVG, SVG.encode()):
    for cols in (40, 60):
        for ascii in (False, True):
            for strict in (False, True):
                try:
                    r = axi.render(source, cols=cols, ascii=ascii, strict=strict)
                    results.append([r.text, r.summary(), r.dimensions, r.losses, r.series, r.scales])
                except axi.RenderLossError as error:
                    results.append(['error', str(error), error.result.text])
        results.append(axi.render_svg(source, cols))
        results.append(axi.render_svg(source, cols, color=True))
from matplotlib.figure import Figure
for kind in ('line', 'bar', 'heat'):
    ax = Figure(figsize=(6, 3)).subplots()
    if kind == 'line':
        ax.plot([1, 2, 3], [2, 4, 3], label='one')
    elif kind == 'bar':
        ax.barh(['north', 'south'], [-2, 3], label='one')
    else:
        ax.imshow([[0, 50], [100, float('nan')]], vmin=0, vmax=100)
    ax.set_title('Route probe')
    for cols in (40, 60):
        results.append(axi.render_figure(ax.figure, cols))
        for ascii in (False, True):
            try:
                r = axi.render(ax.figure, cols, ascii=ascii, strict=True)
                results.append([r.text, r.summary(), r.dimensions, r.losses, r.series, r.scales])
            except axi.RenderLossError as error:
                results.append(['error', str(error), error.result.text])
# Line/scatter points are ndarrays; normalize them only for this lazy/eager comparison.
print(json.dumps(results, sort_keys=True, default=lambda array: array.tolist()))
