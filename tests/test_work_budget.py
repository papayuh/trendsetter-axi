"""Raster work bounds, plus an executable comparison with the old sampler."""
import time

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
import numpy as np
import pytest

from trendsetter_axi import render_figure, render_svg
from trendsetter_axi.core import Canvas


def legacy_line_dots(cv, p, dashes, clip=None, staircase=False):
    """Pre-budget sampler, retained only as an in-viewport fidelity oracle."""
    sx, sy = 2 / cv.cw, 4 / cv.ch
    out, dist = [], 0.0
    pat = None
    if dashes and dashes[1] is not None and len(dashes[1]) and sum(dashes[1]) > 0:
        pat = np.asarray(dashes[1], float)
        pat *= max(1, cv.cw * 0.6 / max(pat.min(), 1e-9) / 2)
    for a, b in zip(p, p[1:]):
        if not (np.isfinite(a).all() and np.isfinite(b).all()):
            continue
        seg = np.hypot(*(b - a))
        n = int(max(abs(b[0] - a[0]) * sx, abs(b[1] - a[1]) * sy)) + 2
        t = np.linspace(0, 1, n)
        q = a + (b - a) * t[:, None]
        if pat is not None:
            d = (dist + t * seg) % pat.sum()
            q = q[np.searchsorted(np.cumsum(pat), d, side="right") % 2 == 0]
        dist += seg
        rc = np.stack([np.floor(q[:, 1] * sy), np.floor(q[:, 0] * sx)], 1).astype(int)
        out.append(rc)
        if pat is None and abs(b[1] - a[1]) * sy >= 3 and abs(b[1] - a[1]) * sy > 2 * abs(b[0] - a[0]) * sx >= 1:
            out.append(rc ^ [0, 1])
    return np.concatenate(out) if out else np.zeros((0, 2), int)


@pytest.mark.parametrize("cols", [40, 80, 120])
def test_huge_offscreen_svg_has_bounded_allocations(monkeypatch, cols):
    # Before clipping this crossing segment requested billions of samples.
    # Guard allocation requests, not wall-clock duration or OOM side effects.
    original_linspace, original_arange, original_repeat = np.linspace, np.arange, np.repeat
    limit = 1024 * (max(2 * cols, 4 * 60) + 2)

    def linspace(start, stop, num=50, *args, **kwargs):
        assert num <= limit
        return original_linspace(start, stop, num, *args, **kwargs)

    def arange(*args, **kwargs):
        if len(args) == 1:
            assert args[0] <= limit
        return original_arange(*args, **kwargs)

    def repeat(a, repeats, *args, **kwargs):
        assert np.asarray(repeats).sum() <= limit
        return original_repeat(a, repeats, *args, **kwargs)

    monkeypatch.setattr(np, "linspace", linspace)
    monkeypatch.setattr(np, "arange", arange)
    monkeypatch.setattr(np, "repeat", repeat)
    for path in ("M -1000000000 50 L 1000000000 50",  # crosses viewport
                 "M 1000000000 0 L 2000000000 100"):  # entirely outside
        text = render_svg(f'<svg viewBox="0 0 100 100"><path d="{path}" fill="none" stroke="red"/><text x="0" y="10">safe</text></svg>', cols)
        assert "safe" in text
    cv = Canvas(100, 100, cols)
    assert not len(cv._line_dots(np.array([[1e9, 0], [2e9, 100]]), None))
    assert len(cv._line_dots(np.array([[-1e9, 50], [1e9, 50]]), None)) <= 8 * cv.rows * cv.cols
    # The alternate ECDF/staircase route must use the same bound.
    cv.stroke([np.array([[-1e9, 30], [1e9, 70]])], (1, 0, 0))
    cv.fam[(1., 0., 0.)] = "box"
    assert cv.render()


def dot_set(rc):
    return set(map(tuple, rc))


@pytest.mark.parametrize("dashes", [None, (0, [3, 2])])
def test_dense_extrema_and_nan_gaps_match_legacy(dashes):
    cv = Canvas(400, 200, 80)
    x = np.linspace(10, 390, 10000)
    y = np.full(len(x), 100.)
    y[117], y[8901] = 10, 190  # one-sample extrema cannot disappear
    y[3000:6000] = np.nan      # cannot connect across missing data
    p = np.column_stack([x, y])
    expected = legacy_line_dots(cv, p, dashes)
    actual = cv._line_dots(p, dashes)
    assert dot_set(actual) == dot_set(expected)
    assert len(actual) <= 8 * cv.rows * cv.cols
    assert not ((actual[:, 1] > 60) & (actual[:, 1] < 85)).any()
    if dashes is None:
        assert actual[:, 0].min() == 4
        assert actual[:, 0].max() == 76


def test_clip_precedes_sampling_and_keeps_crossing_geometry():
    cv = Canvas(100, 100, 40)
    p = np.array([[-1e9, 50], [1e9, 50], [np.nan, np.nan], [50, -1e9], [50, 1e9]])
    rc = cv._line_dots(p, None, (20, 20, 80, 80))
    assert len(rc)
    assert (rc.min(0) >= [16, 16]).all()
    assert (rc.max(0) <= [64, 64]).all()
    assert dot_set(cv._line_dots(np.array([[90, 0], [90, 100]]), None, (20, 20, 80, 80))) == set()


def test_clipping_preserves_dash_distance():
    cv = Canvas(100, 100, 40)
    # Skip 106px before the visible segment: its first dot must be in an off bin.
    p = np.array([[-106., 50.], [100., 50.]])
    rc = cv._line_dots(p, (0, [5, 5]))
    # Scaling grows the 5px pattern only on coarse canvases (not here).
    x = rc[:, 1] / (2 / cv.cw)
    assert not (x == 0).any()
    assert (x > 0).any()


def test_100k_points_same_output_faster(monkeypatch):
    fig = Figure(figsize=(8, 4))
    x = np.linspace(0, 10, 100000)
    fig.subplots().plot(x, np.sin(x))
    render_figure(fig, 80)  # warm caches for both implementations
    with monkeypatch.context() as patch:
        patch.setattr(Canvas, "_line_dots", legacy_line_dots)
        start = time.perf_counter()
        expected = render_figure(fig, 80)
        before = time.perf_counter() - start
    start = time.perf_counter()
    actual = render_figure(fig, 80)
    after = time.perf_counter() - start
    assert actual == expected
    # Broad regression budget; typical local speedup is >10x. Deterministic
    # allocation and returned-dot bounds above remain the main CI guarantees.
    assert after < before * 0.75, (before, after)
