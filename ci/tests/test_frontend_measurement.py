# Copyright (c) 2026
import json
import logging
import sys
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from monori.ci.quality_graph.checks import frontend_measurement
from monori.ci.quality_graph.checks.frontend_measurement import (
    COMMENT_MARKER,
    Entry,
    Measurement,
    PerformanceOutputContext,
    band,
    classify,
    classify_band_crossing,
    classify_relative,
    classify_ttfb,
    compare_measurements,
    config_parts,
    format_delta,
    format_delta_cell,
    format_value,
    load_lighthouse,
    load_measurements,
    load_navigation,
    main,
    median,
    parse_args,
    render_report,
    render_standards,
    report_sections,
    sorted_regressions,
    threshold,
    worst_tier,
    write_error,
    write_json,
    write_outputs,
)
from monori.common import JsonValue, object_value


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


class TestClassification:
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


class TestMeasurement:
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

            measurements = load_measurements(root, object_value(config, "test config"))

        assert measurements[("login", "largest-contentful-paint")].value == 200
        assert measurements[("nav", "navigation")].value == 50

    @pytest.mark.parametrize("runs", [True, 0, "3"])
    def test_config_rejects_invalid_run_counts(self, runs: JsonValue) -> None:
        with pytest.raises(RuntimeError, match="positive integer"):
            config_parts({"runs": runs, "lighthouseRoutes": [], "metrics": {}})

    def test_loaders_reject_unknown_and_duplicate_scenarios(self, tmp_path: Path) -> None:
        config: dict[str, JsonValue] = {
            "runs": 1,
            "lighthouseRoutes": [],
            "navigationScenarios": [{"id": "nav", "label": "Navigation"}],
            "metrics": {"navigation": metric()},
        }
        lighthouse = tmp_path / "lighthouse"
        lighthouse.mkdir()
        (lighthouse / "metadata.json").write_text("[]")
        (lighthouse / "unknown.json").write_text(
            json.dumps({"finalUrl": "http://localhost/unknown", "audits": {}})
        )
        with pytest.raises(RuntimeError, match="Unexpected Lighthouse route"):
            load_measurements(tmp_path, config)

        navigation = tmp_path / "navigation.json"
        navigation.write_text(
            json.dumps(
                {
                    "scenarios": [
                        {"id": "nav", "label": "Navigation", "valuesMs": [1]},
                        {"id": "nav", "label": "Navigation", "valuesMs": [1]},
                    ]
                }
            )
        )
        with pytest.raises(RuntimeError, match="Duplicate navigation scenario"):
            load_navigation(navigation, config)

        navigation.write_text(json.dumps({"scenarios": []}))
        with pytest.raises(RuntimeError, match="differ from config"):
            load_navigation(navigation, config)


