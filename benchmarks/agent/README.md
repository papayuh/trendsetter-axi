# Can an agent read the chart? Text vs summary vs image

The same factual questions about the same charts, asked with each chart given one of these ways:

- `text`: `render(fig, cols=80).text`, the terminal chart a person reads
- `summary`: `RenderResult.summary()`: scales, series values from the figure's data, losses
- `ascii`: `render(fig, 80, ascii=True, rows=16).text`, the same chart drawn in ASCII and shorter
- `ascii_tall`: `render(fig, 80, ascii=True).text`, ASCII at the default height
- `hybrid`: `render(fig, 60, ascii=True, rows=12)`'s text, a blank line, then that result's `summary()`
- `image`: the figure saved as PNG, matplotlib's default 6.4×4.8 in at 100 dpi (640×480 px)
- `mpl_ascii`: the same figure through [mpl_ascii](https://github.com/chriscave/mpl_ascii) 1.0.1 (`str(FigureCanvasAscii(fig).draw_canvas())`, what its `savefig("x.txt")` writes)
- `plotext`: the same figure through [plotext](https://github.com/piccolomo/plotext) 6.1.0's `plotext.matplotlib(fig)` converter, `plot_size(80, 30)`, colourless
- `none`: no chart, to show what the model guesses from the questions alone

Numbers: [RESULTS.md](RESULTS.md). Raw replies, token counts and timings: `results.jsonl`. Answer keys: `questions.json` (dev) and `questions-heldout.json`. Rendered text: `fixtures/`.

## Reproduce

```sh
uv pip install -e '.[dev]' tiktoken mpl_ascii==1.0.1 plotext==6.1.0
PYTHONPATH=src python benchmarks/agent/run.py --no-ask                     # rebuild dev fixtures, regrade results.jsonl, rewrite RESULTS.md
PYTHONPATH=src python benchmarks/agent/run.py --tag after                  # also make dev calls missing for that tag
PYTHONPATH=src python benchmarks/agent/run.py --tag after --split heldout  # the same for the held-out charts
```

Model calls use the locally logged-in `claude -p` (Claude Code CLI): no API key, no tools, no MCP servers, no settings files, one short system prompt. Every row in `results.jsonl` records its tag, the questions it asked and a hash of the chart it showed. A call is re-made when either changed; a call whose chart and questions are identical to an earlier one is reused under the new tag (marked `reused_from`), so the image, mpl_ascii, plotext and no-chart calls were made once. `--formats` limits a run to some formats; `--model` picks another model.

## Method

- Dev split (`charts.py`): 25 charts, 81 questions. 6 lines, 5 multi-line, 5 bars (vertical, horizontal, grouped, negative, 15 categories), 3 scatters, 3 heatmaps, 3 histograms. The data is synthetic but shaped like real data (prices, temperatures, traffic), with fixed seeds.
- Held-out split (`heldout.py`): 12 charts, 39 questions of the same kinds, written and scored on the old renderer before any change. It was not used to tune anything.
- Questions: 3 or 4 per chart: max and min, which series is higher at some x, trend direction, a value read at a point, counts over a threshold. Every answer is computed from the arrays the chart is drawn from.
- Grading is automatic and unchanged across rounds: labels must match (case-insensitive), counts exactly, numbers within a tolerance that is mostly 5% of the plotted data's span (15% of the value on a log axis). Each question's tolerance is in the answer keys.
- One call per chart and format, with all of that chart's questions in it, on `claude-sonnet-5-5`. One run per tag, no repeats. Total cost of every call, tuning rounds included: see the last line of RESULTS.md.
- Tokens: input tokens as the API reports them (Claude's tokenizer), minus the same chart's `none` call, so the prompt and questions cancel out and what's left is the chart. o200k counts (tiktoken `o200k_base`) are given for the text formats too. For the PNG, Anthropic documents about width×height/750 = 410 tokens; the API charged 408 on every chart. Output tokens include the model's hidden reasoning; the replies are a short JSON object.
- Tags: `before` = the renderer at c1f6de5 (the first run of this benchmark). `iter1` = the one tuning round, on dev only. `after` = this renderer, frozen after `iter1` and then run once on both splits. `ascii_tall` was added after the held-out `ascii` result came in, to show the cost of height. Its configuration is the default height, not a tuned value.
- Latency is the wall time of the whole `claude -p` call, which includes about 1 s of CLI start-up. Calls ran one at a time on a shared machine, so treat it as rough.

## Why the summary and the text missed (before)

On dev, `before`:

- **Summary, 11 misses.** Every one was data the summary did not carry:
  - lines over 8 points gave only first, last, min and max, so values in the middle, crossings, week-to-week drops and which line led at an x were guesses (7 misses)
  - more than 12 bars gave only the min and max, so counts over a threshold on 15 bars or 20 histogram bins were guesses (2)
  - heatmaps gave only the min and max cells, so one correlation value was a guess (1)
  - scatters gave only ranges, so the outlier's position was a guess (1)
- **Text, 15 misses**, all reading errors:
  - values between ticks on lines and heatmaps (a 4-shade key gives ranges, not values)
  - which of several overlapping lines is which at a given x
  - a crossing on a dense line
- **Where the tokens go in the text.** In o200k, a braille character costs 2 to 3 tokens and a shade or partial block (`░▒▓▂▄▆`) 1 to 1.75, while a run of `█`, `─`, `#` or spaces costs almost nothing. A braille line or a shaded heatmap is most of a chart's tokens.

## What changed

- `summary()` now carries the data: every line point up to 16, else the first and last point, ~10 evenly spaced points between and the exact extremes. Lines that share x positions share one `lines at x:` row. It also gives every bar up to 40, histograms as bins plus counts plus the peak bin, heatmaps up to 36 cells in full (larger ones as row and column means), and scatter mean, r and outliers. Numbers are rounded to a step near 1/60 of the axis span, and linear axes drop their view range. That paid for the added data.
- `render(..., ascii=True)` translates braille, block and shade glyphs to ASCII after layout, so every line keeps its width and frame. `render(..., rows=N)` sets the height.

## Results

| format | dev before | dev after | held-out before | held-out after | tokens dev before → after | tokens held-out before → after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| summary | 86% | **98%** | 90% | **95%** | 94 → 102 | 97 → 114 |
| hybrid | - | 96% | - | **100%** | 316 | 326 |
| ascii (16 rows) | - | 83% | - | 67% | 263 | 256 |
| ascii_tall | - | 79% | - | 90% | 422 | 421 |
| text (default) | 81% | 81% | 90% | 90% | 639 | 701 |
| image | 99% | 99% | 100% | 100% | 408 | 408 |
| mpl_ascii | 78% | 78% | 72% | 72% | 567 | 514 |
| plotext | 73% | 73% | 56% | 56% | 642 | 626 |
| none | 26% | 26% | 38% | 38% | 0 | 0 |

Tokens are the median per chart. The default text chart is unchanged, so its rows are reused.

- **Summary target (≥ 95% at ≤ ~120 tokens): met on both splits.** 98% at 102 tokens on dev, 95% at 114 on held-out. The model also stopped working it out the hard way: median output fell from 133 to 38 tokens (held-out 142 to 33), and output tokens cost more than input. Its remaining misses are counting slips with the numbers in front of it (months where one city is colder than another, areas under 3.0, bins over 100) and one interpolation on a sampled line.
- **Hybrid** is the best text input: 96% and 100% at ~320 tokens and ~35 output tokens. That is fewer input tokens than the PNG at about the same accuracy.
- **Text chart target (accuracy up, tokens at least halved): not met.**
  - `ascii` at 16 rows cuts the tokens 59% (639 → 263). It scored 83% against 81% on dev but only 67% against 90% on held-out: 16 rows of ASCII hold about 16 levels where braille at 30 rows holds 120, and it lost values on lines, a log axis and heatmaps.
  - `ascii_tall` keeps the held-out accuracy (90%, as the default text) at 40% fewer tokens (701 → 421), and on dev it is 2 points under (79% vs 81%).
  - Both ASCII formats make the model reason at length (650 to 950 output tokens), so per call they cost no less than the braille chart.
  - So the terminal chart stays what it is for: a person reading it. An agent should get `summary()`, or the hybrid when it should also see the shape.
- **The image** stays the most accurate single input (99%, 100%) at 408 tokens.
- **Against mpl_ascii and plotext** (unchanged, on the same figures):
  - mpl_ascii's plain-text output drew no heatmap cells and raised `IndexError` on the log-scale chart.
  - plotext's converter carries lines, scatter points and bar rectangles but not images: heatmaps came out as empty panels, and its 2 dev heatmap hits were guesses (the synthetic gas-price spike sits in June 2022, where real prices peaked). It drew log axes as linear and showed bar positions as numbers instead of names.
  - Neither reports what it dropped.

Not measured: other models, other image sizes, repeats.
