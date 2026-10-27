"""What a render produced and what it lost."""
from dataclasses import dataclass

from .cells import width

MATERIAL = ("lost_artist", "lost_series", "series_label")   # the text misrepresents the chart: strict=True refuses these
FIGURE = dict(color=True, artist_roles=True, source_values=True, artist_losses=True)
SVG = dict(color=True, artist_roles=False, source_values=False, artist_losses=False)   # SVG has shapes, not artists or data


class RenderLossError(ValueError):
    """Raised by render(..., strict=True) when the text would misrepresent the chart. `.result` is the full RenderResult."""
    def __init__(self, result):
        self.result = result
        super().__init__("render loses data: " + "; ".join(f"{l['kind']} {l['what']}: {l['detail']}" for l in result.losses if l["material"]))


@dataclass
class RenderResult:
    text: str                  # the chart, as render_figure / render_svg return it
    dimensions: dict           # cols budget, width (widest line) and height (lines), in terminal cells
    series: list               # one dict per series, from the source data (SVG: values unavailable)
    scales: list               # per axes: title, x and y label, scale kind, range
    warnings: list             # notes about how the input was read
    losses: list               # dicts kind/what/detail/material: everything the text does not show
    supported_features: dict   # what this kind of input lets the renderer know

    def __str__(self): return self.text

    def summary(self):
        """Compact text for an agent: scales, series values from the source data, losses. Far fewer tokens than the chart.

        Lines list every point up to 16, else about 10 samples interpolated at nice x positions plus the exact min and
        max; lines that share their x positions share one `at x:` row. Bars list every bar up to 40; equal-width
        edge-to-edge bars read as a histogram (bins, counts, peak). Heatmaps up to 36 cells come in full, larger ones as row and column means.
        Scatters give the mean, Pearson r and points far off the trend line. Numbers keep about 1/60 of the axis span
        and are rounded presentation strings. NaN gaps, masked points and hidden artists are not yet excluded. `losses:`
        lists render losses only; errorbars, pies, contours and other undescribed artists are left out without notice."""
        multi = len(self.scales) > 1
        lines, shared = [], {}
        for sc in self.scales:
            p = f"axes {sc['axes']} " if multi else ""
            if sc["title"]: lines.append(f"{p}title: {sc['title']}")
            for k in "xy":
                a = sc.get(k)
                if a and (a["label"] or a["scale"] not in ("linear", "category")):   # linear and category axes: the label alone; the values say the rest
                    lines.append(f"{p}{k}: " + ", ".join(v for v in (a["label"], a["scale"] != "linear" and a["scale"], a["scale"] not in ("linear", "category") and a.get("range")) if v))
        if not self.supported_features["source_values"]: lines.append("values unavailable: SVG input carries shapes, not data")
        for s in self.series:
            head = " ".join(v for v in (s["kind"], s["name"] and repr(s["name"]), multi and f"axes {s['axes']}", s["key"] and f"key {s['key']}", s["values"] is None and s["color"]) if v)
            if s["kind"] == "line" and "at" in s:   # lines sharing x positions share one row of them
                at = (s["axes"], tuple(s["at"]))
                if at not in shared:
                    shared[at] = [f"{'axes ' + str(s['axes']) + ' ' if multi else ''}lines at x: " + " ".join(s["at"])]
                    lines.append(shared[at])
                ext = " ".join(v for v in s["values"] if v.startswith(("min ", "max ")))
                name = " ".join(v for v in (s["name"] and repr(s["name"]), s["key"], s["sampled"] and f"n={s['n']}") if v)
                shared[at].append(f"  {name or 'y'}: " + " ".join(s["ys"]) + (f" ({ext})" if ext else ""))
                continue
            parts = [f"{k}={s[k]}" for k in ("n", "shape", "x", "y", "z", "missing", "mean", "r") if s.get(k) not in (None, "")
                     and not (k == "missing" and s[k] == 0) and not (k == "n" and s["kind"] == "heatmap")]
            if s["kind"] == "histogram":
                lines.append(" ".join([head, s["bins"], f"peak {s['peak']}", "counts:", *s["values"]]))
                continue
            lines.append(" ".join([head, *parts, *(s["values"] or [])]))
            if s.get("outliers"): lines.append(f"  outliers {s['outliers']}; others {s['rest']}")
            if s.get("grid"): lines += [f"  cols: {s['cols']}", *(f"  {g}" for g in s["grid"])]
            for k in ("row_means", "col_means"):
                if s.get(k): lines.append(f"  {k.replace('_', ' ')}: {s[k]}")
        lines.append("losses: " + ("; ".join(f"{l['kind']} {l['what']}: {l['detail']}" for l in self.losses) or "none"))
        lines += [f"warning: {w}" for w in self.warnings]
        return "\n".join(l for x in lines for l in (x if isinstance(x, list) else [x]))


def build(text, meta, cols, series, scales, losses, features):
    """The RenderResult of a render: `losses` from the adapter (artists, clipping) plus what the text layout dropped."""
    seen = set()
    for role, s, why in [(r, s, f"dropped ({w})") for r, s, w in meta["dropped"]] + [(r, s, "truncated") for r, s in meta["truncated"]]:
        if (role, s, why) in seen: continue
        seen.add((role, s, why))
        legend = role == "legend"   # a series name the reader cannot see
        losses.append(dict(kind="series_label" if legend else "text", what=f"{role} {s!r}", detail=why))
    losses += [dict(kind="unsupported", what=u, detail="drawn unclipped") for u in dict.fromkeys(meta.get("unsupported", []))]
    for l in losses: l["material"] = l["kind"] in MATERIAL
    warnings = [f"{meta['guessed']} axis-aligned light strokes taken for gridlines by colour, not drawn"] if meta["guessed"] else []
    rows = text.split("\n")
    return RenderResult(text, dict(cols=cols, width=max(map(width, rows)), height=len(rows)), series, scales, warnings, losses, features)


def svg_series(meta):
    """Series of an SVG render: what the canvas drew, keyed by colour. SVG has no data, so no values; a series that drew nothing visible is a loss."""
    series = [dict(name=None, kind="/".join(s["kinds"]) or "legend", axes=0, key=s["key"], color="#%02x%02x%02x" % tuple(round(v * 255) for v in s["rgb"]), values=None)
              for s in meta["series"] if s["kinds"]]
    lost = [dict(kind="lost_series", what=f"{s['kind']} {s['color']}", detail="drawn with no visible cell")
            for s, m in zip(series, [m for m in meta["series"] if m["kinds"]]) if m["id"] not in meta["drawn"]]
    title = next((line for role, line in meta["placed"] if role == "title"), "")
    return series, [dict(axes=0, title=title)], lost