class TestReport:
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

    def test_score_format_and_info_report_are_rendered(self) -> None:
        assert format_value(0.98765, "score") == "0.988"
        body = render_report([self.entry("info", 100, 10)], "info", comment=False)
        assert "A small regression exceeded" in body

    def test_standards_render_ttfb_and_poor_band_policies(self) -> None:
        ttfb: dict[str, JsonValue] = {
            **metric(poor=1800),
            "policy": "ttfb",
            "criticalAbsolute": 300,
        }
        regular = metric(poor=4000)
        config: dict[str, JsonValue] = {
            "runs": 1,
            "lighthouseRoutes": [],
            "metrics": {"ttfb": ttfb, "lcp": regular},
        }
        body = "\n".join(render_standards(config))
        assert "enters the poor band" in body
        assert "crosses into the poor band" in body

    def test_comparison_rejects_different_measurement_sets(self) -> None:
        extra = Measurement("extra", "Extra", "navigation", "Navigation", "ms", 100)
        with pytest.raises(RuntimeError, match="differ from main"):
            compare_measurements({}, {("extra", "navigation"): extra}, {})

    def test_rendered_report_matches_the_contract(self) -> None:
        fixture = Path("ci/tests/fixtures/frontend_measurement")
        assert (
            render_report([self.entry("critical", 10, 5)], "critical", comment=False)
            == (fixture / "critical.md").read_text()
        )
        assert (
            render_report([self.entry("significant", 10, 5)], "significant", comment=False)
            == (fixture / "significant.md").read_text()
        )
        assert (
            render_report([self.entry("info", 10, 5)], "info", comment=False)
            == (fixture / "info.md").read_text()
        )
        assert (
            render_report([self.entry("none", 0, 0)], "none", comment=False)
            == (fixture / "none.md").read_text()
        )
        assert (
            render_report([self.entry("critical", 10, 5)], "critical", comment=True)
            == (fixture / "comment.md").read_text()
        )
        config: dict[str, JsonValue] = {
            "runs": 1,
            "lighthouseRoutes": [],
            "metrics": {
                "ttfb": {**metric(poor=1800), "policy": "ttfb", "criticalAbsolute": 300},
                "lcp": metric(poor=4000),
                "cls": metric(),
            },
        }
        assert "\n".join(render_standards(config)) + "\n" == (fixture / "standards.md").read_text()
        entries = [self.entry("info", float(index), float(index)) for index in range(6)]
        body = render_report(entries, "info", comment=False)
        assert body.count("- Budget") == 5
        assert "+0 ms (+0.0%)" not in body

    def test_report_includes_standards_and_formats_scores(self) -> None:
        config: dict[str, JsonValue] = {
            "runs": 1,
            "lighthouseRoutes": [],
            "metrics": {"lcp": metric()},
        }
        body = render_report(
            [self.entry("none", 0, 0)],
            "none",
            comment=False,
            config=config,
        )
        fixture = Path("ci/tests/fixtures/frontend_measurement/with_standards.md")
        assert body == fixture.read_text()
        score = Entry(
            route_id="budget",
            route_label="Budget",
            metric_id="score",
            metric_label="Score",
            unit="score",
            base=0.9,
            current=0.95,
            delta=0.05,
            delta_percent=5,
            tier="info",
            reason="test reason",
        )
        scored = render_report([score], "info", comment=False)
        assert "Budget · Score: 0.900 → 0.950" in scored

    def test_standards_name_the_missing_field(self) -> None:
        def config(metric_body: dict[str, JsonValue]) -> dict[str, JsonValue]:
            return {"runs": 1, "lighthouseRoutes": [], "metrics": {"lcp": metric_body}}

        base = metric()
        cases = (
            ("label", "lcp label"),
            ("unit", "unit"),
            ("noiseAbsolute", "noiseAbsolute"),
            ("criticalPercent", "criticalPercent"),
        )
        for field, context in cases:
            body = dict(base)
            del body[field]
            with pytest.raises(TypeError, match=f"for {context}"):
                render_standards(config(body))
        ttfb = {**metric(poor=1800), "policy": "ttfb", "criticalAbsolute": 300}
        for field, context in (
            ("criticalPercent", "criticalPercent"),
            ("criticalAbsolute", "criticalAbsolute"),
            ("poor", "poor"),
        ):
            body = dict(ttfb)
            del body[field]
            with pytest.raises(TypeError, match=f"for {context}"):
                render_standards(config(body))
        for body in (metric(poor=4000), ttfb):
            invalid = dict(body)
            invalid["poor"] = "nope"
            with pytest.raises(TypeError, match="for poor"):
                render_standards(config(invalid))
        scored = metric(poor=1.8)
        scored["unit"] = "score"
        scored_text = "\n".join(render_standards(config(scored)))
        assert "100.000" in scored_text
        assert "1.800" in scored_text
        ttfb_score = {
            **metric(poor=1.8),
            "policy": "ttfb",
            "criticalAbsolute": 0.3,
            "unit": "score",
        }
        ttfb_text = "\n".join(render_standards(config(ttfb_score)))
        assert "0.300" in ttfb_text
        assert "1.800" in ttfb_text


class TestCommand:
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
                    "--pr-number",
                    "509",
                    "--head-sha",
                    "head-sha",
                ]
                assert main() == 0
            finally:
                sys.argv = old_argv

            report = json.loads((output / "report.json").read_text())
            comment = (output / "comment.md").read_text()

        assert report["verdict"] == "error"
        assert report["prNumber"] == 509
        assert report["headSha"] == "head-sha"
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
                    "--pr-number",
                    "509",
                    "--head-sha",
                    "head-sha",
                ]
                assert main() == 1
                report = json.loads((output / "report.json").read_text())
                assert report["prNumber"] == 509
                assert report["headSha"] == "head-sha"
                assert "Blocking standards" in (output / "summary.md").read_text()
                config["metrics"] = {"navigation": {**metric(), "criticalPercent": 40}}
                config_path.write_text(json.dumps(config))
                assert main() == 0
            finally:
                sys.argv = old_argv


