"""SVG -> core.Canvas. Handles plain SVG such as plotly, Vega/Altair or
matplotlib (svg.fonttype=none) output."""
import base64, io, re
import xml.etree.ElementTree as ET
import numpy as np
from .core import Canvas, sup
from .cells import width

NS = re.compile(r"\{.*?\}")
NAMED = {"black": (0, 0, 0), "white": (1, 1, 1), "red": (1, 0, 0), "green": (0, .5, 0), "blue": (0, 0, 1),
         "gray": (.5, .5, .5), "grey": (.5, .5, .5), "orange": (1, .65, 0), "steelblue": (.27, .51, .71),
         "darkgray": (.66, .66, .66), "lightgray": (.83, .83, .83), "currentcolor": (0, 0, 0)}
INHERIT = ("fill", "stroke", "fill-opacity", "stroke-opacity", "stroke-width", "stroke-dasharray",
           "font-size", "text-anchor", "visibility", "dominant-baseline")


def color(v):
    if v is None: return None
    v = v.strip().lower()
    if v in ("none", "transparent", "") or v.startswith("url("): return None
    if v.startswith("#"):
        h = v[1:]
        if len(h) in (3, 4): h = "".join(c * 2 for c in h[:3])
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    m = re.match(r"rgba?\(([^)]*)\)", v)
    if m:
        p = [float(x.strip().rstrip("%")) for x in m.group(1).split(",")]
        return tuple(x / 255 for x in p[:3]) + ((p[3],) if len(p) > 3 else ())
    return NAMED.get(v, (0, 0, 0))


def parse_transform(s):
    M = np.eye(3)
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", s or ""):
        a = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        if name == "translate": T = np.array([[1, 0, a[0]], [0, 1, a[1] if len(a) > 1 else 0], [0, 0, 1]])
        elif name == "scale": T = np.diag([a[0], a[1] if len(a) > 1 else a[0], 1])
        elif name == "matrix": T = np.array([[a[0], a[2], a[4]], [a[1], a[3], a[5]], [0, 0, 1]])
        elif name == "rotate":
            t = np.radians(a[0]); c, s_ = np.cos(t), np.sin(t)
            T = np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]])
            if len(a) == 3: T = np.array([[1, 0, a[1]], [0, 1, a[2]], [0, 0, 1]]) @ T @ np.array([[1, 0, -a[1]], [0, 1, -a[2]], [0, 0, 1]])
        else: continue
        M = M @ T
    return M


def path_d(d):
    """SVG path data -> list of (polyline ndarray, closed). Curves/arcs flattened."""
    toks = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", d or "")
    out, cur, start, pos, i, cmd, prev_ctrl = [], [], (0.0, 0.0), (0.0, 0.0), 0, None, None

    def num():
        nonlocal i
        i += 1; return float(toks[i - 1])
    while i < len(toks):
        if toks[i].isalpha(): cmd = toks[i]; i += 1
        if cmd is None: break
        rel = cmd.islower(); C = cmd.upper(); x0, y0 = pos
        if C == "Z":
            if cur: cur.append(start); out.append((np.array(cur), True)); cur = []
            pos = start; cmd = None; continue
        if C == "M":
            if cur: out.append((np.array(cur), False))
            x, y = num(), num(); pos = (x0 + x, y0 + y) if rel else (x, y); start = pos; cur = [pos]
            cmd = "l" if rel else "L"; continue
        if C == "L": x, y = num(), num(); pos = (x0 + x, y0 + y) if rel else (x, y); cur.append(pos)
        elif C == "H": x = num(); pos = (x0 + x if rel else x, y0); cur.append(pos)
        elif C == "V": y = num(); pos = (x0, y0 + y if rel else y); cur.append(pos)
        elif C in "CSQT":
            if C == "C": p = [num() for _ in range(6)]
            elif C == "S":
                p = [num() for _ in range(4)]
                c1 = (2 * x0 - prev_ctrl[0], 2 * y0 - prev_ctrl[1]) if prev_ctrl else (x0, y0)
                p = [c1[0] - (x0 if rel else 0), c1[1] - (y0 if rel else 0)] + p
            elif C == "Q": p = [num() for _ in range(4)]
            else:
                p = [num(), num()]
                c1 = (2 * x0 - prev_ctrl[0], 2 * y0 - prev_ctrl[1]) if prev_ctrl else (x0, y0)
                p = [c1[0] - (x0 if rel else 0), c1[1] - (y0 if rel else 0)] + p
            pts = np.array(p).reshape(-1, 2) + (np.array([x0, y0]) if rel else 0)
            ctrl = np.vstack([[x0, y0], pts])
            t = np.linspace(0, 1, 9)[1:, None]
            if len(ctrl) == 4:
                b = ((1 - t) ** 3) * ctrl[0] + 3 * ((1 - t) ** 2) * t * ctrl[1] + 3 * (1 - t) * t * t * ctrl[2] + t ** 3 * ctrl[3]
            else:
                b = ((1 - t) ** 2) * ctrl[0] + 2 * (1 - t) * t * ctrl[1] + t * t * ctrl[2]
            cur.extend(map(tuple, b)); pos = tuple(ctrl[-1]); prev_ctrl = tuple(ctrl[-2])
            continue
        elif C == "A":
            rx, ry, phi, fa, fs, x, y = (num() for _ in range(7))
            x1, y1 = (x0 + x, y0 + y) if rel else (x, y)
            cur.extend(arc((x0, y0), (x1, y1), rx, ry, phi, fa, fs)); pos = (x1, y1)
        prev_ctrl = None
    if cur: out.append((np.array(cur), False))
    return out


