"""A matplotlib RendererBase that forwards draw calls to core.Canvas.

Trick over mpl_ascii: the renderer's text metrics *are* character cells, and the
layout engine is pointed at this renderer, so matplotlib itself lays out ticks,
legends and margins for the terminal grid instead of us patching collisions later.
"""
import numpy as np
from matplotlib.backend_bases import RendererBase
from matplotlib.transforms import ScaledTranslation
from matplotlib import dates as mdates, ticker as mticker
from matplotlib.category import UnitData
from matplotlib.collections import Collection, PathCollection, PolyCollection, QuadMesh
from matplotlib.colors import to_hex, to_rgb
from matplotlib.lines import Line2D
from matplotlib.container import BarContainer
from matplotlib.image import _ImageBase
from .core import Canvas
from .cells import truncate, width, wrap

CW, CH = 7.0, 14.0  # one cell in points (dpi 72 => pixels)


class TextRenderer(RendererBase):
    def __init__(self, w, h, cols):
        super().__init__()
        self.w, self.h = w, h
        self.cv = Canvas(w, h, cols)
        self.groups = []
        self.wrapped = {}
        self.drawing = []   # (artist, role) being drawn, outermost first (see _hook)
        self.owners = []    # [artist, primitives queued] per top-level data artist drawn, for loss accounting

    # geometry / metrics
    def get_canvas_width_height(self): return self.w, self.h
    def points_to_pixels(self, p): return p
    def flipy(self): return False
    def get_text_width_height_descent(self, s, prop, ismath):
        from .core import clean_text
        lines = clean_text(s).split("\n")
        return max(width(l) for l in lines) * self.cv.cw, self.cv.ch / 1.2, 0
    def open_group(self, s, gid=None): self.groups.append(gid if gid and gid.startswith('trendsetter_axi-candle-') else s or "")
    def close_group(self, s):
        if self.groups: self.groups.pop()
    def option_image_nocomposite(self): return True

    def draw_artist(self, a, role, draw):
        own = role == "data" and not self.drawing
        if own: self.cv.owner, n = len(self.owners), self.cv.nprims; self.owners.append([a, 0])
        self.drawing.append((a, role))
        try: return draw(self)
        finally:
            self.drawing.pop()
            if own: self.owners[self.cv.owner][1] = self.cv.nprims - n; self.cv.owner = None

    @property
    def cur(self):
        """The image / mesh artist being drawn: its array carries the values the pixels lost."""
        a = self.drawing[-1][0] if self.drawing else None
        return a if isinstance(a, (_ImageBase, QuadMesh)) else None

    # helpers
    def _in(self, name): return any(name in g for g in self.groups)
    def _role(self):
        """What the artist being drawn is, from matplotlib's own artist tree; figure-level artists it does not list (plotnine legends) are placed by where they sit, else unknown."""
        return self.drawing[0][1] if self.drawing else "legend" if self._leg() else None
    def _leg(self, t=None):  # plotnine draws legends straight into the figure: no "legend" group, just figure-level artists
        g = self.groups
        return self._in("legend") or "axes" not in g and (g[-1:] in (["line2d"], ["patch"], ["collection"]) or t is not None and g[-1:] == ["text"] and t.get_position() == (0, 0))
    def _flip(self, pts): pts = np.asarray(pts, float).copy(); pts[:, 1] = self.h - pts[:, 1]; return pts
    def _clip(self, gc):
        cr = gc.get_clip_rectangle()
        if cr is None: return None
        x0, y0, x1, y1 = cr.extents
        return (x0, self.h - y1, x1, self.h - y0)
    def _rgb(self, c, alpha=None):
        c = np.asarray(c, float)
        a = c[3] if len(c) > 3 else 1.0
        if alpha is not None: a = alpha
        return c[:3], a

    def draw_path(self, gc, path, transform, rgbFace=None):
        if self._in("text") or self._in("annotation") or self._in("tick"): return  # Text bbox patch, gridlines: not data
        polys = [self._flip(p) for p in path.to_polygons(transform, closed_only=False)]
        clip, role = self._clip(gc), self._role()
        candle = next((g.removeprefix('trendsetter_axi-candle-') for g in self.groups if g.startswith('trendsetter_axi-candle-')), None)
        if candle:
            rgb, _ = self._rgb(rgbFace if rgbFace is not None else gc.get_rgb())
            self.cv.candle(polys, rgb, clip, candle)
            return
        filled = False
        if rgbFace is not None:
            rgb, a = self._rgb(rgbFace, gc.get_forced_alpha() and gc.get_alpha() or None)
            if a > 0.05:
                before = self.cv.ninks
                self.cv.fill(polys, rgb, clip, role=role, alpha=a)
                filled = self.cv.ninks > before
        if not filled and gc.get_linewidth() > 0:
            rgb, a = self._rgb(gc.get_rgb())
            if a > 0.05:
                self.cv.stroke(polys, rgb, gc.get_dashes(), clip, role=role, rule=self._in("LineCollection"))

    def draw_markers(self, gc, marker_path, marker_trans, path, trans, rgbFace=None):
        if self._in("axis") and not self._in("legend"): return  # tick marks: the frame says enough
        raw = [v[-2:] for v, _ in path.iter_segments(trans, simplify=False)]
        ext = marker_path.get_extents(marker_trans)
        if ext.width > self.cv.cw or ext.height > self.cv.ch / 2:
            # Collection fast path: a single big path (fill_between, bars) stamped at offsets
            from matplotlib.transforms import Affine2D
            for x, y in raw: self.draw_path(gc, marker_path, marker_trans + Affine2D().translate(x, y), rgbFace)
            return
        pts = self._flip(raw)
        c = rgbFace if rgbFace is not None and (len(rgbFace) < 4 or rgbFace[3] > 0.05) else gc.get_rgb()   # hollow marker: face (r,g,b,0), the edge carries the colour
        rgb, a = self._rgb(c)
        if a > 0.05 and len(pts): self.cv.marker(pts, rgb, self._clip(gc), role=self._role())

    def _levels(self, shape):
        """0..1 levels (NaN = missing) of the artist being drawn, or None when it has no scalar array of this shape."""
        a = self.cur
        try:
            if a is None or a.get_array() is None: return None
            if a.norm.vmin is None: a.autoscale_None()
            t = np.ma.filled(np.ma.masked_invalid(a.norm(np.ma.masked_invalid(a.get_array()))).astype(float), np.nan)
            if shape is None: shape = t.shape
            if t.size != int(np.prod(shape)): return None
            return t.reshape(shape)
        except Exception: return None

    def draw_quad_mesh(self, gc, master_transform, meshWidth, meshHeight, coordinates, offsets,
                       offsetTrans, facecolors, antialiased, edgecolors):
        xy = self._flip(master_transform.transform(np.asarray(coordinates).reshape(-1, 2)))
        xy = xy.reshape(meshHeight + 1, meshWidth + 1, 2)
        t = self._levels((meshHeight, meshWidth))
        xs, ys = xy[0, :, 0], xy[:, 0, 1]
        if t is not None and np.allclose(xy[..., 0], xs) and np.allclose(xy[..., 1], ys[:, None]) and (np.diff(xs) != 0).all() and (np.diff(ys) != 0).all():
            if xs[0] > xs[-1]: xs, t = xs[::-1], t[:, ::-1]
            if ys[0] > ys[-1]: ys, t = ys[::-1], t[::-1]
            return self.cv.heat_grid(xs, ys, t, self._clip(gc))   # regular mesh: a real cell grid, quantised levels
        fc = np.asarray(facecolors)
        clip = self._clip(gc)
        for i in range(meshHeight):
            for j in range(meshWidth):
                k = i * meshWidth + j
                c = fc[k % len(fc)] if len(fc) else (0, 0, 0, 1)
                if len(c) > 3 and c[3] < 0.05: continue
                quad = np.array([xy[i, j], xy[i, j + 1], xy[i + 1, j + 1], xy[i + 1, j]])
                self.cv.fill([quad], c[:3], clip, continuous=True)

    def draw_gouraud_triangles(self, gc, points, colors, transform):
        clip = self._clip(gc)
        for tri, col in zip(np.asarray(points, float), np.asarray(colors, float)):
            self.cv.fill([self._flip(transform.transform(tri))], col[:, :3].mean(0), clip, continuous=True)

    def draw_image(self, gc, x, y, im, transform=None):
        t = self._levels(None) if self.cur is not None and getattr(self.cur, "get_array", None) and np.ndim(self.cur.get_array()) == 2 else None
        grid = t is not None and self._image_grid(t)
        if grid:   # scalar image (imshow of numbers): masked cells stay blank, the rest take quantised levels
            return self.cv.heat_grid(*grid, self._clip(gc))   # edges of the whole array in pixels: cells outside the view or the clip are skipped, never squeezed into it
        im = np.asarray(im, float)[::-1] / 255.0   # mpl hands rows bottom-first
        rgb = im[..., :3] * im[..., 3:4] + (1 - im[..., 3:4])
        h, w = im.shape[:2]
        # im rows are top-first; (x, y) is the lower-left corner in y-up pixels
        self.cv.image(x, self.h - (y + h), x + w, self.h - y, rgb, im[..., 3])

    def _image_grid(self, t):
        """(xs, ys, t) for heat_grid: pixel edges of every cell of the image array through its own transform (extent, origin, zoom, inverted axes), ascending, row 0 at top. None when the image is not axis-aligned."""
        a = self.cur
        l, r, b, tp = a.get_extent(); n, m = t.shape
        tr = a.get_transform()
        xs = tr.transform(np.column_stack([np.linspace(l, r, m + 1), np.full(m + 1, b)]))
        ys = tr.transform(np.column_stack([np.full(n + 1, l), np.linspace(tp, b, n + 1) if getattr(a, "origin", "upper") == "upper" else np.linspace(b, tp, n + 1)]))
        if not (np.allclose(xs[:, 1], xs[0, 1]) and np.allclose(ys[:, 0], ys[0, 0])): return None
        xs, ys = xs[:, 0], self.h - ys[:, 1]
        if xs[0] > xs[-1]: xs, t = xs[::-1], t[:, ::-1]
        if ys[0] > ys[-1]: ys, t = ys[::-1], t[::-1]
        return xs, ys, t

    def draw_text(self, gc, x, y, s, prop, angle, ismath=False, mtext=None):
        role = (self.wrapped.get(s) if mtext is None and s in self.wrapped else  # mpl passes mtext only for single-line text: wrapped titles/labels arrive line by line without it
                "legend" if self._leg(mtext) else "tick" if self._in("axis") and not self._label(mtext) else
                "title" if mtext is not None and self._is_title(mtext) else
                "label" if self._label(mtext) else "annot" if self._in("annotation") else "other")
        if angle == 0 and mtext is not None and mtext.get_verticalalignment() in ("center", "center_baseline") and "\n" not in s:
            self.cv.text(x, self.h - mtext.get_transform().transform(mtext.get_unitless_position())[1], s, "left", "center", 0, role)   # baseline y is biased by the font metrics: a tick label on a row boundary would hop a row
        elif angle == 0 or mtext is None:
            self.cv.text(x, self.h - y, s, "left", "baseline", angle, role)
        else:  # rotated: use the unrotated anchor + alignment
            ax, ay = mtext.get_transform().transform(mtext.get_unitless_position())
            self.cv.text(ax, self.h - ay, s, mtext.get_horizontalalignment(), mtext.get_verticalalignment(), angle, role)

    def draw_tex(self, gc, x, y, s, prop, angle, *, mtext=None):
        self.draw_text(gc, x, y, s, prop, angle, False, mtext)

    def _label(self, t):
        return t is not None and any(t is a.xaxis.label or t is a.yaxis.label for a in t.figure.axes) if t is not None and t.figure else False
    def _is_title(self, t):
        f = t.figure
        return t is getattr(f, "_suptitle", None) or any(t in (a.title, a._left_title, a._right_title) for a in f.axes)


