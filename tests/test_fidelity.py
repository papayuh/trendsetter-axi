"""Relationships a faithful render must keep, checked on the text itself.

Each test states something that must stay true when the input changes in a way that should not change the answer
(colour, line width), or that must change in a known way (crop, remove a series). Nothing here compares against a
stored render, and "non-empty output" is never enough: a renderer that returns "x" fails every test in this file.
"""
import io
import itertools
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

import trendsetter_axi as tsa

BRAILLE = re.compile("[⠁-⣿]")      # a braille cell with at least one dot
BLOCKS = re.compile("[▀-▟]")
NUM = r"-?\d+(?:\.\d+)?"


def render(build, cols=60, figsize=(8, 3)):
    fig = plt.figure(figsize=figsize)
    try:
        build(fig.subplots())
        return tsa.render_figure(fig, cols)
    finally:
        plt.close(fig)


def body(text):
    """Rows and columns strictly inside the axes frame, as a list of strings."""
    rows = text.split("\n")
    top = next(i for i, r in enumerate(rows) if "┌" in r)
    left, right = rows[top].index("┌"), rows[top].rindex("┐")
    bottom = next(i for i, r in enumerate(rows) if i > top and r[left:left + 1] == "└")   # the frame corner, not a box-drawn curve
    return [r.ljust(right + 1)[left + 1:right] for r in rows[top + 1:bottom]]


def y_ticks(text):
    return [float(m.group(1)) for r in text.split("\n") if (m := re.match(rf"\s*({NUM})\s*[│┌└]", r))]


def x_ticks(text):
    rows = text.split("\n")
    return [float(v) for v in re.findall(NUM, rows[next(i for i, r in enumerate(rows) if "└" in r) + 1])]


def heat_cells(text):
    """The heat grid as rows of collapsed runs (`▒ █` = a ▒ cell, a missing cell, a █ cell), duplicate rows dropped: what the cells say, not how wide or tall they are."""
    rows = [r for r in text.split("\n") if re.search("[░▒▓█]", r)]
    left = min(next(c for c, ch in enumerate(r) if ch in "░▒▓█") for r in rows)
    right = max(max(c for c, ch in enumerate(r) if ch in "░▒▓█") for r in rows)
    runs = ["".join(k for k, _ in itertools.groupby(r[left:right + 1].ljust(right + 1 - left))) for r in rows]
    return [k for k, _ in itertools.groupby(runs)]


X = np.linspace(0, 10, 400)   # 400 points over ~55 columns: every segment is shorter than a text cell


# ---- colour and width must not change what is drawn ------------------------------------------------------

@pytest.mark.parametrize("neutral", ["black", "0.2", "#444444", "dimgray", "0.7", "lightgray"])
def test_dense_curve_survives_color_change(neutral):
    blue = render(lambda ax: ax.plot(X, np.sin(X), color="tab:blue"))
    assert len(BRAILLE.findall("".join(body(blue)))) > 40, blue   # the fixture is a visible curve
    assert render(lambda ax: ax.plot(X, np.sin(X), color=neutral)) == blue


@pytest.mark.parametrize("neutral", ["black", "0.7", "lightgray"])
@pytest.mark.parametrize("build", [lambda ax, c: ax.plot([0, 10], [5, 5], color=c), lambda ax, c: ax.step(np.arange(8), [1, 3, 1, 4, 2, 5, 1, 3], color=c)], ids=["flat", "step"])
def test_axis_aligned_curve_survives_color_change(build, neutral):
    ink = lambda c: {i for r in body(render(lambda ax: build(ax, c))) for i, ch in enumerate(r) if ch != " "}
    blue = ink("tab:blue")
    assert len(blue) > 30 and len(ink(neutral)) >= 0.9 * len(blue)   # a flat or stepped series in any colour is drawn across the plot, not taken for a gridline


