"""Interaction/state/cleanup tests run without a real TTY or GUI."""
import copy
import io
import json
import os
import signal
import subprocess
import sys

from matplotlib.figure import Figure
import pytest

from trendsetter_axi import from_figure, render, render_styled
from trendsetter_axi.cells import SGR, width
from trendsetter_axi import viewer as impl
from trendsetter_axi.styled import Screen
from trendsetter_axi.viewer import InputParser, Point, Projection, Viewer, make_viewer, stats


def scatter():
    ax = Figure().subplots()
    ax.scatter([1, 2, 3, 20], [2, 4, 6, 20], label='samples')
    ax.set(xlim=(0, 10), ylim=(0, 10), title='Source chart')
    return ax.figure


def model(fig=None, cols=120, rows=38):
    v = make_viewer(scatter() if fig is None else fig)
    v.layout(cols, rows)
    return v


def test_parser_every_split_and_wire_order():
    raw = b'\x1b[<0;9;7M\x1b[<32;20;15M\x1b[<0;20;15mxq'
    want = [('mouse', (0, 8, 6, False)), ('mouse', (32, 19, 14, False)),
            ('mouse', (0, 19, 14, True)), ('key', 'x'), ('key', 'q')]
    for split in range(len(raw) + 1):
        parser = InputParser()
        assert parser.feed(raw[:split]) + parser.feed(raw[split:]) == want
    parser = InputParser()
    assert sum((parser.feed(bytes([byte])) for byte in raw), []) == want
    assert parser.feed(b'\x1b[A\x1b[<999;1;1x\x1bOPq') == [('key', 'q')]
    with pytest.raises(KeyboardInterrupt):
        parser.feed(b'\x03')


def test_hover_returns_exact_stored_scatter_and_line_knot():
    fig = scatter()
    fig.axes[0].plot([4, 6], [1.23456789012345, 8], label='line')
    v = model(fig)
    for p in v.points[:-1]:
        if v.projection.visible(p.x, p.y):
            assert v.nearest(*v.projection.cell(p.x, p.y)) == p
    assert v.nearest(-10, -10) is None
    assert v.nearest(v.projection.left + 30, v.projection.top + 2) is None
    point = next(p for p in v.points if p.kind == 'line')
    c, r = v.projection.cell(point.x, point.y)
    v.mouse(35, round(c), round(r), False)
    assert v.hover == point
    text = SGR.sub('', v.frame())
    assert repr(point.y) in text
    assert 'line [0]' in text


def test_brush_live_reverse_drag_clamps_and_excludes_offscreen_and_lines():
    fig = scatter()
    fig.axes[0].plot([1, 2], [2, 4])
    v = model(fig)
    p = v.projection
    v.mouse(0, p.left + p.cols - 1, p.top + p.rows - 1, False)
    v.mouse(32, -100, -100, False)
    assert stats(v.chosen()) == dict(n=3, mean_x=2, mean_y=4, correlation=1, slope=2)
    v.mouse(0, -100, -100, True)
    assert v.press is None
    assert len(v.chosen()) == 3
    assert v.key('x') is False and v.box is None
    assert v.key('q') is True
    # Empty selection and constant-axis stats are well-defined.
    v.box = (p.left, p.top, p.left + 1, p.top + 1)
    assert stats(v.chosen())['n'] == 0
    assert stats(v.chosen())['mean_x'] is None
    assert stats([Point('m', '', 0, 'points', 1, 5)])['slope'] is None
    assert stats([Point('m', '', i, 'points', 1, i) for i in range(3)])['correlation'] is None


def test_moving_brush_preserves_size_and_clamps():
    v = model()
    p = v.projection
    v.box = (p.left, p.top + 3, p.left + 10, p.top + 10)
    v.mouse(0, p.left + 5, p.top + 5, False)
    v.mouse(32, 9999, 9999, False)
    c0, r0, c1, r1 = v.box
    assert c1 - c0 == 10 and r1 - r0 == 7
    assert c1 == p.left + p.cols - 1 and r1 == p.top + p.rows - 1


@pytest.mark.parametrize('horizontal', [False, True])
def test_bars_hit_actual_rectangle_negative_stacked_and_exact_value(horizontal):
    ax = Figure().subplots()
    if horizontal:
        ax.barh(['a', 'b'], [-3.123456789012345, 5], left=[2, 1], height=[.25, .7], label='bars')
    else:
        ax.bar(['a', 'b'], [-3.123456789012345, 5], bottom=[2, 1], width=[.25, .7], label='bars')
    v = model(ax.figure)
    for point in v.points:
        c0, r0, c1, r1 = v.bar_bounds(point)
        assert v.nearest((c0 + c1) / 2, (r0 + r1) / 2) == point
    v.hover = v.points[0]
    text = SGR.sub('', v.frame())
    assert repr(v.hover.top) in text and repr(v.hover.base) in text
    assert 'value=' in text
    assert 'a' in text
    assert len(v.chosen()) == 0
    record = from_figure(ax.figure)
    assert 'width' not in record['marks'][0]  # public schema unchanged
    saved = model(record)
    assert 'widths estimated' in SGR.sub('', saved.frame())


