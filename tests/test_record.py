"""Experimental records/queries: source arrays are the oracle, never rendered ink."""
import copy
from datetime import datetime, timezone
import json
import os
import subprocess
import sys

import numpy as np
from matplotlib.collections import PolyCollection
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
import pytest

from trendsetter_axi import from_figure, query, render
from test_handoff_fixtures import forecast, survival


def mark(rec, name):
    return next(m for m in rec['marks'] if m['name'] == name)


def line(x=(0, 10), y=(0, 10), style='default', **kwargs):
    ax = Figure().subplots()
    ax.plot(x, y, drawstyle=style, label='A', **kwargs)
    return ax


def answer(rec, *args):
    result = query(rec, *args)
    assert result['evidence'] and result['convention']
    assert 'unavailable' not in result, result
    return result['answer']


def unavailable(rec, *args):
    result = query(rec, *args)
    assert result['answer'] is None and result['unavailable']
    assert result['evidence'] and result['convention']
    return result['unavailable']


@pytest.mark.parametrize('half,want', [([2, 4, 6, 8, 10, 12, 14, 16], 6), ([2, 14, 6, 8, 10, 12, 4, 16], 2)])
def test_forecast_arrays_and_queries(half, want):
    fig = forecast(half)
    rec = from_figure(fig)
    band = mark(rec, '80% interval')
    assert band['x'] == list(range(1, 9))
    assert band['lo'] == [100 - h for h in half]
    assert band['hi'] == [100 + h for h in half]
    assert answer(rec, 'first_x_where', band['id'], 'hi-lo >= 24') == want
    assert answer(rec, 'band_width_at', band['id'], 1) == 4
    assert answer(rec, 'check', ['first_x_where', band['id'], 'width>=24', '==', want]) is True
    assert rec == json.loads(json.dumps(rec, allow_nan=False))
    assert rec['declared'] == {} and rec['source'] == 'matplotlib'


@pytest.mark.parametrize('style,want', [('steps-post', [95, 90]), ('default', [95.83333333333333, 91.66666666666667])])
def test_ecdf_interpolation_and_claims(style, want):
    ax = Figure().subplots()
    for name, y in [('A', [50, 95, 100]), ('B', [50, 90, 100])]:
        ax.plot([100, 160, 1000], y, drawstyle=style, label=name)
    rec = from_figure(ax.figure)
    assert [answer(rec, 'value_at', name, 300) for name in 'AB'] == pytest.approx(want)
    assert answer(rec, 'check', ['value_at', 'A', 300, '==', 95]) == (style == 'steps-post')
    assert 'outside the knots' in unavailable(rec, 'value_at', 'A', 50)
    missing = query(rec, 'check', ['value_at', 'A', 50, '==', 0])
    assert missing['verdict'] == 'unavailable' and missing['computed'] is None
    if style == 'steps-post': assert answer(rec, 'crossing', 'A', 97) == 1000


def test_km_requires_records_not_censor_count():
    early, late = [(2, 1), (3, 0), (4, 0), (10, 0)], [(2, 1), (7, 0), (8, 0), (10, 0)]
    records = []
    for dataset, want in [(early, 1), (late, 3), (early * 2, 2)]:
        rec = from_figure(survival(dataset)[0])
        records.append(copy.deepcopy(rec))
        assert 'duplicated subjects' in unavailable(rec, 'count_where', 'time >= 6')
        rec['declared']['records'] = [dict(time=t, event=e) for t, e in dataset]
        assert answer(rec, 'count_where', 'time >= 6') == want
    assert records[0] == records[2]


@pytest.mark.parametrize('step', [None, 'pre', 'post', 'mid'])
@pytest.mark.parametrize('descending', [False, True])
def test_fill_between_preserves_bounds_and_step(step, descending):
    x, lo, hi = np.array([0., 2., 7.]), np.array([1., 3., 2.]), np.array([5., 6., 8.])
    if descending: x, lo, hi = x[::-1], lo[::-1], hi[::-1]
    ax = Figure().subplots()
    ax.fill_between(x, lo, hi, step=step, label='band')
    rec = from_figure(ax.figure)
    m = mark(rec, 'band')
    assert m['kind'] == 'band' and m['interp'] == ('step-' + step if step else 'linear')
    assert m['x'] == list(x) and m['lo'] == list(lo) and m['hi'] == list(hi)
    assert answer(rec, 'band_width_at', 'band', 2) == 3
    assert answer(rec, 'band_width_at', 'band', 1) > 0


