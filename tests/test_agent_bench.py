import importlib.util
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt

BENCH = Path(__file__).parent.parent / "benchmarks" / "agent"
sys.path.insert(0, str(BENCH))
spec = importlib.util.spec_from_file_location("agent_bench", BENCH / "run.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_committed_answer_key_matches_the_charts():
    # results.jsonl was graded against questions.json; a chart edit without a rerun would leave them disagreeing
    key = json.loads((BENCH / "questions.json").read_text())
    assert list(key) == list(bench.CHARTS)
    for cid, (kind, make) in bench.CHARTS.items():
        fig, questions = make()
        plt.close(fig)
        assert key[cid]["kind"] == kind
        assert list(key[cid]["questions"].values()) == questions


def test_grade():
    num = dict(type="number", answer=10.0, tol=0.5)
    assert bench.grade(num, 10.4) and bench.grade(num, "$9.6") and not bench.grade(num, 10.6) and not bench.grade(num, None)
    assert bench.grade(dict(type="int", answer=3), "3") and not bench.grade(dict(type="int", answer=3), 3.5)
    assert bench.grade(dict(type="label", answer="Store A"), "store a") and not bench.grade(dict(type="label", answer="up"), "down")
    assert bench.parse('sure: {"q1": 2}') == {"q1": 2} and bench.parse("no json") == {}
    assert bench.parse('{"q1": 4}\n\nCorrection: {"q1": 5}') == {"q1": 5}


def test_report_grades_only_rows_asked_the_current_questions(tmp_path, monkeypatch):
    key = json.loads((BENCH / "questions.json").read_text())
    monkeypatch.setattr(bench, "REPORT", tmp_path / "RESULTS.md")
    numbers = lambda text: text.split("Environment:")[0]  # noqa: E731
    bench.report(key, "claude-sonnet-5-5")
    assert numbers(bench.REPORT.read_text()) == numbers((BENCH / "RESULTS.md").read_text())
    key["line_stock"]["questions"]["q1"]["q"] = "What is the lowest closing price?"
    bench.report(key, "claude-sonnet-5-5")
    assert "`line_stock`" not in bench.REPORT.read_text()
