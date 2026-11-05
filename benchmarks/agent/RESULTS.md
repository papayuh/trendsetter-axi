# Suite2 benchmark results

Frozen renderer `4376145d51b874f8f3f2799bc4fbd4292d9e221d`. Model `claude-sonnet-5-5`; subscription CLI, effort low.

Manifest SHA-256: `a827b626cb813c6f9dc93bb0b8cc8bbec0ba2ad9604566e782bcc2c64dc4e33d`. Planned: 70 charts × 4 questions × 3 trials × 7 arms = 1,470 calls / 5,880 answers.
Observed: 0 attempts, 0 successful cells, 0 errors. Complete paired chart-trials: 0/210 (0/70 distinct charts).
CLI list-price equivalent (all attempts): $0.000000; subscription billed API spend: $0.
Child wall seconds, summed (parallel, not elapsed): 0.000. Elapsed runner wall seconds (sum of sessions, excluding external reset waits): 0.000.

Only chart-trials complete in all seven arms enter comparative cells; incomplete successes remain in raw JSONL. Numeric error is mean |answer−truth| / max(|truth|, tolerance, 1e-12), finite numeric replies only; abstention includes null/missing answers. Invalid replies count wrong, not numeric error.

## Pooled paired results

| arm | correct / questions | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| table+stats | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| summary | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| text | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| hybrid | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| image | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| none | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |

## Predeclared criterion

Outcome: **NOT EVALUABLE — incomplete run**. Summary must be within 2 correct answers of table+stats in every trial (pooled deficit ≤6), using ≤40% of its total input tokens. No renderer tuning used this suite.

## Trial 1

| arm | correct / questions | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| table+stats | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| summary | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| text | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| hybrid | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| image | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| none | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |

## Trial 2

| arm | correct / questions | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| table+stats | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| summary | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| text | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| hybrid | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| image | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| none | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |

## Trial 3

| arm | correct / questions | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| table+stats | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| summary | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| text | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| hybrid | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| image | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| none | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |

## Kind: line

| arm | correct / questions | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| table+stats | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| summary | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| text | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| hybrid | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| image | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| none | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |

## Kind: multi-line

| arm | correct / questions | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| table+stats | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| summary | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| text | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| hybrid | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| image | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| none | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |

## Kind: bar

| arm | correct / questions | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| table+stats | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| summary | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| text | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| hybrid | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| image | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| none | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |

## Kind: scatter

| arm | correct / questions | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| table+stats | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| summary | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| text | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| hybrid | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| image | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| none | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |

## Kind: heatmap

| arm | correct / questions | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| table+stats | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| summary | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| text | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| hybrid | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| image | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| none | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |

## Kind: histogram

| arm | correct / questions | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| table+stats | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| summary | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| text | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| hybrid | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| image | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| none | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |

## Kind: errorbar

| arm | correct / questions | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| table+stats | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| summary | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| text | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| hybrid | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| image | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| none | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |

## Kind: subplot

| arm | correct / questions | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| table+stats | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| summary | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| text | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| hybrid | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| image | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| none | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |

## Kind: pie

| arm | correct / questions | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| table+stats | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| summary | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| text | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| hybrid | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| image | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |
| none | 0/0 | 0 | 0 | 0 | 0.000 | 0 | — | — |

## Fixture generation timing (single pass, seconds)

| kind | charts | render 80 | summary only | hybrid render+summary | PNG |
| --- | ---: | ---: | ---: | ---: | ---: |
| line | 12 | 1.988862 | 0.000386 | 1.319298 | 0.411672 |
| multi-line | 10 | 1.952804 | 0.000461 | 1.340951 | 0.406547 |
| bar | 10 | 2.725936 | 0.000253 | 2.235864 | 0.409568 |
| scatter | 10 | 1.234543 | 0.000185 | 0.769240 | 0.237726 |
| heatmap | 10 | 2.398028 | 0.000240 | 2.149856 | 0.599715 |
| histogram | 8 | 1.765503 | 0.000182 | 1.124302 | 0.258340 |
| errorbar | 5 | 0.873485 | 0.000202 | 0.556787 | 0.155612 |
| subplot | 4 | 1.224902 | 0.000174 | 0.858625 | 0.205652 |
| pie | 1 | 0.064394 | 0.000010 | 0.057808 | 0.009555 |

## Historical pilot (not rerun; not comparable)

| tag | split | summary | hybrid | image | text | mpl_ascii | plotext | median summary / hybrid / image input chart tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| after @ 9288d2b | dev, 25 charts | 79/81 | 78/81 | 80/81 | 66/81 | 63/81 | 59/81 | 102 / 316 / 408 |
| after @ 9288d2b | held-out, 12 charts | 37/39 | 39/39 | 39/39 | 35/39 | 28/39 | 22/39 | 114 / 326 / 408 |

Historical detail and original raw records remain in `results.jsonl`; see `RESULTS-historical.md`.