def test_interpolated_where_boundaries_and_crossed_branches():
    ax = Figure().subplots()
    ax.fill_between([0, 1, 2], [0, 2, 0], [1, 1, 1], where=[False, True, False], interpolate=True, label='where')
    rec = from_figure(ax.figure)
    assert mark(rec, 'where')['x'] == [.5, 1, 1.5]
    assert answer(rec, 'band_width_at', 'where', .75) == .5
    ax.fill_between([0, 1], [0, 2], [2, 0], label='crossed')
    assert mark(from_figure(ax.figure), 'crossed')['kind'] == 'area'


def test_band_gaps_and_unpairable_polygons():
    ax = Figure().subplots()
    ax.fill_between(range(5), [0, 0, np.nan, 0, 0], [1, 2, np.nan, 4, 5], label='gap')
    ax.fill_betweenx([0, 1], [0, 0], [2, 2], label='horizontal')
    ax.add_collection(PolyCollection([[(0, 0), (1, 0), (1, 2)]], label='triangle'))
    rec = from_figure(ax.figure)
    assert mark(rec, 'gap')['breaks'] == [2]
    assert 'gap' in unavailable(rec, 'band_width_at', 'gap', 2)
    assert mark(rec, 'horizontal')['kind'] == mark(rec, 'triangle')['kind'] == 'area'
    assert 'paired' in unavailable(rec, 'band_width_at', 'triangle', 1)


@pytest.mark.parametrize('horizontal', [False, True])
def test_bar_geometry_keeps_base_top_and_visibility(horizontal):
    ax = Figure().subplots()
    if horizontal: bars = ax.barh(['Start', 'Gain', 'Loss'], [100, 40, -15], left=[0, 100, 140], label='bridge')
    else: bars = ax.bar(['Start', 'Gain', 'Loss'], [100, 40, -15], bottom=[0, 100, 140], label='bridge')
    bars[1].set_visible(False)
    rec = from_figure(ax.figure)
    m = mark(rec, 'bridge')
    assert m['base'] == [0, 140] and m['top'] == [100, 125]
    assert m['labels'] == ['Start', 'Loss'] and rec['hidden'] == 1
    assert m['orientation'] == ('h' if horizontal else 'v')
    assert answer(rec, 'first_x_where', 'bridge', 'height < 0') == 2


def test_eligibility_gaps_identity_and_coverage_share_describe():
    from trendsetter_axi.mpl import describe
    ax = line([0, 1, 2, 3, 4], [0, 1, np.nan, 3, 4])
    ax.plot([90, 91], visible=False, label='hidden')
    ax.scatter([0, 1, 2], np.ma.array([1, 999, 3], mask=[0, 1, 0]), label='masked')
    ax.add_patch(Rectangle((0, 0), 1, 1))
    off = ax.figure.add_subplot(212)
    off.plot([999], label='off'); off.set_visible(False)
    rec = from_figure(ax.figure)
    old, _ = describe(ax.figure, {'series': []})
    assert len(rec['axes']) == 1 and rec['hidden'] == 2
    for name in ['A', 'masked']:
        m, s = mark(rec, name), next(s for s in old if s['name'] == name)
        assert np.array([m['x'], m['y']]).T.tolist() == s['points'].tolist()
        assert m['missing'] == s['missing'] == 1
    assert mark(rec, 'A')['breaks'] == [2]
    assert 'missing source interval' in unavailable(rec, 'value_at', 'A', 2)
    assert 'missing source interval' in unavailable(rec, 'crossing', 'A', 2)
    assert rec['not_described'] == [['Rectangle', 1]]
    assert rec == json.loads(json.dumps(rec, allow_nan=False))
    assert any('Rectangle' in text for text in rec['unavailable'])


