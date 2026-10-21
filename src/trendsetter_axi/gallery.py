"""Gallery of 50 example charts. CHARTS = [dict(id, lib, kind, desc, make)].

Importing this module needs only matplotlib, numpy and pandas; seaborn, plotly, altair and plotnine
are imported inside the charts that use them (install the `gallery` extra for all of them)."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

G = pd.read_csv(Path(__file__).parent / "data" / "gas.csv", parse_dates=["date"])
G["year"] = G.date.dt.year
G["month_n"] = G.date.dt.month
G["decade"] = (G.year // 10 * 10).astype(str) + "s"
YM = G[G.year.between(2016, 2025)].pivot_table(index="year", columns="month_n", values="price_today")
YR = G.groupby("year").price.mean().loc[2016:2025]          # yearly mean Houston price
YR_TODAY = G.groupby("year").price_today.mean()
RECENT = G[G.date >= "2024-10-01"]                           # ~2 years weekly
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CAT4 = ["North", "South", "East", "West"]
GRP3 = ["2022", "2023", "2024"]
GB = np.array([[12, 18, 9, 15], [14, 11, 16, 8], [10, 13, 12, 17]])   # 3 groups x 4 categories
D = lambda: G.dropna(subset=["price_today"])


def mpl(): return plt.subplots()


# ---------------- matplotlib ----------------
def c01():
    fig, ax = mpl(); ax.plot(G.date, G.price_today)
    ax.set(title="Houston Gas Price (inflation-adjusted)", xlabel="Date", ylabel="Price (today's $/gal)"); return fig

def c02():
    fig, ax = mpl(); ax.plot(G.date, G.price, label="Houston"); ax.plot(G.date, G.us, label="US average")
    ax.set(title="Houston vs US Gas Price", xlabel="Date", ylabel="$/gal"); ax.legend(); return fig

def c03():
    fig, ax = mpl(); ax.scatter(G.crude_today, G.price_today, s=8, alpha=.5)
    ax.set(title="Gas vs Crude Oil", xlabel="Crude (today's $/bbl)", ylabel="Gas price (today's $/gal)"); return fig

def c04():
    fig, ax = mpl(); ax.bar(YR.index.astype(str), YR.values)
    ax.set(title="Yearly Mean Houston Gas Price", xlabel="Year", ylabel="Mean price ($/gal)"); return fig

def c05():
    fig, ax = mpl(); w = .25; x = np.arange(4)
    for i, g in enumerate(GRP3): ax.bar(x + (i - 1) * w, GB[i], w, label=g)
    ax.set_xticks(x, CAT4); ax.set(title="Sales by Region and Year", xlabel="Region", ylabel="Sales (k units)"); ax.legend(); return fig

def c06():
    fig, ax = mpl(); b = np.zeros(4)
    for i, g in enumerate(["Product A", "Product B", "Product C"]): ax.bar(CAT4, GB[i], bottom=b, label=g); b += GB[i]
    ax.set(title="Stacked Sales by Region", ylabel="Sales (k units)"); ax.legend(); return fig

def c07():
    fig, ax = mpl(); ax.hist(D().price_today, bins=25)
    ax.set(title="Distribution of Gas Price", xlabel="Price (today's $/gal)", ylabel="Weeks"); return fig

def c08():
    fig, ax = mpl(); d = D(); ks = ["2000s", "2010s", "2020s"]
    ax.boxplot([d[d.decade == k].price_today for k in ks], tick_labels=ks)
    ax.set(title="Gas Price by Decade", xlabel="Decade", ylabel="Price (today's $/gal)"); return fig

def c09():
    r = np.random.default_rng(9); fig, ax = mpl()
    ax.violinplot([r.normal(0, 1, 200), r.normal(2, .5, 200), r.normal(-1, 1.5, 200)], showmedians=True)
    ax.set_xticks([1, 2, 3], ["A", "B", "C"]); ax.set(title="Violin of Three Distributions", ylabel="Value"); return fig

def c10():
    fig, ax = mpl(); im = ax.imshow(YM.values, aspect="auto", cmap="viridis")
    ax.set_xticks(range(12), MON, fontsize=7); ax.set_yticks(range(10), YM.index)
    ax.set(title="Mean Gas Price by Year and Month"); fig.colorbar(im, label="$/gal (today's)"); return fig

def c11():
    g = G.groupby("year").price_today.agg(["min", "mean", "max"]); fig, ax = mpl()
    ax.fill_between(g.index, g["min"], g["max"], alpha=.3, label="min-max"); ax.plot(g.index, g["mean"], label="mean")
    ax.set(title="Yearly Gas Price Band", xlabel="Year", ylabel="Price (today's $/gal)"); ax.legend(); return fig

def c12():
    fig, ax = mpl(); ax.pie([35, 25, 20, 12, 8], labels=["Rent", "Food", "Transport", "Fun", "Other"], autopct="%1.1f%%")
    ax.set_title("Monthly Budget"); return fig

def c13():
    fig, ax = mpl(); ax.step(YR.index, YR.values, where="mid")
    ax.set(title="Yearly Mean Gas Price (step)", xlabel="Year", ylabel="$/gal"); return fig

def c14():
    fig, ax = mpl(); m = [2.0, 3.1, 2.5, 4.2, 3.6]; s = [.3, .5, .4, .8, .6]
    ax.errorbar(range(1, 6), m, yerr=s, fmt="o-", capsize=4)
    ax.set(title="Means with Std Error", xlabel="Trial", ylabel="Measurement"); return fig

def c15():
    x = np.arange(0, 21); fig, ax = mpl(); ax.semilogy(x, 2.0 * 1.8 ** x)
    ax.set(title="Exponential Growth (log scale)", xlabel="Step", ylabel="Value (log)"); return fig

def c16():
    fig, ax = mpl(); ax.plot(RECENT.date, RECENT.price_today); fig.autofmt_xdate()
    ax.set(title="Gas Price, Last 2 Years", ylabel="Price (today's $/gal)"); return fig

def c17():
    fig, axs = plt.subplots(2, 2); x = np.linspace(0, 2 * np.pi, 50)
    for a, f, t in zip(axs.flat, [np.sin, np.cos, np.tanh, np.square], ["sin", "cos", "tanh", "square"]): a.plot(x, f(x)); a.set_title(t)
    fig.tight_layout(); return fig

def c18():
    fig, ax = mpl(); d = D(); ax.plot(d.date, d.price_today); i = d.price_today.idxmax()
    ax.annotate("Peak 2008: $5.99", (d.date[i], d.price_today[i]), xytext=(pd.Timestamp("2015-06-01"), 5.7),
                arrowprops=dict(arrowstyle="->"), bbox=dict(boxstyle="round", fc="yellow"))
    ax.set(title="Gas Price with Peak Annotated", ylabel="Price (today's $/gal)"); return fig

def c19():
    fig, ax = mpl()
    for c, l in [("price", "Houston"), ("us", "US"), ("price_today", "Houston (adj.)"), ("crude", "Crude/20")]:
        ax.plot(G.date, G[c] / (20 if c == "crude" else 1), label=l)
    ax.set(title="Four Series", xlabel="Date", ylabel="$"); ax.legend(); return fig

def c20():
    fig, ax = mpl(); n = ["Department of Transportation and Infrastructure", "National Oceanic and Atmospheric Administration",
                          "Bureau of Land Management", "Federal Aviation Administration", "Energy Dept"]
    ax.barh(n, [8.5, 6.2, 4.8, 3.1, 1.4]); ax.set(title="Agency Budgets", xlabel="Budget ($B)"); fig.tight_layout(); return fig

# ---------------- seaborn ----------------
def _sdf():
    r = np.random.default_rng(21); x = np.tile(np.arange(20), 3)
    return pd.DataFrame(dict(x=x, y=np.concatenate([x[:20] * s + r.normal(0, 1, 20) for s in (1, .5, -.3)]), grp=np.repeat(list("ABC"), 20)))

def c21():
    import seaborn as sns
    fig, ax = mpl(); sns.lineplot(_sdf(), x="x", y="y", hue="grp", ax=ax); ax.set_title("Lines by Group"); return fig

def c22():
    import seaborn as sns
    r = np.random.default_rng(22); c = [(0, 0), (3, 3), (0, 4)]
    d = pd.concat([pd.DataFrame(dict(x=r.normal(a, .7, 40), y=r.normal(b, .7, 40), g=n)) for (a, b), n in zip(c, "XYZ")])
    fig, ax = mpl(); sns.scatterplot(d, x="x", y="y", hue="g", ax=ax); ax.set_title("Three Clusters"); return fig

def c23():
    import seaborn as sns
    fig, ax = mpl(); sns.heatmap(np.array([[1, 2, 1, 3], [2, 1, 3, 1], [3, 1, 2, 2]]), annot=True, cbar=True,
                                 xticklabels=CAT4, yticklabels=["Q1", "Q2", "Q3"], ax=ax); ax.set_title("Annotated Heatmap"); return fig

def c24():
    import seaborn as sns
    r = np.random.default_rng(24)
    d = pd.DataFrame(dict(day=np.repeat(["Thu", "Fri", "Sat"], 60), sex=np.tile(np.repeat(["F", "M"], 30), 3),
                          bill=np.concatenate([r.normal(m, 3, 60) for m in (17, 17, 21)]) + np.tile(np.repeat([0, 3], 30), 3)))
    fig, ax = mpl(); sns.boxplot(d, x="day", y="bill", hue="sex", ax=ax); ax.set_title("Bill by Day and Sex"); return fig

def c25():
    import seaborn as sns
    r = np.random.default_rng(25); fig, ax = mpl(); sns.histplot(r.normal(50, 10, 500), kde=True, ax=ax)
    ax.set(title="Histogram with KDE", xlabel="Value"); return fig

# ---------------- pandas ----------------
def c26():
    fig, ax = mpl(); G.set_index("date")[["price", "us"]].resample("YS").mean().plot(ax=ax)
    ax.set(title="Yearly Mean Price: Houston vs US", ylabel="$/gal"); return fig

def c27():
    fig, ax = mpl(); df = pd.DataFrame(GB.T, index=CAT4, columns=["A", "B", "C"]); df.plot.bar(stacked=True, ax=ax)
    ax.set(title="Stacked Bars (pandas)", ylabel="Count"); return fig

def c28():
    fig, ax = mpl(); df = pd.DataFrame(dict(Houston=YR.values, US=G.groupby("year").us.mean().loc[2016:2025].values), index=YR.index)
    df.plot.area(ax=ax, stacked=False, alpha=.5); ax.set(title="Mean Price Area (pandas)", ylabel="$/gal"); return fig

# ---------------- plotnine ----------------
def c29():
    import plotnine as p9; from plotnine.data import mpg
    return p9.ggplot(mpg, p9.aes("displ", "hwy")) + p9.geom_point() + p9.facet_wrap("drv") + p9.labs(title="Highway MPG vs Displacement")

def c30():
    import plotnine as p9
    d = G.groupby(["year", "decade"]).price_today.mean().reset_index(); d = d[d.year < 2026]
    return p9.ggplot(d, p9.aes("year", "price_today", color="decade")) + p9.geom_line() + p9.labs(title="Yearly Gas Price by Decade", y="Price (today's $/gal)")

# ---------------- plotly ----------------
def c31():
    import plotly.express as px
    return px.line(G, x="date", y=["price", "us"], title="Houston vs US Gas Price")

def c32():
    import plotly.graph_objects as go
    f = go.Figure([go.Bar(name=g, x=CAT4, y=GB[i]) for i, g in enumerate(GRP3)]); f.update_layout(barmode="group", title="Grouped Bars"); return f

def c33():
    import plotly.express as px
    r = np.random.default_rng(33); d = pd.DataFrame(dict(x=r.normal(size=90), g=np.repeat(list("ABC"), 30))); d["y"] = d.x * 2 + r.normal(size=90) + d.g.map(dict(A=0, B=3, C=-3))
    return px.scatter(d, x="x", y="y", color="g", title="Scatter by Group")

def c34():
    import plotly.graph_objects as go
    return go.Figure(go.Heatmap(z=YM.values, x=MON, y=YM.index.astype(str))).update_layout(title="Mean Price by Year and Month")

def c35():
    import plotly.graph_objects as go
    return go.Figure(go.Pie(labels=["Rent", "Food", "Transport", "Fun", "Other"], values=[35, 25, 20, 12, 8])).update_layout(title="Monthly Budget")

def c36():
    import plotly.express as px
    d = G[G.year.isin([2008, 2014, 2022])].groupby(["year", "month_n"]).price_today.mean().reset_index()
    return px.line(d, x="month_n", y="price_today", color="year", facet_col="year", title="Gas Price by Month, Faceted")

def c37():
    import plotly.express as px
    return px.box(D(), x="decade", y="price_today", title="Gas Price by Decade")

# ---------------- altair ----------------
def c38():
    import altair as alt
    return alt.Chart(G).mark_line().encode(x="date:T", y=alt.Y("price_today:Q", title="Price (today's $/gal)")).properties(title="Houston Gas Price")

def c39():
    import altair as alt
    d = pd.DataFrame([dict(region=CAT4[j], product=p, sales=int(GB[i, j])) for i, p in enumerate("ABC") for j in range(4)])
    return alt.Chart(d).mark_bar().encode(x="region:N", y="sales:Q", color="product:N").properties(title="Stacked Sales")

def c40():
    import altair as alt
    r = np.random.default_rng(40); d = pd.DataFrame(dict(x=r.normal(size=90), g=np.repeat(list("ABC"), 30))); d["y"] = d.x + r.normal(size=90) + d.g.map(dict(A=0, B=2, C=-2))
    return alt.Chart(d).mark_point().encode(x="x:Q", y="y:Q", color="g:N").properties(title="Scatter by Group")

def c41():
    import altair as alt
    d = G.groupby("year").price_today.mean().reset_index()
    return alt.Chart(d).mark_area().encode(x="year:O", y="price_today:Q").properties(title="Yearly Mean Gas Price")

def c42():
    import altair as alt
    d = YM.stack().reset_index(name="p")
    return alt.Chart(d).mark_rect().encode(x="month_n:O", y="year:O", color="p:Q").properties(title="Price Heatmap")

# ---------------- edge cases ----------------
def c43():
    fig, ax = mpl(); ax.set_title("Empty Chart"); return fig

def c44():
    fig, ax = mpl(); ax.plot([1, 2, 3, 4], [3, 1, 4, 2])
    ax.set(title="A Very Long Title That Goes On and On to Test How the Renderer Handles Overlong Titles Across the Full Width of a Figure",
           xlabel="An extremely long x axis label describing the horizontal dimension in excessive detail",
           ylabel="An extremely long y axis label describing the vertical dimension"); return fig

def c45():
    fig, ax = mpl(); ax.bar(list("ABCDEF"), [4, -3, 2, -5, 6, -1]); ax.axhline(0, color="k")
    ax.set(title="Profit and Loss", ylabel="Change"); return fig

def c46():
    r = np.random.default_rng(46); fig, ax = mpl()
    for i in range(10): ax.plot(np.cumsum(r.normal(size=50)), label=f"s{i}")
    ax.set(title="Ten Random Walks", xlabel="Step", ylabel="Value"); return fig

def c47():
    fig, ax = mpl(); ax.plot([5], [7], "o"); ax.set_title("Single Point"); return fig

def c48():
    y = np.sin(np.linspace(0, 6, 40)); y[[10, 11, 12, 25, 26]] = np.nan; fig, ax = mpl(); ax.plot(y)
    ax.set(title="Line with Gaps", xlabel="Index", ylabel="sin"); return fig

def c49():
    fig, ax = mpl(); ax.plot(np.arange(10), np.array([1, 3, 2, 5, 8, 7, 9, 12, 11, 15]) * 1e9)
    ax.set(title="Huge Values", xlabel="Year index", ylabel="Revenue"); return fig

def c50():
    fig, ax = mpl(); ax.plot(G.date, G.price_today, color="C0"); ax.set_ylabel("Gas price (today's $/gal)", color="C0")
    a2 = ax.twinx(); a2.plot(G.date, G.crude_today, color="C1"); a2.set_ylabel("Crude (today's $/bbl)", color="C1")
    ax.set_title("Gas Price vs Crude Oil"); return fig



_META = [
("01_mpl_line","matplotlib","line",c01,"Single line chart titled 'Houston Gas Price (inflation-adjusted)'; x axis 'Date' 2000-2026, y axis \"Price (today's $/gal)\" ~1.8 to ~6.0. Starts ~2.9 in 2000, low ~1.8 in late 2001, climbs to peak ~6.0 in mid-2008, drops to ~3.4 in 2009, ~5 in 2011-2013, falls to ~2.0 in 2020, spikes to ~5.2 in 2022, ends ~3.8. No legend."),
("02_mpl_line2","matplotlib","line",c02,"Two-line chart titled 'Houston vs US Gas Price', x 'Date' 2000-2026, y '$/gal' ~1 to 5. Legend with 'Houston' and 'US average'. US line sits slightly above Houston (about 0.2 higher on average); both start ~1.5, peak ~4.1-4.6 in mid-2008 and ~4.6-5.0 in 2022, trough ~1.0 in 2001/2020, end ~3.8 (Houston) and ~4.4 (US)."),
("03_mpl_scatter","matplotlib","scatter",c03,"Scatter plot titled 'Gas vs Crude Oil', x \"Crude (today's $/bbl)\" ~4 to ~217, y \"Gas price (today's $/gal)\" ~1.8 to 6.0, about 1370 small semi-transparent points, single color, no legend. Strong positive correlation (r~0.95), points form a rising band from lower-left (~50, ~2.5) to upper-right (~200, ~5.5)."),
("04_mpl_bar","matplotlib","bar",c04,"Vertical bar chart titled 'Yearly Mean Houston Gas Price', x 'Year' with 10 bars 2016-2025, y 'Mean price ($/gal)' 0 to ~3.5. Heights: 2016 1.87, 2017 2.12, 2018 2.42, 2019 2.29, 2020 1.82, 2021 2.62, 2022 3.45 (tallest), 2023 3.01, 2024 2.83, 2025 2.61. Single series, no legend."),
("05_mpl_groupbar","matplotlib","bar",c05,"Grouped bar chart titled 'Sales by Region and Year', x 'Region' with 4 categories North, South, East, West; y 'Sales (k units)' 0 to ~18. Three bars per category with legend 2022, 2023, 2024. 2022: 12,18,9,15; 2023: 14,11,16,8; 2024: 10,13,12,17."),
("06_mpl_stackbar","matplotlib","bar",c06,"Stacked bar chart titled 'Stacked Sales by Region', y 'Sales (k units)' 0 to ~40, x categories North, South, East, West (no x label). Three stacks with legend Product A, B, C. Totals: North 36, South 42, East 37, West 40. A: 12,18,9,15; B: 14,11,16,8; C: 10,13,12,17."),
("07_mpl_hist","matplotlib","histogram",c07,"Histogram titled 'Distribution of Gas Price', x \"Price (today's $/gal)\" ~1.8 to 6.0, y 'Weeks' 0 to ~170, 25 bins. Right-skewed unimodal: main mode ~3.0-3.2 (tallest bar ~165), secondary bump around 4.5-5.0 (~60-70), thin tail to ~6. Median ~3.3."),
("08_mpl_box","matplotlib","box",c08,"Boxplot titled 'Gas Price by Decade', x 'Decade' with 3 boxes 2000s, 2010s, 2020s; y \"Price (today's $/gal)\" ~1.8 to 6. Medians approx 3.1, 3.6, 3.2. 2010s has the highest and widest box (IQR ~2.9-4.7, whiskers ~2.0-5.7), 2020s narrowest (IQR ~2.7-3.4) with outliers up to ~5.2; 2000s has an outlier/whisker up to ~6.0."),
("09_mpl_violin","matplotlib","violin",c09,"Violin plot titled 'Violin of Three Distributions', x ticks A, B, C, y 'Value' ~-5.5 to 3.5. Three violins with median lines: A centered ~0 (spread about -2.8 to 2.5), B centered ~2 and narrow (0.5 to 3.3), C centered ~-1 and widest (-5.4 to 3.1)."),
("10_mpl_imshow","matplotlib","heatmap",c10,"Heatmap (imshow, viridis) titled 'Mean Gas Price by Year and Month': 10 rows (years 2016-2025, 2016 at top) by 12 columns (Jan-Dec), with a colorbar labeled \"$/gal (today's)\" spanning ~2.0 to ~5.2. Brightest cell Jun 2022 (~5.2); darkest around Apr-May 2020 (~2.0) and early 2016 (~2.1). 2022 row is bright from Mar-Jul and fades toward Dec (~2.9)."),
("11_mpl_fill_between","matplotlib","area",c11,"Line with shaded band titled 'Yearly Gas Price Band', x 'Year' 2000-2026, y \"Price (today's $/gal)\" ~1.8 to 6. Legend 'min-max' (shaded band between each year's min and max) and 'mean' (line). Mean rises from 2.8 (2000) to ~4.8 (2008), dips to 3.4 (2009), ~5.0 in 2011-2012, falls to 2.3 (2020), 3.95 (2022), ~3.35 (2026). Band is widest in 2008 (2.3 to 6.0) and 2022 (2.8 to 5.2)."),
("12_mpl_pie","matplotlib","pie",c12,"Pie chart titled 'Monthly Budget' with 5 slices labeled Rent (35.0%), Food (25.0%), Transport (20.0%), Fun (12.0%), Other (8.0%), percentages shown via autopct with one decimal. No legend; labels are placed around the pie."),
("13_mpl_step","matplotlib","step",c13,"Step plot titled 'Yearly Mean Gas Price (step)', x 'Year' 2016-2025, y '$/gal' ~1.8 to 3.5. Steps (centered) at 1.87, 2.12, 2.42, 2.29, 1.82, 2.62, 3.45 (2022 peak), 3.01, 2.83, 2.61. Single series, no legend."),
("14_mpl_errorbar","matplotlib","errorbar",c14,"Error bar chart titled 'Means with Std Error', x 'Trial' 1-5, y 'Measurement' ~1 to 5. Points connected by line with caps: means 2.0, 3.1, 2.5, 4.2, 3.6 with symmetric errors 0.3, 0.5, 0.4, 0.8, 0.6. No legend."),
("15_mpl_semilogy","matplotlib","line",c15,"Line chart with logarithmic y axis titled 'Exponential Growth (log scale)', x 'Step' 0-20, y 'Value (log)' from 2 to ~260,000 (about 10^0.3 to 10^5.4). Appears as a perfectly straight rising line (value = 2*1.8^x, 2 at x=0, ~2.6e5 at x=20)."),
("16_mpl_dates","matplotlib","line",c16,"Line chart titled 'Gas Price, Last 2 Years' with weekly data from Oct 2024 to Oct 2026 (~105 points), y \"Price (today's $/gal)\" ~2.3 to ~3.9, no x label. X tick date labels are rotated (~30 degrees, right aligned). Starts ~2.84, ends ~3.84 (near the maximum); lowest ~2.3 in 2025."),
("17_mpl_subplots","matplotlib","line",c17,"2x2 grid of line subplots, each with a small title: top-left 'sin' (one wave, -1 to 1 over 0 to 6.28), top-right 'cos', bottom-left 'tanh' (rises from 0 to 1 and saturates), bottom-right 'square' (parabola from 0 to ~39.5). X range 0 to 2*pi in all."),
("18_mpl_annotate","matplotlib","line",c18,"Line chart titled 'Gas Price with Peak Annotated', y \"Price (today's $/gal)\" ~1.8 to 6, x dates 2000-2026. A yellow rounded text box reading 'Peak 2008: $5.99' sits near 2015 at y~5.7 with an arrow pointing to the 2008 peak (~6.0). Line otherwise like the gas price history: peaks 2008, ~5 in 2011-13, trough ~2.0 in 2020, ~5.2 in 2022."),
("19_mpl_4line","matplotlib","line",c19,"Four-line chart titled 'Four Series', x 'Date' 2000-2026, y '$' ~1 to ~7.2, legend with Houston, US, 'Houston (adj.)', 'Crude/20'. Houston (~1 to 4.6) and US (~1 to 5.0) are lowest and similar; 'Houston (adj.)' is higher (~1.8 to 6.0); 'Crude/20' (crude oil $/bbl divided by 20) ranges ~0.2 to 7.1, peaking in mid-2008 and ~2011-2013, plunging in 2015 and 2020."),
("20_mpl_barh","matplotlib","bar",c20,"Horizontal bar chart titled 'Agency Budgets', x 'Budget ($B)' 0 to ~9, 5 bars with long category names (y tick labels): 'Department of Transportation and Infrastructure' 8.5 (drawn at the bottom; first category is at the bottom), 'National Oceanic and Atmospheric Administration' 6.2, 'Bureau of Land Management' 4.8, 'Federal Aviation Administration' 3.1, 'Energy Dept' 1.4. Single series, no legend."),
("21_sns_line","seaborn","line",c21,"Seaborn lineplot titled 'Lines by Group', x 'x' 0-19, y 'y' ~-7 to ~21, with hue legend (title 'grp') for A, B, C with shaded error bands. A rises roughly linearly from ~0 to ~19-20, B rises half as fast to ~9, C falls slowly from ~0 to ~-6. Noise sd 1."),
("22_sns_scatter","seaborn","scatter",c22,"Seaborn scatterplot titled 'Three Clusters', x 'x' ~-2 to 5, y 'y' ~-2 to 6, hue legend titled 'g' with X, Y, Z (40 points each). Cluster X centered near (0,0), Y near (3,3), Z near (0,4); each with sd ~0.7."),
("23_sns_heatmap","seaborn","heatmap",c23,"Seaborn annotated heatmap titled 'Annotated Heatmap', 3 rows (Q1, Q2, Q3) by 4 columns (North, South, East, West), with colorbar (values 1 to 3). Cell values: Q1 1,2,1,3; Q2 2,1,3,1; Q3 3,1,2,2, printed in each cell."),
("24_sns_box","seaborn","box",c24,"Seaborn boxplot titled 'Bill by Day and Sex', x 'day' with Thu, Fri, Sat, y 'bill' roughly 8 to 32, hue legend 'sex' F and M. In each day M boxes are about 3 units higher than F. Medians approx F: 17,17,21; M: 20,20,24."),
("25_sns_hist_kde","seaborn","histogram",c25,"Seaborn histogram with KDE curve titled 'Histogram with KDE', x 'Value' ~20 to ~85, y 'Count' 0 to ~45. 500 samples of a normal distribution (mean 50, sd 10): bell-shaped, peak near 50, smooth overlaid KDE line. No legend."),
("26_pd_line","pandas","line",c26,"Pandas multi-column line plot titled 'Yearly Mean Price: Houston vs US', x year index 2000-2026 (axis label 'date'), y '$/gal' ~1.3 to 3.9, legend 'price' and 'us'. Both rise from ~1.4/1.5 (2000) to ~3.1/3.3 (2008), dip 2009 (~2.2), ~3.4/3.6 in 2012, fall to ~1.8/2.2 in 2020, rise to 3.45/3.95 in 2022, 2026 ~3.3/3.8. US above Houston."),
("27_pd_stackbar","pandas","bar",c27,"Pandas stacked vertical bar chart titled 'Stacked Bars (pandas)', y 'Count' 0 to ~42, x categories North, South, East, West (labels horizontal), legend A, B, C. Stack totals 36, 42, 37, 40. Per category (A,B,C): North 12,14,10; South 18,11,13; East 9,16,12; West 15,8,17."),
("28_pd_area","pandas","area",c28,"Pandas unstacked semi-transparent area chart titled 'Mean Price Area (pandas)', x index years 2016-2025, y '$/gal' 0 to ~4, legend Houston and US. Houston: 1.87, 2.12, 2.42, 2.29, 1.82, 2.62, 3.45, 3.01, 2.83, 2.61; US slightly higher: 2.14, 2.41, 2.72, 2.60, 2.17, 3.01, 3.95, 3.52, 3.30, 3.10. Both peak in 2022 and dip in 2020."),
("29_pn_facet","plotnine","scatter",c29,"plotnine scatter of hwy (y, ~12 to 44 mpg) against displ (x, 1.6 to 7.0 liters) from the mpg dataset, 234 points, in three facet panels labeled 4, f, r (drive type) with title 'Highway MPG vs Displacement'. Negative trend: small engines get 25-44 mpg, large ones 12-20. 'f' panel spans displ 1.6-5.3, high hwy; '4' mid/low; 'r' few points with displ 3.8-7.0."),
("30_pn_line","plotnine","line",c30,"plotnine line chart titled 'Yearly Gas Price by Decade', x year 2000-2025, y \"Price (today's $/gal)\" ~2.3 to 5.0, color legend 'decade' with 2000s, 2010s, 2020s: three line segments. 2000s rises 2.8 (2000) to 4.8 (2008) with a dip to 2.4 (2002) and 3.4 (2009); 2010s ~4-5 around 2011-2013 then falls to 2.6 (2016); 2020s 2.3 (2020), 3.95 (2022), 2.7 (2025)."),
("31_plotly_line","plotly","line",c31,"Plotly Express line chart titled 'Houston vs US Gas Price', x 'date' 2000-2026, y 'value' ~1 to 5, legend 'variable' with price and us. US is slightly above Houston; both peak mid-2008 (~4.1/4.6), 2022 (~4.6/5.0), trough ~1.0 in 2001/2020."),
("32_plotly_groupbar","plotly","bar",c32,"Plotly grouped bar chart titled 'Grouped Bars', x categories North, South, East, West, legend 2022, 2023, 2024. Values: 2022: 12,18,9,15; 2023: 14,11,16,8; 2024: 10,13,12,17. Y axis 0 to ~19."),
("33_plotly_scatter","plotly","scatter",c33,"Plotly scatter titled 'Scatter by Group', x 'x' ~-2 to 2, y 'y' ~-8 to 8, legend 'g' with A, B, C (30 points each). Positive slope ~2 within groups; B offset up (+3), C offset down (-3), A in the middle; groups overlap partially."),
("34_plotly_heatmap","plotly","heatmap",c34,"Plotly heatmap titled 'Mean Price by Year and Month', x Jan-Dec, y years 2016-2025, colorbar ~2.0 to ~5.2. Hot (high) cells in 2022 Mar-Jul (peak Jun ~5.2); coolest in Apr-Jun 2020 (~2.0-2.2) and Jan-Feb 2016 (~2.1-2.3)."),
("35_plotly_pie","plotly","pie",c35,"Plotly pie chart titled 'Monthly Budget' with 5 slices and legend: Rent 35 (35%), Food 25 (25%), Transport 20 (20%), Fun 12 (12%), Other 8 (8%). Percent labels on slices."),
("36_plotly_facet","plotly","line",c36,"Plotly Express line chart titled 'Gas Price by Month, Faceted', 3 side-by-side panels (facet_col year = 2008, 2014, 2022) with color legend 'year'. X 'month_n' 1-12, y 'price_today' ~2.3 to 6. 2008 climbs from ~3.5 to ~5.6 in Jun-Jul then falls to ~2.5 in Dec; 2014 declines from ~4.8 to ~3.1; 2022 peaks ~5.2 in Jun and falls to ~2.9."),
("37_plotly_box","plotly","box",c37,"Plotly box plot titled 'Gas Price by Decade', x 'decade' (2000s, 2010s, 2020s), y 'price_today' ~1.8 to 6. Medians about 3.1, 3.6, 3.2; 2010s widest box (~2.9-4.7), 2020s tightest (~2.7-3.4) with upper outliers to ~5.2."),
("38_alt_line","altair","line",c38,"Altair line chart titled 'Houston Gas Price', x 'date' temporal 2000-2026, y \"Price (today's $/gal)\" ~0 or 1.8 to 6. Single line: peak ~6.0 mid-2008, ~5 around 2011-2013, trough ~2.0 in 2020, ~5.2 in 2022, ends ~3.8."),
("39_alt_stackbar","altair","bar",c39,"Altair stacked bar chart titled 'Stacked Sales', x 'region' (East, North, South, West alphabetical), y 'sales' 0 to ~42, color legend 'product' A, B, C. Totals: North 36, South 42, East 37, West 40. Per product (North,South,East,West): A 12,18,9,15; B 14,11,16,8; C 10,13,12,17."),
("40_alt_scatter","altair","scatter",c40,"Altair point chart titled 'Scatter by Group', x 'x' ~-2.5 to 2, y 'y' ~-5 to 4, color legend 'g' A, B, C (30 points each). Positive slope ~1; B offset up ~+2, C offset down ~-2."),
("41_alt_area","altair","area",c41,"Altair area chart titled 'Yearly Mean Gas Price', x 'year' ordinal 2000-2026, y 'price_today' 0 to ~5. Values: 2.80 (2000), 2.36 (2002), 4.77 (2008), 3.37 (2009), ~4.96-4.98 (2011-2012, max), 3.00 (2015), 2.34 (2020), 3.95 (2022), 2.71 (2025), 3.35 (2026)."),
("42_alt_rect","altair","heatmap",c42,"Altair rect heatmap titled 'Price Heatmap', x 'month_n' ordinal 1-12, y 'year' ordinal 2016-2025, color legend 'p' ~2.0 to ~5.2 (continuous). Brightest/highest cells: 2022 months 3-7 (peak month 6 ~5.2); lowest: 2020 months 4-5 (~2.0) and 2016 months 1-2 (~2.1-2.3)."),
("43_mpl_empty","matplotlib","empty",c43,"Empty axes with only the title 'Empty Chart'. Default axes 0 to 1 on both axes with ticks 0.0-1.0, no data, no labels, no legend."),
("44_mpl_longtitle","matplotlib","line",c44,"Line chart of 4 points (1,3), (2,1), (3,4), (4,2) with an extremely long title ('A Very Long Title That Goes On and On to Test How the Renderer Handles Overlong Titles...') and very long x and y axis labels ('An extremely long x axis label describing the horizontal dimension in excessive detail', 'An extremely long y axis label describing the vertical dimension'). Zig-zag shape. The long text may be clipped."),
("45_mpl_negbar","matplotlib","bar",c45,"Bar chart titled 'Profit and Loss', y 'Change' -5 to 6, categories A-F with values 4, -3, 2, -5, 6, -1; a black horizontal line at y=0. Positive bars go up, negative bars down. No legend."),
("46_mpl_spaghetti","matplotlib","line",c46,"Ten random-walk lines (50 steps each, seed 46) titled 'Ten Random Walks', x 'Step' 0-49, y 'Value' ~-17 to ~11. All start near 0; some drift down (min ~-17), some up (max ~11). Lines are colored with the default cycle (colors repeat after 10). No legend (labels set but legend not drawn)."),
("47_mpl_point","matplotlib","scatter",c47,"Single marker point at (5, 7) (blue circle) on otherwise empty axes, title 'Single Point'. Axis limits are a tiny auto-range around the point, no legend."),
("48_mpl_nan","matplotlib","line",c48,"Sine curve over index 0-39 (x 0 to 6 rad) titled 'Line with Gaps', x 'Index', y 'sin' from about -1 to 1: rises from 0 to a peak of ~1 near index 10, crosses zero near index 21, bottoms at ~-1 near index 31, then rises to ~-0.3 at the end. The line is broken (NaN gaps) at indices 10-12 (around the peak) and 25-26."),
("49_mpl_huge","matplotlib","line",c49,"Line chart titled 'Huge Values', x 'Year index' 0-9, y 'Revenue' with scientific offset text (1e10) at top of the axis; values 1e9 to 1.5e10: 1,3,2,5,8,7,9,12,11,15 (x1e9). Generally rising with a dip at index 2 and 8."),
("50_mpl_twinx","matplotlib","line",c50,"Dual-axis line chart titled 'Gas Price vs Crude Oil', x dates 2000-2026. Left axis (blue label) \"Gas price (today's $/gal)\" ~1.8-6.0; right axis (orange label) \"Crude (today's $/bbl)\" ~4-217. Two lines with similar shape: both peak mid-2008 and fall in 2009, high 2011-2013, crash 2015 and 2020, rise in 2022 (crude ~130, gas ~5.2). No legend."),
]
CHARTS = [dict(id=i, lib=l, kind=k, desc=d, make=f) for i, l, k, f, d in _META]
