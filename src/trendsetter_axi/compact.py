"""Opt-in bounded displays. Rankings use source values, never rasterized labels."""
from dataclasses import dataclass, field, replace
import math
from numbers import Integral

from .cells import CONTROLS, DisplayCapacityError, SGR, width, wrap
from .result import FIGURE, SVG, RenderResult, build


@dataclass
class CompactResult:
    text: str
    dimensions: dict
    records: list
    omitted: int | None
    reason: str | None
    mode: str
    losses: list = field(default_factory=list)
    report: RenderResult | None = None

    def summary(self):
        """Source facts and losses; unlike text, this report is not display-bounded."""
        report = self.report or RenderResult(self.text, self.dimensions, [], [], [], [], FIGURE)
        return replace(report, losses=self.losses).summary()


def _with_report(result, report):
    losses = list(report.losses)
    if result.omitted or result.mode == 'explanation':
        count = f'{result.omitted} source rows' if result.omitted is not None else 'full chart'
        losses.append(dict(kind='omitted', what='display', material=True,
                           detail=f'{count} not displayed: {result.reason}'))
    result.losses = losses
    result.report = replace(report, text=result.text, dimensions=result.dimensions, losses=losses)
    return result


def _source_report(fig, result):
    """Describe a non-raster display using source facts and source-view clipping.

    No raster ink was measured: omitted marks are disclosed by _with_report,
    not invented raster occlusion or sampling diagnostics.
    """
    from . import mpl

    artists = [a for ax in fig.axes if ax.get_visible()
               for a in [*ax.lines, *ax.collections, *ax.images, *ax.patches]]
    meta = dict(series=[], owners=[(a, 1) for a in artists], owned={}, drawn=set(),
                dropped=[], truncated=[], guessed=0)
    return build(result.text, meta, result.dimensions['cols'], *mpl.describe(fig, meta),
                 mpl.losses(fig, meta), FIGURE)


def _budget(cols, max_rows):
    if isinstance(cols, bool) or not isinstance(cols, int) or cols < 1:
        raise ValueError('cols must be a positive integer')
    if isinstance(max_rows, bool) or not isinstance(max_rows, int) or max_rows < 1:
        raise ValueError('max_rows must be a positive integer')


def _plain(value):
    text = SGR.sub('', str(value))
    if CONTROLS.search(text):
        raise ValueError('display labels must not contain control characters')
    return text


def _magnitude(value):
    return abs(int(value) if isinstance(value, Integral) else value)


def _result(lines, cols, records, omitted, reason, mode):
    return CompactResult('\n'.join(lines), dict(cols=cols, width=max(map(width, lines), default=0),
                                              height=len(lines)), records, omitted, reason, mode)


def _unavailable(cols, max_rows, records, reason):
    # ASCII explanation also works at one cell wide; never clip a data row.
    message = 'Display unavailable: ' + reason
    lines = wrap(message, cols)[:max_rows]
    return _result(lines, cols, records or [], len(records) if records is not None else None, reason, 'explanation')


def render_ranking(labels, values, *, cols=80, max_rows=12, title='', unit='', name='',
                   ascii=False, color=False, top_k=None):
    """One category per row, exact signed values and one shared magnitude scale.

    Input order is retained. top_k explicitly requests a stable descending ranking.
    Color is accepted for adapter symmetry; this view needs no color to convey signs.
    Long labels fall back to a wrapped exact table, never ambiguous truncation.
    records always retains every input row; omitted counts rows not displayed.
    """
    result = _ranking(labels, values, cols=cols, max_rows=max_rows, title=title, unit=unit,
                      name=name, ascii=ascii, color=color, top_k=top_k)
    series = [dict(kind='barh', name=_plain(name), axes=0, key=None, n=len(result.records),
                   values=[f"{r['label']}={r['exact']}" for r in result.records])]
    scales = [dict(axes=0, title=_plain(title), x=dict(label=_plain(unit), scale='linear'))]
    report = RenderResult(result.text, result.dimensions, series, scales, [], [], FIGURE)
    return _with_report(result, report)


def _ranking(labels, values, *, cols, max_rows, title, unit, name, ascii, color, top_k):
    _budget(cols, max_rows)
    labels, values = list(labels), list(values)
    if len(labels) != len(values):
        raise ValueError('labels and values must have equal lengths')
    records = []
    for label, value in zip(labels, values):
        if isinstance(value, bool) or not math.isfinite(value):
            raise ValueError('ranking values must be finite numbers')
        exact = str(value)
        if value > 0:
            exact = '+' + exact
        records.append(dict(label=_plain(label), value=value, exact=exact))
    if top_k is not None and (isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1):
        raise ValueError('top_k must be a positive integer')
    selected = sorted(records, key=lambda r: r['value'], reverse=True)[:top_k] if top_k is not None else records
    heading = ' / '.join(filter(None, map(_plain, (title, name))))
    if unit:
        heading += (' ' if heading else '') + '[' + _plain(unit) + ']'
    try:
        header = wrap(heading, cols) if heading else []
    except DisplayCapacityError:
        return _unavailable(cols, max_rows, records, 'heading cannot fit')
    if len(header) > max_rows or len(header) == max_rows and records:
        return _unavailable(cols, max_rows, records, 'heading exceeds row budget')
    label_width = max((width(r['label']) for r in records), default=0)
    value_width = max((width(r['exact']) for r in records), default=1)
    bar_width = min(12, cols - label_width - value_width - 2)
    mode = 'ranking' if bar_width >= 3 else 'table'
    blocks = []
    maximum = max((_magnitude(r['value']) for r in records), default=0)
    for record in selected:
        label, exact = record['label'], record['exact']
        if mode == 'ranking':
            size = round(_magnitude(record['value']) / maximum * bar_width) if maximum else 0
            bar = ('#' if ascii else '█') * size
            blocks.append([label + ' ' * (label_width - width(label) + 1)
                           + exact.rjust(value_width) + ' ' + bar])
        else:
            # Reserve one separating cell and the full value. Wrap only the label.
            available = cols - value_width - 1
            if available < 1:
                return _unavailable(cols, max_rows, records, 'exact value and label cannot fit')
            try:
                pieces = wrap(label, available)
            except DisplayCapacityError:
                return _unavailable(cols, max_rows, records, 'label character cannot fit')
            blocks.append([pieces[0] + ' ' * (available - width(pieces[0]) + 1) + exact.rjust(value_width),
                           *pieces[1:]])
    if len(selected) == len(records) and len(header) + sum(map(len, blocks)) <= max_rows:
        return _result([*header, *(line for block in blocks for line in block)], cols, records, 0, None, mode)
    # Reserve the omission line before accepting whole rows, not after clipping.
    lines, shown = list(header), 0
    for i, block in enumerate(blocks):
        remaining = len(records) - i - 1
        footer = [f'{remaining} omitted'] if remaining else []
        if len(lines) + len(block) + len(footer) > max_rows or any(width(s) > cols for s in footer):
            break
        lines.extend(block)
        shown += 1
    omitted = len(records) - shown
    if omitted:
        footer = f'{omitted} omitted'
        if width(footer) > cols or len(lines) >= max_rows:
            return _unavailable(cols, max_rows, records, 'omission notice cannot fit')
        lines.append(footer)
    return _result(lines, cols, records, omitted, 'row budget or top_k' if omitted else None, mode)


