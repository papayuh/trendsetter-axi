# Suite3 benchmark results

Model `claude-sonnet-5-5`, effort low; subscription CLI only.
Manifest SHA-256: `41b7b5a6df705410450ef7bfe7f385912d2c75663ddf6bbc1d2056ec78a02a1b`.
Planned: 70 charts × 4 questions × 3 trials × 3 arms = 630 cells / 2,520 answers.
Observed: 630 attempts; 630 successful cells; 0 errors; 210/210 complete paired chart-trials.
All-attempt list-price equivalent: $4.740457 / $20 guide. CLI-reported: $4.740457. Not subscription billing. Unknown costs retain conservative reservations.
Summed child wall seconds: 3676.261; interrupted attempts with unknown remaining duration: 0. Recorded session elapsed seconds: 1539.831 (external waits excluded).

Only chart-trials complete in all three arms enter comparisons. Input tokens include cached input, all transcript replays and tool overhead; output separate. Null/missing = abstain; malformed replies wrong. Numeric relative error and mixed-unit MAE include only finite numeric replies, with denominator shown.

## Pooled paired results

| arm | correct / questions | wrong | abstain | input tokens | output tokens | summed wall s | query turns | model invocations | numeric n | mean relative error | mixed-unit MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| record | 828/840 | 1 | 11 | 648990 | 98193 | 1384.828 | 0 | 210 | 787 | 0.000127191 | 0.00127065 |
| record+query | 825/840 | 6 | 9 | 831009 | 92409 | 1403.912 | 27 | 237 | 789 | 0.000338159 | 0.144487 |
| table+stats | 805/840 | 2 | 33 | 330342 | 15383 | 887.521 | 0 | 210 | 765 | 0.0023661 | 0.00245627 |

## Predeclared success bars

Each new arm: strictly beat stored summary/hybrid pooled and in every trial; separately, be within 2 correct of same-day table+stats per trial and within 6 pooled. Incomplete runs cannot pass. No token threshold.

- **record**: earlier summary/hybrid improvement **PASS**; same-day control competitiveness **PASS**. Total input vs same-day control: 196.5%.
- **record+query**: earlier summary/hybrid improvement **PASS**; same-day control competitiveness **PASS**. Total input vs same-day control: 251.6%.

## Earlier-run suite2 results (stored, not rerun here)

| arm | correct / questions | input tokens | trial 1 / 2 / 3 correct |
| --- | ---: | ---: | --- |
| summary | 659/840 | 252243 | 219 / 219 / 221 |
| hybrid | 700/840 | 305481 | 234 / 235 / 231 |
| table+stats | 797/840 | 330342 | 266 / 265 / 266 |

Earlier-run results are not same-day paired controls; compare descriptive counts only. The original suite2 report remains in [RESULTS.md](RESULTS.md).

## Trial 1

| arm | correct / questions | wrong | abstain | input tokens | output tokens | summed wall s | query turns | model invocations | numeric n | mean relative error | mixed-unit MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| record | 277/280 | 0 | 3 | 216330 | 33093 | 461.003 | 0 | 70 | 263 | 3.7763e-07 | 1.52091e-14 |
| record+query | 275/280 | 2 | 3 | 261333 | 32437 | 453.418 | 7 | 77 | 263 | 0.00023802 | 0.144487 |
| table+stats | 269/280 | 0 | 11 | 110114 | 5124 | 278.219 | 0 | 70 | 255 | 4.91211e-07 | 1.05758e-05 |

## Trial 2

| arm | correct / questions | wrong | abstain | input tokens | output tokens | summed wall s | query turns | model invocations | numeric n | mean relative error | mixed-unit MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| record | 275/280 | 1 | 4 | 216330 | 31704 | 437.226 | 0 | 70 | 262 | 0.000381679 | 0.00381679 |
| record+query | 275/280 | 2 | 3 | 282360 | 29638 | 458.214 | 9 | 79 | 263 | 0.000277328 | 0.144487 |
| table+stats | 268/280 | 1 | 11 | 110114 | 5319 | 304.780 | 0 | 70 | 255 | 0.00709739 | 0.00734767 |

## Trial 3

| arm | correct / questions | wrong | abstain | input tokens | output tokens | summed wall s | query turns | model invocations | numeric n | mean relative error | mixed-unit MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| record | 276/280 | 0 | 4 | 216330 | 33396 | 486.599 | 0 | 70 | 262 | 1.85628e-16 | 7.4762e-24 |
| record+query | 275/280 | 2 | 3 | 287316 | 30334 | 492.280 | 11 | 81 | 263 | 0.000499128 | 0.144487 |
| table+stats | 268/280 | 1 | 11 | 110114 | 4940 | 304.522 | 0 | 70 | 255 | 4.09937e-07 | 1.05758e-05 |

## Kind: line

| arm | correct / questions | wrong | abstain | input tokens | output tokens | summed wall s | query turns | model invocations | numeric n | mean relative error | mixed-unit MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| record | 143/144 | 1 | 0 | 90561 | 11018 | 205.676 | 0 | 36 | 144 | 0.000694444 | 0.00694444 |
| record+query | 144/144 | 0 | 0 | 146581 | 9327 | 245.539 | 12 | 48 | 144 | 0 | 0 |
| table+stats | 135/144 | 0 | 9 | 53922 | 2542 | 153.057 | 0 | 36 | 135 | 0 | 0 |

## Kind: multi-line

