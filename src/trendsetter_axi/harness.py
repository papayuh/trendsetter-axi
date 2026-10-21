"""Export each gallery chart (mpl figure / plotnine / plotly / altair) and render it through
mpl.py (path B) and/or svg.py (path C). Plotly export needs kaleido plus a Chrome (set BROWSER_PATH if
Chrome is not on PATH); altair export needs vl-convert-python."""
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from . import mpl as B, svg as C

MPL_LIBS = ("matplotlib", "seaborn", "pandas", "plotnine")
CELL_PX = 8  # SVG export: px per text column (rows are 2x)


def _fig(chart):
    obj = _make(chart)
    if chart["lib"] == "plotnine":
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore"); obj = obj.draw()
    return obj


_KALEIDO = []


def _kaleido():
    if not _KALEIDO:
        import kaleido, warnings
        kaleido.start_sync_server(silence_warnings=True); _KALEIDO.append(1)
        warnings.filterwarnings("ignore", message="The kopts argument")


def _make(chart):
    obj = chart["make"]()
    if isinstance(obj, tuple): chart["desc_full"] = obj[1]; obj = obj[0]
    return obj


def _png(fig, dpi):
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=dpi); return buf.getvalue()


def svg_size(cols): return cols * CELL_PX, round(cols * 0.75 / 2) * 2 * CELL_PX


def export_web(chart, cols):
    """plotly/altair -> (svg text, geometry-matched png bytes, obj)."""
    obj = _make(chart)
    W, H = svg_size(cols)
    if chart["lib"] == "plotly":
        import plotly.io as pio
        _kaleido()
        nl = 0
        if obj.layout.title.text:  # pre-wrap to the grid, one text row (2 cells) of margin per line
            import textwrap
            ls = textwrap.wrap(obj.layout.title.text.replace("<br>", " "), max(12, cols - 8)); nl = len(ls)
            obj.update_layout(title_text="<br>".join(ls), title_font_size=CELL_PX * 2 - 2)
        obj.update_layout(width=W, height=H, margin=dict(l=8, r=8, t=max(40, 2 * CELL_PX * nl + 24) if obj.layout.title.text else 8, b=4 * CELL_PX))  # b: 2 rows so x tick labels get their own row below the plot; default 80/100px margins eat a 40-col export
        obj.update_xaxes(automargin=True, tickangle=0); obj.update_yaxes(automargin=True, tickangle=0)  # rotated labels would squash the plot; core drops colliding ticks
        return pio.to_image(obj, format="svg").decode(), pio.to_image(obj, format="png"), obj
    import vl_convert as vlc
    spec = obj.to_dict()
    spec.setdefault("config", {}).setdefault("axis", {})["labelAngle"] = 0
    t = spec.get("title")
    if isinstance(t, str) or isinstance(t, dict) and isinstance(t.get("text"), str):  # vega lays a title out as one line, however wide: pre-wrap so it reserves a row per line
        import textwrap
        lines = textwrap.wrap(t if isinstance(t, str) else t["text"], max(12, cols - 8))
        spec["title"] = {"text": lines} if isinstance(t, str) else {**t, "text": lines}
    cfg = spec["config"].setdefault("view", {})
    n = len(spec.get("hconcat", [])) or 1   # side-by-side panels share the width: otherwise the svg is n times wider than the grid and every row of text shrinks against it
    pw = (W - 40) // n - 60 if n > 1 else W - 100
    cfg.update(continuousWidth=pw, continuousHeight=H - 80)
    spec["config"]["view"].setdefault("discreteWidth", pw)
    return vlc.vegalite_to_svg(spec), vlc.vegalite_to_png(spec, scale=1), obj


def renders(chart, widths=(80, 40), mpl_svg=(80,)):
    """Yield dict(path, cols, text, meta) for every applicable path x width."""
    lib = chart["lib"]
    for cols in widths:
        if lib in MPL_LIBS:
            fig = _fig(chart)
            text, meta = B.render(fig, cols)
            plt.close(fig)
            yield dict(path="B", cols=cols, text=text, meta=meta)
            if cols in mpl_svg:
                fig = _fig(chart); B.prepare(fig, cols)
                with matplotlib.rc_context({"svg.fonttype": "none"}):
                    buf = io.StringIO(); fig.savefig(buf, format="svg", dpi=72)
                plt.close(fig)
                text, meta = C.render(buf.getvalue(), cols)
                yield dict(path="C", cols=cols, text=text, meta=meta)
        else:
            svg, _, _ = export_web(chart, cols)
            text, meta = C.render(svg, cols)
            yield dict(path="C", cols=cols, text=text, meta=meta)
