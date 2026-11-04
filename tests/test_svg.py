"""SVG work budgets, root size, image decode bound and unsupported effects. The oracle is the bytes built here and the
limits documented in README "SVG limits"."""
import base64, os, struct, subprocess, sys, textwrap, zlib

import pytest

import trendsetter_axi as tsa
from trendsetter_axi import svg as tsvg

HEAD = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="400" height="100" viewBox="0 0 400 100">'
RECT = '<rect x="150" y="20" width="100" height="60" fill="#d62728"{}/>'


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
    assert f"{tsvg.MAX_ELEMENTS:,}" in msg and "elements" in msg, msg


def test_use_cycle_and_depth_are_rejected():
    with pytest.raises(ValueError, match=f"deeper than {tsvg.MAX_DEPTH}"):
        tsa.render_svg(doc('<g id="a"><use href="#a"/></g>'), 80)
    with pytest.raises(ValueError, match=f"deeper than {tsvg.MAX_DEPTH}"):
        tsa.render_svg(doc("<g>" * 2000 + RECT.format("") + "</g>" * 2000), 80)


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
    assert len(big) < 64_000 and 5000 * 5000 > tsvg.MAX_PIXELS
    real = mimg.imread
    monkeypatch.setattr(mimg, "imread", lambda *a, **k: pytest.fail("imread called before the pixel cap"))
    with pytest.raises(ValueError, match=f"{tsvg.MAX_PIXELS:,}"):
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

    plain = tsa.render_svg(doc(RECT.format("")), 80)
    grad = doc('<defs><linearGradient id="g"><stop offset="0" stop-color="#d62728"/><stop offset="1" stop-color="#1f77b4"/></linearGradient></defs>'
               + RECT.format("").replace('fill="#d62728"', 'fill="url(#g)"'))
    r = tsa.render(grad, 80)
    assert unsupported(r)["gradient #g"]["material"] is True, r.losses
    assert r.text.rsplit("\n", 1)[0] == plain, r.text            # drawn flat in its first stop colour, then the caption
    assert r.series == tsa.render(doc(RECT.format("")), 80).series, r.series
    with pytest.raises(tsa.RenderLossError):
        tsa.render(grad, 80, strict=True)
    pat = tsa.render(doc('<defs><pattern id="p"/></defs>' + RECT.format("").replace('fill="#d62728"', 'fill="url(#p)"')), 80)
    grey = tsa.render(doc(RECT.format("").replace("#d62728", "#808080")), 80)
    assert unsupported(pat)["pattern #p"]["material"] is True and pat.series == grey.series, (pat.losses, pat.series)   # mid-grey

    clipped = doc('<defs><clipPath id="c"><circle cx="200" cy="50" r="10"/></clipPath></defs>' + RECT.format(' clip-path="url(#c)"'))
    r = tsa.render(clipped, 80, strict=True)                     # owner decision D2: a clip over-draws and says so
    assert unsupported(r)["clip-path #c"]["material"] is False and "drawn unclipped" in r.text
    assert r.text.rsplit("\n", 1)[0] == plain, r.text


def test_group_opacity_is_inherited():
    empty = tsa.render_svg(doc(""), 80)
    assert tsa.render_svg(doc(RECT.format(' opacity="0.03"')), 80) == empty
    assert tsa.render_svg(doc(f'<g opacity="0.03">{RECT.format("")}</g>'), 80) == empty
    half = RECT.format(' fill-opacity="0.5"')
    assert tsa.render_svg(doc(f'<g opacity="0.5">{half}</g>'), 80) != empty   # 0.25 > 0.05
    assert tsa.render_svg(doc(f'<g opacity="0.5"><g opacity="0.08">{RECT.format("")}</g></g>'), 80) == empty  # 0.04: products nest
    assert tsa.render_svg(doc(f'<g opacity="0">{RECT.format("")}</g>'), 80) == empty


def test_unresolved_use_is_reported():
    r = tsa.render(doc(RECT.format("") + '<use href="#nope"/>'), 80)
    assert r.losses == [] and any("#nope" in w for w in r.warnings), (r.losses, r.warnings)
    assert r.text == tsa.render_svg(doc(RECT.format("")), 80)
