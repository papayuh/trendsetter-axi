"""Dashboard math, refresh, input and terminal cleanup without a real TTY."""
import copy
import io
import math
import os
import signal

from matplotlib.figure import Figure
import pytest

import trendsetter_axi as ts
from trendsetter_axi import dashboards as impl
from trendsetter_axi import viewer as terminal_impl
from trendsetter_axi.cells import SGR, width
from trendsetter_axi.dashboards import Dashboard, Tile, layout


def figure(kind='line', title='Source chart'):
    ax = Figure().subplots()
    if kind == 'scatter':
        ax.scatter([1, 2, 3, 20], [2, 4, 6, 20], label='samples')
    elif kind == 'bar':
        ax.bar(['a', 'b', 'c'], [3, 6, -1], bottom=[1, 0, 2], label='bars')
    elif kind == 'heat':
        image = ax.imshow([[1, 2, 3], [4, 5, 6]], aspect='auto')
        ax.figure.colorbar(image, ax=ax, label='ms')
    else:
        ax.plot([0, 5, 10], [1, 8, 2], label='line')
    if kind in ('line', 'scatter'):
        ax.set(xlim=(0, 10), ylim=(0, 10))
    ax.set(title=title, xlabel='x units', ylabel='y units')
    return ax.figure


def model(kinds=('line', 'bar', 'scatter', 'heat'), cols=140, rows=44):
    m = Dashboard([figure(kind) for kind in kinds])
    m.layout(cols, rows)
    return m


@pytest.mark.parametrize('count', [1, 2, 3, 4, 5, 9, 16])
@pytest.mark.parametrize('cols,rows', [(1, 1), (80, 24), (120, 38), (140, 44), (201, 75)])
@pytest.mark.parametrize('columns', [None, 1, 2, 5])
def test_layout_bounds_no_overlap_and_nothing_silently_omitted(count, cols, rows, columns):
    tiles = layout(count, cols, rows, columns)
    assert not tiles or len(tiles) == count
    cells = set()
    for tile in tiles:
        assert tile.cols >= impl.MIN_COLS and tile.rows >= impl.MIN_ROWS
        assert tile.x >= 1 and tile.y >= 3
        assert tile.x + tile.cols <= cols - 1
        assert tile.y + tile.rows <= rows - 2
        occupied = {(c, r) for r in range(tile.y, tile.y + tile.rows)
                    for c in range(tile.x, tile.x + tile.cols)}
        assert not cells & occupied
        cells |= occupied
    assert tiles == layout(count, cols, rows, columns)


def test_layout_distributes_remainders_and_reflows():
    assert layout(4, 141, 44, 2) == [Tile(1, 3, 69, 19), Tile(71, 3, 69, 19),
                                           Tile(1, 23, 69, 19), Tile(71, 23, 69, 19)]
    assert len({t.x for t in layout(4, 80, 62)}) == 1
    assert len({t.y for t in layout(4, 160, 24)}) == 1
    assert layout(4, 80, 24) == []


@pytest.mark.parametrize('cols,rows', [(1, 1), (20, 5), (80, 24), (120, 38), (140, 44)])
def test_exact_frame_cell_budget_and_no_control_codes_in_monochrome(cols, rows):
    text = ts.dashboard([figure() for _ in range(4)], cols=cols, rows=rows, color=False)
    assert len(text.splitlines()) == rows
    assert all(width(line) == cols for line in text.splitlines())
    assert '\x1b' not in text
    if not layout(4, cols, rows) and cols > 20:
        assert 'Resize' in text


def test_public_function_remains_callable_after_lazy_import_and_static_never_takes_input(monkeypatch):
    monkeypatch.setattr(impl, 'run', lambda *a, **k: pytest.fail('static takes input'))
    monkeypatch.setattr(impl.shutil, 'get_terminal_size', lambda **k: os.terminal_size((101, 33)))
    for _ in range(2):
        text = ts.dashboard([figure()])
        assert callable(ts.dashboard)
        assert len(text.splitlines()) == 33
        assert all(width(line) == 101 for line in text.splitlines())
        assert '\x1b[?1049' not in text and 'q quit' not in text
    text = ts.dashboard([figure()], cols=90)
    assert all(width(line) == 90 for line in text.splitlines())