def test_all_missing_geometry_and_figure_title():
    ax = line([0, 1], [np.nan, np.nan])
    ax.bar(range(8), [np.nan] * 8, label='absent')
    ax.figure.suptitle('source title')
    rec = from_figure(ax.figure)
    assert rec['title'] == 'source title'
    assert mark(rec, 'A')['x'] == [] and mark(rec, 'A')['missing'] == 2
    assert mark(rec, 'absent')['top'] == [] and mark(rec, 'absent')['missing'] == 8
    unavailable(rec, 'value_at', 'A', 0)
    assert answer(rec, 'facts')['marks'][0]['n'] == 0


def test_segments_keep_all_vertices_and_do_not_change_summary_coverage():
    from matplotlib.collections import LineCollection
    ax = Figure().subplots()
    ax.add_collection(LineCollection([[(0, 1), (1, 2), (2, 1)]], label='connector'))
    before = render(ax.figure).summary()
    rec = from_figure(ax.figure)
    assert mark(rec, 'connector')['segments'] == [[[0, 1], [1, 2], [2, 1]]]
    assert rec['not_described'] == [] and 'LineCollection' in before
    assert render(ax.figure).summary() == before


@pytest.mark.parametrize('mesh', [False, True])
def test_heat_missing_distinct_from_zero_and_nan(mesh):
    z = np.ma.array([[0., np.nan], [99., 3.]], mask=[[0, 0], [1, 0]])
    ax = Figure().subplots()
    if mesh: ax.pcolormesh(z)
    else: ax.imshow(z, origin='lower', extent=[0, 4, 0, 2])
    rec = from_figure(ax.figure)
    m = rec['marks'][0]
    assert m['z'] == [[0., None], [None, 3.]]
    assert m['masked'][1][0] and m['invalid'][0][1]
    assert not m['masked'][0][0] and not m['invalid'][0][0]
    assert ('coordinates' in m) == mesh
    json.dumps(rec, allow_nan=False)


def test_errorbar_coverage_and_numeric_arrays_not_rounded():
    ax = Figure().subplots()
    ax.errorbar([0, 1, 2], [1, np.nan, 3], yerr=[[.123456, 2, .3], [.4, 5, .6]], label='estimate')
    rec = from_figure(ax.figure)
    m = mark(rec, 'estimate')
    assert m['x'] == [0, 2]
    assert np.array(m['yerr']) == pytest.approx(np.array([[.123456, .4], [.3, .6]]))
    assert rec['not_described'] == []
    ax.errorbar([0], [1], yerr=1, lolims=True, fmt='none', label='limit')
    rec = from_figure(ax.figure)
    assert all(m['name'] != 'limit' for m in rec['marks'])
    assert any('one-sided' in s for s in rec['unavailable'])


@pytest.mark.parametrize('style,x', [('default', 5), ('steps-post', 10), ('steps-pre', 0), ('steps-mid', 5)])
def test_crossing_and_step_boundaries(style, x):
    rec = from_figure(line(style=style).figure)
    assert answer(rec, 'crossing', 'A', 5) == x
    assert answer(rec, 'crossing', 'A', 20) is None
    assert answer(rec, 'value_at', 'A', 0) == 0
    assert answer(rec, 'value_at', 'A', 10) == 10


def test_crossing_validates_dense_arrays_once(monkeypatch):
    from trendsetter_axi import queries
    rec = from_figure(line().figure)
    n = 2000
    rec['marks'][0].update(x=list(range(n)), y=list(range(n)))
    original = queries._finite
    scanned = 0
    def budget(values):
        nonlocal scanned
        scanned += len(values)
        assert scanned <= 4 * n + 10
        return original(values)
    monkeypatch.setattr(queries, '_finite', budget)
    assert answer(rec, 'crossing', 'A', n + 1) is None


