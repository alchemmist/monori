"""Compare frontend performance measurements and render the CI report."""

import argparse
import json
import logging
import re
import statistics
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path

from monori.common import JsonValue, array_value, number_value, object_value, string_value

type MeasurementKey = tuple[str, str]

SCHEMA_VERSION = 1
TIERS = {"none": 0, "info": 1, "significant": 2, "critical": 3, "error": 4}
TIER_LABELS = {
    "none": "No regressions",
    "info": "Info",
    "significant": "Significant",
    "critical": "Critical",
    "error": "Measurement failure",
}
MS_PER_SECOND = 1000
TIER_EMOJI = {
    "none": "✅",
    "info": "💬",
    "significant": "⚠️",
    "critical": "❌",
    "error": "❌",
}
COMMENT_MARKER = "<!-- monori-frontend-performance -->"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Measurement:
    """One measured run for a specific metric and route."""

    route_id: str
    route_label: str
    metric_id: str
    metric_label: str
    unit: str
    value: float


@dataclass(frozen=True)
class Entry:
    """Single metric comparison row used in performance summary output."""

    route_id: str
    route_label: str
    metric_id: str
    metric_label: str
    unit: str
    base: float
    current: float
    delta: float
    delta_percent: float | None
    tier: str
    reason: str


@dataclass(frozen=True)
class PerformanceOutputContext:
    """Metadata and configuration used to render performance outputs."""

    pr_number: int
    head_sha: str
    config: dict[str, JsonValue]


def decode_json(path: Path) -> JsonValue:
    """Decode json."""
    value: JsonValue = json.loads(path.read_text())
    return value


def config_parts(
    config: dict[str, JsonValue],
) -> tuple[int, list[dict[str, JsonValue]], dict[str, dict[str, JsonValue]]]:
    """Validate and return run count, Lighthouse routes, and metric definitions."""
    raw_runs = config.get("runs")
    if isinstance(raw_runs, bool) or not isinstance(raw_runs, int) or raw_runs < 1:
        message = "config.runs must be a positive integer"
        raise RuntimeError(message)
    routes = [
        object_value(route, "lighthouse route")
        for route in array_value(config.get("lighthouseRoutes"), "lighthouseRoutes")
    ]
    raw_metrics = object_value(config.get("metrics"), "metrics")
    metrics = {
        metric_id: object_value(metric, f"metric {metric_id}")
        for metric_id, metric in raw_metrics.items()
    }
    return raw_runs, routes, metrics


def median(values: list[float], expected_runs: int, context: str) -> float:
    """Return the median after verifying that every configured run produced a value."""
    if len(values) != expected_runs:
        message = f"{context} has {len(values)} runs; expected {expected_runs}"
        raise RuntimeError(message)
    return float(statistics.median(values))


def load_lighthouse(
    directory: Path, config: dict[str, JsonValue]
) -> dict[MeasurementKey, Measurement]:
    """Load lighthouse."""
    runs, routes, metrics = config_parts(config)
    route_by_path = {string_value(route.get("path"), "route path"): route for route in routes}
    values: dict[MeasurementKey, list[float]] = {}

    for report_path in sorted(directory.glob("*.json")):
        raw = decode_json(report_path)
        if not isinstance(raw, dict) or "audits" not in raw:
            continue
        report = object_value(raw, str(report_path))
        raw_url = report.get("finalUrl") or report.get("requestedUrl")
        route_path = urllib.parse.urlparse(string_value(raw_url, "Lighthouse URL")).path
        route = route_by_path.get(route_path)
        if route is None:
            message = f"Unexpected Lighthouse route {route_path}"
            raise RuntimeError(message)
        route_id = string_value(route.get("id"), "route id")
        audits = object_value(report.get("audits"), "Lighthouse audits")
        for metric_id in metrics:
            if metric_id == "navigation":
                continue
            audit = object_value(audits.get(metric_id), f"Lighthouse audit {metric_id}")
            value = number_value(audit.get("numericValue"), f"{metric_id}.numericValue")
            values.setdefault((route_id, metric_id), []).append(value)

    measurements: dict[MeasurementKey, Measurement] = {}
    for route in routes:
        route_id = string_value(route.get("id"), "route id")
        route_label = string_value(route.get("label"), "route label")
        for metric_id, metric in metrics.items():
            if metric_id == "navigation":
                continue
            metric_label = string_value(metric.get("label"), f"{metric_id} label")
            unit = string_value(metric.get("unit"), f"{metric_id} unit")
            key = (route_id, metric_id)
            measurements[key] = Measurement(
                route_id=route_id,
                route_label=route_label,
                metric_id=metric_id,
                metric_label=metric_label,
                unit=unit,
                value=median(values.get(key, []), runs, f"{route_label} {metric_label}"),
            )
    return measurements