def render_compact(source, *, cols=80, max_rows=12, ascii=False, color=False):
    """Compact a single, zero-based horizontal bar series; bound other renders.

    Unsupported figures may use the existing renderer only if its complete output
    fits. Otherwise return a bounded explanation, never a cropped chart.
    """
    _budget(cols, max_rows)
    if not isinstance(source, (str, bytes)):
        from matplotlib.container import BarContainer
        from matplotlib.legend import Legend
        from matplotlib.ticker import NullFormatter, ScalarFormatter
        axes = [ax for ax in source.axes if ax.get_visible()]
        if len(axes) == 1:
            ax = axes[0]
            containers = [c for c in ax.containers if isinstance(c, BarContainer)]
            others = [a for a in [*ax.lines, *ax.collections, *ax.images, *ax.texts, *ax.artists,
                                   *source.texts, *source.legends, *source.lines, *source.patches,
                                   *source.images, *source.artists,
                                   *(a for a in ax.get_children() if isinstance(a, Legend))]
                      if a.get_visible()]
            if (len(containers) == 1 and containers[0].orientation == 'horizontal'
                    and not others and not source.subfigs and not ax.child_axes and not ax.get_ylabel()
                    and not any(ax.get_title(loc=loc) for loc in ('left', 'right'))
                    and ax.get_xscale() == ax.get_yscale() == 'linear'
                    and ax.xaxis.units is None
                    and type(ax.xaxis.get_major_formatter()) is ScalarFormatter
                    and all(type(axis.get_minor_formatter()) is NullFormatter for axis in (ax.xaxis, ax.yaxis))):
                bars = [b for b in containers[0] if b.get_visible()]
                extra_patches = [p for p in ax.patches if p.get_visible() and p not in bars]
                if bars and not extra_patches and all(b.get_x() == 0 for b in bars):
                    # Reading tick labels can create/update Tick artists. Do that on a
                    # copy too, not only when the raster renderer needs layout.
                    from . import _copy
                    work = _copy(source)
                    try:
                        ax = work.axes[source.axes.index(ax)]
                        container = next(c for c in ax.containers if isinstance(c, BarContainer))
                        bars = [b for b in container if b.get_visible()]
                        ticks = dict(zip(ax.get_yticks(), [t.get_text() for t in ax.get_yticklabels()]))
                        positions = [b.get_y() + b.get_height() / 2 for b in bars]
                        values = [b.get_width() for b in bars]
                        if (all(p in ticks for p in positions) and all(math.isfinite(v) for v in values)
                                and not ax.yaxis.get_major_formatter().get_offset()):
                            label = container.get_label()
                            name = '' if not label or label.startswith('_') else label
                            try:
                                labels = [_plain(ticks[p]) for p in positions]
                                title, unit, name = map(_plain, (ax.get_title(), ax.get_xlabel(), name))
                            except ValueError:
                                pass
                            else:
                                result = render_ranking(labels, values, cols=cols, max_rows=max_rows,
                                                        title=title, unit=unit, name=name, ascii=ascii, color=color)
                                return _with_report(result, _source_report(work, result))
                    finally:
                        if work.canvas.manager is not None:
                            import matplotlib.pyplot as plt
                            plt.close(work)
    from . import render
    try:
        result = render(source, cols=cols, rows=max_rows, ascii=ascii, color=color)
    except DisplayCapacityError:
        compact = _unavailable(cols, max_rows, None, 'full chart cannot fit display width; request more columns')
        if isinstance(source, (str, bytes)):
            report = RenderResult(compact.text, compact.dimensions, [], [], [], [], SVG)
        else:
            from . import _copy
            work = _copy(source)
            try:
                report = _source_report(work, compact)
            finally:
                if work.canvas.manager is not None:
                    import matplotlib.pyplot as plt
                    plt.close(work)
        return _with_report(compact, report)
    if result.dimensions['height'] <= max_rows:
        compact = _result(result.text.split('\n'), cols, [], 0, None, 'figure')
    else:
        compact = _unavailable(cols, max_rows, None, 'full chart exceeds row budget; request more rows')
    return _with_report(compact, result)
