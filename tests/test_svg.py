"""SVG work budgets, root size, image decode bound and unsupported effects. The oracle is the bytes built here and the
limits documented in README "SVG limits"."""
import base64, os, struct, subprocess, sys, textwrap, zlib

import pytest

import trendsetter_axi as tsa
from trendsetter_axi import svg as tsvg

HEAD = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="400" height="100" viewBox="0 0 400 100">'
RECT = '<rect x="150" y="20" width="100" height="60" fill="#d62728"{}/>'
# 400 user units / 80 columns = 5 units/cell, 10 units/row. The fixture occupies x=30..49, y=2..7.
RECT_TEXT = "\n".join([" " * 30 + "█" * 20] * 6)


def doc(body, head=HEAD):
    return f"{head}{body}</svg>"


def fanout(levels=18):
    """g0 is one rect; each g<i> uses g<i-1> twice; the root uses the last level: 2**levels rect instances."""
    defs = '<g id="g0"><rect x="0" y="0" width="1" height="1" fill="#000"/></g>'
    defs += "".join(f'<g id="g{i}"><use xlink:href="#g{i - 1}"/><use xlink:href="#g{i - 1}" x="1"/></g>' for i in range(1, levels + 1))
    return doc(f'<defs>{defs}</defs><use xlink:href="#g{levels}"/>')


def test_use_fanout_hits_the_work_budget():
    svg = fanout()
    assert len(svg) < 2000
    child = textwrap.dedent(f"""
        import resource, sys, time
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
        import trendsetter_axi as tsa
        t = time.perf_counter()
        try:
            tsa.render_svg({svg!r}, 80)
        except ValueError as e:
            print(f"{{time.perf_counter() - t:.3f}}"); print(e); sys.exit(0)
        sys.exit("rendered without hitting the budget")
    """)
    p = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True, timeout=60,
                       env={**os.environ, "OPENBLAS_NUM_THREADS": "1"})
    assert p.returncode == 0, (p.returncode, p.stderr[-2000:])   # never a signal exit
    elapsed, msg = p.stdout.split("\n", 1)
    assert float(elapsed) < 2, elapsed
    assert "50,000" in msg and "50,001 visited" in msg and "work budget" in msg, msg


@pytest.mark.parametrize("extra", [0, 1], ids=["at-budget", "over-budget"])
def test_element_work_budget_boundary(extra):
    # ID indexing visits root, defs and each child; drawing visits root and defs again.
    source = doc('<defs>' + '<g/>' * (50_000 - 4 + extra) + '</defs>')
    if extra:
        with pytest.raises(ValueError, match=r"work budget of 50,000 elements \(50,001 visited"):
            tsa.render_svg(source, 80)
    else:
        assert tsa.render_svg(source, 80) == ""


@pytest.mark.parametrize("body", ['<g id="a"><use href="#a"/></g>', "<g>" * 2000 + RECT.format("") + "</g>" * 2000],
                         ids=["cycle", "nested-groups"])
def test_use_cycle_and_depth_are_rejected(body):
    with pytest.raises(ValueError, match="deeper than 256"):
        tsa.render_svg(doc(body), 80)


@pytest.mark.parametrize("attrs", ['width="1e400" height="100"', 'width="-10" height="100"', 'width="nan" height="100"',
                                   'width="400" height="100" viewBox="0 0 0 0"'])
def test_root_size_must_be_finite_and_positive(monkeypatch, attrs):
    def no_canvas(*a, **k): raise AssertionError("Canvas allocated before the size check")
    monkeypatch.setattr(tsvg, "Canvas", no_canvas)
    with pytest.raises(ValueError, match="finite and positive"):
        tsa.render_svg(doc(RECT.format(""), f'<svg xmlns="http://www.w3.org/2000/svg" {attrs}>'), 80)


