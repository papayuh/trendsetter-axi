"""Render matplotlib figures and SVG as unicode text for the terminal."""
import copy, itertools

from matplotlib.category import UnitData

from . import mpl as _mpl, result as _result, svg as _svg
from .result import RenderLossError, RenderResult

__version__ = "0.1.0"


def _copy(fig):
    """Deep copy of a figure. plotnine's __deepcopy__ methods keep links to the original figure's artists, so objects holding them are copied plainly."""
    memo = {id(a.units._counter): itertools.count(len(a.units._mapping))
            for ax in fig.axes for a in (ax.xaxis, ax.yaxis) if isinstance(a.units, UnitData)}
    artists = {id(a) for a in fig.findobj()}
    holds = lambda v: id(v) in artists or isinstance(v, list) and any(id(x) in artists for x in v)
    shells, seen, todo = [], set(), [fig.get_layout_engine()]
    while todo:
        o = todo.pop()
        if id(o) in seen:
            continue
        seen.add(id(o))
        if isinstance(o, (list, tuple)):
            todo.extend(o)
        elif isinstance(o, dict):
            todo.extend(o.values())
        elif type(o).__module__.startswith("plotnine"):
            todo.extend(getattr(o, "__dict__", {}).values())
            if hasattr(type(o), "__deepcopy__") and any(map(holds, vars(o).values())):
                memo[id(o)] = object.__new__(type(o))
                shells.append(o)
    work = copy.deepcopy(fig, memo)
    for o in shells:
        memo[id(o)].__dict__.update(copy.deepcopy(o.__dict__, memo))
    return work


def _figure(fig, cols, color, result):
    work = _copy(fig)
    try:
        text, meta = _mpl.render(work, cols, color)
        if not result: return text
        return _result.build(text, meta, cols, *_mpl.describe(fig, meta), _mpl.losses(work, meta), _result.FIGURE)
    finally:
        if work.canvas.manager is not None:
            import matplotlib.pyplot as plt
            plt.close(work)


def render_figure(fig, cols=80, color=False):
    """Render a matplotlib Figure at most `cols` terminal cells wide per line. The figure itself is left unchanged.
    color=True adds 24-bit ANSI colour; it never changes the cell width."""
    return _figure(fig, cols, color, False)


def render_svg(svg_text, cols=80, color=False):
    """Render SVG source (plain text, e.g. from matplotlib with svg.fonttype='none') as text."""
    return _svg.render(svg_text, cols, ansi=color)[0]


def render(source, cols=80, *, color=False, strict=False):
    """Render a matplotlib Figure or SVG source (str or bytes) and report what the text lost, as a RenderResult.

    strict=True raises RenderLossError when the text would misrepresent the chart: a data artist or series with no
    visible cell, data points outside the axes view, or a legend entry dropped or cut."""
    if isinstance(source, (str, bytes)):
        text, meta = _svg.render(source, cols, ansi=color)
        series, scales, lost = _result.svg_series(meta)
        res = _result.build(text, meta, cols, series, scales, lost, _result.SVG)
    else:
        res = _figure(source, cols, color, True)
    if strict and any(l["material"] for l in res.losses): raise RenderLossError(res)
    return res
