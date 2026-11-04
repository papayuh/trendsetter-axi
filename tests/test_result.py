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
    assert "bars 16 bins of 0.5 from -4 to 4 peak" in s and "heights:" in s, s

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


def observed(s, x, y, ax):
    """Every (at, ys) of a line is a fixture row with finite y, at the summary's rounding step, in the line's own order."""
    step = lambda lo, hi: 10.0 ** -max(0, -round(np.log10(abs(hi - lo) / 60)))
    sx, sy = step(*ax.get_xlim()), step(*ax.get_ylim())
    rows, k = [i for i in range(len(x)) if np.isfinite(x[i]) and np.isfinite(y[i])], -1
    for a, b in zip(s["at"], s["ys"]):
        k = next((i for i in rows if i > k and abs(float(a) - x[i]) <= sx / 2 + 1e-9 and abs(float(b) - y[i]) <= sy / 2 + 1e-9), None)
        assert k is not None, (a, b, s["at"], s["ys"])


def line_of(fig):
    return next(s for s in tsa.render(fig, 60).series if s["kind"] == "line")


def test_line_samples_are_observations_and_keep_gap_edges(close):
    x = np.arange(40.0); y = x.copy(); y[10:30] = np.nan
    fig = figure(lambda ax: ax.plot(x, y, label="gapped"))
    s = line_of(fig)
    observed(s, x, y, fig.axes[0])
    assert "9" in s["at"] and "30" in s["at"] and not any(10 <= float(a) <= 29 for a in s["at"]), s["at"]
    assert s["n"] == 20 and s["missing"] == 20
    assert isinstance(s["points"], np.ndarray) and np.array_equal(s["points"], np.column_stack([x, y])[np.isfinite(y)])


def test_sampling_cutoff_both_sides(close):
    x = np.arange(17.0) ** 1.5; y = np.sin(x)
    gap = y.copy(); gap[8] = np.nan
    fig = figure(lambda ax: ax.plot(x, gap))
    s = line_of(fig)
    assert s["sampled"] is False and len(s["at"]) == 16
    observed(s, x, gap, fig.axes[0])
    fig = figure(lambda ax: ax.plot(x, y))
    s = line_of(fig)
    assert s["sampled"] is True
    observed(s, x, y, fig.axes[0])


def test_samples_follow_x_order(close):
    t = np.arange(30.0) ** 1.5
    down = (t.max() - t, np.cos(t))
    wander = (np.r_[t[:15], t[15:][::-1] / 2], np.sin(t))
    dup = np.insert(t, 10, t[10]), np.insert(t, 10, t[10] + 40)   # two rows at one x, different y
    for x, y in (down, wander, dup):
        fig = figure(lambda ax: ax.plot(x, y))
        s = line_of(fig)
        assert s["sampled"] is True
        observed(s, x, y, fig.axes[0])
        plt.close(fig)
    fig = figure(lambda ax: ax.plot(*down))
    assert [float(v) for v in line_of(fig)["at"]] == sorted((float(v) for v in line_of(fig)["at"]), reverse=True)


def scatter_of(build):
    r = tsa.render(figure(build), 60)
    return next(s for s in r.series if s["kind"] == "scatter"), r


