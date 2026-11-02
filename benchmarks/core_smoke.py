"""Run with a fresh core-only wheel environment: no dev/gallery/trial packages."""
import importlib.util
from importlib.abc import MetaPathFinder
import sys

assert importlib.util.find_spec('pandas') is None


class BlockPandas(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] == 'pandas':
            raise ImportError('pandas blocked for core-only smoke')


sys.meta_path.insert(0, BlockPandas())
import trendsetter_axi as axi

assert 'numpy' not in sys.modules and 'matplotlib' not in sys.modules
assert '#' in axi.render_ranking(['one'], [1], ascii=True).text
axi.render_svg('<svg width="200" height="100"><path d="M10 80 L180 20" stroke="blue"/></svg>')
assert 'numpy' in sys.modules and 'matplotlib' not in sys.modules
from matplotlib.figure import Figure

ax = Figure().subplots()
ax.plot([1, 2, 3], [1, 3, 2])
result = axi.render(ax.figure, cols=60, strict=True)
assert result.text == axi.render_figure(ax.figure, cols=60)
assert axi.present(axi.Scalar(95, '%')).text == '95 %'
assert 'pandas' not in sys.modules
print('core-only smoke: import, ranking, SVG, strict figure, scalar pass; pandas blocked')