class TestPolicyBoundaries:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (99, "good"),
            (100, "good"),
            (101, "needs improvement"),
            (199, "needs improvement"),
            (200, "poor"),
            (201, "poor"),
        ],
    )
    def test_band_endpoints(self, value: float, expected: str) -> None:
        assert band(value, {"good": 100, "poor": 200}) == expected

    @pytest.mark.parametrize("config", [{}, {"good": 100}, {"poor": 200}])
    def test_incomplete_bands_are_disabled(self, config: dict[str, JsonValue]) -> None:
        assert band(150, config) is None

    def test_threshold_defaults_and_explicit_zero(self) -> None:
        assert threshold({}, "noiseAbsolute") == 0
        assert threshold({}, "noiseAbsolute", 17) == 17
        assert threshold({"noiseAbsolute": None}, "noiseAbsolute", 17) == 17
        assert threshold({"noiseAbsolute": 0}, "noiseAbsolute", 17) == 0

    @pytest.mark.parametrize(
        ("base", "current", "expected"),
        [
            (900, 1000, ("significant", "crossed out of the good band")),
            (1000, 1001, None),
            (1900, 2000, ("critical", "crossed into the poor band")),
            (2000, 2100, None),
            (900, 2000, ("critical", "crossed into the poor band")),
        ],
    )
    def test_band_crossing_requires_a_new_band_and_inclusive_noise(
        self, base: float, current: float, expected: tuple[str, str] | None
    ) -> None:
        config = metric(good=900, poor=2000)
        assert classify_band_crossing(base, current, current - base, config) == expected

    @pytest.mark.parametrize(
        ("delta", "percent", "expected"),
        [
            (99, 30, ("none", "within the noise floor")),
            (100, 5, ("none", "within the noise floor")),
            (100, 6, ("info", "above the noise floor")),
            (100, 10, ("info", "above the noise floor")),
            (100, 11, ("significant", "more than 10% slower")),
            (100, 25, ("significant", "more than 10% slower")),
            (100, 26, ("critical", "more than 25% slower")),
        ],
    )
    def test_relative_threshold_endpoints(
        self, delta: float, percent: float, expected: tuple[str, str]
    ) -> None:
        assert classify_relative(delta, percent, metric()) == expected

    @pytest.mark.parametrize(
        ("delta", "percent", "expected"),
        [
            (199, 51, None),
            (200, 50, None),
            (200, 51, ("significant", "TTFB grew by more than 50% and at least 200 ms")),
            (299, 101, ("significant", "TTFB grew by more than 50% and at least 200 ms")),
            (300, 100, ("significant", "TTFB grew by more than 50% and at least 200 ms")),
            (300, 101, ("critical", "TTFB grew by more than 100% and at least 300 ms")),
        ],
    )
    def test_ttfb_threshold_endpoints(
        self, delta: float, percent: float, expected: tuple[str, str] | None
    ) -> None:
        config = {
            **metric(),
            "policy": "ttfb",
            "significantPercent": 50,
            "significantAbsolute": 200,
            "criticalPercent": 100,
            "criticalAbsolute": 300,
        }
        assert classify_ttfb(delta, percent, config) == expected
        assert classify_relative(delta, percent, config) == ("info", "above the noise floor")

    def test_unchanged_and_zero_baselines(self) -> None:
        assert classify(100, 100, metric()) == ("none", "same or better")
        assert classify(0, 100, metric()) == ("critical", "more than 25% slower")
        assert classify(-100, 100, metric()) == ("critical", "more than 25% slower")
        assert classify(1, 1.0625, metric(noise_absolute=0)) == ("info", "above the noise floor")


