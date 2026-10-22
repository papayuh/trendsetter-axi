"""Same questions, six ways to see the chart: render() text at 80 columns, RenderResult.summary(), a PNG, the text that
mpl_ascii and plotext make from the same figure, and nothing (a guessing baseline).

Run from repo root:
    PYTHONPATH=src python benchmarks/agent/run.py            # build fixtures, ask the model (resumes), write RESULTS.md
    PYTHONPATH=src python benchmarks/agent/run.py --no-ask   # fixtures and o200k counts only, no model calls

Model calls go through the locally logged-in `claude -p` CLI: one call per chart and format, all of a chart's questions in
that call, no tools, no MCP servers, no settings files, a short fixed system prompt. Building the fixtures needs tiktoken,
mpl_ascii and plotext: `uv pip install tiktoken mpl_ascii==1.0.1 plotext==6.1.0`.
"""
import argparse
import base64
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
from trendsetter_axi import render  # noqa: E402

HERE = Path(__file__).parent
FIXTURES, OUT = HERE / "fixtures", HERE / "out"
RESULTS, REPORT = HERE / "results.jsonl", HERE / "RESULTS.md"
FORMATS = ["none", "text", "summary", "image", "mpl_ascii", "plotext"]
TEXTS = {"text": "txt", "summary": "summary.txt", "mpl_ascii": "mpl_ascii.txt", "plotext": "plotext.txt"}   # fixture suffix per text format
COLS, DPI = 80, 100
SYSTEM = ("You read charts and answer questions about them. Reply with only a JSON object mapping each question id to its "
          "answer: a number, or one of the listed options. No prose, no code fences.")


def build():
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
    for cid, (kind, make) in CHARTS.items():
        fig, questions = make()
        r = render(fig, cols=COLS)
        fig.savefig(OUT / f"{cid}.png", dpi=DPI, metadata={"Software": None})
        w, h = (round(v * DPI) for v in fig.get_size_inches())
        texts = dict(text=r.text, summary=r.summary())
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
    (HERE / "questions.json").write_text(json.dumps(key, indent=1) + "\n")
    return key


def asks(questions):
    return "\n".join(f"{qid}: {q['q']}" + (f" (one of: {', '.join(q['options'])})" if q.get("options") else "")
                       for qid, q in questions.items())


def prompt(cid, fmt, questions):
    content = []
    if fmt in TEXTS:
        title = "Chart summary" if fmt == "summary" else "Chart, rendered as terminal text"   # same words for both text renderers
        head = f"{title}:\n```\n{(FIXTURES / f'{cid}.{TEXTS[fmt]}').read_text()}```"
    elif fmt == "image":
        data = base64.b64encode((OUT / f"{cid}.png").read_bytes()).decode()
        content.append(dict(type="image", source=dict(type="base64", media_type="image/png", data=data)))
        head = "Chart: the attached image."
    else:
        head = "No chart is attached. Give your best guess for each answer."
    content.append(dict(type="text", text=f"{head}\n\nQuestions:\n{asks(questions)}"))
    return dict(type="user", message=dict(role="user", content=content))


def ask(model, cid, fmt, questions, cli):
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
                wall_s=round(wall, 3), cost_usd=final.get("total_cost_usd"), asked=asks(questions), cli=cli)


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


def load(key):
    """The last usable row per (chart, format, model): asked this answer key's questions and not an error."""
    rows = [json.loads(line) for line in RESULTS.read_text().splitlines()] if RESULTS.exists() else []
    return {(r["chart"], r["format"], r["model"]): r for r in rows
            if r["chart"] in key and r.get("asked") == asks(key[r["chart"]]["questions"]) and not r["is_error"]}


