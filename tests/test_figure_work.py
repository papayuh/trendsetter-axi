"""Figure-copy and discarded-draw work budgets (no machine-dependent timers)."""
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import numpy as np
import pytest

import trendsetter_axi as tsa
from trendsetter_axi import mpl
from benchmarks.render_identity import custom_artist, quiver


@pytest.mark.parametrize("managed", [False, True])
def test_clone_isolated_artist_graph_and_source_pixels(managed):
    fig = plt.figure() if managed else Figure()
    ax = fig.subplots()
    ax.bar(["alpha", "beta"], [2, 3])
    ax.set_title("Source title")

    def png():
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        return buf.getvalue()

    before = png()
    numbers = plt.get_fignums()
    try:
        for cols in (60, 80):
            tsa.render(fig, cols, color=True)
        assert plt.get_fignums() == numbers
        assert png() == before
        # Category counters and cached source artists must remain independent.
        work = tsa._copy(fig)
        try:
            assert work.axes[0].patches[0] is not ax.patches[0]
            work.axes[0].patches[0].set_height(99)
            work.axes[0].bar(["clone-only"], [1])
            assert list(ax.xaxis.units._mapping) == ["alpha", "beta"]
            ax.bar(["source-only"], [1])
            assert ax.xaxis.units._mapping["source-only"] == 2
        finally:
            plt.close(work)
    finally:
        plt.close(fig)


def test_local_formatter_falls_back_to_deepcopy(monkeypatch):
    ax = Figure().subplots()
    ax.plot([0, 1, 2], [1, 0, 3])
    ax.xaxis.set_major_formatter(lambda value, pos: f"local:{value:g}")
    calls = []
    original = tsa._deepcopy

    def deepcopy(fig):
        calls.append(fig)
        return original(fig)

    monkeypatch.setattr(tsa, "_deepcopy", deepcopy)
    first = tsa.render(ax.figure, 60)
    assert calls == [ax.figure]
    repeated = tsa.render(ax.figure, 60)
    assert (repeated.text, repeated.losses) == (first.text, first.losses)


@pytest.mark.parametrize("error", [RuntimeError, NotImplementedError])
def test_custom_copyable_state_can_reject_pickle(error):
    class Copyable:
        def __reduce_ex__(self, protocol):
            raise error("not serializable")

        def __deepcopy__(self, memo):
            return type(self)()

    fig = Figure()
    fig.subplots().plot([0, 1], [1, 0])
    fig.custom = Copyable()
    work = tsa._copy(fig)
    assert isinstance(work.custom, Copyable)
    assert work.custom is not fig.custom
    assert tsa.render_figure(fig, 60)


def test_serializable_figure_skips_python_deepcopy(monkeypatch):
    ax = Figure().subplots()
    ax.plot([0, 1], [1, 0])

    def unexpected(fig):
        pytest.fail("serializable figures should not walk the graph with deepcopy")

    monkeypatch.setattr(tsa, "_deepcopy", unexpected)
    assert tsa.render_figure(ax.figure, 60)


@pytest.mark.parametrize("shorten", [False, True])
def test_layout_pass_does_not_draw_data(monkeypatch, shorten):
    ax = Figure().subplots()
    ax.plot(np.linspace(0, 1, 1000), np.linspace(0, 1, 1000))
    if shorten:
        ax.set_xticks([0, 1], ["very long category label " * 8] * 2)
    calls = []
    original = mpl.TextRenderer.draw_path

    def path(renderer, *args, **kwargs):
        if renderer._role() == "data":
            calls.append(renderer)
        return original(renderer, *args, **kwargs)

    monkeypatch.setattr(mpl.TextRenderer, "draw_path", path)
    assert tsa.render_figure(ax.figure, 60)
    assert len(calls) == 1  # Not once per preliminary layout/shortening pass.


@pytest.mark.parametrize("make", [quiver, custom_artist], ids=["quiver", "custom-subclass"])
@pytest.mark.parametrize("shorten", [False, True])
@pytest.mark.parametrize("cols", [60, 80])
@pytest.mark.parametrize("color,ascii", [(False, False), (True, True)])
def test_draw_dependent_artists_match_full_draws(monkeypatch, make, shorten, cols, color, ascii):
    fig = make()
    ax = fig.axes[0]
    if shorten:
        ax.set_xticks([0, 9], ["very long category label " * 8] * 2)
    limits = ax.get_xlim(), ax.get_ylim()
    draws, retries = [], []
    original_draw, original_shorten = Figure.draw, mpl._shorten

    def draw(fig, renderer):
        draws.append(fig)
        return original_draw(fig, renderer)

    def shorten_labels(fig, cols):
        retries.append(fig)
        return original_shorten(fig, cols)

    monkeypatch.setattr(Figure, "draw", draw)
    monkeypatch.setattr(mpl, "_shorten", shorten_labels)

    def render():
        draws.clear()
        retries.clear()
        result = tsa.render(fig, cols, color=color, ascii=ascii, rows=18)
        assert len(draws) == 2 + int(shorten)
        assert len(retries) == int(shorten)
        return result

    actual = render()
    actual_text = tsa.render_figure(fig, cols, color=color)
    with monkeypatch.context() as baseline:
        baseline.setattr(mpl, "_layout", lambda fig, renderer: fig.draw(renderer))
        expected = render()
        expected_text = tsa.render_figure(fig, cols, color=color)
    assert actual.text.encode("utf-8") == expected.text.encode("utf-8")
    assert actual.losses == expected.losses
    assert actual_text.encode("utf-8") == expected_text.encode("utf-8")
    assert (ax.get_xlim(), ax.get_ylim()) == limits
    if make is quiver:
        assert ax.collections[0].scale is None
        assert ax.collections[0].width is None
    else:
        assert ax.lines[0].initial_ylim is None
        np.testing.assert_array_equal(ax.lines[0].get_ydata(), [0, 1])


def test_no_output_cached_between_calls():
    ax = Figure().subplots()
    line, = ax.plot([0, 1, 2], [0, 2, 0])
    first = tsa.render(ax.figure, 60)
    line.set_ydata([2, 0, 2])
    second = tsa.render(ax.figure, 60)
    assert first.text != second.text
    repeated = tsa.render(ax.figure, 60)
    assert (repeated.text, repeated.losses) == (second.text, second.losses)