class TestMeasurementContracts:
    def test_lighthouse_uses_url_fallback_and_preserves_metadata(self, tmp_path: Path) -> None:
        config: dict[str, JsonValue] = {
            "runs": 1,
            "lighthouseRoutes": [
                {"id": "one", "label": "First page", "path": "/one"},
                {"id": "two", "label": "Second page", "path": "/two"},
            ],
            "metrics": {"navigation": metric(), "lcp": {"label": "Paint", "unit": "score"}},
        }
        for name, report in {
            "metadata": {"note": "not a report"},
            "array": [],
            "first": {
                "requestedUrl": "https://example.test/one?query=1",
                "audits": {"lcp": {"numericValue": 0.25}},
            },
            "second": {
                "finalUrl": "https://example.test/two#fragment",
                "requestedUrl": "https://example.test/unknown",
                "audits": {"lcp": {"numericValue": 0.75}},
            },
        }.items():
            (tmp_path / f"{name}.json").write_text(json.dumps(report))
        assert load_lighthouse(tmp_path, config) == {
            ("one", "lcp"): Measurement("one", "First page", "lcp", "Paint", "score", 0.25),
            ("two", "lcp"): Measurement("two", "Second page", "lcp", "Paint", "score", 0.75),
        }

    def test_navigation_preserves_metadata_and_names_missing_and_extra(
        self, tmp_path: Path
    ) -> None:
        config: dict[str, JsonValue] = {
            "runs": 1,
            "lighthouseRoutes": [],
            "navigationScenarios": [{"id": "nav"}],
            "metrics": {"navigation": {"label": "Duration", "unit": "score"}},
        }
        path = tmp_path / "navigation.json"
        path.write_text(
            json.dumps({"scenarios": [{"id": "nav", "label": "Journey", "valuesMs": [0.125]}]})
        )
        assert load_navigation(path, config) == {
            ("nav", "navigation"): Measurement(
                "nav", "Journey", "navigation", "Duration", "score", 0.125
            )
        }
        config["navigationScenarios"] = [{"id": "z"}, {"id": "a"}]
        with pytest.raises(RuntimeError, match=r"missing=a, z; extra=nav$"):
            load_navigation(path, config)

    def test_comparison_preserves_baseline_metadata_and_sorts_keys(self) -> None:
        first = Measurement("a", "Page A", "duration", "Duration", "ms", 1000)
        second = Measurement("b", "Page B", "duration", "Duration", "ms", 0)
        config: dict[str, JsonValue] = {
            "runs": 1,
            "lighthouseRoutes": [],
            "metrics": {"duration": metric()},
        }
        before = {("b", "duration"): second, ("a", "duration"): first}
        after = {
            ("a", "duration"): replace(first, value=1100, route_label="Changed"),
            ("b", "duration"): replace(second, value=200),
        }
        assert compare_measurements(before, after, config) == [
            Entry(
                "a",
                "Page A",
                "duration",
                "Duration",
                "ms",
                1000,
                1100,
                100,
                10,
                "info",
                "above the noise floor",
            ),
            Entry(
                "b",
                "Page B",
                "duration",
                "Duration",
                "ms",
                0,
                200,
                200,
                None,
                "critical",
                "more than 25% slower",
            ),
        ]
        with pytest.raises(RuntimeError, match=r"missing=a/duration; extra=b/duration$"):
            compare_measurements({("a", "duration"): first}, {("b", "duration"): second}, {})

    def test_median_reports_exact_run_counts(self) -> None:
        assert median([10, 40, 20, 30], 4, "duration") == 25.0
        with pytest.raises(RuntimeError, match=r"^duration has 4 runs; expected 3$"):
            median([10, 20, 30, 40], 3, "duration")


