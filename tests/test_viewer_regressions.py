"""Behavioral regressions for shared styled drawing and interaction geometry."""
import math

from matplotlib.figure import Figure
import numpy as np
import pytest

from trendsetter_axi import from_figure, render_styled
from trendsetter_axi.cells import SGR, clean_text, width
from trendsetter_axi.styled import PALETTE, RIGHT, UP, draw
from trendsetter_axi.viewer import line_edges, make_viewer


def model(source, cols=120, rows=38):
    viewer = make_viewer(source)
    viewer.layout(cols, rows)
    return viewer


def colored_cells(frame):
    """Decode foreground colors from the emitted truecolor terminal protocol."""
    rows, fg = [], None
    for line in frame.splitlines():
        cells, start = [], 0
        for match in SGR.finditer(line):
            cells.extend((ch, fg) for ch in line[start:match.start()])
            codes = list(map(int, match.group()[2:-1].split(';')))
            if codes[:2] == [38, 2]:
                fg = tuple(codes[2:5])
            elif codes == [0]:
                fg = None
            start = match.end()
        cells.extend((ch, fg) for ch in line[start:])
        rows.append(cells)
    return rows


def rectangle_cells(cells, bounds):
    c0, r0, c1, r1 = bounds
    return [cells[r][c]
            for r in range(math.floor(r0), math.ceil(r1))
            for c in range(math.floor(c0), math.ceil(c1))]


@pytest.mark.parametrize('inverted', [False, True])
@pytest.mark.parametrize('yscale', ['linear', 'log'])
@pytest.mark.parametrize('saved', [False, True])
def test_log_steps_mid_projects_arithmetic_data_midpoint(inverted, yscale, saved):
    ax = Figure().subplots()
    ax.plot([1, 100], [1, 100], drawstyle='steps-mid')
    ax.set(xscale='log', yscale=yscale, xlim=(1, 100), ylim=(1, 100))
    if inverted:
        ax.invert_xaxis()
        ax.invert_yaxis()
    v = model(from_figure(ax.figure) if saved else ax.figure)
    p = v.projection
    path, left, right = next(line_edges(v.record['marks'][0], v.points, p))
    mid, _ = p.cell(50.5, 1)
    assert path[1][0] == pytest.approx(mid)
    assert path[2][0] == pytest.approx(mid)
    row = (path[1][1] + path[2][1]) / 4
    assert v.nearest(mid, row) in (left, right)
    cells = colored_cells(v.frame())
    assert any(cells[r][c][0] != ' '
               for r in range(math.floor(row) - 1, math.floor(row) + 2)
               for c in range(math.floor(mid) - 1, math.floor(mid) + 2))


@pytest.mark.parametrize('horizontal', [False, True])
@pytest.mark.parametrize('inverted', [False, True])
@pytest.mark.parametrize('negative_width', [False, True])
@pytest.mark.parametrize('negative_value', [False, True])
def test_bar_rectangles_clip_both_log_axes_before_projection(
        horizontal, inverted, negative_width, negative_value):
    ax = Figure().subplots()
    widths = [-4, -2] if negative_width else [4, 2]
    values, bases = ([-3, 1], [2, 2]) if negative_value else ([2, 2], [0, 1])
    if horizontal:
        ax.barh([1, 10], values, left=bases, height=widths)
    else:
        ax.bar([1, 10], values, bottom=bases, width=widths)
    position_range, value_range = (.1, 20), (.1, 4)
    ax.set(xscale='log', yscale='log',
           xlim=value_range if horizontal else position_range,
           ylim=position_range if horizontal else value_range)
    if inverted:
        ax.invert_xaxis()
        ax.invert_yaxis()
    v = model(ax.figure)
    p, point = v.projection, v.points[0]
    xy0 = (.1, .1)
    xy1 = (2, 3) if horizontal else (3, 2)
    a, b = p.cell(*xy0), p.cell(*xy1)
    expected = min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])
    bounds = v.bar_bounds(point)
    assert bounds == pytest.approx(expected)
    c0, r0, c1, r1 = bounds
    assert v.nearest((c0 + c1) / 2, (r0 + r1) / 2) == point
    assert any(ch != ' ' and rgb == PALETTE[0]
               for ch, rgb in rectangle_cells(colored_cells(v.frame()), bounds))


