"""Human-facing terminal styling, shared by static display and interactive view.

The agent-facing render/summary/record contracts are deliberately unchanged.
"""
import math

from .cells import clean_text, clusters, pack_entries, truncate, width

BG, INK = (15, 17, 21), (236, 236, 232)
MUTED, FAINT, GHOST = (150, 152, 158), (84, 87, 96), (100, 104, 114)
GOOD, BRUSH_BG, TIP_BG = (255, 225, 120), (31, 38, 50), (46, 52, 66)
PALETTE = [(92, 200, 250), (255, 170, 70), (120, 225, 150), (207, 160, 240)]
UP, RIGHT = ' ▁▂▃▄▅▆▇█', ' ▏▎▍▌▋▊▉█'


def _number(value, cols, *, signed=False):
    if value is None:
        return '-'
    if isinstance(value, int):
        text = f'{value:,}'
        if len(text) <= cols:
            return text
    for precision in range(3 if signed else 4, 1, -1):
        text = format(value, f'{"+" if signed else ""}.{precision}g')
        mantissa, sep, exponent = text.partition('e')
        if sep:
            text = f'{mantissa}e{int(exponent)}'
        if len(text) <= cols:
            return text
    raise ValueError('number does not fit terminal cell')


def _numeric_ticks(scale, ticks, cols):
    labels = [clean_text(tick['label']) for tick in ticks]
    if scale.get('_custom_ticks') or any(label != f"{tick['value']:.4g}" for tick, label in zip(ticks, labels)):
        return [truncate(label, cols) for label in labels], ''
    if not ticks:
        return [], ''
    values = [tick['value'] for tick in ticks]
    if max(map(len, labels)) <= cols and len(set(labels)) == len(set(values)):
        return labels, ''
    origin = min(values)
    largest = max(map(abs, values))
    factor = 10.0 ** max(-323, math.floor(math.log10(largest))) if largest else 1.0
    scopes = [(values, ''), ([value - origin for value in values], f'offset {origin!r}'),
              ([value / factor for value in values], f'×{factor!r}')]
    for scope, context in scopes:
        if not all(map(math.isfinite, scope)):
            continue
        for precision in range(4, 18):
            labels = []
            for value in scope:
                text = format(value, f'.{precision}g')
                mantissa, sep, exponent = text.partition('e')
                labels.append(f'{mantissa}e{int(exponent)}' if sep else text)
            if max(map(len, labels)) <= cols and len(set(labels)) == len(set(values)):
                return labels, context
    return [], 'numeric ticks omitted: precision'


def _date_ticks(scale, ticks, cols):
    from matplotlib import dates as mdates

    if not ticks:
        return [], ''
    values = [tick['value'] for tick in ticks]
    dates = mdates.num2date(values, tz=scale.get('timezone', 'UTC'))
    full = [date.replace(tzinfo=None).isoformat(sep=' ', timespec='microseconds') for date in dates]
    fields = [(0, 4), (5, 7), (8, 10), (11, 13), (14, 16), (17, 19), (20, 26)]
    varying = [i for i, (lo, hi) in enumerate(fields) if len({text[lo:hi] for text in full}) > 1]
    lo, hi = fields[min(varying, default=6)][0], fields[max(varying, default=6)][1]
    labels = [text[lo:hi] for text in full]
    template = 'YYYY-MM-DD HH:MM:SS.ffffff'
    context = full[0][:lo] + template[lo:hi] + full[0][hi:] + dates[0].strftime(' %z')
    if (max(map(len, labels)) <= cols and len(set(labels)) == len(set(values)) and
            len({date.utcoffset() for date in dates}) == 1 and len(context) <= 32):
        return labels, context
    origin = min(values)
    seconds = (max(values) - origin) * 86400
    unit, divisor = next((name, size) for name, size in
                         [('d', 86400), ('h', 3600), ('m', 60), ('s', 1), ('ms', .001), ('us', .000001)]
                         if seconds >= size or name == 'us')
    labels = [_number((value - origin) * 86400 / divisor, cols) for value in values]
    context = mdates.num2date(origin).replace(tzinfo=None).isoformat(sep=' ', timespec='microseconds') + f'Z +{unit}'
    return labels, context


