# Suite2 benchmark results

Frozen renderer `4376145d51b874f8f3f2799bc4fbd4292d9e221d`. Model `claude-sonnet-5-5`; subscription CLI, effort low.

Manifest SHA-256: `a827b626cb813c6f9dc93bb0b8cc8bbec0ba2ad9604566e782bcc2c64dc4e33d`. Planned: 70 charts × 4 questions × 3 trials × 7 arms = 1,470 calls / 5,880 answers.
Observed: 1471 attempts, 1470 successful cells, 1 errors. Complete paired chart-trials: 210/210 (70/70 distinct charts).
List-price accounting (all attempts): $7.171070, including $7.071070 reported by CLI and $0.100000 reserved for unknown-cost interruptions. No API keys used; these are not subscription billing measurements.
Measured child wall seconds, summed (parallel, not elapsed): 7686.985; 1 interrupted attempt(s) have unknown duration and are excluded. Recorded runner wall seconds (sum of sessions, excluding external reset waits): 3717.899. The interrupted full-run session contributes its 3,600-second parent timeout allowance, not an exact end-to-end measurement.

Only chart-trials complete in all seven arms enter comparative cells; incomplete successes remain in raw JSONL. Numeric error is mean |answer−truth| / max(|truth|, tolerance, 1e-12), finite numeric replies only; abstention includes null/missing answers. Invalid replies count wrong, not numeric error.

## Pooled paired results

| arm | correct / questions | wrong (non-abstained) | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 677/840 | 7 | 156 | 292365 | 27136 | 866.070 | 645 | 0.00552441 | 1.13925 |
| table+stats | 797/840 | 10 | 33 | 330342 | 15084 | 787.344 | 765 | 0.00529193 | 0.00882354 |
| summary | 659/840 | 14 | 167 | 252243 | 41988 | 945.180 | 637 | 0.0159073 | 0.561209 |
| text | 380/840 | 156 | 304 | 412284 | 238049 | 2628.019 | 495 | 0.163838 | 1.41414e+07 |
| hybrid | 700/840 | 11 | 129 | 305481 | 55936 | 1108.043 | 667 | 0.00760598 | 0.0553487 |
| image | 756/840 | 59 | 25 | 307560 | 48606 | 642.316 | 767 | 0.0626344 | 4.3455e+07 |
| none | 0/840 | 0 | 840 | 220620 | 5675 | 710.012 | 0 | — | — |

## Predeclared criterion

Outcome: **FAIL**. Summary must be within 2 correct answers of table+stats in every trial (pooled deficit ≤6), using ≤40% of its total input tokens. No renderer tuning used this suite.

Summary deficit: 138 answers pooled. Total-input ratio: 76.358%. Beside that total, descriptive chart-only tokens (input minus paired none): summary 31,623 vs table+stats 109,722, or 28.8%. Chart-only token ratio is not the predeclared criterion.

**Design flaw in the token criterion:** the ≤40% total-input target was unreachable under this prompt setup. The none arm alone uses 220,620 input tokens, 66.8% of table+stats. Keep the predeclared criterion and FAIL unchanged: the accuracy deficit independently fails it, regardless of whether common prompt overhead is subtracted.

## Wrong answers versus abstention

Summary mostly declines rather than invents: 659/840 right, 14 wrong (non-abstained), 167 abstained. Misses concentrate in point lookups it does not carry, such as scatter y-at-x and heatmap cell queries. Across all questions of those kinds:

- scatter: 60/120 right, 6 wrong, 54 abstained.
- heatmap: 85/120 right, 0 wrong, 35 abstained.

## Trial 1

