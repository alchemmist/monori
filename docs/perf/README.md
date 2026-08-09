# Performance testing

The performance suite exercises the production nginx, FastAPI, SQLite, and built frontend images in the isolated compose stack. It never calls the T-Bank connector.

## Run it

Install the project dependencies and Playwright Chromium once:

```console
make install
cd tools/frontend-perf && npx playwright install chromium
```

Run the complete baseline or one layer:

```console
make load
make load-api
make load-api-read
make load-api-write
make load-api-import
make load-e2e
make load-fe
make load-sqlite
```

Docker Compose is used by default. Podman users can pass `COMPOSE="podman compose --in-pod=false"`. `LOAD_LEVELS="10 25 50 75 100"` changes the concurrency ladder and `LOAD_DURATION=1m` changes the time spent at each level. Raw k6 summaries, logs, Lighthouse reports, navigation timings, and container resource samples are written to `reports/perf`.

The `Performance suite` GitHub workflow exposes the concurrency levels and duration as manual inputs and uploads every report as an artifact. It is deliberately absent from pull-request and scheduled triggers because measurements are resource-heavy and runner-dependent.

## Workloads and SLOs

`auth` measures password verification and token creation. `read` measures the light snapshot used by Budget, Year grid, and Dashboard plus paginated transaction reads. `write` changes a budget, creates a transaction, and categorizes it. `import` parses and commits a deterministic 25-row statement. `e2e` runs the full API journey through nginx: Budget read, budget assignment, statement preview and commit, then Dashboard read.

Read p95 must stay below 300 ms, write p95 below 800 ms, import p95 below 3 seconds, and operation errors below 0.5%. A concurrency level passes only when every coded k6 threshold passes. The saturation point is the highest passing level before the first failure. The frontend target is LCP below 2.5 seconds, TBT below 300 ms, and CLS below 0.1. TTI, main-thread time, and interaction timings are explicitly report-only and excluded from the verdict.

Dashboard and Year grid have no dedicated backend aggregate endpoint; both derive their views from `/api/snapshot`, so the read scenario measures that source path. Monori stores account currency labels but has no exchange-rate API, so there is no currency-rate endpoint to load-test yet.

## Read the reports

`summary.md` contains RPS, latency percentiles, error rate, integrated CPU-seconds, and peak combined RAM for the backend and frontend containers. Compare results only on the same host class and architecture. CPU-seconds are integrated from one-second container-stat samples, so very short smoke runs are directional rather than precise.

`frontend.md` reports the median of three Lighthouse or Playwright runs per route and metric. Bundle weight stays in the separate bundle-size gate and is not duplicated here.

The deterministic seed contains 500 transactions, two category groups, two categories, and twelve budget cells. Import descriptions include the virtual user and iteration so load-generated rows remain unique while the initial dataset stays identical.

## Change an SLO

Backend thresholds live in `performance/k6/api.js` and `performance/k6/journey.js`. Frontend budgets and route coverage live in `tools/frontend-perf/config.json`; the absolute interaction target lives in `tools/frontend-perf/baseline.mjs`. Update the coded threshold and this document together, then replace `baseline.md` with a complete run from the same reference host.