class Screen:
    def __init__(self, cols, rows):
        self.cols, self.rows = cols, rows
        self.cells = [[(' ', INK, BG) for _ in range(cols)] for _ in range(rows)]
        self.owner = None
        self.owners = {}

    def put(self, row, col, text, fg=INK, bg=None):
        if not 0 <= row < self.rows:
            return
        # Never interpret source strings as terminal control sequences.
        for token, size in clusters(clean_text(str(text)).replace('\n', ' ').replace('\t', ' ')):
            if size < 1:
                continue
            if col >= 0 and col + size <= self.cols:
                # Erase a complete old wide character when overwriting either half.
                for c in range(col, col + size):
                    if self.cells[row][c][0] == '' and c:
                        self.cells[row][c - 1] = (' ', fg, self.cells[row][c - 1][2])
                    elif c + 1 < self.cols and self.cells[row][c + 1][0] == '':
                        self.cells[row][c + 1] = (' ', fg, self.cells[row][c + 1][2])
                self.cells[row][col] = (token, fg, bg if bg is not None else self.cells[row][col][2])
                if self.owner is not None:
                    self.owners[col, row] = self.owner
                for c in range(col + 1, col + size):
                    self.cells[row][c] = ('', fg, bg if bg is not None else self.cells[row][c][2])
            col += size

    def shade(self, row, col, bg):
        ch, fg, _ = self.cells[row][col]
        self.cells[row][col] = (ch, fg, bg)

    def canvas(self, canvas):
        """Use existing renderer primitives/composition, without trimming its grid."""
        raster = canvas._rasterize(True)
        cells, sid, heatrgb = canvas._compose_cells(raster)
        _, inv = canvas._place_text(raster, cells, sid)
        for r in range(min(self.rows, canvas.rows)):
            for c in range(min(self.cols, canvas.cols)):
                if cells[r, c] and cells[r, c] != ' ':
                    rgb = tuple(int(v * 255) for v in inv[sid[r, c]]) if sid[r, c] >= 0 else INK
                    bg, fg = heatrgb.get((r, c), (None, rgb))
                    self.put(r, c, cells[r, c], fg, bg)

    def bar(self, bounds, rgb, *, horizontal):
        c0, r0, c1, r1 = bounds
        if not all(map(math.isfinite, bounds)) or c0 >= c1 or r0 >= r1:
            return
        for r in range(max(0, math.floor(r0)), min(self.rows, math.ceil(r1))):
            for c in range(max(0, math.floor(c0)), min(self.cols, math.ceil(c1))):
                coverage = min(c + 1, c1) - max(c, c0) if horizontal else min(r + 1, r1) - max(r, r0)
                level = max(1, min(8, math.ceil(coverage * 8)))
                self.put(r, c, (RIGHT if horizontal else UP)[level], rgb)

    def text(self, color=True):
        out, last = [], None
        for r, row in enumerate(self.cells):
            for ch, fg, bg in row:
                if color and (fg, bg) != last:
                    out.append('\x1b[38;2;%d;%d;%d;48;2;%d;%d;%dm' % (*fg, *bg))
                    last = (fg, bg)
                out.append(ch)
            if r < self.rows - 1:
                out.append('\r\n')
        if color:
            out.append('\x1b[0m')
        return ''.join(out)


