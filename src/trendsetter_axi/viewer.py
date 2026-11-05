"""Record-backed terminal viewer. Input/state are independent of the POSIX driver."""
from contextlib import contextmanager
from dataclasses import dataclass
import math
import os
import re
import select
import signal
import sys


class InputParser:
    """Consume fragmented SGR mouse reports and keys in wire order."""
    mouse = re.compile(rb"\x1b\[<(\d+);(\d+);(\d+)([Mm])")

    def __init__(self):
        self.buffer = b""

    def feed(self, data):
        self.buffer += data
        events = []
        while self.buffer:
            if self.buffer[0] != 27:
                byte, self.buffer = self.buffer[0], self.buffer[1:]
                if byte == 3:
                    raise KeyboardInterrupt
                if 32 <= byte < 127:
                    events.append(("key", chr(byte)))
                continue
            if len(self.buffer) < 2:
                break
            if self.buffer[1:2] == b"[":
                end = next((i for i in range(2, len(self.buffer)) if 64 <= self.buffer[i] <= 126), None)
                if end is None:
                    break
                report, self.buffer = self.buffer[:end + 1], self.buffer[end + 1:]
                match = self.mouse.fullmatch(report)
                if match:
                    events.append(("mouse", (int(match[1]), int(match[2]) - 1,
                                              int(match[3]) - 1, match[4] == b"m")))
            elif self.buffer[1:2] == b"O":
                if len(self.buffer) < 3:
                    break
                self.buffer = self.buffer[3:]
            else:
                self.buffer = self.buffer[2:]
        return events


def stats(points):
    """Geometry counts (not subjects), arithmetic means and OLS in data units."""
    n = len(points)
    result = dict(n=n, mean_x=None, mean_y=None, correlation=None, slope=None)
    if not n:
        return result
    mx = math.fsum(p.x / n for p in points)
    my = math.fsum(p.y / n for p in points)
    dx, dy = [p.x - mx for p in points], [p.y - my for p in points]
    sx, sy = max(map(abs, dx)), max(map(abs, dy))
    # Scale deviations before squaring; ordinary large coordinates stay usable.
    xx = math.fsum((d / sx) ** 2 for d in dx) if sx else 0
    yy = math.fsum((d / sy) ** 2 for d in dy) if sy else 0
    xy = math.fsum((a / sx) * (b / sy) for a, b in zip(dx, dy)) if sx and sy else 0
    result.update(mean_x=mx, mean_y=my,
                  correlation=xy / math.sqrt(xx * yy) if xx and yy else None,
                  slope=(xy / xx) * (sy / sx) if xx else None)
    return result


@dataclass(frozen=True)
class Point:
    mark: str
    name: str
    index: int
    kind: str
    x: float
    y: float
    base: float | None = None
    top: float | None = None
    label: str = ""


class Projection:
    """Data -> terminal cells; inverse limits and log scales are preserved."""
    def __init__(self, axis, left, top, cols, rows):
        self.axis = axis
        self.left, self.top, self.cols, self.rows = left, top, cols, rows
        self.limits = []
        for k in "xy":
            scale = axis[k]
            if scale["scale"] not in ("linear", "log", "date", "category"):
                raise ValueError(f"unsupported {k} scale: {scale['scale']}")
            lo, hi = [self.transform(k, v) for v in scale["range"]]
            if not all(map(math.isfinite, (lo, hi))) or lo == hi:
                raise ValueError(f"unusable {k} range")
            self.limits.append((lo, hi))

    def transform(self, k, value):
        if self.axis[k]["scale"] == "log":
            return math.log(value) if value > 0 else float("nan")
        return value

    def cell(self, x, y):
        values = [self.transform("x", x), self.transform("y", y)]
        fx, fy = [(v - lo) / (hi - lo) for v, (lo, hi) in zip(values, self.limits)]
        return self.left + fx * (self.cols - 1), self.top + (1 - fy) * (self.rows - 1)

    def inside(self, col, row):
        return self.left <= col <= self.left + self.cols - 1 and self.top <= row <= self.top + self.rows - 1

    def visible(self, x, y):
        c, r = self.cell(x, y)
        return math.isfinite(c) and math.isfinite(r) and self.inside(c, r)


