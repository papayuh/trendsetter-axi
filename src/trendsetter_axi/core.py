"""Renderer core: drawing primitives (pixel coords, y down) -> plain text grid.

Shims (mpl.py for matplotlib figures, svg.py for SVG source) only translate their source into calls on
Canvas. Everything about how a chart looks in text lives here, so this file is the
part that would move to Rust.
"""
import re
import numpy as np
from .cells import clusters, pack_entries, slice_cells, truncate, width, wrap

HEIGHT = ' ▁▂▃▄▅▆▇█'   # eighth-height block glyphs

# viridis ramps for heatmap cells
V5 = [(68, 1, 84), (59, 82, 139), (33, 145, 140), (94, 201, 98), (253, 231, 37)]
V9 = [(68, 1, 84), (72, 40, 120), (62, 74, 137), (49, 104, 142), (38, 130, 142), (31, 158, 137), (53, 183, 121), (109, 205, 89), (253, 231, 37)]


def rel_lum(c):
    f = lambda v: (v / 255 / 12.92) if v / 255 <= 0.03928 else ((v / 255 + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def ramp_rgb(k, L):
    st = V5 if L == 5 else V9
    if L in (5, 9): return st[k]
    t = k / max(1, L - 1) * 8; i = min(int(t), 7); f = t - i
    return tuple(round(a + (b - a) * f) for a, b in zip(V9[i], V9[i + 1]))

BITS = np.array([[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]])
GLYPHS = "●×▲◆■+○△"          # per-series keys for markers, line stamps, legend handles
SHADES = "█▓▒░▚▞"            # per-series fills
RAMP = "█▓▒░· "               # continuous fills/images: dark -> light
HEAT8 = ("··", "░░", "░▒", "▒▒", "▒▓", "▓▓", "▓█", "██")   # 8-level heat (text route opt-in): two glyphs alternate across a cell
HEAT = "░▒▓█"                 # heat grids (imshow/pcolormesh/colorbar): low -> high; blank is reserved for missing
U, D, L, R = 1, 2, 4, 8
BOX = {U | D: "│", L | R: "─", D | R: "┌", D | L: "┐", U | R: "└", U | L: "┘", U | D | R: "├",
       U | D | L: "┤", L | R | D: "┬", L | R | U: "┴", U | D | L | R: "┼", U: "│", D: "│", L: "─", R: "─"}


def lum(c): return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
def neutral(c): return max(c[:3]) - min(c[:3]) < 0.12 or max(c[:3]) < 0.15
def background(c): return neutral(c) and lum(c) > 0.8


SUP = dict(zip("0123456789-+−", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺⁻"))
def sup(t): return "".join(SUP[ch] for ch in t) if all(ch in SUP for ch in t) else "^" + t


def clean_text(s):
    if s.count("$") >= 2 and s.count("$") % 2 == 0:  # mathtext: drop the markup, keep the words
        s = re.sub(r"\\?mathdefault", "", s)
        s = re.sub(r"\^\{([^}]*)\}|\^(.)", lambda m: sup(m.group(1) if m.group(1) is not None else m.group(2)), s)
        for a, b in [("\\times", "×"), ("\\cdot", "·"), ("\\alpha", "α"), ("\\beta", "β"), ("\\mu", "µ"),
                     ("\\sigma", "σ"), ("\\pm", "±"), ("\\degree", "°"), ("_{", "_"), ("\\", "")]:
            s = s.replace(a, b)
        s = s.replace("$", "").replace("{", "").replace("}", "")
    return s.replace("−", "-")


class Canvas:
    def __init__(self, w_px, h_px, cols, max_rows=60):
        if not isinstance(cols, int) or cols < 1:
            raise ValueError("cols must be a positive integer")
        self.w, self.h, self.cols = w_px, h_px, cols
        self.cw = w_px / cols; self.ch = 2 * self.cw
        self.rows = max(4, min(max_rows, round(h_px / self.ch)))
        self.ch = h_px / self.rows
        self.panel = None         # lum of a mid-grey panel background: lighter neutral lines are gridlines
        self.dark = False         # a dark neutral page fill was seen: dark gridlines/panels are background
        self.series = {}          # rgb tuple -> index, in order of first appearance
        self.kind = {}            # series index -> set of {"line","mark","fill"}
        self.strokes, self.marks, self.fills, self.texts, self.side = [], [], [], [], []
        self.legend_marks, self.cont, self.tiny = [], [], []
        self.candles = []         # explicitly tagged text-only OHLC bodies/wicks; never marker/stamp heuristics
        self.heat = []            # (row, col, level 0..3) text cells of a heat grid
        self.rules = []           # (series, a, b, clip): short horizontal collection lines (violin medians, hlines) drawn as one glyph style
        self.ytop = False         # distribution charts: y title on the title row, not a footer
        self.ramp = None          # (label, 5 bin edges as text): one-line colour key replacing a colorbar
        self.stamp = True         # False: series are named on the chart itself, so no glyph stamps chop their lines
        self.fam = {}             # rgb key -> "box" | "dot": monotone line drawn as a glyph staircase instead of braille (text route, ecdf)
        self.levels = 4           # heat levels: 4 (HEAT) or 8 (HEAT8)
        self.hbars = False        # fills are horizontal bars: whole rows with gaps, eighth-width ends
        self.solidfills = False   # opt-in stacks: whole-cell shades, no partial-height segment glyphs
        self.meta = dict(dropped=[], truncated=[], clipped=[], shifted=[], offgrid=0, placed=[], inked=[])

    @property
    def ninks(self): return len(self.fills) + len(self.marks) + len(self.legend_marks) + len(self.tiny)   # callers diff this to see whether a fill drew anything

    # ---- primitives -------------------------------------------------------------
    def _sid(self, rgb, kind):
        key = tuple(round(float(v), 2) for v in rgb[:3])
        i = self.series.setdefault(key, len(self.series))
        if kind: self.kind.setdefault(i, set()).add(kind)   # kind=None: legend handle, not a data mark
        return i

    def bg(self, c): return neutral(c) and (lum(c) < 0.4 if self.dark else lum(c) > 0.8)

    def stroke(self, polylines, rgb, dashes=None, clip=None, legend=False, rule=False):
        if self.bg(rgb) or not polylines: return
        pts = np.concatenate([np.asarray(p, float) for p in polylines if len(p)])
        if legend:  # one short key per handle; frames and long strokes are not keys
            (x0, y0), (x1, y1) = pts.min(0), pts.max(0)
            if x1 - x0 > 5 * self.cw or y1 - y0 > 2 * self.ch: return
            return self.legend_marks.append((pts.mean(0), None if neutral(rgb) else self._sid(rgb, None), "line"))
        (x0, y0), (x1, y1) = pts.min(0), pts.max(0)
        p0 = np.asarray(polylines[0], float)
        if x1 - x0 <= self.cw * 1.2 and y1 - y0 <= self.ch * 0.6 and len(p0) > 3 and np.hypot(*(p0[0] - p0[-1])) < 1e-3:
            return self.marker([pts.mean(0)], rgb, clip)   # hollow marker (open circle etc.)
        if neutral(rgb):  # dark gray/black: axis-aligned -> box drawing, else plain dots
            grid = lum(rgb) > 0.6 and not self.dark or self.panel is not None and lum(rgb) > self.panel   # light gray axis-aligned strokes (or lighter than the panel) are gridlines: skip
            for p in polylines:
                p = np.asarray(p, float)
                if len(p) < 2: continue
                for a, b in zip(p, p[1:]):
                    if abs(a[1] - b[1]) < 0.5 and abs(a[0] - b[0]) >= 2 * self.cw:
                        if not grid: self.strokes.append(("h", a, b, clip, lum(rgb) < 0.35))
                    elif abs(a[0] - b[0]) < 0.5 and abs(a[1] - b[1]) >= self.ch:
                        if not grid: self.strokes.append(("v", a, b, clip, lum(rgb) < 0.35))
                    elif max(abs(a - b)) >= self.cw: self.strokes.append(("dots", -1, [np.array([a, b])], dashes, clip))
            return
        p0 = np.asarray(polylines[0], float)
        if (rule or x1 - x0 < 0.6 * self.w) and len(polylines) == 1 and len(p0) == 2 and abs(p0[0, 1] - p0[1, 1]) < 0.5 and abs(p0[0, 0] - p0[1, 0]) >= 2 * self.cw:   # a short flat ax.plot (violin median drawn as a line) is the same rule
            return self.rules.append((self._sid(rgb, "line"), p0[0], p0[1], clip))   # violin median / cap: always `─`, never a braille pattern that depends on the sub-row
        self.strokes.append(("dots", self._sid(rgb, "line"), [np.asarray(p, float) for p in polylines], dashes, clip))

    def fill(self, polygons, rgb, clip=None, legend=False, continuous=False, alpha=1.0):
        polygons = [np.asarray(p, float) for p in polygons if len(p) > 2]
        if not polygons or self.bg(rgb) and not continuous: return
        pts = np.concatenate(polygons)
        (x0, y0), (x1, y1) = pts.min(0), pts.max(0)
        if not continuous and neutral(rgb) and lum(rgb) < 0.35 and (x1 - x0) * (y1 - y0) >= 0.4 * self.w * self.h:
            self.dark = True; return   # page/panel background of a dark theme
        if not continuous and neutral(rgb) and lum(rgb) <= 0.8 and (x1 - x0) * (y1 - y0) >= 0.4 * self.w * self.h:
            self.panel = lum(rgb); return   # mid-grey panel (plotnine theme_dark/gray): background, not data
        if legend:
            return self.legend_marks.append((pts.mean(0), self._sid(rgb, None), "fill"))
        if continuous: return self.cont.append((polygons, rgb, clip))
        if x1 - x0 <= self.cw * 1.2 and y1 - y0 <= self.ch * 0.6:  # tiny closed shape = marker
            return self.tiny.append((polygons, rgb, clip))   # marker unless it is one cell of a tiled heatmap (see render)
        self.fills.append((polygons, self._sid(rgb, "fill"), clip, alpha < 0.95, (x1 - x0) * (y1 - y0)))

    def candle(self, polygons, rgb, clip, kind):
        points = np.concatenate([p for p in polygons if len(p)])
        if not len(points): return
        self.candles.append((points.min(0), points.max(0), self._sid(rgb, 'line'), clip, kind))

    def marker(self, points, rgb, clip=None, legend=False):
        if self.bg(rgb): return
        sid = -1 if neutral(rgb) else self._sid(rgb, None if legend else "mark")
        if legend: return self.legend_marks.append((np.mean(points, 0), sid, "mark"))
        self.marks.append((np.asarray(points, float).reshape(-1, 2), sid, clip))

    def image(self, x0, y0, x1, y1, rgb, alpha=None):  # rgb: (h, w, 3) floats 0..1, row 0 at top
        if alpha is not None and (alpha < 0.5).mean() > 0.5:
            return self._overlay(x0, y0, x1, y1, rgb, alpha)
        ys = np.linspace(y0, y1, rgb.shape[0] + 1); xs = np.linspace(x0, x1, rgb.shape[1] + 1)
        r0, r1 = self._row(y0), self._row(y1 - 1e-6); c0, c1 = self._col(x0), self._col(x1 - 1e-6)
        for r in range(max(r0, 0), min(r1, self.rows - 1) + 1):
            for c in range(max(c0, 0), min(c1, self.cols - 1) + 1):
                yi = np.clip(np.searchsorted(ys, (r + .5) * self.ch) - 1, 0, rgb.shape[0] - 1)
                xi = np.clip(np.searchsorted(xs, (c + .5) * self.cw) - 1, 0, rgb.shape[1] - 1)
                self.cont.append(([np.array([[c * self.cw, r * self.ch], [(c + 1) * self.cw, r * self.ch],
                                             [(c + 1) * self.cw, (r + 1) * self.ch], [c * self.cw, (r + 1) * self.ch]])],
                                  rgb[yi, xi], None))

    def heat_grid(self, xs, ys, t, clip=None):
        """t: (h, w) levels in 0..1, NaN = missing (stays blank); xs (w+1) / ys (h+1) ascending px edges, row 0 at top.
        One text cell per data cell or the nearest data cell when a text cell spans several."""
        xs, ys, t = (np.asarray(a, float) for a in (xs, ys, t))
        ci = np.searchsorted(xs, (np.arange(self.cols) + .5) * self.cw) - 1
        ri = np.searchsorted(ys, (np.arange(self.rows) + .5) * self.ch) - 1
        for r in np.nonzero((ri >= 0) & (ri < t.shape[0]))[0]:
            for c in np.nonzero((ci >= 0) & (ci < t.shape[1]))[0]:
                if clip is not None and not (clip[0] <= (c + .5) * self.cw <= clip[2] and clip[1] <= (r + .5) * self.ch <= clip[3]): continue
                if (ci == ci[c]).sum() >= 4 and (c + 1 == self.cols or ci[c + 1] != ci[c]): continue   # wide cells keep a blank seam column: neighbours read as separate blocks
                v = t[ri[r], ci[c]]
                if np.isfinite(v): self.heat.append((int(r), int(c), int(min(self.levels - 1, max(0, v) * self.levels))))

    @staticmethod
    def _rect(polys):
        """(x0, y0, x1, y1) of a single axis-aligned rectangle, else None."""
        if len(polys) != 1 or len(polys[0]) not in (4, 5): return None
        p = polys[0][:4]
        if len(set(np.round(p[:, 0], 1))) != 2 or len(set(np.round(p[:, 1], 1))) != 2: return None
        return p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()

    def _snap_hbars(self, rects):
        """Horizontal bars (shared left edge, one per row slot): whole rows with a gap row between neighbours."""
        x0 = np.array([r[0] for _, r in rects]); cy = sorted({round((r[1] + r[3]) / 2 / self.ch, 2) for _, r in rects})
        if len(rects) < 2 or np.ptp(x0) > 1.0 or len(cy) < 2: return False
        p = float(np.median(np.diff(cy))); wid = float(np.median([(r[3] - r[1]) / self.ch for _, r in rects]))
        if p < 1.5 or wid > 0.95 * p: return False
        h = max(1, min(int(wid), int(p) - 1))
        for i, r in rects:
            r0 = int(round((r[1] + r[3]) / 2 / self.ch - h / 2)); f = list(self.fills[i])
            f[0] = [np.array([[r[0], r0 * self.ch], [r[2], r0 * self.ch], [r[2], (r0 + h) * self.ch], [r[0], (r0 + h) * self.ch]])]
            self.fills[i] = tuple(f)
        return True

    def _snap_bars(self):
        """Bars: whole columns with a gap column between neighbours (fused runs read as one slab)."""
        rects = [(i, self._rect(f[0])) for i, f in enumerate(self.fills)]
        rects = [(i, r) for i, r in rects if r]
        if self._snap_hbars(rects): self.hbars = True; return
        cx = sorted({round((r[0] + r[2]) / 2 / self.cw, 2) for _, r in rects})
        if len(cx) < 2: return
        p = float(np.median(np.diff(cx)))
        wid = float(np.median([(r[2] - r[0]) / self.cw for _, r in rects]))
        if p < 1.5: return                          # dense: keep raw spans
        if wid > 0.9 * p:                           # touching (histogram): neighbours share one whole-column edge, so no blank column splits contiguous bins
            ev = sorted(v for _, r in rects for v in (r[0], r[2])); cl = [[ev[0]]]
            for v in ev[1:]: cl[-1].append(v) if v - cl[-1][-1] < .5 * self.cw else cl.append([v])
            snap = lambda v: round(np.mean(next(c for c in cl if any(abs(v - u) < 1e-9 for u in c))) / self.cw) * self.cw
            for i, r in rects:
                f = list(self.fills[i]); a, b = snap(r[0]), snap(r[2])
                if b <= a: b = a + self.cw
                f[0] = [np.array([[a, r[1]], [b, r[1]], [b, r[3]], [a, r[3]]])]; self.fills[i] = tuple(f)
            return
        w = max(1, min(int(wid), int(p) - 1))
        for i, r in rects:
            c0 = int(round((r[0] + r[2]) / 2 / self.cw - w / 2))
            f = list(self.fills[i])
            f[0] = [np.array([[c0 * self.cw, r[1]], [(c0 + w) * self.cw, r[1]], [(c0 + w) * self.cw, r[3]], [c0 * self.cw, r[3]]])]
            self.fills[i] = tuple(f)

    def _overlay(self, x0, y0, x1, y1, rgb, alpha):
        """Mostly-transparent raster = drawn marks: sample at dot resolution, key by color."""
        sx, sy = 2 / self.cw, 4 / self.ch
        r0, r1, c0, c1 = int(y0 * sy), int(np.ceil(y1 * sy)), int(x0 * sx), int(np.ceil(x1 * sx))
        h, w = alpha.shape
        by_color = {}
        for r in range(max(r0, 0), min(r1, self.rows * 4)):
            yi = min(h - 1, int(((r + .5) / sy - y0) / (y1 - y0) * h))
            for c in range(max(c0, 0), min(c1, self.cols * 2)):
                xi = min(w - 1, int(((c + .5) / sx - x0) / (x1 - x0) * w))
                # any opaque pixel inside this dot's footprint counts
                ya, yb = max(0, yi - h // (r1 - r0) // 2), yi + max(1, h // (r1 - r0)) // 2 + 1
                xa, xb = max(0, xi - w // (c1 - c0) // 2), xi + max(1, w // (c1 - c0)) // 2 + 1
                a = alpha[ya:yb, xa:xb]
                if a.max() < 0.5: continue
                k = np.unravel_index(a.argmax(), a.shape)
                col = rgb[ya + k[0], xa + k[1]]
                if background(col): continue
                by_color.setdefault(tuple(np.round(col, 1)), []).append((r, c, col))
        total = sum(len(v) for v in by_color.values())
        for key, v in sorted(by_color.items(), key=lambda kv: -len(kv[1])):
            if len(v) < 0.02 * total: continue  # antialias fringe
            col = np.mean([x[2] for x in v], 0)
            sid = -1 if neutral(col) else self._sid(col, "line")
            self.strokes.append(("pts", sid, np.array([(r, c) for r, c, _ in v]), None, None))

    def text(self, x, y, s, ha="left", va="baseline", angle=0, role="other"):
        s = clean_text(str(s)).strip("\n")
        s = re.sub(r"[ \t]*\n[ \t]*\n", "\n", re.sub(r"[ \t]*\b\w*\s*[=:]\s*-?(?:nan|NaN|NAN)\b|(?<![\w.])-?(?:nan|NaN|NAN)(?![\w.])", "", s)).strip()   # missing renders blank, never "nan" ("med=nan" goes whole)
        if not s.strip(): return
        self.texts.append((x, y, s, ha, va, angle % 360, role))

    # ---- raster helpers ---------------------------------------------------------
    def _col(self, x): return int(np.floor(x / self.cw))
    def _row(self, y): return int(np.floor(y / self.ch))

    def _clipmask(self, clip, shape, scale):
        if clip is None: return None
        x0, y0, x1, y1 = clip
        m = np.zeros(shape, bool)
        m[max(0, int(y0 * scale[1])):max(0, int(np.ceil(y1 * scale[1]))), max(0, int(x0 * scale[0])):max(0, int(np.ceil(x1 * scale[0])))] = True
        return m

    def _visible_segments(self, p, clip):
        """Liang-Barsky viewport clipping before any interpolation allocation.

        Keep each original segment separate: NaNs never become connecting edges.
        Return original lengths/offsets too, so invisible geometry advances dashes.
        """
        p = np.asarray(p, float)
        a, b = p[:-1], p[1:]
        valid = np.isfinite(a).all(1) & np.isfinite(b).all(1)
        a, b = a[valid], b[valid]
        delta = b - a
        lengths = np.hypot(delta[:, 0], delta[:, 1])
        distances = np.r_[0., np.cumsum(lengths)[:-1]] if len(a) else lengths
        low, high = np.array([0., 0.]), np.array([self.w, self.h])
        if clip is not None:
            low, high = np.maximum(low, clip[:2]), np.minimum(high, clip[2:])
        t0, t1 = np.zeros(len(a)), np.ones(len(a))
        valid = np.isfinite(delta).all(1) & (low <= high).all()
        for axis in (0, 1):
            moving = delta[:, axis] != 0
            near, far = np.full(len(a), -np.inf), np.full(len(a), np.inf)
            np.divide(low[axis] - a[:, axis], delta[:, axis], out=near, where=moving)
            np.divide(high[axis] - a[:, axis], delta[:, axis], out=far, where=moving)
            valid &= moving | ((a[:, axis] >= low[axis]) & (a[:, axis] <= high[axis]))
            t0 = np.maximum(t0, np.minimum(near, far))
            t1 = np.minimum(t1, np.maximum(near, far))
        valid &= t0 <= t1
        a, delta, t0, t1 = a[valid], delta[valid], t0[valid], t1[valid]
        start = np.clip(a + delta * t0[:, None], low, high)
        end = np.clip(a + delta * t1[:, None], low, high)
        return start, end, lengths[valid], distances[valid], t0, t1

    def _line_dots(self, p, dashes, clip=None, staircase=False):
        """Rasterize in bounded batches, reducing to occupied terminal dots.

        At most max(2*cols, 4*rows)+2 samples per visible segment, at most
        1024 segments per batch, at most 8*rows*cols returned dots. Every input
        endpoint/extremum is sampled; missing-data gaps are never bridged.
        """
        sx, sy = 2 / self.cw, (2 if staircase else 4) / self.ch
        scale = np.array([sx, sy])
        a, b, lengths, distances, t0, t1 = self._visible_segments(p, clip)
        pat = None
        if dashes and dashes[1] is not None and len(dashes[1]) and sum(dashes[1]) > 0:
            pat = np.asarray(dashes[1], float)
            pat = pat * max(1, self.cw * 0.6 / max(pat.min(), 1e-9) / 2)
        nr, nc = self.rows * (2 if staircase else 4), self.cols * 2
        seen = np.zeros(nr * nc, bool)
        out = []
        for first in range(0, len(a), 1024):
            last = first + 1024
            start, delta = a[first:last], b[first:last] - a[first:last]
            span = np.abs(delta) * scale
            n = np.minimum(span.max(1).astype(int) + 2, max(nr, nc) + 2)
            ids = np.repeat(np.arange(len(n)), n)
            offset = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
            t = offset * (1. / (n[ids] - 1))
            q = start[ids] + delta[ids] * t[:, None]
            rc = np.floor(q[:, ::-1] * scale[::-1]).astype(int)
            if pat is not None:
                phase = (distances[first:last][ids] +
                         (t0[first:last][ids] + t * (t1[first:last] - t0[first:last])[ids]) * lengths[first:last][ids]) % pat.sum()
                rc = rc[np.searchsorted(np.cumsum(pat), phase, side="right") % 2 == 0]
            elif not staircase:
                # Existing steep-run treatment: ink the cell's other dot column.
                steep = (span[:, 1] >= 3) & (span[:, 1] > 2 * span[:, 0]) & (2 * span[:, 0] >= 1)
                rc = np.concatenate([rc, rc[steep[ids]] ^ [0, 1]])
            ok = (rc[:, 0] >= 0) & (rc[:, 0] < nr) & (rc[:, 1] >= 0) & (rc[:, 1] < nc)
            rc = rc[ok]
            keys = rc[:, 0] * nc + rc[:, 1]
            _, keep = np.unique(keys, return_index=True)
            keep.sort()  # first occurrence order for line stamps
            keep = keep[~seen[keys[keep]]]
            seen[keys[keep]] = True
            out.append(rc[keep])
        return np.concatenate(out) if out else np.zeros((0, 2), int)

    def _poly_mask(self, polygons, nr, nc, sx, sy):
        """Even-odd scanline fill at sample centers; returns bool [nr, nc]."""
        m = np.zeros((nr, nc), bool)
        ys = (np.arange(nr) + 0.5) / sy
        xs = (np.arange(nc) + 0.5) / sx
        for poly in polygons:
            p = poly[np.isfinite(poly).all(1)]
            if len(p) < 3: continue
            a, b = p, np.roll(p, -1, 0)
            lo, hi = p[:, 1].min(), p[:, 1].max()
            for r in np.nonzero((ys >= lo) & (ys <= hi))[0]:
                y = ys[r]
                cross = (a[:, 1] <= y) != (b[:, 1] <= y)
                if not cross.any(): continue
                xa = a[cross, 0] + (y - a[cross, 1]) * (b[cross, 0] - a[cross, 0]) / (b[cross, 1] - a[cross, 1])
                xa.sort()
                for x0, x1 in zip(xa[::2], xa[1::2]):
                    m[r] ^= (xs >= x0) & (xs < x1)
        return m

    def _serialize_rows(self, cell, sid_at, under, continuation, inv, heatrgb, color):
        """Serialize cell-aligned rows; isolated for profiling separately from ink."""
        rows = []
        for r in range(self.rows):
            parts = []
            for c in range(self.cols):
                if continuation[r, c]: continue
                ch = cell[r, c] or " "
                o = sid_at[r, c]
                if color and (r, c) in heatrgb:
                    (a, b, d), (x, y, z) = heatrgb[r, c]
                    ch = f"\x1b[48;2;{a};{b};{d};38;2;{x};{y};{z}m{ch}\x1b[0m"
                elif color and o >= 0 and ch != " ":
                    rr, gg, bb = (int(v * 255) for v in inv[o])
                    bgc = "\x1b[48;2;%d;%d;%dm" % tuple(int(v * 255) for v in inv[under[r, c]]) if under[r, c] >= 0 else ""
                    ch = f"{bgc}\x1b[38;2;{rr};{gg};{bb}m{ch}\x1b[0m"
                parts.append(ch)
            rows.append("".join(parts).rstrip())
        return rows

    # ---- compose ----------------------------------------------------------------
    def render(self, color=False):
        if self.tiny:   # many tiny fills in >8 colours tile a heatmap: continuous ramp, not glyph markers
            rect = lambda ps: len(ps) == 1 and len(ps[0]) in (4, 5) and all(np.ptp(np.round(ps[0][:4, k], 1)) > 0 and len(set(np.round(ps[0][:4, k], 1))) == 2 for k in (0, 1))   # axis-aligned quad: a heatmap cell, not a circle/diamond marker
            if len(self.tiny) > 50 and len({tuple(np.round(c[:3], 2)) for _, c, _ in self.tiny}) > 8 and sum(rect(p) for p, _, _ in self.tiny) > 0.9 * len(self.tiny): self.cont += self.tiny
            else:
                for polys, rgb, clip in self.tiny: self.marker([np.concatenate(polys).mean(0)], rgb, clip)
            self.tiny = []
        R_, C_ = self.rows, self.cols
        sx, sy = 2 / self.cw, 4 / self.ch
        nser = len(self.series)
        multi = nser > 1
        dots = np.full((R_ * 4, C_ * 2), -2, int)       # -2 none, -1 neutral, else series id
        cell = np.full((R_, C_), "", object)
        sid_at = np.full((R_, C_), -2, int)                # series for color output
        box = np.zeros((R_, C_), int)
        frame = np.zeros((R_, C_), bool)                  # dark axis/spine lines: beat fills
        fill = np.full((R_, C_), -1, int)
        shade = np.full((R_, C_), "", object)

        def put_dots(rc, sid, clip):
            if not len(rc): return
            ok = (rc[:, 0] >= 0) & (rc[:, 0] < R_ * 4) & (rc[:, 1] >= 0) & (rc[:, 1] < C_ * 2)
            self.meta["offgrid"] += int((~ok).sum() > 0)
            rc = rc[ok]
            if clip is not None:
                cm = self._clipmask(clip, dots.shape, (sx, sy)); rc = rc[cm[rc[:, 0], rc[:, 1]]]
            dots[rc[:, 0], rc[:, 1]] = sid

        # fills (painter's order), continuous fills by luminance
        fill_ids = [i for i in range(nser) if "fill" in self.kind.get(i, ())]
        if len(fill_ids) > 8 and sum(f[3] for f in self.fills) < len(self.fills) / 2:  # a color scale, not categories (translucent fills are overlapping areas): shade by luminance
            inv0 = {v: k for k, v in self.series.items()}
            self.cont += [(f[0], inv0[f[1]], f[2]) for f in self.fills]
            self.fills = []; fill_ids = []
        many = len(fill_ids) > 4   # many stacked series: solid fills, patterns only separate a handful
        flat = lambda ps: not self._rect(ps) and sum(int((np.abs(p[:, 1] - p[:, 1].max()) < 1e-6).sum()) for p in ps) >= 8   # curve standing on a flat baseline (fill_between)
        ridge = sum(flat(f[0]) for f in self.fills) >= 3   # ridgeline: solid fills standing on row baselines, painter's order
        shade_of = {sid: (SHADES[k % len(SHADES)] if (1 < len(fill_ids) <= 4 or self.solidfills) and not ridge else "█") for k, sid in enumerate(fill_ids)}
        under = np.full((R_, C_), -1, int)                # series behind a partial block (colour output backs it)
        self._snap_bars()
        bases = sorted({round(max(p[:, 1].max() for p in f[0]), 1) for f in self.fills if flat(f[0])}) if ridge else []
        pitch = float(np.diff(bases).min()) if len(bases) > 1 else self.ch
        # ridgeline: each ridge lives strictly in its own row band (1 row, or the 2+ rows a sparse figure gives it); never ink in another year's row
        band = (1 if pitch < 1.9 * self.ch else int(pitch / self.ch + .1)) * self.ch
        hts = [max(p[:, 1].max() for p in f[0]) - min(p[:, 1].min() for p in f[0]) for f in self.fills if flat(f[0])] if ridge else [0]
        hmax, hmin = max(hts), min(hts)
        natural = .95 * band <= hmax <= band * 1.001 and hmin >= .6 * hmax   # data already fills the band evenly: draw true proportions, no caption
        rscaled = ridge and not natural and hmax / max(hmin, 1e-9) > 1.05   # per-ridge scale really changed relative heights
        alt, altsid, fills = {}, set(), self.fills   # ridgeline: consecutive same-colour ridges alternate fill (colour: darker shade; plain: ▓) so neighbours separate
        if ridge:
            seq = sorted((f for f in self.fills if flat(f[0])), key=lambda f: max(p[:, 1].max() for p in f[0])); prev, flip, ids = None, 0, []
            for f in seq:
                flip = flip ^ 1 if f[1] == prev else 0; prev = f[1]; ids.append(flip)
                if flip: alt[id(f)] = len(self.series) + len(alt); shade_of[alt[id(f)]] = "█"
            altsid = set(alt.values()); fills = [(f[0], alt.get(id(f), f[1])) + tuple(f[2:]) for f in self.fills]
            seqs = [(f[1], alt.get(id(f), f[1]), fl) for f, fl in zip(seq, ids)]
        lums = [lum(rgb) for _, rgb, _ in self.cont]
        lo, hi = (min(lums), max(lums)) if lums else (0, 1)
        ramp = lambda l: RAMP[min(len(RAMP) - 2, int(((l - lo) / (hi - lo) if hi - lo > 0.05 else l) * (len(RAMP) - 1)))]  # stretch to the full ramp; never blank: blank means "no data"
        for (polys, rgb, clip), l in zip(self.cont, lums):
            m = self._poly_mask(polys, R_, C_, 1 / self.cw, 1 / self.ch)
            if clip is not None: m &= self._clipmask(clip, m.shape, (1 / self.cw, 1 / self.ch))
            shade[m] = ramp(l)
        # opaque fills in painter's order; translucent ones biggest-first so overlaps keep both shapes
        for polys, sid, clip, _, _ in sorted(fills, key=lambda f: (f[3] and not many and not ridge, -f[4] if f[3] and not many and not ridge else 0, max(p[:, 1].max() for p in f[0]) if ridge else 0)):   # ridge: top row first, so a lower ridge's peak overlaps upward onto it
            if not self.solidfills and shade_of[sid] == "█" and self.hbars and self._rect(polys):   # eighth-width ends: the bar's last column is a partial block
                q = self._poly_mask(polys, R_, C_ * 8, 8 / self.cw, 1 / self.ch)
                if clip is not None: q &= self._clipmask(clip, q.shape, (8 / self.cw, 1 / self.ch))
                n = q.reshape(R_, C_, 8).sum(2)
                for r, c in np.argwhere(n > 0):
                    under[r, c] = fill[r, c] if n[r, c] < 8 and fill[r, c] >= 0 and fill[r, c] != sid else -1
                    fill[r, c] = sid; shade[r, c] = " ▏▎▍▌▋▊▉█"[n[r, c]]
                continue
            if not self.solidfills and shade_of[sid] == "█" and (self._rect(polys) or ridge):   # eighth-height blocks; ridges stand on the row of their label
                if ridge and flat(polys):
                    yb = max(p[:, 1].max() for p in polys)
                    top = min(p[:, 1].min() for p in polys)
                    k = (1.0 if natural else band / (yb - top)) if yb - top > 1e-9 else 1.0   # own peak = the band's full height
                    dy = (np.floor(yb / self.ch) + 1) * self.ch - yb
                    polys = [np.column_stack([p[:, 0], yb + (p[:, 1] - yb) * k + dy]) for p in polys]
                if ridge:   # column height = area under the column (mean of the curve over its x span, 4 samples per column), not a point sample at its centre
                    q = self._poly_mask(polys, R_ * 8, C_ * 4, 4 / self.cw, 8 / self.ch)
                    if clip is not None: q &= self._clipmask(clip, q.shape, (4 / self.cw, 8 / self.ch))
                    qf = q.reshape(R_, 8, C_, 4).sum(3) / 4; n = np.rint(qf.sum(1)).astype(int)
                    for r, c in np.argwhere(n > 0):
                        k = n[r, c]
                        g = ("▓" if not color and sid in altsid else "█") if k == 8 else "▀" if k >= 4 and qf[r, :k, c].sum() > qf[r, 8 - k:, c].sum() else HEIGHT[k]
                        if fill[r, c] == sid and "▁▂▃▄▅▆▇█▀".find(shade[r, c]) >= "▁▂▃▄▅▆▇█▀".find(g) >= 0 > -2: continue
                        under[r, c] = fill[r, c] if g != "█" and fill[r, c] >= 0 and fill[r, c] != sid else -1
                        fill[r, c] = sid; shade[r, c] = g
                    continue
                q = self._poly_mask(polys, R_ * 8, C_, 1 / self.cw, 8 / self.ch)
                rc = self._rect(polys)
                if rc and rc[3] - rc[1] > 1e-6 and rc[3] - rc[1] < self.ch / 8:   # a nonzero bar under one eighth-block must still show one (honesty: never drop a nonzero bin)
                    cs = np.arange(C_); cs = cs[(cs + .5) * self.cw >= rc[0]]; cs = cs[(cs + .5) * self.cw <= rc[2]]
                    if not cs.size: cs = np.array([min(C_ - 1, max(0, int((rc[0] + rc[2]) / 2 / self.cw)))])
                    q[min(R_ * 8 - 1, max(0, int((rc[1] + 1e-6) / (self.ch / 8)))), cs] = True
                if clip is not None: q &= self._clipmask(clip, q.shape, (1 / self.cw, 8 / self.ch))
                q = q.reshape(R_, 8, C_); n = q.sum(1)
                for r, c in np.argwhere(n > 0):
                    k, col = n[r, c], q[r, :, c]
                    g = ("▓" if not color and sid in altsid else "█") if k == 8 else HEIGHT[k] if col[8 - k:].all() else "▀" if col[:k].all() and k >= 4 else "█" if k >= 4 else ""
                    if not g: continue
                    if ridge and fill[r, c] == sid and "▁▂▃▄▅▆▇█▀".find(shade[r, c]) >= "▁▂▃▄▅▆▇█▀".find(g) >= 0 > -2: continue   # same colour already stands taller here: a shorter block must not cut a hole
                    under[r, c] = fill[r, c] if g != "█" and fill[r, c] >= 0 and fill[r, c] != sid else -1
                    fill[r, c] = sid; shade[r, c] = g
                continue
            if self.solidfills and self._rect(polys):
                # One shared boundary quantization for adjacent stack segments.
                # Coverage >= 1/2 rounds both edges outward and can add >1 cell.
                hit = self._poly_mask(polys, R_, C_, 1 / self.cw, 1 / self.ch)
                if clip is not None: hit &= self._clipmask(clip, hit.shape, (1 / self.cw, 1 / self.ch))
                fill[hit] = sid; shade[hit] = shade_of[sid]
                continue
            m = self._poly_mask(polys, R_ * 4, C_ * 2, sx, sy)
            if clip is not None: m &= self._clipmask(clip, m.shape, (sx, sy))
            q = m.reshape(R_, 4, C_, 2)
            cov = q.sum((1, 3))
            hit = cov >= 4
            if not self.solidfills and shade_of[sid] == "█" and len(fill_ids) == 1:  # a lone solid fill gets half-block edges (2x resolution); stacked series keep straight edges
                top, bot = q[:, :2].sum((1, 3)), q[:, 2:].sum((1, 3))
                lef, rig = q[:, :, :, 0].sum(1), q[:, :, :, 1].sum(1)
                half = {"▀": (top >= 3) & (bot <= 1), "▄": (bot >= 3) & (top <= 1), "▌": (lef >= 3) & (rig <= 1), "▐": (rig >= 3) & (lef <= 1)}
                anyhalf = np.zeros_like(hit)
                for g, hm in half.items():
                    hm &= ~(cov >= 6) & ~anyhalf; anyhalf |= hm; fill[hm] = sid; shade[hm] = g
                hit = (cov >= 6) | (hit & ~anyhalf)
            # very thin shapes (narrow bars) still deserve one column of ink
            if not hit.any() and cov.any(): hit = cov >= max(1, cov.max() // 2)
            fill[hit] = sid; shade[hit] = shade_of[sid]

        # strokes
        stamps = {}
        famsid = {self.series[k]: v for k, v in self.fam.items() if k in self.series}; famruns = {}
        boxes = [(min(p[:, 0].min() for p in f[0]) - 1, min(p[:, 1].min() for p in f[0]) - 1, max(p[:, 0].max() for p in f[0]) + 1, max(p[:, 1].max() for p in f[0]) + 1) for f in self.fills] if ridge else []
        inside = lambda ps: any(all(b[0] <= q[:, 0].min() and q[:, 0].max() <= b[2] and b[1] <= q[:, 1].min() and q[:, 1].max() <= b[3] for q in ps) for b in boxes)
        if ridge:   # a ridge's own outline (or baseline rule) sits on its fill: braille/box cells would punch the body hollow, the fill is the shape
            self.strokes = [s for s in self.strokes if not (s[0] == "dots" and inside([np.asarray(p, float) for p in s[2]])) and not (s[0] == "h" and any(b[1] <= s[1][1] <= b[3] for b in boxes))]   # axhline baselines too
            self.marks = [m for m in self.marks if not inside([m[0]])]
        for s in self.strokes:
            if s[0] == "pts":
                put_dots(s[2], s[1], None)
                if s[1] >= 0: stamps.setdefault(s[1], []).append(s[2][np.lexsort((s[2][:, 0], s[2][:, 1]))])
            elif s[0] == "dots":
                _, sid, polys, dashes, clip = s
                if sid in famsid: famruns.setdefault(sid, []).append((polys, clip)); continue
                if ridge and sid == -1: continue   # a ridge's black outline would float above its scaled-down block
                for p in polys:
                    rc = self._line_dots(p, dashes, clip)
                    put_dots(rc, sid, clip)
                    if sid >= 0 and len(rc) > 8: stamps.setdefault(sid, []).append(rc)
            else:
                kind, a, b, clip, dark = s
                dark = dark and not ridge and (kind == "h" or np.hypot(*(b - a)) >= 0.25 * self.h)   # dark h-lines (spines, medians) beat fills; only spine-length v-lines do: a short whisker must not hide the box it hangs off
                if clip is not None:
                    a = np.clip(a, clip[:2], clip[2:]); b = np.clip(b, clip[:2], clip[2:])
                if kind == "h":
                    r = self._row(a[1]); c0, c1 = sorted((self._col(a[0]), self._col(b[0] - 1e-6)))
                    if not 0 <= r < R_: continue
                    c0, c1 = max(c0, 0), min(c1, C_ - 1)
                    for c in range(c0, c1 + 1): box[r, c] |= (L if c > c0 else 0) | (R if c < c1 else 0) | (L | R if c0 == c1 else 0); frame[r, c] |= dark
                else:
                    c = self._col(a[0]); r0, r1 = sorted((self._row(a[1]), self._row(b[1] - 1e-6)))
                    if not 0 <= c < C_: continue
                    r0, r1 = max(r0, 0), min(r1, R_ - 1)
                    for r in range(r0, r1 + 1): box[r, c] |= (U if r > r0 else 0) | (D if r < r1 else 0) | (U | D if r0 == r1 else 0); frame[r, c] |= dark

        # markers: braille dots when only one series, glyph per series otherwise
        glyph = lambda sid: GLYPHS[sid % len(GLYPHS)] if sid < len(GLYPHS) else chr(ord("a") + sid % 26)
        marks = {}
        npts = {}
        for pts, sid, _ in self.marks: npts[sid] = npts.get(sid, 0) + len(pts)
        for pts, sid, clip in self.marks:
            for x, y in pts:
                if not (np.isfinite(x) and np.isfinite(y)): continue
                if clip is not None and not (clip[0] - 1 <= x <= clip[2] + 1 and clip[1] - 1 <= y <= clip[3] + 1): continue
                if (multi and sid >= 0) or npts[sid] <= 300:  # sparse marks get a glyph, dense scatter stays braille
                    r, c = self._row(y), self._col(x)
                    if 0 <= r < R_ and 0 <= c < C_: marks[(r, c)] = glyph(sid) if multi and sid >= 0 else "•"
                    else: self.meta["offgrid"] += 1
                else:
                    put_dots(np.array([[int(y * sy), int(x * sx)]]), sid, None)

        # braille cells
        for r in range(R_):
            for c in range(C_):
                blk = dots[r * 4:r * 4 + 4, c * 2:c * 2 + 2]
                on = blk > -2
                if on.any():
                    cell[r, c] = "─" if shade[r, c] and on.any(1).sum() == 1 and 0 < c < C_ - 1 and shade[r, c - 1] and shade[r, c + 1] else chr(0x2800 + int(BITS[on].sum()))   # flat line (violin median) on a fill: a rule, not a dotted hole in the body
                    v = blk[on]; sid_at[r, c] = np.bincount(v + 2).argmax() - 2
                elif frame[r, c]: cell[r, c] = BOX[box[r, c]]
                elif shade[r, c]: cell[r, c] = shade[r, c]; sid_at[r, c] = fill[r, c]   # fills beat gridlines
                elif box[r, c]: cell[r, c] = BOX[box[r, c]]
        heatrgb = {}
        if self.heat:
            for r, c, lv in self.heat:
                if cell[r, c] == "" and not (box[r, c] or shade[r, c]):
                    cell[r, c] = HEAT8[lv][c % 2] if self.levels == 8 else HEAT[lv]; k = ramp_rgb(lv, self.levels)
                    heatrgb[r, c] = (k, k)   # solid fill: ink = bg, so the glyph never hatches the cell; the glyph still carries the level without colour

        for sid, a, b, clip in self.rules:   # median / cap rules: one glyph style, beats braille and fills
            if clip is not None: a = np.clip(a, clip[:2], clip[2:]); b = np.clip(b, clip[:2], clip[2:])
            r = self._row(a[1]); c0, c1 = sorted((self._col(a[0]), self._col(b[0] - 1e-6)))
            if 0 <= r < R_:
                for c in range(max(c0, 0), min(c1, C_ - 1) + 1):
                    if shade[r, c] and fill[r, c] >= 0 and fill[r, c] != sid: under[r, c] = fill[r, c]   # solid body behind the rule: no black cut-out
                    cell[r, c] = "─"; sid_at[r, c] = sid

        # line stamps so several line series stay apart in plain text
        if multi and self.stamp:
            for sid, runs in stamps.items():
                rc = np.concatenate(runs) // [4, 2]
                rc = rc[(rc[:, 0] >= 0) & (rc[:, 0] < R_) & (rc[:, 1] >= 0) & (rc[:, 1] < C_)]   # strokes may leave the grid
                if not len(rc): continue
                for f in (0.12, 0.45, 0.8):
                    for k in range(int(f * len(rc)), len(rc)):  # walk forward to a cell this series owns alone
                        r, c = rc[k]
                        blk = dots[r * 4:r * 4 + 4, c * 2:c * 2 + 2]
                        if (blk[blk > -2] == sid).all() and (r, c) not in marks and not shade[r, c]:   # not on a fill: there the line is a ─ rule
                            marks[(r, c)] = glyph(sid); break
                        if k - int(f * len(rc)) > len(rc) * .2: break
        for (r, c), g in marks.items(): cell[r, c] = g
        for kind in ("dot", "box"):   # glyph staircases (monotone curves): per text column the rows the curve spans, entry from the left at the bottom, exit right at the top
            for sid, runs in famruns.items():
                if famsid[sid] != kind: continue
                for polys, clip in runs:
                    span = {}
                    for p in polys:
                        for r_, c_ in self._line_dots(p, None, clip, staircase=True) // [2, 2]:
                            lo, hi = span.get(c_, (r_, r_))
                            span[c_] = (min(lo, r_), max(hi, r_))
                    prev = None
                    for c_ in sorted(span):
                        top, bot = span[c_]
                        if prev is not None and c_ == prev[0] + 1: bot = max(bot, prev[1])   # entry continues from the previous column's exit row
                        for r_ in range(top, bot + 1):
                            cell[r_, c_] = "∙" if kind == "dot" else ("─" if top == bot else "╭" if r_ == top else "╯" if r_ == bot else "│"); sid_at[r_, c_] = sid
                        prev = (c_, top)

        # OHLC geometry: true cell coordinates, wicks first, bodies opaque on top.
        # Filled caps cannot become tiny scatter markers or get hollowed by line stamps.
        for a, b, sid, clip, kind in sorted(self.candles, key=lambda c: c[4] != 'wick'):
            if clip is not None:
                if (b < clip[:2]).any() or (a > clip[2:]).any(): continue
                a, b = np.maximum(a, clip[:2]), np.minimum(b, clip[2:])
            center = self._col((a[0] + b[0]) / 2)
            # Symmetric cell widths: identical candles must not gain a column from x rounding.
            half = max(0, round(((b[0] - a[0]) / self.cw - 1) / 2))
            c0, c1 = max(0, center - half), min(C_ - 1, center + half)
            r0, r1 = max(0, self._row(a[1])), min(R_ - 1, self._row(b[1]))
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    if kind == 'wick': g = '│'
                    elif kind == 'filled': g = '█'
                    elif kind == 'flat': g = '─'
                    elif r0 == r1: g = '▯' if c == center else ' '
                    elif c0 == c1: g = '▯'
                    elif r == r0: g = '┌' if c == c0 else '┐' if c == c1 else '─'
                    elif r == r1: g = '└' if c == c0 else '┘' if c == c1 else '─'
                    else: g = '│' if c in (c0, c1) else ' '
                    cell[r, c] = g; sid_at[r, c] = sid

        # text: real characters; never overwrite earlier text
        taken = np.zeros((R_, C_), bool)
        continuation = np.zeros((R_, C_), bool)  # trailing cell of wide text
        placed = []
        order = sorted(self.texts, key=lambda t: {"title": 0, "label": 1, "legend": 2, "annot": 3}.get(t[6], 4))
        for x, y, s, ha, va, angle, role in order:
            if (60 < angle < 120 or 240 < angle < 300) and role != "tick":  # vertical axis title: footer
                self.side.append(("y2" if x > self.w / 2 else "y", s)); continue
            if angle and role == "tick":  # rotated tick labels: lay flat, hang below the anchor
                ha, va = "center", ("top" if y > self.h / 2 else "bottom")
            if role in ("title", "label", "annot", "other"):
                s = "\n".join(wrap(s, C_))
            lines = s.split("\n")
            n = len(lines)
            yc = {"top": y + n * self.ch / 2, "bottom": y - n * self.ch / 2, "baseline": y - n * self.ch / 2}.get(va, y)
            r0 = self._row(yc) - (n - 1) // 2 if va in ("center", "center_baseline") else self._row(yc - (n - 1) * self.ch / 2)
            if n > 1: r0 = int(np.clip(r0, 0, max(R_ - n, 0)))   # keep every line of a wrapped block on the grid
            for i, line in enumerate(lines):
                line = line.strip() if n > 1 else line
                r = r0 + i
                w = width(line)
                c = round(x / self.cw - (w / 2 if ha == "center" else w if ha == "right" else 0))
                if w > C_:
                    line = truncate(line, C_); w = width(line); self.meta["truncated"].append(s); self.meta["clipped"].append(s)
                if role in ("tick", "label") and (c < 0 or c + w > C_) and w > 4:  # cut, don't slide over the plot
                    keep = w + min(c, 0) - max(0, c + w - C_)
                    line = truncate(line, max(3, keep)); c = max(c, 0); w = width(line); self.meta["truncated"].append(s); self.meta["clipped"].append(s)
                if c < 0 or c + w > C_ or not 0 <= r < R_:
                    if not 0 <= r < R_ and abs(r - np.clip(r, 0, R_ - 1)) > 1:
                        self.meta["dropped"].append((role, s, "offgrid")); continue
                    self.meta["shifted"].append(s); c = int(np.clip(c, 0, C_ - w)); r = int(np.clip(r, 0, R_ - 1))
                if role == "tick" and 0 <= r + (d := 1 if y > self.h / 2 else -1) < R_ and any(cell[r, c + k] for k in range(w)) and all(cell[r, c + k] in ("", "─", "┬", "┴", "┼") for k in range(w)):
                    r += d; r0 += d   # label centre rounded onto the frame row: it belongs on the row outside the plot
                if role == "tick" and ha != "center":  # don't print over another subplot's ink: keep the anchor-side part that's free
                    ink = [k for k in range(w) if cell[r, c + k]]
                    if ink:
                        keep = w - ink[-1] - 1 if ha == "right" else ink[0]
                        if keep < 3: self.meta["dropped"].append((role, s, "ink")); continue
                        line = "…" + slice_cells(line, w - keep + 1) if ha == "right" else truncate(line, keep)
                        c += w - keep if ha == "right" else 0; w = width(line); self.meta["truncated"].append(s)
                busy = lambda r: taken[r, c:c + w].any() or (role == "tick" and taken[r, max(0, c - 1):c + w + 1].any())
                if ridge and role not in ("tick", "title", "label", "legend") and 0 <= r < R_ and ((fill[r, c:c + w] >= 0).any() or busy(r)):
                    # a note over a ridge body: slide it along its own row to the free run nearest its anchor (right margin first), then to a neighbour row; never drop it
                    r_own = r
                    pre = next((f"{t[2]}: " for t in self.texts if t[6] == "tick" and t[3] != "center" and t[0] < self.w / 2 and self._row(t[1]) == r), "")   # moved off its row: say whose it is
                    for r2 in (r, r - 1, r + 1):
                        if not 0 <= r2 < R_: continue
                        pw = w + (width(pre) if r2 != r else 0)
                        ok = [c2 for c2 in range(C_ - pw + 1) if not (fill[r2, c2:c2 + pw] >= 0).any() and not taken[r2, max(c2 - 1, 0):c2 + pw + 1].any() and not cell[r2, c2:c2 + pw].any()]
                        if ok:
                            c = min(ok, key=lambda c2: abs(c2 - c)); r = r2
                            if r2 != r_own: line = pre + line; w = pw
                            break
                    else: self.meta["inked"].append(s)
                if busy(r):
                    alt = [r2 for r2 in (r + 1, r - 1) if role != "tick" and 0 <= r2 < R_ and not busy(r2)]
                    if not alt:
                        self.meta["dropped"].append((role, s, "overlap")); continue
                    r = alt[0]; r0 += r - (r0 + i)
                taken[r, c:c + w] = True
                k = c
                for token, size in clusters(line):
                    if not size: continue
                    cell[r, k] = token
                    sid_at[r, k:k + size] = -2
                    if size > 1:
                        continuation[r, k + 1:k + size] = True
                    k += size
                self.meta["placed"].append((role, line)); placed.append((role, line, r, c, yc / self.ch + i - (n - 1) / 2))


        inv = {v: k for k, v in self.series.items()}
        if ridge: inv = {i: (lambda c, t: tuple(x + (1 - x) * t for x in c))(k, max(0, (.55 - lum(k)) / (1 - lum(k)))) for i, k in inv.items()}   # dark ridge ink reads on a dark terminal: lift to luminance .55, hue kept
        if ridge:   # alternate shade: x.6 drops a lifted (lum >= .55) colour by >= .22
            for k, (s0, s1, fl) in enumerate(seqs):
                if fl: inv[s1] = tuple(x * .6 for x in inv[s0])
            self.meta["ridge_rgb"] = [inv[s1] for _, s1, _ in seqs]
        # legend handles become the series key, snapped to the row of the nearest legend label
        labels = [(r, c, f) for role, line, r, c, f in placed if role == "legend"]
        hs = [((x, y), sid, kind, self._row(y), self._col(x)) for (x, y), sid, kind in self.legend_marks]
        pairs = sorted((abs(lf - h[0][1] / self.ch) + abs(lc - h[4]) / 4, i, j) for i, h in enumerate(hs) for j, (lr, lc, lf) in enumerate(labels) if abs(lf - h[0][1] / self.ch) <= 1 and lc >= h[4] - 2)  # -2: labels shifted left to fit the grid
        snap, used = {}, set()
        for _, i, j in pairs:  # greedy: nearest handle/label pairs first, each label once
            if i not in snap and j not in used: snap[i] = labels[j][:2]; used.add(j)
        keyed = {(hs[i][1], snap[i][0]) for i in snap}   # (series, row) already has its key
        for i, (_, sid, kind, r, c) in enumerate(hs):
            if i not in snap and any(abs(r - kr) <= 1 for ks, kr in keyed if ks == sid): continue   # area/violin legends draw fill + line for one entry
            if i in snap:
                r, lc = snap[i]; c = min(c, lc - 2) if lc - 2 >= 0 else c
            if not (0 <= r < R_ and 0 <= c < C_) or taken[r, c]: continue
            cell[r, c] = "─" if sid is None or sid < 0 else (shade_of.get(sid, "█") if kind == "fill" and sid in shade_of else ramp(lum(inv[sid])) if kind == "fill" and self.cont and sid in inv else glyph(sid) if multi else ("█" if kind == "fill" else "•" if kind == "mark" else "─"))
            sid_at[r, c] = sid if sid is not None else -2

        rows = self._serialize_rows(cell, sid_at, under, continuation, inv, heatrgb, color)
        while rows and not rows[-1].strip(): rows.pop()
        if self.heat: rows = [r for i, r in enumerate(rows) if r.strip() or not (i and not rows[i - 1].strip())]   # axes shrunk to the observed rows but the canvas did not: at most one blank row
        if self.ramp:   # colour key: ends carry the real values
            lab, edges = self.ramp   # one numeric range per bin
            NL = self.levels; gl = HEAT8 if NL == 8 else HEAT
            cellk = lambda i, g: "\x1b[48;2;%d;%d;%d;38;2;%sm%s\x1b[0m" % (*ramp_rgb(i, NL), "%d;%d;%d" % ramp_rgb(i, NL), g) if color else g
            ents = [f"{cellk(i, g)} {edges[i]}-{edges[i + 1]}" for i, g in enumerate(gl)]
            rows.extend(pack_entries(lab, ents, C_))
        while rows and not rows[0].strip(): rows.pop(0)
        if self.ytop and rows:   # y title sits on the title row's free left, over its axis
            for i, (side, s) in enumerate(self.side):
                if side == "y" and width(s) + 4 <= width(rows[0]) - width(rows[0].lstrip()): rows[0] = f"y: {s}" + slice_cells(rows[0], width(s) + 3); self.side.pop(i); break
        for side, s in self.side:
            rows.extend(wrap(f"{side}: {s}", C_))
        if rscaled: rows.extend(wrap("each ridge scaled to its own peak", C_)); self.meta["ridge_scaled"] = True
        while rows and not rows[0].strip(): rows.pop(0)
        while rows and not rows[-1].strip(): rows.pop()
        self.meta.update(cols=C_, rows=R_, n_series=nser,
                         series=[dict(id=i, rgb=k, kinds=sorted(self.kind.get(i, ())), key=(shade_of[i] if i in shade_of else glyph(i)) if multi else None) for k, i in self.series.items()],
                         side=self.side, cells=cell, n_cont=len(self.cont))
        return "\n".join(rows)