def test_mixed_charts_use_styled_palette_source_heat_scale_and_cached_fallback(monkeypatch):
    m = model()
    v = m.viewers[3]
    original = v.static
    calls = []
    def draw(cols, rows):
        calls.append((cols, rows))
        return original(cols, rows)
    v.static = draw
    text = m.frame()
    plain = SGR.sub('', text)
    assert 'source palette / scale' in plain
    assert '1.00-2.25' in plain  # Source renderer's quantized color key, not a new scale.
    assert all(str(i).zfill(2) + ' / Source chart' in plain for i in range(1, 5))
    assert '\x1b[38;2;92;200;250' in text  # Shared palette, including bars.
    assert m.viewers[1].projection is not None
    assert m.frame() == text and len(calls) == 1
    m.layout(160, 48)
    m.frame()
    assert len(calls) == 2


def test_fallback_never_crops_large_chart_or_interprets_untrusted_controls():
    m = model(('heat',))
    m.viewers[0].static = lambda *args: '\n'.join(['too many rows'] * 100)
    assert 'Chart needs a larger tile' in m.frame()
    m.layout(140, 44)
    m.viewers[0].static = lambda *args: '\x1b]0;evil\x07\x1b[2Jhello'
    text = m.frame()
    assert 'hello' in text and 'evil' not in text and '\x1b[2J' not in text
    assert all(width(line) == 140 for line in text.splitlines())


def test_saved_heat_record_discloses_unavailable_original_ink():
    text = ts.dashboard([ts.from_figure(figure('heat'))], cols=140, rows=44, color=False)
    assert 'data overview' in text
    assert 'source palette / scale' not in text


def test_fallback_render_failure_is_bounded_and_keeps_quit_available():
    m = model(('heat',))
    def fail(*args):
        raise RuntimeError('bad renderer')
    m.viewers[0].static = fail
    assert 'RuntimeError: bad renderer' in m.frame()
    assert m.key('q')


def test_resize_clears_cell_based_hover_brush_and_drag_even_shrink_then_grow():
    m = model(('scatter',))
    v = m.viewers[0]
    p = v.projection
    v.hover = v.points[0]
    v.box = (p.left, p.top, p.left + 5, p.top + 5)
    v.press = (p.left, p.top)
    m.dragging = 0
    m.layout(20, 5)
    assert v.projection is v.hover is v.box is v.press is m.dragging is None
    assert 'Resize' in m.frame()
    m.layout(160, 48)
    assert v.projection is not None and v.hover is v.box is None
    assert all(width(line) == 160 for line in m.frame().splitlines())


def test_hover_coordinates_are_tile_local_and_brush_drag_stays_in_origin_tile():
    m = model(('line', 'scatter'))
    v, tile = m.viewers[1], m.tiles[1]
    p = v.projection
    col, row = p.cell(v.points[0].x, v.points[0].y)
    m.mouse(35, round(col) + tile.x, round(row) + tile.y, False)
    assert m.active == 1 and v.hover == v.points[0]
    assert 'samples[0] x=1.0 y=2.0' in SGR.sub('', m.frame())
    m.mouse(0, tile.x + p.left, tile.y + p.top, False)
    m.mouse(32, -500, 9999, False)
    assert m.active == 1 and m.dragging == 1
    assert v.box[0] >= p.left and v.box[3] < p.top + p.rows
    m.mouse(0, -500, 9999, True)
    assert m.dragging is None and v.press is None
    assert v.box is not None
    m.key('1')
    assert m.active == 0
    m.key('2')
    m.key('x')
    assert v.box is None
    m.mouse(35, 0, 0, False)
    assert v.hover is None


def test_brush_statistics_count_only_visible_scatter_and_static_differs_only_in_controls():
    m = model(('scatter',))
    v, tile = m.viewers[0], m.tiles[0]
    p = v.projection
    m.mouse(0, tile.x + p.left, tile.y + p.top, False)
    m.mouse(0, tile.x + p.left + p.cols - 1, tile.y + p.top + p.rows - 1, True)
    assert len(v.chosen()) == 3
    assert '3 / 3 points selected · r=1.000' in SGR.sub('', m.frame())
    assert 'q quit' not in m.frame(interactive=False)


