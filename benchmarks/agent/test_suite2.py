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
                 cache_read_input_tokens=20, cache_creation_input_tokens=10), total_cost_usd=.002, is_error=False)
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
