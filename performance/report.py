import argparse
import json
import pathlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Result:
    journal: str
    workload: str
    vus: int
    requests: int
    rps: float
    p50: float
    p90: float
    p95: float
    p99: float
    maximum: float
    errors: float
    cpu_seconds: float
    peak_memory_mb: float
    service_resources: str
    passed: bool


NAME = re.compile(r"^(DELETE|WAL)-(auth|read|write|import|e2e)-(\d+)\.json$")


def value(values: dict[str, float], *keys: str) -> float:
    for key in keys:
        if key in values:
            return float(values[key])
    return 0.0


def metric_values(metric: dict) -> dict:
    return metric.get("values", metric)


def thresholds_pass(metric: dict | None) -> bool:
    if not metric:
        return True
    for threshold in metric.get("thresholds", {}).values():
        if isinstance(threshold, dict):
            if not threshold.get("ok", False):
                return False
        elif threshold:
            return False
    return True


def size_mb(raw: str) -> float:
    match = re.match(r"([0-9.]+)\s*([KMGT]?i?B)", raw)
    if not match:
        return 0.0
    number = float(match.group(1))
    unit = match.group(2)
    factors = {"B": 1 / 1_000_000, "kB": 1 / 1000, "KB": 1 / 1000, "KiB": 1 / 1024, "MB": 1, "MiB": 1.048576, "GB": 1000, "GiB": 1073.741824}
    return number * factors.get(unit, 0)


def seconds(raw: str) -> float | None:
    matches = list(re.finditer(r"([0-9.]+)(ns|µs|us|ms|s|m|h)", raw))
    if not matches or "".join(match.group(0) for match in matches) != raw:
        return None
    factors = {"ns": 1e-9, "µs": 1e-6, "us": 1e-6, "ms": 1e-3, "s": 1, "m": 60, "h": 3600}
    return sum(float(match.group(1)) * factors[match.group(2)] for match in matches)


def service_name(name: str) -> str:
    if "_back_" in name or name.endswith("-back"):
        return "back"
    if "_front_" in name or name.endswith("-front"):
        return "front"
    return name


def resources(path: pathlib.Path) -> tuple[float, float, str]:
    cpu_seconds = 0.0
    peak_memory = 0.0
    samples = []
    cpu_times: dict[str, list[float]] = {}
    peak_by_service: dict[str, float] = {}
    if not path.exists():
        return cpu_seconds, peak_memory, "-"
    for line in path.read_text().splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        containers = payload.get("containers", [])
        if isinstance(containers, dict):
            containers = [containers]
        cpu = 0.0
        memory = 0.0
        for container in containers:
            name = str(container.get("Name", container.get("name", "unknown")))
            service = service_name(name)
            cpu_time = seconds(str(container.get("cpu_time", "")))
            if cpu_time is not None:
                cpu_times.setdefault(name, []).append(cpu_time)
            cpu_raw = str(
                container.get(
                    "CPUPerc",
                    container.get("CPU", container.get("cpu_percent", "0")),
                )
            ).rstrip("%")
            memory_raw = str(
                container.get(
                    "MemUsage",
                    container.get("MemUsageBytes", container.get("mem_usage", "0")),
                )
            ).split("/")[0].strip()
            try:
                cpu += float(cpu_raw)
            except ValueError:
                pass
            memory += size_mb(memory_raw)
            peak_by_service[service] = max(peak_by_service.get(service, 0), size_mb(memory_raw))
        samples.append((int(payload.get("sampled_at", 0)), cpu, memory))
        peak_memory = max(peak_memory, memory)
    for current, following in zip(samples, samples[1:], strict=False):
        cpu_seconds += current[1] / 100 * max(0, following[0] - current[0])
    if cpu_times:
        cpu_by_service = {
            service_name(name): max(values) - min(values)
            for name, values in cpu_times.items()
        }
        cpu_seconds = sum(cpu_by_service.values())
    else:
        cpu_by_service = {}
    services = "; ".join(
        f"{service} {cpu_by_service.get(service, 0):.1f}s/{memory:.1f}MB"
        for service, memory in sorted(peak_by_service.items())
    )
    return cpu_seconds, peak_memory, services or "-"


