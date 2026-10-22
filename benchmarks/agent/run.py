"""Same questions, six ways to see the chart: render() text at 80 columns, RenderResult.summary(), a PNG, the text that
mpl_ascii and plotext make from the same figure, and nothing (a guessing baseline).

Run from repo root:
    PYTHONPATH=src python benchmarks/agent/run.py --tag after                  # build fixtures, ask the model (resumes), write RESULTS.md
    PYTHONPATH=src python benchmarks/agent/run.py --tag after --split heldout  # the held-out charts (heldout.py)
    PYTHONPATH=src python benchmarks/agent/run.py --no-ask                     # rebuild fixtures, regrade results.jsonl into RESULTS.md

Every row in results.jsonl carries a tag (a renderer version or a tuning round), the questions it asked and a hash of the
chart it showed. A row is reused, under the new tag and marked `reused_from`, when the same chart was already shown with the
same questions, so formats the renderer does not touch (image, mpl_ascii, plotext, none) are asked once.

Model calls go through the locally logged-in `claude -p` CLI: one call per chart and format, all of a chart's questions in
that call, no tools, no MCP servers, no settings files, a short fixed system prompt. Building the fixtures needs tiktoken,
mpl_ascii and plotext: `uv pip install tiktoken mpl_ascii==1.0.1 plotext==6.1.0`.
"""
import argparse
import base64
import hashlib
import json
import re
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
from charts import CHARTS  # noqa: E402
from heldout import HELDOUT  # noqa: E402
from trendsetter_axi import render  # noqa: E402

HERE = Path(__file__).parent
COLS, DPI = 80, 100
FIXTURES, OUT = HERE / "fixtures", HERE / "out"
RESULTS, REPORT = HERE / "results.jsonl", HERE / "RESULTS.md"
FORMATS = ["none", "text", "summary", "image", "mpl_ascii", "plotext"]
TEXTS = {"text": "txt", "summary": "summary.txt", "ascii": "ascii.txt", "ascii_tall": "ascii_tall.txt", "hybrid": "hybrid.txt",
         "mpl_ascii": "mpl_ascii.txt", "plotext": "plotext.txt"}   # fixture suffix per text format
ASCII = dict(cols=COLS, ascii=True, rows=16)       # the token-lean chart for a model
HYBRID = dict(cols=60, ascii=True, rows=12)       # a small chart, then its summary
HYBRID_DOC = ("`render(fig, 60, ascii=True, rows=12)` text then that result's `summary()`; `ascii` = `render(fig, 80, ascii=True, rows=16).text`; "
              "`ascii_tall` = `render(fig, 80, ascii=True).text` (default height)")
ENV = "matplotlib {matplotlib}, Python {python}, {cli}"   # where a row was asked, as RESULTS.md reports it
SPLITS = {"dev": (CHARTS, HERE / "questions.json"), "heldout": (HELDOUT, HERE / "questions-heldout.json")}
TAGS = ["before", "after"]   # what RESULTS.md compares: before = the renderer at c1f6de5, after = this one
SYSTEM = ("You read charts and answer questions about them. Reply with only a JSON object mapping each question id to its "
          "answer: a number, or one of the listed options. No prose, no code fences.")


def build(split):
    """Render every chart each way; write the text fixtures, the answer key and the PNGs (PNGs are not committed)."""
    import plotext
    import tiktoken
    from mpl_ascii import FigureCanvasAscii

    def via_plotext(fig):
        f = plotext.matplotlib(fig)
        f.plot_size(COLS, 30)
        return f.build().string(colorless=True)

    others = dict(plotext=via_plotext, mpl_ascii=lambda fig: str(FigureCanvasAscii(fig).draw_canvas()))   # mpl_ascii last: it swaps the canvas
    FIXTURES.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    enc = tiktoken.get_encoding("o200k_base")
    key = {}
    charts, path = SPLITS[split]
    for cid, (kind, make) in charts.items():
        fig, questions = make()
        r = render(fig, cols=COLS)
        fig.savefig(OUT / f"{cid}.png", dpi=DPI, metadata={"Software": None})
        w, h = (round(v * DPI) for v in fig.get_size_inches())
        rh = render(fig, **HYBRID)
        texts = dict(text=r.text, summary=r.summary(), ascii=render(fig, **ASCII).text, ascii_tall=render(fig, COLS, ascii=True).text, hybrid=f"{rh.text}\n\n{rh.summary()}")
        for name, draw in others.items():
            try:
                texts[name] = draw(fig)
            except Exception as e:   # the model then gets the error, i.e. no chart
                texts[name] = f"({name} failed on this figure: {type(e).__name__}: {e})"
        plt.close(fig)
        for fmt, suffix in TEXTS.items():
            (FIXTURES / f"{cid}.{suffix}").write_text(texts[fmt] + "\n")
        key[cid] = dict(kind=kind, png=[w, h], o200k={fmt: len(enc.encode(t)) for fmt, t in texts.items()},
                        losses=[l for l in r.losses if l["material"]],
                        questions={f"q{i}": q for i, q in enumerate(questions, 1)})
    path.write_text(json.dumps(key, indent=1) + "\n")
    return key