def test_original_figures_records_plain_render_and_limits_unchanged():
    fig = figure('bar')
    record = ts.from_figure(fig)
    before = copy.deepcopy(record)
    text = ts.render(fig).text
    limits = fig.axes[0].get_xlim(), fig.axes[0].get_ylim()
    ts.dashboard([fig, record], cols=140, rows=44)
    assert record == before == ts.from_figure(fig)
    assert limits == (fig.axes[0].get_xlim(), fig.axes[0].get_ylim())
    assert ts.render(fig).text == text


def test_saved_bars_disclose_estimated_widths():
    text = ts.dashboard([ts.from_figure(figure('bar'))], cols=140, rows=44, color=False)
    assert 'widths estimated' in text
    text = ts.dashboard([figure('bar')], cols=140, rows=44, color=False)
    assert 'widths estimated' not in text


@pytest.mark.parametrize('scale', ['log', 'inverted', 'category', 'symlog'])
def test_projection_scales_or_clear_static_fallback(scale):
    ax = Figure().subplots()
    ax.plot(['a', 'b', 'c'] if scale == 'category' else [1, 10, 100], [2, 3, 4])
    if scale in ('log', 'symlog'):
        ax.set_xscale(scale)
    elif scale == 'inverted':
        ax.invert_xaxis()
    m = Dashboard([ax.figure])
    m.layout(120, 38)
    v = m.viewers[0]
    if scale == 'symlog':
        assert 'unsupported x scale' in m.frame()
    else:
        assert v.projection is not None
        for point in v.points:
            assert v.nearest(*v.projection.cell(point.x, point.y)) == point
        if scale == 'inverted':
            assert v.projection.cell(1, 3)[0] > v.projection.cell(100, 3)[0]


def test_source_text_wide_characters_and_escapes_stay_bounded():
    fig = figure('line', '東京 e\u0301 chart')
    fig.axes[0].lines[0].set_label('東京\x1b[2J\x1b]0;bad\x07')
    text = ts.dashboard([fig], title='🌐 東京\x1b[2J', cols=80, rows=24, color=False)
    assert '東京' in text and 'bad' not in text
    assert '\x1b' not in text
    assert all(width(line) == 80 for line in text.splitlines())


def test_snapshot_replacement_invalidates_geometry_and_is_atomic_on_error():
    m = model(('scatter', 'line'))
    m.active = 1
    previous = m.viewers
    with pytest.raises(ValueError, match='at least one'):
        m.replace([])
    assert m.viewers is previous
    m.replace([figure('bar')])
    assert len(m.viewers) == 1 and m.active == 0 and not m.cache
    assert m.viewers[0].projection is not None


@pytest.mark.parametrize('kwargs', [dict(cols=0), dict(rows=True), dict(columns=1.5),
                                    dict(interval=0), dict(interval=math.inf), dict(interval=True),
                                    dict(interval='1'), dict(refresh=lambda: []),
                                    dict(interactive=True, refresh=4)])
def test_invalid_options_fail_before_terminal_setup(kwargs):
    with pytest.raises(ValueError):
        ts.dashboard([figure()], **kwargs)


def test_empty_dashboard_rejected():
    with pytest.raises(ValueError, match='at least one'):
        ts.dashboard([])


class FakeTTY(io.StringIO):
    def isatty(self):
        return True

    def fileno(self):
        return 42


@pytest.fixture
def terminal(monkeypatch):
    import termios
    import tty
    saved, calls = ['saved'], []
    monkeypatch.setattr(termios, 'tcgetattr', lambda fd: saved)
    monkeypatch.setattr(termios, 'tcsetattr', lambda fd, how, state: calls.append(('restore', state)))
    monkeypatch.setattr(tty, 'setcbreak', lambda fd: calls.append(('cbreak', fd)))
    monkeypatch.setattr(os, 'get_terminal_size', lambda fd: os.terminal_size((140, 44)))
    return FakeTTY(), FakeTTY(), calls, saved


@pytest.mark.parametrize('data', [b'q', b'', b'\x1b[<35;10;10Mq', b'\x03'])
def test_driver_quit_eof_mouse_ctrl_c_restore_without_real_tty(terminal, monkeypatch, data):
    stdin, stdout, calls, saved = terminal
    monkeypatch.setattr(impl.select, 'select', lambda *args: ([stdin], [], []))
    monkeypatch.setattr(os, 'read', lambda *args: data)
    if data == b'\x03':
        with pytest.raises(KeyboardInterrupt):
            impl.run(model(), stdin=stdin, stdout=stdout)
    else:
        impl.run(model(), stdin=stdin, stdout=stdout)
    assert calls[-1] == ('restore', saved)
    assert stdout.getvalue().startswith(terminal_impl.ENTER)
    assert stdout.getvalue().endswith(terminal_impl.LEAVE)