def arc(p0, p1, rx, ry, phi, fa, fs, n=16):
    # endpoint -> center parameterization per the SVG 1.1 spec, implementation notes F.6.5 (written from the spec)
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0 or p0 == p1: return [p1]
    c, s = np.cos(np.radians(phi)), np.sin(np.radians(phi))
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1p, y1p = c * dx + s * dy, -s * dx + c * dy
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1: rx, ry = rx * np.sqrt(lam), ry * np.sqrt(lam)
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    k = np.sqrt(max(0, num / (rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2))) * (-1 if fa == fs else 1)
    cxp, cyp = k * rx * y1p / ry, -k * ry * x1p / rx
    cx, cy = c * cxp - s * cyp + (p0[0] + p1[0]) / 2, s * cxp + c * cyp + (p0[1] + p1[1]) / 2
    ang = lambda u, v: np.arctan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1])
    t1 = ang((1, 0), ((x1p - cxp) / rx, (y1p - cyp) / ry))
    dt = ang(((x1p - cxp) / rx, (y1p - cyp) / ry), ((-x1p - cxp) / rx, (-y1p - cyp) / ry))
    if not fs and dt > 0: dt -= 2 * np.pi
    elif fs and dt < 0: dt += 2 * np.pi
    t = t1 + dt * np.linspace(0, 1, max(2, int(n * abs(dt) / np.pi) + 1))[1:]
    return list(zip(cx + rx * np.cos(t) * c - ry * np.sin(t) * s, cy + rx * np.cos(t) * s + ry * np.sin(t) * c))


def styles(el, parent):
    st = {k: v for k, v in parent.items() if k in INHERIT}
    for k, v in el.attrib.items():
        st[NS.sub("", k)] = v
    for part in (el.get("style") or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1); st[k.strip()] = v.strip()
    if "font" in st:  # matplotlib: "font: 10px 'DejaVu Sans'"
        m = re.search(r"([\d.]+)px", st["font"])
        if m: st["font-size"] = m.group(1)
    return st


def role_of(classes):
    c = " ".join(classes)
    if "legend" in c: return "legend"
    if re.search(r"tick|axis-label|role-axis-label|xtick|ytick", c): return "tick"
    if re.search(r"gtitle|role-title|title", c): return "title" if "axis" not in c and "xtitle" not in c and "ytitle" not in c else "label"
    if "annotation" in c: return "annot"
    return "other"


