"""Isolated interpreters prove import boundaries and unchanged lazy/eager outputs."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def probe(code):
    return json.loads(subprocess.check_output([sys.executable, '-c', code], text=True))


@pytest.mark.parametrize('route, numpy, matplotlib', [
    ('pass', False, False),
    ("a.render_ranking(['one'], [1])", False, False),
    ("a.render_ranking(['loss', 'gain'], [-2**63, 2**62])", False, False),
    ("a.present(a.Scalar(95, '%'))", False, False),
    ("a.render_svg('<svg width=\"10\" height=\"10\"/>')", True, False),
    ("from matplotlib.figure import Figure; a.render(Figure())", True, True),
])
def test_import_boundaries_in_fresh_process(route, numpy, matplotlib):
    modules = probe('import sys, json; import trendsetter_axi as a; ' + route +
                    '; print(json.dumps(sorted(set(m.split(".")[0] for m in sys.modules))))')
    assert ('numpy' in modules) == numpy
    assert ('matplotlib' in modules) == matplotlib
    if not matplotlib:
        assert 'trendsetter_axi.mpl' not in probe('import sys, json; import trendsetter_axi; print(json.dumps(list(sys.modules)))')


def test_public_outputs_match_eager_imports_in_fresh_processes():
    script = Path(__file__).with_name('route_probe.py')
    env = dict(os.environ, MPLBACKEND='Agg')
    lazy = subprocess.check_output([sys.executable, str(script)], env=env)
    eager = subprocess.check_output([sys.executable, str(script), '--eager'], env=env)
    assert lazy == eager
    assert len(json.loads(lazy)) == 42
