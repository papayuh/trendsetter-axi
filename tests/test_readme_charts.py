from pathlib import Path

import matplotlib.pyplot as plt
import pytest

import trendsetter_axi
from examples.gallery import CHARTS
from examples.readme_charts import IDS, SGR

DOCS = Path(__file__).resolve().parents[1] / "docs"


@pytest.mark.parametrize("chart_id", IDS)
def test_readme_charts_match_current_output(chart_id):
    chart = next(c for c in CHARTS if c["id"] == chart_id)
    expected = (DOCS / f"{chart_id}.txt").read_text(encoding="utf-8")
    with plt.rc_context(plt.rcParamsDefault):
        fig = chart["make"]()
        try:
            assert trendsetter_axi.render_figure(fig, 80) == expected
            colored = trendsetter_axi.render_figure(fig, 80, color=True)
            assert SGR.sub("", colored) == expected
        finally:
            plt.close(fig)
