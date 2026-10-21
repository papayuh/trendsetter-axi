from trendsetter_axi import mpl


def test_mpl_embedded_selfchecks():
    """The renderer's own fixtures (`python -m trendsetter_axi.mpl --test`) run under pytest, so CI sees them."""
    mpl._test()
