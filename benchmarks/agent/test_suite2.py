"""Offline invariants: never calls a model or reads credentials."""
import importlib.util
import json
import math
from pathlib import Path
import subprocess

import matplotlib.pyplot as plt
import pytest

spec = importlib.util.spec_from_file_location("suite2", Path(__file__).with_name("suite2.py"))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def test_suite_counts_answers_and_features():
    items = list(s.cases())
    assert len(items) == 70
    assert sum(len(c["questions"]) for _, _, c in items) == 280
    assert len({c["seed"] for _, _, c in items}) == 70
    features = {f for _, _, c in items for f in c["features"]}
    assert {"masked points", "NaN gaps", "tied maxima", "constant", "1e-8 magnitudes", "negatives",
            "large offset", "timestamps seconds apart", "explicit tick aliases", "lone heatmap spike",
            "unsupported Wedge"} <= features
    for _, _, c in items:
        json.dumps(c, allow_nan=False)
        for q in c["questions"].values():
            assert s.score(q, q["answer"])[0]
    plt.close("all")


def test_grade_abstain_and_numeric_error():
    q = s.numeric("tiny?", 1e-8, 1e-8)
    assert not s.score(q, 0)[0]
    assert s.score(q, None) == (False, True, None)
    for invalid in (True, "0", math.inf, []):
        assert not s.score(q, invalid)[0]
    assert s.score(s.integer("count", 3), 3)[0]
    assert not s.score(s.integer("count", 3), 3.01)[0]