@pytest.mark.parametrize('horizontal', [False, True])
@pytest.mark.parametrize('inverted', [False, True])
def test_saved_log_bar_footprint_clips_estimated_width(horizontal, inverted):
    ax = Figure().subplots()
    if horizontal:
        ax.barh([.1], [2])
    else:
        ax.bar([.1], [2])
    ax.set(xscale='log', yscale='log', xlim=(.01, 5), ylim=(.01, 5))
    if inverted:
        ax.invert_xaxis()
        ax.invert_yaxis()
    v = model(from_figure(ax.figure))
    bounds = v.bar_bounds(v.points[0])
    assert all(map(math.isfinite, bounds))
    c0, r0, c1, r1 = bounds
    assert v.nearest((c0 + c1) / 2, (r0 + r1) / 2) == v.points[0]
    assert any(rgb == PALETTE[0] for _, rgb in rectangle_cells(colored_cells(v.frame()), bounds))


@pytest.mark.parametrize('horizontal', [False, True])
def test_log_bars_wholly_outside_domain_have_no_drawable_rectangle(horizontal):
    ax = Figure().subplots()
    if horizontal:
        ax.barh([-3, 2], [2, -2], left=[0, -1])
    else:
        ax.bar([-3, 2], [2, -2], bottom=[0, -1])
    ax.set(xscale='log', yscale='log', xlim=(.1, 5), ylim=(.1, 5))
    v = model(ax.figure)
    assert all(not any(map(math.isfinite, v.bar_bounds(point))) for point in v.points)
    p = v.projection
    assert v.nearest(p.left + p.cols / 2, p.top + p.rows / 2) is None
    cells = colored_cells(v.frame())
    assert not any(rgb == PALETTE[0] and ch != ' '
                   for r in range(p.top, p.top + p.rows)
                   for ch, rgb in cells[r][p.left:p.left + p.cols])


def test_oversized_actual_figure_fallback_omits_whole_chart_not_last_bars():
    ax = Figure().subplots()
    ax.barh([f'bar-{i}' for i in range(20)], range(1, 21))
    ax.set_xscale('symlog')
    v = model(ax.figure, 80, 24)
    assert len(v.static(80, 21).splitlines()) > 21
    frame = SGR.sub('', v.frame())
    assert 'Static chart omitted' in frame
    assert 'complete output does not fit' in frame
    assert 'bar-0' not in frame
    assert len(frame.splitlines()) == 24
    assert all(width(line) == 80 for line in frame.splitlines())
    assert 'omitted' in render_styled(ax.figure, 80, 24, color=False)


@pytest.mark.parametrize('series,points', [(1, 40), (8, 2)])
def test_saved_overview_checks_width_and_height_without_partial_data(series, points):
    ax = Figure().subplots()
    for i in range(series):
        ax.plot(range(points), range(points), label=f'series-{i}')
    ax.set_xscale('symlog')
    v = model(from_figure(ax.figure), 80, 24)
    overview = v.static_record().splitlines()
    assert len(overview) > 21 or max(map(width, overview)) > 80
    frame = SGR.sub('', v.frame())
    assert 'data overview omitted' in frame
    assert 'series-0' not in frame
    assert len(frame.splitlines()) == 24
    assert all(width(line) == 80 for line in frame.splitlines())


def test_fitting_fallback_keeps_complete_output():
    ax = Figure().subplots()
    ax.plot([1, 2], [3, 4])
    ax.set_xscale('symlog')
    v = model(from_figure(ax.figure))
    lines = v.static_record().splitlines()
    frame = SGR.sub('', v.frame()).splitlines()
    assert 'omitted' not in '\n'.join(frame)
    assert [line.rstrip() for line in frame[2:2 + len(lines)]] == list(map(clean_text, lines))


@pytest.mark.parametrize('horizontal', [False, True])
@pytest.mark.parametrize('cols,rows', [(80, 24), (120, 38)])
def test_saved_bar_width_notice_never_overwrites_exact_hover_footer(horizontal, cols, rows):
    ax = Figure().subplots()
    if horizontal:
        ax.barh([1], [5], left=[100])
    else:
        ax.bar([1], [5], bottom=[100])
    v = model(from_figure(ax.figure), cols, rows)
    v.hover = v.points[0]
    for frame in (v.frame(), draw(v, interactive=False, color=False)):
        lines = SGR.sub('', frame).splitlines()
        assert 'widths estimated: 0.8' in lines[2]
        assert 'base=100.0' in lines[-2]
        assert 'top=105.0' in lines[-2]
        assert 'value=5.0' in lines[-2]