def load_navigation(path: Path, config: dict[str, JsonValue]) -> dict[MeasurementKey, Measurement]:
    """Load navigation."""
    runs, _, metrics = config_parts(config)
    navigation_metric = metrics["navigation"]
    root = object_value(decode_json(path), str(path))
    scenarios = array_value(root.get("scenarios"), "navigation scenarios")
    measurements: dict[MeasurementKey, Measurement] = {}
    for raw_scenario in scenarios:
        scenario = object_value(raw_scenario, "navigation scenario")
        scenario_id = string_value(scenario.get("id"), "navigation scenario id")
        label = string_value(scenario.get("label"), "navigation scenario label")
        values = [
            number_value(value, f"{label} duration")
            for value in array_value(scenario.get("valuesMs"), f"{label} values")
        ]
        key = (scenario_id, "navigation")
        if key in measurements:
            message = f"Duplicate navigation scenario {scenario_id}"
            raise RuntimeError(message)
        measurements[key] = Measurement(
            route_id=scenario_id,
            route_label=label,
            metric_id="navigation",
            metric_label=string_value(navigation_metric.get("label"), "navigation label"),
            unit=string_value(navigation_metric.get("unit"), "navigation unit"),
            value=median(values, runs, label),
        )

    configured = {
        string_value(
            object_value(scenario, "configured navigation scenario").get("id"),
            "configured navigation id",
        )
        for scenario in array_value(config.get("navigationScenarios"), "navigationScenarios")
    }
    measured = {route_id for route_id, _ in measurements}
    if measured != configured:
        missing = ", ".join(sorted(configured - measured)) or "none"
        extra = ", ".join(sorted(measured - configured)) or "none"
        message = f"Navigation scenarios differ from config; missing={missing}; extra={extra}"
        raise RuntimeError(message)
    return measurements


def load_measurements(
    directory: Path, config: dict[str, JsonValue]
) -> dict[MeasurementKey, Measurement]:
    """Load measurements."""
    lighthouse = load_lighthouse(directory / "lighthouse", config)
    navigation = load_navigation(directory / "navigation.json", config)
    return lighthouse | navigation


def band(value: float, metric: dict[str, JsonValue]) -> str | None:
    """Return the configured performance band for a value, if bands are defined."""
    raw_good = metric.get("good")
    raw_poor = metric.get("poor")
    if raw_good is None or raw_poor is None:
        return None
    good = number_value(raw_good, "good band")
    poor = number_value(raw_poor, "poor band")
    if value <= good:
        return "good"
    if value >= poor:
        return "poor"
    return "needs improvement"


def threshold(metric: dict[str, JsonValue], name: str, default: float = 0) -> float:
    """Return a numeric metric threshold or its default when omitted."""
    raw = metric.get(name)
    return default if raw is None else number_value(raw, name)


def classify_band_crossing(
    base: float, current: float, delta: float, metric: dict[str, JsonValue]
) -> tuple[str, str] | None:
    """Classify a regression that crosses a configured performance band."""
    base_band = band(base, metric)
    current_band = band(current, metric)
    absolute_noise = threshold(metric, "noiseAbsolute")
    if current_band == "poor" and base_band != "poor" and delta >= absolute_noise:
        return "critical", "crossed into the poor band"
    if base_band == "good" and current_band == "needs improvement" and delta >= absolute_noise:
        return "significant", "crossed out of the good band"
    return None


def classify_ttfb(
    delta: float, delta_percent: float, metric: dict[str, JsonValue]
) -> tuple[str, str] | None:
    """Classify a TTFB regression using both relative and absolute thresholds."""
    if metric.get("policy") != "ttfb":
        return None
    critical_percent = threshold(metric, "criticalPercent")
    critical_absolute = threshold(metric, "criticalAbsolute")
    significant_percent = threshold(metric, "significantPercent")
    significant_absolute = threshold(metric, "significantAbsolute")
    if delta_percent > critical_percent and delta >= critical_absolute:
        return "critical", (
            f"TTFB grew by more than {critical_percent:.0f}% "
            f"and at least {critical_absolute:.0f} ms"
        )
    if delta_percent > significant_percent and delta >= significant_absolute:
        return "significant", (
            f"TTFB grew by more than {significant_percent:.0f}% "
            f"and at least {significant_absolute:.0f} ms"
        )
    return None