@pytest.mark.parametrize('style', ['default', 'steps-pre', 'steps-post', 'steps-mid'])
def test_sparse_line_hover_hits_drawn_segments_and_returns_source_knots(style):
    ax = Figure().subplots()
    ax.plot([0, 10], [0, 10], drawstyle=style, label='sparse')
    ax.set(xlim=(-1, 11), ylim=(-1, 11))
    v = model(ax.figure)
    edges = list(impl.line_edges(v.record['marks'][0], v.points, v.projection))
    for path, left, right in edges:
        for a, b in zip(path, path[1:]):
            col, row = (a[0] + b[0]) / 2, (a[1] + b[1]) / 4
            assert v.nearest(col, row) in (left, right)
    ax.lines[0].set_data([0, float('nan'), 10], [0, float('nan'), 10])
    v = model(ax.figure)
    assert not list(impl.line_edges(v.record['marks'][0], v.points, v.projection))
    assert v.nearest(*v.projection.cell(5, 5)) is None


def test_projection_log_inverted_category_and_clipping():
    axis = {'x': {'scale': 'log', 'range': [100, 1]}, 'y': {'scale': 'linear', 'range': [10, 0]}}
    p = Projection(axis, 8, 6, 69, 25)
    assert p.cell(10, 5) == pytest.approx((42, 18))
    assert not p.visible(0, 5) and not p.visible(1000, 5)
    ax = Figure().subplots()
    ax.scatter(['東京', 'Paris'], [2, 4])
    v = model(ax.figure)
    v.hover = v.points[0]
    assert '東京' in SGR.sub('', v.frame())
    ax = Figure().subplots()
    ax.bar([1, 2], [10, 100])
    ax.set_yscale('log')
    assert 'Static view' not in SGR.sub('', model(ax.figure).frame())


@pytest.mark.parametrize('kind', ['heat', 'area', 'multi', 'polar', 'symlog', 'errorbar'])
def test_unsupported_figures_static_with_clear_message(kind):
    fig = Figure()
    ax = fig.add_subplot(projection='polar' if kind == 'polar' else None)
    if kind == 'heat':
        ax.imshow([[1, 2], [3, 4]])
    elif kind == 'area':
        ax.fill_between([1, 2, 3], [1, 2, 1], [2, 3, 2])
    elif kind == 'errorbar':
        ax.errorbar([1, 2], [2, 3], yerr=[.2, .4])
    else:
        ax.plot([1, 2], [2, 3])
    if kind == 'multi':
        fig.add_subplot(212).plot([1, 2], [3, 4])
    if kind == 'symlog':
        ax.set_xscale('symlog')
    v = model(fig)
    assert v.reason and v.projection is None
    v.mouse(0, 15, 10, False)
    assert 'Static view:' in SGR.sub('', v.frame())
    assert v.key('q')
    saved = model(from_figure(fig))
    if kind != 'polar':  # records don't encode the source axes projection
        assert 'data overview' in SGR.sub('', saved.frame())


@pytest.mark.parametrize('cols,rows', [(80, 24), (120, 38), (160, 45), (30, 10)])
def test_static_and_interactive_share_drawing_and_fixed_cell_bounds(cols, rows):
    fig = scatter()
    v = model(fig, cols, rows)
    static = render_styled(fig, cols, rows)
    frame = v.frame()
    assert len(frame.splitlines()) == rows
    assert all(width(line) == cols for line in frame.splitlines())
    assert all(width(line) == cols for line in static.splitlines())
    # Only the last instruction row differs. Plot/stats/axes are the same.
    if cols >= 80:
        assert frame.splitlines()[:-1] == static.splitlines()[:-1]
    else:
        assert 'Resize' in frame
    if cols >= 80:
        assert 'Source chart' in frame
        assert 'x clear' not in static
        assert '\x1b[38;2;' in static
        mono = render_styled(fig, cols, rows, color=False)
        assert '\x1b' not in mono


def test_source_arrays_record_and_plain_render_unchanged():
    fig = scatter()
    before_record = from_figure(fig)
    before_text = render(fig).text
    limits = [fig.axes[0].get_xlim(), fig.axes[0].get_ylim()]
    original = copy.deepcopy(before_record)
    render_styled(fig)
    render_styled(before_record)
    assert before_record == original == from_figure(fig)
    assert before_text == render(fig).text
    assert limits == [fig.axes[0].get_xlim(), fig.axes[0].get_ylim()]
    saved = json.loads(json.dumps(before_record))
    assert model(saved).points == model(fig).points


def test_unsupported_static_renderer_failure_stays_in_viewer():
    rec = from_figure(scatter())
    rec['marks'][0]['kind'] = 'future-kind'
    def broken(*args):
        raise NotImplementedError('unknown artist')
    v = Viewer(rec, broken)
    v.layout(120, 38)
    assert 'Static rendering unavailable: NotImplementedError' in SGR.sub('', v.frame())
    assert v.key('q')