def test_mixed_crossing_and_log_scale_space():
    ax = line([1, 100], [1, 100])
    ax.set(xscale='log', yscale='log')
    rec = from_figure(ax.figure)
    assert answer(rec, 'value_at', 'A', 10) == pytest.approx(10)
    assert answer(rec, 'crossing', 'A', 10) == pytest.approx(10)
    ax = line()
    ax.plot([0, 10], [8, 2], drawstyle='steps-post', label='B')
    assert answer(from_figure(ax.figure), 'crossing', 'A', 'B') == 8
    ax.set_yscale('symlog')
    rec = from_figure(ax.figure)
    assert answer(rec, 'value_at', 'A', 10) == 10
    assert 'symlog' in unavailable(rec, 'value_at', 'A', 5)


@pytest.mark.parametrize('style', ['default', 'steps-post', 'steps-pre', 'steps-mid'])
def test_descending_lines_keep_source_step_direction(style):
    rec = from_figure(line([10, 0], [10, 0], style).figure)
    expected = {'default': 7.5, 'steps-post': 10, 'steps-pre': 0, 'steps-mid': 10}[style]
    assert answer(rec, 'value_at', 'A', 7.5) == expected
    assert answer(rec, 'first_x_where', 'A', 'y>=0') == 10


def test_points_duplicate_and_nonmonotone_knots_never_guessed():
    rec = from_figure(line([0, 1], [2, 3], linestyle='none', marker='o').figure)
    assert rec['marks'][0]['kind'] == 'points'
    assert answer(rec, 'value_at', 'A', 1) == 3
    assert 'not interpolated' in unavailable(rec, 'value_at', 'A', .5)
    rec = from_figure(line([0, 1, 1, 2], [0, 1, 5, 6]).figure)
    assert 'multiple' in unavailable(rec, 'value_at', 'A', 1)
    assert 'duplicate' in unavailable(rec, 'value_at', 'A', 1.5)
    rec = from_figure(line([0, 2, 1], [0, 2, 1]).figure)
    assert answer(rec, 'value_at', 'A', 1) == 1
    assert 'monotone' in unavailable(rec, 'value_at', 'A', 1.5)


def test_date_units_category_mapping_and_ambiguous_names():
    ax = line([datetime(2026, 1, d, tzinfo=timezone.utc) for d in (1, 2)], [1, 2])
    rec = from_figure(ax.figure)
    assert rec['axes'][0]['x']['scale'] == 'date'
    assert rec['axes'][0]['x']['units'] == 'matplotlib date days'
    ax = line(['north', 'south'], [3, 4])
    ax.plot([0, 1], [2, 3], label='A')
    rec = from_figure(ax.figure)
    assert rec['axes'][0]['x']['mapping'] == {'north': 0, 'south': 1}
    assert 'ambiguous' in unavailable(rec, 'value_at', 'A', 0)
    assert answer(rec, 'value_at', 'm0', 0) == 3
    assert 'category' in unavailable(rec, 'value_at', 'm0', .5)


def test_facts_refuses_intent_aggregates_and_diff_keeps_geometry():
    ax = Figure().subplots()
    ax.bar(['Start', 'Gain', 'End'], [100, 40, 140], bottom=[0, 100, 0], label='bridge')
    ax.scatter([1, 2], ['north', 'south'], label='category')
    rec = from_figure(ax.figure)
    rec['declared'] = {'totals': ['Start', 'End'], 'interval_level': .8}
    facts = answer(rec, 'facts')
    assert facts['declared'] == rec['declared']
    assert any('Totals' in s for s in facts['unavailable'])
    category = next(m for m in facts['marks'] if m['kind'] == 'points')
    assert 'min' not in category and 'max' not in category
    assert 'total' not in facts['marks'][0] and 'r' not in category
    other = copy.deepcopy(rec)
    mark(other, 'bridge')['base'][1] = 99
    other['axes'][0]['y']['scale'] = 'log'
    result = answer(rec, 'diff', other)
    assert result['marks'][0]['fields']['base']['after'][1] == 99
    assert result['axes']
    assert answer(rec, 'diff', rec)['marks'] == []


