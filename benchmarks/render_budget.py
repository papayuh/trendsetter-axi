"""Run from repo root: PYTHONPATH=src python benchmarks/render_budget.py.

Median end-to-end times include figure copying. cProfile separates copy,
layout/draw, rasterization and row serialization (Canvas.render cumulative).
"""
import argparse
import cProfile
import hashlib
import statistics
import time

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
import numpy as np

from trendsetter_axi import render_figure


def figure(n):
    fig = Figure(figsize=(8, 4))
    x = np.linspace(0, 10, n)
    ax = fig.subplots()
    ax.plot(x, np.sin(x))
    ax.set_title("Dense sine")
    return fig


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    for n in (1000, 10000, 100000):
        fig = figure(n)
        render_figure(fig, 80)  # warm caches
        times = []
        for _ in range(3):
            start = time.perf_counter()
            text = render_figure(fig, 80)
            times.append((time.perf_counter() - start) * 1000)
        print(f"{n}: {statistics.median(times):.1f} ms; {len(text)} chars; "
              f"sha256={hashlib.sha256(text.encode()).hexdigest()}")
    if args.profile:
        profiler = cProfile.Profile()
        profiler.runcall(render_figure, fig, 80)
        profiler.print_stats(sort="cumulative")


if __name__ == "__main__":
    main()
