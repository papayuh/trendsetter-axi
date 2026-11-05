import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import matplotlib.pyplot as plt
import pytest

BENCH = Path(__file__).parent.parent / "benchmarks" / "agent"
sys.path.insert(0, str(BENCH))
spec = importlib.util.spec_from_file_location("agent_bench", BENCH / "run.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_committed_answer_keys_match_the_charts():
    # results.jsonl was graded against questions*.json; a chart edit without a rerun would leave them disagreeing
    for charts, path in bench.SPLITS.values():
        key = json.loads(path.read_text())
        assert list(key) == list(charts)
        for cid, (kind, make) in charts.items():
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


def test_scores_only_rows_asked_the_current_questions():
    key = json.loads((BENCH / "questions.json").read_text())
    assert "line_stock" in bench.scored(key, "claude-sonnet-5-5", "after")[3]
    key["line_stock"]["questions"]["q1"]["q"] = "What is the lowest closing price?"
    assert "line_stock" not in bench.scored(key, "claude-sonnet-5-5", "after")[3]


@pytest.mark.parametrize("existing", [False, True])
def test_report_regenerates_from_results(tmp_path, monkeypatch, existing):
    expected = (BENCH / "RESULTS.md").read_bytes()
    monkeypatch.setattr(bench, "REPORT", tmp_path / "RESULTS.md")
    if existing:
        prefix, heading, _ = expected.partition(b"# Suite2 benchmark results\n")
        bench.REPORT.write_bytes(prefix + heading + b"stale body\n")
        monkeypatch.setattr(bench, "HERE", tmp_path)
    for _ in range(2):
        bench.write_report("claude-sonnet-5-5")
        assert bench.REPORT.read_bytes() == expected


@pytest.mark.parametrize("action,outcome", [
    ("report", None), ("smoke", "complete"), ("run", "complete"),
    ("smoke", "budget"), ("run", "budget"),
])
def test_suite2_entrypoint_preserves_aggregate(tmp_path, monkeypatch, action, outcome):
    import suite2

    expected = (BENCH / "RESULTS.md").read_bytes()
    prefix, heading, _ = expected.partition(b"# Suite2 benchmark results\n")
    monkeypatch.setattr(bench, "HERE", tmp_path)
    monkeypatch.setattr(bench, "REPORT", tmp_path / "RESULTS.md")
    bench.REPORT.write_bytes(prefix + heading + b"stale body\n")
    original_report = suite2.report
    if action != "report":
        manifest = suite2.load(verify_renderer=False)
        data = tmp_path / "data"
        data.mkdir()
        for name in ("calls.jsonl", "sessions.jsonl"):
            shutil.copyfile(suite2.DATA / name, data / name)
        monkeypatch.setattr(suite2, "DATA", data)
        def load(verify_renderer):
            assert verify_renderer
            return manifest
        monkeypatch.setattr(suite2, "load", load)
        monkeypatch.setattr(suite2, "run", lambda m, smoke: outcome)
    def forbidden(*args, **kwargs):
        pytest.fail("Offline report must not request renderer git history or call a model")
    monkeypatch.setattr(suite2.subprocess, "check_output", forbidden)
    monkeypatch.setattr(suite2, "call", forbidden)
    for _ in range(2):
        if outcome == "budget":
            with pytest.raises(SystemExit) as exc:
                bench.main(["--suite2", action])
            assert exc.value.code == 2
        else:
            bench.main(["--suite2", action])
        assert suite2.report is original_report
        if action == "report":
            assert bench.REPORT.read_bytes() == expected
        else:
            direct = tmp_path / "suite2.md"
            suite2.report(manifest, path=direct)
            assert bench.REPORT.read_bytes() == prefix + direct.read_bytes()


def test_suite3_report_regenerates_from_frozen_results(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("suite3_report", BENCH / "suite3.py")
    suite3 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(suite3)
    manifest = suite3.load(verify_code=False)
    monkeypatch.setattr(suite3, "HERE", tmp_path)
    suite3.report(manifest)
    assert (tmp_path / "RESULTS-suite3.md").read_bytes() == (BENCH / "RESULTS-suite3.md").read_bytes()


def test_grade_rejects_malformed_numbers():
    num = dict(type="number", answer=10, tol=.5)
    for given in ["1/0", "not 10", "", True, False, "nan", "inf", [10], {"v": 10}, "10 or 11"]:
        assert not bench.grade(num, given), given
    for given in [10, 10.4, "10", "9.6", "$9.6", " 10 "]:
        assert bench.grade(num, given), given
    assert bench.grade(dict(type="number", answer=1000, tol=.5), "1,000")
    count = dict(type="int", answer=3)
    assert bench.grade(count, "3") and bench.grade(count, 3)
    assert not bench.grade(count, 3.5) and not bench.grade(count, "3.0 approx")


def hashed(data):
    return hashlib.sha256(data).hexdigest()[:16]


def test_load_rejects_rows_whose_stimulus_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "RESULTS", tmp_path / "results.jsonl")
    monkeypatch.setattr(bench, "MANIFESTS", tmp_path / "manifests")
    bench.MANIFESTS.mkdir()
    key = {"c1": dict(kind="line", questions={"q1": dict(q="How many?", type="int", answer=3)})}
    row = dict(chart="c1", format="text", model="m", tag="after", asked=bench.asks(key["c1"]["questions"]), is_error=False,
               reply='{"q1": 3}', shown="aaaa")
    bench.RESULTS.write_text(json.dumps(row) + "\n")
    (bench.MANIFESTS / "after.json").write_text(json.dumps({"c1": {"text": "bbbb"}}))
    assert bench.load(key, "after") == ({}, 1)
    (bench.MANIFESTS / "after.json").write_text(json.dumps({"c1": {"text": "aaaa"}}))
    assert bench.load(key, "after") == ({("c1", "text", "m"): row}, 0)
    assert bench.load(key, "nope") == ({}, 0)
    # A missing hash is not evidence of matching a stimulus, even without a manifest entry.
    row.pop("shown")
    bench.RESULTS.write_text(json.dumps(row) + "\n")
    (bench.MANIFESTS / "after.json").write_text("{}")
    assert bench.load(key, "after") == ({}, 1)


def test_stale_hash_seed_is_excluded(tmp_path, monkeypatch):
    # the review's seed: a copied `after` row whose stimulus hash matches no fixture
    lines = (BENCH / "results.jsonl").read_text().splitlines()
    seed = dict(json.loads(next(l for l in lines if '"tag": "after"' in l)), shown="definitely-stale-hash", reply="{}")
    monkeypatch.setattr(bench, "RESULTS", tmp_path / "results.jsonl")
    bench.RESULTS.write_text("\n".join(lines + [json.dumps(seed)]) + "\n")
    key = json.loads((BENCH / "questions.json").read_text())
    usable, excluded = bench.load(key, "after")
    assert excluded == 1 and usable[seed["chart"], seed["format"], seed["model"]]["shown"] != seed["shown"]


def test_committed_manifests_match_rows_and_fixtures():
    rows = [json.loads(l) for l in (BENCH / "results.jsonl").read_text().splitlines()]
    for tag in ("before", "iter1", "after"):
        manifest = json.loads((BENCH / "manifests" / f"{tag}.json").read_text())
        assert manifest.pop("reconstructed", False) is (tag != "after")
        assert {(r["chart"], r["format"]): r["shown"] for r in rows if r["tag"] == tag} == {
            (c, f): h for c, fs in manifest.items() for f, h in fs.items()}
        if tag == "after":   # the text fixtures are committed (the PNGs are not): their bytes are the stimulus
            for c, fs in manifest.items():
                for f, h in fs.items():
                    if f != "image":
                        assert h == hashed((BENCH / "fixtures" / f"{c}.{bench.TEXTS[f]}").read_bytes() if f != "none" else b"")


def test_threshold_uses_integer_arithmetic():
    assert bench.meets(37, 39, 95) is False
    assert bench.meets(38, 39, 95) is True
    assert bench.meets(79, 81, 95) is True


def fake_provider(monkeypatch):
    """Swap the model call for canned right answers with fixed usage; return the list of calls it got."""
    calls = []

    def ask(model, cid, fmt, questions, env, tag):
        calls.append((cid, fmt, tag))
        return dict(chart=cid, format=fmt, model=model, reply=json.dumps({qid: q["answer"] for qid, q in questions.items()}),
                    is_error=False, input_tokens=100 + 10 * len(calls), output_tokens=20, duration_ms=1000, duration_api_ms=900,
                    wall_s=1.0, cost_usd=0.01, asked=bench.asks(questions), **env, tag=tag, shown=bench.shown(cid, fmt))

    monkeypatch.setattr(bench, "ask", ask)
    monkeypatch.setattr(bench, "subprocess", SimpleNamespace(run=lambda *a, **k: SimpleNamespace(stdout="fake-cli 1.0")))
    return calls


def run_main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["run.py", "--model", "m", *argv])
    bench.main()


