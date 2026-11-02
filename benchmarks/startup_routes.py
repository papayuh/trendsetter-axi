"""Fresh-process and warm route timings; no competitor/runtime dependencies.

python benchmarks/startup_routes.py --source src --samples 7 --output .scratch/after.json
Use a git-archive snapshot as --source for an interleaved before/after comparison.
Times exclude interpreter launch. 'cold' means fresh Python, warm OS/font caches.
"""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

SVG = '<svg width="200" height="100"><path d="M10 80 L80 20 L180 60" fill="none" stroke="blue"/></svg>'
NAMES = ['Retail servicing', 'Direct lending', 'Partner channel', 'Branch operations',
         'Digital acquisition', 'Wholesale lending', 'Application support', 'Field underwriting',
         'Central processing', 'Portfolio services']


def ranking():
    from matplotlib.figure import Figure
    ax = Figure(figsize=(7.5, 3.4)).subplots()
    ax.barh(NAMES, range(-9, 1))
    ax.invert_yaxis()
    ax.set(title='Team change', xlabel='pp')
    return ax.figure


def child(route):
    start = time.perf_counter()
    import trendsetter_axi as axi
    if route == 'import':
        value = ''
    elif route == 'svg':
        value = axi.render_svg(SVG, 60)
    else:
        fig = ranking()
        if route.startswith('warm-'):
            # Initialize fonts and route caches, then time only the repeated operation.
            axi.render(fig, 60)
            encode(fig)
            start = time.perf_counter()
        if route.endswith('png'):
            value = encode(fig)
        elif route.endswith('text'):
            value = axi.render_figure(fig, 60)
        elif 'compact' in route:
            value = axi.render_compact(fig, cols=60, max_rows=11, ascii=route.endswith('-ascii')).text
        else:
            value = axi.render(fig, 60).text
    elapsed = (time.perf_counter() - start) * 1000
    print(json.dumps(dict(ms=elapsed, bytes=len(value.encode() if isinstance(value, str) else value),
                          output=value if isinstance(value, str) else None)))


def encode(fig):
    import io
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    return buf.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='src')
    parser.add_argument('--samples', type=int, default=7)
    parser.add_argument('--baseline-source', help='Interleave an archived baseline with --source')
    parser.add_argument('--output')
    parser.add_argument('--child')
    parser.add_argument('--routes', nargs='+', help='Optional route subset, e.g. import')
    args = parser.parse_args()
    if args.child:
        child(args.child)
        return
    sources = {'after': args.source}
    if args.baseline_source:
        sources = {'before': args.baseline_source, **sources}
    routes = args.routes or ['import', 'svg', 'figure', 'warm-structured', 'warm-text', 'warm-png',
                             'warm-compact', 'warm-compact-ascii']
    results = {name: {} for name in sources}
    for route in routes:
        variants = [name for name, source in sources.items() if 'compact' not in route or
                    (Path(source) / 'trendsetter_axi' / 'compact.py').exists()]
        def sample(name):
            env = dict(os.environ, PYTHONPATH=str(Path(sources[name]).resolve()), MPLBACKEND='Agg')
            return json.loads(subprocess.check_output([sys.executable, __file__, '--child', route], env=env))
        samples = {name: [] for name in variants}
        for name in variants:
            sample(name)  # warm OS/font caches, not the next interpreter
        for i in range(args.samples):
            for name in variants if i % 2 == 0 else variants[::-1]:
                samples[name].append(sample(name))
        for name, observations in samples.items():
            times = [s['ms'] for s in observations]
            assert all(s['bytes'] == observations[0]['bytes'] for s in observations)
            results[name][route] = dict(median_ms=statistics.median(times), range_ms=[min(times), max(times)],
                                        output_bytes=observations[0]['bytes'], output=observations[0]['output'])
        if len(variants) == 2 and route not in ('import',):
            assert results['before'][route]['output'] == results['after'][route]['output']
            assert results['before'][route]['output_bytes'] == results['after'][route]['output_bytes']
    sizes, versions = {}, {}
    for name in ('trendsetter-axi', 'numpy', 'matplotlib', 'wcwidth'):
        dist = importlib.metadata.distribution(name)
        versions[name] = dist.version
        sizes[name] = sum(p.stat().st_size for f in dist.files or []
                          if (p := Path(dist.locate_file(f))).is_file())
    source_bytes = {name: sum(p.stat().st_size for p in (Path(source) / 'trendsetter_axi').rglob('*')
                              if p.is_file() and '__pycache__' not in p.parts)
                    for name, source in sources.items()}
    report = dict(python=sys.version, versions=versions, installed_bytes=sizes,
                  source_bytes=source_bytes, state='fresh Python / warm OS and font caches; alternating interleaved variants; warm-* excludes import and fixture',
                  samples=args.samples, routes=results)
    text = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
