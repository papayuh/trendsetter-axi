import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from trendsetter_axi import render_figure, render_svg
from trendsetter_axi.gallery import CHARTS

BY_ID = {c["id"]: c for c in CHARTS}
MPL_IDS = ["01_mpl_line", "03_mpl_scatter", "04_mpl_bar", "07_mpl_hist", "08_mpl_box", "13_mpl_step"]


# the heatmap's colour key is wider than 40 columns, so it only runs at 80
CASES = [(c, w) for c in MPL_IDS for w in (80, 40)] + [("10_mpl_imshow", 80)]


@pytest.mark.parametrize("cid,cols", CASES)
def test_render_matplotlib_charts(cid, cols):
    fig = BY_ID[cid]["make"]()
    try:
        text = render_figure(fig, cols)
    finally:
        plt.close(fig)
    assert text.strip()
    assert all(len(line) <= cols for line in text.split("\n"))
    assert any(ch.strip() for ch in text)


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
