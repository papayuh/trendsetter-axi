"""Held-out split: 12 charts written before any renderer change for the benchmark, used only to check the changes, never to tune them.

Same question types, tolerances and grading as charts.py; different data, shapes and wording.
"""
import numpy as np

from charts import MONTHS, count, label, num, plt, span

HELDOUT = {}


def chart(kind):
    def register(fn):
        HELDOUT[fn.__name__] = (kind, fn)
        return fn
    return register


@chart("line")
def ho_unemployment():
    rng = np.random.default_rng(101)
    m = np.arange(1, 37)
    rate = 5.5 - 1.6 * np.sin((m - 4) / 36 * np.pi) + rng.normal(0, 0.12, 36)
    fig, ax = plt.subplots()
    ax.plot(m, rate)
    ax.set(title="Unemployment rate", xlabel="Month", ylabel="%")
    return fig, [
        num("What is the highest rate?", rate.max(), span(rate)),
        num("In which month is the rate lowest?", m[rate.argmin()], 35),
        num("What is the rate in month 30?", rate[29], span(rate)),
        label("Is the rate in month 36 higher or lower than in month 1?", "higher" if rate[-1] > rate[0] else "lower", ["higher", "lower"]),
    ]


@chart("line")
def ho_sensor():
    rng = np.random.default_rng(103)
    t = np.linspace(0, 200, 400)
    v = 20 + 6 * np.sin(t / 25) + rng.normal(0, 0.6, 400)
    fig, ax = plt.subplots()
    ax.plot(t, v)
    ax.set(title="Tank temperature", xlabel="Seconds", ylabel="°C")
    return fig, [
        num("What is the maximum temperature?", v.max(), span(v)),
        num("At about what time is the first maximum?", t[:200][v[:200].argmax()], 200),
        num("What is the minimum temperature?", v.min(), span(v)),
    ]


@chart("line")
def ho_bacteria_log():
    h = np.arange(0, 11)
    cells = 50 * 2.6 ** h
    fig, ax = plt.subplots()
    ax.plot(h, cells, marker="o")
    ax.set_yscale("log")
    ax.set(title="Colony size (log scale)", xlabel="Hour", ylabel="Cells")
    return fig, [
        dict(num("How many cells at hour 6?", cells[6], 1), tol=round(cells[6] * 0.15, 1)),
        dict(num("How many cells at hour 10?", cells[10], 1), tol=round(cells[10] * 0.15, 1)),
        label("Is the growth faster than linear?", "yes", ["yes", "no"]),
    ]


@chart("multi-line")
def ho_revenue_lines():
    q = np.arange(1, 9)
    lines = {"Cloud": np.array([12, 15, 19, 24, 30, 37, 45, 54]), "Devices": np.array([40, 38, 41, 37, 36, 39, 35, 34]),
             "Ads": np.array([22, 25, 23, 28, 30, 29, 33, 36])}
    fig, ax = plt.subplots()
    for name, y in lines.items():
        ax.plot(q, y, marker="o", label=name)
    ax.legend()
    ax.set(title="Revenue by segment", xlabel="Quarter", ylabel="$M")
    names = list(lines)
    arr = np.array(list(lines.values()))
    growth = arr[:, -1] - arr[:, 0]
    return fig, [
        label("Which segment is highest in quarter 8?", names[arr[:, -1].argmax()], names),
        label("Which segment grew the most from quarter 1 to quarter 8?", names[growth.argmax()], names),
        num("What is Ads revenue in quarter 4?", lines["Ads"][3], span(arr)),
        label("Which segment is highest in quarter 1?", names[arr[:, 0].argmax()], names),
    ]


@chart("multi-line")
def ho_two_sites():
    rng = np.random.default_rng(107)
    w = np.arange(1, 53)
    a = 15 + 10 * np.sin((w - 14) / 52 * 2 * np.pi) + rng.normal(0, 1, 52)
    b = 18 + 4 * np.sin((w - 14) / 52 * 2 * np.pi) + rng.normal(0, 1, 52)
    fig, ax = plt.subplots()
    ax.plot(w, a, label="Inland")
    ax.plot(w, b, label="Coastal")
    ax.legend()
    ax.set(title="Weekly mean temperature", xlabel="Week", ylabel="°C")
    return fig, [
        label("Which site is warmer in week 27?", "Inland" if a[26] > b[26] else "Coastal", ["Inland", "Coastal"]),
        label("Which site is warmer in week 2?", "Inland" if a[1] > b[1] else "Coastal", ["Inland", "Coastal"]),
        num("What is Coastal's highest weekly temperature?", b.max(), span(np.concatenate([a, b]))),
    ]


@chart("bar")
def ho_countries():
    names = ["Norway", "Chile", "Kenya", "Japan", "Peru", "Spain", "India", "Ghana", "Chad", "Laos"]
    v = np.array([71, 54, 38, 66, 42, 59, 47, 33, 21, 29])
    fig, ax = plt.subplots()
    ax.bar(names, v)
    ax.set(title="Renewable share of electricity", ylabel="%")
    order = np.argsort(v)[::-1]
    return fig, [
        label("Which country has the second-highest share?", names[order[1]], names),
        count("How many countries are above 45%?", (v > 45).sum()),
        num("What is Peru's share?", v[4], v.max()),
    ]