def report(key, model):
    rows = [r for r in load(key).values() if r["model"] == model]
    by = {(r["chart"], r["format"]): r for r in rows}
    charts = [c for c in key if all((c, f) in by for f in FORMATS)]
    if not charts:
        return
    score = {}  # (chart, format) -> [bool per question]
    for (cid, fmt), r in by.items():
        got = parse(r["reply"])
        score[cid, fmt] = [grade(q, got.get(qid)) for qid, q in key[cid]["questions"].items()]

    def chart_tokens(cid, fmt):  # what the chart itself cost: this call's input minus the same call with no chart
        return by[cid, fmt]["input_tokens"] - by[cid, "none"]["input_tokens"]

    def acc(cells):
        flat = [ok for c in cells for ok in c]
        return f"{sum(flat)}/{len(flat)} ({100 * sum(flat) / len(flat):.0f}%)"

    def said(c, fmt, qid):
        return parse(by[c, fmt]["reply"]).get(qid)

    def answer(q):
        return f"{q['answer']}" + (f" ± {q['tol']}" if q["type"] == "number" else "")

    shown = FORMATS[1:] + FORMATS[:1]   # none last
    nq = sum(len(key[c]["questions"]) for c in charts)
    w, h = key[charts[0]]["png"]
    failed = {n: [c for c in charts if (FIXTURES / f"{c}.{n}.txt").read_text().startswith(f"({n} failed")] for n in ("mpl_ascii", "plotext")}
    L = [
        "# Agent chart-reading benchmark: results",
        "",
        "Generated by `run.py` from `results.jsonl`; method and reading in [README.md](README.md).",
        "",
        f"- {nq} questions on {len(charts)} charts; formats: `text` = `render(fig, cols={COLS}).text`, `summary` = "
        "`RenderResult.summary()`, `image` = PNG, `mpl_ascii` and `plotext` = those packages' text from the same figure, `none` = no chart",
        f"- model `{model}` via `claude -p`, {len(charts) * len(FORMATS)} calls (one per chart and format, all of that chart's "
        "questions in one call), one run, no repeats",
        f"- PNG {w}×{h} px (matplotlib default 6.4×4.8 in, {DPI} dpi); Anthropic's documented estimate width×height/750 = "
        f"{w * h / 750:.0f} tokens; tables use the API's count",
        "- chart tokens: the call's input tokens as the API reports them (Claude tokenizer), minus the same chart's `none` call",
        "- output tokens include the model's hidden reasoning; the replies themselves are a short JSON object. Calls ran one at a "
        "time; `mpl_ascii` and then `plotext` calls ran in later passes, so their latency is from a different stretch of time",
        *(f"- {n} raised on {len(cs)} chart(s) ({', '.join(f'`{c}`' for c in cs)}); that call got the error in place of a chart"
          for n, cs in failed.items() if cs),
        "",
        "## Totals",
        "",
        "| format | accuracy | chart tokens, median (Claude) | chart tokens, total (Claude) | o200k median | output tokens, median | wall s, median | API s, median | cost, total |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for fmt in shown:
        tok = [chart_tokens(c, fmt) for c in charts] if fmt != "none" else [0]
        o2 = statistics.median(key[c]["o200k"][fmt] for c in charts) if fmt in TEXTS else "-"
        L.append(f"| {fmt} | {acc([score[c, fmt] for c in charts])} | {statistics.median(tok):.0f} | {sum(tok)} | {o2} | "
                 f"{statistics.median(by[c, fmt]['output_tokens'] for c in charts):.0f} | "
                 f"{statistics.median(by[c, fmt]['wall_s'] for c in charts):.1f} | "
                 f"{statistics.median(by[c, fmt]['duration_api_ms'] / 1000 for c in charts):.1f} | "
                 f"${sum(by[c, fmt]['cost_usd'] or 0 for c in charts):.2f} |")
    kinds = defaultdict(list)
    for c in charts:
        kinds[key[c]["kind"]].append(c)
    L += ["", "## Accuracy by chart kind", "", "| kind | charts | " + " | ".join(shown) + " |", "| --- | ---: |" + " ---: |" * len(shown)]
    for kind, cs in kinds.items():
        L.append(f"| {kind} | {len(cs)} | " + " | ".join(acc([score[c, f] for c in cs]) for f in shown) + " |")
    L += ["", "## Per chart", "", "Chart tokens (Claude, from the API), o200k in brackets for text formats; then right answers per format.", "",
          "| chart | kind | " + " | ".join(f"tokens {f}" for f in shown[:-1]) + " | " + " | ".join(shown) + " |",
          "| --- | --- |" + " ---: |" * (2 * len(shown) - 1)]
    for c in charts:
        toks = [f"{chart_tokens(c, f)}" + (f" ({key[c]['o200k'][f]})" if f in TEXTS else "") for f in shown[:-1]]
        L.append(f"| `{c}` | {key[c]['kind']} | " + " | ".join(toks) + " | "
                 + " | ".join(f"{sum(score[c, f])}/{len(score[c, f])}" for f in shown) + " |")
    for title, keep in [("Image right, text wrong", lambda c, i: score[c, "image"][i] and not score[c, "text"][i]),
                        ("Text right, image wrong", lambda c, i: score[c, "text"][i] and not score[c, "image"][i]),
                        ("Summary wrong", lambda c, i: not score[c, "summary"][i])]:
        L += ["", f"## {title}", ""]
        hits = [(c, i, qid, q) for c in charts for i, (qid, q) in enumerate(key[c]["questions"].items()) if keep(c, i)]
        L += [f"- `{c}` {qid}: {q['q']} answer {answer(q)}; text {said(c, 'text', qid)!r}, summary {said(c, 'summary', qid)!r}, "
              f"image {said(c, 'image', qid)!r}" for c, i, qid, q in hits] or ["- none"]
    cost = sum(r["cost_usd"] or 0 for r in rows)
    L += ["", f"Cost reported by the CLI: ${cost:.2f}. Environment: matplotlib {matplotlib.__version__}, "
          f"Python {sys.version.split()[0]}, {', '.join(sorted({r['cli'] for r in rows}))}.", ""]
    REPORT.write_text("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--no-ask", action="store_true")
    args = ap.parse_args()
    key = build()
    if not args.no_ask:
        done = load(key)
        cli = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
        with RESULTS.open("a") as f:
            for cid, k in key.items():
                for fmt in FORMATS:   # interleaved per chart, so drift over the run hits every format alike
                    if (cid, fmt, args.model) in done:
                        continue
                    r = ask(args.model, cid, fmt, k["questions"], cli)
                    f.write(json.dumps(r) + "\n")
                    f.flush()
                    print(cid, fmt, r["input_tokens"], r["wall_s"], r["reply"][:80].replace("\n", " "), flush=True)
    report(key, args.model)


if __name__ == "__main__":
    main()
