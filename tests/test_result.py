"""render(): the RenderResult says what the text shows, what it lost, and refuses misleading text when strict."""
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

import trendsetter_axi as tsa
from trendsetter_axi import core
from trendsetter_axi.cells import width


def figure(build, figsize=(8, 3)):
    fig = plt.figure(figsize=figsize)
    build(fig.subplots())
    return fig


@pytest.fixture
def close():
    yield
    plt.close("all")


def two_lines(ax):
    ax.plot([0, 1, 2], [0, 1, 0], color="tab:blue", label="blue")
    ax.plot([0, 1, 2], [1, 0, 1], color="black", label="black")
    ax.legend()


def test_result_matches_string_functions(close):
    fig = figure(two_lines)
    r = tsa.render(fig, 60)
    assert r.text == str(r) == tsa.render_figure(fig, 60)
    lines = r.text.split("\n")
    assert r.dimensions == dict(cols=60, width=max(map(width, lines)), height=len(lines))
    assert r.losses == [] and r.supported_features["source_values"]


def test_color_option(close):
    fig = figure(two_lines)
    r = tsa.render(fig, 60, color=True)
    assert "\x1b[38;2;" in r.text and r.text == tsa.render_figure(fig, 60, color=True)
    assert r.dimensions["width"] <= 60 and "\x1b[" not in tsa.render_figure(fig, 60)


def test_lost_data_artist_is_counted(close, monkeypatch):
    """The old colour rule took a black curve for the frame and drew nothing, and nothing reported it."""
    stroke = core.Canvas.stroke
    monkeypatch.setattr(core.Canvas, "stroke", lambda self, polylines, rgb, *a, **k: None if core.neutral(rgb) else stroke(self, polylines, rgb, *a, **k))
    r = tsa.render(figure(two_lines), 60)
    assert [(l["kind"], l["what"], l["material"]) for l in r.losses] == [("lost_artist", "Line2D 'black'", True)], r.losses
    with pytest.raises(tsa.RenderLossError, match="black") as e:
        tsa.render(figure(two_lines), 60, strict=True)
    assert e.value.result.text


def test_hidden_series_is_lost(close):
    def build(ax):
        ax.plot([1, 3, 2, 4], color="tab:blue", label="actual")
        ax.plot([1, 3, 2, 4], color="tab:orange", label="forecast")   # drawn on top of every cell of "actual"
    r = tsa.render(figure(build), 60)
    assert [(l["kind"], l["what"]) for l in r.losses] == [("lost_artist", "Line2D 'actual'")], r.losses


def test_clipped_data_is_reported_but_not_material(close):
    def build(ax):
        ax.plot(range(10), label="y")
        ax.set_ylim(0, 5)
    r = tsa.render(figure(build), 60)
    assert [(l["kind"], l["detail"], l["material"]) for l in r.losses] == [("clipped_data", "4 of 10 points outside the axes view", False)], r.losses
    assert tsa.render(figure(build), 60, strict=True).losses == r.losses


def test_readme_ylim_example_passes_strict(close):
    def build(ax):
        ax.plot([1, 2, 3, 4, 5], [2, 4, 3, 5, 7], label="demand")
        ax.set(title="Example", xlabel="x", ylabel="y")
        ax.set_ylim(0, 6)
    r = tsa.render(figure(build), 80, strict=True)
    assert "losses: clipped_data Line2D 'demand': 1 of 5 points outside the axes view" in r.summary()


def test_reference_lines_report_data_values(close):
    def build(ax):
        ax.plot([1, 2, 3], [10, 20, 30])
        ax.axhline(15)
        ax.axvline(2)
    data, h, v = [s for s in tsa.render(figure(build), 60).series if s["kind"] == "line"]
    assert h["y"] == "15..15" and v["x"] == "2..2", (h, v)
    assert h["x"] != "0..1" and v["y"] != "0..1", (h, v)   # view limits in data units, not axes fractions


def test_cut_legend_label_is_material_and_tick_drops_are_not(close):
    def build(ax):
        ax.plot(range(10), label="a legend label far too long to fit in forty columns")
        ax.plot(range(3), label="b")
        ax.legend()
    r = tsa.render(figure(build), 40)
    labels = [l for l in r.losses if l["kind"] == "series_label"]
    assert labels and all(l["material"] for l in labels) and "far too long" in labels[0]["what"], r.losses
    assert all(not l["material"] for l in r.losses if l["kind"] == "text")
    with pytest.raises(tsa.RenderLossError, match="series_label"):
        tsa.render(figure(build), 40, strict=True)


def test_strict_passes_a_faithful_render(close):
    r = tsa.render(figure(two_lines), 60, strict=True)
    assert r.losses == []


def test_summary_values_come_from_the_source(close):
    def build(ax):
        ax.bar(["north", "south", "east"], [3, 9.25, 5], label="sales")
        ax.set(title="Sales", ylabel="units")
    r = tsa.render(figure(build), 60)
    assert r.series == [dict(name="sales", kind="bar", axes=0, key=None, color="#1f77b4", n=3, values=["north=3", "south=9.2", "east=5"])]   # 1/60 of the span
    assert r.scales[0]["x"] == dict(label="", scale="category", categories=3) and r.scales[0]["y"]["label"] == "units"
    s = r.summary()
    assert "bar 'sales' n=3 north=3 south=9.2 east=5" in s and "title: Sales" in s and s.endswith("losses: none")
    assert len(s) < len(r.text) / 4   # an agent reads numbers, not braille

    def line(ax):
        ax.plot(range(20), [v % 7 for v in range(20)], label="saw")
    s = tsa.render(figure(line), 60).summary()
    assert "lines at x: 0 2 4 6 8 10 12 14 16 18 19\n  'saw' n=20: 0 2 4 6 1 3 5 0 2 4 5 (min 0=0 max 6=6)" in s, s   # sampled: first, last, nice x between, exact extremes


