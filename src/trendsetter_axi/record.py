"""Experimental post-transform records, collected by mpl.describe without drawing."""


def from_figure(fig):
    """Return a JSON-safe record of eligible source geometry, not inferred intent."""
    return _collect_figure(fig).result


def _collect_figure(fig):
    from . import mpl

    collector = _Collector()
    meta = {"series": []}
    mpl.describe(fig, meta, record=collector)
    title = getattr(fig, '_suptitle', None)
    collector.result.update(title=mpl.clean_text(title.get_text()) if title is not None and title.get_visible() else '',
                            not_described=[list(item) for item in meta["record_not_described"]], hidden=meta["hidden"])
    collector.result["unavailable"] += [f"{n} {kind}: reader unavailable" for kind, n in meta["record_not_described"]]
    return collector


class _Collector:
    def __init__(self):
        self.artists = []
        self.result = dict(version=1, source="matplotlib", axes=[], marks=[], declared={}, unavailable=[
            "Subject counts and sample support require a records table; duplicated subjects can draw identical curves.",
            "Interval meaning, totals and pairing intent require author declarations."])

    def axes(self, ax, j, scale):
        from . import mpl

        item = dict(scale)
        for k in "xy":
            axis = getattr(ax, k + "axis")
            item[k] = dict(scale[k], range=list(map(float, getattr(ax, f"get_{k}lim")())))
            if scale[k]["scale"] == "category":
                item[k]["mapping"] = dict(axis.units._mapping)
            if scale[k]["scale"] == "date":
                item[k].update(units="matplotlib date days", timezone=str(axis.units or "UTC"))
            item[k]["ticks"] = [dict(value=float(v), label=mpl._fmt(axis, v)) for v in axis.get_ticklocs()]
        self.result["axes"].append(item)

    def add(self, j, a, kind, name=None, **values):
        from . import mpl

        def plain(v):
            if isinstance(v, dict): return {k: plain(x) for k, x in v.items()}
            if isinstance(v, (list, tuple, mpl.np.ndarray)):
                return [plain(x) for x in v]
            if isinstance(v, (float, mpl.np.floating)): return float(v) if mpl.np.isfinite(v) else None
            if isinstance(v, mpl.np.integer): return int(v)
            return v
        marks = self.result["marks"]
        marks.append(dict(id=f"m{len(marks)}", axes=j, kind=kind, name=name or mpl._name(a, {}), **plain(values)))
        self.artists.append(a)

    def geometry(self, a, *, raw=False):
        from . import mpl
        from matplotlib.transforms import IdentityTransform

        tr = a.get_data_transform() if hasattr(a, 'get_data_transform') else a.get_transform()
        reason = f"non-data transform {type(tr).__name__}" if raw and tr is not a.axes.transData else None
        if isinstance(a, mpl.Rectangle) and a.get_angle():
            reason = f"rectangle rotation {a.get_angle()} degrees"
        if isinstance(a, mpl.Collection):
            offset_tr = a.get_offset_transform()
            if mpl.np.any(a.get_offsets()) or not isinstance(offset_tr, IdentityTransform):
                reason = f"collection offsets with transform {type(offset_tr).__name__}"
            elif len(a.get_transforms()):
                reason = 'per-path transforms'
        if reason:
            self.result['unavailable'].append(f"{mpl._name(a, {}) or type(a).__name__}: geometry unavailable; {reason}")
        return reason is None

    def points(self, j, a, raw, xy, kind, name, **extra):
        from . import mpl

        if isinstance(a, mpl.Line2D) and not self.geometry(a, raw=True): return
        raw = mpl.np.ma.filled(mpl.np.ma.asarray(raw, float), mpl.np.nan).reshape(-1, 2)
        valid = mpl.np.isfinite(raw).all(1)
        indices = mpl.np.flatnonzero(valid)
        breaks = (mpl.np.flatnonzero(mpl.np.diff(indices) != 1) + 1).tolist()
        interp = {"default": "linear", "steps-pre": "step-pre", "steps-post": "step-post", "steps-mid": "step-mid"}
        self.add(j, a, kind, name, x=xy[:, 0], y=xy[:, 1], breaks=breaks, missing=int((~valid).sum()),
                 interp=interp.get(a.get_drawstyle(), "unavailable") if kind == "line" else "none", **extra)

    def polygon(self, j, a, data):
        from . import mpl

        if not self.geometry(a): return
        np = mpl.np
        parts, polygons = [], []
        step = getattr(a, "_step", None)
        for path in a.get_paths():
            v = data(a.get_transform(), path.vertices)
            polygons.append(v)
            n = (len(v) - 3) // 2
            lo, hi = v[1:n + 1], v[n + 2:-1][::-1]
            if (getattr(a, "t_direction", None) != "x" or len(v) != 2 * n + 3 or n < 1 or
                    not np.isfinite(v).all() or lo.shape != hi.shape or not np.array_equal(lo[:, 0], hi[:, 0])):
                continue
            x, l, h = lo[:, 0], lo[:, 1], hi[:, 1]
            if step in ("pre", "post"):
                idx = np.r_[0, np.arange(1, n, 2)] if step == "pre" else np.arange(0, n, 2)
                x, l, h = x[::2], l[idx], h[idx]
            elif step == "mid":
                knots = [x[0]]
                for mid in x[1:-1:2]: knots.append(2 * mid - knots[-1])
                if not np.isclose(knots[-1], x[-1]): continue
                x, l, h = np.asarray(knots), l[::2], h[::2]
            if getattr(a, '_interpolate', False):
                if step: continue  # Interpolated where-boundaries are straight, not step intervals.
                if v[0, 0] != x[0]: x, l, h = np.r_[v[0, 0], x], np.r_[v[0, 1], l], np.r_[v[0, 1], h]
                end = v[n + 1]
                if end[0] != x[-1]: x, l, h = np.r_[x, end[0]], np.r_[l, end[1]], np.r_[h, end[1]]
            if not step and np.any(((l[1:] < h[1:]) & (l[:-1] > h[:-1])) |
                                   ((l[1:] > h[1:]) & (l[:-1] < h[:-1]))): continue
            if len(x) > 1 and not ((np.diff(x) > 0).all() or (np.diff(x) < 0).all()): continue
            parts.append(dict(x=x, lo=np.minimum(l, h), hi=np.maximum(l, h)))
        if len(parts) == len(polygons) and parts:
            breaks = np.cumsum([len(p["x"]) for p in parts])[:-1].tolist()
            self.add(j, a, "band", **{k: np.concatenate([p[k] for p in parts]) for k in ("x", "lo", "hi")},
                     breaks=breaks, interp="step-" + step if step else "linear")
        else:
            self.add(j, a, "area", polygons=polygons)
            self.result["unavailable"].append(f"{mpl._name(a, {}) or 'area'}: paired bounds unavailable; raw polygons retained")