@pytest.mark.parametrize('xs', [[1], [1, math.nan, 10, 100], [1, math.nan, 10, math.nan, 100]])
@pytest.mark.parametrize('saved', [False, True])
def test_isolated_marked_line_knots_are_drawn_and_hoverable(xs, saved):
    ax = Figure().subplots()
    ax.plot(xs, [2] * len(xs), marker='o')
    ax.set(xscale='log', xlim=(.5, 200), ylim=(1, 4))
    ax.invert_xaxis()
    v = model(from_figure(ax.figure) if saved else ax.figure)
    edges = list(line_edges(v.record['marks'][0], v.points, v.projection))
    connected = {point.index for _, left, right in edges for point in (left, right)}
    for frame in (v.frame(), render_styled(from_figure(ax.figure) if saved else ax.figure)):
        cells = colored_cells(frame)
        for point in v.points:
            if point.index in connected:
                continue
            c, r = v.projection.cell(point.x, point.y)
            ch, rgb = cells[math.floor(r)][math.floor(c)]
            assert ch != ' ' and rgb is not None
            assert v.nearest(c, r) == point


@pytest.mark.parametrize('horizontal', [False, True])
@pytest.mark.parametrize('negative', [False, True])
@pytest.mark.parametrize('inverted', [False, True])
@pytest.mark.parametrize('saved', [False, True])
def test_discrete_bars_keep_palette_and_sub_eighth_nonzero_coverage(horizontal, negative, inverted, saved):
    ax = Figure().subplots()
    values = [-.01, -10] if negative else [.01, 10]
    for positions, label in (([1, 3], 'first'), ([2, 4], 'second')):
        if horizontal:
            ax.barh(positions, values, label=label)
        else:
            ax.bar(positions, values, label=label)
    value_range = (-10, 0) if negative else (0, 10)
    ax.set(xlim=value_range if horizontal else (0, 5),
           ylim=(0, 5) if horizontal else value_range)
    if inverted:
        ax.invert_xaxis()
        ax.invert_yaxis()
    source = from_figure(ax.figure) if saved else ax.figure
    v = model(source)
    for frame in (v.frame(), render_styled(source)):
        cells = colored_cells(frame)
        for point in v.points:
            ink = [(ch, rgb) for ch, rgb in rectangle_cells(cells, v.bar_bounds(point)) if ch != ' ']
            series = list(v.marks).index(point.mark)
            assert ink and all(rgb == PALETTE[series] for _, rgb in ink)
            if point.index == 0:
                assert all(ch in (RIGHT if horizontal else UP)[1:8] for ch, _ in ink)
            else:
                assert any(ch == '█' for ch, _ in ink)


@pytest.mark.parametrize('bars_last', [False, True])
def test_mixed_line_and_bar_drawing_preserves_record_painter_order(bars_last):
    ax = Figure().subplots()
    ax.bar([2], [10], width=2)
    ax.plot([0, 4], [5, 5])
    ax.set(xlim=(0, 4), ylim=(0, 10))
    record = from_figure(ax.figure)
    record['marks'].sort(key=lambda mark: (mark['kind'] == 'bars') == bars_last)
    v = model(record)
    c, r = map(round, v.projection.cell(2, 5))
    cells = colored_cells(v.frame())
    assert cells[r][c][0] == ('█' if bars_last else '─')