def load(path: pathlib.Path) -> Result | None:
    match = NAME.match(path.name)
    if not match:
        return None
    journal, workload, vus_raw = match.groups()
    payload = json.loads(path.read_text())
    metrics = payload["metrics"]
    duration_metric = metrics.get(
        "operation_duration",
        metrics.get("journey_duration", metrics["http_req_duration"]),
    )
    duration_values = metric_values(duration_metric)
    request_metric = metrics.get("workload_requests", metrics["http_reqs"])
    requests = int(value(metric_values(request_metric), "count"))
    error_metric = metrics.get(
        "operation_errors",
        metrics.get("journey_errors", metrics["http_req_failed"]),
    )
    error_values = metric_values(error_metric)
    errors = value(error_values, "rate", "value")
    cpu_seconds, peak_memory, service_resources = resources(
        path.with_name(path.stem + "-resources.jsonl")
    )
    threshold_metrics = [metrics.get("checks"), metrics.get("operation_errors"), metrics.get("journey_errors"), metrics.get("operation_duration"), metrics.get("journey_duration")]
    passed = all(thresholds_pass(item) for item in threshold_metrics)
    return Result(
        journal=journal,
        workload=workload,
        vus=int(vus_raw),
        requests=requests,
        rps=value(metric_values(request_metric), "rate"),
        p50=value(duration_values, "med", "p(50)"),
        p90=value(duration_values, "p(90)"),
        p95=value(duration_values, "p(95)"),
        p99=value(duration_values, "p(99)"),
        maximum=value(duration_values, "max"),
        errors=errors,
        cpu_seconds=cpu_seconds,
        peak_memory_mb=peak_memory,
        service_resources=service_resources,
        passed=passed,
    )


def render(results: list[Result]) -> str:
    lines = [
        "# Performance summary",
        "",
        "| Journal | Workload | VUs | Requests | RPS | p50 ms | p90 ms | p95 ms | p99 ms | Max ms | Errors | CPU-s | Req/CPU-s | Peak RAM MB | Per-service CPU-s / peak MB | Verdict |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for result in sorted(results, key=lambda item: (item.journal, item.workload, item.vus)):
        lines.append(
            f"| {result.journal} | {result.workload} | {result.vus} | {result.requests} | {result.rps:.1f} | {result.p50:.0f} | {result.p90:.0f} | {result.p95:.0f} | {result.p99:.0f} | {result.maximum:.0f} | {result.errors:.2%} | {result.cpu_seconds:.1f} | {result.requests / result.cpu_seconds if result.cpu_seconds else 0:.1f} | {result.peak_memory_mb:.1f} | {result.service_resources} | {'pass' if result.passed else 'fail'} |"
        )
    lines.extend(
        [
            "",
            "## Saturation",
            "",
            "| Journal | Workload | Result |",
            "| --- | --- | --- |",
        ]
    )
    groups: dict[tuple[str, str], list[Result]] = {}
    for result in results:
        groups.setdefault((result.journal, result.workload), []).append(result)
    for (journal, workload), group in sorted(groups.items()):
        ordered = sorted(group, key=lambda item: item.vus)
        first_failure = next((item for item in ordered if not item.passed), None)
        passing = [item.vus for item in ordered if item.passed and (first_failure is None or item.vus < first_failure.vus)]
        if first_failure is None:
            saturation = f"≥ {max(passing)} VUs"
        elif passing:
            saturation = f"{max(passing)} VUs; first failure at {first_failure.vus}"
        else:
            saturation = f"< {first_failure.vus} VUs"
        lines.append(f"| {journal} | {workload} | {saturation} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    results = [result for path in args.input.glob("*.json") if (result := load(path))]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(results))


if __name__ == "__main__":
    main()