| arm | correct / questions | wrong (non-abstained) | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 225/280 | 3 | 52 | 97455 | 8791 | 329.462 | 215 | 0.00576338 | 1.14195 |
| table+stats | 266/280 | 3 | 11 | 110114 | 5174 | 319.564 | 255 | 0.000560634 | 0.00393214 |
| summary | 219/280 | 5 | 56 | 84081 | 13555 | 344.375 | 212 | 0.0160698 | 0.758634 |
| text | 130/280 | 48 | 102 | 137428 | 79440 | 893.321 | 164 | 0.214119 | 2.06704 |
| hybrid | 234/280 | 3 | 43 | 101827 | 18169 | 399.746 | 223 | 0.00657016 | 0.0487558 |
| image | 252/280 | 18 | 10 | 102520 | 15698 | 206.175 | 254 | 0.0438954 | 3.24803e+07 |
| none | 0/280 | 0 | 280 | 73540 | 1890 | 294.985 | 0 | — | — |

## Trial 2

| arm | correct / questions | wrong (non-abstained) | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 226/280 | 2 | 52 | 97455 | 9176 | 315.172 | 215 | 0.00551135 | 1.13849 |
| table+stats | 265/280 | 4 | 11 | 110114 | 4757 | 300.015 | 255 | 0.00765758 | 0.0112692 |
| summary | 219/280 | 4 | 57 | 84081 | 14083 | 352.974 | 211 | 0.0156266 | 0.245639 |
| text | 125/280 | 60 | 95 | 137428 | 81709 | 952.862 | 171 | 0.172959 | 4.09357e+07 |
| hybrid | 235/280 | 4 | 41 | 101827 | 18043 | 432.598 | 224 | 0.00778575 | 0.0543417 |
| image | 254/280 | 18 | 8 | 102520 | 16743 | 219.123 | 256 | 0.0426865 | 3.22266e+07 |
| none | 0/280 | 0 | 280 | 73540 | 1895 | 249.096 | 0 | — | — |

## Trial 3

| arm | correct / questions | wrong (non-abstained) | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 226/280 | 2 | 52 | 97455 | 9169 | 221.436 | 215 | 0.0052985 | 1.1373 |
| table+stats | 266/280 | 3 | 11 | 110114 | 5153 | 167.765 | 255 | 0.00765758 | 0.0112692 |
| summary | 221/280 | 5 | 54 | 84081 | 14350 | 247.830 | 214 | 0.0160231 | 0.676775 |
| text | 125/280 | 48 | 107 | 137428 | 76900 | 781.835 | 160 | 0.10255 | 1.22174 |
| hybrid | 231/280 | 4 | 45 | 101827 | 19724 | 275.700 | 220 | 0.00847288 | 0.063057 |
| image | 250/280 | 23 | 7 | 102520 | 16165 | 217.019 | 257 | 0.101025 | 6.54864e+07 |
| none | 0/280 | 0 | 280 | 73540 | 1890 | 165.932 | 0 | — | — |

## Kind: line

| arm | correct / questions | wrong (non-abstained) | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 111/144 | 6 | 27 | 48279 | 4711 | 162.589 | 117 | 0.0295968 | 6.27186 |
| table+stats | 135/144 | 0 | 9 | 53922 | 2570 | 135.638 | 135 | 0 | 0 |
| summary | 124/144 | 2 | 18 | 41994 | 5644 | 149.150 | 126 | 0.00421431 | 0.0262061 |
| text | 58/144 | 34 | 52 | 82512 | 32426 | 421.008 | 92 | 0.100877 | 7.6087e+07 |
| hybrid | 123/144 | 3 | 18 | 48756 | 6969 | 168.197 | 126 | 0.00564267 | 0.0365236 |
| image | 133/144 | 8 | 3 | 52695 | 4326 | 85.961 | 141 | 0.222616 | 1.75532e+08 |
| none | 0/144 | 0 | 144 | 37791 | 972 | 114.871 | 0 | — | — |

## Kind: multi-line

| arm | correct / questions | wrong (non-abstained) | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 83/120 | 1 | 36 | 45627 | 6383 | 119.403 | 63 | 0.0015873 | 0.015873 |
| table+stats | 105/120 | 0 | 15 | 55377 | 3606 | 132.658 | 81 | 0 | 0 |
| summary | 96/120 | 6 | 18 | 36186 | 9151 | 163.249 | 78 | 0.0990735 | 4.33336 |
| text | 39/120 | 30 | 51 | 61641 | 38617 | 412.181 | 46 | 0.690182 | 3.91417 |
| hybrid | 98/120 | 0 | 22 | 41772 | 7274 | 151.081 | 72 | 0.0303073 | 0.166694 |
| image | 114/120 | 6 | 0 | 44430 | 9140 | 107.571 | 90 | 0.0238045 | 0.473175 |
| none | 0/120 | 0 | 120 | 32010 | 810 | 109.959 | 0 | — | — |

