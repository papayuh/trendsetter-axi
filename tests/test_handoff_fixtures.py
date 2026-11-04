"""Study fixtures: precise answers come from records, not shaded/raster geometry."""
import numpy as np
from matplotlib.figure import Figure
import pytest

from trendsetter_axi import render


@pytest.mark.parametrize('cols', [60, 80])
def test_calibration_interval_removal_is_disclosed_without_inventing_support(cols):
    scores = np.array([.1, .3, .5, .7, .9])
    counts = np.array([50, 120, 800, 100, 20])
    events = np.array([6, 35, 360, 69, 12])
    observed = events / counts
    z = 1.959963984540054
    center = (observed + z*z/(2*counts)) / (1 + z*z/counts)
    radius = z*np.sqrt(observed*(1-observed)/counts + z*z/(4*counts*counts)) / (1 + z*z/counts)
    outputs = []
    for intervals in (True, False):
        ax = Figure(figsize=(7.5, 3.4)).subplots()
        ax.plot(scores, observed, marker='o', label='observed')
        ax.plot([0, 1], [0, 1], label='ideal')
        if intervals:
            ax.errorbar(scores, observed, yerr=[observed-center+radius, center+radius-observed], fmt='none')
        for x, y, count in zip(scores, observed, counts):
            ax.annotate(f'n={count}', (x, y))
        ax.set(xlim=(0, 1), ylim=(0, 1))
        outputs.append(render(ax.figure, cols, rows=18))
    with_intervals, control = outputs
    assert with_intervals.text != control.text
    assert with_intervals.summary() != control.summary()
    assert with_intervals.summary_omissions and not control.summary_omissions
    assert 'sample support unavailable' in with_intervals.summary()
    interval = next(s for s in with_intervals.series if s['kind'] == 'errorbar')
    assert interval['points'][:, 1] == pytest.approx(center)
    assert np.array(interval['yerr'], float) == pytest.approx(radius, rel=5e-4)
    assert 'centers inferred from segment midpoints' in with_intervals.summary()
    assert abs(observed[-1] - scores[-1]) == pytest.approx(.3)
    assert counts[np.argmax(abs(observed - scores))] == 20
    contributions = abs(events - counts*scores) / counts.sum() * 100
    assert np.argmax(contributions) == 2 and contributions[2] == pytest.approx(3.66972477)
    assert sum(contributions) / 100 == pytest.approx(49/1090)


@pytest.mark.parametrize('cols', [60, 80])
def test_cohorts_keep_future_missing_distinct_from_observed_zero(cols):
    data = np.array([[100, 75, 50, 25, 0], [100, 70, 40, 20, np.nan],
                     [100, 65, 35, np.nan, np.nan], [100, 60, np.nan, np.nan, np.nan],
                     [100, np.nan, np.nan, np.nan, np.nan]])
    outputs = []
    for values in (np.ma.masked_invalid(data), np.nan_to_num(data)):
        ax = Figure(figsize=(7.5, 3.4)).subplots()
        ax.imshow(values, vmin=0, vmax=100)
        ax.set_xticks(range(5), ['M0', 'M1', 'M2', 'M3', 'M4'])
        ax.set_yticks(range(5), ['Jan', 'Feb', 'Mar', 'Apr', 'May'])
        ax.set_title('Retention: blank = unavailable')
        outputs.append(render(ax.figure, cols, rows=18))
    actual, zero_filled = outputs
    series = actual.series[0]
    assert series['missing'] == 10 and series['n'] == 15
    assert series['grid'][0] == 'Jan: 100 75 50 25 0'
    assert sum(line.count('.') for line in series['grid']) == 10
    assert 'blank = unavailable' in actual.summary()
    assert zero_filled.series[0]['missing'] == 0 and actual.text != zero_filled.text


def forecast(half):
    weeks = list(range(1, 9))
    ax = Figure(figsize=(7.5, 3.4)).subplots()
    ax.fill_between(weeks, [100-h for h in half], [100+h for h in half], label='80% interval')
    ax.plot(weeks, [100]*8, label='Median')
    ax.set(xlim=(1, 8), ylim=(80, 120), xlabel='Week', ylabel='Units')
    ax.set_xticks(weeks)
    ax.legend(frameon=False)
    return ax.figure


@pytest.mark.parametrize('cols', [60, 80])
def test_forecast_never_claims_global_range_answers_a_paired_crossing(cols):
    widths = ([2, 4, 6, 8, 10, 12, 14, 16], [2, 14, 6, 8, 10, 12, 4, 16])
    assert [next(w for w, h in enumerate(half, 1) if 2*h >= 24) for half in widths] == [6, 2]
    a, b = [render(forecast(half), cols, rows=18) for half in widths]
    assert a.text != b.text
    for result in (a, b):
        assert 'paired bounds and sample support unavailable' in result.summary()
        assert result.summary_omissions
        assert all(loss['kind'] != 'summary_omission' for loss in result.losses)


