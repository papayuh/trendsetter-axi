"""Offline suite3 protocol, tool isolation, accounting and resume tests."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
spec = importlib.util.spec_from_file_location("suite3", Path(__file__).with_name("suite3.py"))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def test_frozen_inputs_match_original():
    m = s.load(verify_code=False)
    assert len(m["charts"]) == 70
    assert len(m["charts"]) * len(m["trials"]) * len(m["arms"]) == 630
    assert len({v["stimuli"]["record"]["sha256"] for v in m["charts"].values()}) == 70
    for c in m["charts"].values():
        assert c["stimuli"]["record"] == c["stimuli"]["record+query"]
        record = json.loads((s.DATA / c["stimuli"]["record"]["file"]).read_text())
        assert record["declared"] == {}


@pytest.mark.parametrize("auth,error", [("none", False), ("oauth", False), ("env", True), ("user", True), (None, True)])
def test_cli_auth_model_usage(monkeypatch, auth, error):
    def fake(cmd, **kw):
        for flag in ("--safe-mode", "--no-session-persistence", "--strict-mcp-config", "--no-chrome"):
            assert flag in cmd
        assert cmd[cmd.index("--tools")+1] == ""
        assert cmd[cmd.index("--effort")+1] == "low"
        assert "ANTHROPIC_API_KEY" not in kw["env"]
        final = dict(type="result", is_error=False, result='{"q1":3}', total_cost_usd=.003,
                     usage=dict(input_tokens=10, cache_read_input_tokens=20, cache_creation_input_tokens=30,
                                output_tokens=4), modelUsage={s.MODEL:{}})
        events = ([] if auth is None else [dict(type="system", apiKeySource=auth)]) + [final]
        return subprocess.CompletedProcess(cmd, 0, "\n".join(map(json.dumps, events)), "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "never-send")
    monkeypatch.setattr(s.subprocess, "run", fake)
    row = s.invoke("prompt", "system", .1)
    assert row["is_error"] == error
    assert row["input_tokens"] == 60
    assert row["list_price_usd"] == .003


def fake_turn(reply, cost=.003, error=False):
    return dict(reply=json.dumps(reply), is_error=error, api_key_auth=False, input_tokens=100,
                output_tokens=10, list_price_usd=cost, cli_reported_usd=cost, wall_s=1)


def tiny_manifest(tmp_path):
    (tmp_path / "record.json").write_text('{}')
    return dict(charts={"c":dict(questions={"q1":dict(q="number?", type="int", answer=3)},
                stimuli={a:dict(file="record.json", sha256="x") for a in s.ARMS})})


def test_tool_cap_replays_and_cumulative_cost(monkeypatch, tmp_path):
    m = tiny_manifest(tmp_path)
    monkeypatch.setattr(s, "DATA", tmp_path)
    prompts, allowances = [], []
    def invoke(prompt, system, allowance):
        prompts.append(prompt)
        allowances.append(allowance)
        return fake_turn({"query":{"operation":"facts", "args":[]}})
    monkeypatch.setattr(s, "invoke", invoke)
    monkeypatch.setattr(s, "execute_query", lambda *args: dict(answer=3))
    row = s.call(m, "c", "record+query", 1, "attempt")
    assert row["query_turns"] == 4
    assert row["model_invocations"] == 5
    assert row["input_tokens"] == 500
    assert row["list_price_usd"] == pytest.approx(.015)
    assert allowances[-1] == pytest.approx(.088)
    assert "Query turn limit reached" in prompts[-1]
    assert prompts[-1].count("Previous assistant tool request") == 4
    assert row["reply"] == "{}"
    assert not row["is_error"]
    assert len(s.rows("turns.jsonl")) == 5


def test_optional_tool_and_plain_arm(monkeypatch, tmp_path):
    m = tiny_manifest(tmp_path)
    monkeypatch.setattr(s, "DATA", tmp_path)
    monkeypatch.setattr(s, "invoke", lambda *args: fake_turn({"q1":3}))
    for arm in s.ARMS:
        row = s.call(m, "c", arm, 1, arm)
        assert row["query_turns"] == 0
        assert row["model_invocations"] == 1
        assert s.old.parsed(row["reply"]) == {"q1":3}


def test_unknown_cost_uses_remaining_reservation(monkeypatch):
    def timeout(*args, **kw):
        raise subprocess.TimeoutExpired(args[0], 300)
    monkeypatch.setattr(s.subprocess, "run", timeout)
    row = s.invoke("x", "y", .07)
    assert row["list_price_usd"] == .07
    assert row["is_error"]


def test_resume_reserves_interruption_and_preserves_auth(monkeypatch, tmp_path):
    monkeypatch.setattr(s, "DATA", tmp_path)
    pending = [dict(chart="c", arm="record", trial=1, attempt_id="finished"),
               dict(chart="c", arm="record+query", trial=1, attempt_id="interrupted")]
    (tmp_path / "pending.json").write_text(json.dumps(pending))
    s.append(tmp_path / "calls.jsonl", dict(**pending[0], is_error=False, list_price_usd=.01))
    s.append(tmp_path / "turns.jsonl", dict(attempt_id="interrupted", api_key_auth=True,
             list_price_usd=.005, cli_reported_usd=.005, wall_s=2))
    s.recover({})
    rows = s.rows()
    assert len(rows) == 2
    assert rows[-1]["list_price_usd"] == .1
    assert rows[-1]["api_key_auth"]
    assert rows[-1]["wall_unknown"]
    s.recover({})
    assert len(s.rows()) == 2
    with pytest.raises(RuntimeError, match="API-key auth"):
        s.run({})


def test_query_cli_no_shell_or_other_record(monkeypatch, tmp_path):
    monkeypatch.setattr(s, "DATA", tmp_path)
    def fake(cmd, **kwargs):
        assert cmd[:3] == [sys.executable, "-m", "trendsetter_axi.queries"]
        assert cmd[3] == str((tmp_path / "record.json").resolve())
        assert cmd[4:] == ["first_x_where", '"m0"', '"y > 0; $(false)"']
        assert not kwargs.get("shell")
        return subprocess.CompletedProcess(cmd, 0, '{"answer":3}', "")
    monkeypatch.setattr(s.subprocess, "run", fake)
    assert s.execute_query(tmp_path / "record.json", dict(operation="first_x_where", args=["m0", "y > 0; $(false)"])) == {"answer":3}
    for request in ({"operation":"diff", "args":["/etc/passwd"]}, {"operation":"facts", "args":"bad"}, {}):
        assert "unavailable" in s.execute_query(tmp_path / "record.json", request)


def test_actual_query_cli(tmp_path, monkeypatch):
    # Real stdlib CLI invocation, no model/network.
    monkeypatch.setattr(s, "DATA", tmp_path)
    path = tmp_path / "record.json"
    path.write_text(json.dumps(dict(axes=[dict(x=dict(scale="linear"), y=dict(scale="linear"))],
        marks=[dict(id="m0", kind="line", axes=0, x=[0,1], y=[2,4], interp="linear")], declared={})))
    assert s.execute_query(path, dict(operation="value_at", args=["m0", 1]))["answer"] == 4


def test_budget_stops_before_dispatch(monkeypatch, tmp_path):
    m = tiny_manifest(tmp_path)
    m["trials"] = [1,2,3]
    monkeypatch.setattr(s, "DATA", tmp_path)
    s.append(tmp_path / "calls.jsonl", dict(chart="c", arm="record", trial=1, attempt_id="old",
        is_error=True, list_price_usd=19.9, manifest_sha256=s.old.digest(m)))
    monkeypatch.setattr(s, "call", lambda *args: pytest.fail("Must reserve before dispatch"))
    assert s.run(m) == "budget"


def test_completed_resume_has_no_model_calls(monkeypatch, tmp_path):
    m = tiny_manifest(tmp_path)
    m["trials"] = [1, 2, 3]
    monkeypatch.setattr(s, "DATA", tmp_path)
    for trial in m["trials"]:
        for arm in s.ARMS:
            s.append(tmp_path / "calls.jsonl", dict(chart="c", arm=arm, trial=trial,
                attempt_id=f"{arm}-{trial}", is_error=False, list_price_usd=.01,
                manifest_sha256=s.old.digest(m)))
    monkeypatch.setattr(s, "call", lambda *args: pytest.fail("Completed cells must not be re-asked"))
    assert s.run(m) == "complete"


def test_offline_report_never_verifies_code_or_calls_model(monkeypatch, tmp_path):
    m = s.load(verify_code=False)
    monkeypatch.setattr(s, "HERE", tmp_path)
    monkeypatch.setattr(s, "DATA", tmp_path)
    monkeypatch.setattr(s, "invoke", lambda *args: pytest.fail("Report cannot call a model"))
    s.report(m)
    report = (tmp_path / "RESULTS-suite3.md").read_text()
    assert "NOT EVALUABLE — incomplete" in report
    assert "Earlier-run suite2" in report
    assert "659/840" in report and "797/840" in report


def test_query_action_preserves_outer_object():
    assert s.action_object('{"query":{"operation":"facts","args":[]}}') == {
        "query":{"operation":"facts", "args":[]}}
    assert s.action_object('```json\n{"q1":3}\n```') == {"q1":3}


def test_stored_results_auth_model_usage_and_bounds():
    m = s.load(verify_code=False)
    rows = s.rows()
    if not rows:
        pytest.skip("No model observations stored yet")
    good = [r for r in rows if not r["is_error"]]
    assert len(good) == len({(r["chart"], r["arm"], r["trial"]) for r in good})
    assert sum(r["list_price_usd"] for r in rows) <= s.BUDGET
    for r in good:
        assert r["manifest_sha256"] == s.old.digest(m)
        assert r["stimulus_sha256"] == m["charts"][r["chart"]]["stimuli"][r["arm"]]["sha256"]
        assert 0 <= r["query_turns"] <= s.MAX_QUERIES
        assert r["model_invocations"] == r["query_turns"] + 1
        for t in r["turns"]:
            assert t["auth_sources"] == ["none"]
            assert not t["api_key_auth"]
            assert set(t["final"]["modelUsage"]) == {s.MODEL}
            assert t["final"]["subagent_stats"]["spawned"] == 0
        for field in ("input_tokens", "output_tokens", "list_price_usd", "wall_s"):
            assert r[field] == pytest.approx(sum(t[field] for t in r["turns"]))


def test_stored_report_reproduces_exactly(monkeypatch, tmp_path):
    expected_path = s.HERE / "RESULTS-suite3.md"
    if not expected_path.exists():
        pytest.skip("No stored report yet")
    expected = expected_path.read_text()
    m = s.load(verify_code=False)
    monkeypatch.setattr(s, "HERE", tmp_path)
    s.report(m)
    assert (tmp_path / "RESULTS-suite3.md").read_text() == expected


def test_source_change_refused(monkeypatch):
    monkeypatch.setattr(s, "code_hashes", lambda: {})
    with pytest.raises(RuntimeError, match="Frozen source"):
        s.load()
