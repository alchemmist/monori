import json
import pathlib

import pytest
from performance import report


def test_report_renders_percentiles_and_verdict(tmp_path: pathlib.Path) -> None:
    payload = {
        "metrics": {
            "http_reqs": {"values": {"count": 120, "rate": 12.5}},
            "http_req_duration": {
                "values": {"med": 10, "p(90)": 20, "p(95)": 30, "p(99)": 40, "max": 50}
            },
            "http_req_failed": {"values": {"rate": 0}},
            "checks": {"values": {"rate": 1}, "thresholds": {"rate>0.995": {"ok": True}}},
            "operation_duration": {
                "values": {"med": 11, "p(90)": 21, "p(95)": 31, "p(99)": 41, "max": 51},
                "thresholds": {"p(95)<300": {"ok": True}},
            },
            "operation_errors": {
                "values": {"rate": 0},
                "thresholds": {"rate<0.005": {"ok": True}},
            },
        }
    }
    source = tmp_path / "DELETE-read-10.json"
    source.write_text(json.dumps(payload))
    resources = tmp_path / "DELETE-read-10-resources.jsonl"
    resources.write_text(
        "\n".join(
            json.dumps(sample)
            for sample in (
                {
                    "sampled_at": 1,
                    "containers": [
                        {
                            "Name": "monori-load-delete-back-1",
                            "cpu_time": "1s",
                            "MemUsage": "80MiB / 2GiB",
                        },
                        {
                            "Name": "monori-load-delete-front-1",
                            "cpu_time": "0.5s",
                            "MemUsage": "40MiB / 2GiB",
                        },
                    ],
                },
                {
                    "sampled_at": 2,
                    "containers": [
                        {
                            "Name": "monori-load-delete-back-1",
                            "cpu_time": "3.5s",
                            "MemUsage": "100MiB / 2GiB",
                        },
                        {
                            "Name": "monori-load-delete-front-1",
                            "cpu_time": "1.5s",
                            "MemUsage": "50MiB / 2GiB",
                        },
                    ],
                },
            )
        )
    )
    result = report.load(source)
    assert result is not None
    assert result.p95 == 31
    assert result.passed
    assert result.cpu_seconds == pytest.approx(3.5)
    assert result.peak_memory_mb == pytest.approx(157.2864)
    assert "back 2.5s/104.9MB" in result.service_resources
    assert "front 1.0s/52.4MB" in result.service_resources
    assert "| DELETE | read | 10 |" in report.render([result])


def test_resource_duration_accepts_compound_container_time() -> None:
    assert report.seconds("1m2.5s") == 62.5
    assert report.seconds("16.5ms") == 0.0165
