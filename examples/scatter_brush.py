#!/usr/bin/env python3
"""Interactive terminal scatter brush on synthetic data, Python stdlib only.

drag: new brush   drag inside: move it   hover: inspect   click a table row: pin account
z: zoom to brush   b: zoom back   x: clear   1/2/3: toggle segment   q: quit
"""
import math, os, random, re, select, shutil, signal, sys, termios, time, tty

MOUSE = re.compile(rb"\x1b\[<(\d+);(\d+);(\d+)([Mm])")
BITS = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]]
UP = " ▁▂▃▄▅▆▇█"
RIGHT = " ▏▎▍▌▋▊▉█"
INK, MUTED, FAINT, GHOST = (236, 236, 232), (150, 152, 158), (84, 87, 96), (100, 104, 114)
BRUSH_BG, TIP_BG, ROW_BG = (31, 38, 50), (46, 52, 66), (38, 44, 56)
SEGMENTS = [("Starter", (92, 200, 250)), ("Growth", (255, 170, 70)), ("Enterprise", (120, 225, 150))]
GOOD, ALERT = (255, 225, 120), (240, 110, 110)
SIDE = 36
MIN_COLS, MIN_ROWS = 80, 20
X_FULL, Y_FULL = (0.0, 120.0), (0.0, 100.0)


def make_accounts():
    rng, out = random.Random(17), []
    for seg, (mx, sx, my, slope, noise, n) in enumerate([(22, 7, 28, 0.9, 5, 520), (58, 9, 62, 1.0, 6, 480), (92, 8, 34, -0.9, 6, 300)]):
        for _ in range(n):
            x = rng.gauss(mx, sx)
            y = my + slope * (x - mx) + rng.gauss(0, noise)
            if 1 < x < 119 and 1 < y < 99:
                out.append(dict(id=f"AC-{1000 + len(out)}", x=x, y=y, seg=seg, sx=rng.uniform(40, 80), sy=rng.uniform(30, 70), delay=rng.random()))
    return out


def stats(points):
    n = len(points)
    if not n:
        return dict(n=0, mx=None, my=None, r=None, slope=None, icpt=None)
    mx, my = sum(p["x"] for p in points) / n, sum(p["y"] for p in points) / n
    sxx = sum((p["x"] - mx) ** 2 for p in points)
    syy = sum((p["y"] - my) ** 2 for p in points)
    sxy = sum((p["x"] - mx) * (p["y"] - my) for p in points)
    r = sxy / math.sqrt(sxx * syy) if n > 2 and sxx and syy else None
    slope = sxy / sxx if n > 2 and sxx else None
    return dict(n=n, mx=mx, my=my, r=r, slope=slope, icpt=my - slope * mx if slope is not None else None)


def nice_ticks(lo, hi, want=5):
    span = max(hi - lo, 1e-9)
    raw = span / want
    mag = 10 ** math.floor(math.log10(raw))
    step = next((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), 10 * mag)
    first = math.ceil(lo / step) * step
    out = []
    while first <= hi + step * 1e-6:
        out.append(round(first, 6))
        first += step
    return out, step


def fmt(v, step):
    return f"{v:.0f}" if step >= 1 else f"{v:.1f}"


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class InputParser:
    """Reads can split reports anywhere; consume complete events in wire order."""
    def __init__(self):
        self.buffer = b""

    def feed(self, raw):
        self.buffer += raw
        events = []
        while self.buffer:
            if self.buffer[0] != 27:
                byte, self.buffer = self.buffer[0], self.buffer[1:]
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
                match = MOUSE.fullmatch(report)
                if match:
                    events.append(("mouse", (int(match[1]), int(match[2]) - 1, int(match[3]) - 1, match[4] == b"m")))
            elif self.buffer[1:2] == b"O":
                if len(self.buffer) < 3:
                    break
                self.buffer = self.buffer[3:]
            else:
                self.buffer = self.buffer[2:]
        return events


