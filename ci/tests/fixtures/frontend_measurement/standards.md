<details>
<summary>Blocking standards</summary>

The CI fails only for a Critical verdict or a measurement failure. None, Info, and Significant verdicts remain green.

- **Metric:** more than 25% slower and at least +300 ms, or enters the poor band (≥ 1.80 s) with at least +100 ms.
- **Metric:** more than 25% slower and at least +100 ms, or crosses into the poor band (≥ 4.00 s) after clearing +100 ms.
- **Metric:** more than 25% slower and at least +100 ms.
- **Measurement failure:** the collector or comparator exits with status 2 and the CI fails; this is reported separately from a product regression.

</details>
