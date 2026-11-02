import copy

from matplotlib.figure import Figure
import pytest

from trendsetter_axi import render, render_compact, render_ranking
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
