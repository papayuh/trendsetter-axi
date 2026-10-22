"""What a render produced and what it lost."""
from dataclasses import dataclass

from .cells import width

MATERIAL = ("lost_artist", "lost_series", "clipped_data", "series_label")   # the text misrepresents the chart: strict=True refuses these
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
        """Compact text for an agent: scales, series values from the source data, losses. Far fewer tokens than the chart."""
        multi = len(self.scales) > 1
        lines = []
        for sc in self.scales:
            p = f"axes {sc['axes']} " if multi else ""
            if sc["title"]: lines.append(f"{p}title: {sc['title']}")
            for k in "xy":
                a = sc.get(k)
                if a: lines.append(f"{p}{k}: " + ", ".join(v for v in (a["label"], a["scale"], a.get("range") or f"{a.get('categories')} categories") if v))
        if not self.supported_features["source_values"]: lines.append("values unavailable: SVG input carries shapes, not data")
        for s in self.series:
            head = " ".join(v for v in (s["kind"], s["name"] and repr(s["name"]), multi and f"axes {s['axes']}", s["key"] and f"key {s['key']}", s["values"] is None and s["color"]) if v)
            parts = [f"{k}={s[k]}" for k in ("n", "shape", "x", "y", "z", "missing") if s.get(k) not in (None, "")]
            lines.append(" ".join([head, *parts, *(s["values"] or [])]))
        lines.append("losses: " + ("; ".join(f"{l['kind']} {l['what']}: {l['detail']}" for l in self.losses) or "none"))
        lines += [f"warning: {w}" for w in self.warnings]
        return "\n".join(lines)


def build(text, meta, cols, series, scales, losses, features):
    """The RenderResult of a render: `losses` from the adapter (artists, clipping) plus what the text layout dropped."""
    seen = set()
    for role, s, why in [(r, s, f"dropped ({w})") for r, s, w in meta["dropped"]] + [(r, s, "truncated") for r, s in meta["truncated"]]:
        if (role, s, why) in seen: continue
        seen.add((role, s, why))
        legend = role == "legend"   # a series name the reader cannot see
        losses.append(dict(kind="series_label" if legend else "text", what=f"{role} {s!r}", detail=why, material=legend))
    losses += [dict(kind="unsupported", what=u, detail="drawn unclipped", material=False) for u in dict.fromkeys(meta.get("unsupported", []))]
    warnings = [f"{meta['guessed']} axis-aligned light strokes taken for gridlines by colour, not drawn"] if meta["guessed"] else []
    rows = text.split("\n")
    return RenderResult(text, dict(cols=cols, width=max(map(width, rows)), height=len(rows)), series, scales, warnings, losses, features)


def svg_series(meta):
    """Series of an SVG render: what the canvas drew, keyed by colour. SVG has no data, so no values; a series that drew nothing visible is a loss."""
    series = [dict(name=None, kind="/".join(s["kinds"]) or "legend", axes=0, key=s["key"], color="#%02x%02x%02x" % tuple(round(v * 255) for v in s["rgb"]), values=None)
              for s in meta["series"] if s["kinds"]]
    lost = [dict(kind="lost_series", what=f"{s['kind']} {s['color']}", detail="drawn with no visible cell", material=True)
            for s, m in zip(series, [m for m in meta["series"] if m["kinds"]]) if m["id"] not in meta["drawn"]]
    title = next((line for role, line in meta["placed"] if role == "title"), "")
    return series, [dict(axes=0, title=title)], lost
