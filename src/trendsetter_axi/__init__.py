"""Render matplotlib figures and SVG as unicode text for the terminal."""
import copy, itertools

from matplotlib.category import UnitData

from . import mpl as _mpl, svg as _svg

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


def render_figure(fig, cols=80):
    """Render a matplotlib Figure at most `cols` terminal cells wide per line. The figure itself is left unchanged."""
    work = _copy(fig)
    try:
        return _mpl.render(work, cols)[0]
    finally:
        if work.canvas.manager is not None:
            import matplotlib.pyplot as plt
            plt.close(work)


def render_svg(svg_text, cols=80):
    """Render SVG source (plain text, e.g. from matplotlib with svg.fonttype='none') as text."""
    return _svg.render(svg_text, cols)[0]