def png(w, h):
    """A valid 8-bit greyscale PNG of w x h zero pixels."""
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    raw = zlib.compress(b"\0" * ((w + 1) * h), 9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


def image(data):
    return doc(f'<image x="0" y="0" width="400" height="100" href="data:image/png;base64,{base64.b64encode(data).decode()}"/>')


def test_image_decode_is_bounded(monkeypatch):
    import matplotlib.image as mimg
    big = png(5000, 5000)
    assert len(big) < 64_000 and 5000 * 5000 > 16_000_000
    real = mimg.imread
    monkeypatch.setattr(mimg, "imread", lambda *a, **k: pytest.fail("imread called before the pixel cap"))
    with pytest.raises(ValueError, match="16,000,000"):
        tsa.render_svg(image(big), 80)
    monkeypatch.setattr(mimg, "imread", real)
    assert tsa.render(image(png(40, 10)), 80).warnings == []   # under the cap: decoded as before
    gif = tsa.render(image(b"GIF89a" + b"\0" * 40), 80)
    assert any("unsupported image" in w for w in gif.warnings), gif.warnings   # not PNG: reported, never guessed at


def unsupported(r):
    return {l["what"]: l for l in r.losses if l["kind"] == "unsupported"}


def test_mask_and_gradient_are_material_unsupported():
    masked = doc('<defs><mask id="m"><rect x="150" y="20" width="10" height="10" fill="#fff"/></mask></defs>' + RECT.format(' mask="url(#m)"'))
    r = tsa.render(masked, 80)
    assert unsupported(r)["mask #m"]["material"] is True, r.losses
    with pytest.raises(tsa.RenderLossError):
        tsa.render(masked, 80, strict=True)
    assert tsa.render(doc(RECT.format(' style="mask: url(#m)"')), 80).losses[0]["what"] == "mask #m"

    grad = doc('<defs><linearGradient id="g"><stop offset="0" stop-color="#d62728"/><stop offset="1" stop-color="#1f77b4"/></linearGradient></defs>'
               + RECT.format("").replace('fill="#d62728"', 'fill="url(#g)"'))
    r = tsa.render(grad, 80)
    assert unsupported(r)["gradient #g"]["material"] is True, r.losses
    assert r.text.rsplit("\n", 1)[0] == RECT_TEXT, r.text       # drawn flat, then the caption
    # Canvas colour keys round channels to two decimal places; the expected key comes from the fixture's stop bytes.
    rgb = tuple(round(round(int("d62728"[i:i + 2], 16) / 255, 2) * 255) for i in (0, 2, 4))
    assert r.series[0]["color"] == "#%02x%02x%02x" % rgb, r.series
    with pytest.raises(tsa.RenderLossError):
        tsa.render(grad, 80, strict=True)
    pat = tsa.render(doc('<defs><pattern id="p"/></defs>' + RECT.format("").replace('fill="#d62728"', 'fill="url(#p)"')), 80)
    assert unsupported(pat)["pattern #p"]["material"] is True and pat.series[0]["color"] == "#808080", (pat.losses, pat.series)
    filtered = doc('<defs><filter id="f"/></defs>' + RECT.format(' style="filter: url(#f)"'))
    assert unsupported(tsa.render(filtered, 80))["filter #f"]["material"] is True
    with pytest.raises(tsa.RenderLossError):
        tsa.render(filtered, 80, strict=True)

    clipped = doc('<defs><clipPath id="c"><circle cx="200" cy="50" r="10"/></clipPath></defs>' + RECT.format(' clip-path="url(#c)"'))
    r = tsa.render(clipped, 80, strict=True)                     # owner decision D2: a clip over-draws and says so
    assert unsupported(r)["clip-path #c"]["material"] is False and "drawn unclipped" in r.text
    assert r.text.rsplit("\n", 1)[0] == RECT_TEXT, r.text


@pytest.mark.parametrize("definition", ['', '<linearGradient id="g"/>'])
def test_gradient_without_stops_uses_grey(definition):
    body = '<defs>' + definition + '</defs>' + RECT.format(' style="fill: url(#g)"')
    r = tsa.render(doc(body), 80)
    assert r.text.rsplit("\n", 1)[0] == RECT_TEXT
    assert r.series[0]["color"] == "#808080"
    assert unsupported(r)["gradient #g"]["material"] is True


def test_gradient_stroke_is_reported():
    body = '<defs><radialGradient id="g"><stop style="stop-color: #ff0000"/></radialGradient></defs>'
    body += '<line x1="150" y1="50" x2="250" y2="50" style="stroke: url(#g)"/>'
    r = tsa.render(doc(body), 80)
    assert r.series[0]["color"] == "#ff0000"
    assert unsupported(r)["gradient #g"]["material"] is True
    with pytest.raises(tsa.RenderLossError):
        tsa.render(doc(body), 80, strict=True)


def test_group_opacity_is_inherited():
    empty = ""
    assert tsa.render_svg(doc(RECT.format(' opacity="0.03"')), 80) == empty
    assert tsa.render_svg(doc(f'<g opacity="0.03">{RECT.format("")}</g>'), 80) == empty
    half = RECT.format(' fill-opacity="0.5"')
    assert tsa.render_svg(doc(f'<g opacity="0.5">{half}</g>'), 80) != empty   # 0.25 > 0.05
    assert tsa.render_svg(doc(f'<g opacity="0.2">{RECT.format("")}</g>'), 80) != empty   # product applied once, not squared
    assert tsa.render_svg(doc(f'<g opacity="0.5"><g opacity="0.08">{RECT.format("")}</g></g>'), 80) == empty  # 0.04: products nest
    assert tsa.render_svg(doc(f'<g opacity="0">{RECT.format("")}</g>'), 80) == empty


def test_unresolved_use_is_reported():
    r = tsa.render(doc(RECT.format("") + '<use href="#nope"/>'), 80)
    assert r.losses == [] and any("#nope" in w for w in r.warnings), (r.losses, r.warnings)
    assert r.text == RECT_TEXT


def test_text_uses_group_opacity_once():
    label = '<text x="150" y="50" fill="black">visible</text>'
    assert tsa.render_svg(doc(f'<g opacity="0.03">{label}</g>'), 80) == ""
    assert "visible" in tsa.render_svg(doc(f'<g opacity="0.2">{label}</g>'), 80)  # 0.2 > 0.05; not squared
    assert tsa.render_svg(doc('<g opacity="0.2">' + label.replace('fill="black"', 'fill="black" fill-opacity="0.2"') + '</g>'), 80) == ""


@pytest.mark.parametrize("body", [
    '<text>' + '<tspan/>' * 50_001 + '</text>',
    '<text>' + '<tspan>' * 2000 + 'label' + '</tspan>' * 2000 + '</text>',
], ids=["wide-text", "deep-text"])
def test_text_descendants_obey_limits(body):
    with pytest.raises(ValueError, match="work budget|deeper than 256"):
        tsa.render_svg(doc(body), 80)


@pytest.mark.parametrize("kind", ["text", "gradient", "clip"])
def test_repeated_descendant_scans_share_work_budget(kind):
    if kind == "text":
        definitions = '<text id="target">' + '<tspan/>' * 1000 + '</text>'
    elif kind == "gradient":
        definitions = '<linearGradient id="g">' + '<g/>' * 1000 + '<stop stop-color="red"/></linearGradient>'
        definitions += '<rect id="target" width="1" height="1" fill="url(#g)"/>'
    else:
        definitions = '<clipPath id="c">' + '<circle r="1"/>' * 1000 + '</clipPath>'
        definitions += '<rect id="target" width="1" height="1" fill="none" clip-path="url(#c)"/>'
    body = '<defs>' + definitions + '</defs>' + '<use href="#target"/>' * 200
    with pytest.raises(ValueError, match=r"work budget.*50,001 visited"):
        tsa.render_svg(doc(body), 80)


@pytest.mark.parametrize("kind", ["text", "gradient", "clip"])
def test_expanded_descendant_scans_obey_depth(kind):
    if kind == "text":
        definitions = '<text id="target">' + '<tspan>' * 200 + 'label' + '</tspan>' * 200 + '</text>'
        levels = 60
    elif kind == "gradient":
        definitions = '<linearGradient id="g">' + '<g>' * 200 + '<stop stop-color="red"/>' + '</g>' * 200 + '</linearGradient>'
        definitions += '<rect id="target" width="1" height="1" fill="url(#g)"/>'
        levels = 60
    else:
        definitions = '<clipPath id="c"><rect width="1" height="1"/></clipPath>'
        definitions += '<rect id="target" width="1" height="1" clip-path="url(#c)"/>'
        levels = 254
    for i in range(levels):
        definitions += f'<use id="u{i}" href="#{"target" if i == 0 else "u" + str(i - 1)}"/>'
    body = f'<defs>{definitions}</defs><use href="#u{levels - 1}"/>'
    with pytest.raises(ValueError, match="deeper than 256"):
        tsa.render_svg(doc(body), 80)


@pytest.mark.parametrize("container", ["text", "tspan", "nested-tspan"])
@pytest.mark.parametrize("inline", [False, True], ids=["attribute", "inline-style"])
@pytest.mark.parametrize("prop,ref,what,material", [
    ("fill", "g", "gradient #g", True),
    ("stroke", "g", "gradient #g", True),
    ("fill", "p", "pattern #p", True),
    ("stroke", "p", "pattern #p", True),
    ("fill", "missing", "gradient #missing", True),
    ("stroke", "missing", "gradient #missing", True),
    ("mask", "m", "mask #m", True),
    ("filter", "f", "filter #f", True),
    ("clip-path", "c", "clip-path #c", False),
])
def test_text_run_effects_are_reported(container, inline, prop, ref, what, material):
    defs = ('<defs><linearGradient id="g"><stop stop-color="red"/></linearGradient>'
            '<pattern id="p"/><mask id="m"/><filter id="f"/>'
            '<clipPath id="c"><circle cx="150" cy="50" r="1"/></clipPath></defs>')
    effect = f'style="{prop}: url(#{ref})"' if inline else f'{prop}="url(#{ref})"'
    if container == "text":
        label = f'<text x="150" y="50" {effect}>label</text>'
    else:
        run = f'<tspan {effect}>label</tspan>'
        if container == "nested-tspan": run = f'<tspan>{run}</tspan>'
        label = f'<text x="150" y="50">{run}</text>'
    source = doc(defs + label)
    r = tsa.render(source, 80)
    assert "label" in r.text
    assert unsupported(r)[what]["material"] is material
    if material:
        with pytest.raises(tsa.RenderLossError):
            tsa.render(source, 80, strict=True)
    else:
        assert "drawn unclipped" in tsa.render(source, 80, strict=True).text


@pytest.mark.parametrize("body,expected", [
    ('<text x="150" y="50" fill-opacity="0"><tspan fill-opacity="1">visible</tspan></text>', "visible"),
    ('<text x="150" y="50" fill-opacity="0"><tspan><tspan style="fill-opacity: 1">visible</tspan></tspan></text>', "visible"),
    ('<text x="150" y="50" fill-opacity="0" stroke="red">outlined</text>', "outlined"),
    ('<text x="150" y="50" fill="none" stroke="red" stroke-opacity="0"><tspan stroke-opacity="1">outlined</tspan></text>', "outlined"),
    ('<text x="150" y="50"><tspan fill-opacity="0">hidden</tspan><tspan>visible</tspan></text>', "visible"),
    ('<text x="150" y="50"><tspan opacity="0.2"><tspan opacity="0.2">hidden</tspan></tspan><tspan>visible</tspan></text>', "visible"),
    ('<text x="150" y="50"><tspan style="display: none">hidden</tspan><tspan>visible</tspan></text>', "visible"),
    ('<text x="150" y="50" fill="none">hidden</text>', ""),
    ('<text x="150" y="50" fill-opacity="0" stroke="red" stroke-opacity="0">hidden</text>', ""),
    ('<text x="150" y="50" fill="none" stroke="red" stroke-width="0">hidden</text>', ""),
    ('<text x="150" y="50" fill="rgba(0,0,0,0)">hidden</text>', ""),
    ('<text x="150" y="50" fill="none" stroke="rgba(255,0,0,0)">hidden</text>', ""),
    ('<text x="150" y="50" style="fill-opacity: 0; stroke: red">outlined</text>', "outlined"),
    ('<g opacity="0.2"><text x="150" y="50" fill="none" stroke="red">outlined</text></g>', "outlined"),
    ('<g opacity="0.03"><text x="150" y="50" fill="none" stroke="red">hidden</text></g>', ""),
])
def test_text_visibility_is_per_run_and_paint(body, expected):
    text = tsa.render_svg(doc(body), 80)
    if expected:
        assert text.strip() == expected
    else:
        assert text == ""


def test_inherited_text_paints_are_reported():
    body = '<g style="fill: url(#g); stroke: url(#p)"><text x="150" y="50"><tspan>label</tspan></text></g>'
    r = tsa.render(doc('<defs><linearGradient id="g"/><pattern id="p"/></defs>' + body), 80)
    assert "label" in r.text
    assert set(unsupported(r)) == {"gradient #g", "pattern #p"}
    with pytest.raises(tsa.RenderLossError):
        tsa.render(doc(body), 80, strict=True)


def test_mathtext_runs_keep_superscript_layout():
    body = ('<text x="150" y="50"><tspan x="0" y="0" style="font-size: 12px">x</tspan>'
            '<tspan x="8" y="-4" style="font-size: 8px">2</tspan></text>')
    assert tsa.render_svg(doc(body), 80).strip() == "x²"


@pytest.mark.parametrize("baseline_y", ["", ' y=""'])
def test_mathtext_falls_back_when_first_visible_run_has_no_y(baseline_y):
    body = ('<text x="150" y="50"><tspan y="50" opacity="0">hidden</tspan>'
            f'<tspan{baseline_y}>b</tspan><tspan y="46" style="font-size:8px">2</tspan></text>')
    assert tsa.render_svg(doc(body), 80).strip() == "b 2"


@pytest.mark.parametrize("prop", ["fill", "stroke"])
@pytest.mark.parametrize("ref", ["g", "p", "missing"])
@pytest.mark.parametrize("inline", [False, True], ids=["attribute", "inline-style"])
@pytest.mark.parametrize("container", ["group", "use", "image", "text", "tspan", "empty-text", "empty-tspan", "empty-shape", "hidden-run", "excluded-shape"])
def test_nonpainting_containers_do_not_report_paints(prop, ref, inline, container):
    effect = f'style="{prop}: url(#{ref})"' if inline else f'{prop}="url(#{ref})"'
    defs = '<defs><linearGradient id="g"><stop stop-color="blue"/></linearGradient><pattern id="p"/></defs>'
    rect = RECT.format(' stroke="none"')
    if container == "group":
        body, expected = f'<g {effect}>{rect}</g>', RECT_TEXT
    elif container == "use":
        target = rect.replace('<rect ', '<rect id="target" ')
        body, expected = f'<defs>{target}</defs><use href="#target" {effect}/>', RECT_TEXT
    elif container == "image":
        body, expected = f'<image {effect}/>', ""
    elif container == "text":
        body, expected = f'<text x="150" y="50" {effect}><tspan fill="black" stroke="none">label</tspan></text>', "label"
    elif container == "tspan":
        body, expected = f'<text x="150" y="50"><tspan {effect}><tspan fill="black" stroke="none">label</tspan></tspan></text>', "label"
    elif container == "empty-text":
        body, expected = f'<text {effect}/>', ""
    elif container == "empty-tspan":
        body, expected = f'<text><tspan {effect}> </tspan></text>', ""
    elif container == "empty-shape":
        body, expected = f'<rect width="0" height="10" {effect}/>', ""
    elif container == "hidden-run":
        body, expected = f'<text><tspan visibility="hidden" {effect}>hidden</tspan></text>', ""
    else:
        body, expected = f'<g id="annotation"><rect width="10" height="10" {effect}/></g>', ""
    r = tsa.render(doc(defs + body), 80, strict=True)
    assert unsupported(r) == {}
    assert r.text.strip() == expected.strip()


@pytest.mark.parametrize("prop,ref,material", [("mask", "m", True), ("filter", "f", True), ("clip-path", "c", False)])
@pytest.mark.parametrize("inline", [False, True], ids=["attribute", "inline-style"])
@pytest.mark.parametrize("container", ["group", "use"])
def test_container_effects_still_report(prop, ref, material, inline, container):
    defs = '<defs><mask id="m"/><filter id="f"/><clipPath id="c"><circle r="1"/></clipPath></defs>'
    effect = f'style="{prop}: url(#{ref})"' if inline else f'{prop}="url(#{ref})"'
    if container == "group":
        body = f'<g {effect}>{RECT.format("")}</g>'
    else:
        target = RECT.format("").replace('<rect ', '<rect id="target" ')
        body = f'<defs>{target}</defs><use href="#target" {effect}/>'
    source = doc(defs + body)
    r = tsa.render(source, 80)
    assert unsupported(r)[f"{prop} #{ref}"]["material"] is material
    assert r.text.rsplit("\n", 1)[0] == RECT_TEXT
    if material:
        with pytest.raises(tsa.RenderLossError):
            tsa.render(source, 80, strict=True)
    else:
        assert tsa.render(source, 80, strict=True).text == r.text


@pytest.mark.parametrize("definition", [
    '<clipPath id="c"><rect width="10" height="10"/></clipPath>',
    '<clipPath id="c"><circle r="1"/></clipPath>',
    '',
], ids=["rectangular", "circular", "unresolved"])
@pytest.mark.parametrize("nested", [False, True], ids=["direct-tspan", "nested-tspan"])
@pytest.mark.parametrize("inline", [False, True], ids=["attribute", "inline-style"])
def test_run_local_clips_are_reported_unclipped(definition, nested, inline):
    effect = 'style="clip-path: url(#c)"' if inline else 'clip-path="url(#c)"'
    run = f'<tspan {effect}>label</tspan>'
    if nested: run = f'<tspan {effect}><tspan>label</tspan></tspan>'
    source = doc(f'<defs>{definition}</defs><text x="150" y="50">{run}</text>')
    r = tsa.render(source, 80, strict=True)
    assert r.text.rsplit("\n", 1)[0].strip() == "label"
    assert "drawn unclipped" in r.text
    assert unsupported(r)["clip-path #c"]["material"] is False


@pytest.mark.parametrize("container", ["text", "group"])
@pytest.mark.parametrize("inline", [False, True], ids=["attribute", "inline-style"])
@pytest.mark.parametrize("rect,expected", [
    ('width="10" height="10"', ""),
    ('x="100" y="20" width="100" height="60"', "label"),
])
def test_text_root_rectangular_clips_remain_honoured(container, inline, rect, expected):
    effect = 'style="clip-path: url(#c)"' if inline else 'clip-path="url(#c)"'
    if container == "text":
        body = f'<text x="150" y="50" {effect}>label</text>'
    else:
        body = f'<g {effect}><text x="150" y="50">label</text></g>'
    source = doc(f'<defs><clipPath id="c"><rect {rect}/></clipPath></defs>{body}')
    r = tsa.render(source, 80, strict=True)
    assert r.text.strip() == expected
    assert unsupported(r) == {}


@pytest.mark.parametrize("inline", [False, True], ids=["attribute", "inline-style"])
@pytest.mark.parametrize("container", ["text", "tspan", "nested-tspan"])
def test_text_visibility_can_be_overridden(inline, container):
    hidden = 'style="visibility: hidden"' if inline else 'visibility="hidden"'
    visible = 'style="visibility: visible"' if inline else 'visibility="visible"'
    run = f'<tspan {visible}>label</tspan>'
    if container == "text":
        body = f'<text x="150" y="50" {hidden}>hidden{run}</text>'
    else:
        run = f'<tspan {hidden}>hidden{run}</tspan>'
        if container == "nested-tspan": run = f'<tspan {hidden}>{run}</tspan>'
        body = f'<text x="150" y="50">{run}</text>'
    assert tsa.render_svg(doc(body), 80).strip() == "label"


@pytest.mark.parametrize("restriction", ['visibility="hidden"', 'display="none"', 'opacity="0"'])
def test_text_visibility_does_not_override_other_pruning(restriction):
    if restriction.startswith("visibility"):
        body = f'<text x="150" y="50"><tspan {restriction}>hidden<tspan>hidden</tspan></tspan></text>'
    else:
        body = f'<text x="150" y="50"><tspan {restriction}><tspan visibility="visible">hidden</tspan></tspan></text>'
    assert tsa.render_svg(doc(body), 80) == ""


@pytest.mark.parametrize("href", ["href", "xlink:href"])
@pytest.mark.parametrize("malformation", ["duplicate-before-idat", "duplicate-after-idat", "noninitial", "wrong-ihdr-length", "truncated-chunk"])
def test_malformed_png_headers_are_rejected_before_decode(monkeypatch, href, malformation):
    import matplotlib.image as mimg
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    small = png(1, 1)
    if malformation == "duplicate-before-idat":
        data = small[:33] + png(5000, 5000)[8:]
    elif malformation == "duplicate-after-idat":
        data = small[:-12] + png(5000, 5000)[8:]
    elif malformation == "noninitial":
        data = small[:8] + chunk(b"tEXt", struct.pack(">II", 1, 1)) + small[8:]
    elif malformation == "wrong-ihdr-length":
        data = small[:8] + chunk(b"IHDR", small[16:29] + b"\0") + small[33:]
    else:
        data = small[:-1]
    monkeypatch.setattr(mimg, "imread", lambda *a, **k: pytest.fail("imread called on malformed PNG headers"))
    with pytest.raises(ValueError, match="SVG PNG.*(IHDR|truncated chunk)"):
        tsa.render_svg(image(data).replace(" href=", f" {href}="), 80)


def test_png_chunk_payload_may_contain_ihdr_bytes():
    data = png(40, 10)
    payload = b"label\0IHDR"
    ancillary = struct.pack(">I", len(payload)) + b"tEXt" + payload + struct.pack(">I", zlib.crc32(b"tEXt" + payload))
    r = tsa.render(image(data[:33] + ancillary + data[33:]), 80)
    assert r.warnings == []
    assert r.text


@pytest.mark.parametrize("ref", ["g", "p", "missing"])
@pytest.mark.parametrize("geometry,visible", [
    ('<line x1="150" y1="50" x2="250" y2="50" stroke="red"/>', True),
    ('<polyline points="150,50 250,50" stroke="red"/>', True),
    ('<path d="M150 50 L250 50" stroke="red"/>', True),
    ('<path d="M150 50 Z" stroke="none"/>', False),
])
def test_unfillable_geometry_does_not_consume_fill_paints(ref, geometry, visible):
    defs = '<defs><linearGradient id="g"/><pattern id="p"/></defs>'
    r = tsa.render(doc(defs + f'<g fill="url(#{ref})">{geometry}</g>'), 80, strict=True)
    assert unsupported(r) == {}
    if visible:
        assert r.text
        assert r.series[0]["color"] == "#ff0000"
    else:
        assert r.text == ""
        assert r.series == []


@pytest.mark.parametrize("ref", ["g", "p", "missing"])
@pytest.mark.parametrize("inline", [False, True], ids=["attribute", "inline-style"])
@pytest.mark.parametrize("container", ["shape", "text", "tspan", "nested-tspan", "group-shape", "group-text"])
@pytest.mark.parametrize("channel,disabled", [
    ("fill", {"fill-opacity": "0"}),
    ("fill", {"fill-opacity": "0.05"}),
    ("fill", {"opacity": "0.2", "fill-opacity": "0.2"}),
    ("stroke", {"stroke-opacity": "0"}),
    ("stroke", {"stroke-opacity": "0.05"}),
    ("stroke", {"opacity": "0.2", "stroke-opacity": "0.2"}),
    ("stroke", {"stroke-width": "0"}),
])
def test_disabled_paints_do_not_fail_strict(ref, inline, container, channel, disabled):
    props = {"fill": "red", "stroke": "red", channel: f"url(#{ref})", **disabled}
    attrs = 'style="' + '; '.join(f'{k}: {v}' for k, v in props.items()) + '"' if inline else ' '.join(f'{k}="{v}"' for k, v in props.items())
    if container == "shape":
        body = f'<rect x="150" y="20" width="100" height="60" {attrs}/>'
    elif container == "text":
        body = f'<text x="150" y="50" {attrs}>label</text>'
    elif container in ("tspan", "nested-tspan"):
        run = 'label' if container == "tspan" else '<tspan>label</tspan>'
        body = f'<text x="150" y="50"><tspan {attrs}>{run}</tspan></text>'
    else:
        mark = '<rect x="150" y="20" width="100" height="60"/>' if container == "group-shape" else '<text x="150" y="50">label</text>'
        body = f'<g {attrs}>{mark}</g>'
    defs = '<defs><linearGradient id="g"/><pattern id="p"/></defs>'
    r = tsa.render(doc(defs + body), 80, strict=True)
    assert unsupported(r) == {}
    if "shape" in container:
        assert r.text
        assert r.series[0]["color"] == "#ff0000"
    else:
        assert r.text.strip() == "label"


@pytest.mark.parametrize("ref,what", [("g", "gradient #g"), ("p", "pattern #p"), ("missing", "gradient #missing")])
@pytest.mark.parametrize("inline", [False, True], ids=["attribute", "inline-style"])
@pytest.mark.parametrize("enabled", [True, False], ids=["enabled", "disabled"])
@pytest.mark.parametrize("geometry", [
    '<rect x="150" y="20" width="100" height="60"/>',
    '<path d="M150 20 L250 20 L250 80 L150 80 Z"/>',
    '<polygon points="150,20 250,20 250,80 150,80"/>',
    '<circle cx="200" cy="50" r="30"/>',
    '<ellipse cx="200" cy="50" rx="50" ry="30"/>',
    '<g class="legend"><rect x="150" y="20" width="10" height="10"/></g>',
])
def test_filled_shapes_report_enabled_outline_paints(ref, what, inline, enabled, geometry):
    defs = '<defs><linearGradient id="g"/><pattern id="p"/></defs>'
    sw = 20 if enabled else 0
    attrs = f'style="stroke: url(#{ref}); stroke-width: {sw}"' if inline else f'stroke="url(#{ref})" stroke-width="{sw}"'
    source = doc(defs + f'<g fill="#d62728" {attrs}>{geometry}</g>')
    r = tsa.render(source, 80)
    if enabled:
        assert unsupported(r)[what]["material"] is True
        with pytest.raises(tsa.RenderLossError):
            tsa.render(source, 80, strict=True)
    else:
        assert unsupported(r) == {}
        assert tsa.render(source, 80, strict=True).text == r.text
    if geometry.startswith(('<rect', '<path', '<polygon')):
        assert (r.text.rsplit("\n", 1)[0] if enabled else r.text) == RECT_TEXT


def test_mixed_filled_and_open_path_reports_consumed_stroke():
    defs = '<defs><linearGradient id="g"><stop stop-color="blue"/></linearGradient></defs>'
    body = '<path fill="red" stroke="url(#g)" d="M150 20 L250 20 L250 80 L150 80 Z M150 50 L250 50"/>'
    source = doc(defs + body)
    r = tsa.render(source, 80)
    assert unsupported(r)["gradient #g"]["material"] is True
    assert any(s["color"] == "#0000ff" for s in r.series)
    with pytest.raises(tsa.RenderLossError):
        tsa.render(source, 80, strict=True)


@pytest.mark.parametrize("ref", ["g", "p", "missing"])
@pytest.mark.parametrize("transform", ["", "rotate(45 200 50)", "matrix(0 1 -1 0 250 -150)"])
@pytest.mark.parametrize("geometry", [
    '<polyline points="150,50 200,50 250,50"/>',
    '<polyline points="200,20 200,50 200,80"/>',
    '<polyline points="150,20 200,50 250,80"/>',
    '<path d="M150 50 L150 50 L200 50 L250 50"/>',
    '<path d="M150 50 L200 50 L250 50 Z"/>',
    '<polygon points="150,50 200,50 250,50"/>',
    '<ellipse cx="200" cy="50" rx="50" ry="0"/>',
    '<ellipse cx="200" cy="50" rx="0" ry="30"/>',
    '<rect x="150" y="20" width="100" height="60" transform="matrix(1 0 0 0 0 50)"/>',
])
def test_collinear_contours_keep_strokes_without_fill_losses(ref, transform, geometry):
    defs = '<defs><linearGradient id="g"/><pattern id="p"/></defs>'
    source = doc(defs + f'<g transform="{transform}" fill="url(#{ref})" stroke="red">{geometry}</g>')
    r = tsa.render(source, 80, strict=True)
    assert unsupported(r) == {}
    assert r.text
    assert len(r.series) == 1
    assert r.series[0]["color"] == "#ff0000"
    assert r.series[0]["kind"] == "line"


@pytest.mark.parametrize("geometry", [
    '<circle cx="200" cy="50" r="0"/>',
    '<polyline points="200,50 200,50 200,50"/>',
    '<polygon points="200,50 200,50 200,50"/>',
])
def test_point_contours_do_not_consume_fill(geometry):
    source = doc('<g fill="url(#missing)" stroke="none">' + geometry + '</g>')
    r = tsa.render(source, 80, strict=True)
    assert r.text == ""
    assert r.losses == []
    assert r.series == []


def test_mixed_filled_and_collinear_contours_keep_strokes():
    defs = '<defs><linearGradient id="g"><stop stop-color="blue"/></linearGradient></defs>'
    body = '<path fill="url(#g)" stroke="red" d="M150 20 L250 20 L250 80 L150 80 Z M150 50 L200 50 L250 50"/>'
    r = tsa.render(doc(defs + body), 80)
    assert unsupported(r)["gradient #g"]["material"] is True
    assert any(s["color"] == "#0000ff" and s["kind"] == "fill" for s in r.series)
    assert any(s["color"] == "#ff0000" and s["kind"] == "line" for s in r.series)
    assert r.text


def test_self_intersecting_contour_still_consumes_fill():
    defs = '<defs><linearGradient id="g"><stop stop-color="blue"/></linearGradient></defs>'
    body = '<polygon points="150,20 250,80 150,80 250,20" fill="url(#g)"/>'
    source = doc(defs + body)
    r = tsa.render(source, 80)
    assert unsupported(r)["gradient #g"]["material"] is True
    assert any(s["color"] == "#0000ff" and s["kind"] == "fill" for s in r.series)
    with pytest.raises(tsa.RenderLossError):
        tsa.render(source, 80, strict=True)


@pytest.mark.parametrize("prop,ref,material", [("mask", "m", True), ("filter", "f", True), ("clip-path", "c", False)])
@pytest.mark.parametrize("container", ["shape", "text", "tspan"])
def test_disabled_paint_does_not_suppress_other_effects(prop, ref, material, container):
    defs = '<defs><linearGradient id="g"/><mask id="m"/><filter id="f"/><clipPath id="c"><circle r="1"/></clipPath></defs>'
    attrs = f'fill="url(#g)" fill-opacity="0" stroke="red" {prop}="url(#{ref})"'
    if container == "shape":
        body = f'<rect x="150" y="20" width="100" height="60" {attrs}/>'
    elif container == "text":
        body = f'<text x="150" y="50" {attrs}>label</text>'
    else:
        body = f'<text x="150" y="50"><tspan {attrs}>label</tspan></text>'
    source = doc(defs + body)
    r = tsa.render(source, 80)
    assert set(unsupported(r)) == {f"{prop} #{ref}"}
    assert unsupported(r)[f"{prop} #{ref}"]["material"] is material
    if material:
        with pytest.raises(tsa.RenderLossError):
            tsa.render(source, 80, strict=True)
    else:
        assert tsa.render(source, 80, strict=True).text == r.text