@pytest.mark.parametrize('cols', [60, 80])
def test_ecdf_step_semantics_distinguish_straight_line_control(cols):
    results = []
    for style in ('steps-post', 'default'):
        ax = Figure(figsize=(7.5, 3.4)).subplots()
        for label, counts in [('A', [50, 45, 5]), ('B', [50, 40, 10])]:
            cumulative = np.cumsum(counts)
            ax.plot([100, 160, 1000], cumulative, drawstyle=style, label=label)
            assert cumulative[1] == (95 if label == 'A' else 90)  # 160 <= 300 < 1000, post-step
        ax.set(xlim=(0, 1100), ylim=(0, 100), xlabel='ms')
        results.append(render(ax.figure, cols, rows=18))
    step, straight = results
    assert step.text != straight.text and step.summary() != straight.summary()
    assert all(s['drawstyle'] == 'steps-post' for s in step.series)
    assert 'steps-post' in step.summary() and 'steps-post' not in straight.summary()


def survival(records):
    ax = Figure(figsize=(7.5, 3.4)).subplots()
    times, probabilities, censored = [0], [1.0], []
    probability = 1.
    for day in sorted(set(day for day, _ in records)):
        risk = sum(t >= day for t, _ in records)
        events = sum(t == day and event for t, event in records)
        probability *= 1 - events/risk
        times.append(day)
        probabilities.append(probability)
        if any(t == day and not event for t, event in records):
            censored.append((day, probability))
    ax.step(times, probabilities, where='post', label='survival')
    ax.plot(*zip(*censored), linestyle='none', marker='+', color='black')
    ax.set(xlim=(0, 11), ylim=(0, 1.05))
    return ax.figure, probabilities


@pytest.mark.parametrize('cols', [60, 80])
def test_survival_risk_requires_records_even_when_drawing_is_identical(cols):
    early = [(2, 1), (3, 0), (4, 0), (10, 0)]
    late = [(2, 1), (7, 0), (8, 0), (10, 0)]
    records = [early, late, early*2]
    assert [sum(day >= 6 for day, _ in dataset) for dataset in records] == [1, 3, 2]
    fixtures = [survival(dataset) for dataset in records]
    assert all(min(probabilities) > .5 for _, probabilities in fixtures)  # median unreached
    outputs = [render(fig, cols, rows=18) for fig, _ in fixtures]
    assert outputs[0].text != outputs[1].text
    assert outputs[0].text == outputs[2].text  # geometry cannot establish absolute counts
    assert 'steps-post' in outputs[0].summary()


@pytest.mark.parametrize('style', ['steps-pre', 'steps-post', 'steps-mid', 'default'])
@pytest.mark.parametrize('descending', [False, True])
@pytest.mark.parametrize('count', [8, 18])
def test_line_summary_samples_follow_drawstyle(style, descending, count):
    x = list(range(0, count * 3, 3))
    split = 7 if count == 18 else 3
    y = [0] * split + [100] * (count - split)
    if descending:
        x, y = x[::-1], y[::-1]
    ax = Figure().subplots()
    ax.plot(x, y, drawstyle=style)
    series = render(ax.figure).series[0]
    assert series['sampled'] == (count > 16)
    # T1: samples are source observations for every style, not interpolated step lookups.
    pairs = list(zip(map(float, series['at']), map(float, series['ys'])))
    assert all(pair in list(zip(x, y)) for pair in pairs)
    assert pairs[0] == (x[0], y[0]) and pairs[-1] == (x[-1], y[-1])
    assert [x.index(at) for at, _ in pairs] == sorted(x.index(at) for at, _ in pairs)
    if count > 16:
        assert series['values'][-2:] == [f'min {x[y.index(min(y))]}={min(y)}', f'max {x[y.index(max(y))]}={max(y)}']
    if style != 'default':
        assert series['drawstyle'] == style
        assert style in render(ax.figure).summary()
    else:
        assert 'drawstyle' not in series
    if count == 8:
        assert list(map(float, series['at'])) == x
        assert list(map(float, series['ys'])) == y


@pytest.mark.parametrize('style', ['steps-pre', 'steps-post', 'steps-mid'])
@pytest.mark.parametrize('ordering', ['unsorted', 'repeated'])
def test_nonmonotonic_step_summary_retains_source_knots(style, ordering):
    x = list(range(0, 54, 3))
    y = [0] * 7 + [100] * 11
    if ordering == 'unsorted':
        x[5], x[10] = x[10], x[5]
    else:
        x[5] = x[4]
    ax = Figure().subplots()
    ax.plot(x, y, drawstyle=style)
    series = render(ax.figure).series[0]
    assert series['sampled']
    assert all((float(at), float(value)) in list(zip(x, y)) for at, value in zip(series['at'], series['ys']))
