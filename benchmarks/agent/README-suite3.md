# Suite3: chart records and a query tool

## Predeclared success bars (commit before any model call)

Evaluate each new arm separately on all 70 suite2 charts, four unchanged questions,
unchanged answer keys/tolerances, three trials (840 answers per arm). Incomplete
runs cannot pass either bar.

1. **Improves on earlier summary/hybrid:** strictly more correct than both stored
   suite2 arms pooled (summary 659/840, hybrid 700/840), and in every corresponding
   trial (summary 219/219/221; hybrid 234/235/231). These are earlier-run comparisons,
   not same-day paired observations or a significance claim.
2. **Competitive with direct data:** within two correct answers of the same-day
   `table+stats` control in each trial (pooled deficit at most six). This second
   bar does not require a token saving. Report total input/output tokens, query
   turns and input ratios rather than inventing another unreachable token target.

No summary rewrite or new reader is implemented here. Passing a bar supports only
this model, these chart questions and this frozen reader. Repeated trials share
charts; 840 answers are not 840 independent charts. An unsupported artist or a
reader/query defect is reported, never repaired or patched into stimuli mid-run.

## Frozen design

- `suite3.py` is separate from suite2. It imports suite2's generator, grading,
  prompt, environment cleaner and digest helpers without modifying suite2 files.
- Exactly the same 70 figures are regenerated from the fixed seeds; source data,
  features and all questions must equal the stored suite2 manifest before freeze.
- `record`: compact JSON from unmodified `from_figure(fig)`, without declarations,
  source-table additions, query-derived facts, sampling or answer injection.
- `record+query`: identical record JSON plus a tool protocol for calling
  `python -m trendsetter_axi.queries RECORD OPERATION ARGS...`. The model returns
  `{"query":{"operation":"value_at","args":["m0",3]}}` to request one call,
  or the usual question-ID answer object to finish. Only the fixed record and
  operations other than file-reading `diff` are accessible. No shell, filesystem,
  general Python or external MCP tool is available to the model. Query arguments
  are JSON values; `count_where` may receive an explicit model-supplied table.
- At most **four query turns per chart/arm/trial**, then one final answer turn.
  Tool requests are executed as a subprocess argv, never a shell. All requests,
  CLI responses, per-turn usage and model events are saved. The CLI may return
  `unavailable`; no substitute operation or hidden data is injected.
- Tool protocol uses fresh `claude -p` invocations with transcript replay, not
  persisted sessions. Every replay's entire CLI input (including cached tokens,
  tool instructions, previous requests and results) counts in arm totals. This
  is intentionally transparent but may cost more input than a native tool loop.
  Report number of query turns and total model invocations separately.
- `table+stats`: byte-identical suite2 fixture, rerun in the same interleaved
  runner sessions as the new arms. Same plain-answer system prompt as suite2.
- Exact `claude-sonnet-5-5`, effort low, three trials. Seeded trial/chart/arm order,
  four concurrent chart cells maximum. Smoke is five fixed suite2 smoke charts
  in trial 1, not extra observations. 630 planned cells / 2,520 answers.
- Comparative cells include only chart-trials successful in all three arms.
  Malformed answers are wrong; null/missing are abstentions. Numeric errors use
  suite2's finite-reply denominators, relative error and mixed-unit MAE.
- Manifest binds stimuli, original suite2 manifest, all `src/**/*.py` bytes,
  suite3 runner code and this protocol. All are committed before calls. Resume
  refuses mismatched manifests, changed stimuli/code or any prior API-key auth.
  Reporting regrades frozen files without requiring old source git history.

## Subscription, budget and interruptions

Subscription only through `claude -p`; no SDK/API calls, no credential-file reads.
Use suite2's child environment: strip API keys/auth tokens, provider toggles and
custom Anthropic endpoint. Same safe-mode, no tools/plugins/hooks/project memory,
no MCP, Chrome, slash commands or session persistence; never `--bare`. Validate
reported auth and exact model on **every** invocation. Store full usage/modelUsage
and CLI `total_cost_usd`; total input is input + cache creation + cache read.

Spend guide **$20 list-price equivalent**, not subscription billing. Reserve
**$0.10 per chart cell** durably before dispatch; all tool-loop invocations share
that cell allowance, passing the remaining allowance to `--max-budget-usd`.
Unknown-cost invocations/interrupted cells consume the remaining reservation;
known usage is never discarded. Record/retry failures rather than hiding them.
Budget enforcement is request-granular, not a billing hard cap. Stop before a
batch's reservations exceed $20. All attempts count, including smoke and retries.

Stop on any error and retain the raw response. On subscription limits, resume
only after reset; if the pause lasts or would last more than six hours, stop and
report to firstmate. Do not switch model or auth. Record session elapsed wall
seconds separately from parallel child wall seconds. An interrupted session's
end time is unknown, not invented.

```sh
PYTHONPATH=src .venv/bin/python benchmarks/agent/suite3.py freeze
# Commit README, runner, tests, manifest and stimuli BEFORE these commands:
PYTHONPATH=src .venv/bin/python benchmarks/agent/suite3.py smoke
PYTHONPATH=src .venv/bin/python benchmarks/agent/suite3.py run
# Offline; does not update suite2 RESULTS.md:
PYTHONPATH=src .venv/bin/python benchmarks/agent/suite3.py report
```

Suite3's generated report is `RESULTS-suite3.md`. The benchmark index
`RESULTS.md` retains the original suite2 report verbatim below a clearly labeled
suite3 link/summary. Stored suite2 summary, hybrid and table+stats numbers are
explicitly labeled earlier-run results in the suite3 report.
