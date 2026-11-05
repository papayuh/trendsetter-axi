#!/usr/bin/env python3
"""Real matplotlib dashboard with deterministic synthetic telemetry.

python examples/dashboard_demo.py                 # static, no input
python examples/dashboard_demo.py --interactive   # hover / scatter brush
python examples/dashboard_demo.py --live          # opt-in live callback + input
"""
import argparse

import numpy as np
from matplotlib.figure import Figure

from trendsetter_axi import dashboard


def make_figures(step=0):
    rng = np.random.default_rng(41)
    time = np.arange(120)
    figures = [Figure(figsize=(7, 3.5)) for _ in range(4)]
    ax = figures[0].subplots()
    for label, offset, phase in [('edge', 0, 0), ('origin', 32, 1)]:
        y = 80 + offset + 15 * np.sin((time + step * 3) / 12 + phase) + rng.normal(0, 2, len(time))
        ax.plot(time, y, label=label)
    ax.set(xlim=(0, 119), ylim=(45, 150), xlabel='minutes', ylabel='requests / s', title='Traffic / last two hours')

    ax = figures[1].subplots()
    ax.bar(['iad', 'ams', 'sin', 'syd', 'fra', 'gru'],
           [82 + 7 * np.sin(step / 2), 67, 53 + 5 * np.cos(step / 2), 41, 72, 34],
           label='workers busy')
    ax.set(ylim=(0, 100), ylabel='utilization %', xlabel='region', title='Fleet / regional utilization')

    ax = figures[2].subplots()
    for label, x, y in [('cached', 28, 28), ('uncached', 69, 56)]:
        load = rng.normal(x, 9, 360)
        latency = y + .55 * (load - x) + rng.normal(0, 7, len(load)) + np.sin(step / 2) * 3
        ax.scatter(load, latency, label=label)
    ax.set(xlim=(0, 100), ylim=(0, 90), xlabel='load %', ylabel='latency ms', title='Requests / load against latency')

    ax = figures[3].subplots()
    z = 10 + rng.uniform(0, 6, (6, 18))
    z += 16 * np.exp(-((np.arange(18) - (8 + step % 7)) / 3) ** 2)[None, :]
    z[2] += 6
    image = ax.imshow(z, aspect='auto', cmap='viridis', vmin=10, vmax=40)
    figures[3].colorbar(image, ax=ax, label='ms')
    ax.set(yticks=range(6), yticklabels=['iad', 'ams', 'sin', 'syd', 'fra', 'gru'],
           xticks=[0, 6, 12, 17], xticklabels=['00', '06', '12', '18'],
           xlabel='hour UTC', title='Latency / region by hour')
    return figures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interactive', action='store_true')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--cols', type=int)
    parser.add_argument('--rows', type=int)
    args = parser.parse_args()
    step = 0

    def refresh():
        nonlocal step
        step += 1
        return make_figures(step)

    text = dashboard(make_figures(), title='NIGHT SHIFT / synthetic telemetry',
                     cols=args.cols, rows=args.rows,
                     interactive=args.interactive or args.live,
                     refresh=refresh if args.live else None, interval=1.0)
    if text is not None:
        print(text)


if __name__ == '__main__':
    main()
