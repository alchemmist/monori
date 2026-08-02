import json
import tempfile
import unittest
from pathlib import Path

from scripts.frontend_perf import (
    COMMENT_MARKER,
    Entry,
    JsonValue,
    Measurement,
    classify,
    compare_measurements,
    json_object,
    load_measurements,
    median,
    render_report,
    worst_tier,
)


def metric(
    *,
    good: float | None = None,
    poor: float | None = None,
    noise_absolute: float = 100,
) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {
        "label": "Metric",
        "unit": "ms",
        "noisePercent": 5,
        "noiseAbsolute": noise_absolute,
        "significantPercent": 10,
        "criticalPercent": 25,
    }
    if good is not None:
        result["good"] = good
    if poor is not None:
        result["poor"] = poor
    return result


class ClassificationTest(unittest.TestCase):
    def test_duration_tiers_respect_absolute_and_relative_noise(self) -> None:
        config = metric()

        self.assertEqual(classify(1000, 1090, config)[0], "none")
        self.assertEqual(classify(1000, 1100, config)[0], "info")
        self.assertEqual(classify(1000, 1200, config)[0], "significant")
        self.assertEqual(classify(1000, 1300, config)[0], "critical")
        self.assertEqual(classify(1000, 900, config)[0], "none")

    def test_band_crossing_overrides_the_relative_tier(self) -> None:
        config = metric(good=2500, poor=4000)

        self.assertEqual(classify(2490, 2510, config)[0], "none")
        self.assertEqual(classify(3990, 4010, config)[0], "none")
        self.assertEqual(
            classify(2400, 2600, config), ("significant", "crossed out of the good band")
        )
        self.assertEqual(classify(3900, 4100, config), ("critical", "crossed into the poor band"))

    def test_speed_index_ignores_observed_lighthouse_jitter(self) -> None:
        config = metric(noise_absolute=200)

        self.assertEqual(classify(350, 499, config)[0], "none")

    def test_lcp_ignores_observed_lighthouse_jitter(self) -> None:
        config = metric(noise_absolute=200)

        self.assertEqual(classify(663, 813, config)[0], "none")

    def test_cls_uses_its_own_absolute_noise_floor(self) -> None:
        config = metric(good=0.1, poor=0.25, noise_absolute=0.01)

        self.assertEqual(classify(0.11, 0.119, config)[0], "none")
        self.assertEqual(classify(0.1, 0.12, config)[0], "significant")
        self.assertEqual(classify(0.24, 0.26, config)[0], "critical")

    def test_ttfb_only_blocks_a_large_absolute_and_relative_jump(self) -> None:
        config: dict[str, JsonValue] = {
            **metric(good=800, poor=1800),
            "policy": "ttfb",
            "noisePercent": 20,
            "significantPercent": 50,
            "significantAbsolute": 200,
            "criticalPercent": 100,
            "criticalAbsolute": 300,
        }

        self.assertEqual(classify(20, 110, config)[0], "none")
        self.assertEqual(classify(100, 300, config)[0], "significant")
        self.assertEqual(classify(200, 550, config)[0], "critical")
        self.assertEqual(classify(1700, 1800, config)[0], "critical")


class MeasurementTest(unittest.TestCase):
    def test_median_requires_the_configured_number_of_runs(self) -> None:
        self.assertEqual(median([30, 10, 20], 3, "example"), 20)
        with self.assertRaisesRegex(RuntimeError, "expected 3"):
            median([10, 20], 3, "example")

    def test_loads_lighthouse_and_navigation_medians(self) -> None:
        config: dict[str, JsonValue] = {
            "runs": 3,
            "lighthouseRoutes": [{"id": "login", "label": "Login", "path": "/login"}],
            "navigationScenarios": [{"id": "nav", "label": "Navigation"}],
            "metrics": {
                "largest-contentful-paint": metric(),
                "navigation": metric(),
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lighthouse = root / "lighthouse"
            lighthouse.mkdir()
            for index, value in enumerate([300, 100, 200]):
                report = {
                    "finalUrl": "http://localhost/login",
                    "audits": {"largest-contentful-paint": {"numericValue": value}},
                }
                (lighthouse / f"report-{index}.json").write_text(json.dumps(report))
            navigation = {
                "scenarios": [{"id": "nav", "label": "Navigation", "valuesMs": [60, 40, 50]}]
            }
            (root / "navigation.json").write_text(json.dumps(navigation))

            measurements = load_measurements(root, json_object(config, "test config"))

        self.assertEqual(measurements[("login", "largest-contentful-paint")].value, 200)
        self.assertEqual(measurements[("nav", "navigation")].value, 50)


class ReportTest(unittest.TestCase):
    def entry(self, tier: str, delta: float, percent: float) -> Entry:
        return Entry(
            route_id="budget",
            route_label="Budget",
            metric_id="largest-contentful-paint",
            metric_label="LCP",
            unit="ms",
            base=1000,
            current=1000 + delta,
            delta=delta,
            delta_percent=percent,
            tier=tier,
            reason="test reason",
        )

    def test_worst_tier_wins(self) -> None:
        entries = [self.entry("info", 100, 10), self.entry("critical", 300, 30)]

        self.assertEqual(worst_tier(entries), "critical")

    def test_comment_has_marker_callout_and_collapsed_table(self) -> None:
        body = render_report([self.entry("significant", 200, 20)], "significant", comment=True)

        self.assertIn(COMMENT_MARKER, body)
        self.assertIn("> [!WARNING]", body)
        self.assertIn("<summary>Full performance report</summary>", body)
        self.assertIn("Budget · LCP", body)

    def test_comparison_rejects_different_measurement_sets(self) -> None:
        extra = Measurement("extra", "Extra", "navigation", "Navigation", "ms", 100)
        with self.assertRaisesRegex(RuntimeError, "differ from main"):
            compare_measurements({}, {("extra", "navigation"): extra}, {})


if __name__ == "__main__":
    unittest.main()
