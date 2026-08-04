import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

from ci.quality_graph.checks.frontend_measurement import (
    COMMENT_MARKER,
    Entry,
    JsonValue,
    Measurement,
    classify,
    compare_measurements,
    json_object,
    load_measurements,
    main,
    median,
    render_report,
    worst_tier,
    write_error,
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

        assert classify(1000, 1090, config)[0] == "none"
        assert classify(1000, 1100, config)[0] == "info"
        assert classify(1000, 1200, config)[0] == "significant"
        assert classify(1000, 1300, config)[0] == "critical"
        assert classify(1000, 900, config)[0] == "none"

    def test_band_crossing_overrides_the_relative_tier(self) -> None:
        config = metric(good=2500, poor=4000)

        assert classify(2490, 2510, config)[0] == "none"
        assert classify(3990, 4010, config)[0] == "none"
        assert classify(2400, 2600, config) == ("significant", "crossed out of the good band")
        assert classify(3900, 4100, config) == ("critical", "crossed into the poor band")

    def test_speed_index_ignores_observed_lighthouse_jitter(self) -> None:
        config = metric(noise_absolute=200)

        assert classify(350, 499, config)[0] == "none"

    def test_lcp_ignores_observed_lighthouse_jitter(self) -> None:
        config = metric(noise_absolute=200)

        assert classify(663, 813, config)[0] == "none"

    def test_cls_uses_its_own_absolute_noise_floor(self) -> None:
        config = metric(good=0.1, poor=0.25, noise_absolute=0.01)

        assert classify(0.11, 0.119, config)[0] == "none"
        assert classify(0.1, 0.12, config)[0] == "significant"
        assert classify(0.24, 0.26, config)[0] == "critical"

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

        assert classify(20, 110, config)[0] == "none"
        assert classify(100, 300, config)[0] == "significant"
        assert classify(200, 550, config)[0] == "critical"
        assert classify(1700, 1800, config)[0] == "critical"


class MeasurementTest(unittest.TestCase):
    def test_median_requires_the_configured_number_of_runs(self) -> None:
        assert median([30, 10, 20], 3, "example") == 20
        with pytest.raises(RuntimeError, match="expected 3"):
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

        assert measurements[("login", "largest-contentful-paint")].value == 200
        assert measurements[("nav", "navigation")].value == 50


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

        assert worst_tier(entries) == "critical"

    def test_comment_has_marker_callout_and_collapsed_table(self) -> None:
        body = render_report([self.entry("significant", 200, 20)], "significant", comment=True)

        assert COMMENT_MARKER in body
        assert "> [!WARNING]" in body
        assert "<summary>Full performance report</summary>" in body
        assert "Budget | LCP" in body
        assert "Route / interaction" in body

    def test_summary_splits_navigation_and_pages_into_separate_tables(self) -> None:
        navigation = Entry(
            route_id="budget-to-dashboard",
            route_label="Budget · Year → Dashboard",
            metric_id="navigation",
            metric_label="Navigation",
            unit="ms",
            base=100,
            current=100,
            delta=0,
            delta_percent=0,
            tier="none",
            reason="same or better",
        )
        body = render_report(
            [navigation, self.entry("none", 0, 0)],
            "none",
            comment=False,
        )

        assert "### Navigation scenarios" in body
        assert "### Budget" in body
        assert "| Navigation | main | PR | Δ | Tier |" in body
        assert "| Budget · Year → Dashboard | 100 ms | 100 ms | 0 ms (+0.0%) |" in body
        assert "| Navigation | 100 ms |" not in body
        assert "Route / interaction" not in body
        assert body.count("| Metric | main | PR | Δ | Tier |") == 1

    def test_delta_uses_soft_colors_for_direction_and_black_for_zero(self) -> None:
        body = render_report(
            [
                self.entry("critical", 200, 20),
                self.entry("none", -200, -20),
                self.entry("none", 0, 0),
            ],
            "critical",
            comment=False,
        )

        assert '<font color="#c05640">+200 ms (+20.0%)</font>' in body
        assert '<font color="#2f855a">-200 ms (-20.0%)</font>' in body
        assert "| 0 ms (+0.0%) |" in body

    def test_summary_has_collapsed_blocking_standards(self) -> None:
        config: dict[str, JsonValue] = {
            "runs": 1,
            "lighthouseRoutes": [],
            "navigationScenarios": [],
            "metrics": {"navigation": metric()},
        }

        body = render_report([self.entry("none", 0, 0)], "none", comment=False, config=config)

        assert "<summary>Blocking standards</summary>" in body
        assert "more than 25% slower and at least +100 ms" in body
        assert "Measurement failure" in body
        assert body.count("<details>") == 1

    def test_summary_uses_a_human_readable_success_label(self) -> None:
        body = render_report([self.entry("none", 0, 0)], "none", comment=False)

        assert body.startswith("## ✅ Frontend performance\n")
        assert "No regressions" not in body.split("\n", 3)[0]
        assert "Raw Lighthouse and navigation reports" not in body

    def test_summary_uses_a_cross_for_critical_verdict(self) -> None:
        body = render_report([self.entry("critical", 200, 20)], "critical", comment=False)

        assert body.startswith("## ❌ Frontend performance\n")

    def test_comparison_rejects_different_measurement_sets(self) -> None:
        extra = Measurement("extra", "Extra", "navigation", "Navigation", "ms", 100)
        with pytest.raises(RuntimeError, match="differ from main"):
            compare_measurements({}, {("extra", "navigation"): extra}, {})


class CommandTest(unittest.TestCase):
    def test_error_command_writes_an_error_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            old_argv = sys.argv
            try:
                sys.argv = [
                    "frontend_perf.py",
                    "error",
                    "--output",
                    str(output),
                    "--message",
                    "collector failed",
                ]
                assert main() == 0
            finally:
                sys.argv = old_argv

            report = json.loads((output / "report.json").read_text())
            comment = (output / "comment.md").read_text()

        assert report["verdict"] == "error"
        assert report["commentRequired"]
        assert COMMENT_MARKER in comment

    def test_error_report_uses_a_safe_fence_for_backticks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            write_error(output, "collector failed with ``` in the log", 301, "sha")

            summary = (output / "summary.md").read_text()
            comment = (output / "comment.md").read_text()

        assert "````text" in summary
        assert "collector failed with ``` in the log" in summary
        assert COMMENT_MARKER in comment

    def test_main_returns_one_only_for_a_critical_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = {
                "runs": 1,
                "lighthouseRoutes": [{"id": "login", "label": "Login", "path": "/login"}],
                "navigationScenarios": [{"id": "nav", "label": "Navigation"}],
                "metrics": {"navigation": metric()},
            }
            for name in ("base", "pr"):
                directory = root / name
                (directory / "lighthouse").mkdir(parents=True)
                (directory / "navigation.json").write_text(
                    json.dumps(
                        {
                            "scenarios": [
                                {
                                    "id": "nav",
                                    "label": "Navigation",
                                    "valuesMs": [1000 if name == "base" else 1300],
                                }
                            ]
                        }
                    )
                )
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config))
            output = root / "output"
            old_argv = sys.argv
            try:
                sys.argv = [
                    "frontend_perf.py",
                    "compare",
                    "--base-dir",
                    str(root / "base"),
                    "--pr-dir",
                    str(root / "pr"),
                    "--config",
                    str(config_path),
                    "--output",
                    str(output),
                ]
                assert main() == 1
                config["metrics"] = {"navigation": {**metric(), "criticalPercent": 40}}
                config_path.write_text(json.dumps(config))
                assert main() == 0
            finally:
                sys.argv = old_argv


if __name__ == "__main__":
    unittest.main()