## Kind: bar

| arm | correct / questions | wrong (non-abstained) | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 120/120 | 0 | 0 | 38184 | 2600 | 122.448 | 120 | 0 | 0 |
| table+stats | 120/120 | 0 | 0 | 40851 | 1249 | 106.968 | 120 | 0 | 0 |
| summary | 102/120 | 0 | 18 | 36534 | 4946 | 117.366 | 102 | 0 | 0 |
| text | 104/120 | 2 | 14 | 55236 | 26525 | 284.694 | 106 | 0.00251572 | 0.0311321 |
| hybrid | 102/120 | 0 | 18 | 45438 | 7156 | 148.747 | 102 | 0 | 0 |
| image | 120/120 | 0 | 0 | 43530 | 7159 | 87.186 | 120 | 0 | 0 |
| none | 0/120 | 0 | 120 | 31110 | 810 | 97.578 | 0 | — | — |

## Kind: scatter

| arm | correct / questions | wrong (non-abstained) | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 90/120 | 0 | 30 | 39888 | 3198 | 121.583 | 90 | 0 | 0 |
| table+stats | 115/120 | 2 | 3 | 44568 | 1625 | 116.611 | 117 | 0.030935 | 0.0319822 |
| summary | 60/120 | 6 | 54 | 32997 | 4373 | 120.219 | 66 | 0.0233345 | 0.238408 |
| text | 56/120 | 23 | 41 | 43665 | 25591 | 297.348 | 79 | 0.0684495 | 0.422396 |
| hybrid | 68/120 | 6 | 46 | 37797 | 9683 | 170.402 | 74 | 0.0208118 | 0.212634 |
| image | 104/120 | 16 | 0 | 43860 | 4420 | 75.044 | 120 | 0.0907651 | 7.15e+07 |
| none | 0/120 | 0 | 120 | 31440 | 810 | 113.424 | 0 | — | — |

## Kind: heatmap

| arm | correct / questions | wrong (non-abstained) | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 75/120 | 0 | 45 | 43662 | 3388 | 113.325 | 75 | 0 | 0 |
| table+stats | 120/120 | 0 | 0 | 46431 | 1787 | 100.319 | 120 | 0 | 0 |
| summary | 85/120 | 0 | 35 | 40557 | 2799 | 118.909 | 85 | 0 | 0 |
| text | 28/120 | 5 | 87 | 66852 | 11428 | 166.461 | 33 | 0.012285 | 14.5455 |
| hybrid | 102/120 | 0 | 18 | 58341 | 6167 | 141.753 | 102 | 0 | 0 |
| image | 90/120 | 8 | 22 | 43920 | 7490 | 101.879 | 98 | 0.0171769 | 0.0693878 |
| none | 0/120 | 0 | 120 | 31500 | 810 | 81.192 | 0 | — | — |

## Kind: histogram

| arm | correct / questions | wrong (non-abstained) | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 78/96 | 0 | 18 | 34980 | 3725 | 108.357 | 78 | 0 | 0 |
| table+stats | 87/96 | 3 | 6 | 40437 | 2153 | 88.037 | 90 | 0.0047619 | 0.0333333 |
| summary | 84/96 | 0 | 12 | 27927 | 9838 | 145.174 | 84 | 0 | 0 |
| text | 42/96 | 35 | 19 | 38907 | 66441 | 640.246 | 77 | 0.0718008 | 8.36364 |
| hybrid | 89/96 | 1 | 6 | 31425 | 11136 | 152.276 | 90 | 1.23457e-05 | 0.0111111 |
| image | 82/96 | 14 | 0 | 34968 | 11438 | 110.462 | 96 | 0.0174913 | 6.54167 |
| none | 0/96 | 0 | 96 | 25032 | 653 | 96.009 | 0 | — | — |