@pytest.mark.parametrize("lw", [0.5, 3, 6])
def test_line_width_keeps_series_and_axes(lw):
    def two(w):
        def build(ax):
            ax.plot(X, np.sin(X), lw=w, label="a"); ax.plot(X, np.sin(X) + 5, lw=w, label="b"); ax.set_xlabel("time")
        return build
    base = render(two(1))
    assert "time" in base and len(y_ticks(base)) >= 2
    assert render(two(lw)) == base


# ---- what an artist is decides how it draws, not its colour ----------------------------------------------

def ink_cells(text):
    return sum(ch != " " for r in body(text) for ch in r)


def test_black_contour_lines_are_data():
    x, y = np.meshgrid(np.linspace(-3, 3, 80), np.linspace(-3, 3, 80))
    z = np.exp(-(x - 1) ** 2 - y ** 2) + np.exp(-(x + 1) ** 2 - y ** 2 / 3)
    ink = lambda c: ink_cells(render(lambda ax: ax.contour(x, y, z, levels=5, colors=c), figsize=(8, 4)))
    blue = ink("tab:blue")
    assert blue > 60 and ink("black") >= 0.9 * blue   # a dense black curve is all short segments: still the data


@pytest.mark.parametrize("gray", ["0.5", "0.85", "lightgray"])
def test_gray_bars_are_data(gray):
    bars = lambda c: render(lambda ax: ax.bar(range(6), [3, 9, 5, 7, 2, 6], color=c))
    assert len(BLOCKS.findall("".join(body(bars(gray))))) > 20 and bars(gray) == bars("tab:blue")   # a light gray bar is a bar, not page background


@pytest.mark.parametrize("gray", ["0.3", "0.7"])
def test_gray_outline_series_is_data(gray):
    v = np.random.default_rng(0).normal(0, 1, 2000)
    step = lambda c: ink_cells(render(lambda ax: ax.hist(v, bins=20, histtype="step", color=c)))
    assert step(gray) >= 0.9 * step("tab:blue")   # an outline-only histogram is a patch: neither gridlines nor decoration


@pytest.mark.parametrize("dark", ["black", "0.25", "0.5"])
def test_dark_filled_area_is_data(dark):
    area = lambda c: render(lambda ax: (ax.fill_between(X, 0, np.sin(X) + 1.5, color=c), ax.plot(X, np.sin(X) / 2 + 1, color="tab:orange"), ax.set_ylim(0, 2.6)))   # the fill covers most of the figure
    assert len(BLOCKS.findall(area(dark))) > 100 and area(dark) == area("tab:blue")   # a big dark fill is a series, not a dark theme or a gray panel


def test_axes_facecolor_is_background_whatever_its_colour():
    line = lambda c: render(lambda ax: (ax.set_facecolor(c), ax.plot(X, np.sin(X))))
    assert len(BRAILLE.findall("".join(body(line("white"))))) > 40 and line("#dde8ff") == line("white")   # a tinted panel is not a filled series


def test_one_dark_subplot_does_not_darken_the_figure():
    def pair(face):
        fig, axs = plt.subplots(1, 2, figsize=(8, 3))
        try:
            if face: axs[0].set_facecolor(face)
            for ax in axs: ax.plot(X, np.sin(X))
            return tsa.render_figure(fig, 80)
        finally:
            plt.close(fig)
    dark = pair("0.1")
    assert dark.count("┌") == 2 and dark.count("┘") == 2 and dark == pair(None), dark   # one subplot's axes patch is hidden, not a dark page that hides every frame


def test_white_bars_stay_outlined():
    bars = render(lambda ax: ax.bar(range(6), [3, 9, 5, 7, 2, 6], color="white", edgecolor="black"))
    inside = "".join(body(bars))
    assert "█" not in inside and inside.count("│") > 10 and "┌" in inside, bars   # a bar in the page colour is its edge, not a solid block