def test_predicate_language_is_not_python_and_missing_is_not_false():
    rec = from_figure(line().figure)
    assert answer(rec, 'count_where', 'time >= 6 and event == 0', [dict(time=6, event=0), dict(time=2, event=1)]) == 1
    for expr in ["__import__('os')", '(1).__class__', "'x'*10000000000", '[1][0]', 'x ** 1000000']:
        unavailable(rec, 'first_x_where', 'A', expr)
    assert 'missing' in unavailable(rec, 'count_where', 'time >= 6', [{}])
    assert 'missing' in unavailable(rec, 'count_where', 'time >= 6', [dict(time=None)])
    unavailable(rec, 'count_where', 'time >= 6', [dict(time=float('nan'))])
    unavailable(rec, 'check', ['__import__', 'os', '==', 1])
    unavailable(rec, 'unknown')


@pytest.mark.parametrize('horizontal', [False, True])
@pytest.mark.parametrize('mixed', [False, True])
def test_bar_nondata_transforms_are_unavailable(horizontal, mixed):
    ax = Figure().subplots()
    ax.set(xlim=(0, 100), ylim=(0, 100))
    transform = ax.get_yaxis_transform() if horizontal else ax.get_xaxis_transform()
    kwargs = {} if mixed else dict(transform=transform)
    bars = (ax.barh([1, 2], [.2, .3], left=.1, label='bars', **kwargs) if horizontal else
            ax.bar([1, 2], [.2, .3], bottom=.1, label='bars', **kwargs))
    if mixed: bars[1].set_transform(transform)
    rec = from_figure(ax.figure)
    assert rec['marks'] == []
    assert any('non-data transform' in s and type(transform).__name__ in s for s in rec['unavailable'])
    assert answer(rec, 'facts')['marks'] == []


@pytest.mark.parametrize('horizontal', [False, True])
@pytest.mark.parametrize('angle', [90, -45])
@pytest.mark.parametrize('mixed', [False, True])
def test_rotated_bars_are_unavailable(horizontal, angle, mixed):
    ax = Figure().subplots()
    kwargs = {} if mixed else dict(angle=angle)
    bars = (ax.barh([0, 1], [2, 3], height=.8, label='rotated', **kwargs) if horizontal else
            ax.bar([0, 1], [2, 3], width=.8, label='rotated', **kwargs))
    if mixed: bars[1].set_angle(angle)
    rec = from_figure(ax.figure)
    assert rec['marks'] == []
    assert any(f'rectangle rotation {angle}' in reason for reason in rec['unavailable'])
    assert answer(rec, 'facts')['marks'] == []


@pytest.mark.parametrize('style', ['default', 'steps-pre', 'steps-post', 'steps-mid', 'markers'])
@pytest.mark.parametrize('errorbar', [False, True])
@pytest.mark.parametrize('transform_kind', ['axes', 'blended', 'affine'])
def test_nondata_lines_are_unavailable(style, errorbar, transform_kind):
    from matplotlib.transforms import Affine2D
    ax = Figure().subplots()
    ax.set(xscale='log', xlim=(1, 100), ylim=(0, 10))
    transform = {'axes': ax.transAxes, 'blended': ax.get_yaxis_transform(),
                 'affine': Affine2D().translate(1, 0) + ax.transData}[transform_kind]
    kwargs = dict(transform=transform, label='transformed')
    if style == 'markers': kwargs.update(linestyle='none', marker='o')
    else: kwargs['drawstyle'] = style
    if errorbar: ax.errorbar([0, 1], [0, 1], yerr=.1, **kwargs)
    else: ax.plot([0, 1], [0, 1], **kwargs)
    rec = from_figure(ax.figure)
    assert rec['marks'] == []
    assert any(f'non-data transform {type(transform).__name__}' in reason for reason in rec['unavailable'])
    unavailable(rec, 'value_at', 'transformed', 20)
    unavailable(rec, 'crossing', 'transformed', 5)


