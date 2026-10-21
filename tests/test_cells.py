import re

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
import numpy as np
import pytest
from wcwidth import wcswidth

from trendsetter_axi import render_figure, render_svg
from trendsetter_axi.cells import clusters, pack_entries, slice_cells, truncate, width, wrap
from trendsetter_axi.core import Canvas
from trendsetter_axi.mpl import render, TextRenderer

ANSI = re.compile(r"\x1b\[[0-9;:]*m")


def assert_budget(text, cols):
    # Independent oracle: do not let a bug in our width helper hide overflow.
    assert all(0 <= wcswidth(ANSI.sub("", line)) <= cols for line in text.splitlines())


def test_cell_measurement_and_slicing():
    text = "\x1b[31mA界e\u0301B\x1b[0m"
    assert width(text) == 5
    assert [(ANSI.sub("", s), w) for s, w in clusters(text)] == [("A", 1), ("界", 2), ("e\u0301", 1), ("B", 1)]
    assert ANSI.sub("", slice_cells(text, 1, 3)) == "界"
    assert ANSI.sub("", slice_cells(text, 1, 2)) == ""
    assert ANSI.sub("", slice_cells(text, 3, 4)) == "e\u0301"
    assert ANSI.sub("", truncate(text, 4)) == "A界…"
    lines = wrap(text, 3)
    assert [ANSI.sub("", line) for line in lines] == ["A界", "e\u0301B"]
    assert all(line.endswith("\x1b[0m") for line in lines)
    assert_budget("\n".join(lines), 3)


@pytest.mark.parametrize("cols", [40, 80, 120])
@pytest.mark.parametrize("color", [False, True])
@pytest.mark.parametrize("title", ["界" * 34, "e\u0301" * 60, "価格 e\u0301 " * 12])
def test_unicode_titles_and_styled_output(cols, color, title):
    fig = Figure(figsize=(8, 4))
    ax = fig.subplots()
    ax.plot([0, 1, 2], [1, 2, 1], label="系列 e\u0301")
    ax.legend()
    ax.set_title(title)
    ax.set_ylabel("測定 e\u0301 " * 12)
    text, _ = render(fig, cols, color=color)
    assert_budget(text, cols)
    plain = ANSI.sub("", text)
    if title == "界" * 34:
        assert plain.count("界") == 34
    assert "e\u0301" in plain
    if color:
        assert "\x1b[" in text


@pytest.mark.parametrize("cols", [40, 80, 120])
@pytest.mark.parametrize("color", [False, True])
@pytest.mark.parametrize("levels", [4, 8])
def test_color_key_wraps_only_between_complete_ranges(cols, color, levels):
    cv = Canvas(400, 200, cols)
    cv.levels = levels
    edges = [str(-100 + i * 25) for i in range(levels + 1)]
    cv.ramp = ("価格 e\u0301 " * 12, edges)
    text = cv.render(color)
    assert_budget(text, cols)
    rows = ANSI.sub("", text).splitlines()
    for low, high in zip(edges, edges[1:]):
        assert sum(f"{low}-{high}" in row for row in rows) == 1


def test_key_rejects_an_entry_that_cannot_fit_without_splitting():
    with pytest.raises(ValueError, match="color-key entry needs"):
        pack_entries("key", ["░ 123456789-987654321"], 10)


@pytest.mark.parametrize("cols", [40, 80, 120])
def test_caption_uses_same_budget(cols):
    fig = Figure(figsize=(8, 4))
    ax = fig.subplots()
    ax.plot(np.linspace(-1e12, 1e12, 100), np.arange(100))
    ax.set_xlim(-123456789.123456, 987654321.987654)
    text = render_figure(fig, cols)
    assert_budget(text, cols)
    assert "(figure xlim)" in text


@pytest.mark.parametrize("cols", [40, 80, 120])
def test_svg_unicode_text_budget(cols):
    svg = f'<svg viewBox="0 0 400 200"><text x="200" y="20" text-anchor="middle" class="title">{"界" * 34}</text></svg>'
    text = render_svg(svg, cols)
    assert_budget(text, cols)
    assert text.count("界") == 34


@pytest.mark.parametrize("value", [1e-100, 1e100])
def test_extreme_heat_values_use_compact_atomic_ranges(value):
    fig = Figure(figsize=(8, 4))
    ax = fig.subplots()
    im = ax.imshow(np.array([[value, value * 2], [value * 3, value * 4]]))
    fig.colorbar(im, ax=ax)
    text = render_figure(fig, 40)
    assert_budget(text, 40)
    key_rows = [line for line in text.splitlines() if "e-100" in line or "e+100" in line]
    assert len(key_rows) >= 2
    assert sum(len(re.findall(r"[░▒▓█] [\d.e+\-]+-[\d.e+\-]+", row)) for row in key_rows) == 4


@pytest.mark.parametrize("text", ["✈️", "👩\u200d👩", "🇺🇸", "e\u0301", "界"])
def test_complete_clusters_agree_with_terminal_width(text):
    assert width(text) == wcswidth(text)
    assert list(clusters(text)) == [(text, wcswidth(text))]
    assert wrap(text * 3, wcswidth(text)) == [text] * 3


def test_control_characters_cannot_bypass_footer_budget():
    cv = Canvas(400, 200, 40)
    cv.side = [("y", "label\t界" * 8)]
    text = cv.render()
    assert "\t" not in text
    assert_budget(text, 40)


def test_renderer_metrics_use_cells():
    rend = TextRenderer(400, 200, 40)
    assert rend.get_text_width_height_descent("界e\u0301", None, False)[0] == 3 * rend.cv.cw
