## ⚠️ Frontend performance

> [!WARNING]
> Runtime performance regressed noticeably. The check still passes, but the change should be reviewed.

**Biggest regressions:**

- Budget · LCP: 1.00 s → 1.01 s · +10 ms (+5.0%) — test reason

### Budget

| Metric | main | PR | Δ | Tier |
| --- | ---: | ---: | ---: | --- |
| LCP | 1.00 s | 1.01 s | <font color="#c05640">+10 ms (+5.0%)</font> | ⚠ Significant |