def test_summary_reads_each_kind_compactly(close):
    def lines(ax):
        ax.plot(range(1, 13), range(12), label="a")
        ax.plot(range(1, 13), range(12, 0, -1), label="b")
        ax.legend()
    s = tsa.render(figure(lines), 60).summary()
    assert s.count("lines at x:") == 1 and "'a' ● : 0 1 2" not in s and "'b' ×: 12 11 10" in s, s   # one shared x row, every point up to 16

    rng = np.random.default_rng(0)
    def hist(ax): ax.hist(rng.normal(size=500), bins=np.linspace(-4, 4, 17))
    s = tsa.render(figure(hist), 60).summary()
    assert "histogram 16 bins of 0.5 from -4 to 4 peak" in s and "counts:" in s, s

    def heat(ax):
        ax.imshow([[1, 2], [3, 4]]); ax.set_xticks([0, 1], ["a", "b"]); ax.set_yticks([0, 1], ["top", "low"])
    s = tsa.render(figure(heat), 60).summary()
    assert "  cols: a b\n  top: 1 2\n  low: 3 4" in s and "max low/b=4" in s, s   # small grids in full

    def slashed(ax):
        ax.imshow(np.arange(49.0).reshape(7, 7)); ax.set_xticks(range(7), [f"c/{i}" for i in range(7)]); ax.set_yticks(range(7), [f"r/{i}" for i in range(7)])
    s = tsa.render(figure(slashed), 60).summary()
    assert "row means: r/0=3 r/1=10" in s and "col means: c/0=21 c/1=22" in s and "max r/6/c/6=48" in s, s   # labels may hold '/'

    def falling(ax): ax.plot(np.linspace(100, 0, 101), np.linspace(100, 0, 101) ** 2)
    xs = next(l for l in tsa.render(figure(falling), 60).summary().splitlines() if "at x:" in l).split(":")[1].split()
    assert [float(v) for v in xs] == sorted((float(v) for v in xs), reverse=True), xs   # samples keep the line's x order

    x = np.arange(20.0); y = 2 * x; y[5] = 90
    def scatter(ax): ax.scatter(x, y)
    s = tsa.render(figure(scatter), 60).summary()
    assert "outliers (5,90); others x=0..19 y=0..38" in s, s


def test_ascii_and_rows_keep_the_layout_and_cut_glyph_cost(close):
    def build(ax):
        ax.plot(np.linspace(0, 10, 200), np.sin(np.linspace(0, 10, 200)), label="sin")
        ax.plot([0, 10], [1, -1], label="fall")
        ax.bar([2, 5, 8], [0.3, 0.7, 0.5], label="bars")
        ax.legend()
    plain, lean = tsa.render(figure(build), 60), tsa.render(figure(build), 60, ascii=True)
    assert all(ord(ch) < 128 or 0x2500 <= ord(ch) <= 0x257f for ch in lean.text), lean.text   # only ASCII and box drawing
    assert "∙▯".translate(core.ASCII) == ".|"   # dot staircases and flat candle bodies
    assert [width(l) for l in lean.text.split("\n")] == [width(l) for l in plain.text.split("\n")]   # same cells, other glyphs
    assert all(s["key"] is None or s["key"].isascii() for s in lean.series) and lean.summary().count("losses") == 1
    tall = tsa.render(figure(build), 60, rows=20)
    assert tall.dimensions["height"] > plain.dimensions["height"] and tall.dimensions["width"] <= 60


def test_svg_marks_values_unavailable(close):
    fig = figure(two_lines)
    with matplotlib.rc_context({"svg.fonttype": "none"}):
        buf = io.StringIO()
        fig.savefig(buf, format="svg", dpi=72)
    r = tsa.render(buf.getvalue(), 60)
    assert r.text == tsa.render_svg(buf.getvalue(), 60) == tsa.render(buf.getvalue().encode(), 60).text
    assert not r.supported_features["source_values"] and not r.supported_features["artist_roles"]
    assert r.series and all(s["values"] is None for s in r.series)
    assert "values unavailable" in r.summary()


@pytest.mark.parametrize("under", ["black", "0.3"])
def test_hidden_neutral_series_is_lost(close, under):
    """A black or gray curve drawn over by another series is as lost as a coloured one."""
    def build(ax):
        x = np.linspace(0, 6, 200)
        ax.plot(x, np.sin(x), color=under, label="baseline")
        ax.plot(x, np.sin(x), color="tab:red", lw=3, label="model")
    r = tsa.render(figure(build), 60)
    assert [(l["kind"], l["what"], l["material"]) for l in r.losses] == [("lost_artist", "Line2D 'baseline'", True)], r.losses
    with pytest.raises(tsa.RenderLossError, match="baseline"):
        tsa.render(figure(build), 60, strict=True)


def test_visible_neutral_series_is_not_lost(close):
    def build(ax):
        ax.plot([1, 3, 2, 4], color="black", label="actual")
        ax.plot([4, 2, 3, 1], color="tab:red", label="forecast")
        ax.axhline(2.5, color="gray")
    assert tsa.render(figure(build), 60, strict=True).losses == []