def shown(cid, fmt):
    """Hash of the chart a call shows, so a row answers for exactly this fixture."""
    data = (FIXTURES / f"{cid}.{TEXTS[fmt]}").read_bytes() if fmt in TEXTS else (OUT / f"{cid}.png").read_bytes() if fmt == "image" else b""
    return hashlib.sha256(data).hexdigest()[:16]


def asks(questions):
    return "\n".join(f"{qid}: {q['q']}" + (f" (one of: {', '.join(q['options'])})" if q.get("options") else "")
                       for qid, q in questions.items())


def prompt(cid, fmt, questions):
    content = []
    if fmt in TEXTS:
        title = {"summary": "Chart summary", "hybrid": "Chart, rendered as terminal text, then its data summary"}.get(fmt, "Chart, rendered as terminal text")
        head = f"{title}:\n```\n{(FIXTURES / f'{cid}.{TEXTS[fmt]}').read_text()}```"
    elif fmt == "image":
        data = base64.b64encode((OUT / f"{cid}.png").read_bytes()).decode()
        content.append(dict(type="image", source=dict(type="base64", media_type="image/png", data=data)))
        head = "Chart: the attached image."
    else:
        head = "No chart is attached. Give your best guess for each answer."
    content.append(dict(type="text", text=f"{head}\n\nQuestions:\n{asks(questions)}"))
    return dict(type="user", message=dict(role="user", content=content))


