"""Frozen record/query extension to suite2; subscription CLI only."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import time

import numpy as np
import suite2 as old
from trendsetter_axi import from_figure

HERE, ROOT = old.HERE, old.ROOT
MANIFEST = HERE / "manifests/suite3.json"
DATA = HERE / "results/suite3"
ARMS = ["record", "record+query", "table+stats"]
MODEL, BUDGET, CALL_CAP, MAX_QUERIES = old.MODEL, 20.0, .10, 4
OPERATIONS = ["value_at", "band_width_at", "first_x_where", "crossing", "count_where", "check", "facts"]
TOOL = '''
You may query the supplied chart record. To request exactly one tool call return only
{"query":{"operation":"value_at","args":["m0",3]}} instead of answers.
Operations: value_at(mark,x), band_width_at(mark,x), first_x_where(mark,predicate),
crossing(line,line_or_number), count_where(predicate,table=null), check(claim), facts().
Predicates allow column names, constants, arithmetic, comparisons, and/or/not.
count_where needs an attached records table or explicit row objects you supply;
no hidden source data is attached. facts reports eligible geometry, not population intent.
The tool runs python -m trendsetter_axi.queries on this exact record; it returns
answer, evidence, convention and possibly unavailable. No other tool exists.
You may make at most four query requests, then must return the question-ID answer object.
'''.strip()
SUCCESS = ("Each new arm: strictly beat stored summary/hybrid pooled and in every trial; "
           "separately, be within 2 correct of same-day table+stats per trial and within 6 pooled. "
           "Incomplete runs cannot pass. No token threshold.")


def utc():
    return datetime.now(timezone.utc).isoformat()


def code_hashes():
    paths = sorted((ROOT / "src").rglob("*.py")) + [Path(__file__).resolve(), HERE / "suite2.py", HERE / "README-suite3.md"]
    return {str(p.relative_to(ROOT)): old.digest(p.read_bytes()) for p in paths}


def build():
    if MANIFEST.exists():
        raise RuntimeError("Manifest already frozen; refusing overwrite")
    source = old.load(verify_renderer=False)
    DATA.mkdir(parents=True, exist_ok=True)
    charts = {}
    for cid, fig, case in old.cases():
        if any(case[k] != source["charts"][cid][k] for k in case):
            raise RuntimeError(f"Regenerated chart differs from suite2: {cid}")
        start = time.perf_counter()
        record = json.dumps(from_figure(fig), separators=(",", ":"), allow_nan=False)
        elapsed = time.perf_counter() - start
        path = DATA / f"{cid}.record.json"
        path.write_text(record + "\n")
        control = old.DATA / source["charts"][cid]["stimuli"]["table+stats"]["file"]
        cp = DATA / control.name
        cp.write_bytes(control.read_bytes())
        r = dict(file=path.name, sha256=old.digest(path.read_bytes()))
        charts[cid] = dict(kind=case["kind"], questions=case["questions"], reader_s=elapsed,
                           stimuli={"record": r, "record+query": r,
                                    "table+stats": dict(file=cp.name, sha256=old.digest(cp.read_bytes()))})
    return dict(schema=3, source_manifest_sha256=old.digest(source), code_sha256=code_hashes(),
                model=MODEL, effort="low", arms=ARMS, trials=[1, 2, 3], system=old.SYSTEM,
                tool_prompt=TOOL, max_queries=MAX_QUERIES, operations=OPERATIONS,
                budget_usd=BUDGET, call_cap_usd=CALL_CAP, success=SUCCESS, charts=charts,
                environment=dict(python=sys.version.split()[0], numpy=np.__version__,
                                 matplotlib=old.matplotlib.__version__))


def load(verify_code=True):
    m = json.loads(MANIFEST.read_text())
    protocol = (m["model"], m["effort"], m["arms"], m["system"], m["tool_prompt"],
                m["max_queries"], m["operations"], m["budget_usd"], m["call_cap_usd"], m["success"])
    if protocol != (MODEL, "low", ARMS, old.SYSTEM, TOOL, MAX_QUERIES, OPERATIONS, BUDGET, CALL_CAP, SUCCESS):
        raise RuntimeError("Protocol differs from frozen manifest")
    source = old.load(verify_renderer=False)
    if old.digest(source) != m["source_manifest_sha256"]:
        raise RuntimeError("Suite2 source manifest changed")
    if set(m["charts"]) != set(source["charts"]) or m["trials"] != [1, 2, 3]:
        raise RuntimeError("Suite3 cases/trials differ from suite2")
    for cid, case in m["charts"].items():
        if case["questions"] != source["charts"][cid]["questions"]:
            raise RuntimeError("Suite2 questions changed")
        for stimulus in case["stimuli"].values():
            if old.digest((DATA / stimulus["file"]).read_bytes()) != stimulus["sha256"]:
                raise RuntimeError(f"Frozen stimulus changed: {cid}")
        if case["stimuli"]["table+stats"]["sha256"] != source["charts"][cid]["stimuli"]["table+stats"]["sha256"]:
            raise RuntimeError("Control differs from suite2")
    if verify_code:
        if code_hashes() != m["code_sha256"]:
            raise RuntimeError("Frozen source or suite3 protocol changed")
        # Uncommitted stimuli/protocol cannot be used for model calls.
        for rel, sha in m["code_sha256"].items():
            if old.digest(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) != sha:
                raise RuntimeError(f"Uncommitted frozen code: {rel}")
        if subprocess.check_output(["git", "show", "HEAD:" + str(MANIFEST.relative_to(ROOT))], cwd=ROOT) != MANIFEST.read_bytes():
            raise RuntimeError("Manifest must be committed before calls")
        for case in m["charts"].values():
            for stimulus in case["stimuli"].values():
                rel = str((DATA / stimulus["file"]).relative_to(ROOT))
                if old.digest(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) != stimulus["sha256"]:
                    raise RuntimeError(f"Uncommitted stimulus: {rel}")
    return m


def invoke(prompt, system, allowance):
    cmd = ["claude", "-p", "--model", MODEL, "--safe-mode", "--tools", "", "--strict-mcp-config",
           "--mcp-config", '{"mcpServers":{}}', "--setting-sources", "", "--disable-slash-commands",
           "--no-session-persistence", "--no-chrome", "--effort", "low", "--max-budget-usd", str(allowance),
           "--system-prompt", system, "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
    start = time.perf_counter()
    payload = dict(type="user", message=dict(role="user", content=[dict(type="text", text=prompt)]))
    try:
        p = subprocess.run(cmd, input=json.dumps(payload) + "\n", capture_output=True, text=True,
                           env=old.child_env(), timeout=300, cwd=DATA)
        events = []
        for line in p.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        final = next((e for e in reversed(events) if e.get("type") == "result"), {})
        auth = [e["apiKeySource"] for e in events if "apiKeySource" in e]
        raw = p.stdout + "\n" + p.stderr
        api_auth = any(str(a).lower() not in ("none", "null", "", "claude.ai", "oauth") for a in auth)
        api_auth |= bool(re.search(r'using api.?key|api.?key auth|"apiKeySource"\s*:\s*"(?:env|api)', raw, re.I))
        usage, cost = final.get("usage", {}), final.get("total_cost_usd")
        error = (not auth or api_auth or final.get("is_error", not bool(final)) or p.returncode != 0
                 or set(final.get("modelUsage", {})) != {MODEL})
        return dict(reply=final.get("result", ""), final=final, events=events, stderr=p.stderr,
                    auth_sources=auth, api_key_auth=api_auth, is_error=bool(error), usage=usage,
                    input_tokens=sum(usage.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
                    output_tokens=usage.get("output_tokens", 0), cli_reported_usd=cost,
                    list_price_usd=allowance if cost is None else float(cost),
                    wall_s=time.perf_counter()-start, returncode=p.returncode)
    except subprocess.TimeoutExpired as exc:
        return dict(reply="", is_error=True, api_key_auth=False, auth_sources=[], usage={},
                    input_tokens=0, output_tokens=0, cli_reported_usd=None, list_price_usd=allowance,
                    wall_s=time.perf_counter()-start, diagnostic="CLI timeout after 300s",
                    partial_stdout=(exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout)


def action_object(reply):
    """First complete action object, not suite2's innermost-answer parser."""
    for i, char in enumerate(reply):
        if char == "{":
            try:
                value, _ = json.JSONDecoder().raw_decode(reply[i:])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                pass
    return {}


