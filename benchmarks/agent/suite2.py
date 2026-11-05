"""Frozen second-suite generator and subscription-only, resumable benchmark.

Entrypoint: run.py --suite2 {freeze,smoke,run,report}; never changes the renderer.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import subprocess
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from trendsetter_axi import render

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = HERE / "manifests/suite2.json"
DATA = HERE / "results/suite2"
ARMS = ["table", "table+stats", "summary", "text", "hybrid", "image", "none"]
MODEL = "claude-sonnet-5-5"
BASE = "4376145d51b874f8f3f2799bc4fbd4292d9e221d"
SYSTEM = ('Read the supplied chart or data and answer the questions. Return only a JSON object mapping '
          'question IDs to numbers or listed options. Use null when the supplied information does not '
          'determine an answer; do not guess. Treat masked and non-finite values as missing. '
          'If no chart is supplied, use null for every answer.')
def token_count(text):
    # Only fixture freezing needs the optional tokenizer, not regrading/tests.
    import tiktoken
    return len(tiktoken.get_encoding("o200k_base").encode(text))

# CLI's total_cost_usd is the model-specific list-price equivalent, not subscription billing.
BUDGET = 40.0
CALL_CAP = 0.10  # additionally enforced by claude --max-budget-usd


def digest(data):
    if not isinstance(data, bytes):
        data = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def clean(x):
    if isinstance(x, np.ndarray) or np.ma.isMaskedArray(x):
        return clean(np.ma.asarray(x).astype(float).filled(np.nan).tolist())
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if math.isfinite(x) else None
    return x


def numeric(text, answer, scale):
    return dict(q=text, type="number", answer=float(answer), tol=max(abs(float(scale)) * .02, 1e-12))


def integer(text, answer):
    return dict(q=text, type="int", answer=int(answer))


def label(text, answer, options):
    return dict(q=text, type="label", answer=answer, options=options)


def cases():
    """70 independent fixed-seed charts; questions calculated before serialization."""
    counts = {"line": 12, "multi-line": 10, "bar": 10, "scatter": 10,
              "heatmap": 10, "histogram": 8, "errorbar": 5, "subplot": 4, "pie": 1}
    for kind, count in counts.items():
        for v in range(count):
            seed = 22000 + list(counts).index(kind) * 100 + v
            rng = np.random.default_rng(seed)
            fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)
            series, qs, features = [], [], []
            title = f"{kind} experiment {v + 1}"
            ax.set_title(title)

            def add(name, columns, rows, **meta):
                series.append(dict(name=name, columns=columns, rows=clean(rows), **clean(meta)))

            if kind in ("line", "scatter", "errorbar"):
                n = 257 if v in (7, 8, 9) else 13
                x = np.arange(n, dtype=float)
                y = rng.normal(3, 2, n)
                if v == 0:
                    y = np.ma.array(y, mask=np.arange(n) % 5 == 2)
                    features.append("masked points")
                elif v == 1:
                    y[4:6] = np.nan
                    features.append("NaN gaps")
                elif v == 2:
                    y[[2, 9]] = 12
                    features.append("tied maxima")
                elif v == 3:
                    y[:] = 3.125
                    features.append("constant")
                elif v == 4:
                    y *= 1e-8
                    features.append("1e-8 magnitudes")
                elif v == 5:
                    y -= 15
                    features.append("negatives")
                elif v == 6:
                    y += 1e9
                    features.append("large offset")
                if kind == "line" and v == 10:
                    x = mdates.date2num(datetime(2025, 3, 1, tzinfo=timezone.utc)) + x / 86400
                    ax.xaxis_date()
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S", tz=timezone.utc))
                    features.append("timestamps seconds apart")
                aliases = None
                if kind == "line" and v == 11:
                    aliases = [f"slot-{i:02}" for i in range(n)]
                    ax.set_xticks(x, aliases, rotation=45)
                    features.append("explicit tick aliases")
                yc = np.ma.asarray(y).filled(np.nan)
                valid = np.isfinite(yc)
                good = yc[valid]
                span = np.ptp(good)
                if kind == "scatter":
                    ax.scatter(x, y, label="signal")
                elif kind == "errorbar":
                    err = np.abs(rng.normal(.4, .1, n)) * (1e-8 if v == 4 else 1)
                    ax.errorbar(x, y, yerr=err, label="signal", capsize=3)
                else:
                    ax.plot(x, y, marker="o" if n < 20 else None, label="signal")
                rows = [[float(xx), yy, *( [float(ee)] if kind == "errorbar" else [])]
                        for xx, yy, *rest in zip(x, clean(y), *([err] if kind == "errorbar" else []))
                        for ee in ([rest[0]] if rest else [0])]
                add("signal", ["x", "y"] + (["yerr"] if kind == "errorbar" else []), rows,
                    x_aliases=aliases, x_unit="matplotlib UTC days" if v == 10 and kind == "line" else "index")
                mid = int(np.flatnonzero(valid)[len(good) // 2])
                target = aliases[mid] if aliases else (f"UTC second {mid:02} after 2025-03-01T00:00:00Z" if "timestamps seconds apart" in features else f"x={mid}")
                qs = [numeric("What is the maximum finite y?", good.max(), span),
                      numeric(f"What is y at {target}?", yc[mid], span),
                      integer("How many observations have finite unmasked y?", valid.sum()),
                      integer("How many finite observations equal the maximum y (including ties)?", (good == good.max()).sum())]
                if kind == "errorbar":
                    qs[-1] = numeric(f"What is the upper errorbar endpoint at x={mid}?", yc[mid] + err[mid], span + np.max(err))
            elif kind == "multi-line":
                n = 129 if v >= 7 else 13
                x = np.arange(n)
                ys = rng.normal(0, 4, (2, n)).cumsum(axis=1)
                for name, y in zip(["Alpha", "Beta"], ys):
                    ax.plot(x, y, label=name)
                    add(name, ["x", "y"], np.column_stack((x, y)))
                ax.legend()
                mid = n // 2
                qs = [label(f"Which series is higher at x={mid}?", ["Alpha", "Beta"][int(ys[1, mid] > ys[0, mid])], ["Alpha", "Beta"]),
                      integer("At how many x positions is Alpha strictly above Beta?", (ys[0] > ys[1]).sum()),
                      numeric("What is the maximum Beta y?", ys[1].max(), np.ptp(ys)),
                      numeric(f"What is Alpha y at x={mid}?", ys[0, mid], np.ptp(ys))]
            elif kind == "bar":
                n = 55 if v >= 8 else 12
                names = [f"C{i:02}" for i in range(n)]
                y = rng.integers(-12, 25, n)
                if v == 2:
                    y[[1, 6]] = 30
                    features.append("ties")
                (ax.barh if v % 2 else ax.bar)(names, y)
                add("categories", ["category", "value"], list(zip(names, y.tolist())))
                qs = [integer("How many categories have negative values?", (y < 0).sum()),
                      numeric("What is the maximum category value?", y.max(), np.ptp(y)),
                      numeric("What is the value of C05?", y[5], np.ptp(y)),
                      integer("How many categories tie for the maximum value?", (y == y.max()).sum())]
            elif kind == "heatmap":
                shape = (32, 37) if v >= 5 else (5, 6)
                z = rng.integers(-8, 9, shape).astype(float)
                if v == 0 or v == 5:
                    z[:] = 0
                    z[2, 3] = 97
                    features.append("lone heatmap spike")
                if v == 1:
                    z = np.ma.array(z, mask=rng.random(shape) < .2)
                    features.append("masked cells")
                if v == 2:
                    z[1, 2] = np.nan
                    features.append("NaN cell")
                im = ax.imshow(z, aspect="auto")
                fig.colorbar(im)
                rows = [f"R{i:02}" for i in range(shape[0])]
                cols = [f"K{i:02}" for i in range(shape[1])]
                ax.set_yticks(range(shape[0]), rows)
                ax.set_xticks(range(shape[1]), cols, rotation=90)
                zz = np.ma.asarray(z).filled(np.nan)
                add("grid", ["row", "column", "value"], [[rows[i], cols[j], clean(zz[i, j])] for i in range(shape[0]) for j in range(shape[1])], shape=list(shape))
                ri, ci = np.argwhere(np.isfinite(zz))[0]
                qs = [numeric("What is the maximum finite cell value?", np.nanmax(zz), np.nanmax(zz) - np.nanmin(zz)),
                      numeric(f"What is the cell at row {rows[ri]} column {cols[ci]}?", zz[ri, ci], np.nanmax(zz) - np.nanmin(zz)),
                      integer("How many cells have finite unmasked values?", np.isfinite(zz).sum()),
                      integer("How many finite cells equal the maximum?", (zz == np.nanmax(zz)).sum())]
            elif kind == "histogram":
                values = rng.normal(v, 2, 900)
                counts_, edges = np.histogram(values, bins=16 if v < 6 else 80)
                ax.hist(values, bins=edges)
                add("bins", ["left", "right", "count"], np.column_stack((edges[:-1], edges[1:], counts_)))
                qs = [integer("What is the count in the tallest bin?", counts_.max()),
                      integer("How many observations are represented in total?", counts_.sum()),
                      integer("How many bins contain more than 30 observations?", (counts_ > 30).sum()),
                      integer("How many bins are plotted?", len(counts_))]
            elif kind == "subplot":
                plt.close(fig)
                fig, axes = plt.subplots(1, 2, figsize=(6.4, 4.8), dpi=100)
                ys = rng.integers(-10, 15, (2, 9))
                for i, axis in enumerate(axes):
                    axis.plot(np.arange(9), ys[i], marker="o")
                    axis.set_title(["Left", "Right"][i])
                    add(["Left", "Right"][i], ["x", "y"], np.column_stack((np.arange(9), ys[i])))
                qs = [numeric("What is the maximum y in the Left panel?", ys[0].max(), np.ptp(ys)),
                      numeric("What is y at x=4 in the Right panel?", ys[1, 4], np.ptp(ys)),
                      label("Which panel has the greater minimum y?", ["Left", "Right"][int(ys[1].min() > ys[0].min())], ["Left", "Right"]),
                      integer("How many points across both panels have negative y?", (ys < 0).sum())]
            else:
                names = ["Oak", "Pine", "Elm", "Ash"]
                y = rng.integers(3, 30, 4)
                ax.pie(y, labels=names, autopct="%.1f%%")
                add("slices", ["category", "value"], list(zip(names, y.tolist())))
                qs = [label("Which category has the largest slice?", names[y.argmax()], names),
                      numeric("What percentage belongs to Oak?", 100 * y[0] / y.sum(), 100),
                      label("Is Pine's slice larger than Elm's?", "yes" if y[1] > y[2] else "no", ["yes", "no"]),
                      integer("How many slices are plotted?", len(y))]
                features.append("unsupported Wedge")
            yield f"s2_{kind}_{v:02}", fig, dict(kind=kind, seed=seed, features=features, title=title,
                    series=series, questions={f"q{i}": q for i, q in enumerate(qs, 1)})
            plt.close(fig)


def stats(case):
    out = []
    for s in case["series"]:
        fields = {}
        for i, col in enumerate(s["columns"]):
            v = np.array([r[i] for r in s["rows"] if isinstance(r[i], (float, int))], dtype=float)
            if len(v):
                fields[col] = dict(n=len(v), min=float(v.min()), max=float(v.max()), mean=float(v.mean()),
                                   sum=float(v.sum()), negative=int((v < 0).sum()),
                                   max_ties=int((v == v.max()).sum()))
        out.append(dict(name=s["name"], rows=len(s["rows"]), columns=fields))
    if case["kind"] == "multi-line":
        a, b = [np.array([r[1] for r in s["rows"]]) for s in case["series"]]
        out.append(dict(comparison="Alpha > Beta", count=int((a > b).sum())))
    return json.dumps(out, separators=(",", ":"), allow_nan=False)


def table(case, k):
    parts = [case["title"], "Direct source data; null denotes missing. Sampling is not interpolation."]
    for s in case["series"]:
        n = len(s["rows"])
        indices = np.unique(np.linspace(0, n - 1, min(n, k), dtype=int)).tolist()
        parts.append(json.dumps(dict(**{key: value for key, value in s.items() if key != "rows"},
                                    total_rows=n, selected_indices=indices,
                                    rows=[s["rows"][i] for i in indices]), separators=(",", ":")))
    return "\n".join(parts)


def build():
    DATA.mkdir(parents=True, exist_ok=True)
    charts = {}
    for cid, fig, case in cases():
        start = time.perf_counter()
        r = render(fig, cols=80)
        text_s = time.perf_counter() - start
        start = time.perf_counter()
        summary = r.summary()
        summary_s = time.perf_counter() - start
        start = time.perf_counter()
        h = render(fig, cols=60, ascii=True, rows=12)
        hybrid = h.text + "\n\n" + h.summary()
        hybrid_s = time.perf_counter() - start
        start = time.perf_counter()
        png = DATA / f"{cid}.png"
        fig.savefig(png, dpi=100, metadata={"Software": None})
        image_s = time.perf_counter() - start
        k = max(len(s["rows"]) for s in case["series"])
        target = max(256, token_count(summary))
        if k > 64:
            # Fixed, outcome-blind rule: maximize deterministic uniform rows within
            # the summary's o200k budget (256-token floor). No extrema injection.
            lo, hi = 1, k
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if token_count(table(case, mid)) <= target:
                    lo = mid
                else:
                    hi = mid - 1
            k = lo
        raw = table(case, k)
        texts = {"table": raw, "table+stats": raw + "\nFull-source statistics:\n" + stats(case),
                 "summary": summary, "text": r.text, "hybrid": hybrid, "none": "No chart or data supplied."}
        stimuli = {}
        for arm, content in texts.items():
            path = DATA / f"{cid}.{arm}.txt"
            path.write_text(content)
            stimuli[arm] = dict(file=path.name, sha256=digest(path.read_bytes()), o200k=token_count(content))
        stimuli["image"] = dict(file=png.name, sha256=digest(png.read_bytes()), pixels=[640, 480])
        charts[cid] = dict(**case, stimuli=stimuli, table_rows_per_series=k, table_target_o200k=target,
                           renderer_s=dict(text=text_s, summary=summary_s, hybrid=hybrid_s, image=image_s))
    return dict(schema=2, renderer_commit=BASE, model=MODEL, arms=ARMS, trials=[1, 2, 3],
                system=SYSTEM, effort="low", success="summary correct >= table+stats correct - 2 per trial (and pooled -6), and pooled total input tokens <= 40% of table+stats; otherwise narrow claim to hybrid and preview",
                budget_usd=BUDGET, call_cap_usd=CALL_CAP, charts=charts,
                environment=dict(python=os.sys.version.split()[0], matplotlib=matplotlib.__version__, numpy=np.__version__))


def load():
    m = json.loads(MANIFEST.read_text())
    if (m["system"], m["model"], m["arms"], m["effort"], m["renderer_commit"]) != (SYSTEM, MODEL, ARMS, "low", BASE):
        raise RuntimeError("Protocol differs from frozen manifest")
    for cid, c in m["charts"].items():
        for arm, stimulus in c["stimuli"].items():
            if digest((DATA / stimulus["file"]).read_bytes()) != stimulus["sha256"]:
                raise RuntimeError(f"Frozen stimulus changed: {cid} {arm}")
    for path in (ROOT / "src").rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        original = subprocess.check_output(["git", "show", f"{BASE}:{rel}"], cwd=ROOT)
        if path.read_bytes() != original:
            raise RuntimeError(f"Renderer changed since freeze: {rel}")
    return m


def asks(case):
    return "\n".join(f"{qid}: {q['q']}" + (f" Options: {q['options']}" if "options" in q else "") for qid, q in case["questions"].items())


def child_env():
    env = os.environ.copy()
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(key, None)
    # Never route through a third-party provider or a custom API endpoint.
    for key in list(env):
        if key.startswith("CLAUDE_CODE_USE_") or key == "ANTHROPIC_BASE_URL":
            env.pop(key, None)
    return env


def call(m, cid, arm, trial):
    c = m["charts"][cid]
    s = c["stimuli"][arm]
    path = DATA / s["file"]
    content = []
    if arm == "image":
        content.append(dict(type="image", source=dict(type="base64", media_type="image/png", data=base64.b64encode(path.read_bytes()).decode())))
        text = "Attached chart."
    else:
        text = path.read_text()
    content.append(dict(type="text", text=text + "\n\nQuestions:\n" + asks(c)))
    cmd = ["claude", "-p", "--model", MODEL, "--safe-mode", "--tools", "", "--strict-mcp-config",
           "--mcp-config", '{"mcpServers":{}}', "--setting-sources", "", "--disable-slash-commands",
           "--no-session-persistence", "--no-chrome", "--effort", "low", "--max-budget-usd", str(CALL_CAP),
           "--system-prompt", SYSTEM, "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
    start = time.perf_counter()
    started_utc = datetime.now(timezone.utc).isoformat()
    try:
        p = subprocess.run(cmd, input=json.dumps(dict(type="user", message=dict(role="user", content=content))) + "\n",
                           capture_output=True, text=True, env=child_env(), timeout=300, cwd=DATA)
        events = []
        for line in p.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        final = next((e for e in reversed(events) if e.get("type") == "result"), {})
        auth = [e.get("apiKeySource") for e in events if "apiKeySource" in e]
        raw = (p.stdout + "\n" + p.stderr)
        api_auth = any(str(a).lower() not in ("none", "null", "", "claude.ai", "oauth") for a in auth)
        api_auth |= bool(re.search(r'using api.?key|api.?key auth|"apiKeySource"\s*:\s*"(?:env|api)', raw, re.I))
        actual_models = set(final.get("modelUsage", {}))
        error = final.get("is_error", not bool(final)) or p.returncode != 0 or actual_models != {MODEL}
        usage = final.get("usage", {})
        tokens = sum(usage.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        cost = final.get("total_cost_usd")
        # Unknown-cost failures reserve the entire per-call allowance, never zero.
        charge = CALL_CAP if cost is None else float(cost)
        return dict(chart=cid, arm=arm, trial=trial, model=MODEL, manifest_sha256=digest(m), stimulus_sha256=s["sha256"],
                    started_utc=started_utc, wall_s=time.perf_counter() - start,
                    input_tokens=tokens, output_tokens=usage.get("output_tokens", 0), usage=usage,
                    list_price_usd=charge, cli_reported_usd=cost, auth_sources=auth, api_key_auth=api_auth,
                    is_error=bool(error or api_auth), reply=final.get("result", ""), final=final,
                    diagnostic=raw if error or api_auth else "", returncode=p.returncode)
    except subprocess.TimeoutExpired as e:
        return dict(chart=cid, arm=arm, trial=trial, model=MODEL, manifest_sha256=digest(m), is_error=True,
                    list_price_usd=CALL_CAP, reply="", diagnostic="CLI timeout after 300s", wall_s=time.perf_counter()-start)


def rows():
    path = DATA / "calls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def journal_batch(batch):
    """Persist reservations before dispatch so a killed parent cannot lose spend."""
    pending = [dict(chart=c, arm=a, trial=t, attempt_id=f"{time.time_ns()}-{i}")
               for i, (c, a, t) in enumerate(batch)]
    path = DATA / "pending.json"
    temporary = DATA / "pending.tmp"
    with temporary.open("w") as f:
        json.dump(pending, f)
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(path)
    return pending


def recover_pending(m):
    path = DATA / "pending.json"
    if not path.exists():
        return
    completed = {r.get("attempt_id") for r in rows()}
    with (DATA / "calls.jsonl").open("a") as f:
        for attempt in json.loads(path.read_text()):
            if attempt["attempt_id"] not in completed:
                f.write(json.dumps(dict(**attempt, model=MODEL, manifest_sha256=digest(m),
                    is_error=True, list_price_usd=CALL_CAP, wall_s=0, wall_unknown=True,
                    reply="", diagnostic="Parent interrupted; cost reserved before dispatch, actual usage unknown.")) + "\n")
                f.flush()
                os.fsync(f.fileno())
    path.unlink()


def run(m, smoke=False):
    recover_pending(m)
    previous = rows()
    if any(r.get("api_key_auth") for r in previous):
        raise RuntimeError("API-key auth was reported; run is stopped")
    good = {(r["chart"], r["arm"], r["trial"]) for r in previous if not r["is_error"] and r["manifest_sha256"] == digest(m)}
    # Five smoke charts span line, scatter, bar, heatmap, errorbar. Smoke calls
    # are trial 1 of the full run, not an unreported extra trial.
    smoke_ids = ["s2_line_00", "s2_scatter_04", "s2_bar_02", "s2_heatmap_05", "s2_errorbar_01"]
    jobs = []
    for trial in m["trials"]:
        ids = smoke_ids if smoke else list(m["charts"])
        random.Random(9100 + trial).shuffle(ids)
        for cid in ids:
            arms = ARMS.copy()
            random.Random(f"{trial}:{cid}").shuffle(arms)
            for arm in arms:
                if (cid, arm, trial) not in good:
                    jobs.append((cid, arm, trial))
        if smoke:
            break
    spent = sum(r["list_price_usd"] for r in previous)
    with ThreadPoolExecutor(max_workers=4) as executor, (DATA / "calls.jsonl").open("a") as f:
        for offset in range(0, len(jobs), 4):
            batch = jobs[offset:offset+4]
            if spent + len(batch) * CALL_CAP > BUDGET:
                print(f"PAUSED budget: ${spent:.4f}; next batch reserve exceeds $40", flush=True)
                return "budget"
            pending = journal_batch(batch)
            futures = {executor.submit(call, m, *job): attempt for job, attempt in zip(batch, pending)}
            stop = False
            for future in as_completed(futures):
                row = future.result()
                row["attempt_id"] = futures[future]["attempt_id"]
                f.write(json.dumps(row, allow_nan=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
                spent += row["list_price_usd"]
                print(row["chart"], row["arm"], row["trial"], "ERROR" if row["is_error"] else "ok", f"${spent:.4f}", flush=True)
                if row["is_error"]:
                    print(row.get("diagnostic", "")[-2500:], flush=True)
                    stop = True
            (DATA / "pending.json").unlink()
            if stop:
                return "error"
    return "complete"


def parsed(reply):
    result = {}
    for i, ch in enumerate(reply):
        if ch == "{":
            try:
                obj, _ = json.JSONDecoder().raw_decode(reply[i:])
                if isinstance(obj, dict):
                    result = obj
            except json.JSONDecodeError:
                pass
    return result


def score(q, answer):
    if answer is None:
        return False, True, None
    if q["type"] == "label":
        return str(answer).strip().casefold() == str(q["answer"]).casefold(), False, None
    if isinstance(answer, bool) or not isinstance(answer, (int, float)) or not math.isfinite(answer):
        return False, False, None
    error = abs(answer - q["answer"])
    return error <= q.get("tol", 0), False, error / max(abs(q["answer"]), q.get("tol", 1e-12), 1e-12)


def report(m, path=None):
    allrows = rows()
    by = {(r["chart"], r["arm"], r["trial"]): r for r in allrows if not r["is_error"] and r["manifest_sha256"] == digest(m)}
    paired = [(cid, t) for cid in m["charts"] for t in m["trials"] if all((cid, a, t) in by for a in ARMS)]
    session_path = DATA / "sessions.jsonl"
    sessions = [json.loads(line) for line in session_path.read_text().splitlines()] if session_path.exists() else []
    lines = ["# Suite2 benchmark results", "", f"Frozen renderer `{BASE}`. Model `{MODEL}`; subscription CLI, effort low.", "",
             f"Manifest SHA-256: `{digest(m)}`. Planned: 70 charts × 4 questions × 3 trials × 7 arms = 1,470 calls / 5,880 answers.",
             f"Observed: {len(allrows)} attempts, {len(by)} successful cells, {sum(r['is_error'] for r in allrows)} errors. "
             f"Complete paired chart-trials: {len(paired)}/210 ({len(set(c for c,t in paired))}/70 distinct charts).",
             f"List-price accounting (all attempts): ${sum(r['list_price_usd'] for r in allrows):.6f}, including "
             f"${sum(r.get('cli_reported_usd') or 0 for r in allrows):.6f} reported by CLI and "
             f"${sum(r['list_price_usd'] for r in allrows if r.get('cli_reported_usd') is None):.6f} reserved for unknown-cost interruptions. "
             "No API keys used; these are not subscription billing measurements.",
             f"Measured child wall seconds, summed (parallel, not elapsed): {sum(r['wall_s'] for r in allrows):.3f}; "
             f"{sum(r.get('wall_unknown', False) for r in allrows)} interrupted attempt(s) have unknown duration and are excluded. "
             f"Recorded runner wall seconds (sum of sessions, excluding external reset waits): {sum(s['elapsed_s'] for s in sessions):.3f}. "
             "The interrupted full-run session contributes its 3,600-second parent timeout allowance, not an exact end-to-end measurement.", "",
             "Only chart-trials complete in all seven arms enter comparative cells; incomplete successes remain in raw JSONL. "
             "Numeric error is mean |answer−truth| / max(|truth|, tolerance, 1e-12), finite numeric replies only; "
             "abstention includes null/missing answers. Invalid replies count wrong, not numeric error.", ""]

    def metrics(arm, selected):
        correct = abstain = n = inp = out = 0
        errors = []
        abs_errors = []
        wall = 0
        for cid, trial in selected:
            row = by[cid, arm, trial]
            answers = parsed(row["reply"])
            inp += row["input_tokens"]
            out += row["output_tokens"]
            wall += row["wall_s"]
            for qid, q in m["charts"][cid]["questions"].items():
                ok, ab, err = score(q, answers.get(qid))
                correct += ok
                abstain += ab
                n += 1
                if err is not None:
                    errors.append(err)
                    abs_errors.append(abs(answers[qid] - q["answer"]))
        return correct, n, abstain, inp, out, wall, errors, abs_errors

    def section(title, selected):
        lines.extend([f"## {title}", "", "| arm | correct / questions | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |",
                      "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
        for arm in ARMS:
            ok, n, ab, inp, out, wall, err, ae = metrics(arm, selected)
            lines.append(f"| {arm} | {ok}/{n} | {ab} | {inp} | {out} | {wall:.3f} | {len(err)} | " + (f"{np.mean(err):.6g} | {np.mean(ae):.6g} |" if err else "— | — |"))
        lines.append("")

    section("Pooled paired results", paired)
    complete = len(paired) == 210
    summary = metrics("summary", paired)
    table_stats = metrics("table+stats", paired)
    trial_ok = all(metrics("summary", [(c,t) for c,t in paired if t == trial])[0] >= metrics("table+stats", [(c,t) for c,t in paired if t == trial])[0] - 2 for trial in m["trials"])
    passed = complete and trial_ok and summary[0] >= table_stats[0] - 6 and summary[3] <= .4 * table_stats[3]
    lines += ["## Predeclared criterion", "", f"Outcome: **{'PASS' if passed else 'FAIL' if complete else 'NOT EVALUABLE — incomplete run'}**. "
              "Summary must be within 2 correct answers of table+stats in every trial (pooled deficit ≤6), "
              "using ≤40% of its total input tokens. No renderer tuning used this suite.", ""]
    if paired:
        ratio = summary[3] / table_stats[3]
        none = metrics("none", paired)
        lines += [f"Summary deficit: {table_stats[0]-summary[0]} answers pooled. Total-input ratio: {100*ratio:.3f}%. "
                  f"Descriptive chart-only tokens (input minus paired none): summary {summary[3]-none[3]}, "
                  f"table+stats {table_stats[3]-none[3]}. Chart-only token ratio is not the predeclared criterion. "
                  "The accuracy criterion fails regardless of whether common prompt overhead is subtracted.", ""]
    for trial in m["trials"]:
        section(f"Trial {trial}", [(c,t) for c,t in paired if t == trial])
    for kind in dict.fromkeys(c["kind"] for c in m["charts"].values()):
        section(f"Kind: {kind}", [(c,t) for c,t in paired if m["charts"][c]["kind"] == kind])
    lines += ["## Fixture generation timing (single pass, seconds)", "", "| kind | charts | render 80 | summary only | hybrid render+summary | PNG |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for kind in dict.fromkeys(c["kind"] for c in m["charts"].values()):
        cs = [c for c in m["charts"].values() if c["kind"] == kind]
        lines.append(f"| {kind} | {len(cs)} | " + " | ".join(f"{sum(c['renderer_s'][a] for c in cs):.6f}" for a in ["text", "summary", "hybrid", "image"]) + " |")
    lines += ["", "## Historical pilot (not rerun; not comparable)", "", "| tag | split | summary | hybrid | image | text | mpl_ascii | plotext | median summary / hybrid / image input chart tokens |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
              "| after @ 9288d2b | dev, 25 charts | 79/81 | 78/81 | 80/81 | 66/81 | 63/81 | 59/81 | 102 / 316 / 408 |",
              "| after @ 9288d2b | held-out, 12 charts | 37/39 | 39/39 | 39/39 | 35/39 | 28/39 | 22/39 | 114 / 326 / 408 |", "",
              "Historical detail and original raw records remain in `results.jsonl`; see `RESULTS-historical.md`.", "",
              "## Interpretation and limits", "",
              "The summary claim fails; the hybrid and human preview remain available, without a superiority claim. "
              "Direct table+stats is most accurate here; hybrid is below PNG. Repeated trials share charts and are not 840 independent charts. "
              "Questions emphasize source extrema, exact counts, missingness and point values, not open-ended analysis. Full-source stats directly support several question types. "
              "Large tables are intentionally sampled, not a full-data oracle; table+stats retains full-source aggregate statistics. "
              "Uniform source sampling can omit the queried point or heatmap spike. The 256-token metadata floor can exceed a small summary's size. "
              "This suite covers the listed kinds, not every supported artist combination (e.g. filled areas), SVG, other models or image sizes. "
              "Numeric MAE mixes units and large offsets; use per-kind relative errors and abstention counts too. "
              "Trial 3 reused input caches: costs reflect CLI list-price cache rates, while input-token totals count cached tokens in full. "
              "One parent timeout interrupted a single in-flight call; its unobservable cost is reserved at $0.10 and its retry is recorded. "
              "No subscription-limit or API-auth failure was reported.", ""]
    (path or HERE / "RESULTS.md").write_text("\n".join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["freeze", "smoke", "run", "report"])
    args = parser.parse_args(argv)
    if args.action == "freeze":
        if MANIFEST.exists():
            raise RuntimeError("Manifest already frozen; refusing overwrite")
        m = build()
        MANIFEST.parent.mkdir(exist_ok=True)
        MANIFEST.write_text(json.dumps(m, indent=1, allow_nan=False) + "\n")
        print("Frozen", len(m["charts"]), "charts; manifest", digest(m))
    else:
        m = load()
        if args.action in ("smoke", "run"):
            start = time.perf_counter()
            started = datetime.now(timezone.utc).isoformat()
            result = run(m, smoke=args.action == "smoke")
            with (DATA / "sessions.jsonl").open("a") as f:
                f.write(json.dumps(dict(action=args.action, started_utc=started,
                                       elapsed_s=time.perf_counter()-start, outcome=result)) + "\n")
                f.flush()
                os.fsync(f.fileno())
            report(m)
            if result != "complete":
                raise SystemExit(2)
        else:
            report(m)


if __name__ == "__main__":
    main()