class TestOutputContracts:
    @pytest.mark.parametrize(
        ("value", "unit", "expected"),
        [
            (999, "ms", "999 ms"),
            (1000, "ms", "1.00 s"),
            (-1000, "ms", "-1.00 s"),
            (-1250, "ms", "-1.25 s"),
            (1000, "score", "1000.000"),
        ],
    )
    def test_value_format_boundaries(self, value: float, unit: str, expected: str) -> None:
        assert format_value(value, unit) == expected

    def test_regression_order_uses_tier_percent_and_absolute_delta(self) -> None:
        entry = TestReport().entry("info", 100, 10)
        new = replace(entry, delta_percent=None)
        bigger = replace(entry, delta=200)
        faster_percent = replace(entry, delta_percent=20)
        critical = replace(entry, tier="critical", delta=1, delta_percent=1)
        unchanged = replace(entry, tier="none", delta=9999)
        assert sorted_regressions([entry, critical, bigger, unchanged, faster_percent, new]) == [
            critical,
            new,
            faster_percent,
            bigger,
            entry,
        ]
        assert worst_tier([]) == "none"
        assert worst_tier([critical, entry]) == "critical"
        assert format_delta(new) == "+100 ms (new)"
        small = replace(entry, delta=0.5, unit="score", delta_percent=1)
        assert format_delta(small) == "+0.500 (+1.0%)"
        assert format_delta_cell(small) == '<font color="#c05640">+0.500 (+1.0%)</font>'

    @pytest.mark.parametrize("verdict", ["none", "info", "significant", "critical"])
    def test_output_files_and_report_metadata(self, tmp_path: Path, verdict: str) -> None:
        entry = TestReport().entry(verdict, 0 if verdict == "none" else 200, 20)
        config: dict[str, JsonValue] = {
            "runs": 1,
            "lighthouseRoutes": [],
            "metrics": {"lcp": metric()},
        }
        output = tmp_path / "nested" / "output"
        context = PerformanceOutputContext(509, "head-sha", config)
        write_outputs(output, [entry], verdict, context)
        assert {path.name for path in output.iterdir()} == {
            "report.json",
            "summary.md",
            "comment.md",
        }
        assert json.loads((output / "report.json").read_text()) == {
            "schemaVersion": 1,
            "prNumber": 509,
            "headSha": "head-sha",
            "verdict": verdict,
            "commentRequired": verdict != "none",
            "entries": [asdict(entry)],
        }
        assert (output / "summary.md").read_text() == render_report(
            [entry], verdict, comment=False, config=config
        )
        assert (output / "comment.md").read_text() == (
            "" if verdict == "none" else render_report([entry], verdict, comment=True)
        )
        write_outputs(output, [], "none", context)
        assert (output / "comment.md").read_text() == ""

    def test_json_creates_parents_and_uses_stable_readable_format(self, tmp_path: Path) -> None:
        path = tmp_path / "new" / "nested" / "report.json"
        write_json(path, {"z": 1, "a": 2})
        assert path.read_text() == '{\n  "a": 2,\n  "z": 1\n}\n'
        write_json(path, {})
        assert path.read_text() == "{}\n"

    @pytest.mark.parametrize("message", ["failed", "one ` two", "``` then ````` end"])
    def test_error_report_metadata_and_safe_fence(self, tmp_path: Path, message: str) -> None:
        output = tmp_path / "errors" / "nested"
        write_error(output, message, 509, "head-sha")
        assert json.loads((output / "report.json").read_text()) == {
            "schemaVersion": 1,
            "prNumber": 509,
            "headSha": "head-sha",
            "verdict": "error",
            "commentRequired": True,
            "message": message,
            "entries": [],
        }
        fence = "``````" if "`````" in message else "```"
        assert {path.name for path in output.iterdir()} == {
            "report.json",
            "summary.md",
            "comment.md",
        }
        assert (output / "summary.md").read_text() == (
            "## Frontend performance\n\n"
            "### ❌ Measurement failure\n\n"
            "The performance comparison could not finish. This is an infrastructure or "
            "measurement failure, not a detected product regression.\n\n"
            f"{fence}text\n{message}\n{fence}\n"
        )
        assert (output / "comment.md").read_text() == (
            f"{COMMENT_MARKER}\n"
            "## ❌ Frontend performance — measurement failure\n\n"
            "> [!CAUTION]\n"
            "> The performance comparison could not finish. Check the workflow logs and rerun it; "
            "this does not mean that a product regression was measured.\n"
        )
        write_error(output, message, 509, "head-sha")

    @pytest.mark.parametrize("command", ["compare", "error"])
    def test_parser_converts_paths_and_metadata(
        self, monkeypatch: pytest.MonkeyPatch, command: str
    ) -> None:
        arguments = [
            "frontend_measurement",
            command,
            "--output",
            "out",
            "--pr-number",
            "509",
            "--head-sha",
            "head-sha",
        ]
        arguments += (
            ["--base-dir", "base", "--pr-dir", "pr", "--config", "config.json"]
            if command == "compare"
            else ["--message", "failed"]
        )
        monkeypatch.setattr(sys, "argv", arguments)
        args = parse_args()
        expected = {
            "command": command,
            "output": Path("out"),
            "pr_number": 509,
            "head_sha": "head-sha",
        }
        expected.update(
            {"base_dir": Path("base"), "pr_dir": Path("pr"), "config": Path("config.json")}
            if command == "compare"
            else {"message": "failed"}
        )
        assert vars(args) == expected