def classify_relative(
    delta: float, delta_percent: float, metric: dict[str, JsonValue]
) -> tuple[str, str]:
    """Classify a regression against noise and relative thresholds."""
    absolute_noise = threshold(metric, "noiseAbsolute")
    if delta_percent <= threshold(metric, "noisePercent") or delta < absolute_noise:
        return "none", "within the noise floor"
    if metric.get("policy") != "ttfb":
        critical_percent = threshold(metric, "criticalPercent")
        if delta_percent > critical_percent:
            return "critical", f"more than {critical_percent:.0f}% slower"
        significant_percent = threshold(metric, "significantPercent")
        if delta_percent > significant_percent:
            return "significant", f"more than {significant_percent:.0f}% slower"
    return "info", "above the noise floor"


def classify(base: float, current: float, metric: dict[str, JsonValue]) -> tuple[str, str]:
    """Classify a performance change using configured bands and thresholds."""
    delta = current - base
    if delta <= 0:
        return "none", "same or better"

    band_result = classify_band_crossing(base, current, delta, metric)
    if band_result is not None:
        return band_result

    delta_percent = float("inf") if base <= 0 else delta / base * 100
    ttfb_result = classify_ttfb(delta, delta_percent, metric)
    if ttfb_result is not None:
        return ttfb_result
    return classify_relative(delta, delta_percent, metric)


def compare_measurements(
    base: dict[MeasurementKey, Measurement],
    current: dict[MeasurementKey, Measurement],
    config: dict[str, JsonValue],
) -> list[Entry]:
    """Compare matching baseline and PR measurements and classify every delta."""
    if set(base) != set(current):
        missing = ", ".join(
            f"{route}/{metric}" for route, metric in sorted(set(base) - set(current))
        )
        extra = ", ".join(f"{route}/{metric}" for route, metric in sorted(set(current) - set(base)))
        message = (
            "PR measurements differ from main; "
            f"missing={missing or 'none'}; extra={extra or 'none'}"
        )
        raise RuntimeError(message)

    _, _, metrics = config_parts(config)
    entries: list[Entry] = []
    for key in sorted(base):
        before = base[key]
        after = current[key]
        metric = metrics[before.metric_id]
        tier, reason = classify(before.value, after.value, metric)
        delta = after.value - before.value
        delta_percent = None if before.value == 0 else delta / before.value * 100
        entries.append(
            Entry(
                route_id=before.route_id,
                route_label=before.route_label,
                metric_id=before.metric_id,
                metric_label=before.metric_label,
                unit=before.unit,
                base=before.value,
                current=after.value,
                delta=delta,
                delta_percent=delta_percent,
                tier=tier,
                reason=reason,
            )
        )
    return entries


def worst_tier(entries: list[Entry]) -> str:
    """Return the most severe tier present in a collection of report entries."""
    return max((entry.tier for entry in entries), key=lambda tier: TIERS[tier], default="none")


def format_value(value: float, unit: str) -> str:
    """Format a score or millisecond measurement for the Markdown report."""
    if unit == "score":
        return f"{value:.3f}"
    if abs(value) >= MS_PER_SECOND:
        return f"{value / MS_PER_SECOND:.2f} s"
    return f"{value:.0f} ms"


def format_delta(entry: Entry) -> str:
    """Format an entry's absolute and relative changes as report text."""
    sign = "+" if entry.delta > 0 else ""
    value = format_value(entry.delta, entry.unit)
    percent = "new" if entry.delta_percent is None else f"{entry.delta_percent:+.1f}%"
    return f"{sign}{value} ({percent})"


def format_delta_cell(entry: Entry) -> str:
    """Render a delta with the report color associated with its direction."""
    delta = format_delta(entry)
    if entry.delta > 0:
        return f'<font color="#c05640">{delta}</font>'
    if entry.delta < 0:
        return f'<font color="#2f855a">{delta}</font>'
    return delta


def tier_cell(tier: str) -> str:
    """Render a performance tier with its status symbol and human-readable label."""
    symbols = {"none": "✔", "info": "💬", "significant": "⚠", "critical": "✗"}
    return f"{symbols[tier]} {TIER_LABELS[tier]}"


def sorted_regressions(entries: list[Entry]) -> list[Entry]:
    """Return regressed entries ordered from the most to least severe."""
    return sorted(
        (entry for entry in entries if entry.tier != "none"),
        key=lambda entry: (
            TIERS[entry.tier],
            entry.delta_percent if entry.delta_percent is not None else float("inf"),
            entry.delta,
        ),
        reverse=True,
    )