def test_data_step_lines_remain_available_on_log_axes():
    ax = line([1, 100], [0, 10], 'steps-mid')
    ax.set(xscale='log', xlim=(1, 100), ylim=(0, 10))
    rec = from_figure(ax.figure)
    assert answer(rec, 'value_at', 'A', 20) == 0
    assert answer(rec, 'crossing', 'A', 5) == 50.5


@pytest.mark.parametrize('limit,axis', [('lolims', 'y'), ('uplims', 'y'), ('xlolims', 'x'), ('xuplims', 'x')])
@pytest.mark.parametrize('reverse', [False, True])
def test_errorbar_limit_diagnostics_belong_to_each_container(limit, axis, reverse):
    ax = Figure().subplots()
    names = ['limited', 'ordinary']
    for name in reversed(names) if reverse else names:
        ax.errorbar([1, 2], [2, 3], xerr=.2, yerr=.3, label=name,
                    **({limit: True} if name == 'limited' else {}))
    rec = from_figure(ax.figure)
    assert mark(rec, 'limited')[axis + 'err'] == [[None, None], [None, None]]
    assert np.array(mark(rec, 'ordinary')[axis + 'err']) == pytest.approx(np.full((2, 2), .2 if axis == 'x' else .3))
    assert 'limited: sample support unavailable; one-sided bounds unknown' in rec['unavailable']
    assert 'ordinary: sample support unavailable; interval meaning requires declaration' in rec['unavailable']
    assert not any(reason.startswith('ordinary:') and 'one-sided' in reason for reason in rec['unavailable'])


def test_line_free_errorbar_centers_remain_available():
    ax = Figure().subplots()
    ax.errorbar([1, 2], [2, 3], yerr=.3, fmt='none', label='inferred')
    rec = from_figure(ax.figure)
    assert mark(rec, 'inferred')['kind'] == 'points'
    assert answer(rec, 'value_at', 'inferred', 1) == 2
    assert 'inferred: sample support unavailable; centers inferred from segment midpoints' in rec['unavailable']


def test_subject_tables_use_declarations_or_explicit_arguments():
    rec = from_figure(line().figure)
    rec['records'] = [dict(time=10)]
    unavailable(rec, 'count_where', 'time >= 6')
    assert query(rec, 'check', ['count_where', 'time >= 6', '==', 1])['verdict'] == 'unavailable'
    assert answer(rec, 'count_where', 'time >= 6', [dict(time=10)]) == 1
    rec['declared']['records'] = [dict(time=2)]
    assert answer(rec, 'count_where', 'time >= 6') == 0
    other = copy.deepcopy(rec)
    other['records'] = [dict(time=2)]
    assert answer(other, 'count_where', 'time >= 6') == 0
    assert answer(rec, 'diff', other)['declared'] is None
    other['declared']['records'] = [dict(time=10)]
    assert answer(other, 'count_where', 'time >= 6') == 1
    assert answer(other, 'check', ['count_where', 'time >= 6', '==', 1]) is True
    assert answer(rec, 'diff', other)['declared'] == dict(before=rec['declared'], after=other['declared'])
    assert answer(other, 'facts')['declared']['records'] == [dict(time=10)]
    assert answer(other, 'count_where', 'time >= 6', []) == 0
    assert answer(other, 'count_where', 'time >= 6', [dict(time=2)]) == 0


@pytest.mark.parametrize('polygon', [False, True])
@pytest.mark.parametrize('offset,transformed', [([1, 2], False), ([0, 0], True)])
def test_collection_offsets_are_unavailable(polygon, offset, transformed):
    from matplotlib.collections import LineCollection
    ax = Figure().subplots()
    if polygon: artist = ax.fill_between([0, 1], [0, 0], [1, 1], label='offset')
    else: artist = ax.add_collection(LineCollection([[(0, 0), (1, 1)]], label='offset'))
    artist.set_offsets([offset])
    if transformed: artist.set_offset_transform(ax.transData)
    rec = from_figure(ax.figure)
    assert rec['marks'] == []
    assert any('offset: geometry unavailable; collection offsets with transform' in s for s in rec['unavailable'])


