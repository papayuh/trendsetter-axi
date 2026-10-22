"""The 25 benchmark charts. Each builder returns (figure, questions); every answer is computed from the data the chart is drawn from, never read off a render.

Question types: "number" is right within `tol` (absolute); "label" is right when it matches the answer (case and spaces ignored);
"int" must be exact. Number tolerances are a fixed share of the plotted data's span, stated per question.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CHARTS = {}


def chart(kind):
    def register(fn):
        CHARTS[fn.__name__] = (kind, fn)
        return fn
    return register


def num(q, answer, span, share=0.05):
    """A number question, right within `share` of `span` (the data's range on that axis)."""
    return dict(q=q, type="number", answer=round(float(answer), 4), tol=round(float(span) * share, 4))


def label(q, answer, options):
    return dict(q=q, type="label", answer=str(answer), options=[str(o) for o in options])


def count(q, answer):
    return dict(q=q, type="int", answer=int(answer))


def span(a):
    return float(np.nanmax(a) - np.nanmin(a))


# ---- single lines -------------------------------------------------------------------------

@chart("line")
def line_stock():
    rng = np.random.default_rng(1)
    days = np.arange(250)
    price = 100 * np.exp(np.cumsum(rng.normal(0.0008, 0.015, 250)))
    fig, ax = plt.subplots()
    ax.plot(days, price)
    ax.set(title="ACME daily close", xlabel="Trading day", ylabel="Price ($)")
    return fig, [
        num("What is the highest closing price?", price.max(), span(price)),
        num("On which trading day is the highest close?", days[price.argmax()], 249),
        num("What is the closing price on trading day 125?", price[125], span(price)),
        label("Is the last close higher or lower than the first close?", "higher" if price[-1] > price[0] else "lower", ["higher", "lower"]),
    ]


@chart("line")
def line_temperature():
    temp = np.array([2.1, 3.4, 7.8, 12.5, 16.9, 20.6, 23.4, 22.8, 18.7, 12.9, 7.2, 3.3])
    fig, ax = plt.subplots()
    ax.plot(range(1, 13), temp, marker="o")
    ax.set(title="Mean monthly temperature", xlabel="Month (1 = Jan)", ylabel="°C")
    return fig, [
        count("Which month number (1-12) is warmest?", temp.argmax() + 1),
        num("What is the temperature in month 4?", temp[3], span(temp)),
        num("What is the lowest temperature?", temp.min(), span(temp)),
    ]


@chart("line")
def line_visits():
    rng = np.random.default_rng(3)
    d = np.arange(60)
    visits = 1200 + 8 * d + 180 * np.sin(2 * np.pi * d / 7) + rng.normal(0, 40, 60)
    fig, ax = plt.subplots()
    ax.plot(d, visits)
    ax.set(title="Daily site visits", xlabel="Day", ylabel="Visits")
    return fig, [
        label("Over the 60 days, is the overall trend up or down?", "up", ["up", "down"]),
        num("What is the value on the last day?", visits[-1], span(visits)),
        num("What is the maximum value?", visits.max(), span(visits)),
    ]


@chart("line")
def line_decay():
    t = np.linspace(0, 20, 40)
    level = 80 * np.exp(-t / 6) + 5
    half = t[np.argmax(level < level[0] / 2)]
    fig, ax = plt.subplots()
    ax.plot(t, level)
    ax.set(title="Drug concentration after dose", xlabel="Hours", ylabel="mg/L")
    return fig, [
        num("What is the concentration at hour 0?", level[0], span(level)),
        num("At about what hour does the concentration first fall below half its starting value?", half, 20),
        num("What is the concentration at the last hour shown?", level[-1], span(level)),
    ]


@chart("line")
def line_log_users():
    years = np.arange(2012, 2025)
    users = 1000 * 1.9 ** (years - 2012)
    fig, ax = plt.subplots()
    ax.plot(years, users, marker="o")
    ax.set_yscale("log")
    ax.set(title="Registered users (log scale)", xlabel="Year", ylabel="Users")
    return fig, [
        label("Is the y axis linear or logarithmic?", "logarithmic", ["linear", "logarithmic"]),
        dict(num("How many users in 2020?", users[8], 1), tol=round(users[8] * 0.15, 1)),   # log axis: within 15%
        dict(num("How many users in 2012?", users[0], 1), tol=round(users[0] * 0.15, 1)),
    ]


# ---- multiple lines -----------------------------------------------------------------------

@chart("multi-line")
def ml_products():
    m = np.arange(1, 25)
    a = 50 + 2.5 * m
    b = 120 - 1.5 * m + 6 * np.sin(m / 2)
    fig, ax = plt.subplots()
    ax.plot(m, a, label="Alpha")
    ax.plot(m, b, label="Beta")
    ax.legend()
    ax.set(title="Monthly units sold", xlabel="Month", ylabel="Units")
    both = np.concatenate([a, b])
    return fig, [
        label("Which product sells more in month 6?", "Alpha" if a[5] > b[5] else "Beta", ["Alpha", "Beta"]),
        label("Which product sells more in month 20?", "Alpha" if a[19] > b[19] else "Beta", ["Alpha", "Beta"]),
        num("At about which month do the two lines cross?", m[np.argmax(a > b)] - 0.5, 23),
        num("What is Beta's highest value?", b.max(), span(both)),
    ]


@chart("multi-line")
def ml_cities():
    temps = {
        "Oslo": [-4.3, -4.0, -0.2, 4.5, 10.8, 15.2, 16.4, 15.2, 10.8, 6.3, 0.7, -3.1],
        "Madrid": [6.3, 7.9, 10.9, 12.9, 16.7, 22.4, 25.6, 25.1, 20.9, 15.1, 9.9, 6.9],
        "Cairo": [14.0, 15.3, 17.6, 21.5, 24.7, 27.2, 28.0, 28.1, 26.2, 23.6, 19.2, 15.5],
        "Toronto": [-5.5, -4.5, -0.1, 7.1, 13.1, 18.6, 21.5, 20.6, 16.2, 9.5, 3.7, -2.2],
    }
    fig, ax = plt.subplots()
    for city, t in temps.items():
        ax.plot(range(1, 13), t, label=city)
    ax.legend()
    ax.set(title="Mean monthly temperature by city", xlabel="Month", ylabel="°C")
    arr = np.array(list(temps.values()))
    names = list(temps)
    return fig, [
        label("Which city is warmest in month 7?", names[arr[:, 6].argmax()], names),
        label("Which city is coldest in month 1?", names[arr[:, 0].argmin()], names),
        num("What is Madrid's temperature in month 7?", temps["Madrid"][6], span(arr)),
        count("In how many months is Oslo colder than Toronto?", (arr[0] < arr[3]).sum()),
    ]


@chart("multi-line")
def ml_rates():
    rng = np.random.default_rng(7)
    weeks = np.arange(100)
    series = {name: start + np.cumsum(rng.normal(drift, 0.04, 100))
              for name, start, drift in (("2y", 4.6, -0.012), ("10y", 4.1, -0.002), ("30y", 4.3, 0.004))}
    fig, ax = plt.subplots()
    for name, y in series.items():
        ax.plot(weeks, y, label=name)
    ax.legend()
    ax.set(title="Treasury yields", xlabel="Week", ylabel="Yield (%)")
    names = list(series)
    end = [y[-1] for y in series.values()]
    start = [y[0] for y in series.values()]
    allv = np.concatenate(list(series.values()))
    return fig, [
        label("Which series is highest in the last week?", names[int(np.argmax(end))], names),
        label("Which series is highest in week 0?", names[int(np.argmax(start))], names),
        num("What is the 2y yield in the last week?", series["2y"][-1], span(allv)),
    ]


@chart("multi-line")
def ml_cpu():
    rng = np.random.default_rng(11)
    h = np.arange(48)
    servers = {
        "web-1": 35 + 25 * np.clip(np.sin((h - 6) / 24 * 2 * np.pi), 0, None) + rng.normal(0, 3, 48),
        "web-2": 30 + 20 * np.clip(np.sin((h - 8) / 24 * 2 * np.pi), 0, None) + rng.normal(0, 3, 48),
        "db-1": 55 + rng.normal(0, 4, 48),
    }
    servers["db-1"][30] = 97
    fig, ax = plt.subplots()
    for name, y in servers.items():
        ax.plot(h, y, label=name)
    ax.legend()
    ax.set(title="CPU utilisation", xlabel="Hour", ylabel="CPU (%)")
    names = list(servers)
    peaks = [y.max() for y in servers.values()]
    at12 = [y[12] for y in servers.values()]
    return fig, [
        label("Which server reaches the highest CPU?", names[int(np.argmax(peaks))], names),
        num("At which hour is that highest CPU reading?", servers["db-1"].argmax(), 47),
        label("Which server is lowest at hour 2?", names[int(np.argmin([y[2] for y in servers.values()]))], names),
        label("Which server is highest at hour 12?", names[int(np.argmax(at12))], names),
    ]


@chart("multi-line")
def ml_forecast():
    rng = np.random.default_rng(5)
    d = np.arange(30)
    actual = 200 + 3 * d + rng.normal(0, 12, 30)
    forecast = 205 + 2.2 * d
    fig, ax = plt.subplots()
    ax.plot(d, actual, label="actual")
    ax.plot(d, forecast, "--", label="forecast")
    ax.legend()
    ax.set(title="Orders: actual vs forecast", xlabel="Day", ylabel="Orders")
    both = np.concatenate([actual, forecast])
    return fig, [
        label("On the last day, is actual above or below forecast?", "above" if actual[-1] > forecast[-1] else "below", ["above", "below"]),
        num("What is the highest actual value?", actual.max(), span(both)),
        num("What is the forecast on day 0?", forecast[0], span(both)),
    ]


# ---- bars ---------------------------------------------------------------------------------

@chart("bar")
def bar_regions():
    regions = ["North", "South", "East", "West", "Central", "Coast"]
    sales = np.array([412, 287, 530, 365, 198, 451])
    fig, ax = plt.subplots()
    ax.bar(regions, sales)
    ax.set(title="Q3 sales by region", ylabel="Sales ($k)")
    return fig, [
        label("Which region has the highest sales?", regions[sales.argmax()], regions),
        label("Which region has the lowest sales?", regions[sales.argmin()], regions),
        count("How many regions have sales above 400?", (sales > 400).sum()),
        num("What are West's sales?", sales[3], sales.max()),
    ]


@chart("bar")
def bar_fifteen():
    rng = np.random.default_rng(13)
    cats = [f"P{i:02d}" for i in range(1, 16)]
    vals = rng.integers(20, 100, 15)
    fig, ax = plt.subplots()
    ax.bar(cats, vals)
    ax.tick_params(axis="x", labelrotation=90)
    ax.set(title="Defects per product line", ylabel="Defects")
    return fig, [
        label("Which product line has the most defects?", cats[vals.argmax()], cats),
        count("How many product lines have more than 60 defects?", (vals > 60).sum()),
        num("How many defects does P07 have?", vals[6], vals.max()),
    ]


@chart("bar")
def barh_languages():
    langs = ["Python", "JavaScript", "SQL", "Java", "Go", "Rust", "C#", "R"]
    share = np.array([51.0, 62.3, 51.5, 30.3, 13.5, 12.6, 27.1, 4.3])
    fig, ax = plt.subplots()
    ax.barh(langs, share)
    ax.set(title="Developers using each language", xlabel="% of respondents")
    return fig, [
        label("Which language has the largest share?", langs[share.argmax()], langs),
        count("How many languages are above 25%?", (share > 25).sum()),
        num("What is Go's share?", share[4], share.max()),
    ]


@chart("bar")
def bar_grouped():
    q = ["Q1", "Q2", "Q3", "Q4", "Q5"]
    a = np.array([23, 31, 28, 40, 36])
    b = np.array([27, 25, 33, 38, 41])
    x = np.arange(5)
    fig, ax = plt.subplots()
    ax.bar(x - 0.2, a, 0.4, label="Store A")
    ax.bar(x + 0.2, b, 0.4, label="Store B")
    ax.set_xticks(x, q)
    ax.legend()
    ax.set(title="Revenue by quarter", ylabel="Revenue ($k)")
    return fig, [
        label("In Q3, which store has higher revenue?", "Store A" if a[2] > b[2] else "Store B", ["Store A", "Store B"]),
        count("In how many quarters is Store A higher than Store B?", (a > b).sum()),
        num("What is the highest revenue of any bar?", max(a.max(), b.max()), max(a.max(), b.max())),
    ]


@chart("bar")
def bar_profit():
    pnl = np.array([12, 8, -5, -14, 3, 21, 17, -9, 6, 25, -2, 30])
    fig, ax = plt.subplots()
    ax.bar(MONTHS, pnl)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set(title="Monthly profit / loss", ylabel="$k")
    return fig, [
        count("How many months have a loss (below zero)?", (pnl < 0).sum()),
        label("Which month has the biggest loss?", MONTHS[pnl.argmin()], MONTHS),
        num("What is the best month's profit?", pnl.max(), span(pnl)),
    ]


# ---- scatter ------------------------------------------------------------------------------

@chart("scatter")
def sc_height_weight():
    rng = np.random.default_rng(17)
    h = rng.normal(172, 9, 80)
    w = 0.9 * (h - 100) + rng.normal(0, 6, 80)
    fig, ax = plt.subplots()
    ax.scatter(h, w, s=10)
    ax.set(title="Height vs weight", xlabel="Height (cm)", ylabel="Weight (kg)")
    return fig, [
        label("Is the relationship positive or negative?", "positive", ["positive", "negative"]),
        num("What is the largest weight shown?", w.max(), span(w)),
        num("What is the smallest height shown?", h.min(), span(h)),
    ]


@chart("scatter")
def sc_clusters():
    rng = np.random.default_rng(19)
    a = rng.normal([2, 3], 0.6, (40, 2))
    b = rng.normal([6, 7], 0.8, (40, 2))
    fig, ax = plt.subplots()
    ax.scatter(*a.T, s=10, label="Group A")
    ax.scatter(*b.T, s=10, label="Group B")
    ax.legend()
    ax.set(title="Two customer segments", xlabel="Visits / month", ylabel="Spend ($100)")
    ys = np.concatenate([a[:, 1], b[:, 1]])
    return fig, [
        label("Which group has higher spend on average?", "Group B", ["Group A", "Group B"]),
        num("About what is the average spend of Group A?", a[:, 1].mean(), span(ys), 0.1),
        num("What is the largest visits value in Group A?", a[:, 0].max(), span(np.concatenate([a[:, 0], b[:, 0]]))),
    ]


@chart("scatter")
def sc_outlier():
    rng = np.random.default_rng(23)
    x = rng.uniform(0, 10, 50)
    y = 2 * x + rng.normal(0, 1.5, 50)
    x[17], y[17] = 3.0, 45.0
    fig, ax = plt.subplots()
    ax.scatter(x, y, s=12)
    ax.set(title="Latency vs payload size", xlabel="Payload (MB)", ylabel="Latency (ms)")
    return fig, [
        num("One point is a clear outlier. What is its x value?", x[17], span(x)),
        num("What is the outlier's y value?", y[17], span(y)),
        count("How many points have y above 30?", (y > 30).sum()),
    ]


# ---- heatmaps -----------------------------------------------------------------------------

@chart("heatmap")
def hm_monthly():
    rng = np.random.default_rng(29)
    years = [str(y) for y in range(2019, 2025)]
    z = 3 + 0.4 * np.sin(np.arange(12) / 12 * 2 * np.pi)[None, :] + rng.normal(0, 0.15, (6, 12))
    z[3, 5] = 5.2
    fig, ax = plt.subplots()
    im = ax.imshow(z, aspect="auto", cmap="viridis")
    fig.colorbar(im, label="$/gal")
    ax.set_xticks(range(12), MONTHS)
    ax.set_yticks(range(6), years)
    ax.set_title("Gas price by year and month")
    i, j = np.unravel_index(z.argmax(), z.shape)
    return fig, [
        label("Which year has the single highest cell?", years[i], years),
        label("Which month is that highest cell in?", MONTHS[j], MONTHS),
        num("What is the value of the highest cell?", z.max(), span(z)),
        num("What is the value of the lowest cell?", z.min(), span(z)),
    ]


@chart("heatmap")
def hm_correlation():
    names = ["price", "volume", "spread", "vol", "beta"]
    c = np.array([[1, .62, -.71, .18, .44], [.62, 1, -.35, .09, .27], [-.71, -.35, 1, .52, -.12],
                  [.18, .09, .52, 1, .66], [.44, .27, -.12, .66, 1]])
    fig, ax = plt.subplots()
    im = ax.imshow(c, cmap="RdBu_r", vmin=-1, vmax=1)
    fig.colorbar(im)
    ax.set_xticks(range(5), names)
    ax.set_yticks(range(5), names)
    ax.set_title("Feature correlations")
    off = c - np.eye(5) * 2
    return fig, [
        label("Which variable is most negatively correlated with price?", names[c[0].argmin()], names[1:]),
        num("What is the correlation between price and volume?", c[0, 1], 2),
        label("Excluding the diagonal, which variable pairs with 'vol' most strongly?", names[np.argsort(off[3])[-1]], [n for n in names if n != "vol"]),
    ]


@chart("heatmap")
def hm_traffic():
    rng = np.random.default_rng(31)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    hours = np.arange(24)
    base = 20 + 60 * np.exp(-((hours - 8.5) ** 2) / 4) + 70 * np.exp(-((hours - 17.5) ** 2) / 5)
    scale = np.array([1.0, 1.05, 1.0, 1.1, 1.25, 0.5, 0.4])
    z = scale[:, None] * base[None, :] + rng.normal(0, 3, (7, 24))
    fig, ax = plt.subplots()
    im = ax.imshow(z, aspect="auto", cmap="magma")
    fig.colorbar(im, label="Vehicles / min")
    ax.set_yticks(range(7), days)
    ax.set_xticks(range(0, 24, 3))
    ax.set(title="Traffic by weekday and hour", xlabel="Hour")
    i, j = np.unravel_index(z.argmax(), z.shape)
    return fig, [
        label("Which day has the busiest single hour?", days[i], days),
        num("At which hour is that busiest reading?", hours[j], 23),
        label("Which day is quietest overall?", days[z.sum(1).argmin()], days),
    ]


# ---- histograms ---------------------------------------------------------------------------

@chart("histogram")
def hist_normal():
    rng = np.random.default_rng(37)
    v = rng.normal(50, 10, 1000)
    counts, edges = np.histogram(v, bins=20)
    fig, ax = plt.subplots()
    ax.hist(v, bins=edges)
    ax.set(title="Exam scores", xlabel="Score", ylabel="Students")
    k = counts.argmax()
    return fig, [
        num("Where is the tallest bin centred (x value)?", (edges[k] + edges[k + 1]) / 2, edges[-1] - edges[0]),
        num("How many students are in the tallest bin?", counts.max(), counts.max()),
        count("How many bins have more than 60 students?", (counts > 60).sum()),
    ]


@chart("histogram")
def hist_skewed():
    rng = np.random.default_rng(41)
    v = rng.lognormal(3.0, 0.6, 2000)
    v = v[v < 120]
    counts, edges = np.histogram(v, bins=30)
    fig, ax = plt.subplots()
    ax.hist(v, bins=edges)
    ax.set(title="Order values", xlabel="Order value ($)", ylabel="Orders")
    k = counts.argmax()
    return fig, [
        label("Is the distribution skewed left or right?", "right", ["left", "right"]),
        num("Where is the peak (x value of the tallest bin's centre)?", (edges[k] + edges[k + 1]) / 2, edges[-1] - edges[0]),
        num("How many orders are in the tallest bin?", counts.max(), counts.max()),
    ]


@chart("histogram")
def hist_bimodal():
    rng = np.random.default_rng(43)
    v = np.concatenate([rng.normal(30, 5, 600), rng.normal(70, 7, 400)])
    counts, edges = np.histogram(v, bins=25)
    fig, ax = plt.subplots()
    ax.hist(v, bins=edges)
    ax.set(title="Session length", xlabel="Minutes", ylabel="Sessions")
    centres = (edges[:-1] + edges[1:]) / 2
    left = centres < 50
    return fig, [
        count("How many distinct peaks does the distribution have?", 2),
        num("Where is the left peak (x of its tallest bin's centre)?", centres[left][counts[left].argmax()], edges[-1] - edges[0]),
        label("Which peak is taller?", "left" if counts[left].max() > counts[~left].max() else "right", ["left", "right"]),
    ]


@chart("line")
def line_weekly_sales():
    sales = np.array([310, 342, 365, 351, 398, 420, 405, 389, 440, 467, 455, 498, 510, 486, 530, 545])
    fig, ax = plt.subplots()
    ax.plot(range(1, 17), sales, marker="s")
    ax.set(title="Weekly sales", xlabel="Week", ylabel="Units")
    drops = int((np.diff(sales) < 0).sum())
    return fig, [
        count("In how many weeks did sales fall versus the previous week?", drops),
        num("What were sales in week 9?", sales[8], span(sales)),
        count("In which week were sales highest?", sales.argmax() + 1),
    ]