def test_replicate_never_reuses_and_resume_never_repeats(tmp_path, monkeypatch):
    for name in ("FIXTURES", "OUT", "MANIFESTS"):
        monkeypatch.setattr(bench, name, tmp_path / name)
        getattr(bench, name).mkdir()
    monkeypatch.setattr(bench, "RESULTS", tmp_path / "results.jsonl")
    key = {c: dict(kind="line", questions={"q1": dict(q=f"How many in {c}?", type="int", answer=3)}) for c in ("c1", "c2")}
    for c in key:
        (bench.FIXTURES / f"{c}.txt").write_text(f"chart {c}\n")
        (bench.FIXTURES / f"{c}.summary.txt").write_text(f"summary {c}\n")
    monkeypatch.setattr(bench, "build", lambda split: key)
    monkeypatch.setattr(bench, "write_report", lambda model: None)
    calls = fake_provider(monkeypatch)
    cells = {(c, f) for c in key for f in ("none", "text", "summary")}

    run_main(monkeypatch, "--tag", "after", "--formats", "text,summary")
    assert {(c, f) for c, f, _ in calls} == cells and len(calls) == len(cells)
    calls.clear()
    run_main(monkeypatch, "--tag", "after", "--formats", "text,summary")   # resume: every cell present
    assert calls == []
    run_main(monkeypatch, "--tag", "other", "--formats", "text,summary")   # a new tag reuses identical stimuli
    assert calls == []
    run_main(monkeypatch, "--tag", "after", "--formats", "text,summary", "--replicate", "2")
    assert sorted(calls) == sorted((c, f, "after#2") for c, f in cells)
    reps = [json.loads(l) for l in bench.RESULTS.read_text().splitlines() if '"after#2"' in l]
    assert len(reps) == len(cells) and not any("reused_from" in r for r in reps)
    assert json.loads((bench.MANIFESTS / "after#2.json").read_text()) == json.loads((bench.MANIFESTS / "after.json").read_text())
    calls.clear()
    (bench.FIXTURES / "c2.txt").write_text("chart c2, redrawn\n")
    run_main(monkeypatch, "--tag", "after", "--formats", "text,summary")
    assert calls == [("c2", "text", "after")]
    assert json.loads((bench.MANIFESTS / "after.json").read_text())["c2"]["text"] == hashed(b"chart c2, redrawn\n")
    assert bench.load(key, "after")[0]["c2", "text", "m"]["shown"] == hashed(b"chart c2, redrawn\n")


