"""render(): the RenderResult says what the text shows, what it lost, and refuses misleading text when strict."""
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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


def test_clipped_data_is_a_loss(close):
    def build(ax):
        ax.plot(range(10), label="y")
        ax.set_ylim(0, 5)
    r = tsa.render(figure(build), 60)
    assert [(l["kind"], l["detail"]) for l in r.losses] == [("clipped_data", "4 of 10 points outside the axes view")], r.losses
    with pytest.raises(tsa.RenderLossError, match="clipped_data"):
        tsa.render(figure(build), 60, strict=True)


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
    assert r.series == [dict(name="sales", kind="bar", axes=0, key=None, color="#1f77b4", n=3, values=["north=3", "south=9.25", "east=5"])]
    assert r.scales[0]["x"] == dict(label="", scale="category", categories=3) and r.scales[0]["y"]["label"] == "units"
    s = r.summary()
    assert "bar 'sales' n=3 north=3 south=9.25 east=5" in s and "title: Sales" in s and s.endswith("losses: none")
    assert len(s) < len(r.text) / 4   # an agent reads numbers, not braille

    def line(ax):
        ax.plot(range(20), [v % 7 for v in range(20)], label="saw")
    s = tsa.render(figure(line), 60).summary()
    assert "line 'saw' n=20 x=0..19 y=0..6 first 0=0 last 19=5 min 0=0 max 6=6" in s, s


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