def report_table(
    entries: list[Entry], *, include_route: bool = True, navigation: bool = False
) -> list[str]:
    """Render report entries as a navigation, routed, or metric-only Markdown table."""
    if navigation:
        lines = [
            "| Navigation | main | PR | Δ | Tier |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    elif include_route:
        lines = [
            "| Route / interaction | Metric | main | PR | Δ | Tier |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
    else:
        lines = [
            "| Metric | main | PR | Δ | Tier |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    for entry in entries:
        if navigation:
            first_column = entry.route_label
        elif include_route:
            first_column = f"{entry.route_label} | {entry.metric_label}"
        else:
            first_column = entry.metric_label
        lines.append(
            f"| {first_column} | {format_value(entry.base, entry.unit)} | "
            f"{format_value(entry.current, entry.unit)} | {format_delta_cell(entry)} | "
            f"{tier_cell(entry.tier)} |"
        )
    return lines


def report_sections(entries: list[Entry]) -> list[str]:
    """Group navigation and page measurements into Markdown report sections."""
    lines: list[str] = []
    navigation = [entry for entry in entries if entry.metric_id == "navigation"]
    pages: dict[str, list[Entry]] = {}
    for entry in entries:
        if entry.metric_id != "navigation":
            pages.setdefault(entry.route_id, []).append(entry)

    if navigation:
        lines.extend(
            ["### Navigation scenarios", "", *report_table(navigation, navigation=True), ""]
        )
    for page_entries in pages.values():
        lines.extend(
            [
                f"### {page_entries[0].route_label}",
                "",
                *report_table(page_entries, include_route=False),
                "",
            ]
        )
    return lines


def render_standards(config: dict[str, JsonValue]) -> list[str]:
    """Render standards."""
    _, _, metrics = config_parts(config)
    lines = [
        "<details>",
        "<summary>Blocking standards</summary>",
        "",
        "The CI fails only for a Critical verdict or a measurement failure. "
        "None, Info, and Significant verdicts remain green.",
        "",
    ]
    for metric_id, metric in metrics.items():
        label = string_value(metric.get("label"), f"{metric_id} label")
        noise = format_value(
            number_value(metric.get("noiseAbsolute"), "noiseAbsolute"),
            string_value(metric.get("unit"), "unit"),
        )
        policy = metric.get("policy")
        if policy == "ttfb":
            critical_percent = number_value(metric.get("criticalPercent"), "criticalPercent")
            critical_absolute = format_value(
                number_value(metric.get("criticalAbsolute"), "criticalAbsolute"),
                string_value(metric.get("unit"), "unit"),
            )
            poor = format_value(
                number_value(metric.get("poor"), "poor"),
                string_value(metric.get("unit"), "unit"),
            )
            lines.append(
                f"- **{label}:** more than {critical_percent:.0f}% slower and at least "
                f"+{critical_absolute}, or enters the poor band (≥ {poor}) with at least +{noise}."
            )
            continue

        critical_percent = number_value(metric.get("criticalPercent"), "criticalPercent")
        line = f"- **{label}:** more than {critical_percent:.0f}% slower and at least +{noise}"
        if metric.get("poor") is not None:
            poor = format_value(
                number_value(metric.get("poor"), "poor"),
                string_value(metric.get("unit"), "unit"),
            )
            line += f", or crosses into the poor band (≥ {poor}) after clearing +{noise}"
        lines.append(line + ".")

    lines.extend(
        [
            "- **Measurement failure:** the collector or comparator exits with status 2 and the CI "
            "fails; this is reported separately from a product regression.",
            "",
            "</details>",
        ]
    )
    return lines


def render_report(
    entries: list[Entry],
    verdict: str,
    *,
    comment: bool,
    config: dict[str, JsonValue] | None = None,
) -> str:
    """Render report."""
    emoji = TIER_EMOJI[verdict]
    if comment:
        lines = [COMMENT_MARKER, "", f"## {emoji} Frontend performance", ""]
    else:
        lines = [f"## {emoji} Frontend performance", ""]

    if verdict == "critical":
        lines.extend(
            [
                "> [!CAUTION]",
                "> A critical runtime performance regression was detected. Fix the highlighted "
                "route or metric before merging.",
                "",
            ]
        )
    elif verdict == "significant":
        lines.extend(
            [
                "> [!WARNING]",
                "> Runtime performance regressed noticeably. The check still passes, but the "
                "change should be reviewed.",
                "",
            ]
        )
    elif verdict == "info":
        lines.extend(
            [
                "A small regression exceeded the configured noise floor. The check still passes.",
                "",
            ]
        )
    else:
        lines.extend(["No meaningful runtime performance regression was detected.", ""])

    regressions = sorted_regressions(entries)
    if regressions:
        lines.extend(["**Biggest regressions:**", ""])
        for entry in regressions[:5]:
            lines.append(
                f"- {entry.route_label} · {entry.metric_label}: "
                f"{format_value(entry.base, entry.unit)} → "
                f"{format_value(entry.current, entry.unit)} · {format_delta(entry)} — "
                f"{entry.reason}"
            )
        lines.append("")

    if comment:
        lines.extend(["<details>", "<summary>Full performance report</summary>", ""])
    lines.extend(report_table(entries) if comment else report_sections(entries))
    if comment:
        lines.extend(["", "</details>"])
    elif config is not None:
        lines.extend(["", *render_standards(config)])
    return "\n".join(lines).rstrip() + "\n"


def write_json(path: Path, value: JsonValue) -> None:
    """Write json."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_outputs(
    output: Path,
    entries: list[Entry],
    verdict: str,
    context: PerformanceOutputContext,
) -> None:
    """Write outputs."""
    output.mkdir(parents=True, exist_ok=True)
    report: dict[str, JsonValue] = {
        "schemaVersion": SCHEMA_VERSION,
        "prNumber": context.pr_number,
        "headSha": context.head_sha,
        "verdict": verdict,
        "commentRequired": verdict != "none",
        "entries": [asdict(entry) for entry in entries],
    }
    write_json(output / "report.json", report)
    (output / "summary.md").write_text(
        render_report(entries, verdict, comment=False, config=context.config)
    )
    (output / "comment.md").write_text(
        "" if verdict == "none" else render_report(entries, verdict, comment=True)
    )


def write_error(output: Path, message: str, pr_number: int, head_sha: str) -> None:
    """Write error."""
    output.mkdir(parents=True, exist_ok=True)
    longest_backtick_run = max(
        (len(run) for run in re.findall(r"`+", message)),
        default=0,
    )
    fence = "`" * max(3, longest_backtick_run + 1)
    summary = (
        "## Frontend performance\n\n"
        "### ❌ Measurement failure\n\n"
        "The performance comparison could not finish. This is an infrastructure or "
        "measurement failure, not a detected product regression.\n\n"
        f"{fence}text\n{message}\n{fence}\n"
    )
    comment = (
        f"{COMMENT_MARKER}\n"
        "## ❌ Frontend performance — measurement failure\n\n"
        "> [!CAUTION]\n"
        "> The performance comparison could not finish. Check the workflow logs and rerun it; "
        "this does not mean that a product regression was measured.\n"
    )
    report: dict[str, JsonValue] = {
        "schemaVersion": SCHEMA_VERSION,
        "prNumber": pr_number,
        "headSha": head_sha,
        "verdict": "error",
        "commentRequired": True,
        "message": message,
        "entries": [],
    }
    write_json(output / "report.json", report)
    (output / "summary.md").write_text(summary)
    (output / "comment.md").write_text(comment)


def parse_args() -> argparse.Namespace:
    """Parse args."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--base-dir", type=Path, required=True)
    compare.add_argument("--pr-dir", type=Path, required=True)
    compare.add_argument("--config", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    compare.add_argument("--pr-number", type=int, default=0)
    compare.add_argument("--head-sha", default="")

    error = subparsers.add_parser("error")
    error.add_argument("--output", type=Path, required=True)
    error.add_argument("--message", required=True)
    error.add_argument("--pr-number", type=int, default=0)
    error.add_argument("--head-sha", default="")
    return parser.parse_args()


def main() -> int:
    """Run this module as a CLI entrypoint and return its exit code."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args()
    if args.command == "error":
        write_error(args.output, args.message, args.pr_number, args.head_sha)
        return 0

    config = object_value(decode_json(args.config), "config")
    base = load_measurements(args.base_dir, config)
    current = load_measurements(args.pr_dir, config)
    entries = compare_measurements(base, current, config)
    verdict = worst_tier(entries)
    write_outputs(
        args.output,
        entries,
        verdict,
        PerformanceOutputContext(args.pr_number, args.head_sha, config),
    )
    return 1 if verdict == "critical" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, LookupError, TypeError, RuntimeError) as error:
        logger.exception("frontend performance")
        raise SystemExit(2) from error