def test_annotation_arrow_is_drawn_but_never_a_series():
    def chart(arrow):
        def build(ax):
            ax.plot(X, np.sin(X), label="a"); ax.plot(X, np.sin(X) + 3, label="b")
            if arrow: ax.annotate("peak", (1.6, 1), xytext=(4, 2.2), arrowprops=dict(arrowstyle="->", color=arrow))
        return build
    red = render(chart("tab:red"))
    assert "peak" in red and red != render(chart(None)) and red == render(chart("black")), red   # the arrow is ink, in any colour it is not a third series


def test_light_spines_are_the_frame():
    frame = render(lambda ax: (ax.plot(X, np.sin(X)), [s.set_color("0.75") for s in ax.spines.values()]))
    assert "┌" in frame and "┘" in frame, frame   # a spine is the axes frame in any colour, never a gridline


def test_svg_classes_decide_frame_and_grid_whatever_the_colour():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="120" viewBox="0 0 400 120">
<g class="gridlayer"><path class="ygrid crisp" d="M 0 105 L 400 105" style="fill:none;stroke:#222"/></g>
<path class="xlines-above crisp" d="M0,115.5H400" style="stroke:#ccc"/>
<g class="trace scatter"><path d="M 0 90 L 400 10" style="fill:none;stroke:#1f77b4;stroke-width:2"/></g></svg>"""
    text = tsa.render_svg(svg, 80)
    assert "─" * 60 in text and ink_columns(text), text
    assert tsa.render_svg(svg.replace("#222", "#tmp").replace("#ccc", "#222").replace("#tmp", "#ccc"), 80) == text   # swap the colours: the gridline stays hidden, the axis line stays drawn


def test_svg_vega_grid_rules_are_not_the_frame():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="120" viewBox="0 0 400 120">
<g class="mark-group role-axis"><g class="mark-rule role-axis-grid"><line x1="0" y1="105" x2="400" y2="105" style="stroke:#555"/></g>
<g class="mark-rule role-axis-domain"><line x1="0" y1="115" x2="400" y2="115" style="stroke:#888"/></g></g>
<g class="mark-line role-mark"><path d="M 0 90 L 400 10" style="fill:none;stroke:#4c78a8;stroke-width:2"/></g></svg>"""
    rows = tsa.render_svg(svg, 80).split("\n")
    assert sum("─" * 60 in r for r in rows) == 1 and ink_columns("\n".join(rows)), rows   # the domain line is drawn, the grid rule is not


# ---- explicit limits are the caller's domain -------------------------------------------------------------

def test_explicit_ylim_stays_explicit():
    spike = render(lambda ax: (ax.plot([0, 100, 0]), ax.set_ylim(0, 10)))
    ticks = y_ticks(spike)
    assert len(ticks) >= 2 and min(ticks) >= 0 and max(ticks) <= 10, spike
    assert BRAILLE.search("".join(body(spike)))   # the clipped spike is still drawn


def test_autoscaled_ylim_still_shows_the_whole_series():
    ticks = y_ticks(render(lambda ax: ax.plot([0, 100, 0])))
    assert min(ticks) <= 0 and max(ticks) >= 100, ticks


def test_one_explicit_side_leaves_the_other_padded():
    spike = render(lambda ax: (ax.plot([0, 100, 0]), ax.margins(y=0), ax.set_ylim(bottom=-10)))   # autoscaling alone would put the peak on the top edge
    ticks = y_ticks(spike)
    assert min(ticks) >= -10 and max(ticks) >= 100, spike
    assert not BRAILLE.search(next(r for r in spike.split("\n") if "┌" in r)), spike   # the free top is padded: the peak is not in the border row


@pytest.mark.parametrize("fix", [lambda ax: ax.set_ylim(ax.get_ylim()), lambda ax: ax.set_ylim(0, 100)], ids=["freeze", "equal-to-autoscale"])
def test_limits_equal_to_autoscale_stay_explicit(fix):
    spike = render(lambda ax: (ax.plot([0, 100, 0]), ax.margins(y=0), fix(ax)))
    assert BRAILLE.search(next(r for r in spike.split("\n") if "┌" in r)), spike   # the peak sits on the caller's top limit, not padded away from it