def test_driver_detects_resize_without_input(terminal, monkeypatch):
    stdin, stdout, _, _ = terminal
    sizes = iter([(140, 44), (160, 48), (20, 5)])
    monkeypatch.setattr(os, 'get_terminal_size', lambda fd: os.terminal_size(next(sizes)))
    m = model(('scatter',))
    layouts, original = [], m.layout
    def relayout(cols, rows):
        layouts.append((cols, rows))
        original(cols, rows)
    m.layout = relayout
    steps = iter([False, False, True])
    monkeypatch.setattr(impl.select, 'select', lambda *args: ([stdin] if next(steps) else [], [], []))
    monkeypatch.setattr(os, 'read', lambda *args: b'q')
    impl.run(m, stdin=stdin, stdout=stdout)
    assert layouts == [(140, 44), (160, 48), (20, 5)]
    assert m.viewers[0].projection is None
    assert 'Resize' in stdout.getvalue()


@pytest.mark.parametrize('exception', [None, RuntimeError, KeyboardInterrupt, SystemExit])
def test_live_refresh_deadline_and_restore_on_callback_error(terminal, monkeypatch, exception):
    stdin, stdout, calls, saved = terminal
    clock = [0.0]
    monkeypatch.setattr(impl.time, 'monotonic', lambda: clock[0])
    m, refresh_calls = model(('line',)), []
    def refresh():
        refresh_calls.append(clock[0])
        if exception:
            raise exception('callback failed')
        return [figure('bar')]
    steps = iter([.1, .2, 1.0, 1.1])
    def poll(*args):
        clock[0] = next(steps)
        return ([stdin] if clock[0] > 1 else [], [], [])
    monkeypatch.setattr(impl.select, 'select', poll)
    monkeypatch.setattr(os, 'read', lambda *args: b'q')
    if exception:
        with pytest.raises(exception):
            impl.run(m, refresh=refresh, interval=1, stdin=stdin, stdout=stdout)
    else:
        impl.run(m, refresh=refresh, interval=1, stdin=stdin, stdout=stdout)
        assert m.updates == 1 and m.viewers[0].points[0].kind == 'bars'
        assert 'update 0001' in stdout.getvalue()
    assert refresh_calls == [1.0]
    assert calls[-1] == ('restore', saved)
    assert stdout.getvalue().endswith(terminal_impl.LEAVE)


@pytest.mark.parametrize('sig', [signal.SIGTERM, signal.SIGHUP])
def test_signal_during_callback_restores_terminal_and_prior_handlers(terminal, monkeypatch, sig):
    stdin, stdout, calls, saved = terminal
    previous = signal.getsignal(sig)
    clock = [0]
    monkeypatch.setattr(impl.time, 'monotonic', lambda: clock[0])
    def poll(*args):
        clock[0] = 2
        return [], [], []
    monkeypatch.setattr(impl.select, 'select', poll)
    def refresh():
        signal.getsignal(sig)(sig, None)
    with pytest.raises(SystemExit):
        impl.run(model(), refresh=refresh, stdin=stdin, stdout=stdout)
    assert signal.getsignal(sig) == previous
    assert calls[-1] == ('restore', saved)
    assert stdout.getvalue().endswith(terminal_impl.LEAVE)


def test_drawing_failure_restores_terminal(terminal, monkeypatch):
    stdin, stdout, calls, saved = terminal
    m = model()
    def fail(**kwargs):
        raise RuntimeError('drawing failed')
    m.frame = fail
    with pytest.raises(RuntimeError, match='drawing failed'):
        impl.run(m, stdin=stdin, stdout=stdout)
    assert calls[-1] == ('restore', saved)
    assert stdout.getvalue().endswith(terminal_impl.LEAVE)


def test_interactive_requires_tty_before_writing_escape_sequences(monkeypatch):
    monkeypatch.setattr(impl.sys, 'stdin', io.StringIO())
    output = io.StringIO()
    monkeypatch.setattr(impl.sys, 'stdout', output)
    with pytest.raises(ValueError, match='TTY'):
        ts.dashboard([figure()], interactive=True)
    assert output.getvalue() == ''
