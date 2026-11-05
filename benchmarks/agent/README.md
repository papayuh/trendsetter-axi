# Subscription-only agent benchmark, suite2

## Predeclared success criterion (written before calls)

The corrected `summary` must match `table+stats` within **2 correct answers in each trial** (pooled deficit at most 6), using **no more than 40% of its total input tokens**, on all 70 charts. Otherwise the agent claim narrows to the hybrid and the human-readable preview; neither is claimed superior without a corresponding results cell. An incomplete run cannot pass. Output tokens are reported separately, not hidden in this ratio. This criterion is deliberately based on total input, including common prompt overhead, not a favorable subtraction of the no-data arm.

No renderer tuning against this suite. Renderer frozen at current main commit **`4376145d51b874f8f3f2799bc4fbd4292d9e221d`**. `src/` must match that commit before every run. The complete suite, questions, answer key, stimuli and manifest are committed before any model call. The historical `after` pilot is not a new observation: it remains labeled in [RESULTS.md](RESULTS.md), with original details in [RESULTS-historical.md](RESULTS-historical.md) and [README-historical.md](README-historical.md).

## Design

- 70 new charts, four array-derived questions each: 12 line, 10 multi-line, 10 bar (horizontal and vertical), 10 scatter, 10 heatmap, 8 histogram, 5 errorbar, 4 subplot, 1 unsupported pie.
- Independent fixed seeds `22000 + kind_index*100 + variant`. Features include masked points/cells, NaN gaps, ties, constant series, `1e-8` values, negatives, `1e9` offsets, timestamps one second apart, explicit tick aliases, uncertainty endpoints, a lone heatmap spike, two panels and unsupported wedges.
- Arms: `table` (direct arrays and metadata), `table+stats` (identical table plus full-array statistics), `summary` (`render(fig,80).summary()`), `text` (`render(fig,80).text`), `hybrid` (60×12 ASCII text plus its summary), `image` (640×480 PNG), `none`.
- Table sampling is declared independently of answers. Up to 64 rows per source series: all rows. Larger sources: deterministic uniform source indices including endpoints, no min/max or queried-point injection. Choose the largest per-series sample size fitting the summary's **o200k token count**, with a 256-token floor. The metadata plus one row may exceed the budget; manifest records the target and actual tokens. Identical sampled table in `table+stats`; its added full-source stats are not budget-clipped. No model-tokenizer equivalence is assumed.
- Tables retain source precision, missing values as null, aliases, series/panel names, histogram edges/counts, error widths and heatmap coordinates. Statistics are finite-column n/min/max/mean/sum, negative count and max ties, plus paired-series above counts; no textual answer key is supplied. Tables describe the source, not the renderer's sampled/rounded output.
- 3 independent trials on exactly `claude-sonnet-5-5`, effort low. One call per chart/arm/trial with all four questions. 1,470 planned calls; 5,880 answer opportunities. No cross-trial or historical reply reuse. The 35 smoke calls (five charts × seven arms) are part of trial 1, not extra observations. Smoke selection is fixed: masked line, tiny scatter, tied bar, lone large heatmap spike, gapped errorbar.
- Trial chart order and per-chart arm order are seeded/shuffled, at most four calls concurrently. Comparisons use only chart-trials complete across all seven arms. Incomplete successes and all failures remain auditable in raw rows.
- Numeric tolerance: 2% of source span, floor `1e-12`; exact counts, case-insensitive labels. Malformed replies count wrong. Null/missing answers count as abstentions. Relative numeric error and mixed-unit absolute error are reported only for finite numeric answers, with denominator counts, so abstaining cannot silently improve accuracy.

## Auth, budget, resume

Calls use the logged-in **subscription** through `claude -p`, never an SDK or API key. Child environment unsets `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, third-party-provider toggles and a custom Anthropic endpoint. No credential files are read by benchmark code. CLI safe mode disables project instructions, plugins, hooks, memory and customizations; tools, Chrome, slash commands, MCP and session persistence are disabled. Do not use `--bare`: it disables OAuth. Every raw row preserves the auth source reported by CLI initialization. Any API-key auth report stops the run, including on resume.

Spend guide: **$40 list-price equivalent**, not subscription API billing. CLI `total_cost_usd` is the model-specific list-price estimate; preserve its complete `usage`/`modelUsage` metadata. `--max-budget-usd 0.10` bounds each CLI session; before each batch reserve $0.10 per call. Unknown-cost failures are conservatively charged $0.10. All attempts, including smoke/retries/failures, enter the running total. Stop before a batch would exceed $40. CLI budget enforcement is request-granular, not a billing hard cap.

Each finished call is immediately flushed/fsynced to `results/suite2/calls.jsonl`; a rerun skips only successful cells matching the immutable manifest. A durable pre-dispatch batch journal reserves unknown spend after parent interruption (added after the first interrupted run; that single unknown-cost attempt was conservatively reconstructed from the deterministic batch order). Failed calls are retained and retried on resume. Stop on errors; on a subscription limit wait until reset and resume, reporting paused if reset would take over six hours. Do not substitute a model or API key. Capture elapsed run wall time separately from the sum of parallel child wall times. Fixture rendering and summary-generation timings are measured once during freeze, not included in inference times.

```sh
uv pip install --python .venv/bin/python -e '.[dev]' tiktoken
# Already committed; freeze refuses to overwrite an existing manifest:
PYTHONPATH=src .venv/bin/python benchmarks/agent/run.py --suite2 freeze
PYTHONPATH=src .venv/bin/python benchmarks/agent/run.py --suite2 smoke
PYTHONPATH=src .venv/bin/python benchmarks/agent/run.py --suite2 run
# Pure regrade; no model calls:
PYTHONPATH=src .venv/bin/python benchmarks/agent/run.py --suite2 report
```

## Observed outcome

All 1,470 cells completed, 210/210 chart-trials paired. Summary **failed**: 659/840 correct versus 797/840 for `table+stats`, at 76.4% of its total input tokens. Hybrid reached 700/840; PNG 756/840. See [results cells and limits](RESULTS.md). The corrected-summary agent claim is withdrawn; hybrid and human preview remain available without superiority claims. CLI reported $7.071070 equivalent; one interrupted call adds a conservative $0.10 reserve. A parent timeout was resumed, not a subscription limit. Exact interrupted-call wall time is unavailable; the report labels the 3,600-second parent-session allowance and excludes the unknown child's wall time rather than inventing a timing.

The manifest hashes every text/PNG stimulus and includes arrays, questions, sampling sizes, seeds, fixed system prompt, environment and renderer timings. Raw replies bind to the SHA-256 of that entire manifest. Never regenerate fixtures after looking at results. [RESULTS.md](RESULTS.md) is the source of every empirical agent claim in the root README.