def _points(mark):
    name = mark.get("name") or mark["id"]
    if mark["kind"] == "bars":
        horizontal = mark.get("orientation") == "h"
        labels = mark.get('labels')
        for i, (pos, base, top) in enumerate(zip(mark["x"], mark["base"], mark["top"])):
            if not all(v is not None and math.isfinite(v) for v in (pos, base, top)):
                continue
            yield Point(mark["id"], name, i, "bars", top if horizontal else pos,
                        pos if horizontal else top, base, top, labels[i] if labels is not None else '')
    elif mark["kind"] in ("points", "line"):
        for i, (x, y) in enumerate(zip(mark["x"], mark["y"])):
            if x is not None and y is not None and math.isfinite(x) and math.isfinite(y):
                yield Point(mark["id"], name, i, mark["kind"], x, y)


def line_edges(mark, points, projection):
    """Draw/hit-test the same source segments, including gaps and step rules."""
    breaks = set(mark.get('breaks', []))
    style = mark.get('interp', 'linear')
    for left, right in zip(points, points[1:]):
        if right.index in breaks or right.index != left.index + 1:
            continue
        x0, y0 = projection.cell(left.x, left.y)
        x1, y1 = projection.cell(right.x, right.y)
        if not all(map(math.isfinite, (x0, y0, x1, y1))):
            continue
        path = [(x0, y0 * 2)]
        if style == 'step-pre':
            path.append((x0, y1 * 2))
        elif style == 'step-post':
            path.append((x1, y0 * 2))
        elif style == 'step-mid':
            mid, _ = projection.cell(left.x / 2 + right.x / 2, left.y)
            path.extend([(mid, y0 * 2), (mid, y1 * 2)])
        path.append((x1, y1 * 2))
        yield path, left, right