def execute_query(path, request):
    if not isinstance(request, dict) or set(request) != {"operation", "args"}:
        return dict(answer=None, unavailable="tool requires operation and args")
    operation, args = request["operation"], request["args"]
    if operation not in OPERATIONS or not isinstance(args, list) or len(json.dumps(args)) > 32768:
        return dict(answer=None, unavailable="unsupported operation or invalid/oversized argument list")
    cmd = [sys.executable, "-m", "trendsetter_axi.queries", str(path.resolve()), operation]
    cmd += [json.dumps(arg, allow_nan=False) for arg in args]
    env = old.child_env()
    env["PYTHONPATH"] = str(ROOT / "src")
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=DATA, env=env)
    if p.returncode:
        return dict(answer=None, unavailable=p.stderr.strip(), returncode=p.returncode)
    return json.loads(p.stdout)


def append(path, row):
    with path.open("a") as f:
        f.write(json.dumps(row, allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def call(m, cid, arm, trial, attempt_id):
    case = m["charts"][cid]
    stimulus = case["stimuli"][arm]
    path = DATA / stimulus["file"]
    prompt = path.read_text() + "\n\nQuestions:\n" + old.asks(case)
    system = old.SYSTEM + ("\n\n" + TOOL if arm == "record+query" else "")
    row = dict(chart=cid, arm=arm, trial=trial, attempt_id=attempt_id, model=MODEL,
               manifest_sha256=old.digest(m), stimulus_sha256=stimulus["sha256"], started_utc=utc(),
               turns=[], queries=[], input_tokens=0, output_tokens=0, list_price_usd=0,
               wall_s=0, is_error=False, api_key_auth=False, reply="")
    for turn in range(MAX_QUERIES + 1 if arm == "record+query" else 1):
        allowance = CALL_CAP - row["list_price_usd"]
        if allowance <= 0:
            row.update(is_error=True, diagnostic="Cell budget exhausted before final answer")
            break
        if turn == MAX_QUERIES:
            prompt += "\nQuery turn limit reached. Return only final question-ID answers now."
        result = invoke(prompt, system, allowance)
        row["turns"].append(result)
        for key in ("input_tokens", "output_tokens", "list_price_usd", "wall_s"):
            row[key] += result[key]
        row["api_key_auth"] |= result["api_key_auth"]
        row["reply"] = result["reply"]
        # Durable per-invocation evidence survives a later killed parent.
        append(DATA / "turns.jsonl", dict(attempt_id=attempt_id, turn=turn, **result))
        if result["is_error"]:
            row.update(is_error=True, diagnostic="CLI/auth/model error; see turns")
            break
        answer = action_object(result["reply"])
        if arm != "record+query" or "query" not in answer:
            break
        if turn == MAX_QUERIES:
            # Protocol violation is a malformed answer, not an infrastructure retry.
            row["reply"] = "{}"
            row["protocol_violation"] = "Query requested after cap"
            break
        request = answer["query"]
        try:
            response = execute_query(path, request)
        except (ValueError, TypeError, subprocess.TimeoutExpired) as exc:
            response = dict(answer=None, unavailable=f"query invocation failed: {exc}")
        row["queries"].append(dict(request=request, response=response))
        prompt += ("\n\nPrevious assistant tool request:\n" + json.dumps(answer) +
                   "\nTool response:\n" + json.dumps(response) +
                   f"\nQuery requests used: {len(row['queries'])}/{MAX_QUERIES}. Return next request or final answers.")
    row["query_turns"] = len(row["queries"])
    row["model_invocations"] = len(row["turns"])
    return row


def rows(name="calls.jsonl"):
    path = DATA / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def recover(m):
    path = DATA / "pending.json"
    if not path.exists():
        return
    completed = {r["attempt_id"] for r in rows()}
    for attempt in json.loads(path.read_text()):
        if attempt["attempt_id"] not in completed:
            turns = [t for t in rows("turns.jsonl") if t["attempt_id"] == attempt["attempt_id"]]
            append(DATA / "calls.jsonl", dict(**attempt, model=MODEL, manifest_sha256=old.digest(m),
                is_error=True, api_key_auth=any(t.get("api_key_auth") for t in turns),
                list_price_usd=max(CALL_CAP, sum(t["list_price_usd"] for t in turns)),
                turns=turns, wall_s=sum(t["wall_s"] for t in turns), wall_unknown=True,
                reply="", diagnostic="Parent interrupted; reserve full cell allowance; completed turns retained"))
    path.unlink()


def run(m, smoke=False):
    recover(m)
    previous = rows()
    if any(r.get("api_key_auth") for r in previous + rows("turns.jsonl")):
        raise RuntimeError("API-key auth reported; run stopped including on resume")
    if any(r["manifest_sha256"] != old.digest(m) for r in previous):
        raise RuntimeError("Existing attempts belong to a different manifest")
    good = {(r["chart"], r["arm"], r["trial"]) for r in previous if not r["is_error"]}
    jobs = []
    for trial in m["trials"]:
        ids = (["s2_line_00", "s2_scatter_04", "s2_bar_02", "s2_heatmap_05", "s2_errorbar_01"]
               if smoke else list(m["charts"]))
        random.Random(9100 + trial).shuffle(ids)
        for cid in ids:
            arms = ARMS.copy()
            random.Random(f"{trial}:{cid}").shuffle(arms)
            jobs.extend((cid, arm, trial) for arm in arms if (cid, arm, trial) not in good)
        if smoke:
            break
    spent = sum(r["list_price_usd"] for r in previous)
    with ThreadPoolExecutor(max_workers=4) as executor:
        for offset in range(0, len(jobs), 4):
            batch = jobs[offset:offset+4]
            if spent + len(batch) * CALL_CAP > BUDGET:
                print(f"STOP budget ${spent:.6f}; next reservation exceeds ${BUDGET}", flush=True)
                return "budget"
            pending = [dict(chart=c, arm=a, trial=t, attempt_id=f"{time.time_ns()}-{i}")
                       for i, (c, a, t) in enumerate(batch)]
            tmp = DATA / "pending.tmp"
            with tmp.open("w") as f:
                json.dump(pending, f)
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(DATA / "pending.json")
            futures = [executor.submit(call, m, p["chart"], p["arm"], p["trial"], p["attempt_id"]) for p in pending]
            stop = False
            for future in as_completed(futures):
                row = future.result()
                append(DATA / "calls.jsonl", row)
                spent += row["list_price_usd"]
                print(row["chart"], row["arm"], row["trial"], "ERROR" if row["is_error"] else "ok",
                      f"queries={row.get('query_turns', 0)} ${spent:.6f}", flush=True)
                stop |= row["is_error"]
                if row["is_error"]:
                    print(json.dumps(row)[-6000:], flush=True)
            (DATA / "pending.json").unlink()
            if stop:
                return "error"
    return "complete"


def report(m):
    attempts = rows()
    by = {(r["chart"], r["arm"], r["trial"]): r for r in attempts
          if not r["is_error"] and r["manifest_sha256"] == old.digest(m)}
    paired = [(c, t) for c in m["charts"] for t in m["trials"] if all((c, a, t) in by for a in ARMS)]
    complete = len(paired) == 210

    def metrics(arm, selected):
        d = dict(correct=0, n=0, abstain=0, input=0, output=0, wall=0, queries=0, invocations=0)
        relative, absolute = [], []
        for cid, trial in selected:
            r = by[cid, arm, trial]
            answers = old.parsed(r["reply"])
            for k, field in (("input", "input_tokens"), ("output", "output_tokens"), ("wall", "wall_s"),
                             ("queries", "query_turns"), ("invocations", "model_invocations")):
                d[k] += r.get(field, 0)
            for qid, q in m["charts"][cid]["questions"].items():
                ok, ab, err = old.score(q, answers.get(qid))
                d["correct"] += ok
                d["abstain"] += ab
                d["n"] += 1
                if err is not None:
                    relative.append(err)
                    absolute.append(abs(answers[qid] - q["answer"]))
        d.update(numeric_n=len(relative), relative=float(np.mean(relative)) if relative else None,
                 mae=float(np.mean(absolute)) if absolute else None)
        return d

    sessions = rows("sessions.jsonl")
    lines = ["# Suite3 benchmark results", "", f"Model `{MODEL}`, effort low; subscription CLI only.",
             f"Manifest SHA-256: `{old.digest(m)}`.",
             f"Planned: 70 charts × 4 questions × 3 trials × 3 arms = 630 cells / 2,520 answers.",
             f"Observed: {len(attempts)} attempts; {len(by)} successful cells; {sum(r['is_error'] for r in attempts)} errors; {len(paired)}/210 complete paired chart-trials.",
             f"All-attempt list-price equivalent: ${sum(r['list_price_usd'] for r in attempts):.6f} / $20 guide. "
             f"CLI-reported: ${sum(t.get('cli_reported_usd') or 0 for r in attempts for t in r.get('turns', [])):.6f}. "
             "Not subscription billing. Unknown costs retain conservative reservations.",
             f"Summed child wall seconds: {sum(r['wall_s'] for r in attempts):.3f}; interrupted attempts with unknown remaining duration: {sum(r.get('wall_unknown', False) for r in attempts)}. "
             f"Recorded session elapsed seconds: {sum(s['elapsed_s'] for s in sessions):.3f} (external waits excluded).", "",
             "Only chart-trials complete in all three arms enter comparisons. Input tokens include cached input, "
             "all transcript replays and tool overhead; output separate. Null/missing = abstain; malformed replies wrong. "
             "Numeric relative error and mixed-unit MAE include only finite numeric replies, with denominator shown.", ""]

    def section(title, selected):
        lines.extend([f"## {title}", "", "| arm | correct / questions | wrong | abstain | input tokens | output tokens | summed wall s | query turns | model invocations | numeric n | mean relative error | mixed-unit MAE |",
                      "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
        for arm in ARMS:
            d = metrics(arm, selected)
            err = f"{d['relative']:.6g} | {d['mae']:.6g}" if d["numeric_n"] else "— | —"
            lines.append(f"| {arm} | {d['correct']}/{d['n']} | {d['n']-d['correct']-d['abstain']} | {d['abstain']} | {d['input']} | {d['output']} | {d['wall']:.3f} | {d['queries']} | {d['invocations']} | {d['numeric_n']} | {err} |")
        lines.append("")

    section("Pooled paired results", paired)
    lines += ["## Predeclared success bars", "", SUCCESS, ""]
    control = metrics("table+stats", paired)
    for arm in ARMS[:2]:
        d = metrics(arm, paired)
        improvement = complete and d["correct"] > 700 and all(
            metrics(arm, [(c,t) for c,t in paired if t == trial])["correct"] > baseline
            for trial, baseline in zip(m["trials"], [234,235,231]))
        competitive = complete and d["correct"] >= control["correct"] - 6 and all(
            metrics(arm, [(c,t) for c,t in paired if t == trial])["correct"] >=
            metrics("table+stats", [(c,t) for c,t in paired if t == trial])["correct"] - 2 for trial in m["trials"])
        outcome = lambda passed: ("PASS" if passed else "FAIL") if complete else "NOT EVALUABLE — incomplete"
        ratio = f"{100*d['input']/control['input']:.1f}%" if control["input"] else "—"
        lines.append(f"- **{arm}**: earlier summary/hybrid improvement **{outcome(improvement)}**; "
                     f"same-day control competitiveness **{outcome(competitive)}**. Total input vs same-day control: {ratio}.")
    lines += ["", "## Earlier-run suite2 results (stored, not rerun here)", "",
              "| arm | correct / questions | input tokens | trial 1 / 2 / 3 correct |",
              "| --- | ---: | ---: | --- |",
              "| summary | 659/840 | 252243 | 219 / 219 / 221 |",
              "| hybrid | 700/840 | 305481 | 234 / 235 / 231 |",
              "| table+stats | 797/840 | 330342 | 266 / 265 / 266 |", "",
              "Earlier-run results are not same-day paired controls; compare descriptive counts only. "
              "The original suite2 report remains in [RESULTS.md](RESULTS.md).", ""]
    for trial in m["trials"]:
        section(f"Trial {trial}", [(c,t) for c,t in paired if t == trial])
    for kind in dict.fromkeys(c["kind"] for c in m["charts"].values()):
        section(f"Kind: {kind}", [(c,t) for c,t in paired if m["charts"][c]["kind"] == kind])
    lines += ["## Query use and limitations", ""]
    query_rows = [by[c,"record+query",t] for c,t in paired]
    histogram = {i: sum(r["query_turns"] == i for r in query_rows) for i in range(MAX_QUERIES+1)}
    unavailable = sum("unavailable" in q["response"] for r in query_rows for q in r["queries"])
    lines += [f"Query turns per cell (0..4): `{histogram}`. Unavailable responses: {unavailable}. "
              f"Reader generation seconds (one freeze pass): {sum(c['reader_s'] for c in m['charts'].values()):.6f}.", "",
              "No renderer, record or query implementation was changed. Query availability is limited: facts "
              "does not compute every aggregate and count_where requires records/explicit rows. Full records "
              "are not size-matched to sampled source tables; they may retain more point values. Unsupported "
              "artists remain unsupported. Tool requests are optional, not forced; arm accuracy alone cannot "
              "establish that the CLI caused an improvement. Replay inputs are charged in full; this protocol "
              "does not measure an optimized native-tool integration. Fixed source-derived questions favor "
              "lookups/counts/extrema, not open-ended analysis. One model, repeated shared charts, no "
              "statistical independence or general superiority claim. No summary rewrite or other-library "
              "reader is justified solely by a count comparison.", ""]
    (HERE / "RESULTS-suite3.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "smoke", "run", "report"])
    args = parser.parse_args()
    if args.action == "freeze":
        m = build()
        MANIFEST.write_text(json.dumps(m, indent=1, allow_nan=False) + "\n")
        print("Frozen", len(m["charts"]), "charts", old.digest(m))
        return
    m = load(verify_code=args.action != "report")
    if args.action == "report":
        report(m)
        return
    start, started = time.perf_counter(), utc()
    outcome = run(m, smoke=args.action == "smoke")
    append(DATA / "sessions.jsonl", dict(action=args.action, started_utc=started,
                                       elapsed_s=time.perf_counter()-start, outcome=outcome))
    report(m)
    if outcome != "complete":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
