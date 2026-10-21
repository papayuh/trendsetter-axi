"""Render matplotlib figures and SVG as unicode text for the terminal."""
from . import mpl as _mpl, svg as _svg

__version__ = "0.1.0"


def render_figure(fig, cols=80):
    """Render a matplotlib Figure as text at most `cols` characters wide.

    The figure is modified in place to fit the cell grid; render a fresh figure each time."""
    return _mpl.render(fig, cols)[0]


def render_svg(svg_text, cols=80):
    """Render SVG source (plain text, e.g. from matplotlib with svg.fonttype='none') as text."""
    return _svg.render(svg_text, cols)[0]