class TestInvalidMeasurements:
    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("runs", -1, "config.runs must be a positive integer"),
            ("lighthouseRoutes", None, "Expected JSON array for lighthouseRoutes"),
            ("lighthouseRoutes", [None], "Expected JSON object for lighthouse route"),
            ("metrics", None, "Expected JSON object for metrics"),
            ("metrics", {"lcp": None}, "Expected JSON object for metric lcp"),
        ],
    )
    def test_config_diagnostics(self, field: str, value: JsonValue, message: str) -> None:
        config: dict[str, JsonValue] = {"runs": 1, "lighthouseRoutes": [], "metrics": {}}
        config[field] = value
        with pytest.raises((TypeError, RuntimeError)) as error:
            config_parts(config)
        assert str(error.value) == message

    @pytest.mark.parametrize(
        ("field", "message"),
        [
            ("path", "Expected JSON string for route path"),
            ("id", "Expected JSON string for route id"),
            ("label", "Expected JSON string for route label"),
            ("metric_label", "Expected JSON string for lcp label"),
            ("unit", "Expected JSON string for lcp unit"),
            ("url", "Expected JSON string for Lighthouse URL"),
            ("audits", "Expected JSON object for Lighthouse audits"),
            ("lcp", "Expected JSON object for Lighthouse audit lcp"),
            ("value", "Expected JSON number for lcp.numericValue"),
            ("missing_report", "Page Paint has 0 runs; expected 1"),
        ],
    )
    def test_lighthouse_diagnostics(self, tmp_path: Path, field: str, message: str) -> None:
        route: dict[str, JsonValue] = {"id": "page", "path": "/page", "label": "Page"}
        definition: dict[str, JsonValue] = {"label": "Paint", "unit": "ms"}
        audit: dict[str, JsonValue] = {"numericValue": 1}
        audits: dict[str, JsonValue] = {"lcp": audit}
        report: dict[str, JsonValue] = {"finalUrl": "https://example.test/page", "audits": audits}
        config: dict[str, JsonValue] = {
            "runs": 1,
            "lighthouseRoutes": [route],
            "metrics": {"lcp": definition},
        }
        if field in {"path", "id", "label"}:
            route[field] = None
        elif field in {"metric_label", "unit"}:
            definition["label" if field == "metric_label" else field] = None
        elif field == "url":
            report["finalUrl"] = None
        elif field == "audits":
            report["audits"] = None
        elif field == "lcp":
            audits["lcp"] = None
        elif field == "value":
            audit["numericValue"] = None
        if field != "missing_report":
            (tmp_path / "report.json").write_text(json.dumps(report))
        with pytest.raises((TypeError, RuntimeError)) as error:
            load_lighthouse(tmp_path, config)
        assert str(error.value) == message

    @pytest.mark.parametrize(
        ("field", "message"),
        [
            ("root", "Expected JSON object for {path}"),
            ("scenarios", "Expected JSON array for navigation scenarios"),
            ("scenario", "Expected JSON object for navigation scenario"),
            ("id", "Expected JSON string for navigation scenario id"),
            ("label", "Expected JSON string for navigation scenario label"),
            ("valuesMs", "Expected JSON array for Journey values"),
            ("value", "Expected JSON number for Journey duration"),
            ("metric_label", "Expected JSON string for navigation label"),
            ("unit", "Expected JSON string for navigation unit"),
            ("run_count", "Journey has 0 runs; expected 1"),
            ("configured", "Expected JSON array for navigationScenarios"),
            ("configured_scenario", "Expected JSON object for configured navigation scenario"),
            ("configured_id", "Expected JSON string for configured navigation id"),
        ],
    )
    def test_navigation_diagnostics(self, tmp_path: Path, field: str, message: str) -> None:
        scenario: dict[str, JsonValue] = {"id": "nav", "label": "Journey", "valuesMs": [1]}
        definition: dict[str, JsonValue] = {"label": "Duration", "unit": "ms"}
        config: dict[str, JsonValue] = {
            "runs": 1,
            "lighthouseRoutes": [],
            "navigationScenarios": [{"id": "nav"}],
            "metrics": {"navigation": definition},
        }
        root: dict[str, JsonValue] = {"scenarios": [scenario]}
        if field in {"id", "label", "valuesMs"}:
            scenario[field] = None
        elif field in {"metric_label", "unit"}:
            definition["label" if field == "metric_label" else field] = None
        elif field == "value":
            scenario["valuesMs"] = [True]
        elif field == "run_count":
            scenario["valuesMs"] = []
        elif field in {"scenarios", "scenario"}:
            root["scenarios"] = None if field == "scenarios" else [None]
        elif field.startswith("configured"):
            invalid_configured: dict[str, JsonValue] = {
                "configured": None,
                "configured_scenario": [None],
                "configured_id": [{}],
            }
            config["navigationScenarios"] = invalid_configured[field]
        path = tmp_path / "navigation.json"
        path.write_text(json.dumps(None if field == "root" else root))
        with pytest.raises((TypeError, RuntimeError)) as error:
            load_navigation(path, config)
        assert str(error.value) == message.format(path=path)

    @pytest.mark.parametrize("field", ["good", "poor"])
    def test_invalid_bands_name_the_field(self, field: str) -> None:
        config: dict[str, JsonValue] = {"good": 100, "poor": 200}
        config[field] = "invalid"
        with pytest.raises(TypeError) as error:
            band(150, config)
        assert str(error.value) == f"Expected JSON number for {field} band"
        with pytest.raises(TypeError) as error:
            threshold({field: "invalid"}, field)
        assert str(error.value) == f"Expected JSON number for {field}"