def test_environment_removes_keys_and_routing(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK"):
        monkeypatch.setenv(key, "test-secret")
    env = s.child_env()
    assert all(key not in env for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK"))


def test_sample_uniform_no_extrema_injection():
    case = dict(title="sample", series=[dict(name="x", columns=["x", "y"], rows=[[i, i == 3] for i in range(100)])])
    sampled = json.loads(s.table(case, 5).splitlines()[-1])
    assert sampled["selected_indices"] == [0, 24, 49, 74, 99]
    assert sampled["total_rows"] == 100


def test_manifest_fixture_integrity_and_budget():
    m = s.load()
    assert len(m["charts"]) == 70
    assert m["trials"] == [1, 2, 3]
    assert m["renderer_commit"] == s.BASE
    for c in m["charts"].values():
        max_rows = max(len(series["rows"]) for series in c["series"])
        if max_rows <= 64:
            assert c["table_rows_per_series"] == max_rows
        elif c["table_rows_per_series"] > 1:
            assert c["stimuli"]["table"]["o200k"] <= c["table_target_o200k"]
        raw = (s.DATA / c["stimuli"]["table"]["file"]).read_text()
        plus = (s.DATA / c["stimuli"]["table+stats"]["file"]).read_text()
        assert plus.startswith(raw + "\nFull-source statistics:")


@pytest.mark.parametrize("auth,stop", [("none", False), ("user", True), ("env", True)])
def test_auth_guard_and_usage(monkeypatch, auth, stop):
    m = s.load()
    final = dict(type="result", result='{"q1":null}', usage=dict(input_tokens=100, output_tokens=8,
                 cache_read_input_tokens=20, cache_creation_input_tokens=10), total_cost_usd=.002, is_error=False,
                 modelUsage={s.MODEL: {}})
    out = "\n".join(json.dumps(e) for e in [dict(type="system", apiKeySource=auth), final])
    def fake(cmd, **kwargs):
        assert "--safe-mode" in cmd
        assert cmd[cmd.index("--tools")+1] == ""
        assert "ANTHROPIC_API_KEY" not in kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, out, "")
    monkeypatch.setattr(s.subprocess, "run", fake)
    row = s.call(m, "s2_line_00", "summary", 1)
    assert row["api_key_auth"] == stop
    assert row["is_error"] == stop
    assert row["input_tokens"] == 130
    assert row["list_price_usd"] == .002


def test_interrupted_batch_reserves_only_unrecorded_attempts(monkeypatch, tmp_path):
    monkeypatch.setattr(s, "DATA", tmp_path)
    m = {"schema": 2}
    pending = s.journal_batch([("chart", "table", 1), ("chart", "summary", 1)])
    (tmp_path / "calls.jsonl").write_text(json.dumps(dict(**pending[0], is_error=False, list_price_usd=.01)) + "\n")
    s.recover_pending(m)
    recovered = s.rows()
    assert len(recovered) == 2
    assert recovered[1]["attempt_id"] == pending[1]["attempt_id"]
    assert recovered[1]["list_price_usd"] == s.CALL_CAP
    assert recovered[1]["wall_unknown"]
    s.recover_pending(m)
    assert len(s.rows()) == 2


def test_completed_rerun_makes_no_calls(monkeypatch):
    m = s.load()
    if len([r for r in s.rows() if not r["is_error"]]) != 1470:
        pytest.skip("Full raw results not yet present")
    def forbidden(*args, **kwargs):
        raise AssertionError("Completed cells must never be re-asked")
    monkeypatch.setattr(s, "call", forbidden)
    assert s.run(m) == "complete"


def test_full_results_auth_model_and_manifest():
    m = s.load()
    good = [r for r in s.rows() if not r["is_error"]]
    if not good:
        pytest.skip("No model calls yet")
    assert len(good) == len({(r["chart"], r["arm"], r["trial"]) for r in good})
    for r in good:
        assert r["manifest_sha256"] == s.digest(m)
        assert r["stimulus_sha256"] == m["charts"][r["chart"]]["stimuli"][r["arm"]]["sha256"]
        assert r["auth_sources"] == ["none"]
        assert not r["api_key_auth"]
        assert set(r["final"]["modelUsage"]) == {s.MODEL}
        assert r["final"]["subagent_stats"]["spawned"] == 0
    assert sum(r["list_price_usd"] for r in s.rows()) <= s.BUDGET


def test_report_without_frozen_commit(monkeypatch, tmp_path):
    # The aggregate index adds suite3 above the unchanged suite2 report.
    heading = "# Suite2 benchmark results\n"
    expected = heading + (s.HERE / "RESULTS.md").read_text().split(heading, 1)[1]
    def unavailable(*args, **kwargs):
        pytest.fail("Report must not request renderer git history")
    monkeypatch.setattr(s.subprocess, "check_output", unavailable)
    monkeypatch.setattr(s, "HERE", tmp_path)
    s.main(["report"])
    assert (tmp_path / "RESULTS.md").read_text() == expected


@pytest.mark.parametrize("action", ["smoke", "run"])
def test_model_run_refuses_missing_frozen_commit(monkeypatch, action):
    def unavailable(cmd, **kwargs):
        assert cmd[:2] == ["git", "show"]
        assert cmd[2].startswith(s.BASE + ":")
        raise subprocess.CalledProcessError(128, cmd, stderr=b"frozen commit unavailable")
    def forbidden(*args, **kwargs):
        pytest.fail("Model run must not start without verifying frozen renderer")
    monkeypatch.setattr(s.subprocess, "check_output", unavailable)
    monkeypatch.setattr(s, "run", forbidden)
    with pytest.raises(subprocess.CalledProcessError):
        s.main([action])


@pytest.mark.parametrize("change,error", [("protocol", "Protocol differs"), ("fixture", "Frozen stimulus changed")])
def test_report_only_load_keeps_manifest_and_fixture_checks(monkeypatch, tmp_path, change, error):
    manifest = json.loads(s.MANIFEST.read_text())
    if change == "protocol":
        manifest["system"] = "changed prompt"
    else:
        next(iter(manifest["charts"].values()))["stimuli"]["summary"]["sha256"] = "changed fixture"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr(s, "MANIFEST", path)
    with pytest.raises(RuntimeError, match=error):
        s.load(verify_renderer=False)
