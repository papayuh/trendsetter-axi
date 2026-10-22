# Can an agent read the chart? Text vs summary vs image

Same 81 factual questions about 25 charts, asked with the chart given six ways:

- `text`: `render(fig, cols=80).text`, the terminal chart
- `summary`: `RenderResult.summary()`, scales, series values from the figure's data, losses
- `image`: the figure saved as PNG, matplotlib's default 6.4×4.8 in at 100 dpi (640×480 px)
- `mpl_ascii`: the same figure through [mpl_ascii](https://github.com/chriscave/mpl_ascii) 1.0.1 (`str(FigureCanvasAscii(fig).draw_canvas())`, what its `savefig("x.txt")` writes)
- `plotext`: the same figure through [plotext](https://github.com/piccolomo/plotext) 6.1.0's `plotext.matplotlib(fig)` converter, `plot_size(80, 30)`, colourless
- `none`: no chart, to show what the model guesses from the questions alone

Numbers: [RESULTS.md](RESULTS.md). Raw replies, token counts and timings: `results.jsonl`. Answer key: `questions.json`. Rendered text: `fixtures/`.

## Reproduce

```sh
uv pip install -e '.[dev]' tiktoken mpl_ascii==1.0.1 plotext==6.1.0
PYTHONPATH=src python benchmarks/agent/run.py --no-ask   # rebuild fixtures, regrade results.jsonl, rewrite RESULTS.md
PYTHONPATH=src python benchmarks/agent/run.py            # also make model calls missing from results.jsonl (or errored, or asked older questions)
```

Model calls use the locally logged-in `claude -p` (Claude Code CLI): no API key, no tools, no MCP servers, no settings files, one short system prompt. To rerun from scratch, delete `results.jsonl`. `--model` picks another model; rows are kept per model.

## Method

- Charts (`charts.py`): 6 lines, 5 multi-line, 5 bars (vertical, horizontal, grouped, negative, 15 categories), 3 scatters, 3 heatmaps, 3 histograms. Data is synthetic but shaped like real data (prices, temperatures, traffic), with fixed seeds.
- Questions: 3 or 4 per chart: max and min, which series is higher at some x, trend direction, a value read at a point, counts of bars over a threshold. Every answer is computed from the arrays the chart is drawn from.
- Grading is automatic: labels must match (case-insensitive), counts exactly, numbers within a tolerance that is mostly 5% of the plotted data's span (15% of the value on the log axis). Each question's tolerance is in `questions.json`.
- One call per chart and format, with all of that chart's questions in it, so 150 calls on `claude-sonnet-5-5`, one run, no repeats. Total cost reported by the CLI: $1.72.
- Tokens: input tokens as the API reports them (Claude's tokenizer), minus the same chart's `none` call, so the prompt and questions cancel out and what's left is the chart. o200k counts (tiktoken `o200k_base`) are given for the text formats too. For the PNG, Anthropic documents about width×height/750 = 410 tokens; the API charged 408 on every chart.
- Latency: wall time of the whole `claude -p` call, which includes about 1 s of CLI start-up, plus the API time the CLI reports. Calls ran one at a time on a shared machine, and the `mpl_ascii` and `plotext` calls in later passes, so treat latency as rough.

## What it shows

| format | accuracy | chart tokens (median) | output tokens (median) | wall s (median) |
| --- | ---: | ---: | ---: | ---: |
| summary | 86% | 94 | 133 | 3.3 |
| image | 99% | 408 | 37 | 1.7 |
| text | 81% | 639 | 632 | 8.9 |
| mpl_ascii | 78% | 567 | 1,101 | 10.5 |
| plotext | 73% | 642 | 760 | 9.0 |
| none | 26% | 0 | 25 | 2.0 |

- **The image wins on accuracy.** 80 of 81 right. It is also cheaper to send than the 80-column text: 408 tokens, against a median 639 for the text (o200k median 536).
- **The text chart is not the token saver.** Braille and block characters cost more tokens than a 640×480 PNG, and the model then writes about 600 tokens of hidden reasoning per call reading them, against about 40 for the image. Text calls took about 9 s against 1.7 s. On these charts the 80-column text loses to the image on every measure. It is for a person at a terminal.
- **The summary is the token saver.** Median 94 tokens, 4× fewer than the image and 7× fewer than the text, at 86%. On cost it only roughly ties the image ($0.14 vs $0.16 for the 25 charts) because output tokens dominate both.
- **Where the summary misses** (11 questions), it is missing the data, not misreading it: for a line of more than 8 points it gives the first, last, min and max only; for more than 12 bars only the min and max; for a heatmap the min and max cells; for a scatter the ranges. Values in the middle of a long line, week-to-week changes, crossings, a scatter outlier's position and counts over a threshold on 15 bars are not in it, so the model guessed.
- **Where the text misses** (15): exact values between ticks on lines and heatmaps (a 4-shade heatmap key gives ranges, not values), which of several overlapping lines is which at a given x, and a cross point on a dense line. Bars, scatters and histograms were 100%.
- **The image's one miss** was a mid-line value on a 250-point price walk, which the text got right.
- **Against the other matplotlib-to-text routes**, the trendsetter-axi text scored 81%, mpl_ascii 78%, plotext 73%. mpl_ascii's text is the cheapest of the three (median 567 tokens, against 639 and 642).
  - mpl_ascii read multi-line charts better (100% vs 67%). Its plain-text output drew no heatmap cells (0 of 10 on heatmaps, against 6 of 10 for the text), and it raised `IndexError` on the log-scale chart.
  - plotext's converter carries lines, scatter points and bar rectangles, not images: the three heatmaps came out as empty panels. Its 2 heatmap hits were guesses: the synthetic gas-price spike happens to sit in June 2022, where real prices peaked. It drew the log-scale chart on a linear axis and showed bar positions as numbers (`-0.4 … 5.4`) instead of the category names, which cost it the region bars (2 of 4).
  - Neither reports what it dropped. trendsetter-axi's `RenderResult.losses` does, and `summary()` is the format that beat all three text renders.

So for an agent, the evidence supports: send `summary()` when tokens matter and the questions are about the data's extremes, ranges and named values; send the PNG when accuracy matters and the model takes images; keep the text chart for people at a terminal. Not measured here: text and summary together, other models, other image sizes, repeats.
