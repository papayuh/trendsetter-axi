"""Show and save the ten-team before/after at 60 columns and 40x8.

python examples/compact_demo.py --output-dir .scratch
"""
import argparse
from pathlib import Path

from matplotlib.figure import Figure
from trendsetter_axi import render, render_compact

NAMES = ['Retail servicing', 'Direct lending', 'Partner channel', 'Branch operations',
         'Digital acquisition', 'Wholesale lending', 'Application support', 'Field underwriting',
         'Central processing', 'Portfolio services']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('.scratch'))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    ax = Figure(figsize=(7.5, 3.4)).subplots()
    ax.barh(NAMES, range(-9, 1))
    ax.invert_yaxis()
    ax.set(title='Team change', xlabel='pp')
    for cols, rows, label in [(60, 11, '60'), (40, 8, '40x8')]:
        before = render(ax.figure, cols=cols, rows=18 if cols == 60 else rows)
        after = render_compact(ax.figure, cols=cols, max_rows=rows)
        for mode, result in [('before', before), ('after', after)]:
            path = args.output_dir / f'ranking-{mode}-{label}.txt'
            path.write_text(result.text + '\n')
            print(f'\n{path} ({result.dimensions}, {len(result.text.encode())} UTF-8 bytes)\n{result.text}')


if __name__ == '__main__':
    main()
