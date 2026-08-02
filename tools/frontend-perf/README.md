# Frontend performance gate

The `Frontend performance` workflow compares a pull request with its merge base. It runs both
revisions as isolated production compose stacks on the same GitHub runner, so it does not need a
stored baseline, database, or previous workflow artifact.

Each stack gets a new account populated with the deterministic demo ledger through the real API and
UI. Lighthouse measures Login, Budget, Transactions, and Dashboard three times with a simulated
desktop profile. A browser scenario also measures the Year-to-Month interaction and navigation from
Budget to Transactions and Dashboard. The comparator uses the median of each group of three runs.

Thresholds, routes, and scenarios live in `tools/frontend-perf/config.json`. LCP, TBT, Speed Index,
CLS, and SPA navigation use percentage tiers with an absolute noise floor. TTFB is deliberately more
tolerant: it only blocks when it more than doubles with at least 300 ms of growth, or newly enters the
poor band.

The workflow summary always contains the complete comparison. Regressions also create one sticky PR
comment, which is updated after every push and removed after all regressions are fixed. Raw Lighthouse
and navigation reports remain attached to the workflow run for seven days.

## Run locally

Install the project dependencies and Playwright Chromium, then compare the current branch:

```console
make install
cd tools/frontend-perf && npx playwright install chromium && cd ../..
make perf-front-diff BASE=origin/main
```

Docker Compose is required. Reports are written to `reports/frontend-perf` by default. A Critical
verdict exits non-zero; None, Info, and Significant verdicts pass.
