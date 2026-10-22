import io
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

import trendsetter_axi as tsa
from trendsetter_axi.gallery import CHARTS
from trendsetter_axi.cells import width

BY_ID = {c["id"]: c for c in CHARTS}
INK = re.compile("[\u2800-\u28ff\u2580-\u259f•●×▲◆■○△┬┴]")   # braille dots, blocks, markers, box-plot joints: data, not the frame
MPL_IDS = ["01_mpl_line", "03_mpl_scatter", "04_mpl_bar", "07_mpl_hist", "08_mpl_box", "13_mpl_step"]


CASES = [(c, w) for c in MPL_IDS + ["10_mpl_imshow"] for w in (40, 80, 120)]


@pytest.mark.parametrize("cid,cols", CASES)
def test_render_matplotlib_charts(cid, cols):
    fig = BY_ID[cid]["make"]()
    try:
        text = tsa.render_figure(fig, cols)
    finally:
        plt.close(fig)
    assert len(text.splitlines()) >= 6   # a chart, not a placeholder
    assert all(width(line) <= cols for line in text.split("\n"))
    assert INK.search(text), text


@pytest.mark.parametrize("cid", ["04_mpl_bar", "44_mpl_longtitle"])
def test_render_figure_leaves_figure_unchanged(cid):
    fresh = BY_ID[cid]["make"]()
    fig = BY_ID[cid]["make"]()
    try:
        expected = tsa.render_figure(fresh, 80)
        assert INK.search(expected)   # an unchanged figure only means something when the render drew it
        size, dpi, title = fig.get_size_inches().copy(), fig.dpi, fig.axes[0].get_title()
        tsa.render_figure(fig, 40)
        assert tsa.render_figure(fig, 80) == expected
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
    text = tsa.render_svg(buf.getvalue(), 80)
    assert BY_ID["01_mpl_line"]["make"]().axes[0].get_title() in text
    assert INK.search(text), text


def test_gallery_ids():
    ids = [c["id"] for c in CHARTS]
    assert len(ids) == 50
    assert len(set(ids)) == 50