def _heat_axes(ax):
    return any(np.ndim(a.get_array()) == 2 for a in ax.images) or any(isinstance(c, QuadMesh) for c in ax.collections)


def _dist(ax):
    """Ridgeline (3+ fills on row baselines) or violin (a body symmetric about its position): a distribution, drawn without top/right borders."""
    polys = [c for c in ax.collections if isinstance(c, PolyCollection) and len(c.get_paths())]
    sym = lambda v: len(v) > 20 and np.ptp(v[:, 0]) > 0 and abs(v[:, 0].mean() - (v[:, 0].min() + v[:, 0].max()) / 2) < 1e-3 * np.ptp(v[:, 0])
    return bool(polys) and (bool(_rows_of(ax)) and len(polys) >= 3 or any(sym(np.asarray(c.get_paths()[0].vertices)) for c in polys))


def _roles(fig):
    """(artist, role) for every artist whose meaning matplotlib knows: what it is decides how it draws, never its colour."""
    yield fig.patch, "background"
    for lg in fig.legends: yield lg, "legend"
    for ax in fig.axes:
        yield ax.patch, "background"
        for a in (*ax.spines.values(), ax.xaxis, ax.yaxis): yield a, "axis"
        if ax.get_legend() is not None: yield ax.get_legend(), "legend"
        for a in (*ax.lines, *ax.collections, *ax.patches, *ax.images): yield a, "data"
        for a in ax.texts: yield a, "annotation"


def _hook(fig):
    """Tell the renderer which artist is drawing and what it is (images/meshes: their array has the values, the pixels only have colours).
    Returns the hooked artists for _unhook."""
    hooked = list(_roles(fig))
    for a, role in hooked: a.draw = lambda r, a=a, role=role, f=a.draw: r.draw_artist(a, role, f)
    return [a for a, _ in hooked]


def _unhook(artists):
    for a in artists: a.__dict__.pop("draw", None)


def _fixed(ax, axis):
    """(first, second) limit of `axis` the caller (or a library such as plotnine) set: a side that differs from what autoscaling gives.
    When autoscaling is off and neither differs, the side on a sticky edge (set_ylim(bottom=0) on bars) or else both (set_ylim(ax.get_ylim())).
    ponytail: set_ylim(ax.get_ylim()) on bars pads the free top; record set_*lim calls if that ever matters."""
    get, setlim = (ax.get_xlim, ax.set_xlim) if axis == "x" else (ax.get_ylim, ax.set_ylim)
    if getattr(ax, f"get_autoscale{axis}_on")(): return False, False
    lim = get()
    ax.autoscale(True, axis); auto = get(); setlim(lim)
    fixed = tuple(not np.isclose(a, b) for a, b in zip(lim, auto))
    if any(fixed): return fixed
    sticky = [v for a in ax.get_children() for v in getattr(a.sticky_edges, axis)]
    on = tuple(any(np.isclose(v, q) for q in sticky) for v in lim)
    return on if any(on) else (True, True)


def _pad(fig, cv):
    """Keep data one row clear of the frame (a braille peak in the border row pokes through it); room for bar value labels.
    A limit the caller set stays where it is: only free sides move."""
    for ax in fig.axes:
        if _heat_axes(ax) or ax.get_yscale() != "linear": continue
        bb, fx, fy = ax.get_window_extent(), _fixed(ax, "x"), _fixed(ax, "y")
        if getattr(ax, "_tc_hlabels", 0) and bb.width:   # barh values sit past the bar ends: room for the longest
            x0, x1 = ax.get_xlim(); ends = [b.get_x() + b.get_width() for c in ax.containers if isinstance(c, BarContainer) for b in c]
            need = (ax._tc_hlabels + 1) * cv.cw / bb.width * (x1 - x0)
            if x1 > x0 and ends and x1 - max(ends) < need and not fx[1]: ax.set_xlim(right=max(ends) + need)
        if all(fy): continue
        for _ in range(3):   # row height in data units changes as the limits grow: settle
            lo, hi = ax.get_ylim()
            if hi < lo or not bb.height: break
            d = ax.dataLim.intervaly
            row = cv.ch / bb.height * (hi - lo)
            sticky = [v for a in ax.get_children() for v in getattr(a, "sticky_edges", None).y] if ax.get_children() else []
            free = lambda v: not any(abs(v - q) <= 1e-9 * max(1, abs(v)) for q in sticky)
            need = 2.2 if getattr(ax, "_tc_labels", False) else 1.2
            d0 = list(d)
            band = [t for t in ax.texts if t.get_transform() == ax.transData and t.get_text().strip()]
            if len(band) >= 2 and len({round(t.get_position()[1], 6) for t in band}) == 1 and np.isfinite(d0).all():   # one label per body (n=, median): a band clear of the bodies, never across them
                if band[0].get_position()[1] >= (d0[0] + d0[1]) / 2:
                    for t in band: t.set_va("bottom"); t.set_y(d0[1] + 1.0 * row)
                else:
                    for t in band: t.set_va("top"); t.set_y(d0[0] - 1.0 * row)
            for t in ax.texts:   # labels placed in data coordinates (n=, med=) are content too: keep them off the frame
                if t.get_transform() != ax.transData or not t.get_text().strip(): continue
                n, y = t.get_text().count("\n") + 1, t.get_position()[1]
                va = t.get_verticalalignment()
                lo_t, hi_t = (y - n * row, y) if va == "top" else (y, y + n * row) if va in ("bottom", "baseline") else (y - n * row / 2, y + n * row / 2)
                d = [min(d[0], lo_t), max(d[1], hi_t)]
            if np.isfinite(d).all():
                if hi - d[1] < need * row and free(hi) and not fy[1]: ax.set_ylim(top=d[1] + need * row)
                if d[0] - lo < 1.2 * row and free(lo) and not fy[0]: ax.set_ylim(bottom=d[0] - 1.2 * row)


def _rows_of(ax):
    """Row-centre positions (data units, ascending) an axes lays things on: category ticks, or the baselines of a ridgeline."""
    lo, hi = ax.get_ylim()
    yt = np.sort(ax.get_yticks())
    if isinstance(ax.yaxis.get_major_locator(), mticker.FixedLocator) and 8 <= len(yt) <= 60: pass
    else:
        base = [np.asarray(c.get_paths()[0].vertices)[:, 1].min() for c in ax.collections if isinstance(c, PolyCollection) and len(c.get_paths())]
        yt = np.unique(np.round(base, 9)) if len(base) >= 3 else np.array([])
    if len(yt) < 3 or min(lo, hi) != lo: return None
    g = float(np.diff(yt).min())
    return (yt, g) if g > 0 and np.allclose(np.diff(yt), g, rtol=1e-6) and yt[0] > lo - g and yt[-1] < hi + g else None


def moved_ax(ax, bars):  # True unless every bar stands on the axes' bottom edge (ylim low == bar base, bars point up)
    lo, hi = ax.get_ylim()
    return not (hi > lo and all(abs(b.get_y() - lo) < 1e-9 * max(1, abs(lo)) and b.get_height() > 0 for b in bars))


def _visible(ax, e):
    """Number of cells (edges `e`, either direction) with any part inside xlim."""
    x0, x1 = sorted(ax.get_xlim()); e = np.asarray(e, float)
    return int(((np.maximum(e[1:], e[:-1]) > x0 + 1e-9) & (np.minimum(e[1:], e[:-1]) < x1 - 1e-9)).sum())