def test_gappy_line_traversal_has_linear_comparison_cost_for_draw_and_hover():
    class CountedIndex(int):
        comparisons = 0
        __hash__ = int.__hash__

        def __eq__(self, other):
            type(self).comparisons += 1
            return int.__eq__(self, other)

    ax = Figure().subplots()
    xs = [value for i in range(2000) for value in (i, math.nan)]
    ax.plot(xs, [1] * len(xs), marker='o')
    v = model(ax.figure)
    mark = v.record['marks'][0]
    mark['breaks'] = list(map(CountedIndex, mark['breaks']))
    assert not list(line_edges(mark, v.points, v.projection))
    assert CountedIndex.comparisons <= len(v.points) * 4
    CountedIndex.comparisons = 0
    assert v.frame()
    assert CountedIndex.comparisons <= len(v.points) * 4
    CountedIndex.comparisons = 0
    point = v.points[len(v.points) // 2]
    assert v.nearest(*v.projection.cell(point.x, point.y)) == point
    assert CountedIndex.comparisons <= len(v.points) * 4


@pytest.mark.parametrize('axis', ['x', 'y'])
@pytest.mark.parametrize('style', ['default', 'steps-pre', 'steps-post', 'steps-mid'])
@pytest.mark.parametrize('nonpositive', [0, -1])
@pytest.mark.parametrize('inverted', [False, True])
@pytest.mark.parametrize('saved', [False, True])
def test_nonpositive_log_lines_use_explicit_fallback(axis, style, nonpositive, inverted, saved):
    ax = Figure().subplots()
    xs, ys = ([nonpositive, 10], [1, 2]) if axis == 'x' else ([1, 2], [nonpositive, 10])
    ax.plot(xs, ys, drawstyle=style, marker='o')
    getattr(ax, f'set_{axis}scale')('log')
    getattr(ax, f'set_{axis}lim')(1, 10)
    if inverted:
        getattr(ax, f'invert_{axis}axis')()
    original = from_figure(ax.figure)
    source = original if saved else ax.figure
    v = model(source)
    assert v.projection is None
    assert f'nonpositive {axis} line coordinates' in v.reason
    assert v.nearest(20, 15) is None
    assert 'Static view:' in SGR.sub('', v.frame())
    assert 'Static view:' in render_styled(source, color=False)
    v.layout(160, 45)
    assert v.projection is None and v.reason
    assert from_figure(ax.figure) == original


@pytest.mark.parametrize('first,second', [(a, b) for a in ('bars', 'line', 'points')
                                         for b in ('bars', 'line', 'points')])
@pytest.mark.parametrize('zorders', [(0, 3), (3, 0), (2, 2)])
def test_actual_figure_painter_order_controls_drawing_and_picking(first, second, zorders):
    ax = Figure().subplots()
    for kind, name, zorder in zip((first, second), ('first', 'second'), zorders):
        if kind == 'bars':
            ax.bar([30], [24], width=20, label=name, zorder=zorder)
        elif kind == 'line':
            ax.plot([0, 67], [12, 12], label=name, zorder=zorder)
        else:
            count = 3 if name == 'first' else 1
            ax.scatter([30] * count, [12] * count, label=name, zorder=zorder)
    ax.set(xlim=(0, 67), ylim=(0, 24))
    original = from_figure(ax.figure)
    v = model(ax.figure)
    assert not v.reason
    index = 0 if zorders[0] > zorders[1] else 1
    name = ('first', 'second')[index]
    kind = (first, second)[index]
    c, r = map(round, v.projection.cell(30, 12))
    expected = {'bars': '█', 'line': '─', 'points': '⠁'}[kind]
    for frame in (v.frame(), render_styled(ax.figure)):
        assert colored_cells(frame)[r][c][0] == expected
    assert v.nearest(c, r).name == name
    v.mouse(35, c, r, False)
    assert v.hover.name == name
    assert from_figure(ax.figure) == original
    assert all('width' not in mark for mark in original['marks'])


@pytest.mark.parametrize('reverse_patches', [False, True])
def test_unrepresentable_bar_patch_order_uses_explicit_figure_fallback(reverse_patches):
    ax = Figure().subplots()
    bars = ax.bar([1, 1], [3, 3], zorder=1)
    ax.plot([0, 2], [1, 1], zorder=2)
    bars[0 if reverse_patches else 1].set_zorder(3)
    v = model(ax.figure)
    assert v.projection is None
    assert 'painter order unavailable' in v.reason
    assert 'Static view:' in SGR.sub('', v.frame())


@pytest.mark.parametrize('kind', ['points', 'line', 'bars', 'barh'])
@pytest.mark.parametrize('cols', [80, 120])
@pytest.mark.parametrize('saved', [False, True])
def test_long_labels_cannot_displace_exact_hover_numbers(kind, cols, saved):
    ax = Figure().subplots()
    name = 'series-name-' * 20
    label = 'category-界' * 20
    x, y = 1.2345678901234567e200, -2.345678901234567e180
    if kind == 'points':
        ax.scatter([x], [y], label=name)
    elif kind == 'line':
        ax.plot([x], [y], marker='o', label=name)
    elif kind == 'bars':
        ax.bar([label], [2.345678901234567e200], bottom=[-1.2345678901234567e200], label=name)
    else:
        ax.barh([label], [2.345678901234567e200], left=[-1.2345678901234567e200], label=name)
    original = from_figure(ax.figure)
    v = model(original if saved else ax.figure, cols, 38)
    point = v.points[0]
    v.hover = point
    fields = [f'x={point.x!r}', f'y={point.y!r}']
    if point.kind == 'bars':
        assert len(point.label) > 100
        fields += [f'base={point.base!r}', f'top={point.top!r}', f'value={point.top - point.base!r}']
    for frame in (v.frame(), draw(v, interactive=False, color=False)):
        lines = SGR.sub('', frame).splitlines()
        footer = lines[-4:-1]
        assert all(any(field in line for line in footer) for field in fields)
        assert all(width(line) == cols for line in lines)
        assert '…' in '\n'.join(footer)
    assert from_figure(ax.figure) == original


@pytest.mark.parametrize('widths', [False, True])
@pytest.mark.parametrize('labels', [False, True])
def test_bar_defaults_do_not_access_whole_series_per_point(widths, labels):
    class CountedList(list):
        length_calls = 0

        def __len__(self):
            self.length_calls += 1
            return super().__len__()

    ax = Figure().subplots()
    ax.bar(range(300), [1] * 300)
    ax.set(xlim=(-1, 301), ylim=(0, 2))
    source_viewer = model(ax.figure)
    record = source_viewer.record
    mark = record['marks'][0]
    if not widths:
        mark.pop('width')
    if not labels:
        mark.pop('labels')
    xs = CountedList(mark['x'])
    mark['x'] = xs
    v = model(record)
    assert len(v.points) == 300
    assert xs.length_calls <= 4
    xs.length_calls = 0
    for point in v.points:
        assert all(map(math.isfinite, v.bar_bounds(point)))
    assert v.frame()
    assert v.nearest(*v.projection.cell(150, 1.8)) is None
    assert xs.length_calls <= 4
    point = v.points[150]
    assert point.label == (mark['labels'][150] if labels else '')
    c0, _, c1, _ = v.bar_bounds(point)
    expected = v.projection.cell(point.x + .4, 0)[0] - v.projection.cell(point.x - .4, 0)[0]
    assert c1 - c0 == pytest.approx(expected)


@pytest.mark.parametrize('encoding', ['mapped-color', 'colorbar', 'literal-color', 'size', 'edge-color',
                                      'alpha', 'linewidth'])
def test_scatter_encodings_use_explicit_fallback_without_changing_public_records(encoding):
    ax = Figure().subplots()
    options = {
        'mapped-color': {'c': [10, 20]},
        'colorbar': {'c': [10, 20]},
        'literal-color': {'c': ['red', 'blue']},
        'size': {'s': [10, 100]},
        'edge-color': {'edgecolors': ['red', 'blue']},
        'alpha': {'alpha': [.2, .8]},
        'linewidth': {'linewidths': [1, 5]},
    }[encoding]
    collection = ax.scatter([1, 2], [2, 3], **options)
    if encoding == 'colorbar':
        ax.figure.colorbar(collection, ax=ax)
    original = from_figure(ax.figure)
    v = model(ax.figure)
    assert v.projection is None
    assert 'encoding' in v.reason
    assert 'Static view:' in SGR.sub('', v.frame())
    assert 'Static view:' in render_styled(ax.figure, color=False)
    assert v.nearest(20, 15) is None
    assert from_figure(ax.figure) == original


def test_uniform_scatter_style_and_hidden_encoded_artists_remain_interactive():
    ax = Figure().subplots()
    ax.scatter([1, 2], [2, 3], s=[20, 20], c=['red', 'red'], linewidths=[2, 2], label='uniform')
    hidden = ax.scatter([3, 4], [4, 5], s=[10, 100], c=[1, 2], visible=False)
    colorbar = ax.figure.colorbar(hidden, ax=ax)
    colorbar.ax.set_visible(False)
    original = from_figure(ax.figure)
    v = model(ax.figure)
    assert not v.reason and v.projection is not None
    assert len(v.points) == 2
    for point in v.points:
        assert v.nearest(*v.projection.cell(point.x, point.y)) == point
    assert 'Static view:' not in render_styled(ax.figure, color=False)
    assert from_figure(ax.figure) == original


@pytest.mark.parametrize('scale', [1, 1e240, 1e-240])
@pytest.mark.parametrize('cols', [80, 120])
@pytest.mark.parametrize('saved', [False, True])
def test_statistics_and_points_table_emit_complete_bounded_numbers(scale, cols, saved):
    ax = Figure().subplots()
    xs = np.array([-12350, -12340, -12330, 37020]) * scale
    ys = np.array([1, 2, 3, 10]) * scale
    ax.scatter(xs, ys, label='samples')
    ax.set(xlim=(-13000 * scale, 38000 * scale), ylim=(0, 12 * scale))
    original = from_figure(ax.figure)
    v = model(original if saved else ax.figure, cols)
    p = v.projection
    v.mouse(0, p.left, p.top, False)
    v.mouse(32, p.left + p.cols // 2, p.top + p.rows - 1, False)
    v.mouse(0, p.left + p.cols // 2, p.top + p.rows - 1, True)
    chosen = v.chosen()
    assert len(chosen) == 3
    side = p.left + p.cols + 9
    panel = cols - side - 1
    table_row = 15
    ordered = sorted(chosen, key=lambda point: -point.x)
    for frame in (v.frame(), draw(v, interactive=False, color=False)):
        lines = SGR.sub('', frame).splitlines()
        assert all(width(line) == cols for line in lines)
        assert int(lines[3][side + 14:side + 23]) == 3
        assert int(lines[3][side + 24:side + 33]) == 4
        assert lines[4][side + 14:side + 23].strip() == '75%'
        for row, values in ((5, xs), (6, ys)):
            selected = float(lines[row][side + 14:side + 23])
            visible = float(lines[row][side + 24:side + 33])
            expected_selected = math.fsum(float(value) / 3 for value in values[:3])
            expected_visible = math.fsum(float(value) / 4 for value in values)
            assert selected == pytest.approx(expected_selected, rel=.05, abs=scale * 1e-9)
            assert visible == pytest.approx(expected_visible, rel=.05, abs=scale * 1e-9)
        xcols = (panel - 16) // 2
        ycols = panel - 16 - xcols
        for row, point in enumerate(ordered, table_row + 1):
            x = float(lines[row][side + 15:side + 15 + xcols])
            y = float(lines[row][side + 16 + xcols:side + 16 + xcols + ycols])
            assert x == pytest.approx(point.x, rel=.05, abs=scale * 1e-9)
            assert y == pytest.approx(point.y, rel=.05, abs=scale * 1e-9)
    assert from_figure(ax.figure) == original


@pytest.mark.parametrize('near,far', [(a, b) for a in ('points', 'line', 'bars', 'barh')
                                     for b in ('points', 'line', 'bars', 'barh')])
@pytest.mark.parametrize('direction', ['x', 'y'])
@pytest.mark.parametrize('saved', [False, True])
def test_hover_prefers_near_geometry_over_separate_foreground_marks(near, far, direction, saved):
    ax = Figure().subplots()
    farther = (14, 12) if direction == 'x' else (12, 13)
    for kind, (x, y), name, zorder in ((near, (12, 12), 'near', 1), (far, farther, 'far', 3)):
        if kind == 'points':
            ax.scatter([x], [y], label=name, zorder=zorder)
        elif kind == 'line':
            ax.plot([x - .25, x + .25], [y, y], label=name, zorder=zorder)
        elif kind == 'bars':
            ax.bar([x], [.8], bottom=[y - .4], width=.8, label=name, zorder=zorder)
        else:
            ax.barh([y], [.8], left=[x - .4], height=.8, label=name, zorder=zorder)
    ax.set(xlim=(0, 67), ylim=(0, 24))
    original = from_figure(ax.figure)
    v = model(original if saved else ax.figure)
    c, r = v.projection.cell(12, 12)
    assert v.nearest(c, r).name == 'near'
    v.mouse(35, c, r, False)
    assert v.hover.name == 'near'
    assert 'near [' in SGR.sub('', v.frame())
    assert from_figure(ax.figure) == original


@pytest.mark.parametrize('zorders', [(1, 3), (3, 1), (2, 2)])
@pytest.mark.parametrize('kind', ['points', 'line'])
def test_equal_distance_hover_uses_source_painter_precedence(zorders, kind):
    ax = Figure().subplots()
    for x, name, zorder in zip((12, 14), ('first', 'second'), zorders):
        if kind == 'points':
            ax.scatter([x], [12], label=name, zorder=zorder)
        else:
            ax.plot([x, x], [11, 13], label=name, zorder=zorder)
    ax.set(xlim=(0, 67), ylim=(0, 24))
    v = model(ax.figure)
    expected = 'first' if zorders[0] > zorders[1] else 'second'
    assert v.nearest(*v.projection.cell(13, 12)).name == expected


@pytest.mark.parametrize('line_foreground', [False, True])
def test_fractional_line_bar_overlap_keeps_painter_precedence(line_foreground):
    ax = Figure().subplots()
    ax.bar([30.75], [20], width=20, label='bar', zorder=1 if line_foreground else 3)
    ax.plot([1.2, 60.3], [2.3, 22.1], label='line', zorder=3 if line_foreground else 1)
    ax.set(xlim=(0, 67), ylim=(0, 24))
    v = model(ax.figure)
    expected = 'line' if line_foreground else 'bar'
    assert v.nearest(*v.projection.cell(30.75, 12.2)).name == expected


@pytest.mark.parametrize('saved', [False, True])
def test_dense_continuous_lines_retain_batched_rasterization(monkeypatch, saved):
    from trendsetter_axi.core import Canvas

    ax = Figure().subplots()
    xs = np.linspace(0, 100, 100_000)
    ax.plot(xs, 2 + np.sin(xs))
    ax.set(xlim=(0, 100), ylim=(0, 4))
    source = from_figure(ax.figure) if saved else ax.figure
    v = model(source)
    calls = []
    rasterize = Canvas._line_dots

    def counted(canvas, path, *args, **kwargs):
        calls.append(len(path))
        assert len(calls) <= 1, 'continuous run split into per-edge rasterization calls'
        return rasterize(canvas, path, *args, **kwargs)

    monkeypatch.setattr(Canvas, '_line_dots', counted)
    for render_frame in (v.frame, lambda: render_styled(source)):
        calls.clear()
        frame = render_frame()
        assert calls == [len(xs)]
        cells = colored_cells(frame)
        p = v.projection
        assert any(ch != ' ' for row in cells[p.top:p.top + p.rows]
                   for ch, _ in row[p.left:p.left + p.cols])
    point = v.points[50_000]
    assert v.nearest(*v.projection.cell(point.x, point.y)) == point


@pytest.mark.parametrize('style', ['default', 'steps-pre', 'steps-post', 'steps-mid'])
@pytest.mark.parametrize('saved', [False, True])
def test_line_run_batching_preserves_gaps_steps_and_isolated_knots(monkeypatch, style, saved):
    from trendsetter_axi.core import Canvas

    ax = Figure().subplots()
    ax.plot([1, 2, 3, math.nan, 5, math.nan, 7, 8, 9],
            [1, 2, 1, math.nan, 2, math.nan, 1, 2, 1], drawstyle=style, marker='o')
    ax.set(xlim=(0, 10), ylim=(0, 3))
    source = from_figure(ax.figure) if saved else ax.figure
    v = model(source)
    calls = []
    rasterize = Canvas._line_dots

    def counted(canvas, path, *args, **kwargs):
        calls.append(len(path))
        return rasterize(canvas, path, *args, **kwargs)

    monkeypatch.setattr(Canvas, '_line_dots', counted)
    for render_frame in (v.frame, lambda: render_styled(source)):
        calls.clear()
        cells = colored_cells(render_frame())
        assert len(calls) == 2
        assert all(length >= 3 for length in calls)
        for x in (4, 6):
            assert v.nearest(*v.projection.cell(x, 1.5)) is None
            c, r = v.projection.cell(x, 1)
            assert cells[math.floor(r)][math.floor(c)][0] == ' '
        c, r = v.projection.cell(5, 2)
        assert cells[math.floor(r)][math.floor(c)][0] != ' '
    for point in v.points:
        assert v.nearest(*v.projection.cell(point.x, point.y)) == point
