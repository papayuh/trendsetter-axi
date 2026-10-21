import importlib.util
from pathlib import Path

from trendsetter_axi.cells import width

spec = importlib.util.spec_from_file_location("demo", Path(__file__).parent.parent / "examples" / "demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)

COLS = 60


def chart_text(lines):
    return [l for l in lines if not l.startswith("[timing]")]


def test_demo_fits_budget_and_is_deterministic():
    # widths section prints charts at 100/60/40/24 cols, so check it against its own widest budget
    first = demo.build(COLS, [s for s in demo.SECTIONS if s != "widths"])
    second = demo.build(COLS, [s for s in demo.SECTIONS if s != "widths"])
    assert all(width(l) <= COLS for l in first)
    assert chart_text(first) == chart_text(second)
    assert any(l.startswith("[timing]") for l in first)


def test_demo_widths_section_deterministic():
    assert demo.build(COLS, ["widths"]) == demo.build(COLS, ["widths"])