@pytest.mark.parametrize('axis', [0, 1])
def test_errorbar_collection_offsets_are_unavailable(axis):
    ax = Figure().subplots()
    bars = ax.errorbar([0, 1], [1, 2], xerr=.1, yerr=.2, label='estimate')
    bars.lines[2][axis].set_offsets([[1, 2]])
    rec = from_figure(ax.figure)
    assert rec['marks'] == []
    assert any('collection offsets with transform' in s for s in rec['unavailable'])


@pytest.mark.parametrize('mesh', [False, True])
def test_heat_nondata_transforms_are_unavailable(mesh):
    ax = Figure().subplots()
    artist = ax.pcolormesh([[1, 2], [3, 4]]) if mesh else ax.imshow([[1, 2], [3, 4]])
    artist.set_transform(ax.transAxes)
    rec = from_figure(ax.figure)
    assert rec['marks'] == []
    assert any('non-data transform' in s and type(ax.transAxes).__name__ in s for s in rec['unavailable'])


def test_mesh_offsets_are_unavailable():
    ax = Figure().subplots()
    ax.pcolormesh([[1, 2], [3, 4]]).set_offsets([[1, 2]])
    rec = from_figure(ax.figure)
    assert rec['marks'] == []
    assert any('collection offsets with transform' in s for s in rec['unavailable'])


@pytest.mark.parametrize('polygon', [False, True])
def test_converted_collection_transforms_remain_available(polygon):
    from matplotlib.collections import LineCollection
    ax = Figure().subplots()
    ax.set(xlim=(0, 10), ylim=(0, 100))
    if polygon: ax.fill_between([.2, .8], [.1, .1], [.3, .3], transform=ax.transAxes, label='converted')
    else: ax.add_collection(LineCollection([[[.2, .1], [.8, .3]]], transform=ax.transAxes, label='converted'))
    m = mark(from_figure(ax.figure), 'converted')
    if polygon:
        assert m['lo'] == pytest.approx([10, 10]) and m['hi'] == pytest.approx([30, 30])
    else: assert np.array(m['segments']) == pytest.approx(np.array([[[2, 10], [8, 30]]]))


@pytest.mark.parametrize('style,want', [('default', .5), ('steps-pre', 0), ('steps-post', 1), ('steps-mid', .5)])
@pytest.mark.parametrize('other', [0, 'B'])
@pytest.mark.parametrize('descending', [False, True])
def test_tiny_crossing_signs_do_not_underflow(style, want, other, descending):
    rec = from_figure(line(style=style).figure)
    rec['marks'][0].update(x=[1, 0] if descending else [0, 1],
                           y=[1e-200, -1e-200] if descending else [-1e-200, 1e-200])
    rec['marks'].append(dict(rec['marks'][0], id='m1', name='B', y=[0, 0]))
    if descending and style in ('steps-pre', 'steps-post'): want = 1 - want
    assert answer(rec, 'crossing', 'A', other) == want


@pytest.mark.parametrize('descending', [False, True])
def test_tiny_crossed_fill_branches_are_not_paired(descending):
    ax = Figure().subplots()
    ax.fill_between([1, 0] if descending else [0, 1], [-1e-200, 1e-200], [1e-200, -1e-200], label='crossed')
    rec = from_figure(ax.figure)
    assert mark(rec, 'crossed')['kind'] == 'area'
    assert 'paired' in unavailable(rec, 'band_width_at', 'crossed', .5)


@pytest.mark.parametrize('descending', [False, True])
def test_interpolation_overflow_is_unavailable(descending):
    rec = from_figure(line().figure)
    rec['marks'][0].update(x=[1e308, -1e308] if descending else [-1e308, 1e308], y=[0, 1])
    assert 'overflow' in unavailable(rec, 'value_at', 'A', 0)
    assert 'overflow' in unavailable(rec, 'crossing', 'A', .5)