def render(svg, cols=80, ansi=False, shift=0):
    root = ET.fromstring(svg)
    vb = root.get("viewBox")
    if vb: x0, y0, W, H = (float(v) for v in re.split(r"[\s,]+", vb.strip()))
    else: x0, y0, W, H = 0, 0, float(re.sub("[^0-9.]", "", root.get("width"))), float(re.sub("[^0-9.]", "", root.get("height")))
    # pt-sized root (matplotlib) vs viewBox: scale from user units to viewBox units
    cv = Canvas(W, H, cols)
    ids = {el.get("id"): el for el in root.iter() if el.get("id")}
    k = (cols - shift) / cols   # shift > 0: squeeze the drawing right by `shift` columns so left tick labels fit
    base = np.array([[k, 0, shift * cv.cw - x0 * k], [0, 1, -y0], [0, 0, 1]])

    def walk(el, M, st, classes, skip=False):
        tag = NS.sub("", el.tag)
        if tag in ("defs", "clipPath", "mask", "style", "title", "desc", "metadata", "marker", "pattern", "linearGradient", "radialGradient"):
            return
        st = styles(el, st)
        if st.get("display") == "none" or st.get("visibility") == "hidden" or float(st.get("opacity", 1) or 1) == 0: return
        M = M @ parse_transform(el.get("transform"))
        classes = classes + [el.get("class") or "", el.get("id") or ""]
        ids_ = [c for c in classes if c]
        legend = "legend" in " ".join(classes) or (  # matplotlib/plotnine: figure-level artists outside any axes_N group are legend keys
            not any(c.startswith("axes_") for c in ids_) and any(c.startswith(("line2d_", "patch_", "PathCollection_")) for c in ids_))
        if tag == "use":
            ref = ids.get((el.get("{http://www.w3.org/1999/xlink}href") or el.get("href") or "").lstrip("#"))
            if ref is not None:
                T = np.array([[1, 0, float(el.get("x", 0))], [0, 1, float(el.get("y", 0))], [0, 0, 1]])
                walk(ref, M @ T, st, classes)
            return
        if tag == "text":
            return draw_text(el, M, st, classes)
        if tag == "image":
            return draw_image(el, M)
        shapes = shape(tag, el)
        if shapes is not None and not any(c.startswith(("text_", "xtick_", "ytick_")) or "annotation" in c for c in ids_):  # text bbox, annotation boxes, gridlines: not data
            draw_shape(shapes, M, st, legend, "violin" in " ".join(classes))
        for ch in el: walk(ch, M, st, classes)

    def tf(M, p):
        p = np.asarray(p, float)
        return p @ M[:2, :2].T + M[:2, 2]

    def draw_shape(shapes, M, st, legend, violin=False):
        fill = color(st.get("fill", "black")); stroke = color(st.get("stroke"))
        fo = float(st.get("fill-opacity", 1) or 1) * float(st.get("opacity", 1) or 1)
        so = float(st.get("stroke-opacity", 1) or 1) * float(st.get("opacity", 1) or 1)
        if fill is not None and len(fill) > 3: fo *= fill[3]
        if stroke is not None and len(stroke) > 3: so *= stroke[3]
        sw = float(re.sub("[a-z]", "", st.get("stroke-width", "1") or "1") or 1)
        closed = [tf(M, p) for p, c in shapes]
        drawn = False
        if fill is not None and fo > 0.05 and any(c or len(p) > 2 for p, c in shapes):
            before = cv.ninks
            cv.fill(closed, fill[:3], legend=legend, alpha=fo)
            drawn = cv.ninks > before
        if drawn and not legend and stroke is not None and so > 0.05 and sw > 0:  # plotly box: one path = box + median + whiskers; the fill only takes the closed part
            seg = [tf(M, p) for p, c in shapes if not c and len(p) == 2]
            if seg: cv.stroke(seg, (.5, .5, .5) if violin else stroke[:3])   # a violin's inner box is ink on the body, not a line series: mid-grey box-drawing under the fill, no glyph stamps
        if not drawn and stroke is not None and so > 0.05 and sw > 0:
            da = st.get("stroke-dasharray")
            dashes = None
            if da and da != "none":
                dashes = (0, [float(x) for x in re.split(r"[\s,]+", da.replace("px", "").strip()) if x])
            cv.stroke(closed, stroke[:3], dashes, legend=legend)

    def draw_text(el, M, st, classes):
        ts = [t for t in el.iter() if NS.sub("", t.tag) in ("text", "tspan") and t.text and t.text.strip()]
        fsz = lambda t: float(m.group(1)) if (m := re.search(r"font-size:\s*([\d.]+)", t.get("style") or "")) else 0
        if len(ts) > 1 and all(t.get("y") for t in ts[1:]) and fsz(ts[1]):  # matplotlib mathtext: one tspan per glyph run
            y0, f0 = float(ts[0].get("y")), fsz(ts[0]) or fsz(ts[1])
            up = lambda t: float(t.get("y")) < y0 - 1 or (fsz(t) < f0 * .85 and float(t.get("y")) <= y0)
            s = "".join(sup(t.text.strip()) if up(t) else t.text.strip() for t in ts)
        else: s = " ".join(t.text.strip() for t in ts)
        if not s: return
        x, y = float(el.get("x", 0) or 0), float(el.get("y", 0) or 0)
        fs = float(re.sub("[a-z]", "", str(st.get("font-size", "12"))) or 12)
        dy = el.get("dy")
        if dy: y += float(dy.replace("em", "")) * (fs if "em" in dy else 1)
        p = tf(M, [[x, y]])[0]
        angle = (-np.degrees(np.arctan2(M[1, 0], M[0, 0]))) % 360
        ha = {"middle": "center", "end": "right"}.get(st.get("text-anchor", "start"), "left")
        va = "center" if st.get("dominant-baseline") in ("middle", "central") else "top" if st.get("dominant-baseline") == "hanging" else "baseline"
        if va == "baseline": p = p + np.array([0, -fs * 0.35 + cv.ch / 2])  # glyph center, then core's baseline rule
        cv.text(p[0], p[1], s, ha, va, angle, role_of(classes))

    def draw_image(el, M):
        href = el.get("{http://www.w3.org/1999/xlink}href") or el.get("href") or ""
        if "base64," not in href: return
        import matplotlib.image as mimg
        im = mimg.imread(io.BytesIO(base64.b64decode(href.split("base64,", 1)[1])), format="png")
        if im.ndim == 2: im = np.stack([im] * 3, -1)
        alpha = im[..., 3] if im.shape[-1] == 4 else None
        if alpha is not None: im = im[..., :3] * im[..., 3:] + (1 - im[..., 3:])
        x, y = float(el.get("x", 0) or 0), float(el.get("y", 0) or 0)
        num = lambda k, d: float(re.sub("[^0-9.eE-]", "", str(el.get(k, d))) or d)
        w, h = num("width", im.shape[1]), num("height", im.shape[0])
        (ax, ay), (bx, by) = tf(M, [[x, y], [x + w, y + h]])
        cv.image(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by), im if by >= ay else im[::-1], None if alpha is None else alpha if by >= ay else alpha[::-1])

    walk(root, base, {}, [])
    if not shift:  # tick/label text starting left of column 0 -> redo with the drawing shifted right by that overflow
        left = [-(t[0] / cv.cw - width(t[2]) * {"right": 1, "center": .5}.get(t[3], 0))
                for t in cv.texts if t[6] in ("tick", "label") and t[5] in (0, 180) and "\n" not in t[2]]
        ov = int(np.ceil(max(left, default=0)))
        if ov > 0: return render(svg, cols, ansi, min(ov, cols // 4))
    for i, t in enumerate(cv.texts):  # figure-level text next to a legend handle (plotnine) is that handle's label
        if t[6] == "other" and any(abs(t[1] - m[1]) < 1.5 * cv.ch and 0 <= t[0] - m[0] < 12 * cv.cw for m, *_ in cv.legend_marks):
            cv.texts[i] = t[:6] + ("legend",)
    text = cv.render(color=ansi)
    return text, cv.meta


def shapes_closedish(shapes):
    return all(np.hypot(*(p[0] - p[-1])) < 1e-6 for p, _ in shapes)


def shape(tag, el):
    g = lambda k, d=0: float(re.sub("[a-z%]", "", str(el.get(k, d) or d)) or 0)
    if tag == "path": return path_d(el.get("d"))
    if tag == "rect":
        x, y, w, h = g("x"), g("y"), g("width"), g("height")
        if w <= 0 or h <= 0: return []
        return [(np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]]), True)]
    if tag == "line": return [(np.array([[g("x1"), g("y1")], [g("x2"), g("y2")]]), False)]
    if tag in ("polyline", "polygon"):
        p = np.array([float(v) for v in re.split(r"[\s,]+", el.get("points", "").strip()) if v]).reshape(-1, 2)
        return [(np.vstack([p, p[:1]]) if tag == "polygon" else p, tag == "polygon")]
    if tag in ("circle", "ellipse"):
        cx, cy = g("cx"), g("cy"); rx = g("r") if tag == "circle" else g("rx"); ry = g("r") if tag == "circle" else g("ry")
        t = np.linspace(0, 2 * np.pi, 17)
        return [(np.stack([cx + rx * np.cos(t), cy + ry * np.sin(t)], 1), True)]
    return None