class Viewer:
    """One-axis interaction model; unsupported records retain a static view."""
    def __init__(self, record, static=None):
        if not isinstance(record, dict) or record.get("version") != 1:
            raise ValueError("viewer requires a version 1 chart record")
        self.record, self.static = record, static
        self.points = [p for m in record["marks"] for p in _points(m)]
        self.marks = {m["id"]: m for m in record["marks"]}
        self.draw_marks = record['marks']
        self.has_scatter = any(m['kind'] == 'points' for m in record['marks'])
        self.hover = self.box = self.press = self.grab = None
        self.projection = None
        self.reason = ""
        if len(record["axes"]) != 1:
            self.reason = "multiple or missing axes"
        kinds = sorted({m["kind"] for m in record["marks"]} - {"points", "line", "bars"})
        if kinds:
            self.reason = "unsupported interactions: " + ", ".join(kinds)
        if record.get("not_described"):
            self.reason = "unread artists in record"
        if any("geometry unavailable" in s or "bounds and centers unavailable" in s for s in record.get("unavailable", [])):
            self.reason = "source geometry unavailable"
        if any(m.get('interp') == 'unavailable' for m in record['marks']):
            self.reason = 'unsupported line interpolation'
        if any('xerr' in m or 'yerr' in m for m in record['marks']):
            self.reason = 'errorbar interactions unavailable'
        self.initial_reason = self.reason

    def layout(self, cols, rows):
        self.cols, self.rows = cols, rows
        self.projection = None
        self.reason = self.initial_reason
        if cols < 80 or rows < 24:
            return
        if not self.reason:
            try:
                projection = Projection(self.record["axes"][0], 8, 6, cols - 52, rows - 13)
                for k in 'xy':
                    if projection.axis[k]['scale'] == 'log' and any(
                            point.kind == 'line' and getattr(point, k) <= 0 for point in self.points):
                        raise ValueError(f'nonpositive {k} line coordinates on log axis')
                self.projection = projection
            except ValueError as exc:
                self.reason = str(exc)

    def bar_bounds(self, point):
        m = self.marks[point.mark]
        horizontal = m.get("orientation") == "h"
        pos = point.y if horizontal else point.x
        # Saved v1 records contain exact centers/endpoints but omit widths.
        widths = m.get('width')
        w = widths[point.index] if widths is not None else 0.8
        footprint = sorted((pos - w / 2, pos + w / 2))
        value = sorted((point.base, point.top))
        intervals = (value, footprint) if horizontal else (footprint, value)
        clipped = []
        for k, (lo, hi) in zip('xy', intervals):
            lower, upper = sorted(self.projection.axis[k]['range'])
            lo, hi = max(lo, lower), min(hi, upper)
            if lo > hi:
                return (float('nan'),) * 4
            clipped.append((lo, hi))
        (x0, x1), (y0, y1) = clipped
        c0, r0 = self.projection.cell(x0, y0)
        c1, r1 = self.projection.cell(x1, y1)
        return min(c0, c1), min(r0, r1), max(c0, c1), max(r0, r1)

    def nearest(self, col, row):
        """Exact stored knot/bar, never a fabricated interpolated value."""
        p = self.projection
        if p is None or not p.inside(col, row):
            return None
        for mark in reversed(self.draw_marks):
            points = [point for point in self.points if point.mark == mark['id']]
            best, score = None, 2.5
            for point in reversed(points):
                if point.kind == 'bars':
                    c0, r0, c1, r1 = self.bar_bounds(point)
                    if c0 <= col <= c1 and r0 <= row <= r1:
                        return point
                    continue
                if not p.visible(point.x, point.y):
                    continue
                c, r = p.cell(point.x, point.y)
                distance = math.hypot(c - col, 2 * (r - row))
                if distance < score:
                    best, score = point, distance
            if mark['kind'] == 'line':
                for path, left, right in line_edges(mark, points, p):
                    for a, b in zip(path, path[1:]):
                        dx, dy = b[0] - a[0], b[1] - a[1]
                        length = math.hypot(dx, dy)
                        along = (col - a[0]) * (dx / length) + (row * 2 - a[1]) * (dy / length) if length else 0
                        t = max(0, min(1, along / length)) if length else 0
                        distance = math.hypot(col - (a[0] + t * dx), row * 2 - (a[1] + t * dy))
                        if distance < score:
                            def endpoint_distance(point):
                                c, r = p.cell(point.x, point.y)
                                return math.hypot(c - col, 2 * (r - row))
                            best = min((left, right), key=endpoint_distance)
                            score = distance
            if best is not None:
                return best
        return None

    def chosen(self):
        p = self.projection
        if p is None:
            return []
        points = [v for v in self.points if v.kind == "points" and p.visible(v.x, v.y)]
        if self.box is None:
            return points
        c0, r0, c1, r1 = self.box
        return [v for v in points if c0 <= p.cell(v.x, v.y)[0] <= c1 and r0 <= p.cell(v.x, v.y)[1] <= r1]

    def mouse(self, button, col, row, up):
        p = self.projection
        if p is None or button & 64:
            return
        self.hover = self.nearest(col, row)
        if self.has_scatter and not up and not button & 32 and button & 3 == 0 and p.inside(col, row):
            self.press = (col, row)
            self.grab = self.box if self.box and self.box[0] <= col <= self.box[2] and self.box[1] <= row <= self.box[3] else None
            if self.grab is None:
                self.box = None
        elif self.press and (up or button & 32 and button & 3 == 0):
            c = max(p.left, min(p.left + p.cols - 1, col))
            r = max(p.top, min(p.top + p.rows - 1, row))
            a, b = self.press
            if self.grab:
                c0, r0, c1, r1 = self.grab
                dx = max(p.left - c0, min(p.left + p.cols - 1 - c1, c - a))
                dy = max(p.top - r0, min(p.top + p.rows - 1 - r1, r - b))
                self.box = (c0 + dx, r0 + dy, c1 + dx, r1 + dy)
            else:
                self.box = (min(a, c), min(b, r), max(a, c), max(b, r))
            if up:
                self.press = self.grab = None

    def key(self, key):
        if key == "x":
            self.box = self.press = self.grab = None
        return key == "q"

    def frame(self):
        from .styled import draw
        return draw(self)

    def static_record(self):
        """Static data overview when original figure ink isn't available."""
        lines = [self.record.get("title", ""), "Saved record: data overview (original figure ink unavailable)"]
        for m in self.record["marks"]:
            lines.append(f"{m.get('name') or m['id']} ({m['kind']})")
            for key in ("x", "y", "base", "top", "z", "lo", "hi"):
                if key in m:
                    lines.append(f"  {key}: {m[key]}")
        return "\n".join(lines)


ENTER = "\x1b[?1049h\x1b[?25l\x1b[?1003h\x1b[?1006h\x1b[2J"
LEAVE = "\x1b[?2026l\x1b[0m\x1b[?1006l\x1b[?1003l\x1b[?25h\x1b[?1049l"