class TestArgumentRequirements:
    @pytest.mark.parametrize(
        ("command", "missing"),
        [
            ("compare", "--base-dir"),
            ("compare", "--pr-dir"),
            ("compare", "--config"),
            ("compare", "--output"),
            ("error", "--output"),
            ("error", "--message"),
        ],
    )
    def test_required_options(
        self, monkeypatch: pytest.MonkeyPatch, command: str, missing: str
    ) -> None:
        options = (
            ["--base-dir", "base", "--pr-dir", "pr", "--config", "config.json", "--output", "out"]
            if command == "compare"
            else ["--output", "out", "--message", "failed"]
        )
        index = options.index(missing)
        del options[index : index + 2]
        monkeypatch.setattr(sys, "argv", ["frontend_measurement", command, *options])
        with pytest.raises(SystemExit) as error:
            parse_args()
        assert error.value.code == 2

    def test_command_is_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["frontend_measurement"])
        with pytest.raises(SystemExit) as error:
            parse_args()
        assert error.value.code == 2

    @pytest.mark.parametrize("command", ["compare", "error"])
    def test_metadata_defaults(self, monkeypatch: pytest.MonkeyPatch, command: str) -> None:
        options = (
            ["--base-dir", "base", "--pr-dir", "pr", "--config", "config.json", "--output", "out"]
            if command == "compare"
            else ["--output", "out", "--message", "failed"]
        )
        monkeypatch.setattr(sys, "argv", ["frontend_measurement", command, *options])
        args = parse_args()
        assert args.pr_number == 0
        assert args.head_sha == ""


@pytest.mark.parametrize(
    ("configured", "measured", "expected"),
    [(["nav"], [], "missing=nav; extra=none"), ([], ["z", "a"], "missing=none; extra=a, z")],
)
def test_navigation_set_diagnostics(
    tmp_path: Path, configured: list[str], measured: list[str], expected: str
) -> None:
    config: dict[str, JsonValue] = {
        "runs": 1,
        "lighthouseRoutes": [],
        "metrics": {"navigation": metric()},
        "navigationScenarios": [{"id": item} for item in configured],
    }
    path = tmp_path / "navigation.json"
    path.write_text(
        json.dumps(
            {"scenarios": [{"id": item, "label": item, "valuesMs": [1]} for item in measured]}
        )
    )
    with pytest.raises(RuntimeError) as error:
        load_navigation(path, config)
    assert str(error.value) == f"Navigation scenarios differ from config; {expected}"


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (["b", "a"], [], "missing=a/navigation, b/navigation; extra=none"),
        ([], ["b", "a"], "missing=none; extra=a/navigation, b/navigation"),
    ],
)
def test_comparison_set_diagnostics(before: list[str], after: list[str], expected: str) -> None:
    def measurements(ids: list[str]) -> dict[tuple[str, str], Measurement]:
        return {
            (item, "navigation"): Measurement(item, item, "navigation", "Nav", "ms", 1)
            for item in ids
        }

    with pytest.raises(RuntimeError) as error:
        compare_measurements(measurements(before), measurements(after), {})
    assert str(error.value) == f"PR measurements differ from main; {expected}"