@chart("bar")
def ho_survey_barh():
    items = ["Price", "Speed", "Support", "Docs", "Design", "Security", "Uptime", "API", "Mobile", "Search", "Export", "Billing"]
    v = np.array([3.9, 4.2, 3.1, 2.8, 3.6, 4.5, 4.4, 3.3, 2.6, 3.0, 2.9, 3.4])
    fig, ax = plt.subplots()
    ax.barh(items, v)
    ax.set(title="Satisfaction by area (1-5)", xlabel="Mean score")
    return fig, [
        label("Which area scores lowest?", items[v.argmin()], items),
        count("How many areas score below 3.0?", (v < 3.0).sum()),
        num("What is the score for Support?", v[2], v.max()),
    ]


@chart("bar")
def ho_grouped_three():
    years = ["2021", "2022", "2023", "2024"]
    s = {"North": np.array([14, 18, 21, 19]), "South": np.array([16, 15, 17, 23]), "West": np.array([11, 19, 16, 20])}
    x = np.arange(4)
    fig, ax = plt.subplots()
    for i, (name, y) in enumerate(s.items()):
        ax.bar(x + (i - 1) * 0.27, y, 0.27, label=name)
    ax.set_xticks(x, years)
    ax.legend()
    ax.set(title="New stores opened", ylabel="Stores")
    names = list(s)
    arr = np.array(list(s.values()))
    return fig, [
        label("In 2024, which region opened the most stores?", names[arr[:, 3].argmax()], names),
        label("In 2022, which region opened the most stores?", names[arr[:, 1].argmax()], names),
        num("How many stores did West open in 2023?", s["West"][2], arr.max()),
    ]


@chart("scatter")
def ho_ads():
    rng = np.random.default_rng(109)
    spend = rng.uniform(1, 20, 60)
    sales = 40 + 3.5 * spend + rng.normal(0, 6, 60)
    fig, ax = plt.subplots()
    ax.scatter(spend, sales, s=10)
    ax.set(title="Ad spend vs sales", xlabel="Spend ($k)", ylabel="Sales ($k)")
    return fig, [
        label("Is the relationship positive or negative?", "positive", ["positive", "negative"]),
        num("What is the largest sales value?", sales.max(), span(sales)),
        num("What is the smallest spend value?", spend.min(), span(spend)),
    ]


@chart("heatmap")
def ho_region_month():
    rng = np.random.default_rng(113)
    regions = ["North", "South", "East", "West"]
    z = np.round(rng.uniform(20, 60, (4, 6)), 1)
    z[2, 4] = 88.0
    fig, ax = plt.subplots()
    im = ax.imshow(z, cmap="Blues")
    fig.colorbar(im, label="Units")
    ax.set_xticks(range(6), MONTHS[:6])
    ax.set_yticks(range(4), regions)
    ax.set_title("Units sold by region and month")
    i, j = np.unravel_index(z.argmax(), z.shape)
    return fig, [
        label("Which region has the highest cell?", regions[i], regions),
        label("Which month is the highest cell in?", MONTHS[j], MONTHS[:6]),
        num("What is the value for South in Feb?", z[1, 1], span(z)),
        label("Which region has the lowest total?", regions[z.sum(1).argmin()], regions),
    ]


@chart("heatmap")
def ho_corr_six():
    names = ["age", "income", "debt", "score", "tenure", "churn"]
    c = np.array([[1, .48, .12, .33, .57, -.41], [.48, 1, -.22, .61, .35, -.52], [.12, -.22, 1, -.68, .05, .44],
                  [.33, .61, -.68, 1, .29, -.63], [.57, .35, .05, .29, 1, -.37], [-.41, -.52, .44, -.63, -.37, 1]])
    fig, ax = plt.subplots()
    im = ax.imshow(c, cmap="coolwarm", vmin=-1, vmax=1)
    fig.colorbar(im)
    ax.set_xticks(range(6), names)
    ax.set_yticks(range(6), names)
    ax.set_title("Customer feature correlations")
    return fig, [
        label("Which variable is most negatively correlated with score?", names[c[3].argmin()], [n for n in names if n != "score"]),
        num("What is the correlation between income and churn?", c[1, 5], 2),
        label("Which variable is most positively correlated with age (excluding itself)?", names[np.argsort(c[0])[-2]], [n for n in names if n != "age"]),
    ]


@chart("histogram")
def ho_wait_times():
    rng = np.random.default_rng(127)
    v = rng.exponential(6, 1500)
    v = v[v < 40]
    counts, edges = np.histogram(v, bins=20)
    fig, ax = plt.subplots()
    ax.hist(v, bins=edges)
    ax.set(title="Support wait times", xlabel="Minutes", ylabel="Tickets")
    return fig, [
        label("Is the distribution skewed left or right?", "right", ["left", "right"]),
        num("How many tickets are in the tallest bin?", counts.max(), counts.max()),
        count("How many bins have more than 100 tickets?", (counts > 100).sum()),
    ]
