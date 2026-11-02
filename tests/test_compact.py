import copy
import math

from matplotlib.figure import Figure
import pytest

from trendsetter_axi import DisplayPreferences, Surface, present, render, render_compact, render_ranking
from trendsetter_axi.cells import width

NAMES = ['Retail servicing', 'Direct lending', 'Partner channel', 'Branch operations',
         'Digital acquisition', 'Wholesale lending', 'Application support', 'Field underwriting',
         'Central processing', 'Portfolio services']


def bounded(result, cols, rows):
    assert result.dimensions['width'] <= cols
    assert result.dimensions['height'] <= rows
    assert all(width(line) <= cols for line in result.text.split('\n'))
    assert len(result.text.split('\n')) <= rows


def fixture():
    ax = Figure(figsize=(7.5, 3.4)).subplots()
    ax.barh(NAMES, range(-9, 1))
    ax.invert_yaxis()
    ax.set(title='Team change', xlabel='pp')
    return ax.figure


def test_ten_teams_and_hard_40_by_8_limit():
    full = render_ranking(NAMES, range(-9, 1), cols=60, max_rows=11, title='Team change', unit='pp')
    bounded(full, 60, 11)
    assert full.dimensions['height'] == 11 and full.omitted == 0
    for name, value in zip(NAMES, range(-9, 1)):
        line = next(line for line in full.text.splitlines() if name in line)
        assert name + ' ' in line and str(value) in line
    small = render_ranking(NAMES, range(-9, 1), cols=40, max_rows=8, title='Team change', unit='pp')
    bounded(small, 40, 8)
    assert small.omitted == 4 and small.text.endswith('4 omitted')
    assert all(name in small.text for name in NAMES[:6])
    assert all(name not in small.text for name in NAMES[6:])
    assert len(small.records) == 10  # undisplayed is not missing source data


def test_shared_scale_and_explicit_signs_do_not_confuse_magnitudes():
    r = render_ranking(['negative', 'positive', 'half', 'zero'], [-10, 10, 5, 0], cols=40, max_rows=5)
    lines = r.text.splitlines()
    assert '-10' in lines[0] and '+10' in lines[1] and '+5' in lines[2] and '0' in lines[3]
    assert lines[0].count('█') == lines[1].count('█') == 12
    assert lines[2].count('█') == 6 and '█' not in lines[3]


