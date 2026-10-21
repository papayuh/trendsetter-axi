import os

import pytest

import trendsetter_axi


@pytest.fixture(autouse=True)
def fake_renderer(monkeypatch):
    """TSAXI_FAKE_RENDERER=x swaps both public renderers for one that returns "x".

    Tests must call trendsetter_axi.render_figure / render_svg through the module so the swap reaches them;
    test_sensitivity.py runs the suite this way and requires it to fail."""
    if os.environ.get("TSAXI_FAKE_RENDERER") == "x":
        monkeypatch.setattr(trendsetter_axi, "render_figure", lambda fig, cols=80: "x")
        monkeypatch.setattr(trendsetter_axi, "render_svg", lambda svg, cols=80: "x")