## Kind: errorbar

| arm | correct / questions | wrong (non-abstained) | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 60/60 | 0 | 0 | 21684 | 1460 | 62.530 | 60 | 1.8826e-06 | 1.33334e-08 |
| table+stats | 60/60 | 0 | 0 | 25131 | 1188 | 49.279 | 60 | 6.9407e-07 | 3.33341e-09 |
| summary | 60/60 | 0 | 0 | 18495 | 2765 | 67.965 | 60 | 0.00556873 | 0.00752142 |
| text | 11/60 | 17 | 32 | 29571 | 17997 | 192.080 | 28 | 0.0515811 | 0.135805 |
| hybrid | 58/60 | 1 | 1 | 21423 | 4928 | 100.852 | 59 | 0.0107448 | 0.0584855 |
| image | 54/60 | 6 | 0 | 21915 | 2488 | 39.965 | 60 | 0.00416749 | 0.0103437 |
| none | 0/60 | 0 | 60 | 15705 | 405 | 45.017 | 0 | — | — |

## Kind: subplot

| arm | correct / questions | wrong (non-abstained) | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 48/48 | 0 | 0 | 16509 | 1469 | 48.076 | 36 | 0 | 0 |
| table+stats | 43/48 | 5 | 0 | 19818 | 755 | 45.110 | 36 | 0 | 0 |
| summary | 48/48 | 0 | 0 | 14253 | 2011 | 53.904 | 36 | 0 | 0 |
| text | 30/48 | 10 | 8 | 27441 | 18931 | 202.522 | 28 | 0.964752 | 0.742857 |
| hybrid | 48/48 | 0 | 0 | 16962 | 1936 | 60.703 | 36 | 0 | 0 |
| image | 47/48 | 1 | 0 | 17748 | 2052 | 28.772 | 36 | 0 | 0 |
| none | 0/48 | 0 | 48 | 12780 | 324 | 45.602 | 0 | — | — |

## Kind: pie

| arm | correct / questions | wrong (non-abstained) | abstain | input tokens | output tokens | summed wall s | numeric n | mean relative error | numeric MAE (mixed units) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| table | 12/12 | 0 | 0 | 3552 | 202 | 7.759 | 6 | 5.21739e-05 | 0.00134831 |
| table+stats | 12/12 | 0 | 0 | 3807 | 151 | 12.724 | 6 | 5.21739e-05 | 0.00134831 |
| summary | 0/12 | 0 | 12 | 3300 | 461 | 9.244 | 0 | — | — |
| text | 12/12 | 0 | 0 | 6459 | 93 | 11.479 | 6 | 0.000826087 | 0.0213483 |
| hybrid | 12/12 | 0 | 0 | 3567 | 687 | 14.033 | 6 | 0.000826087 | 0.0213483 |
| image | 12/12 | 0 | 0 | 4494 | 93 | 5.476 | 6 | 0.000826087 | 0.0213483 |
| none | 0/12 | 0 | 12 | 3252 | 81 | 6.361 | 0 | — | — |

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

## Interpretation and limits

The summary claim fails; the hybrid and human preview remain available, without a superiority claim. Direct table+stats is most accurate here; hybrid is below PNG. Repeated trials share charts and are not 840 independent charts. Questions emphasize source extrema, exact counts, missingness and point values, not open-ended analysis. Full-source stats directly support several question types. Large tables are intentionally sampled, not a full-data oracle; table+stats retains full-source aggregate statistics. Uniform source sampling can omit the queried point or heatmap spike. The 256-token metadata floor can exceed a small summary's size. This suite covers the listed kinds, not every supported artist combination (e.g. filled areas), SVG, other models or image sizes. Numeric MAE mixes units and large offsets; use per-kind relative errors and abstention counts too. Trial 3 reused input caches: costs reflect CLI list-price cache rates, while input-token totals count cached tokens in full. One parent timeout interrupted a single in-flight call; its unobservable cost is reserved at $0.10 and its retry is recorded. No subscription-limit or API-auth failure was reported.