@pytest.mark.parametrize('dtype', ['int8', 'int16', 'int32', 'int64'])
@pytest.mark.parametrize('ascii', [False, True])
@pytest.mark.parametrize('top_k', [None, 1, 2])
def test_fixed_width_integer_minima_share_python_integer_scale(dtype, ascii, top_k):
    import numpy as np
    from wcwidth import wcswidth

    minimum = int(np.iinfo(dtype).min)
    values = np.array([minimum, -minimum // 2], dtype=dtype)
    labels = ['loss', 'gain']
    kwargs = dict(cols=80, max_rows=2, ascii=ascii, color=False, top_k=top_k)
    expected = render_ranking(labels, [int(v) for v in values], **kwargs)
    with np.errstate(over='raise', invalid='raise'):
        result = render_ranking(labels, values, **kwargs)
    assert result.text == expected.text
    assert result.dimensions == expected.dimensions
    assert result.mode == 'ranking' and result.omitted == (1 if top_k == 1 else 0)
    bounded(result, 80, 2)
    assert all(0 <= wcswidth(line) <= 80 for line in result.text.splitlines())
    assert [r['label'] for r in result.records] == labels
    assert [r['exact'] for r in result.records] == [str(minimum), '+' + str(-minimum // 2)]
    assert all(type(r['value']) is type(v) and r['value'] == v for r, v in zip(result.records, values))
    shown = labels if top_k is None else ['gain', 'loss'][:top_k]
    lines = result.text.splitlines()
    assert [line.split()[0] for line in lines[:len(shown)]] == shown
    for label, count in [('loss', 12), ('gain', 6)]:
        if label in shown:
            line = next(line for line in lines if line.startswith(label + ' '))
            assert line.count('#' if ascii else '█') == count


@pytest.mark.parametrize('dtype', ['int8', 'int16', 'int32', 'int64'])
@pytest.mark.parametrize('cols,rows', [(80, 1), (12, 6), (3, 1)])
def test_fixed_width_integer_minima_keep_python_integer_budget_fallbacks(dtype, cols, rows):
    import numpy as np

    minimum = int(np.iinfo(dtype).min)
    values = np.array([minimum, -minimum // 2], dtype=dtype)
    expected = render_ranking(['loss', 'gain'], [int(v) for v in values], cols=cols, max_rows=rows)
    with np.errstate(over='raise', invalid='raise'):
        result = render_ranking(['loss', 'gain'], values, cols=cols, max_rows=rows)
    bounded(result, cols, rows)
    assert result.text == expected.text and result.dimensions == expected.dimensions
    assert (result.mode, result.omitted, result.reason) == (expected.mode, expected.omitted, expected.reason)
    assert [r['exact'] for r in result.records] == [str(minimum), '+' + str(-minimum // 2)]


@pytest.mark.parametrize('values', [[0, 0, 0], [3, 3, 3], [-2, -2, -2]])
def test_zeros_and_ties_keep_input_order(values):
    r = render_ranking(['c', 'a', 'b'], values)
    assert [record['label'] for record in r.records] == ['c', 'a', 'b']
    assert [line[0] for line in r.text.splitlines()] == ['c', 'a', 'b']


def test_top_k_is_explicit_and_stable_and_discloses_omissions():
    r = render_ranking(['c', 'a', 'b', 'd'], [1, 3, 3, 0], top_k=2, max_rows=3)
    assert r.text.splitlines()[0].startswith('a ') and r.text.splitlines()[1].startswith('b ')
    assert r.omitted == 2 and r.text.endswith('2 omitted')


def test_exact_precision_and_table_fallback_preserve_names_units_and_series():
    labels = ['東京e\u0301長い名前', 'Long combining e\u0301 label']
    r = render_ranking(labels, [-0.123456789, 1.25], name='Series A', unit='pp', cols=24, max_rows=14)
    assert r.mode == 'table' and r.omitted == 0
    bounded(r, 24, 14)
    assert '-0.123456789' in r.text and '+1.25' in r.text and 'Series A [pp]' in r.text
    assert [record['label'] for record in r.records] == labels
    assert 'e\u0301' in r.text


@pytest.mark.parametrize('cols', [1, 2, 3, 8, 16, 24, 40, 60])
@pytest.mark.parametrize('rows', [1, 2, 3, 8, 11])
@pytest.mark.parametrize('ascii', [False, True])
def test_every_line_and_footer_respects_both_budgets(cols, rows, ascii):
    r = render_ranking(['東京e\u0301名' * 4, 'positive', 'zero'], [-1, 1, 0],
                       title='Very long heading', unit='percentage points', name='identity',
                       cols=cols, max_rows=rows, ascii=ascii, color=False)
    bounded(r, cols, rows)
    assert '\x1b' not in r.text
    assert len(r.records) == 3
    if r.mode == 'explanation':
        assert r.omitted == 3 and r.reason


def test_empty_ranking_cannot_escape_height_limit_via_heading():
    bounded(render_ranking([], [], title='long heading', cols=2, max_rows=1), 2, 1)


def test_smallest_window_returns_structured_omission_not_a_cut_value():
    r = render_ranking(['unabridged'], [123456789], cols=3, max_rows=1)
    assert r.mode == 'explanation' and r.omitted == 1 and r.reason
    assert r.records == [dict(label='unabridged', value=123456789, exact='+123456789')]


def test_color_off_and_ascii_do_not_depend_on_terminal_environment(monkeypatch):
    monkeypatch.setenv('TERM', 'xterm-kitty')
    r = render_ranking(['\x1b[31mone\x1b[0m', 'two'], [1, -1], ascii=True, color=False)
    assert r.text.isascii() and '#' in r.text and '\x1b' not in r.text


def test_figure_compact_preserves_source_and_order():
    fig = fixture()
    original = copy.deepcopy((fig.get_size_inches().tolist(), fig.axes[0].get_position().bounds,
                              [(b.get_x(), b.get_y(), b.get_width()) for b in fig.axes[0].patches]))
    ticks_before = [(id(t), t.get_loc(), t.label1.get_text()) for t in fig.axes[0].yaxis.majorTicks]
    r = render_compact(fig, cols=40, max_rows=8)
    bounded(r, 40, 8)
    # Like the existing figure-copy route, Matplotlib may materialize tick caches;
    # existing Tick artists must not be relabelled or moved on the source.
    ticks_after = [(id(t), t.get_loc(), t.label1.get_text()) for t in fig.axes[0].yaxis.majorTicks]
    assert ticks_before == ticks_after[:len(ticks_before)]
    assert r.mode == 'ranking' and r.omitted == 4
    assert [record['label'] for record in r.records] == NAMES
    assert original == (fig.get_size_inches().tolist(), fig.axes[0].get_position().bounds,
                        [(b.get_x(), b.get_y(), b.get_width()) for b in fig.axes[0].patches])


def test_existing_rows_remain_a_preference_not_hard_limit():
    fig = fixture()
    assert render(fig, cols=40, rows=8).dimensions['height'] > 8
    assert render_compact(fig, cols=40, max_rows=8).dimensions['height'] <= 8


def test_other_figure_is_never_cropped_to_fit():
    ax = Figure().subplots()
    ax.plot(range(20))
    r = render_compact(ax.figure, cols=40, max_rows=2)
    bounded(r, 40, 2)
    assert r.mode == 'explanation' and r.reason and r.omitted is None


def test_multiple_bar_series_are_not_silently_collapsed():
    ax = Figure().subplots()
    ax.barh(['a', 'b'], [1, 2], label='first')
    ax.barh(['a', 'b'], [2, 1], label='second')
    ax.legend()
    r = render_compact(ax.figure, cols=40, max_rows=3)
    assert r.mode == 'explanation' and r.reason


@pytest.mark.parametrize('kwargs', [dict(cols=0), dict(max_rows=0), dict(max_rows=True), dict(cols=1.2), dict(top_k=0)])
def test_invalid_budgets(kwargs):
    with pytest.raises(ValueError):
        render_ranking(['a'], [1], **kwargs)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), True])
def test_nonfinite_is_not_silently_filled_with_zero(value):
    with pytest.raises(ValueError):
        render_ranking(['a'], [value])


@pytest.mark.parametrize('context', ['axes_legend', 'axes_legend_title', 'figure_legend',
                                     'figure_legend_title', 'left_title', 'right_title',
                                     'ylabel', 'child_axes', 'figure_artist', 'subfigure',
                                     'suptitle', 'supxlabel', 'supylabel'])
def test_figure_context_refuses_lossy_ranking_conversion(context):
    fig = Figure()
    if context == 'subfigure':
        subfigure = fig.subfigures()
        subfigure.suptitle('2026 forecast')
        ax = subfigure.subplots()
    else:
        ax = fig.subplots()
    ax.barh(['A'], [10])
    if context == 'axes_legend':
        ax.legend(['2026 forecast'])
    elif context == 'axes_legend_title':
        ax.legend(['Series A'], title='2026 forecast')
    elif context == 'figure_legend':
        ax.figure.legend(['2026 forecast'])
    elif context == 'figure_legend_title':
        ax.figure.legend(['Series A'], title='2026 forecast')
    elif context in ('left_title', 'right_title'):
        ax.set_title('2026 forecast', loc=context.split('_')[0])
    elif context == 'ylabel':
        ax.set_ylabel('2026 forecast')
    elif context == 'child_axes':
        inset = ax.inset_axes([.5, .5, .4, .4])
        inset.plot([0, 1], [0, 1])
        inset.set_title('2026 forecast')
    elif context.startswith('sup'):
        getattr(fig, context)('2026 forecast')
    elif context == 'figure_artist':
        from matplotlib.text import Text
        fig.add_artist(Text(.5, .9, '2026 forecast', transform=fig.transFigure))
    complete = render(fig, cols=80, rows=60)
    result = render_compact(fig, cols=80, max_rows=60)
    bounded(result, 80, 60)
    assert result.mode == 'figure' and result.omitted == 0
    assert result.text == complete.text
    assert '2026 forecast' in result.text
    fallback = present(fig, saved=DisplayPreferences(mode='image'), surface=Surface(cols=40, rows=2))
    assert fallback.mode == 'text' and fallback.fallback_reason
    assert fallback.result.mode == 'explanation' and fallback.result.omitted is None
    assert fallback.result.reason
    bounded(fallback.result, 40, 2)


@pytest.mark.parametrize('kind', ['svg', 'svg_bytes', 'figure_text', 'heatmap'])
@pytest.mark.parametrize('via_present', [False, True])
def test_valid_narrow_display_returns_bounded_capacity_omission(kind, via_present):
    cols = 3 if kind == 'heatmap' else 1
    if kind.startswith('svg'):
        source = '<svg width="200" height="100"><text x="100" y="20" class="title">東</text></svg>'
        if kind == 'svg_bytes':
            source = source.encode()
    else:
        ax = Figure().subplots()
        if kind == 'heatmap':
            image = ax.imshow([[0, 1], [2, 3]])
            ax.figure.colorbar(image, ax=ax)
        else:
            ax.plot([0, 1])
            ax.set_title('東')
        source = ax.figure
    with pytest.raises(ValueError):
        render(source, cols=cols, rows=3)
    if via_present:
        delivery = present(source, saved=DisplayPreferences(mode='image'), surface=Surface(cols=cols, rows=3))
        assert delivery.mode == 'text' and delivery.fallback_reason
        result = delivery.result
        assert delivery.text == result.text
    else:
        result = render_compact(source, cols=cols, max_rows=3)
    bounded(result, cols, 3)
    assert result.mode == 'explanation' and result.omitted is None
    assert result.reason and result.records == []


@pytest.mark.parametrize('cols', [1, 80])
@pytest.mark.parametrize('via_present', [False, True])
def test_malformed_source_errors_are_not_capacity_omissions(cols, via_present):
    from xml.etree.ElementTree import ParseError
    for source, error in [('<svg', ParseError),
                          ('<svg width="200" height="100"><text x="invalid">East</text></svg>', ValueError)]:
        with pytest.raises(error):
            if via_present:
                present(source, surface=Surface(cols=cols, rows=3))
            else:
                render_compact(source, cols=cols, max_rows=3)


@pytest.mark.parametrize('labels,cols,body_rows,mode', [(['A', 'B'], 8, 2, 'ranking'),
                                                       (['A', 'B'], 4, 2, 'table'),
                                                       (['ABCD', 'EFGH'], 5, 4, 'table')])
@pytest.mark.parametrize('title', ['', 'T'])
@pytest.mark.parametrize('top_k', [None, 2, 3])
@pytest.mark.parametrize('ascii', [False, True])
def test_complete_blocks_fit_without_an_omission_notice(labels, cols, body_rows, mode, title, top_k, ascii):
    rows = body_rows + bool(title)
    result = render_ranking(labels, [1, 2], cols=cols, max_rows=rows, title=title, top_k=top_k, ascii=ascii)
    bounded(result, cols, rows)
    assert result.mode == mode and result.omitted == 0 and result.reason is None
    assert result.dimensions['height'] == rows
    assert 'omitted' not in result.text
    expected_labels = labels if top_k is None else labels[::-1]
    body = result.text.splitlines()[bool(title):]
    block_size = body_rows // 2
    for i, label in enumerate(expected_labels):
        block = body[i * block_size:(i + 1) * block_size]
        value = [1, 2][labels.index(label)]
        assert f'+{value}' in block[0]
        assert ''.join(line.split()[0] for line in block) == label


@pytest.mark.parametrize('cols', [4, 8])
@pytest.mark.parametrize('top_k,rows', [(None, 1), (1, 2)])
def test_required_omission_notice_is_not_skipped(cols, top_k, rows):
    result = render_ranking(['A', 'B'], [1, 2], cols=cols, max_rows=rows, top_k=top_k)
    bounded(result, cols, rows)
    assert result.mode == 'explanation' and result.omitted == 2 and result.reason


@pytest.mark.parametrize('via_present', [False, True])
def test_complete_narrow_figure_ranking_needs_no_footer(via_present):
    ax = Figure().subplots()
    ax.barh(['A', 'B'], [1, 2])
    if via_present:
        delivery = present(ax.figure, saved=DisplayPreferences(mode='image'), surface=Surface(cols=8, rows=2))
        assert delivery.mode == 'text' and delivery.fallback_reason
        result = delivery.result
    else:
        result = render_compact(ax.figure, cols=8, max_rows=2)
    bounded(result, 8, 2)
    assert result.mode in ('ranking', 'table') and result.omitted == 0 and result.reason is None
    assert [record['label'] for record in result.records] == ['A', 'B']
    assert [record['value'] for record in result.records] == [1, 2]
    assert all(name in result.text for name in ('A', 'B'))


@pytest.mark.parametrize('field', ['label', 'title', 'unit', 'name'])
@pytest.mark.parametrize('separator', ['\n', '\t'])
def test_direct_ranking_keeps_rejecting_control_characters(field, separator):
    text = 'Team' + separator + '2026'
    kwargs = dict(labels=['A'], values=[1])
    if field == 'label':
        kwargs['labels'] = [text]
    else:
        kwargs[field] = text
    with pytest.raises(ValueError, match='control characters'):
        render_ranking(**kwargs)


@pytest.mark.parametrize('field', ['label', 'title', 'unit', 'name'])
@pytest.mark.parametrize('separator', ['\n', '\t'])
@pytest.mark.parametrize('via_present', [False, True])
def test_unsupported_figure_text_uses_complete_or_bounded_fallback(field, separator, via_present):
    text = 'Team' + separator + '2026'
    ax = Figure().subplots()
    ax.barh([text if field == 'label' else 'A'], [1], label=text if field == 'name' else None)
    if field == 'title':
        ax.set_title(text)
    elif field == 'unit':
        ax.set_xlabel(text)
    for rows in (60, 2):
        if via_present:
            delivery = present(ax.figure, saved=DisplayPreferences(mode='image'), surface=Surface(cols=80, rows=rows))
            assert delivery.mode == 'text' and delivery.fallback_reason
            result = delivery.result
        else:
            result = render_compact(ax.figure, cols=80, max_rows=rows)
        bounded(result, 80, rows)
        if rows == 60:
            assert result.mode == 'figure' and result.omitted == 0
            assert result.text == render(ax.figure, cols=80, rows=rows).text
        else:
            assert result.mode == 'explanation' and result.omitted is None and result.reason


@pytest.mark.parametrize('via_present', [False, True])
def test_missing_bar_width_uses_complete_or_bounded_fallback(via_present):
    ax = Figure().subplots()
    ax.barh(['A', 'B'], [1, float('nan')])
    for rows in (60, 2):
        if via_present:
            delivery = present(ax.figure, saved=DisplayPreferences(mode='image'), surface=Surface(cols=80, rows=rows))
            assert delivery.mode == 'text' and delivery.fallback_reason
            result = delivery.result
        else:
            result = render_compact(ax.figure, cols=80, max_rows=rows)
        bounded(result, 80, rows)
        if rows == 60:
            assert result.mode == 'figure' and result.omitted == 0
            assert result.text == render(ax.figure, cols=80, rows=rows).text
            assert 'A' in result.text
        else:
            assert result.mode == 'explanation' and result.omitted is None and result.reason
        assert ax.containers[0][0].get_width() == 1
        assert math.isnan(ax.containers[0][1].get_width())


@pytest.mark.parametrize('formatter_case', ['percent', 'currency', 'custom_scalar', 'x_minor', 'y_minor', 'y_offset'])
@pytest.mark.parametrize('via_present', [False, True])
def test_unsupported_formatter_semantics_use_complete_or_bounded_fallback(formatter_case, via_present):
    from matplotlib.ticker import FixedLocator, PercentFormatter, ScalarFormatter, StrMethodFormatter

    class UnitFormatter(ScalarFormatter):
        def __call__(self, value, pos=None):
            return f'{value:g} kg'

    ax = Figure().subplots()
    ax.barh([1_000_000, 1_000_001] if formatter_case == 'y_offset' else ['A', 'B'], [.25, .5])
    if formatter_case == 'percent':
        ax.xaxis.set_major_formatter(PercentFormatter(1))
    elif formatter_case == 'currency':
        ax.xaxis.set_major_formatter(StrMethodFormatter('${x:.2f}'))
    elif formatter_case == 'custom_scalar':
        ax.xaxis.set_major_formatter(UnitFormatter())
    elif formatter_case in ('x_minor', 'y_minor'):
        axis = ax.xaxis if formatter_case == 'x_minor' else ax.yaxis
        axis.set_minor_locator(FixedLocator([.125, .375]))
        axis.set_minor_formatter(PercentFormatter(1))
    for rows in (60, 2):
        if via_present:
            delivery = present(ax.figure, saved=DisplayPreferences(mode='image'), surface=Surface(cols=80, rows=rows))
            assert delivery.mode == 'text' and delivery.fallback_reason
            result = delivery.result
        else:
            result = render_compact(ax.figure, cols=80, max_rows=rows)
        bounded(result, 80, rows)
        if rows == 60:
            assert result.mode == 'figure' and result.omitted == 0
            assert result.text == render(ax.figure, cols=80, rows=rows).text
            if formatter_case == 'percent':
                assert '%' in result.text
        else:
            assert result.mode == 'explanation' and result.omitted is None and result.reason
