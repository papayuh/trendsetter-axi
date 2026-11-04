"""The private render steps can be exercised without a full adapter render."""
import numpy as np
import pytest

from trendsetter_axi.cells import SGR
from trendsetter_axi.core import Canvas


def canvas():
    cv = Canvas(160, 80, 16)
    red, blue = (0.8, 0.1, 0.1), (0.1, 0.3, 0.9)
    cv.fill([np.array([[20, 35], [70, 35], [70, 65], [20, 65]])], red, role="data")
    cv.stroke([np.array([[20, 60], [130, 20]])], blue, role="data")
    cv.marker([(110, 50)], blue, role="data")
    cv.text(80, 10, "界 title", ha="center", role="title")
    cv.text(100, 75, "line", role="legend")
    cv.stroke([np.array([[75, 70], [90, 70]])], blue, role="legend")
    return cv


def test_raster_and_cells_are_observable_before_text():
    cv = canvas()
    raster = cv._rasterize(False)
    assert raster["dots"].shape == (16, 32)
    assert (raster["dots"] == 1).any()
    assert (raster["fill"] == 0).any()

    cell, sid_at, heatrgb = cv._compose_cells(raster)
    assert cell.shape == sid_at.shape == (4, 16)
    assert not cell[0].any()  # title has not been placed
    assert cell[1, 2] == "▂" and sid_at[1, 2] == 0
    assert cell[2, 11] == "×"  # marker geometry is already composed
    assert heatrgb == {}
    assert cv.meta["placed"] == []


@pytest.mark.parametrize("color", [False, True])
def test_text_and_serialization_keep_the_existing_output(color):
    cv = canvas()
    raster = cv._rasterize(color)
    cell, sid_at, heatrgb = cv._compose_cells(raster)
    continuation, inv = cv._place_text(raster, cell, sid_at)
    assert cell[0, 4] == "界" and continuation[0, 5]
    assert cv.meta["placed"] == [("title", "界 title"), ("legend", "line")]
    assert cv.meta["drawn"] == {0, 1}
    assert cell[3, 8] == "×"  # legend handle snapped beside its label

    text = cv._serialize(raster, cell, sid_at, heatrgb, continuation, inv, color)
    assert SGR.sub("", text) == (
        "    界 title\n"
        "  ▂▂▂▂▂⢀⣀⠤⠔×⠉⠁\n"
        "  ⣀─⠔─⠉×   ×\n"
        "  ⠁     × line"
    )
    assert bool(SGR.search(text)) == color
    if color:
        assert "\x1b[38;2;204;25;25m▂\x1b[0m" in text
        assert "\x1b[38;2;25;76;229m⢀\x1b[0m" in text

    full = canvas()
    assert full.render(color) == text
    np.testing.assert_array_equal(full.meta["cells"], cv.meta["cells"])
    assert {k: v for k, v in full.meta.items() if k != "cells"} == {
        k: v for k, v in cv.meta.items() if k != "cells"
    }


def test_legend_keys_do_not_count_as_visible_data():
    cv = Canvas(160, 80, 16)
    cv.stroke([np.array([[20, 50], [40, 50]])], (0.1, 0.3, 0.9), role="legend")
    cv.text(60, 55, "key", role="legend")
    raster = cv._rasterize(False)
    cell, sid_at, _ = cv._compose_cells(raster)
    assert not cell.any()

    cv._place_text(raster, cell, sid_at)
    assert (sid_at == 0).any()  # key was drawn, but audited after data visibility
    assert cv.meta["drawn"] == set()
    assert cv.meta["placed"] == [("legend", "key")]
