"""ECDF negative control: same knots, different between-knot meaning.

Run against baseline and current package via PYTHONPATH; save stdout as plain text.
"""
import numpy as np
from matplotlib.figure import Figure
from trendsetter_axi import render


def main():
    results = []
    for style in ('steps-post', 'default'):
        ax = Figure(figsize=(7.5, 3.4)).subplots()
        for name, counts in [('A', [50, 45, 5]), ('B', [50, 40, 10])]:
            ax.plot([100, 160, 1000], np.cumsum(counts), drawstyle=style, label=name)
        ax.set(xlim=(0, 1100), ylim=(0, 100), title='Latency ECDF', xlabel='ms', ylabel='%')
        ax.legend(frameon=False)
        results.append(render(ax.figure, cols=60, rows=18))
    step, straight = results
    print('drawing changed', step.text != straight.text, 'summary changed', step.summary() != straight.summary())
    print('From source counts at 300 ms, right-continuous: A=95/100, B=90/100.')
    for style, result in zip(('steps-post (right-continuous)', 'default (straight control)'), results):
        print(f'\n{style}\n{result.text}\n\nSummary:\n{result.summary()}')


if __name__ == '__main__':
    main()