| arm | correct / questions | wrong | abstain | input tokens | output tokens | summed wall s | query turns | model invocations | numeric n | mean relative error | mixed-unit MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| record | 120/120 | 0 | 0 | 85992 | 17222 | 259.917 | 0 | 30 | 90 | 0 | 0 |
| record+query | 119/120 | 1 | 0 | 94452 | 18407 | 224.067 | 0 | 30 | 90 | 0.000347222 | 0.0111111 |
| table+stats | 105/120 | 0 | 15 | 55377 | 3137 | 135.144 | 0 | 30 | 81 | 0 | 0 |

## Kind: bar

| arm | correct / questions | wrong | abstain | input tokens | output tokens | summed wall s | query turns | model invocations | numeric n | mean relative error | mixed-unit MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| record | 120/120 | 0 | 0 | 66387 | 3800 | 139.241 | 0 | 30 | 120 | 0 | 0 |
| record+query | 120/120 | 0 | 0 | 74847 | 3464 | 115.476 | 0 | 30 | 120 | 0 | 0 |
| table+stats | 120/120 | 0 | 0 | 40851 | 1520 | 141.816 | 0 | 30 | 120 | 0 | 0 |

## Kind: scatter

| arm | correct / questions | wrong | abstain | input tokens | output tokens | summed wall s | query turns | model invocations | numeric n | mean relative error | mixed-unit MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| record | 120/120 | 0 | 0 | 79845 | 10796 | 184.693 | 0 | 30 | 120 | 0 | 0 |
| record+query | 119/120 | 1 | 0 | 136743 | 7453 | 235.938 | 12 | 42 | 120 | 0.000833333 | 0.00833333 |
| table+stats | 116/120 | 1 | 3 | 44568 | 1910 | 121.700 | 0 | 30 | 117 | 0.0154675 | 0.0159911 |

## Kind: heatmap

| arm | correct / questions | wrong | abstain | input tokens | output tokens | summed wall s | query turns | model invocations | numeric n | mean relative error | mixed-unit MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| record | 120/120 | 0 | 0 | 212928 | 43068 | 310.343 | 0 | 30 | 120 | 0 | 0 |
| record+query | 116/120 | 4 | 0 | 247364 | 42038 | 321.501 | 2 | 32 | 120 | 0.00112847 | 0.933333 |
| table+stats | 120/120 | 0 | 0 | 46431 | 1657 | 109.077 | 0 | 30 | 120 | 0 | 0 |

## Kind: histogram

| arm | correct / questions | wrong | abstain | input tokens | output tokens | summed wall s | query turns | model invocations | numeric n | mean relative error | mixed-unit MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| record | 96/96 | 0 | 0 | 53949 | 7732 | 133.343 | 0 | 24 | 96 | 0 | 0 |
| record+query | 96/96 | 0 | 0 | 60717 | 7045 | 127.222 | 0 | 24 | 96 | 0 | 0 |
| table+stats | 90/96 | 0 | 6 | 40437 | 2268 | 96.029 | 0 | 24 | 90 | 0 | 0 |

## Kind: errorbar

| arm | correct / questions | wrong | abstain | input tokens | output tokens | summed wall s | query turns | model invocations | numeric n | mean relative error | mixed-unit MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| record | 60/60 | 0 | 0 | 30216 | 2677 | 87.681 | 0 | 15 | 60 | 1.65528e-06 | 6.66667e-14 |
| record+query | 60/60 | 0 | 0 | 36963 | 2698 | 76.438 | 1 | 16 | 60 | 2.34611e-06 | 9.44901e-14 |
| table+stats | 60/60 | 0 | 0 | 25131 | 1309 | 72.488 | 0 | 15 | 60 | 8.66443e-07 | 1.71667e-08 |

## Kind: subplot

| arm | correct / questions | wrong | abstain | input tokens | output tokens | summed wall s | query turns | model invocations | numeric n | mean relative error | mixed-unit MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| record | 48/48 | 0 | 0 | 25215 | 1799 | 54.291 | 0 | 12 | 36 | 0 | 0 |
| record+query | 48/48 | 0 | 0 | 28599 | 1896 | 49.744 | 0 | 12 | 36 | 0 | 0 |
| table+stats | 47/48 | 1 | 0 | 19818 | 893 | 49.253 | 0 | 12 | 36 | 0 | 0 |

## Kind: pie

| arm | correct / questions | wrong | abstain | input tokens | output tokens | summed wall s | query turns | model invocations | numeric n | mean relative error | mixed-unit MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| record | 1/12 | 0 | 11 | 3897 | 81 | 9.644 | 0 | 3 | 1 | 0 | 0 |
| record+query | 3/12 | 0 | 9 | 4743 | 81 | 7.986 | 0 | 3 | 3 | 0 | 0 |
| table+stats | 12/12 | 0 | 0 | 3807 | 147 | 8.956 | 0 | 3 | 6 | 5.21739e-05 | 0.00134831 |

## Query use and limitations

Query turns per cell (0..4): `{0: 188, 1: 17, 2: 5, 3: 0, 4: 0}`. Unavailable responses: 2. Reader generation seconds (one freeze pass): 0.312335.

No renderer, record or query implementation was changed. Query availability is limited: facts does not compute every aggregate and count_where requires records/explicit rows. Full records are not size-matched to sampled source tables; they may retain more point values. Unsupported artists remain unsupported. Tool requests are optional, not forced; arm accuracy alone cannot establish that the CLI caused an improvement. Replay inputs are charged in full; this protocol does not measure an optimized native-tool integration. Fixed source-derived questions favor lookups/counts/extrema, not open-ended analysis. One model, repeated shared charts, no statistical independence or general superiority claim. No summary rewrite or other-library reader is justified solely by a count comparison.
