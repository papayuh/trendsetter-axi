"""Regression fixtures formerly embedded in the Matplotlib renderer."""
import numpy as np

from matplotlib.container import BarContainer

from trendsetter_axi.mpl import render


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


def test_mpl_selfchecks():
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
    from trendsetter_axi.core import Canvas as _C
    for y in np.linspace(20, 160, 23):   # a reference rule on row 0 anchors the blank-row trim
        cv = _C(560, 168, 80); cv.stroke([np.array([[100., 1.], [300., 1.]]), ], (.1, .1, .8), rule=True); cv.stroke([np.array([[100., y], [300., y]])], (.8, .1, .1), rule=True)
        rr = [i for i, l in enumerate(cv.render().split("\n")) if "───" in l]
        assert abs((rr[-1] + .5) * cv.ch - y) <= cv.ch / 2 + 1e-6, ("rule row off", y, rr)
    # line: steep runs take both dot columns of the cell (no stray single-dot fragments)
    from trendsetter_axi.core import Canvas
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