@pytest.mark.parametrize('band', [False, True])
def test_weighted_interpolation_avoids_y_difference_overflow(band):
    rec = from_figure(line().figure)
    rec['marks'][0].update(x=[0, 1], y=[-1e308, 1e308])
    if band: rec['marks'][0].update(kind='band', lo=[-1e308, 1e308], hi=[-1e308, 1e308])
    assert answer(rec, 'value_at', 'A', .5) == ([0, 0] if band else 0)
    if band: assert answer(rec, 'band_width_at', 'A', .5) == 0


@pytest.mark.parametrize('style', ['default', 'steps-mid'])
@pytest.mark.parametrize('descending', [False, True])
def test_large_midpoints_remain_in_domain(style, descending):
    rec = from_figure(line(style=style).figure)
    rec['marks'][0].update(x=[1.6e308, 1e308] if descending else [1e308, 1.6e308],
                           y=[1, 0] if descending else [0, 1])
    assert answer(rec, 'value_at', 'A', 1.4e308) == pytest.approx(1 if style == 'steps-mid' else 2 / 3)
    assert answer(rec, 'crossing', 'A', .5) == pytest.approx(1.3e308)


@pytest.mark.parametrize('other', [0, 1e308, 'B'])
def test_crossing_overflow_cannot_become_no_match(other):
    rec = from_figure(line().figure)
    rec['marks'][0].update(x=[0, 1], y=[-1e308, 1e308])
    rec['marks'].append(dict(rec['marks'][0], id='m1', name='B', y=[1e308, -1e308]))
    assert 'overflow' in unavailable(rec, 'crossing', 'A', other)


@pytest.mark.parametrize('expression', ['x >', "__import__('os')", "False and f()", 'x is None', "b'x'"])
def test_invalid_predicates_fail_without_rows(expression):
    rec = from_figure(line().figure)
    rec['marks'][0].update(x=[], y=[])
    unavailable(rec, 'count_where', expression, [])
    unavailable(rec, 'first_x_where', 'A', expression)
    assert answer(rec, 'count_where', 'x > 0', []) == 0
    assert answer(rec, 'first_x_where', 'A', 'x > 0') is None


def test_predicate_is_parsed_once_before_scanning(monkeypatch):
    from trendsetter_axi import queries
    rec = from_figure(line().figure)
    parse = queries.ast.parse
    calls = []
    def counted(*args, **kwargs):
        calls.append(args[0])
        return parse(*args, **kwargs)
    monkeypatch.setattr(queries.ast, 'parse', counted)
    assert answer(rec, 'count_where', 'x > 0', [dict(x=0), dict(x=1), dict(x=2)]) == 2
    assert calls == ['x > 0']
    calls.clear()
    assert answer(rec, 'first_x_where', 'A', 'y > 5') == 10
    assert calls == ['y > 5']


def test_record_reader_never_draws(monkeypatch):
    ax = line()
    def no_draw(*args): raise AssertionError('record extraction must not draw')
    monkeypatch.setattr(ax.figure, 'draw', no_draw)
    assert answer(from_figure(ax.figure), 'value_at', 'A', 5) == 5


def test_public_query_remains_callable_after_lazy_import():
    import trendsetter_axi as tsa
    rec = tsa.from_figure(line().figure)
    for _ in range(2): assert tsa.query(rec, 'value_at', 'A', 5)['answer'] == 5


def test_cli_and_imports_are_lazy(tmp_path):
    rec = from_figure(line().figure)
    path = tmp_path / 'record.json'
    path.write_text(json.dumps(rec))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.abspath('src'), os.environ.get('PYTHONPATH', '')]))
    result = subprocess.run([sys.executable, '-m', 'trendsetter_axi.queries', str(path), 'value_at', 'A', '5'], env=env, text=True, capture_output=True, check=True)
    assert json.loads(result.stdout)['answer'] == 5
    result = subprocess.run([sys.executable, '-c', "import sys, trendsetter_axi; assert not {'numpy','matplotlib','trendsetter_axi.record','trendsetter_axi.queries'} & sys.modules.keys(); from trendsetter_axi.queries import query; assert not {'numpy','matplotlib','trendsetter_axi.record'} & sys.modules.keys()"], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