def test_screen_sanitizes_control_sequences_and_wide_character_overwrites():
    screen = Screen(8, 2)
    screen.put(0, 0, '東京\x1b[2J\x1b]0;bad\x07!')
    assert '\x1b' not in screen.text(False)
    assert 'bad' not in screen.text(False)
    screen.put(0, 1, 'x')
    assert width(screen.text(False).splitlines()[0]) == 8
    assert screen.text(False).startswith(' x京!')


class FakeTTY(io.StringIO):
    def isatty(self):
        return True

    def fileno(self):
        return 42


@pytest.fixture
def terminal(monkeypatch):
    import termios
    import tty
    calls = []
    saved = ['saved']
    monkeypatch.setattr(termios, 'tcgetattr', lambda fd: saved)
    monkeypatch.setattr(termios, 'tcsetattr', lambda fd, how, state: calls.append(('restore', state)))
    monkeypatch.setattr(tty, 'setcbreak', lambda fd: calls.append(('cbreak', fd)))
    return FakeTTY(), FakeTTY(), calls, saved


@pytest.mark.parametrize('exception', [None, RuntimeError, KeyboardInterrupt])
def test_restore_on_normal_quit_exception_and_ctrl_c(terminal, exception):
    stdin, stdout, calls, saved = terminal
    def use():
        with impl.terminal_session(stdin, stdout):
            if exception:
                raise exception('test')
    if exception:
        with pytest.raises(exception):
            use()
    else:
        use()
    assert calls == [('cbreak', 42), ('restore', saved)]
    assert stdout.getvalue().startswith(impl.ENTER)
    assert stdout.getvalue().endswith(impl.LEAVE)


@pytest.mark.parametrize('sig', [signal.SIGTERM, signal.SIGHUP])
def test_restore_on_termination_and_restore_previous_handlers(terminal, sig):
    stdin, stdout, calls, saved = terminal
    previous = signal.getsignal(sig)
    with pytest.raises(SystemExit) as error:
        with impl.terminal_session(stdin, stdout):
            signal.getsignal(sig)(sig, None)
    assert error.value.code == 128 + sig
    assert calls[-1] == ('restore', saved)
    assert signal.getsignal(sig) == previous
    assert stdout.getvalue().endswith(impl.LEAVE)


def test_restore_even_if_enter_or_leave_output_fails(terminal):
    stdin, stdout, calls, saved = terminal
    class Broken(FakeTTY):
        def write(self, text):
            raise OSError('output lost')
    with pytest.raises(OSError, match='output lost'):
        with impl.terminal_session(stdin, Broken()):
            pytest.fail('setup failed; should not enter')
    assert calls[-1] == ('restore', saved)


@pytest.mark.parametrize('data', [b'q', b'', b'\x1b[<35;12;12Mq'])
def test_run_driver_quit_eof_and_mouse_without_real_tty(terminal, monkeypatch, data):
    stdin, stdout, calls, saved = terminal
    monkeypatch.setattr(os, 'get_terminal_size', lambda fd: os.terminal_size((120, 38)))
    monkeypatch.setattr(impl.select, 'select', lambda *args: ([stdin], [], []))
    monkeypatch.setattr(os, 'read', lambda *args: data)
    impl.run(model(), stdin, stdout)
    assert calls[-1] == ('restore', saved)
    assert stdout.getvalue().endswith(impl.LEAVE)


def test_restore_when_cbreak_setup_itself_fails(terminal, monkeypatch):
    import tty
    stdin, stdout, calls, saved = terminal
    def fail(fd):
        raise RuntimeError('cbreak failed')
    monkeypatch.setattr(tty, 'setcbreak', fail)
    with pytest.raises(RuntimeError, match='cbreak failed'):
        with impl.terminal_session(stdin, stdout):
            pytest.fail('setup failed')
    assert calls[-1] == ('restore', saved)
    assert stdout.getvalue() == impl.LEAVE


def test_non_tty_fails_before_terminal_handling():
    with pytest.raises(ValueError, match='TTY'):
        with impl.terminal_session(io.StringIO(), io.StringIO()):
            pytest.fail('not a tty')


def test_cli_help_and_non_tty_error(tmp_path):
    path = tmp_path / 'chart.json'
    path.write_text(json.dumps(from_figure(scatter())))
    help_result = subprocess.run([sys.executable, '-m', 'trendsetter_axi.interact', '--help'], capture_output=True, text=True)
    assert help_result.returncode == 0 and 'saved' in help_result.stdout
    result = subprocess.run([sys.executable, '-m', 'trendsetter_axi.interact', str(path)], capture_output=True, text=True)
    assert result.returncode == 1 and 'TTY' in result.stderr
    assert '\x1b' not in result.stdout


@pytest.mark.parametrize('cols,rows', [(0, 38), (80, 0), (True, 24), (80, 1.2)])
def test_styled_invalid_budget(cols, rows):
    with pytest.raises(ValueError):
        render_styled(scatter(), cols, rows)
