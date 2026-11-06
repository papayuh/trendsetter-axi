"""Styled labels stay on their value; grid snapping never distorts the data."""
import math
import re

import pytest

from examples.dashboard_demo import make_figures
from examples.scatter_brush import make_figure
from trendsetter_axi import render_styled
from trendsetter_axi.cells import SGR
from trendsetter_axi.dashboards import Dashboard
from trendsetter_axi.viewer import Projection, make_viewer


def axis(limits=(0, 100), ticks=range(0, 101, 20)):
    return {key: {'scale': 'linear', 'range': list(limits),
                  'ticks': [{'value': value, 'label': str(value)} for value in ticks]}
            for key in 'xy'}


@pytest.mark.parametrize('inverted', [False, True])
@pytest.mark.parametrize('extent,expected', [(12, 11), (13, 11), (14, 14), (11, 11), (2, 2)])
def test_projection_snaps_at_most_two_cells_or_keeps_original(extent, expected, inverted):
    scales = axis(limits=(100, 0) if inverted else (0, 100))
    p = Projection(scales, 8, 6, extent, extent)
    assert (p.cols, p.rows) == (expected, expected)
    assert p.axis == scales
    # Endpoints and data use the adjusted plot, not the old available extent.
    assert p.cell(*([scales['x']['range'][0]] * 2)) == (8, 6 + expected - 1)
    assert p.cell(*([scales['x']['range'][1]] * 2)) == (8 + expected - 1, 6)
    if expected == 11:
        for key, index in [('x', 0), ('y', 1)]:
            cells = [round(p.cell(tick['value'], tick['value'])[index])
                     for tick in scales[key]['ticks']]
            assert len(set(b - a for a, b in zip(cells, cells[1:]))) == 1


@pytest.mark.parametrize('ticks', [[], [0], [0, 10, 40, 100]])
def test_missing_or_uneven_ticks_do_not_snap(ticks):
    p = Projection(axis(ticks=ticks), 8, 6, 12, 12)
    assert (p.cols, p.rows) == (12, 12)


def assert_numeric_labels(lines, p, *, styled=False):
    shown = {'x': [], 'y': []}
    for row in range(p.top, p.top + p.rows):
        label = lines[row][:6].strip()
        if not label:
            continue
        value = float(label)
        assert row == round(p.cell(p.axis['x']['range'][0], value)[1])
        shown['y'].append((value, row))
    bottom = p.top + p.rows if styled else p.top + p.rows - 1
    for match in re.finditer(r'\S+', lines[bottom + 1][p.left:p.left + p.cols]):
        value = next(tick['value'] for tick in p.axis['x']['ticks']
                     if tick['label'] == match.group())
        col = p.left + match.start()
        projected = round(p.cell(value, p.axis['y']['range'][0])[0])
        expected = max(p.left, min(p.left + p.cols - len(match.group()),
                                   projected - len(match.group()) // 2))
        assert col == expected
        shown['x'].append((value, projected))
    assert all(len(labels) >= 2 for labels in shown.values())
    return shown


def assert_equal_pitch(labels):
    # Equal differences in values must have equal differences in cells.
    pitches = {}
    for (value, cell), (next_value, next_cell) in zip(labels, labels[1:]):
        delta = next_value - value
        if delta in pitches:
            assert next_cell - cell == pitches[delta]
        pitches[delta] = next_cell - cell


def test_dashboard_demo_all_four_panels_keep_ticks_on_their_projected_rows():
    m = Dashboard(make_figures(), color=False)
    m.layout(140, 44)
    frame = m.frame(interactive=False).splitlines()
    for index in range(3):
        v, tile = m.viewers[index], m.tiles[index]
        lines = [line[tile.x:tile.x + tile.cols] for line in frame[tile.y:tile.y + tile.rows]]
        shown = assert_numeric_labels(lines, v.projection)
        if index in (1, 2):
            assert_equal_pitch(shown['y'])
        # Snapping changes only the available grid, never the source limits.
        assert v.projection.limits == [tuple(v.record['axes'][0][key]['range']) for key in 'xy']
    assert m.viewers[1].projection.rows == 11  # 100 / 20: five two-row intervals.
    assert m.viewers[2].projection.rows == 10  # 90 / 10: nine one-row intervals.

    # Fourth panel is the unchanged static heat renderer, not a styled Projection.
    # Its inverted categorical projection puts each region at its own row centre.
    tile = m.tiles[3]
    lines = [line[tile.x:tile.x + tile.cols] for line in frame[tile.y:tile.y + tile.rows]]
    labels = ['iad', 'ams', 'sin', 'syd', 'fra', 'gru']
    actual = [next(row for row, line in enumerate(lines) if line.lstrip().startswith(label))
              for label in labels]
    top = actual[0]
    lo, hi = m.viewers[3].record['axes'][0]['y']['range']
    for value, row in enumerate(actual):
        projected = top + (1 - (value - lo) / (hi - lo)) * len(labels)
        assert row == math.floor(projected)
    assert actual == list(range(top, top + 6))
    assert all(label in lines[top + 6] for label in ['00', '06', '12', '18'])


@pytest.mark.parametrize('rows', [38, 40])
def test_single_render_styled_ticks_share_snapped_data_projection(rows):
    fig = make_figure()
    viewer = make_viewer(fig)
    viewer.layout(120, rows)
    frame = render_styled(fig, 120, rows, color=False).splitlines()
    shown = assert_numeric_labels(frame, viewer.projection, styled=True)
    assert viewer.projection.cols == 67  # Six eleven-column intervals.
    assert_equal_pitch(shown['x'])
    if rows == 40:
        assert viewer.projection.rows == 26  # Five five-row intervals.
        assert_equal_pitch(shown['y'])
    else:
        assert viewer.projection.rows == 25  # Four-row shrink exceeds budget.
    assert SGR.sub('', viewer.frame()).splitlines()[:-1] == frame[:-1]


def test_colliding_ticks_are_dropped_without_relocation():
    # Fixed tick lists also exercise crowded x labels. A nonuniform list must
    # retain the original projection, even when some labels have to disappear.
    fig = make_figures()[2]
    ax = fig.axes[0]
    ax.set_xticks([0, 1, 2, 3, 50, 100])
    ax.set_yticks([0, 1, 2, 3, 50, 90])
    m = Dashboard([fig], color=False)
    m.layout(80, 24)
    p, tile = m.viewers[0].projection, m.tiles[0]
    frame = m.frame(interactive=False).splitlines()
    lines = [line[tile.x:tile.x + tile.cols] for line in frame[tile.y:tile.y + tile.rows]]
    shown = assert_numeric_labels(lines, p)
    assert len(shown['y']) < 6
    assert len(shown['x']) < 6
    assert (p.cols, p.rows) == (69, 12)