def _snap(fig, cv):
    """Heat grids and one-label-per-row category axes: exactly one text row per data row, ticks on row centres, so labels and ink line up.
    Returns True when an axes was moved (layout must then stay frozen)."""
    moved = False
    for ax in fig.axes:
        bb, pos, rows = ax.get_window_extent(), ax.get_position(), None
        lo, hi = ax.get_ylim()
        if _heat_axes(ax):
            im = next((a for a in ax.images if np.ndim(a.get_array()) == 2), None)
            mesh = next((c for c in ax.collections if isinstance(c, QuadMesh) and np.ndim(c.get_array()) == 2), None)
            if im is not None: nc = _visible(ax, np.linspace(*im.get_extent()[:2], im.get_array().shape[1] + 1))   # zoomed image: only the columns inside xlim
            else: nc = _visible(ax, mesh.get_coordinates()[0, :, 0]) if mesh is not None else 0   # pcolormesh calendar: data columns inside xlim only (xlim may cut the last edge column)
            r = bb.width / cv.cw / nc if nc else 0
            if nc and r > 1 and abs(r - round(r)) > 1e-6:   # a fractional pitch (5.83 cols per column) draws cells of 5 and 6 cols, so values drift off their month labels: whole cells per data column
                x0c = round(pos.x0 * fig.bbox.width / cv.cw); k = max(1, int(r) if r < 2 else round(r))
                vl = max((width(t.get_text()) for t in ax.texts if t.get_gid() == "keep"), default=0)
                if vl and r > vl + 1: k = vl + 1   # labelled cells: value + one shade column, not a glyph on both sides of every number
                while k > 1 and (x0c + k * nc) * cv.cw > fig.bbox.width: k -= 1
                ax.set_position([(x0c + .25) * cv.cw / fig.bbox.width, pos.y0, k * nc * cv.cw / fig.bbox.width, pos.height]); pos = ax.get_position(); moved = True
            n = next((a.get_array().shape[0] for a in ax.images + [c for c in ax.collections if isinstance(c, QuadMesh)] if np.ndim(a.get_array()) == 2), 0)
            if n and abs(abs(hi - lo) - n) < 1e-6 * n: rows = n
        elif _rows_of(ax):
            yt, g = _rows_of(ax)
            m = getattr(ax, "_tc_pitch", 1)   # text rows per tick: a ridge with 2 gets its own two-row strip, the label on the lower row
            off = .5 if m == 1 else .25         # tick at the centre of its (lower) row
            top = yt[-1] + (max(1, np.ceil((hi - yt[-1]) / g - (1 - off))) + 1 - off) * g
            rdg = m == 1 and sum(isinstance(c, PolyCollection) for c in ax.collections) >= 3
            if rdg: top = yt[-1] + 1.5 * g   # a ridge never leaves its own row (core.fill): the top ridge row + one blank row so it never abuts the title
            bot = yt[0] - (max(1, np.ceil((yt[0] - lo) / g - off)) + off) * g
            if (top - bot) / g * m * cv.ch <= bb.height + cv.ch:
                ax.set_ylim(bot, top); rows = int(round((top - bot) / g)) * m
                if rdg:   # in-plot notes ("2026 n=40 med=3.55") get a clear right gutter of their own: widen x so no note ever sits on a ridge body
                    tx = [t for t in ax.texts if t.get_transform() == ax.transData and (t.get_ha() == "right" or t.get_text().startswith(_ylab(ax, t))) and abs(t.get_position()[1] - yt[np.abs(yt - t.get_position()[1]).argmin()]) <= .45 * g]
                    x0, x1 = ax.get_xlim()
                    if tx and x1 > x0 and all(x0 <= t.get_position()[0] <= x1 for t in tx):
                        gc = max(width(t.get_text()) for t in tx) + 2; W = bb.width / cv.cw
                        if gc < W / 2: nx = x1 + (x1 - x0) * gc / (W - gc); ax.set_xlim(x0, nx); [(t.set_position((nx, t.get_position()[1])), t.set_ha("right")) for t in tx]
                for t in ax.texts:   # in-plot ridge labels (ax.text next to a baseline) sit on that baseline's row, not the one above
                    ty = t.get_position()[1]; near = yt[np.abs(yt - ty).argmin()]
                    if t.get_transform() == ax.transData and abs(ty - near) <= .45 * g: t.set_position((t.get_position()[0], near)); t.set_va("center")
        elif getattr(ax, '_tc_even_y', False) and ax.get_yscale() == 'linear':
            # Equal numeric steps need an integer row pitch, not alternating 2/3-row gaps.
            ticks = np.sort(ax.get_yticks()); steps = np.diff(ticks)
            if len(steps) and steps[0] > 0 and np.allclose(steps, steps[0]):
                gap = steps[0]; bottom = np.floor(lo / gap) * gap; top = np.ceil(hi / gap) * gap
                intervals = max(1, round((top - bottom) / gap))
                pitch = max(1, int(bb.height / cv.ch / intervals))
                rows = intervals * pitch
                ax.set_ylim(bottom, top)
        elif _dist(ax) and ax.get_yscale() == "linear":   # violin: rules fall on pixel->row (floor); ticks sit on row edges, so a rule 0.2 units from a tick shared its row. Put ticks on row centres: rule rows are then within half a row of the value
            yt = [v for v in ax.get_yticks() if min(lo, hi) <= v <= max(lo, hi)]
            if len(yt) >= 2:
                p = abs(yt[1] - yt[0]) / abs(hi - lo) * bb.height / cv.ch   # rows per tick step: fractional, ticks drift up to half a row off any common phase
                if p >= 1 and int(p) / p >= .75: ax.set_position([pos.x0, pos.y1 - pos.height * int(p) / p, pos.width, pos.height * int(p) / p]); pos = ax.get_position()   # whole rows per step, top kept: every tick can sit on a row centre
                H = fig.bbox.height; fr = np.array([((H - ax.transData.transform((0, v))[1]) / cv.ch) % 1 for v in yt]); a = np.angle(np.exp(2j * np.pi * (fr - .5)).mean()) / (2 * np.pi)
                ax.set_position([pos.x0, pos.y0 + a * cv.ch / H, pos.width, pos.height]); moved = True
        if rows and rows * cv.ch <= bb.height + .5 * cv.ch:
            k = int((fig.bbox.height - bb.y1) / cv.ch) + .25   # top edge a quarter into a row: exactly on a boundary, float noise picks either row
            ax.set_position([pos.x0, 1 - (k + rows) * cv.ch / fig.bbox.height, pos.width, rows * cv.ch / fig.bbox.height]); moved = True
        bars = [b for c in ax.containers if isinstance(c, BarContainer) for b in c if b.get_height() and b.get_width()]
        if bars and not _heat_axes(ax) and ax.get_yscale() == "linear" and not moved_ax(ax, bars):   # vertical bars: the baseline sits just under a row boundary, so a short bar is ink in the row above the axis line, not hidden under it (a bin < half a row used to vanish)
            pos, H = ax.get_position(), fig.bbox.height; top = (1 - pos.y1) * H; bot = (1 - pos.y0) * H
            nb = (round(bot / cv.ch) + .05) * cv.ch
            if abs(nb - bot) < cv.ch: ax.set_position([pos.x0, 1 - nb / H, pos.width, pos.height + (nb - bot) / H]); moved = True
    return moved


