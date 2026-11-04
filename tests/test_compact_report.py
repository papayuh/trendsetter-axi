"""Compact reports retain source facts even when the bounded chart cannot."""
import json
import subprocess
import sys

from matplotlib.figure import Figure
import pytest

from trendsetter_axi import CompactResult, render_compact, render_ranking


@pytest.mark.parametrize('cols,rows,top_k', [(60, 8, None), (60, 2, None), (3, 1, None), (60, 3, 1)])
def test_ranking_report_keeps_exact_source_values_and_context(cols, rows, top_k):
    result = render_ranking(['North', 'South', 'East'], [-9, 3, .123456789],
                            title='Team change', unit='pp', name='change',
                            cols=cols, max_rows=rows, top_k=top_k)
    summary = result.summary()
    assert result.report.text == result.text and result.report.dimensions == result.dimensions
    assert result.report.losses == result.losses and result.report.summary() == summary
    assert 'title: Team change' in summary and 'x: pp' in summary
    assert "barh 'change' n=3 North=-9 South=+3 East=+0.123456789" in summary
    assert len(result.records) == 3
    if result.omitted:
        loss = next(loss for loss in result.losses if loss['kind'] == 'omitted')
        assert loss['material'] is True and str(result.omitted) in loss['detail']
        assert 'omitted display:' in summary
    else:
        assert result.losses == [] and summary.endswith('losses: none')


def test_ranking_report_stays_dependency_light_in_fresh_interpreter():
    code = '''import json, sys
from trendsetter_axi import render_ranking
r = render_ranking(['North', 'South'], [-9, 3], max_rows=1)
print(json.dumps([r.summary(), r.losses, 'numpy' in sys.modules, 'matplotlib' in sys.modules]))
'''
    summary, losses, numpy, matplotlib = json.loads(subprocess.check_output([sys.executable, '-c', code], text=True))
    assert 'North=-9 South=+3' in summary and losses
    assert not numpy and not matplotlib


@pytest.mark.parametrize('rows', [2, 40])
def test_figure_report_keeps_source_line_values_and_clipping_losses(rows):
    ax = Figure().subplots()
    ax.plot([0, 1, 2], [2, 4, 8], label='demand')
    ax.set(title='Demand', xlabel='day', ylabel='units', ylim=(0, 6))
    result = render_compact(ax.figure, cols=60, max_rows=rows)
    assert result.mode == ('explanation' if rows == 2 else 'figure')
    summary = result.summary()
    assert 'title: Demand' in summary and 'x: day' in summary and 'y: units' in summary
    assert 'lines at x: 0 1 2' in summary and "'demand': 2 4 8" in summary
    assert dict(kind='clipped_data', what="Line2D 'demand'", detail='1 of 3 points outside the axes view', material=False) in result.losses
    assert any(loss['kind'] == 'omitted' for loss in result.losses) == (rows == 2)


@pytest.mark.parametrize('cols,rows', [(60, 8), (60, 2), (1, 1)])
def test_compacted_bar_figure_uses_figure_description_and_reports_omitted_rows(cols, rows):
    ax = Figure().subplots()
    ax.barh(['North', 'South', 'East'], [-9, 3, 5], label='change')
    ax.set(title='Team change', xlabel='pp')
    result = render_compact(ax.figure, cols=cols, max_rows=rows)
    summary = result.summary()
    assert 'title: Team change' in summary and 'x: pp' in summary
    assert "barh 'change' n=3 North=-9 South=3 East=5" in summary
    assert any(loss['kind'] == 'omitted' for loss in result.losses) == bool(result.omitted)


def test_width_capacity_explanation_still_describes_figure_source():
    ax = Figure().subplots()
    ax.plot([0, 1, 2], [2, 4, 8], label='demand')
    ax.set_title('東')
    result = render_compact(ax.figure, cols=1, max_rows=2)
    assert result.mode == 'explanation'
    assert 'title: 東' in result.summary() and "'demand': 2 4 8" in result.summary()
    assert any(loss['kind'] == 'omitted' and loss['material'] for loss in result.losses)


@pytest.mark.parametrize('rows', [2, 40])
def test_svg_report_discloses_unavailable_values_and_unsupported_effect(rows):
    svg = '<svg width="200" height="100"><defs><mask id="m"/></defs><rect x="20" y="20" width="100" height="60" fill="red" mask="url(#m)"/></svg>'
    result = render_compact(svg, cols=60, max_rows=rows)
    assert 'values unavailable: SVG input carries shapes, not data' in result.summary()
    assert dict(kind='unsupported', what='mask #m', detail='drawn unmasked', material=True) in result.losses
    assert any(loss['kind'] == 'omitted' for loss in result.losses) == (rows == 2)


@pytest.mark.parametrize('rows', [2, 40])
def test_fallback_keeps_material_occlusion_losses(rows):
    ax = Figure().subplots()
    ax.plot([1, 3, 2, 4], color='tab:blue', label='actual')
    ax.plot([1, 3, 2, 4], color='tab:orange', label='forecast')
    result = render_compact(ax.figure, cols=60, max_rows=rows)
    assert dict(kind='lost_artist', what="Line2D 'actual'", detail='hidden: no visible cell', material=True) in result.losses
    assert "lost_artist Line2D 'actual': hidden: no visible cell" in result.summary()


def test_heatmap_explanation_keeps_sampling_and_lost_extreme_diagnostics():
    import numpy as np

    grid = np.zeros((100, 100))
    grid[50, 50] = 42
    ax = Figure().subplots()
    ax.imshow(grid, aspect='auto', vmin=0, vmax=42)
    result = render_compact(ax.figure, cols=40, max_rows=2)
    assert result.mode == 'explanation'
    assert any(loss['kind'] == 'heat_sampled' and not loss['material'] for loss in result.losses)
    assert any(loss['kind'] == 'lost_extreme' and 'max (50, 50)=42' in loss['what']
               and loss['material'] for loss in result.losses)
    assert 'shape=100x100' in result.summary() and '42' in result.summary()


def test_original_compact_result_constructor_remains_valid():
    result = CompactResult('chart', {'cols': 5, 'width': 5, 'height': 1}, [], 0, None, 'ranking')
    assert result.losses == [] and result.summary() == 'losses: none'


def test_report_preserves_errorbar_omissions_and_unsupported_artist_coverage():
    from matplotlib.patches import Wedge

    ax = Figure().subplots()
    ax.errorbar([0, 1], [2, 4], yerr=[1, 1], label='estimate')
    ax.add_patch(Wedge((.5, 3), .1, 0, 90))
    result = render_compact(ax.figure, cols=60, max_rows=2)
    summary = result.summary()
    assert '2±1 4±1' in summary
    assert 'sample support unavailable in summary' in summary
    assert 'not described: 1 Wedge' in summary