@pytest.mark.parametrize("build", [lambda ax: ax.bar(range(4), [3, 9, 5, 7]), lambda ax: ax.hist([1, 2, 2, 3, 3, 3, 3, 4, 4], bins=4)], ids=["bar", "hist"])
def test_bottom_on_sticky_zero_leaves_the_top_padded(build):
    def chart(fix):
        def b(ax):
            build(ax); ax.set_title("t")
            if fix: ax.set_ylim(bottom=0)
        return b
    fixed = render(chart(True))
    assert BLOCKS.search("".join(body(fixed))) and fixed == render(chart(False)), fixed   # bottom=0 is where autoscale puts it anyway: the free top keeps its padding, the tallest label stays inside


def test_explicit_xlim_stays_explicit():
    zoom = render(lambda ax: (ax.plot([0, 1, 2], [0, 1, 0]), ax.set_xlim(0.5, 1.5)))
    ticks = x_ticks(zoom)
    assert len(ticks) >= 2 and min(ticks) >= 0.5 and max(ticks) <= 1.5, zoom


# ---- crops show the cropped data, not the whole array squeezed in ----------------------------------------

HEAT = np.column_stack([np.zeros(6), np.linspace(0, 1, 6), np.ones(6), np.zeros(6)])   # four columns, each its own pattern


def heat(arr, xlim=None, ylim=None, **kw):
    def build(ax):
        ax.imshow(arr, aspect="auto", vmin=0, vmax=1, **kw)
        if xlim: ax.set_xlim(*xlim)
        if ylim: ax.set_ylim(*ylim)
    return render(build, cols=50, figsize=(6, 3))


def test_zoom_to_ones_column_shows_only_ones():
    zoom = heat(np.array([[0, 1]] * 6, float), xlim=(0.5, 1.5))
    assert "█" in zoom and not re.search("[░▒▓]", zoom), zoom


@pytest.mark.parametrize("name,crop,subset", [
    ("x middle", dict(xlim=(0.5, 2.5)), lambda: heat(HEAT[:, 1:3], extent=(0.5, 2.5, 5.5, -0.5))),
    ("x right", dict(xlim=(1.5, 3.5)), lambda: heat(HEAT[:, 2:4], extent=(1.5, 3.5, 5.5, -0.5))),
    ("rows, lower origin", dict(ylim=(1.5, 3.5), origin="lower"), lambda: heat(HEAT[2:4], origin="lower", extent=(-0.5, 3.5, 1.5, 3.5))),
    ("rows, upper origin", dict(ylim=(3.5, 1.5)), lambda: heat(HEAT[2:4], extent=(-0.5, 3.5, 3.5, 1.5))),
])
def test_heatmap_crop_matches_rendering_the_subset(name, crop, subset):
    cropped, expected = heat(HEAT, **crop), subset()
    assert len(set("".join(heat_cells(expected)))) >= 2, expected   # the subset is not flat
    assert heat_cells(cropped) == heat_cells(expected), f"{name}\n{cropped}\n{expected}"


# ---- SVG clip paths -------------------------------------------------------------------------------------