def test_full_lifecycle_with_fake_provider(tmp_path, monkeypatch):
    for name in ("FIXTURES", "OUT", "MANIFESTS"):
        monkeypatch.setattr(bench, name, tmp_path / name)
    monkeypatch.setattr(bench, "RESULTS", tmp_path / "results.jsonl")
    monkeypatch.setattr(bench, "REPORT", tmp_path / "RESULTS.md")
    charts = {c: bench.CHARTS[c] for c in ("line_stock", "bar_fifteen", "hm_correlation")}
    monkeypatch.setattr(bench, "SPLITS", {"dev": (charts, tmp_path / "questions.json")})
    # build() needs tiktoken, mpl_ascii and plotext; stand-ins keep this test independent of them
    fail = lambda *a, **k: 1 / 0  # noqa: E731
    monkeypatch.setitem(sys.modules, "tiktoken", SimpleNamespace(get_encoding=lambda name: SimpleNamespace(encode=str.split)))
    monkeypatch.setitem(sys.modules, "plotext", SimpleNamespace(matplotlib=fail))
    monkeypatch.setitem(sys.modules, "mpl_ascii", SimpleNamespace(FigureCanvasAscii=fail))
    calls = fake_provider(monkeypatch)

    run_main(monkeypatch, "--tag", "after")
    arms = ["none", "text", "summary", "image", "mpl_ascii", "plotext", "ascii", "ascii_tall", "hybrid"]
    assert sorted(calls) == sorted((c, f, "after") for c in charts for f in arms)
    manifest = json.loads((bench.MANIFESTS / "after.json").read_text())
    assert manifest == {c: {f: hashed((bench.OUT / f"{c}.png").read_bytes() if f == "image" else b"" if f == "none"
                                      else (bench.FIXTURES / f"{c}.{bench.TEXTS[f]}").read_bytes()) for f in arms} for c in charts}
    n = sum(len(k["questions"]) for k in json.loads((tmp_path / "questions.json").read_text()).values())
    report = bench.REPORT.read_text()
    for arm in arms:   # every canned reply is the answer key's
        assert f"\n| {arm} | {n}/{n} (100%) |" in report, arm
    assert "incomplete" not in report

    lines = bench.RESULTS.read_text().splitlines()
    bench.RESULTS.write_text("\n".join(l for l in lines if not ('"hm_correlation"' in l and '"format": "hybrid"' in l)
                                         and '"bar_fifteen"' not in l) + "\n")
    bench.write_report("m")
    report = bench.REPORT.read_text()
    assert "2 incomplete charts" in report and "`hm_correlation` (hybrid)" in report
    assert f"`bar_fifteen` ({', '.join(arms)})" in report
    assert "questions on 1 charts" in report

    # A whole missing arm must not disappear from the population or make charts complete.
    bench.RESULTS.write_text("\n".join(l for l in lines if '"format": "hybrid"' not in l) + "\n")
    bench.write_report("m")
    report = bench.REPORT.read_text()
    assert "3 incomplete charts" in report
    assert all(f"`{c}` (hybrid)" in report for c in charts)

    # Exclusions remain visible even when no complete chart survives grading.
    bench.RESULTS.write_text("\n".join(json.dumps(dict(json.loads(l), shown="stale")) for l in lines) + "\n")
    bench.write_report("m")
    report = bench.REPORT.read_text()
    assert f"{len(lines)} rows excluded: stimulus changed since the manifest" in report
    assert "3 incomplete charts" in report