def _tune_ticks(fig, cv):
    """Pick tick counts for the cell grid: ~1 x-label per 10 cols, ~1 y-label per 3 rows."""
    for ax in fig.axes:
        bb = ax.get_window_extent()
        for axis, n in ((ax.xaxis, bb.width / cv.cw / 10), (ax.yaxis, bb.height / cv.ch / 2)):
            n = max(2, int(n))
            loc = axis.get_major_locator()
            if isinstance(loc, mdates.AutoDateLocator):
                new = mdates.AutoDateLocator(minticks=max(3, n // 2), maxticks=n + 1)
                axis.set_major_locator(new)
                if isinstance(axis.get_major_formatter(), mdates.AutoDateFormatter):
                    axis.set_major_formatter(mdates.ConciseDateFormatter(new))
            elif type(loc) in (mticker.AutoLocator, mticker.MaxNLocator):
                axis.set_major_locator(mticker.MaxNLocator(nbins=n, steps=[1, 2, 2.5, 5, 10]))
                if isinstance(axis.get_major_formatter(), mticker.ScalarFormatter):   # 3 significant digits, one decimal count per axis
                    from .ticks import tick_formatter
                    t = [v for v in axis.get_major_locator().tick_values(*axis.get_view_interval())]
                    if any(v != round(v) for v in t):
                        f = tick_formatter(t, 3, strict=True); axis.set_major_formatter(mticker.FuncFormatter(lambda v, p, f=f: f(v)))
            axis.set_minor_locator(mticker.NullLocator())


def _shorten(fig, cols):
    from matplotlib.ticker import FuncFormatter, FixedFormatter
    from matplotlib.category import StrCategoryFormatter
    for ax in fig.axes:
        for axis, w in ((ax.xaxis, max(5, int(ax.get_position().width * cols) // max(1, len(ax.get_xticks())))), (ax.yaxis, max(5, cols // 3))):  # y labels: at most a third of the width
            f = axis.get_major_formatter()
            if not isinstance(f, (FixedFormatter, FuncFormatter, StrCategoryFormatter)): continue   # numeric/date labels are short; wrapping them would lose set_locs
            axis.set_major_formatter(FuncFormatter(lambda v, p, f=f, w=w: truncate(str(f(v, p)), w)))


WEEKDAYS = dict(Mon="Monday", Tue="Tuesday", Wed="Wednesday", Thu="Thursday", Fri="Friday", Sat="Saturday", Sun="Sunday")


def _collapse(fig):
    """Heat images / pcolormesh with whole empty rows (weekly data on a weekday grid): keep the observed rows and say so in one line."""
    for ax in fig.axes:
        for im in list(ax.images) + [c for c in ax.collections if isinstance(c, QuadMesh)]:
            a = im.get_array(); mesh = isinstance(im, QuadMesh)
            if np.ndim(a) != 2 or a.shape[0] < 2: continue
            if mesh:   # unit-cell mesh, y axis inverted (row 0 on top) like an upper-origin image
                lo, hi = ax.get_ylim(); co = im.get_coordinates()
                if not (lo > hi and np.allclose(co[:, 0, 1], np.arange(a.shape[0] + 1)) and np.allclose(co[0, :, 0], np.arange(a.shape[1] + 1))): continue
            elif im.origin != "upper": continue
            keep = np.isfinite(np.ma.filled(np.ma.masked_invalid(a).astype(float), np.nan)).any(1)
            if keep.all() or not keep.any(): continue
            idx = np.nonzero(keep)[0]; lab = {int(np.floor(t)) if mesh else int(round(t)): l.get_text() for t, l in zip(ax.get_yticks(), ax.get_yticklabels())}
            names = [lab.get(int(i)) or str(i) for i in idx]
            if mesh:
                kw = dict(cmap=im.cmap, norm=im.norm, edgecolors=im.get_edgecolor() if len(im.get_edgecolor()) else "none", linewidth=im.get_linewidth()[0])
                im.remove(); new = ax.pcolormesh(a[keep], **kw); new.colorbar = getattr(im, "colorbar", None)
                if new.colorbar is not None: new.colorbar.mappable = new
                ax.set_ylim(len(idx), 0); ax.set_yticks(np.arange(len(idx)) + .5)
            else:
                im.set_data(a[keep]); im.set_extent((*im.get_extent()[:2], len(idx) - .5, -.5)); ax.set_ylim(len(idx) - .5, -.5); ax.set_yticks(range(len(idx)))
            ax.set_yticklabels(names)
            note = (WEEKDAYS[names[0]] + "s only" if len(idx) == 1 and names[0] in WEEKDAYS else ", ".join(names) + " only" if len(idx) <= 3 else f"{len(idx)} of {len(keep)} rows have data")
            ax.set_title(f"{ax.get_title()}\n{note}" if ax.get_title() else note)


def _ramp(fig, cols=80):
    """Replace a heat colorbar with complete, cell-wrapped numeric ranges."""
    f = lambda v: (lambda t: np.format_float_positional(float(t), trim="-") if "e" in t else t.rstrip("."))(f"{v:#.3g}")   # 3 significant digits, never scientific
    fig._tc_ramp = None; L = getattr(fig, "_tc_levels", 4)
    for ax in list(fig.axes):
        for m in list(ax.images) + [c for c in ax.collections if isinstance(c, QuadMesh)]:
            cb = getattr(m, "colorbar", None)
            if cb is None or np.ndim(m.get_array()) != 2 and not isinstance(m, QuadMesh): continue
            m.autoscale_None()
            values = [float(m.norm.inverse(k / L)) for k in range(L + 1)]
            edges = [f(v) for v in values]
            if any(width(a + "-" + b) + (3 if L == 8 else 2) > cols for a, b in zip(edges, edges[1:])):
                edges = [f"{v:.3g}" for v in values]  # huge/tiny values: keep ranges atomic
            fig._tc_ramp = (cb.ax.get_ylabel() or cb.ax.get_xlabel(), edges); cb.remove()
            return


def prepare(fig, cols, rows=None):
    """Resize the figure to the cell grid (`rows` lines high, else from the figure's aspect). Returns (w_px, h_px)."""
    _ramp(fig, cols); _collapse(fig); fig._tc_ytop = False
    w_in, h_in = fig.get_size_inches()
    rows = max(8, rows) if rows else max(10, min(36, round(cols * (h_in / w_in) * CW / CH)))
    fig.set_dpi(72)
    fig.set_size_inches(cols * CW / 72, rows * CH / 72)
    fig._wrapped = {}
    for ax in fig.axes:  # core lays rotated tick labels flat and drops collisions; don't let the layout reserve room for the rotation
        ax.tick_params(axis="both", labelrotation=0)
        for l in ax.get_xticklabels(): l.set_horizontalalignment("center")
    # Wrap titles/xlabels in cells now, so layout reserves their extra lines.
    for t, w, role in [(getattr(fig, "_suptitle", None), cols, "title")] + [(t, max(12, int(ax.get_position().width * cols)), role) for ax in fig.axes for t, role in ((ax.title, "title"), (ax.xaxis.label, "label"))]:
        if t is not None and any(width(line) > w for line in t.get_text().split("\n")):
            t.set_text("\n".join(wrap(t.get_text(), w))); fig._wrapped.update({l: role for l in t.get_text().split("\n")})
    nl = lambda t: len(t.get_text().split("\n")) * bool(t.get_text()) if t is not None else 0
    over = nl(getattr(fig, "_suptitle", None)) + max([nl(ax.title) + nl(ax.xaxis.label) for ax in fig.axes], default=0) + 5   # title/label lines + tick row + tight_layout pads
    min_plotrows = max(6, getattr(fig, '_tc_min_plotrows', 6))
    if rows - over < min_plotrows:
        rows = min(over + min_plotrows, 56)
        fig.set_size_inches(cols * CW / 72, rows * CH / 72)   # text-only resolution, independent of PNG aspect
    extra = 0
    for ax in fig.axes:  # narrow figure or many series: a legend inside the plot sits on data, so hang it below the axes where the layout reserves room
        leg = ax.get_legend()
        if leg is None or not (cols < 60 or len(leg.get_texts()) > 8): continue
        labels = [t.get_text() for t in leg.get_texts()]
        ncol = max(1, min(len(labels), int(ax.get_position().width * cols) // (max(map(width, labels)) + 5)))
        below = (1.4 + len(ax.xaxis.label.get_text().split("\n")) * bool(ax.xaxis.label.get_text())) * CH   # tick row + xlabel lines
        ax.legend(leg.legend_handles, labels, title=leg.get_title().get_text() or None, loc="upper center", ncol=ncol, frameon=False, labelspacing=0.25,
                  bbox_to_anchor=(0.5, 0), bbox_transform=ax.transAxes + ScaledTranslation(0, -below / 72, fig.dpi_scale_trans))
        extra = max(extra, -(-len(labels) // ncol))
    for ax in fig.axes:
        if _heat_axes(ax):   # a heat grid is its own frame; terminal cells already carry the aspect
            ax.set_aspect("auto"); ax.set_frame_on(False)
            ax.tick_params(axis="x", length=0, pad=1)   # month labels on the row right under the grid
            if ax.get_box_aspect(): ax.set_box_aspect(max(1.0, rows * .4))   # colorbar: ~3 cells wide, not the 20:1 sliver
            arr = next((np.ndim(a.get_array()) == 2 and a.get_array().shape[0] for a in ax.images), 0)
            if arr and arr <= 40: rows = min(max(rows, arr + over + 1), 56); fig.set_size_inches(cols * CW / 72, rows * CH / 72)
        if _dist(ax): ax.spines[["top", "right"]].set_visible(False); fig._tc_ytop = True
        r = _rows_of(ax)
        if r and len(r[0]) <= 45:   # one label / ridge per row needs >= 1 row per step; two rows per year when they fit
            lim = ax.get_ylim(); span = int(abs(lim[1] - lim[0]) / r[1] * 1.1) + 1
            rows = min(max(rows, span + over + 3), 56); fig.set_size_inches(cols * CW / 72, rows * CH / 72)
        for c in ax.containers:   # barh: value at the bar end, one row per bar and a gap row between
            if isinstance(c, BarContainer) and 0 < len(c) <= 40 and c.orientation == "horizontal":
                from .ticks import tick_formatter
                v = np.array([b.get_width() for b in c], float); f = tick_formatter(v[np.isfinite(v)], 3, strict=True)
                lab = [f(x) if np.isfinite(x) else "" for x in v]
                ax.bar_label(c, labels=lab, padding=CW); ax._tc_hlabels = max(map(width, lab))
                rows = min(max(rows, 2 * len(c) + over + 1), 56); fig.set_size_inches(cols * CW / 72, rows * CH / 72)
        for c in ax.containers:   # bar values: all when they fit, else the extremes
            if isinstance(c, BarContainer) and 0 < len(c) <= 60 and c.orientation == "vertical" and getattr(fig, "_tc_barlabels", True):
                from .ticks import tick_formatter
                v = np.array([b.get_height() for b in c], float); f = tick_formatter(v[np.isfinite(v)], 3, strict=True)
                lab = [f(x) if np.isfinite(x) else "" for x in v]
                if not all(width(l) + 1 <= ax.get_position().width * cols / len(c) for l in lab):
                    keep = {i for i in (int(np.nanargmax(v)), int(np.nanargmin(v))) if v[max(0, i - 2):i + 3].max() <= v[i]}   # an extreme whose neighbours are taller would print over them
                    lab = [l if i in keep else "" for i, l in enumerate(lab)]
                ax.bar_label(c, labels=lab, padding=0); ax._tc_labels = True
    if extra: rows = min(rows + extra, 50); fig.set_size_inches(cols * CW / 72, rows * CH / 72)   # the hung legend needs its own rows
    return cols * CW, rows * CH


def _ylab(ax, t):
    """The y tick label of the row a note sits on ('' if none): a left-anchored note that starts with it names its own row."""
    y = t.get_position()[1]; tk = [(abs(v - y), l.get_text()) for v, l in zip(ax.get_yticks(), ax.get_yticklabels())]
    return min(tk)[1] or "\0" if tk else "\0"


def _clipped(fig):
    """One caption line when an artist's own data runs past the axes' x limits (the figure's xlim clips it); we only ever widen x, never narrow."""
    from matplotlib.collections import PolyCollection
    for ax in fig.axes:
        x0, x1 = sorted(ax.get_xlim()); tol = 1e-9 * (x1 - x0 or 1); ex = []
        for l in ax.lines:
            if l.get_visible() and l.get_transform() == ax.transData: ex += [np.asarray(l.get_xdata(orig=False), float)]   # orig=False: date units arrive as axis floats, not datetime64 ns
        for c in ax.collections:
            if isinstance(c, PolyCollection) and c.get_visible(): ex += [pth.vertices[:, 0] for pth in c.get_paths()]
        for b in ax.patches:
            if b.get_visible() and b.get_transform() == ax.transData and hasattr(b, "get_width"): ex += [np.array([b.get_x(), b.get_x() + b.get_width()], float)]
        ex = [e[np.isfinite(e)] for e in ex]; ex = [e for e in ex if len(e)]
        if ex and (min(e.min() for e in ex) < x0 - tol or max(e.max() for e in ex) > x1 + tol):
            f = (lambda v: ax.format_xdata(v)) if ax.xaxis.get_converter() is not None else (lambda v: f"{v:.4g}")
            return f"clipped at x={f(x0)}\u2013{f(x1)} (figure xlim)"
    return ""


def render(fig, cols=80, color=False, rows=None):
    w, h = prepare(fig, cols, rows)
    cap = _clipped(fig)
    rend = TextRenderer(w, h, cols); rend.wrapped = fig._wrapped
    fig._get_renderer = lambda: rend         # layout engines measure text in cells
    hooked = _hook(fig)
    from matplotlib.layout_engine import PlaceHolderLayoutEngine
    if fig.get_layout_engine() is None or isinstance(fig.get_layout_engine(), PlaceHolderLayoutEngine):  # fig.tight_layout() at build time leaves a no-op placeholder: layout must rerun in cells
        fig.set_layout_engine("tight")
    import warnings
    with warnings.catch_warnings(record=True) as wl:
        warnings.simplefilter("always")
        fig.draw(rend)                        # pass 1: layout
        if any("Tight layout" in str(w.message) for w in wl) or any(min(a.get_position().width, a.get_position().height) < .1 or a.get_position().height > .99 for a in fig.axes):  # plotnine: infeasible gridspec leaves the axes filling the figure   # labels too wide for the grid: layout gave up and kept the old margins, so shorten x labels to their slot and lay out again
            area = lambda: sum(a.get_position().width * a.get_position().height for a in fig.axes)
            a0, old, pos = area(), [(x, x.get_major_formatter()) for a in fig.axes for x in (a.xaxis, a.yaxis)], [a.get_position() for a in fig.axes]
            _shorten(fig, cols); fig.draw(rend)
            if area() < a0:   # shortening squeezed the plot (side-by-side bar panels): keep the long labels, core drops colliding ones
                for x, f in old: x.set_major_formatter(f)
                for a, p in zip(fig.axes, pos): a.set_position(p)
        warnings.simplefilter("ignore")
        _tune_ticks(fig, rend.cv); _pad(fig, rend.cv)
        if _snap(fig, rend.cv): fig.set_layout_engine("none")
        rend = TextRenderer(w, h, cols); rend.wrapped = fig._wrapped
        fig._get_renderer = lambda: rend
        rend.cv.solidfills = getattr(fig, '_tc_solidfills', False)
        rend.cv.stamp = getattr(fig, '_tc_stamp', True); rend.cv.ramp = fig._tc_ramp; rend.cv.ytop = fig._tc_ytop; rend.cv.levels = getattr(fig, '_tc_levels', 4); rend.cv.fam = getattr(fig, '_tc_fam', {})
        fig.draw(rend)                        # pass 2: real
    fig.set_layout_engine("none")             # freeze geometry for the shape-check reference
    del fig._get_renderer
    _unhook(hooked)
    text = rend.cv.render(color=color)
    if cap: text += "\n" + "\n".join(wrap(cap, cols)); rend.cv.meta["clipped"] = cap
    rend.cv.meta.update(owners=rend.owners, owned=rend.cv.owned)
    return text, rend.cv.meta


def _fmt(axis, v):
    """A data value as the axis means it: a date, a category name, else 4 significant digits."""
    if isinstance(axis.units, UnitData):
        names = {i: k for k, i in axis.units._mapping.items()}
        if np.isclose(v, round(v)) and round(v) in names: return str(names[round(v)])
    if "Date" in type(axis.get_converter()).__name__:
        d = mdates.num2date(v); lo, hi = axis.get_view_interval()
        return d.strftime("%Y-%m-%d" if (d.hour, d.minute) == (0, 0) or abs(hi - lo) > 3 else "%Y-%m-%d %H:%M")   # time of day only on a short view
    return f"{v:.4g}"


def _compact(axis, lo, hi):
    """Data values on one axis (None: a colour scale), on a step near 1/60 of their span (3 significant digits on a log axis): within ~2.5% of the span, few tokens."""
    if axis is not None and (isinstance(axis.units, UnitData) or "Date" in type(axis.get_converter()).__name__): return lambda v: _fmt(axis, v)
    if axis is not None and axis.get_scale() == "log":
        return lambda v: (s if "e" not in (s := f"{v:.3g}") or abs(v) >= 1e15 or abs(v) < 1e-3 else f"{float(s):.0f}" if abs(v) >= 1 else s)
    span = abs(hi - lo) or abs(hi) or 1
    d = max(0, -int(np.round(np.log10(span / 60))))
    return lambda v: (t if (t := f"{v:.{d}f}".rstrip("0").rstrip(".") if d else f"{v:.0f}") not in ("-0", "") else "0")


def _samples(x, y, n=10):
    """About n points to stand for a long line: its first and last point and nice x positions between, y interpolated there (nearest point if x is not sorted)."""
    xs = [v for v in mticker.MaxNLocator(nbins=n, steps=[1, 2, 2.5, 5, 10]).tick_values(x.min(), x.max()) if x.min() < v < x.max()]
    xs = sorted({x[0], *xs, x[-1]}) if x[0] <= x[-1] else [x[0], *xs, x[-1]]
    if np.all(np.diff(x) > 0): return np.array(xs), np.interp(xs, x, y)
    i = [int(np.abs(x - v).argmin()) for v in xs]
    return x[i], y[i]


def _outliers(xy):
    """Points far off the least-squares line: residual over 5 robust sigmas (at most 3, largest first)."""
    if len(xy) < 8 or np.ptp(xy[:, 0]) == 0: return []
    res = xy[:, 1] - np.polyval(np.polyfit(xy[:, 0], xy[:, 1], 1), xy[:, 0])
    sig = 1.4826 * np.median(np.abs(res - np.median(res)))
    far = np.flatnonzero(np.abs(res) > 5 * sig) if sig > 0 else []
    return [int(i) for i in sorted(far, key=lambda i: -abs(res[i]))[:3]]


def _scale(ax, k):
    axis = getattr(ax, k + "axis")
    kind = "category" if isinstance(axis.units, UnitData) else "date" if "Date" in type(axis.get_converter()).__name__ else axis.get_scale()
    d = dict(label=axis.label.get_text(), scale=kind)
    if kind == "category": d["categories"] = len(axis.units._mapping)
    else: d["range"] = "..".join(_fmt(axis, v) for v in getattr(ax, f"get_{k}lim")())
    return d


def _data_axes(fig): return [ax for ax in fig.axes if not hasattr(ax, "_colorbar")]


def _name(a, bars):
    c = bars.get(id(a), a)
    label = c.get_label() if hasattr(c, "get_label") else None
    return label if label and not label.startswith("_") else None


def _points(a, bars):
    """Display coordinates of an artist's finite data points (bar ends for bars), or None when it has no point data."""
    if isinstance(a, Line2D): xy, tr = a.get_xydata(), a.get_transform()
    elif isinstance(a, PathCollection): xy, tr = np.asarray(a.get_offsets(), float), a.get_offset_transform()
    elif id(a) in bars and a.get_width() and a.get_height():
        h = bars[id(a)].orientation == "horizontal"
        xy, tr = np.array([[a.get_x() + a.get_width(), a.get_y() + a.get_height() / 2] if h else [a.get_x() + a.get_width() / 2, a.get_y() + a.get_height()]]), a.axes.transData
    else: return None
    xy = np.asarray(xy, float).reshape(-1, 2)
    xy = xy[np.isfinite(xy).all(1)]
    return tr.transform(xy) if len(xy) else xy


def _heat_at(ax, a, z, k):
    """Row, column labels of flat heat cell k: the tick label at the cell centre, else the centre value."""
    i, j = divmod(int(k), z.shape[1])
    if isinstance(a, QuadMesh): x, y = a.get_coordinates()[i:i + 2, j:j + 2].reshape(-1, 2).mean(0)
    else:
        l, r, b, t = a.get_extent(); n, m = z.shape
        x = l + (j + .5) * (r - l) / m; y = (t + (i + .5) * (b - t) / n) if a.origin == "upper" else b + (i + .5) * (t - b) / n
    tick = lambda axis, v: next((lab.get_text() for tv, lab in zip(axis.get_ticklocs(), axis.get_ticklabels()) if abs(tv - v) < .5 and lab.get_text()), None) or _fmt(axis, v)
    return f"{tick(ax.yaxis, y)}/{tick(ax.xaxis, x)}"


def describe(fig, meta):
    """Scales and series of every data axes, read from the figure's own data (never from the text): what the chart says in numbers."""
    keys = {tuple(s["rgb"]): s["key"] for s in meta["series"]}
    key = lambda c: keys.get(tuple(round(float(v), 2) for v in to_rgb(c)))
    scales, series = [], []
    for j, ax in enumerate(_data_axes(fig)):
        scales.append(dict(axes=j, title=ax.get_title(), x=_scale(ax, "x"), y=_scale(ax, "y")))
        fx, fy = (lambda v: _fmt(ax.xaxis, v)), (lambda v: _fmt(ax.yaxis, v))
        data = lambda tr, xy: xy if tr is ax.transData or not len(xy) else ax.transData.inverted().transform(tr.transform(xy))   # axhline, transAxes, blended: back to data
        rng = lambda f, v: f"{f(np.min(v))}..{f(np.max(v))}" if len(v) else ""
        for c in ax.containers:
            if not isinstance(c, BarContainer) or not len(c): continue
            h = c.orientation == "horizontal"
            pos, val = ([b.get_y() + b.get_height() / 2 for b in c], [b.get_width() for b in c]) if h else ([b.get_x() + b.get_width() / 2 for b in c], [b.get_height() for b in c])
            fp, fv = (fy, fx) if h else (fx, fy)
            wid = np.array([b.get_height() if h else b.get_width() for b in c], float); edge = np.array([b.get_y() if h else b.get_x() for b in c], float)
            hist = len(c) > 6 and np.allclose(wid, wid[0]) and np.allclose(np.diff(edge), wid[0]) and not isinstance((ax.yaxis if h else ax.xaxis).units, UnitData)
            if hist:   # equal-width, edge-to-edge bars: one header and the counts, cheaper than a label per bar
                fe, fc = _compact(ax.yaxis if h else ax.xaxis, edge[0], edge[-1] + wid[0]), _compact(ax.xaxis if h else ax.yaxis, 0, np.nanmax(val))
                k = int(np.nanargmax(val))
                series.append(dict(name=_name(c, {}), kind="histogram", axes=j, key=key(c[0].get_facecolor()), color=to_hex(c[0].get_facecolor()), n=len(c),
                                   bins=f"{len(c)} bins of {fe(wid[0])} from {fe(edge[0])} to {fe(edge[-1] + wid[0])}",
                                   peak=f"{fe(edge[k])}-{fe(edge[k] + wid[0])}={fc(val[k])}", values=[fc(v) for v in val]))
                continue
            fv = _compact(ax.xaxis if h else ax.yaxis, min(0, np.nanmin(val)), np.nanmax(val)) if len(val) and np.isfinite(val).any() else fv
            pairs = [f"{fp(p)}={fv(v)}" for p, v in zip(pos, val) if np.isfinite(v)]
            if len(pairs) > 40: i, k = int(np.nanargmin(val)), int(np.nanargmax(val)); pairs = [f"min {fp(pos[i])}={fv(val[i])}", f"max {fp(pos[k])}={fv(val[k])}"]
            series.append(dict(name=_name(c, {}), kind="barh" if h else "bar", axes=j, key=key(c[0].get_facecolor()), color=to_hex(c[0].get_facecolor()), n=len(c), values=pairs))
        for a in ax.lines:
            xy = a.get_xydata(); xy = data(a.get_transform(), xy[np.isfinite(xy).all(1)])
            if not len(xy): continue
            cx, cy = _compact(ax.xaxis, *ax.get_xlim()), _compact(ax.yaxis, *ax.get_ylim())
            sampled = len(xy) > 16
            px, py = _samples(xy[:, 0], xy[:, 1]) if sampled else (xy[:, 0], xy[:, 1])
            at, ys = [cx(v) for v in px], [cy(v) for v in py]
            lo, hi = xy[xy[:, 1].argmin()], xy[xy[:, 1].argmax()]
            ext = [f"min {cx(lo[0])}={cy(lo[1])}", f"max {cx(hi[0])}={cy(hi[1])}"] if sampled else []
            series.append(dict(name=_name(a, {}), kind="line", axes=j, key=key(a.get_color()), color=to_hex(a.get_color()), n=len(xy), x=rng(fx, xy[:, 0]), y=rng(fy, xy[:, 1]),
                               at=at, ys=ys, sampled=sampled, values=[f"{x}={y}" for x, y in zip(at, ys)] + ext))
        for a in ax.collections:
            if isinstance(a, QuadMesh): continue
            fc = a.get_facecolor(); c = fc[0] if len(fc) else (a.get_edgecolor()[0] if len(a.get_edgecolor()) else "k")
            if isinstance(a, PathCollection):
                xy = np.asarray(a.get_offsets(), float); xy = data(a.get_offset_transform(), xy[np.isfinite(xy).all(1)])
                cx, cy = _compact(ax.xaxis, *ax.get_xlim()), _compact(ax.yaxis, *ax.get_ylim())
                out = _outliers(xy) if len(xy) else []
                rest = np.delete(xy, out, 0)
                stats = dict(mean=f"{cx(xy[:, 0].mean())},{cy(xy[:, 1].mean())}") if len(xy) else {}
                if len(xy) > 2 and np.ptp(xy[:, 0]) and np.ptp(xy[:, 1]): stats["r"] = f"{np.corrcoef(xy.T)[0, 1]:.2f}"
                if out: stats.update(outliers=" ".join(f"({cx(xy[i, 0])},{cy(xy[i, 1])})" for i in out), rest=f"x={cx(rest[:, 0].min())}..{cx(rest[:, 0].max())} y={cy(rest[:, 1].min())}..{cy(rest[:, 1].max())}")
                series.append(dict(name=_name(a, {}), kind="scatter", axes=j, key=key(c), color=to_hex(c), n=len(xy), x=rng(cx, xy[:, 0]), y=rng(cy, xy[:, 1]), values=[], **stats))
            elif isinstance(a, PolyCollection) and len(a.get_paths()):
                v = np.concatenate([p.vertices for p in a.get_paths()]); v = data(a.get_transform(), v[np.isfinite(v).all(1)])
                series.append(dict(name=_name(a, {}), kind="area", axes=j, key=key(c), color=to_hex(c), n=len(a.get_paths()), x=rng(fx, v[:, 0]), y=rng(fy, v[:, 1]), values=[]))
        for a in [*ax.images, *(c for c in ax.collections if isinstance(c, QuadMesh))]:
            z = np.ma.masked_invalid(np.ma.asarray(a.get_array(), float)) if a.get_array() is not None else None
            if z is None or z.ndim != 2: continue
            cb = getattr(a, "colorbar", None)
            label = cb.ax.get_ylabel() or cb.ax.get_xlabel() if cb is not None else ""
            cz = _compact(None, float(z.min()), float(z.max())) if z.count() else None
            v = [f"min {_heat_at(ax, a, z, z.argmin())}={cz(z.min())}", f"max {_heat_at(ax, a, z, z.argmax())}={cz(z.max())}"] if z.count() else []
            cells = {}
            if z.count():   # small grids in full, else the mean of every row and column (when there are few enough)
                rl = [_heat_at(ax, a, z, i * z.shape[1]).split("/")[0] for i in range(z.shape[0])]
                cl = [_heat_at(ax, a, z, k).split("/")[1] for k in range(z.shape[1])]
                fmt = lambda row: " ".join("." if m else cz(x) for x, m in zip(row.data, np.ma.getmaskarray(row)))  # noqa: E731
                if z.size <= 36: cells = dict(cols=" ".join(cl), grid=[f"{r}: {fmt(z[i])}" for i, r in enumerate(rl)])
                else:
                    if z.shape[0] <= 12: cells["row_means"] = " ".join(f"{r}={cz(m)}" for r, m in zip(rl, z.mean(1)))
                    if z.shape[1] <= 12: cells["col_means"] = " ".join(f"{k}={cz(m)}" for k, m in zip(cl, z.mean(0)))
            series.append(dict(name=label or _name(a, {}), kind="heatmap", axes=j, key=None, color=None, n=int(z.count()), shape=f"{z.shape[0]}x{z.shape[1]}",
                               missing=int(z.mask.sum()) if np.ma.is_masked(z) else 0, values=v, **cells))
    return series, scales


def losses(fig, meta):
    """Data the text does not show, measured on the drawn figure: data artists that left no visible cell, and points outside the axes view.
    ponytail: series are keyed by colour, so an artist sharing its colour with a drawn one counts as drawn; per-artist ink ids if that matters."""
    bars = {id(b): c for ax in _data_axes(fig) for c in ax.containers if isinstance(c, BarContainer) for b in c}
    kind = lambda a: "bar" if id(a) in bars else type(a).__name__
    lost, clipped = {}, {}
    for i, (a, n) in enumerate(meta["owners"]):
        if not a.get_visible() or a.axes is None: continue
        pts = _points(a, bars)
        if pts is not None and a.get_clip_on():
            x0, y0, x1, y1 = a.axes.bbox.extents
            out = int((~((pts[:, 0] >= x0 - .5) & (pts[:, 0] <= x1 + .5) & (pts[:, 1] >= y0 - .5) & (pts[:, 1] <= y1 + .5))).sum())
            if out:
                k = (kind(a), _name(a, bars)); o, t = clipped.get(k, (0, 0)); clipped[k] = (o + out, t + len(pts))
            if out == len(pts): continue   # wholly outside: clipped, not lost
        sids = meta["owned"].get(i, set())
        if n == 0 or sids and not sids & meta["drawn"]:
            if pts is not None and not len(pts) or isinstance(a, Collection) and not any(np.isfinite(p.vertices).all(1).any() for p in a.get_paths()): continue   # no data to draw
            k = (kind(a), _name(a, bars), "drew nothing" if n == 0 else "hidden: no visible cell"); lost[k] = lost.get(k, 0) + 1
    out = [dict(kind="lost_artist", what=f"{k} {name!r}" if name else k, detail=f"{c} {why}" if c > 1 else why)
           for (k, name, why), c in lost.items()]
    out += [dict(kind="clipped_data", what=f"{k} {name!r}" if name else k, detail=f"{o} of {t} points outside the axes view")
            for (k, name), (o, t) in clipped.items()]
    return out


def bars_without_ink(fig, text, cols=80):
    """Vertical bars with height > 0 that left no fill glyph in their columns/rows of the rendered text (geometry frozen by render): honesty check, must be []."""
    Hh, cw = fig.bbox.height, fig.bbox.width / cols; ch = 2 * cw   # cells are 1:2
    lines, miss = text.split("\n"), []
    for ax in fig.axes:
        L = next((i for i, l in enumerate(lines) if "└" in l), None)   # leading blank rows are trimmed from the text: anchor on the axis line
        off = 0 if L is None else L - int((Hh - ax.get_window_extent().y0 - 1e-6) / ch)
        for c in ax.containers:
            if not isinstance(c, BarContainer): continue
            for b in c:
                if not (b.get_height() > 0 and b.get_width() > 0): continue
                (x0, y1), (x1, y0) = ax.transData.transform((b.get_x(), b.get_y() + b.get_height())), ax.transData.transform((b.get_x() + b.get_width(), b.get_y()))
                r0, r1, cm = int((Hh - y1) / ch) + off, int((Hh - y0 - 1e-6) / ch) + off, int((x0 + x1) / 2 / cw)
                if not any(r < len(lines) and cm < len(lines[r]) and lines[r][cm] in "▁▂▃▄▅▆▇█▀▌▐▓▒░▚▞" for r in range(r0, r1 + 1)): miss.append(b)
    return miss


def _test():
    """One fixture per defect of the model-facing text render (synthetic stand-ins for the gas5 figure scripts)."""
    import re
    from matplotlib.figure import Figure
    strip = lambda t: re.sub(r"\x1b\[[0-9;]*m", "", t)
    BR = lambda t: any(0x2800 <= ord(c) < 0x2900 for c in t)

    # calendar heatmap: weekly data on a weekday grid -> only the observed row, a one-line note, a one-line ramp with real end values
    g = np.full((7, 53), np.nan); g[0, 1:] = np.linspace(2.3, 2.75, 52); g = np.ma.masked_invalid(g)
    f = Figure(figsize=(12, 3.5)); ax = f.subplots(); im = ax.imshow(g, cmap="viridis")
    ax.set_yticks(range(7)); ax.set_yticklabels("Mon Tue Wed Thu Fri Sat Sun".split()); ax.set_xticks([0, 26]); ax.set_xticklabels(["Jan", "Jul"])
    ax.set_title("2025 calendar"); f.colorbar(im, ax=ax, label="Price"); f.tight_layout()
    t, _ = render(f, 80, color=True); p = strip(t); rows = p.split("\n")
    mon = next(r for r in rows if r.lstrip().startswith("Mon "))
    assert sum(c in "░▒▓█" for c in mon[5:]) in range(50, 54) and not BR(p) and "┌" not in p, "calendar: heat row"
    assert not any(r.lstrip().startswith(d) for r in rows for d in ("Tue", "Wed", "Sun")), "calendar: empty weekdays collapsed"
    assert "Mondays only" in p and re.search(r"░ 2\.30-2\.\d+  ▒ [\d.]+-[\d.]+  ▓ [\d.]+-[\d.]+  █ [\d.]+-2\.75", p) and len(rows) <= 6, p   # note + real ramp ends (3 sig digits)
    assert next(i for i, r in enumerate(rows) if "Jan" in r) == rows.index(mon) + 1 and rows.index(next(r for r in rows if "Jan" in r)) < next(i for i, r in enumerate(rows) if "2.30" in r), "calendar: month labels under the grid, ramp below them"
    assert "\x1b[48;2;" in t, "calendar: colour is a cell background"
    assert "48;2;253;231;37;38;2;253;231;37m█" in t and "38;2;0;0;0m█" not in t, "calendar: top bin ink is its own colour, never black on dark"
    assert all(m[:3] == m[3:] for m in re.findall(r"48;2;(\d+);(\d+);(\d+);38;2;(\d+);(\d+);(\d+)m", t)) and not re.search(r"\n\s*\n\s*\n", p), "calendar: solid cells (ink = bg, cell colour = key bin), no blank-row gap"
    g = np.full((7, 52), np.nan); g[0] = np.linspace(2.3, 2.75, 52); f = Figure(figsize=(13, 3.5)); ax = f.subplots(); im = ax.imshow(np.ma.masked_invalid(g), cmap="viridis", aspect="equal")
    ax.set_yticks(range(7)); ax.set_yticklabels("Mon Tue Wed Thu Fri Sat Sun".split()); f.colorbar(im, ax=ax, label="Price"); f.tight_layout()
    mon = next(r for r in strip(render(f, 80, color=True)[0]).split("\n") if r.lstrip().startswith("Mon ")); assert sum(c in "░▒▓█" for c in mon[5:]) == 52, "calendar: one cell per observed week, no duplicated weeks"
    # pcolormesh calendar in the gas5 Y layout (54 mesh cols, xlim cut at 53, white edges, ylim inverted, masked weekdays): one cell per finite data column, masked rows dropped
    g = np.full((7, 54), np.nan); g[0, 1:53] = np.linspace(2.3, 2.75, 52); g[2, 5:30] = 2.5; g[0, 20] = np.nan; g = np.ma.masked_invalid(g)
    f = Figure(figsize=(12, 3.5)); ax = f.subplots(); im = ax.pcolormesh(g, cmap="YlOrRd", edgecolors="white", linewidth=.5); ax.set_ylim(7, 0)
    ax.set_yticks(np.arange(7) + .5); ax.set_yticklabels("Mon Tue Wed Thu Fri Sat Sun".split()); ax.set_xticks([0.5, 26.5]); ax.set_xticklabels(["Jan", "Jul"]); ax.set_xlim(0, 53); ax.set_title("2025 calendar")
    f.colorbar(im, ax=ax, label="Price"); f.tight_layout()
    p = strip(render(f, 80, color=True)[0]); rows = p.split("\n"); cells = lambda d: sum(c in "░▒▓█" for r in rows if r.lstrip().startswith(d + " ") for c in r[5:])
    assert cells("Mon") == 51 and cells("Wed") == 25, "calendar mesh: shaded cells == finite cells (one text cell per data column)"
    assert not any(r.strip() in ("Tue", "Thu", "Fri", "Sat", "Sun") or r.lstrip().startswith(("Tue ", "Thu ", "Fri ")) for r in rows) and not re.search(r"\n\s*\n", p.strip()) and "Monday, Wednesday only" in p.replace("Mon, Wed only", "Monday, Wednesday only"), "calendar mesh: all-blank rows dropped, noted"
    # dashed median over a violin: solid visible rule, not a braille dash texture
    f = Figure(figsize=(8, 5)); ax = f.subplots(); r = np.random.default_rng(1); vs = [r.normal(3 + i / 2, .5, 400) for i in range(3)]; ax.violinplot(vs, showmedians=False)
    for i, v in enumerate(vs): ax.plot([i + .75, i + 1.25], [np.median(v)] * 2, color="tab:red", ls="--", lw=1.5)
    f.tight_layout(); p = strip(render(f, 70)[0]); assert sum(bool(re.search(r"─{11}", r)) for r in p.split("\n")) >= 3 and not re.search("[⠠⠄⠒⠐⠤⠉⠈⠁]", p), "dashed median over a violin: solid rule, no dash fringe"
    h = np.random.default_rng(0).random((7, 40)); f = Figure(figsize=(10, 3.5)); ax = f.subplots(); im = ax.imshow(h, cmap="viridis"); ax.set_yticks(range(7)); ax.set_yticklabels("Mon Tue Wed Thu Fri Sat Sun".split()); f.colorbar(im, ax=ax); f.tight_layout()
    p = render(f, 80)[0]; assert "Sun" in p and "only" not in p and re.search(r"░ 0\.000301-[\d.]+  ▒ [\d.]+-[\d.]+  ▓ [\d.]+-[\d.]+  █ [\d.]+-0\.997", p), "heatmap: full grid keeps every row"

    # ridgeline, 12 years: every label present, one row per year; each ridge strictly inside its own row (never ink in another year's row)
    def band_ok(t, m, shape=True):   # one row per year: ink only on label rows, caption iff per-ridge scaling, >= 3 distinct block heights per ridge
        rows = t.split("\n"); yr = [r for r in rows if re.match(r"\s*\d{4}\b.*│", r)]; cap = "each ridge scaled to its own peak"
        body = lambda r: r.split("│", 1)[1] if "│" in r else ""; first = rows.index(yr[0]); last = rows.index(yr[-1])
        assert all(not re.search("[▁-█▀]", body(r)) for r in rows[:first] + rows[last + 1:] if r not in yr and "│" in r), "ridgeline: ink outside every year's row"
        assert all(re.match(r"\s*\d{4}\b", r) for r in rows[first:last + 1]), "ridgeline: ink in a row that is not a year's own"
        assert (cap in t) == bool(m.get("ridge_scaled")), "ridgeline: caption iff per-ridge scaling"
        if shape: assert all(len(set(re.findall("[▁-█]", body(r)))) >= 3 for r in yr), "ridgeline: every ridge keeps >= 3 distinct block heights"
        return yr
    f = Figure(figsize=(8, 8)); ax = f.subplots(); xs = np.linspace(0, 10, 200)
    for i in range(12):
        d = np.exp(-(xs - 3 - i * .4) ** 2) * 1.8
        ax.fill_between(xs, i, i + d, alpha=.7, zorder=12 - i); ax.plot(xs, i + d, "k", lw=.6, zorder=12 - i)
    ax.set_yticks(range(12)); ax.set_yticklabels([str(2000 + i) for i in range(12)]); f.tight_layout()
    t, mm = render(f, 80); rows = t.split("\n"); band_ok(t, mm)
    lab = {int(m[2]): r for r in rows if (m := re.match(r"\s*(20(\d\d))\s*│", r))}
    assert sorted(lab) == list(range(12)), "ridgeline: a year label was dropped"
    assert all("█" in r for r in lab.values()), "ridgeline: each ridge stands on its own label row"
    assert not re.search("[▚▞░▒]", t), "ridgeline: solid fills, no shade patterns"
    idx = [rows.index(lab[k]) for k in range(12)]; assert [a - b for a, b in zip(idx, idx[1:])] == [1] * 11, "ridgeline: one row per year, in order"
    # 30 years are too many for two rows each: one own-scaled row per year, none shared
    f = Figure(figsize=(8, 8)); ax = f.subplots()
    for i in range(30):
        d = np.exp(-(xs - 3 - i * .2) ** 2) * 1.8
        ax.fill_between(xs, i, i + d, alpha=.7, zorder=30 - i)
    ax.set_yticks(range(30)); ax.set_yticklabels([str(1990 + i) for i in range(30)]); f.tight_layout()
    t, mm = render(f, 80); rows = t.split("\n"); yr = band_ok(t, mm, shape=False)
    assert len(yr) == 30 and all(re.search("[▁-█]", r.split("│")[1]) for r in yr), "ridgeline: 30 years, each with its own ink on its own row"
    # P9: cc ridges. Z: year-bearing ax.text notes at the right edge never touch a body; E: tallest peak <= 2 rows, top ridge stays inside the plot
    f = Figure(figsize=(9, 11)); ax = f.subplots(); xs = np.linspace(0, 6, 300)
    for i in range(27):
        d = np.exp(-(xs - 2 - i * .08) ** 2 / (.3 + .2 * (i % 4))); ax.fill_between(xs, i * .5, i * .5 + d * 1.8, alpha=.8, zorder=27 - i); ax.text(xs[-1], i * .5 + .05, f"{2000 + i} n=5{i % 9} med=2.{i:02d}", fontsize=9, va="bottom", ha="right")
    ax.set_yticks([i * .5 for i in range(27)]); ax.set_yticklabels([str(2000 + i) for i in range(27)]); f.tight_layout()
    t, m = render(f, 80); rows = t.split("\n"); assert not m["inked"] and not m["dropped"] and all(f"{2000 + i} n=5{i % 9} med=2.{i:02d}" in t for i in range(27)), "ridgeline: year-bearing notes all present, none on fill"
    top = next(i for i, r in enumerate(rows) if re.search("[▁-█]", r.split("│", 1)[-1])); first = next(i for i, r in enumerate(rows) if re.match(r"\s*2026\s*│", r)); assert first == top and top >= 1, "ridgeline: top ridge stays in its own row and a blank row is left above it"; band_ok(t, m)
    # 27 years with peaks 0.8 of a step (the cc ridge style): per-ridge scale keeps the shape instead of flat ▁ rows
    f = Figure(figsize=(9, 9)); ax = f.subplots()
    for i in range(27):
        d = np.exp(-(xs - 3 - i * .1) ** 2) * .8 * (1 - .5 * (i % 3 == 0)); ax.fill_between(xs, i, i + d, alpha=.8, zorder=27 - i); ax.plot(xs, i + d, "k", lw=.5, zorder=27 - i)
    ax.set_yticks(range(27)); ax.set_yticklabels([str(2000 + i) for i in range(27)]); f.tight_layout()
    t, m = render(f, 80); rows = t.split("\n"); yr = band_ok(t, m)
    assert m.get("ridge_scaled") and len(yr) == 27 and sum("█" in r or "▇" in r or "▆" in r for r in yr) >= 24, "ridgeline: 27 years labelled, each scaled to its own peak (tall blocks) with the caption"
    assert len(rows) <= 40, "ridgeline: 27 years fit in <= 40 rows"
    # P12: column heights are the mean of the smooth curve over the column (no isolated spike/hole >= 3 eighths vs both neighbours); clip caption iff data beyond xlim
    E = "▁▂▃▄▅▆▇█"
    for r in yr:
        h = [E.find(c) + 1 for c in strip(r).split("│", 1)[1].rstrip()]
        assert not any((h[i] - h[i - 1] >= 3 and h[i] - h[i + 1] >= 3) or (h[i - 1] - h[i] >= 3 and h[i + 1] - h[i] >= 3) for i in range(1, len(h) - 1)), "ridgeline: isolated 1-column spike/hole\n" + r
    assert "clipped at" not in t, "ridgeline: no clip caption when xlim holds the data"
    import pandas as pd, matplotlib.pyplot as plt; fd, ad = plt.subplots(); ad.plot(pd.date_range("2000-01-01", periods=60, freq="MS"), np.arange(60.)); assert "clipped at" not in render(fd, 80)[0], "date axis: padding is not clipping"
    fz, az = plt.subplots(figsize=(9, 8))   # Z: left-aligned in-plot ridge notes go to the right gutter, each on its own year's row
    for i in range(12): az.fill_between(np.linspace(0, 5, 99), i * .5, i * .5 + .4 * np.exp(-(np.linspace(0, 5, 99) - 1 - i * .2) ** 2), color="C0"); az.text(0, i * .5, f"{2000 + i}  n=5 med=2", va="bottom")
    az.set_yticks([i * .5 for i in range(12)], [str(2000 + i) for i in range(12)]); tz, mz = render(fz, 80)
    assert all(re.match(r"\s*(%d)\b.*%d  n=5" % (2000 + i, 2000 + i), r) for i in range(12) for r in tz.split("\n") if re.match(r"\s*%d\s*│" % (2000 + i), r)) and tz.count("n=5") == 12, "ridgeline: left-aligned notes land on neighbour rows"
    cl = lambda lim: (lambda f: (f.subplots().plot(xs, np.sin(xs)), f.axes[0].set_xlim(*lim), render(f, 60)[0])[-1])(Figure(figsize=(6, 3)))
    assert ("clipped at x=2\u20135 (figure xlim)" in cl((2, 5))) and "clipped at" not in cl((xs.min(), xs.max())), "clip caption iff data beyond xlim"
    # notes beside every baseline (some bodies span the whole row): all 27 stay, none printed over fill
    f = Figure(figsize=(9, 9)); ax = f.subplots()
    for i in range(27):
        d = np.exp(-(xs - 3 - i * .1) ** 2 / (1 + 6 * (i % 9 == 0))) * .8; ax.fill_between(xs, i, i + d, alpha=.8, zorder=27 - i); ax.text(xs[-1], i + .1, f"n={i} med=1.23", ha="right", va="bottom")
    ax.set_yticks(range(27)); ax.set_yticklabels([str(2000 + i) for i in range(27)]); f.tight_layout()
    t, m = render(f, 80); assert not m["inked"] and not m["dropped"] and all(f"n={i} med" in t for i in range(27)) and len(t.split("\n")) <= 40, "ridgeline: notes never overwrite fill, none dropped"
    # same-colour neighbours alternate fill (colour: distinct rgb, plain: █/▓); a note moved off its row carries that row's label
    f = Figure(figsize=(8, 8)); ax = f.subplots()
    for i in range(6):
        ax.fill_between(xs, i, i + np.exp(-(xs - 5) ** 2 / (1 + 40 * (i == 2))) * .8, color="C0", alpha=1, zorder=6 - i); ax.text(xs[-1], i + .1, f"n={i} med=1.23", ha="right", va="bottom")
    ax.set_yticks(range(6)); ax.set_yticklabels([str(2000 + i) for i in range(6)]); f.tight_layout()
    t, m = render(f, 80, color=True); rg = m["ridge_rgb"]; assert len(rg) == 6 and all(a != b for a, b in zip(rg, rg[1:])), "ridgeline: adjacent same-colour ridges need different fill colours"
    assert abs(__import__("trendsetter_axi.core", fromlist=["lum"]).lum(rg[0]) - __import__("trendsetter_axi.core", fromlist=["lum"]).lum(rg[1])) >= .15, "ridgeline: alternate shade too close"
    assert "▓" in render(f, 80)[0], "ridgeline: plain mode alternates █/▓"
    f = Figure(figsize=(8, 8)); ax = f.subplots()   # a left-anchored note can't use the right gutter: over a full-row body it slides and carries its row label
    for i in range(6):
        ax.fill_between(xs, i, i + np.exp(-(xs - 5) ** 2 / (1 + 40 * (i == 2))) * .8, color="C0", alpha=1, zorder=6 - i); ax.text(xs[0], i + .1, f"n={i} med=1.23", ha="left", va="bottom")
    ax.set_yticks(range(6)); ax.set_yticklabels([str(2000 + i) for i in range(6)]); f.tight_layout()
    t = render(f, 80)[0]; assert re.search(r"\d{4}: n=\d med", t), "ridgeline: displaced note must carry its row label"
    # a dark terminal_style figure patch is background, not a series: one series -> no stray key glyphs
    f = Figure(figsize=(8, 4)); f.patch.set_facecolor("#121212"); ax = f.subplots(); ax.set_facecolor("#121212"); ax.plot(np.arange(30), np.sin(np.arange(30) / 4)); f.tight_layout()
    t, m = render(f, 80); assert m["n_series"] == 1 and not re.search("[●×]", t), "dark figure patch must not become a series with stray key glyphs"
    # labels placed with ax.text next to each baseline land on that ridge's row
    f = Figure(figsize=(8, 6)); ax = f.subplots()
    for i in range(8):
        ax.fill_between(xs, i, i + np.exp(-(xs - 5) ** 2) * 1.8, alpha=.7, zorder=8 - i); ax.text(0, i + .1, f"Y{i}", va="bottom")
    f.tight_layout(); rows = render(f, 80)[0].split("\n")
    assert all(any(f"Y{i}" in r and "█" in r for r in rows) for i in range(8)), "ridgeline: in-plot ax.text label on its ridge row"

    # bar: gaps between neighbours, a value on the tallest bar, no fused half-block runs
    f = Figure(figsize=(10, 4)); ax = f.subplots(); v = 1 + np.sin(np.arange(27) / 3) ** 2 * 2.45
    ax.bar(np.arange(2000, 2027), v); ax.set_title("bars"); f.tight_layout()
    t, _ = render(f, 80); rows = t.split("\n")
    base = next(r for r in reversed(rows) if "█" in r)
    assert "██" not in base and not re.search("[▐▌]", t), "bar: fused runs"
    assert len(re.findall("█", base)) >= 20, "bar: all bars drawn"
    assert f"{v.max():.2f}" in t, "bar: value on the tallest bar"

    # text artists: missing renders blank, never "nan"
    f = Figure(figsize=(6, 3)); ax = f.subplots(); ax.plot([1, 2, 3], [1, 3, 2]); ax.text(2, 2.5, "n=5 med=nan"); ax.text(1.5, 1.2, "nan"); f.tight_layout()
    t, _ = render(f, 60)
    assert "nan" not in t.lower() and "n=5" in t, t

    # line: peak stays off the border row, >= 4 y ticks on a 10-row plot
    f = Figure(figsize=(10, 4)); ax = f.subplots(); x = np.linspace(0, 10, 300); ax.plot(x, np.sin(x) + 3 * np.exp(-(x - 7) ** 2 * 8)); f.tight_layout()
    t, _ = render(f, 80); rows = t.split("\n"); top = next(i for i, r in enumerate(rows) if "┌" in r)
    assert not BR(rows[top]) and BR("".join(rows[top + 1:top + 4])), "line: border row is clean"
    assert sum(bool(re.match(r"\s*-?\d", r)) for r in rows) >= 4, "line: y ticks"

    # barh: gap rows between bars, eighth-block ends, the value right after the end
    f = Figure(figsize=(10, 4)); ax = f.subplots(); vals = [3.45, 1.2, 2.81, 0.35, 4.02]
    ax.barh(list("abcde"), vals); f.tight_layout(); t, _ = render(f, 80); rows = [r for r in t.split("\n") if re.search("█|[▏▎▍▌▋▊▉]", r)]
    assert len(rows) == 5 and all(v in t for v in ("3.45", "1.20", "2.81", "0.35", "4.02")), "barh: five bars with values"
    assert all(re.search(r"[█▏▎▍▌▋▊▉] ?\d\.\d\d", r) for r in rows) and any(re.search("[▏▎▍▌▋▊▉] \\d", r) for r in rows), "barh: eighth-block end then the value"
    ix = [i for i, r in enumerate(t.split("\n")) if re.search("█|[▏▎▍▌▋▊▉]", r)]; assert all(b - a >= 2 for a, b in zip(ix, ix[1:])), "barh: gap row between bars"

    # violin: n/median labels in a band clear of the bodies, every label kept, medians one style
    f = Figure(figsize=(8, 5)); ax = f.subplots(); rng = np.random.default_rng(1)
    ax.violinplot([rng.normal(m, .4, 200) for m in (1, 2, 3)], showmedians=True)
    for i in range(3): ax.text(i + 1, ax.get_ylim()[0], "n=200\nmed=%d.00" % (i + 1), ha="center", va="bottom")
    f.tight_layout(); t, _ = render(f, 80); rows = t.split("\n")
    lr = [i for i, r in enumerate(rows) if "n=200" in r]; assert len(lr) == 1 and t.count("n=200") == 3 and t.count("med=") == 3, "violin: all labels kept"
    assert not re.search("[▌▐▄▀█─]", "".join(rows[lr[0]:lr[0] + 2]).split("│")[1]) and re.search("[▌▐▄▀█]", "".join(rows[:lr[0]])), "violin: labels sit in a band, not across bodies"
    assert not re.search("[⠀-⣿]", "".join(r for r in rows if "─" in r).replace("⢸", "").replace("⡇", "").replace("⣿", "")) and len(re.findall("─{4,}", t)) >= 3, "violin: median/cap rules are one glyph style"

    f = Figure(figsize=(8, 5)); ax = f.subplots(); ax.violinplot([rng.normal(2, .4, 400)], widths=.8, showextrema=False); ax.plot([.75, 1.25], [2, 2], lw=2.5); f.tight_layout()
    assert not any(0x2800 <= ord(c) < 0x2900 and c != "⠀" for r in render(f, 80)[0].split("\n") if "███" in r for c in r), "violin: a flat line on the body is a rule, not braille dots punched into the fill"
    ok = set(" ░▒▓█▀▄▌▐▚▞▏▎▍▋▊▉▁▂▃▅▆▇⠀●×▲◆■○△•·…±°µαβσ⁰¹²³⁴⁵⁶⁷⁸⁹⁺") | {chr(i) for i in range(32, 127)} | {chr(i) for i in range(0x2500, 0x2580)} | {chr(i) for i in range(0x2800, 0x2900)}   # glyphs the terminal font is known to have
    tofu = lambda t: sorted(set(strip(t)) - ok - {"\n"})
    v = render(f, 80, color=True)[0]; assert not tofu(v) and not BR(strip(v).split("\n")[3]) and "┐" not in v and "┌" not in v, ("violin: no tofu, no top/right box", tofu(v))
    assert re.search(r"48;2;[\d;]+m\x1b\[38;2;[\d;]+m─", v), "violin: median rule keeps the body colour behind it (no black cut-out)"
    # P10: violin medians vs the printed y ticks: each rule's row, read through the tick-label rows, is within 0.5 row of the true median
    rng = np.random.default_rng(3); mu = [1.8, 2.53, 2.74, 3.3]; data = [rng.normal(m, .45, 500) for m in mu]; data = [d - np.median(d) + m for d, m in zip(data, mu)]
    f = Figure(figsize=(8, 4.5)); ax = f.subplots(); ax.violinplot(data, showmedians=True, showextrema=False); ax.set_ylim(0.8, 5); f.tight_layout()
    rows = strip(render(f, 80)[0]).split("\n"); tk = [(i, float(m.group(1))) for i, r in enumerate(rows) if (m := re.match(r"\s*(\d+(?:\.\d+)?)\s*│", r))]
    (i0, v0), (i1, v1) = tk[0], tk[-1]; pr = (v0 - v1) / (i1 - i0)   # value per row from the printed ticks
    rr = [i for i, r in enumerate(rows) if "───" in r and "└" not in r][::-1]; assert len(rr) == 4, ("violin: one median rule per group", rr)
    for i, m in zip(rr, mu): assert abs(v0 - (i - i0) * pr - m) <= .5 * pr + 1e-9, ("violin: median rule > 0.5 row from its value", i, m)
    # a horizontal rule at y lands in the row whose centre is nearest y (within half a row), for violin medians and axhline alike
    from .core import Canvas as _C
    for y in np.linspace(20, 160, 23):   # a reference rule on row 0 anchors the blank-row trim
        cv = _C(560, 168, 80); cv.stroke([np.array([[100., 1.], [300., 1.]]), ], (.1, .1, .8), rule=True); cv.stroke([np.array([[100., y], [300., y]])], (.8, .1, .1), rule=True)
        rr = [i for i, l in enumerate(cv.render().split("\n")) if "───" in l]
        assert abs((rr[-1] + .5) * cv.ch - y) <= cv.ch / 2 + 1e-6, ("rule row off", y, rr)
    # line: steep runs take both dot columns of the cell (no stray single-dot fragments)
    from .core import Canvas
    rc = Canvas(560, 168, 80)._line_dots(np.array([[10., 0.], [14., 100.]]), None)
    assert all({0, 1} <= {c % 2 for c in rc[rc[:, 0] == r, 1]} for r in np.unique(rc[:, 0])), "line: steep stroke is two dots wide"

    # ridgeline with a coloured outline on each body: the fill is the shape, no braille outline punched through it, no baseline rules
    f = Figure(figsize=(8, 8)); ax = f.subplots()
    for i in range(12):
        d = np.exp(-(xs - 3 - i * .4) ** 2) * .8; ax.axhline(i, color="#666666", lw=.4); ax.fill_between(xs, i, i + d, color="#29799a"); ax.plot(xs, i + d, color="#153848", lw=.7)
    ax.set_yticks(range(12)); ax.set_yticklabels([str(2000 + i) for i in range(12)]); f.tight_layout()
    t, _ = render(f, 80)
    body = "\n".join(r.split("│")[1] for r in t.split("\n") if re.match(r"\s*20\d\d\s*│", r)); assert re.search("[▁-█]", body) and not BR(body) and "─" not in body, t+"ridgeline: coloured outline/baseline must not hollow the fill"
    # calendar: every finite artist cell is exactly one shaded text cell (the lowest bin `·` is data, blank is missing)
    g = np.full((7, 53), np.nan); g[0, :52] = np.linspace(2.3, 2.75, 52); g[0, [3, 30, 51]] = 2.3; f = Figure(figsize=(13, 3.5)); ax = f.subplots(); im = ax.imshow(np.ma.masked_invalid(g), cmap="viridis", aspect="equal"); ax.set_yticks(range(7)); ax.set_yticklabels("Mon Tue Wed Thu Fri Sat Sun".split()); f.colorbar(im, ax=ax); f.tight_layout()
    mon = next(r for r in strip(render(f, 80)[0]).split("\n") if r.lstrip().startswith("Mon ")); assert sum(c in "░▒▓█" for c in mon[5:]) == int(np.isfinite(g).sum()), "calendar: finite cells == shaded cells"

    # skewed histogram: tiny tail bins (< half a text row) must still show ink, and the x range must cover every bin edge
    v = np.concatenate([np.random.default_rng(1).normal(2.5, .6, 1300), [.4, .5, 4.4, 4.5, 4.62]]); f = Figure(figsize=(9, 4.5)); ax = f.subplots(); ax.hist(v, bins=np.arange(.2, 4.9, .2)); f.tight_layout()
    t, _ = render(f, 80); lo, hi = ax.get_xlim(); assert lo <= v.min() and hi >= v.max(), "hist: x range covers data"
    assert not bars_without_ink(f, t), t + "hist: every bar with height > 0 must have ink"
    # contiguous bins touch: the row above the axis line has no blank column between the first and last bin
    f = Figure(figsize=(9, 4.5)); ax = f.subplots(); ax.hist(np.random.default_rng(2).normal(0, 1, 4000), bins=np.linspace(-3, 3, 16), edgecolor="#121212"); f.tight_layout()
    t, _ = render(f, 80); L = t.split("\n"); base = L[next(i for i, l in enumerate(L) if "└" in l) - 1].split("│")[1].strip()
    assert base and " " not in base, t + "hist: adjacent bins must touch (no blank column between contiguous bins)"

    print("mpl ok")


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv: _test()