def ask(model, cid, fmt, questions, env, tag):
    cmd = ["claude", "-p", "--model", model, "--tools", "", "--strict-mcp-config", "--setting-sources", "",
           "--no-session-persistence", "--system-prompt", SYSTEM,
           "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
    start = time.perf_counter()
    out = subprocess.run(cmd, input=json.dumps(prompt(cid, fmt, questions)) + "\n", capture_output=True, text=True, timeout=300)
    wall = time.perf_counter() - start
    final = json.loads(out.stdout.strip().splitlines()[-1])
    u = final["usage"]
    return dict(chart=cid, format=fmt, model=model, reply=final.get("result", ""), is_error=final.get("is_error"),
                input_tokens=u["input_tokens"] + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"],
                output_tokens=u["output_tokens"], duration_ms=final["duration_ms"], duration_api_ms=final["duration_api_ms"],
                wall_s=round(wall, 3), cost_usd=final.get("total_cost_usd"), asked=asks(questions), **env, tag=tag, shown=shown(cid, fmt))


def parse(reply):
    """The last JSON object in the reply: a model that corrects itself repeats the object with the fix."""
    found, dec = {}, json.JSONDecoder()
    for i in (i for i, ch in enumerate(reply) if ch == "{"):
        try:
            obj, _ = dec.raw_decode(reply, i)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            found = obj
    return found


def grade(q, given):
    """True when `given` is right for question `q` (see charts.py for the types)."""
    if given is None:
        return False
    if q["type"] == "label":
        norm = lambda s: re.sub(r"\s+", "", str(s)).lower()  # noqa: E731
        return norm(given) == norm(q["answer"])
    try:
        v = float(re.sub(r"[^0-9eE.+-]", "", str(given)))
    except ValueError:
        return False
    return v == q["answer"] if q["type"] == "int" else abs(v - q["answer"]) <= q["tol"]


def rows():
    return [json.loads(line) for line in RESULTS.read_text().splitlines()] if RESULTS.exists() else []


def load(key, tag):
    """The last usable row per (chart, format, model) under `tag`: asked this answer key's questions and not an error."""
    return {(r["chart"], r["format"], r["model"]): r for r in rows()
            if r["tag"] == tag and r["chart"] in key and r.get("asked") == asks(key[r["chart"]]["questions"]) and not r["is_error"]}


def scored(key, model, tag):
    """Rows of one tag by (chart, format), each question graded, and the charts every reported format covers."""
    by = {(c, f): r for (c, f, m), r in load(key, tag).items() if m == model}
    fmts = [f for f in dict.fromkeys(FORMATS + sorted({f for _, f in by})) if f == "none" or any((c, f) in by for c in key)]
    charts = [c for c in key if all((c, f) in by for f in fmts)]
    score = {(c, f): [grade(q, parse(r["reply"]).get(qid)) for qid, q in key[c]["questions"].items()] for (c, f), r in by.items()}
    return by, score, [f for f in fmts if f != "none"] + ["none"], charts


def acc(cells):
    flat = [ok for c in cells for ok in c]
    return f"{sum(flat)}/{len(flat)} ({100 * sum(flat) / len(flat):.0f}%)" if flat else "-"


def section(split, key, model, tag):
    """The detailed tables for one split under one tag."""
    by, score, shown, charts = scored(key, model, tag)
    if not charts:
        return []

    def chart_tokens(cid, fmt):  # what the chart itself cost: this call's input minus the same call with no chart
        return by[cid, fmt]["input_tokens"] - by[cid, "none"]["input_tokens"]

    def said(c, fmt, qid):
        return parse(by[c, fmt]["reply"]).get(qid)

    def answer(q):
        return f"{q['answer']}" + (f" ± {q['tol']}" if q["type"] == "number" else "")

    calls = [by[c, f] for c in charts for f in shown]
    fresh = [r for r in calls if not r.get("reused_from")]
    failed = {n: [c for c in charts if (FIXTURES / f"{c}.{n}.txt").read_text().startswith(f"({n} failed")] for n in ("mpl_ascii", "plotext")}
    L = [f"## {split} split, `{tag}`: {sum(len(key[c]['questions']) for c in charts)} questions on {len(charts)} charts", "",
         f"{len(calls)} calls, {len(fresh)} made for this tag and {len(calls) - len(fresh)} reused from an identical earlier call "
         f"(same chart shown, same questions). Cost of those made for it: ${sum(r['cost_usd'] or 0 for r in fresh):.2f}.",
         *(f"{n} raised on {len(cs)} chart(s) ({', '.join(f'`{c}`' for c in cs)}); that call got the error in place of a chart."
           for n, cs in failed.items() if cs),
         "", "| format | accuracy | chart tokens, median (Claude) | chart tokens, total (Claude) | o200k median | output tokens, median | wall s, median | API s, median |",
         "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for fmt in shown:
        tok = [chart_tokens(c, fmt) for c in charts] if fmt != "none" else [0]
        o2 = statistics.median(key[c]["o200k"][fmt] for c in charts) if fmt in key[charts[0]]["o200k"] else "-"
        L.append(f"| {fmt} | {acc([score[c, fmt] for c in charts])} | {statistics.median(tok):.0f} | {sum(tok)} | {o2} | "
                 f"{statistics.median(by[c, fmt]['output_tokens'] for c in charts):.0f} | "
                 f"{statistics.median(by[c, fmt]['wall_s'] for c in charts):.1f} | "
                 f"{statistics.median(by[c, fmt]['duration_api_ms'] / 1000 for c in charts):.1f} |")
    kinds = defaultdict(list)
    for c in charts:
        kinds[key[c]["kind"]].append(c)
    L += ["", "Accuracy by chart kind:", "", "| kind | charts | " + " | ".join(shown) + " |", "| --- | ---: |" + " ---: |" * len(shown)]
    for kind, cs in kinds.items():
        L.append(f"| {kind} | {len(cs)} | " + " | ".join(acc([score[c, f] for c in cs]) for f in shown) + " |")
    L += ["", "Per chart: chart tokens (Claude, from the API), o200k in brackets for text formats; then right answers per format.", "",
          "| chart | kind | " + " | ".join(f"tokens {f}" for f in shown[:-1]) + " | " + " | ".join(shown) + " |",
          "| --- | --- |" + " ---: |" * (2 * len(shown) - 1)]
    for c in charts:
        toks = [f"{chart_tokens(c, f)}" + (f" ({key[c]['o200k'][f]})" if f in key[c]["o200k"] else "") for f in shown[:-1]]
        L.append(f"| `{c}` | {key[c]['kind']} | " + " | ".join(toks) + " | "
                 + " | ".join(f"{sum(score[c, f])}/{len(score[c, f])}" for f in shown) + " |")
    for fmt in [f for f in shown if f in ("text", "summary", "ascii", "ascii_tall", "hybrid")]:
        L += ["", f"Wrong with `{fmt}`:", ""]
        hits = [(c, qid, q) for c in charts for i, (qid, q) in enumerate(key[c]["questions"].items()) if not score[c, fmt][i]]
        L += [f"- `{c}` {qid}: {q['q']} answer {answer(q)}; {fmt} {said(c, fmt, qid)!r}, image {said(c, 'image', qid)!r}"
              for c, qid, q in hits] or ["- none"]
    return L + [""]


def write_report(model):
    keys = {split: json.loads(path.read_text()) for split, (_, path) in SPLITS.items() if path.exists()}
    every = [r for r in rows() if r["model"] == model]
    w, h = next(iter(keys["dev"].values()))["png"]
    L = ["# Agent chart-reading benchmark: results", "",
         "Generated by `run.py` from `results.jsonl`; method and reading in [README.md](README.md).", "",
         f"- model `{model}` via `claude -p`, one call per chart and format with all of that chart's questions, one run per tag, no repeats",
         "- formats: `text` = `render(fig, cols=80).text`, `summary` = `RenderResult.summary()`, `image` = PNG, `mpl_ascii` and "
         "`plotext` = those packages' text from the same figure, `none` = no chart, `hybrid` = " + HYBRID_DOC,
         f"- tags: `before` = the renderer at c1f6de5 (the first benchmark), `after` = this renderer; the dev split (`charts.py`) "
         "was used to tune `after`, the held-out split (`heldout.py`) was written before any change and only checked",
         f"- PNG {w}×{h} px (matplotlib default 6.4×4.8 in, {DPI} dpi); Anthropic's documented estimate width×height/750 = "
         f"{w * h / 750:.0f} tokens; tables use the API's count",
         "- chart tokens: the call's input tokens as the API reports them (Claude tokenizer), minus the same chart's `none` call; "
         "output tokens include the model's hidden reasoning (the replies are a short JSON object)", "",
         "## Before and after", ""]
    for split, key in keys.items():
        res = {t: scored(key, model, t) for t in TAGS}
        fmts = [f for f in dict.fromkeys(res["before"][2] + res["after"][2])]
        L += [f"{split} split:", "", "| format | accuracy before | accuracy after | chart tokens before | chart tokens after | output tokens before | output tokens after |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for f in fmts:
            cells = []
            for metric in ("acc", "tok", "out"):
                for t in TAGS:
                    by, score, _, charts = res[t]
                    if f not in res[t][2] or not charts:
                        cells.append("-"); continue
                    if metric == "acc": cells.append(acc([score[c, f] for c in charts]))
                    elif metric == "tok": cells.append("0" if f == "none" else f"{statistics.median(by[c, f]['input_tokens'] - by[c, 'none']['input_tokens'] for c in charts):.0f}")
                    else: cells.append(f"{statistics.median(by[c, f]['output_tokens'] for c in charts):.0f}")
            L.append(f"| {f} | " + " | ".join(cells) + " |")
        L.append("")
    for split, key in keys.items():
        for t in TAGS:
            L += section(split, key, model, t) if t == "after" or not scored(key, model, "after")[3] else []
    L += [f"Cost reported by the CLI, every call in results.jsonl including tuning rounds: ${sum(r['cost_usd'] or 0 for r in every if not r.get('reused_from')):.2f}. "
          f"Environment: {'; '.join(sorted({ENV.format(**r) for r in every}))}.", ""]
    REPORT.write_text("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--tag", default="after")
    ap.add_argument("--split", choices=list(SPLITS), default="dev")
    ap.add_argument("--formats", default=",".join(FORMATS), help="comma-separated; none is always asked (it is the token baseline)")
    ap.add_argument("--no-ask", action="store_true")
    args = ap.parse_args()
    key = build(args.split)
    if not args.no_ask:
        fmts = ["none"] + [f for f in args.formats.split(",") if f != "none"]
        done, old = load(key, args.tag), [r for r in rows() if r["model"] == args.model and not r["is_error"]]
        env = dict(cli=subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip(),
                   matplotlib=matplotlib.__version__, python=sys.version.split()[0])
        with RESULTS.open("a") as f:
            for cid, k in key.items():
                for fmt in fmts:   # interleaved per chart, so drift over the run hits every format alike
                    now, asked = shown(cid, fmt), asks(k["questions"])
                    if (cid, fmt, args.model) in done and done[cid, fmt, args.model]["shown"] == now:
                        continue
                    prior = next((r for r in reversed(old) if (r["chart"], r["format"], r.get("shown"), r.get("asked")) == (cid, fmt, now, asked)), None)
                    r = dict(prior, tag=args.tag, reused_from=prior.get("reused_from") or prior["tag"]) if prior else ask(args.model, cid, fmt, k["questions"], env, args.tag)
                    f.write(json.dumps(r) + "\n")
                    f.flush()
                    print(cid, fmt, "reused" if prior else "asked", r["input_tokens"], r["wall_s"], r["reply"][:80].replace("\n", " "), flush=True)
    write_report(args.model)


if __name__ == "__main__":
    main()
