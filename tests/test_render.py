import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from trendsetter_axi import render_figure, render_svg
from trendsetter_axi.gallery import CHARTS
from trendsetter_axi.cells import width

BY_ID = {c["id"]: c for c in CHARTS}
MPL_IDS = ["01_mpl_line", "03_mpl_scatter", "04_mpl_bar", "07_mpl_hist", "08_mpl_box", "13_mpl_step"]


CASES = [(c, w) for c in MPL_IDS + ["10_mpl_imshow"] for w in (40, 80, 120)]


@pytest.mark.parametrize("cid,cols", CASES)
def test_render_matplotlib_charts(cid, cols):
    fig = BY_ID[cid]["make"]()
    try:
        text = render_figure(fig, cols)
    finally:
        plt.close(fig)
    assert text.strip()
    assert all(width(line) <= cols for line in text.split("\n"))
    assert any(ch.strip() for ch in text)


@pytest.mark.parametrize("cid", ["04_mpl_bar", "44_mpl_longtitle"])
def test_render_figure_leaves_figure_unchanged(cid):
    fresh = BY_ID[cid]["make"]()
    fig = BY_ID[cid]["make"]()
    try:
        expected = render_figure(fresh, 80)
        size, dpi, title = fig.get_size_inches().copy(), fig.dpi, fig.axes[0].get_title()
        render_figure(fig, 40)
        assert render_figure(fig, 80) == expected
        assert (fig.get_size_inches() == size).all() and fig.dpi == dpi and fig.axes[0].get_title() == title
    finally:
        plt.close(fresh)
        plt.close(fig)


def test_render_svg():
    fig = BY_ID["01_mpl_line"]["make"]()
    try:
        with matplotlib.rc_context({"svg.fonttype": "none"}):
            buf = io.StringIO()
            fig.savefig(buf, format="svg", dpi=72)
    finally:
        plt.close(fig)
    assert render_svg(buf.getvalue(), 80).strip()


def test_gallery_ids():
    ids = [c["id"] for c in CHARTS]
    assert len(ids) == 50
    assert len(set(ids)) == 50
