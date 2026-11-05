"""Responsive human-facing terminal dashboards; no changes to agent rendering."""
from dataclasses import dataclass
import math
import os
import select
import shutil
import sys
import time

from .cells import SGR, clean_text, truncate, width
from .styled import BG, FAINT, GOOD, INK, MUTED, PALETTE, BRUSH_BG, Screen
from .viewer import InputParser, Projection, line_edges, make_viewer, stats, terminal_session

MIN_COLS, MIN_ROWS = 32, 12


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f'{name} must be a positive integer')


@dataclass(frozen=True)
class Tile:
    x: int
    y: int
    cols: int
    rows: int


def layout(count, cols, rows, columns=None):
    """Return non-overlapping row-major tiles, or [] when all cannot fit.

    Three header rows, two footer rows and one-cell gutters are reserved. Spare
    cells are distributed across the first columns/rows, never lost to rounding.
    """
    for value, name in ((count, 'count'), (cols, 'cols'), (rows, 'rows')):
        _positive(value, name)
    if columns is not None:
        _positive(columns, 'columns')
    choices = []
    for nc in ([min(columns, count)] if columns else range(1, count + 1)):
        nr = math.ceil(count / nc)
        w, h = (cols - 2 - (nc - 1)) // nc, (rows - 5 - (nr - 1)) // nr
        if w >= MIN_COLS and h >= MIN_ROWS:
            # A terminal cell is roughly twice as tall as wide. Prefer broad
            # plots, then fewer unused slots. The order is deterministic.
            choices.append((abs(math.log(w / h / 3.4)) + (nc * nr - count) / count, nc, nr))
    if not choices:
        return []
    _, nc, nr = min(choices)
    usable_w, usable_h = cols - 2 - (nc - 1), rows - 5 - (nr - 1)
    widths = [usable_w // nc + (i < usable_w % nc) for i in range(nc)]
    heights = [usable_h // nr + (i < usable_h % nr) for i in range(nr)]
    return [Tile(1 + sum(widths[:i % nc]) + i % nc,
                 3 + sum(heights[:i // nc]) + i // nc,
                 widths[i % nc], heights[i // nc]) for i in range(count)]


def _paste(target, source, x, y):
    # Copy whole cells, including continuation cells of wide graphemes.
    for row, cells in enumerate(source.cells):
        target.cells[y + row][x:x + source.cols] = cells[:]


def _ansi_screen(text, cols, rows):
    """Read only renderer SGR colors, never arbitrary terminal control codes."""
    screen = Screen(cols, rows)
    fg, bg = INK, BG
    for r, line in enumerate(text.splitlines()):
        c, start = 0, 0
        for match in SGR.finditer(line):
            chunk = line[start:match.start()]
            screen.put(r, c, chunk, fg, bg)
            # Width must be computed after the same control sanitization as put.
            c += width(clean_text(chunk))
            values = [int(v or 0) for v in match.group()[2:-1].replace(':', ';').split(';')]
            i = 0
            while i < len(values):
                if values[i] == 0:
                    fg, bg = INK, BG
                elif (values[i] in (38, 48) and values[i + 1:i + 2] == [2]
                      and len(values[i:i + 5]) == 5):
                    rgb = tuple(max(0, min(255, v)) for v in values[i + 2:i + 5])
                    if values[i] == 38:
                        fg = rgb
                    else:
                        bg = rgb
                    i += 4
                i += 1
            start = match.end()
        screen.put(r, c, line[start:], fg, bg)
    return screen


def _plot(v, screen):
    """Compact drawing with the same primitives, projections and source hits."""
    from .core import BITS, Canvas

    p = v.projection
    clip = (p.left, p.top * 2, p.left + p.cols, (p.top + p.rows) * 2)
    canvas = Canvas(v.cols, v.rows * 2, v.cols, max_rows=v.rows)
    canvas.stamp = False
    selected = {(a.mark, a.index) for a in v.chosen()}
    dots = {}
    for j, m in enumerate(v.record['marks']):
        rgb = PALETTE[j % len(PALETTE)]
        points = [a for a in v.points if a.mark == m['id']]
        if m['kind'] == 'line':
            canvas.stroke([path for path, _, _ in line_edges(m, points, p)],
                          tuple(c / 255 for c in rgb), clip=clip, role='data')
        elif m['kind'] == 'bars':
            for point in points:
                c0, r0, c1, r1 = v.bar_bounds(point)
                if all(map(math.isfinite, (c0, r0, c1, r1))):
                    canvas.fill([[(c0, r0 * 2), (c1, r0 * 2), (c1, r1 * 2), (c0, r1 * 2)]],
                                tuple(c / 255 for c in rgb), clip=clip, role='data')
        elif m['kind'] == 'points':
            for a in points:
                if not p.visible(a.x, a.y):
                    continue
                c, r = p.cell(a.x, a.y)
                ix = min(p.cols * 2 - 1, round((c - p.left) * 2))
                iy = min(p.rows * 4 - 1, round((r - p.top) * 4))
                key = (p.top + iy // 4, p.left + ix // 2)
                active = v.box is None or (a.mark, a.index) in selected
                groups = dots.setdefault(key, {})
                group = j if active else -1
                bits, n = groups.get(group, (0, 0))
                groups[group] = (bits | int(BITS[iy % 4, ix % 2]), n + 1)
    screen.canvas(canvas)
    for (r, c), groups in dots.items():
        j = max(groups, key=lambda k: (k >= 0, groups[k][1]))
        screen.put(r, c, chr(0x2800 + groups[j][0]), PALETTE[j % len(PALETTE)] if j >= 0 else FAINT)
    if v.box:
        c0, r0, c1, r1 = v.box
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                screen.shade(r, c, BRUSH_BG)
        for c in range(c0, c1 + 1):
            screen.put(r0, c, '─', GOOD)
            screen.put(r1, c, '─', GOOD)
        for r in range(r0, r1 + 1):
            screen.put(r, c0, '│', GOOD)
            screen.put(r, c1, '│', GOOD)
    if v.hover and p.visible(v.hover.x, v.hover.y):
        c, r = map(round, p.cell(v.hover.x, v.hover.y))
        screen.put(r, c, '◉', INK)


def _axes(v, screen):
    p, axis = v.projection, v.record['axes'][0]
    screen.put(3, 0, truncate(axis['y'].get('label') or 'y', v.cols), MUTED)
    for r in range(p.top, p.top + p.rows):
        screen.put(r, p.left - 1, '│', FAINT)
    screen.put(p.top + p.rows, p.left - 1, '└' + '─' * p.cols, FAINT)
    occupied = {'x': set(), 'y': set()}
    for k in 'xy':
        for tick in axis[k].get('ticks', []):
            x = tick['value'] if k == 'x' else axis['x']['range'][0]
            y = tick['value'] if k == 'y' else axis['y']['range'][0]
            if not p.visible(x, y):
                continue
            c, r = map(round, p.cell(x, y))
            label = truncate(clean_text(tick['label']), 6 if k == 'y' else 9)
            if k == 'x':
                c = max(p.left, min(p.left + p.cols - width(label), c - width(label) // 2))
                span = set(range(c - 1, c + width(label) + 1))
                if span & occupied[k]:
                    continue
                occupied[k].update(span)
                screen.put(p.top + p.rows + 1, c, label, MUTED)
            elif not {r - 1, r, r + 1} & occupied[k]:
                occupied[k].add(r)
                screen.put(r, 0, label.rjust(6), MUTED)
    screen.put(p.top + p.rows + 2, p.left, truncate(axis['x'].get('label') or 'x', p.cols), MUTED)


class Dashboard:
    """Pure layout/input state; the POSIX driver is separate and testable."""
    def __init__(self, figures, *, columns=None, title='Dashboard', color=True):
        if columns is not None:
            _positive(columns, 'columns')
        self.columns, self.title, self.color = columns, title, color
        self.active, self.dragging, self.updates = 0, None, 0
        self.cols, self.rows, self.tiles = 120, 38, []
        self.replace(figures)

    def replace(self, figures):
        sources = list(figures)
        if not sources:
            raise ValueError('dashboard requires at least one figure')
        # Build all new state before replacing the previous snapshot.
        viewers = [make_viewer(source) for source in sources]
        self.viewers = viewers
        self.active = min(self.active, len(viewers) - 1)
        self.cache = {}
        self.layout(self.cols, self.rows)

    def layout(self, cols, rows):
        self.cols, self.rows = cols, rows
        self.tiles = layout(len(self.viewers), cols, rows, self.columns)
        self.dragging = None
        self.cache.clear()
        for i, v in enumerate(self.viewers):
            v.box = v.press = v.grab = v.hover = v.projection = None
            v.reason = v.initial_reason
            if i >= len(self.tiles):
                continue
            tile = self.tiles[i]
            v.cols, v.rows = tile.cols, tile.rows
            if not v.reason:
                try:
                    v.projection = Projection(v.record['axes'][0], 7, 4, tile.cols - 9, tile.rows - 8)
                except ValueError as exc:
                    v.reason = str(exc)

    def mouse(self, button, col, row, up):
        for v in self.viewers:
            v.hover = None
        hit = next((i for i, t in enumerate(self.tiles)
                    if t.x <= col < t.x + t.cols and t.y <= row < t.y + t.rows), None)
        index = self.dragging if self.dragging is not None else hit
        if index is None:
            return
        self.active = index
        t, v = self.tiles[index], self.viewers[index]
        v.mouse(button, col - t.x, row - t.y, up)
        if v.press is not None:
            self.dragging = index
        if up:
            self.dragging = None

    def key(self, key):
        if key in '123456789' and int(key) <= len(self.viewers):
            self.active = int(key) - 1
        if key == 'x':
            self.viewers[self.active].key(key)
            self.dragging = None
        return key == 'q'

    def _tile(self, index):
        v, t = self.viewers[index], self.tiles[index]
        screen = Screen(t.cols, t.rows)
        axis = v.record['axes'][0] if v.record['axes'] else {}
        title = v.record.get('title') or axis.get('title') or 'Chart'
        screen.put(0, 0, truncate(f'{index + 1:02} / {title}', t.cols), INK)
        if v.projection is None:
            heat = {m['kind'] for m in v.record['marks']} == {'heat'}
            caption = 'STATIC HEATMAP · source palette / scale' if heat and v.static else 'STATIC · ' + v.reason
            screen.put(1, 0, truncate(caption, t.cols), MUTED)
            if index not in self.cache:
                try:
                    text = v.static(t.cols, t.rows - 3) if v.static else v.static_record()
                    lines = text.splitlines()
                    if lines and clean_text(lines[0]).strip() == clean_text(title).strip():
                        lines = lines[1:]  # Dashboard heading already names this chart.
                    text = '\n'.join(lines)
                    if len(lines) > t.rows - 3 or any(width(line) > t.cols for line in lines):
                        text = 'Chart needs a larger tile.\nResize or use fewer columns.'
                    self.cache[index] = _ansi_screen(text, t.cols, t.rows - 3)
                except Exception as exc:
                    self.cache[index] = _ansi_screen(f'Static rendering unavailable:\n{type(exc).__name__}: {exc}', t.cols, t.rows - 3)
            _paste(screen, self.cache[index], 0, 3)
            return screen
        visible = [p for p in v.points if v.projection.visible(p.x, p.y)]
        caption = f'{len(visible):,} visible knots / endpoints' if not v.has_scatter else f'{len(v.chosen()):,} / {sum(p.kind == "points" for p in visible):,} points'
        if v.box:
            result = stats(v.chosen())
            caption += f' selected · r={result["correlation"]:.3f}' if result['correlation'] is not None else ' selected · r=n/a'
        if any(m['kind'] == 'bars' and 'width' not in m for m in v.record['marks']):
            caption += ' · widths estimated'
        screen.put(1, 0, truncate(caption, t.cols), GOOD if v.box else MUTED)
        col = 0
        for j, m in enumerate(v.record['marks']):
            name = m.get('name') or m['kind']
            label = truncate('━ ' + name, max(0, min(22, t.cols - col)))
            screen.put(2, col, label, PALETTE[j % len(PALETTE)])
            col += width(label) + 2
            if col >= t.cols:
                break
        _plot(v, screen)
        _axes(v, screen)
        return screen

    def frame(self, *, interactive=True, live=False):
        screen = Screen(self.cols, self.rows)
        screen.put(0, 1, truncate(self.title, max(0, self.cols - 2)), INK)
        mode = f'LIVE · update {self.updates:04}' if live else 'SNAPSHOT'
        screen.put(1, 1, truncate(f'{len(self.viewers):02} charts / {mode}', max(0, self.cols - 2)), MUTED)
        if not self.tiles:
            screen.put(3, 1, f'Resize to fit all {len(self.viewers)} charts.', GOOD)
            screen.put(4, 1, f'Each tile needs {MIN_COLS}x{MIN_ROWS} cells; try a wider/taller terminal or fewer columns.', MUTED)
        for i, tile in enumerate(self.tiles):
            _paste(screen, self._tile(i), tile.x, tile.y)
            # A quiet focus rule, not a frame around every plot.
            if interactive and i == self.active:
                for c in range(tile.cols):
                    screen.put(tile.y - 1, tile.x + c, '─', PALETTE[0])
        v = self.viewers[self.active]
        if v.hover:
            p = v.hover
            text = f'{self.active + 1:02} / {p.name}[{p.index}] x={p.x!r} y={p.y!r}'
            if p.kind == 'bars':
                text += f' base={p.base!r} top={p.top!r} value={p.top - p.base!r}'
            screen.put(self.rows - 2, 1, truncate(text, max(0, self.cols - 2)), INK)
        controls = 'hover inspect · drag scatter brush · 1-9 focus · x clear · q quit' if interactive else 'trendsetter-axi · static dashboard · interactive=True to explore'
        screen.put(self.rows - 1, 1, truncate(controls, max(0, self.cols - 2)), MUTED)
        return screen.text(self.color)


def run(model, *, refresh=None, interval=1.0, stdin=None, stdout=None):
    """Poll size/input and a monotonic callback deadline; always restore modes."""
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    parser = InputParser()
    with terminal_session(stdin, stdout):
        size, dirty = None, True
        deadline = time.monotonic() + interval
        while True:
            current = os.get_terminal_size(stdout.fileno())
            if current != size:
                size = current
                model.layout(size.columns, size.lines)
                dirty = True
            now = time.monotonic()
            if refresh is not None and now >= deadline:
                model.replace(refresh())
                model.updates += 1
                deadline = time.monotonic() + interval
                dirty = True
            if dirty:
                stdout.write('\x1b[?2026h\x1b[H' + model.frame(live=refresh is not None) + '\x1b[?2026l')
                stdout.flush()
                dirty = False
            timeout = min(.1, max(0, deadline - time.monotonic())) if refresh else .1
            if not select.select([stdin], [], [], timeout)[0]:
                continue
            data = os.read(stdin.fileno(), 4096)
            if not data:
                return
            for kind, value in parser.feed(data):
                if kind == 'mouse':
                    model.mouse(*value)
                elif model.key(value):
                    return
            dirty = True


def dashboard(figures, *, columns=None, cols=None, rows=None, title='Dashboard',
              color=True, interactive=False, refresh=None, interval=1.0):
    """Tile matplotlib Figures or v1 records in one styled terminal screen.

    By default return a string (no input or terminal mode changes). Missing cols /
    rows use the output terminal size, falling back to 120x38 in captured output.
    interactive=True opens the POSIX TTY viewer at its actual size (cols/rows
    only affect static output). refresh is an optional no-argument
    callback returning a new nonempty iterable of figures/records every interval
    seconds. Live refresh requires interactive=True. q exits, x clears the focused
    scatter brush. Heatmaps/unsupported charts use their existing static renderer.
    """
    for value, name in ((cols, 'cols'), (rows, 'rows'), (columns, 'columns')):
        if value is not None:
            _positive(value, name)
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
        raise ValueError('interval must be a finite positive number')
    if refresh is not None and (not callable(refresh) or not interactive):
        raise ValueError('refresh must be callable and requires interactive=True')
    model = Dashboard(figures, columns=columns, title=title, color=color)
    if interactive:
        return run(model, refresh=refresh, interval=interval)
    size = shutil.get_terminal_size(fallback=(120, 38))
    model.layout(size.columns if cols is None else cols, size.lines if rows is None else rows)
    return model.frame(interactive=False)
