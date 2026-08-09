# Performance baseline

Measured on 2026-08-07 on an Apple Silicon macOS host with Podman 6.0.2 and a Linux VM limited to approximately 2 GB RAM. The e2e rows were remeasured on 2026-08-10 after adding per-iteration authentication. Backend scenarios used k6 2.0.0, a deterministic 500-transaction seed, 30 seconds per level, and 10, 25, and 50 virtual users. Frontend values are medians of three production-build runs.

These are reference-host results, not portable capacity claims. Compare future measurements on the same host class, runtime, VM limits, seed, and scenario duration.

## Backend and full-stack results

| Journal | Workload | VUs | RPS | p95 ms | p99 ms | Errors | CPU-s | Peak RAM MB | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| DELETE | auth | 10 | 12.4 | 807 | 1621 | 0.00% | 104.2 | 699.1 | fail |
| DELETE | auth | 25 | 0.6 | 1164 | 1164 | 100.00% | 107.3 | 91.8 | fail |
| DELETE | auth | 50 | 1.7 | 4277 | 4278 | 71.43% | 12.9 | 1354.9 | fail |
| DELETE | read | 10 | 85.7 | 86 | 135 | 0.00% | 14.8 | 169.1 | pass |
| DELETE | read | 25 | 140.7 | 326 | 731 | 0.00% | 27.4 | 185.8 | fail |
| DELETE | read | 50 | 127.3 | 1369 | 1939 | 0.00% | 32.0 | 208.7 | fail |
| DELETE | write | 10 | 136.2 | 49 | 96 | 0.00% | 9.9 | 206.5 | pass |
| DELETE | write | 25 | 237.2 | 353 | 661 | 0.00% | 21.1 | 205.2 | pass |
| DELETE | write | 50 | 183.5 | 1759 | 3056 | 0.00% | 26.8 | 208.9 | fail |
| DELETE | import | 10 | 22.7 | 2545 | 4313 | 0.00% | 30.1 | 228.8 | pass |
| DELETE | import | 25 | 21.6 | 5629 | 6924 | 2.55% | 31.3 | 265.6 | fail |
| DELETE | import | 50 | 22.9 | 9089 | 10788 | 6.99% | 32.5 | 304.4 | fail |
| DELETE | e2e | 10 | 74.8 | 564 | 630 | 0.00% | 58.5 | 297.8 | pass |
| DELETE | e2e | 25 | 87.3 | 2569 | 3582 | 0.00% | 77.1 | 1022.7 | pass |
| DELETE | e2e | 50 | 1.2 | 467 | 467 | 100.00% | 136.1 | 155.9 | fail |
| WAL | write | 10 | 80.9 | 451 | 901 | 0.00% | 20.5 | 96.2 | pass |
| WAL | write | 25 | 106.4 | 1615 | 2404 | 0.00% | 24.9 | 105.6 | fail |
| WAL | write | 50 | 96.3 | 3959 | 5283 | 0.00% | 24.5 | 114.4 | fail |

The first threshold failures put the reference saturation points at below 10 VUs for authentication, 10 VUs for reads and imports, and 25 VUs for writes and the full-stack journey. Authentication is dominated by password hashing and exhausted the constrained VM at higher concurrency. The 25-VU read result missed the 300 ms p95 SLO narrowly at 326 ms.

On this run, WAL did not improve the mixed write scenario: DELETE passed through 25 VUs while WAL first failed there. The journal-mode runs were sequential on a shared development host, so the comparison is directional and should be repeated on an isolated runner before changing the production default.

## Frontend results

| Route | LCP ms | TBT ms | CLS | TTI ms | Main thread ms | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Login | 135 | 0 | 0.000 | 171 | 2052 | pass |
| Welcome | 212 | 141 | 0.000 | 357 | 2842 | pass |
| Budget · Year | 813 | 42 | 0.000 | 813 | 631 | pass |
| Dashboard | 963 | 509 | 0.000 | 963 | 1779 | pass |
| Transactions | 663 | 211 | 0.000 | 663 | 910 | pass |
| Accounts | 813 | 35 | 0.000 | 813 | 489 | pass |
| Categories | 663 | 68 | 0.000 | 663 | 630 | pass |
| Settings | 663 | 61 | 0.000 | 663 | 574 | pass |

Dashboard exceeded the general 300 ms TBT target at 509 ms but passed its explicit 2-second debt budget. Transactions has a corresponding 800 ms TBT debt budget for GitHub runners. All measured routes passed the 2.5 second LCP and 0.1 CLS targets. Budget Year-to-Month interaction took 298 ms; navigation from Budget Year to Transactions took 134 ms and to Dashboard took 840 ms. Interaction, TTI, and main-thread values are report-only until enough stable measurements exist to set meaningful gates.