def test_masked_scatter_rows_are_excluded(close):
    y = np.ma.array([1.0, 999.0, 3.0], mask=[0, 1, 0])
    def build(ax):
        ax.scatter([0, 1, 2], y)
        ax.set_ylim(0, 1000)
    s, r = scatter_of(build)
    assert s["n"] == 2 and s["missing"] == 1 and "r" not in s, s
    assert s["mean"] == "1,2", s   # x (0+2)/2, y (1+3)/2 at steps 0.1 and 1
    assert np.array_equal(s["points"], [[0, 1], [2, 3]])
    s, r = scatter_of(lambda ax: ax.scatter([0, 1, 2], y))   # autoscaled to the valid rows: the masked 999 would sit outside the view
    assert s["n"] == 2 and not [l for l in r.losses if l["kind"] == "clipped_data"], r.losses
    for kw in (dict(x=np.ma.array([0, 1, 2, 3.0], mask=[0, 1, 0, 0]), y=[1, 2, 3, 4]),
               dict(x=[0, 1, 2, 3], y=[1, 2, 3, 4], s=np.ma.array([10, 20, 30, 40.0], mask=[0, 1, 0, 0])),
               dict(x=[0, 1, 2, 3], y=[1, 2, 3, 4], c=np.ma.array([1, 2, 3, 4.0], mask=[0, 1, 0, 0]))):
        s, r = scatter_of(lambda ax: ax.scatter(**kw))
        assert s["n"] == 3 and s["missing"] == 1 and len(s["points"]) == 3, (kw, s)


def test_all_missing_series_is_reported_not_invented(close):
    def build(ax):
        ax.plot(np.arange(40.0), np.full(40, np.nan), label="empty")
        ax.scatter([0, 1, 2], np.ma.array([1, 2, 3.0], mask=True), label="gone")
    r = tsa.render(figure(build), 60)
    line, dots = (next(s for s in r.series if s["name"] == n) for n in ("empty", "gone"))
    assert (line["n"], line["missing"], line["values"]) == (0, 40, []) and (dots["n"], dots["missing"], dots["values"]) == (0, 3, []), r.series
    lines = r.summary().splitlines()
    assert "line 'empty' n=0 missing=40" in lines and "scatter 'gone' n=0 missing=3" in lines, r.summary()


def test_hidden_artists_are_not_described(close):
    fig = plt.figure(figsize=(8, 3))
    ax, off = fig.subplots(1, 2)
    ax.plot([0, 1, 2], [1, 2, 3], label="visible")
    ax.plot([0, 1, 2], [99, 199, 299], label="hidden", visible=False)
    bc = ax.bar([0, 1, 2], [5, 7, 9], label="bars")
    bc[1].set_visible(False)
    off.plot([0, 1], [5, 6], label="on hidden axes")
    off.set_visible(False)
    r = tsa.render(fig, 60)
    names = [s["name"] for s in r.series]
    assert "visible" in names and "hidden" not in names and "on hidden axes" not in names, names
    bar = next(s for s in r.series if s["name"] == "bars")
    assert bar["values"] == ["0=5", "2=9"] and bar["n"] == 2, bar
    assert len(r.scales) == 1, r.scales
    assert [w for w in r.warnings if "hidden" in w] == ["3 hidden artists not described"], r.warnings   # the line, the bar, the axes
    assert all(l["kind"] == "text" for l in r.losses), r.losses   # hidden is not lost: losses() already skips invisible artists


@pytest.mark.parametrize("errors, expected", [
    ([3, 3, 3], ["3", "3", "3"]),
    ([[1, 1, 1], [2, 2, 2]], ["-1/+2"] * 3),
    ([3, np.nan, 3], ["3", "?", "3"]),
])
def test_errorbar_bounds_are_described(close, errors, expected):
    x, y = np.arange(3), np.array([4, 5, 6])
    fig = figure(lambda ax: ax.errorbar(x, y, yerr=errors, xerr=0.5, label="estimate", capsize=3))
    r = tsa.render(fig, 60)
    assert len(r.series) == 1
    s = r.series[0]
    assert s["name"] == "estimate" and s["kind"] == "line"
    assert s["yerr"] == expected and s["xerr"] == ["0.5"] * len(x)
    assert s["missing"] == 0 and np.array_equal(s["points"], np.column_stack([x, y]))
    values = [f"{v}±{e}" if not e.startswith("-") else f"{v}{e}" for v, e in zip(y, expected)]
    assert " ".join(values) in r.summary() and "'estimate'" in r.summary()
    assert "xerr: 0.5 0.5 0.5" in r.summary()
    assert r.not_described == []   # neither caps nor bar segments are extra series