class Screen:
    def __init__(self):
        self.cols, self.rows = shutil.get_terminal_size((120, 38))
        self.cells = [[(" ", None, None)] * self.cols for _ in range(self.rows)]

    def put(self, row, col, text, fg=INK, bg=None):
        if 0 <= row < self.rows:
            for i, ch in enumerate(text):
                if 0 <= col + i < self.cols:
                    self.cells[row][col + i] = (ch, fg, bg if bg is not None else self.cells[row][col + i][2])

    def flush(self):
        out, last = ["\x1b[?2026h\x1b[H"], (None, None)
        for r, row in enumerate(self.cells):
            for ch, fg, bg in row:
                if (fg, bg) != last:
                    code = "0"
                    if fg:
                        code += ";38;2;%d;%d;%d" % fg
                    if bg:
                        code += ";48;2;%d;%d;%d" % bg
                    out.append(f"\x1b[{code}m")
                    last = (fg, bg)
                out.append(ch)
            if r < self.rows - 1:
                out.append("\r\n")
        out.append("\x1b[0m\x1b[?2026l")
        os.write(1, "".join(out).encode())


class App:
    def __init__(self):
        self.pts = make_accounts()
        self.all_stats = stats(self.pts)
        self.xlim, self.ylim = X_FULL, Y_FULL
        self.stack, self.anim = [], None
        self.box, self.press, self.grab, self.dragging = None, None, None, False
        self.hover, self.pin, self.hidden = None, None, set()
        self.rows_map, self.seg_rows = {}, {}
        self.point_cells = set()
        self.usable = False
        self.start = time.time()

    def layout(self, s):
        self.left, self.top = 8, 6
        self.w = max(2, s.cols - self.left - 8 - SIDE)
        self.h = max(2, s.rows - self.top - 5)
        self.usable = s.cols >= MIN_COLS and s.rows >= MIN_ROWS
        return self.usable

    def col_of(self, x):
        return self.left + (x - self.xlim[0]) / (self.xlim[1] - self.xlim[0]) * (self.w - 1)

    def row_of(self, y):
        return self.top + (1 - (y - self.ylim[0]) / (self.ylim[1] - self.ylim[0])) * (self.h - 1)

    def x_at(self, col):
        return self.xlim[0] + (col - self.left) / (self.w - 1) * (self.xlim[1] - self.xlim[0])

    def y_at(self, row):
        return self.ylim[1] - (row - self.top) / (self.h - 1) * (self.ylim[1] - self.ylim[0])

    def visible(self):
        """All enabled accounts, including any outside the viewport."""
        return [p for p in self.pts if p["seg"] not in self.hidden]

    def in_view(self, points=None):
        return [p for p in (self.visible() if points is None else points)
                if p["seg"] not in self.hidden and self.xlim[0] <= p["x"] <= self.xlim[1]
                and self.ylim[0] <= p["y"] <= self.ylim[1]]

    def chosen(self):
        if not self.box:
            return None
        x0, x1, y0, y1 = self.box
        return [p for p in self.visible() if x0 <= p["x"] <= x1 and y0 <= p["y"] <= y1]

    def inside_plot(self, col, row):
        return self.usable and self.left <= col < self.left + self.w and self.top <= row < self.top + self.h

    def inside_box(self, col, row):
        if not self.box:
            return False
        x0, x1, y0, y1 = self.box
        return self.col_of(x0) <= col <= self.col_of(x1) and self.row_of(y1) <= row <= self.row_of(y0)

    def nearest(self, col, row):
        best, score = None, 3.5
        for p in self.in_view():
            d = math.hypot(self.col_of(p["x"]) - col, (self.row_of(p["y"]) - row) * 2)
            if d < score:
                best, score = p, d
        return best

    def zoom_to(self, target):
        if any(not all(math.isfinite(v) for v in axis) or axis[1] <= axis[0] for axis in target):
            return False
        self.anim = (self.xlim, self.ylim, target[0], target[1], time.time(), 0.55)
        return True

    def step_anim(self):
        if self.anim:
            x0, y0, x1, y1, t0, dur = self.anim
            f = ease((time.time() - t0) / dur)
            self.xlim = tuple(a + (b - a) * f for a, b in zip(x0, x1))
            self.ylim = tuple(a + (b - a) * f for a, b in zip(y0, y1))
            if f >= 1:
                self.anim = None

    def busy(self):
        return self.anim is not None or time.time() - self.start < 1.6

    def draw(self):
        s = Screen()
        usable = self.layout(s)
        self.step_anim()
        if not usable:
            self.rows_map, self.seg_rows = {}, {}
            self.press, self.grab, self.dragging = None, None, False
            s.put(0, 0, f"q: quit | Resize terminal to at least {MIN_COLS}x{MIN_ROWS}.", MUTED)
            s.flush()
            return
        chosen = self.chosen()
        keep = set(p["id"] for p in chosen) if chosen is not None else None
        intro = time.time() - self.start
        self.chrome(s, chosen)
        self.marginals(s, chosen)
        if self.box:
            self.brush_bg(s)
        self.scatter(s, keep, intro)
        if chosen and len(chosen) > 2:
            self.trend(s, chosen)
        if self.box:
            self.brush_frame(s, chosen)
        self.side(s, chosen)
        self.tooltip(s)
        s.flush()

    def chrome(self, s, chosen):
        s.put(0, 1, "Accounts: monthly spend against usage", INK)
        s.put(0, s.cols - 15, "synthetic data", MUTED)
        path = "All accounts" + "".join(" > zoomed" for _ in self.stack)
        counts = f"{len(self.in_view()):,} shown / {len(self.visible()):,} enabled"
        width = self.left + self.w + 7
        header = f"{path}   {counts}"
        s.put(1, 1, header if len(header) <= width else counts, MUTED)
        if chosen is not None:
            offscreen = len(chosen) - len(self.in_view(chosen))
            label = f"{len(chosen):,} selected (all enabled)"
            if offscreen:
                label = f"{len(chosen):,} selected / {offscreen:,} offscreen"
            s.put(2, 1, label, MUTED)
        s.put(5, 1, "usage", MUTED)
        xt, xs = nice_ticks(*self.xlim, want=max(4, self.w // 12))
        yt, ys = nice_ticks(*self.ylim, want=max(4, self.h // 5))
        for v in yt:
            r = round(self.row_of(v))
            s.put(r, 1, fmt(v, ys).rjust(5), MUTED)
            s.put(r, self.left - 1, "┤", FAINT)
        for r in range(self.top, self.top + self.h):
            if s.cells[r][self.left - 1][0] == " ":
                s.put(r, self.left - 1, "│", FAINT)
        s.put(self.top + self.h, self.left - 1, "└" + "─" * self.w, FAINT)
        for v in xt:
            c = round(self.col_of(v))
            s.put(self.top + self.h, c, "┬", FAINT)
            label = fmt(v, xs)
            s.put(self.top + self.h + 1, c - len(label) // 2, label, MUTED)
        s.put(self.top + self.h + 2, self.left + self.w // 2 - 9, "monthly spend ($k)", MUTED)
        s.put(s.rows - 2, 1, "gray: in view · yellow: selected · white: trend", MUTED)
        s.put(s.rows - 1, 1, "drag brush/move  hover inspect  row pin  z zoom b back x clear  1-3 hide q quit", MUTED)

    def marginal_bins(self, chosen):
        hx, hxs = [0] * self.w, [0] * self.w
        hy, hys = [0] * self.h, [0] * self.h
        for points, xs, ys in ((self.in_view(), hx, hy), (self.in_view(chosen or []), hxs, hys)):
            for p in points:
                xs[round(self.col_of(p["x"])) - self.left] += 1
                ys[round(self.row_of(p["y"])) - self.top] += 1
        return hx, hxs, hy, hys

    def marginals(self, s, chosen):
        """Both histograms use only in-view accounts; yellow is the selection."""
        rows, base = 3, self.top - 1
        hx, hxs, hy, hys = self.marginal_bins(chosen)
        top, right = max(hx + [1]), max(hy + [1])
        for c in range(self.w):
            for count, rgb in ((hx[c], GHOST), (hxs[c], GOOD)):
                units = count / top * rows * 8
                for k in range(rows):
                    level = max(0, min(8, int(units - k * 8)))
                    if level:
                        s.put(base - k, self.left + c, UP[level], rgb)
        edge = self.left + self.w + 1
        for r in range(self.h):
            for count, rgb in ((hy[r], GHOST), (hys[r], GOOD)):
                units = count / right * 6 * 8
                for k in range(6):
                    level = max(0, min(8, int(units - k * 8)))
                    if level:
                        s.put(self.top + r, edge + k, RIGHT[level], rgb)

    def brush_bounds(self):
        x0, x1, y0, y1 = self.box
        return round(self.col_of(x0)), round(self.col_of(x1)), round(self.row_of(y1)), round(self.row_of(y0))

    def brush_bg(self, s):
        c0, c1, r0, r1 = self.brush_bounds()
        # Border glyphs run through cell centers; shading border cells spills outside.
        for r in range(max(self.top, r0 + 1), min(self.top + self.h, r1)):
            for c in range(max(self.left, c0 + 1), min(self.left + self.w, c1)):
                ch, fg, _ = s.cells[r][c]
                s.cells[r][c] = (ch, fg, BRUSH_BG)

    def scatter(self, s, keep, intro):
        cells = {}
        for p in self.visible():
            f = ease((intro - p["delay"] * 0.6) / 0.8)
            x = p["sx"] + (p["x"] - p["sx"]) * f
            y = p["sy"] + (p["y"] - p["sy"]) * f
            px = (x - self.xlim[0]) / (self.xlim[1] - self.xlim[0]) * (self.w * 2 - 1)
            py = (1 - (y - self.ylim[0]) / (self.ylim[1] - self.ylim[0])) * (self.h * 4 - 1)
            ix, iy = round(px), round(py)
            if 0 <= ix < self.w * 2 and 0 <= iy < self.h * 4:
                cell = cells.setdefault((iy // 4, ix // 2), [0, [0, 0, 0], [0, 0, 0]])
                bit = BITS[iy % 4][ix % 2]
                if keep is None or p["id"] in keep:
                    cell[1][p["seg"]] |= bit
                    cell[2][p["seg"]] += 1
                else:
                    cell[0] |= bit
        self.point_cells = set(cells)
        for (r, c), (context, masks, counts) in cells.items():
            if any(counts):
                winner = counts.index(max(counts))
                bits, rgb = masks[winner], SEGMENTS[winner][1]
            else:
                bits, rgb = context, GHOST
            s.put(self.top + r, self.left + c, chr(0x2800 + bits), rgb)

    def trend(self, s, chosen):
        st = stats(chosen)
        if st["slope"] is None:
            return
        x0, x1 = min(p["x"] for p in chosen), max(p["x"] for p in chosen)
        x0, x1 = max(x0, self.xlim[0]), min(x1, self.xlim[1])
        if x0 > x1:
            return
        steps = max(2, int((self.col_of(x1) - self.col_of(x0)) * 2))
        masks = {}
        for i in range(steps + 1):
            x = x0 + (x1 - x0) * i / steps
            y = st["icpt"] + st["slope"] * x
            px = (x - self.xlim[0]) / (self.xlim[1] - self.xlim[0]) * (self.w * 2 - 1)
            py = (1 - (y - self.ylim[0]) / (self.ylim[1] - self.ylim[0])) * (self.h * 4 - 1)
            ix, iy = round(px), round(py)
            if 0 <= ix < self.w * 2 and 0 <= iy < self.h * 4:
                cell = (iy // 4, ix // 2)
                if cell not in self.point_cells and cell[1] % 3 == 0:
                    masks[cell] = masks.get(cell, 0) | BITS[iy % 4][ix % 2]
        for (r, c), bits in masks.items():
            s.put(self.top + r, self.left + c, chr(0x2800 + bits), INK)

    def brush_frame(self, s, chosen):
        c0, c1, r0, r1 = self.brush_bounds()
        clipc = lambda c: self.left <= c < self.left + self.w
        clipr = lambda r: self.top <= r < self.top + self.h
        for c in range(max(c0, self.left), min(c1, self.left + self.w - 1) + 1):
            if clipr(r0):
                s.put(r0, c, "─", GOOD)
            if clipr(r1):
                s.put(r1, c, "─", GOOD)
        for r in range(max(r0, self.top), min(r1, self.top + self.h - 1) + 1):
            if clipc(c0):
                s.put(r, c0, "│", GOOD)
            if clipc(c1):
                s.put(r, c1, "│", GOOD)
        for r, c, ch in ((r0, c0, "┌"), (r0, c1, "┐"), (r1, c0, "└"), (r1, c1, "┘")):
            if clipr(r) and clipc(c):
                s.put(r, c, ch, GOOD)
        label = f" {len(chosen or []):,} selected "
        start, stop = max(self.left, c0 + 1), min(c1, self.left + self.w)
        if clipr(r0) and stop - start >= len(label):
            s.put(r0, start, label, (20, 20, 20), GOOD)

    def side(self, s, chosen):
        col = self.left + self.w + 9
        width = s.cols - col - 1
        all_st = stats(self.visible())
        sel = stats(chosen or [])
        s.put(1, col, "Selection".ljust(14) + "selected".rjust(9) + "enabled".rjust(9), MUTED)
        s.put(2, col, "─" * min(width, 32), FAINT)
        def row(r, name, a, b, emph=False):
            s.put(r, col, name.ljust(14), MUTED)
            s.put(r, col + 14, a.rjust(9), GOOD if emph else INK)
            s.put(r, col + 23, b.rjust(11), MUTED)
        dash = "-"
        val = lambda v, f: dash if v is None else f.format(v)
        total = all_st["n"] or 1
        row(3, "accounts", f"{sel['n']:,}" if chosen is not None else dash, f"{all_st['n']:,}", True)
        row(4, "share", f"{sel['n'] / total:.0%}" if chosen is not None else dash, "100%")
        row(5, "mean spend $k", val(sel["mx"], "{:.1f}"), val(all_st["mx"], "{:.1f}"))
        row(6, "mean usage", val(sel["my"], "{:.1f}"), val(all_st["my"], "{:.1f}"))
        row(7, "correlation r", val(sel["r"], "{:+.2f}"), val(all_st["r"], "{:+.2f}"), True)
        row(8, "trend slope", val(sel["slope"], "{:+.2f}"), val(all_st["slope"], "{:+.2f}"))
        s.put(10, col, "Segments", MUTED)
        self.seg_rows = {}
        pool = chosen if chosen is not None else self.visible()
        most = max([sum(p["seg"] == g for p in pool) for g in range(3)] + [1])
        for g, (name, rgb) in enumerate(SEGMENTS):
            r = 11 + g
            self.seg_rows[r] = g
            n = sum(p["seg"] == g for p in pool)
            off = g in self.hidden
            s.put(r, col, f"{g + 1} " + name.ljust(11), MUTED if off else rgb)
            units = n / most * 13 * 8
            s.put(r, col + 14, "█" * int(units // 8) + RIGHT[int(units % 8)].strip(), MUTED if off else rgb)
            s.put(r, col + 28, "off" if off else f"{n:>4}", MUTED)
        s.put(15, col, "Top accounts by spend", MUTED)
        self.rows_map = {}
        hover_row = self.hover[1] if self.hover and self.hover[0] >= col else None
        top = sorted(pool, key=lambda p: -p["x"])[:max(1, s.rows - 19)]
        for i, p in enumerate(top):
            r = 16 + i
            self.rows_map[r] = p
            bg = ROW_BG if r == hover_row or p is self.pin else None
            s.put(r, col, " " * min(width, 32), MUTED, bg)
            s.put(r, col, p["id"], INK, bg)
            s.put(r, col + 9, f"${p['x']:5.1f}k", SEGMENTS[p["seg"]][1], bg)
            s.put(r, col + 18, f"usage {p['y']:4.1f}", MUTED, bg)
        if chosen is not None and not chosen:
            s.put(16, col, "nothing inside the brush", MUTED)

    def tooltip(self, s):
        marks = []
        pin = self.pin if self.pin and self.pin["seg"] not in self.hidden else None
        if pin:
            marks.append((pin, GOOD))
        target = None
        if self.hover and self.inside_plot(*self.hover) and not self.dragging:
            target = self.nearest(*self.hover)
        if target:
            marks.append((target, INK))
        for p, rgb in marks:
            c, r = round(self.col_of(p["x"])), round(self.row_of(p["y"]))
            if self.inside_plot(c, r):
                s.put(r, c, "◉", rgb)
        show = target or pin
        if not show:
            return
        c, r = round(self.col_of(show["x"])), round(self.row_of(show["y"]))
        if not self.inside_plot(c, r):
            return
        name, rgb = SEGMENTS[show["seg"]]
        lines = [(f" {show['id']}  {name} ", rgb), (f" spend  ${show['x']:.1f}k ", INK), (f" usage  {show['y']:.1f} hrs ", INK)]
        w = max(len(t) for t, _ in lines)
        col = c + 2 if c + 2 + w < self.left + self.w else c - w - 1
        row = r - 3 if r - 3 >= self.top else r + 1
        for i, (t, fg) in enumerate(lines):
            s.put(row + i, col, t.ljust(w), fg, TIP_BG)

    def mouse(self, b, col, row, up):
        if not self.usable:
            return
        wheel = b & 64
        if wheel:
            return
        motion = b & 32
        held = (b & 3) != 3
        if not up and not motion and held:
            self.dragging = False
            if row in self.rows_map and col >= self.left + self.w + 9:
                self.pin = None if self.pin is self.rows_map[row] else self.rows_map[row]
                self.press = None
            elif row in self.seg_rows and col >= self.left + self.w + 9:
                self.hidden.symmetric_difference_update({self.seg_rows[row]})
                self.press = None
            elif self.inside_plot(col, row):
                self.press = (col, row)
                self.grab = self.box if self.inside_box(col, row) else None
            else:
                self.press = None
        elif up:
            if self.press and not self.dragging and self.grab is None:
                self.box = None
            self.press, self.grab, self.dragging = None, None, False
        elif motion and held and self.press:
            self.dragging = True
            if self.grab:
                dx, dy = self.x_at(col) - self.x_at(self.press[0]), self.y_at(row) - self.y_at(self.press[1])
                x0, x1, y0, y1 = self.grab
                self.box = (x0 + dx, x1 + dx, y0 + dy, y1 + dy)
            else:
                cc = max(self.left, min(self.left + self.w - 1, col))
                rr = max(self.top, min(self.top + self.h - 1, row))
                ax, ay = self.x_at(self.press[0]), self.y_at(self.press[1])
                bx, by = self.x_at(cc), self.y_at(rr)
                self.box = (min(ax, bx), max(ax, bx), min(ay, by), max(ay, by))
        self.hover = (col, row)

    def key(self, k):
        if k == "z" and self.box:
            x0, x1, y0, y1 = self.box
            mx, my = (x1 - x0) * 0.08, (y1 - y0) * 0.08
            if self.zoom_to(((x0 - mx, x1 + mx), (y0 - my, y1 + my))):
                self.stack.append((self.xlim, self.ylim))
        elif k == "b" and self.stack:
            if self.zoom_to(self.stack[-1]):
                self.stack.pop()
        elif k == "x":
            self.box, self.pin = None, None
        elif k in ("1", "2", "3"):
            self.hidden.symmetric_difference_update({int(k) - 1})


def main():
    app, parser, saved = App(), InputParser(), termios.tcgetattr(0)
    dirty = True
    def resized(signum, frame):
        nonlocal dirty
        dirty = True
    old_resize = signal.signal(signal.SIGWINCH, resized)
    try:
        tty.setcbreak(0)
        os.write(1, b"\x1b[?1049h\x1b[?25l\x1b[?1003h\x1b[?1006h\x1b[2J")
        while True:
            if dirty or app.busy():
                dirty = False
                app.draw()
            wait = 1 / 30 if app.busy() else 0.05
            if not select.select([0], [], [], wait)[0]:
                continue
            raw = os.read(0, 4096)
            if not raw:
                return
            dirty = True
            for kind, value in parser.feed(raw):
                if kind == "mouse":
                    app.mouse(*value)
                elif value == "q":
                    return
                else:
                    app.key(value)
    finally:
        signal.signal(signal.SIGWINCH, old_resize)
        try:
            os.write(1, b"\x1b[?1006l\x1b[?1003l\x1b[?25h\x1b[?1049l")
        finally:
            termios.tcsetattr(0, termios.TCSADRAIN, saved)


if __name__ == "__main__":
    main()
