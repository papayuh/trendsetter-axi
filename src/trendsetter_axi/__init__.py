"""Render matplotlib figures and SVG as unicode text for the terminal."""
import copy
import dataclasses
import itertools

from . import result as _result
from .result import RenderLossError as RenderLossError, RenderResult as RenderResult   # public API
from .compact import CompactResult as CompactResult, render_compact as render_compact, render_ranking as render_ranking
from .display import (DisplayPreferences as DisplayPreferences, Surface as Surface, Scalar as Scalar,
                      Presentation as Presentation, present as present, resolve_preferences as resolve_preferences)

__version__ = "0.1.0"


def _copy(fig):
    """Isolated figure, using matplotlib's serialization protocol when possible.

    Pickle reconstructs the same artist graph in C instead of recursively walking
    every dictionary in Python. Local functions/custom artists may not support
    pickle; keep the deepcopy route for those figures.
    """
    import pickle

    # As on the deepcopy route, materialize matplotlib's tick caches before
    # cloning. Otherwise prepare/findobj rebuilds the initial Tick artists on
    # every disposable copy (Axis._get_tick in the warm profile).
    fig.findobj()
    try:
        work = pickle.loads(pickle.dumps(fig, protocol=pickle.HIGHEST_PROTOCOL))
    except Exception:
        # Custom objects can reject serialization with arbitrary exception
        # types while still supporting deepcopy. Preserve that existing route.
        work = _deepcopy(fig)
    for ax in work.axes:
        for a in ax._children:
            a._remove_method = ax._children.remove
    return work


def _deepcopy(fig):
    """plotnine's __deepcopy__ can retain source artists; copy their holders plainly."""
    from matplotlib.category import UnitData

    memo = {id(a.units._counter): itertools.count(len(a.units._mapping))
            for ax in fig.axes for a in (ax.xaxis, ax.yaxis) if isinstance(a.units, UnitData)}
    artists = {id(a) for a in fig.findobj()}
    def holds(v):
        return id(v) in artists or isinstance(v, list) and any(id(x) in artists for x in v)
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


def _figure(fig, cols, color, result, rows=None):
    from . import mpl as _mpl

    work = _copy(fig)
    try:
        text, meta = _mpl.render(work, cols, color, rows)
        if not result:
            return text
        return _result.build(text, meta, cols, *_mpl.describe(fig, meta), _mpl.losses(work, meta), _result.FIGURE)
    finally:
        if work.canvas.manager is not None:
            import matplotlib.pyplot as plt
            plt.close(work)


def render_figure(fig, cols=80, color=False):
    """Render a matplotlib Figure at most `cols` terminal cells wide per line. The figure itself is left unchanged.
    Shortcut for render(fig, cols=cols, color=color).text, without building a report.
    color=True adds 24-bit ANSI colour; it never changes the cell width."""
    return _figure(fig, cols, color, False)


def render_svg(svg_text, cols=80, color=False):
    """Shortcut for render(svg_text, cols=cols, color=color).text, without building a report.

    SVG source is plain text, e.g. from matplotlib with svg.fonttype='none'.
    """
    from . import svg as _svg

    return _svg.render(svg_text, cols, ansi=color)[0]


def render(source, cols=80, *, color=False, strict=False, ascii=False, rows=None):
    """Render a matplotlib Figure or SVG source (str or bytes) and report what the text lost, as a RenderResult.

    strict=True raises RenderLossError on material losses. See README.md, "What the text lost: render", for
    materiality and known limits.

    ascii=True draws the same cells in ASCII (lines in ' - _ / \\ |, bars in #, heat levels in . : = #, series keys
    o x ^ ...): coarser than braille, a fraction of the tokens for a model to read. Frame and labels are unchanged.
    rows must be None or a positive int (not bool). It is the preferred height in lines, with a minimum of 8;
    heatmaps and bar charts may take more rows so each row or bar keeps a line. By default it follows the figure's
    aspect. SVG input ignores this preference. cols is the hard terminal-cell budget per line."""
    if rows is not None and (isinstance(rows, bool) or not isinstance(rows, int) or rows < 1):
        raise ValueError("rows must be a positive int")
    if isinstance(source, (str, bytes)):
        from . import svg as _svg

        text, meta = _svg.render(source, cols, ansi=color)
        series, scales, lost = _result.svg_series(meta)
        res = _result.build(text, meta, cols, series, scales, lost, _result.SVG)
    else:
        res = _figure(source, cols, color, True, rows)
    if ascii:
        from . import core as _core

        tr = lambda t: t.translate(_core.ASCII) if t else t  # noqa: E731
        res = dataclasses.replace(res, text=tr(res.text), series=[dict(s, key=tr(s["key"])) for s in res.series])
    if strict and any(loss["material"] for loss in res.losses):
        raise RenderLossError(res)
    return res