def test_sections_preserve_page_groups_and_score_units() -> None:
    entry = TestReport().entry("none", 0, 0)
    navigation = replace(entry, route_id="nav", route_label="Journey", metric_id="navigation")
    score = replace(
        entry,
        route_id="other",
        route_label="Other",
        metric_label="Score",
        unit="score",
        base=0.5,
        current=0.5,
    )
    assert report_sections([navigation, entry, score]) == [
        "### Navigation scenarios",
        "",
        "| Navigation | main | PR | Δ | Tier |",
        "| --- | ---: | ---: | ---: | --- |",
        "| Journey | 1.00 s | 1.00 s | 0 ms (+0.0%) | ✔ No regressions |",
        "",
        "### Budget",
        "",
        "| Metric | main | PR | Δ | Tier |",
        "| --- | ---: | ---: | ---: | --- |",
        "| LCP | 1.00 s | 1.00 s | 0 ms (+0.0%) | ✔ No regressions |",
        "",
        "### Other",
        "",
        "| Metric | main | PR | Δ | Tier |",
        "| --- | ---: | ---: | ---: | --- |",
        "| Score | 0.500 | 0.500 | 0.000 (+0.0%) | ✔ No regressions |",
        "",
    ]


def test_compare_command_rejects_non_object_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    path.write_text("[]")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "frontend_measurement",
            "compare",
            "--base-dir",
            "base",
            "--pr-dir",
            "pr",
            "--config",
            str(path),
            "--output",
            "out",
        ],
    )
    with pytest.raises(TypeError) as error:
        main()
    assert str(error.value) == "Expected JSON object for config"


def test_lighthouse_validates_route_id_even_without_reports(tmp_path: Path) -> None:
    config: dict[str, JsonValue] = {
        "runs": 1,
        "lighthouseRoutes": [{"path": "/page", "label": "Page"}],
        "metrics": {"lcp": metric()},
    }
    with pytest.raises(TypeError) as error:
        load_lighthouse(tmp_path, config)
    assert str(error.value) == "Expected JSON string for route id"


def test_measurement_loader_uses_the_collector_artifact_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths: list[Path] = []
    config: dict[str, JsonValue] = {"runs": 1}
    page = Measurement("page", "Page", "lcp", "Paint", "ms", 10)
    navigation = Measurement("nav", "Journey", "navigation", "Duration", "ms", 20)

    def lighthouse_loader(
        path: Path, passed_config: dict[str, JsonValue]
    ) -> dict[tuple[str, str], Measurement]:
        paths.append(path)
        assert passed_config == config
        return {("page", "lcp"): page}

    def navigation_loader(
        path: Path, passed_config: dict[str, JsonValue]
    ) -> dict[tuple[str, str], Measurement]:
        paths.append(path)
        assert passed_config == config
        return {("nav", "navigation"): navigation}

    monkeypatch.setattr(frontend_measurement, "load_lighthouse", lighthouse_loader)
    monkeypatch.setattr(frontend_measurement, "load_navigation", navigation_loader)
    assert load_measurements(tmp_path, config) == {
        ("page", "lcp"): page,
        ("nav", "navigation"): navigation,
    }
    assert paths == [tmp_path / "lighthouse", tmp_path / "navigation.json"]


def test_command_initializes_plain_info_logging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, str | int]] = []

    def configure(**kwargs: str | int) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(logging, "basicConfig", configure)
    monkeypatch.setattr(
        sys,
        "argv",
        ["frontend_measurement", "error", "--output", str(tmp_path), "--message", "failed"],
    )
    assert main() == 0
    assert calls == [{"level": logging.INFO, "format": "%(message)s"}]
