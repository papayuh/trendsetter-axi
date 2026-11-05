"""Byte/loss regression matrix against an archived source tree.

PYTHONPATH=.scratch/speed-base/src python benchmarks/render_identity.py --svg-dir .scratch/identity-svg --output .scratch/base-identity.json
PYTHONPATH=src python benchmarks/render_identity.py --svg-dir .scratch/identity-svg --output .scratch/head-identity.json
python benchmarks/render_identity.py --compare .scratch/base-identity.json .scratch/head-identity.json

Requires the gallery extra and its SVG exporters. No charts may be skipped.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys

from matplotlib.lines import Line2D

# Make development fixtures importable without overriding the selected package.
sys.path.append(str(Path(__file__).resolve().parents[1]))


class DeferredLine(Line2D):
    def __init__(self):
        super().__init__([0, 9], [0, 1])
        self.initial_ylim = None

    def draw(self, renderer):
        if self.initial_ylim is None:
            self.initial_ylim = self.axes.get_ylim()
            self.set_ydata([self.initial_ylim[1] * .8] * 2)
        super().draw(renderer)


def quiver():
    from matplotlib.figure import Figure

    ax = Figure().subplots()
    ax.quiver(range(10), [1] * 9 + [0], [0] * 10, [1] * 9 + [3], angles="xy", scale_units="xy")
    return ax.figure


def custom_artist():
    from matplotlib.figure import Figure

    ax = Figure().subplots()
    ax.add_line(DeferredLine())
    ax.autoscale_view()
    return ax.figure


def records(svg_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    import numpy as np
    from examples import demo
    from examples.gallery import CHARTS
    from examples.compact_demo import NAMES
    from trendsetter_axi import render, render_compact, render_figure

    cases = [(c["id"], c["lib"], c["make"]) for c in CHARTS]
    cases += [("demo-" + name, "matplotlib", getattr(demo, name))
              for name in ("line", "bar", "scatter", "heatmap", "big", "cjk")]

    def ecdf(style):
        ax = Figure(figsize=(7.5, 3.4)).subplots()
        for name, counts in [("A", [50, 45, 5]), ("B", [50, 40, 10])]:
            ax.plot([100, 160, 1000], np.cumsum(counts), drawstyle=style, label=name)
        ax.set(xlim=(0, 1100), ylim=(0, 100), title="Latency ECDF", xlabel="ms", ylabel="%")
        ax.legend(frameon=False)
        return ax.figure

    def ranking():
        ax = Figure(figsize=(7.5, 3.4)).subplots()
        ax.barh(NAMES, range(-9, 1))
        ax.invert_yaxis()
        ax.set(title="Team change", xlabel="pp")
        return ax.figure

    cases += [("semantics-" + style, "matplotlib", lambda style=style: ecdf(style))
              for style in ("steps-post", "default")]
    cases += [("compact-ranking", "matplotlib", ranking),
              ("deferred-quiver", "matplotlib", quiver),
              ("deferred-custom", "matplotlib", custom_artist)]
    # The SVG example uses a matplotlib-generated SVG as its source.
    def svg_example():
        fig = demo.line()
        try:
            with matplotlib.rc_context({"svg.fonttype": "none"}):
                buf = io.StringIO()
                fig.savefig(buf, format="svg", dpi=72)
            return buf.getvalue()
        finally:
            plt.close(fig)
    cases += [("demo-svg", "svg", svg_example)]

    output = {}

    def record(key, result):
        data = result.text.encode("utf-8")
        output[key] = dict(text=result.text, bytes=len(data),
                           sha256=hashlib.sha256(data).hexdigest(), losses=result.losses)

    svg_dir.mkdir(parents=True, exist_ok=True)
    for name, lib, make in cases:
        svg_path = svg_dir / (name + ".svg")
        obj = svg_path.read_text() if lib in ("svg", "plotly", "altair") and svg_path.exists() else make()
        try:
            if isinstance(obj, str):
                pass
            elif lib == "plotnine":
                obj = obj.draw()
            elif lib == "plotly":
                obj = obj.to_image(format="svg").decode()
            elif lib == "altair":
                import vl_convert as vlc
                obj = vlc.vegalite_to_svg(obj.to_dict())
            if isinstance(obj, str) and not svg_path.exists():
                # Exporters use random element IDs which can appear verbatim in
                # loss captions. Both versions must receive the exact same SVG.
                svg_path.write_text(obj)
            for cols in (60, 80):
                for color in (False, True):
                    for ascii in (False, True):
                        rows = 18 if name.startswith(("semantics-", "deferred-")) or name == "compact-ranking" else None
                        result = render(obj, cols=cols, color=color, ascii=ascii, rows=rows)
                        key = f"{name}/{cols}/{color}/{ascii}"
                        record(key, result)
                        if not isinstance(obj, (str, bytes)) and not ascii and rows is None:
                            assert render_figure(obj, cols=cols, color=color).encode() == result.text.encode(), key
                        if name == "compact-ranking":
                            for max_rows in (8, 11):
                                compact = render_compact(obj, cols=cols, max_rows=max_rows, color=color, ascii=ascii)
                                record(f"{key}/compact-{max_rows}", compact)
        finally:
            plt.close("all")
        print(name, file=sys.stderr, flush=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--svg-dir", type=Path)
    parser.add_argument("--compare", nargs=2, type=Path)
    args = parser.parse_args()
    if args.compare:
        before, after = [json.loads(p.read_text()) for p in args.compare]
        assert before.keys() == after.keys(), "case matrix differs"
        changed = [key for key in before if before[key] != after[key]]
        assert not changed, f"bytes/losses differ: {changed}"
        print(f"{len(before)} renders: identical UTF-8 bytes and RenderResult losses")
    else:
        if args.output is None or args.svg_dir is None:
            parser.error("--output and --svg-dir (or --compare) are required")
        args.output.write_text(json.dumps(records(args.svg_dir), ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