def line_svg(clip):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100" viewBox="0 0 400 100">
<defs><clipPath id="c">{clip}</clipPath></defs>
<g clip-path="url(#c)"><path d="M 0 90 L 400 10" style="fill:none;stroke:#1f77b4;stroke-width:2"/></g></svg>"""


def ink_columns(text):
    return sorted({c for r in text.split("\n") for c, ch in enumerate(r) if BRAILLE.match(ch)})


def test_svg_clip_rect_is_respected():
    cols = 80
    free = ink_columns(tsa.render_svg(line_svg('<rect x="0" y="0" width="400" height="100"/>'), cols))
    clipped = ink_columns(tsa.render_svg(line_svg('<rect x="160" y="0" width="80" height="100"/>'), cols))   # middle 20%
    assert free and free[0] <= 1 and free[-1] >= cols - 2          # the line really spans the canvas
    assert clipped and 0.4 * cols - 1 <= clipped[0] and clipped[-1] <= 0.6 * cols + 1, clipped


def test_svg_clip_rect_with_transform_and_nesting():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100" viewBox="0 0 400 100">
<defs><clipPath id="outer"><rect x="0" y="0" width="300" height="100"/></clipPath><clipPath id="inner"><rect x="0" y="0" width="100" height="100"/></clipPath></defs>
<g clip-path="url(#outer)"><g transform="translate(150 0)" clip-path="url(#inner)">
<path d="M -150 90 L 250 10" style="fill:none;stroke:#1f77b4;stroke-width:2"/></g></g></svg>"""
    cols = ink_columns(tsa.render_svg(svg, 80))
    assert cols and 0.375 * 80 - 1 <= cols[0] and cols[-1] <= 0.75 * 80 + 1, cols   # inner clip, moved right by the group transform, cut by the outer one


def test_svg_clip_outside_everything_draws_nothing():
    assert ink_columns(tsa.render_svg(line_svg('<rect x="0" y="0" width="400" height="100"/>'), 80))   # the same line, unclipped, is there
    assert not ink_columns(tsa.render_svg(line_svg('<rect x="500" y="0" width="10" height="10"/>'), 80))


def test_svg_dense_dark_line_outside_matplotlib_is_drawn():
    pts = " ".join(f"L {x:.1f} {50 - 40 * np.sin(x / 30):.1f}" for x in np.linspace(0, 400, 600))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100" viewBox="0 0 400 100">
<g class="gridlayer"><path class="ygrid crisp" d="M 0 50 L 400 50" style="fill:none;stroke:rgb(200,200,200)"/></g>
<g class="trace scatter"><path class="js-line" d="M 0 50 {pts}" style="fill:none;stroke:#222;stroke-width:2"/></g></svg>"""
    assert len(ink_columns(tsa.render_svg(svg, 80))) > 70   # unclassified strokes are unknown, not decoration: every short segment is kept
    grid_only = tsa.render_svg(svg.replace("#222", "none"), 80)
    assert not re.search("[─━]", grid_only), grid_only     # a known gridline is still a gridline


def test_svg_vega_view_border_is_not_data():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100" viewBox="0 0 400 100">
<g class="mark-group role-frame root"><g><path class="background" d="M 0.5 0.5 h 399 v 99 h -399 Z" style="fill:none;stroke:#ddd"/>
<g class="mark-line role-mark"><path d="M 20 80 L 380 20" style="fill:none;stroke:#4c78a8;stroke-width:2"/></g></g></g></svg>"""
    text = tsa.render_svg(svg, 80)
    assert ink_columns(text) and not re.search("[┌┐└┘│]", text), text   # the line is drawn, the view border is not


def test_svg_unsupported_clip_is_reported_not_ignored():
    text = tsa.render_svg(line_svg('<circle cx="200" cy="50" r="30"/>'), 80)
    assert "unsupported: clip-path #c" in text, text
    narrow = tsa.render_svg(line_svg('<circle cx="200" cy="50" r="30"/>').replace('"c"', '"clip83cf7exyplot"').replace("#c)", "#clip83cf7exyplot)"), 40)
    assert "clip83cf7exyplot" in narrow and max(map(len, narrow.split("\n"))) <= 40, narrow   # the note keeps the cols budget


def test_svg_plotly_tick_marks_are_frame():
    ticks = "".join(f'<path class="xtick ticks crisp" d="M{x},100v5" style="stroke:#444"/>' for x in range(0, 401, 50))
    yticks = "".join(f'<path class="ytick ticks crisp" d="M0,{y}h-5" style="stroke:#444"/>' for y in range(0, 101, 25))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="420" height="120" viewBox="-10 0 420 120">
