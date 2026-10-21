"""Fixed demo of trendsetter-axi. Run: python examples/demo.py [--cols N] [--section NAME]

Data and seeds are fixed, so chart text is identical run to run. Timings are
the only varying output; they print on lines starting with "[timing]".
"""
import argparse
import io
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from trendsetter_axi import render_figure, render_svg
from trendsetter_axi.cells import width
from trendsetter_axi.gallery import CHARTS

BY_ID = {c["id"]: c for c in CHARTS}
GALLERY = ["01_mpl_line", "05_mpl_groupbar", "07_mpl_hist", "08_mpl_box", "46_mpl_spaghetti", "50_mpl_twinx"]


def line():
    fig, ax = plt.subplots()
    x = np.linspace(0, 4 * np.pi, 200)
    ax.plot(x, np.sin(x), label="sin")
    ax.plot(x, np.cos(x), label="cos")
    ax.set(title="Sine and cosine", xlabel="radians", ylabel="value")
    ax.legend()
    return fig


def bar():
    fig, ax = plt.subplots()
    ax.bar(["Mon", "Tue", "Wed", "Thu", "Fri"], [12, 19, 7, 15, 22])
    ax.set(title="Tickets per day", ylabel="count")
    return fig


def scatter():
    r = np.random.default_rng(7)
    x = r.normal(size=120)
    fig, ax = plt.subplots()
    ax.scatter(x, 2 * x + r.normal(size=120), s=8)
    ax.set(title="Noisy slope", xlabel="x", ylabel="y")
    return fig


def heatmap():
    fig, ax = plt.subplots()
    im = ax.imshow(np.add.outer(np.arange(8), np.arange(12)) % 7 + np.arange(12) / 4, aspect="auto")
    fig.colorbar(im)
    ax.set(title="Heatmap")
    return fig


def big():
    r = np.random.default_rng(1)
    fig, ax = plt.subplots()
    ax.plot(np.cumsum(r.normal(size=100_000)), lw=0.5)
    ax.set(title="100,000-point random walk")
    return fig


def cjk():
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3, 4], [3, 1, 4, 2])
    ax.set(title="月別の売上推移と前年同期比の比較グラフ（テスト用の長いタイトル）")
    return fig


def show(caption, text, cols, out):
    out.append(f"## {caption}")
    out.append(text)
    out.append("")


def render(make, cols):
    fig = make()
    try:
        return render_figure(fig, cols)
    finally:
        plt.close(fig)


def section_basic(cols, out):
    for caption, make in [("line chart", line), ("bar chart", bar), ("scatter plot", scatter), ("heatmap", heatmap)]:
        show(f"basic: {caption} at {cols} cols", render(make, cols), cols, out)


def section_widths(cols, out):
    for w in (100, 60, 40, 24):
        text = render(line, w)
        show(f"width budget: same chart at {w} cols", text, w, out)
        out.append(f"max line width: {max(width(l) for l in text.split(chr(10)))} / {w} cells")
        out.append("")


def section_big(cols, out):
    t = time.perf_counter()
    text = render(big, cols)
    dt = time.perf_counter() - t
    show(f"100k points at {cols} cols", text, cols, out)
    out.append(f"[timing] 100,000 points rendered in {dt:.2f}s")
    out.append("")


def section_cjk(cols, out):
    text = render(cjk, cols)
    show(f"CJK title fits the {cols}-cell budget", text, cols, out)
    out.append(f"max line width: {max(width(l) for l in text.split(chr(10)))} / {cols} cells")
    out.append("")


def section_svg(cols, out):
    fig = line()
    try:
        with matplotlib.rc_context({"svg.fonttype": "none"}):
            buf = io.StringIO()
            fig.savefig(buf, format="svg", dpi=72)
    finally:
        plt.close(fig)
    show(f"render_svg on a matplotlib SVG at {cols} cols", render_svg(buf.getvalue(), cols), cols, out)


def section_gallery(cols, out):
    for cid in GALLERY:
        fig = BY_ID[cid]["make"]()
        try:
            show(f"gallery: {cid} at {cols} cols", render_figure(fig, cols), cols, out)
        finally:
            plt.close(fig)


SECTIONS = dict(basic=section_basic, widths=section_widths, big=section_big, cjk=section_cjk, svg=section_svg, gallery=section_gallery)


def build(cols=80, sections=None):
    """Return the demo as a list of output lines."""
    out = []
    for name in sections or SECTIONS:
        SECTIONS[name](cols, out)
    return "\n".join(out).split("\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cols", type=int, default=80)
    p.add_argument("--section", choices=SECTIONS, action="append", help="repeatable; default: all")
    a = p.parse_args()
    print("\n".join(build(a.cols, a.section)))