def draw(viewer, *, interactive=True, color=True):
    from .core import BITS, Canvas
    from .viewer import line_edges, stats

    v = viewer
    v.hit_cells = {}
    s = Screen(v.cols, v.rows)
    if v.cols < 80 or v.rows < 24:
        s.put(0, 1, 'Resize to at least 80x24' + (' | q quit' if interactive else ''), MUTED)
        return s.text(color)
    if v.reason:
        s.put(0, 1, f'Static view: {v.reason}' + (' | q quit' if interactive else ''), MUTED)
        try:
            text = v.static(v.cols, v.rows - 3) if v.static else v.static_record()
        except Exception as exc:
            text = f'Static rendering unavailable: {type(exc).__name__}: {exc}'
        lines = [clean_text(line) for line in text.splitlines()]
        needed_cols = max(map(width, lines), default=0)
        if len(lines) > v.rows - 3 or needed_cols > v.cols:
            label = 'Static chart' if v.static else 'Saved record: data overview'
            lines = [f'{label} omitted: complete output does not fit.',
                     f'Needs {needed_cols}x{len(lines)} cells; available {v.cols}x{v.rows - 3}.',
                     'Resize terminal to see complete output.']
        for i, line in enumerate(lines, 2):
            s.put(i, 0, line)
        return s.text(color)
    p = v.projection
    axis = v.record['axes'][0]
    title = v.record.get('title') or axis.get('title') or 'Chart'
    s.put(0, 1, truncate(title, v.cols - 2))
    scatter = [a for a in v.points if a.kind == 'points' and p.visible(a.x, a.y)]
    chosen = v.chosen()
    selected = {(a.mark, a.index) for a in chosen}
    visible = [a for a in v.points if p.visible(a.x, a.y)]
    caption = f'{_number(len(scatter), 8)} visible scatter points' if v.has_scatter else f'{_number(len(visible), 8)} visible knots / bar endpoints'
    if v.box:
        caption = f'{_number(len(chosen), 8)} selected / {_number(len(scatter), 8)} visible points'
    s.put(1, 1, caption, MUTED)
    if any(m['kind'] == 'bars' and 'width' not in m for m in v.record['marks']):
        s.put(2, 1, 'Saved bar widths estimated: 0.8', MUTED)
    side, panel = p.left + p.cols + 9, v.cols - (p.left + p.cols + 9) - 1
    header = 'Selection'.ljust(14) + 'selected'.rjust(9) + ' ' + 'visible'.rjust(9) if v.has_scatter else 'Source values'
    s.put(1, side, header, MUTED)
    s.put(2, side, '─' * panel, FAINT)
    a, b = stats(chosen), stats(scatter)
    for row, (key, label) in enumerate([('n', 'points'), ('share', 'share'), ('mean_x', 'mean x'),
                                      ('mean_y', 'mean y'), ('correlation', 'Pearson r'), ('slope', 'OLS slope')], 3):
        if not v.has_scatter:
            continue
        if key == 'share':
            va = f"{len(chosen) / max(len(scatter), 1):.0%}" if v.box else '-'
            vb = '100%' if scatter else '-'
        elif key == 'n':
            va = _number(a[key], 9) if v.box else '-'
            vb = _number(b[key], 9)
        else:
            va = _number(a[key], 9, signed=key in ('correlation', 'slope')) if v.box else '-'
            vb = _number(b[key], 9, signed=key in ('correlation', 'slope'))
        s.put(row, side, label.ljust(14), MUTED)
        s.put(row, side + 14, va.rjust(9), GOOD if key in ('n', 'correlation') else INK)
        s.put(row, side + 24, vb.rjust(9), MUTED)
    if v.has_scatter:
        s.put(9, side, 'points, not subject counts', FAINT)
    else:
        s.put(3, side, 'Hover to inspect exact values', MUTED)
        s.put(5, side, 'Line: nearest stored knot', MUTED)
        s.put(6, side, 'Bar: base, top and value', MUTED)
        s.put(8, side, 'Box-select is scatter-only', FAINT)
    s.put(11, side, 'Series', MUTED)
    for j, m in enumerate(v.record['marks'][:max(0, v.rows - 19)]):
        row = 12 + j
        n = sum(a.mark == m['id'] for a in chosen)
        rgb = PALETTE[j % len(PALETTE)]
        s.put(row, side, truncate(m.get('name') or m['id'], 13), rgb)
        if m['kind'] == 'points':
            units = n / max(len(scatter), 1) * 13 * 8
            s.put(row, side + 14, '█' * int(units // 8) + RIGHT[int(units % 8)].strip(), rgb)
            s.put(row, side + 28, _number(n, panel - 28).rjust(panel - 28), MUTED)
        else:
            count = sum(point.mark == m['id'] for point in visible)
            s.put(row, side + 15, f"{m['kind']} ({_number(count, panel - 18 - len(m['kind']))})", MUTED)
    # Common bounds for both static and interactive geometry, including inverted axes.
    clip = (p.left, p.top * 2, p.left + p.cols, (p.top + p.rows) * 2)
    if v.box and len(chosen) > 2 and a['slope'] is not None:
        canvas = Canvas(v.cols, v.rows * 2, v.cols, max_rows=v.rows)
        canvas.stamp = False
        lo, hi = min(q.x for q in chosen), max(q.x for q in chosen)
        run = []
        for i in range(max(2, p.cols * 2)):
            x = lo + (hi - lo) * i / max(1, p.cols * 2 - 1)
            y = a['mean_y'] + a['slope'] * (x - a['mean_x'])
            c, r = p.cell(x, y)
            run.append((c, r * 2))
        canvas.stroke([run], (0.92, 0.92, 0.91), clip=clip, role='data')
        s.canvas(canvas)
    for m in v.draw_marks:
        s.owner = (m['id'], None)
        j = list(v.marks).index(m['id'])
        rgb = PALETTE[j % len(PALETTE)]
        points = [a for a in v.points if a.mark == m['id']]
        if m['kind'] == 'line':
            canvas = Canvas(v.cols, v.rows * 2, v.cols, max_rows=v.rows)
            canvas.stamp = False
            paths, connected, previous = [], set(), None
            for path, left, right in line_edges(m, points, p):
                if previous == left.index:
                    paths[-1].extend(path[1:])
                else:
                    paths.append(path)
                previous = right.index
                connected.update((left.index, right.index))
            ink = tuple(c / 255 for c in rgb)
            canvas.stroke(paths, ink, clip=clip, role='data')
            isolated = [p.cell(a.x, a.y) for a in points if a.index not in connected and p.visible(a.x, a.y)]
            if isolated:
                canvas.marker([(c, r * 2) for c, r in isolated], ink, clip=clip, role='data')
            s.canvas(canvas)
        elif m['kind'] == 'bars':
            for point in points:
                s.owner = (m['id'], point.index)
                s.bar(v.bar_bounds(point), rgb, horizontal=m.get('orientation') == 'h')
        elif m['kind'] == 'points':
            cells = {}
            for point in points:
                if not p.visible(point.x, point.y):
                    continue
                c, r = p.cell(point.x, point.y)
                ix, iy = min(p.cols * 2 - 1, round((c - p.left) * 2)), min(p.rows * 4 - 1, round((r - p.top) * 4))
                cell = cells.setdefault((p.top + iy // 4, p.left + ix // 2), {})
                active = v.box is None or (point.mark, point.index) in selected
                bits, _ = cell.get(active, (0, point.index))
                cell[active] = (bits | int(BITS[iy % 4, ix % 2]), point.index)
            for (r, c), groups in cells.items():
                active = max(groups)
                bits, index = groups[active]
                s.owner = (m['id'], index)
                s.put(r, c, chr(0x2800 + bits), rgb if active else GHOST)
    s.owner = None
    v.hit_cells = s.owners
    # Linked marginals: visible context in gray, selected portion in yellow.
    hx, hy, sx, sy = [0] * p.cols, [0] * p.rows, [0] * p.cols, [0] * p.rows
    for point in scatter:
        c, r = p.cell(point.x, point.y)
        x, y = round(c - p.left), round(r - p.top)
        hx[x] += 1
        hy[y] += 1
        if (point.mark, point.index) in selected and v.box:
            sx[x] += 1
            sy[y] += 1
    for x in range(p.cols):
        for count, rgb in ((hx[x], GHOST), (sx[x], GOOD)):
            units = count / max(max(hx), 1) * 3 * 8
            for k in range(3):
                level = max(0, min(8, int(units - k * 8)))
                if level:
                    s.put(p.top - 1 - k, p.left + x, UP[level], rgb)
    for y in range(p.rows):
        for count, rgb in ((hy[y], GHOST), (sy[y], GOOD)):
            units = count / max(max(hy), 1) * 6 * 8
            for k in range(6):
                level = max(0, min(8, int(units - k * 8)))
                if level:
                    s.put(p.top + y, p.left + p.cols + 1 + k, RIGHT[level], rgb)
    table_row = 14 + min(len(v.record['marks']), max(0, v.rows - 19))
    s.put(table_row, side, 'Top points by x', MUTED)
    pool = chosen if v.has_scatter else visible
    for r, point in enumerate(sorted(pool, key=lambda q: -q.x)[:max(0, v.rows - table_row - 5)], table_row + 1):
        label = truncate(f'{point.name}[{point.index}]', 14)
        s.put(r, side, label, INK)
        xcols = (panel - 16) // 2
        ycols = panel - 16 - xcols
        s.put(r, side + 15, _number(point.x, xcols).rjust(xcols), MUTED)
        s.put(r, side + 16 + xcols, _number(point.y, ycols).rjust(ycols), MUTED)
    if v.box:
        c0, r0, c1, r1 = v.box
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                s.shade(r, c, BRUSH_BG)
        for c in range(c0, c1 + 1):
            s.put(r0, c, '─', GOOD)
            s.put(r1, c, '─', GOOD)
        for r in range(r0, r1 + 1):
            s.put(r, c0, '│', GOOD)
            s.put(r, c1, '│', GOOD)
        for r, c, ch in ((r0, c0, '┌'), (r0, c1, '┐'), (r1, c0, '└'), (r1, c1, '┘')):
            s.put(r, c, ch, GOOD)
    s.put(p.top - 1, 1, truncate(axis['y'].get('label') or 'y', 7), MUTED)
    for r in range(p.top, p.top + p.rows):
        s.put(r, p.left - 1, '│', FAINT)
    s.put(p.top + p.rows, p.left - 1, '└' + '─' * p.cols, FAINT)
    occupied = {'x': set(), 'y': set()}
    for k in 'xy':
        ticks = [tick for tick in axis[k].get('ticks', []) if
                 p.visible(tick['value'] if k == 'x' else axis['x']['range'][0],
                           tick['value'] if k == 'y' else axis['y']['range'][0])]
        cols = 6 if k == 'y' else 9
        context = ''
        if axis[k]['scale'] == 'date':
            labels, context = _date_ticks(axis[k], ticks, cols)
        elif axis[k]['scale'] == 'linear':
            labels, context = _numeric_ticks(axis[k], ticks, cols)
        else:
            labels = [truncate(clean_text(tick['label']), cols) for tick in ticks]
        if context:
            s.put(9 if k == 'x' else 10, side, f'{k} {context}', MUTED)
        seen = set()
        for tick, label in zip(ticks, labels):
            if axis[k]['scale'] == 'date' and label in seen:
                continue
            seen.add(label)
            x = tick['value'] if k == 'x' else axis['x']['range'][0]
            y = tick['value'] if k == 'y' else axis['y']['range'][0]
            c, r = map(round, p.cell(x, y))
            if k == 'x':
                c = max(p.left, min(p.left + p.cols - width(label), c - width(label) // 2))
                span = set(range(c - 1, c + width(label) + 1))
                if span & occupied[k]:
                    continue
                occupied[k].update(span)
                s.put(p.top + p.rows + 1, c, label, MUTED)
            elif not {r - 1, r, r + 1} & occupied[k]:
                occupied[k].add(r)
                s.put(r, 0, label.rjust(6) + ' ┤', MUTED)
    s.put(p.top + p.rows + 2, p.left, truncate(axis['x'].get('label') or 'x', p.cols), MUTED)
    # Exact inspection has a stable footer; it never covers the plot or side panel.
    if v.hover:
        a = v.hover
        if a.kind == 'points':
            for (c, r), owner in v.hit_cells.items():
                if owner == (a.mark, a.index):
                    s.put(r, c, '◉', INK, TIP_BG)
                    break
        elif p.visible(a.x, a.y):
            c, r = p.cell(a.x, a.y)
            s.put(round(r), round(c), '◉', INK, TIP_BG)
        def labeled(text, label):
            label = clean_text(label).replace('\n', ' ').replace('\t', ' ')
            label = truncate(label, max(0, v.cols - 3 - width(text)))
            return f'{label} {text}' if label else text
        bar_lines = pack_entries('', [f'base={a.base!r}', f'top={a.top!r}', f'value={a.top - a.base!r}'],
                                 v.cols - 2) if a.kind == 'bars' else []
        row = v.rows - 2 - max(1, len(bar_lines))
        text = f'[{a.index}]  x={a.x!r}  y={a.y!r}'
        s.put(row, 1, labeled(text, a.name), INK, TIP_BG)
        if a.kind == 'bars':
            for i, line in enumerate(bar_lines, row + 1):
                s.put(i, 1, labeled(line, a.label) if i == v.rows - 2 else line, MUTED)
        else:
            labels = []
            for key, val in (('x', a.x), ('y', a.y)):
                scale = axis[key]
                if scale['scale'] == 'category':
                    labels.extend(f'{key}: {label}' for label, pos in scale.get('mapping', {}).items() if pos == val)
                elif scale['scale'] == 'date':
                    labels.append(f"{key}: matplotlib date days ({scale.get('timezone', 'UTC')})")
            s.put(v.rows - 2, 1, truncate(clean_text(' | '.join(labels)).replace('\n', ' ').replace('\t', ' '), v.cols - 2), MUTED)
    else:
        caption = 'gray: context · yellow: selection · white: OLS trend (data units)' if v.has_scatter else 'Hover inspects exact source values; lines report the nearest stored knot.'
        s.put(v.rows - 3, 1, caption, MUTED)
    controls = 'drag brush  hover inspect  x clear  q quit' if v.has_scatter else 'hover inspect  q quit'
    s.put(v.rows - 1, 1, controls if interactive else 'trendsetter-axi · static terminal view · call interact(fig) to explore', MUTED)
    return s.text(color)


def render_styled(source, cols=120, rows=38, *, color=True):
    """Styled human-facing terminal chart; no input, TTY probes or interaction.

    Supports the viewer's scatter/line/bar charts; other figures use the existing
    static renderer. render(...).text, summaries and chart records stay unchanged.
    """
    from .viewer import make_viewer

    if isinstance(cols, bool) or not isinstance(cols, int) or cols < 1:
        raise ValueError('cols must be a positive integer')
    if isinstance(rows, bool) or not isinstance(rows, int) or rows < 1:
        raise ValueError('rows must be a positive integer')
    viewer = make_viewer(source)
    viewer.layout(cols, rows)
    return draw(viewer, interactive=False, color=color)