<g class="minor-gridlayer"><path class="xgrid crisp" d="M 0 30 L 400 30" style="stroke:rgb(200,200,200)"/></g>
<g class="xaxislayer-above">{ticks}</g><g class="yaxislayer-above">{yticks}</g>
<path class="xlines-above crisp" d="M0,100.5H400" style="stroke:#444"/><path class="ylines-above crisp" d="M0.5,0V100" style="stroke:#444"/></svg>"""
    text = tsa.render_svg(svg, 80)
    assert not BRAILLE.search(text) and "─" * 60 in text, text   # ticks and the minor grid are not data: a clean axis frame, no braille blobs


def test_matplotlib_svg_zoom_stays_inside_the_axes():
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(X, np.sin(X)); ax.set_xlim(2, 5)
    try:
        with matplotlib.rc_context({"svg.fonttype": "none"}):
            buf = io.StringIO(); fig.savefig(buf, format="svg", dpi=72)
    finally:
        plt.close(fig)
    text = tsa.render_svg(buf.getvalue(), 80)
    rows = text.split("\n")
    frame = next(r for r in rows if "└" in r)
    left, right = frame.index("└"), len(frame.rstrip()) - 1
    outside = [(i, c) for i, r in enumerate(rows) for c, ch in enumerate(r) if BRAILLE.match(ch) and not left <= c <= right]
    assert not outside, text
    assert len(ink_columns(text)) > 30, text   # and the zoomed curve is there


# ---- series, sign and missing data -----------------------------------------------------------------------

def two_series(ax, drop=False):
    ax.plot(X, np.sin(X), label="low")
    if not drop: ax.plot(X, np.sin(X) + 10, label="high")


def check_both_series(text):
    rows = body(text)
    band = len(rows) // 4
    assert BRAILLE.search("".join(rows[:band])), "series in the upper band is missing"
    assert BRAILLE.search("".join(rows[-band:])), "series in the lower band is missing"
    assert len(set(re.findall("[●×▲◆■+○△]", text))) >= 2, "series keys: one glyph per series"


def test_removed_series_is_detected():
    check_both_series(render(two_series))
    with pytest.raises(AssertionError):
        check_both_series(render(lambda ax: two_series(ax, drop=True)))


def test_negative_values_keep_sign():
    down = render(lambda ax: ax.plot(np.arange(10), -np.arange(10) - 1.))
    ticks = y_ticks(down)
    assert ticks and max(ticks) <= 0 and min(ticks) < 0, down
    cols = [(c, r) for r, row in enumerate(body(down)) for c, ch in enumerate(row) if BRAILLE.match(ch)]
    first, last = min(cols), max(cols)
    assert first[1] < last[1], "a falling series must fall"

    bars = render(lambda ax: ax.bar(range(4), [3, -2, 4, -1]))
    rows = bars.split("\n")
    zero = next(i for i, r in enumerate(rows) if re.match(r"\s*0(\.0+)?\s*[│┌└]", r))
    above = sum(len(BLOCKS.findall(r)) for r in rows[:zero]); below = sum(len(BLOCKS.findall(r)) for r in rows[zero + 1:])
    assert below > 0 and above > below, bars   # negative bars hang under the zero line, positive ones stand over it


def test_missing_observations_stay_missing():
    y = np.sin(np.arange(100) / 8); y[40:60] = np.nan
    text = render(lambda ax: (ax.plot(np.arange(100), y), ax.set_xlim(0, 99)))
    rows = body(text)
    width = len(rows[0])
    ink = lambda lo, hi: sum(len(BRAILLE.findall(r[int(lo / 99 * width):int(hi / 99 * width)])) for r in rows)
    assert ink(0, 38) > 10 and ink(62, 99) > 10, text   # observations are drawn...
    assert ink(42, 58) == 0, text                       # ...and the gap between them is not bridged

    grid = np.array([[1, np.nan, 3], [np.nan, 2, np.nan]])
    cells = heat(grid / 4)   # levels 1 2 3 of 0..3
    assert heat_cells(cells) == ["▒ █", " ▓ "], cells   # a blank cell where an observation is missing, never a filled one