@pytest.mark.parametrize("kw, field, values", [
    (dict(yerr=3), "yerr", "4±3 5±3 6±3"),
    (dict(xerr=0.5), "xerr", "0±0.5 1±0.5 2±0.5"),
    (dict(xerr=0.5, yerr=3), "yerr", "4±3 5±3 6±3"),
])
def test_errorbar_only_plot_is_described(close, kw, field, values):
    x, y = np.arange(3), np.array([4, 5, 6])
    r = tsa.render(figure(lambda ax: ax.errorbar(x, y, fmt="none", label="estimate", **kw)), 60)
    assert len(r.series) == 1
    s = r.series[0]
    assert s["kind"] == "errorbar" and s["n"] == len(x) and field in s
    assert np.array_equal(s["points"], np.column_stack([x, y]))
    assert values in r.summary() and "'estimate'" in r.summary()
    assert r.summary() != "losses: none" and r.not_described == []


@pytest.mark.parametrize("kind", ["pie", "contour", "patch", "empty"])
def test_unsupported_artists_are_listed(close, kind):
    from matplotlib.patches import Rectangle
    from trendsetter_axi.mpl import describe
    from trendsetter_axi.result import FIGURE
    fig, ax = plt.subplots(figsize=(8, 3))
    expected = []
    if kind == "pie":
        ax.pie([20, 80], labels=["A", "B"])
        expected = [("Wedge", 2)]
    elif kind == "contour":
        artist = ax.contour(np.arange(9).reshape(3, 3))
        expected = [(type(artist).__name__, 1)]
    elif kind == "patch":
        ax.add_patch(Rectangle((0.1, 0.1), 0.5, 0.5))
        expected = [("Rectangle", 1)]
    ax.add_patch(Rectangle((0, 0), 1, 1, visible=False))
    r = tsa.render(fig, 60)
    assert r.series == [] and r.not_described == expected
    assert r.supported_features == FIGURE
    coverage = [line for line in r.summary().splitlines() if line.startswith("not described:")]
    assert coverage == (["not described: " + ", ".join(f"{n} {name}" for name, n in expected)] if expected else [])
    losses = [loss.copy() for loss in r.losses]
    meta = dict(series=[], losses=losses)
    describe(fig, meta)
    assert meta["losses"] == losses and all(loss["kind"] != "not_described" for loss in losses)


@pytest.mark.parametrize("kind", ["density", "weighted", "bar", "stacked", "barh", "six", "seven"])
def test_bar_bins_claim_no_statistics(close, kind):
    x, heights = np.arange(8), np.arange(1, 9)
    def build(ax):
        if kind in ("density", "weighted"):
            samples = np.linspace(0, 16, 1601)
            ax.hist(samples, bins=np.arange(0, 18, 2), **(dict(density=True) if kind == "density" else dict(weights=np.full(len(samples), 0.5))))
        elif kind == "barh":
            ax.barh(x, heights, height=1, label="price")
        else:
            n = 6 if kind == "six" else 7 if kind == "seven" else 8
            ax.bar(x[:n], heights[:n], width=1, label="price")
            if kind == "stacked": ax.bar(x, heights * 2, width=1, bottom=heights, label="extra")
    r = tsa.render(figure(build), 60)
    assert len(r.series) == (2 if kind == "stacked" else 1)
    assert "counts:" not in r.summary()
    if kind == "six":
        assert r.series[0]["kind"] == "bar" and "heights:" not in r.summary()
    else:
        assert all(s["kind"] == "histogram" for s in r.series)
        rows = [line for line in r.summary().splitlines() if line.startswith("bars ")]
        assert len(rows) == len(r.series) and all("heights:" in line for line in rows)
        if kind == "bar": assert "bars 'price' 8 bins of 1 from -0.5 to 7.5 peak 6.5-7.5=8 heights: 1 2 3 4 5 6 7 8" in rows[0]