@contextmanager
def terminal_session(stdin, stdout):
    """Restore terminal modes even if setup, drawing or input raises."""
    if not stdin.isatty() or not stdout.isatty():
        raise ValueError("interact requires a real input/output TTY; use render_styled() or render() for captured output")
    if os.name != "posix":
        raise ValueError("interact requires a POSIX terminal with SGR mouse reporting")
    import termios
    import tty

    fd = stdin.fileno()
    saved = termios.tcgetattr(fd)
    handlers = {}
    def terminate(signum, frame):
        raise SystemExit(128 + signum)
    try:
        for sig in (signal.SIGTERM, signal.SIGHUP):
            handlers[sig] = signal.signal(sig, terminate)
        tty.setcbreak(fd)
        stdout.write(ENTER)
        stdout.flush()
        yield
    finally:
        try:
            stdout.write(LEAVE)
            stdout.flush()
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSANOW, saved)
            finally:
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)


def run(viewer, stdin=None, stdout=None):
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    parser = InputParser()
    with terminal_session(stdin, stdout):
        dirty, size = True, None
        while True:
            current = os.get_terminal_size(stdout.fileno())
            if current != size:
                size = current
                viewer.box = viewer.press = viewer.grab = viewer.hover = None
                viewer.layout(size.columns, size.lines)
                dirty = True
            if dirty:
                stdout.write("\x1b[?2026h\x1b[H" + viewer.frame() + "\x1b[?2026l")
                stdout.flush()
                dirty = False
            if not select.select([stdin], [], [], 0.1)[0]:
                continue
            data = os.read(stdin.fileno(), 4096)
            if not data:
                return
            for kind, value in parser.feed(data):
                if kind == "mouse":
                    viewer.mouse(*value)
                elif viewer.key(value):
                    return
            dirty = True


def make_viewer(source):
    """Read source once; artist order and width hints stay private to the viewer."""
    if isinstance(source, dict):
        return Viewer(source)
    from . import render
    from .record import _collect_figure
    from matplotlib.collections import PathCollection
    from matplotlib.container import BarContainer
    import numpy as np

    collected = _collect_figure(source)
    record = collected.result
    axes = [ax for ax in source.axes if not hasattr(ax, '_colorbar') and ax.get_visible()]
    ranks = [{artist: i for i, artist in enumerate(sorted(ax.get_children(), key=lambda a: a.get_zorder()))}
             for ax in axes]
    painter, reason = [], ''
    for mark, artist in zip(record['marks'], collected.artists):
        artists = [artist]
        if isinstance(artist, BarContainer):
            artists = [b for b in artist if b.get_visible() and all(math.isfinite(v) for v in
                       (b.get_x(), b.get_y(), b.get_width(), b.get_height()))]
            if len(artists) == len(mark['x']):
                mark['width'] = [b.get_height() if artist.orientation == 'horizontal' else b.get_width() for b in artists]
            else:
                reason = 'bar geometry unavailable'
        positions = [ranks[mark['axes']].get(a, -1) for a in artists]
        if -1 in positions or positions != sorted(positions):
            reason = 'source painter order unavailable'
        painter.extend((mark['axes'], rank, mark['id']) for rank in positions)
        if isinstance(artist, PathCollection) and (artist.get_array() is not None or any(
                len(np.unique(values, axis=0)) > 1 for values in
                (artist.get_sizes(), artist.get_facecolors(), artist.get_edgecolors(), artist.get_linewidths()))):
            reason = 'unsupported scatter encodings'
    order = []
    for _, _, key in sorted(painter):
        if not order or order[-1] != key:
            order.append(key)
    if len(order) != len(set(order)):
        reason = 'interleaved artist painter order unavailable'
    viewer = Viewer(record, lambda cols, rows: render(source, cols=cols, rows=rows, color=True).text)
    viewer.draw_marks = [viewer.marks[key] for key in order]
    if reason:
        viewer.initial_reason = reason
    if any(hasattr(ax, '_colorbar') and ax.get_visible() for ax in source.axes):
        viewer.initial_reason = 'unsupported colorbar encoding'
    if any(ax.name != 'rectilinear' for ax in axes):
        viewer.initial_reason = 'non-rectilinear axes'
    return viewer


def interact(source):
    """Explore a matplotlib Figure or v1 record in a POSIX mouse-enabled terminal.

    Drag to select scatter points; hover for exact stored knots/bar values.
    x clears selection, q exits. No GUI/backend changes or new dependencies.
    Unsupported figures get a static chart; saved records get a data overview.
    """
    run(make_viewer(source))


def main(argv=None):
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Explore a saved trendsetter chart record (POSIX TTY required)")
    parser.add_argument("record", help="JSON from trendsetter_axi.from_figure(fig)")
    args = parser.parse_args(argv)
    try:
        with open(args.record, encoding="utf-8") as f:
            interact(json.load(f))
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"interact: {exc}", file=sys.stderr)
        return 1
    return 0
