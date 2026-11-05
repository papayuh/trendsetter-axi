#!/usr/bin/env python3
"""A real matplotlib Figure, displayed through the installed package.

python examples/scatter_brush.py           # opt-in mouse interaction
python examples/scatter_brush.py --static  # same styled drawing, no input
python examples/scatter_brush.py --record chart.json  # CLI-compatible record

Synthetic account data, deterministic seed; no window or browser is opened.
"""
import argparse
import json
import random

from matplotlib.figure import Figure

from trendsetter_axi import from_figure, interact, render_styled


def make_figure():
    rng = random.Random(17)
    fig = Figure(figsize=(12, 7))
    ax = fig.subplots()
    groups = [('Starter', 22, 7, 28, 0.9, 5, 520),
              ('Growth', 58, 9, 62, 1, 6, 480),
              ('Enterprise', 92, 8, 34, -0.9, 6, 300)]
    for name, mx, sx, my, slope, noise, n in groups:
        points = []
        for _ in range(n):
            x = rng.gauss(mx, sx)
            y = my + slope * (x - mx) + rng.gauss(0, noise)
            if 1 < x < 119 and 1 < y < 99:
                points.append((x, y))
        ax.scatter(*zip(*points), label=name)
    ax.set(xlim=(0, 120), ylim=(0, 100), xlabel='monthly spend ($k)', ylabel='usage',
           title='Accounts: monthly spend against usage (synthetic data)')
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--static', action='store_true')
    parser.add_argument('--record')
    args = parser.parse_args()
    fig = make_figure()
    if args.record:
        with open(args.record, 'w', encoding='utf-8') as f:
            json.dump(from_figure(fig), f, allow_nan=False)
    elif args.static:
        print(render_styled(fig))
    else:
        interact(fig)


if __name__ == '__main__':
    main()
